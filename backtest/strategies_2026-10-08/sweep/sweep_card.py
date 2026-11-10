# -*- coding: utf-8 -*-
"""بطاقة «الكنس ثمّ العودة» على تاريخ الناسداك — قياسٌ فقط، خارج المشروع، بمسطرة البطاقة 414 نفسها.

  المستويات : قمم/قيعان الساعة والأربع ساعات المؤكَّدة (بعمق سلّم الحيّ 200 لكلّ إطار وجهة)
              [+ قمّة/قاع يوم الوسيط السابق — شمعة اليوم المغلقة].
  أوّل لمس  : المستوى «سليم» — لم يتجاوزه أيّ سعرٍ منذ تأكيده (أو منذ إغلاق يومه) حتّى بداية شمعة الحدث.
  الحدث     : شمعة 5 د تأخذ مستوى قمّةٍ سليمًا أو أكثر بذيلها (القمّة > المستوى، والافتتاح ≤ المستوى)
              وتُغلق دون أدنى ما أخذته ⟸ بيعٌ بالإغلاق. والعكس للقاع ⟸ شراء. أخذُ الجهتين معًا ⟸ لا شيء.
  الوقف     : max(قمّة الشمعة + ب×مدى5د , الإغلاق + ن×مدى5د) للبيع (والعكس للشراء). أدنى 3 ن.أ وإلّا لا دخول.
  الهدف     : أقرب مستوى معاكس مؤكَّد (ساعة/4س [+ اليوم السابق]) صافيه ≥ 3: (المسافة−1.5)÷(الخطر+1.5) ≥ 3،
              وفي المتناول ≤ ج × مدى اليوم 14.
  الإدارة   : أثلاث المالك R.thirds (كلفة 1.5) من أوّل دقيقة بعد الإغلاق · مركزٌ واحد · نوافذ المالك · منع الخبر.
"""
import sys
sys.dont_write_bytecode = True
import bisect
import itertools
import json
import os
import time
from datetime import datetime, timezone

sys.path.insert(0, r"C:\Users\NQ\QUANT_NQ")
sys.path.insert(0, r"C:\Users\NQ\QUANT_NQ\backtest\card_414")
import card_replay as R
import card_replay_shared as S
from shared import card_trend as CT
from shared.owner_windows import owner_window

OUT = os.path.dirname(os.path.abspath(__file__))
SPREAD = R.COST            # 1.5 نقطة
MIN_BPS = 3.0
KEEP = S.KEEP
T0 = time.time()
m5, td1, d1 = R.m5, R.td1, R.d1

# ---------------------------------------------------------------- فحص محاذاة اليوم
_hours = {}
for t in td1[-200:]:
    hh = datetime.fromtimestamp(t, timezone.utc).hour
    _hours[hh] = _hours.get(hh, 0) + 1
print("ساعات بدء شموع اليوم (غرينتش) في آخر 200:", _hours, flush=True)

# ---------------------------------------------------------------- المستويات بترتيب السلّم
# (وقت التأكيد، السعر، قمّة؟، الإطار، الرتبة في قائمة الإطار/الجهة) — الرتبة = فهرس ladder_at
LEVELS = []
for frame, sw in (("1h", S.sw1), ("4h", S.sw4)):
    cnt = {True: 0, False: 0}
    for ts, p, hi in sw:
        LEVELS.append((ts, p, hi, frame, cnt[hi]))
        cnt[hi] += 1
LEVELS.sort(key=lambda x: x[0])
FT = {f: (S.frames[f][0][1], S.frames[f][1][1]) for f in ("1h", "4h")}   # أوقات تأكيد القمم، القيعان


def eligible(lv, t):
    """في سلّم الحيّ عند t: من آخر KEEP مستوى مؤكَّد في إطاره وجهته."""
    ts, p, hi, frame, rank = lv
    times = FT[frame][0 if hi else 1]
    return ts <= t and rank >= bisect.bisect_right(times, t) - KEEP[frame]


# سلامة المستويات المؤكَّدة قبل بداية شموع 5 د: تُفحص بشموع إطارها نفسه
M5_START = m5[0][0]
pre_taken = set()
for lid, (ts, p, hi, frame, rank) in enumerate(LEVELS):
    if ts >= M5_START:
        continue
    rows, times = (R.h1, R.th1) if frame == "1h" else (R.h4, R.th4)
    a = bisect.bisect_left(times, ts)
    b = bisect.bisect_left(times, M5_START)
    seg = rows[a:b]
    if hi and any(r[2] > p for r in seg):
        pre_taken.add(lid)
    if not hi and any(r[3] < p for r in seg):
        pre_taken.add(lid)


