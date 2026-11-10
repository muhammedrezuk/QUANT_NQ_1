# -*- coding: utf-8 -*-
"""فحص 2: توقيت الأحداث وجهتها مقابل الشموع نفسها (لا نظر في المستقبل، الجهة صحيحة)."""
import json
import sqlite3
import sys
from collections import Counter

SB = r"C:\Users\NQ\AppData\Local\Temp\claude\C--\500dc279-a556-4c4c-881e-d017738aae39\scratchpad\structure_bench"
db = sqlite3.connect(r"file:C:\Users\NQ\QUANT_NQ\forex_runtime\var\history\ctrader_history.db?mode=ro", uri=True)
SEC = {"5m": 300, "15m": 900, "1h": 3600}
DBP = {"5m": "M5", "15m": "M15", "1h": "H1"}

for frame, lb in (("15m", 2), ("5m", 2), ("1h", 2), ("15m", 3)):
    sec = SEC[frame]
    C = {t: (o, h, l, c) for t, o, h, l, c in db.execute(
        "select period_start, open, high, low, close from candles_history where symbol='USTEC' and period=?", (DBP[frame],))}
    keys = sorted(C)
    idx = {t: i for i, t in enumerate(keys)}
    stats = Counter()
    sigs = Counter()
    for line in open(f"{SB}\\events\\{frame}_lb{lb}.jsonl", encoding="utf-8"):
        r = json.loads(line)
        e = r["e"]
        sigs[(e, r.get("sig") or r.get("official"))] += 1
        t = r["t"]
        ps = t - sec
        if e in ("bos", "choch"):
            stats[e + "_n"] += 1
            if ps not in C:
                stats[e + "_no_candle"] += 1
                continue
            c = C[ps][3]
            stats[e + "_close_eq"] += abs(c - r["close"]) < 1e-6
            side = r.get("break_side")
            lvl = r.get("level")
            if side == "above":
                stats[e + "_dir_ok"] += c > lvl
            elif side == "below":
                stats[e + "_dir_ok"] += c < lvl
            else:
                stats[e + "_noside"] += 1
            # هل كان الإغلاق السابق قد تجاوز المستوى (أي كسرٌ متأخّر)؟
            i = idx[ps]
            if i > 0:
                pc = C[keys[i - 1]][3]
                stats[e + "_prev_already_beyond"] += (pc > lvl) if side == "above" else (pc < lvl)
        elif e == "swing":
            stats["swing_n"] += 1
            st_ = r.get("swing_time")
            if st_ not in C:
                stats["swing_no_candle"] += 1
                continue
            i = idx[st_]
            lag = (idx.get(ps, -1) - i)
            stats[f"swing_lag_bars={lag}"] += 1
            o, h, l, c = C[st_]
            p = r["price"]
            if r["sig"] == "swing_high":
                stats["swing_price_eq"] += abs(h - p) < 1e-6
                win = [C[keys[j]][1] for j in range(max(0, i - lb), min(len(keys), i + lb + 1))]
                stats["swing_is_extreme"] += h >= max(win) - 1e-9
            else:
                stats["swing_price_eq"] += abs(l - p) < 1e-6
                win = [C[keys[j]][2] for j in range(max(0, i - lb), min(len(keys), i + lb + 1))]
                stats["swing_is_extreme"] += l <= min(win) + 1e-9
    print(frame, "lb", lb, dict(sorted(stats.items())), flush=True)
    print("   الإشارات:", dict(sorted(sigs.items(), key=lambda kv: -kv[1])), flush=True)
