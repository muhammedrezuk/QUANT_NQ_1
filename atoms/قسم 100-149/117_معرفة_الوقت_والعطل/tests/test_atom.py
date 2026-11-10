"""117 — معرفة الوقت والعطل: كلّ حقيقة على مثالٍ معروف بالأرقام (٢٠٢٦-١٠-٠٨، ختم المالك «NQ» — المعرفة أوّلًا).

⛔ كلّ قاعدة تقويمٍ هنا مؤقّتة في `tmp_path` — لا تُقرأ القاعدة الحيّة أبدًا، ومتغيّر البيئة الذي يسبق
`config` يُزال قبل كلّ اختبار. والساعة تُقاد (`atom._clock`) فلا تتعلّق نتيجةٌ بيوم التشغيل.
"""
import asyncio
import calendar as calendar_mod
import importlib.util
import json
import re
import sqlite3
import sys
import time
from datetime import date
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[4]
FOLDER = Path(__file__).resolve().parents[1]
for _path in (str(ROOT), str(FOLDER)):
    if _path not in sys.path:
        sys.path.insert(0, _path)

_spec = importlib.util.spec_from_file_location("_t117", FOLDER / "atom.py")
m = importlib.util.module_from_spec(_spec)
sys.modules["_t117"] = m
_spec.loader.exec_module(m)

import time_holidays_clock as clock  # noqa: E402
# ٢٠٢٦-١٠-٠٩ (ختم المالك «NQ» — الوقت من مصدرٍ واحد): الجلسات والقواعد انتقلت إلى الوحدة المشتركة؛ التوكيدات كما هي.
from shared import market_clock as mc  # noqa: E402
from core.contracts.atom import AtomContext, HealthState  # noqa: E402

SERVER_S = 10800
FORBIDDEN = re.compile(r"\b(direction|signal|strength|confidence|weight|score|probability|threshold|depth|"
                       r"readiness|buy|sell|bullish|bearish|strong|weak)\b")

# عطل 2026 الأمريكيّة كما في تقويم ميتاتريدر الحيّ (أسماؤها ورموزها؛ و4 تمّوز سبتٌ فنُقل إلى 3).
US_2026 = [
    ("2026-01-01", "new-years-day", "رأس السنة الميلادية الجديدة"),
    ("2026-01-19", "birthday-of-martin-luther-king", "عيد ميلاد مارتن لوثر كينغ"),
    ("2026-02-16", "washingtons-birthday", "عيد ميلاد واشنطن"),
    ("2026-05-25", "memorial-day", "يوم الذكرى"),
    ("2026-06-19", "juneteenth-national-independence-day", "Juneteenth National Independence Day"),
    ("2026-07-03", "independence-day", "عيد الاستقلال"),
    ("2026-07-04", "independence-day", "عيد الاستقلال"),
    ("2026-09-07", "labor-day", "عيد العمال"),
    ("2026-10-12", "columbus-day", "يوم كولومبوس"),
    ("2026-11-11", "veterans-day", "يوم المحاربين القدامى"),
    ("2026-11-26", "thanksgiving-day", "عيد الشكر"),
    ("2026-12-25", "christmas-day", "عيد الميلاد"),
]
GB_2026 = [("2026-08-31", "summer-bank-holiday", "عطلة الصيف للمصرف"), ("2026-12-25", "christmas-day", "عيد الميلاد")]
JP_2026 = [("2026-10-12", "health-and-sports-day", "يوم الصحة والرياضة")]


def utc(text: str) -> float:
    return float(calendar_mod.timegm(time.strptime(text, "%Y-%m-%d %H:%M")))


def make_db(path: Path, us=US_2026, gb=GB_2026, jp=JP_2026, horizon="2026-12-31") -> Path:
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE calendar_history (value_id INTEGER PRIMARY KEY, event_code TEXT, event_name TEXT, "
                "country_code TEXT, sector INTEGER, time_server INTEGER)")
    con.execute("CREATE TABLE export_meta (key TEXT PRIMARY KEY, value TEXT)")
    con.execute("INSERT INTO export_meta VALUES ('server_offset_s_at_export', '10800')")
    sql = ("INSERT INTO calendar_history (event_code, event_name, country_code, sector, time_server) "
           "VALUES (?, ?, ?, ?, ?)")
    for country, rows in (("US", us), ("GB", gb), ("JP", jp)):
        for day, code, name in rows:
            con.execute(sql, (code, name, country, 12, int(utc(day + " 00:00")) + SERVER_S))
    # حدثٌ ليس عطلة (قطاع 4) يحدّد أفق التقويم = آخر ما فيه.
    con.execute(sql, ("cpi", "مؤشّر أسعار المستهلك", "US", 4, int(utc(horizon + " 15:30")) + SERVER_S))
    con.commit()
    con.close()
    return path


