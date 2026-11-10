# -*- coding: utf-8 -*-
"""طبيعة سلسلة الناسداك — دراسةٌ وصفيّة أساسيّة (الخطوة 1 من «العمل على ما بين أيدينا»، ختم المالك «nq» ٢٠٢٦-١٠-١٣).

الأسئلة (فيديو «ما هو السوق؟»): هل الحركة عشوائيّة؟ هل يؤثّر الماضي في المستقبل؟ هل التقلّب ثابت؟ ما شكل التوزيع وأطرافه؟
البيانات: شموع دقيقة الناسداك (USTEC M1) من مخزن سي‑تريدر، 2014-07 ⟵ اليوم. العائد لوغاريتميّ بنقطة الأساس.
الآفاق: دقيقة · 5 د · 15 د · ساعة · 4 س (حاويات ساعة غرينتش، متجاورةٌ فقط — لا عبور فجوة) · يوم (أيّام التداول المتتالية).
الحقب: 2014-07⟵2019 · 2020⟵2024 · 2025⟵2026.

ما يُحسب لكلّ أفقٍ وحقبة: العدد · المتوسّط · الانحراف · ارتباط العائد بالذي قبله (فجوة 1 و2 و5) ونطاق الصدفة ±2/√ن · نسبة تتابع
الإشارة نفسها · ارتباط حجم الحركة بالذي قبله (بقاء التقلّب، فجوة 1 و10) · الالتواء والتفلطح الزائد · نسبة الحركات أكبر من 3 و5 انحرافات
(الطبيعيّ: 0.27٪ و0.00006٪) · «الجزء المتوقَّع» = |الارتباط| × الانحراف مقابل التكلفة (سبريد 1.5 نقطة ÷ متوسّط السعر).
وتقلّب 5 د حسب ساعة نيويورك.

قراءةٌ مكتوبة قبل النتائج: الارتباط «له معنى» إن خرج من نطاق الصدفة **في الحقب الثلاث بالإشارة نفسها**؛ و«قابلٌ للتداول» إن تجاوز
الجزء المتوقَّع التكلفة في الحقب الثلاث. ما سوى ذلك وصفٌ لا ميزة. قياسٌ فقط: لا يمسّ الحيّ.
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
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
if sys.stdout is None or sys.stderr is None:
    sys.stdout = sys.stderr = open(os.path.join(HERE, "run.log"), "a", encoding="utf-8")
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, ROOT)
from shared.market_clock import CITY_NEW_YORK, local_time  # noqa: E402

HIST = "file:C:/Users/NQ/QUANT_NQ/forex_runtime/var/history/ctrader_history.db?mode=ro"
HORIZONS = (("دقيقة", 1), ("5 د", 5), ("15 د", 15), ("ساعة", 60), ("4 س", 240))
ERAS = (("2014–2019", 0, calendar.timegm((2020, 1, 1, 0, 0, 0))),
        ("2020–2024", calendar.timegm((2020, 1, 1, 0, 0, 0)), calendar.timegm((2025, 1, 1, 0, 0, 0))),
        ("2025–2026", calendar.timegm((2025, 1, 1, 0, 0, 0)), 1e12))
LAGS = (1, 2, 5)
ABS_LAGS = (1, 10)
SPREAD_PTS = 1.5
DAY = 86400


def load():
    con = sqlite3.connect(HIST, uri=True)
    a = np.array(con.execute("select period_start, close from candles_history where symbol='USTEC' and period='M1' "
                             "order by period_start").fetchall(), dtype=float)
    con.close()
    return a[:, 0], a[:, 1]


def bucketed(ts, cl, minutes):
    """آخر إغلاقٍ في كلّ حاوية؛ العائد بين حاويتين متجاورتين فقط. يعيد: رقم حاوية بدء العائد، وقته، العائد بنقطة الأساس."""
    b = np.floor(ts / (minutes * 60)).astype(np.int64)
    last = np.r_[np.nonzero(np.diff(b))[0], len(b) - 1]
    B, C, T = b[last], cl[last], ts[last]
    ok = np.diff(B) == 1
    r = np.log(C[1:] / C[:-1]) * 1e4
    return B[:-1][ok], T[:-1][ok], r[ok]


def daily(ts, cl):
    d = np.floor(ts / DAY).astype(np.int64)
    last = np.r_[np.nonzero(np.diff(d))[0], len(d) - 1]
    C, T = cl[last], ts[last]
    r = np.log(C[1:] / C[:-1]) * 1e4
    return np.arange(len(r), dtype=np.int64), T[:-1], r          # أيّام التداول المتتالية متجاورةٌ بالتعريف


def lag_corr(B, x, k):
    """ارتباط x[i] بـ x[i+k] حيث الحاويات متتالية فعلًا (B[i+k] − B[i] = k)."""
    if len(x) <= k:
        return None, 0
    m = (B[k:] - B[:-k]) == k
    a, c = x[:-k][m], x[k:][m]
    if len(a) < 30 or a.std() == 0 or c.std() == 0:
        return None, len(a)
    return float(np.corrcoef(a, c)[0, 1]), int(len(a))


def describe(B, r, price):
    n = len(r)
    if n < 100:
        return {"n": n}
    sd = float(r.std())
    z = (r - r.mean()) / sd
    out = {"n": n, "متوسّط": round(float(r.mean()), 3), "انحراف": round(sd, 2),
           "التواء": round(float((z ** 3).mean()), 2), "تفلطح_زائد": round(float((z ** 4).mean() - 3), 1),
           "أكبر_من_3": round(float(np.mean(np.abs(z) > 3)) * 100, 3), "أكبر_من_5": round(float(np.mean(np.abs(z) > 5)) * 100, 4)}
    for k in LAGS:
        c, m = lag_corr(B, r, k)
        out["ارتباط_%d" % k] = None if c is None else round(c, 4)
        out["نطاق_%d" % k] = round(2 / math.sqrt(m), 4) if m else None
    s = np.sign(r)
    adj = (B[1:] - B[:-1]) == 1
    both = adj & (s[1:] != 0) & (s[:-1] != 0)
    out["تتابع_الإشارة"] = round(float(np.mean(s[1:][both] == s[:-1][both])) * 100, 1) if both.any() else None
    for k in ABS_LAGS:
        c, _ = lag_corr(B, np.abs(r), k)
        out["بقاء_التقلّب_%d" % k] = None if c is None else round(c, 3)
    cost = SPREAD_PTS / price * 1e4
    out["التكلفة"] = round(cost, 2)
    if out.get("ارتباط_1") is not None:
        out["المتوقَّع"] = round(abs(out["ارتباط_1"]) * sd, 2)
    return out


def ny_hours(T):
    days = np.floor(T / DAY).astype(np.int64)
    offs = {}
    for d in np.unique(days):
        noon = float(d) * DAY + DAY / 2
        lt = local_time(noon, CITY_NEW_YORK)
        offs[int(d)] = (lt.hour + lt.minute / 60.0) - 12.0
    off = np.array([offs[int(d)] for d in days])
    return np.floor(((T % DAY) / 3600.0 + off) % 24).astype(int)


def main():
    t0 = time.time()
    ts, cl = load()
    out = {"التصميم": __doc__, "من": time.strftime("%Y-%m-%d", time.gmtime(ts[0])), "إلى": time.strftime("%Y-%m-%d", time.gmtime(ts[-1])),
           "شموع": int(len(ts)), "الآفاق": {}}
    series = [(name, bucketed(ts, cl, m)) for name, m in HORIZONS] + [("يوم", daily(ts, cl))]
    for name, (B, T, r) in series:
        res = {}
        for era, a, b in ERAS:
            m = (T >= a) & (T < b)
            pm = (ts >= a) & (ts < b)
            res[era] = describe(B[m], r[m], float(cl[pm].mean()) if pm.any() else float(cl.mean()))
        out["الآفاق"][name] = res
    B5, T5, r5 = series[1][1]
    hours = ny_hours(T5)
    out["تقلّب_5د_حسب_ساعة_نيويورك"] = {}
    for era, a, b in ERAS:
        m = (T5 >= a) & (T5 < b)
        out["تقلّب_5د_حسب_ساعة_نيويورك"][era] = {int(h): round(float(r5[m & (hours == h)].std()), 2)
                                                  for h in range(24) if (m & (hours == h)).sum() > 200}
    out["المدّة_ث"] = round(time.time() - t0, 1)
    json.dump(out, open(os.path.join(HERE, "results.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    report(out)
    print("انتهى في", out["المدّة_ث"], "ث", flush=True)


def report(out):
    L = ["# طبيعة سلسلة الناسداك — دراسة وصفيّة (ختم «nq» ٢٠٢٦-١٠-١٣)", "",
         "شموع دقيقة %s من %s إلى %s. العائد بنقطة الأساس (100 = 1٪). «ارتباط ١» = ارتباط العائد بالذي قبله مباشرةً؛ «نطاق» = حدّ الصدفة"
         " (داخله = لا علاقة). «تتابع» = نسبة تكرار الإشارة نفسها (50 = عشوائيّ). «بقاء التقلّب» = ارتباط حجم الحركة بحجم التي قبلها."
         " «المتوقَّع» = |ارتباط ١| × الانحراف، يُقارَن بـ«التكلفة» (سبريد 1.5 نقطة)." % (out["شموع"], out["من"], out["إلى"]), "",
         "| الأفق | الحقبة | عدد | انحراف | ارتباط ١ (نطاق) | ارتباط ٢ | ارتباط ٥ | تتابع | بقاء التقلّب ١ / ١٠ | التواء | تفلطح زائد | >3σ ٪ | >5σ ٪ | المتوقَّع / التكلفة |",
         "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for h, res in out["الآفاق"].items():
        for era, r in res.items():
            if r.get("n", 0) < 100:
                continue
            L.append("| %s | %s | %d | %s | %s (±%s) | %s | %s | %s | %s / %s | %s | %s | %s | %s | %s / %s |" % (
                h, era, r["n"], r["انحراف"], r.get("ارتباط_1"), r.get("نطاق_1"), r.get("ارتباط_2"), r.get("ارتباط_5"),
                r.get("تتابع_الإشارة"), r.get("بقاء_التقلّب_1"), r.get("بقاء_التقلّب_10"), r["التواء"], r["تفلطح_زائد"],
                r["أكبر_من_3"], r["أكبر_من_5"], r.get("المتوقَّع"), r.get("التكلفة")))
    L += ["", "## تقلّب 5 دقائق حسب ساعة نيويورك (انحراف بنقطة الأساس)", ""]
    for era, hs in out["تقلّب_5د_حسب_ساعة_نيويورك"].items():
        L.append("- **%s:** " % era + " · ".join("%02d: %s" % (h, v) for h, v in sorted(hs.items())))
    L += ["", "المدّة: %s ث. الأرقام الكاملة في results.json." % out["المدّة_ث"]]
    open(os.path.join(HERE, "التقرير.md"), "w", encoding="utf-8").write("\n".join(L) + "\n")


if __name__ == "__main__":
    main()
