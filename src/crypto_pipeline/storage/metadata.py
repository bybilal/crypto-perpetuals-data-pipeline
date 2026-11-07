"""Load only actual saved exchangeInfo specifications; never parse symbol prefixes."""
# Import hashlib for use below.
import hashlib
# Import json for use below.
import json
# Import SYMBOLS from ..config for use below.
from ..config import SYMBOLS
# Import decimal_text from ..normalization for use below.
from ..normalization import decimal_text
# Import filename_timestamp_ms from ..time_utils for use below.
from ..time_utils import filename_timestamp_ms
# Import emit from ..events for use below.
from ..events import emit
from .foundation import seed_native_mappings

# Use the explicit text 'binance_usdm'; store the result in EXCHANGE.
EXCHANGE = "binance_usdm"

def validate_specification(spec):
    """Validate the supported contract identity and filters before writing reference rows."""
    # Missing/duplicate filter definitions cannot silently establish trading increments.
    for field in ("symbol", "baseAsset", "quoteAsset", "marginAsset", "contractType", "status"):
        if not isinstance(spec.get(field), str) or not spec[field].strip():
            raise ValueError(f"Missing or invalid contract {field}")
    filters = spec.get("filters")
    if not isinstance(filters, list):
        raise ValueError("Contract filters must be a list")
    by_type = {}
    for item in filters:
        if not isinstance(item, dict) or not isinstance(item.get("filterType"), str):
            raise ValueError("Invalid contract filter")
        name = item["filterType"]
        if name in by_type:
            raise ValueError(f"Duplicate contract filter: {name}")
        by_type[name] = item
    # Price/quantity increments and minimum quantities are separate validations.
    for name, fields in (("PRICE_FILTER", ("tickSize",)), ("LOT_SIZE", ("stepSize", "minQty"))):
        for field in fields:
            if field not in by_type.get(name, {}):
                raise ValueError(f"Missing {name}.{field}")
            decimal_text(by_type[name][field], f"{name}.{field}", True)
    # An absent contractSize remains unknown; any supplied size must be positive.
    if spec.get("contractSize") is not None:
        decimal_text(spec["contractSize"], "contractSize", True)


