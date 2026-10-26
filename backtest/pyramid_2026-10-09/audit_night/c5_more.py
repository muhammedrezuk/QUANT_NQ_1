# -*- coding: utf-8 -*-
"""فحص 5: (أ) 207 في القمّة بحالتها الحقيقيّة (الانتقال = لا جهة) · (ب) قدرة القمّة على رؤية حافّةٍ مزروعة بقوّاتٍ مختلفة ·
(ج) مدّة الصفقات وأثر الإغلاق عند نهاية النافذة · (د) زرع حافّةٍ في أداة وسط 150."""
import bisect
import json
import math
import random
import statistics as st
import sys
from collections import defaultdict
from datetime import datetime, timezone
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


# ── (أ) 207 بحالتها: الانتقال لا جهة ──
res_a = []
for frame in ("1h", "4h", "1d"):
    for lb in (1, 2, 3, 5):
        ev = E.load(frame, lb)
        if ev is None:
            continue
        rows = ev.get("trend207", [])
        times = [r["t"] for r in rows]
        for sess in ("london", "ny"):
            parts = {"train": [], "test": []}
            skipped = {"train": 0, "test": 0}
            for name, day, td, te, c0, c1 in E.SESS:
                if td < E.START or name != sess:
                    continue
                part = "train" if td < E.SPLIT else "test"
                i = bisect.bisect_right(times, td) - 1
                if i < 0:
                    continue
                d = {"uptrend": 1, "downtrend": -1}.get(rows[i]["official"], 0)
                if d == 0:
                    skipped[part] += 1
                    continue
                parts[part].append((c1 - c0) / c0 * 1e4 * d)
            res_a.append({"frame": frame, "lb": lb, "sess": sess,
                          **{p: {"n": len(v), "انتقال_متروك": skipped[p], "agree": round(sum(x > 0 for x in v) / len(v), 4) if v else None,
                                 "bps": round(st.mean(v), 2) if v else None, "t": tstat(v)} for p, v in parts.items()}})
best = sorted(res_a, key=lambda r: -min(r["train"]["t"] or -9, r["test"]["t"] or -9))[:6]
print("(أ) 207 بحالتها — أفضل ستّ:", json.dumps(best, ensure_ascii=False), flush=True)
print("(أ) عدد ما اجتاز t≥2 في الفترتين:", sum(1 for r in res_a if (r["train"]["t"] or 0) >= 2 and (r["test"]["t"] or 0) >= 2), "من", len(res_a), flush=True)

# ── (ب) قدرة القمّة: حقلٌ يصيب جهة الجلسة بنسبة q ──
random.seed(11)
for q in (0.53, 0.55, 0.60):
    out = {}
    for sess in ("london", "ny"):
        parts = {"train": defaultdict(list), "test": defaultdict(list)}
        for name, day, td, te, c0, c1 in E.SESS:
            if td < E.START or name != sess:
                continue
            ret = (c1 - c0) / c0 * 1e4
            true = 1 if ret > 0 else -1
            d = true if random.random() < (2 * q - 1) else random.choice((1, -1))
            parts["train" if td < E.SPLIT else "test"][d].append(ret)
        out[sess] = {p: {"t": M.welch(v[1], v[-1])} for p, v in parts.items()}
    print(f"(ب) حقلٌ يصيب {int(q*100)}٪:", json.dumps(out, ensure_ascii=False), flush=True)

# ── (ج) مدّة الصفقات والإغلاق عند نهاية النافذة ──
def capped(entry, stop, target, buy, t0, t_end):
    risk, span, sgn = abs(entry - stop), abs(target - entry), (1 if buy else -1)
    t1_, t2_ = entry + sgn * span / 3, entry + sgn * 2 * span / 3
    cur, rem, real, stage = stop, 1.0, 0.0, 0
    k = bisect.bisect_left(E.MT, t0)
    while k < len(E.M1) and E.M1[k][0] < t_end:
        t, o, h, lo, c = E.M1[k]
        if (lo <= cur) if buy else (h >= cur):
            px = min(o, cur) if buy else max(o, cur)
            return real + rem * ((px - entry) * sgn / risk) - 1.5 / risk, stage
        hit = (lambda v: h >= v) if buy else (lambda v: lo <= v)
        if stage < 1 and hit(t1_):
            real += (rem / 3) * (span / 3 / risk); rem -= rem / 3; cur = entry; stage = 1
        if stage < 2 and hit(t2_):
            real += (rem / 2) * (2 * span / 3 / risk); rem -= rem / 2; cur = t1_; stage = 2
        if hit(target):
            return real + rem * (span / risk) - 1.5 / risk, 3
        k += 1
    px, _ = E.close_at(t_end)
    return real + rem * ((px - entry) * sgn / risk) - 1.5 / risk, stage


