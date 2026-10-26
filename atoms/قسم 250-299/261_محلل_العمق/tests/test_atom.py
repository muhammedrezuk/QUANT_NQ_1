import asyncio
import importlib.util
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(root))
spec = importlib.util.spec_from_file_location(
    "_t261", Path(__file__).resolve().parents[1] / "atom.py")
m = importlib.util.module_from_spec(spec)
sys.modules["_t261"] = m
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
    await a.initialize(m.AtomContext(261, cfg or {"weight": 20.0, "required_levels": 3.0},
                                     L(), b.publish, b.subscribe))
    await a.start()
    return a, b


def _depth(imbalance=0.6, levels=5, symbol="NQ"):
    return {"symbol": symbol, "account_id": "A", "broker": "BR",
            "provider": "CTRADER", "levels": levels, "imbalance": imbalance,
            "bid_volume": 160.0, "ask_volume": 40.0, "mid": 64000.0,
            "spread": 0.5, "best_bid": 63999.75, "best_ask": 64000.25,
            "timestamp": 1000.0}


async def test_card_from_snapshot_honest():
    a, b = await _new()
    await a._on_depth(_depth(imbalance=0.6, levels=5))
    out = [p for n, p in b.e if n == m.EVENT_OUT]
    assert out, "لم تُنشر البطاقة"
    c = out[-1]
    # ٢٠٢٦-١٠-٠٧ (عقد الحقائق، ختم المالك «NQ»): لا جهة ولا قوّة ولا ثقة ولا جاهزيّة؛ الحقيقة اختلال الدفتر وأحجامه كما في اللقطة.
    for judged in _JUDGED:
        assert judged not in c, f"حقل حكمٍ ظهر: {judged}"
    md = c["metadata"]
    assert md["method"] == "book_imbalance"
    assert md["imbalance_raw"] == 0.6, md["imbalance_raw"]
    assert md["levels"] == 5 and md["bid_volume"] == 160.0 and md["ask_volume"] == 40.0
    assert md["bid_volume"] > md["ask_volume"]
    assert md["best_bid"] == 63999.75 and md["best_ask"] == 64000.25 and md["spread"] == 0.5
    assert c["status"] == "ok" and c["contract"] == "facts.v1"
    assert c["section_id"] == "250" and c["atom_id"] == "261"
    print("OK — بطاقة من لقطة العمق: اختلال 0.6 وأحجام 160/40، كل رقم من اللقطة نفسها بلا حكم")


async def test_sell_side_and_neutral():
    a, b = await _new()
    await a._on_depth(_depth(imbalance=-0.45, levels=4))
    c = [p for n, p in b.e if n == m.EVENT_OUT][-1]
    # ٢٠٢٦-١٠-٠٧ (عقد الحقائق، ختم المالك «NQ»): «بيع» و«محايد» حكمان نُزعا؛ الحقيقة قيمة الاختلال الخام بإشارتها.
    for judged in ("signal", "direction"):
        assert judged not in c, f"حقل حكمٍ ظهر: {judged}"
    assert c["metadata"]["imbalance_raw"] == -0.45, c["metadata"]["imbalance_raw"]
    await a._on_depth(_depth(imbalance=0.0, levels=4))
    c2 = [p for n, p in b.e if n == m.EVENT_OUT][-1]
    for judged in ("signal", "direction"):
        assert judged not in c2, f"حقل حكمٍ ظهر: {judged}"
    assert c2["metadata"]["imbalance_raw"] == 0.0, c2["metadata"]["imbalance_raw"]
    print("OK — اختلال -0.45 واختلال 0 منشوران كما هما، بلا كلمة جهة")


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


async def test_health_and_rejects():
    a, b = await _new()
    h0 = await a.health_check()
    assert h0.state.value == "DEGRADED" or "NO_DEPTH" in h0.message
    await a._on_depth({"symbol": "", "levels": 0})
    h = await a.health_check()
    assert h.details["rejected"] == 1 and h.details["received"] == 1
    print("OK — الصحة: بلا لقطات DEGRADED، والمرفوض معدود")


async def main():
    await test_card_from_snapshot_honest()
    await test_sell_side_and_neutral()
    await test_not_ready_below_required_levels()
    await test_health_and_rejects()
    print("261 depth analyzer tests passed")


if __name__ == "__main__":
    asyncio.run(main())
