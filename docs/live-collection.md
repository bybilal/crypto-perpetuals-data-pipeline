# Local live collection

Run `crypto-pipeline --human-log --limit 25 --coverage` for one live capture. The manual default remains three records. Scheduled runs request 25 recent records per endpoint, preserving raw responses and deduplicating normalized rows. No archive downloader is enabled.

Temporary network and HTTP 500/502/503/504 failures receive at most three attempts, separated by two and four seconds. HTTP access restrictions and rate limits surface immediately. A per-database process lock prevents overlapping CLI fetch/load runs. The standalone legacy loader should not be run concurrently with the collector.

Coverage checks twelve five-minute period ends over the last mature hour with one minute of publication grace. OI and candles are counted independently. JSONL records exact missing timestamps. Missing observations are evidence of absent stored data, not a diagnosis of source failure. Coverage warnings do not change a successful run's exit code.

## macOS schedule

Install after testing with `python -m crypto_pipeline.schedule install`. Inspect with `python -m crypto_pipeline.schedule status`. Stop with `python -m crypto_pipeline.schedule stop`.

The user LaunchAgent is `~/Library/LaunchAgents/com.crypto-pipeline.collector.plist`. It runs the repository virtual environment at minutes 01, 06, 11 and so on, plus once at load/login. It requires a logged-in user session. launchd can coalesce calendar invocations missed during sleep into one wake-up invocation. The recent overlap supports brief interruptions. Older gaps remain for a future explicit recovery command.

Per-run logs live under `logs/`. Scheduler stdout and stderr append to `logs/scheduler.stdout.log` and `logs/scheduler.stderr.log`. Raw files, exchange metadata snapshots and logs accumulate. Retention/rotation is a follow-up task. Repeated installation is a no-op for the same loaded configuration. A different existing plist requires review before replacement.

A fresh clone needs its own virtual environment and schedule installation. Generated absolute paths are local to that installation. The repository contains the portable installer rather than a machine-specific plist.
