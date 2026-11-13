"""Local Streamlit entry point. Database access is exclusively read-only."""
from datetime import datetime,date,time,timezone,timedelta
from collections import Counter
import streamlit as st
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from crypto_pipeline.analytics import read_database,observations,quality,scanner,STEP
from crypto_pipeline.config import SYMBOLS

st.set_page_config(page_title='Perpetuals Observatory',page_icon='◈',layout='wide')
st.markdown('<style>.block-container{padding-top:2rem}h1{letter-spacing:-1px}div[data-testid="stMetric"] *{color:#e4eef8!important}div[data-testid="stMetric"]{color:#e4eef8;background:#152333;padding:16px;border-radius:12px}</style>',unsafe_allow_html=True)
st.title('Perpetuals Observatory')
st.caption('LOCAL RESEARCH WORKSPACE · Binance USDⓈ-M · All times UTC · Read-only SQLite')
now=int(datetime.now(timezone.utc).timestamp()*1000)
with read_database() as c:
    latest=c.execute('SELECT MAX(bucket_end_ms) FROM price_candles').fetchone()[0]
    scanner_end=min([c.execute('SELECT MAX(bucket_end_ms) FROM oi_observations WHERE symbol=?',(s,)).fetchone()[0] or 0 for s in SYMBOLS]+[latest or 0])
if latest is None:st.info('No candles available yet.');st.stop()
latest_dt=datetime.fromtimestamp(latest/1000,timezone.utc)
st.sidebar.header('Explore stored history')
day=st.sidebar.date_input('UTC date',value=latest_dt.date())
symbol=st.sidebar.selectbox('Contract',SYMBOLS)
st.sidebar.button('Refresh database')
st.sidebar.caption('No API requests or ingestion. Reload to see new captures.')
start=int(datetime.combine(day,time(),tzinfo=timezone.utc).timestamp()*1000)
end=start+86400000-STEP
col1,col2,col3=st.columns(3)
col1.metric('Latest candle boundary',latest_dt.strftime('%b %d · %H:%M UTC'))
col2.metric('Candle age',f'{max(0,(now-latest)//60000)} min')
col3.metric('Contracts',len(SYMBOLS))
if now-latest>900000:st.warning('Stored candles are stale by more than 15 minutes. Collection success is not a completeness guarantee.')
tabs=st.tabs(['▦ Data quality','◉ OI scanner','↗ Market timeline','⌕ Asset & source inspector'])
colors={'Present':'#55b58a','Recovered':'#82b7ef','Missing':'#ed7272','Pending':'#edc66a','Outside scope':'#344457'}
def utc(t):return datetime.fromtimestamp(t/1000,timezone.utc)
def layout(fig,height=440):
    fig.update_layout(height=height,template='plotly_dark',paper_bgcolor='#0e1722',plot_bgcolor='#0e1722',margin=dict(l=30,r=30,t=35,b=30),font=dict(color='#dbe5f0'))
    return fig
