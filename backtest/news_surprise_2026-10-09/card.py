# -*- coding: utf-8 -*-
"""(ب) بطاقة «بعد الخبر» بمسطرة 414 — قياسٌ فقط. التعريف الكامل في «التصميم.md».

  python card.py 2y                      ⟵ الشبكة (48) على السنتين + الاختيار على التعلّم + الدمج مع 414 ⟵ results_b_2y.json
  python card.py old 2014-08-01 2016-07-31 ⟵ كلّ الشبكة على قطعةٍ من الفترة الأقدم بنسخة المسطرة ذات البداية والنهاية
                                            (strategies_2026-10-08/unseen/card_replay.py) ⟵ old_<البداية>.json

القرار عند إغلاق شمعة 5 د (t_close)، ولا يُستعمل إلّا ما أُغلق حتّى t_close:
  الإصدار T مؤهَّل إن كانت |z| لفئةٍ مختارة ≥ ك (z من الماضي وحده — events.py).
  الجهة: «حركة» = إشارة (إغلاق T+15 − إغلاق الدقيقة قبل T) · «مفاجأة» = إشارة Σ جهة_الفئة × z للفئات المؤهَّلة
         (جهة الفئة متعلَّمة على التعلّم وحده — results_a.json).
  النطاق: أعلى/أدنى شموع 5 د الثلاث [T, T+15). الزناد: أوّل إغلاق 5 د خارج النطاق (شمعةٌ تبدأ ≥ T+15 وتُغلق ≤ T+و):
         في الجهة ⟸ دخول عند إغلاقها؛ في عكسها ⟸ لا صفقة لهذا الخبر.
  الوقف: الطرف المقابل للنطاق (< 3 ن.أ ⟸ لا دخول). منع خبرٍ أمريكيّ عالٍ آخر ±15 د عند الزناد (R.news_block).
  الهدف: أقرب قمّة/قاع ساعة أو 4 س مؤكَّد حتّى t_close بنسبة صافية ≥ 3 بعد سبريد 1.5 وفي متناول ج × مدى اليوم 14.
  الإدارة: R.thirds (أثلاث المالك، كلفة 1.5) من أوّل دقيقة بعد الإغلاق · مركزٌ واحد · صفقةٌ واحدة لكلّ خبر.
"""
import sys

sys.dont_write_bytecode = True
sys.stdout.reconfigure(encoding="utf-8")
import os

MODE = sys.argv[1] if len(sys.argv) > 1 else "2y"
if MODE == "old":
    os.environ["UNSEEN_START"], os.environ["UNSEEN_END"] = sys.argv[2], sys.argv[3]
    RULER = r"C:\Users\NQ\QUANT_NQ\backtest\strategies_2026-10-08\unseen"
else:
    RULER = r"C:\Users\NQ\QUANT_NQ\backtest\card_414"
sys.path.insert(0, r"C:\Users\NQ\QUANT_NQ")
sys.path.insert(0, RULER)

import bisect
import itertools
import json
import time
from collections import Counter
from datetime import datetime, timezone

T_START = time.time()
import card_replay as R
import card_replay_shared as S
from shared import card_trend as CT

assert os.path.dirname(os.path.abspath(R.__file__)).lower() == RULER.lower(), R.__file__
HERE = os.path.dirname(os.path.abspath(__file__))
SPREAD = R.COST
NET_MIN = 3.0
MIN_BPS = 3.0
ALL = ("تضخّم", "وظائف", "مطالبات", "تجزئة", "منتجين", "ناتج", "نفقات", "مصانع", "خدمات", "فائدة")
INF_JOBS = ("تضخّم", "وظائف")
CATSETS = {"كلّها": ALL, "تضخّم_وظائف": INF_JOBS}
GRID = list(itertools.product((0.5, 1.0, 1.5), ("حركة", "مفاجأة"), ("كلّها", "تضخّم_وظائف"), (1.0, 1.5), (60, 180)))
assert len(GRID) <= 48

EV = json.load(open(os.path.join(HERE, "events.json"), encoding="utf-8"))
LEARNED = json.load(open(os.path.join(HERE, "results_a.json"), encoding="utf-8"))["الجهات_المتعلَّمة"]
SRC = "أقدم" if MODE == "old" else "سنتان"
CLUSTERS = [c for c in EV["clusters"] if c["src"] == SRC and R.START <= c["T"] < R.END and c["cats"]]
print("المسطرة: %s · %s ⟶ %s · إصدارات بـz: %d · %.0f ث" % (
    R.__file__, datetime.fromtimestamp(R.START, timezone.utc).date(), datetime.fromtimestamp(R.END, timezone.utc).date(),
    len(CLUSTERS), time.time() - T_START), flush=True)


