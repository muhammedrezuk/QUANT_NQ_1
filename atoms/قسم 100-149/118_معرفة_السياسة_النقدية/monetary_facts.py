"""حساب حقائق السياسة النقديّة (118) — دوالّ صافية على صفوف التقويم، بلا قراءة ولا حكم.

٢٠٢٦-١٠-٠٨ (ختم المالك «NQ» — المعرفة أوّلًا): الماضي (ما صدر في 30 يومًا وأكبر فروقه عن توقّع الوسيط)،
والحاضر (الفائدة ودورتها وآخر الإصدارات)، والمستقبل (الاجتماع القادم والـ48 ساعة و«ما هو جاي» لـ30 يومًا).
«المتوقَّع» توقّع الوسيط لا الإجماع (مقيس سابقًا: طابق مرّة من عشر). الأهمّيّة تصنيف ميتاتريدر الخام.
"""
from __future__ import annotations

import math
import time
from typing import Any

from shared.owner_windows import local_time, new_york_offset_h

HIGH_IMPORTANCE = 3
WINDOW_H = 48
WINDOW_S = WINDOW_H * 3600
CYCLE_DAYS = 365
CYCLE_S = CYCLE_DAYS * 86400
PAST_DAYS = 30
PAST_S = PAST_DAYS * 86400
COMING_DAYS = 30
COMING_S = COMING_DAYS * 86400
MAX_LISTED = 20
MAX_COMING = 80
MAX_LARGEST = 5
# (المفتاح، رمز الحدث الأمريكيّ، الاسم المعروض)
RELEASES = (
    ("core_cpi_mm", "consumer-price-index-ex-food-energy-mm", "التضخّم الأساسيّ الشهريّ"),
    ("core_cpi_yy", "consumer-price-index-ex-food-energy-yy", "التضخّم الأساسيّ السنويّ"),
    ("cpi_mm", "consumer-price-index-mm", "التضخّم الكلّيّ الشهريّ"),
    ("cpi_yy", "consumer-price-index-yy", "التضخّم الكلّيّ السنويّ"),
    ("nonfarm_payrolls", "nonfarm-payrolls", "الوظائف غير الزراعيّة"),
    ("unemployment_rate", "unemployment-rate", "البطالة"),
    ("core_pce_mm", "core-pce-price-index-mm", "نفقات الاستهلاك الشخصيّ الأساسيّ الشهريّ"),
    ("core_pce_yy", "core-pce-price-index-yy", "نفقات الاستهلاك الشخصيّ الأساسيّ السنويّ"),
)
RELEASE_CODES = tuple(code for _, code, _ in RELEASES)
# «ما هو جاي» — أبواب المالك: التضخّم · الوظائف · الفائدة · الناتج · نفقات الاستهلاك · خطابات الفيدراليّ.
# الباب برمز الحدث (أيًّا كانت أهمّيّته عند ميتاتريدر: بيان اللجنة والتضخّم الأساسيّ السنويّ «متوسّطان» عنده).
CATEGORY_CODES = {
    "consumer-price-index-mm": "inflation", "consumer-price-index-yy": "inflation",
    "consumer-price-index-ex-food-energy-mm": "inflation", "consumer-price-index-ex-food-energy-yy": "inflation",
    "producer-price-index-mm": "inflation",
    "nonfarm-payrolls": "jobs", "unemployment-rate": "jobs", "average-hourly-earnings-mm": "jobs",
    "initial-jobless-claims": "jobs", "adp-nonfarm-employment-change": "jobs", "jolts-job-openings": "jobs",
    "fed-interest-rate-decision": "rate", "fomc-meeting-statement": "rate", "fomc-press-conference": "rate",
    "fomc-economic-projections": "rate", "fomc-minutes": "rate",
    "gross-domestic-product-qq": "gdp",
    "core-pce-price-index-mm": "pce", "core-pce-price-index-yy": "pce",
    "pce-price-index-mm": "pce", "pce-price-index-yy": "pce",
}
SPEECH_CATEGORY = "fed_speech"
CATEGORY_AR = {"rate": "الفائدة", "inflation": "التضخّم", "jobs": "الوظائف", "gdp": "الناتج",
               "pce": "نفقات الاستهلاك", SPEECH_CATEGORY: "خطابات الفيدراليّ"}
