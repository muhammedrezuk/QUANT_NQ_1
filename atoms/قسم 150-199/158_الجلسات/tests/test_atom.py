"""158 — الجلسات بالتوقيت الصيفيّ الصحيح، من الساعة المشتركة نفسها التي تقرؤها 117.

٢٠٢٦-١٠-٠٩ (ختم المالك «NQ» — الوقت من مصدرٍ واحد): كانت الاختبارات تقود ساعاتٍ ثابتة بغرينتش من 1970؛ صارت
تقود لحظاتٍ حقيقيّة صيفًا وشتاءً وعند لحظتَي تبديل الساعة (لندن 2026-10-25 01:00 · نيويورك 2026-11-01 06:00
غرينتش)، وتثبت أنّ 158 و117 تقولان الشيء نفسه في اللحظة نفسها.
"""
import asyncio
import calendar as calendar_mod
import importlib.util as _ilu
import sys
import time
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
from shared import market_clock as mc  # noqa: E402


def _load(name, path):
    spec = _ilu.spec_from_file_location(name, path)
    mod = _ilu.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


_mod = _load("_atom158", FOLDER / "atom.py")
_m117 = _load("_atom117_for158", FOLDER_117 / "atom.py")
Atom = _mod.Atom
EVENT_OUT = _mod.EVENT_OUT
CFG = yaml.safe_load((FOLDER / "manifest.yaml").read_text(encoding="utf-8"))["config"]
SWEEP_STEP_S = 97 * 60          # خطوة أوّليّة مع اليوم (1440) فتمرّ على كلّ دقائقه عبر السنة
SWITCH_SPAN_MIN = 90


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
        return AtomContext(atom_id=158, config=config, logger=_NullLogger(),
                           publish=self.publish, subscribe=self.subscribe)


def _candle(ts, symbol="USTEC", tf="60s"):
    return {"symbol": symbol, "period_start": ts, "timestamp": ts, "timeframe": tf}


async def _emit_at(text, symbol="USTEC"):
    bus = FakeEventBus()
    atom = Atom()
    await atom.initialize(bus.make_context(dict(CFG)))
    await atom.start()
    await atom._on_candle(_candle(utc(text), symbol))
    return [p for n, p in bus.published if n == EVENT_OUT][-1]


async def _signal(text, symbol="USTEC"):
    return (await _emit_at(text, symbol))["signal"]


# ── الصيف والشتاء ───────────────────────────────────────────────────────────
async def test_summer_sessions_on_local_clocks():
    # الأربعاء 2026-07-15 (نيويورك −4 · لندن +1).
    asia = await _emit_at("2026-07-15 00:30")                      # طوكيو 09:30
    assert asia["signal"] == "asia" and asia["metadata"]["active"] == ["asia"]
    assert await _signal("2026-07-15 07:30") == "london"           # لندن 08:30 صيفيّ
    assert await _signal("2026-07-15 12:30") == "london"           # نيويورك 08:30 — كانت «overlap» بغرينتش الثابت
    overlap = await _emit_at("2026-07-15 13:45")                   # نيويورك 09:45 · لندن 14:45
    assert overlap["signal"] == "overlap" and set(overlap["metadata"]["active"]) == {"london", "new_york"}
    assert overlap["metadata"]["cash_open"] is True
    assert await _signal("2026-07-15 15:45") == "new_york"         # لندن أغلقت 16:30 بتوقيتها
    assert await _signal("2026-07-15 20:30") == "nq_globex"        # النقديّ أغلق 16:00 والعقد يتداول
    assert await _signal("2026-07-15 21:30") == "closed"           # استراحة 17:00–18:00 نيويورك


async def test_winter_sessions_shift_by_one_hour():
    # الثلاثاء 2026-12-15 (نيويورك −5 · لندن 0).
    assert await _signal("2026-12-15 07:30") == "nq_globex"        # لندن 07:30 — لم تفتح بعد
    assert await _signal("2026-12-15 08:00") == "london"
    assert await _signal("2026-12-15 14:15") == "london"           # نيويورك 09:15
    assert await _signal("2026-12-15 14:30") == "overlap"          # نيويورك 09:30
    assert await _signal("2026-12-15 16:30") == "new_york"
    assert await _signal("2026-12-15 21:00") == "nq_globex"        # النقديّ أغلق 16:00 شتاءً
    assert await _signal("2026-12-15 22:00") == "closed"           # استراحة 17:00 شتاءً
    assert await _signal("2026-12-15 23:00") == "nq_globex"


