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
    "_atom206", _Path(__file__).resolve().parents[1] / "atom.py")
_mod = _ilu.module_from_spec(_spec)
sys.modules["_atom206"] = _mod
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
        return AtomContext(atom_id=206, config=config, logger=_NullLogger(),
                           publish=self.publish, subscribe=self.subscribe)


def _bos(signal="none", direction=None, level=None, score=0, cycle="c1", symbol="NQ100", tf="60s"):
    return {"symbol": symbol, "id": "bos", "cycle_id": cycle, "status": "ok",
            "signal": signal, "score": score, "confidence": 1.0 if signal == "bos" else 0.0,
            "quality": "good", "warnings": [],
            "metadata": {"method": "close_break_continuation", "timeframe": tf,
                         "direction": direction, "level": level, "close": 0.0}}


def _choch(signal="none", direction=None, level=None, score=0, cycle="c1", symbol="NQ100", tf="60s"):
    return {"symbol": symbol, "id": "choch", "cycle_id": cycle, "status": "ok",
            "signal": signal, "score": score, "confidence": 1.0 if signal == "choch" else 0.0,
            "quality": "good", "warnings": [],
            "metadata": {"method": "close_break_reversal", "timeframe": tf,
                         "direction": direction, "level": level, "close": 0.0}}


async def _mk():
    bus = FakeEventBus()
    atom = Atom()
    await atom.initialize(bus.make_context({}))
    await atom.start()
    return atom, bus


def _mss(bus):
    return [p for n, p in bus.published if n == EVENT_OUT]


async def test_bos_becomes_shift():
    print("\n--- test_bos_becomes_shift ---")
    atom, bus = await _mk()
    await atom._on_bos(_bos(signal="bos", direction="up", level=12, score=14, cycle="c1"))
    last = _mss(bus)[-1]
    assert last["signal"] == "shift", last["signal"]
    assert last["metadata"]["shift_type"] == "bos"
    # ٢٠٢٦-١٠-٠٧ (عقد الحقائق، ختم المالك «NQ»): «up» كلمة جهةٍ نُزعت مع الدرجة والثقة؛ الحقيقة نوع التحوّل ومستواه.
    assert "direction" not in last["metadata"], last["metadata"]
    for judged in ("score", "confidence", "quality"):
        assert judged not in last, f"حقل حكمٍ ظهر: {judged}"
    assert last["metadata"]["level"] == 12, last["metadata"]
    print(f"OK — BOS → تحوّل: shift_type={last['metadata']['shift_type']} level={last['metadata']['level']}")


async def test_choch_becomes_shift():
    print("\n--- test_choch_becomes_shift ---")
    atom, bus = await _mk()
    await atom._on_choch(_choch(signal="choch", direction="down", level=8, score=20, cycle="c1"))
    last = _mss(bus)[-1]
    assert last["signal"] == "shift"
    assert last["metadata"]["shift_type"] == "choch"
    print("OK — CHoCH → تحوّل: shift_type=choch")


async def test_no_break_single_none():
    print("\n--- test_no_break_single_none ---")
    atom, bus = await _mk()
    await atom._on_bos(_bos(signal="none", cycle="c1"))
    await atom._on_choch(_choch(signal="none", cycle="c1"))
    mss = _mss(bus)
    assert len(mss) == 1, f"لا كسر = تحوّل واحد none (طلع {len(mss)})"
    assert mss[0]["signal"] == "none"
    print("OK — لا كسر: none واحد (choch none ما يكرّر)")


async def test_shift_guard_ordering():
    print("\n--- test_shift_guard_ordering ---")
    atom, bus = await _mk()
    await atom._on_choch(_choch(signal="choch", direction="down", level=8, cycle="c1"))
    await atom._on_bos(_bos(signal="none", cycle="c1"))  # نفس الدورة — لا يطمس التحوّل
    mss = _mss(bus)
    assert len(mss) == 1, f"التحوّل ما ينطمس بـnone (طلع {len(mss)})"
    assert mss[0]["signal"] == "shift" and mss[0]["metadata"]["shift_type"] == "choch"
    print("OK — التحوّل محميّ: bos none بعد choch shift لا يطمسه")


async def test_contract_shape_complete():
    print("\n--- test_contract_shape_complete ---")
    atom, bus = await _mk()
    await atom._on_bos(_bos(signal="bos", direction="up", level=12, cycle="c1"))
    last = _mss(bus)[-1]
    # ٢٠٢٦-١٠-٠٧ (عقد الحقائق، ختم المالك «NQ»): الحقول المطلوبة صارت ختم الحقيقة، وحقول الحكم وكلمة الجهة ممنوعة.
    for field in ("symbol", "id", "cycle_id", "status", "signal", "warnings", "metadata",
                  "as_of", "computed_on", "section_id", "atom_id", "contract"):
        assert field in last, f"حقل ناقص بالعقد: {field}"
    for judged in ("score", "confidence", "quality"):
        assert judged not in last, f"حقل حكمٍ ظهر: {judged}"
    for field in ("method", "timeframe", "shift_type", "level"):
        assert field in last["metadata"], f"حقل metadata ناقص: {field}"
    assert "direction" not in last["metadata"], last["metadata"]
    assert last["id"] == "mss"
    assert last["contract"] == "facts.v1"
    assert last["section_id"] == "200" and last["atom_id"] == "206"
    print("OK — عقد الحقائق كامل الحقول")


