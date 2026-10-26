"""ذاكرة الناسداك الموسميّة 119 — كلّ حقيقة بأرقامٍ معروفة على قواعد مؤقّتة (لا القاعدة الحيّة).

٢٠٢٦-١٠-٠٨ (ختم المالك «NQ» — المعرفة أوّلًا): المتوسّط والوسيط ونسبة الموجب وn · الأيّام الخاصّة ·
اليوم الجاري لا يدخل إحصاءه · قاعدةٌ غائبة أو تالفة لا تكسر · الحمولة بلا حقلٍ ممنوع · الحفظ والاستعادة.
"""
import calendar
import importlib.util
import sqlite3
import statistics
import sys
import time
from datetime import date, timedelta
from pathlib import Path

import pytest

from core.contracts.atom import AtomContext, HealthState
from tests.learning_test_support import Bus, Logger

ATOM_DIR = Path(__file__).resolve().parents[1]
if str(ATOM_DIR) not in sys.path:
    sys.path.insert(0, str(ATOM_DIR))
import seasonal_facts as sf  # noqa: E402
import seasonal_memory as sm  # noqa: E402

SYM = "USTEC"
SCHEMA = ("CREATE TABLE candles_history (symbol TEXT NOT NULL, period TEXT NOT NULL, period_seconds INTEGER NOT NULL, "
          "period_start INTEGER NOT NULL, open REAL NOT NULL, high REAL NOT NULL, low REAL NOT NULL, "
          "close REAL NOT NULL, tick_volume INTEGER NOT NULL, PRIMARY KEY (symbol, period, period_start)) WITHOUT ROWID")
CAL_SCHEMA = ("CREATE TABLE calendar_history (value_id INTEGER PRIMARY KEY, event_code TEXT, event_name TEXT, "
              "country_code TEXT, sector INTEGER, importance INTEGER, time_server INTEGER)")
FORBIDDEN = ("direction", "signal", "strength", "confidence", "weight", "score", "probability", "threshold",
             "depth", "readiness", "buy", "sell", "bullish", "bearish", "strong", "weak")
PATTERN = (0.3, -0.2, 0.5, -0.4, 0.1)          # عائد كلّ يومٍ بحسب يومه من الأسبوع


def _ts(text):
    return calendar.timegm(time.strptime(text, "%Y-%m-%d %H:%M"))


def _start(day):
    """بداية يوم الوسيط لتاريخٍ (17:00 نيويورك من اليوم السابق)."""
    midnight = calendar.timegm(day.timetuple())
    start = midnight - sm.broker_day_offset_s(midnight)
    assert sm.broker_date(start) == day
    return start


def _days(spec, first_close=100.0):
    """spec: [(تاريخ، عائد٪، مدى٪)] بالترتيب؛ الأوّل بذرة. العائد None ⟸ شمعة «عطلة أسبوع» إغلاقها 1.0."""
    rows, prev = [], first_close
    for iso, ret, rng in spec:
        start = _start(date.fromisoformat(iso))
        if ret is None:
            rows.append((start, prev, prev, prev, 1.0))
            continue
        close = prev * (1 + ret / 100)
        rows.append((start, prev, prev * (1 + rng / 200), prev * (1 - rng / 200), close))
        prev = close
    return rows


def _hour(utc, opened, move, rng):
    return (_ts(utc), opened, opened * (1 + rng / 200), opened * (1 - rng / 200), opened * (1 + move / 100))


def _write_history(path, days, hours=()):
    con = sqlite3.connect(path)
    con.execute(SCHEMA)
    con.executemany("INSERT INTO candles_history VALUES (?,?,?,?,?,?,?,?,?)",
                    [(SYM, "D1", 86400, *row, 100) for row in days] + [(SYM, "H1", 3600, *row, 10) for row in hours])
    con.commit()
    con.close()
    return str(path)


def _write_calendar(path, rows):
    con = sqlite3.connect(path)
    con.execute(CAL_SCHEMA)
    con.executemany("INSERT INTO calendar_history (event_code, event_name, country_code, sector, importance, "
                    "time_server) VALUES (?,?,?,?,?,?)", rows)
    con.commit()
    con.close()
    return str(path)


