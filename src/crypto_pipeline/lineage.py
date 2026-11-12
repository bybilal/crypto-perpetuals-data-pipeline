"""Durable execution lifecycle sharing JSONL IDs, called inside the existing CLI lock."""
from contextlib import contextmanager, closing
import sqlite3
from time import time_ns
from .storage.migrations import apply_migrations
from .gaps import reconcile
from .events import emit

@contextmanager
def tracked_run(path, run_id, offline, mode=None):
    with closing(sqlite3.connect(path)) as c:
        c.execute('PRAGMA foreign_keys=ON')
        apply_migrations(c,path)
        before={t:c.execute(f'SELECT COALESCE(MAX(id),0) FROM {t}').fetchone()[0] for t in ('raw_files','metadata_sources')}
        with c:
            c.execute("INSERT INTO pipeline_runs VALUES (?,?,NULL,?,NULL,'running',NULL)",(run_id,time_ns()//1000000,mode or ('offline' if offline else 'online')))
        error=None
        try:
            yield
        except BaseException as exc:
            error=exc
            raise
        finally:
            try:
                with c:
                    for table,column in (('raw_files','raw_file_id'),('metadata_sources','metadata_source_id')):
                        c.execute(f'INSERT INTO run_sources(run_id,{column}) SELECT ?,id FROM {table} WHERE id>?',(run_id,before[table]))
                    reconcile(c,run_id=run_id)
                    c.execute('UPDATE pipeline_runs SET ended_ms=?,status=?,error=? WHERE run_id=?',(time_ns()//1000000,'failed' if error else 'succeeded',str(error) if error else None,run_id))
                emit('reconciliation','completed',run_id=run_id)
            except Exception as tracking_error:
                with c:
                    c.execute("UPDATE pipeline_runs SET ended_ms=?,status='failed',error=? WHERE run_id=?",(time_ns()//1000000,str(tracking_error),run_id))
                if error is None:raise