class Bus:
    def __init__(self):
        self.events = []

    def subscribe(self, name, handler):
        pass

    async def publish(self, name, payload):
        self.events.append((name, payload))

    def payloads(self, name):
        return [p for n, p in self.events if n == name]


class Logger:
    def __getattr__(self, _name):
        return lambda *a, **k: None


@pytest.fixture(autouse=True)
def _no_live_db(monkeypatch):
    monkeypatch.delenv(m.DB_ENV, raising=False)


async def ready(db: Path, at: float, **cfg):
    """ذرّة بدأت وقرأت قاعدتها المؤقّتة ونشرت مرّة (مهلة الإقلاع صفر)."""
    atom, bus = m.Atom(), Bus()
    atom._clock = lambda: at
    await atom.initialize(AtomContext(117, {"db_path": str(db), "boot_delay_s": 0.0, **cfg},
                                      Logger(), bus.publish, bus.subscribe))
    await atom.start()
    await atom._tasks["boot"]
    return atom, bus


def facts_at(atom, text: str) -> dict:
    return m.build_facts(utc(text), atom._cal)


# ── قواعد بورصة نيويورك ─────────────────────────────────────────────────────
def test_nyse_rule_calendars_match_published_years():
    d = date.fromisoformat
    assert set(mc.nyse_holidays(2026)) == {d(x) for x in (
        "2026-01-01", "2026-01-19", "2026-02-16", "2026-04-03", "2026-05-25", "2026-06-19", "2026-07-03",
        "2026-09-07", "2026-11-26", "2026-12-25")}
    assert set(mc.nyse_holidays(2027)) == {d(x) for x in (
        "2027-01-01", "2027-01-18", "2027-02-15", "2027-03-26", "2027-05-31", "2027-06-18", "2027-07-05",
        "2027-09-06", "2027-11-25", "2027-12-24")}
    # 2022: رأس السنة سبتٌ فلا يُنقل · جونتينث أحدٌ ⟵ الاثنين · الميلاد أحدٌ ⟵ الاثنين.
    assert set(mc.nyse_holidays(2022)) == {d(x) for x in (
        "2022-01-17", "2022-02-21", "2022-04-15", "2022-05-30", "2022-06-20", "2022-07-04", "2022-09-05",
        "2022-11-24", "2022-12-26")}
    for year, sunday in ((2008, "2008-03-23"), (2019, "2019-04-21"), (2024, "2024-03-31"),
                         (2025, "2025-04-20"), (2026, "2026-04-05"), (2038, "2038-04-25")):
        assert mc.easter(year) == d(sunday)


def test_early_close_rules():
    d = date.fromisoformat
    assert mc.is_early_close(d("2026-11-27"))          # الجمعة بعد عيد الشكر
    assert mc.is_early_close(d("2026-12-24"))          # خميس
    assert not mc.is_early_close(d("2026-07-03"))      # هو نفسه العطلة (4 تمّوز سبت)
    assert mc.is_early_close(d("2029-07-03"))          # ثلاثاء
    assert not mc.is_early_close(d("2027-07-03"))      # سبت
    assert not mc.is_early_close(d("2021-12-24"))      # عطلة الميلاد المنقولة
    assert not mc.is_early_close(d("2026-11-26"))


