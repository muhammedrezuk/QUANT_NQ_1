# -*- coding: utf-8 -*-
"""الدفعة والاستمرار بتعريف الذرّة 152 الجديد (2.6.0) — **المحاولة السابعة لفكرة الزخم** (المالك ١٠-١٣: «NQ اصلح وعيد تشغيل اختبارات»).
(الدفعة المحاذية نسبيّةٌ لجهة صافي الحركة ⟸ تُقارَن بالأفق في تلك الجهة.) ⚠️ بالقانون: **لا جزء معزول باقٍ** لهذه المقاييس على 2014–2026 (المحاولة السادسة استعملته كلّه) ⟸ النتيجة **وصفٌ لا دليل**؛ أيّ نتيجةٍ موجبة
لا تُتداول، بل تذهب إلى سجلٍّ أماميّ. الاختبار نفسه حرفيًّا (الأطر · الأفق 5 · الفترات · السبريد · قاعدة الحكم) والتغيير في التعريف وحده:
نافذةٌ واحدة 25 للثلاثة · الاستمرار في جهة صافي الحركة · ① على `impulse_aligned` (الدفعة بإشارة محاذاة آخر شمعة لصافي الحركة).
"""

import calendar
import json
import math
import os
import sqlite3
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
if sys.stdout is None or sys.stderr is None:
    sys.stdout = sys.stderr = open(os.path.join(HERE, "run_impulse_v26.log"), "a", encoding="utf-8")
sys.stdout.reconfigure(encoding="utf-8")
HIST = "file:C:/Users/NQ/QUANT_NQ/forex_runtime/var/history/ctrader_history.db?mode=ro"
FRAMES = (("5 د", 5), ("15 د", 15), ("ساعة", 60), ("4 س", 240))
ROC_N, IMP_N, PER_N = 25, 25, 25
FLAT_PCT, PER_MIN = 0.04, 0.55
H = 5
SPREAD_PTS = 1.0
PERIODS = (("بناء", 0, calendar.timegm((2020, 1, 1, 0, 0, 0))),
           ("امتحان", calendar.timegm((2020, 1, 1, 0, 0, 0)), calendar.timegm((2025, 1, 1, 0, 0, 0))),
           ("ملموسة", calendar.timegm((2025, 1, 1, 0, 0, 0)), 1e12))


def load():
    con = sqlite3.connect(HIST, uri=True)
    a = np.array(con.execute("select period_start, close from candles_history where symbol='USTEC' and period='M1' "
                             "order by period_start").fetchall(), dtype=float)
    con.close()
    return a[:, 0], a[:, 1]


def bucket(ts, cl, minutes):
    b = np.floor(ts / (minutes * 60)).astype(np.int64)
    last = np.r_[np.nonzero(np.diff(b))[0], len(b) - 1]
    return b[last], ts[last], cl[last]


def samples(B, T, C):
    need = max(ROC_N, IMP_N, PER_N)
    rows = []
    i = need
    while i + H < len(C):
        # تصحيح ١٠-١٣: الذرّة تعدّ شموعها متتابعة عبر العطلة (لا تشترط اتّصال النافذة)، فالنافذة الماضية هنا مثلها؛ والاتّصال يُشترط للأفق
        # القادم وحده (لا يعبر الهدفُ عطلة). كان اشتراط 65 شمعةً متّصلة يستحيل على 4 ساعات (≈ 11 يومًا) فتوقّف البرنامج بلا عيّنات.
        if B[i + H] - B[i] == H:
            w = C[i - need:i + 1]
            d = np.diff(w)
            roc = (C[i] - C[i - ROC_N]) / C[i - ROC_N] * 100
            avg = np.mean(np.abs(d[-IMP_N:]))
            imp = abs(d[-1]) / avg if avg > 0 else 0.0
            up, dn = int((d[-PER_N:] > 0).sum()), int((d[-PER_N:] < 0).sum())
            direction = 1 if roc > 0 else -1 if roc < 0 else 0
            per = ((up if direction > 0 else dn) / (up + dn)) if (up + dn and direction) else 0.5
            aligned = 0.0 if (direction == 0 or d[-1] == 0) else (imp if d[-1] * direction > 0 else -imp)
            sig = 0 if (abs(roc) <= FLAT_PCT or per < PER_MIN) else (1 if roc > 0 else -1)
            fwd = math.log(C[i + H] / C[i]) * 1e4
            rows.append((T[i], aligned, roc, per, sig, fwd, SPREAD_PTS / C[i] * 1e4))
            i += H
        else:
            i += 1
    return np.array(rows)


def corr(x, y):
    return float(np.corrcoef(x, y)[0, 1]) if len(x) > 30 and x.std() > 0 and y.std() > 0 else None


def mean(x):
    return round(float(np.mean(x)), 3) if len(x) else None


