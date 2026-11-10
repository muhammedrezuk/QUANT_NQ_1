"""حقائق تسعير قرار الفائدة وسطرها العربيّ (121) — دوالّ صافية بلا شبكة ولا حالة.

٢٠٢٦-١٠-٠٨ (ختم المالك «NQ» — المعرفة أوّلًا): من آخر أسعار العقود (وأعمارها) وجدول الاجتماعات والحدّ الأعلى
للنطاق تُبنى الحقائق: أوّل عشر مفردة يختمها دفتر البطاقات على كلّ صفقة، ثمّ تفاصيل كلّ اجتماعٍ وعقوده.
لا كلمة «احتمال» ولا «ثقة» (عقد الحقائق ١٠-٠٧): النسب «مسعَّرة في السوق» — سعرٌ لا حكم ذرّة ولا توقّع النظام.

٢٠٢٦-١٠-٠٨ (ختم المالك «NQ» — «الأخبار من مكانٍ واحد … تحت سقفٍ واحد»): الأسعار يجلبها بوت الأخبار من ياهو إلى
جدول الجسر `fed_futures`، والذرّة تقرأ ما فيه وحده: النافذة = الشهر الجاري حتّى آخر شهرٍ في الجدول (لا عدد أشهرٍ
في الإعداد). عمران معلنان: عمر سعر السوق (`quotes_age_minutes`) وعمر جلب البوت (`fetched_age_minutes`).
غياب القاعدة أو الجدول ⟸ «غير متاح» بسببه، وآخر الأسعار المعروفة تبقى في التفاصيل بأعمارها ولا يُسعَّر منها.
"""
from __future__ import annotations

import time
from datetime import date
from typing import Any

import fed_pricing_chain as chain

DETAIL_CHARS = 160
REPORTED_MEETINGS = 3                  # الاجتماعات الثلاثة القادمة
SUMMARY_MEETINGS = 2
MAX_WINDOW_MONTHS = 12                 # سقف النافذة على شهرٍ شاذّ في الجدول (البوت يكتب الجاري وخمسة بعده)
TARGET_SOURCE = "knowledge.monetary.state · fed_rate_current = upper bound (118)"
AGE_BASIS = ("quotes_age_minutes = oldest market time, fetched_age_minutes = oldest bot fetch time — among the "
             "contracts used for the next meeting (else among all known contracts)")
DECISION_RULE = "14:00 America/New_York, effective next day"

# أسباب غياب التسعير
NOT_READ = "NOT_READ_YET"
BRIDGE_MISSING = "BRIDGE_FILE_MISSING"
TABLE_MISSING = "BRIDGE_TABLE_MISSING"
READ_FAILED = "BRIDGE_READ_FAILED"
NO_ROWS = "NO_CONTRACTS_IN_BRIDGE"
NO_SCHEDULE = "NO_UPCOMING_MEETING_IN_CONFIG"
NO_MEETING_IN_WINDOW = "NO_MEETING_IN_CONTRACT_WINDOW"
MISSING_CONTRACTS = "MISSING_CONTRACTS"
COMPUTE_FAILED = "COMPUTE_FAILED"
STRUCTURAL = (BRIDGE_MISSING, TABLE_MISSING)   # غيابٌ بنيويّ: لا يُسعَّر من أسعارٍ محفوظة
REASON_AR = {NOT_READ: "لم تُقرأ قاعدة الجسر بعد", BRIDGE_MISSING: "قاعدة الجسر غير موجودة",
             TABLE_MISSING: "جدول الجسر غير موجود بعد", READ_FAILED: "تعذّرت قراءة جدول الجسر",
             NO_ROWS: "لا عقود في جدول الجسر للشهر الجاري وما بعده", NO_SCHEDULE: "لا اجتماع قادم في جدول الإعداد",
             NO_MEETING_IN_WINDOW: "الاجتماع القادم خارج نافذة العقود",
             MISSING_CONTRACTS: "عقودٌ ناقصة لحساب الاجتماع القادم",
             COMPUTE_FAILED: "تعذّر حساب التسعير من الأسعار المحفوظة"}
