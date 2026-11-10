# -*- coding: utf-8 -*-
"""فحص 6: (أ) قدرة معيار القمّة (|t|≥2 في الفترتين) على رؤية حقلٍ يصيب الجهة بنسبة q — 300 تكرار ·
(ب) التركيبة التي لم تُقس: زناد البنية/الكنس في جهة البطاقة 414 نفسها (إغلاق الساعة والأربع ساعات مقابل متوسّط 20 من 151)
بقوانين المالك (وقف 15–50 من البنية · 3R · أثلاث · صفقتان · نافذتاه)."""
import bisect
import json
import math
import random
import statistics as st
import sys
from collections import defaultdict
from datetime import datetime
from zoneinfo import ZoneInfo

SB = r"C:\Users\NQ\AppData\Local\Temp\claude\C--\500dc279-a556-4c4c-881e-d017738aae39\scratchpad\structure_bench"
S150 = r"C:\Users\NQ\AppData\Local\Temp\claude\C--\500dc279-a556-4c4c-881e-d017738aae39\scratchpad\s150_bench"
sys.path.insert(0, SB)
sys.path.insert(0, S150)
import eval_structure as E  # noqa: E402
import eval150_mid as M  # noqa: E402

LON, NY = ZoneInfo("Europe/London"), ZoneInfo("America/New_York")


def tstat(xs):
    n = len(xs)
    if n < 3 or st.pstdev(xs) == 0:
        return None
    return round(st.mean(xs) / (st.pstdev(xs) / math.sqrt(n)), 2)


# ── (أ) القدرة ──
sess_rets = {"london": [], "ny": []}
for name, day, td, te, c0, c1 in E.SESS:
    if td >= E.START:
        sess_rets[name].append((td < E.SPLIT, (c1 - c0) / c0 * 1e4))
for q in (0.53, 0.55, 0.57, 0.60):
    rate = {}
    for sess, rows in sess_rets.items():
        ok = 0
        for seed in range(300):
            rnd = random.Random(seed)
            g = {True: {1: [], -1: []}, False: {1: [], -1: []}}
            for tr, ret in rows:
                true = 1 if ret > 0 else -1
                d = true if rnd.random() < (2 * q - 1) else (1 if rnd.random() < 0.5 else -1)
                g[tr][d].append(ret)
            a = M.welch(g[True][1], g[True][-1])
            b = M.welch(g[False][1], g[False][-1])
            ok += a is not None and b is not None and a >= 2 and b >= 2
        rate[sess] = round(ok / 300, 2)
    print(f"(أ) حقلٌ يصيب جهة الجلسة {int(q * 100)}٪ ⟸ نسبة اجتيازه معيار القمّة:", rate, flush=True)

# ── (ب) جهة 414 (إغلاق الساعة والأربع مقابل متوسّط 20) فوق زناد البنية ──
def series151(frame):
    rows = []
    for line in open(S150 + rf"\facts\151_{frame}_base.jsonl", encoding="utf-8"):
        r = json.loads(line)
        if "m.close" in r and "m.ema_slow_value" in r:
            rows.append((r["t"], 1 if r["m.close"] > r["m.ema_slow_value"] else (-1 if r["m.close"] < r["m.ema_slow_value"] else 0)))
    return rows, [x[0] for x in rows]


H1, H4 = series151("1h"), series151("4h")


def dir414(t):
    i = bisect.bisect_right(H1[1], t) - 1
    j = bisect.bisect_right(H4[1], t) - 1
    if i < 0 or j < 0:
        return 0
    a, b = H1[0][i][1], H4[0][j][1]
    return a if a == b else 0


def window_key(t_close):
    t = t_close - 1
    for name, tz, a, b in (("london", LON, 8 * 60 + 15, 11 * 60), ("ny", NY, 9 * 60 + 45, 13 * 60)):
        lt = datetime.fromtimestamp(t, tz)
        if lt.weekday() < 5 and a <= lt.hour * 60 + lt.minute < b:
            return name + "|" + lt.date().isoformat()
    return None


