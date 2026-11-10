# -*- coding: utf-8 -*-
"""بطاقة المالك — الترجمة الثانية: المحرّك (قياسٌ فقط، خارج المشروع، قراءة البيانات وحدها).

التعريفات كلّها في prereg.json (كُتب قبل أيّ نتيجة). الأساس (الدقيقة · متوسّط مدى الخمس · قمم الربع ساعة والساعة
للأهداف · قمم الساعة للجهة · المدى اليوميّ) وأيّام الجلستين من القياس الأوّل (قراءة فقط)، والربع ساعة والخمس
تُقرأ من القاعدة للمناطق والتضييق. الإدارة R.thirds حرفًا (نسخة القياس الأوّل) والقمم R.swings حرفًا.
"""
import sys
sys.dont_write_bytecode = True

import bisect
import calendar
import os
import pickle
import sqlite3
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone

import numpy as np

T0 = time.time()
HERE = os.path.dirname(os.path.abspath(__file__))
OLD = os.path.join(os.path.dirname(HERE), "owner_card")
DB = "file:C:/Users/NQ/QUANT_NQ/forex_runtime/var/history/ctrader_history.db?mode=ro"
SYMBOL = "USTEC"
COST = 1.5
P_REF = 25000.0
START = calendar.timegm((2014, 7, 21, 0, 0, 0))
KEEP = 200
NDAYS = 5            # نافذة قمم/قيعان الربع ساعة (أيّام تقويميّة قبل القرار)
M_IMP = 15           # م: دقائق الاندفاع
TOLS = (0.0003, 0.0006)          # ع
SDS = ((2.0, 5), (5.0, 15))       # (س نقاط، د دقائق)
KS = (1.0, 2.5)                   # ك
DMAX = 15


def log(*a):
    print("[%5.0f ث]" % (time.time() - T0), *a, flush=True)


def fmt(t):
    return datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%d %H:%M")


# ───────── أدوات المسطرة (نسخٌ حرفيّة) ─────────
def swings_idx(rows, seconds, look=2):
    """R.swings حرفًا + فهرس شمعة المركز: (وقت التأكيد، السعر، قمّة؟، الفهرس)."""
    out = []
    for i in range(look, len(rows) - look):
        h, l = rows[i][2], rows[i][3]
        win = rows[i - look:i + look + 1]
        confirm = rows[i + look][0] + seconds
        if h == max(r[2] for r in win) and all(r[2] < h for r in win if r is not rows[i]):
            out.append((confirm, h, True, i))
        if l == min(r[3] for r in win) and all(r[3] > l for r in win if r is not rows[i]):
            out.append((confirm, l, False, i))
    out.sort()
    return out


def closed_index(times, seconds, t):
    return bisect.bisect_right(times, t - seconds) - 1


# ───────── الأساس من القياس الأوّل (قراءة فقط) ─────────
with open(os.path.join(OLD, "cache_base.pkl"), "rb") as _f:
    B = pickle.load(_f)
log("الأساس من القياس الأوّل")
MT, MO, MH, ML, MC = B["MT"], B["MO"], B["MH"], B["ML"], B["MC"]
MTn, MOn, MHn, MLn, MCn = (np.frombuffer(x, dtype=np.float64) for x in (MT, MO, MH, ML, MC))
T5, A5 = B["T5"], B["A5"]
TH1, CH1, TD1, AD1 = B["TH1"], B["CH1"], B["TD1"], B["AD1"]
CH1np = np.frombuffer(CH1, dtype=np.float64)
END = MT[-1]
NM1 = len(MT)
SPLIT = START + 0.7 * (END - START)

LV = {}
for side in ("H", "L"):
    c15 = np.array([x[0] for x in B["S15"][side]]); p15 = np.array([x[1] for x in B["S15"][side]])
    ch1 = np.array([x[0] for x in B["SH1"][side]]); ph1 = np.array([x[1] for x in B["SH1"][side]])
    LV[side] = ((c15, p15), (ch1, ph1))
