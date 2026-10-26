# -*- coding: utf-8 -*-
"""Stage 4, attempt 2 (declared in the attempts ledger before running): everything relative to the median session range of
the previous five valid days ("ref"), because absolute pips do not hold between the two eras (the price itself doubled).

Q24b excursion / ref per half hour and horizon -- the table the "enough time" rule needs
Q26b first touch of each of the six levels after 09:45, then reversal vs break by 0.1 and 0.2 x ref within 60 minutes,
     counted from the bar AFTER the touch -- against random levels drawn the same way (the baseline)
Q27b the owner's footprint: pre-market tick volume / its median of the previous 20 days; agreement of the pre-market move
     with the session on unusual-volume days vs all days
Holdout (2025-10-01 ->) untouched. One process, 5-minute candles.
"""
from __future__ import annotations

import json
import random
import sqlite3
import statistics
import sys
import time
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import measure as m1  # noqa: E402

REF_DAYS = 5
VOL_DAYS = 20
K_REF = (0.1, 0.2)
RANDOM_PER_DAY = 6
UNUSUAL_VOL = 1.5


def load_bars_vol():
    con = sqlite3.connect("file:%s?mode=ro" % m1.HISTORY_DB, uri=True)
    rows = con.execute("SELECT period_start, open, high, low, close, tick_volume FROM candles_history "
                       "WHERE symbol=? AND period='M5' ORDER BY period_start", (m1.SYMBOL,)).fetchall()
    con.close()
    days = defaultdict(list)
    cache: dict[int, timedelta] = {}
    for ps, o, h, l, c, v in rows:
        hour = int(ps // 3600)
        if hour not in cache:
            cache[hour] = datetime.fromtimestamp(hour * 3600, m1.NY).utcoffset()
        local = datetime.fromtimestamp(ps, timezone.utc) + cache[hour]
        days[local.date()].append((local.hour * 60 + local.minute, o, h, l, c, v or 0))
    return days


def session_range(bars) -> float:
    rth = m1.window(bars, m1.RTH_OPEN, m1.RTH_CLOSE)
    h, l = m1.hl(rth)
    return h - l


def pct(values):
    return m1.pct(values)


def q24b(days, order, refs):
    cells = defaultdict(lambda: defaultdict(list))
    for idx, day in enumerate(order):
        sp = m1.split_of(day)
        ref = refs.get(day)
        if sp is None or not ref:
            continue
        rth = m1.window(days[day], m1.RTH_OPEN, m1.RTH_CLOSE)
        for slot in range(m1.RTH_OPEN, m1.RTH_CLOSE, m1.SLOT_MIN):
            start = [b for b in rth if b[0] >= slot]
            if not start:
                continue
            p0 = start[0][1]
            for horizon in m1.HORIZONS:
                end = slot + horizon
                if end > m1.RTH_CLOSE:
                    continue
                w = [b for b in start if b[0] < end]
                if not w:
                    continue
                key = "%02d:%02d|%d" % (slot // 60, slot % 60, horizon)
                cells[sp][key].append(((max(b[2] for b in w) - p0) / ref, (p0 - min(b[3] for b in w)) / ref))
    out = {}
    for sp, table in cells.items():
        out[sp] = {k: {"up": {p: round(sorted(u for u, _ in v)[min(len(v) - 1, int(len(v) * p / 100))], 3) for p in m1.PCTS},
                       "down": {p: round(sorted(d for _, d in v)[min(len(v) - 1, int(len(v) * p / 100))], 3) for p in m1.PCTS},
                       "n": len(v)} for k, v in sorted(table.items())}
    return out


def outcome(seg, level, above, k):
    for b in seg:
        rev = b[3] <= level - k if above else b[2] >= level + k
        brk = b[2] >= level + k if above else b[3] <= level - k
        if rev and brk:
            return "same_bar"
        if rev:
            return "reversal_first"
        if brk:
            return "break_first"
    return "neither"


def q26b(days, order, refs):
    tally = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))
    rng = random.Random(20261017)
    for idx, day in enumerate(order):
        sp = m1.split_of(day)
        ref = refs.get(day)
        if sp is None or not ref or idx == 0:
            continue
        bars = days[day]
        after = m1.window(bars, m1.FIRST15_END, m1.RTH_CLOSE)
        before = m1.window(bars, m1.RTH_OPEN, m1.FIRST15_END)
        if not after or not before:
            continue
        p0 = before[-1][4]
        levels = dict(m1.level_map(days, order, idx))
        for i in range(RANDOM_PER_DAY):
            sign = 1 if i % 2 == 0 else -1
            levels["random_%d" % i] = p0 + sign * rng.uniform(0.05, 0.5) * ref
        for name, level in levels.items():
            kind = "random" if name.startswith("random") else name
            above = level > p0
            touch = next((i for i, b in enumerate(after) if (b[2] >= level if above else b[3] <= level)), None)
            if touch is None:
                continue
            t0 = after[touch][0]
            seg = [b for b in after[touch + 1:] if b[0] < t0 + m1.TOUCH_WINDOW_MIN]
            for kr in K_REF:
                cell = tally[sp]["%s|%.1f" % (kind, kr)]
                cell["touch"] += 1
                cell[outcome(seg, level, above, kr * ref)] += 1
    return {sp: {k: dict(v) for k, v in t.items()} for sp, t in tally.items()}


