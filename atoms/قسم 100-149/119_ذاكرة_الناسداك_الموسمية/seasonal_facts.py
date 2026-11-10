"""ذاكرة الناسداك الموسميّة (119) — حقائق اللحظة الحاليّة من الذاكرة، وسطرها العربيّ للمالك.

٢٠٢٦-١٠-٠٨ (ختم المالك «NQ» — المعرفة أوّلًا): ما يعرفه النظام عن «اليوم والشهر والساعة» الآن — أرقامٌ خام بعيّنتها،
للعلم والختم على الصفقة، لا تدخل قرارًا.
ترتيب `facts`: أوّلًا عشر حقائق مفردة (رقم أو نصّ قصير) لأنّ دفتر البطاقات 465 يختم أوّل عشر مفرداتٍ بأسمائها
على كلّ صفقة، ثمّ التفاصيل قواميس.
"""
from __future__ import annotations

from datetime import date
from typing import Any

import seasonal_memory as sm

WEEKDAY_EN = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
WEEKDAY_AR = ("الاثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة", "السبت", "الأحد")
MONTH_EN = ("January", "February", "March", "April", "May", "June", "July", "August", "September",
            "October", "November", "December")
MONTH_AR = ("كانون الثاني", "شباط", "آذار", "نيسان", "أيّار", "حزيران", "تمّوز", "آب", "أيلول",
            "تشرين الأوّل", "تشرين الثاني", "كانون الأوّل")
KIND_AR = {sm.PRE_HOLIDAY: "قبل عطلة", sm.POST_HOLIDAY: "بعد عطلة", sm.HOLIDAY: "يوم عطلة أمريكيّة",
           sm.FOMC: "يوم قرار الفائدة", sm.OPEX: "الجمعة الثالثة (انتهاء الخيارات)",
           sm.MONTH_END: "آخر يوم تداول في الشهر", sm.MONTH_START: "أوّل يوم تداول في الشهر"}
NO_KIND = "none"
RATIO_DIGITS = 3
REASON_NEWER = "memory_newer_than_moment"


def today_kinds(memory: dict[str, Any], day: date) -> tuple[str, ...]:
    """أنواع يوم الوسيط الجاري بقاعدة أيّام التداول (اليوم التالي لم يُغلق بعد فلا شمعة تقول إنّه آخر الشهر)."""
    if day.weekday() >= sm.WEEKEND_FROM:
        return ()
    cal = memory["calendar"]
    before, after = sm.prev_trading(day, cal), sm.next_trading(day, cal)
    return sm.date_kinds(day, cal, (before.year, before.month) != (day.year, day.month),
                         (after.year, after.month) != (day.year, day.month))


def _holiday_of(cal: dict[str, Any], day: date, kinds: tuple[str, ...]) -> tuple[date, str, str] | None:
    holidays = cal.get("holidays") or {}
    for kind, near in ((sm.HOLIDAY, day), (sm.PRE_HOLIDAY, sm.next_weekday(day)),
                       (sm.POST_HOLIDAY, sm.prev_weekday(day))):
        if kind in kinds and near in holidays:
            return (near, *holidays[near])
    return None


def _ratio(part: Any, whole: Any) -> float | None:
    return round(part / whole, RATIO_DIGITS) if part is not None and whole else None


def _iso(value: Any) -> str | None:
    return value.isoformat() if isinstance(value, date) else None


def unavailable(reason: str) -> tuple[dict[str, Any], str, str]:
    return ({"available": False, "reason": reason},
            "ذاكرة الناسداك الموسميّة غير متاحة الآن: %s" % reason, sm.STATUS_UNAVAILABLE)