def simulate(k, dmode, catset, c, W, detail=False):
    cats_ok = CATSETS[catset]
    trades, busy, tally = [], 0.0, Counter()
    for cl in CLUSTERS:
        T = cl["T"]
        qual = {cat: z for cat, z in cl["cats"].items() if cat in cats_ok and abs(z) >= k}
        if not qual:
            continue
        tally["مؤهَّل"] += 1
        j0 = bisect.bisect_left(R.t5, T)
        if j0 + 3 >= len(R.m5) or R.m5[j0][0] != T or R.m5[j0 + 1][0] != T + 300 or R.m5[j0 + 2][0] != T + 600:
            tally["بلا_شموع_النطاق"] += 1
            continue
        hi15 = max(R.m5[j][2] for j in range(j0, j0 + 3))
        lo15 = min(R.m5[j][3] for j in range(j0, j0 + 3))
        k0 = bisect.bisect_right(R.t1, T - 60) - 1
        if k0 < 0 or R.t1[k0] < T - 60 - 300:
            tally["بلا_سعر_قبل"] += 1
            continue
        p0, p15 = R.m1[k0][4], R.m5[j0 + 2][4]
        if dmode == "حركة":
            d = (p15 > p0) - (p15 < p0)
        else:
            sc = sum(LEARNED[cat] * max(-4.0, min(4.0, z)) for cat, z in qual.items() if LEARNED.get(cat))
            d = (sc > 0) - (sc < 0)
        if d == 0:
            tally["بلا_جهة"] += 1
            continue
        j, side = j0 + 3, 0
        while j < len(R.m5) and R.m5[j][0] + 300 <= T + W * 60:
            x = R.m5[j][4]
            if x > hi15:
                side = 1
                break
            if x < lo15:
                side = -1
                break
            j += 1
        if side == 0:
            tally["بلا_كسر"] += 1
            continue
        if side != d:
            tally["كسر_معاكس"] += 1
            continue
        t_close = R.m5[j][0] + 300
        if t_close < busy:
            tally["مشغول"] += 1
            continue
        if R.news_block(t_close):
            tally["خبر_آخر±15"] += 1
            continue
        buy = side > 0
        entry = R.m5[j][4]
        stop = lo15 if buy else hi15
        risk = abs(entry - stop)
        bps = risk / entry * 1e4
        if risk <= 0 or bps < MIN_BPS:
            tally["وقف<3ن.أ"] += 1
            continue
        idd = R.closed_index(R.td1, 86400, t_close)
        adr = R.ad1[idd] if idd >= 0 else None
        if not adr or adr <= 0:
            tally["بلا_مدى_يوم"] += 1
            continue
        lad = S.ladder_at(t_close, S.frames)
        key = "highs" if buy else "lows"
        lv = [(p, ts, "1h") for p, ts in lad["1h"][key]] + [(p, ts, "4h") for p, ts in lad["4h"][key]]
        target = CT.nearest_target(lv, buy, entry, risk, c * adr, t_close, rr=NET_MIN + 4.0 * SPREAD / risk)
        if target is None:
            tally["بلا_هدف"] += 1
            continue
        net = (abs(target - entry) - SPREAD) / (risk + SPREAD)
        assert net >= NET_MIN - 1e-9 and abs(target - entry) <= c * adr + 1e-9
        k1 = bisect.bisect_right(R.t1, t_close - 60)
        r, exit_t = R.thirds(entry, stop, target, buy, k1)
        if r is None:
            tally["نهاية_البيانات"] += 1
            break
        tally["صفقة"] += 1
        label = "+".join(sorted(qual))
        row = (t_close, r, label, buy, bps, exit_t)
        if detail:
            src = next(x for x in lv if x[0] == target and x[1] <= t_close)
            row = row + ({"T": T, "z": qual, "first_move": (p15 > p0) - (p15 < p0), "hi15": hi15, "lo15": lo15,
                          "range_last_close_t": R.m5[j0 + 2][0] + 300, "entry": entry, "stop": stop, "target": target,
                          "target_src": src[2], "target_confirm_t": src[1], "adr_day_close_t": R.td1[idd] + 86400,
                          "net": round(net, 3), "adr": adr, "comps": cl["comps"]},)
        trades.append(row)
        busy = exit_t + 60
    return trades, tally


