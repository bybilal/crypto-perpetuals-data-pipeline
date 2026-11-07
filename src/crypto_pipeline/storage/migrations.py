"""Additive, transactional migrations; existing databases are backed up first."""
# Import datetime, timezone from datetime for use below.
from datetime import datetime, timezone
# Import Path from pathlib for use below.
from pathlib import Path
# Import sqlite3 for use below.
import sqlite3
from contextlib import closing
# Import uuid for use below.
import uuid
# Import SCHEMA from .schema for use below.
from .schema import SCHEMA
from .foundation import FOUNDATION_SCHEMA
# Import emit from ..events for use below.
from ..events import emit

# Define the SQLite tables, keys and indexes; field meanings are in docs/data-model.md; store the result in REFERENCE_SCHEMA.
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
# Set the explicit starting value; store the result in LATEST_VERSION.
LATEST_VERSION = 3

# Define backup database with the inputs listed below.
def backup_database(path, directory=None):
    # Represent this filesystem location as a path object; store the result in path.
    path = Path(path)
    # Choose the value according to directory; store the result in directory.
    directory = Path(directory) if directory else path.parent / "backups"
    # Create the needed output directory, including missing parents.
    directory.mkdir(parents=True, exist_ok=True)
    # Format the timestamp using the explicit date/time pattern; store the result in stamp.
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    # Construct the path or ratio from the specified components; store the result in target.
    target = directory / f"{path.stem}-{stamp}-{uuid.uuid4().hex[:8]}.sqlite3"
    # Close the read-only source handle after the backup operation.
    with closing(sqlite3.connect(path.resolve().as_uri()+"?mode=ro", uri=True)) as source:
        # Close the destination handle after verifying the backup.
        with closing(sqlite3.connect(target)) as dest:
            # Copy a consistent SQLite snapshot through the database backup API.
            source.backup(dest)
            # Enter this branch only when dest.execute('PRAGMA integrity_check').fetchone()[0] != 'ok'.
            if dest.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                # Stop this operation with RuntimeError('Backup integrity check failed').
                raise RuntimeError("Backup integrity check failed")
    # Write this stage event to the active run logs without printing to the terminal.
    emit("migration", "backup_created", path=str(target))
    # Return target to the caller.
    return target

# Define apply migrations with the inputs listed below.
def apply_migrations(connection, path=None):
    # Refuse to run schema changes inside an unrelated pending transaction.
    if connection.in_transaction:
        # Stop this operation with RuntimeError('Migrations require a connection outside a transaction').
        raise RuntimeError("Migrations require a connection outside a transaction")
    # Read connection.execute('PRAGMA user_version').fetchone()[0] from the source data; store the result in version.
    version = connection.execute("PRAGMA user_version").fetchone()[0]
    # Refuse to modify a database created by a newer schema version.
    if version > LATEST_VERSION:
        # Stop this operation with RuntimeError(f'Unsupported future schema version: {version}').
        raise RuntimeError(f"Unsupported future schema version: {version}")
    # Leave an already-current schema unchanged.
    if version == LATEST_VERSION:
        # Stop this function without returning a result.
        return
    # Create a backup only when this path already holds a database with existing tables.
    if path and Path(path).exists() and connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' LIMIT 1"
    ).fetchone():
        # Create and integrity-check a timestamped SQLite recovery copy.
        backup_database(path)
    # executescript starts its own transaction. Explicit rollback protects DDL as well as version.
    script = "BEGIN IMMEDIATE;\n"
    # Create the original observation tables for an unversioned database, without replacing existing tables.
    if version < 1:
        # Update script using SCHEMA for this step.
        script += SCHEMA
    # Add the exchange, asset, contract and metadata-provenance reference tables.
    if version < 2:
        # Update script using REFERENCE_SCHEMA for this step.
        script += REFERENCE_SCHEMA
    if version < 3:
        script += FOUNDATION_SCHEMA
    # Update script using f'PRAGMA user_version={LATEST_VERSION};\nCOMMIT;' for this step.
    script += f"PRAGMA user_version={LATEST_VERSION};\nCOMMIT;"
    # Run this operation with the error handling and cleanup defined below.
    try:
        # Execute the schema SQL; migration scripts supply their own transaction boundaries.
        connection.executescript(script)
    except Exception:
        # Undo the pending transaction after a failure.
        connection.rollback()
        # Propagate the current error to the caller.
        raise
    # Write this stage event to the active run logs without printing to the terminal.
    emit("migration", "schema_updated", previous_version=version, version=LATEST_VERSION)
