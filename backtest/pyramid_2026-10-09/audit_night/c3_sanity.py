# -*- coding: utf-8 -*-
"""فحص 3: (أ) مطابقة الأثلاث بتنفيذٍ مستقلّ · (ب) إعادة إنتاج 414 من صفقاتها · (ج) إعادة بناء صفقات الوسط باستقلال ·
(د) زرع حافّةٍ معروفة في أداة الوسط (يجب أن تُظهر ربحًا كبيرًا)."""
import bisect
import json
import random
import statistics as st
import sys
from collections import defaultdict
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

SB = r"C:\Users\NQ\AppData\Local\Temp\claude\C--\500dc279-a556-4c4c-881e-d017738aae39\scratchpad\structure_bench"
sys.path.insert(0, SB)
import eval_structure as E  # noqa: E402

LON, NY = ZoneInfo("Europe/London"), ZoneInfo("America/New_York")


def my_thirds(entry, stop, buy, t0, target):
    """تنفيذٌ مستقلّ من نصّ قانون المالك: ثلثٌ عند ثلث المسافة والوقف للدخول، نصف الباقي عند ثلثيها والوقف للأوّل،
    والباقي عند الهدف. الوقف أوّلًا عند الالتباس. كلفة 1.5 نقطة على الدورة."""
    risk = abs(entry - stop)
    d = 1 if buy else -1
    dist = abs(target - entry)
    lv1, lv2 = entry + d * dist / 3, entry + d * 2 * dist / 3
    size, pnl, sl, stage = 1.0, 0.0, stop, 0
    i = bisect.bisect_left(E.MT, t0)
    while i < len(E.M1):
        _, o, h, l, c = E.M1[i]
        adverse = l if buy else h
        if (adverse - sl) * d <= 0:
            fill = (min(o, sl) if buy else max(o, sl))
            pnl += size * (fill - entry) * d
            return (pnl - 1.5) / risk, stage
        fav = h if buy else l
        if stage == 0 and (fav - lv1) * d >= 0:
            pnl += (size / 3) * (lv1 - entry) * d; size *= 2 / 3; sl = entry; stage = 1
        if stage == 1 and (fav - lv2) * d >= 0:
            pnl += (size / 2) * (lv2 - entry) * d; size /= 2; sl = lv1; stage = 2
        if (fav - target) * d >= 0:
            pnl += size * (target - entry) * d
            return (pnl - 1.5) / risk, 3
        i += 1
    return None, None


out = {}
# ── (أ+ب) صفقات 414 ──
d414 = json.load(open(r"C:\Users\NQ\QUANT_NQ\backtest\card_414\نتائج\card_prob_trades.json", encoding="utf-8"))
T = d414["trades"]
mis_E = mis_my = 0
agg = defaultdict(list)
for tr in T:
    rE, sE, _ = E.thirds(tr["entry"], tr["stop"], tr["target"], tr["buy"], tr["t"])
    rM, sM = my_thirds(tr["entry"], tr["stop"], tr["buy"], tr["t"], tr["target"])
    if rE is None:
        continue
    mis_E += abs(rE - tr["r"]) > 1e-6
    mis_my += abs(rM - rE) > 1e-9
    w = "london" if tr["window"].startswith("london") else "ny"
    agg[w].append((tr["r"], rE, sE))
for w, rows in agg.items():
    out[f"414_{w}"] = {"n": len(rows), "R_ملف": round(st.mean(r[0] for r in rows), 4),
                       "R_بأداة_الليلة": round(st.mean(r[1] for r in rows), 4),
                       "الهدف_الأوّل%": round(sum(1 for r in rows if r[2] >= 1) / len(rows), 3),
                       "الهدف_الثالث%": round(sum(1 for r in rows if r[2] == 3) / len(rows), 3)}
out["414_اختلاف_أداة_الليلة_عن_الملف"] = mis_E
out["اختلاف_الأثلاث_المستقلّة_عن_أداة_الليلة"] = mis_my
print(json.dumps(out, ensure_ascii=False), flush=True)

