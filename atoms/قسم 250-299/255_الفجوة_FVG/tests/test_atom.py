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
    "_atom255", _Path(__file__).resolve().parents[1] / "atom.py")
_mod = _ilu.module_from_spec(_spec)
sys.modules["_atom255"] = _mod
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
        return AtomContext(atom_id=255, config=config, logger=_NullLogger(),
                           publish=self.publish, subscribe=self.subscribe)


def _candle(high, low, ps=0.0, symbol="NQ100", tf="60s"):
    return {"symbol": symbol, "timeframe": tf, "period_start": ps, "timestamp": ps,
            "open": (high + low) / 2, "high": high, "low": low,
            "close": (high + low) / 2, "volume": 1}


async def _run(bars):
    bus = FakeEventBus()
    atom = Atom()
    await atom.initialize(bus.make_context({}))
    await atom.start()
    for i, (h, l) in enumerate(bars):
        await atom._on_candle(_candle(h, l, ps=float(i)))
    out = [p for n, p in bus.published if n == EVENT_OUT]
    return atom, bus, out


async def test_warmup_insufficient():
    print("\n--- test_warmup_insufficient ---")
    _atom, _bus, out = await _run([(10, 9), (11, 10)])  # < 3
    last = out[-1]
    assert last["status"] == "insufficient_data"
    assert last["signal"] == "none"
    assert "score" not in last, "لا حقل score ميت — §12"
    print("OK — الإحماء (<3 شموع): insufficient")


async def test_bullish_fvg():
    print("\n--- test_bullish_fvg ---")
    # candle1.high(10) < candle3.low(12) → فجوة صعودية
    _atom, _bus, out = await _run([(10, 9), (15, 11), (16, 12)])
    last = out[-1]
    assert last["signal"] == "fvg_bullish", last["signal"]
    assert last["metadata"]["gap_bottom"] == 10 and last["metadata"]["gap_top"] == 12
    assert "score" not in last, "لا حقل score ميت — §12"
    # ٢٠٢٦-١٠-٠٧ (عقد الحقائق، ختم المالك «NQ»): الثقة نُزعت؛ الحقيقة حجم الفجوة من حدّيها: 12 − 10 = 2.
    assert "confidence" not in last, last.get("confidence")
    assert last["metadata"]["gap_top"] - last["metadata"]["gap_bottom"] == 2
    print(f"OK — فجوة صعودية: [{last['metadata']['gap_bottom']}, {last['metadata']['gap_top']}] "
          f"size={last['metadata']['gap_top'] - last['metadata']['gap_bottom']}")


async def test_bearish_fvg():
    print("\n--- test_bearish_fvg ---")
    # candle1.low(15) > candle3.high(13) → فجوة هبوطية
    _atom, _bus, out = await _run([(16, 15), (14, 10), (13, 12)])
    last = out[-1]
    assert last["signal"] == "fvg_bearish", last["signal"]
    assert last["metadata"]["gap_top"] == 15 and last["metadata"]["gap_bottom"] == 13
    # ٢٠٢٦-١٠-٠٧ (عقد الحقائق، ختم المالك «NQ»): الثقة نُزعت؛ الحقيقة حجم الفجوة من حدّيها: 15 − 13 = 2.
    assert "confidence" not in last, last.get("confidence")
    assert last["metadata"]["gap_top"] - last["metadata"]["gap_bottom"] == 2
    print(f"OK — فجوة هبوطية: [{last['metadata']['gap_bottom']}, {last['metadata']['gap_top']}] "
          f"size={last['metadata']['gap_top'] - last['metadata']['gap_bottom']}")


async def test_confidence_scales_with_gap_size():
    print("\n--- test_confidence_scales_with_gap_size ---")
    # ٢٠٢٦-١٠-٠٧ (عقد الحقائق، ختم المالك «NQ»): لا ثقة بعد اليوم؛ الحقيقة حجم كلّ فجوة من حدّيها (29 مقابل 0.5).
    _atom, _bus, wide = await _run([(10, 9), (30, 20), (40, 39)])  # فجوة كبيرة نسبيًّا
    _atom, _bus, narrow = await _run([(10, 9), (100, 5), (11, 10.5)])  # فجوة ضيّقة داخل مدى شاسع
    assert wide[-1]["signal"] == "fvg_bullish" and narrow[-1]["signal"] == "fvg_bullish"
    for card in (wide[-1], narrow[-1]):
        assert "confidence" not in card, card.get("confidence")
    wide_size = wide[-1]["metadata"]["gap_top"] - wide[-1]["metadata"]["gap_bottom"]
    narrow_size = narrow[-1]["metadata"]["gap_top"] - narrow[-1]["metadata"]["gap_bottom"]
    assert wide_size == 29 and narrow_size == 0.5, (wide_size, narrow_size)
    assert 0.0 < narrow_size < wide_size
    print(f"OK — فجوة ضيّقة size={narrow_size} · فجوة واسعة size={wide_size} (بلا ثقة)")


async def test_overlap_no_fvg():
    print("\n--- test_overlap_no_fvg ---")
    _atom, _bus, out = await _run([(10, 8), (11, 9), (12, 10)])  # متداخلة
    assert out[-1]["signal"] == "none", "شموع متداخلة = لا فجوة"
    print("OK — شموع متداخلة: لا فجوة")


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
    await atom._on_candle(_candle(10, 9))
    h2 = await atom.health_check()
    assert h2.state == HealthState.HEALTHY
    print("OK — الصحة: UNHEALTHY→DEGRADED→HEALTHY")


async def main():
    tests = [
        test_warmup_insufficient,
        test_bullish_fvg,
        test_bearish_fvg,
        test_confidence_scales_with_gap_size,
        test_overlap_no_fvg,
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