def compact(tr):
    return [[x[0], x[5], round(x[1], 5), x[2], x[3], round(x[4], 3)] for x in tr]


def months(a, b):
    return max(1e-9, (b - a) / (86400 * 30.4375))


def owner_pass(test, whole):
    halves = whole.get("أنصاف") or {}
    pos = sum(1 for v in halves.values() if v > 0)
    checks = {"R/صفقة>0": (test.get("R/صفقة") or -1) > 0, "معامل≥1.15": (test.get("معامل") or 0) >= 1.15,
              "أنصاف_موجبة≥نصفها": len(halves) > 0 and pos * 2 >= len(halves)}
    return {"شروط": checks, "أنصاف_موجبة": "%d/%d" % (pos, len(halves)), "يجتاز": all(checks.values()),
            "عدد_الاختبار": test.get("n", 0), "عدد_كافٍ(≥20)": test.get("n", 0) >= 20}


def run_2y():
    split = R.START + 0.7 * (R.END - R.START)
    rows, best, best_key, fallback, fb_key = [], None, None, None, None
    for g in GRID:
        tr, tally = simulate(*g)
        L = [x for x in tr if x[0] < split]
        Tt = [x for x in tr if x[0] >= split]
        sL, sT, sA = R.stats(L), R.stats(Tt), R.stats(tr)
        rows.append({"ك": g[0], "الجهة": g[1], "الفئات": g[2], "ج": g[3], "و_د": g[4], "تعلّم": sL, "اختبار": sT,
                     "كلّه": sA, "عدّاد": dict(tally), "صفقات/شهر": round(len(tr) / months(R.START, R.END), 2)})
        lm = sL.get("R/صفقة")
        if sL.get("n", 0) >= 20 and (best is None or lm > best_key):
            best, best_key = g, lm
        if sL.get("n", 0) >= 10 and (fallback is None or lm > fb_key):
            fallback, fb_key = g, lm
        print("ك=%.1f %-6s %-11s ج=%.1f و=%3d | تعلّم n=%s R/ص=%s | اختبار n=%s R/ص=%s معامل=%s | كلّه n=%s R=%s سحب=%s | %.0f ث" % (
            g[0], g[1], g[2], g[3], g[4], sL.get("n"), lm, sT.get("n"), sT.get("R/صفقة"), sT.get("معامل"),
            sA.get("n"), sA.get("R"), sA.get("سحب_R"), time.time() - T_START), flush=True)
    out = {"تعريف": __doc__, "حدّ_التعلّم": datetime.fromtimestamp(split, timezone.utc).isoformat(),
           "البداية": datetime.fromtimestamp(R.START, timezone.utc).isoformat(),
           "النهاية": datetime.fromtimestamp(R.END, timezone.utc).isoformat(),
           "الجهات_المتعلَّمة": LEARNED, "إصدارات_بـz": len(CLUSTERS), "التركيبات": rows}
    tests = [r["اختبار"].get("R/صفقة") for r in rows if r["اختبار"].get("n", 0) >= 5]
    out["ثبات_الشبكة"] = {"تركيبات_باختبار≥5": len(tests), "اختبار_موجب": sum(1 for v in tests if v > 0),
                          "وسيط_اختبار_R/صفقة": sorted(tests)[len(tests) // 2] if tests else None}
    flag = None
    if best is None and fallback is not None:
        best, flag = fallback, "عددٌ غير كافٍ: لا تركيبة بـ≥ 20 صفقة تعلّم — اختيرت الأعلى بـ≥ 10"
    if best is None:
        out["المختارة"] = None
        print("لا تركيبة بعددٍ كافٍ", flush=True)
        return out
    tr, tally = simulate(*best, detail=True)
    for x in tr:     # تدقيق التسريب على كلّ صفقة
        d = x[6]
        assert x[0] >= d["T"] + 1200 and d["range_last_close_t"] == d["T"] + 900 <= x[0]
        assert d["target_confirm_t"] <= x[0] and d["adr_day_close_t"] <= x[0] and x[5] >= x[0]
    L = [x for x in tr if x[0] < split]
    Tt = [x for x in tr if x[0] >= split]
    sA, sT = R.stats(tr), R.stats(Tt)
    by_cat = {}
    for cat in ALL:
        sub = [x for x in tr if cat in x[2].split("+")]
        if sub:
            by_cat[cat] = R.stats(sub)
    sel = {"ك": best[0], "الجهة": best[1], "الفئات": best[2], "ج": best[3], "و_د": best[4], "وسم": flag,
           "تعلّم": R.stats(L), "اختبار": sT, "كلّه": sA, "عدّاد": dict(tally),
           "صفقات/شهر": round(len(tr) / months(R.START, R.END), 2),
           "صفقات/شهر_اختبار": round(len(Tt) / months(split, R.END), 2),
           "معيار_المالك_على_الاختبار": owner_pass(sT, sA),
           "شراء": R.stats([x for x in tr if x[3]]), "بيع": R.stats([x for x in tr if not x[3]]),
           "حسب_الفئة": by_cat, "مصدر_الهدف": dict(Counter(x[6]["target_src"] for x in tr)),
           "الحركة_الأولى_=_جهة_الصفقة": sum(1 for x in tr if x[6]["first_move"] == (1 if x[3] else -1)),
           "مدّة_الصفقة_د_وسيط": round(sorted((x[5] - x[0]) / 60 for x in tr)[len(tr) // 2]) if tr else None}
    out["المختارة"] = sel
    json.dump(compact(tr), open(os.path.join(HERE, "trades_best.json"), "w", encoding="utf-8"), ensure_ascii=False)
    json.dump([{**x[6], "t_close": x[0], "exit_t": x[5], "r": x[1], "cats": x[2], "buy": x[3], "bps": x[4],
                "t_close_utc": datetime.fromtimestamp(x[0], timezone.utc).strftime("%Y-%m-%d %H:%M")} for x in tr],
              open(os.path.join(HERE, "trades_best_detail.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=0)
    print("المختارة:", json.dumps({k: sel[k] for k in ("ك", "الجهة", "الفئات", "ج", "و_د", "وسم", "تعلّم", "اختبار", "كلّه",
                                                     "معيار_المالك_على_الاختبار", "صفقات/شهر")}, ensure_ascii=False), flush=True)
    # ── الدمج مع 414 (الإس آند بي وحده) بمنطق combine.py ──
    sys.path.insert(0, r"C:\Users\NQ\QUANT_NQ\backtest\strategies_2026-10-08")
    import card_variants as V
    import combine as C
    CT.PEERS = ("US500",)
    for kname in [k for k in V.REF if k != "US500"]:
        V.REF.pop(kname)
    base = C.card414()
    merged = C.merge(base, compact(tr))
    days = (R.END - R.START) / 86400 * 5 / 7

    def summary(t5):
        return {"كلّه": R.stats(t5), "تعلّم": R.stats([x for x in t5 if x[0] < split]),
                "اختبار": R.stats([x for x in t5 if x[0] >= split]), "صفقات/يوم": round(len(t5) / days, 2)}
    out["الدمج"] = {"414 وحدها (الإس آند بي وحده)": summary([(t[0], t[2], t[3], t[4], t[5]) for t in base]),
                   "414 + الأخبار": {**summary(merged), "من الأخبار": sum(1 for x in merged if x[5] == 1),
                                     "أخبار حجبها مركز 414": len(tr) - sum(1 for x in merged if x[5] == 1)}}
    print("الدمج:", json.dumps(out["الدمج"], ensure_ascii=False), flush=True)
    return out


def run_old():
    res = {"البداية": os.environ["UNSEEN_START"], "النهاية": os.environ["UNSEEN_END"], "إصدارات_بـz": len(CLUSTERS),
           "التركيبات": []}
    for g in GRID:
        tr, tally = simulate(*g)
        res["التركيبات"].append({"g": list(g), "صفقات": compact(tr), "عدّاد": dict(tally)})
    json.dump(res, open(os.path.join(HERE, "old_%s.json" % os.environ["UNSEEN_START"]), "w", encoding="utf-8"),
              ensure_ascii=False)
    print("قطعة %s ⟶ %s: %d إصدار · %.0f ث" % (res["البداية"], res["النهاية"], len(CLUSTERS), time.time() - T_START),
          flush=True)


if __name__ == "__main__":
    if MODE == "old":
        run_old()
    else:
        out = run_2y()
        json.dump(out, open(os.path.join(HERE, "results_b_2y.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("انتهى: %.0f ث" % (time.time() - T_START), flush=True)
