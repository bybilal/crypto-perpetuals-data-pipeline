"""Audit a consistent SQLite snapshot and replay its indexed sources in an isolated directory."""
# Run from the repository using .venv/bin/python scripts/validate_pipeline.py.
from collections import Counter
from contextlib import closing
from datetime import datetime, timezone
from decimal import Decimal, localcontext
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile

from crypto_pipeline.config import PROJECT_ROOT, DB_PATH
from crypto_pipeline.locking import pipeline_lock
from crypto_pipeline.normalization import normalize_oi, normalize_kline
from crypto_pipeline.storage.records import COLUMNS
from crypto_pipeline.coverage import recent_coverage
from crypto_pipeline.time_utils import utc_label


def table_rows(connection):
    """Read full rows, including primary keys, decimals and source references."""
    names=[row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
    return {name: connection.execute('SELECT * FROM "'+name.replace('"','""')+'"').fetchall() for name in names}


def main():
    # Snapshot and copy only indexed files while the CLI scheduler is excluded by the same lock.
    with tempfile.TemporaryDirectory(prefix='crypto-validation-') as temporary:
        root=Path(temporary)
        db=root/'data/db/market_data.sqlite3'
        db.parent.mkdir(parents=True)
        with pipeline_lock(DB_PATH), closing(sqlite3.connect(DB_PATH.resolve().as_uri()+'?mode=ro',uri=True)) as source:
            with closing(sqlite3.connect(db)) as copy:
                source.backup(copy)
                references=copy.execute('SELECT file_path,sha256 FROM raw_files UNION ALL SELECT file_path,sha256 FROM metadata_sources').fetchall()
                for name,digest in references:
                    path=Path(name)
                    # A snapshot built with external overrides needs its own explicit replay mapping.
                    if path.is_absolute() or '..' in path.parts:
                        raise RuntimeError('Audit replay requires repository-relative indexed source paths')
                    payload=(PROJECT_ROOT/path).read_bytes()
                    assert hashlib.sha256(payload).hexdigest()==digest, name
                    target=root/path
                    target.parent.mkdir(parents=True,exist_ok=True)
                    target.write_bytes(payload)
        # Read-only validation checks both database constraints and application-level joins.
        with closing(sqlite3.connect(db)) as c:
            before=table_rows(c)
            # Operational lineage intentionally changes on replay; financial/reference rows must not.
            operational={'pipeline_runs','run_sources','monitoring_windows','observation_gaps'}
            assert c.execute('PRAGMA integrity_check').fetchall()==[('ok',)]
            assert c.execute('PRAGMA foreign_key_check').fetchall()==[]
            report={'audited_at_utc':datetime.now(timezone.utc).isoformat(),
                    'schema_version':c.execute('PRAGMA user_version').fetchone()[0],
                    'counts':{t:len(rows) for t,rows in before.items()},
                    'verified_source_checksums':len(references),'integrity':'ok','foreign_key_violations':0}
            report['schema']={t:{'columns':c.execute(f'PRAGMA table_info({t})').fetchall(),
                                 'foreign_keys':c.execute(f'PRAGMA foreign_key_list({t})').fetchall(),
                                 'indexes':c.execute(f'PRAGMA index_list({t})').fetchall()} for t in before}
            raw_by_id={row[0]:row for row in before['raw_files']}
            # Every observation must be reproducible from its exact linked source record.
            for table,normalizer in [('oi_observations',normalize_oi),('price_candles',normalize_kline)]:
                columns=COLUMNS[table]
                for row in before[table]:
                    source_row=raw_by_id[row[-1]]
                    assert source_row[3]==row[0]
                    assert source_row[4]==('oi' if table=='oi_observations' else 'klines')
                    payload=json.loads((root/source_row[1]).read_text())
                    candidates=[]
                    for item in payload:
                        normalized=normalizer(item,row[0])
                        candidates.append(tuple(normalized[k] for k in columns))
                    assert tuple(row[:-1]) in candidates,(table,row[:2])
                    if table=='price_candles':
                        assert row[3]<=source_row[6], 'Unfinished candle in normalized table'
                # Physical SQLite types must match the schema's declared INTEGER/TEXT columns.
                for _,name,kind,*_ in c.execute(f'PRAGMA table_info({table})'):
                    types={x[0] for x in c.execute(f'SELECT DISTINCT typeof({name}) FROM {table}')}
                    assert types <= ({'integer','null'} if kind=='INTEGER' else {'text','null'}),(table,name,types)
            report['lineage']='All normalized OI and candles reproduce from linked source files'
            report['unmatched_contracts']={t:c.execute(f'SELECT DISTINCT symbol FROM {t} WHERE symbol NOT IN (SELECT symbol FROM contracts)').fetchall() for t in COLUMNS}
            assert not any(report['unmatched_contracts'].values()), 'Observation has no contract reference'
            # Metadata payloads and selected contract specifications must match their retained sources.
            metadata = {row[0]: row for row in before['metadata_sources']}
            for row in metadata.values():
                assert row[4] == (root / row[1]).read_text()
            for row in before['contracts']:
                source_row = metadata[row[12]]
                specifications = json.loads(source_row[4])['symbols']
                assert json.loads(row[14]) == next(s for s in specifications if s['symbol'] == row[0])
                assert row[13] == source_row[3]
            report['metadata_lineage'] = 'Stored payloads, selected specifications and retrieval timestamps match linked sources'
            report['financial_checks']={}
            with localcontext() as context:
                context.prec=50
                for symbol in ('BTCUSDT','1000PEPEUSDT'):
                    rows=c.execute('''SELECT o.bucket_end_ms,o.oi_quantity,o.oi_notional_quote,k.close_price
                        FROM oi_observations o JOIN price_candles k ON o.symbol=k.symbol AND o.bucket_end_ms=k.bucket_end_ms
                        WHERE o.symbol=? ORDER BY o.bucket_end_ms''',(symbol,)).fetchall()
                    values=[]
                    for stamp,quantity,notional,close in rows:
                        if Decimal(quantity)==0:
                            continue
                        implied=Decimal(notional)/Decimal(quantity)
                        ratio=implied/Decimal(close)
                        values.append({'utc':utc_label(stamp),'implied_price':str(implied),
                                       'candle_close':close,'ratio':str(ratio),'difference_ppm':str((ratio-1)*1_000_000)})
                    report['financial_checks'][symbol]={'aligned_samples':len(values),
                        'examples':[values[i] for i in sorted({0,len(values)//2,len(values)-1})] if values else [],
                        'largest_difference':max(values,key=lambda x:abs(Decimal(x['difference_ppm']))) if values else None}
            report['coverage']=recent_coverage(db)
        # Run the ordinary CLI twice using a private project root, preserving relative provenance paths.
        env=dict(os.environ,CRYPTO_PIPELINE_ROOT=str(root))
        for iteration in (1,2):
            result=subprocess.run([sys.executable,'-m','crypto_pipeline','--offline','--human-log','--coverage','--limit','25'],env=env,capture_output=True,text=True)
            assert result.returncode==0,result.stdout+result.stderr
            with closing(sqlite3.connect(db)) as c:
                after=table_rows(c)
                assert before.keys()==after.keys()
                assert all(Counter(before[t])==Counter(after[t]) for t in before if t not in operational),'Replay changed existing rows'
        report['isolated_replays']=2
        report['idempotency']='Every row in all market/reference tables is unchanged (operational lineage excluded) after both ordinary offline CLI runs'
        print(json.dumps(report,indent=2))


if __name__=='__main__':
    main()
