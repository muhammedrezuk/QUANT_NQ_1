import asyncio
import os
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from pathlib import Path as _Path
sys.path.insert(0, str(_Path(__file__).resolve().parents[4]))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.contracts.atom import AtomContext, HealthState  # noqa: E402
import importlib.util as _ilu  # noqa: E402

_spec = _ilu.spec_from_file_location(
    "_atom251", _Path(__file__).resolve().parents[1] / "atom.py")
_mod = _ilu.module_from_spec(_spec)
sys.modules["_atom251"] = _mod
_spec.loader.exec_module(_mod)
Atom = _mod.Atom
EVENT_OUT = _mod.EVENT_OUT


class _NullLogger:
    def debug(self, *a): pass
    def info(self, *a): pass
    def warning(self, *a): pass
    def error(self, *a): pass
    def critical(self, *a): pass


class FakeEventBus:
    def __init__(self):
        self.published = []
        self._handlers = {}

    def subscribe(self, name, handler):
        self._handlers.setdefault(name, []).append(handler)

    async def publish(self, name, payload):
        self.published.append((name, payload))

    def make_context(self, config):
        return AtomContext(atom_id=251, config=config, logger=_NullLogger(),
                           publish=self.publish, subscribe=self.subscribe)


def _swing(signal, price=None, close=100.0, ts=0.0, score=0, symbol="NQ100", tf="60s"):
    meta = {"timeframe": tf, "close": close}
    if price is not None:
        meta["price"] = price
        meta["swing_time"] = ts
    return {"symbol": symbol, "id": "swing", "cycle_id": "%s|%s|%s" % (symbol, tf, ts),
            "status": "ok", "signal": signal, "score": score,
            "confidence": 1.0 if price is not None else 0.0,
            "quality": "good", "warnings": [], "metadata": meta}


async def _run(swings):
    bus = FakeEventBus()
    atom = Atom()
    await atom.initialize(bus.make_context({}))
    await atom.start()
    for s in swings:
        await atom._on_swing(s)
    pools = [p for n, p in bus.published if n == EVENT_OUT]
    return atom, bus, pools


async def test_swing_high_becomes_pool_high():
    print("\n--- test_swing_high_becomes_pool_high ---")
    _atom, _bus, pools = await _run([_swing("swing_high", 12, ts=2, score=67)])
    last = pools[-1]
    assert last["signal"] == "pool_high", last["signal"]
    assert last["metadata"]["side"] == "high"
    assert last["metadata"]["price"] == 12
    assert last["metadata"]["pool_time"] == 2
    # ٢٠٢٦-١٠-٠٧ (عقد الحقائق، ختم المالك «NQ»): البروز (score) والثقة حكمان نُزعا؛ تبقى البركة: جانبها وسعرها وزمنها.
    for judged in ("score", "confidence", "quality"):
        assert judged not in last, f"حقل حكمٍ ظهر: {judged}"
    print(f"OK — قمة → بركة: side=high price={last['metadata']['price']} "
          f"pool_time={last['metadata']['pool_time']} بلا ثقة")


async def test_swing_low_becomes_pool_low():
    print("\n--- test_swing_low_becomes_pool_low ---")
    _atom, _bus, pools = await _run([_swing("swing_low", 8, ts=2, score=55)])
    last = pools[-1]
    assert last["signal"] == "pool_low", last["signal"]
    assert last["metadata"]["side"] == "low"
    assert last["metadata"]["price"] == 8
    assert last["metadata"]["pool_time"] == 2
    # ٢٠٢٦-١٠-٠٧ (عقد الحقائق، ختم المالك «NQ»): البروز (score) والثقة حكمان نُزعا؛ تبقى البركة: جانبها وسعرها وزمنها.
    for judged in ("score", "confidence", "quality"):
        assert judged not in last, f"حقل حكمٍ ظهر: {judged}"
    print(f"OK — قاع → بركة: side=low price={last['metadata']['price']} "
          f"pool_time={last['metadata']['pool_time']} بلا ثقة")


async def test_confidence_scales_with_prominence():
    print("\n--- test_confidence_scales_with_prominence ---")
    # ٢٠٢٦-١٠-٠٧ (عقد الحقائق، ختم المالك «NQ»): الثقة المشتقّة من البروز نُزعت ولا حقيقة بديلة لها؛ يثبت الغياب وبقاء سعر البركة وجانبها.
    _atom, _bus, weak = await _run([_swing("swing_high", 12, ts=2, score=20)])
    _atom, _bus, strong = await _run([_swing("swing_high", 12, ts=2, score=90)])
    for card in (weak[-1], strong[-1]):
        for judged in ("score", "confidence"):
            assert judged not in card, f"حقل حكمٍ ظهر: {judged}"
        assert card["metadata"]["price"] == 12 and card["metadata"]["side"] == "high", card["metadata"]
    print("OK — بروز 20 وبروز 90: لا ثقة منشورة، والبركة نفسها (price=12 side=high)")


