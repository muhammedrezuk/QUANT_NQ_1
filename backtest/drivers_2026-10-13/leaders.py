# -*- coding: utf-8 -*-
"""هل تقود الشركات الكبرى الناسداك؟ — المحاولة الأولى لهذه الفكرة (المالك ١٠-١٣: «قيس منها»). الخطوة 4 من «العمل على ما بين أيدينا».

البيانات: منصّة ميتاتريدر (حساب ICMarketsSC-Demo) — قراءةٌ فقط: لا اختيار رموز ولا تغيير ولا أوامر. شموع 5 دقائق لأبل · مايكروسوفت ·
إنفيديا · أمازون · جوجل · برودكوم · تسلا · ميتا (عقود فروقات أسهم)، والناسداك من المنصّة نفسها (توقيتٌ واحد). تُحفظ في mt5_bars.db.
السلّة = متوسّط عوائد الأسهم في الشمعة (حين تتوفّر 6 فأكثر — جلسة نيويورك).
الاختبارات (عددها مُعلَن: 3 × 3 = 9):
  أ) قيادة: ارتباط عائد السلّة في آخر k شمعة بعائد الناسداك في الـk التالية.
  ب) فجوة: ارتباط (عائد السلّة − عائد الناسداك) في آخر k بعائد الناسداك في الـk التالية — هل يلحق الناسداك سلّته؟
  ج) مرجع: ارتباط الناسداك بماضيه وحده.
  k = 1 · 3 · 12 شمعة (5 · 15 · 60 دقيقة)، والنوافذ لا تتداخل.
القسمة: أوّل 60٪ من الزمن ثمّ آخر 40٪ (لا شيء يُتعلَّم — القسمة للثبات).
الحكم الرئيس (مكتوبٌ قبل النتائج): (ب) عند k = 3 — «تقود» إن كان موجبًا وخارج نطاق الصدفة (±2/√ن) في القسمين، والجزء المتوقَّع
(|الارتباط| × انحراف الناسداك) أكبر من التكلفة (سبريد نقطة ÷ السعر) في القسمين؛ وإلّا «لا تقود بما يتجاوز التكلفة». قياسٌ فقط.
"""
import json
import math
import os
import sqlite3
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
if sys.stdout is None or sys.stderr is None:
    sys.stdout = sys.stderr = open(os.path.join(HERE, "run_leaders.log"), "a", encoding="utf-8")
sys.stdout.reconfigure(encoding="utf-8")
import MetaTrader5 as mt5  # noqa: E402

STOCKS = ("AAPL.NAS", "MSFT.NAS", "NVDA.NAS", "AMZN.NAS", "GOOG.NAS", "AVGO.NAS", "TSLA.NAS")  # ميتا الظاهرة عمرها 75 يومًا فاستُبعدت
INDEX = "USTEC"
FROM_YEAR = 2018                                   # المنصّة ترفض عددًا كبيرًا دفعةً واحدة («Invalid params») ⟸ شهرًا شهرًا
MIN_STOCKS = 6
KS = (1, 3, 12)
SPLIT = 0.6
SPREAD_PTS = 1.0
DB = os.path.join(HERE, "mt5_bars.db")


def fetch():
    if not mt5.initialize():
        raise SystemExit("تعذّر الاتّصال بالمنصّة: %s" % (mt5.last_error(),))
    con = sqlite3.connect(DB)
    con.execute("create table if not exists bars (symbol text, t integer, close real, primary key(symbol, t))")
    got = {}
    try:
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        months = [(y, m) for y in range(FROM_YEAR, now.year + 1) for m in range(1, 13) if (y, m) <= (now.year, now.month)]
        for s in STOCKS + (INDEX,):
            got[s] = 0
            for y, m in months:
                a = datetime(y, m, 1, tzinfo=timezone.utc)
                b = datetime(y + (m == 12), m % 12 + 1, 1, tzinfo=timezone.utc)
                r = mt5.copy_rates_range(s, mt5.TIMEFRAME_M5, a, b)
                if r is None or len(r) == 0:
                    continue
                con.executemany("insert or replace into bars values (?,?,?)", [(s, int(x["time"]), float(x["close"])) for x in r])
                got[s] += int(len(r))
            con.commit()
    finally:
        mt5.shutdown()
    return con, got


def series(con, s):
    a = np.array(con.execute("select t, close from bars where symbol=? order by t", (s,)).fetchall(), dtype=float)
    return a.reshape(-1, 2)


def corr(x, y):
    if len(x) < 50 or x.std() == 0 or y.std() == 0:
        return None
    return float(np.corrcoef(x, y)[0, 1])