# ── (ج) إعادة بناء صفقات «15د عرض 2 كسر بلا مرشّح» باستقلال ──
ev = E.load("15m", 2)
sw_hi = sorted((r["t"], r["price"]) for r in ev["swing"] if r["sig"] == "swing_high")
sw_lo = sorted((r["t"], r["price"]) for r in ev["swing"] if r["sig"] == "swing_low")
hi_t, lo_t = [x[0] for x in sw_hi], [x[0] for x in sw_lo]


def window_key(t_close):
    t = t_close - 1
    for name, tz, a, b in (("london", LON, 8 * 60 + 15, 11 * 60), ("ny", NY, 9 * 60 + 45, 13 * 60)):
        lt = datetime.fromtimestamp(t, tz)
        if lt.weekday() < 5 and a <= lt.hour * 60 + lt.minute < b:
            return name + "|" + lt.date().isoformat()
    return None


def simulate(events, direction_fn, stop_mode="swing"):
    trades, busy, per = [], 0.0, defaultdict(int)
    for r in events:
        t = r["t"]
        if t < E.START or t < busy:
            continue
        k = window_key(t)
        if k is None or per[k] >= 2:
            continue
        buy = direction_fn(r)
        if buy is None:
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
        R, stage = my_thirds(entry, stop, buy, t, target)
        if R is None:
            continue
        _, _, t_exit = E.thirds(entry, stop, target, buy, t)
        per[k] += 1
        busy = t_exit
        trades.append({"t": t, "buy": buy, "R": R, "stage": stage})
    return trades


def summary(trades):
    res = {}
    for part, sel in (("تعلّم", lambda x: x["t"] < E.SPLIT), ("اختبار", lambda x: x["t"] >= E.SPLIT)):
        rs = [x["R"] for x in trades if sel(x)]
        n = len(rs)
        res[part] = {"n": n, "R": round(st.mean(rs), 4) if rs else None,
                     "t": round(st.mean(rs) / (st.pstdev(rs) / n ** 0.5), 2) if n > 2 else None,
                     "sd": round(st.pstdev(rs), 3) if n > 2 else None,
                     "t3%": round(sum(1 for x in trades if sel(x) and x["stage"] == 3) / n, 3) if n else None}
    return res


bos = sorted([r for r in ev["bos"] if r.get("break_side") in ("above", "below")], key=lambda r: r["t"])
mine = simulate(bos, lambda r: r["break_side"] == "above")
theirs = json.load(open(SB + r"\mid_trades.json", encoding="utf-8"))["15m_lb2_bos_none"]
same = len({(x["t"], x["buy"]) for x in mine} & {(x["t"], x["buy"]) for x in theirs})
dR = max((abs(a["R"] - b["R"]) for a, b in zip(mine, theirs)), default=None)
print(json.dumps({"إعادة_البناء_15د_كسر": {"عندي": len(mine), "عندهم": len(theirs), "مشترك": same,
                                           "أقصى_فرق_R": dR, "ملخّصي": summary(mine)}}, ensure_ascii=False), flush=True)

# ── (د) حافّة مزروعة: الجهة = إشارة حركة الثلاثين دقيقة التالية (نظرٌ في المستقبل عمدًا) ──
def peek(r, minutes=30):
    c0, _ = E.close_at(r["t"])
    c1, _ = E.close_at(r["t"] + minutes * 60)
    if c0 is None or c1 is None or c1 == c0:
        return None
    return c1 > c0


planted = simulate(bos, peek)
print(json.dumps({"مزروعة_30د": summary(planted)}, ensure_ascii=False), flush=True)
# حافّة أضعف: الجهة الصحيحة (30 د) بنسبة 60٪ وعشوائيّة في الباقي
random.seed(7)
weak = simulate(bos, lambda r: (peek(r) if random.random() < 0.2 else random.random() < 0.5))
print(json.dumps({"مزروعة_ضعيفة_60٪": summary(weak)}, ensure_ascii=False), flush=True)
# الجهة عكس الكسر (للعلم): هل الكسر يعكس؟
rev = simulate(bos, lambda r: r["break_side"] != "above")
print(json.dumps({"عكس_الكسر": summary(rev)}, ensure_ascii=False), flush=True)