# ── العطل والإغلاق المبكّر ───────────────────────────────────────────────────
async def test_thanksgiving_2026_is_a_holiday_and_the_next_day_closes_early(tmp_path):
    atom, _ = await ready(make_db(tmp_path / "cal.db"), utc("2026-11-26 15:00"))
    f = facts_at(atom, "2026-11-26 15:00")                 # 10:00 نيويورك شتاءً
    assert f["is_holiday_today"] is True and f["holiday_name"] == "عيد الشكر"
    assert f["holiday_source"] == clock.SOURCE_BOTH and f["cash_open"] is False       # التقويم يشهد للقاعدة
    assert f["is_trading_day"] is False and f["session_now"] == mc.SESSION_LONDON
    assert f["minutes_to_cash_open"] == 1410               # ⟵ الجمعة 09:30 نيويورك = 14:30 غرينتش
    pre = facts_at(atom, "2026-11-25 15:00")
    assert pre["is_pre_holiday"] is True and pre["days_to_next_holiday"] == 1
    early = facts_at(atom, "2026-11-27 15:00")
    assert early["is_early_close_today"] is True and early["early_close_time_utc"] == "18:00"
    assert early["cash_open"] is True and early["minutes_to_cash_close"] == 180
    assert "إغلاق مبكّر" in m.summary_ar(early)
    after = facts_at(atom, "2026-11-27 18:30")             # بعد الإغلاق المبكّر ⟵ الاثنين 14:30 غرينتش
    assert after["cash_open"] is False and after["minutes_to_cash_open"] == 4080
    await atom.stop()


async def test_columbus_day_is_a_bank_holiday_and_the_exchange_trades(tmp_path):
    atom, _ = await ready(make_db(tmp_path / "cal.db"), utc("2026-10-12 14:00"))
    f = facts_at(atom, "2026-10-12 14:00")
    assert f["is_holiday_today"] is False and f["is_bank_holiday_today"] is True
    assert f["bank_holiday_name"] == "يوم كولومبوس" and f["cash_open"] is True
    assert "عطلة مصارف" in m.summary_ar(f)
    await atom.stop()


async def test_rules_extend_the_calendar_beyond_its_horizon(tmp_path):
    # كالقاعدة الحيّة: أفقها 2026-10-21 فلا عيد شكرٍ 2026 فيها، ولا «جمعة عظيمة» أصلًا.
    past = [("2025-11-27", "thanksgiving-day", "عيد الشكر"), ("2025-12-25", "christmas-day", "عيد الميلاد")]
    rows = past + [r for r in US_2026 if r[0] <= "2026-10-12"]
    atom, _ = await ready(make_db(tmp_path / "cal.db", us=rows, gb=GB_2026[:1], horizon="2026-10-21"),
                          utc("2026-10-08 13:48"))
    assert atom._cal["horizon"] == "2026-10-21"
    f = facts_at(atom, "2026-10-08 13:48")
    assert f["next_holiday_name"] == "عيد الشكر" and f["next_holiday_date"] == "2026-11-26"
    assert f["next_holiday_source"] == mc.SOURCE_RULES and f["days_to_next_holiday"] == 49
    good_friday = facts_at(atom, "2026-04-03 14:00")
    assert good_friday["is_holiday_today"] is True and good_friday["holiday_source"] == mc.SOURCE_RULES
    assert good_friday["cash_open"] is False
    gf_2027 = facts_at(atom, "2027-03-26 14:00")
    assert gf_2027["holiday_name"] == "الجمعة العظيمة" and gf_2027["is_holiday_today"] is True
    await atom.stop()


async def test_federal_only_days_are_not_market_holidays(tmp_path):
    # القائمة فيدراليّة: رأس سنة 2028 سبتٌ ⟵ الحكومة تعطّل الجمعة 2027-12-31 والبورصة تعمل (قاعدتها: لا نقل).
    # و2025-01-21 صفٌّ زائد في القاعدة الحيّة نفسها. ورمزٌ لا تعرفه القواعد (حداد وطنيّ) يُؤخذ من التقويم كما هو.
    us = US_2026 + [("2027-12-31", "new-years-day", "رأس السنة الميلادية الجديدة"),
                    ("2025-01-20", "birthday-of-martin-luther-king", "عيد ميلاد مارتن لوثر كينغ"),
                    ("2025-01-21", "birthday-of-martin-luther-king", "عيد ميلاد مارتن لوثر كينغ"),
                    ("2025-01-09", "national-day-of-mourning", "يوم حداد وطني")]
    atom, _ = await ready(make_db(tmp_path / "cal.db", us=us, horizon="2028-01-05"), utc("2027-12-31 15:00"))
    eve = facts_at(atom, "2027-12-31 15:00")
    assert eve["is_holiday_today"] is False and eve["is_bank_holiday_today"] is True
    assert eve["cash_open"] is True and eve["is_year_end"] is True
    extra = facts_at(atom, "2025-01-21 15:00")
    assert extra["is_holiday_today"] is False and extra["cash_open"] is True
    mlk = facts_at(atom, "2025-01-20 15:00")
    assert mlk["is_holiday_today"] is True and mlk["holiday_source"] == clock.SOURCE_BOTH
    mourning = facts_at(atom, "2025-01-09 15:00")
    assert mourning["holiday_name"] == "يوم حداد وطني" and mourning["holiday_source"] == clock.SOURCE_CALENDAR
    assert mourning["cash_open"] is False
    await atom.stop()


