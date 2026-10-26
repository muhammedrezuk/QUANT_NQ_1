"""ساعة السوق — المصدر الواحد للوقت في المنظومة: الجلسات · التوقيت الصيفيّ · يوم السوق · يوم الوسيط.

٢٠٢٦-١٠-٠٩ (ختم المالك «NQ» — الوقت من مصدرٍ واحد): ختم المالك «نعتمد ذرّة الوقت، ونصحّح محلّل الجلسات ليقرأ
التوقيت الصحيح، فلا يبقى في المنظومة رقمان متعارضان للوقت». كانت الجلسات تُحسب في مكانين: شقيق الذرّة 117
بالتوقيت الصيفيّ الصحيح، والذرّة 158 بساعات غرينتش ثابتة (آسيا 0–9 · لندن 7–16 · نيويورك 12–21) تخطئ ساعةً
نصف السنة؛ والذرّة 159 تعدّ اليوم والأسبوع والشهر بغرينتش. فنُقل حساب 117 إلى هنا كما هو، وتقرؤه 117 و158 و159.

التوقيت الصيفيّ ويوم الوسيط: من `shared/owner_windows` نفسه (قاعدتا أوروبا وأمريكا الرسميّتان) — فمفسّر المشروع
يحمل `zoneinfo` بلا قاعدة مناطق (`tzdata`). وطوكيو +9 ثابتة (اليابان بلا صيفيّ).
عطل بورصة نيويورك هنا بقواعدها المنشورة وحدها (دوالّ خالصة بلا قراءة). وتقويم ميتاتريدر (يشهد للقواعد ويحمل عطل
لندن وطوكيو) يقرؤه شقيق 117 وحده ويمرّر جداوله إلى `market_sessions`؛ ومن لا يملكه يمشي على القواعد ويُعلن ذلك.
"""
from __future__ import annotations

import calendar
from datetime import date, datetime, timedelta, timezone
from functools import lru_cache
from typing import Any, NamedTuple

from shared.owner_windows import broker_day_offset_s, london_offset_h, new_york_offset_h

CITY_NEW_YORK = "new_york"
CITY_LONDON = "london"
CITY_TOKYO = "tokyo"
TOKYO_OFFSET_H = 9
NY_SUMMER_OFFSET_H = -4                    # نيويورك صيفًا (وإلّا −5)
LONDON_SUMMER_OFFSET_H = 1                 # لندن صيفًا (وإلّا 0)
SECONDS_PER_HOUR = 3600
SECONDS_PER_DAY = 86400

MONDAY, THURSDAY, FRIDAY, SATURDAY, SUNDAY = 0, 3, 4, 5, 6
DECEMBER = 12
QUARTER_MONTHS = (3, 6, 9, 12)
WEEK_DAYS = 7
WEEKDAY_NAMES = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")

ASIA_OPEN_MIN, ASIA_CLOSE_MIN = 9 * 60, 15 * 60                  # طوكيو بتوقيتها
LONDON_OPEN_MIN, LONDON_CLOSE_MIN = 8 * 60, 16 * 60 + 30         # لندن بتوقيتها
CASH_OPEN_MIN, CASH_CLOSE_MIN = 9 * 60 + 30, 16 * 60             # نيويورك النقديّة بتوقيتها
EARLY_CLOSE_MIN = 13 * 60                                         # الإغلاق المبكّر لبورصة نيويورك
GLOBEX_HALT_MIN, GLOBEX_REOPEN_MIN = 17 * 60, 18 * 60            # استراحة عقد الناسداك اليوميّة

SESSION_ASIA = "asia_tokyo"
SESSION_LONDON = "london"
SESSION_NY_CASH = "new_york_cash"
SESSION_OVERLAP = "london_ny_overlap"
SESSION_GLOBEX = "nq_globex"
SESSION_CLOSED = "closed"
#: الجلسة «الآن» = أوّل ما يُفتح بهذا الترتيب.
SESSION_ORDER = (SESSION_OVERLAP, SESSION_NY_CASH, SESSION_LONDON, SESSION_ASIA, SESSION_GLOBEX)

