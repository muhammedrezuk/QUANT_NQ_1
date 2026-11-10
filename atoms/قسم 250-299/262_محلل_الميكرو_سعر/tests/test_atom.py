import asyncio
import importlib.util
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(root))
spec = importlib.util.spec_from_file_location(
    "_t262", Path(__file__).resolve().parents[1] / "atom.py")
m = importlib.util.module_from_spec(spec)
sys.modules["_t262"] = m
spec.loader.exec_module(m)


class L:
    def __getattr__(self, n): return lambda *a, **k: None


class B:
    def __init__(self): self.e = []
    def subscribe(self, *a): pass
    async def publish(self, n, p): self.e.append((n, p))


# ٢٠٢٦-١٠-٠٧ (عقد الحقائق، ختم المالك «NQ»): حقول الحكم التي كانت البطاقة تنشرها ولا تخرج بعد اليوم.
_JUDGED = ("signal", "direction", "strength", "confidence", "current_depth", "required_depth",
           "weight", "weight_applied", "ready", "analysis_state", "state")


async def _new(cfg=None):
    b = B(); a = m.Atom()
    await a.initialize(m.AtomContext(262, cfg or {"weight": 20.0, "required_levels": 3.0},
                                     L(), b.publish, b.subscribe))
    await a.start()
    return a, b


def _depth(qb=160.0, qa=40.0, levels=5, symbol="NQ"):
    # أفضل مستوى يحمل الحجمين المختبَرين، والبقيّة حشوٌ صحيح الترتيب.
    bids = [[63999.75, qb], [63999.50, 20.0], [63999.25, 15.0],
            [63999.00, 10.0], [63998.75, 5.0]]
    asks = [[64000.25, qa], [64000.50, 20.0], [64000.75, 15.0],
            [64001.00, 10.0], [64001.25, 5.0]]
    return {"symbol": symbol, "account_id": "A", "broker": "BR", "provider": "CTRADER",
            "bids": bids, "asks": asks, "levels": levels, "timestamp": 1000.0}


async def test_buy_pressure_micro_toward_ask():
    a, b = await _new()
    await a._on_depth(_depth(qb=160.0, qa=40.0))     # طلبٌ ثقيل ⇒ العادل نحو العرض
    out = [p for n, p in b.e if n == m.EVENT_OUT]
    assert out, "لم تُنشر البطاقة"
    c = out[-1]
    # micro = (63999.75·40 + 64000.25·160)/200 = 64000.15 ⇒ موضعه +60% من نصف السبريد
    assert c["metadata"]["microprice"] == 64000.15, c["metadata"]["microprice"]
    # ٢٠٢٦-١٠-٠٧ (عقد الحقائق، ختم المالك «NQ»): لا جهة ولا قوّة ولا ثقة ولا جاهزيّة؛ الحقيقة ميل العادل عن المنتصف (+0.15) وحجما أفضل مستوى.
    for judged in _JUDGED:
        assert judged not in c, f"حقل حكمٍ ظهر: {judged}"
    md = c["metadata"]
    assert md["mid"] == 64000.0 and md["tilt"] == 0.15, (md["mid"], md["tilt"])
    assert md["microprice"] > md["mid"] and md["tilt_pips"] > 0
    assert md["best_bid_size"] == 160.0 and md["best_ask_size"] == 40.0
    assert md["method"] == "microprice_stoikov"
    assert c["status"] == "ok" and c["contract"] == "facts.v1"
    assert c["section_id"] == "250" and c["atom_id"] == "262"
    print("OK — طلبٌ ثقيل يرفع العادل نحو العرض: tilt=+0.15 من الدفتر وحده، بلا حكم")


async def test_sell_pressure_and_neutral():
    a, b = await _new()
    await a._on_depth(_depth(qb=40.0, qa=160.0))     # عرضٌ ثقيل ⇒ العادل نحو الطلب
    c = [p for n, p in b.e if n == m.EVENT_OUT][-1]
    # ٢٠٢٦-١٠-٠٧ (عقد الحقائق، ختم المالك «NQ»): «بيع» و«محايد» حكمان نُزعا؛ الحقيقة ميل العادل عن المنتصف بإشارته.
    for judged in ("signal", "direction"):
        assert judged not in c, f"حقل حكمٍ ظهر: {judged}"
    assert c["metadata"]["tilt"] == -0.15, c["metadata"]["tilt"]
    assert c["metadata"]["microprice"] < c["metadata"]["mid"]
    await a._on_depth(_depth(qb=100.0, qa=100.0))    # تماثل ⇒ العادل = المنتصف
    c2 = [p for n, p in b.e if n == m.EVENT_OUT][-1]
    for judged in ("signal", "direction"):
        assert judged not in c2, f"حقل حكمٍ ظهر: {judged}"
    assert c2["metadata"]["tilt"] == 0.0, c2["metadata"]["tilt"]
    assert c2["metadata"]["microprice"] == c2["metadata"]["mid"]
    print("OK — عرضٌ ثقيل tilt=-0.15، وتماثل tilt=0 (العادل=المنتصف)، بلا كلمة جهة")


async def test_not_ready_below_required_levels():
    a, b = await _new({"weight": 20.0, "required_levels": 8.0})
    await a._on_depth(_depth(levels=3))
    c = [p for n, p in b.e if n == m.EVENT_OUT][-1]
    # ٢٠٢٦-١٠-٠٧ (عقد الحقائق، ختم المالك «NQ»): لا جاهزيّة ولا وزن؛ الحقيقة عدد المستويات الفعليّ (3) والمطلوب (8) في الصحّة.
    for judged in _JUDGED:
        assert judged not in c, f"حقل حكمٍ ظهر: {judged}"
    assert c["status"] == "ok" and c["metadata"]["levels"] == 3, c
    h = await a.health_check()
    assert h.details["required_levels"] == 8.0, h.details
    assert c["metadata"]["levels"] < h.details["required_levels"]
    print("OK — أقل من المستويات المطلوبة: levels=3 من 8 منشور حقيقةً، بلا جاهزيّة ولا وزن")


async def test_reject_crossed_and_empty():
    a, b = await _new()
    await a._on_depth({"symbol": "NQ", "account_id": "A", "broker": "BR",
                       "bids": [[64001.0, 10.0]], "asks": [[64000.0, 10.0]], "levels": 1})
    await a._on_depth({"symbol": "NQ", "bids": [], "asks": [], "levels": 0})
    out = [p for n, p in b.e if n == m.EVENT_OUT]
    assert not out, "الدفتر المتقاطع/الفارغ لا يُنشر"
    h = await a.health_check()
    assert h.details["rejected"] == 2 and h.details["received"] == 2
    print("OK — الدفتر المتقاطع والفارغ مرفوضان معدودان، بلا نشر مخترع")


async def main():
    await test_buy_pressure_micro_toward_ask()
    await test_sell_pressure_and_neutral()
    await test_not_ready_below_required_levels()
    await test_reject_crossed_and_empty()
    print("262 microprice analyzer tests passed")


if __name__ == "__main__":
    asyncio.run(main())
