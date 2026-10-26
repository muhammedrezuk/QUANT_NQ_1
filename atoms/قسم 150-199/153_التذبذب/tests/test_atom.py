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
    "_atom153", _Path(__file__).resolve().parents[1] / "atom.py")
_mod = _ilu.module_from_spec(_spec)
sys.modules["_atom153"] = _mod
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

    def subscribe(self, name, handler):
        pass

    async def publish(self, name, payload):
        self.published.append((name, payload))

    def make_context(self, config):
        return AtomContext(atom_id=153, config=config, logger=_NullLogger(),
                           publish=self.publish, subscribe=self.subscribe)


CFG = {"atr_window": 3, "baseline_window": 12, "stddev_window": 5,
       "high_mult": 1.5, "low_mult": 0.6, "min_candles": 8}


def _candle(rng, close=100.0, symbol="NQ100", tf="60s"):
    return {"symbol": symbol, "high": close + rng / 2.0, "low": close - rng / 2.0,
            "close": close, "timeframe": tf, "period_start": 0.0, "timestamp": 0.0}


async def _run(ranges, cfg=None):
    bus = FakeEventBus()
    atom = Atom()
    await atom.initialize(bus.make_context(cfg or dict(CFG)))
    await atom.start()
    for r in ranges:
        await atom._on_candle(_candle(r))
    return atom, bus, [p for n, p in bus.published if n == EVENT_OUT]


async def test_warmup_insufficient():
    print("\n--- test_warmup_insufficient ---")
    _a, _b, out = await _run([1.0, 1.0, 1.0])
    assert out and out[-1]["status"] == "insufficient_data"
    print("OK — الإحماء: insufficient_data")


async def test_high_volatility():
    print("\n--- test_high_volatility ---")
    _a, _b, out = await _run([1.0] * 12 + [5.0] * 3)  # هدوء ثم اتساع
    last = out[-1]
    assert last["status"] == "ok" and last["signal"] == "high", last
    assert last["metadata"]["ratio"] > 1.5
    # ٢٠٢٦-١٠-٠٧ (عقد الحقائق، ختم المالك «NQ»): الدرجة نُزعت؛ يبقى مقدار التذبذب الخامّ نسبةً من السعر.
    assert "score" not in last, f"حقل حكمٍ ظهر: score"
    assert last["metadata"]["atr_pct"] > 0
    print(f"OK — تذبذب عالي: signal={last['signal']} ratio={last['metadata']['ratio']} "
          f"atr_pct={last['metadata']['atr_pct']}")


async def test_low_volatility():
    print("\n--- test_low_volatility ---")
    _a, _b, out = await _run([5.0] * 12 + [0.5] * 3)  # اتساع ثم هدوء
    last = out[-1]
    assert last["signal"] == "low", last["signal"]
    assert last["metadata"]["ratio"] < 0.6
    print(f"OK — تذبذب منخفض: signal={last['signal']} ratio={last['metadata']['ratio']}")


async def test_normal_volatility():
    print("\n--- test_normal_volatility ---")
    _a, _b, out = await _run([2.0] * 15)  # ثابت
    last = out[-1]
    assert last["signal"] == "normal", last["signal"]
    print(f"OK — تذبذب طبيعي: signal={last['signal']} ratio={last['metadata']['ratio']}")


async def test_contract_shape():
    print("\n--- test_contract_shape ---")
    _a, _b, out = await _run([2.0] * 12 + [3.0] * 3)
    last = out[-1]
    # ٢٠٢٦-١٠-٠٧ (عقد الحقائق، ختم المالك «NQ»): الحقول المطلوبة صارت ختم الحقيقة، وحقول الحكم ممنوعة.
    for f in ("symbol", "id", "cycle_id", "status", "signal", "warnings", "metadata",
              "as_of", "computed_on", "section_id", "atom_id", "contract"):
        assert f in last, f"حقل ناقص بالعقد: {f}"
    for judged in ("score", "confidence", "quality"):
        assert judged not in last, f"حقل حكمٍ ظهر: {judged}"
    for f in ("method", "atr", "atr_pct", "baseline_atr", "ratio", "range", "stddev"):
        assert f in last["metadata"], f"metadata ناقص: {f}"
    assert last["id"] == "volatility"
    assert last["contract"] == "facts.v1"
    assert last["section_id"] == "150" and last["atom_id"] == "153"
    print("OK — عقد الحقائق كامل + قياسات ATR/StdDev/Range")


