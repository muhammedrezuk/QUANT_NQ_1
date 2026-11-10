# -*- coding: utf-8 -*-
"""المرحلة 2: الشبكة والاختيار والعرّاف والتشخيص والمقارنة بسجلّ المالك والدمج مع 414 — بحسب prereg.json."""
import sys
sys.dont_write_bytecode = True
sys.stdout.reconfigure(encoding="utf-8")
import bisect
import calendar
import itertools
import json
import os
from collections import Counter
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import oc_core as C

HERE = C.HERE
TRACKS = {"نقاط": "pts", "نسبيّ": "rel"}
KINDS = {"lon": "لندن", "ny": "أمريكا"}
GRID = list(itertools.product(C.DMODES, ("أ", "ب"), (1.5, 3.0), (2, 3)))
assert len(GRID) == 40
MIN_LEARN = 100

SESS = {k: C.cached("sess_%s.pkl" % k, lambda: C.session_days(k))[0] for k in ("lon", "ny", "his")}
EV = {}
for kind in ("lon", "ny"):
    for track, tag in TRACKS.items():
        EV[(kind, track)] = C.cached("ev_%s_%s_base.pkl" % (kind, tag), lambda: C.build_events(SESS[kind], None, track))[0]
C.log("جاهز")


def key_of(g):
    return "%s|%s|ك%.1f|%d" % g


def short(s):
    return {k: s.get(k) for k in ("n", "R", "R/صفقة", "خطأ_معياريّ", "معامل", "سحب_R", "فوز%", "صفقات/شهر")}


def row_of(g, tr, tally):
    s = C.pack(tr)
    return {"الجهة": g[0], "الزناد": g[1], "ك": g[2], "العدد": g[3], "تعلّم": s["تعلّم"], "اختبار": s["اختبار"],
            "كلّه": short(s["كلّه"]), "معيار_المالك": s["معيار_المالك"], "عدّاد": tally}


def select(rows, pred=lambda r: True):
    best = None
    for r in rows:
        if not pred(r) or r["تعلّم"].get("n", 0) < MIN_LEARN:
            continue
        if best is None or r["تعلّم"]["R/صفقة"] > best["تعلّم"]["R/صفقة"]:
            best = r
    return best


def gkey(r):
    return (r["الجهة"], r["الزناد"], r["ك"], r["العدد"])


def compact(r):
    if r is None:
        return None
    return {"التركيبة": key_of(gkey(r)), "تعلّم": short(r["تعلّم"]), "اختبار": short(r["اختبار"]),
            "أنصاف_الاختبار": {k: r["اختبار"].get("أنصاف", {}).get(k, 0.0) for k in C.TEST_HALVES},
            "معيار_المالك": r["معيار_المالك"]}


def dir_accuracy(sessions):
    out = {}
    for m in ("ج1", "ج2", "ج3", "ج4"):
        res = {}
        for name, lo, hi in (("تعلّم", C.START, C.SPLIT), ("اختبار", C.SPLIT, C.END + 1)):
            ss = [s for s in sessions if lo <= s["D"] < hi]
            have = [s for s in ss if s["dir"][m] != 0]
            both = [s for s in have if s["dir"]["ج★"] != 0]
            agree = sum(1 for s in both if s["dir"][m] == s["dir"]["ج★"])
            res[name] = {"أيّام": len(ss), "بجهة%": round(100 * len(have) / max(1, len(ss)), 1),
                         "توافق_العرّاف%": round(100 * agree / max(1, len(both)), 1)}
        out[m] = res
    ss = sessions
    up = sum(1 for s in ss if s["dir"]["ج★"] > 0)
    out["ج★_صعود%"] = round(100 * up / max(1, len(ss)), 1)
    return out


