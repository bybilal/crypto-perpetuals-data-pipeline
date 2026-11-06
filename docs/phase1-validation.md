# Phase 1 validation acceptance report

Phase 1 is complete with explicit financial and operational limitations below. Phase 2, historical archive ingestion, universe expansion and GitHub push are not part of this change. The live database, history and LaunchAgent were preserved; schema version remains 2.

## Changes and verification

- Critical source-file errors now fail the pipeline; success is emitted only after requested coverage checks finish. Invalid individual records remain visible warnings. Successfully committed valid rows are retained for retry.
- Contract parsing rejects missing identities, duplicate filters/symbols and invalid required increments/minimum quantities or supplied contract sizes before reference writes.
- Duplicate inserts ignore only the observation primary-key conflict, preserving all original fields and provenance while allowing other constraints to fail.
- Canonical project-root paths prevent symlink aliases from creating different source identities. External raw paths display correctly. Backup connections explicitly close.
- Coverage reads a consistent snapshot and distinguishes missing observations ≤10 minutes old from older missing observations in its one-hour window. It reports exact boundaries and latest stored boundaries in JSONL.
- Added isolated full-row replay and financial/lineage auditing in `scripts/validate_pipeline.py`.

**75 tests passed**: the original 54 tests remain, with one warning-test fixture changed to represent an invalid individual record rather than a now-critical file error. Added 21 deterministic cases. Tests cover malformed metadata, rollback, full-row duplicate preservation, Decimal precision, late arrival, failure status/log ordering, path overrides and symlink roots. Existing migration, boundary, offline, concurrency, formatting and logging tests still pass. No live Binance requests are required by pytest.

## Actual database and lineage

The [implemented schema and full Mermaid ER diagram](implemented-schema.md) describe actual columns, keys, foreign keys and indexes, rather than future proposals.

Snapshot at **2026-11-06T22:20:33.350010+00:00**:

| Table | Rows |
|---|---:|
| assets | 3 |
| contracts | 2 |
| exchanges | 1 |
| metadata_sources | 11 |
| oi_observations | 93 |
| price_candles | 80 |
| raw_files | 88 |

The audit took a consistent SQLite backup under the existing collector lock, then released the live database and worked only on a temporary copy. Integrity check passed; foreign-key violations: **0**. All **99** indexed source checksums matched. All **173** normalized observations reproduced from their linked source records; completed-candle boundaries precede source retrieval. Metadata payloads, selected specifications and retrieval times matched their linked sources. All observed symbols had contract references. Physical observation storage types matched INTEGER/TEXT declarations.

Two ordinary offline CLI executions against the isolated snapshot left **every row in all seven tables unchanged**, including decimal text, primary keys and source references. This is stronger than comparing counts. Live collection can legitimately increase counts after this audit.

## Financial-unit reference

Evidence: locally retained exchangeInfo and source observations, plus Binance's [USDⓈ-M market-data API documentation](https://developers.binance.com/en/docs/catalog/core-trading-derivatives-trading-usd-s-m-futures/api/rest-api/market-data) and [1000PEPE contract launch specification](https://www.binance.com/en/support/announcement/detail/41993e3389654713946bcb6b9b032eaf). Trading filters can change; the following values describe the saved specifications, not a perpetual guarantee.

