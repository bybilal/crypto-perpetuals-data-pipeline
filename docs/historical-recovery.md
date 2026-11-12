# Bounded historical recovery

The manual command plans solely from schema-v4 unresolved gap keys. It defaults to read-only planning:

```bash
python -m crypto_pipeline.recovery --dry-run
python -m crypto_pipeline.recovery --execute --max-requests 24
python -m crypto_pipeline.gaps status
python -m pytest -q -p no:cacheprovider
python scripts/validate_pipeline.py
```

OI is prioritized, then candles. Contiguous ranges are split into pages of at most 499 expected timestamps. Limits are deliberately below Binance's OI maximum 500 and USD-M candle maximum 1500. Candle request startTime is the first bucket end minus 300000 and endTime is the last bucket end minus one; OI requests use the original period-end timestamps. Every page has explicit inclusive bounds. Pagination advances by planned boundary, never by an assumed full response length; an omitted record cannot cause an infinite pagination loop.

[Official market-data reference](https://developers.binance.com/en/docs/catalog/core-trading-derivatives-trading-usd-s-m-futures/api/rest-api/market-data), reviewed November 12, 2026: OI has only the latest month of history; the planner conservatively excludes OI older than 30 days. Exclusion is endpoint eligibility, not proof permanent unavailability. OI can omit periods. Two-second spacing and a per-invocation request cap limit traffic. Existing fetch retries remain bounded to three attempts with 2/4-second waits for transient server/transport errors; 429, 418 and access restrictions stop immediately without alternate hosts. Retries can increase HTTP attempts above the page count. Replan before retrying a stopped invocation.

## Architecture and lineage

`recovery.plan` reads gap keys; `request_url` converts boundaries; `execute_job` fetches one page under the existing database lock and uses `load_files(paths=[raw])` to process only that response. Original collector calls still scan their original directory unchanged. `tracked_run` accepts an optional mode; recovery uses **recovery**, so a successful recovery run does not masquerade as latest successful live collection. Existing mode behavior is unchanged.

Each response is preserved byte-for-byte under data/raw with its UTC retrieval filename. A `.request.json` sidecar stores URL, planned bounds and JSONL run ID. The normal raw_files checksum and observation source FK remain authoritative. A transaction commits valid normalized records; lineage links newly indexed sources to the run. Reconciliation then verifies stored rows before transitioning any gap. Original detection time and historical recovered records remain intact. No schema migration was necessary.

The lock is released between pages. Network work holds it for one bounded request/retry cycle, so a coincident scheduled run may report the existing lock error; the schedule itself is not modified or stopped. If the collector holds the lock, recovery stops safely and can be resumed with a new plan. Committed earlier pages remain durable. If interrupted after raw capture but before ingestion, ordinary `python -m crypto_pipeline --offline` can ingest retained responses; replan afterward. A crash before sidecar creation leaves filename/checksum provenance, but may lack complete request metadata. No raw data is deleted.

## Outcome meanings

Per-page JSONL records requested bounds, source path, returned/inserted counts and post-reconciliation remaining counts. Fully/partially recovered describe verified gap transitions. `provider_unobserved_in_response` means no target gap was resolved by that successful validated response; it does **not** mean the provider failed, or the record can never be retrieved. Errors remain failed runs with unresolved gaps. Unavailable is not assigned without evidence. Do not sum API response lengths as completeness.

No dedicated attempts table is added: pipeline_runs, run_sources, gap history and request/outcome JSONL supply the small project's attempt trail. SQL-only dashboards can query recovered/missing state and run mode; exact HTTP outcomes require joining operational logs by run_id. A future attempts table may be useful if SQL-only retry analytics are needed.

## Dashboard interpretation

Join observations to raw_files for source integrity, and run_sources/pipeline_runs for newly indexed execution provenance. A source indexed by a recovery-mode run indicates recovery ingestion; an observation associated with a recovered gap may also have arrived later through ordinary live collection. Neither should erase the original gap-detection history. Earlier observations without run links have unknown acquisition mode, not assumed live origin.

A heatmap should enumerate boundaries inside monitoring_windows, join observation_gaps and actual observations, and separately label recent grace periods and times outside the monitoring window. Missing OI remains cause-unknown. Collection success, verified source integrity and temporal completeness are separate dimensions. The registry does not reopen recovered gaps after unsupported manual observation deletion.

No UI, derived analytics, new symbols, CoinGecko changes or launchd edits are included. Official candle archives remain a deferred fallback: use only if REST fails to supply needed history and archive availability/schema/checksums are independently verified. No archive downloader or restriction bypass is included.

## Milestone 4 execution results

The reviewed plan made 22 successful recovery-page requests (10 OI, 12 candles), covering all 5263 targeted observations. Each page has its own succeeded recovery run and linked raw source. No API access errors, partial responses or archive fallback occurred. A subsequent dry-run returned zero pages.

| Stream | Before missing | Newly recovered | After unresolved | Confirmed unavailable |
|---|---:|---:|---:|---:|
| BTCUSDT OI | 1314 | 1314 | 0 | 0 |
| 1000PEPEUSDT OI | 1313 | 1313 | 0 | 0 |
| BTCUSDT candles | 1318 | 1318 | 0 | 0 |
| 1000PEPEUSDT candles | 1318 | 1318 | 0 | 0 |

The unavailable column means no observations were classified unavailable, not a general guarantee of provider history. No missing gaps remain inside the reconciled monitoring windows at this snapshot. This does not claim completeness before their starts or inside publication grace periods.

113 deterministic tests passed. The existing validation script verified 2011 source checksums and two offline replays preserved all market/reference rows. Every pre-recovery OI/candle/raw-file/CoinGecko row was compared against the consistent pre-execution SQLite snapshot and remained byte-for-byte equal at the row level. Integrity OK; zero FK violations. All 22 recovery runs link to their indexed raw files. Scheduler status after recovery reported 1709 invocations, last exit code 0. It was neither stopped nor reconfigured.

Changed files: recovery.py (planner/controller), storage/loader.py (optional targeted-file input), lineage.py (explicit recovery mode), tests/test_recovery.py, this document and README. Existing fetch retry and normalization tests remain applicable because those implementations are reused unchanged. The recovery regression tests additionally cover bounded planning, timestamp conversion, pagination/retention exclusions, partial and repeated responses, source lineage, database locking and geographic-access errors.
