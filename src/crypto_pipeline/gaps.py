"""Persistent detection and read-only status; never downloads or manufactures observations."""
import argparse
import sqlite3
from contextlib import closing
from time import time_ns
from .config import DB_PATH, SYMBOLS
from .normalization import INTERVAL_MS
from .time_utils import utc_label
from .reporting import console

STREAMS = {'oi': 'oi_observations', 'klines': 'price_candles'}
GRACE = {'oi': 600000, 'klines': 60000}


def reconcile(c, now_ms=None, run_id=None, start_ms=None):
    """Advance each persisted window; recheck only unresolved gaps plus new boundaries."""
    now = time_ns()//1000000 if now_ms is None else now_ms
    if start_ms is not None and (start_ms < 0 or start_ms % INTERVAL_MS):
        raise ValueError('Monitoring start must be a nonnegative exact 5m boundary')
    for symbol in SYMBOLS:
        for dataset, table in STREAMS.items():
            key = ('binance_usdm',symbol,dataset,'5m')
            end = ((now-GRACE[dataset])//INTERVAL_MS)*INTERVAL_MS
            state = c.execute('SELECT start_ms,checked_through_ms FROM monitoring_windows WHERE exchange=? AND symbol=? AND dataset=? AND interval=?',key).fetchone()
            if state is None:
                first = start_ms
                if first is None:
                    first = c.execute(f'SELECT MIN(bucket_end_ms) FROM {table} WHERE symbol=?',(symbol,)).fetchone()[0]
                    if first is None:
                        first = ((now+INTERVAL_MS-1)//INTERVAL_MS)*INTERVAL_MS
                c.execute('INSERT INTO monitoring_windows VALUES (?,?,?,?,?,NULL,NULL)',(*key,first))
                state = (first,None)
            elif start_ms is not None and start_ms != state[0]:
                raise ValueError('Monitoring start is immutable; review any window change separately')
            first = state[0] if state[1] is None else max(state[0],state[1]+INTERVAL_MS)
            found = {r[0] for r in c.execute(f'SELECT bucket_end_ms FROM {table} WHERE symbol=? AND bucket_end_ms BETWEEN ? AND ?',(symbol,first,end))}
            c.executemany('INSERT OR IGNORE INTO observation_gaps VALUES (?,?,?,?,?,?,?,\'missing\',NULL,?,NULL,NULL)',
                ((*key,t,now,now,run_id) for t in range(first,end+1,INTERVAL_MS) if t not in found))
            # Indexed exact-boundary lookups include old gaps recovered by out-of-order ingestion.
            missing = c.execute('SELECT bucket_end_ms FROM observation_gaps WHERE exchange=? AND symbol=? AND dataset=? AND interval=? AND status=\'missing\'',key).fetchall()
            for (boundary,) in missing:
                source = c.execute(f'SELECT raw_file_id FROM {table} WHERE symbol=? AND bucket_end_ms=? ORDER BY raw_file_id LIMIT 1',(symbol,boundary)).fetchone()
                if source:
                    c.execute("UPDATE observation_gaps SET status='recovered',recovered_ms=?,reconciled_ms=?,recovered_run_id=?,raw_file_id=? WHERE exchange=? AND symbol=? AND dataset=? AND interval=? AND bucket_end_ms=?",(now,now,run_id,source[0],*key,boundary))
                else:
                    c.execute('UPDATE observation_gaps SET reconciled_ms=? WHERE exchange=? AND symbol=? AND dataset=? AND interval=? AND bucket_end_ms=?',(now,*key,boundary))
            # Clock regression never moves the cursor backwards.
            cursor = max(end,state[1] if state[1] is not None else state[0]-INTERVAL_MS)
            c.execute('UPDATE monitoring_windows SET checked_through_ms=?,reconciled_ms=? WHERE exchange=? AND symbol=? AND dataset=? AND interval=?',(cursor,now,*key))


def ranges(boundaries):
    groups=[]
    for t in sorted(boundaries):
        if groups and t==groups[-1][1]+INTERVAL_MS:groups[-1]=(groups[-1][0],t)
        else:groups.append((t,t))
    return sorted(groups,key=lambda r:r[1]-r[0],reverse=True)


def status(path):
    with closing(sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True)) as c:
        c.execute('BEGIN')
        for exchange,symbol,dataset,interval,start,end,checked in c.execute('SELECT * FROM monitoring_windows ORDER BY symbol,dataset'):
            key=(exchange,symbol,dataset,interval)
            missing=[r[0] for r in c.execute("SELECT bucket_end_ms FROM observation_gaps WHERE exchange=? AND symbol=? AND dataset=? AND interval=? AND status='missing'",key)]
            recovered=c.execute("SELECT COUNT(*) FROM observation_gaps WHERE exchange=? AND symbol=? AND dataset=? AND interval=? AND status='recovered'",key).fetchone()[0]
            expected=max(0,(end-start)//INTERVAL_MS+1) if end is not None else 0
            console.print(f'{symbol} {dataset}: coverage at reconciliation {expected-len(missing)}/{expected}; missing {len(missing)}, recovered {recovered}',markup=False)
            console.print(f'  Window {utc_label(start)} — {utc_label(end) if end is not None else "not checked"}; reconciled {utc_label(checked) if checked else "never"}',markup=False)
            for a,b in ranges(missing)[:3]:console.print(f'  Missing range {utc_label(a)} — {utc_label(b)} ({(b-a)//INTERVAL_MS+1} observations)',markup=False)
        latest=c.execute("SELECT MAX(ended_ms) FROM pipeline_runs WHERE mode='online' AND status='succeeded'").fetchone()[0]
        console.print('Latest successful tracked collection: '+(utc_label(latest) if latest else 'unknown'),markup=False)
        console.print('OI absence may be delayed, omitted or unavailable; no cause is inferred. Status is read-only.')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=['status'])
    parser.add_argument('--db-path',type=__import__('pathlib').Path,default=DB_PATH)
    args=parser.parse_args()
    status(args.db_path)

if __name__=='__main__':main()
