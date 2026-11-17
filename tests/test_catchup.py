import sqlite3
from urllib.error import HTTPError,URLError
import pytest
from crypto_pipeline import catchup,binance
from crypto_pipeline.storage.migrations import apply_migrations
from crypto_pipeline.gaps import reconcile
from crypto_pipeline.locking import pipeline_lock
from crypto_pipeline.catchup_schedule import launch_agent

@pytest.fixture
def database(tmp_path):
 path=tmp_path/'db'
 with sqlite3.connect(path) as c:
  apply_migrations(c)
  c.execute("INSERT INTO pipeline_runs VALUES ('online',100,NULL,'online',NULL,'succeeded',NULL)")
  c.execute('UPDATE pipeline_runs SET ended_ms=10000000')
  reconcile(c,10000000,start_ms=300000)
 return path

def test_eligibility_overlap_retention(database):
 reason,jobs,old,warning=catchup.inspect(database,10000000)
 assert reason is None and jobs[0]['dataset']=='oi'
 assert all(j['last']<10000000-catchup.OVERLAP_MS for j in jobs)
 assert catchup.inspect(database,12000001)[0]
 assert catchup.inspect(database,29*catchup.DAY)[3]>0
 assert catchup.inspect(database,31*catchup.DAY)[2]
 with sqlite3.connect(database) as c:
  c.execute("UPDATE pipeline_runs SET status='failed'")
 assert catchup.inspect(database,10000000)[0]

@pytest.mark.parametrize('code,expected',[(451,'access_restricted'),(403,'access_restricted'),(418,'access_restricted'),(429,'rate_limited'),(503,'provider_error')])
def test_http_stops(database,tmp_path,monkeypatch,code,expected):
 calls=[]
 def fail(*a):calls.append(a);raise HTTPError('https://fapi.binance.com',code,'denied',{},None)
 monkeypatch.setattr(catchup,'execute_job',fail)
 assert catchup.run(database,tmp_path/'logs',execute=True,clock=lambda:10000000)==1
 assert len(calls)==1
 assert expected in next((tmp_path/'logs').glob('*.jsonl')).read_text()

def test_budget_and_lock(database,tmp_path,monkeypatch):
 calls=[]
 monkeypatch.setattr(catchup,'execute_job',lambda *args:calls.append(args))
 monkeypatch.setattr(catchup.time,'sleep',lambda _:None)
 catchup.run(database,tmp_path/'logs',max_pages=2,execute=True,clock=lambda:10000000)
 assert len(calls)==2
 from crypto_pipeline.recovery import execute_job
 monkeypatch.setattr(catchup,'execute_job',execute_job)
 with pipeline_lock(database):
  assert catchup.run(database,tmp_path/'logs',execute=True,clock=lambda:10000000)==0
 with sqlite3.connect(database) as c:assert c.execute('select count(*) from raw_files').fetchone()[0]==0

def test_bounded_transport_retries(monkeypatch,tmp_path):
 calls=[];sleeps=[]
 def fail(*a,**kw):calls.append(1);raise URLError('offline')
 monkeypatch.setattr(binance,'urlopen',fail);monkeypatch.setattr(binance,'sleep',sleeps.append)
 with pytest.raises(URLError):binance.request_and_save('https://fapi.binance.com/test','test')
 assert len(calls)==3 and sleeps==[2,4]
 assert catchup.classify(URLError('offline'))=='network_failure'

@pytest.mark.parametrize('code',[451,429])
def test_no_http_retries(monkeypatch,code):
 calls=[]
 def fail(*a,**kw):calls.append(1);raise HTTPError('https://fapi.binance.com',code,'denied',{},None)
 monkeypatch.setattr(binance,'urlopen',fail)
 with pytest.raises(HTTPError):binance.request_and_save('https://fapi.binance.com/test','test')
 assert len(calls)==1

def test_scheduler_separate_and_not_immediate(tmp_path):
 spec=launch_agent(tmp_path)
 assert spec['Label']=='com.crypto-pipeline.catchup'
 assert spec['StartCalendarInterval']=={'Minute':3}
 assert spec['RunAtLoad'] is False
 assert 'crypto_pipeline.catchup' in spec['ProgramArguments']

def test_restriction_requires_newer_success(database):
 with sqlite3.connect(database) as c:
  c.execute("INSERT INTO pipeline_runs VALUES ('blocked',10000001,10000002,'recovery',NULL,'failed','HTTP Error 451: denied')")
 assert 'newer' in catchup.inspect(database,10000003)[0]

def test_no_gaps_repeated_execution_no_fetch(database,tmp_path,monkeypatch):
 with sqlite3.connect(database) as c:c.execute('DELETE FROM observation_gaps')
 def unexpected(*args):raise AssertionError('No request expected')
 monkeypatch.setattr(catchup,'execute_job',unexpected)
 for _ in range(2):assert catchup.run(database,tmp_path/'logs',execute=True,clock=lambda:10000000)==0
 with sqlite3.connect(database) as c:
  assert c.execute('pragma integrity_check').fetchone()[0]=='ok'
  assert not c.execute('pragma foreign_key_check').fetchall()

def test_missing_source_cannot_be_linked(database):
 with sqlite3.connect(database) as c:
  c.execute('PRAGMA foreign_keys=ON')
  with pytest.raises(sqlite3.IntegrityError):
   c.execute('UPDATE observation_gaps SET raw_file_id=999999')
  assert c.execute('SELECT COUNT(*) FROM observation_gaps WHERE raw_file_id IS NOT NULL').fetchone()[0]==0
