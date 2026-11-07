# Import json for use below.
import json
# Import sqlite3 for use below.
import sqlite3
# Import subprocess for use below.
import subprocess
# Import sys for use below.
import sys
# Import Path from pathlib for use below.
from pathlib import Path
# Import pytest for use below.
import pytest
# Import apply_migrations, backup_database from crypto_pipeline.storage.migrations for use below.
from crypto_pipeline.storage.migrations import apply_migrations, backup_database
# Import load_metadata from crypto_pipeline.storage.metadata for use below.
from crypto_pipeline.storage.metadata import load_metadata
# Import SCHEMA from crypto_pipeline.storage.schema for use below.
from crypto_pipeline.storage.schema import SCHEMA
# Import logging_run, emit from crypto_pipeline.events for use below.
from crypto_pipeline.events import logging_run, emit

# Define database with the inputs listed below.
@pytest.fixture
def database(tmp_path):
    # Construct the path or ratio from the specified components; store the result in path.
    path=tmp_path/'test.sqlite3'
    # Open a database transaction context; commit on success or roll back on failure.
    with sqlite3.connect(path) as c:
        # Enable SQLite foreign-key validation for this connection.
        c.execute('PRAGMA foreign_keys=ON')
        # Use (yield (c, path)).
        yield c,path

# Define test legacy migration backup and idempotence with the inputs listed below.
def test_legacy_migration_backup_and_idempotence(database):
    # Use database; store the result in (c, path).
    c,path=database
    # Execute the schema SQL; migration scripts supply their own transaction boundaries.
    c.executescript(SCHEMA)
    # Persist the supplied fields using SQL parameters instead of string interpolation.
    c.execute("INSERT INTO raw_files VALUES (1,'a','hash','BTCUSDT','oi','5m',300000,1)")
    # Persist the supplied fields using SQL parameters instead of string interpolation.
    c.execute("INSERT INTO oi_observations VALUES ('BTCUSDT',300000,300000,'1.000','2.000',NULL,1)")
    # Make the pending database changes durable.
    c.commit()
    # Read all result rows from the SQL query; store the result in before.
    before=c.execute('SELECT * FROM oi_observations').fetchall()
    # Apply any required schema upgrades, backing up an existing database first.
    apply_migrations(c,path)
    # Apply any required schema upgrades, backing up an existing database first.
    apply_migrations(c,path)
    # Verify the expected condition: c.execute('SELECT * FROM oi_observations').fetchall() == before.
    assert c.execute('SELECT * FROM oi_observations').fetchall()==before
    # Call list with the supplied arguments; store the result in backups.
    backups=list((path.parent/'backups').glob('*.sqlite3'))
    # Verify the expected condition: len(backups) == 1.
    assert len(backups)==1
    # Open a database transaction context; commit on success or roll back on failure.
    with sqlite3.connect(backups[0]) as old:
        # Verify the expected condition: old.execute('PRAGMA user_version').fetchone()[0] == 0.
        assert old.execute('PRAGMA user_version').fetchone()[0]==0
        # Verify the expected condition: old.execute('SELECT * FROM oi_observations').fetchall() == before.
        assert old.execute('SELECT * FROM oi_observations').fetchall()==before
    # Verify the expected condition: c.execute('PRAGMA user_version').fetchone()[0] == 2.
    assert c.execute('PRAGMA user_version').fetchone()[0]==3
    # Verify the expected condition: c.execute('PRAGMA foreign_key_check').fetchall() == [].
    assert c.execute('PRAGMA foreign_key_check').fetchall()==[]

# Define test future schema rejected with the inputs listed below.
def test_future_schema_rejected(database):
    # Use database; store the result in (c, path).
    c,path=database; c.execute('PRAGMA user_version=99')
    # Check that this invalid input raises the expected exception.
    with pytest.raises(RuntimeError,match='future'): apply_migrations(c,path)

# Define test migration failure rolls back with the inputs listed below.
def test_migration_failure_rolls_back(database):
    # Use database; store the result in (c, path).
    c,path=database; c.execute('CREATE TABLE contracts (existing TEXT)'); c.commit()
    # Check that this invalid input raises the expected exception.
    with pytest.raises(sqlite3.OperationalError): apply_migrations(c,path)
    # Verify the expected condition: c.execute('PRAGMA user_version').fetchone()[0] == 0.
    assert c.execute('PRAGMA user_version').fetchone()[0]==0
    # Verify the failed migration left only the original table.
    assert c.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()==[('contracts',)]

