# -*- coding: utf-8 -*-
"""سياق الزمن والجلسات — خطّة المالك ١٠-١٧ (المرحلة 3: الخطوات 12 و13 و21؛ ختم «NQ»).

يكمل ما تنشره «معرفة الوقت والعطل» (117: يوم الأسبوع · أسبوع الشهر · أيّام التداول · العطل القادمة · دقائق افتتاح نيويورك
وإغلاقها) بما طلبه المالك ولم يكن:
  · موقع الزمن كاملًا بساعة تركيا: السنة · الربع · النصف · الشهر · **أسبوع الشهر بأسابيع سبعة أيّام تبدأ الإثنين** («أسبوع
    كامل — وين السبت والأحد؟») · كم أسبوعًا في الشهر · هل أوّله وآخره كاملان · العدّ التنازليّ لإغلاق اليوم والأسبوع والشهر
    والربع والسنة.
  · الجلسات بأسواقها (سيدني · طوكيو · شنغهاي · هونغ كونغ · سنغافورة · فرانكفورت · لندن · نيويورك · تورونتو): مفتوحة أم
    لا · كم بقي على افتتاحها أو إغلاقها · مواعيدها بساعة تركيا · **وتداخلها** («إذا في جلستين لازم يذكرها إنّها متّصلة»).
  · جدول الأصول على مدار اليوم (الخطوة 21): نافذة كلّ أصلٍ بساعة تركيا مرتّبةً بالافتتاح (من ``shared.red_lines``).

كلّ منطقةٍ من قاعدة المناطق الزمنيّة (صيفها وشتاؤها آليّان). دوالّ صافية بلا ساعة: اللحظة تُعطى لها.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

from shared import red_lines

try:
    from zoneinfo import ZoneInfo
except ImportError:  # noqa: BLE001
    ZoneInfo = None

OWNER_ZONE = "Europe/Istanbul"
NEW_YORK = "America/New_York"
DAILY_CLOSE_NY = (17, 0)          # إغلاق اليوم (يوم الوسيط) 17:00 نيويورك
FRIDAY = 4
DAYS_PER_WEEK = 7
MONTHS_PER_QUARTER = 3
MONTHS_PER_HALF = 6

#: البورصات: (المنطقة · الافتتاح · الإغلاق) بساعة البورصة، أيّام الإثنين–الجمعة بساعتها.
EXCHANGES: dict[str, tuple[str, tuple[int, int], tuple[int, int]]] = {
    "SYDNEY": ("Australia/Sydney", (10, 0), (16, 0)),
    "TOKYO": ("Asia/Tokyo", (9, 0), (15, 30)),
    "SHANGHAI": ("Asia/Shanghai", (9, 30), (15, 0)),
    "HONG_KONG": ("Asia/Hong_Kong", (9, 30), (16, 0)),
    "SINGAPORE": ("Asia/Singapore", (9, 0), (17, 0)),
    "FRANKFURT": ("Europe/Berlin", (9, 0), (17, 30)),
    "LONDON": ("Europe/London", (8, 0), (16, 30)),
    "NEW_YORK": ("America/New_York", (9, 30), (16, 0)),
    "TORONTO": ("America/Toronto", (9, 30), (16, 0)),
}
TRADED = ("USTEC", "US30", "US500", "XAUUSD", "BTCUSD", "EURUSD", "GBPUSD")


def _zone(name: str):
    return ZoneInfo(name) if ZoneInfo is not None else None


def available() -> bool:
    try:
        return _zone(OWNER_ZONE) is not None and _zone(NEW_YORK) is not None
    except Exception:  # noqa: BLE001
        return False


def owner_date(epoch: float) -> date:
    """تاريخ اليوم بساعة المالك (تركيا)."""
    return datetime.fromtimestamp(epoch, _zone(OWNER_ZONE)).date()


def _hhmm(epoch: float) -> str:
    return datetime.fromtimestamp(epoch, _zone(OWNER_ZONE)).strftime("%H:%M")


def _week_of_month(day: date) -> int:
    """أسبوع الشهر بأسابيع سبعة أيّام تبدأ الإثنين: الأسبوع الأوّل من 1 إلى أوّل أحد."""
    first = day.replace(day=1)
    return (day.day + first.weekday() - 1) // DAYS_PER_WEEK + 1


def _month_end(day: date) -> date:
    nxt = (day.replace(day=28) + timedelta(days=4)).replace(day=1)
    return nxt - timedelta(days=1)


def _local_midnight(day: date, zone) -> float:
    return datetime(day.year, day.month, day.day, tzinfo=zone).timestamp()


def _next_at(epoch: float, zone_name: str, hm: tuple[int, int], weekday: int | None = None) -> float:
    """أوّل لحظةٍ بعد اللحظة تكون فيها الساعة hm بساعة المنطقة (وفي يوم الأسبوع المعطى إن أُعطي)."""
    zone = _zone(zone_name)
    local = datetime.fromtimestamp(epoch, zone)
    at = local.replace(hour=hm[0], minute=hm[1], second=0, microsecond=0)
    while at <= local or (weekday is not None and at.weekday() != weekday):
        at += timedelta(days=1)
    return at.timestamp()


def time_position(epoch: float) -> dict[str, Any]:
    """موقع اللحظة من الزمن بساعة المالك (تركيا)."""
    zone = _zone(OWNER_ZONE)
    local = datetime.fromtimestamp(epoch, zone)
    today = local.date()
    month_end = _month_end(today)
    quarter = (today.month - 1) // MONTHS_PER_QUARTER + 1
    quarter_end_month = quarter * MONTHS_PER_QUARTER
    quarter_end = _month_end(date(today.year, quarter_end_month, 1))
    year_end = date(today.year, 12, 31)
    first = today.replace(day=1)

    def until_after(day: date) -> float:
        return round(_local_midnight(day + timedelta(days=1), zone) - epoch, 1)

    return {
        "owner_time": local.strftime("%Y-%m-%d %H:%M:%S"), "year": today.year, "quarter": quarter,
        "half": (today.month - 1) // MONTHS_PER_HALF + 1, "month": today.month, "day": today.day,
        "weekday": today.weekday(), "day_of_year": today.timetuple().tm_yday,
        "week_of_month": _week_of_month(today), "weeks_in_month": _week_of_month(month_end),
        "first_week_full": first.weekday() == 0, "last_week_full": month_end.weekday() == DAYS_PER_WEEK - 1,
        "days_in_month": month_end.day, "days_left_in_month": (month_end - today).days,
        "seconds_to_day_end": until_after(today), "seconds_to_month_end": until_after(month_end),
        "seconds_to_quarter_end": until_after(quarter_end), "seconds_to_year_end": until_after(year_end),
        "seconds_to_week_end": round(_next_at(epoch, NEW_YORK, DAILY_CLOSE_NY, FRIDAY) - epoch, 1),
        "seconds_to_daily_close": round(_next_at(epoch, NEW_YORK, DAILY_CLOSE_NY) - epoch, 1),
    }


def _session_bounds(epoch: float, zone_name: str, open_hm, close_hm) -> tuple[bool, float, float]:
    """(مفتوحة الآن؟ · افتتاحها التالي أو الحاليّ · إغلاقها الحاليّ أو التالي) — أيّام العمل بساعة البورصة."""
    zone = _zone(zone_name)
    local = datetime.fromtimestamp(epoch, zone)
    day = local
    for _ in range(DAYS_PER_WEEK + 1):
        if day.weekday() < 5:
            opened = day.replace(hour=open_hm[0], minute=open_hm[1], second=0, microsecond=0)
            closes = day.replace(hour=close_hm[0], minute=close_hm[1], second=0, microsecond=0)
            if local < closes:
                return opened <= local, opened.timestamp(), closes.timestamp()
        day = (day + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    raise ValueError("no session within a week")


def sessions(epoch: float) -> dict[str, Any]:
    """كلّ بورصة: مفتوحة أم لا، وكم بقي، ومواعيدها بساعة تركيا؛ ثمّ التداخل بين المفتوحة منها."""
    rows = []
    for name, (zone_name, open_hm, close_hm) in EXCHANGES.items():
        is_open, opens, closes = _session_bounds(epoch, zone_name, open_hm, close_hm)
        rows.append({"name": name, "open": is_open, "opens_at": opens, "closes_at": closes,
                     "seconds_to_open": None if is_open else round(opens - epoch, 1),
                     "seconds_to_close": round(closes - epoch, 1) if is_open else None,
                     "open_owner": _hhmm(opens), "close_owner": _hhmm(closes)})
    live = [r for r in rows if r["open"]]
    overlaps = [{"a": a["name"], "b": b["name"], "until_owner": _hhmm(min(a["closes_at"], b["closes_at"])),
                 "seconds_left": round(min(a["closes_at"], b["closes_at"]) - epoch, 1)}
                for i, a in enumerate(live) for b in live[i + 1:]]
    upcoming = sorted((r for r in rows if not r["open"]), key=lambda r: r["opens_at"])
    return {"exchanges": rows, "open_now": [r["name"] for r in live], "overlaps": overlaps,
            "next_open": upcoming[0]["name"] if upcoming else None,
            "seconds_to_next_open": upcoming[0]["seconds_to_open"] if upcoming else None}


def _asset_window(epoch: float, symbol: str) -> tuple[bool, float, float]:
    name = red_lines.session_of(symbol)
    if name == red_lines.GENERAL:
        inside, opened = red_lines.session_state(epoch, symbol)
        close_zone, close_hm = red_lines.GENERAL_CLOSE
        open_zone, open_hm = red_lines.GENERAL_OPEN
        closes = _next_at(epoch, close_zone, close_hm)
        opens = opened if inside and opened is not None else _next_at(epoch, open_zone, open_hm)
        # ١٧/١٠: الافتتاح التالي بعد العطلة الأسبوعيّة · ٢٣/١٠ (القانون 23): والبتكوين معها، لا يُستثنى.
        while not inside and red_lines.weekend_open(opens):
            opens = _next_at(opens + 60, open_zone, open_hm)
        return inside, opens, closes
    zone_name, open_hm, close_hm = red_lines.SESSIONS[name]
    return _session_bounds(epoch, zone_name, open_hm, close_hm)


def asset_schedule(epoch: float, symbols=TRADED) -> list[dict[str, Any]]:
    """جدول الأصول على مدار اليوم بساعة تركيا، مرتّبًا بالافتتاح (الخطوة 21)."""
    rows = []
    for symbol in symbols:
        inside, opens, closes = _asset_window(epoch, symbol)
        rows.append({"symbol": symbol, "session": red_lines.session_of(symbol), "open": inside,
                     "open_owner": _hhmm(opens), "close_owner": _hhmm(closes),
                     "seconds_to_open": None if inside else round(opens - epoch, 1),
                     "seconds_to_close": round(closes - epoch, 1) if inside else None,
                     "first_minutes": red_lines.in_first_minutes(epoch, symbol),
                     # ٢٥/١٠ (القانون 21): الساعة الأخيرة من النافذة — لا صفقة جديدة، والمفتوح يكمل حتّى الإغلاق
                     "last_hour": red_lines.in_last_hour(epoch, symbol),
                     "no_new_owner": _hhmm(closes - red_lines.LAST_HOUR_S), "_opens": opens})
    rows.sort(key=lambda r: (not r["open"], r["_opens"]))
    for r in rows:
        r.pop("_opens")
    return rows


def context(epoch: float) -> dict[str, Any]:
    if not available():
        return {"available": False, "reason": "TIME_ZONE_DATABASE_MISSING"}
    return {"available": True, "time": time_position(epoch), "sessions": sessions(epoch),
            "schedule": asset_schedule(epoch)}