def precompute(use_pd):
    """أحداث الكنس على كلّ شمعة 5 د — سببيّة بالبناء: المستوى يُعرف قبل بداية الشمعة، وسلامته من الشموع السابقة وحدها."""
    events = []
    hi_list, lo_list = [], []           # (السعر، رقم المستوى) مرتّبة تصاعديًّا — السليمة فقط
    p = 0
    cur_day, pdh, pdl, pdh_ok, pdl_ok = None, None, None, False, False
    both = 0
    for j in range(1, len(m5)):
        t0, o, h, l, c = m5[j]
        while p < len(LEVELS) and LEVELS[p][0] <= t0:
            if p not in pre_taken:
                bisect.insort(hi_list if LEVELS[p][2] else lo_list, (LEVELS[p][1], p))
            p += 1
        # القمم المأخوذة: كلّ سليمٍ سعره < قمّة الشمعة (تُزال كلّها — استُهلكت)
        k = bisect.bisect_left(hi_list, (h, -1))
        taken_hi = [LEVELS[x[1]] for x in hi_list[:k]]
        del hi_list[:k]
        k = bisect.bisect_right(lo_list, (l, float("inf")))
        taken_lo = [LEVELS[x[1]] for x in lo_list[k:]]
        del lo_list[k:]
        hi_px = [lv[1] for lv in taken_hi if eligible(lv, t0)]
        lo_px = [lv[1] for lv in taken_lo if eligible(lv, t0)]
        # اليوم السابق: شمعة اليوم المغلقة قبل بداية هذه الشمعة؛ سليمٌ منذ إغلاقها
        idd = R.closed_index(td1, 86400, t0)
        if idd != cur_day:
            cur_day = idd
            if idd >= 0:
                assert td1[idd] + 86400 <= t0
                pdh, pdl, pdh_ok, pdl_ok = d1[idd][2], d1[idd][3], True, True
        if use_pd and cur_day is not None and cur_day >= 0:
            if pdh_ok and h > pdh:
                hi_px.append(pdh)
            if pdl_ok and l < pdl:
                lo_px.append(pdl)
        if cur_day is not None and cur_day >= 0:
            if h > pdh:
                pdh_ok = False
            if l < pdl:
                pdl_ok = False
        sell = bool(hi_px) and c < min(hi_px) and o <= min(hi_px)
        buy = bool(lo_px) and c > max(lo_px) and o >= max(lo_px)
        if sell and buy:
            both += 1
            continue
        if sell:
            events.append((j, False, min(hi_px)))
        elif buy:
            events.append((j, True, max(lo_px)))
    return events, both


def precompute_any_touch(use_pd):
    """للعلم: بلا شرط أوّل لمس — أيّ مستوى في سلّم الحيّ [افتتاح ≤ المستوى < القمّة] والإغلاق دونه."""
    events = []
    for j in range(1, len(m5)):
        t0, o, h, l, c = m5[j]
        t_close = t0 + 300
        if t_close < R.START or not owner_window(t_close):
            continue
        lad = S.ladder_at(t0, S.frames)
        his = [x[0] for f in ("1h", "4h") for x in lad[f]["highs"] if x[1] <= t0]
        los = [x[0] for f in ("1h", "4h") for x in lad[f]["lows"] if x[1] <= t0]
        idd = R.closed_index(td1, 86400, t0)
        if use_pd and idd >= 0:
            his.append(d1[idd][2]); los.append(d1[idd][3])
        hi_px = [x for x in his if o <= x < h]
        lo_px = [x for x in los if l < x <= o]
        sell = bool(hi_px) and c < min(hi_px)
        buy = bool(lo_px) and c > max(lo_px)
        if sell and buy:
            continue
        if sell:
            events.append((j, False, min(hi_px)))
        elif buy:
            events.append((j, True, max(lo_px)))
    return events


_tcache, _thcache = {}, {}


def target_levels(t_close, buy, use_pd):
    key = (t_close, buy, use_pd)
    if key not in _tcache:
        lad = S.ladder_at(t_close, S.frames)
        side = "highs" if buy else "lows"
        lv = list(lad["1h"][side]) + list(lad["4h"][side])
        if use_pd:
            idd = R.closed_index(td1, 86400, t_close)
            if idd >= 0:
                lv.append([d1[idd][2] if buy else d1[idd][3], td1[idd] + 86400])
        _tcache[key] = lv
    return _tcache[key]