SOURCE_RULES = "nyse_rules"
NEXT_DAY_SCAN = 14                 # أطول فجوة بين يومَي تداول أقلّ من أسبوع؛ والمسح أسبوعان
NEW_YEAR = "new-years-day"
GOOD_FRIDAY = "good-friday"
THANKSGIVING = "thanksgiving-day"
#: قواعد عطل بورصة نيويورك المنشورة: (الرمز، الشهر، اليوم الثابت، يوم الأسبوع، ترتيبه، أوّل سنة).
#: الثابتة تُنقل: السبت ⟵ الجمعة قبله، والأحد ⟵ الاثنين بعده؛ ورأس السنة يوم سبت لا يُنقل (قاعدة البورصة).
NYSE_RULES = (
    ("birthday-of-martin-luther-king", 1, None, MONDAY, 3, None),
    ("washingtons-birthday", 2, None, MONDAY, 3, None),
    ("memorial-day", 5, None, MONDAY, -1, None),
    ("juneteenth-national-independence-day", 6, 19, None, None, 2022),
    ("independence-day", 7, 4, None, None, None),
    ("labor-day", 9, None, MONDAY, 1, None),
    (THANKSGIVING, 11, None, THURSDAY, 4, None),
    ("christmas-day", 12, 25, None, None, None),
)
#: الإغلاق المبكّر 13:00 نيويورك: (الشهر، اليوم) إن كان يوم عمل وليس عطلة — وفوقهما الجمعة بعد عيد الشكر.
EARLY_CLOSE_DAYS = ((7, 3), (12, 24))

# خوارزميّة «ميوس/جونز/بوتشر» لأحد الفصح الغريغوريّ — ثوابتها جزءٌ من تعريفها لا عيار.
_E_CYCLE = 19
_E_CENTURY_DIV = 4
_E_SOLAR = (8, 25)
_E_LUNAR_DIV = 3
_E_EPACT = (15, 30)
_E_WEEK = (32, 7)
_E_CORR = (11, 22, 451)
_E_MONTH = (114, 31)
GOOD_FRIDAY_BEFORE_EASTER = 2
# ٢٠٢٦-١٠-٠٩ (ختم المالك «NQ» — الوقت من مصدرٍ واحد): 158 و159 تسألان عند كلّ شمعة، فجداول القواعد تُحفظ
# بعد حسابها مرّة (سنواتٌ معدودة — لا نموّ بلا حدّ). و«بلا عطل» لمن لا يعرف عطل لندن وطوكيو.
RULE_YEARS_CACHED = 64
NO_HOLIDAYS: frozenset = frozenset()
# ٢٠٢٦-١٠-٠٩ (ختم المالك «NQ» — الوقت من مصدرٍ واحد): قاعدتا `owner_windows` تبحثان عن أحد التحويل من جديد عند كلّ
# نداء (مقيس: 90٪ من زمن الجلسات، ~0.5 مللي ثانية للّحظة). والتحويل يقع على رأس ساعة غرينتش دائمًا (01:00 لندن ·
# 07:00 و06:00 نيويورك) فالفرق ثابتٌ داخل كلّ ساعة: يُسأل عنه مرّةً لكلّ ساعة ويُحفظ. القاعدة نفسها لا تُكرَّر هنا.
OFFSET_HOURS_CACHED = 4096


def tokyo_offset_h(_epoch_s: float) -> int:
    return TOKYO_OFFSET_H


_OFFSET_RULES = {CITY_NEW_YORK: new_york_offset_h, CITY_LONDON: london_offset_h, CITY_TOKYO: tokyo_offset_h}


@lru_cache(maxsize=OFFSET_HOURS_CACHED)
def _hour_offset_h(city: str, hour_index: int) -> int:
    return _OFFSET_RULES[city](float(hour_index * SECONDS_PER_HOUR))


