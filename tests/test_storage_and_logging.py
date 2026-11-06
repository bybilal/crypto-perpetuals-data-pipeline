import json
import sqlite3
import subprocess
import sys
from pathlib import Path
import pytest
from crypto_pipeline.storage.migrations import apply_migrations, backup_database
from crypto_pipeline.storage.metadata import load_metadata
from crypto_pipeline.storage.schema import SCHEMA
from crypto_pipeline.events import logging_run, emit

@pytest.fixture
def database(tmp_path):
    path=tmp_path/'test.sqlite3'
    with sqlite3.connect(path) as c:
        c.execute('PRAGMA foreign_keys=ON')
        yield c,path

def test_legacy_migration_backup_and_idempotence(database):
    c,path=database
    c.executescript(SCHEMA)
    c.execute("INSERT INTO raw_files VALUES (1,'a','hash','BTCUSDT','oi','5m',300000,1)")
    c.execute("INSERT INTO oi_observations VALUES ('BTCUSDT',300000,300000,'1.000','2.000',NULL,1)")
    c.commit()
    before=c.execute('SELECT * FROM oi_observations').fetchall()
    apply_migrations(c,path)
    apply_migrations(c,path)
    assert c.execute('SELECT * FROM oi_observations').fetchall()==before
    backups=list((path.parent/'backups').glob('*.sqlite3'))
    assert len(backups)==1
    with sqlite3.connect(backups[0]) as old:
        assert old.execute('PRAGMA user_version').fetchone()[0]==0
        assert old.execute('SELECT * FROM oi_observations').fetchall()==before
    assert c.execute('PRAGMA user_version').fetchone()[0]==2
    assert c.execute('PRAGMA foreign_key_check').fetchall()==[]

def test_future_schema_rejected(database):
    c,path=database; c.execute('PRAGMA user_version=99')
    with pytest.raises(RuntimeError,match='future'): apply_migrations(c,path)

def test_migration_failure_rolls_back(database):
    c,path=database; c.execute('CREATE TABLE contracts (existing TEXT)'); c.commit()
    with pytest.raises(sqlite3.OperationalError): apply_migrations(c,path)
    assert c.execute('PRAGMA user_version').fetchone()[0]==0
    assert c.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()==[('contracts',)]

def test_actual_metadata_units_provenance_and_changed_file(database,samples,tmp_path):
    c,path=database; apply_migrations(c,path)
    raw=tmp_path/'raw'; raw.mkdir()
    source=raw/'exchangeInfo_20261106T190812555577Z.json'
    source.write_text(json.dumps(samples['exchangeInfo']))
    with c: assert load_metadata(c,raw,tmp_path)==1
    with c: assert load_metadata(c,raw,tmp_path)==0
    pepe=c.execute("SELECT base_asset_id,price_tick,quantity_step,contract_size,underlying_multiplier FROM contracts WHERE symbol='1000PEPEUSDT'").fetchone()
    assert pepe==('binance_usdm:1000PEPE','0.0000001','1',None,None)
    assert c.execute('SELECT count(*) FROM assets').fetchone()[0]==3
    assert c.execute('SELECT count(*) FROM metadata_sources').fetchone()[0]==1
    assert c.execute('PRAGMA foreign_key_check').fetchall()==[]
    source.write_text('{}')
    with pytest.raises(ValueError,match='changed'): load_metadata(c,raw,tmp_path)

def test_metadata_older_snapshot_does_not_override(database,samples,tmp_path):
    c,path=database; apply_migrations(c,path)
    raw=tmp_path/'raw'; raw.mkdir()
    (raw/'exchangeInfo_20261106T190812Z.json').write_text(json.dumps(samples['exchangeInfo']))
    with c: load_metadata(c,raw,tmp_path)
    samples['exchangeInfo']['symbols'][0]['status']='OLD'
    (raw/'exchangeInfo_20261105T190812Z.json').write_text(json.dumps(samples['exchangeInfo']))
    with c: load_metadata(c,raw,tmp_path)
    assert c.execute("SELECT status FROM contracts WHERE symbol='BTCUSDT'").fetchone()[0]=='TRADING'

def test_logs_no_console_output_and_separate_runs(tmp_path,capsys):
    for _ in range(2):
        with logging_run(tmp_path,human=True):
            emit('load','completed',counts={'oi':3},error='bad\x1b[31m red\nline')
    rows=[json.loads(p.read_text()) for p in tmp_path.glob('*.jsonl')]
    assert len(rows)==2 and rows[0]['run_id']!=rows[1]['run_id']
    assert all(row['timestamp'].endswith('Z') for row in rows)
    assert all('\x1b' not in p.read_text() for p in tmp_path.glob('*.log'))
    assert capsys.readouterr().out==''

def test_cli_offline_logs_and_error_exit(tmp_path,samples):
    raw=tmp_path/'raw'; raw.mkdir()
    (raw/'BTCUSDT_oi_20261106T230000Z.json').write_text(json.dumps(samples['BTCUSDT_oi']))
    command=[sys.executable,'src/run_pipeline.py','--offline','--raw-dir',str(raw),'--db-path',str(tmp_path/'db.sqlite3'),'--log-dir',str(tmp_path/'logs'),'--human-log']
    result=subprocess.run(command,capture_output=True,text=True)
    assert result.returncode==0,result.stdout+result.stderr
    events=[json.loads(line) for p in (tmp_path/'logs').glob('*.jsonl') for line in p.read_text().splitlines()]
    assert any(e['stage']=='fetch' and e['event']=='skipped' for e in events)
    assert events[-1]['event']=='completed'
    command[command.index('--raw-dir')+1]=str(tmp_path/'missing')
    result=subprocess.run(command,capture_output=True,text=True)
    assert result.returncode==1
    events=[json.loads(line) for p in (tmp_path/'logs').glob('*.jsonl') for line in p.read_text().splitlines()]
    assert any(e['event']=='failed' and e['error_type']=='FileNotFoundError' for e in events)

def test_contract_join_isolation_and_provenance_foreign_key(database):
    c,path=database; apply_migrations(c,path)
    c.execute("INSERT INTO raw_files VALUES (1,'fixture','hash','BTCUSDT','oi','5m',300000,1)")
    c.execute("INSERT INTO oi_observations VALUES ('1000PEPEUSDT',300000,300000,'1','2',NULL,1)")
    c.execute("INSERT INTO price_candles VALUES ('BTCUSDT',0,299999,300000,'1','1','1','1','1','1',1,'1','1',1)")
    from crypto_pipeline.storage.queries import database_snapshot
    assert database_snapshot(c)['contracts']['1000PEPEUSDT']['aligned']==0
    assert database_snapshot(c)['contracts']['BTCUSDT']['aligned']==0
    with pytest.raises(sqlite3.IntegrityError):
        c.execute("INSERT INTO oi_observations VALUES ('BTCUSDT',600000,600000,'1','2',NULL,999)")