def facts_at(memory: dict[str, Any], now: float,
             today_bars: dict[str, Any] | None) -> tuple[dict[str, Any], str, str]:
    """(الحقائق، السطر العربيّ، الحالة) للحظة `now`. الذاكرة من أيّامٍ مغلقة قبل يومها، وإلّا فلا حقائق."""
    if memory.get("status") != sm.STATUS_OK:
        return unavailable(str(memory.get("reason") or "unknown"))
    if sm.broker_day_start(now) < memory["cut"]:
        return unavailable(REASON_NEWER)
    day = sm.broker_date(now)
    weekday, hour = day.weekday(), sm.ny_hour(now)
    trading = weekday < sm.WEEKEND_FROM
    week_all = memory["weekday_all"].get(weekday) or sm.day_stats([])
    week_recent = memory["weekday_recent"].get(weekday) or sm.day_stats([])
    month = memory["month"].get(day.month) or {"return": sm.value_stats([]), "daily_range_pct": None, "days_n": 0}
    hour_row = memory["hour"].get(hour) or {**sm.value_stats([]), "abs_move_pct": None, "range_pct": None,
                                            "rank_by_abs_move": None}
    kinds = today_kinds(memory, day)
    cal = memory["calendar"]
    so_far = dict(today_bars or {}) if trading else {}
    so_far.setdefault("hours", 0)
    so_far.setdefault("range_pct", None)
    so_far.update({"weekday_range_pct_all": week_all["range_pct"],
                   "ratio_all": _ratio(so_far["range_pct"], week_all["range_pct"]),
                   "weekday_range_pct_recent": week_recent["range_pct"],
                   "ratio_recent": _ratio(so_far["range_pct"], week_recent["range_pct"])})
    holiday = _holiday_of(cal, day, kinds)
    special = {"kinds": list(kinds),
               "holiday_date": _iso(holiday[0]) if holiday else None,
               "holiday_code": holiday[1] if holiday else None,
               "by_kind": {kind: memory["special"]["by_kind"][kind] for kind in kinds},
               "normal": memory["special"]["normal"],
               "calendar_covers_today": bool(cal.get("available")) and sm.covered(day, cal)}
    facts = {
        "weekday": WEEKDAY_EN[weekday],
        "weekday_mean_pct": week_all["mean_pct"],
        "weekday_pos_pct": week_all["pos_pct"],
        "weekday_range_pct": week_all["range_pct"],
        "weekday_n": week_all["n"],
        "month_mean_pct": month["return"]["mean_pct"],
        "hour_ny": hour,
        "hour_abs_move_pct": hour_row["abs_move_pct"],
        "day_range_ratio": so_far["ratio_all"],
        "special_day": "+".join(kinds) or NO_KIND,
        "broker_date": day.isoformat(),
        "weekday_all": {**week_all, "from": _iso(memory["history_from"]), "through": _iso(memory["history_through"])},
        "weekday_recent": {**week_recent, "years": memory["recent_years"], "from": _iso(memory["recent_from"])},
        "month": {"number": day.month, "name": MONTH_EN[day.month - 1], "return": month["return"],
                  "daily_range_pct": month["daily_range_pct"], "days_n": month["days_n"]},
        "hour": {"ny_hour": hour, **hour_row, "hours_ranked": memory["hours_ranked"]},
        "day_so_far": so_far,
        "special": special,
        # ٢٠٢٦-١٠-١٧ (الخطوة 17): الشهر الحاليّ والربع الحاليّ سنةً سنة.
        "by_year": memory.get("by_year"),
        "coverage": {
            "history_from": _iso(memory["history_from"]), "history_through": _iso(memory["history_through"]),
            "days_n": memory["days_n"], "hours_n": memory["hours_n"], "memory_built_at": memory["built_at"],
            "build_s": memory["build_s"], "calendar_available": bool(cal.get("available")),
            "calendar_reason": cal.get("reason"), "calendar_from": _iso(cal.get("from")),
            "calendar_through": _iso(cal.get("through")), "holidays_n": len(cal.get("holidays") or {}),
            "fomc_n": len(cal.get("fomc") or ()), "closed_holidays": list(cal.get("closed_codes") or [])},
    }
    return facts, summary_ar(facts, memory, holiday), sm.STATUS_OK


