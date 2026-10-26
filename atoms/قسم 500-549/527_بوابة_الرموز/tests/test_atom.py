import pytest
import asyncio,importlib.util,sys
from pathlib import Path
root=Path(__file__).resolve().parents[4];folder=Path(__file__).resolve().parents[1];sys.path.insert(0,str(root));s=importlib.util.spec_from_file_location('a586',folder/'atom.py');m=importlib.util.module_from_spec(s);sys.modules['a586']=m;s.loader.exec_module(m)
class L:
 def __getattr__(self,n):return lambda *a,**k:None
class B:
 def __init__(self):self.e=[]
 def subscribe(self,*a):pass
 async def publish(self,n,p):self.e.append((n,p))
async def main():
 b=B();a=m.Atom();await a.initialize(m.AtomContext(586,{},L(),b.publish,b.subscribe));await a.start();await a._on_order({'request_id':'r','account_id':'A','symbol':'BTCUSD','side':'BUY'});await a._on_result({'request_id':'r','account_id':'A','symbol':'BTCUSD','logical_symbol':'BTCUSD','status':'SYMBOL_UNRESOLVED','approved':False});assert [p for n,p in b.e if n==m.EVENT_REJECTED];b.e.clear();await a._on_order({'request_id':'r1','account_id':'A','symbol':'BTCUSD','side':'BUY'});b.e.clear();await a._on_order({'request_id':'r2','account_id':'A','symbol':'BTCUSD','side':'BUY'});rejs=[p for n,p in b.e if n==m.EVENT_REJECTED];assert rejs and rejs[-1]['reason']=='ENTRY_COOLDOWN';print('586 symbol gate + common cooldown tests passed')
if __name__=='__main__':asyncio.run(main())


@pytest.mark.asyncio
async def test_common_open_cooldown_is_atomic_and_survives_restore():
    b=B()
    a=m.Atom()
    await a.initialize(m.AtomContext(586,{},L(),b.publish,b.subscribe))
    await a.start()
    first = {
        "request_id":"from-581",
        "account_id":"A",
        "symbol":"BTCUSD",
        "side":"SELL",
        "action":"OPEN",
    }
    second = {
        "request_id":"from-555",
        "account_id":"A",
        "symbol":"BTCUSD",
        "side":"SELL",
        "action":"OPEN",
    }
    await asyncio.gather(a._on_order(first), a._on_order(second))
    requests = [p for n,p in b.e if n == m.EVENT_REQUEST]
    rejects = [p for n,p in b.e if n == m.EVENT_REJECTED]
    assert len(requests) == 1
    assert len(rejects) == 1 and rejects[0]["reason"] == "ENTRY_COOLDOWN"

    state = await a.snapshot()
    b2=B()
    restored=m.Atom()
    await restored.initialize(m.AtomContext(586,{},L(),b2.publish,b2.subscribe))
    await restored.restore(state)
    await restored.start()
    await restored._on_order({
        "request_id":"after-reload",
        "account_id":"A",
        "symbol":"BTCUSD",
        "side":"SELL",
        "action":"OPEN",
    })
    rejects2 = [p for n,p in b2.e if n == m.EVENT_REJECTED]
    assert rejects2 and rejects2[-1]["reason"] == "ENTRY_COOLDOWN"
