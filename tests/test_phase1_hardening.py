"""Phase 1 financial and operational regressions use only fixtures and temporary files."""
import copy
import json
import sqlite3
import subprocess
import sys
from decimal import Decimal, localcontext
import pytest
from crypto_pipeline import cli, reporting
from crypto_pipeline.coverage import recent_coverage
from crypto_pipeline.events import logging_run
from crypto_pipeline.storage.metadata import validate_specification, load_metadata
from crypto_pipeline.storage.migrations import apply_migrations
from crypto_pipeline.storage.records import insert_observation
from crypto_pipeline.normalization import normalize_oi
from crypto_pipeline.units import quote_delta, underlying_quantity


@pytest.mark.parametrize('field', ['baseAsset','quoteAsset','marginAsset','status','contractType','filters'])
def test_missing_metadata_field(samples, field):
    spec=copy.deepcopy(samples['exchangeInfo']['symbols'][0])
    del spec[field]
    with pytest.raises(ValueError):
        validate_specification(spec)


@pytest.mark.parametrize('value', ['NaN','Infinity','0','-1'])
def test_invalid_contract_size(samples,value):
    spec=copy.deepcopy(samples['exchangeInfo']['symbols'][0])
    spec['contractSize']=value
    with pytest.raises(ValueError):
        validate_specification(spec)


def test_duplicate_filter_and_missing_minimum(samples):
    spec=copy.deepcopy(samples['exchangeInfo']['symbols'][0])
    spec['filters'].append(spec['filters'][0])
    with pytest.raises(ValueError,match='Duplicate'):
        validate_specification(spec)
    spec=copy.deepcopy(samples['exchangeInfo']['symbols'][0])
    next(f for f in spec['filters'] if f['filterType']=='LOT_SIZE').pop('minQty')
    with pytest.raises(ValueError,match='minQty'):
        validate_specification(spec)


@pytest.mark.parametrize('problem', ['duplicate','missing','invalid'])
def test_metadata_error_preserves_existing_rows(samples,tmp_path,problem):
    raw=tmp_path/'raw';raw.mkdir()
    payload=copy.deepcopy(samples['exchangeInfo'])
    with sqlite3.connect(tmp_path/'test.sqlite3') as c:
        apply_migrations(c)
        (raw/'exchangeInfo_20261106T190000Z.json').write_text(json.dumps(payload))
        with c:
            load_metadata(c,raw,tmp_path)
        before=c.execute('SELECT * FROM contracts').fetchall()
        if problem=='duplicate':payload['symbols'].append(payload['symbols'][0])
        elif problem=='missing':payload['symbols'].pop()
        else:payload['symbols'][0]['baseAsset']=''
        (raw/'exchangeInfo_20261106T200000Z.json').write_text(json.dumps(payload))
        with pytest.raises(ValueError), c:
            load_metadata(c,raw,tmp_path)
        assert c.execute('SELECT * FROM contracts').fetchall()==before
        assert c.execute('SELECT COUNT(*) FROM metadata_sources').fetchone()[0]==1


def test_duplicate_keeps_every_original_value_and_provenance(samples,tmp_path):
    with sqlite3.connect(tmp_path/'test.sqlite3') as c:
        apply_migrations(c)
        c.execute('PRAGMA foreign_keys=ON')
        c.execute("INSERT INTO raw_files VALUES(1,'a','h','BTCUSDT','oi','5m',300000,1)")
        row=normalize_oi(samples['BTCUSDT_oi'][0],'BTCUSDT')
        assert insert_observation(c,'oi_observations',row,1)==1
        before=c.execute('SELECT * FROM oi_observations').fetchall()
        changed=dict(row,oi_quantity='999999',oi_notional_quote='999999')
        assert insert_observation(c,'oi_observations',changed,1)==0
        assert c.execute('SELECT * FROM oi_observations').fetchall()==before
        invalid=dict(row,source_timestamp_ms=row['source_timestamp_ms']+300000,oi_quantity=None)
        with pytest.raises(sqlite3.IntegrityError):
            insert_observation(c,'oi_observations',invalid,1)


