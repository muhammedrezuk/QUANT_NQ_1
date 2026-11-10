# -*- coding: utf-8 -*-
"""بناء جدول الإصدارات والمفاجآت (z) والعوائد من المصدرين — قراءة فقط. التصميم في «التصميم.md».

المخرج: events.json — {
  "components": [ {T, comp, cat, src, actual, consensus, s, z, sz} ... ],
  "clusters":   [ {T, src, cats: {cat: z_cat}, ret: {h: bps}, spike: {...}} ... ],
  "checks":     {...} }
"""
import bisect
import json
import math
import os
import re
import sqlite3
import statistics
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import numpy as np

NY = ZoneInfo("America/New_York")

sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))
BRIDGE = "file:C:/Users/NQ/AppData/Roaming/MetaQuotes/Terminal/Common/Files/nq_brain.db?mode=ro"
OLD = "file:%s?mode=ro" % os.path.join(HERE, "news_old.db").replace("\\", "/")
CAL = "file:C:/Users/NQ/AppData/Roaming/MetaQuotes/Terminal/Common/Files/nq_calendar_history.db?mode=ro"
HIST = "file:C:/Users/NQ/QUANT_NQ/forex_runtime/var/history/ctrader_history.db?mode=ro"
CAL_OFFSET_S = 3 * 3600
BRIDGE_FIRST = "2024-10-08"
WIN, MIN_PAST = 24, 8
HORIZONS = (15, 60, 240)

# الاسم ⟵ (الفئة، الإشارة، له شهريّ وسنويّ بالاسم نفسه؟، رمز ميتاتريدر)
COMP = {
    "CPI": ("تضخّم", 1, True, "consumer-price-index-mm"),
    "Core CPI": ("تضخّم", 1, True, "consumer-price-index-ex-food-energy-mm"),
    "Nonfarm Payrolls": ("وظائف", 1, False, "nonfarm-payrolls"),
    "Unemployment Rate": ("وظائف", -1, False, "unemployment-rate"),
    "Initial Jobless Claims": ("مطالبات", -1, False, "initial-jobless-claims"),
    "Retail Sales": ("تجزئة", 1, True, "retail-sales-mm"),
    "Core Retail Sales": ("تجزئة", 1, False, "retail-sales-ex-autos-mm"),
    "PPI": ("منتجين", 1, True, "producer-price-index-mm"),
    "Core PPI": ("منتجين", 1, True, "producer-price-index-ex-food-energy-mm"),
    "GDP": ("ناتج", 1, False, "gross-domestic-product-qq"),
    "Core PCE Price Index": ("نفقات", 1, True, "core-pce-price-index-mm"),
    "ISM Manufacturing PMI": ("مصانع", 1, False, "ism-manufacturing-pmi"),
    "ISM Non-Manufacturing PMI": ("خدمات", 1, False, "ism-non-manufacturing-pmi"),
    "Fed Interest Rate Decision": ("فائدة", 1, False, "fed-interest-rate-decision"),
}
SCALE = {"": 1.0, "%": 1.0, "K": 1e3, "M": 1e6, "B": 1e9, "T": 1e12}
MT5_SCALE = {0: 1.0, 1: 1e3, 2: 1e6, 3: 1e9, 4: 1e12}
VALUE_RE = re.compile(r"^([-+]?\d+(?:\.\d+)?)([KMBT%]?)$", re.IGNORECASE)   # منطق monetary_consensus.parse_value


def parse(text):
    m = VALUE_RE.match(str(text or "").replace(",", "").replace(" ", ""))
    return None if not m else float(m.group(1)) * SCALE[m.group(2).upper()]


def fmt(t):
    return datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%d %H:%M")


def load_rows():
    """صفوف المكوّنات من المصدرين: (الاسم، T، فعليّ، إجماع، سابق، المصدر، المعرّف)."""
    out = []
    names = tuple(COMP)
    q = "in (%s)" % ",".join("?" * len(names))
    br = sqlite3.connect(BRIDGE, uri=True, timeout=10)
    for rid, nm, at, a, c, p in br.execute(
            "select id, event_name, scheduled_at, actual, consensus, previous from econ_calendar "
            "where country='United States' and scheduled_at is not null and event_date>=? and event_name " + q,
            (BRIDGE_FIRST,) + names):
        out.append((nm, float(at), a, c, p, "سنتان", rid))
    br.close()
    if os.path.isfile(os.path.join(HERE, "news_old.db")):
        old = sqlite3.connect(OLD, uri=True, timeout=10)
        for rid, nm, at, a, c, p in old.execute(
                "select id, event_name, scheduled_at, actual, consensus, previous from econ "
                "where scheduled_at is not null and event_date<? and event_name " + q, (BRIDGE_FIRST,) + names):
            out.append((nm, float(at), a, c, p, "أقدم", rid))
        old.close()
    return out


