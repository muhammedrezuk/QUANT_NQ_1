# -*- coding: utf-8 -*-
"""فحص بيانات مخزن سي‑تريدر — شموع الدقيقة لكلّ رمز (المالك ١٠-١٣: «هذا الفحص للبيانات»؛ فيديو اليوم الحادي عشر: «خلّي المشكلة تطلع قدّامنا»).

لكلّ رمز: المدى وعدد الشموع، ثمّ ستّة عيوب:
① شموعٌ مستحيلة: أعلى < أدنى، أو الإغلاق/الافتتاح خارج المدى، أو سعرٌ ≤ صفر.
② أيّامٌ ناقصة: يوم عملٍ (والبتكوين كلّ يوم) شموعه أقلّ من 80٪ من وسيط أيّام سنته — قد يكون عطلةً رسميّة أو انقطاعًا.
③ أيّام عملٍ بلا شمعةٍ واحدة.
④ فجوات: أكثر من 90 دقيقة بين شمعتين خارج عطلة نهاية الأسبوع (للبتكوين: أيّ فجوة).
⑤ قفزاتٌ شاذّة: حركة دقيقة > 15 ضعف انحراف الساعة السابقة **ثمّ عودةٌ** في الدقيقة التالية (أكثر من نصفها) — شكل التِّكّة الخاطئة.
⑥ فتراتٌ جامدة: 30 دقيقة فأكثر متتالية بالإغلاق نفسه والأعلى = الأدنى — تغذيةٌ متوقّفة تتظاهر بأنّها سوق.
المخرج: «فحص البيانات.md» و audit.json. قراءةٌ فقط.
"""
import json
import os
import sqlite3
import sys
import time
from collections import Counter, defaultdict

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
if sys.stdout is None or sys.stderr is None:
    sys.stdout = sys.stderr = open(os.path.join(HERE, "run.log"), "a", encoding="utf-8")
sys.stdout.reconfigure(encoding="utf-8")
HIST = "file:C:/Users/NQ/QUANT_NQ/forex_runtime/var/history/ctrader_history.db?mode=ro"
SYMBOLS = ("USTEC", "US30", "US500", "XAUUSD", "BTCUSD")
ALL_DAYS = {"BTCUSD"}
SHORT_FRAC = 0.8
GAP_S = 90 * 60
SPIKE_SIGMA = 15.0
SPIKE_WIN = 60
FROZEN_MIN = 30
TOP = 12


def day_str(t):
    return time.strftime("%Y-%m-%d", time.gmtime(t))