# أوّل عشر حقائق مفردة بترتيبها — يختمها دفتر البطاقات على كلّ صفقة (ثابتة الأسماء حتّى في الغياب).
FIRST_TEN = ("next_fomc_date", "days_to_next_fomc", "expected_change_bp_next", "market_implied_hike_pct_next",
             "market_implied_cut_pct_next", "implied_rate_after_next", "expected_change_bp_second",
             "implied_rate_year_end", "quotes_age_minutes", "pricing_available")

MONTH_AR = ("كانون الثاني", "شباط", "آذار", "نيسان", "أيّار", "حزيران", "تمّوز", "آب", "أيلول",
            "تشرين الأوّل", "تشرين الثاني", "كانون الأوّل")
METHOD_AR = ("الضمنيّ = 100 − سعر العقد = متوسّط الفائدة الفعليّة اليوميّ في شهره، والقرار يسري من اليوم التالي. "
             "شهرٌ بلا اجتماع يثبّت الفائدة السارية فيه؛ وشهر الاجتماع: ضمنيّه × أيّامه = قبله × يوم القرار + بعده × "
             "باقي الأيّام (أماميًّا ثمّ خلفيًّا). والنسبة = |الفرق| ÷ 25 ن.أ، وما فوق 100٪ جزؤه لتحريك 50 ن.أ.")
LIMITS_AR = ("أسعار ياهو (يجلبها بوت الأخبار إلى الجسر) قد تتأخّر ~10–20 دقيقة عن البورصة — عمر سعر السوق وعمر "
             "الجلب منشوران مع كلّ حمولة",
             "اجتماعات 2027 مبدئيّة حتّى يؤكّدها الفيدراليّ",
             "هذا تسعير السوق لا توقّع النظام ولا حكمه",
             "إن تعذّرت قراءة الجدول لحظةً بقيت آخر الأسعار المقروءة وأعمارها تكبر معلنةً؛ وغياب القاعدة أو الجدول "
             "يُعلن «غير متاح»")


def iso(ts: float | None) -> str | None:
    return None if ts is None else time.strftime("%Y-%m-%dT%H:%MZ", time.gmtime(ts))


