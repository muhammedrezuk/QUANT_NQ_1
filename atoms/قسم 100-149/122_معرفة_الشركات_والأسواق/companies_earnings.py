"""مواعيد أرباح الشركات (122) — من قاعدة الجسر قراءةً فقط، وحقائقها دوالّ صافية بلا حكم.

٢٠٢٦-١٠-٠٨ (ختم المالك «NQ» — المعرفة أوّلًا، وأمره «الأخبار من مكانٍ واحد — ما نشتّت، نجمعهم تحت سقفٍ واحد»):
الذرّة لا تتّصل بالإنترنت أبدًا. بوت الأخبار (مشروع QUANT_NQ_NEWS) يجلب من موقع بورصة ناسداك الرسميّ مرّةً في اليوم
ويكتب في قاعدة الجسر `nq_brain.db` جدولين، وهنا يُقرآن كلّ `SYS_5MIN` (`mode=ro` ومهلة قفلٍ قصيرة، في خيطٍ جانبيّ):
  earnings_calendar (ticker مفتاح · report_date · report_time pre-market|after-hours|not-supplied · is_estimated 1/0 ·
                     eps_consensus · source_text نصّ الموقع كما هو · fetched_at_utc · source)
  earnings_history  (ticker · date_reported · fiscal_qtr_end · eps · eps_consensus · surprise_pct · fetched_at_utc · source)
غياب القاعدة أو الجدولين ⟸ حقائق الأرباح «غير متاحة» بسببها، والباقي يعمل.

والتاريخ: أيّام إعلانات كلّ شركة الأربعة الأخيرة ⟸ حركة الناسداك في جلسة ردّ الفعل (اليوم التالي إن كان الإعلان
بعد الإغلاق، ويومه إن كان قبل الافتتاح) مقابل الأيّام العاديّة — للعلم لا للقرار. وجدول التاريخ بلا وقت إعلان: فوقتُ
كلّ إعلانٍ رُئي في التقويم يُحفظ («observed»)، وما لم يُرَ يُفترض بآخر وقتٍ رُئي للشركة نفسها ويُعلن تاريخ مصدره
(«assumed_latest_observed»)، وما لا وقت له يُعدّ ولا يدخل ردّ الفعل. وحركتا يوم الإعلان واليوم التالي تُنشران لكلّ إعلان.
"""
from __future__ import annotations

import bisect
import os
import sqlite3
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import companies_quotes as quotes
from shared.owner_windows import new_york_offset_h

NO_FILE = "BRIDGE_DB_MISSING"
READ_FAILED = "BRIDGE_DB_READ_FAILED"
NO_TABLES = "EARNINGS_TABLES_MISSING"
NO_ROWS = "EARNINGS_TABLES_EMPTY"
CALENDAR_TABLE = "earnings_calendar"
HISTORY_TABLE = "earnings_history"
BRIDGE_TIMEOUT_S = 1.0            # الإكسبرت الحيّ يكتب في الجسر: مهلة قفلٍ قصيرة ثمّ «غير متاح» (كما 118)
DETAIL_CHARS = 160
TEXT_CHARS = 1000
HISTORY_ROWS = 4
PCT_DIGITS = 3
HOURS_DIGITS = 1
MAX_GAP_DAYS = 4                  # يوم التداول التالي لإعلانٍ لا يبعد أكثر من عطلة أسبوعٍ طويلة
OBSERVED_KEEP = 400
WORK_DAYS_SPAN = 4                # الاثنين ⟶ الجمعة
DAYS_IN_WEEK = 7

PRE_MARKET = "pre_market"
AFTER_HOURS = "after_hours"
NOT_SUPPLIED = "not_supplied"
TIME_OF = {"pre-market": PRE_MARKET, "after-hours": AFTER_HOURS, "not-supplied": NOT_SUPPLIED}
#: ترتيب إعلانات اليوم الواحد: قبل الافتتاح أوّلًا ثمّ غير المعلن ثمّ بعد الإغلاق.
TIME_ORDER = {PRE_MARKET: 0, NOT_SUPPLIED: 1, AFTER_HOURS: 2}
BASIS_OBSERVED = "observed"
BASIS_ASSUMED = "assumed_latest_observed"
BASIS_UNKNOWN = "unknown"