# ── أيّام السوق الخاصّة ─────────────────────────────────────────────────────
async def test_third_friday_opex_and_period_ends(tmp_path):
    atom, _ = await ready(make_db(tmp_path / "cal.db"), utc("2026-10-16 14:00"))
    f = facts_at(atom, "2026-10-16 14:00")
    assert f["is_monthly_opex"] is True and f["is_quarterly_opex"] is False
    assert f["day_of_week"] == "Friday" and f["week_of_month"] == 3 and f["days_to_next_opex"] == 0
    assert f["trading_day_of_month"] == 12 and f["trading_days_in_month"] == 22
    before = facts_at(atom, "2026-10-08 13:48")
    assert before["days_to_next_opex"] == 8 and before["next_opex_date"] == "2026-10-16"
    assert facts_at(atom, "2026-09-18 14:00")["is_quarterly_opex"] is True
    # حزيران 2026: الجمعة الثالثة (19) عطلة جونتينث ⟵ الانتهاء الخميس 18.
    june = facts_at(atom, "2026-06-18 14:00")
    assert june["is_monthly_opex"] is True and june["is_quarterly_opex"] is True
    assert facts_at(atom, "2026-06-19 14:00")["is_monthly_opex"] is False
    assert facts_at(atom, "2026-10-17 14:00")["days_to_next_opex"] == 34      # ⟵ 2026-11-20
    ends = facts_at(atom, "2026-12-31 15:00")
    assert ends["is_month_end"] and ends["is_quarter_end"] and ends["is_year_end"]
    assert facts_at(atom, "2026-09-30 15:00")["is_quarter_end"] is True
    assert facts_at(atom, "2026-10-01 15:00")["is_month_start"] is True
    assert facts_at(atom, "2027-05-28 15:00")["is_month_end"] is True        # 31 أيّار 2027 يوم الذكرى
    await atom.stop()


# ── الجلسات والتوقيت الصيفيّ ────────────────────────────────────────────────
async def test_dst_switches_new_york_and_london(tmp_path):
    atom, _ = await ready(make_db(tmp_path / "cal.db"), utc("2026-10-08 13:48"))
    assert facts_at(atom, "2026-11-01 05:59")["is_dst_new_york"] is True
    winter = facts_at(atom, "2026-11-01 06:00")
    assert winter["is_dst_new_york"] is False and winter["utc_offset_new_york_h"] == -5
    assert facts_at(atom, "2026-10-30 13:45")["cash_open"] is True             # 09:45 صيفيّ
    monday = facts_at(atom, "2026-11-02 13:45")                                # 08:45 شتويّ
    assert monday["cash_open"] is False and monday["minutes_to_cash_open"] == 45
    assert facts_at(atom, "2026-11-02 14:45")["cash_open"] is True
    assert facts_at(atom, "2026-10-25 00:59")["is_dst_london"] is True
    assert facts_at(atom, "2026-10-25 01:00")["is_dst_london"] is False
    assert mc.SESSION_LONDON in facts_at(atom, "2026-10-23 07:30")["sessions_open"]       # 08:30 صيفيّ
    assert mc.SESSION_LONDON not in facts_at(atom, "2026-10-26 07:30")["sessions_open"]   # 07:30 شتويّ
    assert mc.SESSION_LONDON in facts_at(atom, "2026-10-26 08:00")["sessions_open"]
    await atom.stop()


