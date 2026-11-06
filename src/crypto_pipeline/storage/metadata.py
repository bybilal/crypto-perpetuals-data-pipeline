"""Load only actual saved exchangeInfo specifications; never parse symbol prefixes."""
import hashlib
import json
from ..config import SYMBOLS
from ..normalization import decimal_text
from ..time_utils import filename_timestamp_ms
from ..events import emit

EXCHANGE = "binance_usdm"

def load_metadata(connection, raw_dir, project_root):
    imported = 0
    for path in sorted(raw_dir.glob("exchangeInfo_*.json")):
        raw = path.read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        file_path = path.relative_to(project_root).as_posix() if path.is_relative_to(project_root) else str(path.resolve())
        existing = connection.execute("SELECT sha256 FROM metadata_sources WHERE file_path=?", (file_path,)).fetchone()
        if existing:
            if existing[0] != digest:
                raise ValueError(f"Metadata changed since indexing: {path.name}")
            continue
        payload = json.loads(raw)
        if not isinstance(payload, dict) or not isinstance(payload.get("symbols"), list):
            raise ValueError("exchangeInfo must contain a symbols list")
        retrieved = filename_timestamp_ms(path.stem.removeprefix("exchangeInfo_"))
        selected = {item["symbol"]: item for item in payload["symbols"] if isinstance(item, dict) and item.get("symbol") in SYMBOLS}
        if set(selected) != set(SYMBOLS):
            raise ValueError("exchangeInfo is missing configured contracts")
        connection.execute("INSERT OR IGNORE INTO exchanges VALUES (?, ?, ?)", (EXCHANGE, "Binance", "USDⓈ-M Futures"))
        source_id = connection.execute("INSERT INTO metadata_sources(file_path, sha256, retrieved_at_ms, payload_json) VALUES (?,?,?,?)", (file_path, digest, retrieved, raw.decode("utf-8"))).lastrowid
        for symbol, spec in selected.items():
            asset_ids = []
            for field in ("baseAsset", "quoteAsset", "marginAsset"):
                native = spec[field]
                if not isinstance(native, str) or not native:
                    raise ValueError(f"Invalid {field}")
                asset_id = f"{EXCHANGE}:{native}"
                connection.execute("INSERT OR IGNORE INTO assets VALUES (?,?,?)", (asset_id, EXCHANGE, native))
                asset_ids.append(asset_id)
            filters = {item["filterType"]: item for item in spec["filters"]}
            tick = decimal_text(filters["PRICE_FILTER"]["tickSize"], "tick size", True)
            step = decimal_text(filters["LOT_SIZE"]["stepSize"], "quantity step", True)
            size = spec.get("contractSize")
            if size is not None:
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
        imported += 1
    emit("metadata", "loaded", files_imported=imported)
    return imported
