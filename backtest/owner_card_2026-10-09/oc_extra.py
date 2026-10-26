# -*- coding: utf-8 -*-
"""المرحلة 3: مطابقة المسطرة الأصليّة · محاذاة الصفقات للعرّاف (دقّة التعادل) · لماذا لم تُطلق البطاقة عند صفقات المالك."""
import sys
sys.dont_write_bytecode = True
sys.stdout.reconfigure(encoding="utf-8")
import bisect
import calendar
import json
import os
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import oc_core as C

HERE = C.HERE
RES = json.load(open(os.path.join(HERE, "results.json"), encoding="utf-8"))
SESS = {k: C.cached("sess_%s.pkl" % k, lambda: C.session_days(k))[0] for k in ("lon", "ny")}
EV = {k: C.cached("ev_%s_pts_base.pkl" % k, lambda: None)[0] for k in ("lon", "ny")}
SELK = {"lon": RES["لندن|نقاط"]["المختارة"]["التركيبة"], "ny": RES["أمريكا|نقاط"]["المختارة"]["التركيبة"]}


def parse(key):
    d, trig, k, n = key.split("|")
    return d, trig, float(k[1:]), int(n)


EXTRA = {}

# ───────── ١) محاذاة الصفقات لجهة النافذة الحقيقيّة (العرّاف) ─────────
al = {}
for kind, lab in (("lon", "لندن"), ("ny", "أمريكا")):
    d0, trig, K, maxn = parse(SELK[kind])
    out = {}
    for m in C.DMODES:
        tr, _ = C.run(SESS[kind], EV[kind], m, trig, K, maxn)
        both = [x for x in tr if x[12] != 0]
        A = [x[1] for x in both if x[3] == (x[12] > 0)]
        B = [x[1] for x in both if x[3] != (x[12] > 0)]
        a = sum(A) / len(A) if A else None
        b = sum(B) / len(B) if B else None
        out[m] = {"صفقات": len(both), "محاذية%": round(100 * len(A) / max(1, len(both)), 1),
                  "R/صفقة_المحاذية": a and round(a, 3), "R/صفقة_المعاكسة": b and round(b, 3),
                  "دقّة_التعادل%": round(100 * (-b) / (a - b), 1) if (a is not None and b is not None and a != b) else None}
    al[lab] = {"العيار": "%s|ك%.1f|%d" % (trig, K, maxn), "الجهات": out}
EXTRA["محاذاة_العرّاف"] = al
print(json.dumps(al, ensure_ascii=False, indent=0), flush=True)

# ───────── ٢) لماذا لم تُطلق: صفقات المالك الـ33 ─────────
OWNER = [
    (6, 1, 11, 57, 1, 30448.45), (6, 1, 12, 8, 1, 30426.20), (6, 1, 14, 16, 1, 30346.45), (6, 2, 16, 42, 1, 30635.95),
    (6, 3, 5, 33, 1, 30682.55), (6, 3, 6, 14, 1, 30670.80), (6, 4, 19, 13, 1, 30542.95), (6, 4, 19, 26, 0, 30564.30),
    (6, 8, 7, 47, 1, 29245.80), (6, 9, 6, 18, 0, 29675.30), (6, 10, 5, 33, 1, 28929.45), (6, 10, 5, 40, 0, 28934.80),
    (6, 10, 5, 44, 1, 28921.70), (6, 10, 5, 47, 1, 28915.45), (6, 11, 6, 41, 0, 28774.30), (6, 11, 6, 52, 1, 28781.95),
    (3, 11, 1, 18, 0, 25051.80), (3, 11, 3, 47, 0, 25087.30), (3, 12, 5, 51, 1, 24715.22), (3, 13, 10, 16, 0, 24572.88),
    (3, 13, 10, 33, 1, 24564.32), (3, 13, 13, 54, 0, 24758.68), (3, 16, 14, 45, 1, 24641.50), (3, 16, 14, 58, 0, 24660.30),
    (3, 16, 15, 20, 0, 24693.60), (3, 17, 14, 47, 0, 24847.00), (3, 18, 14, 20, 1, 24689.84), (3, 18, 14, 27, 1, 24619.39),
    (3, 19, 18, 52, 1, 24236.36), (3, 19, 19, 25, 0, 24393.66), (3, 20, 16, 39, 1, 24068.09), (3, 23, 15, 10, 1, 24483.01),
    (3, 23, 15, 21, 1, 24417.01)]
