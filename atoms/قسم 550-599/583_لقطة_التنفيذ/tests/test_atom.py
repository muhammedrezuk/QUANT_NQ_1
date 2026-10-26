import asyncio,importlib.util,sys
from pathlib import Path
root=Path(__file__).resolve().parents[4];folder=Path(__file__).resolve().parents[1];sys.path.insert(0,str(root));s=importlib.util.spec_from_file_location('a583',folder/'atom.py');m=importlib.util.module_from_spec(s);sys.modules['a583']=m;s.loader.exec_module(m)
class L:
 def __getattr__(self,n):return lambda *a,**k:None
class B:
 def __init__(self):self.e=[]
 def subscribe(self,*a):pass
 async def publish(self,n,p):self.e.append((n,p))
async def main():
 b=B();a=m.Atom();await a.initialize(m.AtomContext(583,{},L(),b.publish,b.subscribe));await a.start();await a._on_account({'account_id':'A','broker':'BR'});await a._on_ledger({'ledgers':[{'account_id':'A','broker':'BR','symbol':'BTCUSD','R':100}]});await a._on_target({'account_id':'A','broker':'BR','symbol':'BTCUSD','target_net':1});p=[p for n,p in b.e if n==m.EVENT_OUT][-1];assert p['snapshot_id'] and p['snapshot']['ledger']['R']==100;print('583 execution snapshot tests passed')
if __name__=='__main__':asyncio.run(main())


# ٢٠٢٦-١٠-٠٧ (ختم «NQ»): ناشر perpetual.target.state (٥٨١) أُرشف — فلا اشتراك فيه، والباقي كما هو.
class _RecordingBus(B):
 def __init__(self):super().__init__();self.h={}
 def subscribe(self,name,handler,*a):self.h.setdefault(name,[]).append(handler)
async def test_snapshot_still_builds_when_target_is_called_directly():
 await main()
async def test_no_subscription_to_archived_target_state():
 b=_RecordingBus();a=m.Atom();await a.initialize(m.AtomContext(583,{},L(),b.publish,b.subscribe))
 assert 'perpetual.target.state' not in b.h
 for kept in ('SYS_SECOND','risk.asset_ledger.state','asset.portfolio.state','feed.mt5.tick','market.symbol_specs','dial.profile.state','platform.account.state'):assert kept in b.h,kept
