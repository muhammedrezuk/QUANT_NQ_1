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
    "_atom202", _Path(__file__).resolve().parents[1] / "atom.py")
_mod = _ilu.module_from_spec(_spec)
sys.modules["_atom202"] = _mod
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
        return AtomContext(atom_id=202, config=config, logger=_NullLogger(),
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
    ext = [p for n, p in bus.published if n == EVENT_OUT]
    return atom, bus, ext


async def test_no_structure_insufficient():
    print("\n--- test_no_structure_insufficient ---")
    _atom, _bus, ext = await _run([_swing("none"), _swing("none")])
    last = ext[-1]
    assert last["status"] == "insufficient_data", last["status"]
    assert last["signal"] == "none"
    assert "no_structure_yet" in last["warnings"]
    print("OK — بلا بنية بعد: insufficient_data")


async def test_higher_high():
    print("\n--- test_higher_high ---")
    _atom, _bus, ext = await _run([
        _swing("swing_high", 10, ts=1, score=50),
        _swing("swing_high", 12, ts=2, score=60)])
    last = ext[-1]
    assert last["status"] == "ok", last
    assert last["signal"] == "HH", last["signal"]
    assert last["metadata"]["swing_high"] == 12
    # ٢٠٢٦-١٠-٠٧ (عقد الحقائق، ختم المالك «NQ»): لا درجة ولا ثقة؛ الحقيقة الحدث HH ومستواه ووقته.
    for judged in ("score", "confidence", "quality"):
        assert judged not in last, f"حقل حكمٍ ظهر: {judged}"
    assert last["metadata"]["swing_high_time"] == 2, last["metadata"]
    # ٢٠٢٦-١٠-٠٧ (عقد الحقائق، ختم المالك «NQ»): بطاقة 201 الحيّة بلا درجة ولا ثقة، والحدث HH يقع منها كما هو.
    bare = [{k: v for k, v in s.items() if k not in ("score", "confidence", "quality")}
            for s in (_swing("swing_high", 10, ts=1), _swing("swing_high", 12, ts=2))]
    _a2, _b2, ext2 = await _run(bare)
    assert ext2[-1]["signal"] == "HH" and ext2[-1]["metadata"]["swing_high"] == 12, ext2[-1]
    print(f"OK — قمة أعلى: HH · مستوى={last['metadata']['swing_high']} "
          f"وقت={last['metadata']['swing_high_time']}")


async def test_lower_low():
    print("\n--- test_lower_low ---")
    _atom, _bus, ext = await _run([
        _swing("swing_low", 10, ts=1, score=40),
        _swing("swing_low", 8, ts=2, score=55)])
    last = ext[-1]
    assert last["signal"] == "LL", last["signal"]
    assert last["metadata"]["swing_low"] == 8
    print(f"OK — قاع أدنى: LL · مستوى={last['metadata']['swing_low']}")


async def test_first_swing_no_event():
    print("\n--- test_first_swing_no_event ---")
    _atom, _bus, ext = await _run([_swing("swing_high", 10, ts=1, score=50)])
    last = ext[-1]
    assert last["status"] == "ok", last
    assert last["signal"] == "none", "أول قمة بلا سابقة = لا حدث HH"
    assert last["metadata"]["swing_high"] == 10
    print("OK — أول قمة: مستوى مسجّل بلا حدث (بحقّ)")


async def test_contract_shape_complete():
    print("\n--- test_contract_shape_complete ---")
    _atom, _bus, ext = await _run([
        _swing("swing_high", 10, ts=1), _swing("swing_high", 12, ts=2)])
    last = ext[-1]
    # ٢٠٢٦-١٠-٠٧ (عقد الحقائق، ختم المالك «NQ»): الحقول المطلوبة صارت ختم الحقيقة، وحقول الحكم ممنوعة.
    for field in ("symbol", "id", "cycle_id", "status", "signal", "warnings", "metadata",
                  "as_of", "computed_on", "section_id", "atom_id", "contract"):
        assert field in last, f"حقل ناقص بالعقد: {field}"
    for judged in ("score", "confidence", "quality"):
        assert judged not in last, f"حقل حكمٍ ظهر: {judged}"
    for field in ("method", "timeframe", "swing_high", "swing_high_time",
                  "swing_low", "swing_low_time", "close"):
        assert field in last["metadata"], f"حقل metadata ناقص: {field}"
    assert last["id"] == "external"
    assert last["contract"] == "facts.v1"
    assert last["section_id"] == "200" and last["atom_id"] == "202"
    print("OK — عقد الحقائق كامل الحقول")


async def test_health_states():
    print("\n--- test_health_states ---")
    bus = FakeEventBus()
    atom = Atom()
    await atom.initialize(bus.make_context({}))
    h0 = await atom.health_check()
    assert h0.state == HealthState.UNHEALTHY, "قبل start"
    await atom.start()
    h1 = await atom.health_check()
    assert h1.state == HealthState.DEGRADED, "بعد start بلا مدخل"
    await atom._on_swing(_swing("swing_high", 10, ts=1))
    h2 = await atom.health_check()
    assert h2.state == HealthState.HEALTHY, "بعد وصول قمة"
    print("OK — الصحة: UNHEALTHY→DEGRADED→HEALTHY")


async def test_an_equal_swing_is_not_a_new_extreme():
    """تأرجحٌ مساوٍ ليس حدثًا — والحدّ يُختبر **عنده** لا في وسطه.

    ⛔ ثلاث طفرات نجت (٢٠٢٦-٠٩-١٦): مقارنتا السعر بالسابق تقلبان إلى
       `>=` و`<=` فيصير **التساوي** حدثًا جديدًا — إشارةٌ من سوقٍ لم يتحرّك.
       والثالثة `event != SIGNAL_NONE` تقلب فينقلب عدّاد الأحداث. وكانت
       الاختبارات تجرّب الأعلى والأدنى ولا تجرّب المساوي قطّ.
    """
    print("\n--- test_an_equal_swing_is_not_a_new_extreme ---")
    atom, bus, out = await _run([
        _swing("swing_high", price=100.0, ts=1.0),
        _swing("swing_high", price=100.0, ts=2.0),      # مساوية تمامًا
        _swing("swing_low", price=50.0, ts=3.0),
        _swing("swing_low", price=50.0, ts=4.0)])      # مساوية تمامًا
    assert all(o["signal"] == "none" for o in out), (
        "التساوي صار حدثًا", [o["signal"] for o in out])
    h = await atom.health_check()
    assert h.details["events"] == 0, ("عُدّت أحداثٌ لم تقع", h.details)

    # وحركةٌ حقيقيّة بمقدار خانةٍ واحدة تبقى حدثًا — الحارس لا يُعمي
    atom2, bus2, out2 = await _run([
        _swing("swing_high", price=100.0, ts=1.0),
        _swing("swing_high", price=100.01, ts=2.0)])
    assert out2[-1]["signal"] == "HH", ("الحركة الحقيقيّة ضاعت", out2[-1]["signal"])
    atom3, bus3, out3 = await _run([
        _swing("swing_low", price=50.0, ts=1.0),
        _swing("swing_low", price=49.99, ts=2.0)])
    assert out3[-1]["signal"] == "LL", out3[-1]["signal"]
    print("OK — المساوي لا حدث، وHH/LL الحقيقيّتان تمرّان، والعدّاد يطابق")

async def test_a_priceless_swing_is_ignored_and_the_timeframe_survives():
    """تأرجحٌ بلا سعر لا يُعدّ · والإطار يعبر الاحتياط.

    ⛔ طفرتان نجتا (٢٠٢٦-٠٩-١٦):
       · `elif swing_signal == SWING_LOW and swing_price is not None` ← `or` :
         حمولةٌ بلا سعر تدخل المسار فتُفسد الحالة المحفوظة وتُعدّ تأرجحًا
         لم يقع.
       · `payload.get("timeframe","") or meta_in.get("timeframe","")` ← `and` :
         الإطار يضيع — و٢٠١ لا ينشره أعلى الحمولة، فالاحتياط **هو** المسار.
    """
    print("\n--- test_a_priceless_swing_is_ignored_and_the_timeframe_survives ---")
    atom, bus, out = await _run([
        _swing("swing_low"),                       # بلا سعر
        _swing("swing_high"),                      # بلا سعر
        _swing("swing_high", price=100.0, ts=1.0), # وسعرٌ حقيقيّ
        _swing("swing_low", price=50.0, ts=2.0)])
    h = await atom.health_check()
    assert h.details["swings"] == 2, ("عُدّ تأرجحٌ بلا سعر", h.details)
    assert out[-1]["timeframe"] == "60s", ("الإطار ضاع", out[-1]["timeframe"])
    assert (out[-1]["metadata"] or {}).get("timeframe") == "60s", out[-1]["metadata"]
    print("OK — بلا سعرٍ لا يُعدّ، والإطار يعبر الاحتياط")

async def main():
    tests = [
        test_no_structure_insufficient,
        test_higher_high,
        test_lower_low,
        test_first_swing_no_event,
        test_contract_shape_complete,
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
