"""Mocked HTTP and temporary SQLite only; no provider requests."""
import hashlib
import json
import sqlite3
from urllib.error import HTTPError
import pytest
from crypto_pipeline import coingecko as client
from crypto_pipeline.storage.coingecko import normalize, ingest
from crypto_pipeline.storage.migrations import apply_migrations

COIN = b'{"id":"bitcoin","categories":["Layer 1"],"market_data":{"current_price":{"usd":123.123456789012345678901},"market_cap":{"usd":1000},"max_supply":null,"last_updated":"2026-11-06T12:00:00.123Z"}}'
CATEGORIES = b'[{"category_id":"layer-1","name":"Layer 1"}]'

@pytest.fixture
def captured(tmp_path,monkeypatch):
    monkeypatch.setattr(client,'request_bytes',lambda endpoint,key: COIN if endpoint.startswith('coins/bitcoin?') else CATEGORIES)
    return client.capture(tmp_path)

@pytest.fixture
def db():
    c=sqlite3.connect(':memory:')
    c.execute('PRAGMA foreign_keys=ON')
    apply_migrations(c)
    yield c
    c.close()

def test_precision_null_timestamp():
    stamp,values,categories=normalize(COIN,CATEGORIES)
    assert stamp==1793966400123
    assert values==['123.123456789012345678901','1000',None,None,None,None,None]
    assert categories==[('layer-1','Layer 1')]

@pytest.mark.parametrize('body',[b'{}',COIN.replace(b'bitcoin',b'pepe'),COIN.replace(b'123.123456789012345678901',b'-1'),COIN.replace(b'123.123456789012345678901',b'NaN'),COIN.replace(b'00.123Z',b'00.123')])
def test_bad_payload(body):
    with pytest.raises((ValueError,TypeError)):
        normalize(body,CATEGORIES)

@pytest.mark.parametrize('categories',[b'[]',b'{}',b'[{"category_id":"a","name":"Layer 1"},{"category_id":"b","name":"Layer 1"}]'])
def test_missing_ambiguous_categories(categories):
    with pytest.raises(ValueError):normalize(COIN,categories)

def rows(db):
    return {t:db.execute('SELECT * FROM '+t).fetchall() for t in ('market_sources','market_snapshots','categories','asset_categories')}

def test_atomic_idempotence_and_provenance(db,captured):
    with db:result=ingest(db,captured)
    assert result['snapshots_added']==1 and result['sources_added']==2
    before=rows(db)
    with db:assert ingest(db,captured)['snapshots_added']==0
    assert rows(db)==before
    assert db.execute('PRAGMA foreign_key_check').fetchall()==[]
    assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
    (captured/'bitcoin.json').write_bytes(b'{}')
    with pytest.raises(ValueError),db:ingest(db,captured)
    assert rows(db)==before

def test_new_capture_keeps_history(db,captured,tmp_path,monkeypatch):
    with db:ingest(db,captured)
    second=client.capture(tmp_path)
    with db:ingest(db,second)
    assert db.execute('SELECT count(*) FROM market_snapshots').fetchone()[0]==2

def test_mapping_error_has_no_partial_writes(db,captured):
    db.execute("DELETE FROM provider_assets WHERE provider_coin_id='bitcoin'")
    db.commit()
    with pytest.raises(ValueError),db:ingest(db,captured)
    assert not db.execute('SELECT * FROM market_sources').fetchall()

@pytest.mark.parametrize('status',[401,403,429,500])
def test_http_failures_bounded_and_redacted(monkeypatch,status):
    calls=[];sleeps=[]
    def fail(request,timeout):
        calls.append(request)
        raise HTTPError(request.full_url,status,'secret-must-not-appear',{},None)
    monkeypatch.setattr(client,'urlopen',fail)
    monkeypatch.setattr(client.time,'sleep',sleeps.append)
    with pytest.raises(RuntimeError) as error:client.request_bytes('coins/bitcoin','fake-demo-secret')
    assert 'secret' not in str(error.value)
    assert len(calls)==(3 if status in (429,500) else 1)
    assert sleeps==([15,30] if status in (429,500) else [])

def test_retry_after_is_respected(monkeypatch):
    def fail(request,timeout):raise HTTPError(request.full_url,429,'limited',{'Retry-After':'120'},None)
    monkeypatch.setattr(client,'urlopen',fail)
    monkeypatch.setattr(client.time,'sleep',lambda _:pytest.fail('Should stop instead of retrying early'))
    with pytest.raises(RuntimeError,match='later retry'):client.request_bytes('coins/bitcoin')

def test_missing_provider_timestamp():
    body=COIN.replace(b',"last_updated":"2026-11-06T12:00:00.123Z"',b'')
    assert normalize(body,CATEGORIES)[0] is None

def test_http_auth_header_and_bytes(monkeypatch):
    class Response:
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def read(self):return COIN
    def opened(request,timeout):
        assert request.get_header('X-cg-demo-api-key')=='test-key'
        assert 'test-key' not in request.full_url
        assert timeout==30
        return Response()
    monkeypatch.setattr(client,'urlopen',opened)
    assert client.request_bytes(client.ENDPOINTS['bitcoin'],'test-key')==COIN

def test_offline_cli_and_logs(captured,tmp_path,monkeypatch):
    import sys
    from crypto_pipeline import coingecko_cli
    monkeypatch.setattr(client,'request_bytes',lambda *a:pytest.fail('Replay must not fetch'))
    monkeypatch.setattr(sys,'argv',['coingecko','--replay',str(captured),'--db-path',str(tmp_path/'db.sqlite3'),'--log-dir',str(tmp_path/'logs'),'--human-log'])
    assert coingecko_cli.main()==0
    events=[json.loads(line) for p in (tmp_path/'logs').glob('*.jsonl') for line in p.read_text().splitlines()]
    assert events[-1]['event']=='completed'
    assert '\x1b' not in next((tmp_path/'logs').glob('*.log')).read_text()
