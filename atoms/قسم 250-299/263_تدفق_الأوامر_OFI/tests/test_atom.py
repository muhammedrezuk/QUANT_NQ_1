import asyncio
import importlib.util
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(root))
spec = importlib.util.spec_from_file_location(
    "_t263", Path(__file__).resolve().parents[1] / "atom.py")
m = importlib.util.module_from_spec(spec)
sys.modules["_t263"] = m
spec.loader.exec_module(m)


class L:
    def __getattr__(self, n): return lambda *a, **k: None


class B:
    def __init__(self): self.e = []
    def subscribe(self, *a): pass
    async def publish(self, n, p): self.e.append((n, p))


# ٢٠٢٦-١٠-٠٧ (عقد الحقائق، ختم المالك «NQ»): حقول الحكم التي كانت البطاقة تنشرها ولا تخرج بعد اليوم.
_JUDGED = ("signal", "direction", "strength", "confidence", "current_depth", "required_depth",
           "weight", "weight_applied", "ready", "analysis_state", "state", "unified")


async def _new(cfg=None):
    b = B(); a = m.Atom()
    await a.initialize(m.AtomContext(263, cfg or {"weight": 20.0, "required_levels": 3.0},
                                     L(), b.publish, b.subscribe))
    await a.start()
    return a, b


def _depth(bp, bq, ap, aq, levels=5, symbol="NQ"):
    bids = [[bp, bq]] + [[round(bp - 0.05 * i, 2), 10.0] for i in range(1, 5)]
    asks = [[ap, aq]] + [[round(ap + 0.05 * i, 2), 10.0] for i in range(1, 5)]
    return {"symbol": symbol, "account_id": "A", "broker": "BR", "provider": "CTRADER",
            "bids": bids, "asks": asks, "levels": levels, "timestamp": 1000.0}


def _last(b):
    return [p for n, p in b.e if n == m.EVENT_OUT][-1]


async def test_first_snapshot_is_honest_warming():
    a, b = await _new()
    await a._on_depth(_depth(100.00, 40.0, 100.10, 40.0))     # لا سابق
    c = _last(b)
    # ٢٠٢٦-١٠-٠٧ (عقد الحقائق، ختم المالك «NQ»): لا حالة ولا «مجهول» موحّد؛ الحقيقة الإحماء وسببه وغياب رقم OFI المختلق.
    assert c["status"] == "insufficient_data", c["status"]
    for judged in _JUDGED:
        assert judged not in c, f"حقل حكمٍ ظهر: {judged}"
    assert c["metadata"]["reason"] == "awaiting_prior_snapshot", c["metadata"]
    for invented in ("ofi", "e_bid", "e_ask"):
        assert invented not in c["metadata"], f"رقم مختلق قبل لقطةٍ ثانية: {invented}"
    assert c["contract"] == "facts.v1"
    assert c["section_id"] == "250" and c["atom_id"] == "263"
    print("OK — أوّل لقطة: إحماء صادق بسببه، بلا OFI مختلق ولا حكم")


async def test_bid_growth_positive_ofi():
    a, b = await _new()
    await a._on_depth(_depth(100.00, 40.0, 100.10, 40.0))     # سابق
    await a._on_depth(_depth(100.00, 100.0, 100.10, 40.0))    # طابور الطلب نما 60
    c = _last(b)
    assert c["metadata"]["ofi"] == 60.0, c["metadata"]["ofi"]  # e_bid=60, e_ask=0
    # ٢٠٢٦-١٠-٠٧ (عقد الحقائق، ختم المالك «NQ»): «شراء» والجاهزيّة حكمان نُزعا؛ الحقيقة OFI وطرفاه.
    assert c["metadata"]["e_bid"] == 60.0 and c["metadata"]["e_ask"] == 0.0, c["metadata"]
    assert c["status"] == "ok"
    for judged in _JUDGED:
        assert judged not in c, f"حقل حكمٍ ظهر: {judged}"
    print("OK — نموّ طابور الطلب ⇒ OFI=+60 (لقطتان، بلا صفقة ولا حكم)")


async def test_both_sides_drop_negative_ofi():
    a, b = await _new()
    await a._on_depth(_depth(100.00, 40.0, 100.10, 40.0))     # سابق
    await a._on_depth(_depth(100.00, 100.0, 100.10, 40.0))    # سابق ثانٍ (100,100)/(100.10,40)
    await a._on_depth(_depth(99.90, 30.0, 100.00, 50.0))      # الطلب هبط والعرض هبط
    c = _last(b)
    # e_bid = -100 (السعر هبط ⇒ يُزال الحجم السابق) · e_ask = +50 (العرض هبط ⇒ +حجمه)
    assert c["metadata"]["ofi"] == -150.0, c["metadata"]["ofi"]
    # ٢٠٢٦-١٠-٠٧ (عقد الحقائق، ختم المالك «NQ»): «بيع» حكمٌ نُزع؛ الحقيقة OFI وطرفاه.
    assert c["metadata"]["e_bid"] == -100.0 and c["metadata"]["e_ask"] == 50.0, c["metadata"]
    for judged in _JUDGED:
        assert judged not in c, f"حقل حكمٍ ظهر: {judged}"
    print("OK — هبوط الجهتين ⇒ OFI=-150 (بلا حكم)")


async def test_reject_crossed():
    a, b = await _new()
    await a._on_depth({"symbol": "NQ", "bids": [[100.5, 10.0]], "asks": [[100.0, 10.0]], "levels": 1})
    assert not [p for n, p in b.e if n == m.EVENT_OUT], "متقاطع لا يُنشر"
    h = await a.health_check()
    assert h.details["rejected"] == 1
    print("OK — الدفتر المتقاطع مرفوض")


async def main():
    await test_first_snapshot_is_honest_warming()
    await test_bid_growth_positive_ofi()
    await test_both_sides_drop_negative_ofi()
    await test_reject_crossed()
    print("263 OFI tests passed")


if __name__ == "__main__":
    asyncio.run(main())
