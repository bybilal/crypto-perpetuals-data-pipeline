import io
from urllib.error import HTTPError
from crypto_pipeline import binance


def test_raw_bytes_are_saved_unchanged(tmp_path,monkeypatch):
    payload=b'[ {"numeric": "1.00000000001"} ]\n'
    monkeypatch.setattr(binance,'RAW_DIR',tmp_path)
    monkeypatch.setattr(binance,'urlopen',lambda *args,**kwargs: io.BytesIO(payload))
    parsed,path=binance.request_and_save('https://example.invalid','BTCUSDT_oi')
    assert path.read_bytes()==payload
    assert parsed[0]['numeric']=='1.00000000001'


def test_restricted_access_is_reported_without_alternate_hosts(tmp_path,monkeypatch):
    monkeypatch.setattr(binance,'RAW_DIR',tmp_path)
    calls=[]
    def restricted(url,**kwargs):
        calls.append(url)
        raise HTTPError(url,451,'Unavailable',None,io.BytesIO(b'restricted access'))
    monkeypatch.setattr(binance,'urlopen',restricted)
    stats=binance.fetch_market_data()
    assert stats=={'successful_requests':0,'failed_requests':5,'saved_files':0}
    assert len(calls)==5
    assert all(url.startswith('https://fapi.binance.com/') for url in calls)
    assert list(tmp_path.iterdir())==[]