def run_struct(frame, lb, kind, use414):
    ev = E.load(frame, lb)
    sw_hi = sorted((r["t"], r["price"]) for r in ev["swing"] if r["sig"] == "swing_high")
    sw_lo = sorted((r["t"], r["price"]) for r in ev["swing"] if r["sig"] == "swing_low")
    hi_t, lo_t = [x[0] for x in sw_hi], [x[0] for x in sw_lo]
    evs = sorted((r for r in ev[kind] if r.get("break_side") in ("above", "below")), key=lambda r: r["t"])
    trades, busy, per = [], 0.0, defaultdict(int)
    for r in evs:
        t = r["t"]
        if t < E.START or t < busy:
            continue
        k = window_key(t)
        if k is None or per[k] >= 2:
            continue
        buy = r["break_side"] == "above"
        if use414 and dir414(t) != (1 if buy else -1):
            continue
        entry = r["close"]
        if buy:
            i = bisect.bisect_right(lo_t, t) - 1
            if i < 0:
                continue
            stop = sw_lo[i][1] - 1.0
        else:
            i = bisect.bisect_right(hi_t, t) - 1
            if i < 0:
                continue
            stop = sw_hi[i][1] + 1.0
        risk = (entry - stop) if buy else (stop - entry)
        if not (15.0 <= risk <= 50.0):
            continue
        target = entry + 3 * risk if buy else entry - 3 * risk
        R, stage, tx = E.thirds(entry, stop, target, buy, t)
        if R is None:
            continue
        per[k] += 1
        busy = tx
        trades.append({"t": t, "R": R, "stage": stage, "s": k[:2]})
    return trades


def run_false_break(frame, lb, use414):
    rows = []
    for line in open(SB + rf"\liq\{frame}_lb{lb}.jsonl", encoding="utf-8"):
        if '"e": "sweep"' not in line:
            continue
        r = json.loads(line)
        if r["t"] >= E.START:
            rows.append(r)
    rows.sort(key=lambda r: r["t"])
    trades, busy, per = [], 0.0, defaultdict(int)
    for r in rows:
        t = r["t"]
        if t < busy:
            continue
        k = window_key(t)
        if k is None or per[k] >= 2:
            continue
        took_high = r.get("direction") == "buy_side"
        level, hi, lo = r.get("price"), r.get("high"), r.get("low")
        if level is None:
            continue
        c, _ = E.close_at(t)
        if not ((c < level) if took_high else (c > level)):
            continue
        buy = not took_high
        if use414 and dir414(t) != (1 if buy else -1):
            continue
        stop = (lo - 1.0) if buy else (hi + 1.0)
        risk = (c - stop) if buy else (stop - c)
        if not (15.0 <= risk <= 50.0):
            continue
        target = c + 3 * risk if buy else c - 3 * risk
        R, stage, tx = E.thirds(c, stop, target, buy, t)
        if R is None:
            continue
        per[k] += 1
        busy = tx
        trades.append({"t": t, "R": R, "stage": stage, "s": k[:2]})
    return trades


def summ(trades):
    out = {}
    for part, sel in (("تعلّم", lambda x: x["t"] < E.SPLIT), ("اختبار", lambda x: x["t"] >= E.SPLIT)):
        rs = [x["R"] for x in trades if sel(x)]
        out[part] = {"n": len(rs), "R": round(st.mean(rs), 4) if rs else None, "t": tstat(rs),
                     "t3%": round(sum(1 for x in trades if sel(x) and x["stage"] == 3) / len(rs), 3) if rs else None}
    for s in ("lo", "ny"):
        rs = [x["R"] for x in trades if x["s"] == s]
        out[s] = {"n": len(rs), "R": round(st.mean(rs), 4) if rs else None}
    return out


for frame, lb in (("5m", 2), ("5m", 3), ("15m", 2), ("15m", 3)):
    for kind in ("bos", "choch"):
        print(f"(ب) {frame} عرض{lb} {kind} في جهة 414:", json.dumps(summ(run_struct(frame, lb, kind, True)), ensure_ascii=False), flush=True)
for frame, lb in (("5m", 2), ("15m", 2), ("1m", 2)):
    print(f"(ب) كسر كاذب {frame} عرض{lb} في جهة 414:", json.dumps(summ(run_false_break(frame, lb, True)), ensure_ascii=False), flush=True)
