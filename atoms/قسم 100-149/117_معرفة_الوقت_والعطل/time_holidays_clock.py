"""تقويم التداول — شقيق الذرّة 117 (دوالّ خالصة بلا حالة، وقارئ التقويم للقراءة فقط).

٢٠٢٦-١٠-٠٨ (ختم المالك «NQ» — المعرفة أوّلًا): حقائق خام عن الوقت، لا تدخل قرار الدخول.

٢٠٢٦-١٠-٠٩ (ختم المالك «NQ» — الوقت من مصدرٍ واحد): الساعة نفسها — الجلسات والتوقيت الصيفيّ وقواعد البورصة وأيّام
التداول ويوم الوسيط — نُقلت من هنا كما هي إلى `shared/market_clock` لتقرأها 117 و158 و159 من مكانٍ واحد. وبقي هنا
ما يخصّ 117 وحدها: تقويم ميتاتريدر وجداول عطله، وانتهاء الخيارات.

العطل الأمريكيّة: تقويم ميتاتريدر المحفوظ يُقرأ (قراءةً فقط) ويشهد ويسمّي، وقواعد بورصة نيويورك المنشورة تحدّد
يوم الإغلاق — مقيس اليوم: قائمة التقويم عطل الحكومة الفيدراليّة (مكتب العمل) لا البورصة، بلا «الجمعة العظيمة»،
ويكتبها السكربت مرّةً عند تشغيله فأفقها 2026-10-21 (لا عيد شكرٍ فيها). ويوما كولومبوس والمحاربين القدامى عطلتا
مصارف والبورصة تعمل فيهما — يُعرفان ولا يُعدّان عطلة سوق. وبلا تقويمٍ تُعلَن العطل «غير متاحة» (انظر `atom.py`).
"""
from __future__ import annotations

import sqlite3
from datetime import date, timedelta
from pathlib import Path
from typing import Any

# ٢٠٢٦-١٠-١٧ (ختم المالك «NQ»، المرحلة 1 الخطوة 4): التاريخ من ساعة الوسيط بفرقه في كلّ لحظة، لا بالعيار الثابت (10800).
from shared.owner_windows import broker_day_offset_s
from shared.market_clock import (DECEMBER, FRIDAY, GOOD_FRIDAY, NEW_YEAR, NYSE_RULES, SATURDAY, SOURCE_RULES,
                                 THANKSGIVING, day_iso, is_trading_day, nth_weekday, nyse_holidays)

SOURCE_CALENDAR = "mt5_calendar"
SOURCE_BOTH = SOURCE_CALENDAR + "+" + SOURCE_RULES
STATUS_OK = "ok"
STATUS_UNAVAILABLE = "unavailable"
REASON_MISSING = "missing_file"
REASON_READ = "read_error"
DB_TIMEOUT_S = 3.0
READ_ERROR_CHARS = 120
OPEX_MONTH_SCAN = 3

HOLIDAY_SECTOR = 12                # قطاع «العطل» في تقويم ميتاتريدر
HOLIDAY_COUNTRIES = ("US", "GB", "JP")
BANK_ONLY_CODES = frozenset({"columbus-day", "veterans-day"})
RULE_NAMES_AR = {
    NEW_YEAR: "رأس السنة الميلادية الجديدة", "birthday-of-martin-luther-king": "عيد ميلاد مارتن لوثر كينغ",
    "washingtons-birthday": "عيد ميلاد واشنطن", GOOD_FRIDAY: "الجمعة العظيمة", "memorial-day": "يوم الذكرى",
    "juneteenth-national-independence-day": "عيد التحرّر (جونتينث)", "independence-day": "عيد الاستقلال",
    "labor-day": "عيد العمال", THANKSGIVING: "عيد الشكر", "christmas-day": "عيد الميلاد",
}
OPEX_NTH = 3                        # انتهاء الخيارات الشهريّ: الجمعة الثالثة (أو يوم التداول قبلها إن كانت عطلة)


# ── انتهاء الخيارات ─────────────────────────────────────────────────────────
def opex_date(year: int, month: int, holidays: Any) -> date:
    day = nth_weekday(year, month, FRIDAY, OPEX_NTH)
    while not is_trading_day(day, holidays):
        day -= timedelta(days=1)
    return day


def next_opex(today: date, holidays: Any) -> date | None:
    year, month = today.year, today.month
    for _ in range(OPEX_MONTH_SCAN):
        day = opex_date(year, month, holidays)
        if day >= today:
            return day
        year, month = (year + 1, 1) if month == DECEMBER else (year, month + 1)
    return None


