"""159 — موضع الشمعة على يوم الوسيط وأيّام التداول، من الساعة المشتركة نفسها التي تقرؤها 117.

٢٠٢٦-١٠-٠٩ (ختم المالك «NQ» — الوقت من مصدرٍ واحد): كانت الاختبارات تقود منتصف ليل غرينتش (2024) والاثنين
والجمعة من البيان؛ صارت تقود شموعًا حقيقيّة كما يبنيها 103 (شمعة اليوم تبدأ 17:00 نيويورك من اليوم السابق)، وتثبت
أنّ يوم الوسيط هنا هو يوم الوسيط في 117، وأنّ موضع الشهر يطابق 117 ما دام يوم نيويورك هو يوم الوسيط.
"""
import asyncio
import calendar as calendar_mod
import importlib.util as _ilu
import sys
import time
from datetime import date, timedelta
from pathlib import Path as _Path

import yaml

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

ROOT = _Path(__file__).resolve().parents[4]
FOLDER = _Path(__file__).resolve().parents[1]
FOLDER_117 = next((ROOT / "atoms").glob("*/117_*"))
for _path in (str(ROOT), str(FOLDER), str(FOLDER_117)):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from core.contracts.atom import AtomContext, HealthState  # noqa: E402


def _load(name, path):
    spec = _ilu.spec_from_file_location(name, path)
    mod = _ilu.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


_mod = _load("_atom159", FOLDER / "atom.py")
_m117 = _load("_atom117_for159", FOLDER_117 / "atom.py")
_m103 = _load("_atom103_for159", next((ROOT / "atoms").glob("*/103_*")) / "atom.py")
Atom = _mod.Atom
EVENT_OUT = _mod.EVENT_OUT
CFG = yaml.safe_load((FOLDER / "manifest.yaml").read_text(encoding="utf-8"))["config"] or {}
SWEEP_STEP_S = 97 * 60          # خطوة أوّليّة مع اليوم (1440) فتمرّ على كلّ دقائقه عبر السنة
DAY_S = 86400.0


def utc(text):
    return float(calendar_mod.timegm(time.strptime(text, "%Y-%m-%d %H:%M")))


class _NullLogger:
    def __getattr__(self, _name):
        return lambda *a, **k: None


class FakeEventBus:
    def __init__(self):
        self.published = []

    def subscribe(self, name, handler):
        pass

    async def publish(self, name, payload):
        self.published.append((name, payload))

    def make_context(self, config):
        return AtomContext(atom_id=159, config=config, logger=_NullLogger(),
                           publish=self.publish, subscribe=self.subscribe)


def _candle(ts, symbol="USTEC", tf="60s"):
    return {"symbol": symbol, "period_start": ts, "timestamp": ts, "timeframe": tf}


async def _emit_ts(ts, tf="60s"):
    bus = FakeEventBus()
    atom = Atom()
    await atom.initialize(bus.make_context(dict(CFG)))
    await atom.start()
    await atom._on_candle(_candle(ts, tf=tf))
    return [p for n, p in bus.published if n == EVENT_OUT][-1]


async def _emit(text):
    return await _emit_ts(utc(text))


# ── يوم الوسيط ──────────────────────────────────────────────────────────────
async def test_daily_candle_of_monday_is_monday_not_sunday():
    # شمعة اليوم كما يبنيها 103: تبدأ الأحد 21:00 غرينتش صيفًا (22:00 شتاءً) — بغرينتش كانت «weekend».
    for during, monday in (("2026-10-12 15:00", "2026-10-12"), ("2026-12-14 15:00", "2026-12-14")):
        start = _m103.frame_period_start(utc(during), DAY_S)
        o = await _emit_ts(start, tf="1d")
        md = o["metadata"]
        assert time.gmtime(start).tm_wday == 6, "تبدأ الأحد بغرينتش"
        assert md["broker_day_date"] == monday and md["weekday_name"] == "monday" and md["hour"] == 0, md
        assert o["signal"] == "week_open"


