"""سلسلة تسعير قرارات الفائدة من عقود الفائدة الفيدراليّة لثلاثين يومًا (121) — دوالّ صافية بلا شبكة ولا حالة.

٢٠٢٦-١٠-٠٨ (ختم المالك «NQ» — «تسعير الفائدة حيًّا يحتاج ياهو NQ»):
العقد الشهريّ يُسوّى على متوسّط الفائدة الفعليّة اليوميّ في شهره، فالضمنيّ = 100 − السعر = ذلك المتوسّط.
النموذج: الفائدة ثابتةٌ بين الاجتماعات، والقرار (14:00 نيويورك) يسري من اليوم التالي له. لشهرٍ فيه اجتماعٌ يومه d
وعدد أيّامه N:      ضمنيّ الشهر × N = قبله × d + بعده × (N − d)
ولشهرٍ بلا اجتماع:  ضمنيّه = الفائدة السارية فيه كلّه.

الحلّ (طريقة سوق العقود المعروفة — أمر المالك):
  ١) كلّ شهرٍ بلا اجتماع يثبّت الفائدة السارية فيه مباشرةً — «إن كان الشهر التالي بلا اجتماع ⟸ بعده = ضمنيّ الشهر التالي».
  ٢) أماميًّا: بعده = (ضمنيّ الشهر × N − قبله × d) ÷ (N − d)، وقبله = بعد الاجتماع السابق.
  ٣) خلفيًّا لما بقي: قبله = (ضمنيّ الشهر × N − بعده × (N − d)) ÷ d.
     هذا يحسم «قبل» الاجتماع الأوّل حين يقع في الشهر الجاري: أخذ ضمنيّ الشهر الجاري نفسه «قبلًا» يخلط أيّام ما بعد
     الاجتماع بما قبله (اليوم: ضمنيّ تشرين الأوّل 3.885 مقابل 3.8802 محلولًا من معادلته وتشرين الثاني) — والمحلول
     يحقّق معادلة الشهر حرفيًّا، فلا تخمين.
والشهر الجاري الذي مرّ فيه اجتماعٌ قبل الآن لا تُستعمل معادلته (فيه فائدةُ ما قبل ذلك الاجتماع، وليست في السلسلة).
وكلّ فائدةٍ محسوبة تحمل طريقتها والعقود التي بُنيت عليها — فلا رقم بلا أصله.
"""
from __future__ import annotations

import calendar
import time
from datetime import date
from typing import Any

from shared.owner_windows import new_york_offset_h

MONTH_CODES = "FGHJKMNQUVXZ"          # حروف أشهر العقود الآجلة المعياريّة (كانون الثاني … كانون الأوّل)
SYMBOL_PREFIX = "ZQ"                  # عقود الفائدة الفيدراليّة لثلاثين يومًا (CBOT)
SYMBOL_SUFFIX = ".CBT"                # لاحقة ياهو لبورصة شيكاغو للسلع
MONTHS_PER_YEAR = 12
DECISION_HOUR_NY = 14                 # القرار 14:00 بتوقيت نيويورك (federalreserve.gov)
BP_STEP = 25.0                        # خطوة تحريك الفيدراليّ المعتادة بنقاط الأساس
TARGET_HALF_WIDTH = 0.125             # نصف عرض النطاق (25 ن.أ): الوسط = الحدّ الأعلى − 0.125
IMPLIED_DIGITS = 4                    # العقد يتحرّك بربع نقطة أساس (0.0025) — أربع منازل تحفظه بلا ضجيج الفاصلة
BP_DIGITS = 1
PCT_DIGITS = 1
METHOD_MONTH = "month_average"        # شهرٌ بلا اجتماع: ضمنيّه هو الفائدة السارية
METHOD_MONTH_END = "decision_on_last_day"
METHOD_FORWARD = "solved_forward"
METHOD_BACKWARD = "solved_backward"


def _iso(ts: float | None) -> str | None:
    return None if ts is None else time.strftime("%Y-%m-%dT%H:%MZ", time.gmtime(ts))


def month_add(year: int, month: int, k: int) -> tuple[int, int]:
    index = year * MONTHS_PER_YEAR + (month - 1) + k
    return index // MONTHS_PER_YEAR, index % MONTHS_PER_YEAR + 1