| Measurement | BTCUSDT | 1000PEPEUSDT | Meaning / evidence |
|---|---|---|---|
| Base asset | BTC | 1000PEPE | Actual exchangeInfo baseAsset; retain native units |
| Quote / margin | USDT / USDT | USDT / USDT | Actual quoteAsset / marginAsset; settlement of these USDT-margined perpetuals is USDT, not USD |
| Price | USDT per BTC | USDT per native 1000PEPE | Price scale corroborated by OI notional / quantity comparisons |
| OI quantity | Native BTC quantity | Native 1000PEPE quantity | Stock of open interest at source timestamp; do not add long and short as two separate outstanding positions |
| OI notional | USDT | USDT | Source sumOpenInterestValue; preserve reported amount rather than recomputing from candle close |
| Base traded volume | BTC | Native 1000PEPE | Flow over the candle, distinct from outstanding OI |
| Quote traded volume | USDT | USDT | Sum of traded quote amounts; not necessarily base volume × closing price |
| Taker-buy base / quote | BTC / USDT | Native 1000PEPE / USDT | Buy-aggressor subset of total volumes; quote delta = 2 × taker-buy quote − total quote |
| Price tick | 0.10 | 0.0000001 | PRICE_FILTER.tickSize; valid price increment, not quantity conversion |
| LOT_SIZE step / minimum | 0.001 / 0.001 | 1 / 1 | stepSize vs minQty: increment vs floor, not the same rule even when numerically equal |
| MIN_NOTIONAL | 50 USDT | 5 USDT | Separate order-value floor; minimum quantity alone does not establish an executable order |
| MARKET_LOT_SIZE min / step | 0.001 / 0.001 | 1 / 1 | Market-order quantity filters are separate from LOT_SIZE |
| contractSize | Absent → NULL | Absent → NULL | Not supplied; never default to 1 |
| Underlying-token multiplier | NULL | NULL | No verified conversion provenance stored; no automatic prefix parsing |
| CMC supply reference | Source reference | Source reference | Preserved as cmc_supply; not a verified CoinGecko supply or conversion factor |

PERCENT_PRICE multipliers (BTC 0.9700–1.0300; PEPE 0.8500–1.1500) constrain order prices relative to a reference; they are **not token multipliers**. The saved full specification also retains min/max prices and maximum quantities; this pipeline is not an order-validation engine.

**1000PEPE conversion remains unverified.** Independent official-document research confirmed the native underlying label and settlement currency, but the examined specification and announcement did not explicitly establish individual PEPE tokens per native quantity unit. The commonly stated factor 1,000 is not populated from the symbol name. Before conversion, obtain an explicit authoritative quantity definition and record its source, effective date and verification status. Unknown does not mean zero or one. Native-unit analysis remains usable.

USDT amounts are not USD amounts. Future USD market-cap ratios require a documented timestamped USDT/USD conversion or an explicitly named approximation. Decimal text is retained in SQLite; arithmetic uses Decimal with local precision. Display rounding never replaces stored measurements.

## Historical implied-price checks

Compared all 79 exact-boundary joined observations (39 BTC, 40 PEPE) in the snapshot. Compute implied price = source OI notional / source OI quantity with 50-digit Decimal precision. Examples (UTC on 2026-11-06; displayed values rounded):

| Contract | Boundary | Implied price | Candle close | Difference |
|---|---|---:|---:|---:|
| BTC | 17:35 | 75822.5 | 75822.50 | 0% |
| BTC | 20:35 | 75883 | 75875.30 | +0.010148% |
| BTC | 22:10 | 76025.02278111 | 76019.60 | +0.007133% |
| BTC | 21:05 (largest) | 75858.9 | 75831.40 | +0.036265% |
| 1000PEPE | 17:35 (largest) | 0.00508432 | 0.0050894 | −0.099815% |
| 1000PEPE | 20:40 | 0.0050455 | 0.0050469 | −0.027740% |
| 1000PEPE | 22:15 | 0.00497058 | 0.0049697 | +0.017707% |

These comparisons support the native quantity/price scale; they do not independently prove a token multiplier. Some differences exceed a price tick, so display rounding alone cannot explain them. An OI valuation snapshot and a last-trade candle close need not use the same price observation. Different valuation prices or sampling timing are plausible explanations, **not established causes**: concurrent valuation/mark-price snapshots are not stored. Keep both source values and do not force equality or infer corruption from that difference alone.

## Time and coverage findings

Source times are integer Unix milliseconds; display uses UTC. Retrieval time comes separately from the UTC capture filename (microsecond filename precision reduced to milliseconds). A candle is [open_ms, open_ms + 300000), with API close_ms = exclusive end − 1. Unfinished candles are excluded using the file's retrieval time, not today's clock. OI retains its original source timestamp; exact five-minute boundaries are used as period ends. Unaligned timestamps are preserved without rounding into matches.

Coverage uses 12 period ends with a 60-second grace. This is a diagnostic convention, not a guarantee of publication within a minute. At 22:01:13 UTC, both contracts lacked 22:00 OI; those observations were first captured around 22:06:06/08. At 22:11:13 both lacked 22:10 OI; those observations appeared around 22:16:06/08. This demonstrates later arrival in our captures, consistent with publication lag; it does not measure the exact moment Binance published them. No observations were invented or forward-filled. At the 22:16 run BTC lacked newest 22:15 OI while PEPE had it, illustrating independent stream timing.

