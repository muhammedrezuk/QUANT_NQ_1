"""حركة الناسداك نفسه (122) — من شموع 103 الحيّة ومن قاعدة تاريخ سي‑تريدر قراءةً فقط.

٢٠٢٦-١٠-٠٨ (ختم المالك «NQ» — المعرفة أوّلًا): «متوسّط حركة الشركات مقابل حركة الناسداك» يحتاج حركة الناسداك منذ
إغلاق أمس على **يوم الوسيط** (يُغلق مع إغلاق نيويورك 17:00 — `shared/owner_windows.broker_day_offset_s`)، وعليه
باني الشموع 103 وقاعدة التاريخ والبطاقة 414.
  · إغلاق كلّ يوم: شمعة 1d من 103 أوّلًا، ثمّ شمعة D1 من قاعدة التاريخ، ثمّ آخر شمعة دقيقة رآها الحيّ في ذلك اليوم.
  · افتتاح اليوم: أوّل شمعة دقيقة بعد بداية يوم الوسيط — من الحيّ إن رأى الانتقال بين اليومين، وإلّا أوّل M1 في التاريخ.
  · آخر سعر: آخر شمعة دقيقة أُغلقت (الحيّ، وإلّا آخر M1 في التاريخ). والمرجع يومُ آخر سعر: يوم السبت يُقرأ يوم الجمعة.
وشموع D1 لأربعة عشر شهرًا ⟸ حركة كلّ يوم تداول (إغلاقه ÷ إغلاق الذي قبله) — لحركة أيّام إعلانات الأرباح.
"""
from __future__ import annotations

import os
import sqlite3
from datetime import date
from pathlib import Path
from typing import Any

import companies_quotes as quotes
from shared.owner_windows import broker_day_offset_s

HISTORY_NO_FILE = "HISTORY_DB_MISSING"
HISTORY_READ_FAILED = "HISTORY_DB_READ_FAILED"
NO_CANDLES = "NO_CANDLES_YET"
#: ~14 شهرًا: أربعة إعلاناتٍ للخلف لكلّ شركة وما بينها من أيّامٍ عاديّة.
HISTORY_DAYS = 430
DB_TIMEOUT_S = 5.0
DETAIL_CHARS = 160
KEEP_DAYS = 10
CANDLE_1M = "candle_1m"
CANDLE_1D = "candle_1d"
HISTORY_D1 = "history_d1"
HISTORY_M1 = "history_m1"
FIRST_1M = "candle_1m_first"
FIRST_M1 = "history_m1_first"
#: أيّ إغلاقٍ ليومٍ يسبق: شمعة اليوم الحيّة، ثمّ شمعة التاريخ، ثمّ آخر دقيقة.
CLOSE_RANK = {CANDLE_1M: 1, HISTORY_M1: 1, HISTORY_D1: 2, CANDLE_1D: 3}


def broker_day_start(ts: float) -> float:
    return ts - ((ts + broker_day_offset_s(ts)) % 86400)


def broker_date(ts: float) -> date:
    return quotes.utc_date(ts + broker_day_offset_s(ts))


def read_history(path: str, symbol: str, now: float) -> dict[str, Any]:
    """يُستدعى في `asyncio.to_thread`: شموع D1 المكتملة لأربعة عشر شهرًا، وأوّل M1 في يوم الوسيط الجاري وآخر M1
    مغلقة. الغياب أو التعذّر ⟸ سببٌ مسمًّى لا استثناء."""
    if not path or not os.path.isfile(path):
        return {"error": HISTORY_NO_FILE, "detail": path}
    day = broker_day_start(now)
    try:
        con = sqlite3.connect("file:%s?mode=ro" % Path(path).as_posix(), uri=True, timeout=DB_TIMEOUT_S)
        try:
            d1 = con.execute(
                "SELECT period_start, close FROM candles_history WHERE symbol=? AND period='D1' "
                "AND period_start>=? AND period_start<=? ORDER BY period_start",
                (symbol, now - HISTORY_DAYS * 86400, now - 86400)).fetchall()
            first = con.execute(
                "SELECT period_start, open FROM candles_history WHERE symbol=? AND period='M1' "
                "AND period_start>=? AND period_start<? ORDER BY period_start LIMIT 1",
                (symbol, day, day + 86400)).fetchone()
            last = con.execute(
                "SELECT period_start, close FROM candles_history WHERE symbol=? AND period='M1' "
                "AND period_start<=? ORDER BY period_start DESC LIMIT 1", (symbol, now - 60)).fetchone()
        finally:
            con.close()
    except sqlite3.Error as exc:
        return {"error": HISTORY_READ_FAILED, "detail": str(exc)[:DETAIL_CHARS]}
    return {"error": None, "d1": [(float(start), float(close)) for start, close in d1],
            "first_m1": first, "last_m1": last}


def daily_moves(rows: list[tuple[float, float]]) -> dict[date, float]:
    """حركة كلّ يوم تداول ٪ (إغلاقه ÷ إغلاق يوم التداول قبله) بتاريخ يوم الوسيط — والسبت والأحد يُسقطان."""
    moves: dict[date, float] = {}
    prev = None
    for start, close in rows:
        day = broker_date(start)
        if day.weekday() >= quotes.WEEKEND_FROM or close <= 0:
            continue
        if prev is not None:
            moves[day] = (close / prev - 1.0) * 100.0
        prev = close
    return moves


