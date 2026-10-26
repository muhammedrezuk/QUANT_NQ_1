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
    "_atom208", _Path(__file__).resolve().parents[1] / "atom.py")
_mod = _ilu.module_from_spec(_spec)
sys.modules["_atom208"] = _mod
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
        return AtomContext(atom_id=208, config=config, logger=_NullLogger(),
                           publish=self.publish, subscribe=self.subscribe)


def _tr(signal="uptrend", confirms=0, cycle="c1", symbol="NQ100", tf="60s"):
    return {"symbol": symbol, "id": "structure_trend", "cycle_id": cycle, "status": "ok",
            "signal": signal, "score": 0, "confidence": 1.0, "quality": "good",
            "warnings": [], "metadata": {"method": "mss_governed", "timeframe": tf,
                                         "confirmations": confirms, "source": "mss"}}


async def _run(trends):
    bus = FakeEventBus()
    atom = Atom()
    await atom.initialize(bus.make_context({}))
    await atom.start()
    for t in trends:
        await atom._on_trend(t)
    ph = [p for n, p in bus.published if n == EVENT_OUT]
    return atom, bus, ph


async def test_zero_confirms_neutral():
    print("\n--- test_zero_confirms_neutral ---")
    _atom, _bus, ph = await _run([_tr("uptrend", confirms=0)])
    # ٢٠٢٦-١٠-٠٧ (عقد الحقائق، ختم المالك «NQ»): «neutral» كلمة حكمٍ نُزعت مع الدرجة والثقة؛ الحقيقة صفر تأكيدات.
    assert ph[-1].get("signal") == "neutral", ph[-1].get("signal")      # ١٨/١٠ (ختم «NQ»): كلمة الطور عادت
    for judged in ("score", "confidence", "quality"):
        assert judged not in ph[-1], f"حقل حكمٍ ظهر: {judged}"
    assert ph[-1]["metadata"]["confirmations"] == 0, ph[-1]["metadata"]
    assert ph[-1]["contract"] == "facts.v1" and ph[-1]["atom_id"] == "208"
    print("OK — اتجاه بلا تأكيد: لا طور يُنشر، والتأكيدات صفر")


async def test_one_confirm_early():
    print("\n--- test_one_confirm_early ---")
    _atom, _bus, ph = await _run([_tr("uptrend", confirms=1)])
    # ٢٠٢٦-١٠-٠٧ (عقد الحقائق، ختم المالك «NQ»): «early» كلمة طورٍ نُزعت؛ الحقيقة الباقية عدد التأكيدات نفسه.
    assert ph[-1].get("signal") == "early", ph[-1].get("signal")
    assert ph[-1]["metadata"]["confirmations"] == 1, ph[-1]["metadata"]
    print("OK — تأكيد واحد: confirmations=1 بلا كلمة طور")


async def test_mid_confirms_established():
    print("\n--- test_mid_confirms_established ---")
    _atom, _bus, ph = await _run([_tr("downtrend", confirms=3)])
    last = ph[-1]
    # ٢٠٢٦-١٠-٠٧ (عقد الحقائق، ختم المالك «NQ»): «established» كلمة طورٍ نُزعت؛ الحقل غائب.
    assert last.get("signal") == "established", last.get("signal")
    # ٢٠٢٦-١٠-٠٧ (عقد الحقائق، ختم المالك «NQ»): الدرجة (التأكيدات × 20) نُزعت؛ عدد التأكيدات نفسه هو الحقيقة.
    assert "score" not in last, last.get("score")
    assert last["metadata"]["confirmations"] == 3, last["metadata"]
    print(f"OK — 3 تأكيدات بلا كلمة طور (confirmations={last['metadata']['confirmations']})")


async def test_many_confirms_extended():
    print("\n--- test_many_confirms_extended ---")
    _atom, _bus, ph = await _run([_tr("uptrend", confirms=6)])
    last = ph[-1]
    # ٢٠٢٦-١٠-٠٧ (عقد الحقائق، ختم المالك «NQ»): «extended» كلمة طورٍ نُزعت؛ الحقل غائب.
    assert last.get("signal") == "extended", last.get("signal")
    # ٢٠٢٦-١٠-٠٧ (عقد الحقائق، ختم المالك «NQ»): الثقة نُزعت؛ عدد التأكيدات نفسه هو الحقيقة.
    assert "confidence" not in last, last.get("confidence")
    assert last["metadata"]["confirmations"] == 6, last["metadata"]
    print("OK — 6 تأكيدات بلا كلمة طور")


