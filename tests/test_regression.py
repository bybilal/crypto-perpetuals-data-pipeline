# Import copy for use below.
import copy
# Import json for use below.
import json
# Import sqlite3 for use below.
import sqlite3
# Import datetime, timezone from datetime for use below.
from datetime import datetime, timezone
# Import Decimal from decimal for use below.
from decimal import Decimal
# Import pytest for use below.
import pytest
# Import normalize_market_data for use below.
import normalize_market_data as normal
# Import load_sqlite for use below.
import load_sqlite as loader
# Import run_pipeline for use below.
import run_pipeline as pipeline
# Import count_with_growth, GROWTH_COLOR from format_market_data for use below.
from format_market_data import count_with_growth, GROWTH_COLOR

# Define test native units and exact decimals with the inputs listed below.
@pytest.mark.parametrize("symbol", ["BTCUSDT", "1000PEPEUSDT"])
def test_native_units_and_exact_decimals(samples, symbol):
    # Read samples[symbol + '_oi'][0] from the source data; store the result in oi.
    oi = samples[symbol + "_oi"][0]
    # Validate OI fields and preserve native decimal units and exact time alignment; store the result in row.
    row = normal.normalize_oi(oi, symbol)
    # Verify the expected condition: row['oi_quantity'] == oi['sumOpenInterest'].
    assert row["oi_quantity"] == oi["sumOpenInterest"]
    # Verify the expected condition: row['oi_notional_quote'] == oi['sumOpenInterestValue'].
    assert row["oi_notional_quote"] == oi["sumOpenInterestValue"]
    # Read samples[symbol + '_klines'][0] from the source data; store the result in k.
    k = samples[symbol + "_klines"][0]
    # Validate five-minute candle boundaries, prices and volume constraints; store the result in row.
    row = normal.normalize_kline(k, symbol)
    # Verify the expected condition: row['base_volume'] == k[5].
    assert row["base_volume"] == k[5]
    # Verify the expected condition: row['quote_volume'] == k[7].
    assert row["quote_volume"] == k[7]
    # Verify the expected condition: row['close_price'] == k[4].
    assert row["close_price"] == k[4]
    # Verify the expected condition: row['bucket_end_ms'] == k[0] + 300000 == k[6] + 1.
    assert row["bucket_end_ms"] == k[0] + 300000 == k[6] + 1
    # Verify normalization preserves the quote-volume delta calculation.
    assert Decimal(row["taker_buy_quote"]) * 2 - Decimal(row["quote_volume"]) == Decimal(k[10])*2-Decimal(k[7])

# Define test bad numbers with the inputs listed below.
@pytest.mark.parametrize("value", ["NaN", "Infinity", "-1", "bad"])
def test_bad_numbers(value):
    # Check that this invalid input raises the expected exception.
    with pytest.raises(ValueError): normal.decimal_text(value, "test")

# Define test precision with the inputs listed below.
def test_precision():
    # Use the explicit text '12345678901234567890.00000000000000000001'; store the result in value.
    value = "12345678901234567890.00000000000000000001"
    # Verify the expected condition: normal.decimal_text(value, 'test') == value.
    assert normal.decimal_text(value, "test") == value

# Define test oi alignment and symbol with the inputs listed below.
def test_oi_alignment_and_symbol(samples):
    # Call copy.deepcopy with the supplied arguments; store the result in row.
    row = copy.deepcopy(samples["BTCUSDT_oi"][0])
    # Set the explicit starting value; store the result in row['timestamp'].
    row["timestamp"] = 300001
    # Verify the expected condition: normal.normalize_oi(row, 'BTCUSDT')['bucket_end_ms'] is None.
    assert normal.normalize_oi(row, "BTCUSDT")["bucket_end_ms"] is None
    # Check that this invalid input raises the expected exception.
    with pytest.raises(ValueError): normal.normalize_oi(row, "1000PEPEUSDT")

# Define test invalid candles with the inputs listed below.
@pytest.mark.parametrize("index,value", [(0,1),(6,1),(2,"0.01"),(3,"99999999"),(5,"-1"),(9,"9999999999999999"),(10,"999999999999999999"),(8,-1)])
def test_invalid_candles(samples,index,value):
    # Call copy.deepcopy with the supplied arguments; store the result in row.
    row = copy.deepcopy(samples["BTCUSDT_klines"][0]); row[index]=value
    # Check that this invalid input raises the expected exception.
    with pytest.raises(ValueError): normal.normalize_kline(row,"BTCUSDT")

# Define test filename time with the inputs listed below.
def test_filename_time():
    # Verify the expected condition: loader.filename_timestamp_ms('20261106T190812555577Z') == 1793992092555.
    assert loader.filename_timestamp_ms("20261106T190812555577Z") == 1793992092555
    # Verify the expected condition: loader.filename_timestamp_ms('20261106T190812Z') == 1793992092000.
    assert loader.filename_timestamp_ms("20261106T190812Z") == 1793992092000

