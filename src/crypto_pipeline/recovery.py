"""Bounded manual recovery from registered gaps; dry-run is the default."""
import argparse
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import time
from urllib.parse import urlencode
from . import binance
from .config import DB_PATH, PROJECT_ROOT, SYMBOLS
from .events import logging_run, emit
from .gaps import ranges, STREAMS
from .lineage import tracked_run
from .locking import pipeline_lock
from .storage.loader import load_files
from .reporting import console

STEP=300000


def plan(c,now_ms,limit=499):
    if not 1<=limit<=499:raise ValueError('Page size must be 1..499')
    jobs=[];outside=[]
    for dataset in ('oi','klines'):
        for symbol in SYMBOLS:
            stamps=[r[0] for r in c.execute("SELECT bucket_end_ms FROM observation_gaps WHERE exchange='binance_usdm' AND symbol=? AND dataset=? AND interval='5m' AND status='missing' ORDER BY bucket_end_ms",(symbol,dataset))]
            eligible=[]
            for t in stamps:
                if dataset=='oi' and t < now_ms-30*86400000:outside.append((symbol,dataset,t))
                else:eligible.append(t)
            for start,end in sorted(ranges(eligible)):
                for a in range(start,end+1,limit*STEP):
                    b=min(end,a+(limit-1)*STEP)
                    jobs.append({'symbol':symbol,'dataset':dataset,'first':a,'last':b,'expected':(b-a)//STEP+1})
    return jobs,outside


def request_url(job):
    candle=job['dataset']=='klines'
    endpoint='/fapi/v1/klines' if candle else '/futures/data/openInterestHist'
    params={'symbol':job['symbol'],'interval' if candle else 'period':'5m',
            'startTime':job['first']-STEP if candle else job['first'],
            'endTime':job['last']-1 if candle else job['last'], 'limit':job['expected']}
    return binance.BASE_URL+endpoint+'?'+urlencode(params)


def missing(c,job):
    return c.execute("SELECT COUNT(*) FROM observation_gaps WHERE exchange='binance_usdm' AND symbol=? AND dataset=? AND interval='5m' AND status='missing' AND bucket_end_ms BETWEEN ? AND ?",(job['symbol'],job['dataset'],job['first'],job['last'])).fetchone()[0]


def execute_job(path,job,log_dir):
    # Each page is an independent committed run. Release the shared collector lock between pages.
    with logging_run(log_dir,human=True) as run_id:
        try:
            with pipeline_lock(path),tracked_run(path,run_id,False,mode='recovery'):
                with closing(sqlite3.connect(path)) as c:
                    c.execute('PRAGMA foreign_keys=ON')
                    before=missing(c,job)
                    if not before:return
                    url=request_url(job)
                    emit('recovery','requested',**job,url=url)
                    binance.RAW_DIR.mkdir(parents=True,exist_ok=True)
                    data,raw=binance.request_and_save(url,job['symbol']+'_'+job['dataset'])
                    # Sidecar binds request bounds and execution ID to unmodified response bytes.
                    raw.with_suffix('.request.json').write_text(json.dumps({'run_id':run_id,'url':url,'target':job},indent=2))
                    if not isinstance(data,list):raise ValueError('Expected list response')
                    with c:
                        stats=load_files(c,paths=[raw])
                        if stats['file_errors'] or stats['invalid_records']:raise ValueError('Recovery response failed validation')
                    emit('recovery','ingested',raw_path=str(raw),returned=len(data),**stats)
            # The lineage context reconciles verified stored rows before this outcome is emitted.
            with closing(sqlite3.connect(path)) as c:remaining=missing(c,job)
            emit('recovery','completed',**job,remaining=remaining,recovered=before-remaining,
                 outcome='fully_recovered' if remaining==0 else 'partially_recovered' if remaining<before else 'provider_unobserved_in_response')
            console.print(f"{job['symbol']} {job['dataset']}: recovered {before-remaining}, unresolved {remaining}; run {run_id}")
        except Exception as error:
            emit('recovery','failed',error=str(error),**job)
            raise


def main():
    p=argparse.ArgumentParser(description=__doc__)
    mode=p.add_mutually_exclusive_group();mode.add_argument('--dry-run',action='store_true');mode.add_argument('--execute',action='store_true')
    p.add_argument('--db-path',type=Path,default=DB_PATH)
    p.add_argument('--max-requests',type=int,default=24)
    args=p.parse_args()
    if not 1<=args.max_requests<=100:p.error('--max-requests must be 1..100')
    with closing(sqlite3.connect(args.db_path.resolve().as_uri()+'?mode=ro',uri=True)) as c:
        c.execute('BEGIN');jobs,outside=plan(c,time.time_ns()//1000000)
    selected=jobs[:args.max_requests]
    console.print(f'Recovery plan: {len(jobs)} pages, {sum(j["expected"] for j in jobs)} target observations; executing at most {len(selected)} pages. OI first.')
    console.print(f'OI outside conservative 30-day API window: {len(outside)}; retained unresolved, not declared permanently unavailable.')
    for job in selected:console.print(json.dumps(job))
    if not args.execute:return 0
    try:
        for index,job in enumerate(selected):
            if index:time.sleep(2)
            execute_job(args.db_path,job,PROJECT_ROOT/'logs')
        return 0
    except Exception as error:
        console.print(f'Recovery stopped: {error}. Prior batches remain committed; inspect logs and dry-run before resuming.',markup=False)
        return 1

if __name__=='__main__':raise SystemExit(main())