async def test_health_states():
    print("\n--- test_health_states ---")
    bus = FakeEventBus()
    atom = Atom()
    await atom.initialize(bus.make_context(dict(CFG)))
    assert (await atom.health_check()).state == HealthState.UNHEALTHY
    await atom.start()
    assert (await atom.health_check()).state == HealthState.DEGRADED
    await atom._on_candle(_candle(1.0))
    assert (await atom.health_check()).state == HealthState.HEALTHY
    print("OK — الصحة: UNHEALTHY→DEGRADED→HEALTHY")


async def test_state_survives_restart():
    print("\n--- test_state_survives_restart ---")
    ranges = [1.0, 1.2, 0.8, 1.5, 1.0, 1.3, 0.9, 1.1, 1.4, 1.0]
    atom, _bus, out = await _run(ranges)
    assert out[-1]["status"] == "ok", out[-1]["status"]
    key = ("NQ100", "60s")
    before = dict(atom._state[key])
    saved = await atom.snapshot()
    assert "live_analysis" in saved, "الغلاف الحيّ لازم يبقى محفوظًا"
    assert "atom" in saved, "المدى الحقيقي وسلسلة الإغلاقات لازم تُحفظ بجانبه — لا تُدهَس"

    revived = Atom()
    bus2 = FakeEventBus()
    await revived.initialize(bus2.make_context(dict(CFG)))
    await revived.restore(saved)
    await revived.start()
    after = revived._state[key]
    assert list(after["tr"]) == list(before["tr"])
    assert list(after["closes"]) == list(before["closes"])
    assert after["prev_close"] == before["prev_close"]
    assert revived._candles_seen == atom._candles_seen

    await revived._on_candle(_candle(1.0))
    fresh = [p for n, p in bus2.published if n == EVENT_OUT]
    assert fresh and fresh[-1]["status"] != "insufficient_data", fresh[-1]["status"]
    print(f"OK — تاريخ التذبذب نجا الإقلاع: tr={len(after['tr'])} بلا إحماء جديد")


async def main():
    tests = [test_warmup_insufficient, test_high_volatility, test_low_volatility,
             test_normal_volatility, test_contract_shape, test_health_states,
             test_state_survives_restart]
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


def test_fixed_window_atr_14_is_published_untouched_by_the_speed_key():
    """٢٠٢٦-١٠-٠٨ (تدقيق الإغلاق — «الحيّ = المقيس»): البطاقة 414 قيست على متوسّط مدى 14 شمعة، فتُنشر
    حقيقةٌ مسمّاة بنافذتها الثابتة `atr_14`.

    ٢٠٢٦-١٠-٠٩ (ختم المالك «NQ» — إلغاء مفاتيح السرعة إلى الأرشيف): مفتاح السرعة نفسه خرج من الذرّة، فنافذة
    `atr` هي رقم المانيفست حرفيًّا (16) — لا 21 — و`atr_14` كما كان."""
    assert not hasattr(_mod, "speed_factor") and not hasattr(_mod, "_speed_window")
    bus = FakeEventBus()
    atom = Atom()
    asyncio.run(atom.initialize(bus.make_context({"atr_window": 16, "baseline_window": 32, "stddev_window": 20,
                                                  "high_mult": 1.35, "low_mult": 0.7, "min_candles": 16})))
    asyncio.run(atom.start())
    ranges = [10.0 + 0.5 * i for i in range(40)]          # متزايدة: متوسّط 14 ≠ متوسّط 21
    for i, r in enumerate(ranges):                       # الإغلاق في المنتصف: المدى الحقيقيّ = العالي − المنخفض
        asyncio.run(atom._on_candle({"symbol": "NQ", "timeframe": "5m", "period_start": float(i * 300),
                                     "open": 100.0, "high": 100.0 + r / 2, "low": 100.0 - r / 2, "close": 100.0}))
    meta = [p for n, p in bus.published if n == EVENT_OUT][-1]["metadata"]
    assert abs(meta["atr_14"] - sum(ranges[-14:]) / 14) < 1e-4, meta
    assert abs(meta["atr"] - sum(ranges[-16:]) / 16) < 1e-4, meta   # نافذة المانيفست 16 حرفيًّا
    assert abs(meta["baseline_atr"] - sum(ranges[-32:]) / 32) < 1e-4, meta