def classify(rows):
    """يفرز الشهريّ من السنويّ باستمرار «السابق»؛ ويعيد صفوف المكوّن الواحد (T، فعليّ، إجماع، سابق، مصدر، معرّف)."""
    by = defaultdict(lambda: defaultdict(list))
    for nm, at, a, c, p, src, rid in rows:
        by[nm][at].append((parse(a), parse(c), parse(p), src, rid, a, c))
    out, diag = {}, {}
    for nm, slots in by.items():
        paired = COMP[nm][2]
        lm = ly = None
        res, disagree, singles = [], 0, 0
        for at in sorted(slots):
            cand = slots[at]
            if not paired:
                res.extend((at,) + x for x in cand[:1])
                continue
            if len(cand) >= 2:
                a, b = cand[0], cand[1]
                mag = lambda r: abs(r[0] or 0) + abs(r[2] or 0)
                by_mag = a if mag(a) <= mag(b) else b
                if lm is not None and ly is not None and a[2] is not None and b[2] is not None:
                    cost_a = abs(a[2] - lm) + abs(b[2] - ly)
                    cost_b = abs(b[2] - lm) + abs(a[2] - ly)
                    mom = a if cost_a < cost_b else b if cost_b < cost_a else by_mag
                else:
                    mom = by_mag
                yoy = b if mom is a else a
                if mom is not by_mag:
                    disagree += 1
                res.append((at,) + mom)
                lm, ly = (mom[0] if mom[0] is not None else lm), (yoy[0] if yoy[0] is not None else ly)
            else:
                x = cand[0]
                singles += 1
                if ly is not None and lm is not None and x[2] is not None and abs(x[2] - ly) < abs(x[2] - lm):
                    ly = x[0] if x[0] is not None else ly        # سنويٌّ وحده ⟸ يُترك
                    continue
                res.append((at,) + x)
                lm = x[0] if x[0] is not None else lm
        out[nm] = res
        diag[nm] = {"إصدارات": len(res), "استمرار≠الحجم": disagree, "مفرد": singles}
    return out, diag


def mt5_events():
    cal = sqlite3.connect(CAL, uri=True, timeout=10)
    codes = tuple(v[3] for v in COMP.values())
    ev = defaultdict(list)
    for code, ts, act, mult in cal.execute(
            "select event_code, time_server, actual, multiplier from calendar_history where country_code='US' and "
            "event_code in (%s)" % ",".join("?" * len(codes)), codes):
        ev[code].append((ts - CAL_OFFSET_S, None if act is None else act * MT5_SCALE.get(int(mult or 0), 1.0)))
    for code in ev:
        ev[code].sort()
    return ev


SPIKE_MIN = 3.0


