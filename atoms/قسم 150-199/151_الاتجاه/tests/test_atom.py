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
    "_atom151", _Path(__file__).resolve().parents[1] / "atom.py")
_mod = _ilu.module_from_spec(_spec)
sys.modules["_atom151"] = _mod
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
        return AtomContext(atom_id=151, config=config, logger=_NullLogger(),
                           publish=self.publish, subscribe=self.subscribe)


# small periods → fast warmup for tests
CFG = {"ema_fast": 3, "ema_slow": 5, "slope_lookback": 2, "min_candles": 6,
       "flat_slope_pct": 0.02, "flat_distance_pct": 0.05,
       "strong_score": 80, "moderate_score": 45, "emerging_bars": 2}


def _candle(close, symbol="NQ100", tf="60s"):
    return {"symbol": symbol, "open": close, "high": close, "low": close,
            "close": close, "volume": 1, "timeframe": tf,
            "period_start": 0.0, "timestamp": 0.0}


async def _run(closes, cfg=None):
    bus = FakeEventBus()
    atom = Atom()
    await atom.initialize(bus.make_context(cfg or dict(CFG)))
    await atom.start()
    for c in closes:
        await atom._on_candle(_candle(c))
    trend = [p for n, p in bus.published if n == EVENT_OUT]
    return atom, bus, trend


async def test_candle_memory_survives_restart():
    """ختم المالك ٢٠٢٦-٠٨-٢١ — «لا فقدان للبيانات» (ورقة التنفيذ §٣٦).

    العطل المقيس قبل هذا الحارس: الغلاف الحيّ كان يستبدل snapshot/restore،
    فذاكرة الشموع تضيع كاملة عند كل إقلاع — والذرّة تطلب ٥٥ شمعة والشمعة
    دقيقة، أي **٥٥ دقيقة صمت** بعد كل إعادة تشغيل. هنا نُثبت أنّها تنجو.
    """
    print("\n--- test_candle_memory_survives_restart ---")
    closes = [100 + i for i in range(30)]
    atom, _bus, trend = await _run(closes)
    before = dict(atom._state[("NQ100", "60s")])
    saved = await atom.snapshot()
    assert "live_analysis" in saved, "الغلاف الحيّ لازم يبقى محفوظًا"
    assert "atom" in saved, "حالة الشموع لازم تُحفظ بجانبه — لا تُدهَس"

    revived = Atom()
    bus2 = FakeEventBus()
    await revived.initialize(bus2.make_context(dict(CFG)))
    await revived.restore(saved)
    await revived.start()
    after = revived._state[("NQ100", "60s")]
    assert after["count"] == before["count"], (after["count"], before["count"])
    assert abs(after["ema_slow"] - before["ema_slow"]) < 1e-9
    assert abs(after["ema_fast"] - before["ema_fast"]) < 1e-9
    assert list(after["slow_hist"]) == list(before["slow_hist"])
    assert revived._candles_seen == atom._candles_seen

    # وشمعة واحدة بعد الإحياء تكمل من حيث وقفت، لا من الصفر.
    await revived._on_candle(_candle(closes[-1] + 1))
    assert revived._state[("NQ100", "60s")]["count"] == before["count"] + 1
    fresh = [p for n, p in bus2.published if n == EVENT_OUT]
    assert fresh and fresh[-1]["status"] != "insufficient_data", fresh[-1]["status"]
    print(f"OK — ذاكرة الشموع نجت الإقلاع: count={after['count']} بلا إحماء جديد")


async def test_warmup_insufficient():
    print("\n--- test_warmup_insufficient ---")
    _atom, _bus, trend = await _run([100, 101, 102])  # < min_candles(6)
    assert trend, "لازم ينشر حتى وقت الإحماء"
    last = trend[-1]
    assert last["status"] == "insufficient_data", last["status"]
    # ٢٠٢٦-١٠-٠٧ (عقد الحقائق، ختم المالك «NQ»): «sideways» كلمة جهةٍ نُزعت؛ تبقى الحالة والتحذير وختم العقد.
    assert "signal" not in last, last.get("signal")
    assert last["contract"] == "facts.v1"
    assert "insufficient_candles" in last["warnings"]
    print("OK — الإحماء: insufficient_data بلا كلمة جهة")


async def test_clear_uptrend():
    print("\n--- test_clear_uptrend ---")
    closes = [100 + i for i in range(30)]  # steadily rising
    _atom, _bus, trend = await _run(closes)
    last = trend[-1]
    assert last["status"] == "ok", last
    # ٢٠٢٦-١٠-٠٧ (عقد الحقائق، ختم المالك «NQ»): لا جهة ولا درجة ولا قوّة ولا طور؛ الصعود يُقرأ من الحقيقة الخام.
    for judged in ("signal", "score", "strength", "phase", "confidence", "quality"):
        assert judged not in last, f"حقل حكمٍ ظهر: {judged}"
    md = last["metadata"]
    assert md["ema_fast_value"] > md["ema_slow_value"], md
    assert md["price_position"] == "above_fast"
    assert md["ema_slope"] > 0 and md["ema_distance"] > 0
    print(f"OK — صعود: distance={md['ema_distance']} slope={md['ema_slope']} "
          f"position={md['price_position']}")