Rows can arrive out of order and deduplicate by source identity/time. First valid values win; revised duplicate values are retained only in raw captures, not a separate revision table. Missing older history outside the one-hour report is not automatically repaired. The 25-record request overlap supports recent recovery, not arbitrary historical backfill.

## Scheduler, CLI and logs

The existing LaunchAgent remains installed, with the same interpreter, root and five-minute calendar schedule. Inspected status: 8 invocations, last exit code 0; “not running” between invocations is normal. The 22:16:04–22:16:12 UTC scheduled run used the revised code: coverage event preceded pipeline completion. No reinstall or schedule change was required.

`python -m crypto_pipeline`, offline mode, human logs, coverage, limit and path overrides are exercised by the existing and added tests and isolated replay. The collector lock protects CLI runs; the legacy standalone loader is not a safe concurrent entry point. The audit fails promptly if it encounters the collector lock; rerun after the active collection finishes.

JSONL carries UTC timestamps, run IDs, stages and counts/errors; optional human logs contain no ANSI escapes. Rich blue headings, brown stages and pastel-green increments remain. Coverage adds a small missing-observation detail only when needed. Invalid records can yield a completed run with quality warnings; malformed/changed source files and metadata failures now fail. A partial online fetch can retain successful raw captures, but the command reports failure rather than full success.

## Limitations and decisions before Phase 2

- Underlying multiplier and exact OI valuation-price methodology remain unresolved as described above.
- SQLite is not STRICT and lacks financial CHECK constraints; application validation does most domain enforcement. Observation-to-contract links are logical, not enforced FKs. Single-symbol keys must change before adding exchanges with overlapping symbols.
- Native asset IDs must map through verified canonical identities before CoinGecko joins. No symbol-only automatic matching, USD/USDT equivalence or unproven quantity conversion.
- Contract rows represent the latest specification, while historical metadata snapshots are preserved. Historical effective-dated contract lookup needs an explicit design.
- First-source lineage does not enumerate every duplicate capture or detect provider revisions. The audit validates indexed captures; it does not claim all unindexed disk files are ingested.
- Audit replay currently requires repository-relative indexed sources. CLI external-path support is tested, but auditing a database whose indexed files use absolute external paths requires an explicit copy/path mapping.
- One-hour coverage and finite overlap do not constitute full historical gap detection/backfill. No Airflow/Databricks or archive ingestion was added.
- Logs/raw capture retention, rotation and unattended failure notifications remain follow-up work. Sleep/logout/network restrictions affect collection; no access restrictions are bypassed.

## Files and local commits

Validation fixes: cli.py, config.py, coverage.py, reporting.py, storage/{loader,metadata,migrations,records}.py. Tests: test_phase1_hardening.py and the warning fixture in test_terminal_details.py. Audit: scripts/validate_pipeline.py. Documentation: this report, implemented-schema.md, operations.md, live-collection.md and README links.

Planned local commit messages: `fix: harden ingestion status metadata and coverage diagnostics`; `test: add isolated full-row pipeline validation audit`; `docs: record Phase 1 schema and financial validation evidence`. No raw files, databases or operational logs belong in these commits. Review local history before approving a push.

## Independent verification

From the repository:

```bash
cd /Users/b/Developer/crypto-perpetuals-data-pipeline
source .venv/bin/activate
python -m pytest -q
python scripts/validate_pipeline.py
python -m crypto_pipeline.schedule status
git log -3 --oneline
git diff --check
```

The audit prints JSON findings and runs both offline replays in a temporary directory; it does not replace the live database. It copies only indexed files while holding the collector lock. Do not use Python's `-O` option: verification assertions must remain enabled. Tests need no API access. `--human-log` is useful for manual live runs but already enabled in the scheduler; no additional manual live run is required to validate this milestone.

Stop here for review before GitHub push, destructive migration or Phase 2. The next approved milestone should begin with canonical asset identity and verified mapping design, then separate CoinGecko snapshots/categories ingestion and tests.
