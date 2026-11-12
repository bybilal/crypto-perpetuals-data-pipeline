import sqlite3
from urllib.parse import urlparse,parse_qs
import pytest
from crypto_pipeline.recovery import plan,request_url,execute_job
from crypto_pipeline.storage.migrations import apply_migrations
from crypto_pipeline.gaps import reconcile
from crypto_pipeline.locking import pipeline_lock

def test_planning_pagination_retention(tmp_path):
 with sqlite3.connect(tmp_path/'db') as c:
  apply_migrations(c)
  with c:reconcile(c,900000,start_ms=300000)
  jobs,old=plan(c,900000,1)
  assert jobs[0]['dataset']=='oi' and all(j['expected']==1 for j in jobs)
  assert not old
  oi=parse_qs(urlparse(request_url(jobs[0])).query)
  assert oi['startTime']==['300000'] and oi['endTime']==['300000']
  candle=next(j for j in jobs if j['dataset']=='klines')
  q=parse_qs(urlparse(request_url(candle)).query)
  assert q['startTime']==['0'] and q['endTime']==['299999']
  remaining,old=plan(c,40*86400000)
  assert old and all(j['dataset']=='klines' for j in remaining)
  with pytest.raises(ValueError):plan(c,900000,0)

def test_partial_and_resume(tmp_path,monkeypatch):
 import json
 from crypto_pipeline import recovery, lineage
 monkeypatch.setattr(lineage,"reconcile",lambda c,run_id=None: reconcile(c,1200000,run_id=run_id))
 db=tmp_path/'db'
 with sqlite3.connect(db) as c:
  apply_migrations(c)
  with c:reconcile(c,1200000,start_ms=300000)
 job={'symbol':'BTCUSDT','dataset':'oi','first':300000,'last':600000,'expected':2}
 path=tmp_path/'BTCUSDT_oi_20261112T090000Z.json'
 payload=[{'symbol':'BTCUSDT','timestamp':300000,'sumOpenInterest':'1','sumOpenInterestValue':'2'}]
 path.write_text(json.dumps(payload))
 monkeypatch.setattr(recovery.binance,'RAW_DIR',tmp_path)
 monkeypatch.setattr(recovery.binance,'request_and_save',lambda *a:(payload,path))
 execute_job(db,job,tmp_path/'logs')
 with sqlite3.connect(db) as c:
  assert c.execute("SELECT status,raw_file_id FROM observation_gaps WHERE symbol='BTCUSDT' AND dataset='oi' AND bucket_end_ms=300000").fetchone()==('recovered',1)
  original=c.execute('SELECT * FROM oi_observations').fetchall()
 execute_job(db,job,tmp_path/'logs')
 with sqlite3.connect(db) as c:
  assert c.execute('SELECT * FROM oi_observations').fetchall()==original
  assert c.execute('PRAGMA foreign_key_check').fetchall()==[]
  assert c.execute('SELECT count(*) FROM run_sources').fetchone()[0]==1
 with pipeline_lock(db):
  with pytest.raises(RuntimeError,match='Another pipeline'):execute_job(db,job,tmp_path/'logs')

def test_access_error_stops_without_rows(tmp_path,monkeypatch):
 from urllib.error import HTTPError
 from crypto_pipeline import recovery,lineage
 monkeypatch.setattr(lineage,'reconcile',lambda c,run_id=None:reconcile(c,1200000,run_id=run_id))
 db=tmp_path/'db'
 with sqlite3.connect(db) as c:
  apply_migrations(c)
  with c:reconcile(c,1200000,start_ms=300000)
 def denied(*args):raise HTTPError('https://fapi.binance.com',451,'restricted',{},None)
 monkeypatch.setattr(recovery.binance,'request_and_save',denied)
 job={'symbol':'BTCUSDT','dataset':'oi','first':300000,'last':600000,'expected':2}
 with pytest.raises(HTTPError):execute_job(db,job,tmp_path/'logs')
 with sqlite3.connect(db) as c:
  assert c.execute('SELECT status,mode FROM pipeline_runs').fetchone()==('failed','recovery')
  assert c.execute('SELECT count(*) FROM oi_observations').fetchone()[0]==0
