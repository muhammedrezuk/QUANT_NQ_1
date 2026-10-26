# -*- coding: utf-8 -*-
"""فحوص التسريب وخطأ القياس للمختارة — مستقلّة عن الحلقة: إعادة اشتقاق كلّ صفقة من قاعدة الشموع مباشرةً."""
import sys
sys.dont_write_bytecode = True
import json
import os
import random
import sqlite3
from collections import Counter
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import reversion as V                                   # noqa: E402  (لا يشغّل الشبكة: __main__ فقط)
R = V.R

OUT = V.OUT
db = sqlite3.connect("file:C:/Users/NQ/QUANT_NQ/forex_runtime/var/history/ctrader_history.db?mode=ro", uri=True)
res = json.load(open(os.path.join(OUT, "results.json"), encoding="utf-8"))
trades = json.load(open(os.path.join(OUT, "trades_best.json"), encoding="utf-8"))
P = res["المختارة"]["المعامِلات"]
report = {}

# ١) بدايات شموع اليوم: ساعة غرينتش ويوم الأسبوع (هل «اليوم السابق» يوم وسيطٍ كامل؟)
hrs = Counter(datetime.fromtimestamp(r[0], timezone.utc).hour for r in R.d1 if r[0] >= R.START)
wds = Counter(datetime.fromtimestamp(r[0], timezone.utc).strftime("%a") for r in R.d1 if r[0] >= R.START)
gaps = Counter(int(R.d1[i + 1][0] - R.d1[i][0]) // 3600 for i in range(len(R.d1) - 1) if R.d1[i][0] >= R.START)
report["شموع_اليوم"] = {"ساعة_البدء": dict(hrs), "يوم_البدء": dict(wds), "الفجوات_بالساعات": dict(gaps)}

# ٢) إعادة اشتقاق 12 صفقة عشوائيّة من القاعدة مباشرةً
random.seed(7)
sample = random.sample(trades, min(12, len(trades)))
rows = []
for t_close, exit_t, r, w, buy, bps in sorted(sample):
    bar5 = db.execute("select period_start,open,high,low,close from candles_history where symbol='USTEC' and period='M5' "
                      "and period_start<=? order by period_start desc limit 8", (t_close - 300,)).fetchall()[::-1]
    d1 = db.execute("select period_start,high,low from candles_history where symbol='USTEC' and period='D1' "
                    "and period_start+86400<=? order by period_start desc limit 1", (t_close,)).fetchone()
    h1 = db.execute("select period_start from candles_history where symbol='USTEC' and period='H1' "
                    "and period_start+3600<=? order by period_start desc limit 1", (t_close,)).fetchone()
    trig, prev = bar5[-1], bar5[-2]
    j = V.tc.index(t_close)
    ok_trig = (trig[4] < prev[3]) if not buy else (trig[4] > prev[2])
    rows.append({"t_close_utc": datetime.fromtimestamp(t_close, timezone.utc).strftime("%Y-%m-%d %H:%M"),
                 "نافذة": w, "شراء": buy, "زناد_مستقلّ": ok_trig, "شمعة_الزناد_آخر_مغلقة": trig[0] + 300 == t_close,
                 "يوم_سابق_مستقلّ": [d1[1], d1[2]], "يوم_سابق_في_الحلقة": [V.pdh[j], V.pdl[j]],
                 "يوم_مغلق_قبل": d1[0] + 86400 <= t_close, "ساعة_مغلقة_قبل": h1[0] + 3600 <= t_close,
                 "تمدّد_أقصى": round(V.EXT[P["تمدّد"]][1 if buy else 0][j], 3),
                 "متوسّط20س": round(V.ema[j], 2), "دخول": trig[4], "ن.أ_وقف": bps, "r": r,
                 "مدّة_د": round((exit_t - t_close) / 60)})
report["عيّنة_مستقلّة"] = rows

# ٣) الدخول دائمًا بعد الإغلاق: أوّل دقيقة في الإدارة ≥ t_close، والخروج بعده
bad = 0
for t_close, exit_t, *_ in trades:
    k1 = V.bisect.bisect_right(R.t1, t_close - 60)
    if R.t1[k1] < t_close or exit_t < t_close:
        bad += 1
report["دخول_قبل_الإغلاق"] = bad

# ٤) تداخل: مركزٌ واحد (لا صفقة تبدأ قبل خروج سابقتها)
ov = sum(1 for a, b in zip(trades, trades[1:]) if b[0] < a[1] + 60)
report["تداخل"] = ov

# ٥) ارتباط ترتيب التعلّم بالاختبار عبر الشبكة (المؤهّلة ≥ 60)
el = [(r["تعلّم"]["R/صفقة"], r["اختبار"].get("R/صفقة")) for r in res["تركيبات"]
      if r["تعلّم"].get("n", 0) >= 60 and r["اختبار"].get("n", 0) > 0]


def rank(v):
    o = sorted(range(len(v)), key=lambda i: v[i]); rk = [0] * len(v)
    for pos, i in enumerate(o):
        rk[i] = pos
    return rk


a, b = rank([x[0] for x in el]), rank([x[1] for x in el])
n = len(el)
rho = 1 - 6 * sum((x - y) ** 2 for x, y in zip(a, b)) / (n * (n * n - 1)) if n > 2 else None
report["سبيرمان_تعلّم_اختبار"] = {"n": n, "rho": round(rho, 3) if rho is not None else None}

# ٦) أفضل التعلّم داخل عائلة «المتوسّط» وحدها (حساسيّة: لو لم تدخل العائلة البديلة)
fam = [r for r in res["تركيبات"] if r["تمدّد"] == "متوسّط" and r["تعلّم"].get("n", 0) >= 60]
bf = max(fam, key=lambda r: r["تعلّم"]["R/صفقة"])
report["أفضل_عائلة_المتوسّط"] = {k: bf[k] for k in ("ك", "ب", "ن", "سياق", "تعلّم", "اختبار", "كلّه", "لندن", "نيويورك",
                                                      "صفقات/يوم")}
report["أفضل_عائلة_المتوسّط"]["معيار_المالك"] = V.owner_ok(bf)

json.dump(report, open(os.path.join(OUT, "checks.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(json.dumps(report, ensure_ascii=False, indent=1))