async def test_asia_session_runs_on_tokyo_clock_and_its_holidays(tmp_path):
    atom, _ = await ready(make_db(tmp_path / "cal.db"), utc("2026-10-08 00:30"))
    f = facts_at(atom, "2026-10-08 00:30")
    assert f["tokyo_time"] == "09:30" and f["session_now"] == mc.SESSION_ASIA
    assert mc.SESSION_ASIA in facts_at(atom, "2026-10-08 05:59")["sessions_open"]       # 14:59 طوكيو
    assert mc.SESSION_ASIA not in facts_at(atom, "2026-10-08 06:00")["sessions_open"]   # 15:00
    assert mc.SESSION_ASIA not in facts_at(atom, "2026-10-11 23:30")["sessions_open"]   # الاثنين 08:30
    holiday = facts_at(atom, "2026-10-12 01:00")                                           # يوم الرياضة
    assert mc.SESSION_ASIA not in holiday["sessions_open"]
    assert holiday["tokyo_holiday_name"] == "يوم الصحة والرياضة"
    assert mc.SESSION_ASIA in facts_at(atom, "2026-10-19 00:00")["sessions_open"]
    await atom.stop()


async def test_overlap_owner_window_broker_day_and_summary(tmp_path):
    atom, bus = await ready(make_db(tmp_path / "cal.db"), utc("2026-10-08 13:48"))
    body = bus.payloads(m.EV_STATE)[-1]
    f = body["facts"]
    assert f["sessions_open"] == [mc.SESSION_LONDON, mc.SESSION_NY_CASH, mc.SESSION_OVERLAP,
                                  mc.SESSION_GLOBEX]
    assert f["session_now"] == mc.SESSION_OVERLAP and f["owner_window"] == "ny_open"
    assert f["minutes_to_cash_close"] == 372 and f["minutes_to_cash_open"] == 0
    assert f["new_york_time"] == "09:48" and f["london_time"] == "14:48"
    assert f["days_to_next_holiday"] == 49 and f["next_holiday_name"] == "عيد الشكر"   # كولومبوس والمحاربون عطلتا مصارف
    assert f["broker_day_date"] == "2026-10-08" and f["broker_day_start_utc"] == utc("2026-10-07 21:00")
    summary = body["summary_ar"]
    assert summary.startswith("الآن: لندن ونيويورك مفتوحتان (تداخل)")
    for part in ("النقديّ يغلق بعد 6س12د", "العطلة القادمة عيد الشكر بعد 49 يومًا", "انتهاء الخيارات الشهريّ بعد 8 أيّام"):
        assert part in summary, summary
    winter = facts_at(atom, "2026-11-02 21:30")            # يوم الوسيط شتاءً +2
    assert winter["broker_day_date"] == "2026-11-02" and winter["broker_day_start_utc"] == utc("2026-11-01 22:00")
    assert facts_at(atom, "2026-11-02 22:30")["broker_day_date"] == "2026-11-03"
    await atom.stop()


async def test_nasdaq_globex_weekly_hours(tmp_path):
    atom, _ = await ready(make_db(tmp_path / "cal.db"), utc("2026-10-08 13:48"))
    def globex(text):
        return mc.SESSION_GLOBEX in facts_at(atom, text)["sessions_open"]
    saturday = facts_at(atom, "2026-10-10 15:00")
    assert not globex("2026-10-10 15:00") and saturday["session_now"] == mc.SESSION_CLOSED
    assert not globex("2026-10-11 21:59") and globex("2026-10-11 22:00")      # الأحد 18:00 نيويورك
    assert not globex("2026-10-07 21:30") and globex("2026-10-07 22:00")      # استراحة 17:00–18:00
    assert globex("2026-10-09 20:59") and not globex("2026-10-09 21:00")      # الجمعة 17:00
    await atom.stop()


