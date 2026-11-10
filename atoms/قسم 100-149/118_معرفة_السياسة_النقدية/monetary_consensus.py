"""الفعليّ والإجماع من تقويم بورصة ناسداك الاقتصاديّ (118) — للقراءة فقط، في الخيط الجانبيّ نفسه.

٢٠٢٦-١٠-٠٨ (ختم المالك «NQ» — «الأخبار من مكانٍ واحد — عدّة مصادر تحت سقفٍ واحد»):
مقيس اليوم: تقويم ميتاتريدر لا يستقبل القيم الفعليّة منذ 2026-10-02 19:30 (ولا الجسر)، وجدول ForexFactory بلا
فعليّ أصلًا. فالمصدر الأوّل للفعليّ و**الإجماع الحقيقيّ** (`consensus`): جدول `econ_calendar` في قاعدة الجسر،
يكتبه بوت الأخبار من تقويم ناسداك (عقد: id · event_date · time_et · scheduled_at بغرينتش · country · event_name
إنكليزيّ · actual/consensus/previous نصوصٌ مثل '206K' و'0.2%' و'-3.186M' · fetched_at · source).
المطابقة بأحداث ميتاتريدر **بالوقت (±2 دقيقة) وبجدول تسمياتٍ صغير** للأبواب، والمبهم («Core CPI» بلا شهريّ/سنويّ
وحدثان في اللحظة نفسها) يُحسم بتساوي «السابق» — وإلّا لا يُطابق ويبقى كلٌّ بمصدره. والقيم تُحوَّل إلى وحدة ميتاتريدر
(آلاف/ملايين/نسبة). وإن اختلف الفعليّ بين مصدرين أُعلن (`sources_disagree`) والأوّل ناسداك.
قرار الفائدة وحده يُشترط فيه تساوي «السابق» قبل أخذ فعليّه: ميتاتريدر يكتب الحدّ الأعلى للنطاق، وصيغةٌ أخرى
(الحدّ الأدنى أو المدى) تصنع تغييرًا زائفًا.
"""
from __future__ import annotations

import math
import os
import re
import sqlite3
from pathlib import Path
from typing import Any

TABLE = "econ_calendar"
ECON_TIMEOUT_S = 1.0                              # الجسر يكتبه غيرنا: مهلة قفلٍ قصيرة ثمّ «غير متاح»
MATCH_TOL_S = 120.0
PAST_DAYS = 40                                    # آخر إصدار شهريّ قد يسبق بأكثر من 30 يومًا
PAST_S = PAST_DAYS * 86400
AHEAD_DAYS = 31
AHEAD_S = AHEAD_DAYS * 86400
HALF_DIGIT = 0.5
EPSILON = 1e-9
MAX_SAMPLE = 10
DETAIL_CHARS = 160
SOURCE_NASDAQ = "nasdaq"
NO_FILE = "BRIDGE_FILE_MISSING"
NO_TABLE = "ECON_TABLE_MISSING"
READ_FAILED = "ECON_READ_FAILED"
US_NAMES = {"united states", "us", "usa", "u s", "u s a"}
SCALE = {"": 1.0, "%": 1.0, "K": 1e3, "M": 1e6, "B": 1e9, "T": 1e12}
MT5_SCALE = {0: 1.0, 1: 1e3, 2: 1e6, 3: 1e9, 4: 1e12}
VALUE_RE = re.compile(r"^([-+]?\d+(?:\.\d+)?)([KMBT%]?)$", re.IGNORECASE)
PERIOD_RE = re.compile(r"\((mom|yoy|qoq|m/m|y/y|q/q)\)")
PERIODS = {"mom": "mm", "mm": "mm", "yoy": "yy", "yy": "yy", "qoq": "qq", "qq": "qq"}
# جدول التسميات: الاسم بلا أقواس ولا رموز ⟵ الباب؛ والباب ⟵ رموز ميتاتريدر بفترتها (None = حدثٌ واحد).
NAME_FAMILIES = {
    "cpi": "cpi", "consumer price index": "cpi", "core cpi": "core_cpi", "cpi ex food energy": "core_cpi",
    "ppi": "ppi", "producer price index": "ppi", "core ppi": "core_ppi", "ppi ex food energy": "core_ppi",
    "nonfarm payrolls": "nfp", "non farm payrolls": "nfp", "unemployment rate": "unemployment",
    "initial jobless claims": "claims", "core pce price index": "core_pce", "core pce prices": "core_pce",
    "gdp": "gdp", "gdp annualized": "gdp", "gross domestic product": "gdp",
    "fed interest rate decision": "fed_rate", "interest rate decision": "fed_rate", "fed funds rate": "fed_rate",
    "federal funds rate": "fed_rate", "crude oil inventories": "crude",
}
FAMILIES = {
    "cpi": {"mm": "consumer-price-index-mm", "yy": "consumer-price-index-yy"},
    "core_cpi": {"mm": "consumer-price-index-ex-food-energy-mm", "yy": "consumer-price-index-ex-food-energy-yy"},
    "ppi": {"mm": "producer-price-index-mm", "yy": "producer-price-index-yy"},
    "core_ppi": {"mm": "producer-price-index-ex-food-energy-mm", "yy": "producer-price-index-ex-food-energy-yy"},
    "nfp": {None: "nonfarm-payrolls"}, "unemployment": {None: "unemployment-rate"},
    "claims": {None: "initial-jobless-claims"},
    "core_pce": {"mm": "core-pce-price-index-mm", "yy": "core-pce-price-index-yy"},
    "gdp": {"qq": "gross-domestic-product-qq"}, "fed_rate": {None: "fed-interest-rate-decision"},
    "crude": {None: "eia-crude-oil-stocks-change"},
}
TRACKED_CODES = {code for periods in FAMILIES.values() for code in periods.values()}
CONVENTION_CHECK = {"fed-interest-rate-decision"}


