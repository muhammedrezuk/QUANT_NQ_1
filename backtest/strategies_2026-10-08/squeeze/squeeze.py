# -*- coding: utf-8 -*-
"""استراتيجيّة «التذبذب»: انضغاطٌ ثمّ انفجار — قياسٌ فقط بمسطرة البطاقة 414 (لا يُكتب شيءٌ في المشروع).

التعريف (القرار عند إغلاق شمعة 5 د j، t_close = m5[j][0] + 300، ولا يُستعمل إلّا ما أُغلق حتّى t_close):
  الصندوق   : الشموع j−m … j−1 (م شمعة متّصلة بلا فجوة) — أعلى قمّة وأدنى قاع.
  الانضغاط  : ق رقم ⟸ مدى الصندوق ≤ ق × مدى اليوم 14 (آخر يومٍ مغلق).
              ق = «ربع» ⟸ متوسّط مدى 5 د للشمعة j−1 ≤ الربع الأدنى لقيمه في نفس دقيقة اليوم على آخر 20 يومًا
              ماضيًا (≥ 10 قيم) — توزيعٌ متدحرج من الماضي وحده.
  الانفجار  : إغلاق الشمعة j فوق قمّة الصندوق ⟸ شراء، أو تحت قاعه ⟸ بيع (أوّل إغلاقٍ خارج الصندوق بالبناء،
              فكلّ إغلاقات الصندوق داخله).
  السياق    : «أيّ» أو «اتّفاق» (إغلاق الساعة والأربع ساعات المغلقتين في جهة الانفجار مقابل متوسّط 20 — كـ414).
  الوقف     : «مقابل» = الطرف المقابل من الصندوق · «منتصف» = منتصف الصندوق (ب = 0 كـ414)،
              وأبعد من ن × مدى 5 د من الإغلاق (ن = 2 كـ414). وقفٌ < 3 نقاط أساس ⟸ لا دخول (كحكم الإرسال 555).
  الهدف     : أقرب مستوى حقيقيّ في الجهة (قمّة/قاع مؤكَّد ساعة أو 4 س حتّى t_close، أو قمّة/قاع اليوم السابق المغلق)
              بنسبةٍ صافية (المسافة − 1.5) ÷ (الخطر + 1.5) ≥ 3، وفي المتناول ≤ ج × مدى اليوم.
  الوقت     : نوافذ المالك owner_window · منع الخبر ±15 د · مركزٌ واحد (busy = exit_t + 60).
  الإدارة   : R.thirds من أوّل دقيقة بعد الإغلاق (كلفة 1.5).
"""
import sys

sys.dont_write_bytecode = True
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, r"C:\Users\NQ\QUANT_NQ")
sys.path.insert(0, r"C:\Users\NQ\QUANT_NQ\backtest\card_414")

import bisect
import itertools
import json
import os
import time
from collections import Counter, defaultdict, deque
from datetime import datetime, timezone

T_START = time.time()
import card_replay as R
import card_replay_shared as S
from shared import card_trend as CT
from shared.owner_windows import owner_window

OUT = os.path.dirname(os.path.abspath(__file__))
N_NOISE = 2.0          # ن: الوقف لا يقلّ عن ضعفَي متوسّط مدى 5 د (عيار 414)
MIN_BPS = 3.0          # أدنى وقف للناسداك (ختم المالك ٢٠٢٦-١٠-٠٦)
NET_MIN = 3.0          # النسبة الصافية بعد السبريد
SPREAD = R.COST        # 1.5 نقطة
LOOKBACK_DAYS, MIN_HIST = 20, 10

m5 = R.m5
N5 = len(m5)
print("تحميل البيانات: %.0f ث" % (time.time() - T_START), flush=True)

# ── الصناديق (الشموع j−m … j−1، متّصلة) ──
BOX = {}
for m in (6, 12):
    bh, bl, okc = [0.0] * N5, [0.0] * N5, [False] * N5
    for j in range(m, N5):
        if m5[j][0] - m5[j - m][0] != m * 300:
            continue
        seg = m5[j - m:j]
        bh[j] = max(r[2] for r in seg)
        bl[j] = min(r[3] for r in seg)
        okc[j] = True
    BOX[m] = (bh, bl, okc)

