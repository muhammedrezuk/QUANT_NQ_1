# -*- coding: utf-8 -*-
"""استراتيجيّة «الانعكاس» (فكرة 405 المؤرشفة) بطاقةً كاملة — قياسٌ فقط بمسطرة البطاقة 414، خارج المشروع.

التعريف (ثابت قبل المعايرة):
  القرار   : عند إغلاق شمعة 5 د (t_close)، ولا يُقرأ إلّا ما أُغلق حتّى t_close.
  الوقت    : نافذتا المالك (owner_window) · لا دخول ±15 د حول خبرٍ أمريكيّ عالٍ (R.news_block) · مركزٌ واحد.
  التمدّد  : (أ) «متوسّط»: z = (إغلاق 5 د − متوسّط 20 لآخر ساعة مغلقة) ÷ مدى اليوم 14 (آخر يومٍ مغلق)؛
               أعلى z لإغلاقات الشموع الستّ السابقة (30 د، قبل شمعة الزناد) ≥ ك ⟸ تمدّدٌ صاعد (وبالعكس ≤ −ك).
             (ب) «اليوم السابق»: (إغلاق − قمّة يوم الوسيط السابق) ÷ مدى اليوم ≥ ك' في الشموع الستّ السابقة
               (وللهبوط: (قاع اليوم السابق − الإغلاق) ÷ مدى اليوم ≥ ك').
  الزناد   : شمعة 5 د تُغلق دون قاع الشمعة السابقة بعد تمدّدٍ صاعد ⟸ بيع؛ وفوق قمّتها بعد تمدّدٍ هابط ⟸ شراء.
  السياق   : أيّ · «بلا اتّجاه» (الساعة والأربع ساعات مختلفتان) · «ضدّ اتّجاهٍ متّفق» (الإطاران متّفقان في جهة التمدّد).
  الوقف    : خلف طرف التمدّد: أعلى قمّة الشموع السبع الأخيرة (الستّ + الزناد) + ب×مدى5د (للبيع)،
             وأبعد من ن×مدى5د من الإغلاق. ووقفٌ أقلّ من 3 نقاط أساس يُردّ (لا يُوسَّع — لا وقف مخترَع).
  الهدف    : أقرب مستوى حقيقيّ نحو المتوسّط — قمّة أو قاع مؤكَّد على الساعة/الأربع ساعات (سلّم الحيّ S.ladder_at)
             أو قمّة/قاع يوم الوسيط السابق أو متوسّط 20 الساعة نفسه — بين الدخول والمتوسّط (لا يتجاوزه)،
             بنسبةٍ صافية (|ه−د| − 1.5) ÷ (الخطر + 1.5) ≥ 3، وفي المتناول ≤ 1.5 × مدى اليوم.
  الإدارة  : أثلاث المالك R.thirds من أوّل دقيقة بعد الإغلاق، بكلفة 1.5.
"""
import sys
sys.dont_write_bytecode = True          # لا __pycache__ داخل مجلّد المشروع

import bisect
import itertools
import json
import os
import time
from datetime import datetime, timezone, timedelta

sys.path.insert(0, r"C:\Users\NQ\QUANT_NQ")
sys.path.insert(0, r"C:\Users\NQ\QUANT_NQ\backtest\card_414")
T0 = time.time()
import card_replay as R                      # noqa: E402
import card_replay_shared as S               # noqa: E402
from shared.owner_windows import owner_window  # noqa: E402

OUT = os.path.dirname(os.path.abspath(__file__))
M = 6                 # ساق التمدّد: الشموع الستّ السابقة للزناد (30 د) — ثابت لا يُعايَر
C_REACH = 1.5         # المتناول كالبطاقة 414
RR_NET = 3.0
SPREAD = R.COST       # 1.5
MIN_STOP_BPS = 3.0
SPLIT = R.START + 0.7 * (R.END - R.START)

print("تحميل المسطرة: %.1f ث" % (time.time() - T0), flush=True)