SH = {s: (np.array([x[0] for x in B["SH1"][s]]), [x[1] for x in B["SH1"][s]], [x[2] for x in B["SH1"][s]])
      for s in ("H", "L")}

# ───────── الربع ساعة والخمس (قراءة من القاعدة، مخزَّنة هنا) ─────────
V2 = os.path.join(HERE, "cache_v2.pkl")


def _build_v2():
    db = sqlite3.connect(DB, uri=True)
    m15 = [tuple(map(float, r)) for r in db.execute(
        "select period_start, open, high, low, close from candles_history where symbol=? and period='M15' "
        "order by period_start", (SYMBOL,))]
    m5 = np.array(db.execute("select period_start, high, low from candles_history where symbol=? and period='M5' "
                             "order by period_start", (SYMBOL,)).fetchall(), dtype=float)
    db.close()
    sw = swings_idx(m15, 900)
    a15 = np.array(m15, dtype=float)
    v = {"T15": a15[:, 0].copy(), "O15": a15[:, 1].copy(), "H15": a15[:, 2].copy(), "L15": a15[:, 3].copy(),
         "C15": a15[:, 4].copy(), "SW": sw, "T5b": m5[:, 0].copy(), "H5b": m5[:, 1].copy(), "L5b": m5[:, 2].copy()}
    with open(V2, "wb") as f:
        pickle.dump(v, f, protocol=pickle.HIGHEST_PROTOCOL)
    return v


if os.path.exists(V2):
    with open(V2, "rb") as _f:
        V = pickle.load(_f)
else:
    V = _build_v2()
T15, O15, H15, L15, C15 = V["T15"], V["O15"], V["H15"], V["L15"], V["C15"]
T5b, H5b, L5b = V["T5b"], V["H5b"], V["L5b"]
log("الربع ساعة %d · الخمس %d" % (len(T15), len(T5b)))

# ───────── البحث الأوّل بالكتل ─────────
BS = 1024