async def test_timeframe_and_metadata_survive_the_fallback():
    """الإطار يُلتقط من `metadata` حين يغيب أعلى الحمولة — والاحتياط مُختبَر.

    ⛔ طفرتان نجتا (٢٠٢٦-٠٩-١٦): `payload.get("metadata") or {}` و
       `payload.get("timeframe","") or meta_in.get("timeframe","")` تقلبان
       إلى `and` فيصير الإطار فارغًا والبيانات الوصفيّة مهدورة — ولا يصرخ
       شيء، لأنّ الاختبارات كانت تفحص الإشارة ولا تفحص ما يُبنى حولها.
       و٢٠٤/٢٠٥ لا ينشران `timeframe` أعلى الحمولة أصلًا، فالاحتياط **هو**
       المسار الحيّ لا حالةً نادرة.
    """
    print("\n--- test_timeframe_and_metadata_survive_the_fallback ---")
    atom, bus = await _mk()
    await atom._on_bos(_bos("bos", direction="up", level=12.5, score=60, tf="30s"))
    out = _mss(bus)
    assert out, "لم يُنشر تحوّل"
    last = out[-1]
    assert last["timeframe"] == "30s", ("الإطار ضاع", last["timeframe"])
    meta = last["metadata"]
    assert meta["timeframe"] == "30s", meta
    # ٢٠٢٦-١٠-٠٧ (عقد الحقائق، ختم المالك «NQ»): الجهة نُزعت من metadata؛ يعبر الاحتياطَ الإطارُ والمستوى ونوع التحوّل.
    assert "direction" not in meta and meta["level"] == 12.5, meta
    assert meta["shift_type"] == "bos", meta
    print("OK — الإطار والمستوى ونوع التحوّل تعبر الاحتياط سليمة")


async def test_empty_cycle_id_never_poisons_the_dedup_list():
    """معرّف دورةٍ فارغ لا يُسجَّل — وإلّا ابتلع صمتًا مشروعًا.

    ⛔ طفرة نجت: `if cycle_id and cycle_id not in self._shifted` تقلب إلى
       `or` فيُسجَّل الفارغ في قائمة المكتومين، فتُكتم بعده كلّ حمولةٍ فارغة
       المعرّف — أي صمتٌ يبدو قرارًا.
    """
    print("\n--- test_empty_cycle_id_never_poisons_the_dedup_list ---")
    atom, bus = await _mk()
    await atom._on_bos(_bos("bos", direction="up", level=1.0, cycle=""))
    before = len(_mss(bus))
    await atom._on_bos(_bos("none", cycle=""))
    after = _mss(bus)
    assert len(after) > before, "الحمولة الفارغة المعرّف كُتمت"
    assert after[-1]["signal"] != "shift", after[-1]["signal"]
    print("OK — الفارغ لا يدخل قائمة الكتم، والصمت لا يُخترع")


async def test_the_silent_path_keeps_its_timeframe():
    """الإطار يعبر الاحتياط في مسار «لا شيء» أيضًا.

    ⛔ طفرتان نجتا (٢٠٢٦-٠٩-١٦): `payload.get("metadata") or {}` و
       `payload.get("timeframe","") or meta_in.get("timeframe","")` تقلبان
       إلى `and`، فيخرج الإطار فارغًا. والذرّات المغذِّية لا تنشر `timeframe`
       أعلى الحمولة، فالاحتياط **هو** المسار الحيّ — وكانت الاختبارات تفحص
       مسار الإشارة وحده وتترك مسار الصمت بلا حارس.
    """
    print("\n--- test_the_silent_path_keeps_its_timeframe ---")
    atom, bus = await _mk()
    await atom._on_bos(_bos("none", tf="15m"))
    out = _mss(bus)
    assert out, "لم يُنشر شيء على مسار الصمت"
    assert out[-1]["signal"] == "none", out[-1]["signal"]
    assert out[-1]["timeframe"] == "15m", ("الإطار ضاع في مسار الصمت", out[-1]["timeframe"])
    assert (out[-1]["metadata"] or {}).get("timeframe") == "15m", out[-1]["metadata"]
    print("OK — مسار الصمت يحمل إطاره كاملًا")

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
    await atom._on_bos(_bos(signal="none", cycle="c1"))
    h2 = await atom.health_check()
    assert h2.state == HealthState.HEALTHY
    print("OK — الصحة: UNHEALTHY→DEGRADED→HEALTHY")


async def main():
    tests = [
        test_bos_becomes_shift,
        test_choch_becomes_shift,
        test_no_break_single_none,
        test_shift_guard_ordering,
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