def num(value: Any) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def parse_value(text: Any) -> tuple[float, str] | None:
    """'206K' ⟵ (206, 'K') · '0.2%' ⟵ (0.2, '%') · '-3.186M' ⟵ (-3.186, 'M'). وما سواها (مدى، فراغ) ⟵ لا شيء."""
    match = VALUE_RE.match(str(text or "").replace(",", "").replace(" ", ""))
    return None if not match else (float(match.group(1)), match.group(2).upper())


def to_mt5(parsed: tuple[float, str] | None, row: dict[str, Any]) -> float | None:
    """بوحدة صفّ ميتاتريدر: النسبة كما هي، والآلاف/الملايين بمضاعفه (المطالبات والوظائف آلاف، النفط ملايين)."""
    if parsed is None:
        return None
    value, suffix = parsed
    if suffix == "%":
        return value
    return round(value * SCALE[suffix] / MT5_SCALE.get(int(row.get("multiplier") or 0), 1.0), 6)


def parse_name(name: Any) -> tuple[str | None, str | None]:
    """الباب والفترة من الاسم. تُنزع أقواس الفترة وحدها — فـ«(4-Week Avg)» يبقى في الاسم فلا يُطابق المطالبات."""
    text = str(name or "").lower()
    found = PERIOD_RE.search(text)
    period = None if not found else PERIODS[found.group(1).replace("/", "")]
    base = " ".join(re.sub(r"[^a-z ]+", " ", PERIOD_RE.sub(" ", text)).split())
    return NAME_FAMILIES.get(base), period


def candidate_codes(family: str | None, period: str | None) -> set[str]:
    periods = FAMILIES.get(family or "") or {}
    if period in periods:
        return {periods[period]}
    if period is not None and None not in periods:
        return set()
    return set(periods.values())


def read_econ(path: str, now: float) -> dict[str, Any]:
    if not path or not os.path.isfile(path):
        return {"available": False, "reason": NO_FILE}
    try:
        con = sqlite3.connect("file:%s?mode=ro" % Path(path).as_posix(), uri=True, timeout=ECON_TIMEOUT_S)
        try:
            if con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (TABLE,)).fetchone() is None:
                return {"available": False, "reason": NO_TABLE}
            rows = con.execute("SELECT id, event_name, country, scheduled_at, actual, consensus, previous FROM %s "
                               "WHERE scheduled_at>=? AND scheduled_at<=?" % TABLE, (now - PAST_S, now + AHEAD_S)).fetchall()
            fetched = con.execute("SELECT MAX(fetched_at) FROM %s" % TABLE).fetchone()[0]
        finally:
            con.close()
    except sqlite3.Error as exc:
        return {"available": False, "reason": READ_FAILED, "detail": str(exc)[:DETAIL_CHARS]}
    us = []
    for rid, name, country, at, actual, consensus, previous in rows:
        when = num(at)
        if when is not None and " ".join(re.sub(r"[^a-z ]+", " ", str(country or "").lower()).split()) in US_NAMES:
            us.append({"id": str(rid), "name": str(name or "").strip(), "at": when, "actual": parse_value(actual),
                       "consensus": parse_value(consensus), "previous": parse_value(previous), "raw_actual": actual})
    return {"available": True, "reason": None, "rows": us, "fetched_at": num(fetched)}