class NasdaqTape:
    """إغلاق كلّ يوم وسيطٍ وافتتاحه وآخر سعر — الحيّ أوّلًا، والتاريخ عند الإقلاع وكلّ يوم."""

    def __init__(self) -> None:
        self.closes: dict[float, dict[str, Any]] = {}
        self.opens: dict[float, dict[str, Any]] = {}
        self.last: dict[str, Any] | None = None
        self.minute_day: float | None = None

    def _close(self, day: float, close: float, source: str, at: float) -> None:
        old = self.closes.get(day)
        if old is None or (CLOSE_RANK[source], at) >= (CLOSE_RANK.get(old.get("source"), 0), old.get("at") or 0.0):
            self.closes[day] = {"close": close, "source": source, "at": at}

    def _trim(self) -> None:
        for store in (self.closes, self.opens):
            for day in sorted(store)[:-KEEP_DAYS]:
                store.pop(day, None)

    def on_minute(self, start: float, opened: float, close: float) -> None:
        day = broker_day_start(start)
        # الافتتاح من الحيّ لا يُعرف إلّا إن رأى الحيّ دقيقةً من يومٍ سابق قبله (لا أوّل ما رآه بعد إقلاعٍ وسط اليوم).
        if self.minute_day is not None and day > self.minute_day and day not in self.opens:
            self.opens[day] = {"open": opened, "source": FIRST_1M}
        self.minute_day = day if self.minute_day is None else max(self.minute_day, day)
        self._close(day, close, CANDLE_1M, start + 60)
        if self.last is None or start + 60 >= self.last["at"]:
            self.last = {"price": close, "at": start + 60, "source": CANDLE_1M}
        self._trim()

    def on_day(self, start: float, close: float) -> None:
        self._close(broker_day_start(start), close, CANDLE_1D, start + 86400)
        self._trim()

    def apply_history(self, ref: dict[str, Any]) -> None:
        for start, close in ref.get("d1") or []:
            self._close(broker_day_start(start), close, HISTORY_D1, start + 86400)
        first = ref.get("first_m1")
        if first:
            self.opens.setdefault(broker_day_start(float(first[0])), {"open": float(first[1]), "source": FIRST_M1})
        last = ref.get("last_m1")
        if last:
            at = float(last[0]) + 60
            self._close(broker_day_start(float(last[0])), float(last[1]), HISTORY_M1, at)
            if self.last is None or at > self.last["at"]:
                self.last = {"price": float(last[1]), "at": at, "source": HISTORY_M1}
        self._trim()

    def facts(self, now: float) -> dict[str, Any]:
        out: dict[str, Any] = {"nasdaq_change_pct": None, "nasdaq_from_open_pct": None, "nasdaq_last": None,
                               "nasdaq_last_source": None, "nasdaq_last_age_min": None, "nasdaq_day": None,
                               "nasdaq_prev_close": None, "nasdaq_prev_close_source": None,
                               "nasdaq_prev_close_day": None, "nasdaq_day_open": None,
                               "nasdaq_day_open_source": None, "nasdaq_unavailable_reason": None}
        last = self.last
        # المرجع يومُ آخر سعر؛ وبلا سعرٍ بعدُ يومُ اللحظة — فيُعرف إغلاق أمس وافتتاح اليوم ولو لم تصل دقيقة.
        day = broker_day_start(last["at"] - 1 if last else now)
        prior = [d for d in self.closes if d < day]
        prev = self.closes[max(prior)] if prior else None
        opened = self.opens.get(day)
        price = last["price"] if last else None
        out.update({"nasdaq_day": broker_date(day).isoformat(),
                    "nasdaq_prev_close": prev["close"] if prev else None,
                    "nasdaq_prev_close_source": prev["source"] if prev else None,
                    "nasdaq_prev_close_day": broker_date(max(prior)).isoformat() if prior else None,
                    "nasdaq_day_open": opened["open"] if opened else None,
                    "nasdaq_day_open_source": opened["source"] if opened else None,
                    "nasdaq_change_pct": quotes.pct(price, prev["close"] if prev else None),
                    "nasdaq_from_open_pct": quotes.pct(price, opened["open"] if opened else None)})
        if last is None:
            out["nasdaq_unavailable_reason"] = NO_CANDLES
            return out
        out.update({"nasdaq_last": price, "nasdaq_last_source": last["source"],
                    "nasdaq_last_age_min": round((now - last["at"]) / 60.0, 1)})
        if prev is None:
            out["nasdaq_unavailable_reason"] = "NO_PREVIOUS_CLOSE"
        return out

    def snapshot(self) -> dict[str, Any]:
        return {"closes": {str(int(d)): dict(v) for d, v in self.closes.items()},
                "opens": {str(int(d)): dict(v) for d, v in self.opens.items()},
                "last": dict(self.last) if self.last else None, "minute_day": self.minute_day}

    def restore(self, state: Any) -> None:
        if not isinstance(state, dict):
            return
        for name, store, field in (("closes", self.closes, "close"), ("opens", self.opens, "open")):
            rows = state.get(name)
            for key, value in (rows.items() if isinstance(rows, dict) else ()):
                day = quotes.num(key)
                if day is not None and isinstance(value, dict) and quotes.num(value.get(field)) is not None:
                    store[day] = {**value, field: quotes.num(value.get(field)),
                                  "at": quotes.num(value.get("at")) or day}
        last = state.get("last")
        if isinstance(last, dict) and quotes.num(last.get("price")) and quotes.num(last.get("at")):
            self.last = {"price": quotes.num(last["price"]), "at": quotes.num(last["at"]),
                         "source": str(last.get("source") or CANDLE_1M)}
        self.minute_day = quotes.num(state.get("minute_day"))
        self._trim()
