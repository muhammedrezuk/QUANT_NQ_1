# -*- coding: utf-8 -*-
"""Stage 4 of the owner's 44-step plan (2026-10-17): facts measured on the Nasdaq history, build vs test, holdout untouched.

Q24 expected movement per half hour of the New York session and per horizon (max excursion up/down, pips)
Q26 the six levels: after 09:45, first touch of each level, then reversal-first vs break-first by K pips within 60 minutes
Q27 the owner's question: does the pre-market move (04:00-09:30 NY) agree with the session (09:30-16:00) more on big-news,
    FOMC, earnings and unusual-pre-market days than on all days?
Q28 the spread per New York hour from the recorded ticks (if bid and ask are paired)
Q29 the month and the quarter: session range and share of up sessions per calendar month

Read-only on the databases. Writes a JSON and an Arabic Markdown report next to this file. One process, 5-minute candles
(about 860k rows), no lists of millions -- the freeze of 10-14 came from twelve processes loading 4.2M rows each.
"""
from __future__ import annotations

import json
import os
import sqlite3
import statistics
import sys
import time
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from shared import market_clock  # noqa: E402

HERE = Path(__file__).resolve().parent
HISTORY_DB = ROOT / "forex_runtime" / "var" / "history" / "ctrader_history.db"
BRIDGE_DB = Path(os.path.expandvars(r"%APPDATA%\MetaQuotes\Terminal\Common\Files\nq_brain.db"))
CALENDAR_DB = Path(os.path.expandvars(r"%APPDATA%\MetaQuotes\Terminal\Common\Files\nq_calendar_history.db"))
SYMBOL = "USTEC"
NY = ZoneInfo("America/New_York")
SPLITS = {"build": (date(2014, 7, 17), date(2020, 12, 31)), "test": (date(2021, 1, 1), date(2025, 9, 30))}
HOLDOUT_FROM = date(2025, 10, 1)
RTH_OPEN, RTH_CLOSE = 9 * 60 + 30, 16 * 60
PRE_OPEN = 4 * 60
FIRST15_END = RTH_OPEN + 15
SLOT_MIN = 30
HORIZONS = (15, 30, 60, 90, 120, 180, 240)
K_PIPS = (10, 20, 40)
TOUCH_WINDOW_MIN = 60
MIN_RTH_BARS = 70
PCTS = (25, 50, 75, 90)
BIG_NEWS = ("nonfarm", "cpi", "interest-rate", "fomc", "gdp", "retail-sales", "pce", "unemployment-rate", "ppi")
TOP_TICKERS = ("AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "GOOG", "META", "TSLA", "AVGO", "COST", "NFLX")


def split_of(day: date) -> str | None:
    for name, (a, b) in SPLITS.items():
        if a <= day <= b:
            return name
    return None


def pct(values: list[float]) -> dict:
    if not values:
        return {"n": 0}
    s = sorted(values)
    out = {"n": len(s)}
    for p in PCTS:
        out["p%d" % p] = round(s[min(len(s) - 1, int(len(s) * p / 100))], 1)
    return out


def load_bars():
    con = sqlite3.connect("file:%s?mode=ro" % HISTORY_DB, uri=True)
    rows = con.execute("SELECT period_start, open, high, low, close FROM candles_history WHERE symbol=? AND period='M5' "
                       "ORDER BY period_start", (SYMBOL,)).fetchall()
    con.close()
    days: dict[date, list] = defaultdict(list)
    cache: dict[int, timedelta] = {}
    for ps, o, h, l, c in rows:
        hour = int(ps // 3600)
        if hour not in cache:
            cache[hour] = datetime.fromtimestamp(hour * 3600, NY).utcoffset()
        local = datetime.fromtimestamp(ps, timezone.utc) + cache[hour]
        days[local.date()].append((local.hour * 60 + local.minute, o, h, l, c, ps))
    return days


def valid_day(day: date, bars: list) -> bool:
    if day.weekday() >= 5 or day >= HOLDOUT_FROM:
        return False
    noon = datetime(day.year, day.month, day.day, 12, tzinfo=NY).timestamp()
    if market_clock.no_trade_day(noon):
        return False
    return sum(1 for b in bars if RTH_OPEN <= b[0] < RTH_CLOSE) >= MIN_RTH_BARS


def window(bars: list, start_min: int, end_min: int) -> list:
    return [b for b in bars if start_min <= b[0] < end_min]


def hl(bars: list):
    return (max(b[2] for b in bars), min(b[3] for b in bars)) if bars else None


def q24(days: dict, order: list) -> dict:
    moves = defaultdict(lambda: defaultdict(list))
    ranges = defaultdict(lambda: defaultdict(list))
    for day in order:
        sp = split_of(day)
        if sp is None:
            continue
        bars = days[day]
        rth = window(bars, RTH_OPEN, RTH_CLOSE)
        r = hl(rth)
        ranges[sp]["session"].append(r[0] - r[1])
        pre = window(bars, PRE_OPEN, RTH_OPEN)
        if pre:
            p = hl(pre)
            ranges[sp]["premarket"].append(p[0] - p[1])
        for slot in range(RTH_OPEN, RTH_CLOSE, SLOT_MIN):
            start = [b for b in rth if b[0] >= slot]
            if not start:
                continue
            p0 = start[0][1]
            for horizon in HORIZONS:
                end = min(slot + horizon, RTH_CLOSE)
                if end - slot < horizon and horizon > 15:
                    continue                     # the horizon runs past the close: not counted
                w = [b for b in start if b[0] < end]
                if not w:
                    continue
                moves[sp]["%02d:%02d|%d" % (slot // 60, slot % 60, horizon)].append(
                    (max(b[2] for b in w) - p0, p0 - min(b[3] for b in w)))
    out = {}
    for sp, table in moves.items():
        out[sp] = {k: {"up": pct([u for u, _ in v]), "down": pct([d for _, d in v]),
                       "either": pct([max(u, d) for u, d in v])} for k, v in sorted(table.items())}
    return {"by_slot_horizon": out, "ranges": {sp: {k: pct(v) for k, v in t.items()} for sp, t in ranges.items()}}


def level_map(days: dict, order: list, idx: int) -> dict:
    day = order[idx]
    bars = days[day]
    prev = order[idx - 1] if idx > 0 else None
    out = {}
    if prev is not None:
        prth = window(days[prev], RTH_OPEN, RTH_CLOSE)
        if prth:
            h, l = hl(prth)
            out.update(yesterday_high=h, yesterday_low=l, yesterday_close=prth[-1][4])
        night = window(days[prev], RTH_CLOSE, 24 * 60) + window(bars, 0, RTH_OPEN)
        if night:
            out["overnight_high"], out["overnight_low"] = hl(night)
    pre = window(bars, PRE_OPEN, RTH_OPEN)
    if pre:
        out["premarket_high"], out["premarket_low"] = hl(pre)
    f15 = window(bars, RTH_OPEN, FIRST15_END)
    if f15:
        out["first15_high"], out["first15_low"] = hl(f15)
    week_days = [d for d in order[max(0, idx - 10):idx] if d.isocalendar()[:2] == day.isocalendar()[:2]]
    prev_week = [d for d in order[max(0, idx - 15):idx]
                 if d.isocalendar()[:2] == (day - timedelta(days=7)).isocalendar()[:2]]
    month_days = [d for d in order[max(0, idx - 25):idx] if (d.year, d.month) == (day.year, day.month)]
    first_of_month = day.replace(day=1)
    pm = first_of_month - timedelta(days=1)
    prev_month = [d for d in order[max(0, idx - 50):idx] if (d.year, d.month) == (pm.year, pm.month)]
    for name, ds in (("week", week_days), ("prev_week", prev_week), ("month", month_days), ("prev_month", prev_month)):
        rows = [b for d in ds for b in window(days[d], RTH_OPEN, RTH_CLOSE)]
        if rows:
            out[name + "_high"], out[name + "_low"] = hl(rows)
    return out


def q26(days: dict, order: list) -> dict:
    tally = defaultdict(lambda: defaultdict(lambda: {"touch": 0, "reversal_first": 0, "break_first": 0,
                                                     "neither": 0, "same_bar": 0}))
    for idx, day in enumerate(order):
        sp = split_of(day)
        if sp is None or idx == 0:
            continue
        bars = days[day]
        after = window(bars, FIRST15_END, RTH_CLOSE)
        before = window(bars, RTH_OPEN, FIRST15_END)
        if not after or not before:
            continue
        p0 = before[-1][4]
        for name, level in level_map(days, order, idx).items():
            above = level > p0
            touch = next((i for i, b in enumerate(after) if (b[2] >= level if above else b[3] <= level)), None)
            if touch is None:
                continue
            t0 = after[touch][0]
            seg = [b for b in after[touch:] if b[0] < t0 + TOUCH_WINDOW_MIN]
            for k in K_PIPS:
                cell = tally[sp]["%s|%d" % (name, k)]
                cell["touch"] += 1
                outcome = "neither"
                for b in seg:
                    rev = b[3] <= level - k if above else b[2] >= level + k
                    brk = b[2] >= level + k if above else b[3] <= level - k
                    if rev and brk:
                        outcome = "same_bar"
                        break
                    if rev:
                        outcome = "reversal_first"
                        break
                    if brk:
                        outcome = "break_first"
                        break
                cell[outcome] += 1
    return {sp: dict(t) for sp, t in tally.items()}


def broker_to_utc(server_ts: float) -> float:
    """MT5 calendar times are the broker's wall clock written as an epoch: subtract the broker offset of that date."""
    return server_ts - market_clock.broker_day_offset_s(server_ts)


def news_days() -> dict[str, set]:
    out = {"big_news_premarket": set(), "fomc": set(), "codes": set()}
    if not CALENDAR_DB.is_file():
        return out
    con = sqlite3.connect("file:%s?mode=ro" % CALENDAR_DB, uri=True)
    for code, name, importance, ts in con.execute(
            "SELECT event_code, event_name, importance, time_server FROM calendar_history WHERE currency='USD'"):
        text = (str(code) + " " + str(name)).lower()
        if not any(k in text for k in BIG_NEWS):
            continue
        utc = broker_to_utc(float(ts))
        local = datetime.fromtimestamp(utc, NY)
        minute = local.hour * 60 + local.minute
        if "interest-rate" in text or "fomc" in text:
            out["fomc"].add(local.date())
        elif PRE_OPEN <= minute < RTH_OPEN:
            out["big_news_premarket"].add(local.date())
            out["codes"].add(str(code))
    con.close()
    return out


def earnings_days() -> set:
    days = set()
    if not BRIDGE_DB.is_file():
        return days
    con = sqlite3.connect("file:%s?mode=ro" % BRIDGE_DB, uri=True)
    try:
        for ticker, reported in con.execute("SELECT ticker, date_reported FROM earnings_history"):
            if str(ticker).upper() in TOP_TICKERS:
                d = date.fromisoformat(str(reported)[:10])
                days.add(d)
                days.add(d + timedelta(days=1))   # after-hours reports show in the next pre-market
    except sqlite3.Error:
        pass
    con.close()
    return days


def q27(days: dict, order: list) -> dict:
    news = news_days()
    earn = earnings_days()
    rows = []
    for day in order:
        sp = split_of(day)
        if sp is None:
            continue
        bars = days[day]
        pre = window(bars, PRE_OPEN, RTH_OPEN)
        rth = window(bars, RTH_OPEN, RTH_CLOSE)
        if len(pre) < 30 or not rth:
            continue
        pre_move = pre[-1][4] - pre[0][1]
        rth_move = rth[-1][4] - rth[0][1]
        h, l = hl(pre)
        rows.append((sp, day, pre_move, rth_move, h - l))
    cut = {sp: pct([r[4] for r in rows if r[0] == sp]).get("p75") for sp in SPLITS}
    def agree(sel):
        pairs = [(a, b) for a, b in sel if a != 0 and b != 0]
        same = sum(1 for a, b in pairs if (a > 0) == (b > 0))
        return {"n": len(pairs), "agree_pct": round(100.0 * same / len(pairs), 1) if pairs else None}
    out = {"big_news_codes": sorted(news["codes"])[:40], "earnings_days_known": len(earn)}
    for sp in SPLITS:
        mine = [r for r in rows if r[0] == sp]
        out[sp] = {
            "all_days": agree([(r[2], r[3]) for r in mine]),
            "big_news_premarket": agree([(r[2], r[3]) for r in mine if r[1] in news["big_news_premarket"]]),
            "fomc_days": agree([(r[2], r[3]) for r in mine if r[1] in news["fomc"]]),
            "earnings_days": agree([(r[2], r[3]) for r in mine if r[1] in earn]),
            "unusual_premarket_range": agree([(r[2], r[3]) for r in mine if cut[sp] and r[4] >= cut[sp]]),
            "unusual_and_news": agree([(r[2], r[3]) for r in mine if cut[sp] and r[4] >= cut[sp]
                                       and (r[1] in news["big_news_premarket"] or r[1] in earn)]),
            "premarket_range_p75": cut[sp]}
    return out


def q28() -> dict:
    con = sqlite3.connect("file:%s?mode=ro" % HISTORY_DB, uri=True)
    try:
        last = con.execute("SELECT MAX(ts_ms) FROM ticks_history WHERE symbol=?", (SYMBOL,)).fetchone()[0]
        if not last:
            return {"available": False, "reason": "no ticks for the symbol"}
        since = last - 10 * 86400 * 1000
        bid, ask = {}, {}
        for side, ts, price in con.execute("SELECT side, ts_ms, price FROM ticks_history WHERE symbol=? AND ts_ms>=?",
                                           (SYMBOL, since)):
            (bid if str(side).lower().startswith("b") else ask)[ts] = price
    finally:
        con.close()
    by_hour = defaultdict(list)
    for ts, b in bid.items():
        a = ask.get(ts)
        if a is not None and a >= b:
            by_hour[datetime.fromtimestamp(ts / 1000, NY).hour].append(a - b)
    if not by_hour:
        return {"available": False, "reason": "bid and ask are not paired by time"}
    return {"available": True, "days": 10, "by_ny_hour": {h: {"median": round(statistics.median(v), 2), "n": len(v)}
                                                           for h, v in sorted(by_hour.items())}}


def q29(days: dict, order: list) -> dict:
    cells = defaultdict(lambda: defaultdict(lambda: {"ranges": [], "up": 0, "n": 0}))
    for day in order:
        sp = split_of(day)
        if sp is None:
            continue
        rth = window(days[day], RTH_OPEN, RTH_CLOSE)
        h, l = hl(rth)
        c = cells[sp][day.month]
        c["ranges"].append(h - l)
        c["n"] += 1
        c["up"] += 1 if rth[-1][4] > rth[0][1] else 0
    out = {}
    for sp, months in cells.items():
        out[sp] = {m: {"n": c["n"], "up_pct": round(100.0 * c["up"] / c["n"], 1),
                       "range_median": round(statistics.median(c["ranges"]), 1)} for m, c in sorted(months.items())}
    return out


def main() -> None:
    began = time.time()
    days = load_bars()
    order = sorted(d for d in days if valid_day(d, days[d]))
    result = {"symbol": SYMBOL, "splits": {k: [a.isoformat(), b.isoformat()] for k, (a, b) in SPLITS.items()},
              "holdout_from": HOLDOUT_FROM.isoformat(), "days_used": len(order)}
    result["q24"] = q24(days, order)
    result["q26"] = q26(days, order)
    result["q27"] = q27(days, order)
    try:
        result["q28"] = q28()
    except sqlite3.Error as exc:
        result["q28"] = {"available": False, "reason": str(exc)}
    result["q29"] = q29(days, order)
    result["seconds"] = round(time.time() - began, 1)
    (HERE / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    print("done", result["days_used"], result["seconds"])


if __name__ == "__main__":
    main()