def parse_day(text: Any) -> date | None:
    try:
        return date.fromisoformat(str(text or "").strip()[:10])
    except ValueError:
        return None


def time_of(raw: Any) -> str | None:
    """«pre-market» · «time-after-hours» · «not_supplied» ⟸ اسمٌ واحد؛ وما لا يُعرف يبقى `None`."""
    text = str(raw or "").strip().lower().replace("_", "-")
    if text.startswith("time-"):
        text = text[len("time-"):]
    return TIME_OF.get(text)


def ny_today(now: float) -> date:
    """تاريخ نيويورك الآن — أيّام الإعلانات بتاريخ البورصة الأمريكيّة."""
    return quotes.utc_date(now + new_york_offset_h(now) * 3600)


def _mean_abs(values: list[float]) -> float | None:
    return round(sum(abs(v) for v in values) / len(values), PCT_DIGITS) if values else None


def read_earnings(path: str, tickers: list[str]) -> dict[str, Any]:
    """يُستدعى في `asyncio.to_thread`: الجدولان للشركات المطلوبة وحدها. كلّ غيابٍ أو تعذّرٍ سببٌ مسمًّى لا استثناء."""
    if not path or not os.path.isfile(path):
        return {"error": NO_FILE, "detail": path}
    wanted = {t.upper() for t in tickers}
    try:
        con = sqlite3.connect("file:%s?mode=ro" % Path(path).as_posix(), uri=True, timeout=BRIDGE_TIMEOUT_S)
        try:
            tables = {row[0] for row in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            calendar = con.execute(
                "SELECT ticker, report_date, report_time, is_estimated, eps_consensus, source_text, fetched_at_utc, "
                "source FROM %s" % CALENDAR_TABLE).fetchall() if CALENDAR_TABLE in tables else []
            history = con.execute(
                "SELECT ticker, date_reported, fiscal_qtr_end, eps, eps_consensus, surprise_pct, fetched_at_utc, "
                "source FROM %s ORDER BY ticker, date_reported DESC" % HISTORY_TABLE).fetchall() \
                if HISTORY_TABLE in tables else []
        finally:
            con.close()
    except sqlite3.Error as exc:
        return {"error": READ_FAILED, "detail": str(exc)[:DETAIL_CHARS]}
    missing = [name for name in (CALENDAR_TABLE, HISTORY_TABLE) if name not in tables]
    if len(missing) == len((CALENDAR_TABLE, HISTORY_TABLE)):
        return {"error": NO_TABLES, "detail": ", ".join(missing)}
    companies: dict[str, dict[str, Any]] = {}
    stamps: list[float] = []
    for ticker, day, when, estimated, eps, text, fetched, source in calendar:
        ticker = str(ticker or "").upper()
        if ticker in wanted:
            stamps.append(quotes.num(fetched) or 0.0)
            estimated = quotes.num(estimated)
            companies.setdefault(ticker, {})["calendar"] = {
                "report_date": parse_day(day).isoformat() if parse_day(day) else None,
                "report_time": time_of(when), "report_time_raw": None if when is None else str(when),
                "is_estimated": None if estimated is None else bool(estimated),
                "eps_consensus": quotes.num(eps), "source_text": str(text or "")[:TEXT_CHARS],
                "fetched_at_utc": quotes.num(fetched), "source": source}
    for ticker, day, quarter, eps, consensus, surprise, fetched, source in history:
        ticker = str(ticker or "").upper()
        rows = companies.setdefault(ticker, {}).setdefault("history", []) if ticker in wanted else None
        if rows is not None and len(rows) < HISTORY_ROWS and parse_day(day):
            stamps.append(quotes.num(fetched) or 0.0)
            rows.append({"date_reported": parse_day(day).isoformat(), "fiscal_qtr_end": quarter,
                         "eps": quotes.num(eps), "eps_consensus": quotes.num(consensus),
                         "surprise_pct": quotes.num(surprise), "fetched_at_utc": quotes.num(fetched),
                         "source": source})
    if not companies:
        return {"error": NO_ROWS, "detail": "%d+%d rows" % (len(calendar), len(history)), "missing_tables": missing}
    return {"error": None, "missing_tables": missing, "companies": companies,
            "fetched_at": max(stamps) if stamps else None,
            "rows_calendar": len(calendar), "rows_history": len(history)}


def record_times(observed: dict[str, dict[str, Any]], raw: dict[str, Any] | None, now: float) -> int:
    """وقت كلّ موعدٍ قادم رُئي في التقويم (قبل الافتتاح/بعد الإغلاق) يُحفظ ليُعرف به ردّ الفعل بعد مروره."""
    added = 0
    for ticker, company in ((raw or {}).get("companies") or {}).items():
        cal = company.get("calendar") or {}
        if cal.get("report_date") and cal.get("report_time") in (PRE_MARKET, AFTER_HOURS):
            key = "%s|%s" % (ticker, cal["report_date"])
            added += key not in observed
            observed[key] = {"time": cal["report_time"], "seen_at": now}
    for key in sorted(observed, key=lambda k: k.split("|")[-1])[:-OBSERVED_KEEP]:
        observed.pop(key, None)
    return added


def _latest_observed(observed: dict[str, dict[str, Any]], ticker: str) -> tuple[str, str] | None:
    seen = [(key.split("|")[-1], value["time"]) for key, value in observed.items()
            if key.split("|")[0] == ticker and isinstance(value, dict) and value.get("time")]
    return max(seen) if seen else None


def _next_trading(days: list[date], day: date) -> date | None:
    index = bisect.bisect_right(days, day)
    if index < len(days) and (days[index] - day).days <= MAX_GAP_DAYS:
        return days[index]
    return None


def reaction_history(companies: dict[str, dict[str, Any]], observed: dict[str, dict[str, Any]],
                     moves: dict[date, float], today: date) -> tuple[dict[str, Any], dict[str, Any]]:
    """لكلّ شركة: إعلاناتها الماضية ⟸ حركة الناسداك يوم الإعلان واليوم التالي، وجلسة ردّ الفعل بحسب الوقت.
    ومجمّعة: متوسّط |الحركة| في جلسات ردّ الفعل مقابل الأيّام العاديّة (لا إعلان فيها ولا ردّ فعل) — بـn."""
    days = sorted(moves)
    excluded: set[date] = set()
    on_day: list[float] = []
    next_day: list[float] = []
    reaction: list[float] = []
    basis_n = {BASIS_OBSERVED: 0, BASIS_ASSUMED: 0, BASIS_UNKNOWN: 0}
    first: date | None = None
    per: dict[str, Any] = {}
    for ticker in sorted(companies):
        latest = _latest_observed(observed, ticker)
        rows = []
        for item in companies[ticker].get("history") or []:
            day = parse_day(item.get("date_reported"))
            if day is None or day >= today:
                continue
            following = _next_trading(days, day)
            seen = observed.get("%s|%s" % (ticker, day.isoformat()))
            if seen:
                when, basis, assumed_from = seen.get("time"), BASIS_OBSERVED, None
            elif latest:
                when, basis, assumed_from = latest[1], BASIS_ASSUMED, latest[0]
            else:
                when, basis, assumed_from = None, BASIS_UNKNOWN, None
            m_day = moves.get(day)
            m_next = moves.get(following) if following else None
            r_day, r_move = ((day, m_day) if when == PRE_MARKET else
                             (following, m_next) if when == AFTER_HOURS else (None, None))
            excluded.update(d for d in (day, following) if d)
            first = day if first is None else min(first, day)
            basis_n[basis] += 1
            on_day += [m_day] if m_day is not None else []
            next_day += [m_next] if m_next is not None else []
            reaction += [r_move] if r_move is not None else []
            rows.append({"date": day.isoformat(), "time": when, "time_basis": basis, "time_assumed_from": assumed_from,
                         "nasdaq_move_report_day_pct": None if m_day is None else round(m_day, PCT_DIGITS),
                         "nasdaq_move_next_day_pct": None if m_next is None else round(m_next, PCT_DIGITS),
                         "reaction_day": r_day.isoformat() if r_day else None,
                         "nasdaq_reaction_move_pct": None if r_move is None else round(r_move, PCT_DIGITS)})
        moved = [r["nasdaq_reaction_move_pct"] for r in rows if r["nasdaq_reaction_move_pct"] is not None]
        per[ticker] = {"reports": rows, "mean_abs_reaction_pct": _mean_abs(moved), "n": len(moved)}
    normal = [moves[d] for d in days if first is not None and d >= first and d not in excluded]
    return per, {"reaction_abs_move_pct": _mean_abs(reaction), "reaction_n": len(reaction),
                 "report_day_abs_move_pct": _mean_abs(on_day), "report_day_n": len(on_day),
                 "next_day_abs_move_pct": _mean_abs(next_day), "next_day_n": len(next_day),
                 "normal_day_abs_move_pct": _mean_abs(normal), "normal_day_n": len(normal),
                 "time_observed_n": basis_n[BASIS_OBSERVED], "time_assumed_n": basis_n[BASIS_ASSUMED],
                 "time_unknown_n": basis_n[BASIS_UNKNOWN],
                 "from_date": first.isoformat() if first else None,
                 "through_date": days[-1].isoformat() if days else None}


def company_facts(company: dict[str, Any], history: dict[str, Any] | None, today: date,
                  now: float) -> dict[str, Any]:
    """حقائق شركةٍ واحدة: الموعد القادم · الأيّام الباقية · قبل/بعد · تقديريّ؟ · توقّع ربح السهم · آخر مفاجأة ٪ وتاريخها."""
    cal = company.get("calendar") or {}
    day = parse_day(cal.get("report_date"))
    rows = company.get("history") or []
    last = rows[0] if rows else {}
    fetched = cal.get("fetched_at_utc")
    return {"next_date": day.isoformat() if day else None, "days_to": (day - today).days if day else None,
            "time": cal.get("report_time"), "date_is_estimated": cal.get("is_estimated"),
            "eps_consensus": cal.get("eps_consensus"),
            "last_report_date": last.get("date_reported"), "last_surprise_pct": last.get("surprise_pct"),
            "last_eps": last.get("eps"), "last_eps_consensus": last.get("eps_consensus"),
            "surprises": [dict(row) for row in rows], "nasdaq_reaction": history,
            "calendar_fetched_age_h": None if fetched is None else round((now - fetched) / 3600.0, HOURS_DIGITS),
            "data_source": cal.get("source") or last.get("source"),
            "nasdaq_source_text": cal.get("source_text") or None}


def week_start(today: date) -> date:
    """اثنين أسبوع البورصة الجاري — والسبت والأحد يُقرآن الأسبوعَ القادم (لا إعلانات في العطلة)."""
    if today.weekday() >= quotes.WEEKEND_FROM:
        return today + timedelta(days=DAYS_IN_WEEK - today.weekday())
    return today - timedelta(days=today.weekday())


def upcoming_facts(companies: dict[str, dict[str, Any]], today: date) -> dict[str, Any]:
    """الشركة التالية وأيّامها · إعلانات هذا الأسبوع · إعلانات اليوم · وترتيب القادمة كلّها."""
    rows = sorted((f["days_to"], TIME_ORDER.get(f.get("time"), 1), ticker) for ticker, f in companies.items()
                  if f.get("days_to") is not None and f["days_to"] >= 0)
    monday = week_start(today)
    friday = monday + timedelta(days=WORK_DAYS_SPAN)

    def item(ticker: str) -> dict[str, Any]:
        f = companies[ticker]
        return {"ticker": ticker, "date": f["next_date"], "days_to": f["days_to"], "time": f.get("time"),
                "date_is_estimated": f.get("date_is_estimated")}

    week = sorted((item(t) for t, f in companies.items()
                   if parse_day(f.get("next_date")) and monday <= parse_day(f["next_date"]) <= friday),
                  key=lambda r: (r["date"], TIME_ORDER.get(r["time"], 1), r["ticker"]))
    head = companies[rows[0][2]] if rows else {}
    return {"next_earnings_ticker": rows[0][2] if rows else None,
            "days_to_next_earnings": rows[0][0] if rows else None,
            "next_earnings_date": head.get("next_date"), "next_earnings_time": head.get("time"),
            "next_earnings_date_is_estimated": head.get("date_is_estimated"),
            "earnings_today_count": sum(1 for row in rows if row[0] == 0),
            "earnings_this_week": week, "earnings_this_week_count": len(week),
            "earnings_upcoming": [item(row[2]) for row in rows]}
