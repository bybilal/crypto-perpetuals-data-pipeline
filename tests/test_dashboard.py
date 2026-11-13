from decimal import Decimal
from pathlib import Path
import sqlite3
import pytest
from crypto_pipeline.analytics import classify,scanner,read_database,observations,quality
from crypto_pipeline.storage.migrations import apply_migrations

@pytest.mark.parametrize('t,now,start,present,recovered,expected',[(300000,900000,300000,True,False,'Present'),(300000,900000,300000,True,True,'Recovered'),(300000,900000,300000,False,True,'Missing'),(900000,900000,300000,False,False,'Pending'),(0,900000,300000,False,False,'Outside scope')])
def test_states(t,now,start,present,recovered,expected):assert classify(t,now,start,60000,present,recovered)==expected

def test_indicators():
 rows=[dict(timestamp=i*300000,oi=str(v),price='100' if i<4 else '110') for i,v in enumerate([100,101,103,106,110])]
 result,error=scanner(rows,1,3)
 assert error is None and result['price_change']==pytest.approx(10)
 changes=[(Decimal(b)/Decimal(a)-1)*100 for a,b in zip([100,101,103,106],[101,103,106,110])]
 mean=sum(changes[:3])/3;sd=(sum((x-mean)**2 for x in changes[:3])/2).sqrt()
 assert result['z']==pytest.approx(float((changes[-1]-mean)/sd))
 rows[2]['oi']=None
 assert scanner(rows,1,3)[0] is None

def test_read_only_and_missing_slots(tmp_path):
 path=tmp_path/'test.db'
 with sqlite3.connect(path) as c:apply_migrations(c)
 with read_database(path) as c:
  with pytest.raises(sqlite3.OperationalError):c.execute('DELETE FROM raw_files')
  rows=observations(c,'BTCUSDT',300000,900000)
  assert len(rows)==3 and all(r['price'] is None for r in rows)
  assert all(r['state']=='Outside scope' for r in quality(c,'BTCUSDT','oi',300000,900000,1200000))

def test_zero_variance_and_short_history():
 rows=[dict(timestamp=i*300000,oi='100',price='100') for i in range(5)]
 assert scanner(rows,1,3)[1]=='Zero baseline variance'
 assert scanner(rows[:2],1,3)[1]=='Insufficient history'
