# -*- coding: utf-8 -*-
"""المرحلة 2: دقّة جهة الساعة وحدها · الشبكة والاختيار · الأساس والعرّاف · التشخيص · مراحل الأثلاث · التسريب ·
التشابه مع سجلّ المالك · الدمج مع 414 — بحسب prereg.json."""
import sys
sys.dont_write_bytecode = True
sys.stdout.reconfigure(encoding="utf-8")
import bisect
import calendar
import itertools
import json
import os
from collections import Counter

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import oc2_core as C

HERE = C.HERE
KINDS = {"lon": "لندن", "ny": "أمريكا"}
TRACKS = {"نقاط": "pts", "نسبيّ": "rel"}
TRIGS = ("S1", "S2", "كلاهما")
GRID = list(itertools.product(("هـ1", "هـ2"), TRIGS, (0, 1), (0, 1), C.KS))
assert len(GRID) == 48
SUB = list(itertools.product(TRIGS, (0, 1), (0, 1), C.KS))          # بلا محور الجهة (24) للأساس والعرّاف
MIN_LEARN, MIN_LEARN_FALLBACK = 100, 50

SESS = {k: C.cached("sess2_%s.pkl" % k, lambda: None) for k in ("lon", "ny")}
EV = {(k, t): C.cached("ev2_%s_%s_n5.pkl" % (k, tag), lambda: None)[0] for k in ("lon", "ny") for t, tag in TRACKS.items()}
C.candidates()
C.log("جاهز")


def gname(g):
    if len(g) == 5:
        d, trig, ei, sdi, K = g
    else:
        d, (trig, ei, sdi, K) = None, g
    s_, d_ = C.SDS[sdi]
    body = "%s|ع%.2f٪|س%g/د%d|ك%.1f" % (trig, 100 * C.TOLS[ei], s_, d_, K)
    return (d + "|" + body) if d else body


def short(s):
    return {k: s.get(k) for k in ("n", "R", "R/صفقة", "خطأ_معياريّ", "معامل", "سحب_R", "فوز%", "صفقات/شهر")}


def row_of(g, tr, tally):
    s = C.pack(tr)
    return {"g": g, "التركيبة": gname(g), "تعلّم": s["تعلّم"], "اختبار": s["اختبار"], "كلّه": short(s["كلّه"]),
            "معيار_المالك": s["معيار_المالك"], "عدّاد": tally}


def compact(r):
    if r is None:
        return None
    return {"التركيبة": r["التركيبة"], "تعلّم": short(r["تعلّم"]), "اختبار": short(r["اختبار"]),
            "أنصاف_الاختبار": {k: r["اختبار"].get("أنصاف", {}).get(k, 0.0) for k in C.TEST_HALVES},
            "معيار_المالك": r["معيار_المالك"]}


def select(rows, minn=MIN_LEARN):
    best = None
    for r in rows:
        if r["تعلّم"].get("n", 0) < minn:
            continue
        if best is None or r["تعلّم"]["R/صفقة"] > best["تعلّم"]["R/صفقة"]:
            best = r
    return best


def window_move(sd):
    kE = bisect.bisect_right(C.MT, sd["E"] - 60) - 1
    return C.MC[kE] - sd["C_D"]