def main():
    t0 = time.time()
    ts, cl = load()
    out = {"التصميم": __doc__, "الأطر": {}}
    for fname, m in FRAMES:
        R = samples(*bucket(ts, cl, m))
        per = {p: R[(R[:, 0] >= a) & (R[:, 0] < b)] for p, a, b in PERIODS}
        sgn = 1 if (corr(per["بناء"][:, 1], np.sign(per["بناء"][:, 2]) * per["بناء"][:, 5]) or 0) >= 0 else -1
        res = {"إشارة_الدفعة_من_البناء": sgn, "الفترات": {}}
        for p, r in per.items():
            n = len(r)
            follow = np.sign(r[:, 2]) * r[:, 5] - r[:, 6]
            hi, lo = r[:, 3] >= PER_MIN, r[:, 3] < PER_MIN
            act = r[:, 4] != 0
            res["الفترات"][p] = {
                "عدد": n, "نطاق": round(2 / math.sqrt(n), 4) if n else None,
                "١_ارتباط_الدفعة": None if corr(r[:, 1], np.sign(r[:, 2]) * r[:, 5]) is None else round(corr(r[:, 1], np.sign(r[:, 2]) * r[:, 5]), 4),
                "١_محاكاة_الدفعة": mean(sgn * np.sign(r[:, 1]) * np.sign(r[:, 2]) * r[:, 5] - r[:, 6]),
                "٢_اتّباع_الصافي_استمرار_عالٍ": mean(follow[hi]), "٢_عدد_عالٍ": int(hi.sum()),
                "٢_اتّباع_الصافي_استمرار_منخفض": mean(follow[lo]), "٢_عدد_منخفض": int(lo.sum()),
                "٣_حكم_الذرّة_محاكاة": mean(r[act, 4] * r[act, 5] - r[act, 6]), "٣_صفقات": int(act.sum()),
                "الانجراف": mean(r[:, 5]), "التكلفة": mean(r[:, 6])}
        t = res["الفترات"]["امتحان"]
        c1 = t["١_ارتباط_الدفعة"]
        res["الحكم"] = {
            "١_الدفعة": "يضيف" if (c1 is not None and sgn * c1 > t["نطاق"] and (t["١_محاكاة_الدفعة"] or -1) > 0) else "لا يضيف",
            "٢_الاستمرار": "يضيف" if ((t["٢_اتّباع_الصافي_استمرار_عالٍ"] or -1) > 0 and
                                   (t["٢_اتّباع_الصافي_استمرار_عالٍ"] or -1) > (t["٢_اتّباع_الصافي_استمرار_منخفض"] or 0)) else "لا يضيف",
            "٣_حكم_الذرّة": "يضيف" if (t["٣_حكم_الذرّة_محاكاة"] or -1) > 0 else "لا يضيف"}
        out["الأطر"][fname] = res
    out["المدّة_ث"] = round(time.time() - t0, 1)
    json.dump(out, open(os.path.join(HERE, "impulse_persistence_v26.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    L = ["# الدفعة والاستمرار بتعريف 152 الجديد (2.6.0) — المحاولة السابعة (وصفٌ لا دليل: لا جزء معزول باقٍ)", "",
         "بتعريف 2.6.0 (25 · 25 · 25 · 0.04٪ · 0.55، الاستمرار في جهة الصافي، الدفعة المحاذية)، أفق 5 شمعات، بناء 2014–2019 · امتحان 2020–2024 (الحكم) · 2025–2026 ملموسة. المحاكاة بنقطة الأساس للصفقة بعد السبريد.", ""]
    for fname, res in out["الأطر"].items():
        L += ["## %s — إشارة الدفعة من البناء %s" % (fname, res["إشارة_الدفعة_من_البناء"]), "",
              "**الحكم:** " + " · ".join("%s: %s" % kv for kv in res["الحكم"].items()), "",
              "| الفترة | عدد | ارتباط الدفعة (نطاق) | محاكاة الدفعة | اتّباع الصافي: استمرار عالٍ (عدد) | استمرار منخفض (عدد) | حكم الذرّة (صفقات) | الانجراف | التكلفة |",
              "|---|---|---|---|---|---|---|---|---|"]
        for p, r in res["الفترات"].items():
            L.append("| %s | %s | %s (±%s) | %s | %s (%s) | %s (%s) | %s (%s) | %s | %s |" % (
                p, r["عدد"], r["١_ارتباط_الدفعة"], r["نطاق"], r["١_محاكاة_الدفعة"], r["٢_اتّباع_الصافي_استمرار_عالٍ"], r["٢_عدد_عالٍ"],
                r["٢_اتّباع_الصافي_استمرار_منخفض"], r["٢_عدد_منخفض"], r["٣_حكم_الذرّة_محاكاة"], r["٣_صفقات"], r["الانجراف"], r["التكلفة"]))
        L.append("")
    L.append("المدّة: %s ث." % out["المدّة_ث"])
    open(os.path.join(HERE, "الدفعة والاستمرار — التعريف الجديد.md"), "w", encoding="utf-8").write("\n".join(L) + "\n")
    print("انتهى", out["المدّة_ث"], "ث", flush=True)


if __name__ == "__main__":
    main()