def dedup_and_check(series, mt5, spike):
    """التكرار الزائف + مطابقة التوقيت والفعليّ بتقويم ميتاتريدر (+ حسم الاختلاف بقفزة الدقيقة)."""
    checks = {}
    for nm, res in series.items():
        code = COMP[nm][3]
        mt = mt5.get(code, [])
        mt_t = [x[0] for x in mt]

        def near(at):
            k = bisect.bisect_left(mt_t, at - 2 * 86400)
            best = None
            while k < len(mt) and mt[k][0] <= at + 2 * 86400:
                if best is None or abs(mt[k][0] - at) < abs(best[0] - at):
                    best = mt[k]
                k += 1
            return best
        # التكرار: القيم الثلاث نفسها في إصدارين خلال 3 أيّام
        drop = set()
        for i in range(len(res)):
            for j in range(i + 1, len(res)):
                if res[j][0] - res[i][0] > 3 * 86400:
                    break
                if res[i][1:4] == res[j][1:4] and res[i][1] is not None:
                    ni, nj = near(res[i][0]), near(res[j][0])
                    oki = ni is not None and abs(ni[0] - res[i][0]) <= 120
                    okj = nj is not None and abs(nj[0] - res[j][0]) <= 120
                    drop.add(i if (okj or not oki) else j)
        kept = [r for k, r in enumerate(res) if k not in drop]
        tally = Counter()
        val = Counter()
        odd_t, odd_v = [], []
        final = []
        for r in kept:
            nb = near(r[0])
            d = None if nb is None else nb[0] - r[0]
            key = "بلا_مقابل" if nb is None else "مطابق" if abs(d) <= 120 else (
                "±ساعة" if abs(abs(d) - 3600) <= 120 else "غيره")
            tally[key] += 1
            if key == "مطابق":
                final.append(r)
                if nb[1] is not None and r[1] is not None:
                    same = abs(nb[1] - r[1]) <= max(0.011, 0.001 * abs(r[1]))
                    val["فعليّ_متطابق" if same else "فعليّ_مختلف"] += 1
                    if not same:
                        odd_v.append("%s %s ناسداك=%s ميتاتريدر=%s" % (fmt(r[0]), r[4], r[6], round(nb[1], 4)))
                continue
            # اختلاف التوقيت: يُحسم بقفزة شمعة الدقيقة (≥ 3)، وإلّا يُحذف المكوّن (لا تسريب ولا ضجيج)
            cands = [(spike(r[0]) or 0.0, r[0])] + ([(spike(nb[0]) or 0.0, nb[0])] if nb is not None else [])
            best = max(cands)
            if best[0] >= SPIKE_MIN:
                final.append((best[1],) + tuple(r[1:]))
                verdict = "أُبقي" if best[1] == r[0] else "صُحّح إلى ميتاتريدر"
                tally[verdict] += 1
            else:
                verdict = "حُذف"
                tally["حُذف_لاختلاف_التوقيت"] += 1
            odd_t.append("%s %s ميتاتريدر=%s قفزة=%s ⟸ %s" % (fmt(r[0]), r[4], fmt(nb[0]) if nb else "—",
                                                            "/".join("%.1f" % c[0] for c in cands), verdict))
        # أكثر من صفٍّ للمكوّن في اليوم نفسه (نيويورك) بعد الحسم ⟸ مبهم، يُحذف كلّه
        per_day = Counter(datetime.fromtimestamp(r[0], NY).date() for r in final)
        amb = [r for r in final if per_day[datetime.fromtimestamp(r[0], NY).date()] > 1]
        final = [r for r in final if per_day[datetime.fromtimestamp(r[0], NY).date()] == 1]
        final.sort(key=lambda r: r[0])
        checks[nm] = {"مكرّر_محذوف": [fmt(res[k][0]) for k in sorted(drop)], "توقيت_ميتاتريدر": dict(tally),
                      "الفعليّ_مقابل_ميتاتريدر": dict(val), "توقيت_مختلف": odd_t[:40], "فعليّ_مختلف_أمثلة": odd_v[:8],
                      "مبهم_في_اليوم_محذوف": [fmt(r[0]) for r in amb]}
        series[nm] = final
    return checks


def surprises(series):
    comps = []
    eq = {}
    for nm, res in series.items():
        cat, sign = COMP[nm][0], COMP[nm][1]
        past = []
        n_eq = n_c = 0
        for at, a, c, p, src, rid, ra, rc in res:
            if a is None or c is None:
                continue
            s = a - c
            n_c += 1
            n_eq += abs(s) < 1e-12
            z = None
            if len(past) >= MIN_PAST:
                w = past[-WIN:]
                sd = statistics.stdev(w)
                if sd > 0:
                    z = s / sd
            comps.append({"T": at, "comp": nm, "cat": cat, "src": src, "actual": ra, "consensus": rc, "s": s,
                          "z": z, "sz": None if z is None else sign * z})
            past.append(s)
        eq[nm] = {"بإجماع": n_c, "الإجماع=الفعليّ": n_eq}
    comps.sort(key=lambda x: (x["T"], x["comp"]))
    return comps, eq


