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
    "_atom207", _Path(__file__).resolve().parents[1] / "atom.py")
_mod = _ilu.module_from_spec(_spec)
sys.modules["_atom207"] = _mod
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
        return AtomContext(atom_id=207, config=config, logger=_NullLogger(),
                           publish=self.publish, subscribe=self.subscribe)


def _mss(signal="none", shift_type=None, direction=None, cycle="c1", symbol="NQ100", tf="60s"):
    return {"symbol": symbol, "id": "mss", "cycle_id": cycle, "status": "ok",
            "signal": signal, "score": 0, "confidence": 1.0 if signal == "shift" else 0.0,
            "quality": "good", "warnings": [],
            "metadata": {"method": "shift_unifier", "timeframe": tf,
                         "shift_type": shift_type, "direction": direction, "level": None}}


def _t151(signal="sideways", symbol="NQ100", tf="60s"):
    return {"symbol": symbol, "id": "trend", "cycle_id": "x", "status": "ok",
            "signal": signal, "score": 50, "confidence": 0.7, "strength": "moderate",
            "phase": "established", "quality": "good", "warnings": [],
            "metadata": {"method": "ema_slope", "timeframe": tf}}


async def _mk():
    bus = FakeEventBus()
    atom = Atom()
    await atom.initialize(bus.make_context({}))
    await atom.start()
    return atom, bus


def _trend(bus):
    return [p for n, p in bus.published if n == EVENT_OUT]


async def test_default_from_151_before_mss():
    print("\n--- test_default_from_151_before_mss ---")
    atom, bus = await _mk()
    await atom._on_trend151(_t151("up"))
    await atom._on_mss(_mss(signal="none"))
    last = _trend(bus)[-1]
    # ١٨/١٠ (ختم المالك «NQ»: «رجّعهم»): كلمة الحالة عادت؛ والثقة باقيةٌ منزوعة كما في ٠٧/١٠.
    assert last.get("signal") == "uptrend", last.get("signal")
    for judged in ("score", "confidence", "quality"):
        assert judged not in last, f"حقل حكمٍ ظهر: {judged}"
    assert last["metadata"]["source"] == "trend_151"
    assert last["metadata"]["confirmations"] == 0, last["metadata"]
    print("OK — قبل MSS: المصدر 151 بلا تأكيد، وكلمة الجهة منزوعة")


async def test_bos_up_sets_uptrend():
    print("\n--- test_bos_up_sets_uptrend ---")
    atom, bus = await _mk()
    await atom._on_mss(_mss(signal="shift", shift_type="bos", direction="up"))
    last = _trend(bus)[-1]
    # ١٨/١٠ (ختم المالك «NQ»): «uptrend» عادت؛ والثقة منزوعة؛ مصدر MSS وتأكيدٌ واحد.
    assert last.get("signal") == "uptrend", last.get("signal")
    for judged in ("score", "confidence", "quality"):
        assert judged not in last, f"حقل حكمٍ ظهر: {judged}"
    assert last["metadata"]["source"] == "mss"
    assert last["metadata"]["confirmations"] == 1
    assert last["contract"] == "facts.v1" and last["atom_id"] == "207"
    print("OK — BOS → مصدر MSS (confirmations=1) بلا كلمة جهة")


async def test_choch_sets_transition():
    print("\n--- test_choch_sets_transition ---")
    atom, bus = await _mk()
    await atom._on_mss(_mss(signal="shift", shift_type="bos", direction="up"))
    await atom._on_mss(_mss(signal="shift", shift_type="choch", direction="down"))
    out = _trend(bus)
    last = out[-1]
    # ١٨/١٠ (ختم المالك «NQ»): «transition» عادت.
    assert last.get("signal") == "transition", last.get("signal")
    # ٢٠٢٦-١٠-٠٧ (عقد الحقائق، ختم المالك «NQ»): الثقة نُزعت؛ حدث الانتقال يبقى ويصفّر التأكيدات.
    assert "confidence" not in last, last.get("confidence")
    # ٢٠٢٦-١٠-٠٧ (عقد الحقائق، ختم المالك «NQ»): نوع التحوّل لا يُنشر في حقيقة 207؛ يميّزه أنّ المصدر MSS والتأكيدات صُفّرت من واحدٍ قبله.
    assert out[-2]["metadata"]["source"] == "mss" and out[-2]["metadata"]["confirmations"] == 1, out[-2]["metadata"]
    assert last["metadata"]["source"] == "mss", last["metadata"]
    assert last["metadata"]["confirmations"] == 0, last["metadata"]
    print("OK — CHoCH: مصدر MSS والتأكيدات صُفّرت (1 → 0) بلا كلمة حالة")


async def test_mss_governs_over_151():
    print("\n--- test_mss_governs_over_151 ---")
    atom, bus = await _mk()
    await atom._on_mss(_mss(signal="shift", shift_type="bos", direction="up"))  # has_mss
    await atom._on_trend151(_t151("down"))   # يجب ألا يتجاوز MSS
    await atom._on_mss(_mss(signal="none"))
    last = _trend(bus)[-1]
    # ٢٠٢٦-١٠-٠٧ (عقد الحقائق، ختم المالك «NQ»): كلمة الجهة نُزعت؛ حكم MSS يُقرأ من المصدر والتأكيد الباقي وغياب «range».
    assert last.get("signal") == "uptrend", ("MSS يحكم بعد وصوله — 151 لا يتجاوزه", last.get("signal"))
    assert last["metadata"]["source"] == "mss" and last["metadata"]["confirmations"] == 1, last["metadata"]
    # ٢٠٢٦-١٠-٠٧ (عقد الحقائق، ختم المالك «NQ»): وبطاقة 151 الحيّة بلا كلمة جهة لا تقلب الحالة إلى «range» بعد MSS.
    live151 = {k: v for k, v in _t151("down").items() if k not in ("signal", "score", "confidence", "strength", "phase", "quality")}
    await atom._on_trend151(live151)
    await atom._on_mss(_mss(signal="none", cycle="c2"))
    last2 = _trend(bus)[-1]
    assert last2.get("signal") != "range" and last2["metadata"]["source"] == "mss", last2
    print("OK — MSS الحاكم: 151 المعاكس لا يتجاوزه")