def main():
    t0 = time.time()
    con, got = fetch()
    idx = series(con, INDEX)
    grid = idx[:, 0].astype(np.int64)
    pos = {int(t): i for i, t in enumerate(grid)}
    ix_close = idx[:, 1]
    ix_ret = np.full(len(grid), np.nan)
    ix_ret[1:] = np.where(np.diff(grid) == 300, np.log(ix_close[1:] / ix_close[:-1]) * 1e4, np.nan)
    stock_rets = []
    for s in STOCKS:
        a = series(con, s)
        if len(a) < 1000:
            continue
        r = np.full(len(grid), np.nan)
        t = a[:, 0].astype(np.int64)
        rr = np.where(np.diff(t) == 300, np.log(a[1:, 1] / a[:-1, 1]) * 1e4, np.nan)
        for tt, v in zip(t[1:], rr):
            j = pos.get(int(tt))
            if j is not None:
                r[j] = v
        stock_rets.append(r)
    S = np.vstack(stock_rets)
    count = np.sum(~np.isnan(S), axis=0)
    with np.errstate(all="ignore"):
        basket = np.where(count >= MIN_STOCKS, np.nanmean(S, axis=0), np.nan)
    ok = ~np.isnan(basket) & ~np.isnan(ix_ret)
    out = {"التصميم": __doc__, "الشموع_المجلوبة": got, "أسهم_مستعملة": len(stock_rets),
           "من": time.strftime("%Y-%m-%d", time.gmtime(int(grid[ok][0]))) if ok.any() else None,
           "إلى": time.strftime("%Y-%m-%d", time.gmtime(int(grid[ok][-1]))) if ok.any() else None,
           "شموع_الجلسة": int(ok.sum()), "النتائج": {}}
    ok_idx = np.nonzero(ok)[0]
    if len(ok_idx) < 500:
        out["الحكم"] = "بيانات غير كافية"
        return finish(out, t0)
    cut = grid[ok_idx[0]] + SPLIT * (grid[ok_idx[-1]] - grid[ok_idx[0]])
    price = float(np.nanmedian(ix_close))
    cost = SPREAD_PTS / price * 1e4
    main_ok = True
    for k in KS:
        rows = []
        i = ok_idx[0]
        while i + 2 * k < len(grid):
            past = slice(i, i + k)
            fut = slice(i + k, i + 2 * k)
            if grid[i + 2 * k - 1] - grid[i] == (2 * k - 1) * 300 and ok[past].all() and ok[fut].all():
                b, xp, xf = basket[past].sum(), ix_ret[past].sum(), ix_ret[fut].sum()
                rows.append((grid[i], b, xp, xf))
                i += 2 * k
            else:
                i += 1
        arr = np.array(rows) if rows else np.zeros((0, 4))
        res = {}
        for half, m in (("الأوّل 60٪", arr[:, 0] < cut), ("الأخير 40٪", arr[:, 0] >= cut)):
            sub = arr[m]
            n = len(sub)
            sd = float(sub[:, 3].std()) if n else 0.0
            cA, cB, cC = corr(sub[:, 1], sub[:, 3]), corr(sub[:, 1] - sub[:, 2], sub[:, 3]), corr(sub[:, 2], sub[:, 3])
            band = 2 / math.sqrt(n) if n else None
            res[half] = {"عدد": n, "أ_قيادة": cA, "ب_فجوة": cB, "ج_مرجع": cC, "نطاق": band, "انحراف_الناسداك": sd,
                         "متوقَّع_ب": abs(cB) * sd if cB is not None else None, "التكلفة": cost}
            res[half] = {kk: (round(v, 4) if isinstance(v, float) else v) for kk, v in res[half].items()}
            if k == 3:
                if not (cB is not None and band and cB > band and abs(cB) * sd > cost):
                    main_ok = False
        out["النتائج"]["%d د" % (k * 5)] = res
    out["الحكم"] = "تقود" if main_ok else "لا تقود بما يتجاوز التكلفة"
    finish(out, t0)


def finish(out, t0):
    out["المدّة_ث"] = round(time.time() - t0, 1)
    json.dump(out, open(os.path.join(HERE, "leaders.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    L = ["# هل تقود الشركات الكبرى الناسداك؟ (المحاولة الأولى، ١٠-١٣)", "", "**الحكم: %s.**" % out["الحكم"], "",
         "البيانات: %s ⟵ %s · شموع جلسة %s · أسهم %s · المجلوب: %s" % (out.get("من"), out.get("إلى"), out.get("شموع_الجلسة"),
                                                                   out.get("أسهم_مستعملة"), json.dumps(out["الشموع_المجلوبة"])), "",
         "أ = عائد السلّة الماضي ⟵ الناسداك القادم · ب = فجوة (السلّة − الناسداك) الماضية ⟵ الناسداك القادم · ج = الناسداك بماضيه. "
         "نطاق = حدّ الصدفة. المتوقَّع والتكلفة بنقطة الأساس.", "",
         "| الأفق | القسم | عدد | أ | ب | ج | نطاق | المتوقَّع (ب) / التكلفة |", "|---|---|---|---|---|---|---|---|"]
    for k, res in out.get("النتائج", {}).items():
        for half, r in res.items():
            L.append("| %s | %s | %s | %s | %s | %s | ±%s | %s / %s |" % (k, half, r["عدد"], r["أ_قيادة"], r["ب_فجوة"], r["ج_مرجع"],
                                                                     r["نطاق"], r["متوقَّع_ب"], r["التكلفة"]))
    L += ["", "المدّة: %s ث." % out["المدّة_ث"]]
    open(os.path.join(HERE, "قيادة الشركات.md"), "w", encoding="utf-8").write("\n".join(L) + "\n")
    print("الحكم:", out["الحكم"], "|", out["المدّة_ث"], "ث", flush=True)


if __name__ == "__main__":
    main()