# ───────────── حقائق كلّ شمعة 5 د (كلّها ممّا أُغلق حتّى إغلاقها) ─────────────
m5 = R.m5
N5 = len(m5)
tc = [r[0] + 300 for r in m5]
op = [r[1] for r in m5]; hi = [r[2] for r in m5]; lo = [r[3] for r in m5]; cl = [r[4] for r in m5]
ema = [None] * N5; adv = [None] * N5; pdh = [None] * N5; pdl = [None] * N5
z = [None] * N5; zpu = [None] * N5; zpd = [None] * N5
win = [None] * N5; news = [False] * N5; dirn = [0] * N5
J0 = bisect.bisect_left(tc, R.START - 3 * 86400)
for j in range(J0, N5):
    t = tc[j]
    i1 = R.closed_index(R.th1, 3600, t)
    idd = R.closed_index(R.td1, 86400, t)
    if i1 < 20 or idd < 14:
        continue
    e, a = R.e_h1[i1], R.ad1[idd]
    if a <= 0:
        continue
    ema[j], adv[j] = e, a
    pdh[j], pdl[j] = R.d1[idd][2], R.d1[idd][3]
    z[j] = (cl[j] - e) / a
    zpu[j] = (cl[j] - pdh[j]) / a
    zpd[j] = (pdl[j] - cl[j]) / a
    if t >= R.START:
        win[j] = owner_window(t)
        news[j] = R.news_block(t)
        dirn[j] = R.direction(t)


def roll_max(vals):
    """أعلى قيمة في الشموع M السابقة (j−M … j−1) — لا تشمل شمعة الزناد."""
    out = [None] * N5
    for j in range(J0 + M, N5):
        w = [v for v in vals[j - M:j] if v is not None]
        out[j] = max(w) if w else None
    return out


zneg = [None if v is None else -v for v in z]
EXT = {"متوسّط": (roll_max(z), roll_max(zneg)), "يوم_سابق": (roll_max(zpu), roll_max(zpd))}
print("الحقائق: %.1f ث" % (time.time() - T0), flush=True)

# آخر قاع/قمّة 5 د مؤكَّدَين قبل اللحظة (للزناد البديل — للعلم فقط)
sw5_hi = [(ts, p) for ts, p, h in R.sw5 if h]; sw5_hi_t = [x[0] for x in sw5_hi]
sw5_lo = [(ts, p) for ts, p, h in R.sw5 if not h]; sw5_lo_t = [x[0] for x in sw5_lo]


def last_sw5(is_hi, t):
    rows, times = (sw5_hi, sw5_hi_t) if is_hi else (sw5_lo, sw5_lo_t)
    k = bisect.bisect_left(times, t) - 1        # تأكيدٌ أصغر من اللحظة تمامًا (كـ CT.last_swings)
    return rows[k][1] if k >= 0 else None


_lad = {}


def levels_at(j):
    if j not in _lad:
        lad = S.ladder_at(tc[j], S.frames)
        lv = []
        for fr in ("1h", "4h"):
            for side in ("highs", "lows"):
                lv.extend(p for p, ts in lad[fr][side] if ts <= tc[j])
        _lad[j] = lv
    return _lad[j]


def target_for(j, buy, entry, risk):
    """أقرب مستوى حقيقيّ بين الدخول والمتوسّط بنسبةٍ صافية ≥ 3 وفي المتناول."""
    mean, reach = ema[j], C_REACH * adv[j]
    room = (mean - entry) if buy else (entry - mean)
    if room <= 0:
        return None
    need = RR_NET * (risk + SPREAD) + SPREAD          # (المسافة − س) ÷ (الخطر + س) ≥ 3
    best = None
    for p in levels_at(j) + [pdh[j], pdl[j], mean]:
        d = (p - entry) if buy else (entry - p)
        if d <= 0 or d > room + 1e-9 or d + 1e-9 < need or d > reach:
            continue
        if best is None or d < best[1]:
            best = (p, d)
    return None if best is None else best[0]


_th = {}


def thirds(j, entry, stop, target, buy):
    key = (j, round(stop, 6), round(target, 6), buy)
    if key not in _th:
        k1 = bisect.bisect_right(R.t1, tc[j] - 60)        # أوّل دقيقة بعد الإغلاق
        _th[key] = R.thirds(entry, stop, target, buy, k1)
    return _th[key]


