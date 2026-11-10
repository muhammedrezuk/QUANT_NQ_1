# -*- coding: utf-8 -*-
"""فحص ثبات «ارتداد الأربع ساعات» على الناسداك — بأمر المالك ١٠-١٣ (نصّه: «شغّل فحص الثبات من دون تعديل الاستراتيجيّة أو اختيار إعدادات جديدة»).

الاختبار نفسه بلا تعديل (من momentum_tests.py): حاويات 4 ساعات · الزخم M = عائد آخر 10 شمعات · الأفق H = 5 شمعات (20 ساعة) · العيّنات كلّ 5 شمعات
بلا تداخلٍ في الهدف · الجهة من البناء 2014–2019 (−1) ⟸ الصفقة = عكس إشارة M. لا نافذة جديدة ولا مدّة جديدة ولا حدود جديدة.

المحاولات السابقة (سلامة الاختبار، القانون): الزخم ① 408 الحيّة على السنة −165 وحدة ② شبكة النوافذ +0.005 ≈ صفر ③ 24 اختبارًا (2014–2024):
اجتاز إطار 4 ساعات وحده بإشارة ارتداد ④ **هذا الفحص** (ثبات الاختبار ③ لا صيغة جديدة). والفكرة القريبة «ارتداد اليوم التالي»: ① الوصف (−0.051/−0.082/−0.218)
② فحص الثبات: لم يصمد (ذاب بعد قصّ الأطراف).

الفحوص بالترتيب (معيار القصّ مسبق: أطراف 1٪ من كلّ جهة في الزخم أو الهدف — نفس معيار فحص ارتداد اليوم):
 ١) الترتيب بدل القيم · ٢) قبل الاستبعاد وبعده · ٣) سنةً سنة: عدد الصفقات والصافي · ٤) أقصى تراجع، والتكاليف: سبريد نقطة + انزلاق نقطة عند الدخول ونقطة
 عند الخروج + تمويل الليلة من مواصفات الرمز في ميتاتريدر (قراءةٌ فقط؛ **سعر اليوم مطبَّقٌ على الماضي** — الفائدة كانت قرب الصفر 2014–2021) · ٥) المحاولات أعلاه.
الفترات: بناء 2014–2019 · امتحان 2020–2024 · ملموسة 2025–2026.

قاعدة الحكم (نصّ المالك، مُعرَّفةٌ هنا قبل التشغيل):
 • **صمد:** (أ) الارتباط بالترتيب في الامتحان سالبٌ وخارج الصدفة (±2/√ن) · (ب) وبعد القصّ سالبٌ وخارج الصدفة · (ج) لم يعتمد على سنةٍ واحدة: صافي الامتحان
   موجبٌ بعد حذف أفضل سنة، ونصف سنوات الامتحان على الأقلّ موجبة · (د) الصافي بعد كلّ التكاليف موجبٌ في الامتحان وفي الملموسة.
 • **صمد جزئيًّا:** (أ) و(ب) تحقّقا، وسقط (ج) أو (د).
 • **لم يصمد:** سقط (أ) أو (ب) — اختفى الأثر أو انعكس بتغيير القياس أو باستبعاد المتطرّف.
قياسٌ فقط.
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
    sys.stdout = sys.stderr = open(os.path.join(HERE, "run_robust4h.log"), "a", encoding="utf-8")
sys.stdout.reconfigure(encoding="utf-8")
HIST = "file:C:/Users/NQ/QUANT_NQ/forex_runtime/var/history/ctrader_history.db?mode=ro"
MINUTES, N, H, SIGN = 240, 10, 5, -1
SPREAD_PTS, SLIP_PTS_EACH = 1.0, 1.0
TRIM = 0.01
ROLL_SHIFT_S = 3 * 3600          # تبديل يوم الوسيط ≈ 21:00 غرينتش
PERIODS = (("بناء", 0, calendar.timegm((2020, 1, 1, 0, 0, 0))),
           ("امتحان", calendar.timegm((2020, 1, 1, 0, 0, 0)), calendar.timegm((2025, 1, 1, 0, 0, 0))),
           ("ملموسة", calendar.timegm((2025, 1, 1, 0, 0, 0)), 1e12))


def swap_info():
    try:
        import MetaTrader5 as mt5
        if not mt5.initialize():
            return {"خطأ": str(mt5.last_error())}
        s = mt5.symbol_info("USTEC")
        mt5.shutdown()
        if s is None:
            return {"خطأ": "لا مواصفات"}
        return {"swap_mode": int(s.swap_mode), "swap_long": float(s.swap_long), "swap_short": float(s.swap_short),
                "triple_day": int(s.swap_rollover3days), "point": float(s.point), "contract": float(s.trade_contract_size)}
    except Exception as e:  # noqa: BLE001
        return {"خطأ": "%s" % type(e).__name__}


def swap_bps(info, side, price, nights_list):
    """تمويل الصفقة بنقطة الأساس (موجب = ربح، سالب = كلفة). النمط 1 = نقاط لكلّ يوم؛ 5 و6 = فائدة سنويّة ٪. غير ذلك: صفر ويُعلَن."""
    mode = info.get("swap_mode")
    rate = info.get("swap_long") if side > 0 else info.get("swap_short")
    if rate is None:
        return 0.0
    total = 0.0
    for wd in nights_list:
        mult = 3 if wd == info.get("triple_day") else 1
        if mode == 1:
            total += rate * info["point"] / price * 1e4 * mult
        elif mode in (5, 6):
            total += rate / 100.0 / 360.0 * 1e4 * mult
    return total


def load():
    con = sqlite3.connect(HIST, uri=True)
    a = np.array(con.execute("select period_start, close from candles_history where symbol='USTEC' and period='M1' "
                             "order by period_start").fetchall(), dtype=float)
    con.close()
    return a[:, 0], a[:, 1]


def rows_4h(ts, cl):
    b = np.floor(ts / (MINUTES * 60)).astype(np.int64)
    last = np.r_[np.nonzero(np.diff(b))[0], len(b) - 1]
    B, T, C = b[last], ts[last], cl[last]
    out = []
    i = N
    while i + H < len(C):
        if B[i + H] - B[i - N] == N + H:
            out.append((T[i], T[i + H], math.log(C[i] / C[i - N]) * 1e4, math.log(C[i + H] / C[i]) * 1e4, C[i]))
            i += H
        else:
            i += 1
    return np.array(out)


def ranks(x):
    o = np.argsort(x, kind="mergesort")
    r = np.empty(len(x))
    r[o] = np.arange(len(x))
    return r


def corr(x, y):
    return float(np.corrcoef(x, y)[0, 1]) if len(x) > 30 and x.std() > 0 and y.std() > 0 else None


def nights(t0, t1):
    d0, d1 = int((t0 + ROLL_SHIFT_S) // 86400), int((t1 + ROLL_SHIFT_S) // 86400)
    return [time.gmtime(d * 86400).tm_wday for d in range(d0, d1)]   # يوم الأسبوع لكلّ تبديلٍ عُبر


def main():
    t0 = time.time()
    info = swap_info()
    R = rows_4h(*load())
    lo_m, hi_m = np.quantile(R[:, 2], [TRIM, 1 - TRIM])
    lo_f, hi_f = np.quantile(R[:, 3], [TRIM, 1 - TRIM])
    keep = (R[:, 2] > lo_m) & (R[:, 2] < hi_m) & (R[:, 3] > lo_f) & (R[:, 3] < hi_f)
    side = SIGN * np.sign(R[:, 2])
    gross = side * R[:, 3]
    cost = (SPREAD_PTS + 2 * SLIP_PTS_EACH) / R[:, 4] * 1e4
    fin = np.array([swap_bps(info, s, p, nights(a, b)) if s != 0 else 0.0 for s, p, a, b in zip(side, R[:, 4], R[:, 0], R[:, 1])])
    net = gross - cost + fin
    out = {"التصميم": __doc__, "التمويل_من_ميتاتريدر": info, "عيّنات": int(len(R)), "مستبعدة_بالقصّ": int((~keep).sum()), "الفترات": {}, "سنةً_سنة": {}}
    for p, a, b in PERIODS:
        m = (R[:, 0] >= a) & (R[:, 0] < b)
        mk = m & keep
        n, nk = int(m.sum()), int(mk.sum())
        x = R[m]
        eq = np.cumsum(net[m])
        dd = float((np.maximum.accumulate(np.r_[0, eq]) - np.r_[0, eq]).max()) if n else None
        out["الفترات"][p] = {
            "عدد": n, "نطاق": round(2 / math.sqrt(n), 4) if n else None,
            "بالقيم": None if n < 30 else round(corr(x[:, 2], x[:, 3]), 4),
            "بالترتيب": None if n < 30 else round(corr(ranks(x[:, 2]), ranks(x[:, 3])), 4),
            "بعد_القصّ": None if nk < 30 else round(corr(R[mk][:, 2], R[mk][:, 3]), 4), "عدد_بعد_القصّ": nk,
            "نطاق_بعد_القصّ": round(2 / math.sqrt(nk), 4) if nk else None,
            "متوسّط_قبل_التكاليف": round(float(gross[m].mean()), 2) if n else None,
            "التكلفة_سبريد_وانزلاق": round(float(cost[m].mean()), 2) if n else None,
            "التمويل": round(float(fin[m].mean()), 2) if n else None,
            "الصافي_للصفقة": round(float(net[m].mean()), 2) if n else None, "الصافي_المجموع": round(float(net[m].sum()), 0) if n else None,
            "الصافي_بعد_القصّ_للصفقة": round(float(net[mk].mean()), 2) if nk else None,
            "أقصى_تراجع_ن.أ": round(dd, 0) if dd is not None else None}
    for y in sorted({time.gmtime(t).tm_year for t in R[:, 0]}):
        m = np.array([time.gmtime(t).tm_year == y for t in R[:, 0]])
        out["سنةً_سنة"][y] = {"صفقات": int(m.sum()), "الصافي_المجموع": round(float(net[m].sum()), 0), "الصافي_للصفقة": round(float(net[m].mean()), 2)}
    T = out["الفترات"]["امتحان"]
    test_years = {y: v for y, v in out["سنةً_سنة"].items() if 2020 <= y <= 2024}
    best = max(test_years.items(), key=lambda kv: kv[1]["الصافي_المجموع"])
    without_best = sum(v["الصافي_المجموع"] for y, v in test_years.items() if y != best[0])
    pos_years = sum(1 for v in test_years.values() if v["الصافي_المجموع"] > 0)
    cond = {"أ_بالترتيب": T["بالترتيب"] is not None and T["بالترتيب"] < -T["نطاق"],
            "ب_بعد_القصّ": T["بعد_القصّ"] is not None and T["بعد_القصّ"] < -T["نطاق_بعد_القصّ"],
            "ج_لا_سنة_واحدة": without_best > 0 and pos_years * 2 >= len(test_years),
            "د_صافٍ_موجب": T["الصافي_للصفقة"] > 0 and out["الفترات"]["ملموسة"]["الصافي_للصفقة"] > 0}
    out["الشروط"] = cond
    out["تفصيل_ج"] = {"أفضل_سنة": best[0], "صافي_الامتحان_بدونها": without_best, "سنوات_موجبة": "%d/%d" % (pos_years, len(test_years))}
    out["الحكم"] = ("صمد" if all(cond.values()) else "صمد جزئيًّا" if cond["أ_بالترتيب"] and cond["ب_بعد_القصّ"] else "لم يصمد")
    out["المدّة_ث"] = round(time.time() - t0, 1)
    json.dump(out, open(os.path.join(HERE, "robust_4h.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    L = ["# فحص ثبات «ارتداد الأربع ساعات» — بلا تعديل (١٠-١٣)", "", "**الحكم: %s.** الشروط: %s" % (
        out["الحكم"], " · ".join("%s %s" % (k, "✅" if v else "⛔") for k, v in cond.items())), "",
         "تفصيل (ج): أفضل سنة %s · صافي الامتحان بدونها %s ن.أ · سنوات موجبة %s." % (best[0], without_best, out["تفصيل_ج"]["سنوات_موجبة"]), "",
         "التمويل من ميتاتريدر: %s · عيّنات %d · مستبعدة بالقصّ %d." % (json.dumps(info, ensure_ascii=False), out["عيّنات"], out["مستبعدة_بالقصّ"]), "",
         "| الفترة | عدد | بالقيم | بالترتيب (نطاق) | بعد القصّ (نطاق) | قبل التكاليف | سبريد وانزلاق | تمويل | الصافي للصفقة | الصافي المجموع | الصافي بعد القصّ | أقصى تراجع |",
         "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for p, r in out["الفترات"].items():
        L.append("| %s | %s | %s | %s (±%s) | %s (±%s) | %s | %s | %s | %s | %s | %s | %s |" % (
            p, r["عدد"], r["بالقيم"], r["بالترتيب"], r["نطاق"], r["بعد_القصّ"], r["نطاق_بعد_القصّ"], r["متوسّط_قبل_التكاليف"],
            r["التكلفة_سبريد_وانزلاق"], r["التمويل"], r["الصافي_للصفقة"], r["الصافي_المجموع"], r["الصافي_بعد_القصّ_للصفقة"], r["أقصى_تراجع_ن.أ"]))
    L += ["", "| السنة | صفقات | الصافي المجموع ن.أ | الصافي للصفقة |", "|---|---|---|---|"]
    for y, v in out["سنةً_سنة"].items():
        L.append("| %s | %s | %s | %s |" % (y, v["صفقات"], v["الصافي_المجموع"], v["الصافي_للصفقة"]))
    L += ["", "المحاولات: الزخم ①–③ ثمّ هذا الفحص ④؛ وارتداد اليوم التالي ①–② (لم يصمد). المدّة: %s ث." % out["المدّة_ث"]]
    open(os.path.join(HERE, "ثبات ارتداد الأربع ساعات.md"), "w", encoding="utf-8").write("\n".join(L) + "\n")
    print("الحكم:", out["الحكم"], cond, flush=True)


if __name__ == "__main__":
    main()