def thirds(entry, stop, target, buy, k1):
    key = (k1, entry, stop, target, buy)
    if key not in _thcache:
        _thcache[key] = R.thirds(entry, stop, target, buy, k1)
    return _thcache[key]


def run(events, b, n, c, ctx, use_pd, windows=True):
    trades, busy = [], 0.0
    rej = {"ضدّ_السياق": 0, "وقف<3ن.أ": 0, "لا_هدف": 0, "خبر": 0, "خارج_النافذة": 0, "مشغول": 0}
    for j, buy, lvl in events:
        t0, o, h, l, cl = m5[j]
        t_close = t0 + 300
        if t_close < R.START:
            continue
        if t_close < busy:
            rej["مشغول"] += 1
            continue
        win = owner_window(t_close)
        if windows and not win:
            rej["خارج_النافذة"] += 1
            continue
        if R.news_block(t_close):
            rej["خبر"] += 1
            continue
        d = R.direction(t_close)
        side = 1 if buy else -1
        if (ctx == "مع" and d != side) or (ctx == "ضدّ" and d != -side):
            rej["ضدّ_السياق"] += 1
            continue
        a5 = R.a5[j]
        entry = cl
        stop = min(l - b * a5, entry - n * a5) if buy else max(h + b * a5, entry + n * a5)
        risk = abs(entry - stop)
        if risk <= 0 or risk / entry * 1e4 < MIN_BPS:
            rej["وقف<3ن.أ"] += 1
            continue
        idd = R.closed_index(td1, 86400, t_close)
        if idd < 0 or R.ad1[idd] <= 0:
            rej["لا_هدف"] += 1
            continue
        reach = c * R.ad1[idd]
        lv = target_levels(t_close, buy, use_pd)
        target = CT.nearest_target(lv, buy, entry, risk, reach, t_close, rr=3.0 + 4.0 * SPREAD / risk)
        if target is None:
            rej["لا_هدف"] += 1
            continue
        net = (abs(target - entry) - SPREAD) / (risk + SPREAD)
        assert net >= 3.0 - 1e-9 and abs(target - entry) <= reach + 1e-9
        assert (target > entry) if buy else (target < entry)
        k1 = bisect.bisect_right(R.t1, t_close - 60)
        assert k1 >= len(R.t1) or R.t1[k1] >= t_close
        r, exit_t = thirds(entry, stop, target, buy, k1)
        if r is None:
            break
        trades.append((t_close, r, win or "خارج", buy, risk / entry * 1e4, exit_t))
        busy = exit_t + 60
    return trades, rej