def audit(con, sym):
    a = np.array(con.execute("select period_start, open, high, low, close from candles_history where symbol=? and period='M1' "
                             "order by period_start", (sym,)).fetchall(), dtype=float)
    if not len(a):
        return {"شموع": 0}
    ts, o, h, l, c = a.T
    out = {"شموع": int(len(ts)), "من": day_str(ts[0]), "إلى": day_str(ts[-1])}
    bad = (h < l) | (c > h + 1e-9) | (c < l - 1e-9) | (o > h + 1e-9) | (o < l - 1e-9) | (l <= 0)
    out["مستحيلة"] = int(bad.sum())
    out["أمثلة_مستحيلة"] = [time.strftime("%Y-%m-%d %H:%M", time.gmtime(t)) for t in ts[bad][:5]]
    days = (ts // 86400).astype(np.int64)
    per_day = Counter(days.tolist())
    all_week = sym in ALL_DAYS
    by_year = defaultdict(list)
    for d, n in per_day.items():
        wd = time.gmtime(d * 86400).tm_wday
        if all_week or wd < 5:
            by_year[time.gmtime(d * 86400).tm_year].append(n)
    med = {y: float(np.median(v)) for y, v in by_year.items()}
    short = []
    for d, n in per_day.items():
        g = time.gmtime(d * 86400)
        if (all_week or g.tm_wday < 5) and n < SHORT_FRAC * med.get(g.tm_year, n):
            short.append((day_str(d * 86400), n, int(med[g.tm_year])))
    short.sort(key=lambda x: x[1])
    out["أيّام_ناقصة"] = len(short)
    out["أسوأ_الناقصة"] = short[:TOP]
    first, last = int(days[0]), int(days[-1])
    empty = [day_str(d * 86400) for d in range(first, last + 1)
             if (all_week or time.gmtime(d * 86400).tm_wday < 5) and d not in per_day]
    out["أيّام_بلا_شمعة"] = len(empty)
    out["أمثلة_بلا_شمعة"] = empty[:TOP]
    dt = np.diff(ts)
    gaps = []
    for k in np.nonzero(dt > GAP_S)[0]:
        g0 = time.gmtime(ts[k])
        weekend = (not all_week) and (g0.tm_wday == 4 and g0.tm_hour >= 19 or g0.tm_wday >= 5 or
                                       (time.gmtime(ts[k + 1]).tm_wday == 6) or dt[k] > 40 * 3600)
        if not weekend:
            gaps.append((time.strftime("%Y-%m-%d %H:%M", g0), round(float(dt[k]) / 60)))
    gaps.sort(key=lambda x: -x[1])
    out["فجوات"] = len(gaps)
    out["أكبر_الفجوات_دقائق"] = gaps[:TOP]
    r = np.zeros(len(c))
    r[1:] = np.log(c[1:] / c[:-1])
    adj = np.r_[False, dt == 60]
    csum = np.cumsum(np.r_[0.0, r ** 2])
    spikes = []
    for k in range(SPIKE_WIN + 1, len(r) - 1):
        if not (adj[k] and adj[k + 1]):
            continue
        var = (csum[k] - csum[k - SPIKE_WIN]) / SPIKE_WIN
        if var <= 0:
            continue
        sd = var ** 0.5
        if abs(r[k]) > SPIKE_SIGMA * sd and r[k + 1] * r[k] < 0 and abs(r[k + 1]) > 0.5 * abs(r[k]):
            spikes.append((time.strftime("%Y-%m-%d %H:%M", time.gmtime(ts[k])), round(float(r[k]) * 1e4, 1), round(float(abs(r[k]) / sd), 1)))
    spikes.sort(key=lambda x: -abs(x[1]))
    out["قفزات_شاذّة"] = len(spikes)
    out["أكبر_القفزات_ن.أ"] = spikes[:TOP]
    flat = (h == l)
    same = np.r_[False, (c[1:] == c[:-1]) & (dt == 60)]
    frozen, run, start = [], 0, 0
    for k in range(len(c)):
        if flat[k] and same[k]:
            if run == 0:
                start = k - 1
            run += 1
        else:
            if run + 1 >= FROZEN_MIN:
                frozen.append((time.strftime("%Y-%m-%d %H:%M", time.gmtime(ts[start])), run + 1))
            run = 0
    frozen.sort(key=lambda x: -x[1])
    out["فترات_جامدة"] = len(frozen)
    out["أطول_الجامدة_دقائق"] = frozen[:TOP]
    return out


def main():
    t0 = time.time()
    con = sqlite3.connect(HIST, uri=True)
    res = {s: audit(con, s) for s in SYMBOLS}
    con.close()
    out = {"التصميم": __doc__, "الرموز": res, "المدّة_ث": round(time.time() - t0, 1)}
    json.dump(out, open(os.path.join(HERE, "audit.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    L = ["# فحص بيانات مخزن سي‑تريدر — شموع الدقيقة (١٠-١٣)", "",
         "| الرمز | المدى | شموع | مستحيلة | أيّام ناقصة | أيّام عملٍ بلا شمعة | فجوات > 90 د | قفزات شاذّة | فترات جامدة ≥ 30 د |",
         "|---|---|---|---|---|---|---|---|---|"]
    for s, r in res.items():
        L.append("| %s | %s ⟵ %s | %s | %s | %s | %s | %s | %s | %s |" % (s, r.get("من"), r.get("إلى"), r["شموع"], r.get("مستحيلة"),
                                                                    r.get("أيّام_ناقصة"), r.get("أيّام_بلا_شمعة"), r.get("فجوات"),
                                                                    r.get("قفزات_شاذّة"), r.get("فترات_جامدة")))
    for s, r in res.items():
        L += ["", "## %s" % s, "",
              "- **أسوأ الأيّام الناقصة (اليوم · شموعه · وسيط سنته):** " + " · ".join("%s (%s/%s)" % x for x in r.get("أسوأ_الناقصة", [])),
              "- **أيّام عملٍ بلا شمعة:** " + " · ".join(r.get("أمثلة_بلا_شمعة", [])),
              "- **أكبر الفجوات (البداية · دقائق):** " + " · ".join("%s (%s)" % x for x in r.get("أكبر_الفجوات_دقائق", [])),
              "- **أكبر القفزات الشاذّة (الوقت · ن.أ · أضعاف الانحراف):** " + " · ".join("%s (%s، ×%s)" % x for x in r.get("أكبر_القفزات_ن.أ", [])),
              "- **أطول الفترات الجامدة (البداية · دقائق):** " + " · ".join("%s (%s)" % x for x in r.get("أطول_الجامدة_دقائق", [])),
              "- **شموعٌ مستحيلة (أمثلة):** " + " · ".join(r.get("أمثلة_مستحيلة", []))]
    L += ["", "المدّة: %s ث." % out["المدّة_ث"]]
    open(os.path.join(HERE, "فحص البيانات.md"), "w", encoding="utf-8").write("\n".join(L) + "\n")
    print("انتهى", out["المدّة_ث"], "ث", flush=True)


if __name__ == "__main__":
    main()