# Define load metadata with the inputs listed below.
def load_metadata(connection, raw_dir, project_root):
    # Set the explicit starting value; store the result in imported.
    imported = 0
    # Process each path from sorted(raw_dir.glob('exchangeInfo_*.json')).
    for path in sorted(raw_dir.glob("exchangeInfo_*.json")):
        # Read the file exactly as stored, before JSON parsing or normalization; store the result in raw.
        raw = path.read_bytes()
        # Represent the content fingerprint as a hexadecimal string; store the result in digest.
        digest = hashlib.sha256(raw).hexdigest()
        # Choose the value according to path.is_relative_to(project_root); store the result in file_path.
        file_path = path.relative_to(project_root).as_posix() if path.is_relative_to(project_root) else str(path.resolve())
        # Read the first result row from the SQL query; store the result in existing.
        existing = connection.execute("SELECT sha256 FROM metadata_sources WHERE file_path=?", (file_path,)).fetchone()
        # Enter this branch only when existing.
        if existing:
            # Enter this branch only when existing[0] != digest.
            if existing[0] != digest:
                # Stop this operation with ValueError(f'Metadata changed since indexing: {path.name}').
                raise ValueError(f"Metadata changed since indexing: {path.name}")
            # Skip the remaining work for this item and continue the enclosing loop.
            continue
        # Parse the JSON payload into Python objects; store the result in payload.
        payload = json.loads(raw)
        # Enter this branch only when not isinstance(payload, dict) or not isinstance(payload.get('symbols'), list).
        if not isinstance(payload, dict) or not isinstance(payload.get("symbols"), list):
            # Stop this operation with ValueError('exchangeInfo must contain a symbols list').
            raise ValueError("exchangeInfo must contain a symbols list")
        # Convert the UTC filename timestamp to integer Unix milliseconds; store the result in retrieved.
        retrieved = filename_timestamp_ms(path.stem.removeprefix("exchangeInfo_"))
        # Build a collection by selecting and transforming the specified inputs; store the result in selected.
        selected_items = [item for item in payload["symbols"] if isinstance(item, dict) and item.get("symbol") in SYMBOLS]
        selected = {item["symbol"]: item for item in selected_items}
        if len(selected_items) != len(selected):
            raise ValueError("Duplicate configured symbol in exchangeInfo")
        for spec in selected.values():
            validate_specification(spec)
        # Enter this branch only when set(selected) != set(SYMBOLS).
        if set(selected) != set(SYMBOLS):
            # Stop this operation with ValueError('exchangeInfo is missing configured contracts').
            raise ValueError("exchangeInfo is missing configured contracts")
        # Insert a new row while leaving an existing unique-key match unchanged.
        connection.execute("INSERT OR IGNORE INTO exchanges VALUES (?, ?, ?)", (EXCHANGE, "Binance", "USDⓈ-M Futures"))
        # Save the metadata payload and retain its new row ID for each contract specification.
        source_id = connection.execute("INSERT INTO metadata_sources(file_path, sha256, retrieved_at_ms, payload_json) VALUES (?,?,?,?)", (file_path, digest, retrieved, raw.decode("utf-8"))).lastrowid
        # Process each (symbol, spec) from selected.items().
        for symbol, spec in selected.items():
            # Build the ordered collection used by this operation; store the result in asset_ids.
            asset_ids = []
            # Process each field from ('baseAsset', 'quoteAsset', 'marginAsset').
            for field in ("baseAsset", "quoteAsset", "marginAsset"):
                # Read spec[field] from the source data; store the result in native.
                native = spec[field]
                # Enter this branch only when not isinstance(native, str) or not native.
                if not isinstance(native, str) or not native:
                    # Stop this operation with ValueError(f'Invalid {field}').
                    raise ValueError(f"Invalid {field}")
                # Build the text using the current field values; store the result in asset_id.
                asset_id = f"{EXCHANGE}:{native}"
                # Insert a new row while leaving an existing unique-key match unchanged.
                connection.execute("INSERT OR IGNORE INTO assets VALUES (?,?,?)", (asset_id, EXCHANGE, native))
                # Add this item to the accumulating list.
                asset_ids.append(asset_id)
            # Build a collection by selecting and transforming the specified inputs; store the result in filters.
            filters = {item["filterType"]: item for item in spec["filters"]}
            # Validate the numeric field while retaining its original decimal text; store the result in tick.
            tick = decimal_text(filters["PRICE_FILTER"]["tickSize"], "tick size", True)
            # Validate the numeric field while retaining its original decimal text; store the result in step.
            step = decimal_text(filters["LOT_SIZE"]["stepSize"], "quantity step", True)
            # Read the requested optional value using its default when absent; store the result in size.
            size = spec.get("contractSize")
            # Enter this branch only when size is not None.
            if size is not None:
                # Validate the numeric field while retaining its original decimal text; store the result in size.
                size = decimal_text(size, "contract size", True)
            # Native 1000PEPE units remain native; a prefix is NOT conversion evidence.
            connection.execute("""
                INSERT INTO contracts VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(symbol) DO UPDATE SET
                  base_asset_id=excluded.base_asset_id, quote_asset_id=excluded.quote_asset_id,
                  margin_asset_id=excluded.margin_asset_id, contract_type=excluded.contract_type,
                  status=excluded.status, price_tick=excluded.price_tick,
                  quantity_step=excluded.quantity_step, contract_size=excluded.contract_size,
                  source_id=excluded.source_id, retrieved_at_ms=excluded.retrieved_at_ms,
                  specification_json=excluded.specification_json
                WHERE excluded.retrieved_at_ms >= contracts.retrieved_at_ms
            """, (symbol, EXCHANGE, *asset_ids, spec["contractType"], spec["status"], tick, step,
                  size, None, None, source_id, retrieved, json.dumps(spec, sort_keys=True)))
        # Update imported using 1 for this step.
        imported += 1
    # Write this stage event to the active run logs without printing to the terminal.
    seed_native_mappings(connection)
    emit("metadata", "loaded", files_imported=imported)
    # Return imported to the caller.
    return imported
