"""Version 3: provider identity and empty historical measurement tables; no network I/O."""
FOUNDATION_SCHEMA = """
CREATE TABLE canonical_assets (
 id TEXT PRIMARY KEY NOT NULL, name TEXT NOT NULL, network TEXT NOT NULL,
 contract_address TEXT, UNIQUE(network, contract_address)
);
CREATE TABLE provider_assets (
 provider TEXT NOT NULL, provider_coin_id TEXT NOT NULL,
 canonical_id TEXT NOT NULL REFERENCES canonical_assets(id),
 evidence TEXT NOT NULL, verified_on TEXT NOT NULL,
 PRIMARY KEY(provider, provider_coin_id), UNIQUE(provider, canonical_id)
);
CREATE TABLE asset_mappings (
 native_asset_id TEXT PRIMARY KEY NOT NULL REFERENCES assets(asset_id),
 canonical_id TEXT NOT NULL REFERENCES canonical_assets(id),
 status TEXT NOT NULL CHECK(status IN ('verified','pending')),
 evidence TEXT NOT NULL, reviewed_on TEXT NOT NULL
);
CREATE TABLE market_sources (
 id INTEGER PRIMARY KEY, provider TEXT NOT NULL,
 source_key TEXT NOT NULL, retrieved_at_ms INTEGER NOT NULL CHECK(retrieved_at_ms>=0),
 sha256 TEXT NOT NULL, UNIQUE(provider, source_key), UNIQUE(id, provider)
);
CREATE TABLE market_snapshots (
 provider TEXT NOT NULL, provider_coin_id TEXT NOT NULL,
 source_id INTEGER NOT NULL, provider_timestamp_ms INTEGER,
 currency TEXT NOT NULL CHECK(currency='USD'),
 price TEXT, market_cap TEXT, fdv TEXT, circulating_supply TEXT,
 total_supply TEXT, max_supply TEXT, volume_24h TEXT,
 PRIMARY KEY(source_id, provider_coin_id, currency),
 FOREIGN KEY(provider, provider_coin_id) REFERENCES provider_assets(provider, provider_coin_id),
 FOREIGN KEY(source_id, provider) REFERENCES market_sources(id, provider),
 CHECK(provider_timestamp_ms IS NULL OR provider_timestamp_ms>=0)
);
CREATE TABLE categories (
 provider TEXT NOT NULL, category_id TEXT NOT NULL, name TEXT NOT NULL,
 source_id INTEGER NOT NULL,
 PRIMARY KEY(provider, category_id),
 FOREIGN KEY(source_id, provider) REFERENCES market_sources(id, provider)
);
CREATE TABLE asset_categories (
 provider TEXT NOT NULL, provider_coin_id TEXT NOT NULL, category_id TEXT NOT NULL,
 source_id INTEGER NOT NULL,
 PRIMARY KEY(provider, provider_coin_id, category_id, source_id),
 FOREIGN KEY(provider, provider_coin_id) REFERENCES provider_assets(provider, provider_coin_id),
 FOREIGN KEY(provider, category_id) REFERENCES categories(provider, category_id),
 FOREIGN KEY(source_id, provider) REFERENCES market_sources(id, provider)
);
INSERT INTO canonical_assets VALUES ('asset:bitcoin','Bitcoin','bitcoin',NULL);
INSERT INTO canonical_assets VALUES ('asset:pepe','Pepe','ethereum','0x6982508145454ce325ddbe47a25d4ec3d2311933');
INSERT INTO provider_assets VALUES ('coingecko','bitcoin','asset:bitcoin','https://www.coingecko.com/en/coins/bitcoin; Bitcoin network identity','2026-11-06');
INSERT INTO provider_assets VALUES ('coingecko','pepe','asset:pepe','https://www.coingecko.com/en/coins/pepe; Ethereum contract 0x6982508145454ce325ddbe47a25d4ec3d2311933','2026-11-06');
INSERT OR IGNORE INTO asset_mappings SELECT asset_id,'asset:bitcoin','verified','https://www.binance.com/en/price/bitcoin; Bitcoin network and named asset, not ticker alone','2026-11-06' FROM assets WHERE asset_id='binance_usdm:BTC';
INSERT OR IGNORE INTO asset_mappings SELECT asset_id,'asset:pepe','pending','https://www.binance.com/en/support/announcement/detail/41993e3389654713946bcb6b9b032eaf; native underlying label confirmed; explicit token-address linkage still required','2026-11-06' FROM assets WHERE asset_id='binance_usdm:1000PEPE';
"""


def resolve_asset(connection, native_asset_id):
    """Only reviewed identities may join market data; never infer from a symbol."""
    row = connection.execute(
        "SELECT canonical_id FROM asset_mappings WHERE native_asset_id=? AND status='verified'",
        (native_asset_id,),
    ).fetchone()
    return row[0] if row else None


def measurement_text(value):
    """Validate nonnegative finite Decimal text without rounding or inventing missing values."""
    from decimal import Decimal
    if value is None:
        return None
    if not isinstance(value, (str, Decimal)):
        raise ValueError('Measurements require decimal strings or Decimal, not floats')
    number = Decimal(value)
    if not number.is_finite() or number < 0:
        raise ValueError('Measurement must be finite and nonnegative')
    return str(value)


def seed_native_mappings(connection):
    """Seed reviewed candidates after native assets exist, including a fresh installation."""
    connection.execute("INSERT OR IGNORE INTO asset_mappings SELECT asset_id,'asset:bitcoin','verified','https://www.binance.com/en/price/bitcoin; Bitcoin network and named asset, not ticker alone','2026-11-06' FROM assets WHERE asset_id='binance_usdm:BTC';")
    connection.execute("INSERT OR IGNORE INTO asset_mappings SELECT asset_id,'asset:pepe','pending','https://www.binance.com/en/support/announcement/detail/41993e3389654713946bcb6b9b032eaf; native underlying label confirmed; explicit token-address linkage still required','2026-11-06' FROM assets WHERE asset_id='binance_usdm:1000PEPE';")
