# -*- coding: utf-8 -*-
"""الاستراتيجيّة الثانية للقياس: «الاختراق ثمّ إعادة الاختبار» على الناسداك — سنتان، بأثلاث المالك.
  الجهة والنافذة والخبر: كالبطاقة 414 (الطبقات الثقيلة نفسها).
  الاختراق : إغلاق 5 د خلف آخر قمّة ساعةٍ مؤكَّدة (للشراء) والإغلاق الذي قبله دونها.
  الإعادة  : خلال W شمعة بعده: قاع شمعةٍ ≤ المستوى + k×مدى5 وإغلاقها ≥ المستوى − k×مدى5 (صمد).
  الزناد   : إغلاقٌ فوق قمّة آخر شمعة إعادة.
  الوقف    : أبعد من (أدنى قاعٍ منذ الإعادة) ومن (الدخول − n×مدى5).  الهدف كـ414 (≥3R، في المتناول).
"""
import bisect
import itertools
import json
import sys

sys.path.insert(0, r"C:\Users\NQ\QUANT_NQ")
import card_replay as R
import card_replay_shared as S
from shared import card_trend as CT
from shared.owner_windows import owner_window

sw1_hi = [(ts, p) for ts, p, h in S.sw1 if h]; sw1_hi_t = [x[0] for x in sw1_hi]
sw1_lo = [(ts, p) for ts, p, h in S.sw1 if not h]; sw1_lo_t = [x[0] for x in sw1_lo]


def last_level(buy, t):
    rows, times = (sw1_hi, sw1_hi_t) if buy else (sw1_lo, sw1_lo_t)
    k = bisect.bisect_left(times, t) - 1
    return rows[k][1] if k >= 0 else None


def run(W=12, k=0.5, n=2.0, c=1.5):
    trades, busy, pend = [], 0.0, None
    for j in range(1, len(R.m5)):
        t0, o, h, lo, cl = R.m5[j]
        t_close = t0 + 300
        if t_close < R.START:
            continue
        a5 = R.a5[j]
        d = CT.direction_of(S.fact_trend(R.h1, R.e_h1, R.th1, 3600, t_close),
                            S.fact_trend(R.h4, R.e_h4, R.th4, 14400, t_close))
        if d == 0:
            pend = None
            continue
        buy = d > 0
        prev = R.m5[j - 1][4]
        if pend and (pend["buy"] != buy or j - pend["j"] > W):
            pend = None
        if pend is None:
            lvl = last_level(buy, t_close)
            if lvl is not None and ((prev <= lvl < cl) if buy else (prev >= lvl > cl)):
                pend = {"buy": buy, "lvl": lvl, "j": j, "retest": False, "ext": None, "trig": None}
            continue
        L = pend["lvl"]
        touched = (lo <= L + k * a5 and cl >= L - k * a5) if buy else (h >= L - k * a5 and cl <= L + k * a5)
        if touched:
            pend["retest"] = True
            if buy:
                pend["ext"] = lo if pend["ext"] is None else min(pend["ext"], lo)
            else:
                pend["ext"] = h if pend["ext"] is None else max(pend["ext"], h)
            pend["trig"] = h if buy else lo
            continue
        if not pend["retest"]:
            continue
        fire = (cl > pend["trig"]) if buy else (cl < pend["trig"])
        if not fire or t_close < busy:
            continue
        if not owner_window(t_close) or R.news_block(t_close):
            continue
        entry = cl
        stop = min(pend["ext"], entry - n * a5) if buy else max(pend["ext"], entry + n * a5)
        risk = abs(entry - stop)
        idd = R.closed_index(R.td1, 86400, t_close)
        reach = c * R.ad1[idd] if idd >= 0 else None
        lad = S.ladder_at(t_close, S.frames)
        levels = (lad["1h"]["highs" if buy else "lows"] + lad["4h"]["highs" if buy else "lows"])
        target = CT.nearest_target(levels, buy, entry, risk, reach, t_close)
        pend = None
        if risk <= 0 or target is None:
            continue
        kk = bisect.bisect_right(R.t1, t_close - 60)
        r, exit_t = R.thirds(entry, stop, target, buy, kk)
        if r is None:
            break
        trades.append((t_close, r, owner_window(t_close), buy, risk / entry * 1e4))
        busy = exit_t + 60
    return trades


if __name__ == "__main__":
    split = R.START + 0.7 * (R.END - R.START)
    rows = []
    for W, k, n in itertools.product((6, 12, 24), (0.25, 0.5, 1.0), (1.5, 2.0)):
        tr = run(W, k, n)
        L = R.stats([x for x in tr if x[0] < split]); T = R.stats([x for x in tr if x[0] >= split]); A = R.stats(tr)
        rows.append({"W": W, "k": k, "n": n, "تعلّم": L, "اختبار": T, "كلّه": A})
        print("W=%2d k=%.2f n=%.1f | كلّه n=%s R=%s R/ص=%s أنصاف=%s | تعلّم R/ص=%s | اختبار n=%s R/ص=%s معامل=%s" % (
            W, k, n, A.get("n"), A.get("R"), A.get("R/صفقة"), A.get("أنصاف"), L.get("R/صفقة"), T.get("n"),
            T.get("R/صفقة"), T.get("معامل")), flush=True)
    json.dump(rows, open("card_breakout.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
