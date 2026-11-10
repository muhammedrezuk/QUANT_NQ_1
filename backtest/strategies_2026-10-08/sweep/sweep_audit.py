# -*- coding: utf-8 -*-
"""تدقيق السببيّة لقياس «الكنس ثمّ العودة»:
  1) القطع: الأحداث قبل لحظةٍ ما لا تتغيّر إن حُذف كلّ ما بعدها من شموع 5 د.
  2) القوّة الغاشمة: لكلّ صفقةٍ من المختارة يُعاد اشتقاق الحدث من الصفر (المستوى مؤكَّدٌ قبل بداية الشمعة،
     في سلّم الحيّ، سليمٌ بمسحٍ مباشر لكلّ شموع 5 د بين تأكيده والشمعة السابقة، والإغلاق عاد دونه).
  3) الهدف: مؤكَّدٌ ≤ لحظة القرار، صافيه ≥ 3، وفي المتناول.
"""
import sys
sys.dont_write_bytecode = True
import bisect
import json
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sweep_card as SC

R, S = SC.R, SC.S
OUT = SC.OUT
res = json.load(open(os.path.join(OUT, "results.json"), encoding="utf-8"))
best = res["المختارة"]
use_pd = best["المستويات"] != "ساعة/4س"
full_m5 = R.m5

# 1) القطع
ev_full, _ = SC.precompute(use_pd)
cut_report = []
for frac in (0.4, 0.7, 0.9):
    K = int(len(full_m5) * frac)
    SC.m5 = full_m5[:K]
    ev_cut, _ = SC.precompute(use_pd)
    SC.m5 = full_m5
    a = [e for e in ev_full if e[0] < K]
    cut_report.append({"نسبة": frac, "أحداث_الكامل_قبل_القطع": len(a), "أحداث_المقطوع": len(ev_cut), "متطابقة": a == ev_cut})
print("القطع:", cut_report, flush=True)

# 2) القوّة الغاشمة على صفقات المختارة
trades = json.load(open(os.path.join(OUT, "trades_best.json"), encoding="utf-8"))
t5 = R.t5
highs = [r[2] for r in full_m5]; lows = [r[3] for r in full_m5]
bad, checked = [], 0
for t_close, exit_t, r, win, buy, bps in trades:
    j = bisect.bisect_left(t5, t_close - 300)
    assert full_m5[j][0] + 300 == t_close
    t0, o, h, l, c = full_m5[j]
    lad = S.ladder_at(t0, S.frames)
    side = "lows" if buy else "highs"
    cands = [(p, ts) for f in ("1h", "4h") for p, ts in lad[f][side] if ts <= t0]
    if use_pd:
        idd = R.closed_index(R.td1, 86400, t0)
        cands.append((R.d1[idd][3] if buy else R.d1[idd][2], R.td1[idd] + 86400))
    taken = []
    for p, ts in cands:
        a = bisect.bisect_left(t5, ts)          # أوّل شمعة 5 د تبدأ عند التأكيد أو بعده
        # تأكيدٌ عند بداية الشمعة نفسها: لا شموع بينهما ⟸ سليمٌ بالضرورة
        if buy:
            intact = a >= j or min(lows[a:j]) >= p
            if intact and l < p:
                taken.append(p)
        else:
            intact = a >= j or max(highs[a:j]) <= p
            if intact and h > p:
                taken.append(p)
    ok = bool(taken) and ((c > max(taken) and o >= max(taken)) if buy else (c < min(taken) and o <= min(taken)))
    checked += 1
    if not ok:
        bad.append({"t_close": t_close, "buy": buy, "taken": taken, "o": o, "c": c})
print("القوّة الغاشمة: فُحصت %d · مخالفة %d" % (checked, len(bad)), flush=True)
if bad:
    print(bad[:5])
json.dump({"القطع": cut_report, "القوّة_الغاشمة": {"فُحصت": checked, "مخالفة": len(bad), "أمثلة": bad[:10]}},
          open(os.path.join(OUT, "audit.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