def contract_symbol(year: int, month: int) -> str:
    """رمز ياهو للعقد: ZQ + حرف الشهر + آخر رقمين من السنة + .CBT (مثل ZQX26.CBT = تشرين الثاني 2026)."""
    return "%s%s%02d%s" % (SYMBOL_PREFIX, MONTH_CODES[month - 1], year % 100, SYMBOL_SUFFIX)


def month_label(ym: tuple[int, int]) -> str:
    return "%04d-%02d" % ym


def window_months(now: float, months_ahead: int) -> list[tuple[int, int]]:
    """الشهر الجاري (بغرينتش) و`months_ahead` شهرًا بعده."""
    today = time.gmtime(now)
    return [month_add(today.tm_year, today.tm_mon, k) for k in range(months_ahead + 1)]


def days_in(ym: tuple[int, int]) -> int:
    return calendar.monthrange(ym[0], ym[1])[1]


def decision_utc(day: date) -> float:
    """14:00 بتوقيت نيويورك يوم القرار بغرينتش (صيفًا 18:00 وشتاءً 19:00) — القاعدة الرسميّة في owner_windows."""
    base = calendar.timegm((day.year, day.month, day.day, DECISION_HOUR_NY, 0, 0))
    return float(base - new_york_offset_h(base) * 3600)


def _parse(values: Any, tentative: bool) -> tuple[list[dict[str, Any]], int]:
    out, bad = [], 0
    for value in values or ():
        try:
            day = date.fromisoformat(str(value))
        except ValueError:
            bad += 1
            continue
        out.append({"day": day, "utc": decision_utc(day), "tentative": tentative})
    return out, bad


def build_schedule(confirmed: Any, tentative: Any) -> tuple[list[dict[str, Any]], int]:
    """أيّام القرار مرتّبة بلا تكرار (المؤكَّد يسبق المبدئيّ لليوم نفسه)، وعدد الأيّام غير المقروءة."""
    first, bad_first = _parse(confirmed, False)
    second, bad_second = _parse(tentative, True)
    seen: dict[date, dict[str, Any]] = {}
    for meeting in first + second:
        seen.setdefault(meeting["day"], meeting)
    return sorted(seen.values(), key=lambda m: m["day"]), bad_first + bad_second


def _ym(meeting: dict[str, Any]) -> tuple[int, int]:
    return meeting["day"].year, meeting["day"].month


def _pin(months, implied, upcoming, passed_now, rates, how, deps) -> None:
    index = {_ym(m): i for i, m in enumerate(upcoming, start=1)}
    for pos, ym in enumerate(months):
        value = implied.get(ym)
        if value is None or (pos == 0 and passed_now):
            continue
        symbol = contract_symbol(*ym)
        if ym in index:
            i = index[ym]
            if upcoming[i - 1]["day"].day == days_in(ym) and rates[i - 1] is None:
                rates[i - 1], how[i - 1], deps[i - 1] = value, METHOD_MONTH_END, {symbol}
            continue
        k = sum(1 for m in upcoming if _ym(m) < ym)
        if rates[k] is None:
            rates[k], how[k], deps[k] = value, METHOD_MONTH, {symbol}


def _propagate(implied, upcoming, rates, how, deps) -> bool:
    changed = False
    for i, meeting in enumerate(upcoming, start=1):
        ym, d = _ym(meeting), meeting["day"].day
        value, n = implied.get(ym), days_in(ym)
        if value is None or rates[i - 1] is None or rates[i] is not None or n - d <= 0:
            continue
        rates[i] = (value * n - rates[i - 1] * d) / (n - d)
        how[i], deps[i] = METHOD_FORWARD, deps[i - 1] | {contract_symbol(*ym)}
        changed = True
    for i in range(len(upcoming), 0, -1):
        meeting = upcoming[i - 1]
        ym, d = _ym(meeting), meeting["day"].day
        value, n = implied.get(ym), days_in(ym)
        if value is None or rates[i] is None or rates[i - 1] is not None:
            continue
        rates[i - 1] = (value * n - rates[i] * (n - d)) / d
        how[i - 1], deps[i - 1] = METHOD_BACKWARD, deps[i] | {contract_symbol(*ym)}
        changed = True
    return changed