# ── الربع الأدنى المتدحرج لمتوسّط مدى 5 د في نفس دقيقة اليوم (الماضي وحده) ──
LOWQ = [False] * N5
_hist = defaultdict(lambda: deque(maxlen=LOOKBACK_DAYS))
for i in range(N5):
    hq = _hist[int(m5[i][0]) % 86400]
    if len(hq) >= MIN_HIST:
        srt = sorted(hq)
        LOWQ[i] = R.a5[i] <= srt[(len(srt) - 1) // 4]
    hq.append(R.a5[i])

# ── حقائق كلّ إغلاق (مرّةً واحدة) ──
J0 = next(j for j in range(N5) if m5[j][0] + 300 >= R.START)
WIN, NEWS, IDD, DIR = [None] * N5, [False] * N5, [-1] * N5, [0] * N5
for j in range(J0, N5):
    tc = m5[j][0] + 300
    WIN[j] = owner_window(tc)
    NEWS[j] = R.news_block(tc)
    IDD[j] = R.closed_index(R.td1, 86400, tc)
    DIR[j] = CT.direction_of(S.fact_trend(R.h1, R.e_h1, R.th1, 3600, tc),
                             S.fact_trend(R.h4, R.e_h4, R.th4, 14400, tc))
print("الحقائق: %.0f ث" % (time.time() - T_START), flush=True)

_LV = {}


def levels(j, buy):
    """مستويات الهدف الحقيقيّة حتّى t_close: قمم/قيعان الساعة والأربع ساعات المؤكَّدة + قمّة/قاع اليوم السابق."""
    key = (j, buy)
    if key not in _LV:
        tc = m5[j][0] + 300
        lad = S.ladder_at(tc, S.frames)
        side = "highs" if buy else "lows"
        lv = [(p, ts, "1h") for p, ts in lad["1h"][side]] + [(p, ts, "4h") for p, ts in lad["4h"][side]]
        idd = IDD[j]
        if idd >= 0:
            lv.append((R.d1[idd][2] if buy else R.d1[idd][3], R.td1[idd] + 86400, "يوم_سابق"))
        _LV[key] = lv
    return _LV[key]


def run(m, q, stop_mode, ctx, c, windows=True, detail=False):
    trades, busy, tally = [], 0.0, Counter()
    bh, bl, okc = BOX[m]
    for j in range(max(J0, m), N5):
        t_close = m5[j][0] + 300
        win = WIN[j]
        if windows and not win:
            continue
        if NEWS[j] or not okc[j]:
            continue
        cl = m5[j][4]
        hi, lo = bh[j], bl[j]
        if cl > hi:
            buy = True
        elif cl < lo:
            buy = False
        else:
            continue
        idd = IDD[j]
        adr = R.ad1[idd] if idd >= 0 else None
        if not adr or adr <= 0:
            tally["بلا_مدى_يوم"] += 1
            continue
        if q == "ربع":
            if not LOWQ[j - 1]:
                continue
        elif hi - lo > q * adr:
            continue
        if ctx == "اتّفاق" and DIR[j] != (1 if buy else -1):
            tally["سياق_مخالف"] += 1
            continue
        tally["انفجار"] += 1
        if t_close < busy:
            tally["مشغول"] += 1
            continue
        a5 = R.a5[j]
        struct = (lo if buy else hi) if stop_mode == "مقابل" else (hi + lo) / 2.0
        stop = min(struct, cl - N_NOISE * a5) if buy else max(struct, cl + N_NOISE * a5)
        risk = abs(cl - stop)
        if risk <= 0:
            tally["خطر_غير_موجب"] += 1
            continue
        bps = risk / cl * 1e4
        if bps < MIN_BPS:
            tally["وقف<3ن.أ"] += 1
            continue
        lv = levels(j, buy)
        target = CT.nearest_target(lv, buy, cl, risk, c * adr, t_close, rr=NET_MIN + 4.0 * SPREAD / risk)
        if target is None:
            tally["بلا_هدف"] += 1
            continue
        net = (abs(target - cl) - SPREAD) / (risk + SPREAD)
        assert net >= NET_MIN - 1e-9 and abs(target - cl) <= c * adr + 1e-9
        k1 = bisect.bisect_right(R.t1, t_close - 60)
        r, exit_t = R.thirds(cl, stop, target, buy, k1)
        if r is None:
            tally["نهاية_البيانات"] += 1
            break
        tally["صفقة"] += 1
        row = (t_close, r, win or "خارج", buy, bps, exit_t)
        if detail:
            src = next(x for x in lv if x[0] == target and x[1] <= t_close)
            row = row + ({"j": j, "entry": cl, "stop": stop, "target": target, "box_hi": hi, "box_lo": lo,
                          "box_last_close_t": m5[j - 1][0] + 300, "box_first_t": m5[j - m][0],
                          "target_src": src[2], "target_confirm_t": src[1],
                          "adr_day_close_t": R.td1[idd] + 86400, "net": net, "adr": adr, "a5": a5},)
        trades.append(row)
        busy = exit_t + 60
    return trades, tally


SPLIT = R.START + 0.7 * (R.END - R.START)
WEEKDAYS = sum(1 for d in range(int(R.START // 86400), int(R.END // 86400) + 1)
               if datetime.fromtimestamp(d * 86400, timezone.utc).weekday() < 5)
WD_LEARN = sum(1 for d in range(int(R.START // 86400), int(SPLIT // 86400) + 1)
               if datetime.fromtimestamp(d * 86400, timezone.utc).weekday() < 5)
WD_TEST = WEEKDAYS - WD_LEARN


def pack(tr):
    return {"تعلّم": R.stats([x for x in tr if x[0] < SPLIT]), "اختبار": R.stats([x for x in tr if x[0] >= SPLIT]),
            "كلّه": R.stats(tr), "لندن": R.stats([x for x in tr if x[2] == "london_peak"]),
            "نيويورك": R.stats([x for x in tr if x[2] == "ny_open"])}


def mean(xs):
    return sum(xs) / len(xs) if xs else float("-inf")


def owner_pass(s):
    T, A = s["اختبار"], s["كلّه"]
    halves = A.get("أنصاف") or {}
    pos = sum(1 for v in halves.values() if v > 0)
    checks = {"اختبار_R/صفقة>0": (T.get("R/صفقة") or -1) > 0,
              "اختبار_معامل≥1.15": (T.get("معامل") or 0) >= 1.15,
              "اختبار_n≥30": T.get("n", 0) >= 30,
              "أنصاف_موجبة≥4من5": pos >= 4 and len(halves) >= 5}
    return {"شروط": checks, "أنصاف_موجبة": "%d/%d" % (pos, len(halves)), "يجتاز": all(checks.values())}


if __name__ == "__main__":
    # ق: تشخيص التعلّم وحده (diag_box) أظهر أنّ 0.25 تشمل 64–79٪ من كلّ إغلاقات النوافذ — ليست انضغاطًا؛
    # فالشبكة {0.10 · 0.15 · ربع متدحرج}، و0.25 تُقاس ضابطًا للعلم (انفجارٌ بلا انضغاطٍ تقريبًا) ولا تدخل الاختيار.
    grid = list(itertools.product((6, 12), (0.10, 0.15, "ربع"), ("مقابل", "منتصف"), ("أيّ", "اتّفاق"), (1.0, 1.5)))
    control = list(itertools.product((6, 12), (0.25,), ("مقابل", "منتصف"), ("أيّ", "اتّفاق"), (1.0, 1.5)))
    if len(sys.argv) > 1 and sys.argv[1] == "smoke":
        grid, control = grid[:2], []
    assert len(grid) <= 48
    rows, best, best_key = [], None, None
    for g in grid + control:
        m, q, sm, ctx, c = g
        tr, tally = run(m, q, sm, ctx, c)
        s = pack(tr)
        learn_mean = mean([x[1] for x in tr if x[0] < SPLIT])
        n_learn = s["تعلّم"].get("n", 0)
        in_grid = g in grid
        row = {"م": m, "ق": q, "الوقف": sm, "السياق": ctx, "ج": c, "في_الشبكة": in_grid, **s, "عدّاد": dict(tally),
               "صفقات/يوم": round(len(tr) / WEEKDAYS, 3), "معيار_المالك": owner_pass(s)}
        rows.append(row)
        if in_grid and n_learn >= 60 and (best is None or learn_mean > best_key):
            best, best_key = g, learn_mean
        L, T, A = s["تعلّم"], s["اختبار"], s["كلّه"]
        print("م=%2d ق=%-4s وقف=%-5s سياق=%-6s ج=%.1f | تعلّم n=%s R/ص=%s | اختبار n=%s R/ص=%s معامل=%s | كلّه n=%s R=%s سحب=%s أنصاف=%s | %.0f ث" % (
            m, q, sm, ctx, c, L.get("n"), L.get("R/صفقة"), T.get("n"), T.get("R/صفقة"), T.get("معامل"),
            A.get("n"), A.get("R"), A.get("سحب_R"), A.get("أنصاف"), time.time() - T_START), flush=True)

    out = {"تعريف": __doc__, "ثوابت": {"ن": N_NOISE, "ب": 0.0, "أدنى_وقف_ن.أ": MIN_BPS, "صافي≥": NET_MIN,
                                      "سبريد": SPREAD, "ربع_متدحرج": "%d يومًا/≥%d" % (LOOKBACK_DAYS, MIN_HIST)},
           "حدّ_التعلّم": datetime.fromtimestamp(SPLIT, timezone.utc).isoformat(),
           "البداية": datetime.fromtimestamp(R.START, timezone.utc).isoformat(),
           "النهاية": datetime.fromtimestamp(R.END, timezone.utc).isoformat(),
           "أيّام_عمل": {"كلّه": WEEKDAYS, "تعلّم": WD_LEARN, "اختبار": WD_TEST}, "التركيبات": rows}
    tests = [r["اختبار"].get("R/صفقة") for r in rows if r["في_الشبكة"] and r["اختبار"].get("n", 0) >= 10]
    out["ثبات_الشبكة"] = {"تركيبات_باختبار≥10": len(tests), "اختبار_موجب": sum(1 for v in tests if v > 0),
                          "وسيط_اختبار_R/صفقة": sorted(tests)[len(tests) // 2] if tests else None}
    if best is not None:
        m, q, sm, ctx, c = best
        tr, tally = run(m, q, sm, ctx, c, detail=True)
        # تدقيق التسريب على كلّ صفقة
        for x in tr:
            d = x[6]
            assert d["box_last_close_t"] <= x[0] - 0 and d["box_last_close_t"] == m5[d["j"]][0]
            assert d["target_confirm_t"] <= x[0] and d["adr_day_close_t"] <= x[0]
            assert x[5] >= x[0]
        s = pack(tr)
        sel = {"م": m, "ق": q, "الوقف": sm, "السياق": ctx, "ج": c, **s, "عدّاد": dict(tally),
               "صفقات/يوم": round(len(tr) / WEEKDAYS, 3),
               "صفقات/يوم_تعلّم": round(s["تعلّم"].get("n", 0) / WD_LEARN, 3),
               "صفقات/يوم_اختبار": round(s["اختبار"].get("n", 0) / WD_TEST, 3),
               "معيار_المالك": owner_pass(s),
               "شراء": R.stats([x for x in tr if x[3]]), "بيع": R.stats([x for x in tr if not x[3]]),
               "مصدر_الهدف": dict(Counter(x[6]["target_src"] for x in tr)),
               "مدّة_الصفقة_د_وسيط": sorted((x[5] - x[0]) / 60 for x in tr)[len(tr) // 2]}
        out["المختارة"] = sel
        json.dump([[x[0], x[5], round(x[1], 5), x[2], x[3], round(x[4], 3)] for x in tr],
                  open(os.path.join(OUT, "trades_best.json"), "w", encoding="utf-8"), ensure_ascii=False)
        json.dump([{**x[6], "t_close": x[0], "exit_t": x[5], "r": x[1], "window": x[2], "buy": x[3]} for x in tr],
                  open(os.path.join(OUT, "trades_best_detail.json"), "w", encoding="utf-8"), ensure_ascii=False)
        # للعلم فقط: نفس المختارة على كلّ ساعات التداول بلا نوافذ (منع الخبر باقٍ)
        tra, tallya = run(m, q, sm, ctx, c, windows=False)
        sa = pack(tra)
        sa["خارج_النوافذ"] = R.stats([x for x in tra if x[2] == "خارج"])
        sa["عدّاد"] = dict(tallya)
        sa["صفقات/يوم"] = round(len(tra) / WEEKDAYS, 3)
        out["كلّ_الساعات_للعلم"] = sa
        json.dump([[x[0], x[5], round(x[1], 5), x[2], x[3], round(x[4], 3)] for x in tra],
                  open(os.path.join(OUT, "trades_best_allhours.json"), "w", encoding="utf-8"), ensure_ascii=False)
        print("المختارة:", json.dumps({k: sel[k] for k in ("م", "ق", "الوقف", "السياق", "ج", "تعلّم", "اختبار", "كلّه",
                                                         "معيار_المالك", "صفقات/يوم")}, ensure_ascii=False), flush=True)
        print("كلّ الساعات:", json.dumps({k: sa[k] for k in ("تعلّم", "اختبار", "كلّه", "خارج_النوافذ")},
                                         ensure_ascii=False), flush=True)
    else:
        print("لا تركيبة بـ≥ 60 صفقة تعلّم", flush=True)
    name = "results_smoke.json" if len(sys.argv) > 1 and sys.argv[1] == "smoke" else "results.json"
    json.dump(out, open(os.path.join(OUT, name), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("انتهى: %.0f ث" % (time.time() - T_START), flush=True)