# Define sandbox with the inputs listed below.
@pytest.fixture
def sandbox(tmp_path, monkeypatch, samples):
    # Construct the path or ratio from the specified components; store the result in raw.
    raw=tmp_path/"data/raw"; raw.mkdir(parents=True)
    # Construct the path or ratio from the specified components; store the result in db.
    db=tmp_path/"test.sqlite3"
    # Process each module from (loader, pipeline).
    for module in (loader,pipeline):
        # Call monkeypatch.setattr with the supplied arguments.
        monkeypatch.setattr(module,"RAW_DIR",raw)
        # Call monkeypatch.setattr with the supplied arguments.
        monkeypatch.setattr(module,"DB_PATH",db)
    # Call monkeypatch.setattr with the supplied arguments.
    monkeypatch.setattr(loader,"PROJECT_ROOT",tmp_path)
    # Call copy.deepcopy with the supplied arguments; store the result in k.
    k=copy.deepcopy(samples["BTCUSDT_klines"][0])
    # Calculate k[0] + 300000; store the result in end.
    end=k[0]+300000
    # Format the timestamp using the explicit date/time pattern; store the result in stamp.
    stamp=datetime.fromtimestamp(end/1000,tz=timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    # Call copy.deepcopy with the supplied arguments; store the result in oi.
    oi=copy.deepcopy(samples["BTCUSDT_oi"][0]); oi["timestamp"]=end
    # Call dict with the supplied arguments; store the result in unaligned.
    unaligned=dict(oi,timestamp=end+1)
    # Call copy.deepcopy with the supplied arguments; store the result in future.
    future=copy.deepcopy(k); future[0]+=300000; future[6]+=300000
    # Process each (kind, rows) from [('oi', [oi, oi, unaligned]), ('klines', [k, k, future])].
    for kind,rows in [("oi",[oi,oi,unaligned]),("klines",[k,k,future])]:
        # Write the specified text to the file.
        (raw/f"BTCUSDT_{kind}_{stamp}.json").write_text(json.dumps(rows))
    # Return (raw, db) to the caller.
    return raw,db

# Define test dedup joins boundaries and checksum with the inputs listed below.
def test_dedup_joins_boundaries_and_checksum(sandbox):
    # Use sandbox; store the result in (raw, db).
    raw,db=sandbox
    # Open a database transaction context; commit on success or roll back on failure.
    with sqlite3.connect(db) as c:
        # Enable SQLite foreign-key validation for this connection.
        c.execute("PRAGMA foreign_keys=ON"); c.executescript(loader.SCHEMA)
        # Validate saved raw files and insert previously unseen observations; store the result in first.
        first=loader.load_files(c); second=loader.load_files(c)
        # Verify the expected condition: first['oi_inserted'] == 2 and first['candles_inserted'] == 1.
        assert first["oi_inserted"]==2 and first["candles_inserted"]==1
        # Verify the expected condition: first['incomplete_candles_skipped'] == 1.
        assert first["incomplete_candles_skipped"]==1
        # Verify the expected condition: second['oi_inserted'] == second['candles_inserted'] == 0.
        assert second["oi_inserted"]==second["candles_inserted"]==0
        # Verify the expected condition: loader.database_snapshot(c)['contracts']['BTCUSDT']['aligned'] == 1.
        assert loader.database_snapshot(c)["contracts"]["BTCUSDT"]["aligned"]==1
        # Verify the expected condition: c.execute('PRAGMA foreign_key_check').fetchall() == [].
        assert c.execute("PRAGMA foreign_key_check").fetchall()==[]
        # Call next with the supplied arguments; store the result in path.
        path=next(raw.glob("*oi*")); path.write_text("[]")
        # Verify the expected condition: loader.load_files(c)['oi_inserted'] == 0.
        assert loader.load_files(c)["oi_inserted"]==0
        # Verify the expected condition: c.execute('SELECT count(*) FROM oi_observations').fetchone()[0] == 2.
        assert c.execute("SELECT count(*) FROM oi_observations").fetchone()[0]==2

# Define test offline pipeline with the inputs listed below.
def test_offline_pipeline(sandbox,monkeypatch,capsys):
    # Define fail with the inputs listed below.
    def fail(): raise AssertionError("offline called fetch")
    # Call monkeypatch.setattr with the supplied arguments.
    monkeypatch.setattr(pipeline,"fetch_market_data",fail)
    # Coordinate fetch, normalization, database storage and terminal reporting.
    pipeline.run_pipeline(offline=True)
    # Use capsys.readouterr().out; store the result in text.
    text=capsys.readouterr().out
    # Verify the expected condition: 'Pipeline completed' in text and 'Offline' in text.
    assert "Pipeline completed" in text and "Offline" in text
    # Open a database transaction context; commit on success or roll back on failure.
    with sqlite3.connect(sandbox[1]) as c:
        # Verify the expected condition: c.execute('SELECT count(*) FROM price_candles').fetchone()[0] == 1.
        assert c.execute("SELECT count(*) FROM price_candles").fetchone()[0]==1

# Define test growth style with the inputs listed below.
def test_growth_style():
    # Build a count label with a pastel-green increment only when growth is positive; store the result in text.
    text=count_with_growth(12,3)
    # Verify the expected condition: text.plain == '12  +3'.
    assert text.plain=="12  +3"
    # Verify the expected condition: text.spans[0].style == GROWTH_COLOR == '#72D9A4'.
    assert text.spans[0].style==GROWTH_COLOR=="#72D9A4"
    # Verify the expected condition: count_with_growth(12, 0).plain == '12'.
    assert count_with_growth(12,0).plain=="12"

# Define test old one minute files and invalid records with the inputs listed below.
def test_old_one_minute_files_and_invalid_records(sandbox,samples):
    # Use sandbox; store the result in (raw, db).
    raw,db=sandbox
    # Call copy.deepcopy with the supplied arguments; store the result in k.
    k=copy.deepcopy(samples['BTCUSDT_klines'][0]); k[6]=k[0]+59999
    # Write the specified text to the file.
    (raw/'BTCUSDT_klines_20261106T235900Z.json').write_text(json.dumps([k]))
    # Write the specified text to the file.
    (raw/'BTCUSDT_oi_20261106T235900Z.json').write_text(json.dumps([{'symbol':'BTCUSDT'}]))
    # Open a database transaction context; commit on success or roll back on failure.
    with sqlite3.connect(db) as c:
        # Execute the schema SQL; migration scripts supply their own transaction boundaries.
        c.executescript(loader.SCHEMA)
        # Validate saved raw files and insert previously unseen observations; store the result in stats.
        stats=loader.load_files(c)
        # Verify the expected condition: stats['one_minute_files_skipped'] == 1.
        assert stats['one_minute_files_skipped']==1
        # Verify the expected condition: stats['invalid_records'] == 1.
        assert stats['invalid_records']==1

# Define test integer fields reject truncation with the inputs listed below.
@pytest.mark.parametrize('value', [True,1.5,'1.5',float('inf')])
def test_integer_fields_reject_truncation(samples,value):
    # Call copy.deepcopy with the supplied arguments; store the result in oi.
    oi=copy.deepcopy(samples['BTCUSDT_oi'][0]); oi['timestamp']=value
    # Check that this invalid input raises the expected exception.
    with pytest.raises(ValueError): normal.normalize_oi(oi,'BTCUSDT')
    # Call copy.deepcopy with the supplied arguments; store the result in k.
    k=copy.deepcopy(samples['BTCUSDT_klines'][0]); k[8]=value
    # Check that this invalid input raises the expected exception.
    with pytest.raises(ValueError): normal.normalize_kline(k,'BTCUSDT')

# Define test explicit unit conversion and decimal arithmetic with the inputs listed below.
def test_explicit_unit_conversion_and_decimal_arithmetic():
    # Import underlying_quantity, quote_delta from crypto_pipeline.units for use below.
    from crypto_pipeline.units import underlying_quantity,quote_delta
    # Check that this invalid input raises the expected exception.
    with pytest.raises(ValueError): underlying_quantity('10',None,None)
    # Check that this invalid input raises the expected exception.
    with pytest.raises(ValueError): underlying_quantity('10','1000',None)
    # A synthetic conversion example, NOT evidence for a real contract.
    assert underlying_quantity('1.00000000000000000000000000001','1000','synthetic test')==Decimal('1000.00000000000000000000000001')
    # Verify tiny differences survive arithmetic on very large quote volumes.
    assert quote_delta('100000000000000000000000000000.01','50000000000000000000000000000.01')==Decimal('0.01')

# Define test malformed interval detection with the inputs listed below.
@pytest.mark.parametrize('row', [[0,0,0,0,0,0,float('inf')], {}, None])
def test_malformed_interval_detection(row):
    # Verify the expected condition: loader.detect_interval('klines', [row]) == 'unknown'.
    assert loader.detect_interval('klines',[row])=='unknown'

# Define test sqlite integer overflow is rejected with the inputs listed below.
def test_sqlite_integer_overflow_is_rejected(samples):
    # Call copy.deepcopy with the supplied arguments; store the result in oi.
    oi=copy.deepcopy(samples['BTCUSDT_oi'][0]); oi['timestamp']=2**63
    # Check that this invalid input raises the expected exception.
    with pytest.raises(ValueError): normal.normalize_oi(oi,'BTCUSDT')