with tabs[0]:
    st.subheader('Every square is one five-minute period end')
    st.caption('Green present · Blue recovered · Red missing · Amber publication grace/future · Slate outside scope. Presence uses actual rows; recovered uses registry history.')
    for dataset in ('klines','oi'):
        with read_database() as c:cells=quality(c,symbol,dataset,start,end,now)
        fig=go.Figure()
        for state,color in colors.items():
            subset=[r for r in cells if r['state']==state]
            fig.add_trace(go.Scatter(x=[(r['timestamp']-start)//STEP%24 for r in subset],y=[11-(r['timestamp']-start)//STEP//24 for r in subset],mode='markers',name=state,marker=dict(symbol='square',size=6,color=color),text=[f"{utc(r['timestamp']).isoformat()}<br>{state}<br>raw_file_id: {r['source_id']}" for r in subset],hovertemplate='%{text}<extra></extra>'))
        fig.update_layout(legend=dict(orientation='h',y=-0.25))
        fig.update_yaxes(tickvals=list(range(12)),ticktext=[f'{22-2*i:02d}:00' for i in range(12)],title='UTC two-hour row')
        fig.update_xaxes(tickvals=[0,6,12,18,23],ticktext=['+00m','+30m','+60m','+90m','+115m'])
        st.markdown(f'**{symbol} / {dataset}** · '+ ' · '.join(f'{k}: {v}' for k,v in Counter(r['state'] for r in cells).items()))
        st.plotly_chart(layout(fig,380),width='stretch',theme=None,key=dataset)
with tabs[1]:
    st.subheader('Price movement × unusual OI change')
    a,b,d=st.columns(3)
    horizon=a.selectbox('Change horizon', [1,3,12,48],index=2,format_func=lambda x:f'{x*5} minutes')
    baseline=b.selectbox('Prior baseline changes',[12,48,144,288],index=1)
    chosen=d.time_input('Analysis boundary UTC',value=datetime.fromtimestamp(scanner_end/1000,timezone.utc).time().replace(second=0,microsecond=0),step=timedelta(minutes=5))
    target=int(datetime.combine(day,chosen,tzinfo=timezone.utc).timestamp()*1000)//STEP*STEP
    st.caption('Z = (latest horizon OI % change − mean of preceding N changes) / sample standard deviation. Baseline excludes current change; rolling horizons overlap. Z > 0 means above-baseline change, not necessarily rising OI. No inference of positions or liquidations.')
    fig=go.Figure();results=[]
    for ticker in SYMBOLS:
        with read_database() as c:rows=observations(c,ticker,target-(horizon+baseline)*STEP,target)
        result,error=scanner(rows,horizon,baseline)
        if error:st.info(f'{ticker}: {error}. Requires {horizon+baseline+1} consecutive OI levels plus endpoint prices.')
        else:
            results.append(dict(contract=ticker,**result))
            fig.add_trace(go.Scatter(x=[result['price_change']],y=[result['z']],mode='markers+text',text=[ticker],textposition='top center',name=ticker,marker=dict(size=18),customdata=[[result['oi_change'],baseline]],hovertemplate='Price %{x:.3f}%<br>OI Z %{y:.3f}<br>OI change %{customdata[0]:.3f}%<br>Baseline n=%{customdata[1]}<extra>%{fullData.name}</extra>'))
    fig.add_hline(y=0,line_dash='dot');fig.add_vline(x=0,line_dash='dot')
    for x,y,label in [(.02,.98,'Price ↓ / OI change above baseline'),(.98,.98,'Price ↑ / OI change above baseline'),(.02,.02,'Price ↓ / OI change below baseline'),(.98,.02,'Price ↑ / OI change below baseline')]:
        fig.add_annotation(x=x,y=y,xref='paper',yref='paper',text=label,showarrow=False,xanchor='left' if x<.5 else 'right',font=dict(size=10))
    fig.update_xaxes(title='Price change (%)',range=[-max(1,max([abs(r['price_change']) for r in results],default=0)*1.4),max(1,max([abs(r['price_change']) for r in results],default=0)*1.4)])
    fig.update_yaxes(title='OI change Z-score',range=[-max(3,max([abs(r['z']) for r in results],default=0)*1.4),max(3,max([abs(r['z']) for r in results],default=0)*1.4)])
    st.plotly_chart(layout(fig),width='stretch',theme=None);st.dataframe(results)
with tabs[2]:
    st.subheader(symbol+' / five-minute timeline')
    st.caption('Price: USDT per native base unit. OI: native BTC or 1000PEPE units, not verified individual PEPE tokens. Volume: traded USDT per candle. Missing slots break lines.')
    with read_database() as c:rows=observations(c,symbol,start,end)
    fig=make_subplots(rows=3,cols=1,shared_xaxes=True,subplot_titles=['Close price · USDT/native unit','Open interest · native units','Traded volume · USDT'])
    for i,field in enumerate(('price','oi','volume'),1):
        values=[float(r[field]) if r[field] is not None else None for r in rows]
        trace=go.Bar(x=[utc(r['timestamp']) for r in rows],y=values,name=field) if field=='volume' else go.Scatter(x=[utc(r['timestamp']) for r in rows],y=values,name=field,connectgaps=False)
        fig.add_trace(trace,row=i,col=1)
    st.plotly_chart(layout(fig,690),width='stretch',theme=None)
with tabs[3]:
    st.subheader('Identity, fundamentals & source evidence')
    with read_database() as c:
        contract=dict(c.execute('SELECT * FROM contracts WHERE symbol=?',(symbol,)).fetchone())
        st.json({k:v for k,v in contract.items() if k!='specification_json'})
        mapping=c.execute('SELECT * FROM asset_mappings WHERE native_asset_id=?',(contract['base_asset_id'],)).fetchone()
        st.write('Native identity mapping',dict(mapping) if mapping else 'Unmapped')
        if mapping and mapping['status']=='verified':
            fundamentals=[dict(r) for r in c.execute("SELECT m.*,s.retrieved_at_ms,s.source_key FROM market_snapshots m JOIN provider_assets p USING(provider,provider_coin_id) JOIN market_sources s ON s.id=m.source_id WHERE p.canonical_id=? ORDER BY s.retrieved_at_ms DESC LIMIT 5",(mapping['canonical_id'],))]
            st.write('Latest CoinGecko captures — USD valuations; supply in canonical coins. Source timestamps are Unix milliseconds.');st.dataframe(fundamentals)
        else:st.warning('Pending identity: no CoinGecko fundamentals join. Underlying multiplier remains unknown.')
        st.dataframe([dict(r) for r in c.execute('SELECT * FROM raw_files WHERE symbol=? ORDER BY retrieved_at_ms DESC LIMIT 10',(symbol,))])
        source=st.number_input('Inspect raw_file_id',min_value=1,value=1,step=1)
        record=c.execute('SELECT * FROM raw_files WHERE id=?',(source,)).fetchone()
        if record:
            st.json(dict(record))
            st.dataframe([dict(r) for r in c.execute('SELECT p.* FROM run_sources s JOIN pipeline_runs p USING(run_id) WHERE s.raw_file_id=?',(source,))])
        else:st.info('No such indexed source.')
    st.caption('Raw-file checksums are provenance identifiers; this view does not rehash files or equate collection success with completeness. Data provided by CoinGecko: https://www.coingecko.com')