SPLIT = R.START + 0.7 * (R.END - R.START)
DAYS = sum(1 for d in range(int(R.START // 86400), int(R.END // 86400) + 1)
           if datetime.fromtimestamp(d * 86400, timezone.utc).weekday() < 5)


def block(tr):
    return {"تعلّم": R.stats([x for x in tr if x[0] < SPLIT]), "اختبار": R.stats([x for x in tr if x[0] >= SPLIT]),
            "كلّه": R.stats(tr), "لندن": R.stats([x for x in tr if x[2] == "london_peak"]),
            "نيويورك": R.stats([x for x in tr if x[2] == "ny_open"]),
            "صفقات/يوم": round(len(tr) / DAYS, 3)}


def owner_pass(bl):
    T, A = bl["اختبار"], bl["كلّه"]
    halves = list((A.get("أنصاف") or {}).values())
    pos = sum(v > 0 for v in halves)
    checks = {"اختبار_R/صفقة>0": (T.get("R/صفقة") or -1) > 0,
              "اختبار_معامل≥1.15": (T.get("معامل") or 0) >= 1.15,
              "اختبار_n≥30": T.get("n", 0) >= 30,
              "أنصاف_موجبة≥4/5": pos >= 4}
    return {"الشروط": checks, "أنصاف_موجبة": "%d/%d" % (pos, len(halves)), "يجتاز": all(checks.values())}


if __name__ == "__main__":
    print("أيّام عمل في العيّنة: %d · الحدّ بين التعلّم والاختبار: %s" % (
        DAYS, datetime.fromtimestamp(SPLIT, timezone.utc).strftime("%Y-%m-%d %H:%M")), flush=True)
    EV = {}
    for use_pd in (False, True):
        ev, both = precompute(use_pd)
        EV[use_pd] = ev
        nwin = sum(1 for j, _, _ in ev if m5[j][0] + 300 >= R.START and owner_window(m5[j][0] + 300))
        print("أحداث الكنس (اليوم السابق=%s): كلّها %d · في النوافذ بعد البدء %d · الجهتان معًا %d · %.0f ث" % (
            use_pd, len(ev), nwin, both, time.time() - T0), flush=True)

    rows = []
    grid = list(itertools.product((0.0, 0.25), (1.0, 2.0), (1.0, 1.5), ("أيّ", "مع", "ضدّ"), (False, True)))
    for b, n, c, ctx, use_pd in grid:
        tr, rej = run(EV[use_pd], b, n, c, ctx, use_pd)
        bl = block(tr)
        rows.append({"ب": b, "ن": n, "ج": c, "السياق": ctx, "المستويات": "ساعة/4س+اليوم_السابق" if use_pd else "ساعة/4س",
                     **bl, "مردود": rej})
        L, T, A = bl["تعلّم"], bl["اختبار"], bl["كلّه"]
        print("ب=%.2f ن=%.0f ج=%.1f %-3s يوم=%d | تعلّم n=%s R/ص=%s | اختبار n=%s R/ص=%s معامل=%s | كلّه n=%s R=%s سحب=%s أنصاف=%s" % (
            b, n, c, ctx, use_pd, L.get("n"), L.get("R/صفقة"), T.get("n"), T.get("R/صفقة"), T.get("معامل"),
            A.get("n"), A.get("R"), A.get("سحب_R"), A.get("أنصاف")), flush=True)

    ok = [r for r in rows if r["تعلّم"].get("n", 0) >= 60]
    best = max(ok, key=lambda r: r["تعلّم"]["R/صفقة"]) if ok else None
    out = {"التعريف": __doc__, "الحدّ": SPLIT, "أيّام_العمل": DAYS, "الشبكة": rows}
    if best:
        b, n, c, ctx = best["ب"], best["ن"], best["ج"], best["السياق"]
        use_pd = best["المستويات"] != "ساعة/4س"
        tr, rej = run(EV[use_pd], b, n, c, ctx, use_pd)
        out["المختارة"] = {"ب": b, "ن": n, "ج": c, "السياق": ctx, "المستويات": best["المستويات"],
                           **block(tr), "معيار_المالك": owner_pass(block(tr)), "مردود": rej,
                           "ترتيبها_في_الاختبار": sorted(rows, key=lambda r: -(r["اختبار"].get("R/صفقة") or -9)).index(best) + 1}
        json.dump([[t, ex, r, w, bu, round(bps, 2)] for t, r, w, bu, bps, ex in tr],
                  open(os.path.join(OUT, "trades_best.json"), "w", encoding="utf-8"), ensure_ascii=False)
        # للعلم فقط — لا للاختيار
        tr_all, rej_all = run(EV[use_pd], b, n, c, ctx, use_pd, windows=False)
        bl_all = block(tr_all)
        bl_all["خارج_النوافذ"] = R.stats([x for x in tr_all if x[2] == "خارج"])
        out["للعلم_بلا_نوافذ"] = bl_all
        ev_any = precompute_any_touch(use_pd)
        tr_any, _ = run(ev_any, b, n, c, ctx, use_pd)
        out["للعلم_بلا_أوّل_لمس"] = {**block(tr_any), "أحداث": len(ev_any)}
        # تحقّقات سببيّة على صفقات المختارة
        audit = {"صفقات": len(tr), "تداخل_مراكز": 0}
        for a_, b_ in zip(tr, tr[1:]):
            if b_[0] < a_[5] + 60:
                audit["تداخل_مراكز"] += 1
        out["تدقيق"] = audit
        print("المختارة:", json.dumps({k: out["المختارة"][k] for k in ("ب", "ن", "ج", "السياق", "المستويات")}, ensure_ascii=False))
        for k in ("تعلّم", "اختبار", "كلّه", "لندن", "نيويورك", "صفقات/يوم", "معيار_المالك", "ترتيبها_في_الاختبار", "مردود"):
            print("  ", k, json.dumps(out["المختارة"][k], ensure_ascii=False))
        print("بلا نوافذ (للعلم):", json.dumps({k: bl_all[k] for k in ("كلّه", "اختبار", "خارج_النوافذ", "صفقات/يوم")}, ensure_ascii=False))
        print("بلا أوّل لمس (للعلم):", json.dumps({k: out["للعلم_بلا_أوّل_لمس"][k] for k in ("كلّه", "اختبار", "أحداث")}, ensure_ascii=False))
        print("تدقيق:", audit)
    json.dump(out, open(os.path.join(OUT, "results.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("تمّ في %.0f ث" % (time.time() - T0), flush=True)