def run(ext, k, b, n, ctx, windows=True, trigger="شمعة"):
    up_ext, dn_ext = EXT[ext]
    trades, busy = [], 0.0
    tally = {"زناد": 0, "سياق": 0, "وقف<3": 0, "بلا_هدف": 0, "مفتوحة": 0}
    for j in range(max(J0 + M, 1), N5):
        t = tc[j]
        if t < R.START or t < busy or ema[j] is None:
            continue
        w = win[j]
        if windows and not w:
            continue
        if news[j]:
            continue
        sell_ext = up_ext[j] is not None and up_ext[j] >= k
        buy_ext = dn_ext[j] is not None and dn_ext[j] >= k
        if not (sell_ext or buy_ext):
            continue
        if trigger == "شمعة":
            sell = sell_ext and cl[j] < lo[j - 1]
            buy = buy_ext and cl[j] > hi[j - 1]
        else:   # كسر آخر قاع/قمّة 5 د مؤكَّد
            sl, sh = last_sw5(False, t), last_sw5(True, t)
            sell = sell_ext and sl is not None and cl[j] < sl <= cl[j - 1]
            buy = buy_ext and sh is not None and cl[j] > sh >= cl[j - 1]
        if not (sell or buy):
            continue
        tally["زناد"] += 1
        is_buy = buy
        s = -1 if is_buy else 1               # جهة التمدّد: +1 صاعد (نبيع)، −1 هابط (نشتري)
        d = dirn[j]
        if (ctx == "بلا_اتّجاه" and d != 0) or (ctx == "ضدّ_المتّفق" and d != s):
            tally["سياق"] += 1
            continue
        entry, a5 = cl[j], R.a5[j]
        if is_buy:
            stop = min(min(lo[j - M:j + 1]) - b * a5, entry - n * a5)
        else:
            stop = max(max(hi[j - M:j + 1]) + b * a5, entry + n * a5)
        risk = abs(entry - stop)
        if risk <= 0 or risk / entry * 1e4 < MIN_STOP_BPS:
            tally["وقف<3"] += 1
            continue
        target = target_for(j, is_buy, entry, risk)
        if target is None:
            tally["بلا_هدف"] += 1
            continue
        r, exit_t = thirds(j, entry, stop, target, is_buy)
        if r is None:
            break
        tally["مفتوحة"] += 1
        trades.append((t, r, w or "خارج_النوافذ", is_buy, risk / entry * 1e4, exit_t))
        busy = exit_t + 60
    return trades, tally


def weekdays(a, b):
    d0 = datetime.fromtimestamp(a, timezone.utc).date(); d1 = datetime.fromtimestamp(b, timezone.utc).date()
    return sum(1 for i in range((d1 - d0).days + 1) if (d0 + timedelta(days=i)).weekday() < 5)


DAYS = weekdays(R.START, R.END)


def block(tr, tally=None):
    out = {"تعلّم": R.stats([x for x in tr if x[0] < SPLIT]), "اختبار": R.stats([x for x in tr if x[0] >= SPLIT]),
           "كلّه": R.stats(tr), "لندن": R.stats([x for x in tr if x[2] == "london_peak"]),
           "نيويورك": R.stats([x for x in tr if x[2] == "ny_open"]),
           "صفقات/يوم": round(len(tr) / DAYS, 3)}
    if tally is not None:
        out["عدّاد"] = tally
    return out


def owner_ok(blk):
    T, A = blk["اختبار"], blk["كلّه"]
    pos = sum(1 for v in (A.get("أنصاف") or {}).values() if v > 0)
    return {"اختبار_R/صفقة>0": (T.get("R/صفقة") or 0) > 0, "اختبار_معامل≥1.15": (T.get("معامل") or 0) >= 1.15,
            "اختبار_n≥30": T.get("n", 0) >= 30, "أنصاف_موجبة": "%d/%d" % (pos, len(A.get("أنصاف") or {})),
            "أنصاف≥4": pos >= 4}


def line(p, blk):
    L, T, A = blk["تعلّم"], blk["اختبار"], blk["كلّه"]
    return ("%s | تعلّم n=%s R/ص=%s | اختبار n=%s R/ص=%s معامل=%s | كلّه n=%s R=%s سحب=%s أنصاف=%s | ص/يوم=%s" % (
        p, L.get("n"), L.get("R/صفقة"), T.get("n"), T.get("R/صفقة"), T.get("معامل"), A.get("n"), A.get("R"),
        A.get("سحب_R"), A.get("أنصاف"), blk["صفقات/يوم"]))


