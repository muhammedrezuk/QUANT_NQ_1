import asyncio
import importlib.util
import sys
from pathlib import Path

root=Path(__file__).resolve().parents[4]; folder=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root)); spec=importlib.util.spec_from_file_location("_atom512_work",folder/"atom.py")
mod=importlib.util.module_from_spec(spec); sys.modules["_atom512_work"]=mod; spec.loader.exec_module(mod)
class Log:
    def debug(self,*a,**k): pass
    def info(self,*a,**k): pass
    def warning(self,*a,**k): pass
    def error(self,*a,**k): pass
    def critical(self,*a,**k): pass
class Bus:
    def __init__(self): self.events=[]; self.subs={}
    # الوهمي القديم كان يبتلع المشترِك؛ هنا يُحفظ فيُختبر المسار الحقيقي.
    def subscribe(self,event,handler): self.subs.setdefault(event,[]).append(handler)
    async def publish(self,n,p): self.events.append((n,p))
    def ctx(self): return mod.AtomContext(512,{"price_decimals":8},Log(),self.publish,self.subscribe)

READY_LEDGER={"account_id":"A","symbol":"NQ","R":50,"K":20,"cost":0,"v_net":1,"w":100,"vpu":20}
FLAT_LEDGER={"account_id":"A","symbol":"NQ","R":50,"K":20,"cost":0,"v_net":0,"w":0,"vpu":20}

async def _wired():
    b=Bus(); a=mod.Atom(); await a.initialize(b.ctx()); await a.start(); return b,a
def _last(b,name): return [p for n,p in b.events if n==name][-1]

def test_ready_stop_is_computed():
    async def run():
        b,a=await _wired()
        for h in b.subs[mod.EVENT_LEDGER]: await h(READY_LEDGER)
        p=_last(b,mod.EVENT_OUT)
        assert p["status"]=="READY" and p["stop_price"]==96.5, p
    asyncio.run(run())

def test_flat_position_reads_hedged():
    async def run():
        b,a=await _wired()
        for h in b.subs[mod.EVENT_LEDGER]: await h(FLAT_LEDGER)
        assert _last(b,mod.EVENT_OUT)["status"]=="FLAT" and "target_net" not in _last(b,mod.EVENT_OUT)  # 2026-10-23 law 13
    asyncio.run(run())

def test_legacy_payload_carries_the_stop_price_526_reads():
    """٥٢٦ يشترك في الحدث الموروث ويقرأ `stop_price` منه — فليبقَ محمولًا."""
    async def run():
        b,a=await _wired()
        for h in b.subs[mod.EVENT_LEDGER]: await h(READY_LEDGER)
        legacy=_last(b,mod.EVENT_LEGACY)
        assert legacy["stop_price"]==96.5, legacy
        assert legacy["signal"]=="structure_stop"
        assert legacy["metadata"]["buy_stop"]==96.5 and legacy["metadata"]["sell_stop"] is None
    asyncio.run(run())

def test_state_survives_a_snapshot_round_trip():
    """كانت ٥١٢ بلا `snapshot()` فلا لقطة لها، وخريطة الأوقاف تضيع كل إقلاع."""
    async def run():
        b,a=await _wired()
        for h in b.subs[mod.EVENT_LEDGER]: await h(READY_LEDGER)
        snap=await a.snapshot()
        assert snap["version"]==mod.ATOM_VERSION and snap["published"]==1, snap
        c_bus,c=await _wired(); await c.restore(snap)
        assert c._seen==a._seen and c._published==a._published
        key=list(a._last)[0]
        assert c._last[key]["stop_price"]==96.5
    asyncio.run(run())

def test_restore_keeps_the_map_identity():
    async def run():
        b,a=await _wired(); before=id(a._last)
        await a.restore({"version":mod.ATOM_VERSION,"seen":1,"published":1,
                         "last":{"A\x1fNQ":{"status":"READY","stop_price":96.5}}})
        assert id(a._last)==before, "الاستعادة استبدلت الخريطة — درس ٥٠٠"
        assert a._last["A\x1fNQ"]["stop_price"]==96.5
    asyncio.run(run())

def test_health_reports_the_number_not_a_claim():
    """«stop_targets_ready» كانت تخرج بمجرّد `_seen>0` بلا نظرٍ إلى وقفٍ واحد."""
    async def run():
        b,a=await _wired()
        for h in b.subs[mod.EVENT_LEDGER]: await h(FLAT_LEDGER)
        h1=await a.health_check()
        assert h1.state is mod.HealthState.HEALTHY
        assert "ready=0" in h1.message, h1.message
        for h in b.subs[mod.EVENT_LEDGER]: await h(READY_LEDGER)
        h2=await a.health_check()
        assert "ready=1" in h2.message, h2.message
    asyncio.run(run())

if __name__=="__main__":
    for name,fn in sorted(globals().items()):
        if name.startswith("test_"): fn()
    print("512 P0 tests passed")