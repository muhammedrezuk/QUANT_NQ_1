# -*- coding: utf-8 -*-
"""محرّك تشخيص البطاقة 414 ومعايرتها — قياسٌ فقط، خارج المشروع، قراءة البيانات وحدها.

يحمّل الفترة بنسخة المسطرة القابلة للضبط نفسها (unseen/card_replay.py · البداية والنهاية وحدهما)،
ثمّ يبني «المرشّحات»: كلّ شمعة 5 د تمرّ فيها شروط البطاقة التي لا تتعلّق بالعيار
(النافذة · الخبر · الجهة على الساعة و4 س · الإس آند بي · بنية الارتداد · الزناد) — بالتعريفات نفسها
في `shared/card_trend.evaluate` حرفًا. ثمّ لكلّ عيار: الوقف (ب، ن) والهدف (ج، ≥ 3) وحكم الإرسال الصافي
(سبريد 1.5) وأدنى وقف 3 ن.أ ثمّ أثلاث المالك على شموع الدقيقة (نسخة R.thirds حرفًا + مرحلة الأثلاث).

التحقّق: العيار الحاليّ بلا أرضيّة الوقف يجب أن يطابق ملفّ صفقات المرجع صفقةً صفقة، وكلّ صفقةٍ منه
تُعاد بـ CT.evaluate مع سلّم S.ladder_at فتعطي OPEN بالوقف والهدف نفسيهما.

الاستعمال: python engine.py <البداية> <آخر يوم أو -> <ملفّ العيارات.json> <ملفّ الإخراج.json> [ملفّ صفقات المرجع] [مفتاحه]
"""
import sys
sys.dont_write_bytecode = True
sys.stdout.reconfigure(encoding="utf-8")

import bisect
import calendar
import json
import os
import sqlite3
import time
from datetime import datetime, timezone

T0 = time.time()
START_DAY, END_DAY, CFG_PATH, OUT_PATH = sys.argv[1:5]
REF_PATH = sys.argv[5] if len(sys.argv) > 5 else None
REF_KEY = sys.argv[6] if len(sys.argv) > 6 else None
os.environ.pop("UNSEEN_START", None); os.environ.pop("UNSEEN_END", None)
os.environ["UNSEEN_START"] = START_DAY
if END_DAY != "-":
    os.environ["UNSEEN_END"] = END_DAY

HERE = os.path.dirname(os.path.abspath(__file__))
UNSEEN = os.path.join(os.path.dirname(HERE), "unseen")
sys.path.insert(0, r"C:\Users\NQ\QUANT_NQ")
sys.path.insert(0, UNSEEN)

import card_replay as R
import card_replay_shared as S
import card_variants as V
import card_final_check as FC
from shared import card_trend as CT
from shared.owner_windows import owner_window
for _m in (R, S, V, FC):
    assert os.path.dirname(os.path.abspath(_m.__file__)) == UNSEEN, _m.__file__
assert CT.PEERS == ("US500",), CT.PEERS
assert R.COST == 1.5

fmt = lambda t: datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%d %H:%M")
print("الفترة %s ⟶ %s · تحميل %.0f ث" % (fmt(R.START), fmt(R.END), time.time() - T0), flush=True)

SPREAD = 1.5
REF = {"US500": V.REF["US500"]}

# ───────── اليوميّ الكامل (للنظام فقط: متوسّطا 50 و200 وتذبذب اليوم مقابل وسيطه) ─────────
_db = sqlite3.connect(R.DB, uri=True)
D1 = [tuple(map(float, r)) for r in _db.execute(
    "select period_start, open, high, low, close from candles_history where symbol='USTEC' and period='D1' "
    "order by period_start")]
TD = [r[0] for r in D1]
CL = [r[4] for r in D1]
ATR_D = R.atr(D1)


def _sma(k, n):
    return sum(CL[k - n + 1:k + 1]) / n if k >= n - 1 else None


