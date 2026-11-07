"""Database-only foundation tests; synthetic measurements never enter the live database."""
import sqlite3
from decimal import Decimal
import pytest
from crypto_pipeline.storage.migrations import apply_migrations, REFERENCE_SCHEMA
from crypto_pipeline.storage.schema import SCHEMA
from crypto_pipeline.storage.foundation import resolve_asset, measurement_text

@pytest.fixture
def db():
    c = sqlite3.connect(':memory:')
    c.execute('PRAGMA foreign_keys=ON')
    c.executescript(SCHEMA + REFERENCE_SCHEMA + "PRAGMA user_version=2;")
    c.execute("INSERT INTO exchanges VALUES ('binance_usdm','Binance','futures')")
    c.executemany('INSERT INTO assets VALUES (?,?,?)', [('binance_usdm:'+s,'binance_usdm',s) for s in ('BTC','1000PEPE')])
    c.commit()
    yield c
    c.close()

def test_migration_preserves_v2_and_repeats(db):
    before = {t: db.execute('SELECT * FROM '+t).fetchall() for t in ('assets','exchanges','raw_files','oi_observations','price_candles','contracts','metadata_sources')}
    apply_migrations(db)
    for table, rows in before.items():
        assert db.execute('SELECT * FROM '+table).fetchall() == rows
    snapshot = db.iterdump()
    first = list(snapshot)
    apply_migrations(db)
    assert list(db.iterdump()) == first
    assert db.execute('PRAGMA foreign_key_check').fetchall() == []
    assert db.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'

def test_identity_resolution_and_duplicates(db):
    apply_migrations(db)
    assert resolve_asset(db,'binance_usdm:BTC') == 'asset:bitcoin'
    assert resolve_asset(db,'binance_usdm:1000PEPE') is None  # Pending evidence is not a verified conversion.
    assert resolve_asset(db,'BTC') is None
    assert resolve_asset(db,'missing') is None
    assert db.execute("SELECT canonical_id FROM provider_assets WHERE provider_coin_id='pepe'").fetchone()[0]=='asset:pepe'
    with pytest.raises(sqlite3.IntegrityError):
        db.execute("INSERT INTO asset_mappings SELECT * FROM asset_mappings LIMIT 1")
    with pytest.raises(sqlite3.IntegrityError):
        db.execute("INSERT INTO provider_assets VALUES ('coingecko','bad','absent','evidence','2026-11-06')")

def test_nullable_history_currency_and_categories(db):
    apply_migrations(db)
    db.executemany('INSERT INTO market_sources VALUES (?,?,?,?,?)',[(1,'coingecko','capture1',1,'fixture'),(2,'coingecko','capture2',2,'fixture')])
    db.execute("INSERT INTO market_snapshots(provider,provider_coin_id,source_id,currency,price) VALUES ('coingecko','bitcoin',1,'USD',?)",(measurement_text('0.12345678901234567890123456789'),))
    db.execute("INSERT INTO market_snapshots(provider,provider_coin_id,source_id,currency) VALUES ('coingecko','bitcoin',2,'USD')")
    assert db.execute('SELECT market_cap,fdv,circulating_supply FROM market_snapshots').fetchall()==[(None,None,None)]*2
    assert db.execute('SELECT price FROM market_snapshots WHERE source_id=1').fetchone()[0]=='0.12345678901234567890123456789'
    with pytest.raises(sqlite3.IntegrityError):
        db.execute("INSERT INTO market_snapshots(provider,provider_coin_id,source_id,currency) VALUES ('coingecko','pepe',1,'USDT')")
    with pytest.raises(sqlite3.IntegrityError):
        db.execute("INSERT INTO market_snapshots SELECT * FROM market_snapshots LIMIT 1")
    for cat in ('first','second'):
        db.execute('INSERT INTO categories VALUES (?,?,?,?)',('coingecko',cat,cat,1))
        for coin in ('bitcoin','pepe'):
            db.execute('INSERT INTO asset_categories VALUES (?,?,?,?)',('coingecko',coin,cat,1))
    assert db.execute('SELECT count(*) FROM asset_categories').fetchone()[0]==4
    with pytest.raises(sqlite3.IntegrityError):
        db.execute("INSERT INTO asset_categories VALUES ('coingecko','bitcoin','absent',1)")
    assert db.execute('PRAGMA foreign_key_check').fetchall()==[]

@pytest.mark.parametrize('value',[float('nan'),1.2,'NaN','Infinity','-1'])
def test_invalid_decimal(value):
    with pytest.raises(ValueError):
        measurement_text(value)

def test_null_and_exact_decimal():
    assert measurement_text(None) is None
    assert measurement_text(Decimal('1.00000000000000000000000000001'))=='1.00000000000000000000000000001'

def test_fresh_native_mapping_seed_is_repeatable():
    from crypto_pipeline.storage.foundation import seed_native_mappings
    with sqlite3.connect(':memory:') as c:
        c.execute('PRAGMA foreign_keys=ON')
        apply_migrations(c)
        assert resolve_asset(c,'binance_usdm:BTC') is None
        c.execute("INSERT INTO exchanges VALUES ('binance_usdm','Binance','futures')")
        c.execute("INSERT INTO assets VALUES ('binance_usdm:BTC','binance_usdm','BTC')")
        seed_native_mappings(c)
        seed_native_mappings(c)
        assert resolve_asset(c,'binance_usdm:BTC') == 'asset:bitcoin'
        assert c.execute('SELECT count(*) FROM asset_mappings').fetchone()[0] == 1