# الموعد القادم لكلّ باب بحدثه الرئيس (للسطر العربيّ ولحقيقة `next_dates`)
MAIN_CODES = (("rate", "fed-interest-rate-decision"), ("inflation", "consumer-price-index-ex-food-energy-mm"),
              ("jobs", "nonfarm-payrolls"), ("gdp", "gross-domestic-product-qq"), ("pce", "core-pce-price-index-mm"))
# أمر المالك: «خطاب» ومعه «الفيدرالي» أو «باول» أو «اللجنة الفيدرالية» — ويُكمَّل برمز الحدث (مقيس: «باول» مكتوبٌ
# «بويل»، ووالر وبار وكولينز بأسماء إنكليزيّة).
SPEECH_WORD = "خطاب"
SPEECH_FED_WORDS = ("الفيدرالي", "باول", "اللجنة الفيدرالية")
SPEECH_CODE_PREFIXES = ("fed-", "fomc-")
SPEECH_CODE_SUFFIXES = ("-speech", "-testimony")
UNIT_TEXT = {1: "%", 4: "وظيفة"}
MULTIPLIER_TEXT = {1: "ألف", 2: "مليون", 3: "مليار", 4: "تريليون"}
RANKING_RULE_AR = ("مرتّبة بالفرق مقسومًا على الحجم المعتاد لفروق الحدث نفسه منذ 2014 (الجذر التربيعيّ لمتوسّط "
                   "مربّعات الفروق) — لتُقارن وحداتٌ مختلفة؛ والفرق الخام معها")
DIFF_LABEL_AR = "فرق الفعليّ عن توقّع الوسيط"
BASIS_AR = {"consensus": "الإجماع", "broker_forecast": "توقّع الوسيط"}
FORECAST_NOTE_AR = ("«المتوقَّع» في تقويم ميتاتريدر توقّع الوسيط لا إجماع السوق — مقيس سابقًا: طابق الإجماع "
                    "مرّة من عشر؛ فالفرق فرقٌ عن توقّع الوسيط")
RATE_NOTE_AR = "قيمة القرار في تقويم ميتاتريدر هي الحدّ الأعلى لنطاق الفائدة (مثل 2024-09-18: 5.0 للنطاق 4.75–5.00)"
PRICING_REASON_AR = ("لا تسعير للقرار القادم: يحتاج أسعار عقود الفائدة الآجلة أو أداة تسعير خارجيّة — "
                     "مصدرٌ لم يأذن به المالك")


def num(value: Any) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def iso(ts: float | None) -> str | None:
    return None if ts is None else time.strftime("%Y-%m-%dT%H:%MZ", time.gmtime(ts))


def day(ts: float | None) -> str | None:
    return None if ts is None else time.strftime("%Y-%m-%d", time.gmtime(ts))


def _ny_day(ts: float) -> str:
    return local_time(ts, new_york_offset_h).date().isoformat()


def _ny_day_end(ts: float) -> float:
    local = local_time(ts, new_york_offset_h)
    return ts - (local.hour * 3600 + local.minute * 60 + local.second) + 86400


def fed_facts(decisions: list[dict[str, Any]], now: float, horizon: float | None) -> dict[str, Any]:
    released = [d for d in decisions if d["time_utc"] <= now and d["actual"] is not None]
    scheduled = [d for d in decisions if d["time_utc"] > now]
    last_time = released[-1]["time_utc"] if released else 0.0
    unreported = [d for d in decisions if last_time < d["time_utc"] <= now and d["actual"] is None]
    out: dict[str, Any] = {"current": None, "previous": None, "change": None, "count": len(released),
                           "first_date": day(released[0]["time_utc"]) if released else None,
                           "current_source": released[-1].get("actual_source") if released else None}
    if released:
        out["current"] = released[-1]["actual"]
        out["previous"] = released[-2]["actual"] if len(released) > 1 else num(released[-1].get("prev"))
    for i in range(len(released) - 1, 0, -1):
        before, after = released[i - 1]["actual"], released[i]
        if after["actual"] != before:
            out["change"] = {"value": after["actual"], "from": before, "date_utc": day(after["time_utc"]),
                             "change_bp": int(round((after["actual"] - before) * 100))}
            break
    steps = [(released[i - 1]["actual"], released[i]) for i in range(1, len(released))
             if released[i]["time_utc"] > now - CYCLE_S]
    out["cycle"] = {"window_days": CYCLE_DAYS, "n": len(steps),
                    "hikes": sum(1 for before, d in steps if d["actual"] > before),
                    "cuts": sum(1 for before, d in steps if d["actual"] < before),
                    "holds": sum(1 for before, d in steps if d["actual"] == before),
                    "net_change_bp": int(round((steps[-1][1]["actual"] - steps[0][0]) * 100)) if steps else 0,
                    "first_utc": iso(steps[0][1]["time_utc"]) if steps else None,
                    "last_utc": iso(steps[-1][1]["time_utc"]) if steps else None}
    nxt = scheduled[0]["time_utc"] if scheduled else None
    out["next_utc"] = nxt
    out["days"] = None if nxt is None else round((nxt - now) / 86400, 1)
    out["hours"] = None if nxt is None else round((nxt - now) / 3600, 1)
    out["next_reason"] = None if nxt is not None else (
        "لا قرار فائدة مجدول في المصدر حتّى أفقه %s" % (iso(horizon) or "—"))
    today = _ny_day(now)
    if any(_ny_day(d["time_utc"]) == today for d in decisions):
        out["is_day"] = True
    else:
        out["is_day"] = False if horizon is not None and horizon >= _ny_day_end(now) else None
    out["unreported_utc"] = iso(unreported[-1]["time_utc"]) if unreported else None
    return out


