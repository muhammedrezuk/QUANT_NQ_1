"""قراءة مصدرَي معرفة السياسة النقديّة (118) — للقراءة فقط (`mode=ro`) وفي خيطٍ جانبيّ (`asyncio.to_thread`).

٢٠٢٦-١٠-٠٨ (ختم المالك «NQ» — «لازم يعرف شو صار بالماضي، وإيمتى مواعيد المستقبل، شو جاي»):
  ١) قاعدة التاريخ `nq_calendar_history.db` — يكتبها الإكسبرت `mt5/NQ_CalendarSync.mq5` كلّ ساعة (30 يومًا ماضية
     و180 قادمة)، وقبله السكربت مرّةً. الوقت: `time_server − 3 ساعات = غرينتش` ثابتة (مقيس).
  ٢) قاعدة الجسر `nq_brain.db` جدول `calendar` — يكتبه الإكسبرت الحيّ ليومٍ قبل ويومين بعد. منه **القيمة الفعليّة
     لحظة صدورها** لما صدر في الأيّام الثلاثة الأخيرة وليست له قيمة في التاريخ بعد (`actual_source: "bridge"`).
     مقيس ١٠-٠٨ على القاعدتين الحيّتين: معرّف الجسر `id` = `value_id` في التاريخ لـ402 من 402 صفًّا أمريكيًّا،
     والأسماء متطابقة حرفيًّا، ووقت الجسر يسبق التاريخ بثانية في 257 صفًّا (12:29:59) — فالمطابقة بالمعرّف أوّلًا
     مع سماحٍ زمنيّ، ثمّ بالاسم والوقت إن انفرد صفٌّ واحد. الجسر مقفلٌ أو غائب ⟸ يُعلن سببه، ولا ينكسر شيء.
"""
from __future__ import annotations

import math
import os
import sqlite3
from pathlib import Path
from typing import Any

# ٢٠٢٦-١٠-١٧ (ختم المالك «NQ»، المرحلة 1 الخطوة 4): كان «time_server − 3 ساعات = غرينتش (ثابت مقيس)» — ثابتٌ ينكسر شتاءً
# (الوسيط = نيويورك + 7 ⟸ ساعتان من 1/11). الآن فرق الوسيط لكلّ لحظةٍ بقاعدته (`broker_day_offset_s`).
from shared.owner_windows import broker_day_offset_s


def server_to_utc(server_ts: float) -> float:
    return float(server_ts) - broker_day_offset_s(float(server_ts))


def utc_to_server(utc_ts: float) -> float:
    return float(utc_ts) + broker_day_offset_s(float(utc_ts))
COUNTRY = "US"
BRIDGE_CURRENCY = "USD"                           # بلد الجسر بالعربيّة؛ عملته USD وحدها للولايات المتحدة (مقيس 402)
HIGH_IMPORTANCE = 3
HISTORY_TIMEOUT_S = 5.0
BRIDGE_TIMEOUT_S = 1.0                            # الإكسبرت الحيّ يكتب في الجسر: مهلة قفلٍ قصيرة ثمّ «غير متاح»
FILL_DAYS = 3
FILL_S = FILL_DAYS * 86400
BRIDGE_TIME_TOL_S = 120.0
PAST_DAYS = 30
PAST_S = PAST_DAYS * 86400
AHEAD_DAYS = 30
AHEAD_S = AHEAD_DAYS * 86400
RELEASE_LOOKBACK = 6                              # آخر ستّة صفوف للمؤشّر حتّى الآن تكفي لإيجاد آخر قيمة فعليّة
DETAIL_CHARS = 160
FED_DECISION_CODE = "fed-interest-rate-decision"

NO_FILE = "SOURCE_FILE_MISSING"
READ_FAILED = "SOURCE_READ_FAILED"
BRIDGE_NO_FILE = "BRIDGE_FILE_MISSING"
BRIDGE_READ_FAILED = "BRIDGE_READ_FAILED"
SOURCE_HISTORY = "history"
SOURCE_BRIDGE = "bridge"

COLUMNS = ("value_id", "event_code", "event_name", "importance", "time_server", "actual", "forecast",
           "prev", "revised_prev", "digits", "unit", "multiplier")
SELECT = "SELECT %s FROM calendar_history" % ", ".join(COLUMNS)


def num(value: Any) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def _norm(text: Any) -> str:
    return " ".join(str(text or "").split())


def _row(values: tuple) -> dict[str, Any]:
    row = dict(zip(COLUMNS, values))
    row["time_utc"] = server_to_utc(row["time_server"])
    row["event_name"] = _norm(row.get("event_name"))
    row["actual"] = num(row.get("actual"))
    row["actual_source"] = SOURCE_HISTORY if row["actual"] is not None else None
    return row


def _connect(path: str, timeout: float) -> sqlite3.Connection:
    return sqlite3.connect("file:%s?mode=ro" % Path(path).as_posix(), uri=True, timeout=timeout)