async def test_clear_downtrend():
    print("\n--- test_clear_downtrend ---")
    closes = [200 - i for i in range(30)]  # steadily falling
    _atom, _bus, trend = await _run(closes)
    last = trend[-1]
    # ٢٠٢٦-١٠-٠٧ (عقد الحقائق، ختم المالك «NQ»): «down» كلمة جهةٍ نُزعت؛ الهبوط يُقرأ من المتوسّطين والميل.
    assert "signal" not in last, last.get("signal")
    md = last["metadata"]
    assert md["ema_fast_value"] < md["ema_slow_value"], md
    assert md["ema_distance"] < 0
    assert md["ema_slope"] < 0
    assert md["price_position"] == "below_fast"
    print(f"OK — هبوط: distance={md['ema_distance']} slope={md['ema_slope']}")


async def test_chop_is_neutral():
    print("\n--- test_chop_is_neutral ---")
    # tiny oscillation around a flat level → entangled + flat slope → neutral
    base = 100.0
    closes = [base + (0.01 if i % 2 == 0 else -0.01) for i in range(30)]
    _atom, _bus, trend = await _run(closes)
    last = trend[-1]
    # ٢٠٢٦-١٠-٠٧ (عقد الحقائق، ختم المالك «NQ»): لا «sideways» ولا درجة ولا قوّة؛ التذبذب يُقرأ من مسافةٍ وميلٍ دون العتبتين.
    for judged in ("signal", "score", "strength"):
        assert judged not in last, f"حقل حكمٍ ظهر: {judged}"
    md = last["metadata"]
    assert abs(md["ema_distance"]) < CFG["flat_distance_pct"], md["ema_distance"]
    assert abs(md["ema_slope"]) < CFG["flat_slope_pct"], md["ema_slope"]
    print("OK — تذبذب: مسافة وميل دون العتبتين، بلا حكم")


async def test_contract_shape_complete():
    print("\n--- test_contract_shape_complete ---")
    _atom, _bus, trend = await _run([100 + i for i in range(20)])
    last = trend[-1]
    # ٢٠٢٦-١٠-٠٧ (عقد الحقائق، ختم المالك «NQ»): الحقول المطلوبة صارت ختم الحقيقة، وحقول الحكم ممنوعة.
    for field in ("symbol", "id", "cycle_id", "status", "warnings", "metadata",
                  "as_of", "computed_on", "section_id", "atom_id", "contract"):
        assert field in last, f"حقل ناقص بالعقد: {field}"
    for judged in ("signal", "score", "confidence", "strength", "phase", "quality"):
        assert judged not in last, f"حقل حكمٍ ظهر: {judged}"
    for field in ("method", "timeframe", "ema_fast", "ema_slow",
                  "ema_distance", "ema_slope", "price_position",
                  "close", "ema_fast_value", "ema_slow_value", "candles"):
        assert field in last["metadata"], f"حقل metadata ناقص: {field}"
    assert last["id"] == "trend"
    assert last["metadata"]["method"] == "ema_slope"
    assert last["contract"] == "facts.v1"
    assert last["section_id"] == "150" and last["atom_id"] == "151"
    assert last["computed_on"] == last["metadata"]["candles"]
    print("OK — عقد الحقائق كامل الحقول")


async def test_health_states():
    print("\n--- test_health_states ---")
    bus = FakeEventBus()
    atom = Atom()
    await atom.initialize(bus.make_context(dict(CFG)))
    h0 = await atom.health_check()
    assert h0.state == HealthState.UNHEALTHY, "قبل start"
    await atom.start()
    h1 = await atom.health_check()
    assert h1.state == HealthState.DEGRADED, "بعد start بلا شموع"
    await atom._on_candle(_candle(100))
    h2 = await atom.health_check()
    assert h2.state == HealthState.HEALTHY, "بعد وصول شمعة"
    print("OK — الصحة: UNHEALTHY→DEGRADED→HEALTHY")


async def main():
    tests = [
        test_warmup_insufficient,
        test_clear_uptrend,
        test_clear_downtrend,
        test_chop_is_neutral,
        test_contract_shape_complete,
        test_health_states,
        test_candle_memory_survives_restart,
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


async def test_long_frame_trend_is_republished_at_boot():
    """٢٠٢٦-١٠-٠٨ (تدقيق الإغلاق): شمعة الأربع ساعات تُغلق كلّ أربع ساعات — فتُعاد حقيقتها الخام المحفوظة
    (آخر إغلاق والمتوسّطان) عند الإقلاع، كي لا تبقى البطاقة 414 بلا اتّجاهها حتّى الإغلاق التالي."""
    closes = [100 + i for i in range(30)]
    bus = FakeEventBus()
    atom = Atom()
    await atom.initialize(bus.make_context(dict(CFG)))
    await atom.start()
    for c in closes:
        await atom._on_candle(_candle(c, symbol="USTEC", tf="4h"))
    saved = await atom.snapshot()
    revived = Atom()
    bus2 = FakeEventBus()
    await revived.initialize(bus2.make_context(dict(CFG)))
    await revived.restore(saved)
    await revived._republish_restored()          # يُجدوَل بعد الإقلاع بـ30 ث — يُستدعى مباشرة
    out = [p for n, p in bus2.published if n == EVENT_OUT]
    assert len(out) == 1 and out[0]["timeframe"] == "4h", out
    meta = out[0]["metadata"]
    assert meta["restored"] is True and meta["close"] == closes[-1]
    assert abs(meta["ema_slow_value"] - atom._state[("USTEC", "4h")]["ema_slow"]) < 1e-9