# ── السطر العربيّ ──────────────────────────────────────────────────────
def _signed(value: Any) -> str:
    return "—" if value is None else "%+.2f٪" % value


def _plain(value: Any) -> str:
    return "—" if value is None else "%.2f٪" % value


def _share(value: Any) -> str:
    return "—" if value is None else "%.0f٪" % value


def _day_line(stats: dict[str, Any]) -> str:
    return "%s وسطيًّا، %s موجب، مدى %s" % (_signed(stats["mean_pct"]), _share(stats["pos_pct"]),
                                          _plain(stats["range_pct"]))


def _hour_line(hour: dict[str, Any], trading: bool) -> str:
    head = "الساعة %d نيويورك" % hour["ny_hour"]
    if not trading:
        return head + ": خارج الجلسة"
    if not hour["n"]:
        return head + ": لا شموع لهذه الساعة في التاريخ"
    if hour["rank_by_abs_move"] == 1:
        return head + ": أكبر ساعات اليوم حركة (%s)" % _plain(hour["abs_move_pct"])
    return head + ": الـ%d من %d ساعة في الحركة (%s)" % (hour["rank_by_abs_move"], hour["hours_ranked"],
                                                      _plain(hour["abs_move_pct"]))


def _special_line(special: dict[str, Any], holiday: tuple[date, str, str] | None) -> str:
    if not special["kinds"]:
        return "اليوم ليس يومًا خاصًّا"
    normal = special["normal"]
    lines = []
    for kind in special["kinds"]:
        stats = special["by_kind"][kind]
        label = KIND_AR[kind]
        if holiday and kind in (sm.PRE_HOLIDAY, sm.POST_HOLIDAY, sm.HOLIDAY):
            label += " (%s)" % (holiday[2] or holiday[1])
        lines.append("اليوم %s: %s (%d يومًا) مقابل العاديّة %s (%d)" % (
            label, _day_line(stats), stats["n"], _day_line(normal), normal["n"]))
    return " · ".join(lines)


def summary_ar(facts: dict[str, Any], memory: dict[str, Any], holiday: tuple[date, str, str] | None) -> str:
    """مثل: «الخميس تاريخيًّا (2014–2026، 600 يومًا): +0.06٪ وسطيًّا، 54٪ موجب، مدى 1.40٪ · …»."""
    weekday = WEEKDAY_EN.index(facts["weekday"])
    name = WEEKDAY_AR[weekday]
    trading = weekday < sm.WEEKEND_FROM
    parts = []
    if trading:
        every, recent = facts["weekday_all"], facts["weekday_recent"]
        parts.append("%s تاريخيًّا (%d–%d، %d يومًا): %s" % (
            name, memory["history_from"].year, memory["history_through"].year, every["n"], _day_line(every)))
        parts.append("آخر %d سنوات (%d يومًا): %s" % (recent["years"], recent["n"], _day_line(recent)))
    else:
        parts.append("%s: لا جلسة للناسداك في يوم الوسيط" % name)
    month = facts["month"]
    parts.append("%s (%d سنة): %s وسطيًّا، %s موجب، مدى يوميّ %s" % (
        MONTH_AR[month["number"] - 1], month["return"]["n"], _signed(month["return"]["mean_pct"]),
        _share(month["return"]["pos_pct"]), _plain(month["daily_range_pct"])))
    parts.append(_hour_line(facts["hour"], trading))
    if trading:
        so_far = facts["day_so_far"]
        if so_far["hours"] and so_far["ratio_all"] is not None:
            parts.append("مدى اليوم حتّى الآن %s في %d ساعة = %.0f٪ من متوسّط %s" % (
                _plain(so_far["range_pct"]), so_far["hours"], so_far["ratio_all"] * 100, name))
        else:
            parts.append("لم تُغلق ساعةٌ من اليوم بعد")
        parts.append(_special_line(facts["special"], holiday))
    return " · ".join(parts)