if __name__ == "__main__":
    print("الفصل: %s · أيّام عمل=%d" % (datetime.fromtimestamp(SPLIT, timezone.utc).strftime("%Y-%m-%d %H:%M"), DAYS),
          flush=True)
    grid = [("متوسّط", k, b, n, c) for k, b, n, c in itertools.product(
        (0.5, 0.75, 1.0), (0.0, 0.25), (1.0, 2.0), ("أيّ", "بلا_اتّجاه", "ضدّ_المتّفق"))]
    grid += [("يوم_سابق", k, b, n, "أيّ") for k, b, n in itertools.product((0.0, 0.25, 0.5), (0.0, 0.25), (1.0, 2.0))]
    assert len(grid) <= 48
    rows, all_tr = [], {}
    for p in grid:
        tr, tally = run(*p)
        blk = block(tr, tally)
        all_tr[p] = tr
        rows.append({"تمدّد": p[0], "ك": p[1], "ب": p[2], "ن": p[3], "سياق": p[4], **blk})
        print(line(p, blk), "| %.0f ث" % (time.time() - T0), flush=True)

    elig = [(i, r) for i, r in enumerate(rows) if r["تعلّم"].get("n", 0) >= 60]
    best_i, best = max(elig, key=lambda x: x[1]["تعلّم"]["R/صفقة"]) if elig else (None, None)
    result = {"تعريف": __doc__, "ثوابت": {"م_شموع": M, "ج_متناول": C_REACH, "نسبة_صافية": RR_NET, "سبريد": SPREAD,
                                           "أدنى_وقف_ن.أ": MIN_STOP_BPS, "فصل_التعلّم": SPLIT, "أيّام_عمل": DAYS},
              "تركيبات": rows, "عدد_المؤهّلة_≥60": len(elig)}
    if best is not None:
        p = grid[best_i]
        print("\nالمختارة على التعلّم وحده:", p, flush=True)
        result["المختارة"] = {"المعامِلات": {"تمدّد": p[0], "ك": p[1], "ب": p[2], "ن": p[3], "سياق": p[4]},
                               **{kk: best[kk] for kk in ("تعلّم", "اختبار", "كلّه", "لندن", "نيويورك", "صفقات/يوم", "عدّاد")},
                               "معيار_المالك": owner_ok(best)}
        tr = all_tr[p]
        json.dump([[x[0], x[5], round(x[1], 4), x[2], x[3], round(x[4], 2)] for x in tr],
                  open(os.path.join(OUT, "trades_best.json"), "w", encoding="utf-8"), ensure_ascii=False)
        # للعلم فقط (لا للاختيار)
        info = {}
        tr_all, tl_all = run(*p, windows=False)
        info["كلّ_الساعات_بلا_نوافذ"] = block(tr_all, tl_all)
        info["كلّ_الساعات_خارج_النوافذ_وحدها"] = block([x for x in tr_all if x[2] == "خارج_النوافذ"])
        tr_sw, tl_sw = run(*p, trigger="قاع_مؤكَّد")
        info["زناد_كسر_قاع_5د_مؤكَّد"] = block(tr_sw, tl_sw)
        for name, blk in info.items():
            print(line(name, blk), flush=True)
        result["للعلم"] = info
        pos_test = sum(1 for r in rows if (r["اختبار"].get("R/صفقة") or -1) > 0)
        pos_learn = sum(1 for r in rows if (r["تعلّم"].get("R/صفقة") or -1) > 0)
        result["الشبكة_كلّها"] = {"تعلّم_موجب": pos_learn, "اختبار_موجب": pos_test, "من": len(rows)}
        print("الشبكة: تعلّم موجب %d · اختبار موجب %d من %d" % (pos_learn, pos_test, len(rows)), flush=True)
        print(json.dumps(result["المختارة"], ensure_ascii=False), flush=True)
    json.dump(result, open(os.path.join(OUT, "results.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("تمّ: %.0f ث" % (time.time() - T0), flush=True)