async def test_confirmations_grow():
    print("\n--- test_confirmations_grow ---")
    atom, bus = await _mk()
    for _ in range(3):
        await atom._on_mss(_mss(signal="shift", shift_type="bos", direction="up"))
    last = _trend(bus)[-1]
    assert last["metadata"]["confirmations"] == 3, last["metadata"]["confirmations"]
    # ٢٠٢٦-١٠-٠٧ (عقد الحقائق، ختم المالك «NQ»): الدرجة (التأكيدات × 20) نُزعت؛ عدد التأكيدات نفسه هو الحقيقة.
    assert "score" not in last, last.get("score")
    print(f"OK — تراكم التأكيد: confirmations={last['metadata']['confirmations']}")


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
    await atom._on_mss(_mss(signal="none"))
    h2 = await atom.health_check()
    assert h2.state == HealthState.HEALTHY
    print("OK — الصحة: UNHEALTHY→DEGRADED→HEALTHY")


async def test_same_direction_confirms_and_the_opposite_resets():
    """الكسر بنفس الجهة يُراكم التأكيد، والمعاكس يصفّره — لا العكس.

    ⛔ طفرة نجت (٢٠٢٦-٠٩-١٦): `if new_dir == st["dir"]` تقلب إلى `!=`
       فينقلب معنى الاتجاه كلّه: الاستمرار يصفّر والانعكاس يُراكم. و٢٠٨
       يبني الطور على هذا العدّاد، و٢١٠ ينشره إلى مسار القرار.
    """
    print("\n--- test_same_direction_confirms_and_the_opposite_resets ---")
    atom, bus = await _mk()
    await atom._on_mss(_mss("shift", shift_type="bos", direction="up"))
    await atom._on_mss(_mss("shift", shift_type="bos", direction="up", cycle="c2"))
    out = _trend(bus)
    # ١٨/١٠ (ختم المالك «NQ»): «uptrend/downtrend» عادتا، ومعهما عدد التأكيدات.
    assert out[-1].get("signal") == "uptrend", out[-1].get("signal")
    assert out[-1]["metadata"]["confirmations"] == 2, (
        "الاستمرار لم يُراكم", out[-1]["metadata"])
    await atom._on_mss(_mss("shift", shift_type="bos", direction="down", cycle="c3"))
    out2 = _trend(bus)
    assert out2[-1].get("signal") == "downtrend", out2[-1].get("signal")
    assert out2[-1]["metadata"]["confirmations"] == 1, (
        "الانعكاس لم يصفّر", out2[-1]["metadata"])
    print("OK — نفس الجهة تُراكم (٢)، والمعاكسة تصفّر إلى (١)")

async def main():
    tests = [
        test_default_from_151_before_mss,
        test_bos_up_sets_uptrend,
        test_choch_sets_transition,
        test_mss_governs_over_151,
        test_confirmations_grow,
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

# 2026-10-18 (owner seal "NQ"): 151's word is stripped by the facts contract, so before the first shift the state is
# rebuilt from 151's published numbers with 151's own rule; and the contract keeps 207's and 208's words, theirs only.
def _t151_facts(fast, slow, slope, position, symbol="NQ100", tf="60s"):
    return {"symbol": symbol, "id": "trend", "cycle_id": "x", "status": "ok",
            "metadata": {"method": "ema_slope", "timeframe": tf, "ema_fast_value": fast, "ema_slow_value": slow,
                         "ema_slope": slope, "price_position": position}}


async def _state_from_facts(*facts):
    atom, bus = await _mk()
    await atom._on_trend151(_t151_facts(*facts))
    await atom._on_mss(_mss())
    return _trend(bus)[-1]["signal"]


def test_state_before_any_shift_is_rebuilt_from_151_numbers():
    assert asyncio.run(_state_from_facts(101.0, 100.0, 0.05, "above_fast")) == "uptrend"
    assert asyncio.run(_state_from_facts(99.0, 100.0, -0.05, "below_fast")) == "downtrend"
    assert asyncio.run(_state_from_facts(100.01, 100.0, 0.001, "above_fast")) == "range"   # entangled and flat
    assert asyncio.run(_state_from_facts(101.0, 100.0, -0.05, "below_fast")) == "range"    # nothing confirms


def test_facts_contract_keeps_207_and_208_words_and_only_theirs():
    from shared.section_contract import stamp_section
    for atom_id, word in (("207", "uptrend"), ("207", "transition"), ("208", "established"), ("208", "extended")):
        out = stamp_section({"symbol": "NQ", "signal": word, "score": 60, "confidence": 1.0}, section_id="200", atom_id=atom_id)
        assert out["signal"] == word and "score" not in out and "confidence" not in out
    assert "signal" not in stamp_section({"symbol": "NQ", "signal": "bullish"}, section_id="200", atom_id="207")
    assert "signal" not in stamp_section({"symbol": "NQ", "signal": "up"}, section_id="150", atom_id="151")
    assert "signal" not in stamp_section({"symbol": "NQ", "signal": "range"}, section_id="350", atom_id="356")
