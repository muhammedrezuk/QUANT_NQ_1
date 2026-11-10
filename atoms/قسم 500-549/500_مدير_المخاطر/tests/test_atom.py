import asyncio,importlib.util,sys,time
from pathlib import Path
root=Path(__file__).resolve().parents[4];folder=Path(__file__).resolve().parents[1];sys.path.insert(0,str(root));spec=importlib.util.spec_from_file_location('_t500',folder/'atom.py');m=importlib.util.module_from_spec(spec);sys.modules['_t500']=m;spec.loader.exec_module(m)
class L:
 def __getattr__(self,n):return lambda *a,**k:None
class B:
 def __init__(self):self.e=[];self.subs={}
 # الوهمي القديم كان `subscribe(*a):pass` فيبتلع المشترِك، فاضطرّ الاختبار
 # لبناء الـhandler بيده — وهناك اختبأت علّة ٤٫٩ يوم.  هنا يُحفظ ويُستدعى.
 def subscribe(self,event,handler):self.subs.setdefault(event,[]).append(handler)
 async def publish(self,n,p):self.e.append((n,p))
async def _wired():
 b=B();a=m.Atom();await a.initialize(m.AtomContext(500,{},L(),b.publish,b.subscribe));await a.start();return b,a
def _out(b):return [p for n,p in b.e if n==m.EVENT_OUT][-1]

def test_aggregates_from_the_registered_subscriber():
 async def run():
  b,a=await _wired()
  for h in b.subs[m.EVENT_RISK]:await h({'account_id':'A','status':'READY'})
  out=_out(b);assert out['authority']=='516' and out['accounts']['A']['risk']['status']=='READY';assert not hasattr(a,'_kill')
 asyncio.run(run())

def test_live_event_after_restore_overwrites_the_restored_snapshot():
 """المسار الذي كان أعمى: تسجيل ثمّ استعادة ثمّ حمولة حيّة.

 مقيس ٢٠٢٦-٠٩-٠٩: ٥٠٠ كان يُخرج `open_trade_count=0` و`equity=10494.87`
 بطابع عمره ٤٫٩ يوم، بينما ٥١٦/٥٠٨ يبثّان 1 و9674.54 في اللحظة نفسها.
 """
 async def run():
  b,a=await _wired()
  await a.restore({'risk':{'A':{'account_id':'A','status':'READY','open_trade_count':0,'timestamp':1788557666}},
                   'exposure':{'A':{'account_id':'A','equity':10494.87}},'profit':{},'session':{}})
  for h in b.subs[m.EVENT_RISK]:await h({'account_id':'A','status':'READY','open_trade_count':1,'timestamp':1788979651})
  for h in b.subs[m.EVENT_EXPOSURE]:await h({'account_id':'A','equity':9674.54})
  row=_out(b)['accounts']['A']
  assert row['risk']['open_trade_count']==1,'الحمولة الحيّة لم تدهس المستعادة — الوصلة مقطوعة'
  assert row['risk']['timestamp']==1788979651
  assert row['exposure']['equity']==9674.54
  assert a._risk['A']['open_trade_count']==1
 asyncio.run(run())

def test_restore_keeps_bucket_identity():
 async def run():
  b,a=await _wired();before=[id(getattr(a,'_'+n)) for n in m.BUCKETS]
  await a.restore({'risk':{'A':{'account_id':'A'}},'exposure':{},'profit':{},'session':{}})
  assert [id(getattr(a,'_'+n)) for n in m.BUCKETS]==before,'الاستعادة استبدلت الأوعية فقطعت المشترِكين'
 asyncio.run(run())

def test_restored_state_is_not_green_until_a_live_event_arrives():
 async def run():
  b,a=await _wired()
  await a.restore({'risk':{'A':{'account_id':'A','status':'READY'}},'exposure':{},'profit':{},'session':{}})
  h=await a.health_check();assert h.state is m.HealthState.DEGRADED and h.message=='RISK_STATE_RESTORED_AWAITING_LIVE_516'
  for cb in b.subs[m.EVENT_RISK]:await cb({'account_id':'A','status':'READY'})
  h=await a.health_check();assert h.state is m.HealthState.HEALTHY and 'aggregating_516_accounts=1' in h.message
 asyncio.run(run())

def test_silence_past_the_threshold_reads_stale():
 async def run():
  b,a=await _wired()
  for cb in b.subs[m.EVENT_RISK]:await cb({'account_id':'A','status':'READY'})
  a._last_seen_mono=time.monotonic()-(m.STALE_AFTER_S+1.0)
  h=await a.health_check();assert h.state is m.HealthState.DEGRADED and h.message.startswith('RISK_STATE_STALE')
 asyncio.run(run())

def test_snapshot_round_trip():
 async def run():
  b,a=await _wired()
  for cb in b.subs[m.EVENT_RISK]:await cb({'account_id':'A','status':'READY'})
  snap=await a.snapshot();assert snap['version']==m.ATOM_VERSION
  c=m.Atom();await c.restore(snap);assert 'A' in c._risk
 asyncio.run(run())

if __name__=='__main__':
 for name,fn in sorted(globals().items()):
  if name.startswith('test_'):fn()
 print('500 read-only 516 aggregation tests passed')