ATRPCT = [a / c for a, c in zip(ATR_D, CL)]
# الكلفة النسبيّة (للعلم): 1.5 نقطة عند وسيط إغلاق الفترة أ (2024-10-01 ⟶ 2026-10-05)
_a0, _a1 = calendar.timegm((2024, 10, 1, 0, 0, 0)), calendar.timegm((2026, 10, 6, 0, 0, 0))
_closes_a = sorted(c for t, c in zip(TD, CL) if _a0 <= t < _a1)
P_REF = _closes_a[len(_closes_a) // 2]
K_PROP = SPREAD / P_REF


def regime(t):
    k = bisect.bisect_right(TD, t - 86400) - 1          # آخر يومٍ أُغلق قبل t (كـ closed_index)
    if k < 260:
        return None
    s50, s200 = _sma(k, 50), _sma(k, 200)
    win = sorted(ATRPCT[k - 249:k + 1])
    med = win[len(win) // 2]
    return {"cd": CL[k], "s50": s50, "s200": s200, "above50": CL[k] > s50, "above200": CL[k] > s200,
            "atrpct": ATRPCT[k], "atrmed": med, "volhi": ATRPCT[k] > med,
            "volratio": ATRPCT[k] / med}


# ───────── المرشّحات (شروط البطاقة المستقلّة عن العيار) ─────────
(HI5, HI5T), (LO5, LO5T) = S.frames["5m"]
(HI1, HI1T), (LO1, LO1T) = S.frames["1h"]
(HI4, HI4T), (LO4, LO4T) = S.frames["4h"]
KEEP = S.KEEP


def levels_at(t, buy):
    """مستويات الساعة ثمّ 4 س في الجهة — آخر KEEP مؤكَّدة حتّى t (كـ S.ladder_at ثمّ CT.evaluate)."""
    out = []
    for name in ("1h", "4h"):
        (hi, hit), (lo, lot) = S.frames[name]
        rows, times = (hi, hit) if buy else (lo, lot)
        k = bisect.bisect_right(times, t)
        out.extend(p for ts, p in rows[max(0, k - KEEP[name]):k])
    return out


CANDS = []
tally = {}
for j in range(1, len(R.m5)):
    t_close = R.m5[j][0] + 300
    if t_close < R.START:
        continue
    win = owner_window(t_close)
    if not win:
        continue
    if R.news_block(t_close):
        continue
    d = CT.direction_of(S.fact_trend(R.h1, R.e_h1, R.th1, 3600, t_close),
                        S.fact_trend(R.h4, R.e_h4, R.th4, 14400, t_close))
    if d == 0:
        continue
    pf = (FC.peer_fact(REF["US500"][0], 3600, t_close), FC.peer_fact(REF["US500"][1], 14400, t_close))
    if None in pf:
        tally["peers_missing"] = tally.get("peers_missing", 0) + 1
        continue
    if CT.direction_of(*pf) != d:
        continue
    atr5 = R.a5[j]
    idd = R.closed_index(R.td1, 86400, t_close)
    atr1d = R.ad1[idd] if idd >= 0 else None
    if atr5 is None or atr5 <= 0 or atr1d is None or atr1d <= 0:
        tally["fact_missing"] = tally.get("fact_missing", 0) + 1
        continue
    kh, kl = bisect.bisect_left(HI5T, t_close) - 1, bisect.bisect_left(LO5T, t_close) - 1
    if kh < 0 or kl < 0:
        continue
    hi_ts, hi_p = HI5[kh]; lo_ts, lo_p = LO5[kl]
    close, prev = R.m5[j][4], R.m5[j - 1][4]
    buy = d > 0
    if buy:
        if not (lo_ts > hi_ts and close > hi_p and prev <= hi_p):
            continue
        pull = lo_p
    else:
        if not (hi_ts > lo_ts and close < lo_p and prev >= lo_p):
            continue
        pull = hi_p
    rg = regime(t_close)
    CANDS.append({"j": j, "t": t_close, "win": win, "buy": buy, "entry": close, "pull": pull,
                  "atr5": atr5, "atr1d": atr1d, "levels": levels_at(t_close, buy),
                  "year": datetime.fromtimestamp(t_close, timezone.utc).year, **(rg or {})})
print("مرشّحات: %d · %s · %.0f ث" % (len(CANDS), tally, time.time() - T0), flush=True)


def thirds(entry, stop, target, buy, k, cost):
    """R.thirds حرفًا (الكلفة معاملٌ) + المرحلة التي بلغتها (0 وقف كامل · 1 الأوّل · 2 الثاني · 3 الهدف)."""
    m1 = R.m1
    risk, span, sgn = abs(entry - stop), abs(target - entry), (1 if buy else -1)
    t1_, t2_ = entry + sgn * span / 3, entry + sgn * 2 * span / 3
    cur, rem, real, stage = stop, 1.0, 0.0, 0
    while k < len(m1):
        t, o, h, lo, c = m1[k]
        if (lo <= cur) if buy else (h >= cur):
            px = min(o, cur) if buy else max(o, cur)
            return real + rem * ((px - entry) * sgn / risk) - cost / risk, t, stage
        hit = (lambda v: h >= v) if buy else (lambda v: lo <= v)
        if stage < 1 and hit(t1_):
            real += (rem / 3) * (span / 3 / risk); rem -= rem / 3; cur = entry; stage = 1
        if stage < 2 and hit(t2_):
            real += (rem / 2) * (2 * span / 3 / risk); rem -= rem / 2; cur = t1_; stage = 2
        if hit(target):
            return real + rem * (span / risk) - cost / risk, t, 3
        k += 1
    return None, None, None


_cache = {}


def run(cfg):
    b, n, c = cfg["b"], cfg["n"], cfg["c"]
    filt = compile(cfg.get("filter", "True"), "<filter>", "eval")
    verdict = cfg.get("verdict", True)
    prop = cfg.get("cost", "fixed") == "prop"
    floor = cfg.get("min_stop_bps", 3.0)
    trades, busy = [], 0.0
    rej = {"filter": 0, "no_target": 0, "verdict": 0, "floor": 0, "bad_risk": 0}
    for x in CANDS:
        t = x["t"]
        if t < busy:
            continue
        if not eval(filt, {}, x):
            rej["filter"] += 1
            continue
        entry, pull, atr5, buy = x["entry"], x["pull"], x["atr5"], x["buy"]
        stop = min(pull - b * atr5, entry - n * atr5) if buy else max(pull + b * atr5, entry + n * atr5)
        risk = abs(entry - stop)
        if risk <= 0:
            rej["bad_risk"] += 1
            continue
        reach = c * x["atr1d"]
        best = None
        for p in x["levels"]:
            dist = (p - entry) if buy else (entry - p)
            if dist <= 0 or dist < 3.0 * risk or dist > reach:
                continue
            if best is None or dist < best[1]:
                best = (p, dist)
        if best is None:
            rej["no_target"] += 1
            continue
        target = best[0]
        spread = K_PROP * entry if prop else SPREAD
        net = (abs(target - entry) - spread) / (risk + spread)
        if verdict and net + 1e-9 < 3.0:
            rej["verdict"] += 1
            continue
        bps = risk / entry * 1e4
        if bps + 1e-9 < floor:
            rej["floor"] += 1
            continue
        k1 = bisect.bisect_right(R.t1, t - 60)
        key = (k1, entry, stop, target, buy, spread)
        if key not in _cache:
            _cache[key] = thirds(entry, stop, target, buy, k1, spread)
        r, exit_t, stage = _cache[key]
        if r is None:
            break
        trades.append({"t": t, "exit": exit_t, "r": r, "win": x["win"], "buy": buy, "bps": bps,
                       "entry": entry, "stop": stop, "target": target, "risk": risk,
                       "rr": abs(target - entry) / risk, "net": net, "cost_r": spread / risk, "stage": stage,
                       "year": x["year"], "above50": x.get("above50"), "above200": x.get("above200"),
                       "volhi": x.get("volhi"), "volratio": x.get("volratio"),
                       "atr5_bps": atr5 / entry * 1e4, "reach_r": reach / risk, "j": x["j"]})
        busy = exit_t + 60
    return trades, rej


CFGS = json.load(open(CFG_PATH, encoding="utf-8"))
OUT = {"الفترة": {"البداية": fmt(R.START), "النهاية_حصريّة": fmt(R.END)}, "P_REF": P_REF,
       "مرشّحات": len(CANDS), "مرشّحات_بلا_نظام": sum(1 for x in CANDS if "above50" not in x), "عيارات": {}}
for cfg in CFGS:
    tr, rej = run(cfg)
    OUT["عيارات"][cfg["name"]] = {"cfg": cfg, "رفض": rej, "trades": tr}
    rs = [x["r"] for x in tr]
    gp = sum(r for r in rs if r > 0); gl = -sum(r for r in rs if r < 0)
    print("%-40s n=%4d R=%7.1f R/ص=%7.3f معامل=%s · %s · %.0f ث" % (
        cfg["name"], len(rs), sum(rs), sum(rs) / len(rs) if rs else 0, round(gp / gl, 2) if gl else None, rej,
        time.time() - T0), flush=True)

# ───────── التحقّق مقابل المرجع ─────────
if REF_PATH:
    ref = json.load(open(REF_PATH, encoding="utf-8"))[REF_KEY]
    mine = OUT["عيارات"]["تحقّق_المرجع"]["trades"]
    a = [(x[0], x[1], x[2], x[3], x[4], x[5]) for x in ref]
    b_ = [(x["t"], x["exit"], round(x["r"], 5), x["win"], x["buy"], round(x["bps"], 3)) for x in mine]
    same = a == b_
    diff = [(p, q) for p, q in zip(a, b_) if p != q][:5]
    # كلّ صفقة تُعاد بالقلب المشترك نفسه
    bad = 0
    for x in mine:
        j, t = x["j"], x["t"]
        idd = R.closed_index(R.td1, 86400, t)
        peers = {"US500": (FC.peer_fact(REF["US500"][0], 3600, t), FC.peer_fact(REF["US500"][1], 14400, t))}
        card = CT.evaluate(at=t, close=R.m5[j][4], prev_close=R.m5[j - 1][4],
                           trend_1h=S.fact_trend(R.h1, R.e_h1, R.th1, 3600, t),
                           trend_4h=S.fact_trend(R.h4, R.e_h4, R.th4, 14400, t),
                           atr_5m=R.a5[j], atr_1d=R.ad1[idd], ladder=S.ladder_at(t, S.frames),
                           window=owner_window(t), news_blocked=R.news_block(t), peers=peers)
        bad += not (card["status"] == CT.OPEN and card["stop"] == x["stop"] and card["target"] == x["target"])
        r2, e2 = R.thirds(card["entry"], card["stop"], card["target"], x["buy"], bisect.bisect_right(R.t1, t - 60))
        bad += not (r2 == x["r"] and e2 == x["exit"])
    OUT["تحقّق"] = {"المرجع_n": len(a), "المحرّك_n": len(b_), "مطابق_حرفًا": same, "أوّل_فروق": diff,
                    "صفقات_لا_يعيدها_القلب_المشترك": bad}
    print("تحقّق: %s" % OUT["تحقّق"], flush=True)

json.dump(OUT, open(OUT_PATH, "w", encoding="utf-8"), ensure_ascii=False)
print("تمّ %.0f ث" % (time.time() - T0), flush=True)