def _weekdays(first, last, skip=()):
    out, day = [], date.fromisoformat(first)
    while day <= date.fromisoformat(last):
        if day.weekday() < 5 and day.isoformat() not in skip:
            out.append(day)
        day += timedelta(days=1)
    return out


def _pattern_spec(days, overrides=None):
    overrides = overrides or {}
    return [(d.isoformat(), 0.0 if i == 0 else overrides.get(d.isoformat(), PATTERN[d.weekday()]),
             1.0 + d.weekday() / 10) for i, d in enumerate(days)]


def _holiday(iso, code, name="عطلة", country="US"):
    return (code, name, country, 12, 0, sm.cal_server(_ts(iso + " 00:00")))


def _fomc(utc, country="US"):
    return ("rate", "قرار سعر فائدة", country, 5, 3, sm.cal_server(_ts(utc)))


def _calendar_rows():
    return [("start", "بداية", "US", 1, 1, sm.cal_server(_ts("2024-12-01 12:00"))),
            _holiday("2025-01-01", "new-years"), _holiday("2025-06-19", "juneteenth", "يوم جونتينث"),
            _holiday("2025-05-01", "may-day", "عيد العمّال الأوروبيّ", country="EU"),
            _fomc("2025-06-18 18:00"), _fomc("2025-06-05 12:15", country="EU"),
            ("end", "نهاية", "US", 1, 1, sm.cal_server(_ts("2025-07-15 12:00")))]