async def test_range_is_neutral():
    print("\n--- test_range_is_neutral ---")
    _atom, _bus, ph = await _run([_tr("range", confirms=0), _tr("transition", confirms=0)])
    # ٢٠٢٦-١٠-٠٧ (عقد الحقائق، ختم المالك «NQ»): «neutral» نُزعت؛ العرضيّ والانتقاليّ لا يُنشر لهما طور.
    assert len(ph) == 2 and all(p.get("signal") == "neutral" for p in ph), [p.get("signal") for p in ph]
    assert all(p["metadata"]["confirmations"] == 0 for p in ph), [p["metadata"] for p in ph]
    print("OK — عرضي/انتقالي: لا طور")


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
    await atom._on_trend(_tr("uptrend", confirms=1))
    h2 = await atom.health_check()
    assert h2.state == HealthState.HEALTHY
    print("OK — الصحة: UNHEALTHY→DEGRADED→HEALTHY")


async def test_the_established_boundary_is_tested_at_the_boundary():
    """التأكيد عند الحدّ **راسخ**، وبعده بواحدٍ **ممتدّ** — لا قبله.

    ⛔ طفرة نجت (٢٠٢٦-٠٩-١٦): `if confirms <= established_max` تقلب إلى `<`
       فيصير التأكيد الرابع «ممتدًّا» بدل «راسخ» — طورٌ يقفز درجةً كاملة،
       و٢١٠ ينشره إلى مسار القرار. والاختبارات كانت تجرّب وسط المدى فقط.
    """
    print("\n--- test_the_established_boundary_is_tested_at_the_boundary ---")
    # ٢٠٢٦-١٠-٠٧ (عقد الحقائق، ختم المالك «NQ»): كلمات الطور نُزعت كلّها، فالحدّ (راسخ/ممتدّ) لم يعد يُرى في المخرج؛ الباقي غيابها وعدد التأكيدات كما دخل.
    _a, _b, out = await _run([_tr("uptrend", confirms=4)])      # الحدّ بالضبط
    assert out[-1].get("signal") == "established", ("الحدّ نفسه راسخ", out[-1].get("signal"))
    assert out[-1]["metadata"]["confirmations"] == 4, out[-1]["metadata"]
    _a2, _b2, out2 = await _run([_tr("uptrend", confirms=5)])   # بعده بواحد
    assert out2[-1].get("signal") == "extended", out2[-1].get("signal")
    assert out2[-1]["metadata"]["confirmations"] == 5, out2[-1]["metadata"]
    _a3, _b3, out3 = await _run([_tr("uptrend", confirms=1)])   # وحدُّ البداية
    assert out3[-1].get("signal") == "early", out3[-1].get("signal")
    assert out3[-1]["metadata"]["confirmations"] == 1, out3[-1]["metadata"]
    _a4, _b4, out4 = await _run([_tr("uptrend", confirms=0)])
    # ٢٠٢٦-١٠-٠٧ (عقد الحقائق، ختم المالك «NQ»): «neutral» نُزعت؛ صفر التأكيدات لا يُنشر له طور.
    assert out4[-1].get("signal") == "neutral", out4[-1].get("signal")
    # وطفرةٌ ثالثة نجت: احتياط الإطار — و٢٠٧ لا ينشره أعلى الحمولة
    _a5, _b5, out5 = await _run([_tr("uptrend", confirms=4, tf="5m")])
    assert out5[-1]["timeframe"] == "5m", ("الإطار ضاع", out5[-1]["timeframe"])
    print("OK — 0 · 1 · 4 · 5 تأكيدات تخرج كما دخلت بلا كلمة طور")

async def main():
    tests = [
        test_zero_confirms_neutral,
        test_one_confirm_early,
        test_mid_confirms_established,
        test_many_confirms_extended,
        test_range_is_neutral,
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
