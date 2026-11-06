# Import io for use below.
import io
# Import HTTPError from urllib.error for use below.
from urllib.error import HTTPError
# Import binance from crypto_pipeline for use below.
from crypto_pipeline import binance


# Define test raw bytes are saved unchanged with the inputs listed below.
def test_raw_bytes_are_saved_unchanged(tmp_path,monkeypatch):
    # Set the explicit starting value; store the result in payload.
    payload=b'[ {"numeric": "1.00000000001"} ]\n'
    # Call monkeypatch.setattr with the supplied arguments.
    monkeypatch.setattr(binance,'RAW_DIR',tmp_path)
    # Call monkeypatch.setattr with the supplied arguments.
    monkeypatch.setattr(binance,'urlopen',lambda *args,**kwargs: io.BytesIO(payload))
    # Save original response bytes before parsing the returned JSON; store the result in (parsed, path).
    parsed,path=binance.request_and_save('https://example.invalid','BTCUSDT_oi')
    # Verify the expected condition: path.read_bytes() == payload.
    assert path.read_bytes()==payload
    # Verify the expected condition: parsed[0]['numeric'] == '1.00000000001'.
    assert parsed[0]['numeric']=='1.00000000001'


# Define test restricted access is reported without alternate hosts with the inputs listed below.
def test_restricted_access_is_reported_without_alternate_hosts(tmp_path,monkeypatch):
    # Call monkeypatch.setattr with the supplied arguments.
    monkeypatch.setattr(binance,'RAW_DIR',tmp_path)
    # Build the ordered collection used by this operation; store the result in calls.
    calls=[]
    # Define restricted with the inputs listed below.
    def restricted(url,**kwargs):
        # Add this item to the accumulating list.
        calls.append(url)
        # Stop this operation with HTTPError(url, 451, 'Unavailable', None, io.BytesIO(b'restricted access')).
        raise HTTPError(url,451,'Unavailable',None,io.BytesIO(b'restricted access'))
    # Call monkeypatch.setattr with the supplied arguments.
    monkeypatch.setattr(binance,'urlopen',restricted)
    # Fetch and save the configured Binance market-data responses; store the result in stats.
    stats=binance.fetch_market_data()
    # Verify the expected condition: stats == {'successful_requests': 0, 'failed_requests': 5, 'saved_files': 0}.
    assert stats=={'successful_requests':0,'failed_requests':5,'saved_files':0}
    # Verify the expected condition: len(calls) == 5.
    assert len(calls)==5
    # Verify the expected condition: all((url.startswith('https://fapi.binance.com/') for url in calls)).
    assert all(url.startswith('https://fapi.binance.com/') for url in calls)
    # Verify the expected condition: list(tmp_path.iterdir()) == [].
    assert list(tmp_path.iterdir())==[]