def buckets(tr):
    out = {}
    for name, a, b in (("10–15", 0, 15), ("15–30", 15, 30), ("30–50", 30, 1e9)):
        sub = [x for x in tr if a <= x[4] < b]
        out[name] = {"كلّه": short(C.stats(sub)), "تعلّم": short(C.stats([x for x in sub if x[0] < C.SPLIT])),
                     "اختبار": short(C.stats([x for x in sub if x[0] >= C.SPLIT]))}
    out["وقف_عند_الأرضيّة_10"] = sum(1 for x in tr if abs(x[4] - 10.0) < 1e-6)
    return out


def ny_clock(t):
    return datetime.fromtimestamp(t, timezone.utc).timestamp() + C.new_york_offset_h(t) * 3600


def holding(tr):
    if not tr:
        return {}
    mins = sorted((x[5] + 60 - x[0]) / 60 for x in tr)
    q = lambda p: round(mins[min(len(mins) - 1, int(p * len(mins)))], 1)
    past16 = overnight = 0
    for x in tr:
        e_loc = ny_clock(x[0]); x_loc = ny_clock(x[5] + 60)
        day0 = e_loc - e_loc % 86400
        past16 += x_loc > day0 + 16 * 3600
        overnight += x_loc > day0 + 17 * 3600
    st = Counter(x[9] for x in tr)
    return {"دقائق_وسيط": q(0.5), "ر75": q(0.75), "ر90": q(0.9), "أقصى": round(mins[-1], 1),
            "بعد_16:00_نيويورك%": round(100 * past16 / len(tr), 1), "بعد_17:00_نيويورك%": round(100 * overnight / len(tr), 1),
            "المراحل": {"وقف_كامل": st.get(0, 0), "بعد_الأوّل": st.get(1, 0), "بعد_الثاني": st.get(2, 0), "الهدف": st.get(3, 0)}}


def shift_test(tr):
    """الدخول بإغلاق الدقيقة التالية بالوقف والهدف نفسيهما."""
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


def cap16(sd):
    t = sd["D"]
    off = C.new_york_offset_h(t)
    d = datetime.fromtimestamp(t + off * 3600, timezone.utc).date()
    return calendar.timegm((d.year, d.month, d.day, 16, 0, 0)) - off * 3600


RES = {"المرجع": "prereg.json", "البيانات": {"البداية": C.fmt(C.START), "حدّ_التعلّم": C.fmt(C.SPLIT),
                                             "النهاية": C.fmt(C.END), "أنصاف_الاختبار": C.TEST_HALVES,
                                             "دقائق": C.NM1}}