# ── لحظتا تبديل الساعة ──────────────────────────────────────────────────────
async def test_london_switch_2026_10_25_0100_utc():
    before, after = await _emit_at("2026-10-25 00:59"), await _emit_at("2026-10-25 01:00")
    assert before["metadata"]["utc_offset_london_h"] == 1 and after["metadata"]["utc_offset_london_h"] == 0
    assert await _signal("2026-10-23 07:30") == "london"           # الجمعة 08:30 صيفيّ
    assert await _signal("2026-10-26 07:30") == "nq_globex"        # الاثنين 07:30 شتويّ — كانت «overlap» (آسيا+لندن)
    assert await _signal("2026-10-26 08:00") == "london"
    # أسبوع اللاتماثل: لندن شتويّة ونيويورك صيفيّة بعد ⟵ التداخل 13:30–16:30 غرينتش (ثلاث ساعات لا ساعتان).
    assert await _signal("2026-10-27 16:15") == "overlap"
    assert await _signal("2026-07-14 16:15") == "new_york"


async def test_new_york_switch_2026_11_01_0600_utc():
    before, after = await _emit_at("2026-11-01 05:59"), await _emit_at("2026-11-01 06:00")
    assert before["metadata"]["utc_offset_new_york_h"] == -4 and after["metadata"]["utc_offset_new_york_h"] == -5
    assert await _signal("2026-10-30 13:30") == "overlap"          # الجمعة 09:30 صيفيّ
    assert await _signal("2026-11-02 13:30") == "london"           # الاثنين 08:30 شتويّ
    assert await _signal("2026-11-02 14:30") == "overlap"
    # إعادة فتح العقد الأحد 18:00 نيويورك = 23:00 غرينتش شتاءً (22:00 صيفًا).
    assert await _signal("2026-11-01 22:30") == "closed" and await _signal("2026-11-01 23:00") == "nq_globex"
    assert await _signal("2026-10-25 22:00") == "nq_globex"


def test_hourly_offset_memo_equals_the_rule_every_minute_around_every_switch_2024_2030():
    # الساعة المشتركة تحفظ فرق كلّ مدينةٍ لكلّ ساعة غرينتش (التحويل على رأس الساعة) — تُقارن هنا بالقاعدة نفسها.
    from shared.owner_windows import london_offset_h, new_york_offset_h
    for year in range(2024, 2031):
        switches = (calendar_mod.timegm(mc.nth_weekday(year, 3, mc.SUNDAY, 2).timetuple()) + 7 * 3600,
                    calendar_mod.timegm(mc.nth_weekday(year, 11, mc.SUNDAY, 1).timetuple()) + 6 * 3600,
                    calendar_mod.timegm(mc.nth_weekday(year, 3, mc.SUNDAY, -1).timetuple()) + 3600,
                    calendar_mod.timegm(mc.nth_weekday(year, 10, mc.SUNDAY, -1).timetuple()) + 3600)
        for switch in switches:
            for minute in range(-SWITCH_SPAN_MIN, SWITCH_SPAN_MIN + 1):
                t = float(switch + minute * 60)
                assert mc.OFFSET_FNS[mc.CITY_NEW_YORK](t) == new_york_offset_h(t), (year, minute)
                assert mc.OFFSET_FNS[mc.CITY_LONDON](t) == london_offset_h(t), (year, minute)


# ── عطلة الأسبوع والسوق · رموز الساعة الدائمة ──────────────────────────────
async def test_weekend_and_market_holidays():
    assert await _signal("2026-10-10 10:00") == "closed"           # السبت — كانت «london» بالساعة وحدها
    thanks = await _emit_at("2026-11-26 15:00")                     # عيد الشكر: البورصة مغلقة ولندن تعمل
    assert thanks["signal"] == "london" and thanks["metadata"]["cash_open"] is False
    assert thanks["metadata"]["trading_calendar_source"] == mc.SOURCE_RULES
    assert await _signal("2026-11-27 18:30") == "nq_globex"        # بعد الإغلاق المبكّر 13:00 نيويورك


async def test_round_clock_and_always_open_symbols():
    assert await _signal("2026-10-10 10:00", "BTCUSD") == "round_clock_24h"
    assert await _signal("2026-07-15 20:30", "XAUUSD") == "open"
    assert await _signal("2026-07-15 07:30", "BTCUSD") == "london"           # الجلسة المسمّاة أوّلًا
    o = await _emit_at("2026-10-10 10:00", "BTCUSD")
    assert "score" not in o and o["metadata"]["active"] == [] and o["metadata"]["hour_utc"] == 10


