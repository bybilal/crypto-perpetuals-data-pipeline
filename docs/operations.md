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

Each command-line pipeline run creates `logs/<run-id>.jsonl`. `--human-log` adds a legible `.log` with the same ID. Events include UTC timestamp, run ID, stage, event, counts, and error details. Logs are written to files only, so they do not interleave with Rich output. Human logs contain no ANSI colors; they summarize operations rather than reproducing the Rich screen. Open them in any text editor. Logs and databases are ignored by Git. Per-run files avoid shared-handler duplication; retention/rotation is a future operational task.

```bash
crypto-pipeline --offline --raw-dir /path/to/raw --db-path /path/to/test.sqlite3 --log-dir /path/to/logs --human-log
```

Exceptions produce exit status 1 and a failed event. Invalid records and changed raw files retain the earlier skip-and-report behavior; completion logs expose counts and `quality_warnings`. Thus exit status 0 means the pipeline finished, not that every source record was accepted. Metadata corruption fails the metadata/load transaction. The standalone loader compatibility script does not create a run log; use the pipeline command for operational logging.

## Database safety

One active SQLite database remains at `data/market_data.sqlite3`. Version 0 was the original unversioned schema; version 1 represents that schema; version 2 adds reference/provenance tables. `PRAGMA user_version` records the version. Upgrades are additive and transactional, reject future versions, and use SQLite's backup API before changing an existing database. A backup is a recovery snapshot, not a second ingestion target. Foreign-key enforcement is enabled on pipeline connections.

The migration applied in this change preserved all 48 raw-file rows, 30 OI rows, 18 candles, and every raw JSON checksum. Two offline runs added no observations. Integrity and foreign-key checks passed. The pre-migration backup is in `data/backups/`.

### Proposed relocation, awaiting review

Prefer `data/db/market_data.sqlite3` after review. No destructive move or deletion was performed. To relocate safely in a follow-up:

1. Stop writers and create a fresh SQLite backup.
2. Copy using SQLite's backup API to the new path, refusing to overwrite an existing destination.
3. Compare every table's rows, schema version, integrity, and foreign-key checks.
4. Switch the configured default and verify an offline run against the new database.
5. Only after explicit approval, remove/archive the old live path so it cannot silently diverge. Keep the recovery backup.

Do not rename a running SQLite database or omit its WAL. Do not restore over the active database without a separate backup and review. No automated downgrade is supplied; recovery uses the verified pre-migration copy with the corresponding code revision.

## Tests and review

Pytest executes small examples with known expected results. Fixtures are selected records from the saved Binance responses, including the actual two selected exchangeInfo specifications. Temporary databases isolate tests from live history. Network connections are blocked in in-process tests; subprocess integration tests always use offline mode.

Coverage includes native decimals, timestamp boundaries, OHLC/volume checks, malformed values, 1m skipping, unfinished candles, deduplication, exact joins, checksum protection, offline execution, growth color, metadata provenance, newer-snapshot precedence, backup preservation, migration rollback/future-version rejection, logs and failure exit status.

Local commits separate the regression baseline, package extraction, and operational/schema features. Review with `git log --oneline` and `git show <commit>`. No push is performed without review approval.