def _read_history(con: sqlite3.Connection, now: float, release_codes: tuple[str, ...]) -> dict[str, Any]:
    try:
        meta = {str(k): v for k, v in con.execute("SELECT key, value FROM export_meta")}
    except sqlite3.Error:
        meta = {}
    count, last = con.execute("SELECT COUNT(*), MAX(time_server) FROM calendar_history").fetchone()
    fed = [_row(r) for r in con.execute(SELECT + " WHERE country_code=? AND event_code=? ORDER BY time_server",
                                        (COUNTRY, FED_DECISION_CODE))]
    window = [_row(r) for r in con.execute(
        SELECT + " WHERE country_code=? AND time_server>? AND time_server<=? ORDER BY time_server",
        (COUNTRY, utc_to_server(now - PAST_S), utc_to_server(now + AHEAD_S)))]
    releases: dict[str, list[dict[str, Any]]] = {code: [] for code in release_codes}
    marks = ",".join("?" * len(release_codes))
    for values in con.execute(SELECT + " WHERE country_code=? AND event_code IN (%s) AND time_server<=? "
                              "ORDER BY time_server DESC" % marks,
                              (COUNTRY, *release_codes, utc_to_server(now))):
        rows = releases[values[1]]
        if len(rows) < RELEASE_LOOKBACK:
            rows.append(_row(values))
    # الحجم المعتاد لفرق الفعليّ عن المتوقَّع لكلّ حدثٍ عالٍ منذ أوّل التاريخ — لمقارنة فروقٍ بوحداتٍ مختلفة.
    typical = {code: {"n": int(n), "rms": math.sqrt(mean_sq) if mean_sq else None} for code, n, mean_sq in con.execute(
        "SELECT event_code, COUNT(*), AVG((actual - forecast) * (actual - forecast)) FROM calendar_history "
        "WHERE country_code=? AND importance=? AND actual IS NOT NULL AND forecast IS NOT NULL GROUP BY event_code",
        (COUNTRY, HIGH_IMPORTANCE))}
    return {"meta": meta, "rows": int(count or 0),
            "horizon": None if last is None else server_to_utc(last), "fed": fed,
            "past": [r for r in window if r["time_utc"] <= now],
            "ahead": [r for r in window if r["time_utc"] > now], "releases": releases, "typical": typical}


def read_bridge(path: str, now: float) -> dict[str, Any]:
    """صفوف الجسر الأمريكيّة في الأيّام الثلاثة الأخيرة. غيابه أو قفله ⟸ `available: false` بسببه."""
    if not path or not os.path.isfile(path):
        return {"available": False, "reason": BRIDGE_NO_FILE}
    try:
        con = _connect(path, BRIDGE_TIMEOUT_S)
        try:
            rows = con.execute("SELECT id, title, scheduled_at, actual FROM calendar WHERE currency=? "
                               "AND scheduled_at>=? AND scheduled_at<=?",
                               (BRIDGE_CURRENCY, now - FILL_S - BRIDGE_TIME_TOL_S, now + BRIDGE_TIME_TOL_S)).fetchall()
        finally:
            con.close()
    except sqlite3.Error as exc:
        return {"available": False, "reason": BRIDGE_READ_FAILED, "detail": str(exc)[:DETAIL_CHARS]}
    by_id: dict[str, dict[str, Any]] = {}
    by_title: dict[str, list[dict[str, Any]]] = {}
    for bid, title, scheduled, actual in rows:
        at = num(scheduled)
        if at is None:
            continue
        item = {"id": str(bid), "title": _norm(title), "at": at, "actual": num(actual)}
        by_id[item["id"]] = item
        by_title.setdefault(item["title"], []).append(item)
    return {"available": True, "reason": None, "rows": len(rows), "by_id": by_id, "by_title": by_title,
            "with_actual": sum(1 for item in by_id.values() if item["actual"] is not None)}


def match_bridge(row: dict[str, Any], bridge: dict[str, Any]) -> dict[str, Any] | None:
    """بالمعرّف أوّلًا (مع سماحٍ زمنيّ)، ثمّ بالاسم والوقت إن انفرد صفٌّ واحد — لا تخمين عند الالتباس."""
    hit = bridge["by_id"].get(str(row.get("value_id")))
    if hit is not None and abs(hit["at"] - row["time_utc"]) <= BRIDGE_TIME_TOL_S:
        return hit
    near = [item for item in bridge["by_title"].get(row["event_name"], [])
            if abs(item["at"] - row["time_utc"]) <= BRIDGE_TIME_TOL_S]
    return near[0] if len(near) == 1 else None


def apply_bridge(groups: list[list[dict[str, Any]]], bridge: dict[str, Any], now: float) -> set[str]:
    """يملأ القيمة الفعليّة الغائبة من الجسر لما صدر في الأيّام الثلاثة الأخيرة. يعيد معرّفات ما مُلئ."""
    filled: set[str] = set()
    for rows in groups:
        for row in rows:
            if row["actual"] is not None or not now - FILL_S <= row["time_utc"] <= now:
                continue
            hit = match_bridge(row, bridge)
            if hit is not None and hit["actual"] is not None:
                row.update({"actual": hit["actual"], "actual_source": SOURCE_BRIDGE, "bridge_id": hit["id"]})
                filled.add(str(row.get("value_id")))
    return filled


def read_sources(history_path: str, bridge_path: str, now: float, release_codes: tuple[str, ...]) -> dict[str, Any]:
    """يُستدعى في `asyncio.to_thread`. غياب التاريخ أو تعذّره ⟸ سببٌ مسمًّى لا استثناء؛ والجسر إضافةٌ لا شرط."""
    if not os.path.isfile(history_path):
        return {"error": NO_FILE, "detail": history_path}
    try:
        con = _connect(history_path, HISTORY_TIMEOUT_S)
        try:
            raw = _read_history(con, now, release_codes)
        finally:
            con.close()
    except sqlite3.Error as exc:
        return {"error": READ_FAILED, "detail": str(exc)[:DETAIL_CHARS]}
    bridge = read_bridge(bridge_path, now)
    filled: set[str] = set()
    if bridge["available"]:
        filled = apply_bridge([raw["fed"], raw["past"], *raw["releases"].values()], bridge, now)
    raw["bridge"] = {"available": bridge["available"], "reason": bridge["reason"],
                     "detail": bridge.get("detail"), "rows_3d": bridge.get("rows"),
                     "rows_3d_with_actual": bridge.get("with_actual"),
                     "actuals_filled": len(filled) if bridge["available"] else None}
    return raw