async def test_evening_after_new_york_close_belongs_to_the_next_trade_date():
    # الخميس 2026-10-08 22:32 غرينتش = 18:32 نيويورك ⟵ يوم الوسيط الجمعة 01:32 (117 تقول الشيء نفسه).
    o = await _emit("2026-10-08 22:32")
    ref = _m117.build_facts(utc("2026-10-08 22:32"), {})
    assert o["metadata"]["broker_day_date"] == ref["broker_day_date"] == "2026-10-09"
    assert o["metadata"]["weekday_name"] == "friday" and o["signal"] == "week_close" and o["metadata"]["hour"] == 1
    assert ref["day_of_week"] == "Thursday" and ref["new_york_date"] == "2026-10-08"     # يوم نيويورك حقيقةٌ أخرى باسمها
    assert (await _emit("2026-10-09 21:30"))["signal"] == "weekend"      # الجمعة 17:30 نيويورك: السوق أغلق للعطلة
    sunday = await _emit("2026-10-11 22:30")                              # الأحد 18:30 نيويورك: أوّل الاثنين
    assert sunday["signal"] == "week_open" and sunday["metadata"]["weekday_name"] == "monday"


# ── الأسبوع والشهر بأيّام التداول ──────────────────────────────────────────
async def test_week_phase_follows_trading_days():
    assert (await _emit("2026-09-07 15:00"))["signal"] == "market_holiday"   # عيد العمال (الاثنين)
    assert (await _emit("2026-09-08 15:00"))["signal"] == "week_open"        # الثلاثاء أوّل يوم تداول
    assert (await _emit("2026-04-02 15:00"))["signal"] == "week_close"       # الخميس قبل الجمعة العظيمة
    assert (await _emit("2026-04-03 15:00"))["signal"] == "market_holiday"
    assert (await _emit("2026-10-14 15:00"))["signal"] == "mid_week"
    assert (await _emit("2026-10-10 12:00"))["signal"] == "weekend"
    assert (await _emit("2026-10-12 15:00"))["signal"] == "week_open"        # كولومبوس: عطلة مصارف والبورصة تعمل


async def test_month_and_quarter_ends_are_trading_days():
    may = (await _emit("2026-05-29 15:00"))["metadata"]                     # الجمعة — 30 و31 عطلة أسبوع
    assert may["is_month_end"] is True and may["day_of_month"] == 29
    june = (await _emit("2026-06-30 15:00"))["metadata"]
    assert june["is_month_end"] and june["is_quarter_end"] and june["quarter"] == 2
    rolled = (await _emit("2026-06-30 21:30"))["metadata"]                  # 17:30 نيويورك ⟵ يوم الوسيط 1 تمّوز
    assert rolled["is_month_start"] and rolled["month"] == 7 and rolled["quarter"] == 3
    jan = (await _emit("2026-01-02 15:00"))["metadata"]                     # 1 كانون الثاني عطلة
    assert jan["is_month_start"] is True and (await _emit("2026-01-01 15:00"))["signal"] == "market_holiday"


# ── 159 و117: يوم الوسيط نفسه، وموضع الشهر نفسه ما دام يوم نيويورك هو يوم الوسيط ──
def test_parity_with_117_across_2026():
    t, end, checked = utc("2026-01-01 00:00"), utc("2027-01-01 00:00"), 0
    while t < end:
        _phase, facts = _mod.time_facts(t)
        ref = _m117.build_facts(t, {})
        stamp = time.strftime("%Y-%m-%d %H:%M", time.gmtime(t))
        assert facts["broker_day_date"] == ref["broker_day_date"], stamp
        if ref["new_york_time"] < "17:00":
            assert facts["broker_day_date"] == ref["new_york_date"], stamp
            assert facts["weekday_name"] == ref["day_of_week"].lower(), stamp
            for key in ("is_month_start", "is_month_end", "is_quarter_end", "is_trading_day"):
                assert facts[key] == ref[key], (stamp, key)
        else:
            nxt = date.fromisoformat(ref["new_york_date"]) + timedelta(days=1)
            assert facts["broker_day_date"] == nxt.isoformat(), stamp
        checked += 1
        t += SWEEP_STEP_S
    assert checked > 5000