def test_long_frame_facts_are_republished_at_boot_from_the_saved_history():
    """٢٠٢٦-١٠-٠٨ (تدقيق الإغلاق): شمعة اليوم تُغلق مرّةً في اليوم — فيُعاد عند الإقلاع نشر `atr_14` المحفوظ
    لليوم والأربع ساعات، كي لا تبقى البطاقة 414 بلا «مدى اليوم» نافذتَي يومٍ كامل."""
    cfg = {"atr_window": 16, "baseline_window": 32, "stddev_window": 20, "high_mult": 1.35,
           "low_mult": 0.7, "min_candles": 16}
    bus = FakeEventBus()
    atom = Atom()
    asyncio.run(atom.initialize(bus.make_context(cfg)))
    asyncio.run(atom.start())
    for i in range(20):
        r = 300.0 + i
        asyncio.run(atom._on_candle({"symbol": "USTEC", "timeframe": "1d", "period_start": float(i * 86400),
                                     "open": 30000.0, "high": 30000.0 + r / 2, "low": 30000.0 - r / 2,
                                     "close": 30000.0}))
    state = asyncio.run(atom.snapshot())
    bus2 = FakeEventBus()
    fresh = Atom()
    asyncio.run(fresh.initialize(bus2.make_context(cfg)))
    asyncio.run(fresh.restore(state))
    asyncio.run(fresh._republish_restored())     # يُجدوَل بعد الإقلاع بـ30 ث — يُستدعى مباشرة
    out = [p for n, p in bus2.published if n == EVENT_OUT]
    assert len(out) == 1 and out[0]["timeframe"] == "1d" and out[0]["metadata"]["restored"] is True
    assert abs(out[0]["metadata"]["atr_14"] - sum(300.0 + i for i in range(6, 20)) / 14) < 1e-4


def test_short_daily_history_is_seeded_from_the_history_db(tmp_path, monkeypatch):
    """٢٠٢٦-١٠-٠٨ (تدقيق الإغلاق): تاريخ يومٍ أقصر من 14 يُبذر من قاعدة التاريخ (شموع يوم الوسيط المكتملة)،
    ويُسقط آخرها — فيصير «مدى اليوم على 14» حاضرًا بعد الإقلاع كما قيست البطاقة."""
    import sqlite3 as _sql
    db = tmp_path / "hist.db"
    con = _sql.connect(db)
    con.execute("CREATE TABLE candles_history (symbol TEXT, period TEXT, period_start INTEGER, "
                "open REAL, high REAL, low REAL, close REAL)")
    import time as _time
    base = int(_time.time() // 86400) * 86400 - 29 * 86400     # الشمعة 29 = اليوم الجاري (غير مكتملة)
    for i in range(30):
        con.execute("INSERT INTO candles_history VALUES ('USTEC','D1',?,?,?,?,?)",
                    (base + i * 86400, 30000.0, 30000.0 + (200 + i) / 2, 30000.0 - (200 + i) / 2, 30000.0))
    con.commit(); con.close()
    monkeypatch.setenv("QUANT_HISTORY_DB", str(db))
    monkeypatch.delenv("QUANT_REPLAY_NO_WARM", raising=False)
    cfg = {"atr_window": 16, "baseline_window": 32, "stddev_window": 20, "high_mult": 1.35,
           "low_mult": 0.7, "min_candles": 16}
    bus = FakeEventBus()
    atom = Atom()
    asyncio.run(atom.initialize(bus.make_context(cfg)))
    atom._state[("USTEC", "1d")] = {"tr": _mod.deque([1.0] * 8), "closes": _mod.deque([30000.0] * 8),
                                    "prev_close": 30000.0}
    assert atom._seed_daily_from_history() == 1
    asyncio.run(atom._republish_restored())
    meta = [p for n, p in bus.published if n == EVENT_OUT][-1]["metadata"]
    # الشموع 0..28 (الأخيرة 29 أُسقطت) ⟸ آخر 14 مدى: 215..228
    assert abs(meta["atr_14"] - sum(200 + i for i in range(15, 29)) / 14) < 1e-4, meta
