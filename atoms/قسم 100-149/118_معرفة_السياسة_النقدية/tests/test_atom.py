"""معرفة السياسة النقديّة 118 — كلّ حقيقة على قاعدتَي اختبارٍ مؤقّتتين (تاريخٌ وجسر) بأرقامٍ معروفة، لا الحيّتين."""
import asyncio
import calendar
import re
import sqlite3
import sys
import time
from pathlib import Path

import pytest

# الوحدتان الشقيقتان تُستوردان باسمهما (المُقلِع يضيف مجلّد الذرّة أثناء التحميل؛ وهنا يُضاف للاختبار) — في آخر
# مسار البحث لا أوّله، فلا يظلّل `atom.py` ولا مجلّد `tests` هنا شيئًا من المشروع عند التشغيل الموحّد.
_ATOM_DIR = str(Path(__file__).resolve().parents[1])
if _ATOM_DIR not in sys.path:
    sys.path.append(_ATOM_DIR)

from tests.learning_test_support import make_atom  # noqa: E402

# ٢٠٢٦-١٠-١٧: وقت الخادم = غرينتش + فرق الوسيط في تلك اللحظة (ساعتان شتاءً، ثلاث صيفًا) — كان 3 ثابتة فأخفى العلّة.
from shared.owner_windows import broker_day_offset_s  # noqa: E402
FORBIDDEN = ("direction", "signal", "strength", "confidence", "weight", "score", "probability",
             "threshold", "depth", "readiness", "buy", "sell", "bullish", "bearish", "strong", "weak")


def utc(text):
    return float(calendar.timegm(time.strptime(text, "%Y-%m-%d %H:%M")))


NOW = utc("2026-10-08 13:00")         # الخميس


def _row(code, name, at, *, imp=3, actual=None, forecast=None, prev=None, digits=1, unit=1, mult=0,
         country="US", revised=None, vid=None):
    return {"value_id": vid, "event_code": code, "event_name": name, "country_code": country,
            "currency": "USD" if country == "US" else "JPY", "importance": imp,
            "time_server": int(utc(at) + broker_day_offset_s(utc(at))), "actual": actual, "forecast": forecast, "prev": prev,
            "revised_prev": revised, "digits": digits, "unit": unit, "multiplier": mult}


DECISION = ("fed-interest-rate-decision", "قرار سعر فائدة بنك الإحتياطي الفيدرالي")
CORE = ("consumer-price-index-ex-food-energy-mm", "مؤشر أسعار المستهلك الأساسي على أساس شهري")
NFP = ("nonfarm-payrolls", "قوائم الرواتب غير الزراعية")
CLAIMS = ("initial-jobless-claims", "مطالبات البطالة الأولية")
PCE = ("core-pce-price-index-mm", "مؤشر سعر نفقات الاستهلاك الشخصي الأساسي على أساس شهري")
ROWS = [
    # قرارات الفائدة: خفضان ثمّ تثبيتان ثمّ رفع 25 ن.أ، وقرارٌ مجدول بلا قيمة.
    _row(*DECISION, "2025-09-17 18:00", actual=4.25, prev=4.5, digits=2),
    _row(*DECISION, "2025-10-29 18:00", actual=4.0, prev=4.25, digits=2),
    _row(*DECISION, "2025-12-10 19:00", actual=3.75, prev=4.0, digits=2),
    _row(*DECISION, "2026-01-28 19:00", actual=3.75, prev=3.75, digits=2),
    _row(*DECISION, "2026-03-18 18:00", actual=3.75, prev=3.75, digits=2),
    _row(*DECISION, "2026-09-16 18:00", actual=4.0, prev=3.75, digits=2),
    _row(*DECISION, "2026-10-28 18:00", prev=4.0, digits=2),
    # آخر الإصدارات (ومعها صفٌّ يابانيّ بالرمز نفسه وأحدث — لا يُقرأ).
    _row(*CORE, "2026-08-12 12:30", actual=0.2, forecast=0.3, prev=0.3),
    _row(*CORE, "2026-09-11 12:30", actual=0.3, forecast=0.2, prev=0.2),
    _row(CORE[0], "مؤشر ياباني", "2026-10-02 09:00", actual=9.9, forecast=1.0, prev=1.0, country="JP"),
    _row(*NFP, "2026-09-04 12:30", actual=162.0, forecast=41.0, prev=-23.0, digits=0, unit=4, mult=1),
    _row(*NFP, "2026-10-02 12:30", actual=29.0, forecast=52.0, prev=162.0, revised=133.0, digits=0, unit=4, mult=1),
    _row("unemployment-rate", "معدل البطالة", "2026-10-02 12:30", actual=4.2, forecast=4.1, prev=4.1),
    _row(*PCE, "2026-09-30 12:30", actual=0.2, forecast=0.2, prev=0.2),
    _row(*PCE, "2026-10-07 20:00", forecast=0.3, prev=0.2),        # مرّ ولا قيمة في التاريخ ولا في الجسر
    _row(*CLAIMS, "2026-10-08 12:30", forecast=190.0, prev=197.0, digits=0, unit=0, mult=1, vid=317675),  # آلاف (كالحيّ)
    # القادم: نفطٌ بعد 90 د وتضخّمٌ غدًا (عاليان في النافذة)، ومتوسّطٌ وعالٍ بعد النافذة ويابانيّ — خارجها.
    _row("eia-crude-oil-stocks-change", "التغيير في مخزون النفط الخام", "2026-10-08 14:30", forecast=1.07, prev=0.922),
    _row(*CORE, "2026-10-09 12:30", forecast=0.3, prev=0.3),
    _row("michigan-consumer-sentiment", "ثقة مستهلك ميشيغان", "2026-10-09 14:00", imp=2, forecast=55.0),
    _row("retail-sales-mm", "مبيعات التجزئة على أساس شهري", "2026-10-11 12:30", forecast=0.5),
    _row("tankan", "مؤشر ياباني عالٍ", "2026-10-08 23:50", country="JP"),
    _row(*NFP, "2026-11-06 13:30", forecast=60.0, prev=29.0, digits=0, unit=4, mult=1),
    _row("gross-domestic-product-qq", "الناتج الإجمالي المحلي على أساس ربع سنوي", "2026-11-20 13:30"),  # بعد 30 يومًا
    # خطابات: بالاسم (بويل)، وبالرمز (والر باسمٍ إنكليزيّ)، ووزير الخزانة لا، وخطابٌ بعد النافذة لا.
    _row("fed-chair-powell-speech", "خطاب بويل رئيس مجلس بنك الاحتياطي الفيدرالي", "2026-10-09 16:00", imp=3),
    _row("fed-governor-waller-speech", "Fed Governor Waller Speech", "2026-10-08 20:00", imp=2),
    _row("treasury-secretary-mnuchin-speech", "خطاب وزير الخزانة منوشين", "2026-10-08 18:00", imp=2),
    _row("fed-governor-cook-speech", "خطاب كوك محافظ بنك الاحتياطي الفيدرالي", "2026-10-12 18:00", imp=2),
]
FIELDS = ("value_id", "event_code", "event_name", "country_code", "currency", "importance", "time_server",
          "actual", "forecast", "prev", "revised_prev", "digits", "unit", "multiplier")


