"""Local defaults; explicit CLI overrides are available for isolated runs."""
from pathlib import Path
import os
PROJECT_ROOT = Path(os.environ.get("CRYPTO_PIPELINE_ROOT", Path(__file__).resolve().parents[2]))
RAW_DIR = PROJECT_ROOT / "data/raw"
# Keep the live database separate from raw captures and recovery backups.
DB_PATH = PROJECT_ROOT / "data/db/market_data.sqlite3"
SYMBOLS = ("BTCUSDT", "1000PEPEUSDT")
