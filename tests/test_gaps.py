import sqlite3
import pytest
from crypto_pipeline.storage.migrations import apply_migrations
from crypto_pipeline.gaps import reconcile,ranges,status
from crypto_pipeline.lineage import tracked_run

@pytest.fixture
def db(tmp_path):
    path=tmp_path/'db.sqlite3'
    c=sqlite3.connect(path);c.execute('PRAGMA foreign_keys=ON');apply_migrations(c)
    yield c,path
    c.close()

def test_grace_and_outage(db):
    c,_=db
    with c:reconcile(c,900000,start_ms=300000)
    assert c.execute("SELECT COUNT(*) FROM observation_gaps WHERE dataset='oi'").fetchone()[0]==2
    assert c.execute("SELECT COUNT(*) FROM observation_gaps WHERE dataset='klines'").fetchone()[0]==4
    with c:reconcile(c,3*86400000)
    count=c.execute('SELECT COUNT(*) FROM observation_gaps').fetchone()[0]
    with c:reconcile(c,3*86400000)
    assert c.execute('SELECT COUNT(*) FROM observation_gaps').fetchone()[0]==count
    assert count>3000
    assert c.execute('SELECT COUNT(*) FROM observation_gaps WHERE raw_file_id IS NOT NULL').fetchone()[0]==0

def test_recovery_preserves_history(db):
    c,_=db
    with c:reconcile(c,900000,start_ms=300000)
    detected=c.execute("SELECT detected_ms FROM observation_gaps WHERE symbol='BTCUSDT' AND dataset='oi'").fetchone()[0]
    with c:
        c.execute("INSERT INTO raw_files VALUES (1,'test','hash','BTCUSDT','oi','5m',900000,1)")
        c.execute("INSERT INTO oi_observations VALUES ('BTCUSDT',300000,300000,'1','2',NULL,1)")
        reconcile(c,1200000)
    assert c.execute("SELECT status,raw_file_id,detected_ms,recovered_ms FROM observation_gaps WHERE symbol='BTCUSDT' AND dataset='oi' AND bucket_end_ms=300000").fetchone()==('recovered',1,detected,1200000)
    with c:reconcile(c,1500000)
    assert c.execute("SELECT recovered_ms FROM observation_gaps WHERE status='recovered'").fetchone()[0]==1200000
    assert c.execute('PRAGMA foreign_key_check').fetchall()==[]

def test_alignment_and_unique_constraints(db):
    c,_=db
    with pytest.raises(ValueError):reconcile(c,1000000,start_ms=1)
    with c:reconcile(c,1000000,start_ms=300000)
    with pytest.raises(sqlite3.IntegrityError):c.execute('INSERT INTO observation_gaps SELECT * FROM observation_gaps LIMIT 1')
    c.rollback()
    with pytest.raises(sqlite3.IntegrityError):c.execute("UPDATE observation_gaps SET raw_file_id=999")
    c.rollback()
    assert ranges([300000,600000,1200000])==[(300000,600000),(1200000,1200000)]

def test_runs_failure_and_new_source_lineage(db):
    c,path=db
    with tracked_run(path,'same-as-jsonl',True):
        with c:c.execute("INSERT INTO raw_files VALUES(1,'a','h','BTCUSDT','oi','5m',900000,0)")
    assert c.execute('SELECT run_id,raw_file_id FROM run_sources').fetchall()==[('same-as-jsonl',1)]
    assert c.execute('SELECT trigger,status FROM pipeline_runs').fetchone()==(None,'succeeded')
    with pytest.raises(ValueError),tracked_run(path,'failed',False):raise ValueError('fixture failure')
    assert c.execute("SELECT status,error FROM pipeline_runs WHERE run_id='failed'").fetchone()==('failed','fixture failure')

def test_status_read_only_and_repeat_migration(db):
    c,path=db
    with c:reconcile(c,1000000,start_ms=300000)
    before=list(c.iterdump());apply_migrations(c);status(path)
    assert list(c.iterdump())==before