def make_db(path, rows=ROWS, exported=NOW - 20 * 3600, meta=None):
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE calendar_history (value_id INTEGER PRIMARY KEY, event_id INTEGER, event_code TEXT, "
                "event_name TEXT, country_code TEXT, currency TEXT, importance INTEGER, type INTEGER, "
                "sector INTEGER, frequency INTEGER, time_mode INTEGER, unit INTEGER, multiplier INTEGER, "
                "digits INTEGER, time_server INTEGER, period INTEGER, revision INTEGER, actual REAL, "
                "forecast REAL, prev REAL, revised_prev REAL, impact_type INTEGER, source_url TEXT, "
                "exported_at INTEGER)")
    con.execute("CREATE TABLE export_meta (key TEXT PRIMARY KEY, value TEXT)")
    for row in rows:
        con.execute("INSERT INTO calendar_history (%s) VALUES (%s)" % (", ".join(FIELDS), ",".join("?" * len(FIELDS))),
                    tuple(row[f] for f in FIELDS))
    pairs = {"exported_at_utc": str(int(exported)), "server": "ICMarketsSC-Demo", **(meta or {})}
    con.executemany("INSERT INTO export_meta VALUES (?, ?)", list(pairs.items()))
    con.commit()
    con.close()
    return str(path)