def _load_module():
    spec = importlib.util.spec_from_file_location("seasonal_atom_119_under_test", ATOM_DIR / "atom.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


async def _atom(config, clock):
    module = _load_module()
    bus = Bus()
    atom = module.Atom()
    atom._clock = lambda: clock
    await atom.initialize(AtomContext(119, {"boot_delay_s": 0, **config}, Logger(), bus.publish, bus.subscribe))
    return module, atom, bus


async def _boot(atom):
    await atom.start()
    task = atom._tasks.get("boot")
    if task is not None:
        await task


# ── اليوم من الأسبوع: الأرقام · عطلة الأسبوع · لا نظر إلى المستقبل ──────────────
WEEK_SPEC = [("2025-05-29", 0.0, 1.0), ("2025-05-30", 0.5, 1.0),
             ("2025-06-02", 1.0, 2.0), ("2025-06-03", -0.5, 1.5), ("2025-06-04", 0.0, 1.0),
             ("2025-06-05", 1.0, 2.0), ("2025-06-06", -1.0, 1.0),
             ("2025-06-07", None, None), ("2025-06-08", None, None),        # «سبت» و«أحد» بإغلاقٍ شاذّ
             ("2025-06-09", 0.5, 1.2), ("2025-06-10", 0.2, 1.0), ("2025-06-11", -0.3, 1.0),
             ("2025-06-12", -2.0, 3.0), ("2025-06-13", 0.4, 1.0),
             ("2025-06-16", 0.6, 1.0), ("2025-06-17", 0.1, 1.0), ("2025-06-18", 0.2, 1.0),
             ("2025-06-19", 3.0, 4.0), ("2025-06-20", -0.1, 1.0),
             ("2025-06-23", 50.0, 60.0), ("2025-06-24", 50.0, 60.0)]          # اليوم الجاري وما بعده
NOW = _ts("2025-06-23 15:30")                  # الاثنين، يوم الوسيط بدأ الأحد 21:00 غرينتش
PAST_HOURS = [_hour("2025-06-16 14:00", 100.0, 0.5, 0.8), _hour("2025-06-17 14:00", 100.0, -1.5, 2.0),
              _hour("2025-06-17 07:00", 100.0, 0.1, 0.2), _hour("2025-06-18 07:00", 100.0, 0.1, 0.2)]
TODAY_HOURS = [(_ts("2025-06-22 22:00"), 100.0, 100.5, 99.8, 100.1), (_ts("2025-06-23 03:00"), 100.2, 101.0, 100.0, 100.4),
               (_ts("2025-06-23 14:00"), 100.4, 100.6, 99.5, 100.0), (_ts("2025-06-23 15:00"), 100.0, 110.0, 90.0, 100.0)]


def test_weekday_stats_exact_and_current_day_excluded(tmp_path):
    db = _write_history(tmp_path / "h.db", _days(WEEK_SPEC), PAST_HOURS + TODAY_HOURS)
    memory = sm.build_memory(db, "", SYM, None, 3, NOW)
    assert memory["status"] == "ok" and memory["calendar"]["available"] is False
    thursday = memory["weekday_all"][3]
    assert thursday["n"] == 3
    assert thursday["mean_pct"] == pytest.approx((1.0 - 2.0 + 3.0) / 3, abs=1e-3)
    assert thursday["median_pct"] == pytest.approx(1.0, abs=1e-3)
    assert thursday["pos_pct"] == pytest.approx(66.7)
    assert thursday["range_pct"] == pytest.approx(3.0, abs=1e-3)
    # الأربعاء 0.0 و−0.3 و+0.2: الصفر ليس موجبًا — نسبة الموجب 1 من 3، والوسيط 0.
    wednesday = memory["weekday_all"][2]
    assert wednesday["pos_pct"] == pytest.approx(33.3) and wednesday["n"] == 3
    assert wednesday["median_pct"] == pytest.approx(0.0, abs=1e-3)
    # «السبت» و«الأحد» لا يدخلان ولا يقطعان السلسلة: عائد الاثنين 06-09 من إغلاق الجمعة لا من 1.0.
    assert set(memory["weekday_all"]) == {0, 1, 2, 3, 4}
    monday = memory["weekday_all"][0]
    assert monday["n"] == 3 and monday["mean_pct"] == pytest.approx((1.0 + 0.5 + 0.6) / 3, abs=1e-3)
    # اليوم الجاري (+50٪) وما بعده لا يدخلان؛ آخر يومٍ في الذاكرة الجمعة 06-20.
    assert memory["history_through"] == date(2025, 6, 20) and memory["days_n"] == 16   # 05-30 + ثلاثة أسابيع
    # الساعة: الجارية لا تدخل (شمعة 06-23 14:00 من اليوم الجاري خارج الذاكرة).
    ten = memory["hour"][10]
    assert ten["n"] == 2 and ten["mean_pct"] == pytest.approx(-0.5, abs=1e-3)
    assert ten["median_pct"] == pytest.approx(-0.5, abs=1e-3) and ten["pos_pct"] == pytest.approx(50.0)
    assert ten["abs_move_pct"] == pytest.approx(1.0, abs=1e-3) and ten["range_pct"] == pytest.approx(1.4, abs=1e-3)
    assert ten["rank_by_abs_move"] == 1 and memory["hour"][3]["rank_by_abs_move"] == 2


def test_recent_window_and_facts_at_moment(tmp_path):
    db = _write_history(tmp_path / "h.db", _days(WEEK_SPEC), PAST_HOURS + TODAY_HOURS)
    memory = sm.build_memory(db, "", SYM, None, 3, NOW)
    # الساعة 10:30 نيويورك (14:30 غرينتش): شمعتا اليوم المغلقتان قبلها وحدهما.
    moment = _ts("2025-06-23 14:30")
    facts, summary, status = sf.facts_at(memory, moment, sm.today_range(db, SYM, moment))
    assert status == "ok" and facts["weekday"] == "Monday" and facts["hour_ny"] == 10
    assert facts["hour_abs_move_pct"] == pytest.approx(1.0, abs=1e-3) and facts["hour"]["rank_by_abs_move"] == 1
    assert facts["day_so_far"]["hours"] == 2
    assert facts["day_so_far"]["range_pct"] == pytest.approx((101.0 - 99.8) / 100.0 * 100, abs=1e-3)
    monday_range = memory["weekday_all"][0]["range_pct"]
    assert facts["day_range_ratio"] == pytest.approx(1.2 / monday_range, abs=1e-3)
    assert "أكبر ساعات اليوم حركة" in summary and "الاثنين تاريخيًّا" in summary
    # 15:30: ثلاث شمعات مغلقة، والجارية (15:00، مداها 20٪) لا تدخل.
    later = sm.today_range(db, SYM, NOW)
    assert later["hours"] == 3 and later["range_pct"] == pytest.approx(1.5, abs=1e-3)
    assert later["last_bar_start"] == _ts("2025-06-23 14:00")


def test_month_returns_complete_months_only(tmp_path):
    days = _weekdays("2025-03-28", "2025-06-27")
    db = _write_history(tmp_path / "h.db", _days(_pattern_spec(days)))
    memory = sm.build_memory(db, "", SYM, None, 3, _ts("2025-06-30 15:00"))
    def expected(month):
        product = 1.0
        for d in days[1:]:
            if d.month == month:
                product *= 1 + PATTERN[d.weekday()] / 100
        return (product - 1) * 100
    assert memory["month"][4]["return"]["n"] == 1
    assert memory["month"][4]["return"]["mean_pct"] == pytest.approx(expected(4), abs=1e-3)
    assert memory["month"][5]["return"]["mean_pct"] == pytest.approx(expected(5), abs=1e-3)
    assert memory["month"][6]["return"]["n"] == 0            # حزيران لم يكتمل
    assert memory["month"][3]["return"]["n"] == 0            # آذار بلا شباط قبله
    june_days = [d for d in days[1:] if d.month == 6]
    assert memory["month"][6]["days_n"] == len(june_days)
    assert memory["month"][6]["daily_range_pct"] == pytest.approx(
        statistics.mean(1.0 + d.weekday() / 10 for d in june_days), abs=1e-3)
    # آخر 3 سنوات = كلّ هذا التاريخ هنا، وآخر سنةٍ واحدة كذلك؛ والحدّ تاريخ.
    assert memory["recent_from"] == date(2022, 6, 30)


# ── الأيّام الخاصّة ─────────────────────────────────────────────────────
def _special_memory(tmp_path, moment):
    days = _weekdays("2024-12-27", "2025-06-27", skip=("2025-01-01",))
    spec = _pattern_spec(days, {"2025-06-18": 2.5, "2025-06-19": -0.7, "2025-06-20": 1.1})
    db = _write_history(tmp_path / "h.db", _days(spec))
    cal = _write_calendar(tmp_path / "c.db", _calendar_rows())
    return sm.build_memory(db, cal, SYM, None, 3, moment), days, db


def test_special_kinds_against_normal(tmp_path):
    memory, days, _ = _special_memory(tmp_path, _ts("2025-06-30 15:00"))
    cal = memory["calendar"]
    assert cal["available"] and cal["closed_codes"] == ["new-years"]        # بلا شمعة ⟸ مغلقة (مقيس)
    assert set(cal["holidays"]) == {date(2025, 1, 1), date(2025, 6, 19)}    # عطلة أوروبا لا تدخل
    assert cal["fomc"] == {date(2025, 6, 18)}                               # قرار أوروبا لا يدخل
    kinds = memory["special"]["by_kind"]
    assert kinds["fomc"]["n"] == 1 and kinds["fomc"]["mean_pct"] == pytest.approx(2.5, abs=1e-3)
    assert kinds["holiday"]["n"] == 1 and kinds["holiday"]["mean_pct"] == pytest.approx(-0.7, abs=1e-3)
    assert kinds["pre_holiday"]["n"] == 2                                   # 12-31 و06-18
    assert kinds["post_holiday"]["n"] == 2                                  # 01-02 و06-20
    assert kinds["opex"]["n"] == 6                                          # الجمعة الثالثة كانون الثاني ⟵ حزيران
    assert kinds["month_start"]["n"] == 6 and kinds["month_end"]["n"] == 6  # حزيران لم يُغلق آخره
    special = {date(2024, 12, 31), date(2025, 1, 2), date(2025, 6, 18), date(2025, 6, 19), date(2025, 6, 20)}
    for month in range(1, 7):
        month_days = [d for d in days[1:] if d.month == month]
        special |= {month_days[0]} | ({month_days[-1]} if month < 6 else set())
        special |= {d for d in month_days if d.weekday() == 4 and 15 <= d.day <= 21}
    normal = [d for d in days[1:] if d not in special]
    assert memory["special"]["normal"]["n"] == len(normal)
    assert memory["special"]["normal"]["mean_pct"] == pytest.approx(
        statistics.mean(PATTERN[d.weekday()] for d in normal), abs=1e-3)


@pytest.mark.parametrize("moment, expected", [
    ("2025-06-18 15:00", "pre_holiday+fomc"),
    ("2025-06-20 15:00", "post_holiday+opex"),
    ("2025-01-02 15:00", "post_holiday+month_start"),     # رأس السنة مغلق ⟸ أوّل يوم تداول في كانون الثاني
    ("2024-12-31 15:00", "pre_holiday+month_end"),
    ("2025-06-11 15:00", "none"),
])
def test_today_special_day(tmp_path, moment, expected):
    memory, _, db = _special_memory(tmp_path, _ts(moment))
    facts, summary, status = sf.facts_at(memory, _ts(moment), sm.today_range(db, SYM, _ts(moment)))
    assert status == "ok" and facts["special_day"] == expected
    if expected == "none":
        assert "اليوم ليس يومًا خاصًّا" in summary
    else:
        assert "مقابل العاديّة" in summary and facts["special"]["by_kind"]
    if "holiday" in expected:
        assert facts["special"]["holiday_code"] in ("new-years", "juneteenth")


# ── الحمولة والذرّة ─────────────────────────────────────────────────────
def _walk(node):
    if isinstance(node, dict):
        for key, value in node.items():
            yield str(key)
            yield from _walk(value)
    elif isinstance(node, list):
        for value in node:
            yield from _walk(value)
    elif isinstance(node, str):
        yield node


@pytest.mark.asyncio
async def test_atom_publishes_clean_payload_and_counts(tmp_path):
    days = _weekdays("2024-12-27", "2025-06-27", skip=("2025-01-01",))
    db = _write_history(tmp_path / "h.db", _days(_pattern_spec(days)), PAST_HOURS)
    cal = _write_calendar(tmp_path / "c.db", _calendar_rows())
    clock = _ts("2025-06-30 15:00")
    _, atom, bus = await _atom({"history_db": db, "calendar_db": cal}, clock)
    await _boot(atom)
    payload = bus.payloads("knowledge.seasonal.state")[-1]
    assert payload["status"] == "ok" and payload["symbol"] == SYM and payload["id"] == "nasdaq_seasonal_memory"
    assert payload["computed_at"] == clock and payload["summary_ar"] and payload["source"]
    facts = payload["facts"]
    first_ten = list(facts.items())[:10]
    for key, value in first_ten:                          # الدفتر 465 يختم أوّل عشر مفردات
        assert not isinstance(value, (dict, list)), key
        assert not isinstance(value, str) or len(value) <= 24, key
    assert [k for k, _ in first_ten][:2] == ["weekday", "weekday_mean_pct"]
    words = " ".join(_walk(payload)).lower()
    assert not [word for word in FORBIDDEN if word in words]
    assert facts["weekday"] == "Monday" and facts["month"]["name"] == "June"
    # نبضة الساعة تنشر · مدخلٌ تالف يُعدّ · نبضة اليوم تعيد البناء.
    await atom._on_hour({"official_time": clock + 3600})
    await atom._on_hour({"count": 3})
    await atom._on_day({"official_time": clock + 86400})
    assert len(bus.payloads("knowledge.seasonal.state")) == 3
    assert atom._rejected == 1 and atom._builds == 2
    health = await atom.health_check()
    assert health.state == HealthState.HEALTHY and "تعرف" in health.message and "مرميّات=1" in health.message
    # الحفظ والاستعادة: العدّادات وآخر ما عرفته.
    state = await atom.snapshot()
    _, fresh, _ = await _atom({"history_db": db, "calendar_db": cal}, clock)
    await fresh.restore(state)
    assert fresh._published == 3 and fresh._rejected == 1
    assert fresh._last_payload["facts"]["weekday"] == "Tuesday"
    await atom.stop()


@pytest.mark.asyncio
async def test_older_moment_rebuilds_without_future(tmp_path):
    db = _write_history(tmp_path / "h.db", _days(WEEK_SPEC))
    _, atom, bus = await _atom({"history_db": db, "calendar_db": ""}, NOW)
    await _boot(atom)
    assert atom._memory["history_through"] == date(2025, 6, 20)
    # إعادةٌ تاريخيّة: لحظةٌ أقدم من الذاكرة ⟸ تُبنى عندها، فلا يدخل ما بعدها.
    await atom._on_hour({"official_time": _ts("2025-06-12 15:00")})
    facts = bus.payloads("knowledge.seasonal.state")[-1]["facts"]
    assert facts["coverage"]["history_through"] == "2025-06-11"
    assert facts["weekday"] == "Thursday" and facts["weekday_n"] == 1     # خميس 06-05 وحده
    assert atom._builds == 2
    await atom.stop()


@pytest.mark.asyncio
async def test_missing_or_broken_sources_do_not_break(tmp_path):
    _, atom, bus = await _atom({"history_db": str(tmp_path / "absent.db"),
                                "calendar_db": str(tmp_path / "absent_cal.db")}, NOW)
    await _boot(atom)
    payload = bus.payloads("knowledge.seasonal.state")[-1]
    assert payload["status"] == "unavailable" and payload["facts"] == {"available": False, "reason": "history_db_missing"}
    health = await atom.health_check()
    assert health.state == HealthState.DEGRADED and "history_db_missing" in health.message
    await atom._on_hour({"official_time": NOW + 3600})                   # يعيد المحاولة كلّ ساعة ولا ينكسر
    assert atom._builds == 2 and bus.payloads("knowledge.seasonal.state")[-1]["status"] == "unavailable"
    await atom.stop()
    broken = tmp_path / "broken.db"
    broken.write_bytes(b"this is not a sqlite database" * 64)
    memory = sm.build_memory(str(broken), str(broken), SYM, None, 3, NOW)
    assert memory["status"] == "unavailable" and memory["reason"].startswith("history_db_error")
    assert sm.today_range(str(broken), SYM, NOW)["hours"] == 0
    # ذاكرةٌ مشوّهة (لا تبنيها الذرّة، لكنّها حيّة): التعثّر يُعدّ ويُعلن، والنبضة لا تنكسر.
    atom._running = True
    atom._memory = {"status": "ok", "cut": 0.0}
    atom._history_db = str(broken)
    await atom._on_hour({"official_time": NOW + 7200})
    assert atom._failed == 1 and "تعثّرت=1" in (await atom.health_check()).message
    await atom.stop()
    # التقويم وحده غائب: الذاكرة تعمل، والأنواع بلا تقويم (الجمعة الثالثة · الشهر) باقية.
    db = _write_history(tmp_path / "h.db", _days(WEEK_SPEC))
    memory = sm.build_memory(db, str(tmp_path / "absent_cal.db"), SYM, None, 3, NOW)
    facts, _, status = sf.facts_at(memory, NOW, None)
    assert status == "ok" and facts["coverage"]["calendar_available"] is False
    assert facts["coverage"]["calendar_reason"] == "calendar_db_missing"
    assert memory["special"]["by_kind"]["opex"]["n"] == 1 and memory["special"]["by_kind"]["fomc"]["n"] == 0


@pytest.mark.asyncio
async def test_weekend_day_has_no_session_facts(tmp_path):
    db = _write_history(tmp_path / "h.db", _days(WEEK_SPEC))
    sunday = _ts("2025-06-22 12:00")
    memory = sm.build_memory(db, "", SYM, None, 3, sunday)
    facts, summary, status = sf.facts_at(memory, sunday, None)
    assert status == "ok" and facts["weekday"] == "Sunday" and facts["weekday_n"] == 0
    assert facts["special_day"] == "none" and "لا جلسة للناسداك" in summary