# ── التقويم ─────────────────────────────────────────────────────────────────
def holiday_tables(cal: dict[str, Any], years: tuple[int, ...]) -> tuple[dict, dict, dict, dict]:
    """(عطل السوق الأمريكيّ {تاريخ: (اسم، مصدر)}، عطلٌ فيدراليّة والبورصة تعمل، عطل لندن، عطل طوكيو) — أيّام العمل.

    ٢٠٢٦-١٠-٠٨ (ختم المالك «NQ» — المعرفة أوّلًا): مقيس على القاعدة الحيّة (2017–2026): قائمتها الأمريكيّة عطل
    الحكومة الفيدراليّة (مصدرها مكتب العمل) لا البورصة — تطابق قواعد البورصة في كلّ سنة إلّا الجمعة العظيمة (غائبة
    دائمًا) وثلاثة أيّام فيدراليّة كانت البورصة فيها تعمل (2021-06-18 · 2021-12-31 · 2025-01-21)، وغاب منها
    2021-12-24 والبورصة مغلقة. فعطلة السوق = قواعد البورصة، والتقويم يشهد لها («المصدران معًا») ويحمل أسماءها؛
    ويومه الذي تخالفه القواعد عطلةٌ فيدراليّة والبورصة تعمل؛ ورمزٌ لا تعرفه القواعد يُؤخذ من التقويم كما هو."""
    rows = cal.get("rows") or {}
    us_rows = rows.get("US") or []
    known_codes = {NEW_YEAR, GOOD_FRIDAY, *(rule[0] for rule in NYSE_RULES)}
    tables: dict[str, dict[date, str]] = {}
    market: dict[date, tuple[str, str]] = {}
    federal: dict[date, str] = {}
    listed: dict[date, str] = {}
    for country in HOLIDAY_COUNTRIES:
        for day_text, code, name in rows.get(country) or []:
            day = date.fromisoformat(day_text)
            if day.weekday() >= SATURDAY:
                continue
            if country != "US":
                tables.setdefault(country, {})[day] = name
            elif code in BANK_ONLY_CODES:
                federal[day] = name
            elif code in known_codes:
                listed[day] = name
            else:
                market[day] = (name, SOURCE_CALENDAR)
    if us_rows:
        names = {code: name for _, code, name in us_rows}
        for year in years:
            for day, code in nyse_holidays(year).items():
                market[day] = (names.get(code) or RULE_NAMES_AR.get(code, code),
                               SOURCE_BOTH if day in listed else SOURCE_RULES)
        for day, name in listed.items():
            if day.year in years and day not in market:
                federal[day] = name
    return market, federal, tables.get("GB", {}), tables.get("JP", {})


def load_calendar(path: str, server_offset_s: int, now: float) -> dict[str, Any]:
    """قراءة عطل التقويم (قراءةً فقط) — تُنادى في خيطٍ منفصل. وقت التقويم = غرينتش + فرق الخادم الثابت."""
    base = {"path": path, "loaded_at": now, "server_offset_s": server_offset_s}
    file = Path(path)
    if not file.is_file():
        return {**base, "status": STATUS_UNAVAILABLE, "reason": REASON_MISSING}
    try:
        con = sqlite3.connect("file:%s?mode=ro" % file.as_posix(), uri=True, timeout=DB_TIMEOUT_S)
        try:
            marks = ",".join("?" * len(HOLIDAY_COUNTRIES))
            raw = con.execute(
                "SELECT country_code, event_code, event_name, time_server FROM calendar_history "
                "WHERE sector=? AND country_code IN (%s) ORDER BY time_server" % marks,
                (HOLIDAY_SECTOR, *HOLIDAY_COUNTRIES)).fetchall()
            last, total = con.execute("SELECT MAX(time_server), COUNT(*) FROM calendar_history").fetchone()
            try:
                meta = dict(con.execute("SELECT key, value FROM export_meta").fetchall())
            except sqlite3.Error:
                meta = {}
        finally:
            con.close()
    except sqlite3.Error as exc:
        return {**base, "status": STATUS_UNAVAILABLE, "reason": "%s: %s" % (REASON_READ, str(exc)[:READ_ERROR_CHARS])}
    rows: dict[str, list[list[str]]] = {country: [] for country in HOLIDAY_COUNTRIES}
    for country, code, name, stamp in raw:
        if stamp is not None and country in rows:
            rows[country].append([day_iso(stamp - broker_day_offset_s(stamp)), str(code or ""), str(name or code or "")])
    return {**base, "status": STATUS_OK, "reason": None, "rows": rows,
            "horizon": day_iso(last - broker_day_offset_s(last)) if last else None, "rows_total_n": int(total or 0),
            "export_offset_s": _int_or_none(meta.get("server_offset_s_at_export")),
            "exported_at": _int_or_none(meta.get("exported_at_utc"))}


def _int_or_none(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