def make_bridge(path, rows):
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE calendar(id TEXT PRIMARY KEY,title TEXT,country TEXT,currency TEXT,impact_level TEXT,"
                "scheduled_at REAL,actual TEXT,forecast TEXT,previous TEXT,written_at REAL)")
    for bid, title, at, actual in rows:
        con.execute("INSERT INTO calendar VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (bid, title, "الولايات المتحدة", "USD", "HIGH", at, actual, "", "", NOW))
    con.commit()
    con.close()
    return str(path)


async def _atom(tmp_path, monkeypatch, rows=ROWS, name="cal.db", bridge="", meta=None):
    monkeypatch.delenv("NQ_CALENDAR_HISTORY_DB", raising=False)
    monkeypatch.delenv("NQ_BRIDGE_DB", raising=False)
    path = make_db(tmp_path / name, rows, meta=meta) if rows is not None else str(tmp_path / "missing.db")
    module, atom, bus = await make_atom(118, {"db_path": path, "bridge_db_path": bridge or str(tmp_path / "no_bridge.db"),
                                              "boot_delay_s": 3600.0})
    atom._clock = lambda: NOW
    return module, atom, bus


def _walk(value, path=""):
    if isinstance(value, dict):
        for key, inner in value.items():
            yield "key", str(key), path
            yield from _walk(inner, path + "." + str(key))
    elif isinstance(value, list):
        for inner in value:
            yield from _walk(inner, path)
    elif isinstance(value, str):
        yield "text", value, path


async def test_rate_change_count_and_cycle(tmp_path, monkeypatch):
    _, atom, bus = await _atom(tmp_path, monkeypatch)
    payload = await atom.refresh(NOW)
    f = payload["facts"]
    assert payload["status"] == "ok" and payload["symbol"] == "USTEC"
    assert f["fed_rate_current"] == 4.0 and f["fed_rate_previous"] == 3.75 and f["fed_rate_current_source"] == "history"
    assert f["fed_last_change"] == {"value": 4.0, "from": 3.75, "date_utc": "2026-09-16", "change_bp": 25}
    assert f["fed_decisions_count"] == 6 and f["fed_first_decision_date"] == "2025-09-17"
    cycle = f["fed_cycle"]          # منذ 2025-10-08: خفضان ثمّ تثبيتان ثمّ رفع ⟸ صافي −25 على 5 قرارات
    assert (cycle["n"], cycle["hikes"], cycle["cuts"], cycle["holds"], cycle["net_change_bp"]) == (5, 1, 2, 2, -25)
    assert bus.payloads("knowledge.monetary.state")[-1] is payload
    await atom.stop()


async def test_next_meeting_and_fomc_day(tmp_path, monkeypatch):
    _, atom, _ = await _atom(tmp_path, monkeypatch)
    f = (await atom.refresh(NOW))["facts"]
    assert f["next_fomc_date_utc"] == "2026-10-28T18:00Z"          # بعد 20 يومًا و5 ساعات
    assert f["days_to_next_fomc"] == pytest.approx(20.2) and f["hours_to_next_fomc"] == pytest.approx(485.0)
    assert f["is_fomc_day"] is False and f["next_fomc_unavailable_reason"] is None
    day = (await atom.refresh(utc("2026-10-28 12:00")))["facts"]
    assert day["is_fomc_day"] is True and day["hours_to_next_fomc"] == pytest.approx(6.0)
    await atom.stop()


async def test_no_scheduled_meeting_is_declared_not_guessed(tmp_path, monkeypatch):
    rows = [r for r in ROWS if not (r["event_code"] == DECISION[0] and r["actual"] is None)]
    _, atom, _ = await _atom(tmp_path, monkeypatch, rows=rows)
    payload = await atom.refresh(NOW)
    f = payload["facts"]
    assert f["next_fomc_date_utc"] is None and f["days_to_next_fomc"] is None
    assert "أفقه 2026-11-20T13:30Z" in f["next_fomc_unavailable_reason"]
    assert "لا قرار فائدة مجدول في المصدر" in payload["summary_ar"] and f["next_dates"]["rate"] is None
    await atom.stop()


async def test_upcoming_high_impact_window_and_speeches(tmp_path, monkeypatch):
    _, atom, _ = await _atom(tmp_path, monkeypatch)
    f = (await atom.refresh(NOW))["facts"]
    # العالية الأمريكيّة في 48 ساعة وحدها: النفط (+90 د) ثمّ التضخّم ثمّ خطاب بويل — لا المتوسّط ولا اليابانيّ
    # ولا مبيعات التجزئة بعد النافذة.
    codes = [e["code"] for e in f["high_impact_next_48h"]]
    assert codes == ["eia-crude-oil-stocks-change", CORE[0], "fed-chair-powell-speech"]
    cpi = f["high_impact_next_48h"][1]
    assert cpi["time_utc"] == "2026-10-09T12:30Z" and cpi["broker_forecast"] == 0.3 and cpi["prev"] == 0.3
    assert cpi["consensus"] is None                                  # لا جدول ناسداك هنا
    assert f["minutes_to_next_high_impact"] == 90 and f["next_high_impact_event"]["code"] == "eia-crude-oil-stocks-change"
    speeches = {e["code"]: e["matched_by"] for e in f["fed_speeches_next_48h"]}
    assert speeches == {"fed-governor-waller-speech": "event_code", "fed-chair-powell-speech": "name"}
    assert f["fed_speeches_next_48h_count"] == 2 and f["window_48h_within_source"] is True
    late = (await atom.refresh(utc("2026-10-29 18:00")))["facts"]      # قرار 10-28 مرّ والقاعدة بلا قيمته
    assert late["fed_decision_passed_without_actual_utc"] == "2026-10-28T18:00Z" and late["fed_rate_current"] == 4.0
    assert late["minutes_to_next_high_impact"] == utc("2026-11-06 13:30") // 60 - utc("2026-10-29 18:00") // 60
    await atom.stop()


async def test_future_horizon_sync_and_whats_coming(tmp_path, monkeypatch):
    meta = {"sync_mode": "hourly_ea", "horizon_days_ahead": "180", "last_sync_rows": "4200", "failed_chunks": "0"}
    _, atom, _ = await _atom(tmp_path, monkeypatch, meta=meta)
    payload = await atom.refresh(NOW)
    f = payload["facts"]
    assert f["calendar_horizon_utc"] == "2026-11-20T13:30Z" and f["calendar_days_ahead"] == pytest.approx(43.0)
    assert f["sync_mode"] == "hourly_ea" and f["sync_age_minutes"] == 1200 and f["sync_days_ahead_setting"] == 180
    coming = [(e["code"], e["category"]) for e in f["coming_30d"]]
    # أبواب المالك وحدها في 30 يومًا (لا النفط ولا مبيعات التجزئة ولا ميشيغان ولا وزير الخزانة، ولا الناتج بعد 30 يومًا).
    assert coming == [("fed-governor-waller-speech", "fed_speech"), (CORE[0], "inflation"),
                      ("fed-chair-powell-speech", "fed_speech"), ("fed-governor-cook-speech", "fed_speech"),
                      (DECISION[0], "rate"), (NFP[0], "jobs")]
    assert f["coming_30d_count"] == 6 and f["coming_30d"][4]["days_to"] == pytest.approx(20.2)
    assert f["next_dates"] == {"rate": "2026-10-28", "inflation": "2026-10-09", "jobs": "2026-11-06",
                               "gdp": None, "pce": None}
    assert "مواعيد قادمة: الفائدة 2026-10-28، التضخّم 2026-10-09، الوظائف 2026-11-06" in payload["summary_ar"]
    await atom.stop()


async def test_actual_minus_forecast_from_us_rows_only(tmp_path, monkeypatch):
    _, atom, _ = await _atom(tmp_path, monkeypatch)
    payload = await atom.refresh(NOW)
    f = payload["facts"]
    core = f["releases"]["core_cpi_mm"]            # الصفّ اليابانيّ الأحدث (9.9) لا يُقرأ
    assert (core["actual"], core["broker_forecast"], core["prev"], core["actual_source"]) == (0.3, 0.2, 0.2, "history")
    assert core["actual_minus_broker_forecast"] == pytest.approx(0.1) and core["consensus"] is None
    assert f["core_cpi_mm_actual_minus_forecast"] == pytest.approx(0.1) and f["core_cpi_mm_diff_basis"] == "broker_forecast"
    nfp = f["releases"]["nonfarm_payrolls"]
    assert nfp["actual_minus_broker_forecast"] == -23 and nfp["unit"] == "ألف وظيفة" and nfp["revised_prev"] == 133.0
    assert f["releases"]["unemployment_rate"]["actual_minus_broker_forecast"] == pytest.approx(0.1)
    assert f["releases"]["core_pce_mm"]["passed_without_actual_utc"] == "2026-10-07T20:00Z"
    assert f["releases"]["cpi_yy"]["available"] is False
    assert f["actual_minus_broker_forecast_label_ar"] == "فرق الفعليّ عن توقّع الوسيط"
    assert f["broker_forecast_is_consensus"] is False and f["econ_calendar_available"] is False
    assert f["econ_calendar_unavailable_reason"] == "BRIDGE_FILE_MISSING"
    assert f["last_release_surprise"]["code"] == NFP[0] and f["last_release_surprise"]["consensus"] is None
    assert "آخر تضخّم أساسيّ 0.3 مقابل توقّع الوسيط 0.2" in payload["summary_ar"]
    assert "الفائدة 4.00٪ (رُفعت 25 ن.أ في 2026-09-16)" in payload["summary_ar"]
    await atom.stop()


async def test_bridge_fills_actual_at_release_moment(tmp_path, monkeypatch):
    rows = ROWS + [_row(*CORE, "2026-10-07 12:30", forecast=0.3, prev=0.3, vid=277504),
                   _row("ism-non-manufacturing-pmi", "مؤشر معهد إدارة التوريد لمدراء المشتريات غير النصنيعيين",
                        "2026-10-07 14:00", forecast=54.7, vid=283028),
                   _row(*NFP, "2026-10-03 12:30", forecast=40.0, digits=0, vid=900001)]
    bridge = make_bridge(tmp_path / "brain.db", [
        ("317675", "مطالبات البطالة الأولية", utc("2026-10-08 12:30") - 1, "205.0000"),       # بالمعرّف (يسبق بثانية)
        ("999999", "مؤشر أسعار المستهلك الأساسي على أساس شهري", utc("2026-10-07 12:30"), "0.5000"),  # بالاسم والوقت
        ("283028", "مؤشر معهد إدارة التوريد لمدراء المشتريات غير النصنيعيين", utc("2026-10-07 13:59") + 59, ""),  # بلا قيمة
        ("555001", "قوائم الرواتب غير الزراعية", utc("2026-10-03 12:30"), "77.0000"),           # أقدم من 3 أيّام
        ("555002", "معدل البطالة", utc("2026-10-08 12:30"), "4.5"), ("555003", "معدل البطالة", utc("2026-10-08 12:30"), "4.6")])
    rows.append(_row("unemployment-rate", "معدل البطالة", "2026-10-08 12:30", forecast=4.2))   # ملتبس: صفّان في الجسر
    _, atom, _ = await _atom(tmp_path, monkeypatch, rows=rows, bridge=bridge)
    f = (await atom.refresh(NOW))["facts"]
    # في نافذة الأيّام الثلاثة خمسة صفوف (صفّ 10-03 خارجها)، أربعةٌ منها بقيمة.
    assert f["bridge_available"] is True and f["bridge_rows_3d"] == 5 and f["bridge_rows_3d_with_actual"] == 4
    assert f["actuals_from_bridge"] == 2                      # المطالبات بالمعرّف، والتضخّم الأساسيّ بالاسم والوقت
    core = f["releases"]["core_cpi_mm"]
    assert (core["actual"], core["actual_source"], core["time_utc"]) == (0.5, "bridge", "2026-10-07T12:30Z")
    assert core["actual_minus_broker_forecast"] == pytest.approx(0.2)
    assert f["core_cpi_mm_actual_minus_forecast"] == pytest.approx(0.2)
    assert f["econ_calendar_available"] is False and f["econ_calendar_unavailable_reason"] == "ECON_TABLE_MISSING"
    assert f["releases"]["unemployment_rate"]["time_utc"] == "2026-10-02T12:30Z"   # الملتبس لا يُملأ
    assert f["releases"]["nonfarm_payrolls"]["actual"] == 29.0                     # الأقدم من 3 أيّام لا يُملأ
    past = f["last_30d_high_impact"]
    claims = [d for d in past["largest_diffs"] if d["code"] == CLAIMS[0]]
    assert past["n_actual_from_bridge"] == 2 and (not claims or claims[0]["actual_source"] == "bridge")
    await atom.stop()


async def test_past_30_days_largest_diffs_in_typical_units(tmp_path, monkeypatch):
    rows = ROWS + [_row(*CORE, "2026-10-07 12:30", forecast=0.3, prev=0.3, vid=277504)]
    bridge = make_bridge(tmp_path / "brain.db", [("277504", CORE[1], utc("2026-10-07 12:30"), "0.5")])
    _, atom, _ = await _atom(tmp_path, monkeypatch, rows=rows, bridge=bridge)
    past = (await atom.refresh(NOW))["facts"]["last_30d_high_impact"]
    # العالي الأمريكيّ منذ 2026-09-08 13:00: التضخّم الأساسيّ (09-11 و10-07)، والفائدة، والوظائف والبطالة (10-02)،
    # ونفقات الاستهلاك (09-30 و10-07 بلا قيمة)، والمطالبات (10-08 بلا قيمة).
    assert (past["n"], past["n_with_actual"], past["n_actual_from_bridge"], past["n_with_diff"]) == (8, 6, 1, 5)
    top = [(d["code"], d["date_utc"], d["diff_to_typical"]) for d in past["largest_diffs"]]
    # المعتاد: التضخّم الأساسيّ √((0.1²+0.1²)/2)=0.1 · الوظائف √((121²+23²)/2)=87.09 · البطالة 0.1 · النفقات 0 ⟸ بلا معتاد.
    assert top[0] == (CORE[0], "2026-10-07", 2.0)
    assert top[1] == (CORE[0], "2026-09-11", 1.0) and top[2] == ("unemployment-rate", "2026-10-02", 1.0)
    assert top[3] == (NFP[0], "2026-10-02", pytest.approx(-0.26)) and top[4][2] is None
    assert past["largest_diffs"][3]["actual_minus_broker_forecast"] == -23 and past["largest_diffs"][3]["typical_n"] == 2
    await atom.stop()


async def test_missing_and_locked_bridge_do_not_break(tmp_path, monkeypatch):
    _, atom, _ = await _atom(tmp_path, monkeypatch)
    f = (await atom.refresh(NOW))["facts"]
    assert f["bridge_available"] is False and f["bridge_unavailable_reason"] == "BRIDGE_FILE_MISSING"
    assert f["fed_rate_current"] == 4.0
    await atom.stop()
    bridge = make_bridge(tmp_path / "locked.db", [("317675", CLAIMS[1], utc("2026-10-08 12:30"), "205")])
    holder = sqlite3.connect(bridge, timeout=0.1)
    holder.execute("BEGIN EXCLUSIVE")                       # الإكسبرت الحيّ يكتب: القاعدة مقفلة
    try:
        _, locked, _ = await _atom(tmp_path, monkeypatch, name="cal2.db", bridge=bridge)
        f = (await locked.refresh(NOW))["facts"]
        assert f["bridge_available"] is False and f["bridge_unavailable_reason"] == "BRIDGE_READ_FAILED"
        assert f["econ_calendar_available"] is False and f["econ_calendar_unavailable_reason"] == "ECON_READ_FAILED"
        assert f["actuals_from_bridge"] is None and f["fed_rate_current"] == 4.0
        await locked.stop()
    finally:
        holder.rollback()
        holder.close()


async def test_payload_contract_and_first_ten_scalars(tmp_path, monkeypatch):
    _, atom, _ = await _atom(tmp_path, monkeypatch)
    payload = await atom.refresh(NOW)
    assert set(payload) == {"id", "symbol", "status", "facts", "computed_at", "summary_ar", "source"}
    f = payload["facts"]
    assert f["fed_pricing_available"] is False and f["fed_pricing_unavailable_reason"]
    assert f["source_age_hours"] == pytest.approx(20.0) and f["source_server"] == "ICMarketsSC-Demo"
    assert list(f)[:10] == ["fed_rate_current", "fed_rate_previous", "fed_last_change_bp", "days_to_next_fomc",
                            "is_fomc_day", "minutes_to_next_high_impact", "high_impact_next_48h_count",
                            "fed_speeches_next_48h_count", "core_cpi_mm_actual_minus_forecast", "source_age_hours"]
    for key, value in list(f.items())[:10]:
        assert value is None or isinstance(value, (int, float, bool)) or (isinstance(value, str) and len(value) <= 24), key
    for kind, text, where in _walk(payload):
        words = set(re.split(r"[^a-z]+", text.lower()))
        assert not words & set(FORBIDDEN), (kind, where, text)
    await atom.stop()


async def test_missing_or_broken_history_does_not_break(tmp_path, monkeypatch):
    _, atom, bus = await _atom(tmp_path, monkeypatch, rows=None)
    payload = await atom.refresh(NOW)
    assert payload["status"] == "unavailable" and payload["facts"]["unavailable_reason"] == "SOURCE_FILE_MISSING"
    assert "غير متاحة" in payload["summary_ar"] and bus.payloads("knowledge.monetary.state")
    health = await atom.health_check()
    assert health.state.name == "DEGRADED" and "أخطاء قراءة=1" in health.message
    await atom.stop()
    path = tmp_path / "broken.db"
    path.write_bytes(b"not a database at all" * 50)
    _, broken, _ = await make_atom(118, {"db_path": str(path), "boot_delay_s": 3600.0})
    assert (await broken.refresh(NOW))["facts"]["unavailable_reason"] == "SOURCE_READ_FAILED"
    await broken.stop()


async def test_health_degrades_when_hourly_sync_stops_or_horizon_ends(tmp_path, monkeypatch):
    fresh = {"sync_mode": "hourly_ea"}
    _, atom, _ = await _atom(tmp_path, monkeypatch, meta=fresh)
    await atom.refresh(NOW)
    assert atom._exported == NOW - 20 * 3600
    atom._exported = NOW - 30 * 60                           # مزامنةٌ قبل نصف ساعة ⟸ سليمة
    health = await atom.health_check()
    assert health.state.name == "HEALTHY" and "الفائدة 4.0" in health.message and "قرارات=6" in health.message
    atom._exported = NOW - 151 * 60                          # أكثر من ساعتين ونصف ⟸ توقّفت
    health = await atom.health_check()
    assert health.state.name == "DEGRADED" and "مزامنة التقويم الساعيّة متوقّفة منذ 151 د" in health.message
    atom._exported = NOW
    atom._clock = lambda: utc("2026-11-21 00:00")            # بعد أبعد حدثٍ في القاعدة
    assert "أفق التقويم انتهى" in (await atom.health_check()).message
    await atom.stop()


async def test_pulse_boot_read_snapshot_restore(tmp_path, monkeypatch):
    monkeypatch.delenv("NQ_CALENDAR_HISTORY_DB", raising=False)
    monkeypatch.delenv("NQ_BRIDGE_DB", raising=False)
    path = make_db(tmp_path / "cal.db")
    _, atom, bus = await make_atom(118, {"db_path": path, "boot_delay_s": 0.0})
    for _ in range(100):                                     # القراءة الأولى عند الإقلاع (هنا بلا تأجيل)
        if bus.payloads("knowledge.monetary.state"):
            break
        await asyncio.sleep(0.02)
    assert bus.payloads("knowledge.monetary.state")
    await atom._on_pulse({"official_time": NOW})
    assert bus.payloads("knowledge.monetary.state")[-1]["computed_at"] == NOW
    await atom._on_pulse("not a pulse")
    assert atom._rejected == {"bad_pulse": 1}
    state = await atom.snapshot()
    _, other, _ = await _atom(tmp_path, monkeypatch, name="other.db")
    await other.restore(state)
    assert other._last["facts"]["fed_rate_current"] == 4.0 and other._published == 2
    await other.restore({"last": {"id": "other"}, "published": "x"})
    assert other._last["facts"]["fed_rate_current"] == 4.0
    await atom.stop()
    await other.stop()


# ── ٢٠٢٦-١٠-٠٨ (ختم المالك «NQ» — «عدّة مصادر تحت سقفٍ واحد»): تقويم ناسداك في الجسر — الفعليّ والإجماع ──────────
def make_econ(path, rows, fetched=NOW - 10 * 60):
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE econ_calendar(id TEXT PRIMARY KEY, event_date TEXT, time_et TEXT, scheduled_at REAL, "
                "country TEXT, event_name TEXT, actual TEXT, consensus TEXT, previous TEXT, fetched_at REAL, source TEXT)")
    for i, (name, at, actual, consensus, previous, *country) in enumerate(rows):
        con.execute("INSERT INTO econ_calendar VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    ("n%d" % i, at[:10], "", utc(at), (country or ["United States"])[0], name, actual, consensus,
                     previous, fetched, "nasdaq"))
    con.commit()
    con.close()
    return str(path)


