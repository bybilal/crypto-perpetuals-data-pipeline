# Engineering decision log

## 2026-11-17 — independent bounded catch-up

### Evidence and debugging

The November 14–17 interruption was investigated through stored pipeline_runs, observation_gaps and JSONL events, not inferred from dashboard colors. Local fetch/request_error events explicitly contain HTTP 451 and Binance's restricted-location message. That confirms the response; it does not establish whether a location change, network routing, provider policy or another condition caused it. No bypass was attempted.

The user reported five consecutive successful online runs on November 17. Independent inspection found resumed successful online collection and a concurrently running collector. November 17 recovery/completed events confirm **12 pages and 4,193 recovered observations**. At validation, all **9,548** registered gaps were recovered and none missing. SQLite integrity was OK, no foreign-key violations, and **3,014** indexed raw-file checksums matched. These are point-in-time results; the live collector continues independently.

### Decision and trade-offs

Use a separate optional hourly command and LaunchAgent. Reuse existing recovery.plan/execute_job, raw capture, loader, lock, run lineage and reconciliation. Add only an optional planning cutoff and optional parent invocation identifier to recovery; do not refactor collection. Latest successful online evidence gates traffic, OI is prioritized, recent collector overlap is excluded, and page/retry budgets bound requests. Access/rate failures stop rather than trigger alternate endpoints.

Keep attempt evidence in existing JSONL logs and database lineage. This avoids an additional schema/table, at the cost of bounded log scanning and needing retained logs for complete historical investigations. NULL provenance remains meaningful; a missing source is not filled with a guessed association. Request success, inserted rows, time completeness and source integrity remain different measurements.

### Isolation and validation

Branch `reliability-catchup` starts at c064bb9 in a separate worktree. Uncommitted Observatory files in the original repository are untouched and excluded from this commit. Tests use temporary databases and mocked transport. No live recovery execution, production database writes, new scheduler activation or push is part of this milestone. The 135-test regression suite includes existing pagination/partial-response/idempotency tests and new gates, budget, collision, restriction, retry, retention, provenance and optional-agent checks.

### Interview explanation

“I kept the five-minute collector small and isolated catch-up into a bounded worker. It only runs after collection demonstrates recent access, prioritizes expiring OI, and yields to the shared lock. A successful HTTP response does not close a gap: verified normalized rows do. I reused source and run IDs so an expected timestamp can be traced from first detection through recovery to exact bytes. Restrictions stop the worker; unknown causes and unavailable evidence stay explicit.”
