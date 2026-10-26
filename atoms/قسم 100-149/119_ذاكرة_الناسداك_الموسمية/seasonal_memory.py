"""ذاكرة الناسداك الموسميّة (119) — بناء الذاكرة من القواعد، قراءةً فقط.

٢٠٢٦-١٠-٠٨ (ختم المالك «NQ» — المعرفة أوّلًا): «قبل كلّ شي لازم يعرف النظام هاد الشي ثمّ الباقي» — الوقت
والمواسم والعطل. حقائق خامٌ من تاريخ الناسداك نفسه (متوسّط · وسيط · نسبة الموجب · متوسّط المدى · عدد العيّنة)،
لا حكم فيها ولا جهة، ولا تدخل قرار الدخول.

المصادر (قراءةً فقط):
  شموع سي‑تريدر   `candles_history` (D1 وH1 للرمز) — اليوم «يوم الوسيط» كما في القاعدة، لا يُعاد تجميعه.
  تقويم ميتاتريدر  `calendar_history` — عطل أمريكا (sector 12) وقرارات الفائدة؛ وقته − 3 ساعات = غرينتش.

٢٠٢٦-١٠-٠٨ (ختم المالك «NQ» — المعرفة أوّلًا): التاريخ يُقرأ من 2014-09-22 لا من 2012 — مقيسٌ على القاعدة:
  · حتّى أسبوع 2014-09-19 فيها شمعة يومٍ سادسة كلّ أسبوع تبدأ الجمعة 21:00 غرينتش (~5 آلاف تِكّة، يومها «سبت»)،
    وآخر شمعة ساعة في الأسبوع مختومة الجمعة 23:00 غرينتش (بعد إغلاق السوق).
  · أكبر ساعات الحركة 12–13 بتوقيت نيويورك في 2012–2014، و9–10 من 2015 إلى اليوم (افتتاح نيويورك 9:30):
    الطوابع القديمة مزاحةٌ ثلاث ساعات، فيومها ليس يوم الوسيط وساعاتها ليست ساعات نيويورك.
  · من الأحد 2014-09-21 21:00 غرينتش تستقيم الشموع (خمسة أيّام، ومساء الأحد جزءٌ من الاثنين).
  والحدّ في `history_from` بالبيان. وشمعتا «سبت» بتِكّتين (2015-03-07 و2015-03-14) تُسقطان مع كلّ يوم عطلة أسبوع.
"""
from __future__ import annotations

import sqlite3
import statistics
import time
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from shared.owner_windows import broker_day_offset_s, new_york_offset_h

STATUS_OK = "ok"
STATUS_UNAVAILABLE = "unavailable"

PCT = 100.0
PCT_DIGITS = 4
SHARE_DIGITS = 1
BUILD_DIGITS = 3
DB_TIMEOUT_S = 5.0
EPOCH_ORDINAL = date(1970, 1, 1).toordinal()
ONE_DAY = timedelta(days=1)
#: السبت (5) والأحد (6) بيوم الوسيط: لا جلسة للناسداك.
WEEKEND_FROM = 5
FRIDAY = 4
#: الجمعة الثالثة من الشهر (انتهاء الخيارات الشهريّة) تقع حتمًا بين 15 و21 منه.
OPEX_FIRST_DAY = 15
OPEX_LAST_DAY = 21
MONTHS_IN_YEAR = 12
PERIOD_DAY = "D1"
PERIOD_HOUR = "H1"

#: وقت التقويم − 3 ساعات = غرينتش (ثبت على قرارات الفائدة: 14:00 نيويورك = 18:00/19:00 غرينتش).
# ٢٠٢٦-١٠-١٧ (ختم المالك «NQ»، المرحلة 1 الخطوة 4): كان `CAL_SHIFT_S = 3 * 3600` — ثابتٌ يخطئ ساعةً في أيّام الشتاء من التاريخ.


def cal_utc(server_ts: float) -> float:
    """وقت تقويم ميتاتريدر (ساعة الوسيط مكتوبةً كأنّها غرينتش) ⟵ غرينتش، بفرق الوسيط في تلك اللحظة."""
    return float(server_ts) - broker_day_offset_s(float(server_ts))


