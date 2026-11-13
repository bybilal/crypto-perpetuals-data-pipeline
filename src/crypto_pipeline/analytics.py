"""Read-only, exact-boundary dashboard queries and Decimal indicators."""
from contextlib import contextmanager
from decimal import Decimal, localcontext
import sqlite3
from .config import DB_PATH
STEP=300000

@contextmanager
def read_database(path=DB_PATH):
    c=sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True)
    c.row_factory=sqlite3.Row
    c.execute('PRAGMA query_only=ON');c.execute('BEGIN')
    try:yield c
    finally:c.close()

def observations(c,symbol,start,end):
    prices={r['bucket_end_ms']:dict(r) for r in c.execute('SELECT bucket_end_ms,close_price,quote_volume,raw_file_id FROM price_candles WHERE symbol=? AND bucket_end_ms BETWEEN ? AND ?',(symbol,start,end))}
    oi={r['bucket_end_ms']:dict(r) for r in c.execute('SELECT bucket_end_ms,oi_quantity,oi_notional_quote,raw_file_id FROM oi_observations WHERE symbol=? AND bucket_end_ms BETWEEN ? AND ?',(symbol,start,end))}
    return [{'timestamp':t,'price':prices.get(t,{}).get('close_price'),'volume':prices.get(t,{}).get('quote_volume'),'oi':oi.get(t,{}).get('oi_quantity'),'candle_source':prices.get(t,{}).get('raw_file_id'),'oi_source':oi.get(t,{}).get('raw_file_id')} for t in range(start,end+1,STEP)]

def classify(t,now,start,grace,present,recovered):
    if present:return 'Recovered' if recovered else 'Present'
    if start is None or t<start:return 'Outside scope'
    if t>now-grace:return 'Pending'
    return 'Missing'

def quality(c,symbol,dataset,start,end,now):
    table='oi_observations' if dataset=='oi' else 'price_candles'
    sources={r[0]:r[1] for r in c.execute(f'SELECT bucket_end_ms,raw_file_id FROM {table} WHERE symbol=? AND bucket_end_ms BETWEEN ? AND ?',(symbol,start,end))}
    recovered={r[0] for r in c.execute("SELECT bucket_end_ms FROM observation_gaps WHERE symbol=? AND dataset=? AND status='recovered' AND bucket_end_ms BETWEEN ? AND ?",(symbol,dataset,start,end))}
    window=c.execute("SELECT start_ms,reconciled_ms FROM monitoring_windows WHERE exchange='binance_usdm' AND symbol=? AND dataset=? AND interval='5m'",(symbol,dataset)).fetchone()
    return [{'timestamp':t,'state':classify(t,now,window[0] if window else None,600000 if dataset=='oi' else 60000,t in sources,t in recovered),'source_id':sources.get(t)} for t in range(start,end+1,STEP)]

def scanner(rows,horizon,baseline):
    """Z of latest horizon OI percentage change vs preceding baseline changes (sample SD)."""
    required=horizon+baseline+1
    if len(rows)<required:return None,'Insufficient history'
    rows=rows[-required:]
    if any(b['timestamp']-a['timestamp']!=STEP for a,b in zip(rows,rows[1:])):return None,'Noncontiguous history'
    if any(r['oi'] is None for r in rows) or rows[-1]['price'] is None or rows[-1-horizon]['price'] is None:return None,'Missing observation'
    with localcontext() as ctx:
        ctx.prec=50
        def change(a,b):
            a,b=Decimal(a),Decimal(b)
            if a<=0:raise ValueError('Nonpositive denominator')
            return (b/a-1)*100
        try:
            changes=[change(rows[i-horizon]['oi'],rows[i]['oi']) for i in range(horizon,len(rows))]
            price=change(rows[-1-horizon]['price'],rows[-1]['price'])
        except ValueError as e:return None,str(e)
        prior=changes[:-1];mean=sum(prior)/Decimal(len(prior))
        sd=(sum((v-mean)**2 for v in prior)/Decimal(len(prior)-1)).sqrt()
        if sd==0:return None,'Zero baseline variance'
        return {'price_change':float(price),'oi_change':float(changes[-1]),'z':float((changes[-1]-mean)/sd),'samples':len(prior)},None
