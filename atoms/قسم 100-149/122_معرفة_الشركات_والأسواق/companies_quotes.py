"""أسعار الشركات من ميتاتريدر (122) — قراءةُ `nq_stocks.db` للقراءة فقط وفي خيطٍ جانبيّ، وحسابُها دوالّ صافية.

٢٠٢٦-١٠-٠٨ (ختم المالك «NQ» — المعرفة أوّلًا): «بس بميتاتريدر في كلّ الأسهم موجودة» · «في فيكس وفي دي إكس واي
كمان على ميتاتريدر». إكسبرت القراءة `mt5/NQ_StocksSync.mq5` (لا تداول) يكتب كلّ دقيقة صفًّا لكلّ رمز:
`broker_symbol` فارغ = غير موجود عند الوسيط (يُعلن)، والسعر الصفريّ يُكتب NULL، ووقت التِّكّة بغرينتش، وشمعة
اليوم `day_bar_server` بوقت الخادم (`stocks_meta.server_offset_s`)، و`prev_close` إغلاق شمعة اليوم السابقة عنده.
مقيس ١٠-٠٨ 14:25 غرينتش: 16 رمزًا من 17 عند الوسيط (GOOGL غائب)، والخوف `VIX_V6` والدولار `DXY_Z6`، والإزاحة 10800.
"""
from __future__ import annotations

import math
import os
import sqlite3
from datetime import date
from pathlib import Path
from typing import Any

from shared.owner_windows import new_york_offset_h

NO_FILE = "STOCKS_DB_MISSING"
READ_FAILED = "STOCKS_DB_READ_FAILED"
NO_ROWS = "STOCKS_DB_EMPTY"
NOT_AT_BROKER = "not_at_broker"
NO_ROW = "no_row_written"
NO_PRICE = "no_price"
DB_TIMEOUT_S = 2.0
DETAIL_CHARS = 160
PCT_DIGITS = 3
PRICE_DIGITS = 4
EPOCH_ORDINAL = date(1970, 1, 1).toordinal()
#: الجلسة الأمريكيّة النظاميّة بتوقيت نيويورك (09:30–16:00)، والسبت والأحد بلا جلسة.
SESSION_OPEN_MIN = 9 * 60 + 30
SESSION_CLOSE_MIN = 16 * 60
WEEKEND_FROM = 5
COLUMNS = ("ticker", "broker_symbol", "bid", "ask", "last", "tick_time_utc", "day_open", "day_high",
           "day_low", "prev_close", "day_bar_server", "written_at_utc")