def cal_server(utc_ts: float) -> float:
    """العكس: لحظة غرينتش ⟵ وقتها بساعة الوسيط كما يكتبه تقويم ميتاتريدر (للتجارب والاستعلام)."""
    return float(utc_ts) + broker_day_offset_s(float(utc_ts))
US = "US"
HOLIDAY_SECTOR = 12
RATE_DECISION_LIKE = ("%قرار%", "%فائدة%")

PRE_HOLIDAY = "pre_holiday"
POST_HOLIDAY = "post_holiday"
HOLIDAY = "holiday"
FOMC = "fomc"
OPEX = "opex"
MONTH_END = "month_end"
MONTH_START = "month_start"
KINDS = (PRE_HOLIDAY, POST_HOLIDAY, HOLIDAY, FOMC, OPEX, MONTH_END, MONTH_START)

_SQL_CANDLES = ("SELECT period_start, open, high, low, close FROM candles_history "
                "WHERE symbol=? AND period=? AND period_start>=? AND period_start<? ORDER BY period_start")
_SQL_TODAY = ("SELECT open, high, low, close, period_start FROM candles_history WHERE symbol=? AND period=? "
              "AND period_start>=? AND period_start+?<=? ORDER BY period_start")

_NY_CACHE: dict[int, tuple[int, int]] = {}
_BROKER_CACHE: dict[int, tuple[int, int]] = {}