PPI = ("producer-price-index-ex-food-energy-mm", "مؤشر أسعار المنتجين الأساسيين على أساس شهري")
ECON_ROWS = ROWS + [
    _row(*CLAIMS, "2026-09-11 12:30", actual=206.0, forecast=211.0, prev=206.0, digits=0, unit=0, mult=1, vid=400001),
    _row(*PPI, "2026-09-10 12:30", imp=2, actual=0.2, forecast=0.6, prev=0.2),
    _row("producer-price-index-ex-food-energy-yy", PPI[1], "2026-09-10 12:30", imp=1, actual=4.6, forecast=4.5, prev=4.2),
]
NASDAQ = [
    ("Initial Jobless Claims", "2026-09-11 12:30", "206K", "205K", "207K"),       # 08:30 نيويورك
    ("Core PPI", "2026-09-10 12:30", "0.2%", "0.3%", "0.2%"),                     # مبهم: يُحسم بالسابق ⟸ الشهريّ
    ("Core CPI (MoM)", "2026-09-11 12:30", "0.3%", "0.3%", "0.2%"),
    ("Core CPI (YoY)", "2026-09-11 12:30", "2.4%", "2.4%", "2.5%"),              # لا حدث سنويّ في التاريخ ⟸ غير مطابَق
    ("Nonfarm Payrolls", "2026-10-02 12:30", "29K", "50K", "22K"),
    ("Unemployment Rate", "2026-10-02 12:30", "4.3%", "4.2%", "4.1%"),            # يخالف التاريخ (4.2) ⟸ خلاف معلن
    ("Initial Jobless Claims", "2026-10-08 12:31", "203K", "195K", "206K"),       # ميتاتريدر بلا فعليّ ⟸ ناسداك يملأ
    ("Initial Jobless Claims (4-Week Avg)", "2026-10-08 12:30", "201K", "", "200K"),
    ("Fed Interest Rate Decision", "2026-09-16 18:00", "3.75%", "3.75%", "3.50%"),  # صيغة الحدّ الأدنى ⟸ لا يُؤخذ
    ("Core CPI (MoM)", "2026-10-09 12:30", "", "0.3%", "0.3%"),                   # القادم: الإجماع وحده
    ("CPI", "2026-10-08 12:30", "9.9%", "1.0%", "1.0%", "Japan"),                 # ليس أمريكيًّا
]


