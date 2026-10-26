# -*- coding: utf-8 -*-
"""سجلّ الزخم الأماميّ — ناسداك، ساعةً بساعة، من اليوم فصاعدًا، بلا تداول (ختم المالك «Nq» ٢٠٢٦-١٠-١٣).

لماذا: بعد سبع محاولاتٍ على التاريخ بقي أثرٌ حقيقيّ صغير — **الدفعة المحاذية على الساعة** (+0.028 / +0.035 / +0.059 خارج الصدفة في الفترات الثلاث) — لكنّه
أصغر من السبريد؛ ولا جزء معزول باقٍ ⟸ الحكم على ساعاتٍ لم تُرَ.
بتعريف الذرّة 152 (2.6.0) حرفيًّا وبلا معايرة: نافذةٌ واحدة 25 شمعة ساعة (عبر العطلة كالذرّة) · صافي الحركة ٪ · الاستمرار في جهة الصافي · الدفعة المحاذية
(|حركة آخر شمعة| ÷ متوسّط |الحركة| في 25، بإشارة محاذاتها للصافي). الهدف: عائد الساعات الخمس التالية **في جهة صافي الحركة** (متّصلة)، والعيّنات كلّ 5
بلا تداخل. يعمل كلّ ليلة (مهمّة ويندوز) ويعيد الحساب كلّه من START.
ما يُكتب: ارتباط الدفعة المحاذية بالهدف (ونطاق الصدفة) · محاكاة «اتّبع إشارة الدفعة» بعد سبريد نقطة · اتّباع الصافي حين الاستمرار ≥ 0.55 مقابل < 0.55 ·
آخر العيّنات. قياسٌ فقط: لا يمسّ الحيّ.
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
    sys.stdout = sys.stderr = open(os.path.join(HERE, "run.log"), "a", encoding="utf-8")
sys.stdout.reconfigure(encoding="utf-8")
HIST = "file:C:/Users/NQ/QUANT_NQ/forex_runtime/var/history/ctrader_history.db?mode=ro"
START = calendar.timegm(time.strptime(os.environ.get("MOM_FWD_START") or "2026-10-13", "%Y-%m-%d"))
W, H, PER_MIN = 25, 5, 0.55
#: ١٠-١٤ (ختم المالك «حطها 200 nq» بعد معايرة الذرّة وحدها): الاستمرار في الذرّة صار على 200 ⟸ يُسجَّل بجانب 25 (الجهة من صافي 25).
W_PER2 = 200
SPREAD_PTS = 1.0
LOOKBACK_S = 21 * 86400
LAST = 30


def load():
    con = sqlite3.connect(HIST, uri=True)
    a = np.array(con.execute("select period_start, close from candles_history where symbol='USTEC' and period='M1' and "
                             "period_start >= ? order by period_start", (START - LOOKBACK_S,)).fetchall(), dtype=float)
    con.close()
    return a.reshape(-1, 2)


def main():
    now = time.time()
    a = load()
    rows = []
    if len(a):
        b = np.floor(a[:, 0] / 3600).astype(np.int64)
        last = np.r_[np.nonzero(np.diff(b))[0], len(b) - 1]
        B, T, C = b[last], a[last, 0], a[last, 1]
        i = W
        while i + H < len(C):
            if T[i] >= START and B[i + H] - B[i] == H:
                d = np.diff(C[i - W:i + 1])
                roc = (C[i] - C[i - W]) / C[i - W] * 100
                direction = 1 if roc > 0 else -1 if roc < 0 else 0
                avg = float(np.mean(np.abs(d)))
                imp = abs(d[-1]) / avg if avg > 0 else 0.0
                aligned = 0.0 if (direction == 0 or d[-1] == 0) else (imp if d[-1] * direction > 0 else -imp)
                up, dn = int((d > 0).sum()), int((d < 0).sum())
                per = ((up if direction > 0 else dn) / (up + dn)) if (up + dn and direction) else 0.5
                d2 = np.diff(C[i - W_PER2:i + 1]) if i >= W_PER2 else None
                u2, n2 = (int((d2 > 0).sum()), int((d2 < 0).sum())) if d2 is not None else (0, 0)
                per2 = (((u2 if direction > 0 else n2) / (u2 + n2)) if (u2 + n2 and direction) else 0.5) if d2 is not None else None
                fwd_dir = direction * math.log(C[i + H] / C[i]) * 1e4
                rows.append({"الساعة": time.strftime("%Y-%m-%d %H:00", time.gmtime(B[i] * 3600)), "صافي_الحركة_٪": round(roc, 3),
                             "الدفعة_المحاذية": round(aligned, 2), "الاستمرار": round(per, 2), "الاستمرار_200": None if per2 is None else round(per2, 2), "الأفق_في_جهة_الصافي_ن.أ": round(fwd_dir, 1),
                             "التكلفة_ن.أ": round(SPREAD_PTS / C[i] * 1e4, 3)})
                i += H
            else:
                i += 1
    out = {"من": time.strftime("%Y-%m-%d", time.gmtime(START)), "آخر_تحديث": time.strftime("%Y-%m-%d %H:%M غ", time.gmtime(now)),
           "عيّنات": len(rows)}
    if rows:
        x = np.array([r["الدفعة_المحاذية"] for r in rows]); y = np.array([r["الأفق_في_جهة_الصافي_ن.أ"] for r in rows])
        c = np.array([r["التكلفة_ن.أ"] for r in rows]); p = np.array([r["الاستمرار"] for r in rows])
        out["ارتباط_الدفعة"] = round(float(np.corrcoef(x, y)[0, 1]), 4) if len(rows) > 30 and x.std() > 0 and y.std() > 0 else None
        out["نطاق_الصدفة"] = round(2 / math.sqrt(len(rows)), 4)
        out["محاكاة_الدفعة_بعد_السبريد_ن.أ"] = round(float(np.mean(np.sign(x) * y - c)), 2)
        out["محاكاة_الدفعة_المجموع_ن.أ"] = round(float(np.sum(np.sign(x) * y - c)), 1)
        hi, lo = p >= PER_MIN, p < PER_MIN
        out["اتّباع_الصافي_استمرار_عالٍ"] = round(float(np.mean(y[hi] - c[hi])), 2) if hi.any() else None
        out["اتّباع_الصافي_استمرار_منخفض"] = round(float(np.mean(y[lo] - c[lo])), 2) if lo.any() else None
        out["عدد_عالٍ_منخفض"] = "%d / %d" % (int(hi.sum()), int(lo.sum()))
        p2 = np.array([np.nan if r["الاستمرار_200"] is None else r["الاستمرار_200"] for r in rows])
        ok2 = np.isfinite(p2)
        for name, xs, m in (("ارتباط_الاستمرار_25", p, np.ones(len(p), bool)), ("ارتباط_الاستمرار_200", p2, ok2)):
            out[name] = (round(float(np.corrcoef(xs[m], y[m])[0, 1]), 4)
                         if m.sum() > 30 and xs[m].std() > 0 and y[m].std() > 0 else None)
    json.dump({"الخلاصة": out, "العيّنات": rows}, open(os.path.join(HERE, "records.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    L = ["# سجلّ الزخم الأماميّ — ناسداك ساعةً بساعة من %s (بلا تداول، ختم «Nq» ١٠-١٣)" % out["من"], "",
         "آخر تحديث: %s · عيّنات: %d (كلّ 5 ساعات بلا تداخل). الدفعة المحاذية موجبة = آخر شمعة مع صافي الحركة. الهدف = الساعات الخمس التالية في جهة الصافي." % (
             out["آخر_تحديث"], out["عيّنات"]), "",
         "- **ارتباط الدفعة المحاذية بالهدف:** %s (نطاق الصدفة ±%s) — التاريخ: +0.028 / +0.035 / +0.059" % (out.get("ارتباط_الدفعة"), out.get("نطاق_الصدفة")),
         "- **محاكاة «اتّبع إشارة الدفعة» بعد السبريد:** %s ن.أ للعيّنة · المجموع %s ن.أ — التاريخ (الامتحان): −0.50" % (
             out.get("محاكاة_الدفعة_بعد_السبريد_ن.أ"), out.get("محاكاة_الدفعة_المجموع_ن.أ")),
         "- **اتّباع الصافي بعد السبريد:** استمرار عالٍ %s · منخفض %s ن.أ (العدد %s)" % (
             out.get("اتّباع_الصافي_استمرار_عالٍ"), out.get("اتّباع_الصافي_استمرار_منخفض"), out.get("عدد_عالٍ_منخفض")),
         "- **ارتباط الاستمرار بالهدف (١٠-١٤):** نافذة 25: %s · نافذة 200 (الحيّة منذ ١٠-١٤): %s — التاريخ على الساعة: +0.012 مقابل +0.049 (البناء)" % (
             out.get("ارتباط_الاستمرار_25"), out.get("ارتباط_الاستمرار_200")), "",
         "| الساعة (غ) | صافي الحركة ٪ | الدفعة المحاذية | الاستمرار | الأفق في جهة الصافي ن.أ |", "|---|---|---|---|---|"]
    for r in rows[-LAST:][::-1]:
        L.append("| %s | %s | %s | %s | %s |" % (r["الساعة"], r["صافي_الحركة_٪"], r["الدفعة_المحاذية"], r["الاستمرار"], r["الأفق_في_جهة_الصافي_ن.أ"]))
    open(os.path.join(HERE, "سجلّ الزخم الأماميّ.md"), "w", encoding="utf-8").write("\n".join(L) + "\n")
    print(out["آخر_تحديث"], "عيّنات:", out["عيّنات"], flush=True)


if __name__ == "__main__":
    main()
