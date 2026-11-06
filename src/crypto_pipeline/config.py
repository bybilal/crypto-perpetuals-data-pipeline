"""Local defaults; explicit CLI overrides are available for isolated runs."""
# Import Path from pathlib for use below.
from pathlib import Path
# Import os for use below.
import os
# Use an explicit data root when provided; otherwise locate the repository above src/.
PROJECT_ROOT = Path(os.environ.get("CRYPTO_PIPELINE_ROOT", Path(__file__).resolve().parents[2])).resolve()
# Keep original exchange response files in the raw-data directory.
RAW_DIR = PROJECT_ROOT / "data/raw"
# Keep the live database separate from raw captures and recovery backups.
DB_PATH = PROJECT_ROOT / "data/db/market_data.sqlite3"
# Limit collection and summaries to the two contracts whose units are under review.
SYMBOLS = ("BTCUSDT", "1000PEPEUSDT")