def _blk(a, how):
    n = len(a)
    nb = -(-n // BS)
    pad = np.full(nb * BS, np.inf if how == "min" else -np.inf)
    pad[:n] = a
    pad = pad.reshape(nb, BS)
    return pad.min(1) if how == "min" else pad.max(1)


def first_lt(a, bm, s, p):
    """أوّل فهرس ≥ s قيمته < p، أو −1."""
    n = len(a)
    if s >= n:
        return -1
    b = s // BS
    e = min((b + 1) * BS, n)
    h = np.flatnonzero(a[s:e] < p)
    if h.size:
        return s + int(h[0])
    m = bm[b + 1:] < p
    if not m.any():
        return -1
    b2 = b + 1 + int(m.argmax())
    seg = a[b2 * BS:min((b2 + 1) * BS, n)]
    return b2 * BS + int(np.flatnonzero(seg < p)[0])


def first_gt(a, bm, s, p):
    n = len(a)
    if s >= n:
        return -1
    b = s // BS
    e = min((b + 1) * BS, n)
    h = np.flatnonzero(a[s:e] > p)
    if h.size:
        return s + int(h[0])
    m = bm[b + 1:] > p
    if not m.any():
        return -1
    b2 = b + 1 + int(m.argmax())
    seg = a[b2 * BS:min((b2 + 1) * BS, n)]
    return b2 * BS + int(np.flatnonzero(seg > p)[0])


BMIN_L, BMAX_H = _blk(MLn, "min"), _blk(MHn, "max")
BMIN_C, BMAX_C = _blk(MCn, "min"), _blk(MCn, "max")
BMIN_C15, BMAX_C15 = _blk(C15, "min"), _blk(C15, "max")


def a5_at(t):
    i = bisect.bisect_right(T5, t - 300) - 1
    assert T5[i] + 300 <= t
    return A5[i]


# ───────── قمم/قيعان الربع ساعة مع التضييق والأخذ ─────────
def _swing_table(is_high):
    rows = [x for x in V["SW"] if x[2] == is_high]
    rows.sort(key=lambda x: x[3])
    idx = np.array([x[3] for x in rows], dtype=np.int64)
    px = np.array([x[1] for x in rows])
    conf = np.array([x[0] for x in rows])
    start = T15[idx]
    a5i = np.searchsorted(T5b, start, "left"); b5i = np.searchsorted(T5b, start + 900, "left")
    other = np.empty(len(rows))      # للقاع: قمّة شمعة الخمس التي صنعته · للقمّة: قاعها
    for n, (a, b) in enumerate(zip(a5i, b5i)):
        if b <= a:
            other[n] = H15[idx[n]] if not is_high else L15[idx[n]]
            continue
        if is_high:
            j = a + int(np.argmax(H5b[a:b]))
            other[n] = L5b[j]
        else:
            j = a + int(np.argmin(L5b[a:b]))
            other[n] = H5b[j]
    s1 = np.searchsorted(MTn, start + 900, "left")
    take = np.empty(len(rows), dtype=np.int64)
    for n in range(len(rows)):
        take[n] = (first_gt(MHn, BMAX_H, int(s1[n]), px[n]) if is_high
                   else first_lt(MLn, BMIN_L, int(s1[n]), px[n]))
    takeT = np.where(take >= 0, MTn[np.maximum(take, 0)], np.inf)
    return {"idx": idx, "px": px, "conf": conf, "start": start, "other": other, "take": take, "takeT": takeT}


SWT = {}


def swing_tables():
    if not SWT:
        p = os.path.join(HERE, "cache_sw.pkl")
        if os.path.exists(p):
            with open(p, "rb") as f:
                SWT.update(pickle.load(f))
        else:
            SWT["L"] = _swing_table(False)
            SWT["H"] = _swing_table(True)
            with open(p, "wb") as f:
                pickle.dump(dict(SWT), f, protocol=pickle.HIGHEST_PROTOCOL)
        log("قيعان %d · قمم %d" % (len(SWT["L"]["px"]), len(SWT["H"]["px"])))
    return SWT


# ───────── المرشّحون العامّون (مستقلّون عن اليوم والعيار) ─────────
BADCONF = [0]


def s1_candidates(buy):
    """سحب السيولة: لكلّ قاعٍ (للشراء) أوّل نفاذٍ تحته وأوّل إغلاقٍ عائدٍ فوقه خلال ≤ 15 د."""
    S = swing_tables()["L" if buy else "H"]
    out = []
    for j in range(len(S["px"])):
        k0 = int(S["take"][j])
        if k0 < 0:
            continue
        p = S["px"][j]
        if S["conf"][j] > MT[k0]:          # اختلاف الربع ساعة عن الدقيقة (نادر) — يُترك
            BADCONF[0] += 1
            continue
        k = first_gt(MCn, BMAX_C, k0, p) if buy else first_lt(MCn, BMIN_C, k0, p)
        if k < 0:
            continue
        dur = MT[k] + 60 - MT[k0]
        if dur > DMAX * 60:
            continue
        if buy:
            seg = MLn[k0:k + 1]
            ks = k0 + int(np.argmin(seg))
            ext = MLn[ks]
            depth = p - ext
        else:
            seg = MHn[k0:k + 1]
            ks = k0 + int(np.argmax(seg))
            ext = MHn[ks]
            depth = ext - p
        tc = MT[k] + 60
        kw = bisect.bisect_left(MT, MT[ks] - M_IMP * 60)
        mv = (MHn[kw:ks + 1].max() - ext) if buy else (ext - MLn[kw:ks + 1].min())
        a5 = a5_at(tc)
        if a5 <= 0:
            continue
        out.append((tc, buy, j, p, k0, k, float(ext), float(depth), dur, float(mv / a5)))
    out.sort()
    return out


def s2_candidates(buy):
    """إعادة الاختبار: لكلّ قمّةٍ (للشراء) أوّل كسرٍ بإغلاق ربع ساعة فوقها، ثمّ أوّل عودةٍ إليها، ثمّ أوّل دقيقةٍ رافضة خلال ≤ 15 د."""
    S = swing_tables()["H" if buy else "L"]
    out = []
    tally = Counter()
    for j in range(len(S["px"])):
        p = S["px"][j]
        i15 = int(S["idx"][j])
        jb = first_gt(C15, BMAX_C15, i15 + 1, p) if buy else first_lt(C15, BMIN_C15, i15 + 1, p)
        if jb < 0:
            continue
        tb = T15[jb] + 900
        assert tb >= S["conf"][j]
        a, b = bisect.bisect_left(MT, tb - M_IMP * 60), bisect.bisect_left(MT, tb)
        if b <= a:
            tally["بلا_دقائق_الكسر"] += 1
            continue
        a5 = a5_at(tb)
        if a5 <= 0:
            continue
        imp = ((C15[jb] - MLn[a:b].min()) if buy else (MHn[a:b].max() - C15[jb])) / a5
        other = S["other"][j]          # للشراء: قاع شمعة الخمس (أدنى المنطقة) · للبيع: قمّتها (أعلى المنطقة)
        jf = first_lt(C15, BMIN_C15, jb + 1, other) if buy else first_gt(C15, BMAX_C15, jb + 1, other)
        tf = T15[jf] + 900 if jf >= 0 else np.inf
        s = bisect.bisect_left(MT, tb)
        kt = first_lt(MLn, BMIN_L, s, p + 1e-9) if buy else first_gt(MHn, BMAX_H, s, p - 1e-9)
        if kt < 0:
            continue
        found = None
        k = kt
        while k < NM1 and MT[k] + 60 - MT[kt] <= DMAX * 60:
            tc = MT[k] + 60
            if tc > tf:
                break
            o, h, l, c = MO[k], MH[k], ML[k], MC[k]
            rng = h - l
            if buy:
                ok = (min(ML[k - 1], l) <= p and c >= other and
                      ((rng > 0 and (min(o, c) - l) >= 0.6 * rng) or c > MH[k - 1]))
            else:
                ok = (max(MH[k - 1], h) >= p and c <= other and
                      ((rng > 0 and (h - max(o, c)) >= 0.6 * rng) or c < ML[k - 1]))
            if ok:
                found = k
                break
            k += 1
        if found is None:
            tally["بلا_رفض"] += 1
            continue
        k = found
        tc = MT[k] + 60
        ext = min(ML[k - 2], ML[k - 1], ML[k]) if buy else max(MH[k - 2], MH[k - 1], MH[k])
        out.append((tc, buy, j, p, kt, k, float(ext), float(other), tc - MT[kt], float(imp), tb, tf))
        tally["زناد"] += 1
    out.sort()
    return out, dict(tally)


CAND = {}


def candidates():
    if not CAND:
        p = os.path.join(HERE, "cache_cand.pkl")
        if os.path.exists(p):
            with open(p, "rb") as f:
                CAND.update(pickle.load(f))
        else:
            for buy in (True, False):
                CAND[("S1", buy)] = s1_candidates(buy)
                CAND[("S2", buy)], CAND[("S2tally", buy)] = s2_candidates(buy)
                log("مرشّحون", "شراء" if buy else "بيع", "S1", len(CAND[("S1", buy)]), "S2", len(CAND[("S2", buy)]),
                    CAND[("S2tally", buy)])
            with open(p, "wb") as f:
                pickle.dump(dict(CAND), f, protocol=pickle.HIGHEST_PROTOCOL)
        for key in list(CAND):
            if key[0] in ("S1", "S2"):
                CAND[("tc",) + key] = [x[0] for x in CAND[key]]
    return CAND


# ───────── الهدف (كالقياس الأوّل حرفًا) ─────────
def target_for(tc, buy, entry, risk, marg, cost, reach):
    (c15, p15), (ch1, ph1) = LV["H" if buy else "L"]
    k1 = bisect.bisect_right(c15, tc); k2 = bisect.bisect_right(ch1, tc)
    lv = np.concatenate((p15[max(0, k1 - KEEP):k1], ph1[max(0, k2 - KEEP):k2]))
    if k1:
        assert c15[k1 - 1] <= tc
    if k2:
        assert ch1[k2 - 1] <= tc
    if not lv.size:
        return None, None
    tg = (lv - marg) if buy else (lv + marg)
    dist = (tg - entry) if buy else (entry - tg)
    ok = (dist > 0) & ((dist - cost) / (risk + cost) + 1e-9 >= 3.0) & (dist <= reach)
    if not ok.any():
        return None, None
    i = int(np.argmin(np.where(ok, dist, np.inf)))
    return float(tg[i]), float((dist[i] - cost) / (risk + cost))


# ───────── جهة الساعة ─────────
def hour_dirs(t):
    """(هـ1، هـ2) من قمم/قيعان الساعة المؤكَّدة ≤ t وإغلاقات الساعة المغلقة ≤ t."""
    ch, ph, ih = SH["H"]
    cl, pl, il = SH["L"]
    a = bisect.bisect_right(ch, t) - 1
    b = bisect.bisect_right(cl, t) - 1
    if a < 1 or b < 1:
        return 0, 0
    assert ch[a] <= t and cl[b] <= t
    H1, H2, L1, L2 = ph[a], ph[a - 1], pl[b], pl[b - 1]
    up1 = H1 > H2 and L1 > L2
    dn1 = H1 < H2 and L1 < L2
    h1 = 1 if up1 else -1 if dn1 else 0
    jl = closed_index(TH1, 3600, t)
    assert TH1[jl] + 3600 <= t
    brk_up = jl > ih[a] and CH1np[ih[a] + 1:jl + 1].max() > H1
    brk_dn = jl > il[b] and CH1np[il[b] + 1:jl + 1].min() < L1
    up2 = up1 or (L1 > L2 and brk_up)
    dn2 = dn1 or (H1 < H2 and brk_dn)
    h2 = 0 if (up2 and dn2) else 1 if up2 else -1 if dn2 else 0
    return h1, h2


def load_sessions(kind):
    with open(os.path.join(OLD, "sess_%s.pkl" % kind), "rb") as f:
        ss = pickle.load(f)[0]
    for s in ss:
        s["dir"]["هـ1"], s["dir"]["هـ2"] = hour_dirs(s["D"])
    return ss


# ───────── أحداث الجلسة ─────────
# الحدث: 0 tc · 1 buy · 2 النوع (1=S1، 2=S2) · 3 الدخول · 4 الوقف · 5 الخطر · 6 الهدف · 7 الصافي · 8 k · 9 الكلفة · 10 f
#        11 السبب · 12 العمق · 13 المدّة/التأخّر ث · 14 نسبة الاندفاع · 15،16 أعضاء ع1،ع2 · 17،18 حجبٌ ع1،ع2 · 19 الخطر÷f
#        20 مصدر المنطقة (j) · 21 خطّ المنطقة
def pool_info(buy, j, k0, lb):
    """أعضاء المجمّع والحجب لكلّ ع (عند بداية شمعة النفاذ k0)، بنافذة القمم/القيعان من lb."""
    S = swing_tables()["L" if buy else "H"]
    p = S["px"][j]
    sj = S["start"][j]
    a = int(np.searchsorted(S["start"], lb, "left"))
    b = int(np.searchsorted(S["conf"], MT[k0], "right"))
    memb = [0, 0]
    blk = [False, False]
    for q in range(a, b):
        if q == j:
            continue
        pq = S["px"][q]
        assert S["conf"][q] <= MT[k0] and S["start"][q] >= lb
        older_ok = S["start"][q] >= sj or S["takeT"][q] >= sj
        intact_k0 = S["take"][q] < 0 or S["take"][q] >= k0
        for e, tol in enumerate(TOLS):
            if buy:
                if p <= pq <= p * (1 + tol) and older_ok:
                    memb[e] += 1
                elif p * (1 - tol) <= pq < p and intact_k0:
                    blk[e] = True
            else:
                if p * (1 - tol) <= pq <= p and older_ok:
                    memb[e] += 1
                elif p < pq <= p * (1 + tol) and intact_k0:
                    blk[e] = True
    return memb, blk


def build_events(spans, track="نقاط", ndays=NDAYS):
    C = candidates()
    S_ = swing_tables()
    out, tally = {}, Counter()
    for sp in spans:
        f = (sp["C_D"] / P_REF) if track == "نسبيّ" else 1.0
        floor_, cap_, buf_, marg_, cost_ = 10.0 * f, 50.0 * f, 1.0 * f, 2.0 * f, COST * f
        lb = sp["D"] - ndays * 86400
        evs = []
        for buy in (True, False):
            for typ in ("S1", "S2"):
                lst, tcs = C[(typ, buy)], C[("tc", typ, buy)]
                a, b = bisect.bisect_right(tcs, sp["D"]), bisect.bisect_right(tcs, sp["X"])
                src = S_["L" if buy else "H"] if typ == "S1" else S_["H" if buy else "L"]
                for c in lst[a:b]:
                    j = c[2]
                    if src["start"][j] < lb:
                        continue
                    tc, k = c[0], c[5]
                    assert sp["D"] < tc <= sp["X"] and MT[k] + 60 == tc
                    if typ == "S1":
                        memb, blk = pool_info(buy, j, c[4], lb)
                        if not any(memb[e] >= 1 and not blk[e] for e in range(2)):
                            tally["S1_بلا_مجمّع"] += 1
                            continue
                        ext, depth, dur, ratio = c[6], c[7], c[8], c[9]
                    else:
                        memb, blk = [1, 1], [False, False]
                        ext, depth, dur, ratio = c[6], 0.0, c[8], c[9]
                        assert c[10] <= tc <= c[11]
                    entry = MC[k]
                    stop = (ext - buf_) if buy else (ext + buf_)
                    risk = abs(entry - stop)
                    assert (entry > stop) if buy else (entry < stop)
                    if risk < floor_:
                        stop = entry - floor_ if buy else entry + floor_
                        risk = floor_
                    target = net = None
                    reason = ""
                    if risk > cap_:
                        reason = "وقف>50"
                    else:
                        idd = closed_index(TD1, 86400, tc)
                        assert TD1[idd] + 86400 <= tc
                        target, net = target_for(tc, buy, entry, risk, marg_, cost_, 1.0 * AD1[idd])
                        if target is None:
                            reason = "بلا_هدف"
                    tally["%s_%s" % (typ, reason or "صالح")] += 1
                    evs.append((tc, buy, 1 if typ == "S1" else 2, entry, stop, risk, target, net, k, cost_, f, reason,
                                depth, dur, ratio, memb[0], memb[1], blk[0], blk[1], risk / f, j, c[3]))
        evs.sort(key=lambda e: (e[0], e[2], not e[1]))
        out[sp["id"]] = evs
    return out, dict(tally)


def passes(ev, trig, ei, sdi, K):
    s_, d_ = SDS[sdi]
    if ev[2] == 1:
        if trig == "S2":
            return False
        if ev[15 + ei] < 1 or ev[17 + ei]:
            return False
        if ev[12] < s_ * ev[10]:
            return False
    else:
        if trig == "S1":
            return False
    return ev[13] <= d_ * 60 and ev[14] >= K


# ───────── الإدارة: R.thirds حرفًا (نسخة القياس الأوّل) ─────────
def thirds(entry, stop, target, buy, k, cost=COST):
    risk, span, sgn_ = abs(entry - stop), abs(target - entry), (1 if buy else -1)
    t1_, t2_ = entry + sgn_ * span / 3, entry + sgn_ * 2 * span / 3
    cur, rem, real, stage = stop, 1.0, 0.0, 0
    while k < NM1:
        t, o, h, lo = MT[k], MO[k], MH[k], ML[k]
        if (lo <= cur) if buy else (h >= cur):
            px = min(o, cur) if buy else max(o, cur)
            return real + rem * ((px - entry) * sgn_ / risk) - cost / risk, t, stage
        if buy:
            if stage < 1 and h >= t1_:
                real += (rem / 3) * (span / 3 / risk); rem -= rem / 3; cur = entry; stage = 1
            if stage < 2 and h >= t2_:
                real += (rem / 2) * (2 * span / 3 / risk); rem -= rem / 2; cur = t1_; stage = 2
            if h >= target:
                return real + rem * (span / risk) - cost / risk, t, 3
        else:
            if stage < 1 and lo <= t1_:
                real += (rem / 3) * (span / 3 / risk); rem -= rem / 3; cur = entry; stage = 1
            if stage < 2 and lo <= t2_:
                real += (rem / 2) * (2 * span / 3 / risk); rem -= rem / 2; cur = t1_; stage = 2
            if lo <= target:
                return real + rem * (span / risk) - cost / risk, t, 3
        k += 1
    return None


_SIM = {}


def sim(ev, cost_mult=1.0):
    k = ev[8]
    assert k + 1 >= NM1 or MT[k + 1] >= ev[0]
    key = (k, ev[1], ev[3], ev[4], ev[6], ev[9] * cost_mult)
    if key not in _SIM:
        _SIM[key] = thirds(ev[3], ev[4], ev[6], ev[1], k + 1, ev[9] * cost_mult)
    return _SIM[key]


# ───────── تشغيل تركيبة ─────────
def run(sessions, evmap, dmode, trig, ei, sdi, K, maxn=2, end_key="E", cost_mult=1.0):
    """الصفقة: (tc, r, kind, buy, risk÷f, exit_t, entry, stop, target, stage, k, f, oracle, bps, typ)."""
    trades, busy, tally = [], 0.0, Counter()
    for sd in sessions:
        d = 0 if dmode == "ج0" else sd["dir"][dmode]
        if dmode != "ج0" and d == 0:
            tally["بلا_جهة"] += 1
            continue
        n = 0
        lim = sd[end_key]
        for ev in evmap.get(sd["id"], ()):
            if ev[0] > lim or n >= maxn:
                break
            if ev[0] < busy:
                continue
            if d and ev[1] != (d > 0):
                continue
            if not passes(ev, trig, ei, sdi, K):
                continue
            if ev[6] is None:
                tally[ev[11]] += 1
                continue
            res = sim(ev, cost_mult)
            if res is None:
                tally["غير_منتهية"] += 1
                continue
            r, exit_t, stage = res
            trades.append((ev[0], r, sd["kind"], ev[1], ev[19], exit_t, ev[3], ev[4], ev[6], stage, ev[8], ev[10],
                           sd["dir"]["ج★"], ev[5] / ev[3] * 1e4, ev[2]))
            busy = exit_t + 60
            n += 1
        tally["أيّام_بجهة"] += 1
    return trades, dict(tally)


# ───────── الإحصاء (كالقياس الأوّل) ─────────
def months(a, b):
    return (b - a) / 86400 / 30.4375


def stats(tr, a=None, b=None):
    if not tr:
        return {"n": 0}
    rs = [x[1] for x in tr]
    n = len(rs)
    wins = sum(r > 0 for r in rs)
    gp = sum(r for r in rs if r > 0); gl = -sum(r for r in rs if r < 0)
    eq = peak = dd = 0.0
    for r in rs:
        eq += r; peak = max(peak, eq); dd = max(dd, peak - eq)
    halves = defaultdict(float); years = defaultdict(lambda: [0, 0.0])
    for x in tr:
        dt = datetime.fromtimestamp(x[0], timezone.utc)
        halves["%d%s" % (dt.year, "أ" if dt.month <= 6 else "ب")] += x[1]
        years[dt.year][0] += 1; years[dt.year][1] += x[1]
    mean = sum(rs) / n
    sd = (sum((r - mean) ** 2 for r in rs) / (n - 1)) ** 0.5 if n > 1 else 0.0
    out = {"n": n, "فوز%": round(100 * wins / n), "R": round(sum(rs), 1), "R/صفقة": round(mean, 3),
           "خطأ_معياريّ": round(sd / n ** 0.5, 3), "معامل": round(gp / gl, 2) if gl else None, "سحب_R": round(dd, 1),
           "أنصاف": {k: round(v, 1) for k, v in sorted(halves.items())},
           "سنوات": {str(y): [v[0], round(v[1], 1)] for y, v in sorted(years.items())}}
    if a is not None:
        out["صفقات/شهر"] = round(n / months(a, b), 2)
    return out


def test_halves():
    keys = []
    y0 = datetime.fromtimestamp(SPLIT, timezone.utc).year
    y1 = datetime.fromtimestamp(END, timezone.utc).year
    for y in range(y0, y1 + 1):
        for h, (a, b) in (("أ", ((y, 1, 1), (y, 7, 1))), ("ب", ((y, 7, 1), (y + 1, 1, 1)))):
            ta = calendar.timegm(a + (0, 0, 0)); tb = calendar.timegm(b + (0, 0, 0))
            cov = min(tb, END) - max(ta, SPLIT)
            if cov >= 91 * 86400:
                keys.append("%d%s" % (y, h))
    return keys


TEST_HALVES = test_halves()


def owner_pass(T):
    halves = T.get("أنصاف") or {}
    pos = sum(1 for k in TEST_HALVES if halves.get(k, 0.0) > 0)
    checks = {"اختبار_R/صفقة>0": (T.get("R/صفقة") or -1) > 0,
              "اختبار_معامل≥1.15": (T.get("معامل") or 0) >= 1.15,
              "أنصاف_الاختبار_الموجبة≥80٪": pos >= 0.8 * len(TEST_HALVES),
              "اختبار_n≥30": T.get("n", 0) >= 30}
    return {"شروط": checks, "أنصاف_موجبة": "%d/%d" % (pos, len(TEST_HALVES)), "يجتاز": all(checks.values())}


def pack(tr):
    L = [x for x in tr if x[0] < SPLIT]; T = [x for x in tr if x[0] >= SPLIT]
    out = {"تعلّم": stats(L, START, SPLIT), "اختبار": stats(T, SPLIT, END), "كلّه": stats(tr, START, END)}
    out["معيار_المالك"] = owner_pass(out["اختبار"])
    return out


STAGE_NAMES = {0: "الوقف_الأصليّ_−1R", 1: "الأوّل_ثمّ_التعادل", 2: "الهدفان_ثمّ_وقف_الأوّل", 3: "الهدف_الثالث"}


def stage_dist(tr, unfinished=0):
    n = len(tr)
    if not n:
        return {"n": 0, "غير_منتهية": unfinished}
    c = Counter(x[9] for x in tr)
    out = {"n": n}
    for s, name in STAGE_NAMES.items():
        out[name + "%"] = round(100.0 * c.get(s, 0) / n, 1)
    out["بلغ_الأوّل%"] = round(100.0 * sum(c.get(s, 0) for s in (1, 2, 3)) / n, 1)
    out["غير_منتهية"] = unfinished
    out["الثالث_يتجاوز_40٪"] = c.get(3, 0) / n > 0.40
    return out


def cached(name, fn):
    p = os.path.join(HERE, name)
    if os.path.exists(p):
        with open(p, "rb") as f:
            return pickle.load(f)
    v = fn()
    with open(p, "wb") as f:
        pickle.dump(v, f, protocol=pickle.HIGHEST_PROTOCOL)
    return v