# ── غياب المصدر · العقد · الحفظ ──────────────────────────────────────────────
async def test_missing_calendar_does_not_break_and_says_so(tmp_path):
    atom, bus = await ready(tmp_path / "absent.db", utc("2026-11-26 15:00"))
    f = bus.payloads(m.EV_STATE)[-1]["facts"]
    assert f["holidays_status"] == clock.STATUS_UNAVAILABLE and f["calendar"]["reason"] == clock.REASON_MISSING
    for key in ("is_holiday_today", "is_pre_holiday", "next_holiday_name", "days_to_next_holiday", "holiday_name"):
        assert f[key] is None, key
    # والساعة لا تكذب: عيد الشكر بقواعد البورصة ⟵ النقديّ مغلق، ولندن تعمل.
    assert f["cash_open"] is False and f["trading_calendar_source"] == mc.SOURCE_RULES
    assert mc.SESSION_LONDON in f["sessions_open"] and f["day_of_week"] == "Thursday"
    assert "العطل غير متاحة (ملفّ التقويم مفقود)" in bus.payloads(m.EV_STATE)[-1]["summary_ar"]
    health = await atom.health_check()
    assert health.state == HealthState.DEGRADED and "غير متاحة" in health.message
    await atom._on_pulse({})
    assert len(bus.payloads(m.EV_STATE)) == 2 and atom._read_errors == 2
    await atom.stop()
    broken = tmp_path / "broken.db"
    broken.write_bytes(b"not a sqlite database at all" * 40)
    result = clock.load_calendar(str(broken), SERVER_S, 0.0)
    assert result["status"] == clock.STATUS_UNAVAILABLE and result["reason"].startswith(clock.REASON_READ)


async def test_payload_contract_ten_scalars_first_and_no_forbidden_fields(tmp_path):
    atom, bus = await ready(make_db(tmp_path / "cal.db"), utc("2026-11-27 15:00"))
    body = bus.payloads(m.EV_STATE)[-1]
    assert set(body) == {"id", "symbol", "status", "facts", "computed_at", "summary_ar", "source"}
    assert body["symbol"] == "USTEC" and body["status"] == "ok" and body["id"].isascii()
    first_ten = list(body["facts"].items())[:10]
    for key, value in first_ten:
        assert value is None or isinstance(value, (bool, int, float)) or (
            isinstance(value, str) and len(value) <= 24), (key, value)
    assert all(key.isascii() for key in body["facts"])
    english = json.dumps({k: v for k, v in body.items() if k != "summary_ar"}, ensure_ascii=False).lower()
    assert not FORBIDDEN.search(english), FORBIDDEN.search(english)
    assert body["facts"]["calendar"]["us_holiday_rows_n"] == len(US_2026)
    await atom.stop()


async def test_boot_waits_then_pulse_publishes_and_bad_input_is_counted(tmp_path):
    atom, bus = m.Atom(), Bus()
    atom._clock = lambda: utc("2026-10-08 13:48")
    await atom.initialize(AtomContext(117, {"db_path": str(make_db(tmp_path / "cal.db"))}, Logger(),
                                      bus.publish, bus.subscribe))
    await atom.start()
    await asyncio.sleep(0.2)
    assert not bus.payloads(m.EV_STATE)                    # مهلة الإقلاع 30 ث لم تنقضِ
    await atom._on_pulse("not-a-dict")
    assert atom._rejected == {m.BAD_PULSE: 1}
    await atom._on_pulse({"official_time": 1.0})
    assert len(bus.payloads(m.EV_STATE)) == 1
    await atom.stop()
    assert not atom._tasks


async def test_snapshot_restore_keeps_the_last_known_calendar(tmp_path):
    first, _ = await ready(make_db(tmp_path / "cal.db"), utc("2026-11-26 15:00"))
    state = json.loads(json.dumps(await first.snapshot()))
    await first.stop()
    atom, _ = m.Atom(), Bus()
    atom._clock = lambda: utc("2026-11-26 15:00")
    await atom.initialize(AtomContext(117, {"db_path": str(tmp_path / "gone.db")}, Logger(),
                                      Bus().publish, Bus().subscribe))
    await atom.restore(state)
    assert atom._cal["status"] == "restored" and atom._published == 1
    await atom._reload()                                    # القاعدة اختفت ⟵ آخر ما عُرف يبقى «قديمًا»
    f = m.build_facts(utc("2026-11-26 15:00"), atom._cal)
    assert f["holidays_status"] == "stale" and f["is_holiday_today"] is True
    assert f["calendar"]["reason"] == clock.REASON_MISSING
    atom._running = True
    assert "قديم" in (await atom.health_check()).message