# Define test actual metadata units provenance and changed file with the inputs listed below.
def test_actual_metadata_units_provenance_and_changed_file(database,samples,tmp_path):
    # Use database; store the result in (c, path).
    c,path=database; apply_migrations(c,path)
    # Construct the path or ratio from the specified components; store the result in raw.
    raw=tmp_path/'raw'; raw.mkdir()
    # Construct the path or ratio from the specified components; store the result in source.
    source=raw/'exchangeInfo_20261106T190812555577Z.json'
    # Write the specified text to the file.
    source.write_text(json.dumps(samples['exchangeInfo']))
    # Commit this batch on success; roll it back if an exception escapes.
    with c: assert load_metadata(c,raw,tmp_path)==1
    # Commit this batch on success; roll it back if an exception escapes.
    with c: assert load_metadata(c,raw,tmp_path)==0
    # Read the first result row from the SQL query; store the result in pepe.
    pepe=c.execute("SELECT base_asset_id,price_tick,quantity_step,contract_size,underlying_multiplier FROM contracts WHERE symbol='1000PEPEUSDT'").fetchone()
    # Verify the expected condition: pepe == ('binance_usdm:1000PEPE', '0.0000001', '1', None, None).
    assert pepe==('binance_usdm:1000PEPE','0.0000001','1',None,None)
    # Verify the expected condition: c.execute('SELECT count(*) FROM assets').fetchone()[0] == 3.
    assert c.execute('SELECT count(*) FROM assets').fetchone()[0]==3
    # Verify the expected condition: c.execute('SELECT count(*) FROM metadata_sources').fetchone()[0] == 1.
    assert c.execute('SELECT count(*) FROM metadata_sources').fetchone()[0]==1
    # Verify the expected condition: c.execute('PRAGMA foreign_key_check').fetchall() == [].
    assert c.execute('PRAGMA foreign_key_check').fetchall()==[]
    # Write the specified text to the file.
    source.write_text('{}')
    # Check that this invalid input raises the expected exception.
    with pytest.raises(ValueError,match='changed'): load_metadata(c,raw,tmp_path)

# Define test metadata older snapshot does not override with the inputs listed below.
def test_metadata_older_snapshot_does_not_override(database,samples,tmp_path):
    # Use database; store the result in (c, path).
    c,path=database; apply_migrations(c,path)
    # Construct the path or ratio from the specified components; store the result in raw.
    raw=tmp_path/'raw'; raw.mkdir()
    # Write the specified text to the file.
    (raw/'exchangeInfo_20261106T190812Z.json').write_text(json.dumps(samples['exchangeInfo']))
    # Commit this batch on success; roll it back if an exception escapes.
    with c: load_metadata(c,raw,tmp_path)
    # Use the explicit text 'OLD'; store the result in samples['exchangeInfo']['symbols'][0]['status'].
    samples['exchangeInfo']['symbols'][0]['status']='OLD'
    # Write the specified text to the file.
    (raw/'exchangeInfo_20261105T190812Z.json').write_text(json.dumps(samples['exchangeInfo']))
    # Commit this batch on success; roll it back if an exception escapes.
    with c: load_metadata(c,raw,tmp_path)
    # Verify an older metadata snapshot cannot overwrite a newer contract status.
    assert c.execute("SELECT status FROM contracts WHERE symbol='BTCUSDT'").fetchone()[0]=='TRADING'

# Define test logs no console output and separate runs with the inputs listed below.
def test_logs_no_console_output_and_separate_runs(tmp_path,capsys):
    # Process each _ from range(2).
    for _ in range(2):
        # Open this run's log files and restore the logging context when the run ends.
        with logging_run(tmp_path,human=True):
            # Write this stage event to the active run logs without printing to the terminal.
            emit('load','completed',counts={'oi':3},error='bad\x1b[31m red\nline')
    # Build a collection by selecting and transforming the specified inputs; store the result in rows.
    rows=[json.loads(p.read_text()) for p in tmp_path.glob('*.jsonl')]
    # Verify the expected condition: len(rows) == 2 and rows[0]['run_id'] != rows[1]['run_id'].
    assert len(rows)==2 and rows[0]['run_id']!=rows[1]['run_id']
    # Verify the expected condition: all((row['timestamp'].endswith('Z') for row in rows)).
    assert all(row['timestamp'].endswith('Z') for row in rows)
    # Verify the expected condition: all(('\x1b' not in p.read_text() for p in tmp_path.glob('*.log'))).
    assert all('\x1b' not in p.read_text() for p in tmp_path.glob('*.log'))
    # Verify the expected condition: capsys.readouterr().out == ''.
    assert capsys.readouterr().out==''