def test_nasdaq_value_and_name_parsing():
    import monetary_consensus as mc
    assert mc.parse_value("206K") == (206.0, "K") and mc.parse_value("0.2%") == (0.2, "%")
    assert mc.parse_value("-3.186M") == (-3.186, "M") and mc.parse_value("1,234K") == (1234.0, "K")
    assert mc.parse_value("4.00%-4.25%") is None and mc.parse_value("") is None
    assert mc.to_mt5((-3.186, "M"), {"multiplier": 2}) == -3.186 and mc.to_mt5((206.0, "K"), {"multiplier": 1}) == 206.0
    assert mc.to_mt5((1.2, "M"), {"multiplier": 1}) == 1200.0 and mc.to_mt5((0.2, "%"), {"multiplier": 0}) == 0.2
    assert mc.parse_name("Core CPI (MoM)") == ("core_cpi", "mm") and mc.parse_name("Core CPI") == ("core_cpi", None)
    assert mc.parse_name("Nonfarm Payrolls") == ("nfp", None) and mc.parse_name("Private Nonfarm Payrolls")[0] is None
    assert mc.parse_name("Initial Jobless Claims (4-Week Avg)")[0] is None and mc.parse_name("GDP (QoQ)") == ("gdp", "qq")


async def test_nasdaq_is_first_source_for_actual_and_consensus(tmp_path, monkeypatch):
    bridge = make_bridge(tmp_path / "brain.db", [])
    make_econ(bridge, NASDAQ)
    _, atom, _ = await _atom(tmp_path, monkeypatch, rows=ECON_ROWS, bridge=bridge)
    payload = await atom.refresh(NOW)
    f = payload["facts"]
    assert f["econ_calendar_available"] is True and f["econ_calendar_age_minutes"] == 10
    assert (f["econ_calendar_rows"], f["econ_calendar_matched"], f["econ_calendar_unmatched"]) == (10, 8, 2)
    assert {u["name"] for u in f["econ_calendar_unmatched_sample"]} == {"Core CPI (YoY)", "Initial Jobless Claims (4-Week Avg)"}
    core = f["releases"]["core_cpi_mm"]            # الإجماع الحقيقيّ والفرق عنه، وتوقّع الوسيط معه
    assert (core["actual"], core["actual_source"], core["consensus"], core["broker_forecast"]) == (0.3, "nasdaq", 0.3, 0.2)
    assert core["actual_minus_consensus"] == 0.0 and core["actual_minus_broker_forecast"] == pytest.approx(0.1)
    assert core["sources_disagree"] is False and core["other_actuals"] == {"history": 0.3}
    assert f["core_cpi_mm_actual_minus_forecast"] == 0.0 and f["core_cpi_mm_diff_basis"] == "consensus"
    unemp = f["releases"]["unemployment_rate"]
    assert (unemp["actual"], unemp["actual_source"], unemp["sources_disagree"]) == (4.3, "nasdaq", True)
    assert unemp["other_actuals"] == {"history": 4.2}
    disagree = {d["code"]: d["why"] for d in f["sources_disagree"]}
    assert disagree == {"unemployment-rate": "actual_differs", "fed-interest-rate-decision": "previous_convention_differs"}
    assert f["fed_rate_current"] == 4.0 and f["fed_last_change_bp"] == 25 and f["fed_rate_current_source"] == "history"
    last = f["last_release_surprise"]               # المطالبات 10-08: ميتاتريدر بلا فعليّ، وناسداك يملأ
    assert (last["code"], last["time_utc"], last["actual"], last["consensus"]) == (CLAIMS[0], "2026-10-08T12:30Z", 203.0, 195.0)
    assert last["actual_minus_consensus"] == 8.0 and last["actual_source"] == "nasdaq" and last["broker_forecast"] == 190.0
    assert f["high_impact_next_48h"][1]["consensus"] == 0.3   # القادم: الإجماع قبل الصدور
    past = f["last_30d_high_impact"]
    assert past["n_actual_from_nasdaq"] == 5 and past["n_with_actual"] == 7
    assert "آخر تضخّم أساسيّ 0.3 مقابل الإجماع 0.3" in payload["summary_ar"]
    assert "آخر إصدار مهمّ: مطالبات البطالة الأولية 203 مقابل الإجماع 195" in payload["summary_ar"]
    health = await atom.health_check()
    assert "ناسداك: صفوف=10 مطابَقة=8 غير مطابَقة=2 عمرها 10 د خلافات=2" in health.message
    await atom.stop()