def window_end(t, sess, kind):
    if kind == "day":
        lt = datetime.fromtimestamp(t - 1, NY)
        return lt.replace(hour=16, minute=0, second=0, microsecond=0).timestamp()
    tz, (h, m) = (LON, (11, 0)) if sess == "london" else (NY, (13, 0))
    lt = datetime.fromtimestamp(t - 1, tz)
    return lt.replace(hour=h, minute=m, second=0, microsecond=0).timestamp()


def sess_of(t):
    k = E.in_window(t - 1)
    return k.split("|")[0] if k else None


mid = json.load(open(SB + r"\mid_trades.json", encoding="utf-8"))
liq = json.load(open(SB + r"\liq_trades.json", encoding="utf-8"))
for label, trades in (("كسر 15د عرض2", mid["15m_lb2_bos_none"]), ("كسر 5د عرض2", mid["5m_lb2_bos_none"]),
                      ("كسر كاذب 5د عرض2", liq["5m_lb2_false_break_none"]), ("تغيّر 15د عرض3", mid["15m_lb3_choch_none"])):
    durs, rows = [], []
    for tr in trades:
        entry, _ = E.close_at(tr["t"])
        stop = entry - tr["risk"] if tr["buy"] else entry + tr["risk"]
        target = entry + 3 * tr["risk"] if tr["buy"] else entry - 3 * tr["risk"]
        R0, s0, tx = E.thirds(entry, stop, target, tr["buy"], tr["t"])
        if R0 is None:
            continue
        durs.append((tx - tr["t"]) / 3600)
        s = sess_of(tr["t"])
        Rw, sw = capped(entry, stop, target, tr["buy"], tr["t"], window_end(tr["t"], s, "win"))
        Rd, sd = capped(entry, stop, target, tr["buy"], tr["t"], window_end(tr["t"], s, "day"))
        rows.append((tr["t"], R0, Rw, Rd, sw))
    durs.sort()
    rep = {"مدّة_وسيط_ساعة": round(durs[len(durs) // 2], 2), "تتجاوز_يومًا%": round(sum(d > 24 for d in durs) / len(durs), 3)}
    for part, sel in (("تعلّم", lambda r: r[0] < E.SPLIT), ("اختبار", lambda r: r[0] >= E.SPLIT)):
        rr = [r for r in rows if sel(r)]
        rep[part] = {"n": len(rr), "R_بلا_سقف": round(st.mean(r[1] for r in rr), 4),
                     "R_إغلاق_نهاية_النافذة": round(st.mean(r[2] for r in rr), 4), "t_نافذة": tstat([r[2] for r in rr]),
                     "R_إغلاق_16_نيويورك": round(st.mean(r[3] for r in rr), 4)}
    print("(ج)", label, json.dumps(rep, ensure_ascii=False), flush=True)

# ── (د) حافّة مزروعة في أداة وسط 150 ──
import sqlite3  # noqa: E402
db = sqlite3.connect(r"file:C:\Users\NQ\QUANT_NQ\forex_runtime\var\history\ctrader_history.db?mode=ro", uri=True)
M5 = [r[0] + 300 for r in db.execute("select period_start from candles_history where symbol='USTEC' and period='M5' and period_start>=1512086400 order by period_start")]
random.seed(5)
fake_strong, fake_weak = [], []
for t in M5:
    c0, _ = E.close_at(t)
    c1, _ = E.close_at(t + 1800)
    if c0 is None or c1 is None:
        continue
    fr = c1 - c0
    fake_strong.append({"t": t, "m.fake_return": fr})
    fake_weak.append({"t": t, "m.fake_return": fr if random.random() < 0.2 else random.gauss(0, 10)})


def eval_fake(recs, base_key):
    fname, key, frame = M.BASES[base_key]
    trades = json.load(open(M.SB / fname, encoding="utf-8"))[key]
    times = [r["t"] for r in recs]
    rows = []
    for tr in trades:
        i = bisect.bisect_right(times, tr["t"]) - 1
        if i < 0:
            continue
        dd = M.direction("m.fake_return", recs[i]["m.fake_return"])
        if dd == 0:
            continue
        rows.append((tr, "توافق" if (dd > 0) == tr["buy"] else "تخالف"))
    res = {}
    for g in ("توافق", "تخالف"):
        res[g] = {}
        for part, sel in (("train", lambda x: x["t"] < M.SPLIT), ("test", lambda x: x["t"] >= M.SPLIT)):
            ing = [tr["R"] for tr, gg in rows if gg == g and sel(tr)]
            rest = [tr["R"] for tr, gg in rows if gg != g and sel(tr)]
            res[g][part] = {"n": len(ing), "R": round(st.mean(ing), 3) if ing else None, "t": M.welch(ing, rest)}
    return res


for base in ("كسر_5د_عرض2", "كنس_كاذب_5د_عرض2"):
    print("(د) مزروعة قويّة", base, json.dumps(eval_fake(fake_strong, base), ensure_ascii=False), flush=True)
    print("(د) مزروعة ضعيفة", base, json.dumps(eval_fake(fake_weak, base), ensure_ascii=False), flush=True)