def minutes(now: float, ts: float | None) -> int | None:
    return None if ts is None else max(0, int((now - ts) // 60))


def parse_label(label: str) -> tuple[int, int] | None:
    """«YYYY-MM» ⟸ (السنة، الشهر) أو None."""
    try:
        year, month = (int(part) for part in str(label).split("-"))
    except ValueError:
        return None
    return (year, month) if 1 <= month <= chain.MONTHS_PER_YEAR else None


def window(now: float, quotes: dict[str, Any]) -> list[tuple[int, int]]:
    """الشهر الجاري (بغرينتش) حتّى آخر شهرٍ في الجدول — متّصلة، والفجوات عقودٌ ناقصة معلنة."""
    today = time.gmtime(now)
    first = (today.tm_year, today.tm_mon)
    months = [ym for ym in (parse_label(label) for label in quotes) if ym is not None and ym >= first]
    if not months:
        return [first]
    span = (max(months)[0] - first[0]) * chain.MONTHS_PER_YEAR + max(months)[1] - first[1]
    return [chain.month_add(first[0], first[1], k) for k in range(min(span, MAX_WINDOW_MONTHS - 1) + 1)]


def _contracts(months: list, quotes: dict, bad_rows: list, now: float) -> tuple[list[dict[str, Any]], dict]:
    rows, implied = [], {}
    for ym in months:
        label, symbol = chain.month_label(ym), chain.contract_symbol(*ym)
        quote = quotes.get(label)
        implied[ym] = None if quote is None else round(100 - quote["price"], chain.IMPLIED_DIGITS)
        rows.append({"symbol": symbol, "month": label, "available": quote is not None,
                     "price": None if quote is None else quote["price"], "implied_rate": implied[ym],
                     "market_time_utc": iso(quote and quote["market_time"]),
                     "age_minutes": minutes(now, quote and quote["market_time"]),
                     "fetched_at_utc": iso(quote and quote.get("fetched_at")),
                     "fetched_age_minutes": minutes(now, quote and quote.get("fetched_at")),
                     "source": None if quote is None else quote.get("source"),
                     "bridge_row_invalid": symbol in bad_rows})
    return rows, implied


def _reason(rows: list, contracts: list, nxt: dict | None, last_read: dict | None) -> tuple[str, str]:
    read = last_read or {}
    if read.get("error") in STRUCTURAL:
        kept = sum(1 for c in contracts if c["available"])
        return read["error"], ("%s · last known contracts kept with their ages: %d" % (read.get("detail"), kept))
    if nxt is None:
        return NO_SCHEDULE, ""
    if not any(c["available"] for c in contracts):
        if last_read is None:
            return NOT_READ, ""
        return (read["error"], str(read.get("detail") or "")) if read.get("error") else (NO_ROWS, "")
    if not rows:
        return NO_MEETING_IN_WINDOW, ""
    return MISSING_CONTRACTS, " ".join(c["symbol"] for c in contracts if not c["available"])


def build_facts(state: dict[str, Any], now: float) -> dict[str, Any]:
    quotes, last_read = state["quotes"], state["last_read"]
    read = last_read or {}
    months = window(now, quotes)
    contracts, implied = _contracts(months, quotes, list(read.get("bad_rows") or []), now)
    structural = read.get("error") in STRUCTURAL
    path = chain.solve_path(months, {} if structural else implied, state["schedule"], now)
    upper = state["target_upper"]
    mid = None if upper is None else upper - chain.TARGET_HALF_WIDTH
    by_symbol = {c["symbol"]: c for c in contracts}
    rows = chain.meeting_rows(path, now, mid)[:REPORTED_MEETINGS]
    for row in rows:
        row["contracts_used"] = [{key: by_symbol[s][key] for key in ("symbol", "month", "price", "implied_rate",
                                                                     "market_time_utc", "fetched_at_utc")}
                                 for s in row.pop("_deps") if s in by_symbol]
    nxt = next((m for m in state["schedule"] if m["utc"] > now), None)
    first = rows[0] if rows and nxt is not None and rows[0]["date"] == nxt["day"].isoformat() else None
    second = rows[1] if first is not None and len(rows) > 1 else None
    available = first is not None and first["expected_change_bp"] is not None
    used = [quotes[c["month"]] for c in (first["contracts_used"] if available else contracts) if c["month"] in quotes]
    fetched = [q["fetched_at"] for q in used if q.get("fetched_at") is not None]
    year = chain.year_end(path, state["schedule"], now)
    r0 = path["rates"][0]
    reason, detail = (None, "") if available else _reason(rows, contracts, nxt, last_read)
    pick = (lambda row, key: None if row is None else row[key])
    # ٢٠٢٦-١٠-٠٨ (أمر الوكيل الرئيس): أوّل عشر حقائق مفردة يختمها دفتر البطاقات بأسمائها على كلّ صفقة؛ والتفاصيل بعدها.
    return {
        "next_fomc_date": None if nxt is None else nxt["day"].isoformat(),
        "days_to_next_fomc": None if nxt is None else round((nxt["utc"] - now) / 86400, 1),
        "expected_change_bp_next": pick(first, "expected_change_bp"),
        "market_implied_hike_pct_next": pick(first, "market_implied_hike_pct"),
        "market_implied_cut_pct_next": pick(first, "market_implied_cut_pct"),
        "implied_rate_after_next": pick(first, "rate_after"),
        "expected_change_bp_second": pick(second, "expected_change_bp"),
        "implied_rate_year_end": year["rate"],
        "quotes_age_minutes": minutes(now, min(q["market_time"] for q in used)) if used else None,
        "pricing_available": available,
        "fetched_age_minutes": minutes(now, min(fetched)) if fetched else None,
        "pricing_unavailable_reason": reason,
        "pricing_unavailable_reason_ar": None if reason is None else REASON_AR.get(reason, reason),
        "pricing_unavailable_detail": (detail or "")[:DETAIL_CHARS] or None,
        "next_fomc_decision_utc": None if nxt is None else iso(nxt["utc"]),
        "next_fomc_tentative": None if nxt is None else nxt["tentative"],
        "implied_rate_now": None if r0 is None else round(r0, chain.IMPLIED_DIGITS),
        "implied_rate_now_method": path["how"][0],
        "fed_target_upper": upper,
        "fed_target_mid": mid,
        "implied_now_vs_target_mid_bp": None if r0 is None or mid is None else round((r0 - mid) * 100, chain.BP_DIGITS),
        "fed_target_received_at_utc": iso(state["target_at"]),
        "fed_target_source": TARGET_SOURCE,
        "year_end_last_meeting_date": year["meeting"],
        "implied_rate_year_end_unavailable_reason": year["reason"] or (
            MISSING_CONTRACTS if year["rate"] is None else None),
        "meetings": rows,
        "contracts": contracts,
        "contracts_in_window": len(contracts),
        "contracts_available": sum(1 for c in contracts if c["available"]),
        "quotes_age_basis": AGE_BASIS,
        "bridge_read_utc": iso(read.get("at")),
        "bridge_read_error": read.get("error"),
        "bridge_read_detail": read.get("detail") or None,
        "bridge_rows": read.get("rows"),
        "bridge_bad_rows": list(read.get("bad_rows") or []),
        "fomc_schedule_source": state["schedule_source"],
        "fomc_tentative_dates": [m["day"].isoformat() for m in state["schedule"] if m["tentative"]],
        "decision_time_rule": DECISION_RULE,
        "method_ar": METHOD_AR,
        "limits_ar": list(LIMITS_AR),
    }


def failed_facts(detail: str) -> dict[str, Any]:
    """خطأ حسابٍ غير متوقَّع ⟸ حقائق «غير متاح» بسببه، بالأسماء نفسها — لا انهيار للذرّة."""
    facts: dict[str, Any] = dict.fromkeys(FIRST_TEN)
    facts.update({"pricing_available": False, "pricing_unavailable_reason": COMPUTE_FAILED,
                  "pricing_unavailable_reason_ar": REASON_AR[COMPUTE_FAILED],
                  "pricing_unavailable_detail": detail[:DETAIL_CHARS], "meetings": [], "limits_ar": list(LIMITS_AR)})
    return facts


def _meeting_ar(row: dict[str, Any]) -> str:
    day = date.fromisoformat(row["date"])
    return "%d %s%s" % (day.day, MONTH_AR[day.month - 1], " (مبدئيّ)" if row["tentative"] else "")


def _move_ar(row: dict[str, Any]) -> str:
    change = row["expected_change_bp"]
    if change is None:
        return "غير محسوب (عقود ناقصة)"
    text = "%+d ن.أ" % round(change)
    for kind, word in (("hike", "رفع"), ("cut", "خفض")):
        if row["market_implied_%s_50bp_pct" % kind]:
            return text + " (%s 100٪ ومنه 50 ن.أ %d٪)" % (word, round(row["market_implied_%s_50bp_pct" % kind]))
        if round(row["market_implied_%s_pct" % kind]):
            return text + " (%s %d٪)" % (word, round(row["market_implied_%s_pct" % kind]))
    return text + " (لا تحريك مسعَّر)"


def _age_ar(age: int) -> str:
    if age < 60:
        return "%d د" % age
    if age < 24 * 60:
        return "%d س" % (age // 60)
    return "%d يومًا" % (age // (24 * 60))


def _until_ar(days: float) -> str:
    return "بعد %d يومًا" % int(days) if days >= 1 else "بعد %d س" % int(days * 24)


def summary_ar(facts: dict[str, Any]) -> str:
    rows = facts["meetings"]
    if not facts["pricing_available"]:
        text = "تسعير قرار الفائدة غير متاح: %s" % facts["pricing_unavailable_reason_ar"]
        if facts["next_fomc_date"]:
            day = date.fromisoformat(facts["next_fomc_date"])
            text += " · الاجتماع القادم %d %s %s" % (day.day, MONTH_AR[day.month - 1],
                                                    _until_ar(facts["days_to_next_fomc"]))
        return text
    head = rows[0]
    parts = ["السوق يسعّر لاجتماع %s (%s): %s" % (_meeting_ar(head), _until_ar(head["days_to"]), _move_ar(head))]
    parts += ["%s: %s" % (_meeting_ar(row), _move_ar(row)) for row in rows[1:SUMMARY_MEETINGS]]
    if facts["quotes_age_minutes"] is not None:
        age = "الأسعار من ياهو قبل %s" % _age_ar(facts["quotes_age_minutes"])
        if facts.get("fetched_age_minutes") is not None:
            age += " (جلبها بوت الأخبار قبل %s)" % _age_ar(facts["fetched_age_minutes"])
        parts.append(age)
    return " · ".join(parts)