def test_ambiguous_core_ppi_is_settled_by_previous():
    import monetary_consensus as mc
    at = utc("2026-09-10 12:30")
    rows = [{"event_code": code, "time_utc": at, "actual": actual, "actual_source": "history", "forecast": forecast,
             "prev": prev, "revised_prev": None, "digits": 1, "multiplier": 0}
            for code, actual, forecast, prev in ((PPI[0], 0.2, 0.6, 0.2), ("producer-price-index-ex-food-energy-yy", 4.6, 4.5, 4.2))]
    econ = {"available": True, "fetched_at": NOW, "rows": [
        {"id": "x", "name": "Core PPI", "at": at + 60, "actual": (0.2, "%"), "consensus": (0.3, "%"), "previous": (0.2, "%")}]}
    out = mc.merge([rows], econ)
    assert out["matched"] == 1 and out["unmatched"] == 0
    assert (rows[0]["consensus"], rows[0]["actual_source"], rows[0]["sources_disagree"]) == (0.3, "nasdaq", False)
    assert rows[1]["consensus"] is None and rows[1]["actual_source"] == "history" and rows[1]["broker_forecast"] == 4.5
    econ["rows"][0]["previous"] = (9.9, "%")                    # لا سابق يحسم ⟸ لا مطابقة (لا تخمين)
    fresh = [dict(r, actual_source="history", consensus=None) for r in rows]
    for r in fresh:
        r.pop("sources_disagree", None)
        r.pop("other_actuals", None)
    assert mc.merge([fresh], econ)["unmatched"] == 1 and fresh[0]["consensus"] is None