# ── 158 و117: الشيء نفسه في اللحظة نفسها ───────────────────────────────────
def _instants():
    t, end = utc("2026-01-01 00:00"), utc("2027-01-01 00:00")
    while t < end:
        yield t
        t += SWEEP_STEP_S
    for switch in ("2026-03-08 07:00", "2026-03-29 01:00", "2026-10-25 01:00", "2026-11-01 06:00"):
        for minute in range(-SWITCH_SPAN_MIN, SWITCH_SPAN_MIN + 1):
            yield utc(switch) + minute * 60


def test_parity_with_117_every_instant_of_2026():
    checked = 0
    for ts in _instants():
        _named, facts = _mod.session_facts(ts)
        ref = _m117.build_facts(ts, {})
        for key in ("session_now", "sessions_open", "cash_open", "utc_offset_new_york_h", "utc_offset_london_h",
                    "trading_calendar_source"):
            assert facts[key] == ref[key], (time.strftime("%Y-%m-%d %H:%M", time.gmtime(ts)), key, facts[key], ref[key])
        checked += 1
    assert checked > 5000


def test_with_a_calendar_117_differs_only_on_london_and_tokyo_holidays():
    # تقويم ميتاتريدر تقرؤه 117 وحدها: عطل لندن وطوكيو تُغلق جلستيهما عندها، و158 تمشي على القواعد وتُعلن ذلك.
    cal = {"status": "ok", "rows": {"US": [["2026-11-26", "thanksgiving-day", "عيد الشكر"]],
                                    "GB": [["2026-08-31", "summer-bank-holiday", "x"]],
                                    "JP": [["2026-10-12", "health-and-sports-day", "y"]]}}
    differing_days = set()
    for ts in _instants():
        if _mod.session_facts(ts)[1]["sessions_open"] != _m117.build_facts(ts, cal)["sessions_open"]:
            differing_days.add(time.strftime("%Y-%m-%d", time.gmtime(ts)))
    assert differing_days == {"2026-08-31", "2026-10-12"}, differing_days


# ── العقد والبيان ───────────────────────────────────────────────────────────
async def test_contract_shape_and_no_fixed_hours_in_manifest():
    o = await _emit_at("2026-07-15 13:45")
    for f in ("symbol", "id", "cycle_id", "status", "signal", "warnings", "metadata",
              "as_of", "computed_on", "section_id", "atom_id", "contract"):
        assert f in o, f"حقل ناقص بالعقد: {f}"
    for judged in ("score", "confidence", "quality"):
        assert judged not in o, f"حقل حكمٍ ظهر: {judged}"
    for f in ("method", "hour_utc", "active", "session_now", "sessions_open", "cash_open",
              "utc_offset_new_york_h", "utc_offset_london_h", "trading_calendar_source"):
        assert f in o["metadata"], f"metadata ناقص: {f}"
    assert o["id"] == "session" and o["contract"] == "facts.v1"
    assert o["section_id"] == "150" and o["atom_id"] == "158"
    assert set(CFG) == {"round_clock_symbols", "always_open_symbols"}, CFG


async def test_health_states():
    bus = FakeEventBus()
    atom = Atom()
    await atom.initialize(bus.make_context(dict(CFG)))
    assert (await atom.health_check()).state == HealthState.UNHEALTHY
    await atom.start()
    assert (await atom.health_check()).state == HealthState.DEGRADED
    await atom._on_candle(_candle(utc("2026-07-15 10:00")))
    assert (await atom.health_check()).state == HealthState.HEALTHY


async def test_no_state_to_survive():
    # أول شمعة بعد الإقلاع مباشرة — لا نافذة إحماء هنا أصلًا لتُفقد.
    bus = FakeEventBus()
    atom = Atom()
    await atom.initialize(bus.make_context(dict(CFG)))
    await atom.start()
    await atom._on_candle(_candle(utc("2026-07-15 13:45")))
    out = [p for n, p in bus.published if n == EVENT_OUT][-1]
    assert out["status"] == "ok", out["status"]
    saved = await atom.snapshot()
    assert "live_analysis" in saved, "الغلاف الحيّ لازم يبقى محفوظًا"
    assert "atom" not in saved, "لا حالة خاصة بالذرّة لتُحفظ — كل نتيجة دالّة نقية"


async def main():
    tests = [test_summer_sessions_on_local_clocks, test_winter_sessions_shift_by_one_hour,
             test_london_switch_2026_10_25_0100_utc, test_new_york_switch_2026_11_01_0600_utc,
             test_hourly_offset_memo_equals_the_rule_every_minute_around_every_switch_2024_2030,
             test_weekend_and_market_holidays, test_round_clock_and_always_open_symbols,
             test_parity_with_117_every_instant_of_2026, test_with_a_calendar_117_differs_only_on_london_and_tokyo_holidays,
             test_contract_shape_and_no_fixed_hours_in_manifest, test_health_states, test_no_state_to_survive]
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
