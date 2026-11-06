"""Exercise retry bounds, overlap requests, locking and coverage without network access."""
import io
import plistlib
import sqlite3
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlparse
import pytest
from crypto_pipeline import binance
from crypto_pipeline.coverage import recent_coverage
from crypto_pipeline.locking import pipeline_lock
from crypto_pipeline.schedule import launch_agent
from crypto_pipeline.storage.schema import SCHEMA


def test_transient_retries_then_saves_once(tmp_path, monkeypatch):
    # Fail twice, then deliver original bytes on the final permitted attempt.
    calls = []
    waits = []
    def request(*args, **kwargs):
        calls.append(args[0])
        if len(calls) < 3:
            raise URLError('temporary')
        return io.BytesIO(b'[]')
    monkeypatch.setattr(binance, 'RAW_DIR', tmp_path)
    monkeypatch.setattr(binance, 'urlopen', request)
    monkeypatch.setattr(binance, 'sleep', waits.append)
    binance.request_and_save('https://example.invalid', 'BTCUSDT_oi')
    assert len(calls) == 3 and waits == [2, 4]
    assert len(list(tmp_path.iterdir())) == 1


@pytest.mark.parametrize('status', [403, 418, 429, 451])
def test_restrictions_and_limits_are_not_retried(status, tmp_path, monkeypatch):
    # These responses require the normal error path, not immediate repeat requests.
    calls = []
    def request(url, **kwargs):
        calls.append(url)
        raise HTTPError(url, status, 'stop', None, io.BytesIO(b'error'))
    monkeypatch.setattr(binance, 'RAW_DIR', tmp_path)
    monkeypatch.setattr(binance, 'urlopen', request)
    with pytest.raises(HTTPError):
        binance.request_and_save('https://example.invalid', 'BTCUSDT_oi')
    assert len(calls) == 1
    assert not list(tmp_path.iterdir())


def test_retry_exhaustion(tmp_path, monkeypatch):
    # A persistent server error stops after three attempts without saving partial data.
    calls = []
    def request(url, **kwargs):
        calls.append(url)
        raise HTTPError(url, 503, 'temporary', None, io.BytesIO(b'error'))
    monkeypatch.setattr(binance, 'RAW_DIR', tmp_path)
    monkeypatch.setattr(binance, 'urlopen', request)
    monkeypatch.setattr(binance, 'sleep', lambda seconds: None)
    with pytest.raises(HTTPError):
        binance.request_and_save('https://example.invalid', 'BTCUSDT_oi')
    assert len(calls) == 3
    assert not list(tmp_path.iterdir())


def test_overlap_limit_reaches_each_endpoint(tmp_path, monkeypatch):
    # A larger batch must affect all four market-data requests equally.
    urls = []
    def response(url, prefix):
        urls.append(url)
        return [], tmp_path / 'test.json'
    monkeypatch.setattr(binance, 'RAW_DIR', tmp_path)
    monkeypatch.setattr(binance, 'request_and_save', response)
    monkeypatch.setattr(binance, 'fetch_exchange_info', lambda: None)
    monkeypatch.setattr(binance, 'display_response', lambda **kwargs: None)
    assert binance.fetch_market_data(limit=25)['failed_requests'] == 0
    assert len(urls) == 4
    assert all(parse_qs(urlparse(url).query)['limit'] == ['25'] for url in urls)


def test_lock_exclusion_release_and_symlink(tmp_path):
    # The same database must be protected across aliases, and errors must release the lock.
    db = tmp_path / 'data.sqlite3'
    db.touch()
    alias = tmp_path / 'alias.sqlite3'
    alias.symlink_to(db)
    with pytest.raises(ValueError):
        with pipeline_lock(db):
            with pytest.raises(RuntimeError, match='already'):
                with pipeline_lock(alias):
                    pytest.fail('A second writer acquired the lock')
            raise ValueError('simulated failure')
    with pipeline_lock(db):
        pass


def test_coverage_grace_and_independent_streams(tmp_path):
    # Check the exact publication-grace boundary and avoid joining away one stream's gaps.
    db = tmp_path / 'test.sqlite3'
    with sqlite3.connect(db) as c:
        c.executescript(SCHEMA)
        c.execute("INSERT INTO raw_files VALUES (1,'fixture','hash','BTCUSDT','oi','5m',7200000,1)")
        c.execute("INSERT INTO oi_observations VALUES ('BTCUSDT',7200000,7200000,'1','2',NULL,1)")
    before = recent_coverage(db, now_ms=7259999)
    after = recent_coverage(db, now_ms=7260000)
    assert before['last_end_ms'] == 6900000
    assert after['last_end_ms'] == 7200000
    assert after['contracts'][0]['oi'] == 1
    assert after['contracts'][0]['candles'] == 0
    assert len(after['contracts'][0]['oi_missing_ms']) == 11
    assert len(after['contracts'][1]['oi_missing_ms']) == 12


def test_launch_agent_roundtrip_and_schedule(tmp_path):
    # Preserve path arguments and schedule one minute after each five-minute boundary.
    root = tmp_path / 'project with spaces'
    spec = plistlib.loads(plistlib.dumps(launch_agent(root)))
    assert spec['ProgramArguments'][0] == str(root / '.venv/bin/python')
    assert spec['StartCalendarInterval'] == [{'Minute': m} for m in range(1, 60, 5)]
    assert spec['RunAtLoad'] is True
    assert '--limit' in spec['ProgramArguments']
