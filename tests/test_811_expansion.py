# -*- coding: utf-8 -*-
"""توسيع 811 (كلمة المالك «811» — بند v1.1 المختوم رقم 2).

العقد: يرى حقول المحورين والهدف والدلتا والميزانيات — قياسًا فقط، صفر قرار.
كل صف يحمل المفاتيح الحية (provenance) ولقطة هدف 581 وإيقاع السوق وقاعدة الصمت.
العزل: بدائل دوال المفاتيح — لا قراءة على السجل الحي.
"""
import asyncio
import importlib.util
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
from build_registry.paths import RegistryAtomRoot
ATOM_ROOT = RegistryAtomRoot(root)
folder = ATOM_ROOT / "811_قياس_سلوك_القرار"
sys.path.insert(0, str(root))
spec = importlib.util.spec_from_file_location("_atom811", folder / "atom.py")
mod = importlib.util.module_from_spec(spec)
sys.modules["_atom811"] = mod
spec.loader.exec_module(mod)


class L:
    def debug(self, *a, **k): pass
    def info(self, *a, **k): pass
    def warning(self, *a, **k): pass
    def error(self, *a, **k): pass
    def critical(self, *a, **k): pass


class B:
    def __init__(self):
        self.e = []
        self.subs = {}

    def subscribe(self, n, h): self.subs[n] = h

    async def publish(self, n, p): self.e.append((n, p))

    def c(self):
        return mod.AtomContext(811, {}, L(), self.publish, self.subscribe)


def scored(direction, stamp, **over):
    row = {"account_id": "A", "broker": "X", "symbol": "GOLD",
           "cycle_id": "GOLD|t|%s" % stamp, "direction": direction,
           "complete": True, "source_timestamp": stamp,
           "direction_value": over.get("dv", 60.0 if direction == "buy" else -60.0 if direction == "sell" else 0.0),
           "strength_value": over.get("sv", 40.0), "confidence_value": over.get("cv", 55.0),
           "net": over.get("net", 10.0), "participation": over.get("p", 0.5)}
    return row


async def main():
    b = B()
    a = mod.Atom()
    await a.initialize(b.c())
    await a.start()
    # عزل عيار المخاطرة عن السجل الحي — قيمة معلومة للإثبات.
    # ٢٠٢٦-١٠-٠٩ (ختم المالك «NQ» — إلغاء مفاتيح السرعة إلى الأرشيف): المفاتيح الأربعة خرجت من 811.
    mod.effective_value = lambda name, fallback: 100.0
    assert not any(hasattr(mod, name) for name in
                   ("speed_value", "horizon_value", "limits_value", "master_offset"))

    # ٢٠٢٦-١٠-٠٧ (ختم المالك «NQ»): 811 لم تعد تشترك في decision.scored.state ولا perpetual.target.state —
    # ناشراهما 453/581 أُرشفا مع فكّ الأقسام عن القرار؛ والمعالجان باقيان فيُستدعيان مباشرةً.
    assert mod.EVENT_TARGET not in b.subs and mod.EVENT_IN not in b.subs

    # لقطة هدف 581 تصل أولًا وتلتصق بكل صف تالٍ لنفس (الحساب، الرمز).
    await a._on_target({"account_id": "A", "symbol": "GOLD",
                        "risk_dial": 100.0, "base_target": 5.0,
                        "target_gross": 5.0, "target_net": 4.0,
                        "remaining_RB": 86.0, "dial_add_budget": 86.0,
                        "remaining_add_budget": 86.0, "action": "ADD"})
    await a._on_scored(scored("buy", 1000.0))
    await a._on_scored(scored("buy", 1002.5))
    await a._on_scored(scored("sell", 1004.0))

    rows = [p for n, p in b.e if n == mod.EVENT_OUT]
    assert len(rows) == 3
    last = rows[-1]
    # عيار المخاطرة الحيّ على كل صف — والمفاتيح الأربعة المؤرشفة غائبة.
    assert last["keys"] == {"risk_dial": 100.0}
    # لقطة الهدف والميزانيات ملتصقة.
    assert last["target"]["remaining_RB"] == 86.0
    assert last["target"]["action"] == "ADD"
    # انعكاس مباشر مصنف (BUY→SELL بلا حياد).
    assert last["reversal_kind"] == mod.REVERSAL_DIRECT
    # إيقاع السوق من الأختام لا من ساعة الجهاز: فجوتان 2.5 و1.5.
    cadence = last["cadence_gap_s"]
    assert cadence["count"] == 2 and cadence["max"] == 2.5
    # قاعدة الصمت: يوجد إشارات ⇒ ليس صامتًا.
    assert last["all_neutral"] is False

    # سيناريو الصمت: نطاق آخر كله حياد ⇒ العلم يرتفع ولا يُخفى.
    for i in range(3):
        await a._on_scored({**scored("neutral", 2000.0 + i),
                            "symbol": "USTEC", "dv": 0.0, "net": 0.0})
    silent = [p for n, p in b.e if n == mod.EVENT_OUT and p["symbol"] == "USTEC"][-1]
    assert silent["all_neutral"] is True

    # البقاء: لقطة/استعادة تحفظ الهدف والفجوات.
    snap = await a.snapshot()
    a2 = mod.Atom()
    b2 = B()
    await a2.initialize(b2.c())
    await a2.start()
    await a2.restore(snap)
    assert a2._targets[("A", "GOLD")]["remaining_RB"] == 86.0
    assert list(a2._books[("A", "X", "GOLD")]["gaps"]) == [2.5, 1.5]

    print("test_811_expansion: OK")


def test_811_expansion():
    asyncio.run(main())


if __name__ == "__main__":
    asyncio.run(main())