def q27b(days, order, refs):
    rows = []
    vols = []
    for day in order:
        pre = m1.window(days[day], m1.PRE_OPEN, m1.RTH_OPEN)
        rth = m1.window(days[day], m1.RTH_OPEN, m1.RTH_CLOSE)
        if len(pre) < 30 or not rth:
            vols.append(None)
            continue
        vol = sum(b[5] for b in pre)
        prior = [v for v in vols[-VOL_DAYS:] if v]
        ratio = vol / statistics.median(prior) if len(prior) >= VOL_DAYS // 2 and statistics.median(prior) > 0 else None
        vols.append(vol)
        ref = refs.get(day)
        rows.append((m1.split_of(day), pre[-1][4] - pre[0][1], rth[-1][4] - rth[0][1], ratio,
                     abs(pre[-1][4] - pre[0][1]) / ref if ref else None))

    def agree(sel):
        pairs = [(a, b) for a, b in sel if a != 0 and b != 0]
        same = sum(1 for a, b in pairs if (a > 0) == (b > 0))
        return {"n": len(pairs), "agree_pct": round(100.0 * same / len(pairs), 1) if pairs else None}

    out = {}
    for sp in m1.SPLITS:
        mine = [r for r in rows if r[0] == sp]
        out[sp] = {
            "all_days": agree([(r[1], r[2]) for r in mine]),
            "unusual_volume": agree([(r[1], r[2]) for r in mine if r[3] and r[3] >= UNUSUAL_VOL]),
            "unusual_volume_and_strong_move": agree([(r[1], r[2]) for r in mine if r[3] and r[3] >= UNUSUAL_VOL
                                                     and r[4] and r[4] >= 0.3]),
            "strong_move_any_volume": agree([(r[1], r[2]) for r in mine if r[4] and r[4] >= 0.3]),
            "unusual_volume_days": sum(1 for r in mine if r[3] and r[3] >= UNUSUAL_VOL)}
    return out


def main():
    began = time.time()
    days = load_bars_vol()
    order = sorted(d for d in days if m1.valid_day(d, days[d]))
    ranges = {d: session_range(days[d]) for d in order}
    refs = {}
    for i, d in enumerate(order):
        prev = [ranges[x] for x in order[max(0, i - REF_DAYS):i]]
        if len(prev) == REF_DAYS:
            refs[d] = statistics.median(prev)
    result = {"attempt": 2, "ref": "median session range of the previous %d valid days" % REF_DAYS,
              "q24b": q24b(days, order, refs), "q26b": q26b(days, order, refs), "q27b": q27b(days, order, refs)}
    result["seconds"] = round(time.time() - began, 1)
    (HERE / "result2.json").write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    print("done", result["seconds"])


if __name__ == "__main__":
    main()
