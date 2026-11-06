"""Additive, transactional migrations; existing databases are backed up first."""
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
import uuid
from .schema import SCHEMA
from ..events import emit

REFERENCE_SCHEMA = """
CREATE TABLE exchanges (
    exchange_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    market_type TEXT NOT NULL
);
CREATE TABLE assets (
    asset_id TEXT PRIMARY KEY,
    exchange_id TEXT NOT NULL REFERENCES exchanges(exchange_id),
    native_symbol TEXT NOT NULL,
    UNIQUE(exchange_id, native_symbol)
);
CREATE TABLE metadata_sources (
    id INTEGER PRIMARY KEY,
    file_path TEXT NOT NULL UNIQUE,
    sha256 TEXT NOT NULL,
    retrieved_at_ms INTEGER NOT NULL,
    payload_json TEXT NOT NULL
);
CREATE TABLE contracts (
    symbol TEXT PRIMARY KEY,
    exchange_id TEXT NOT NULL REFERENCES exchanges(exchange_id),
    base_asset_id TEXT NOT NULL REFERENCES assets(asset_id),
    quote_asset_id TEXT NOT NULL REFERENCES assets(asset_id),
    margin_asset_id TEXT NOT NULL REFERENCES assets(asset_id),
    contract_type TEXT NOT NULL,
    status TEXT NOT NULL,
    price_tick TEXT NOT NULL,
    quantity_step TEXT NOT NULL,
    contract_size TEXT,
    underlying_multiplier TEXT,
    multiplier_evidence TEXT,
    source_id INTEGER NOT NULL REFERENCES metadata_sources(id),
    retrieved_at_ms INTEGER NOT NULL,
    specification_json TEXT NOT NULL
);
"""
LATEST_VERSION = 2

def backup_database(path, directory=None):
    path = Path(path)
    directory = Path(directory) if directory else path.parent / "backups"
    directory.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    target = directory / f"{path.stem}-{stamp}-{uuid.uuid4().hex[:8]}.sqlite3"
    with sqlite3.connect(path.resolve().as_uri()+"?mode=ro", uri=True) as source:
        with sqlite3.connect(target) as dest:
            source.backup(dest)
            if dest.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise RuntimeError("Backup integrity check failed")
    emit("migration", "backup_created", path=str(target))
    return target

def apply_migrations(connection, path=None):
    if connection.in_transaction:
        raise RuntimeError("Migrations require a connection outside a transaction")
    version = connection.execute("PRAGMA user_version").fetchone()[0]
    if version > LATEST_VERSION:
        raise RuntimeError(f"Unsupported future schema version: {version}")
    if version == LATEST_VERSION:
        return
    if path and Path(path).exists() and connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' LIMIT 1"
    ).fetchone():
        backup_database(path)
    # executescript starts its own transaction. Explicit rollback protects DDL as well as version.
    script = "BEGIN IMMEDIATE;\n"
    if version < 1:
        script += SCHEMA
    if version < 2:
        script += REFERENCE_SCHEMA
    script += f"PRAGMA user_version={LATEST_VERSION};\nCOMMIT;"
    try:
        connection.executescript(script)
    except Exception:
        connection.rollback()
        raise
    emit("migration", "schema_updated", previous_version=version, version=LATEST_VERSION)