def speech_match(row: dict[str, Any]) -> str | None:
    name, code = str(row.get("event_name") or ""), str(row.get("event_code") or "")
    if SPEECH_WORD in name and any(word in name for word in SPEECH_FED_WORDS):
        return "name"
    if code.startswith(SPEECH_CODE_PREFIXES) and code.endswith(SPEECH_CODE_SUFFIXES):
        return "event_code"
    return None


def _event(row: dict[str, Any], now: float) -> dict[str, Any]:
    return {"name": row["event_name"], "code": row["event_code"], "time_utc": iso(row["time_utc"]),
            "minutes_to": int((row["time_utc"] - now) // 60), "importance": row["importance"],
            "consensus": row.get("consensus"), "broker_forecast": num(row["forecast"]), "prev": num(row["prev"])}


def upcoming_facts(ahead: list[dict[str, Any]], now: float) -> dict[str, Any]:
    end = now + WINDOW_S
    high = [r for r in ahead if r["importance"] == HIGH_IMPORTANCE and r["time_utc"] > now]
    speeches = []
    for row in ahead:
        how = speech_match(row) if now < row["time_utc"] <= end else None
        if how:
            speeches.append({**_event(row, now), "matched_by": how})
    nxt = _event(high[0], now) if high else None
    return {"high": [_event(r, now) for r in high if r["time_utc"] <= end][:MAX_LISTED],
            "speeches": speeches[:MAX_LISTED], "next": nxt,
            "minutes": None if nxt is None else nxt["minutes_to"]}


def coming_facts(ahead: list[dict[str, Any]], now: float, fed_next: float | None) -> dict[str, Any]:
    """«ما هو جاي» لـ30 يومًا بأبواب المالك، وأوّل موعدٍ لكلّ باب بحدثه الرئيس."""
    rows = []
    for row in ahead:
        if not now < row["time_utc"] <= now + COMING_S:
            continue
        category = CATEGORY_CODES.get(row["event_code"]) or (SPEECH_CATEGORY if speech_match(row) else None)
        if category:
            rows.append({"name": row["event_name"], "code": row["event_code"], "category": category,
                         "time_utc": iso(row["time_utc"]), "days_to": round((row["time_utc"] - now) / 86400, 1),
                         "importance": row["importance"], "consensus": row.get("consensus"),
                         "broker_forecast": num(row["forecast"]), "prev": num(row["prev"])})
    dates = {key: next((day(r["time_utc"]) for r in ahead if r["event_code"] == code), None)
             for key, code in MAIN_CODES}
    dates["rate"] = day(fed_next)
    return {"rows": rows[:MAX_COMING], "count": len(rows), "next_dates": dates}


def _unit(row: dict[str, Any]) -> str:
    unit = UNIT_TEXT.get(int(row.get("unit") or 0), "")
    scale = MULTIPLIER_TEXT.get(int(row.get("multiplier") or 0), "")
    return " ".join(part for part in (scale, unit) if part)


def _diff(row: dict[str, Any], key: str = "forecast") -> float | None:
    """الفعليّ ناقص `forecast` (توقّع الوسيط) أو `consensus` (إجماع ناسداك)، بدقّة الحدث."""
    other = num(row.get(key))
    if row.get("actual") is None or other is None:
        return None
    return round(row["actual"] - other, int(row.get("digits") or 0) + 1)


def _values(row: dict[str, Any]) -> dict[str, Any]:
    """قيم الإصدار من كلّ مصدر: الفعليّ ومصدره، والإجماع وفرقه، وتوقّع الوسيط وفرقه، وخلاف المصادر."""
    return {"actual": row.get("actual"), "actual_source": row.get("actual_source"),
            "consensus": row.get("consensus"), "actual_minus_consensus": _diff(row, "consensus"),
            "broker_forecast": num(row.get("forecast")), "actual_minus_broker_forecast": _diff(row),
            "sources_disagree": row.get("sources_disagree"), "other_actuals": row.get("other_actuals")}


def last_release_facts(past: list[dict[str, Any]]) -> dict[str, Any] | None:
    """آخر إصدارٍ أمريكيّ مهمّ (أبواب المالك) له قيمة فعليّة — وعند التزامن الأسبق في ترتيب الأبواب."""
    order = {code: i for i, code in enumerate(CATEGORY_CODES)}
    rows = [r for r in past if r["event_code"] in order and r.get("actual") is not None]
    if not rows:
        return None
    row = max(rows, key=lambda r: (r["time_utc"], -order[r["event_code"]]))
    return {"name": row["event_name"], "code": row["event_code"], "time_utc": iso(row["time_utc"]),
            **_values(row), "unit": _unit(row), "digits": int(row.get("digits") or 0)}


def past_facts(past: list[dict[str, Any]], typical: dict[str, dict[str, Any]], now: float) -> dict[str, Any]:
    """ما صدر من العالي الأمريكيّ في 30 يومًا، وأكبر فروقه عن توقّع الوسيط (بالحجم المعتاد لفروق الحدث نفسه)."""
    rows = [r for r in past if r["importance"] == HIGH_IMPORTANCE and now - PAST_S < r["time_utc"] <= now]
    with_actual = [r for r in rows if r["actual"] is not None]
    diffs = []
    for row in with_actual:
        diff = _diff(row)
        if diff is None:
            continue
        usual = typical.get(row["event_code"]) or {}
        rms = usual.get("rms")
        diffs.append({"name": row["event_name"], "code": row["event_code"], "date_utc": day(row["time_utc"]),
                      **_values(row), "unit": _unit(row), "typical_diff": None if not rms else round(rms, 4),
                      "typical_n": usual.get("n"), "diff_to_typical": round(diff / rms, 2) if rms else None})
    diffs.sort(key=lambda d: -1.0 if d["diff_to_typical"] is None else abs(d["diff_to_typical"]), reverse=True)
    return {"window_days": PAST_DAYS, "n": len(rows), "n_with_actual": len(with_actual),
            "n_actual_from_bridge": sum(1 for r in with_actual if r["actual_source"] == "bridge"),
            "n_actual_from_nasdaq": sum(1 for r in with_actual if r["actual_source"] == "nasdaq"),
            "n_with_diff": len(diffs), "largest_diffs": diffs[:MAX_LARGEST], "ranking_rule_ar": RANKING_RULE_AR}


def release_facts(rows: list[dict[str, Any]], label: str) -> dict[str, Any]:
    """`rows` من الأحدث إلى الأقدم وكلّها حتّى الآن. آخر قيمة فعليّة، وأيّ إصدارٍ أحدث مرّ بلا قيمة."""
    known = next((r for r in rows if r["actual"] is not None), None)
    newer = [r for r in rows if r["actual"] is None and (known is None or r["time_utc"] > known["time_utc"])]
    out: dict[str, Any] = {"label_ar": label, "available": known is not None,
                           "passed_without_actual_utc": iso(newer[0]["time_utc"]) if newer else None}
    if known is None:
        return out
    out.update({"name": known["event_name"], "code": known["event_code"], "time_utc": iso(known["time_utc"]),
                **_values(known), "prev": num(known["prev"]), "revised_prev": num(known["revised_prev"]),
                "digits": int(known.get("digits") or 0), "unit": _unit(known)})
    return out


def _until_ar(minutes: int) -> str:
    if minutes < 60:
        return "%d د" % minutes
    if minutes < WINDOW_H * 60:
        return "%d س" % (minutes // 60)
    return "%d يومًا" % (minutes // (24 * 60))


def _fmt(value: float | None, digits: int) -> str:
    return "—" if value is None else "%.*f" % (digits, value)


def summary_ar(facts: dict[str, Any]) -> str:
    parts = []
    change, rate = facts.get("fed_last_change"), facts.get("fed_rate_current")
    if rate is None:
        parts.append("الفائدة: غير معروفة في المصدر")
    elif change:
        parts.append("الفائدة %.2f٪ (%s %d ن.أ في %s)" % (
            rate, "رُفعت" if change["change_bp"] > 0 else "خُفّضت", abs(change["change_bp"]), change["date_utc"]))
    else:
        parts.append("الفائدة %.2f٪" % rate)
    if facts.get("is_fomc_day"):
        parts.append("اليوم يوم قرار الفائدة")
    elif facts.get("days_to_next_fomc") is not None:
        parts.append("الاجتماع القادم بعد %d يومًا" % int(facts["days_to_next_fomc"]))
    else:
        parts.append("الاجتماع القادم: %s" % facts.get("next_fomc_unavailable_reason"))
    nxt = facts.get("next_high_impact_event")
    parts.append("القادم عالي الأهمّيّة: %s بعد %s" % (nxt["name"], _until_ar(nxt["minutes_to"])) if nxt
                 else "لا حدث عالي الأهمّيّة في أفق المصدر")
    core = (facts.get("releases") or {}).get("core_cpi_mm") or {}
    if core.get("available"):
        basis = "consensus" if core.get("consensus") is not None else "broker_forecast"
        parts.append("آخر تضخّم أساسيّ %s مقابل %s %s" % (
            _fmt(core["actual"], core["digits"]), BASIS_AR[basis], _fmt(core[basis], core["digits"])))
    last = facts.get("last_release_surprise")
    if last and last.get("consensus") is not None:
        parts.append("آخر إصدار مهمّ: %s %s مقابل الإجماع %s (%s)" % (
            last["name"], _fmt(last["actual"], last["digits"]), _fmt(last["consensus"], last["digits"]),
            last["time_utc"]))
    if facts.get("fed_speeches_next_48h_count"):
        parts.append("خطابات الفيدراليّ في %d س: %d" % (WINDOW_H, facts["fed_speeches_next_48h_count"]))
    dates = [(CATEGORY_AR[key], value) for key, value in (facts.get("next_dates") or {}).items() if value]
    if dates:
        parts.append("مواعيد قادمة: " + "، ".join("%s %s" % item for item in dates))
    past = facts.get("last_30d_high_impact") or {}
    parts.append("صدر في %d يومًا: %d عاليًا (بقيمة فعليّة %d)" % (
        PAST_DAYS, past.get("n") or 0, past.get("n_with_actual") or 0))
    if facts.get("sync_age_minutes") is not None:
        parts.append("التقويم حُدِّث قبل %d د" % int(facts["sync_age_minutes"]))
    return " · ".join(parts)


def build_facts(raw: dict[str, Any], now: float) -> dict[str, Any]:
    fed = fed_facts(raw["fed"], now, raw["horizon"])
    up = upcoming_facts(raw["ahead"], now)
    coming = coming_facts(raw["ahead"], now, fed["next_utc"])
    past = past_facts(raw["past"], raw.get("typical") or {}, now)
    releases = {key: release_facts(raw["releases"].get(code) or [], label) for key, code, label in RELEASES}
    meta, bridge, horizon = raw.get("meta") or {}, raw.get("bridge") or {}, raw["horizon"]
    econ = raw.get("econ") or {}
    exported, fetched = num(meta.get("exported_at_utc")), num(econ.get("fetched_at"))
    core = releases["core_cpi_mm"]
    # ٢٠٢٦-١٠-٠٨ (ختم المالك «NQ» — «عدّة مصادر تحت سقفٍ واحد»): فرق التضخّم الأساسيّ عن **الإجماع** حين يتوفّر
    # (ناسداك)، وإلّا عن توقّع الوسيط — والأساس مكتوبٌ في `core_cpi_mm_diff_basis`. الاسم باقٍ لأنّ الدفتر يختمه.
    core_basis = ("consensus" if core.get("actual_minus_consensus") is not None
                  else "broker_forecast" if core.get("actual_minus_broker_forecast") is not None else None)
    # ٢٠٢٦-١٠-٠٨ (أمر الوكيل الرئيس): أوّل عشر حقائق مفردة (رقم · نعم/لا · نصّ قصير) — يختمها دفتر البطاقات 465
    # بأسمائها على كلّ صفقة؛ والقواميس والقوائم وكلّ جديدٍ بعدها.
    return {
        "fed_rate_current": fed["current"],
        "fed_rate_previous": fed["previous"],
        "fed_last_change_bp": (fed["change"] or {}).get("change_bp"),
        "days_to_next_fomc": fed["days"],
        "is_fomc_day": fed["is_day"],
        "minutes_to_next_high_impact": up["minutes"],
        "high_impact_next_48h_count": len(up["high"]),
        "fed_speeches_next_48h_count": len(up["speeches"]),
        "core_cpi_mm_actual_minus_forecast": None if core_basis is None else core["actual_minus_" + core_basis],
        "source_age_hours": None if exported is None else round((now - exported) / 3600, 1),
        "core_cpi_mm_diff_basis": core_basis,
        "last_release_surprise": last_release_facts(raw["past"]),
        "econ_calendar_available": bool(econ.get("available")),
        "econ_calendar_age_minutes": None if fetched is None else int((now - fetched) // 60),
        "econ_calendar_unavailable_reason": econ.get("reason"),
        "econ_calendar_rows": econ.get("rows"),
        "econ_calendar_matched": econ.get("matched"),
        "econ_calendar_unmatched": econ.get("unmatched"),
        "econ_calendar_unmatched_sample": [{"name": u["name"], "time_utc": iso(u["at"])}
                                           for u in econ.get("unmatched_sample") or []],
        "sources_disagree": [{**d, "time_utc": iso(d["time_utc"])} for d in econ.get("disagree") or []],
        "consensus_source": "nasdaq",
        "calendar_horizon_utc": iso(horizon),
        "calendar_days_ahead": None if horizon is None else round((horizon - now) / 86400, 1),
        "sync_mode": meta.get("sync_mode"),
        "sync_age_minutes": None if exported is None else int((now - exported) // 60),
        "next_dates": coming["next_dates"],
        "coming_30d_count": coming["count"],
        "coming_30d": coming["rows"],
        "last_30d_high_impact": past,
        "fed_last_change": fed["change"],
        "fed_rate_current_source": fed["current_source"],
        "fed_decisions_count": fed["count"],
        "fed_first_decision_date": fed["first_date"],
        "fed_cycle": fed["cycle"],
        "fed_decision_passed_without_actual_utc": fed["unreported_utc"],
        "next_fomc_date_utc": iso(fed["next_utc"]),
        "hours_to_next_fomc": fed["hours"],
        "next_fomc_unavailable_reason": fed["next_reason"],
        "next_high_impact_event": up["next"],
        "high_impact_next_48h": up["high"],
        "fed_speeches_next_48h": up["speeches"],
        "window_48h_within_source": horizon is not None and horizon >= now + WINDOW_S,
        "releases": releases,
        "actual_minus_consensus_label_ar": "فرق الفعليّ عن الإجماع",
        "actual_minus_broker_forecast_label_ar": DIFF_LABEL_AR,
        "broker_forecast_is_consensus": False,
        "forecast_note_ar": FORECAST_NOTE_AR,
        "fed_rate_note_ar": RATE_NOTE_AR,
        "fed_pricing_available": False,
        "fed_pricing_unavailable_reason": PRICING_REASON_AR,
        "bridge_available": bridge.get("available"),
        "bridge_unavailable_reason": bridge.get("reason"),
        "bridge_rows_3d": bridge.get("rows_3d"),
        "bridge_rows_3d_with_actual": bridge.get("rows_3d_with_actual"),
        "actuals_from_bridge": bridge.get("actuals_filled"),
        "source_available": True,
        "source_exported_at_utc": iso(exported),
        "source_rows": raw["rows"],
        "source_server": meta.get("server"),
        "sync_days_ahead_setting": num(meta.get("horizon_days_ahead")),
        "sync_last_rows": num(meta.get("last_sync_rows")),
        "sync_failed_chunks": num(meta.get("failed_chunks")),
        "time_rule": "time_server - 3h = UTC",
    }