def num(value: Any) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def utc_date(ts: float) -> date:
    return date.fromordinal(EPOCH_ORDINAL + int(ts // 86400))


def pct(price: float | None, base: float | None) -> float | None:
    """الحركة ٪ من مرجعٍ موجب — وبلا مرجعٍ لا رقم (لا صفرٌ يُقرأ «لم يتحرّك»)."""
    if price is None or base is None or base <= 0:
        return None
    return round((price / base - 1.0) * 100.0, PCT_DIGITS)


def us_session_open(now: float) -> bool:
    """الجلسة الأمريكيّة النظاميّة الآن؟ بالتوقيت الصيفيّ لنيويورك (`shared/owner_windows`). العطل الرسميّة لا تُعرف
    هنا — فعمر آخر تِكّة لكلّ رمز يُنشر معها."""
    local = now + new_york_offset_h(now) * 3600
    if utc_date(local).weekday() >= WEEKEND_FROM:
        return False
    minute = int(local % 86400) // 60
    return SESSION_OPEN_MIN <= minute < SESSION_CLOSE_MIN


def read_stocks(path: str) -> dict[str, Any]:
    """يُستدعى في `asyncio.to_thread`. غياب القاعدة أو تعذّرها أو فراغها ⟸ سببٌ مسمًّى لا استثناء."""
    if not path or not os.path.isfile(path):
        return {"error": NO_FILE, "detail": path}
    try:
        con = sqlite3.connect("file:%s?mode=ro" % Path(path).as_posix(), uri=True, timeout=DB_TIMEOUT_S)
        try:
            rows = con.execute("SELECT %s FROM stock_quotes" % ", ".join(COLUMNS)).fetchall()
            try:
                meta = {str(key): value for key, value in con.execute("SELECT key, value FROM stocks_meta")}
            except sqlite3.Error:
                meta = {}
        finally:
            con.close()
    except sqlite3.Error as exc:
        return {"error": READ_FAILED, "detail": str(exc)[:DETAIL_CHARS]}
    if not rows:
        return {"error": NO_ROWS, "detail": path, "meta": meta}
    return {"error": None, "rows": {str(row[0]).upper(): dict(zip(COLUMNS, row)) for row in rows}, "meta": meta}


def quote_facts(row: dict[str, Any] | None, now: float, server_offset_s: float) -> dict[str, Any]:
    """حقائق رمزٍ واحد: السعر (منتصف العرض والطلب، وإلّا آخر صفقة) · الحركة ٪ منذ إغلاق أمس ومنذ افتتاح اليوم ·
    عمر آخر تِكّة بالدقائق · تاريخ شمعة اليوم عند الخادم وهل هي شمعة اليوم (قبل الجلسة تكون شمعة أمس)."""
    if row is None:
        return {"available": False, "unavailable_reason": NO_ROW}
    symbol = str(row.get("broker_symbol") or "")
    if not symbol:
        return {"available": False, "unavailable_reason": NOT_AT_BROKER, "broker_symbol": None}
    bid, ask, last = num(row.get("bid")), num(row.get("ask")), num(row.get("last"))
    price = (bid + ask) / 2.0 if bid and ask else (last or bid or ask)
    if not price:
        return {"available": False, "unavailable_reason": NO_PRICE, "broker_symbol": symbol}
    prev, opened = num(row.get("prev_close")), num(row.get("day_open"))
    tick, bar = num(row.get("tick_time_utc")), num(row.get("day_bar_server"))
    bar_day = utc_date(bar) if bar else None
    return {"available": True, "broker_symbol": symbol, "price": round(price, PRICE_DIGITS),
            "change_pct": pct(price, prev), "from_open_pct": pct(price, opened),
            "prev_close": prev, "day_open": opened, "day_high": num(row.get("day_high")),
            "day_low": num(row.get("day_low")),
            "tick_age_min": None if tick is None else round((now - tick) / 60.0, 1),
            "day_bar_date": bar_day.isoformat() if bar_day else None,
            "day_bar_is_today": None if bar_day is None else bar_day == utc_date(now + server_offset_s)}


def breadth(quotes: dict[str, dict[str, Any]], tickers: list[str]) -> dict[str, Any]:
    """كم شركة صاعدة/هابطة منذ إغلاق أمس · أكبر صاعد وأكبر هابط · متوسّط حركتها — وعدد العيّنة `change_n`."""
    moves = {t: quotes[t]["change_pct"] for t in tickers if (quotes.get(t) or {}).get("change_pct") is not None}
    out: dict[str, Any] = {"rising_count": None, "falling_count": None, "unchanged_count": None,
                           "change_n": len(moves), "companies_avg_change_pct": None,
                           "max_change_ticker": None, "max_change_pct": None,
                           "min_change_ticker": None, "min_change_pct": None}
    if not moves:
        return out
    top, low = max(moves, key=moves.get), min(moves, key=moves.get)
    out.update({"rising_count": sum(1 for v in moves.values() if v > 0),
                "falling_count": sum(1 for v in moves.values() if v < 0),
                "unchanged_count": sum(1 for v in moves.values() if v == 0),
                "companies_avg_change_pct": round(sum(moves.values()) / len(moves), PCT_DIGITS),
                "max_change_ticker": top, "max_change_pct": moves[top],
                "min_change_ticker": low, "min_change_pct": moves[low]})
    return out


def stocks_status(raw: dict[str, Any] | None, now: float) -> dict[str, Any]:
    """حال المصدر نفسه: هل يُقرأ · متى كتب الإكسبرت آخر مرّة · كم رمزًا وجد وكم كتب · خادمه."""
    if raw is None:
        return {"stocks_available": False, "stocks_unavailable_reason": "NOT_READ_YET"}
    meta = raw.get("meta") or {}
    written = num(meta.get("written_at_utc"))
    found, wrote = num(meta.get("tickers_found")), num(meta.get("tickers_written"))
    return {"stocks_available": not raw.get("error"), "stocks_unavailable_reason": raw.get("error"),
            "stocks_written_age_min": None if written is None else round((now - written) / 60.0, 1),
            "stocks_tickers_found": None if found is None else int(found),
            "stocks_tickers_written": None if wrote is None else int(wrote),
            "stocks_server": meta.get("server")}
