"""تجميع حقائق «معرفة الشركات والأسواق» (122) بترتيبها وسطرها العربيّ — دوالّ صافية بلا حكم.

٢٠٢٦-١٠-٠٨ (ختم المالك «NQ» — المعرفة أوّلًا): ترتيب `facts` مقصود — دفتر البطاقات 465 يختم على كلّ صفقة أوّل عشر
حقائق مفردة (`fact_summary`)، فأوّلها: كم صاعدة · كم هابطة · حركة الناسداك · متوسّط حركة الشركات · الفرق الخام بينهما ·
مستوى الخوف وحركته · حركة الدولار · الشركة التالية بأرباحها وأيّامها. ومع كلّ متوسّطٍ عدد عيّنته `n`.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import companies_earnings as earnings
import companies_quotes as quotes

STATUS_OK = "ok"
STATUS_PARTIAL = "partial"
STATUS_UNAVAILABLE = "unavailable"
NOT_READ_YET = "NOT_READ_YET"
INDEXES = {"vix": "VIX", "dxy": "DXY"}
PCT_DIGITS = 3
HOURS_DIGITS = 1
SUMMARY_UPCOMING = 3
NASDAQ_STALE_MIN = 10.0           # آخر سعرٍ للناسداك أقدم من عشر دقائق ⟸ يُذكر يومه وعمره في السطر
LIMITS_AR = "مواعيد الأرباح قد تكون تقديريّة حتّى تؤكّدها الشركة؛ وأسعار الأسهم بائتة خارج الجلسة الأمريكيّة"
NAMES_AR = {"NVDA": "إنفيديا", "MSFT": "مايكروسوفت", "AAPL": "أبل", "AMZN": "أمازون", "AVGO": "برودكوم",
            "META": "ميتا", "GOOGL": "ألفابت (أ)", "GOOG": "ألفابت (ج)", "TSLA": "تسلا", "COST": "كوستكو",
            "NFLX": "نتفليكس", "AMD": "إيه إم دي", "PLTR": "بالانتير", "CSCO": "سيسكو", "TMUS": "تي‑موبايل"}
TIME_AR = {earnings.PRE_MARKET: "قبل الافتتاح", earnings.AFTER_HOURS: "بعد الإغلاق",
           earnings.NOT_SUPPLIED: "الوقت غير معلن"}
REASON_AR = {
    quotes.NO_FILE: "قاعدة أسعار الشركات غير موجودة (يكتبها إكسبرت أسعار الشركات)",
    quotes.READ_FAILED: "تعذّرت قراءة قاعدة أسعار الشركات",
    quotes.NO_ROWS: "قاعدة أسعار الشركات فارغة",
    earnings.NO_FILE: "قاعدة الجسر غير موجودة",
    earnings.READ_FAILED: "تعذّرت قراءة قاعدة الجسر",
    earnings.NO_TABLES: "جدولا الأرباح غير موجودين في قاعدة الجسر بعد (يكتبهما بوت الأخبار)",
    earnings.NO_ROWS: "جدولا الأرباح بلا صفوفٍ لشركاتنا",
    NOT_READ_YET: "لم تُقرأ بعد",
    quotes.NOT_AT_BROKER: "غير موجود عند الوسيط",
    quotes.NO_ROW: "لم يكتب له الإكسبرت صفًّا",
    quotes.NO_PRICE: "بلا سعر",
}


def iso_utc(ts: float | None) -> str | None:
    return None if ts is None else datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%dT%H:%MZ")


def _field(quote: dict[str, Any] | None, name: str) -> Any:
    return (quote or {}).get(name)


def build_facts(stocks: dict[str, Any] | None, nasdaq_facts: dict[str, Any], earnings_raw: dict[str, Any] | None,
                observed: dict[str, dict[str, Any]], moves: dict, history_state: dict[str, Any] | None,
                tickers: list[str], now: float) -> tuple[dict[str, Any], str]:
    """الحقائق كلّها بترتيبها، وحال المصدرين (`ok` كلاهما · `partial` أحدهما · `unavailable` لا شيء)."""
    source = quotes.stocks_status(stocks, now)
    meta = (stocks or {}).get("meta") or {}
    rows = (stocks or {}).get("rows") or {}
    offset = quotes.num(meta.get("server_offset_s")) or 0.0
    have_stocks = bool(source["stocks_available"])
    companies = {t: quotes.quote_facts(rows.get(t), now, offset) for t in tickers} if have_stocks else {}
    index = {name: quotes.quote_facts(rows.get(t), now, offset) if have_stocks else None
             for name, t in INDEXES.items()}
    spread = quotes.breadth(companies, tickers)
    avg, ndx = spread["companies_avg_change_pct"], nasdaq_facts.get("nasdaq_change_pct")
    session = quotes.us_session_open(now)
    # ٢٠٢٦-١٠-٠٨ (ختم المالك «NQ» — المعرفة أوّلًا): الفرق الخام بين الشركات والناسداك على **اليوم نفسه** وحده.
    # مقيس اليوم: آخر M1 في قاعدة التاريخ من 10-06 — فبلا شموعٍ حيّة كانت حركة الناسداك حركةَ يومٍ مضى تُطرح من حركة اليوم.
    days = [q.get("day_bar_date") for q in companies.values() if q.get("change_pct") is not None]
    stocks_day = max(sorted(set(days)), key=days.count) if days else None
    same_day = stocks_day is not None and stocks_day == nasdaq_facts.get("nasdaq_day")

    e_ok = bool(earnings_raw) and not earnings_raw.get("error")
    today = earnings.ny_today(now)
    e_companies = (earnings_raw or {}).get("companies") or {} if e_ok else {}
    per_history, reaction = earnings.reaction_history(e_companies, observed, moves, today) if e_ok else ({}, None)
    per = {t: earnings.company_facts(e_companies[t], per_history.get(t), today, now)
           for t in tickers if t in e_companies}
    upcoming = earnings.upcoming_facts(per, today) if e_ok else {}
    fetched = (earnings_raw or {}).get("fetched_at")
    history_state = history_state or {}
    missing_at_broker = sorted(t for t, q in {**companies, **{INDEXES[k]: v for k, v in index.items() if v}}.items()
                               if q.get("unavailable_reason") == quotes.NOT_AT_BROKER)
    facts: dict[str, Any] = {
        "rising_count": spread["rising_count"], "falling_count": spread["falling_count"],
        "nasdaq_change_pct": ndx, "companies_avg_change_pct": avg,
        "companies_minus_nasdaq_pct": round(avg - ndx, PCT_DIGITS) if same_day and avg is not None and ndx is not None
        else None,
        "vix_level": _field(index["vix"], "price"), "vix_change_pct": _field(index["vix"], "change_pct"),
        "dxy_change_pct": _field(index["dxy"], "change_pct"),
        "next_earnings_ticker": upcoming.get("next_earnings_ticker"),
        "days_to_next_earnings": upcoming.get("days_to_next_earnings"),
        # ── بعد العشر الأولى ──
        "earnings_today_count": upcoming.get("earnings_today_count"),
        "max_change_ticker": spread["max_change_ticker"], "max_change_pct": spread["max_change_pct"],
        "min_change_ticker": spread["min_change_ticker"], "min_change_pct": spread["min_change_pct"],
        "unchanged_count": spread["unchanged_count"], "change_n": spread["change_n"],
        "dxy_level": _field(index["dxy"], "price"),
        "us_session_open": session, "stock_prices_stale": not session,
        "stocks_day": stocks_day, "nasdaq_same_day_as_stocks": same_day,
        **source, "stocks_missing_at_broker": missing_at_broker,
        "vix_broker_symbol": _field(index["vix"], "broker_symbol"),
        "vix_unavailable_reason": _field(index["vix"], "unavailable_reason"),
        "dxy_broker_symbol": _field(index["dxy"], "broker_symbol"),
        "dxy_unavailable_reason": _field(index["dxy"], "unavailable_reason"),
        **nasdaq_facts,
        "earnings_available": e_ok,
        "earnings_unavailable_reason": None if e_ok else (earnings_raw or {}).get("error", NOT_READ_YET),
        "earnings_missing_tables": (earnings_raw or {}).get("missing_tables"),
        "earnings_last_read_error": (earnings_raw or {}).get("last_read_error"),
        "earnings_fetched_at_utc": iso_utc(fetched),
        "earnings_fetch_age_h": None if fetched is None else round((now - fetched) / 3600.0, HOURS_DIGITS),
        "earnings_companies_n": len(per),
        "earnings_with_date_n": sum(1 for f in per.values() if f["next_date"]),
        "earnings_dates_estimated_n": sum(1 for f in per.values() if f["date_is_estimated"]),
        "next_earnings_date": upcoming.get("next_earnings_date"),
        "next_earnings_time": upcoming.get("next_earnings_time"),
        "next_earnings_date_is_estimated": upcoming.get("next_earnings_date_is_estimated"),
        "earnings_this_week_count": upcoming.get("earnings_this_week_count"),
        "earnings_this_week": upcoming.get("earnings_this_week"),
        "earnings_upcoming": upcoming.get("earnings_upcoming"),
        "nasdaq_history_available": not history_state.get("error") and bool(history_state),
        "nasdaq_history_unavailable_reason": history_state.get("error") if history_state else NOT_READ_YET,
        "nasdaq_history_days_n": len(moves),
        "earnings_reaction_history": reaction,
        "companies": companies, "indexes": index, "earnings": per,
        "limits_ar": LIMITS_AR,
    }
    status = STATUS_OK if have_stocks and e_ok else STATUS_PARTIAL if have_stocks or e_ok else STATUS_UNAVAILABLE
    return facts, status


def signed(value: float) -> str:
    return ("%+.1f٪" % value).replace("-", "−")


def days_ar(days: int) -> str:
    if days == 0:
        return "اليوم"
    if days == 1:
        return "غدًا"
    if days == 2:
        return "بعد يومين"
    return ("بعد %d أيّام" if days <= 10 else "بعد %d يومًا") % days


def name_ar(ticker: Any) -> str:
    return NAMES_AR.get(str(ticker), str(ticker))


def _level(label: str, level: Any, change: Any, reason: Any) -> str:
    if level is None:
        return "%s غير متاح (%s)" % (label, REASON_AR.get(reason, reason or "بلا سعر"))
    return "%s %.1f%s" % (label, level, "" if change is None else " (%s)" % signed(change))


def summary_ar(facts: dict[str, Any]) -> str:
    """سطرٌ واحد يقرؤه المالك — الأرقام نفسها التي في `facts`."""
    parts: list[str] = []
    if facts.get("change_n"):
        head = "الشركات الآن: %d صاعدة · %d هابطة" % (facts["rising_count"], facts["falling_count"])
        if facts.get("unchanged_count"):
            head += " · %d بلا تغيّر" % facts["unchanged_count"]
        parts += [head, "الأعلى %s %s" % (name_ar(facts["max_change_ticker"]), signed(facts["max_change_pct"])),
                  "الأدنى %s %s" % (name_ar(facts["min_change_ticker"]), signed(facts["min_change_pct"]))]
    else:
        reason = facts.get("stocks_unavailable_reason")
        parts.append("أسعار الشركات غير متاحة: %s" % REASON_AR.get(reason, reason or "لا حركة محسوبة"))
    ndx, age = facts.get("nasdaq_change_pct"), facts.get("nasdaq_last_age_min")
    if ndx is None:
        parts.append("حركة الناسداك غير معروفة بعد")
    elif age is not None and age > NASDAQ_STALE_MIN:
        parts.append("الناسداك %s (يوم %s، آخر سعرٍ قبل %.1f س)" % (signed(ndx), facts.get("nasdaq_day"), age / 60.0))
    else:
        parts.append("الناسداك %s" % signed(ndx))
    if facts.get("stocks_available"):
        parts.append(_level("الخوف", facts.get("vix_level"), facts.get("vix_change_pct"),
                            facts.get("vix_unavailable_reason")))
        parts.append(_level("الدولار", facts.get("dxy_level"), facts.get("dxy_change_pct"),
                            facts.get("dxy_unavailable_reason")))
    upcoming = facts.get("earnings_upcoming") or []
    if upcoming:
        parts.append("الأرباح القادمة: " + "، ثمّ ".join(
            "%s %s (%s%s)" % (name_ar(r["ticker"]), days_ar(r["days_to"]), TIME_AR.get(r["time"], "الوقت غير معلن"),
                              "، تقديريّ" if r["date_is_estimated"] else "")
            for r in upcoming[:SUMMARY_UPCOMING]))
    elif facts.get("earnings_available"):
        parts.append("لا موعد أرباح قادم معروف لشركاتنا")
    else:
        reason = facts.get("earnings_unavailable_reason")
        parts.append("مواعيد الأرباح غير متاحة: %s" % REASON_AR.get(reason, reason))
    if facts.get("stocks_available") and facts.get("stock_prices_stale"):
        parts.append("أسعار الأسهم بائتة: خارج الجلسة الأمريكيّة")
    return " · ".join(parts)