def dir_accuracy(sessions):
    out = {}
    for m in ("هـ1", "هـ2"):
        res = {}
        for name, lo, hi in (("تعلّم", C.START, C.SPLIT), ("اختبار", C.SPLIT, C.END + 1), ("كلّه", C.START, C.END + 1)):
            ss = [s for s in sessions if lo <= s["D"] < hi]
            have = [s for s in ss if s["dir"][m] != 0]
            both = [s for s in have if s["dir"]["ج★"] != 0]
            agree = sum(1 for s in both if s["dir"][m] == s["dir"]["ج★"])
            mv = [window_move(s) * s["dir"][m] for s in have]
            up = sum(1 for s in have if s["dir"][m] > 0)
            ups_agree = sum(1 for s in both if s["dir"][m] > 0 and s["dir"]["ج★"] > 0)
            ups_both = sum(1 for s in both if s["dir"][m] > 0)
            dn_agree = sum(1 for s in both if s["dir"][m] < 0 and s["dir"]["ج★"] < 0)
            dn_both = sum(1 for s in both if s["dir"][m] < 0)
            res[name] = {"أيّام": len(ss), "بجهة": len(have), "بجهة%": round(100 * len(have) / max(1, len(ss)), 1),
                         "شراء_من_الجهات%": round(100 * up / max(1, len(have)), 1),
                         "توافق_جهة_النافذة%": round(100 * agree / max(1, len(both)), 1),
                         "توافق_أيّام_الشراء%": round(100 * ups_agree / max(1, ups_both), 1),
                         "توافق_أيّام_البيع%": round(100 * dn_agree / max(1, dn_both), 1),
                         "متوسّط_حركة_النافذة_بالجهة_نقاط": round(float(np.mean(mv)), 2) if mv else None,
                         "وسيطها": round(float(np.median(mv)), 2) if mv else None}
        out[m] = res
    for name, lo, hi in (("تعلّم", C.START, C.SPLIT), ("اختبار", C.SPLIT, C.END + 1)):
        ss = [s for s in sessions if lo <= s["D"] < hi and s["dir"]["ج★"] != 0]
        out["صعود_النافذة%_" + name] = round(100 * sum(1 for s in ss if s["dir"]["ج★"] > 0) / max(1, len(ss)), 1)
    return out


def buckets(tr, fn):
    out = {}
    for name, a, b in (("10–15", 0, 15), ("15–30", 15, 30), ("30–50", 30, 1e9)):
        sub = [x for x in tr if a <= x[4] < b]
        out[name] = fn(sub)
    return out


def bstats(sub):
    return {"كلّه": short(C.stats(sub)), "تعلّم": short(C.stats([x for x in sub if x[0] < C.SPLIT])),
            "اختبار": short(C.stats([x for x in sub if x[0] >= C.SPLIT]))}


def stages_full(tr, tally):
    unf = (tally or {}).get("غير_منتهية", 0)
    return {"كلّه": C.stage_dist(tr, unf), "تعلّم": C.stage_dist([x for x in tr if x[0] < C.SPLIT]),
            "اختبار": C.stage_dist([x for x in tr if x[0] >= C.SPLIT]),
            "بحسب_الوقف": buckets(tr, lambda s: C.stage_dist(s))}


def alignment(tr):
    both = [x for x in tr if x[12] != 0]
    A = [x[1] for x in both if x[3] == (x[12] > 0)]
    Bm = [x[1] for x in both if x[3] != (x[12] > 0)]
    a = sum(A) / len(A) if A else None
    b = sum(Bm) / len(Bm) if Bm else None
    return {"صفقات": len(both), "موافقة_لجهة_النافذة%": round(100 * len(A) / max(1, len(both)), 1),
            "R/صفقة_الموافقة": a and round(a, 3), "R/صفقة_المعاكسة": b and round(b, 3),
            "دقّة_التعادل%": round(100 * (-b) / (a - b), 1) if (a is not None and b is not None and a != b) else None}


def holding(tr):
    if not tr:
        return {}
    mins = sorted((x[5] + 60 - x[0]) / 60 for x in tr)
    q = lambda p: round(mins[min(len(mins) - 1, int(p * len(mins)))], 1)
    return {"دقائق_وسيط": q(0.5), "ر90": q(0.9), "أقصى": round(mins[-1], 1)}


def shift_test(tr):
    out, skipped = [], 0
    for x in tr:
        k = x[10] + 1
        tc, entry, stop, target, buy = C.MT[k] + 60, C.MC[k], x[7], x[8], x[3]
        if (buy and (entry <= stop or entry >= target)) or ((not buy) and (entry >= stop or entry <= target)):
            skipped += 1
            continue
        res = C.thirds(entry, stop, target, buy, k + 1, C.COST * x[11])
        if res is None:
            continue
        out.append((tc, res[0]) + x[2:])
    return out, skipped