def _city_offset(city: str):
    def offset_h(epoch_s: float) -> int:
        return _hour_offset_h(city, int(float(epoch_s) // SECONDS_PER_HOUR))
    return offset_h


OFFSET_FNS = {city: _city_offset(city) for city in _OFFSET_RULES}


def local_time(epoch_s: float, city: str) -> datetime:
    """الساعة الجداريّة للمدينة (بلا منطقة) عند لحظةٍ بغرينتش."""
    return (datetime.fromtimestamp(float(epoch_s), timezone.utc).replace(tzinfo=None)
            + timedelta(hours=OFFSET_FNS[city](float(epoch_s))))


def local_to_utc(day: date, minute: int, city: str) -> float:
    """لحظة غرينتش لدقيقةٍ جداريّة في يومٍ بتوقيت المدينة (الساعات المعنيّة هنا لا تقع في ساعة التحويل)."""
    wall = calendar.timegm(day.timetuple()) + minute * 60
    guess = wall - OFFSET_FNS[city](wall) * 3600
    return float(wall - OFFSET_FNS[city](guess) * 3600)


def hhmm(epoch_s: float) -> str:
    return datetime.fromtimestamp(float(epoch_s), timezone.utc).strftime("%H:%M")


def day_iso(epoch_s: float) -> str:
    return datetime.fromtimestamp(float(epoch_s), timezone.utc).date().isoformat()


def clock_offsets(epoch_s: float) -> dict[str, Any]:
    """٢٠٢٦-١٠-٠٩ (ختم المالك «NQ» — الوقت من مصدرٍ واحد): الصيفيّ وفرقا نيويورك ولندن عن غرينتش — بأسماء حقائق 117."""
    new_york, london = OFFSET_FNS[CITY_NEW_YORK](epoch_s), OFFSET_FNS[CITY_LONDON](epoch_s)
    return {"is_dst_new_york": new_york == NY_SUMMER_OFFSET_H, "is_dst_london": london == LONDON_SUMMER_OFFSET_H,
            "utc_offset_new_york_h": new_york, "utc_offset_london_h": london}


class BrokerDay(NamedTuple):
    day: date
    start_utc: int
    offset_h: int
    hour: int


def broker_day(epoch_s: float) -> BrokerDay:
    """٢٠٢٦-١٠-٠٩ (ختم المالك «NQ» — الوقت من مصدرٍ واحد): يوم الوسيط (يُغلق مع إغلاق نيويورك 17:00؛ ساعة الخادم
    = نيويورك + 7) — تاريخه وبدايته بغرينتش وفرقه وساعته. عليه يبني 103 شموع الأربع ساعات واليوم، وعليه شارت المالك."""
    offset = broker_day_offset_s(float(epoch_s))
    shifted = datetime.fromtimestamp(float(epoch_s) + offset, timezone.utc)
    return BrokerDay(shifted.date(), int(epoch_s - ((epoch_s + offset) % SECONDS_PER_DAY)),
                     offset // SECONDS_PER_HOUR, shifted.hour)


# ── قواعد بورصة نيويورك ─────────────────────────────────────────────────────
def easter(year: int) -> date:
    a = year % _E_CYCLE
    b, c = divmod(year, 100)
    d, e = divmod(b, _E_CENTURY_DIV)
    f = (b + _E_SOLAR[0]) // _E_SOLAR[1]
    g = (b - f + 1) // _E_LUNAR_DIV
    h = (_E_CYCLE * a + b - d - g + _E_EPACT[0]) % _E_EPACT[1]
    i, k = divmod(c, _E_CENTURY_DIV)
    weekday_shift = (_E_WEEK[0] + 2 * e + 2 * i - h - k) % _E_WEEK[1]
    m = (a + _E_CORR[0] * h + _E_CORR[1] * weekday_shift) // _E_CORR[2]
    month, day = divmod(h + weekday_shift - _E_WEEK[1] * m + _E_MONTH[0], _E_MONTH[1])
    return date(year, month, day + 1)


def nth_weekday(year: int, month: int, weekday: int, nth: int) -> date:
    """يوم الأسبوع بترتيبه في الشهر (nth ≥ 1) أو الأخير (nth = −1)."""
    days = [date(year, month, d) for d in range(1, calendar.monthrange(year, month)[1] + 1)
            if date(year, month, d).weekday() == weekday]
    return days[nth - 1] if nth > 0 else days[-1]


def _observed(day: date) -> date:
    if day.weekday() == SATURDAY:
        return day - timedelta(days=1)
    if day.weekday() == SUNDAY:
        return day + timedelta(days=1)
    return day


def nyse_holidays(year: int) -> dict[date, str]:
    """عطل بورصة نيويورك لسنةٍ بقواعدها المنشورة: {التاريخ: الرمز}."""
    return dict(_nyse_table(year))


@lru_cache(maxsize=RULE_YEARS_CACHED)
def _nyse_table(year: int) -> tuple[tuple[date, str], ...]:
    out: dict[date, str] = {}
    new_year = date(year, 1, 1)
    if new_year.weekday() != SATURDAY:
        out[_observed(new_year)] = NEW_YEAR
    out[easter(year) - timedelta(days=GOOD_FRIDAY_BEFORE_EASTER)] = GOOD_FRIDAY
    for code, month, fixed, weekday, nth, since in NYSE_RULES:
        if since is not None and year < since:
            continue
        day = _observed(date(year, month, fixed)) if fixed else nth_weekday(year, month, weekday, nth)
        out[day] = code
    return tuple(out.items())


@lru_cache(maxsize=RULE_YEARS_CACHED)
def rule_holidays(years: tuple[int, ...]) -> frozenset:
    """٢٠٢٦-١٠-٠٩ (ختم المالك «NQ» — الوقت من مصدرٍ واحد): أيّام عطل البورصة بقواعدها وحدها لسنواتٍ — لمن لا تقويم له."""
    return frozenset(day for year in years for day, _code in _nyse_table(year))


def is_early_close(day: date) -> bool:
    """إغلاق مبكّر 13:00 نيويورك بقواعد البورصة: 3 تمّوز · الجمعة بعد عيد الشكر · 24 كانون الأوّل — يوم عمل لا عطلة."""
    if day.weekday() >= SATURDAY or day in nyse_holidays(day.year):
        return False
    if (day.month, day.day) in EARLY_CLOSE_DAYS:
        return True
    month, weekday, nth = next((m, w, n) for code, m, _, w, n, _ in NYSE_RULES if code == THANKSGIVING)
    return day == nth_weekday(day.year, month, weekday, nth) + timedelta(days=1)


#: ٢٠٢٦-١٠-١٧ (ختم المالك «nq»): عطلتا البنوك الأمريكيّة اللتان تعمل فيهما البورصة — كولومبوس (الاثنين الثاني من تشرين الأوّل) والمحاربون
#: القدامى (11 تشرين الثاني؛ الأحد ⟵ الاثنين، والسبت لا يُنقل في المصارف الفيدراليّة).
COLUMBUS = "columbus-day"
VETERANS = "veterans-day"
EARLY_CLOSE = "early-close"
OCTOBER, NOVEMBER, VETERANS_DAY = 10, 11, 11


def bank_only_holidays(year: int) -> dict[date, str]:
    out = {nth_weekday(year, OCTOBER, MONDAY, 2): COLUMBUS}
    veterans = date(year, NOVEMBER, VETERANS_DAY)
    if veterans.weekday() == SUNDAY:
        veterans += timedelta(days=1)
    if veterans.weekday() < SATURDAY:
        out[veterans] = VETERANS
    return out


def no_trade_day(epoch_s: float) -> str | None:
    """قانون الأيّام (ختم المالك «nq» ٢٠٢٦-١٠-١٧): لا تداول لأيّ رمزٍ — والبتكوين معها — يوم عطلة البورصة أو البنوك الأمريكيّة أو الإغلاق
    المبكّر (15 يومًا في السنة). اليوم يوم الوسيط (يبدأ مع افتتاح 18:00 نيويورك ⟸ ساعة المالك) — فليلة العطلة من يومها. يعيد رمزها أو None."""
    day = broker_day(epoch_s)[0]
    code = nyse_holidays(day.year).get(day) or bank_only_holidays(day.year).get(day)
    if code:
        return code
    return EARLY_CLOSE if is_early_close(day) else None


# ── أيّام التداول ───────────────────────────────────────────────────────────
def is_trading_day(day: date, holidays: Any) -> bool:
    return day.weekday() < SATURDAY and day not in holidays


def next_weekday(day: date) -> date:
    day += timedelta(days=1)
    while day.weekday() >= SATURDAY:
        day += timedelta(days=1)
    return day


def month_trading_days(year: int, month: int, holidays: Any) -> list[date]:
    return [date(year, month, d) for d in range(1, calendar.monthrange(year, month)[1] + 1)
            if is_trading_day(date(year, month, d), holidays)]


class MarketDay(NamedTuple):
    is_trading_day: bool
    is_week_start: bool
    is_week_end: bool
    is_month_start: bool
    is_month_end: bool
    trading_day_of_month: int | None
    trading_days_in_month: int


def market_day(day: date, holidays: Any) -> MarketDay:
    """٢٠٢٦-١٠-٠٩ (ختم المالك «NQ» — الوقت من مصدرٍ واحد): موضع اليوم في أسبوع التداول وشهره — أوّل يوم تداول وآخره
    (لا الاثنين والجمعة ولا أوّل الشهر وآخره بالتقويم). تعريف 117 نفسه، وتقرؤه 159."""
    trading = is_trading_day(day, holidays)
    month_days = month_trading_days(day.year, day.month, holidays)
    monday = day - timedelta(days=day.weekday())
    week_days = [d for d in (monday + timedelta(days=n) for n in range(SATURDAY)) if is_trading_day(d, holidays)]
    return MarketDay(trading, trading and day == week_days[0], trading and day == week_days[-1],
                     trading and day == month_days[0], trading and day == month_days[-1],
                     month_days.index(day) + 1 if trading else None, len(month_days))


# ── الجلسات ─────────────────────────────────────────────────────────────────
def _minute(local: datetime) -> int:
    return local.hour * 60 + local.minute


def _within(local: datetime, start: int, end: int, holidays: Any) -> bool:
    return is_trading_day(local.date(), holidays) and start <= _minute(local) < end


def globex_weekly_open(ny: datetime) -> bool:
    """جدول عقد الناسداك الأسبوعيّ: الأحد 18:00 ⟶ الجمعة 17:00 نيويورك، واستراحة 17:00–18:00 يوميًّا."""
    minute, weekday = _minute(ny), ny.weekday()
    if weekday == SATURDAY:
        return False
    if weekday == SUNDAY:
        return minute >= GLOBEX_REOPEN_MIN
    if weekday == FRIDAY:
        return minute < GLOBEX_HALT_MIN
    return not GLOBEX_HALT_MIN <= minute < GLOBEX_REOPEN_MIN


def cash_close_min(day: date) -> int:
    return EARLY_CLOSE_MIN if is_early_close(day) else CASH_CLOSE_MIN


def cash_timing(now: float, holidays: Any) -> tuple[bool, int | None, int | None]:
    """(النقديّ مفتوح؟، دقائق حتّى الافتتاح — صفر إن كان مفتوحًا، دقائق حتّى الإغلاق — إن كان مفتوحًا)."""
    today = local_time(now, CITY_NEW_YORK).date()
    if is_trading_day(today, holidays):
        open_at = local_to_utc(today, CASH_OPEN_MIN, CITY_NEW_YORK)
        close_at = local_to_utc(today, cash_close_min(today), CITY_NEW_YORK)
        if open_at <= now < close_at:
            return True, 0, int((close_at - now) // 60)
        if now < open_at:
            return False, int((open_at - now) // 60), None
    day = today
    for _ in range(NEXT_DAY_SCAN):
        day += timedelta(days=1)
        if is_trading_day(day, holidays):
            return False, int((local_to_utc(day, CASH_OPEN_MIN, CITY_NEW_YORK) - now) // 60), None
    return False, None, None


def open_sessions(now: float, cash_open: bool, london_holidays: Any, tokyo_holidays: Any) -> list[str]:
    london = _within(local_time(now, CITY_LONDON), LONDON_OPEN_MIN, LONDON_CLOSE_MIN, london_holidays)
    out = []
    if _within(local_time(now, CITY_TOKYO), ASIA_OPEN_MIN, ASIA_CLOSE_MIN, tokyo_holidays):
        out.append(SESSION_ASIA)
    if london:
        out.append(SESSION_LONDON)
    if cash_open:
        out.append(SESSION_NY_CASH)
    if london and cash_open:
        out.append(SESSION_OVERLAP)
    if globex_weekly_open(local_time(now, CITY_NEW_YORK)):
        out.append(SESSION_GLOBEX)
    return out


def session_now(sessions: list[str]) -> str:
    return next((name for name in SESSION_ORDER if name in sessions), SESSION_CLOSED)


class MarketSessions(NamedTuple):
    sessions_open: list[str]
    session_now: str
    cash_open: bool
    minutes_to_cash_open: int | None
    minutes_to_cash_close: int | None


def market_sessions(epoch_s: float, market_holidays: Any = None, london_holidays: Any = NO_HOLIDAYS,
                    tokyo_holidays: Any = NO_HOLIDAYS) -> MarketSessions:
    """٢٠٢٦-١٠-٠٩ (ختم المالك «NQ» — الوقت من مصدرٍ واحد): الجلسات عند لحظةٍ بغرينتش — التعريف الواحد لـ117 و158.

    `market_holidays` عطل السوق الأمريكيّ (من التقويم عند 117)؛ وبلاها قواعد البورصة لسنة نيويورك وتاليتها — كما
    تفعل 117 حين يغيب تقويمها. وعطل لندن وطوكيو لا تُعرف إلّا من التقويم: من لا يمرّرها يعدّ أيّام عملهما مفتوحة."""
    if market_holidays is None:
        year = local_time(epoch_s, CITY_NEW_YORK).year
        market_holidays = rule_holidays((year, year + 1))
    cash, to_open, to_close = cash_timing(epoch_s, market_holidays)
    sessions = open_sessions(epoch_s, cash, london_holidays, tokyo_holidays)
    return MarketSessions(sessions, session_now(sessions), cash, to_open, to_close)