SEL = {}
for kind in ("lon", "ny"):
    for track in TRACKS:
        sessions, evmap = SESS[kind], EV[(kind, track)]
        rows = []
        for g in GRID:
            tr, tally = C.run(sessions, evmap, *g)
            rows.append(row_of(g, tr, tally))
        oracle = []
        for trig, K, maxn in itertools.product(("أ", "ب"), (1.5, 3.0), (2, 3)):
            tr, tally = C.run(sessions, evmap, "ج★", trig, K, maxn)
            oracle.append(row_of(("ج★", trig, K, maxn), tr, tally))
        sel = select(rows)
        per_mode = {m: compact(select(rows, lambda r, m=m: r["الجهة"] == m)) for m in C.DMODES}
        lab = "%s|%s" % (KINDS[kind], track)
        tests = [r["اختبار"].get("R/صفقة") for r in rows if r["اختبار"].get("n", 0) >= 30]
        RES[lab] = {"جلسات": len(sessions), "الشبكة": [compact(r) for r in rows], "العرّاف": [compact(r) for r in oracle],
                    "المختارة": compact(sel), "الأفضل_لكلّ_جهة": per_mode,
                    "ثبات_الشبكة": {"تركيبات_اختبار≥30": len(tests), "اختبار_موجب": sum(1 for v in tests if v > 0),
                                    "وسيط_اختبار_R/صفقة": sorted(tests)[len(tests) // 2] if tests else None},
                    "دقّة_الجهة": dir_accuracy(sessions)}
        SEL[(kind, track)] = sel
        C.log(lab, "المختارة:", json.dumps(compact(sel), ensure_ascii=False))
        for m, v in per_mode.items():
            C.log("   ", m, json.dumps(v and {"ت": v["التركيبة"], "تعلّم": v["تعلّم"]["R/صفقة"], "n_ت": v["تعلّم"]["n"],
                                              "اختبار": v["اختبار"]["R/صفقة"], "n_خ": v["اختبار"]["n"]}, ensure_ascii=False))

# ───────── تشخيص المختارة (مسار النقاط هو الحكم) ─────────
BEST_TR = {}
for kind in ("lon", "ny"):
    for track in TRACKS:
        sel = SEL[(kind, track)]
        lab = "%s|%s" % (KINDS[kind], track)
        if sel is None:
            continue
        g = gkey(sel)
        sessions, evmap = SESS[kind], EV[(kind, track)]
        tr, tally = C.run(sessions, evmap, *g)
        D = {"التركيبة": key_of(g), "عدّاد": tally}
        D["شراء"] = C.pack([x for x in tr if x[3]]); D["بيع"] = C.pack([x for x in tr if not x[3]])
        for k in ("شراء", "بيع"):
            D[k] = {"تعلّم": short(D[k]["تعلّم"]), "اختبار": short(D[k]["اختبار"])}
        D["حجم_الوقف"] = buckets(tr)
        D["الإمساك"] = holding(tr)
        D["سنوات_كلّه"] = C.stats(tr)["سنوات"]
        # الجهات كلّها والعرّاف بالعيار نفسه (الزناد · ك · العدد)
        D["الجهات_بالعيار_نفسه"] = {}
        for m in C.DMODES + ("ج★",):
            t2, _ = C.run(sessions, evmap, m, *g[1:])
            p2 = C.pack(t2)
            D["الجهات_بالعيار_نفسه"][m] = {"تعلّم": short(p2["تعلّم"]), "اختبار": short(p2["اختبار"]),
                                           "كلّه": short(p2["كلّه"])}
        t0, _ = C.run(sessions, evmap, "ج0", *g[1:])
        D["ج0_بحسب_العرّاف"] = {
            "مع_جهة_النافذة": short(C.stats([x for x in t0 if x[12] != 0 and x[3] == (x[12] > 0)])),
            "ضدّها": short(C.stats([x for x in t0 if x[12] != 0 and x[3] != (x[12] > 0)]))}
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
        t2, _ = C.run(sessions, evmap, *g, cap_fn=cap16)
        p2 = C.pack(t2)
        D["إغلاق_قسريّ_16:00_نيويورك_للعلم"] = {"تعلّم": short(p2["تعلّم"]), "اختبار": short(p2["اختبار"])}
        if track == "نقاط":
            sens = {}
            for name, P in (("ع0.10٪", {"tol": 0.0010}), ("ع0.30٪", {"tol": 0.0030}), ("ن7", {"ndays": 7}),
                            ("ن28", {"ndays": 28}), ("م15", {"m": 15}), ("م60", {"m": 60})):
                ev2 = C.cached("ev_%s_pts_%s.pkl" % (kind, name), lambda: C.build_events(sessions, P, "نقاط"))[0]
                t2, _ = C.run(sessions, ev2, *g)
                p2 = C.pack(t2)
                sens[name] = {"تعلّم": short(p2["تعلّم"]), "اختبار": short(p2["اختبار"])}
            D["حساسيّة_للعلم"] = sens
            BEST_TR[kind] = tr
        RES[lab]["تشخيص_المختارة"] = D
        C.log(lab, "تشخيص تمّ")

# ───────── نافذة سجلّه الرابحة (05:30–07:00 غرينتش) بعيار لندن المختار — للعلم ─────────
if SEL[("lon", "نقاط")] is not None:
    g = gkey(SEL[("lon", "نقاط")])
    evh = C.cached("ev_his_pts_base.pkl", lambda: C.build_events(SESS["his"], None, "نقاط"))[0]
    th, _ = C.run(SESS["his"], evh, *g)
    ph = C.pack(th)
    RES["نافذة_سجلّه_05:30–07:00غ"] = {"عيار_لندن": key_of(g), "تعلّم": short(ph["تعلّم"]), "اختبار": short(ph["اختبار"]),
                                        "كلّه": short(ph["كلّه"]), "معيار_المالك": ph["معيار_المالك"]}
    t0, _ = C.run(SESS["his"], evh, "ج0", *g[1:])
    p0 = C.pack(t0)
    RES["نافذة_سجلّه_05:30–07:00غ"]["ج0_بالعيار"] = {"تعلّم": short(p0["تعلّم"]), "اختبار": short(p0["اختبار"])}

# ───────── ملفّا الصفقات ─────────
for kind, fname in (("lon", "trades_best_london.json"), ("ny", "trades_best_ny.json")):
    tr = BEST_TR.get(kind, [])
    json.dump([{"دخول_غ": C.fmt(x[0]), "t": x[0], "خروج_t": x[5], "R": round(x[1], 4), "شراء": x[3],
                "سعر_الدخول": x[6], "الوقف": x[7], "الهدف": x[8], "الخطر_نقاط": round(x[4], 2), "المرحلة": x[9],
                "جهة_النافذة_العرّاف": x[12], "عيّنة": "تعلّم" if x[0] < C.SPLIT else "اختبار"} for x in tr],
              open(os.path.join(HERE, fname), "w", encoding="utf-8"), ensure_ascii=False, indent=0)

# ───────── المقارنة بسجلّ المالك (33 صفقة، غرينتش) ─────────
OWNER = [  # (شهر، يوم، ساعة، دقيقة، شراء؟، سعره، فارق السعر)
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
    t0 = calendar.timegm((2026, mo, d, 0, 0, 0))
    spans.append({"id": "%02d-%02d" % (mo, d), "D": t0, "X": t0 + 86400, "C_D": 25000.0})
raw, _ = C.build_events(spans, None, "نقاط")


def in_window(t, kind):
    for s in SESS[kind]:
        if s["D"] < t <= s["E"]:
            return s
    return None


cmp_rows = []
summary = Counter()
selp = {k: (gkey(SEL[(k, "نقاط")]) if SEL[(k, "نقاط")] else None) for k in ("lon", "ny")}
for mo, d, hh, mm, buy, px in OWNER:
    off = 45.0 if mo == 6 else 0.0
    t = calendar.timegm((2026, mo, d, hh, mm, 0))
    ours = px - off
    near = [e for e in raw["%02d-%02d" % (mo, d)] if abs(e[0] - t) <= 900 and abs(e[5] - ours) <= 20]
    row = {"الوقت_غ": "%02d-%02d %02d:%02d" % (mo, d, hh, mm), "جهته": "شراء" if buy else "بيع", "سعره_عندنا": ours}
    row["زناد_خام_قريب"] = [{"t": C.fmt(e[0]), "جهة": "شراء" if e[1] else "بيع", "صفعة": e[2], "اختناق": e[3],
                             "نسبة": round(e[4], 2), "بهدف": e[8] is not None} for e in near]
    row["خام_بجهته"] = any(e[1] == bool(buy) for e in near)
    row["خام_بجهته_ك1.5"] = any(e[1] == bool(buy) and e[4] >= 1.5 and e[8] is not None for e in near)
    for kind in ("lon", "ny"):
        g = selp[kind]
        if g:
            ok = [e for e in near if e[1] == bool(buy) and (e[2] if g[1] == "أ" else e[3]) and e[4] >= g[2] and e[8] is not None]
            row["عيار_%s_بجهته" % KINDS[kind]] = bool(ok)
        s = in_window(t, kind)
        row["في_نافذة_%s" % KINDS[kind]] = bool(s)
        if s and g:
            dm = g[0]
            row["جهة_اليوم_%s(%s)" % (KINDS[kind], dm)] = "حرّ" if dm == "ج0" else s["dir"][dm]
            row["جهة_العرّاف_%s" % KINDS[kind]] = s["dir"]["ج★"]
        tr = BEST_TR.get(kind, [])
        row["البطاقة_الكاملة_%s" % KINDS[kind]] = [
            {"t": C.fmt(x[0]), "جهة": "شراء" if x[3] else "بيع", "R": round(x[1], 2)} for x in tr
            if abs(x[0] - t) <= 900 and abs(x[6] - ours) <= 20]
    for k in ("خام_بجهته", "خام_بجهته_ك1.5", "عيار_لندن_بجهته", "عيار_أمريكا_بجهته"):
        summary[k] += bool(row.get(k))
    summary["البطاقة_الكاملة_قريبة"] += bool(row["البطاقة_الكاملة_لندن"] or row["البطاقة_الكاملة_أمريكا"])
    summary["في_نافذة_لندن"] += row["في_نافذة_لندن"]; summary["في_نافذة_أمريكا"] += row["في_نافذة_أمريكا"]
    cmp_rows.append(row)
RES["المقارنة_بسجلّه"] = {"الملخّص_من_33": dict(summary), "الصفقات": cmp_rows}
C.log("المقارنة:", dict(summary))

# ───────── الدمج مع 414 ─────────
D414 = r"C:\Users\NQ\QUANT_NQ\backtest\strategies_2026-10-08\diag414"
b414 = []
for name in ("diag_A", "diag_B", "grid_C"):
    x = json.load(open(os.path.join(D414, name + ".json"), encoding="utf-8"))
    for t in x["عيارات"]["الحاليّة"]["trades"]:
        b414.append((t["t"], t["exit"], t["r"], t["win"], t["buy"], t["bps"]))
b414.sort()
T414 = calendar.timegm((2014, 10, 1, 0, 0, 0))


def merge(a, b):
    """combine.merge: مركزٌ واحد، الأسبق أوّلًا، a أوّلًا عند التساوي. الصفّ (t, exit, r, win, buy, bps) ⟵ + المصدر."""
    rows = sorted([(t[0], 0, t) for t in a] + [(t[0], 1, t) for t in b], key=lambda z: (z[0], z[1]))
    out, busy = [], 0.0
    for t_close, src, t in rows:
        if t_close < busy:
            continue
        out.append(tuple(t) + (src,))
        busy = t[1] + 60
    return out


def summ(rows):
    tr = [(x[0], x[2]) for x in rows]
    L = [x for x in tr if x[0] < C.SPLIT]; T = [x for x in tr if x[0] >= C.SPLIT]
    sL, sT = C.stats(L, T414, C.SPLIT), C.stats(T, C.SPLIT, C.END)
    return {"تعلّم": short(sL), "اختبار": short(sT), "كلّه": short(C.stats(tr, T414, C.END)),
            "أنصاف_الاختبار": {k: sT.get("أنصاف", {}).get(k, 0.0) for k in C.TEST_HALVES} if sT.get("n") else {},
            "معيار_المالك": C.owner_pass(sT)}


own_rows = sorted((x[0], x[5], x[1], kind, x[3], x[13]) for kind in ("lon", "ny") for x in BEST_TR.get(kind, [])
                  if x[0] >= T414)
own_one = [r[:6] for r in merge(own_rows, [])]          # مركزٌ واحد بين الجلستين
comb = merge(b414, own_one)
RES["الدمج_مع_414"] = {
    "الفترة": "%s ⟶ %s" % (C.fmt(T414), C.fmt(C.END)),
    "414_وحدها": summ(b414),
    "بطاقة_المالك_(لندن+أمريكا_مركز_واحد)": summ(own_one),
    "414+بطاقة_المالك": summ(comb),
    "من_بطاقة_المالك_في_الدمج": sum(1 for x in comb if x[6] == 1),
    "صفقات_المالك_المحجوبة_بـ414": len(own_one) - sum(1 for x in comb if x[6] == 1)}
C.log("الدمج:", json.dumps({k: (v["اختبار"] if isinstance(v, dict) and "اختبار" in v else v)
                             for k, v in RES["الدمج_مع_414"].items()}, ensure_ascii=False))

json.dump(RES, open(os.path.join(HERE, "results.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
C.log("انتهى")