P = C.BASEP
rows, summ = [], Counter()
for mo, d, hh, mm, buy, px in OWNER:
    buy = bool(buy)
    off = 45.0 if mo == 6 else 0.0
    t = calendar.timegm((2026, mo, d, hh, mm, 0))
    ours = px - off
    # المناطق في جهته عند ساعته
    hb = t - t % 3600
    zl = C.zones_at(hb, buy, P["tol"], P["ndays"], P["wmin"])
    zo = C.zones_at(hb, not buy, P["tol"], P["ndays"], P["wmin"])

    def dist(z):
        w = z[1] - z[0]
        lo, hi = (z[0] - 0.5 * w, z[1]) if buy else (z[0], z[1] + 0.5 * w)
        return 0.0 if lo <= ours <= hi else min(abs(ours - lo), abs(ours - hi))
    near_z = min((dist(z) for z in zl), default=None)
    # الدقائق ±15 حول دخوله
    k0, k1 = bisect.bisect_left(C.MT, t - 900), bisect.bisect_right(C.MT, t + 900) - 1
    touch = recent = slap = choke = 0
    best_ratio = None
    for k in range(k0, k1 + 1):
        tc = C.MT[k] + 60
        z_here = C.zones_at(tc - tc % 3600, buy, P["tol"], P["ndays"], P["wmin"])
        ext = min(C.ML[k - 2], C.ML[k - 1], C.ML[k]) if buy else max(C.MH[k - 2], C.MH[k - 1], C.MH[k])
        hit = None
        for z in z_here:
            w = z[1] - z[0]
            if (z[0] - 0.5 * w <= ext <= z[1]) if buy else (z[0] <= ext <= z[1] + 0.5 * w):
                hit = z
        if not hit:
            continue
        touch += 1
        kw = bisect.bisect_left(C.MT, tc - P["m"] * 60)
        seg = range(kw, k + 1)
        istar = (min(seg, key=lambda i: (C.ML[i], -i)) if buy else max(seg, key=lambda i: (C.MH[i], i)))
        if istar >= k - 2:
            recent += 1
            a5 = C.A5[bisect.bisect_right(C.T5, tc - 300) - 1]
            mv = (max(C.MH[kw:istar + 1]) - C.ML[istar]) if buy else (C.MH[istar] - min(C.ML[kw:istar + 1]))
            best_ratio = max(best_ratio or 0, mv / a5)
    # شراسة الحركة إلى دخوله (30 د قبل دقيقته)
    kd = bisect.bisect_left(C.MT, t)
    kw = bisect.bisect_left(C.MT, t - 1800)
    a5 = C.A5[bisect.bisect_right(C.T5, t - 300) - 1]
    if buy:
        mv = max(C.MH[kw:kd + 1]) - min(C.ML[kw:kd + 1])
        frac_low = (ours - min(C.ML[kw:kd + 1])) / max(1e-9, max(C.MH[kw:kd + 1]) - min(C.ML[kw:kd + 1]))
    else:
        mv = max(C.MH[kw:kd + 1]) - min(C.ML[kw:kd + 1])
        frac_low = (max(C.MH[kw:kd + 1]) - ours) / max(1e-9, mv)
    row = {"الوقت_غ": "%02d-%02d %02d:%02d" % (mo, d, hh, mm), "جهته": "شراء" if buy else "بيع",
           "مناطق_في_جهته": len(zl), "مناطق_معاكسة": len(zo),
           "بُعد_سعره_عن_أقرب_منطقة": None if near_z is None else round(near_z, 1),
           "دقائق_لمس_±15": touch, "لمس_بقاع_حديث": recent, "أعلى_نسبة_شراسة_عند_اللمس": best_ratio and round(best_ratio, 2),
           "مدى_30د_قبله÷مدى5د": round(mv / a5, 2), "موضع_سعره_من_مدى_30د%": round(100 * frac_low)}
    rows.append(row)
    summ["بلا_منطقة_في_جهته"] += (len(zl) == 0)
    summ["سعره_ضمن_20_من_منطقة"] += (near_z is not None and near_z <= 20)
    summ["لمسٌ_ضمن_±15"] += (touch > 0)
    summ["لمسٌ_بقاع_حديث"] += (recent > 0)
EXTRA["لماذا_لم_تُطلق_عند_صفقاته"] = {"الملخّص_من_33": dict(summ), "الصفقات": rows}
print(json.dumps(EXTRA["لماذا_لم_تُطلق_عند_صفقاته"]["الملخّص_من_33"], ensure_ascii=False), flush=True)
for r in rows:
    print(json.dumps(r, ensure_ascii=False), flush=True)

# ───────── ٣) مطابقة المسطرة الأصليّة (R.thirds · R.swings · الشموع) ─────────
sys.path.insert(0, r"C:\Users\NQ\QUANT_NQ\backtest\card_414")
import card_replay as R  # noqa: E402  (يحمّل 2024-10 ⟶ للقراءة فقط)
ver = {}
n = same = 0
bad = []
for fname in ("trades_best_london.json", "trades_best_ny.json"):
    for x in json.load(open(os.path.join(HERE, fname), encoding="utf-8")):
        if x["t"] < R.START + 86400:
            continue
        k1 = bisect.bisect_right(R.t1, x["t"] - 60)
        r2, e2 = R.thirds(x["سعر_الدخول"], x["الوقف"], x["الهدف"], x["شراء"], k1)
        n += 1
        ok = r2 is not None and abs(r2 - x["R"]) < 1e-3 and e2 == x["خروج_t"]
        same += ok
        if not ok and len(bad) < 5:
            bad.append({"t": x["دخول_غ"], "R_محرّكي": x["R"], "R_المسطرة": r2, "خروج": [x["خروج_t"], e2]})
ver["الأثلاث"] = {"صفقات_مقارنة": n, "مطابقة": same, "أوّل_فروق": bad}
# شموع الدقيقة نفسها
i0 = bisect.bisect_left(C.MT, R.m1[0][0])
mism = sum(1 for j in range(0, len(R.m1), 997)
           if (C.MT[i0 + j], C.MO[i0 + j], C.MH[i0 + j], C.ML[i0 + j], C.MC[i0 + j]) != R.m1[j])
ver["شموع_الدقيقة_عيّنة"] = {"فحص": len(range(0, len(R.m1), 997)), "اختلاف": mism}
a = R.swings(R.h1, 3600)
b = [(c, p, h) for c, p, h, i in C.swings_idx(R.h1, 3600)]
ver["قمم_الساعة"] = {"المسطرة": len(a), "محرّكي": len(b), "مطابقة_حرفًا": a == b}
EXTRA["مطابقة_المسطرة"] = ver
print(json.dumps(ver, ensure_ascii=False), flush=True)

RES["إضافات"] = EXTRA
json.dump(RES, open(os.path.join(HERE, "results.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("تمّ", flush=True)