def _tol(row: dict[str, Any]) -> float:
    return HALF_DIGIT * 10 ** -int(row.get("digits") or 0) + EPSILON


def same_previous(econ: dict[str, Any], row: dict[str, Any]) -> bool:
    previous = to_mt5(econ["previous"], row)
    known = [x for x in (num(row.get("prev")), num(row.get("revised_prev"))) if x is not None]
    return previous is not None and any(abs(previous - x) <= _tol(row) for x in known)


def _key(row: dict[str, Any]) -> tuple[str, int]:
    return row["event_code"], int(round(row["time_utc"]))


def _apply(row: dict[str, Any], econ: dict[str, Any]) -> dict[str, Any] | None:
    """يُلحق الإجماع، ويجعل فعليّ ناسداك الأوّل ويعلن الخلاف. يعيد سطر الخلاف إن وُجد."""
    row["consensus"] = to_mt5(econ["consensus"], row)
    row["econ_id"] = econ["id"]
    actual = to_mt5(econ["actual"], row)
    if actual is None:
        return None
    existing, source = row.get("actual"), row.get("actual_source")
    if row["event_code"] in CONVENTION_CHECK and not same_previous(econ, row):
        row["other_actuals"] = {SOURCE_NASDAQ: actual}
        row["sources_disagree"] = existing is None or abs(actual - existing) > _tol(row)
        return {"code": row["event_code"], "time_utc": row["time_utc"], "used": existing, "used_source": source,
                "other": {SOURCE_NASDAQ: actual}, "why": "previous_convention_differs"}
    disagree = None
    if existing is not None:
        row["other_actuals"] = {source: existing}
        row["sources_disagree"] = abs(actual - existing) > _tol(row)
        if row["sources_disagree"]:
            disagree = {"code": row["event_code"], "time_utc": row["time_utc"], "used": actual,
                        "used_source": SOURCE_NASDAQ, "other": {source: existing}, "why": "actual_differs"}
    row.update({"actual": actual, "actual_source": SOURCE_NASDAQ})
    return disagree


def merge(groups: list[list[dict[str, Any]]], econ: dict[str, Any]) -> dict[str, Any]:
    """يطابق صفوف ناسداك الأمريكيّة بأحداث ميتاتريدر ويُلحقها بكلّ نسخةٍ من الحدث في كلّ قائمة."""
    for rows in groups:
        for row in rows:
            row.setdefault("consensus", None)
            row["broker_forecast"] = num(row.get("forecast"))
    out = {"available": econ.get("available", False), "reason": econ.get("reason"), "detail": econ.get("detail"),
           "fetched_at": econ.get("fetched_at"), "rows": None, "matched": None, "unmatched": None,
           "unmatched_sample": [], "disagree": []}
    if not econ.get("available"):
        return out
    events: dict[tuple[str, int], dict[str, Any]] = {}
    for rows in groups:
        for row in rows:
            if row["event_code"] in TRACKED_CODES:
                events.setdefault(_key(row), row)
    matches: dict[tuple[str, int], dict[str, Any]] = {}
    unmatched = []
    for item in econ["rows"]:
        codes = candidate_codes(*parse_name(item["name"]))
        near = [k for k in events if k[0] in codes and abs(k[1] - item["at"]) <= MATCH_TOL_S]
        if len(near) > 1:
            near = [k for k in near if same_previous(item, events[k])]
        if len(near) != 1 or near[0] in matches:
            unmatched.append(item)
            continue
        matches[near[0]] = item
    disagree: dict[tuple[str, int], dict[str, Any]] = {}
    for rows in groups:
        for row in rows:
            item = matches.get(_key(row)) if row["event_code"] in TRACKED_CODES else None
            line = _apply(row, item) if item is not None else None
            if line is not None:
                disagree[_key(row)] = line
    out.update({"rows": len(econ["rows"]), "matched": len(matches), "unmatched": len(unmatched),
                "unmatched_sample": [{"name": u["name"], "at": u["at"]} for u in unmatched[:MAX_SAMPLE]],
                "disagree": list(disagree.values())})
    return out