async def test_none_swing_no_pool():
    print("\n--- test_none_swing_no_pool ---")
    _atom, _bus, pools = await _run([_swing("none")])
    last = pools[-1]
    assert last["signal"] == "none"
    # ٢٠٢٦-١٠-٠٧ (عقد الحقائق، ختم المالك «NQ»): لا ثقة صفريّة بعد اليوم؛ «لا بركة» تُقرأ من غياب سعرها وجانبها.
    assert "confidence" not in last, last.get("confidence")
    assert last["metadata"]["price"] is None and last["metadata"]["side"] is None, last["metadata"]
    print("OK — لا سوينغ = لا بركة (بلا سعر ولا جانب)")


async def test_contract_shape_complete():
    print("\n--- test_contract_shape_complete ---")
    _atom, _bus, pools = await _run([_swing("swing_high", 12, ts=2, score=67)])
    last = pools[-1]
    # ٢٠٢٦-١٠-٠٧ (عقد الحقائق، ختم المالك «NQ»): الحقول المطلوبة صارت ختم الحقيقة، وحقول الحكم ممنوعة.
    for field in ("symbol", "id", "cycle_id", "status", "signal", "warnings", "metadata",
                  "as_of", "computed_on", "section_id", "atom_id", "contract"):
        assert field in last, f"حقل ناقص بالعقد: {field}"
    for judged in ("score", "confidence", "quality"):
        assert judged not in last, f"حقل حكمٍ ظهر: {judged}"
    for field in ("method", "timeframe", "side", "price", "pool_time", "close"):
        assert field in last["metadata"], f"حقل metadata ناقص: {field}"
    assert last["id"] == "pool"
    assert last["contract"] == "facts.v1"
    assert last["section_id"] == "250" and last["atom_id"] == "251"
    print("OK — عقد الحقائق كامل الحقول")


async def test_score_boundaries_no_crash_correct_confidence():
    print("\n--- test_score_boundaries_no_crash_correct_confidence ---")
    # بند 26 (فحص من الصفر، لا نصّ تدقيق أصليّ متاح): 251 تحوّل score
    # لـ int() بلا try/except، بخلاف كل تحويل رقميّ آخر بالملف -- تحقّقت
    # أن المنتِج الحقيقيّ الوحيد (201) يرسل score كعدد صحيح 0..100 دومًا
    # (int(round(...)) قبل النشر)، فلا مسار حيّ يبعث None أو نصًّا هناك.
    # هذا الاختبار يقفل الطرفين الحقيقيّين اللذين لا يغطّيهما ملف الاختبار
    # الحالي: بروز صفريّ (score=0 مع إشارة حقيقية) وبروز أقصى (score=100).
    # ٢٠٢٦-١٠-٠٧ (عقد الحقائق، ختم المالك «NQ»): الدرجة والثقة نُزعتا؛ يبقى إثبات عدم السقوط عند الحدّين وبقاء البركة الصحيحة.
    _atom, _bus, zero = await _run([_swing("swing_high", 12, ts=2, score=0)])
    assert zero[-1]["signal"] == "pool_high" and zero[-1]["metadata"]["price"] == 12, zero[-1]
    _atom, _bus, full = await _run([_swing("swing_low", 8, ts=2, score=100)])
    assert full[-1]["signal"] == "pool_low" and full[-1]["metadata"]["price"] == 8, full[-1]
    for card in (zero[-1], full[-1]):
        for judged in ("score", "confidence"):
            assert judged not in card, f"حقل حكمٍ ظهر: {judged}"
    print("OK — score=0 وscore=100 (طرفا مدى المنتِج الحقيقيّ 201): بلا سقوط، والبركة صحيحة بلا ثقة")


async def test_health_states():
    print("\n--- test_health_states ---")
    bus = FakeEventBus()
    atom = Atom()
    await atom.initialize(bus.make_context({}))
    h0 = await atom.health_check()
    assert h0.state == HealthState.UNHEALTHY
    await atom.start()
    h1 = await atom.health_check()
    assert h1.state == HealthState.DEGRADED
    await atom._on_swing(_swing("swing_high", 12, ts=1))
    h2 = await atom.health_check()
    assert h2.state == HealthState.HEALTHY
    print("OK — الصحة: UNHEALTHY→DEGRADED→HEALTHY")


async def main():
    tests = [
        test_swing_high_becomes_pool_high,
        test_swing_low_becomes_pool_low,
        test_confidence_scales_with_prominence,
        test_none_swing_no_pool,
        test_contract_shape_complete,
        test_score_boundaries_no_crash_correct_confidence,
        test_health_states,
    ]
    failed = []
    for t in tests:
        try:
            await t()
        except AssertionError as e:
            failed.append((t.__name__, str(e)))
            print(f"FAILED: {t.__name__}: {e}")
        except Exception as e:
            failed.append((t.__name__, repr(e)))
            print(f"ERROR: {t.__name__}: {e!r}")
    print("\n" + "=" * 60)
    if failed:
        print(f"فشل {len(failed)} من أصل {len(tests)}")
        sys.exit(1)
    print(f"نجح كل الاختبارات ({len(tests)}/{len(tests)})")


if __name__ == "__main__":
    asyncio.run(main())
