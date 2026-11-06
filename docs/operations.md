# Running, testing and reviewing

Use Python 3.11+ (validated here on 3.13). From the repository with its virtual environment activated:

```bash
python -m pip install -e '.[dev]'
python -m pytest -q
crypto-pipeline --offline --human-log
```

`python src/run_pipeline.py --offline` and `python -m crypto_pipeline --offline` also work. Existing inspection, formatting, normalization and loader imports remain compatibility entry points. The earlier Lambda connectivity probe and its README milestone remain intact; the package is not yet deployed to Lambda.

For just the original script workflow, `pip install -r requirements-dev.txt` suffices. Rich is the runtime dependency; pytest is development-only. `pyproject.toml` defines the installable package and command. Version ranges are bounded, not a reproducible lockfile. For a non-editable installation, set `CRYPTO_PIPELINE_ROOT` to the intended project/data directory; do not rely on the installed package's location for data paths.

## Layout

```text
src/crypto_pipeline/
  binance.py          existing requests and raw-response preservation
  normalization.py    validated API records, no I/O
  units.py            Decimal arithmetic and guarded conversions
  time_utils.py       exact UTC timestamp helpers
  config.py           local defaults
  cli.py              pipeline stages, options, exit status
  events.py           file-only structured events
  formatting.py       field/number formatting and style constants
  reporting.py        Rich presentation
  summary.py          database summary presentation
  storage/
    schema.py         original observation schema
    migrations.py     schema versions, transactional upgrades, backups
    metadata.py       saved exchangeInfo references and provenance
    records.py        fixed-column inserts
    loader.py         raw-file traversal and ingestion
    queries.py        counts and exact-boundary joins
```

## Logs

Each command-line pipeline run creates `logs/<run-id>.jsonl`. `--human-log` adds a legible `.log` with the same ID. Events include UTC timestamp, run ID, stage, event, counts, and error details. Logs are written to files only, so they do not interleave with Rich output. Human logs contain no ANSI colors; they summarize operations rather than reproducing the Rich screen. The terminal prints the run ID and both file paths (when enabled), including on failure. Local paths are relative to the repository. Open a `.log` in any text editor or read it with `cat logs/<run-id>.log`. You do not need to watch logs during normal manual runs; they are the durable record when the terminal closes or collection runs unattended. Logs and databases are ignored by Git. Per-run files avoid shared-handler duplication; retention/rotation is a future operational task.

```bash
crypto-pipeline --offline --raw-dir /path/to/raw --db-path /path/to/test.sqlite3 --log-dir /path/to/logs --human-log
```

Exceptions produce exit status 1 and a failed event. Invalid individual records are skipped with counts and `quality_warnings`. File-level failures (including checksum changes or malformed JSON) now produce pipeline exit status 1 after reporting the loader results. Valid rows already committed remain stored for safe retry. Exit status 0 still does not mean every individual source record was accepted. Metadata corruption fails the metadata/load transaction. The standalone loader compatibility script does not create a run log; use the pipeline command for operational logging.

## Database safety

One active SQLite database lives at `data/db/market_data.sqlite3`. Version 0 was the original unversioned schema; version 1 represents that schema; version 2 adds reference/provenance tables. `PRAGMA user_version` records the version. Upgrades are additive and transactional, reject future versions, and use SQLite's backup API before changing an existing database. A backup is a recovery snapshot, not a second ingestion target. Foreign-key enforcement is enabled on pipeline connections.

The migration applied in this change preserved all 48 raw-file rows, 30 OI rows, 18 candles, and every raw JSON checksum. Two offline runs added no observations. Integrity and foreign-key checks passed. The pre-migration backup is in `data/backups/`.

### Completed database relocation

The approved relocation created a fresh SQLite backup, copied through SQLite's backup API, and compared all seven tables and the schema version. Integrity and foreign-key checks passed. An offline run at the new default added no duplicate observations. The original file was archived in `data/backups/`; the old live path no longer exists. Raw JSON files were not moved or modified.

Recovery files from this relocation:

- `data/backups/market_data-20261106T211341942166Z-e7fbee0b.sqlite3`
- `data/backups/market_data-20261106T211341942166Z-e7fbee0b-original.sqlite3` (original file)

Do not rename a running SQLite database or omit its WAL. Do not restore over the active database without a separate backup and review. No automated downgrade is supplied; recovery uses the verified pre-migration copy with the corresponding code revision.

## Tests and review

Pytest executes small examples with known expected results. Fixtures are selected records from the saved Binance responses, including the actual two selected exchangeInfo specifications. Temporary databases isolate tests from live history. Network connections are blocked in in-process tests; subprocess integration tests always use offline mode.

Coverage includes native decimals, timestamp boundaries, OHLC/volume checks, malformed values, 1m skipping, unfinished candles, deduplication, exact joins, checksum protection, offline execution, growth color, metadata provenance, newer-snapshot precedence, backup preservation, migration rollback/future-version rejection, logs and failure exit status.

Local commits separate the regression baseline, package extraction, and operational/schema features. Review with `git log --oneline` and `git show <commit>`. No push is performed without review approval.

## Data collection comes before analytics

The current schema already stores OI, candles and actual Binance specifications. An offline rerun normalizes saved files and deduplicates them; it cannot collect new history. Zero new rows in offline mode is expected.

`crypto-pipeline --human-log` runs the existing online fetch-and-store flow once, when Binance access is permitted from the environment. It does not schedule itself. The current request limit is only three observations/candles per endpoint; it is a sampling configuration, not a complete backfill system.

The next implementation milestone is a collection service for the existing two contracts: recover recent missing intervals, detect gaps separately for OI and candles, retry transient errors with backoff, and run regularly with overlap so late/completed candles are recovered. Stop on access restrictions rather than selecting alternate hosts or regions to bypass them. Backfill availability must be checked against each endpoint's current documented retention.

Do not delay OI/candle collection for CoinGecko. Add CoinGecko identity mappings, categories and timestamped valuation snapshots after their source/units design is reviewed. Market cap and FDV snapshots will accumulate from their own collection start; creating tables does not create historical observations.

## Terminal versus logs

The terminal is the quick answer to “did this run work?” It keeps the minimalist table and pastel-green increments. File errors and a completion warning are visible when data-quality issues occur. JSONL is one structured event per line for future automation; the optional human log expresses those same operations as plain text. Neither replaces the market-data database.

Next display additions should accompany actual monitoring logic: age of the newest stored observation, missing 5m intervals over a stated window, and last successful fetch. Do not label missing historical samples as a live outage or show a green health status solely because a command exited successfully.

## Reading the code

Python statements have nearby teaching comments explaining data flow, conditions, calls, returns and cleanup. Multiline calls are explained as one operation; closing brackets and literal data are not independent operations. SQL table fields and units are explained in [the data model](data-model.md). Start with `cli.main`, follow `run_pipeline`, then `storage.loader.main`; `normalization.py` contains the record checks.
