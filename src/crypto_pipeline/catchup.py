"""Bounded, optional catch-up. Dry-run by default; never changes schedules."""
import argparse
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import time
from urllib.error import HTTPError, URLError
from .config import DB_PATH, PROJECT_ROOT
from .events import logging_run, emit
from .recovery import plan, execute_job

DAY = 86400000
# Collector requests 25 five-minute records. Keep a conservative extra interval.
OVERLAP_MS = 26 * 300000

def read_db(path):
    return closing(sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True))

def eligibility(c, now):
    row=c.execute("SELECT ended_ms,status FROM pipeline_runs WHERE mode='online' AND ended_ms IS NOT NULL ORDER BY started_ms DESC LIMIT 1").fetchone()
    if not row or row[1]!='succeeded':return 'latest completed online collection did not succeed'
    if not 0<=now-row[0]<=20*60000:return 'online success is not within the last 20 minutes'
    restricted=c.execute("SELECT error FROM pipeline_runs WHERE mode='recovery' AND status='failed' AND ended_ms>?",(row[0],)).fetchall()
    if any(any(f'HTTP Error {code}' in (r[0] or '') for code in (401,403,418,429,451)) for r in restricted):
        return 'recovery access/rate failure requires a newer successful online collection'
    return None

def classify(error):
    if isinstance(error,HTTPError):
        if error.code in (401,403,418,451):return 'access_restricted'
        if error.code==429:return 'rate_limited'
        return 'provider_error'
    if isinstance(error,(URLError,TimeoutError,ConnectionError)):return 'network_failure'
    if isinstance(error,RuntimeError) and isinstance(error.__cause__,BlockingIOError):return 'lock_busy'
    return 'validation_or_local_error'

def inspect(path,now):
    with read_db(path) as c:
        c.execute('BEGIN')
        reason=eligibility(c,now)
        jobs,outside=plan(c,now,before_ms=now-OVERLAP_MS)
        warning=c.execute("SELECT COUNT(*) FROM observation_gaps WHERE dataset='oi' AND status='missing' AND bucket_end_ms BETWEEN ? AND ?",(now-30*DAY,now-27*DAY)).fetchone()[0]
    return reason,jobs,outside,warning

def run(path,logs,max_pages=4,execute=False,clock=lambda:time.time_ns()//1000000):
    if not 1<=max_pages<=8:raise ValueError('max-pages must be 1..8')
    reason,jobs,outside,warning=inspect(path,clock())
    print(json.dumps({'eligible':reason is None,'skip_reason':reason,'planned_pages':len(jobs),'selected':jobs[:max_pages], 'outside_oi_window':len(outside),'oi_within_three_days_of_retention':warning}))
    if not execute:return 0
    with logging_run(logs,human=True) as invocation:
        emit('catchup','planned',pages=len(jobs),max_pages=max_pages,retention_warning=warning,outside_oi_window=len(outside))
        if reason:
            emit('catchup','skipped',reason=reason);return 0
        for index,job in enumerate(jobs[:max_pages]):
            # Recheck current collection evidence before every page. No probe or bypass host.
            with read_db(path) as c:reason=eligibility(c,clock())
            if reason:emit('catchup','skipped',reason=reason);return 0
            if index:time.sleep(2)
            emit('catchup','attempt',**job)
            try:
                execute_job(path,job,logs,invocation)
            except Exception as error:
                kind=classify(error)
                emit('catchup','stopped',classification=kind,error=str(error),**job)
                print(f'Catch-up stopped: {kind}; invocation {invocation}')
                return 0 if kind=='lock_busy' else 1
        emit('catchup','finished',pages_considered=min(len(jobs),max_pages))
    return 0

def audit(path,logs,limit=20):
    with read_db(path) as c:
        c.row_factory=sqlite3.Row
        print('Gap totals:',[dict(r) for r in c.execute('SELECT symbol,dataset,status,COUNT(*) AS n FROM observation_gaps GROUP BY symbol,dataset,status')])
        print('Recent gap evidence:',[dict(r) for r in c.execute('SELECT * FROM observation_gaps ORDER BY reconciled_ms DESC LIMIT ?',(limit,))])
    # Bounded operational log inspection; explicitly disclose that older files are omitted.
    files=sorted(logs.glob('*.jsonl'),key=lambda p:p.stat().st_mtime,reverse=True)[:200]
    events=[]
    for file in files:
        for line in file.read_text().splitlines():
            try:row=json.loads(line)
            except ValueError:continue
            if row.get('stage') in ('recovery','catchup'):events.append(row)
    print('Recent recovery events (latest 200 log files only):')
    for row in sorted(events,key=lambda r:r.get('timestamp',''),reverse=True)[:limit]:print(json.dumps(row))
    _,_,outside,warning=inspect(path,time.time_ns()//1000000)
    print(f'OI near retention: {warning}; outside conservative window: {len(outside)} (not proven permanently unavailable)')

def main():
    p=argparse.ArgumentParser(description=__doc__)
    group=p.add_mutually_exclusive_group();group.add_argument('--execute',action='store_true');group.add_argument('--dry-run',action='store_true');group.add_argument('--audit',action='store_true')
    p.add_argument('--db-path',type=Path,default=DB_PATH);p.add_argument('--log-dir',type=Path,default=PROJECT_ROOT/'logs');p.add_argument('--max-pages',type=int,default=4)
    args=p.parse_args()
    if not 1<=args.max_pages<=8:p.error('--max-pages must be 1..8')
    if args.audit:audit(args.db_path,args.log_dir);return 0
    return run(args.db_path,args.log_dir,args.max_pages,args.execute)

if __name__=='__main__':raise SystemExit(main())