def test_decimal_math_ignores_low_global_precision():
    with localcontext() as context:
        context.prec=6
        assert quote_delta('100000000000000000000000000000.01','50000000000000000000000000000.01')==Decimal('.01')
        assert underlying_quantity('1.00000000000000000000000000001','1000','synthetic fixture')==Decimal('1000.00000000000000000000000001')
        assert context.prec==6


def test_recent_missing_can_resolve_without_forward_fill(tmp_path):
    db=tmp_path/'test.sqlite3'
    with sqlite3.connect(db) as c:
        apply_migrations(c)
        c.execute("INSERT INTO raw_files VALUES(1,'a','h','BTCUSDT','oi','5m',7200000,1)")
    first=recent_coverage(db,7260000)['contracts'][0]
    assert 7200000 in first['oi_recent_missing_ms']
    assert 3900000 in first['oi_older_missing_ms']
    with sqlite3.connect(db) as c:
        c.execute("INSERT INTO oi_observations VALUES('BTCUSDT',7200000,7200000,'1','2',NULL,1)")
    second=recent_coverage(db,7560000)['contracts'][0]
    assert 7200000 not in second['oi_missing_ms']
    assert 7500000 in second['oi_missing_ms']
    assert second['candles']==0


def test_coverage_failure_never_logs_completed(tmp_path,monkeypatch):
    raw=tmp_path/'raw';raw.mkdir();(raw/'a.json').write_text('[]')
    db=tmp_path/'db.sqlite3';db.touch()
    monkeypatch.setattr(cli,'RAW_DIR',raw);monkeypatch.setattr(cli,'DB_PATH',db)
    monkeypatch.setattr(cli,'load_sqlite',lambda:{'file_errors':0,'invalid_records':0})
    def fail(path):raise sqlite3.DatabaseError('coverage failed')
    monkeypatch.setattr(cli,'display_recent_coverage',fail)
    with logging_run(tmp_path/'logs'):
        with pytest.raises(sqlite3.DatabaseError):
            cli.run_pipeline(offline=True,coverage=True)
    events=[json.loads(l) for p in (tmp_path/'logs').glob('*.jsonl') for l in p.read_text().splitlines()]
    assert not any(e['stage']=='pipeline' and e['event']=='completed' for e in events)


def test_critical_file_error_cli_status_and_log(tmp_path):
    raw=tmp_path/'raw';raw.mkdir()
    (raw/'BTCUSDT_oi_20261106T230000Z.json').write_text('{broken')
    result=subprocess.run([sys.executable,'-m','crypto_pipeline','--offline','--human-log','--coverage','--limit','25','--raw-dir',str(raw),'--db-path',str(tmp_path/'db.sqlite3'),'--log-dir',str(tmp_path/'logs')],capture_output=True,text=True)
    assert result.returncode==1
    events=[json.loads(l) for p in (tmp_path/'logs').glob('*.jsonl') for l in p.read_text().splitlines()]
    assert events[-1]['event']=='failed'
    assert not any(e['stage']=='pipeline' and e['event']=='completed' for e in events)
    assert '\x1b' not in next((tmp_path/'logs').glob('*.log')).read_text()


def test_external_raw_path_display(tmp_path,capsys):
    reporting.display_saved_path(tmp_path/'external.json',tmp_path/'other')
    assert 'external.json' in capsys.readouterr().out


def test_project_root_symlink_keeps_relative_provenance(tmp_path):
    import os
    real = tmp_path / 'real'
    real.mkdir()
    alias = tmp_path / 'alias'
    alias.symlink_to(real, target_is_directory=True)
    result = subprocess.run(
        [sys.executable, '-c',
         'from crypto_pipeline.config import PROJECT_ROOT; print(PROJECT_ROOT)'],
        env=dict(os.environ, CRYPTO_PIPELINE_ROOT=str(alias)),
        capture_output=True, text=True, check=True,
    )
    assert result.stdout.strip() == str(real.resolve())
