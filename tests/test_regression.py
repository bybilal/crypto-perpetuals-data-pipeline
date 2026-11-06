import copy
import json
import sqlite3
from datetime import datetime, timezone
from decimal import Decimal
import pytest
import normalize_market_data as normal
import load_sqlite as loader
import run_pipeline as pipeline
from format_market_data import count_with_growth, GROWTH_COLOR

@pytest.mark.parametrize("symbol", ["BTCUSDT", "1000PEPEUSDT"])
def test_native_units_and_exact_decimals(samples, symbol):
    oi = samples[symbol + "_oi"][0]
    row = normal.normalize_oi(oi, symbol)
    assert row["oi_quantity"] == oi["sumOpenInterest"]
    assert row["oi_notional_quote"] == oi["sumOpenInterestValue"]
    k = samples[symbol + "_klines"][0]
    row = normal.normalize_kline(k, symbol)
    assert row["base_volume"] == k[5]
    assert row["quote_volume"] == k[7]
    assert row["close_price"] == k[4]
    assert row["bucket_end_ms"] == k[0] + 300000 == k[6] + 1
    assert Decimal(row["taker_buy_quote"]) * 2 - Decimal(row["quote_volume"]) == Decimal(k[10])*2-Decimal(k[7])

@pytest.mark.parametrize("value", ["NaN", "Infinity", "-1", "bad"])
def test_bad_numbers(value):
    with pytest.raises(ValueError): normal.decimal_text(value, "test")

def test_precision():
    value = "12345678901234567890.00000000000000000001"
    assert normal.decimal_text(value, "test") == value

def test_oi_alignment_and_symbol(samples):
    row = copy.deepcopy(samples["BTCUSDT_oi"][0])
    row["timestamp"] = 300001
    assert normal.normalize_oi(row, "BTCUSDT")["bucket_end_ms"] is None
    with pytest.raises(ValueError): normal.normalize_oi(row, "1000PEPEUSDT")

@pytest.mark.parametrize("index,value", [(0,1),(6,1),(2,"0.01"),(3,"99999999"),(5,"-1"),(9,"9999999999999999"),(10,"999999999999999999"),(8,-1)])
def test_invalid_candles(samples,index,value):
    row = copy.deepcopy(samples["BTCUSDT_klines"][0]); row[index]=value
    with pytest.raises(ValueError): normal.normalize_kline(row,"BTCUSDT")

def test_filename_time():
    assert loader.filename_timestamp_ms("20261106T190812555577Z") == 1793992092555
    assert loader.filename_timestamp_ms("20261106T190812Z") == 1793992092000

@pytest.fixture
def sandbox(tmp_path, monkeypatch, samples):
    raw=tmp_path/"data/raw"; raw.mkdir(parents=True)
    db=tmp_path/"test.sqlite3"
    for module in (loader,pipeline):
        monkeypatch.setattr(module,"RAW_DIR",raw)
        monkeypatch.setattr(module,"DB_PATH",db)
    monkeypatch.setattr(loader,"PROJECT_ROOT",tmp_path)
    k=copy.deepcopy(samples["BTCUSDT_klines"][0])
    end=k[0]+300000
    stamp=datetime.fromtimestamp(end/1000,tz=timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    oi=copy.deepcopy(samples["BTCUSDT_oi"][0]); oi["timestamp"]=end
    unaligned=dict(oi,timestamp=end+1)
    future=copy.deepcopy(k); future[0]+=300000; future[6]+=300000
    for kind,rows in [("oi",[oi,oi,unaligned]),("klines",[k,k,future])]:
        (raw/f"BTCUSDT_{kind}_{stamp}.json").write_text(json.dumps(rows))
    return raw,db

def test_dedup_joins_boundaries_and_checksum(sandbox):
    raw,db=sandbox
    with sqlite3.connect(db) as c:
        c.execute("PRAGMA foreign_keys=ON"); c.executescript(loader.SCHEMA)
        first=loader.load_files(c); second=loader.load_files(c)
        assert first["oi_inserted"]==2 and first["candles_inserted"]==1
        assert first["incomplete_candles_skipped"]==1
        assert second["oi_inserted"]==second["candles_inserted"]==0
        assert loader.database_snapshot(c)["contracts"]["BTCUSDT"]["aligned"]==1
        assert c.execute("PRAGMA foreign_key_check").fetchall()==[]
        path=next(raw.glob("*oi*")); path.write_text("[]")
        assert loader.load_files(c)["oi_inserted"]==0
        assert c.execute("SELECT count(*) FROM oi_observations").fetchone()[0]==2

def test_offline_pipeline(sandbox,monkeypatch,capsys):
    def fail(): raise AssertionError("offline called fetch")
    monkeypatch.setattr(pipeline,"fetch_market_data",fail)
    pipeline.run_pipeline(offline=True)
    text=capsys.readouterr().out
    assert "Pipeline completed" in text and "Offline" in text
    with sqlite3.connect(sandbox[1]) as c:
        assert c.execute("SELECT count(*) FROM price_candles").fetchone()[0]==1

def test_growth_style():
    text=count_with_growth(12,3)
    assert text.plain=="12  +3"
    assert text.spans[0].style==GROWTH_COLOR=="#72D9A4"
    assert count_with_growth(12,0).plain=="12"
