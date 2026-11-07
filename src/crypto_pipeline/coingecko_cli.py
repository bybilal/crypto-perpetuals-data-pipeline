"""Manual Bitcoin capture or offline replay; independent of Binance scheduling."""
import argparse
import os
import sqlite3
from contextlib import closing
from pathlib import Path
from rich.console import Console
from .config import PROJECT_ROOT, DB_PATH
from .events import logging_run, emit
from .locking import pipeline_lock
from .coingecko import capture
from .storage.coingecko import ingest
from .storage.migrations import apply_migrations


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--replay', type=Path, help='Offline capture directory containing manifest.json')
    parser.add_argument('--raw-dir',type=Path,default=PROJECT_ROOT/'data/raw/coingecko')
    parser.add_argument('--db-path',type=Path,default=DB_PATH)
    parser.add_argument('--log-dir',type=Path,default=PROJECT_ROOT/'logs')
    parser.add_argument('--human-log',action='store_true')
    args = parser.parse_args()
    console = Console()
    with logging_run(args.log_dir, args.human_log) as run:
        try:
            emit('coingecko','started',offline=bool(args.replay))
            # Network work does not hold the Binance lock; database mutation uses the shared lock.
            directory = args.replay or capture(args.raw_dir, os.environ.get('COINGECKO_DEMO_API_KEY'))
            console.print('Capture: '+str(directory),markup=False)
            with pipeline_lock(args.db_path), closing(sqlite3.connect(args.db_path)) as connection:
                connection.execute('PRAGMA foreign_keys=ON')
                apply_migrations(connection,args.db_path)
                with connection:
                    result = ingest(connection,directory)
            emit('coingecko','completed',**result)
            console.print('[#8EAABD]Bitcoin / CoinGecko / USD[/#8EAABD]')
            console.print(f"  Price {result['price_usd'] or 'unavailable'} USD | New snapshots {result['snapshots_added']} | Categories {result['categories']}",markup=False)
            console.print('Data provided by CoinGecko: https://www.coingecko.com',markup=False)
            return 0
        except Exception as error:
            emit('coingecko','failed',error=str(error))
            console.print('CoinGecko failed: '+str(error),markup=False)
            return 1
        finally:
            console.print(f'Run: {run}\nJSONL log: {args.log_dir / (run + ".jsonl")}',markup=False)
            if args.human_log:
                console.print('Human log: '+str(args.log_dir/(run+'.log')),markup=False)


if __name__ == '__main__':
    raise SystemExit(main())