# ── العقد والبيان ───────────────────────────────────────────────────────────
async def test_contract_shape_and_no_numbers_in_manifest():
    o = await _emit("2026-10-14 15:00")
    for f in ("symbol", "id", "cycle_id", "status", "signal", "warnings", "metadata",
              "as_of", "computed_on", "section_id", "atom_id", "contract"):
        assert f in o, f"حقل ناقص بالعقد: {f}"
    for judged in ("score", "confidence", "quality"):
        assert judged not in o, f"حقل حكمٍ ظهر: {judged}"
    for f in ("method", "hour", "weekday", "weekday_name", "month", "quarter", "day_of_month",
              "is_month_start", "is_month_end", "is_quarter_end", "broker_day_date", "is_trading_day"):
        assert f in o["metadata"], f"metadata ناقص: {f}"
    assert o["id"] == "time" and o["contract"] == "facts.v1"
    assert o["section_id"] == "150" and o["atom_id"] == "159"
    assert CFG == {}, CFG


async def test_missing_timestamp_is_insufficient():
    bus = FakeEventBus()
    atom = Atom()
    await atom.initialize(bus.make_context(dict(CFG)))
    await atom.start()
    await atom._on_candle({"symbol": "USTEC", "timeframe": "60s"})
    out = [p for n, p in bus.published if n == EVENT_OUT][-1]
    assert out["status"] == "insufficient_data" and out["warnings"] == ["no_timestamp"]


async def test_health_states():
    bus = FakeEventBus()
    atom = Atom()
    await atom.initialize(bus.make_context(dict(CFG)))
    assert (await atom.health_check()).state == HealthState.UNHEALTHY
    await atom.start()
    assert (await atom.health_check()).state == HealthState.DEGRADED
    await atom._on_candle(_candle(utc("2026-10-14 15:00")))
    assert (await atom.health_check()).state == HealthState.HEALTHY


async def test_no_state_to_survive():
    # أول شمعة بعد الإقلاع مباشرة — لا نافذة إحماء هنا أصلًا لتُفقد.
    bus = FakeEventBus()
    atom = Atom()
    await atom.initialize(bus.make_context(dict(CFG)))
    await atom.start()
    await atom._on_candle(_candle(utc("2026-10-14 15:00")))
    out = [p for n, p in bus.published if n == EVENT_OUT][-1]
    assert out["status"] == "ok", out["status"]
    saved = await atom.snapshot()
    assert "live_analysis" in saved, "الغلاف الحيّ لازم يبقى محفوظًا"
    assert "atom" not in saved, "لا حالة خاصة بالذرّة لتُحفظ — كل نتيجة دالّة نقية"


async def main():
    tests = [test_daily_candle_of_monday_is_monday_not_sunday,
             test_evening_after_new_york_close_belongs_to_the_next_trade_date,
             test_week_phase_follows_trading_days, test_month_and_quarter_ends_are_trading_days,
             test_parity_with_117_across_2026, test_contract_shape_and_no_numbers_in_manifest,
             test_missing_timestamp_is_insufficient, test_health_states, test_no_state_to_survive]
    failed = []
    for t in tests:
        try:
            result = t()
            if asyncio.iscoroutine(result):
                await result
            print("OK —", t.__name__)
        except Exception as e:  # noqa: BLE001
            failed.append((t.__name__, repr(e)))
            print(f"FAILED: {t.__name__}: {e!r}")
    print("\n" + "=" * 60)
    if failed:
        print(f"فشل {len(failed)} من أصل {len(tests)}")
        sys.exit(1)
    print(f"نجح كل الاختبارات ({len(tests)}/{len(tests)})")


if __name__ == "__main__":
    asyncio.run(main())