def main():
    t0 = time.time()
    rows = load_rows()
    print("صفوف المكوّنات: %d" % len(rows), flush=True)
    series, cdiag = classify(rows)
    mt5 = mt5_events()

    # الشموع: دقيقة الناسداك كاملة (وقت، أعلى، أدنى، إغلاق) كمصفوفات
    h = sqlite3.connect(HIST, uri=True)
    arr = np.array(h.execute("select period_start, high, low, close from candles_history where symbol='USTEC' and period='M1' "
                             "order by period_start").fetchall(), dtype=np.float64)
    tm, hi, lo, cl = arr[:, 0], arr[:, 1], arr[:, 2], arr[:, 3]
    print("دقائق: %d (%s ⟶ %s) · %.0f ث" % (len(tm), fmt(tm[0]), fmt(tm[-1]), time.time() - t0), flush=True)

    def close_at(t_end, tol=300):
        """إغلاق آخر دقيقة تنتهي عند t_end (تبدأ t_end−60)، أو أقرب سابقة خلال tol."""
        k = np.searchsorted(tm, t_end - 60, side="right") - 1
        if k < 0 or tm[k] < t_end - 60 - tol:
            return None
        return cl[k]

    def spike(t):
        k0 = np.searchsorted(tm, t)
        if k0 >= len(tm) or tm[k0] != t:
            return None
        kb = np.searchsorted(tm, t - 1800)
        base = hi[kb:k0] - lo[kb:k0]
        if len(base) < 15:
            return None
        med = float(np.median(base))
        return float((hi[k0] - lo[k0]) / med) if med > 0 else None

    checks = dedup_and_check(series, mt5, spike)
    comps, eq = surprises(series)
    print("مفاجآت: %d (بـz: %d) · %.0f ث" % (len(comps), sum(c["z"] is not None for c in comps), time.time() - t0), flush=True)

    # الإصدارات (كلّ ما في الدقيقة نفسها)
    groups = defaultdict(list)
    for c in comps:
        groups[c["T"]].append(c)
    clusters = []
    for T in sorted(groups):
        cs = groups[T]
        cats = defaultdict(list)
        for c in cs:
            if c["sz"] is not None:
                cats[c["cat"]].append(c["sz"])
        p0 = close_at(T)
        ret = {}
        if p0:
            for hh in HORIZONS:
                p = close_at(T + hh * 60, tol=120)
                ret[str(hh)] = None if p is None else (p / p0 - 1) * 1e4
            p15 = close_at(T + 900, tol=120)
            for hh in (60, 240):
                p = close_at(T + hh * 60, tol=120)
                ret["15-%d" % hh] = None if (p is None or p15 is None) else (p / p15 - 1) * 1e4
        clusters.append({"T": T, "src": cs[0]["src"], "comps": sorted({c["comp"] for c in cs}),
                         "cats": {k: sum(v) / len(v) for k, v in cats.items()}, "ret": ret,
                         "spike": {"T": spike(T), "T-1h": spike(T - 3600), "T+1h": spike(T + 3600)}})
    # فحص القفزة لكلّ فئة ومصدر
    sp = defaultdict(lambda: defaultdict(list))
    for cl_ in clusters:
        season = "صيف" if datetime.fromtimestamp(cl_["T"], NY).utcoffset().total_seconds() == -14400 else "شتاء"
        for cat in {COMP[n][0] for n in cl_["comps"]}:
            for k, v in cl_["spike"].items():
                if v is not None:
                    sp[(cat, cl_["src"] + "_" + season)][k].append(v)
    spike_tab = {"%s|%s" % key: {k: {"n": len(v), "وسيط": round(statistics.median(v), 2)} for k, v in d.items()}
                 for key, d in sorted(sp.items())}
    # مسح الإزاحة: أين تقع قفزة الوظائف والتضخّم سنةً سنة؟ (هل شموع الدقيقة القديمة مُزاحة؟)
    scan = {}
    offs = (-120, -60, -30, -3, -2, -1, 0, 1, 2, 3, 30, 60, 120)
    for cl_ in clusters:
        if not ({"تضخّم", "وظائف"} & {COMP[n][0] for n in cl_["comps"]}):
            continue
        y = datetime.fromtimestamp(cl_["T"], timezone.utc).year
        for o in offs:
            v = spike(cl_["T"] + o * 60)
            if v is not None:
                scan.setdefault(y, {}).setdefault(o, []).append(v)
    scan_tab = {y: {o: round(statistics.median(v), 2) for o, v in sorted(d.items())} for y, d in sorted(scan.items())}
    out = {"components": comps, "clusters": clusters,
           "checks": {"فرز_الشهريّ": cdiag, "ميتاتريدر": checks, "الإجماع_مقابل_الفعليّ": eq, "قفزة_الدقيقة": spike_tab, "مسح_الإزاحة_بالدقائق": scan_tab,
                      "دقائق_الناسداك": [fmt(tm[0]), fmt(tm[-1])]}}
    json.dump(out, open(os.path.join(HERE, "events.json"), "w", encoding="utf-8"), ensure_ascii=False)
    print(json.dumps(out["checks"], ensure_ascii=False, indent=1))
    print("انتهى: %.0f ث" % (time.time() - t0), flush=True)


if __name__ == "__main__":
    main()