RES = {"المرجع": "prereg.json",
       "البيانات": {"البداية": C.fmt(C.START), "حدّ_التعلّم": C.fmt(C.SPLIT), "النهاية": C.fmt(C.END),
                    "أنصاف_الاختبار": C.TEST_HALVES, "دقائق": C.NM1}}
SEL, BEST_TR = {}, {}

# ───────── ١) الجهة وحدها ─────────
for kind in ("lon", "ny"):
    RES["دقّة_جهة_الساعة_%s" % KINDS[kind]] = dir_accuracy(SESS[kind])
    C.log(KINDS[kind], "الجهة وحدها:", json.dumps(RES["دقّة_جهة_الساعة_%s" % KINDS[kind]], ensure_ascii=False))

# ───────── ٢) الشبكة والاختيار ─────────
for kind in ("lon", "ny"):
    for track in TRACKS:
        sessions, evmap = SESS[kind], EV[(kind, track)]
        lab = "%s|%s" % (KINDS[kind], track)
        rows = []
        for g in GRID:
            tr, tally = C.run(sessions, evmap, *g)
            rows.append(row_of(g, tr, tally))
        rows0 = []
        for g in SUB:
            tr, tally = C.run(sessions, evmap, "ج0", *g)
            rows0.append(row_of(("ج0",) + g, tr, tally))
        rowsS = []
        for g in SUB:
            tr, tally = C.run(sessions, evmap, "ج★", *g)
            rowsS.append(row_of(("ج★",) + g, tr, tally))
        sel = select(rows)
        flag = None
        if sel is None:
            sel = select(rows, MIN_LEARN_FALLBACK)
            flag = "لا تركيبة بـ≥100 صفقة تعلّم — اختيرت بـ≥50"
        tests = [r["اختبار"].get("R/صفقة") for r in rows if r["اختبار"].get("n", 0) >= 30]
        RES[lab] = {"جلسات": len(sessions), "المختارة": compact(sel), "تنبيه_الاختيار": flag,
                    "الأفضل_لكلّ_جهة": {"هـ1": compact(select([r for r in rows if r["g"][0] == "هـ1"])),
                                         "هـ2": compact(select([r for r in rows if r["g"][0] == "هـ2"])),
                                         "ج0_بلا_جهة": compact(select(rows0)),
                                         "ج★_العرّاف_للعلم": compact(select(rowsS))},
                    "ثبات_الشبكة": {"تركيبات_اختبار≥30": len(tests), "اختبار_موجب": sum(1 for v in tests if v > 0),
                                    "وسيط_اختبار_R/صفقة": sorted(tests)[len(tests) // 2] if tests else None,
                                    "تعلّم_موجب": sum(1 for r in rows if (r["تعلّم"].get("R/صفقة") or -1) > 0
                                                      and r["تعلّم"].get("n", 0) >= MIN_LEARN)},
                    "الشبكة": [compact(r) for r in rows], "ج0_الشبكة": [compact(r) for r in rows0],
                    "ج★_الشبكة": [compact(r) for r in rowsS]}
        SEL[(kind, track)] = sel
        C.log(lab, "المختارة:", json.dumps(compact(sel), ensure_ascii=False))
        C.log(lab, "ثبات:", json.dumps(RES[lab]["ثبات_الشبكة"], ensure_ascii=False))

# ───────── ٣) تشخيص المختارة ─────────
for kind in ("lon", "ny"):
    for track in TRACKS:
        sel = SEL[(kind, track)]
        lab = "%s|%s" % (KINDS[kind], track)
        if sel is None:
            continue
        g = sel["g"]
        sessions, evmap = SESS[kind], EV[(kind, track)]
        tr, tally = C.run(sessions, evmap, *g)
        D = {"التركيبة": gname(g), "عدّاد": tally}
        t0, tl0 = C.run(sessions, evmap, "ج0", *g[1:])
        ts, tls = C.run(sessions, evmap, "ج★", *g[1:])
        D["الأساس_ج0_بعيارها"] = {k: short(v) for k, v in C.pack(t0).items() if k != "معيار_المالك"}
        D["الأساس_ج0_بعيارها"]["معيار_المالك"] = C.pack(t0)["معيار_المالك"]
        D["العرّاف_ج★_بعيارها"] = {k: short(v) for k, v in C.pack(ts).items() if k != "معيار_المالك"}
        D["العرّاف_ج★_بعيارها"]["أنصاف_الاختبار"] = {k: C.pack(ts)["اختبار"].get("أنصاف", {}).get(k, 0.0) for k in C.TEST_HALVES}
        D["الجهة_الأخرى_بعيارها"] = {}
        other = "هـ2" if g[0] == "هـ1" else "هـ1"
        t2, _ = C.run(sessions, evmap, other, *g[1:])
        D["الجهة_الأخرى_بعيارها"][other] = {k: short(v) for k, v in C.pack(t2).items() if k != "معيار_المالك"}
        # مراحل الأثلاث (طلب المالك: الهدف الثالث > 40٪؟)
        D["مراحل_الأثلاث"] = {"المختارة": stages_full(tr, tally), "الأساس_ج0": stages_full(t0, tl0),
                              "العرّاف_ج★": stages_full(ts, tls)}
        # S1 مقابل S2 بالعيار نفسه
        D["S1_مقابل_S2"] = {}
        for trig in TRIGS:
            t3, tl3 = C.run(sessions, evmap, g[0], trig, *g[2:])
            p3 = C.pack(t3)
            D["S1_مقابل_S2"][trig] = {"تعلّم": short(p3["تعلّم"]), "اختبار": short(p3["اختبار"]),
                                      "مراحل_كلّه": C.stage_dist(t3, tl3.get("غير_منتهية", 0))}
        D["بحسب_النوع_داخل_المختارة"] = {"S1": bstats([x for x in tr if x[14] == 1]),
                                         "S2": bstats([x for x in tr if x[14] == 2])}
        D["شراء"] = bstats([x for x in tr if x[3]]); D["بيع"] = bstats([x for x in tr if not x[3]])
        D["حجم_الوقف"] = buckets(tr, bstats)
        D["وقف_عند_الأرضيّة_10"] = sum(1 for x in tr if abs(x[4] - 10.0) < 1e-6)
        D["سنوات_كلّه"] = C.stats(tr)["سنوات"]
        D["الإمساك"] = holding(tr)
        D["محاذاة_جهة_النافذة"] = {"المختارة": alignment(tr), "الأساس_ج0": alignment(t0)}
        # التسريب والحساسيّة
        sh, skipped = shift_test(tr)
        D["إزاحة_دقيقة"] = {"تعلّم": short(C.stats([x for x in sh if x[0] < C.SPLIT])),
                            "اختبار": short(C.stats([x for x in sh if x[0] >= C.SPLIT])), "سقطت": skipped}
        t2, _ = C.run(sessions, evmap, *g, cost_mult=2.0)
        p2 = C.pack(t2)
        D["ضعف_الكلفة"] = {"تعلّم": short(p2["تعلّم"]), "اختبار": short(p2["اختبار"]), "n_نفسه": len(t2) == len(tr)}
        t2, _ = C.run(sessions, evmap, *g, end_key="X")
        p2 = C.pack(t2)
        D["نهاية_الدخول_القصوى"] = {"تعلّم": short(p2["تعلّم"]), "اختبار": short(p2["اختبار"])}
        t2, _ = C.run(sessions, evmap, *g, maxn=3)
        p2 = C.pack(t2)
        D["ثلاث_صفقات"] = {"تعلّم": short(p2["تعلّم"]), "اختبار": short(p2["اختبار"])}
        if track == "نقاط":
            sens = {}
            for nd in (2, 10):
                ev2 = C.cached("ev2_%s_pts_n%d.pkl" % (kind, nd), lambda: None)[0]
                t2, _ = C.run(sessions, ev2, *g)
                p2 = C.pack(t2)
                sens["ن%d" % nd] = {"تعلّم": short(p2["تعلّم"]), "اختبار": short(p2["اختبار"])}
            D["حساسيّة_ن"] = sens
            BEST_TR[kind] = tr
            BEST_TR[(kind, "ج0")] = t0
            BEST_TR[(kind, "ج★")] = ts
        RES[lab]["تشخيص_المختارة"] = D
        C.log(lab, "تشخيص تمّ")
        C.log("   مراحل:", json.dumps({k: v["كلّه"] for k, v in D["مراحل_الأثلاث"].items()}, ensure_ascii=False))
        C.log("   S1/S2:", json.dumps({k: (v["تعلّم"]["R/صفقة"], v["تعلّم"]["n"], v["اختبار"].get("R/صفقة"), v["اختبار"]["n"])
                                      for k, v in D["S1_مقابل_S2"].items()}, ensure_ascii=False))
        C.log("   ج0/ج★:", json.dumps({"ج0": D["الأساس_ج0_بعيارها"]["اختبار"], "ج★": D["العرّاف_ج★_بعيارها"]["اختبار"]},
                                      ensure_ascii=False))

# ───────── ٤) ملفّا الصفقات ─────────
for kind, fname in (("lon", "trades_best_london.json"), ("ny", "trades_best_ny.json")):
    tr = BEST_TR.get(kind, [])
    json.dump([{"دخول_غ": C.fmt(x[0]), "t": x[0], "خروج_t": x[5], "R": round(x[1], 4), "شراء": x[3],
                "النوع": "S%d" % x[14], "سعر_الدخول": x[6], "الوقف": x[7], "الهدف": x[8], "الخطر_نقاط": round(x[4], 2),
                "المرحلة": x[9], "جهة_النافذة_العرّاف": x[12], "عيّنة": "تعلّم" if x[0] < C.SPLIT else "اختبار"} for x in tr],
              open(os.path.join(HERE, fname), "w", encoding="utf-8"), ensure_ascii=False, indent=0)

# ───────── ٥) التشابه مع سجلّ المالك (33 صفقة، غرينتش) ─────────
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
assert len(OWNER) == 33
days = sorted({(mo, d) for mo, d, *_ in OWNER})
spans = []
for mo, d in days:
    t0_ = calendar.timegm((2026, mo, d, 0, 0, 0))
    spans.append({"id": "%02d-%02d" % (mo, d), "D": t0_, "X": t0_ + 86400, "C_D": 25000.0})
raw, _ = C.build_events(spans, "نقاط", C.NDAYS)
SW = C.swing_tables()


def zone_dist(t, buy, price, tol=max(C.TOLS), kmin=min(C.KS), ndays=C.NDAYS):
    """أقرب منطقةٍ لنا في جهته: حزمة مجمّعٍ سليم (أ) أو مستوى مكسورٍ باندفاع فعّال (ب) في [t−15د، t]."""
    lb = t - ndays * 86400
    best = (None, None)
    # (أ) المجمّعات
    S = SW["L" if buy else "H"]
    a = int(np.searchsorted(S["start"], lb, "left")); b = int(np.searchsorted(S["conf"], t, "right"))
    for j in range(a, b):
        if S["takeT"][j] < t - 900:
            continue
        p, sj = S["px"][j], S["start"][j]
        memb = blk = 0
        for q in range(a, b):
            if q == j:
                continue
            pq = S["px"][q]
            older_ok = S["start"][q] >= sj or S["takeT"][q] >= sj
            if buy:
                if p <= pq <= p * (1 + tol) and older_ok:
                    memb += 1
                elif p * (1 - tol) <= pq < p and S["takeT"][q] >= t - 900:
                    blk += 1
            else:
                if p * (1 - tol) <= pq <= p and older_ok:
                    memb += 1
                elif p < pq <= p * (1 + tol) and S["takeT"][q] >= t - 900:
                    blk += 1
        if memb < 1 or blk:
            continue
        lo, hi = (p, S["other"][j]) if buy else (S["other"][j], p)
        dd = 0.0 if lo <= price <= hi else min(abs(price - lo), abs(price - hi))
        if best[0] is None or dd < best[0]:
            best = (dd, "مجمّع")
    # (ب) المستويات المكسورة
    S = SW["H" if buy else "L"]
    a = int(np.searchsorted(S["start"], lb, "left")); b = int(np.searchsorted(S["conf"], t, "right"))
    for j in range(a, b):
        p, i15 = S["px"][j], int(S["idx"][j])
        jb = C.first_gt(C.C15, C.BMAX_C15, i15 + 1, p) if buy else C.first_lt(C.C15, C.BMIN_C15, i15 + 1, p)
        if jb < 0 or C.T15[jb] + 900 > t:
            continue
        tb = C.T15[jb] + 900
        a1, b1 = bisect.bisect_left(C.MT, tb - 900), bisect.bisect_left(C.MT, tb)
        if b1 <= a1:
            continue
        imp = ((C.C15[jb] - C.MLn[a1:b1].min()) if buy else (C.MHn[a1:b1].max() - C.C15[jb])) / C.a5_at(tb)
        if imp < kmin:
            continue
        oth = S["other"][j]
        jf = C.first_lt(C.C15, C.BMIN_C15, jb + 1, oth) if buy else C.first_gt(C.C15, C.BMAX_C15, jb + 1, oth)
        tf = C.T15[jf] + 900 if jf >= 0 else np.inf
        if tf < t - 900:
            continue
        lo, hi = (oth, p) if buy else (p, oth)
        dd = 0.0 if lo <= price <= hi else min(abs(price - lo), abs(price - hi))
        if best[0] is None or dd < best[0]:
            best = (dd, "مكسور")
    return best


selg = {k: (SEL[(k, "نقاط")]["g"] if SEL[(k, "نقاط")] else None) for k in ("lon", "ny")}
cmp_rows, summ = [], Counter()
dir_agree = {"هـ1": [0, 0], "هـ2": [0, 0]}
for mo, d, hh, mm, buy, px in OWNER:
    buy = bool(buy)
    off = 45.0 if mo == 6 else 0.0
    t = calendar.timegm((2026, mo, d, hh, mm, 0))
    ours = px - off
    evs = raw["%02d-%02d" % (mo, d)]
    near = [e for e in evs if abs(e[0] - t) <= 900 and abs(e[3] - ours) <= 20 and e[1] == buy]
    wide = [e for e in near if any(C.passes(e, "كلاهما", ei, sdi, min(C.KS)) for ei in (0, 1) for sdi in (0, 1))]
    row = {"الوقت_غ": "%02d-%02d %02d:%02d" % (mo, d, hh, mm), "جهته": "شراء" if buy else "بيع", "سعره_عندنا": ours,
           "زناد_بأوسع_عيار": [{"t": C.fmt(e[0]), "S": e[2], "دخول": e[3], "بهدف": e[6] is not None} for e in wide]}
    row["أوسع_عيار_بجهته"] = bool(wide)
    for kind in ("lon", "ny"):
        g = selg[kind]
        if g:
            ok = [e for e in near if C.passes(e, *g[1:]) and e[6] is not None]
            row["عيار_%s_بجهته" % KINDS[kind]] = bool(ok)
        tr = BEST_TR.get(kind, [])
        row["البطاقة_الكاملة_%s" % KINDS[kind]] = [
            {"t": C.fmt(x[0]), "جهة": "شراء" if x[3] else "بيع", "R": round(x[1], 2)} for x in tr
            if abs(x[0] - t) <= 900 and abs(x[6] - ours) <= 20 and x[3] == buy]
    dz, zt = zone_dist(t, buy, ours)
    row["بُعد_أقرب_منطقة_لنا"] = None if dz is None else round(float(dz), 1)
    row["نوعها"] = zt
    h1, h2 = C.hour_dirs(t)
    row["جهة_الساعة_عند_دقيقته"] = {"هـ1": int(h1), "هـ2": int(h2)}
    for m, v in (("هـ1", h1), ("هـ2", h2)):
        if v != 0:
            dir_agree[m][1] += 1
            dir_agree[m][0] += (v > 0) == buy
    summ["أوسع_عيار_بجهته"] += row["أوسع_عيار_بجهته"]
    summ["عيار_لندن_بجهته"] += bool(row.get("عيار_لندن_بجهته"))
    summ["عيار_أمريكا_بجهته"] += bool(row.get("عيار_أمريكا_بجهته"))
    summ["البطاقة_الكاملة_قريبة"] += bool(row["البطاقة_الكاملة_لندن"] or row["البطاقة_الكاملة_أمريكا"])
    summ["على_منطقةٍ_لنا_≤20"] += int(bool(dz is not None and dz <= 20))
    summ["أبعد_من_20_أو_بلا_منطقة"] += int(not (dz is not None and dz <= 20))
    summ["بلا_منطقة_في_جهته"] += int(dz is None)
    cmp_rows.append(row)
RES["التشابه_مع_سجلّه"] = {
    "الملخّص_من_33": dict(summ),
    "جهة_الساعة_عند_دقيقته_توافق_جهته": {m: "%d من %d بجهة (من 33)" % tuple(v) for m, v in dir_agree.items()},
    "الترجمة_الأولى_للمقارنة": {"زناد_خام_قريب_بجهته": 4, "البطاقة_الكاملة_قريبة": 0, "أبعد_من_20_عن_مناطقنا": 24},
    "الصفقات": cmp_rows}
C.log("التشابه:", json.dumps(RES["التشابه_مع_سجلّه"]["الملخّص_من_33"], ensure_ascii=False),
      json.dumps(RES["التشابه_مع_سجلّه"]["جهة_الساعة_عند_دقيقته_توافق_جهته"], ensure_ascii=False))

# ───────── ٦) الدمج مع 414 ─────────
D414 = r"C:\Users\NQ\QUANT_NQ\backtest\strategies_2026-10-08\diag414"
b414 = []
for name in ("diag_A", "diag_B", "grid_C"):
    x = json.load(open(os.path.join(D414, name + ".json"), encoding="utf-8"))
    for t in x["عيارات"]["الحاليّة"]["trades"]:
        b414.append((t["t"], t["exit"], t["r"], t["win"], t["buy"], t["bps"]))
b414.sort()
T414 = calendar.timegm((2014, 10, 1, 0, 0, 0))


def merge(a, b):
    rows = sorted([(t[0], 0, t) for t in a] + [(t[0], 1, t) for t in b], key=lambda z: (z[0], z[1]))
    out, busy = [], 0.0
    for t_close, src, t in rows:
        if t_close < busy:
            continue
        out.append(tuple(t) + (src,))
        busy = t[1] + 60
    return out


def summ414(rows):
    tr = [(x[0], x[2]) for x in rows]
    L = [x for x in tr if x[0] < C.SPLIT]; T = [x for x in tr if x[0] >= C.SPLIT]
    sL, sT = C.stats(L, T414, C.SPLIT), C.stats(T, C.SPLIT, C.END)
    return {"تعلّم": short(sL), "اختبار": short(sT), "كلّه": short(C.stats(tr, T414, C.END)),
            "أنصاف_الاختبار": {k: sT.get("أنصاف", {}).get(k, 0.0) for k in C.TEST_HALVES} if sT.get("n") else {},
            "معيار_المالك": C.owner_pass(sT)}


own_rows = sorted((x[0], x[5], x[1], kind, x[3], x[13]) for kind in ("lon", "ny") for x in BEST_TR.get(kind, [])
                  if x[0] >= T414)
own_one = [r[:6] for r in merge(own_rows, [])]
comb = merge(b414, own_one)
RES["الدمج_مع_414"] = {
    "الفترة": "%s ⟶ %s" % (C.fmt(T414), C.fmt(C.END)),
    "414_وحدها": summ414(b414),
    "بطاقة_المالك_(لندن+أمريكا_مركز_واحد)": summ414(own_one),
    "414+بطاقة_المالك": summ414(comb),
    "من_بطاقة_المالك_في_الدمج": sum(1 for x in comb if x[6] == 1),
    "صفقات_المالك_المحجوبة_بـ414": len(own_one) - sum(1 for x in comb if x[6] == 1)}
C.log("الدمج:", json.dumps({k: (v["اختبار"] if isinstance(v, dict) and "اختبار" in v else v)
                             for k, v in RES["الدمج_مع_414"].items()}, ensure_ascii=False))

json.dump(RES, open(os.path.join(HERE, "results.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
C.log("انتهى")