def solve_path(months: list[tuple[int, int]], implied: dict[tuple[int, int], float | None],
               schedule: list[dict[str, Any]], now: float) -> dict[str, Any]:
    """`rates[0]` الفائدة السارية قبل الاجتماع القادم، و`rates[i]` بعد الاجتماع i في نافذة العقود — أو None."""
    first, last = months[0], months[-1]
    in_window = [m for m in schedule if first <= _ym(m) <= last]
    upcoming = [m for m in in_window if m["utc"] > now]
    passed_now = any(_ym(m) == first and m["utc"] <= now for m in in_window)
    size = len(upcoming) + 1
    rates: list[float | None] = [None] * size
    how: list[str | None] = [None] * size
    deps: list[set[str]] = [set() for _ in range(size)]
    _pin(months, implied, upcoming, passed_now, rates, how, deps)
    # أماميًّا أوّلًا (أمر المالك) ثمّ خلفيًّا لما بقي، حتّى لا جديد.
    while _propagate(implied, upcoming, rates, how, deps):
        pass
    return {"upcoming": upcoming, "rates": rates, "how": how, "deps": deps}


def move_shares(change_bp: float | None) -> dict[str, Any]:
    """نسبة السوق المسعَّرة لتحريك 25 ن.أ = |الفرق| ÷ 25، وما فوق 100٪ جزؤه لتحريك 50 ن.أ — سعرٌ لا حكم."""
    keys = ("market_implied_hike_pct", "market_implied_cut_pct", "market_implied_hike_50bp_pct",
            "market_implied_cut_50bp_pct", "priced_25bp_steps")
    if change_bp is None:
        return dict.fromkeys(keys)
    steps = abs(change_bp) / BP_STEP
    first = round(min(steps, 1.0) * 100, PCT_DIGITS)
    second = round(min(max(steps - 1.0, 0.0), 1.0) * 100, PCT_DIGITS)
    up, down = change_bp > 0, change_bp < 0
    return dict(zip(keys, (first if up else 0.0, first if down else 0.0, second if up else 0.0,
                           second if down else 0.0, round(steps, 2))))


def _rate(value: float | None) -> float | None:
    return None if value is None else round(value, IMPLIED_DIGITS)


def meeting_rows(path: dict[str, Any], now: float, target_mid: float | None) -> list[dict[str, Any]]:
    """لكلّ اجتماعٍ في النافذة: التاريخ · قبله · بعده · الفرق · النسب · العقود التي بُني عليها (`_deps`)."""
    rows = []
    rates, how, deps = path["rates"], path["how"], path["deps"]
    for i, meeting in enumerate(path["upcoming"], start=1):
        before, after = rates[i - 1], rates[i]
        raw = None if before is None or after is None else (after - before) * 100
        ym = _ym(meeting)
        rows.append({
            "date": meeting["day"].isoformat(), "decision_utc": _iso(meeting["utc"]),
            "days_to": round((meeting["utc"] - now) / 86400, 1), "tentative": meeting["tentative"],
            "contract": contract_symbol(*ym), "days_in_month": days_in(ym), "decision_day": meeting["day"].day,
            "rate_before": _rate(before), "rate_before_method": how[i - 1],
            "rate_after": _rate(after), "rate_after_method": how[i],
            "expected_change_bp": None if raw is None else round(raw, BP_DIGITS), **move_shares(raw),
            "rate_after_vs_target_mid_bp": None if after is None or target_mid is None
            else round((after - target_mid) * 100, BP_DIGITS),
            "_deps": sorted(deps[i - 1] | deps[i]) if raw is not None else [],
        })
    return rows


def year_end(path: dict[str, Any], schedule: list[dict[str, Any]], now: float) -> dict[str, Any]:
    """الفائدة المسعَّرة السارية آخر السنة الجارية: بعد آخر اجتماعٍ باقٍ فيها — أو السارية الآن إن لم يبقَ اجتماع."""
    year = time.gmtime(now).tm_year
    remaining = [m for m in schedule if m["utc"] > now and m["day"].year == year]
    if not remaining:
        return {"rate": _rate(path["rates"][0]), "meeting": None, "reason": None}
    last = remaining[-1]
    if last not in path["upcoming"]:
        return {"rate": None, "meeting": last["day"].isoformat(), "reason": "MEETING_BEYOND_CONTRACT_WINDOW"}
    return {"rate": _rate(path["rates"][path["upcoming"].index(last) + 1]),
            "meeting": last["day"].isoformat(), "reason": None}