# ── الوقت ──────────────────────────────────────────────────────────────
def _per_day(fn: Any, cache: dict[int, tuple[int, int]], ts: float) -> int:
    """فرق التوقيت ثابتٌ طول اليوم إلّا يوم التحويل — يُحسب مرّتين لليوم بدل كلّ شمعة (82 ألف شمعة ساعة)،
    ويوم التحويل يُحسب لكلّ لحظة بدالّة المشروع نفسها (`shared/owner_windows`)."""
    key = int(ts // 86400)
    pair = cache.get(key)
    if pair is None:
        start = key * 86400
        pair = (fn(start), fn(start + 86400 - 1))
        cache[key] = pair
    return pair[0] if pair[0] == pair[1] else fn(ts)


def utc_date(ts: float) -> date:
    return date.fromordinal(EPOCH_ORDINAL + int(ts // 86400))


def broker_date(ts: float) -> date:
    """تاريخ يوم الوسيط الذي تقع فيه اللحظة (يومٌ يُغلق مع إغلاق نيويورك 17:00)."""
    return utc_date(ts + _per_day(broker_day_offset_s, _BROKER_CACHE, ts))


def broker_day_start(ts: float) -> float:
    return ts - ((ts + broker_day_offset_s(ts)) % 86400)


def ny_hour(ts: float) -> int:
    return int(((ts + _per_day(new_york_offset_h, _NY_CACHE, ts) * 3600) % 86400) // 3600)


def parse_date(text: Any) -> date | None:
    try:
        return date.fromisoformat(str(text).strip())
    except (TypeError, ValueError):
        return None


def years_before(day: date, years: int) -> date:
    try:
        return day.replace(year=day.year - years)
    except ValueError:                       # 29 شباط
        return day.replace(year=day.year - years, day=day.day - 1)


def next_weekday(day: date) -> date:
    day += ONE_DAY
    while day.weekday() >= WEEKEND_FROM:
        day += ONE_DAY
    return day


def prev_weekday(day: date) -> date:
    day -= ONE_DAY
    while day.weekday() >= WEEKEND_FROM:
        day -= ONE_DAY
    return day


def next_trading(day: date, cal: dict[str, Any]) -> date:
    closed = cal.get("closed") or set()
    day = next_weekday(day)
    while day in closed:
        day = next_weekday(day)
    return day


def prev_trading(day: date, cal: dict[str, Any]) -> date:
    closed = cal.get("closed") or set()
    day = prev_weekday(day)
    while day in closed:
        day = prev_weekday(day)
    return day


def covered(day: date, cal: dict[str, Any]) -> bool:
    """هل يعرف التقويم ما حول هذا اليوم (اليوم التالي داخل مداه)؟ وبلا تقويم: الأنواع بلا تقويم وحدها."""
    if not cal.get("available"):
        return True
    return cal["from"] <= day and next_weekday(day) <= cal["through"]


def date_kinds(day: date, cal: dict[str, Any], month_start: bool, month_end: bool) -> tuple[str, ...]:
    """أنواع اليوم الخاصّة — تعريفٌ واحد للتاريخ وللحظة الحيّة."""
    kinds: list[str] = []
    holidays = cal.get("holidays") or {}
    if day in holidays:
        kinds.append(HOLIDAY)
    else:
        if next_weekday(day) in holidays:
            kinds.append(PRE_HOLIDAY)
        if prev_weekday(day) in holidays:
            kinds.append(POST_HOLIDAY)
    if day in (cal.get("fomc") or set()):
        kinds.append(FOMC)
    if day.weekday() == FRIDAY and OPEX_FIRST_DAY <= day.day <= OPEX_LAST_DAY:
        kinds.append(OPEX)
    if month_end:
        kinds.append(MONTH_END)
    if month_start:
        kinds.append(MONTH_START)
    return tuple(kind for kind in KINDS if kind in kinds)


# ── القراءة ────────────────────────────────────────────────────────────
def _ro(path: str) -> sqlite3.Connection:
    return sqlite3.connect("file:%s?mode=ro" % Path(path).as_posix(), uri=True, timeout=DB_TIMEOUT_S)


def load_calendar(path: str) -> dict[str, Any]:
    """عطل أمريكا وقرارات الفائدة؛ وغياب القاعدة أو تعذّرها ⟸ «غير متاح» بسببه، لا انهيار."""
    if not path or not Path(path).is_file():
        return {"available": False, "reason": "calendar_db_missing"}
    try:
        con = _ro(path)
        try:
            holiday_rows = con.execute(
                "SELECT time_server, event_code, event_name FROM calendar_history "
                "WHERE country_code=? AND sector=? ORDER BY time_server", (US, HOLIDAY_SECTOR)).fetchall()
            rate_rows = con.execute(
                "SELECT time_server FROM calendar_history WHERE country_code=? "
                "AND event_name LIKE ? AND event_name LIKE ?", (US, *RATE_DECISION_LIKE)).fetchall()
            low, high = con.execute("SELECT MIN(time_server), MAX(time_server) FROM calendar_history").fetchone()
        finally:
            con.close()
    except sqlite3.Error as exc:
        return {"available": False, "reason": "calendar_db_error: %s" % exc}
    if low is None:
        return {"available": False, "reason": "calendar_empty"}
    holidays: dict[date, tuple[str, str]] = {}
    for stamp, code, name in holiday_rows:
        holidays.setdefault(utc_date(cal_utc(stamp)), (str(code or ""), str(name or "")))
    return {"available": True, "holidays": holidays,
            "fomc": {broker_date(cal_utc(stamp)) for (stamp,) in rate_rows},
            "from": utc_date(cal_utc(low)), "through": utc_date(cal_utc(high)),
            "closed": set(), "closed_codes": []}


def mark_closed(cal: dict[str, Any], traded: set[date], first: date, last: date) -> None:
    """أيّ عطلةٍ بلا جلسة؟ مقيسٌ لا مفترض (أكثر عطل أمريكا جلسةٌ قصيرة للناسداك، ورأس السنة والميلاد بلا شمعة):
    عطلةٌ مضت بين `first` و`last` (اليوم السابق لليوم الجاري) مغلقةٌ إن غابت شمعتها؛ والقادمة مغلقةٌ إن غابت شمعة
    نوعها في أكثر من نصف مرّاته على التاريخ."""
    if not cal.get("available"):
        return
    seen: dict[str, int] = {}
    missing: dict[str, int] = {}
    for day, (code, _) in cal["holidays"].items():
        if first <= day <= last and day.weekday() < WEEKEND_FROM:
            seen[code] = seen.get(code, 0) + 1
            if day not in traded:
                missing[code] = missing.get(code, 0) + 1
    codes = sorted(code for code, count in seen.items() if 2 * missing.get(code, 0) > count)
    cal["closed_codes"] = codes
    cal["closed"] = {day for day, (code, _) in cal["holidays"].items()
                     if (day not in traded if first <= day <= last else code in codes)}


def load_candles(path: str, symbol: str, start: date | None, cut: float) -> dict[str, list[tuple]]:
    """D1 وH1 للرمز قبل `cut` (بداية يوم الوسيط الجاري) — اليوم الجاري لا يدخل الذاكرة."""
    begin = 0 if start is None else (start.toordinal() - EPOCH_ORDINAL - 1) * 86400
    con = _ro(path)
    try:
        return {period: con.execute(_SQL_CANDLES, (symbol, period, begin, cut)).fetchall()
                for period in (PERIOD_DAY, PERIOD_HOUR)}
    finally:
        con.close()


def today_range(path: str, symbol: str, now: float) -> dict[str, Any]:
    """مدى يوم الوسيط الجاري حتّى آخر شمعة ساعة مغلقة قبل `now` في القاعدة. والقاعدة يكتبها جالب التاريخ
    دوريًّا (مقيس ١٠-٠٨: آخر كتابة 12:15 وآخر ساعة 11:00) — فتُذكر بداية آخر ساعة وعمر إغلاقها."""
    start = broker_day_start(now)
    try:
        if not path or not Path(path).is_file():
            return {"hours": 0, "range_pct": None, "reason": "history_db_missing"}
        con = _ro(path)
        try:
            rows = con.execute(_SQL_TODAY, (symbol, PERIOD_HOUR, start, 3600, now)).fetchall()
        finally:
            con.close()
    except sqlite3.Error as exc:
        return {"hours": 0, "range_pct": None, "reason": "history_db_error: %s" % exc}
    if not rows or rows[0][0] <= 0:
        return {"hours": 0, "range_pct": None}
    opened = rows[0][0]
    high = max(row[1] for row in rows)
    low = min(row[2] for row in rows)
    return {"hours": len(rows), "range_pct": round((high - low) / opened * PCT, PCT_DIGITS),
            "open": opened, "high": high, "low": low, "last_close": rows[-1][3],
            "last_bar_start": rows[-1][4], "last_bar_age_s": round(now - rows[-1][4] - 3600, 1)}


# ── الإحصاء ────────────────────────────────────────────────────────────
def day_stats(rows: list[tuple]) -> dict[str, Any]:
    """صفوف الأيّام (التاريخ، العائد٪، المدى٪، …) ⟸ متوسّط · وسيط · نسبة الموجب · متوسّط المدى · n."""
    if not rows:
        return {"mean_pct": None, "median_pct": None, "pos_pct": None, "range_pct": None, "n": 0}
    returns = [row[1] for row in rows]
    n = len(rows)
    return {"mean_pct": round(sum(returns) / n, PCT_DIGITS),
            "median_pct": round(statistics.median(returns), PCT_DIGITS),
            "pos_pct": round(PCT * sum(1 for value in returns if value > 0) / n, SHARE_DIGITS),
            "range_pct": round(sum(row[2] for row in rows) / n, PCT_DIGITS), "n": n}


def value_stats(values: list[float]) -> dict[str, Any]:
    if not values:
        return {"mean_pct": None, "median_pct": None, "pos_pct": None, "n": 0}
    n = len(values)
    return {"mean_pct": round(sum(values) / n, PCT_DIGITS),
            "median_pct": round(statistics.median(values), PCT_DIGITS),
            "pos_pct": round(PCT * sum(1 for value in values if value > 0) / n, SHARE_DIGITS), "n": n}


def daily_rows(candles: list[tuple], start: date | None) -> tuple[list[tuple], set[date]]:
    """(التاريخ، عائد إغلاق‑لإغلاق٪، المدى٪ من الافتتاح، الإغلاق، تاريخ اليوم السابق) لكلّ يوم تداول.
    أوّل يومٍ بذرةٌ لعائد ما بعده؛ وأيّام «السبت/الأحد» تُسقط ولا تقطع السلسلة."""
    rows: list[tuple] = []
    traded: set[date] = set()
    prev: tuple[date, float] | None = None
    for stamp, opened, high, low, close in candles:
        day = broker_date(stamp)
        if (start is not None and day < start) or day.weekday() >= WEEKEND_FROM or opened <= 0 or close <= 0:
            continue
        traded.add(day)
        if prev is not None:
            rows.append((day, (close / prev[1] - 1) * PCT, (high - low) / opened * PCT, close, prev[0]))
        prev = (day, close)
    return rows, traded


def month_table(rows: list[tuple], today: date) -> dict[int, dict[str, Any]]:
    """لكلّ شهرٍ تقويميّ: عائد الشهر (إغلاق آخر يومٍ منه ÷ إغلاق آخر يومٍ من الشهر قبله) على الأشهر المكتملة
    وحدها، ومتوسّط المدى اليوميّ لأيّامه المغلقة."""
    last_close: dict[tuple[int, int], float] = {}
    ranges: dict[int, list[float]] = {}
    for day, _, rng, close, _ in rows:
        last_close[(day.year, day.month)] = close
        ranges.setdefault(day.month, []).append(rng)
    returns: dict[int, list[float]] = {}
    for (year, month), close in last_close.items():
        if (year, month) >= (today.year, today.month):
            continue
        prev = (year, month - 1) if month > 1 else (year - 1, MONTHS_IN_YEAR)
        if prev in last_close:
            returns.setdefault(month, []).append((close / last_close[prev] - 1) * PCT)
    return {month: {"return": value_stats(returns.get(month, [])),
                    "daily_range_pct": round(sum(ranges[month]) / len(ranges[month]), PCT_DIGITS),
                    "days_n": len(ranges[month])} for month in ranges}


def hour_table(candles: list[tuple], start: date | None) -> tuple[dict[int, dict[str, Any]], int]:
    """لكلّ ساعةٍ بتوقيت نيويورك: الحركة٪ (إغلاق − افتتاح) و|الحركة|٪ ومدى الشمعة٪، وترتيبها بمتوسّط |الحركة|."""
    groups: dict[int, list[tuple[float, float]]] = {}
    for stamp, opened, high, low, close in candles:
        day = broker_date(stamp)
        if (start is not None and day < start) or day.weekday() >= WEEKEND_FROM or opened <= 0:
            continue
        groups.setdefault(ny_hour(stamp), []).append(((close - opened) / opened * PCT,
                                                      (high - low) / opened * PCT))
    table: dict[int, dict[str, Any]] = {}
    for hour, rows in groups.items():
        stats = value_stats([move for move, _ in rows])
        stats["abs_move_pct"] = round(sum(abs(move) for move, _ in rows) / len(rows), PCT_DIGITS)
        stats["range_pct"] = round(sum(rng for _, rng in rows) / len(rows), PCT_DIGITS)
        table[hour] = stats
    for rank, hour in enumerate(sorted(table, key=lambda h: -table[h]["abs_move_pct"]), 1):
        table[hour]["rank_by_abs_move"] = rank
    return table, sum(len(rows) for rows in groups.values())


def special_table(rows: list[tuple], cal: dict[str, Any]) -> dict[str, Any]:
    """كلّ نوعٍ من الأيّام الخاصّة مقابل الأيّام العاديّة (لا نوع لها). الشهر أوّلًا وآخرًا من الشموع نفسها،
    وآخر يومٍ مغلق بقاعدة أيّام التداول (ما بعده لم يُغلق بعد)."""
    labelled: dict[str, list[tuple]] = {kind: [] for kind in KINDS}
    normal: list[tuple] = []
    for index, row in enumerate(rows):
        day, prev_day = row[0], row[4]
        if not covered(day, cal):
            continue
        after = rows[index + 1][0] if index + 1 < len(rows) else next_trading(day, cal)
        kinds = date_kinds(day, cal, (prev_day.year, prev_day.month) != (day.year, day.month),
                           (after.year, after.month) != (day.year, day.month))
        for kind in kinds:
            labelled[kind].append(row)
        if not kinds:
            normal.append(row)
    return {"by_kind": {kind: day_stats(items) for kind, items in labelled.items()},
            "normal": day_stats(normal), "days_n": sum(1 for row in rows if covered(row[0], cal))}


MONTHS_IN_QUARTER = 3


def units_by_year(candles: list[tuple], start: date | None, today: date) -> dict[str, Any]:
    """٢٠٢٦-١٠-١٧ (ختم المالك «NQ»، الخطوة 17: «شو صار بالربع الأخير بالسنوات الماضية … الشهر 10 من سنين ماضية»):
    الشهر الحاليّ والربع الحاليّ في كلّ سنة — افتتاح · إغلاق · أعلى · أدنى · التغيّر٪ · المدى٪ · الإغلاق فوق الافتتاح أم تحته؛ والسنة الحاليّة
    حتّى أمس وحدها (`complete=False`)."""
    quarter = (today.month - 1) // MONTHS_IN_QUARTER + 1
    groups: dict[str, dict[int, list[tuple]]] = {"month": {}, "quarter": {}}
    for stamp, opened, high, low, close in candles:
        day = broker_date(stamp)
        if (start is not None and day < start) or day.weekday() >= WEEKEND_FROM or opened <= 0 or close <= 0:
            continue
        if day.month == today.month:
            groups["month"].setdefault(day.year, []).append((day, opened, high, low, close))
        if (day.month - 1) // MONTHS_IN_QUARTER + 1 == quarter:
            groups["quarter"].setdefault(day.year, []).append((day, opened, high, low, close))
    out: dict[str, Any] = {"month_number": today.month, "quarter_number": quarter}
    for unit, years in groups.items():
        table = {}
        for year, rows in sorted(years.items()):
            rows.sort()
            o, c = rows[0][1], rows[-1][4]
            h, lo = max(r[2] for r in rows), min(r[3] for r in rows)
            table[year] = {"open": o, "close": c, "high": h, "low": lo, "days_n": len(rows),
                           "change_pct": round((c / o - 1) * PCT, PCT_DIGITS),
                           "range_pct": round((h - lo) / o * PCT, PCT_DIGITS),
                           "close_vs_open": "higher" if c > o else "lower" if c < o else "equal",
                           "complete": year < today.year}
        out[unit] = table
    return out


def _unavailable(reason: str, path: str, began: float) -> dict[str, Any]:
    return {"status": STATUS_UNAVAILABLE, "reason": reason, "path": path,
            "build_s": round(time.perf_counter() - began, BUILD_DIGITS)}


def build_memory(history_db: str, calendar_db: str, symbol: str, start: date | None,
                 recent_years: int, now: float) -> dict[str, Any]:
    """الذاكرة كلّها عند اللحظة `now` من الأيّام المغلقة قبل يومها وحدها. ثقيلة ⟸ تُنادى في خيطٍ منفصل."""
    began = time.perf_counter()
    cut = broker_day_start(now)
    today = broker_date(now)
    if not history_db or not Path(history_db).is_file():
        return _unavailable("history_db_missing", history_db, began)
    try:
        candles = load_candles(history_db, symbol, start, cut)
    except sqlite3.Error as exc:
        return _unavailable("history_db_error: %s" % exc, history_db, began)
    rows, traded = daily_rows(candles[PERIOD_DAY], start)
    if not rows:
        return _unavailable("no_closed_days", history_db, began)
    cal = load_calendar(calendar_db)
    mark_closed(cal, traded, min(traded), today - ONE_DAY)
    recent_from = years_before(today, recent_years)
    hours, hours_n = hour_table(candles[PERIOD_HOUR], start)
    return {
        "status": STATUS_OK, "built_at": now, "cut": cut, "today": today, "symbol": symbol,
        "history_from": rows[0][4], "history_through": rows[-1][0], "days_n": len(rows), "hours_n": hours_n,
        "recent_years": recent_years, "recent_from": recent_from,
        "weekday_all": {wd: day_stats([r for r in rows if r[0].weekday() == wd]) for wd in range(WEEKEND_FROM)},
        "weekday_recent": {wd: day_stats([r for r in rows if r[0].weekday() == wd and r[0] >= recent_from])
                           for wd in range(WEEKEND_FROM)},
        "month": month_table(rows, today), "hour": hours, "hours_ranked": len(hours),
        "special": special_table(rows, cal), "calendar": cal,
        "by_year": units_by_year(candles[PERIOD_DAY], start, today),
        "build_s": round(time.perf_counter() - began, BUILD_DIGITS),
    }