# Define test cli offline logs and error exit with the inputs listed below.
def test_cli_offline_logs_and_error_exit(tmp_path,samples):
    # Construct the path or ratio from the specified components; store the result in raw.
    raw=tmp_path/'raw'; raw.mkdir()
    # Write the specified text to the file.
    (raw/'BTCUSDT_oi_20261106T230000Z.json').write_text(json.dumps(samples['BTCUSDT_oi']))
    # Build the ordered collection used by this operation; store the result in command.
    command=[sys.executable,'src/run_pipeline.py','--offline','--raw-dir',str(raw),'--db-path',str(tmp_path/'db.sqlite3'),'--log-dir',str(tmp_path/'logs'),'--human-log']
    # Run the command and capture its exit status and any requested output; store the result in result.
    result=subprocess.run(command,capture_output=True,text=True)
    # Verify the expected condition: result.returncode == 0.
    assert result.returncode==0,result.stdout+result.stderr
    # Build a collection by selecting and transforming the specified inputs; store the result in events.
    events=[json.loads(line) for p in (tmp_path/'logs').glob('*.jsonl') for line in p.read_text().splitlines()]
    # Verify the expected condition: any((e['stage'] == 'fetch' and e['event'] == 'skipped' for e in events)).
    assert any(e['stage']=='fetch' and e['event']=='skipped' for e in events)
    # Verify the expected condition: events[-1]['event'] == 'completed'.
    assert events[-1]['event']=='completed'
    # Represent the value as text; store the result in command[command.index('--raw-dir') + 1].
    command[command.index('--raw-dir')+1]=str(tmp_path/'missing')
    # Run the command and capture its exit status and any requested output; store the result in result.
    result=subprocess.run(command,capture_output=True,text=True)
    # Verify the expected condition: result.returncode == 1.
    assert result.returncode==1
    # Build a collection by selecting and transforming the specified inputs; store the result in events.
    events=[json.loads(line) for p in (tmp_path/'logs').glob('*.jsonl') for line in p.read_text().splitlines()]
    # Verify the failed CLI run logged the missing-source exception.
    assert any(e['event']=='failed' and e['error_type']=='FileNotFoundError' for e in events)

# Define test contract join isolation and provenance foreign key with the inputs listed below.
def test_contract_join_isolation_and_provenance_foreign_key(database):
    # Use database; store the result in (c, path).
    c,path=database; apply_migrations(c,path)
    # Persist the supplied fields using SQL parameters instead of string interpolation.
    c.execute("INSERT INTO raw_files VALUES (1,'fixture','hash','BTCUSDT','oi','5m',300000,1)")
    # Persist the supplied fields using SQL parameters instead of string interpolation.
    c.execute("INSERT INTO oi_observations VALUES ('1000PEPEUSDT',300000,300000,'1','2',NULL,1)")
    # Persist the supplied fields using SQL parameters instead of string interpolation.
    c.execute("INSERT INTO price_candles VALUES ('BTCUSDT',0,299999,300000,'1','1','1','1','1','1',1,'1','1',1)")
    # Import database_snapshot from crypto_pipeline.storage.queries for use below.
    from crypto_pipeline.storage.queries import database_snapshot
    # Verify the expected condition: database_snapshot(c)['contracts']['1000PEPEUSDT']['aligned'] == 0.
    assert database_snapshot(c)['contracts']['1000PEPEUSDT']['aligned']==0
    # Verify the expected condition: database_snapshot(c)['contracts']['BTCUSDT']['aligned'] == 0.
    assert database_snapshot(c)['contracts']['BTCUSDT']['aligned']==0
    # Check that this invalid input raises the expected exception.
    with pytest.raises(sqlite3.IntegrityError):
        # Persist the supplied fields using SQL parameters instead of string interpolation.
        c.execute("INSERT INTO oi_observations VALUES ('BTCUSDT',600000,600000,'1','2',NULL,999)")
