# Optional hourly catch-up

Normal collection remains the existing five-minute LaunchAgent. Catch-up is an independent, optional process, not a replacement collector. It is not installed or activated by this milestone.

## Commands

After installing this branch into its own virtual environment (`python3 -m venv .venv`, then `.venv/bin/python -m pip install -e '.[dev]'`):

```sh
# Use the existing data root explicitly when running from the reliability worktree.
export CRYPTO_PIPELINE_ROOT=/Users/b/Developer/crypto-perpetuals-data-pipeline
.venv/bin/python -m crypto_pipeline.catchup --dry-run
.venv/bin/python -m crypto_pipeline.catchup --execute --max-pages 4
.venv/bin/python -m crypto_pipeline.catchup --audit
```

Do not install the agent while the production environment still imports the older package. Following review/merge and installation of the new package in the production root's .venv, optional commands are:

```sh
python -m crypto_pipeline.catchup_schedule install
python -m crypto_pipeline.catchup_schedule status
python -m crypto_pipeline.catchup_schedule stop
```

**Installation requires separate user approval.** It loads only `com.crypto-pipeline.catchup`, hourly at minute 03, without RunAtLoad. Stop unloads it but preserves its plist (so login can load it again); remove the optional plist manually if permanent removal is desired. The five-minute collector agent is unchanged.

## Decision rules and bounds

Latest completed online collection must have succeeded within 20 minutes. A newer failed collection suppresses catch-up. Recovery access/rate errors after that success also suppress catch-up until a newer online success. This evidence is a gate, not proof of entitlement or continuing accessibility. Each actual request remains subject to normal provider restrictions; no host switching, proxying or circumvention occurs.

Registered missing boundaries older than 130 minutes (25-record collector overlap plus one interval) qualify. Existing planner orders OI before candles, oldest ranges first, with at most 499 observations per page. Default four pages, hard maximum eight. The existing transport retries only transient network failures and HTTP 500/502/503/504, at most three attempts with 2/4-second delays: default upper bound **12 HTTP attempts**, maximum 24, plus two seconds between pages. There is no extra reachability probe or outer retry loop. HTTP 401/403/418/451 stop as access restrictions; 429 stops as rate limiting. No retry of these responses occurs within the invocation. Other HTTP errors are provider errors; transport failures and local/validation errors are separate outcomes.

The existing nonblocking database lock is held for each recovery page and released between pages. A collision skips gracefully. Reconciliation checks actual normalized rows before recording recovery; raw bytes, checksums, request sidecars, run_sources and gap detection/recovery lineage are reused. Restarting replans unresolved gaps. Partial responses remain unresolved, never invented. No schema migration or new table is needed.

## Operations and audit

1. During normal collection, inspect collection logs and `python -m crypto_pipeline.gaps status` independently.
2. During interruption, inspect actual HTTP/network evidence. Do not infer causes from missing periods. Access restrictions require stopping requests, not bypassing them.
3. Once recent collection succeeds, dry-run catch-up; an approved agent can make the same bounded execution hourly.
4. For larger/manual recovery use the existing `crypto_pipeline.recovery --dry-run` and bounded `--execute --max-requests` workflow.
5. `catchup --audit` prints per-stream gap totals, recent full gap lineage fields and recent recovery/catch-up JSONL events. The report examines only the latest 200 log files and prints 20 recent events; older attempts require their retained run-ID JSONL files. Do not treat an absent report entry as proof of no attempt.

`observation_gaps` contains expected bucket_end_ms, detected_ms, recovered_ms, recovered_run_id and raw_file_id. Missing observations retain NULL source IDs. Each page's `recovery/requested` event includes exact bounds and parent_run_id linking to the catch-up invocation. `ingested` records source path/counts; `completed` records recovered/remaining and full/partial/provider-unobserved outcome. Exceptions emit failed page events and classified catch-up stops. An interrupted attempt with no completion is unknown, not success. No new attempt table is introduced.

OI older than the existing conservative 30-day cutoff is not requested; records 27–30 days old receive warnings. These are operational approximations of Binance's documented latest-one-month availability, not a guarantee. Outside-window observations remain unresolved, not declared permanently unavailable. [Official USDⓈ-M connector documentation](https://binance.github.io/binance-connector-js/classes/_binance_derivatives-trading-usds-futures.DerivativesTradingUsdsFuturesRestAPI.MarketDataApi.html).

## Limitations

The latest completed-run gate is rechecked before each page, but collection may begin immediately afterward; shared locking prevents simultaneous writers. Automatic recovery depends on collection resuming and maintaining the gap registry. Repeated provider-omitted ranges can be retried on later invocations and may delay newer ranges; bounded traffic limits impact, but no persistent per-range retry cooldown is added. 429 Retry-After is not scheduled explicitly; the invocation stops and a later invocation requires newer collection success. The hourly job depends on the Mac being awake and the user logged in. Default overlap assumes the unchanged collector's limit=25. Actual geographic/API eligibility must be respected independently of connectivity.
