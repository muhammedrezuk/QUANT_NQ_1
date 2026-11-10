# -*- coding: utf-8 -*-
"""بطاقة المالك اليدويّة — المحرّك (قياسٌ فقط، خارج المشروع، قراءة البيانات وحدها).

التعريفات كلّها في prereg.json (كُتب قبل أيّ نتيجة). الإدارة R.thirds حرفًا على مصفوفات الدقيقة الكاملة،
والقمم/القيعان R.swings حرفًا (مع فهرس الشمعة)، ومتوسّط المدى والمتوسّط الأسّيّ كالمسطرة.
"""
import sys
sys.dont_write_bytecode = True

import bisect
import calendar
import os
import pickle
import sqlite3
import time
from array import array
from collections import Counter, defaultdict
from datetime import datetime, timezone, timedelta

import numpy as np

sys.path.insert(0, r"C:\Users\NQ\QUANT_NQ")
from shared.owner_windows import london_offset_h, new_york_offset_h  # noqa: E402

T0 = time.time()
HERE = os.path.dirname(os.path.abspath(__file__))
DB = "file:C:/Users/NQ/QUANT_NQ/forex_runtime/var/history/ctrader_history.db?mode=ro"
SYMBOL = "USTEC"
COST = 1.5
P_REF = 25000.0
START = calendar.timegm((2014, 7, 21, 0, 0, 0))
KEEP = 200            # آخر 200 قمّة لكلّ إطار في سلّم الأهداف (كسلّم المسطرة)


def log(*a):
    print("[%5.0f ث]" % (time.time() - T0), *a, flush=True)


def fmt(t):
    return datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%d %H:%M")


# ───────── أدوات المسطرة (نسخٌ حرفيّة) ─────────
def ema(values, n=20):
    k, out, e = 2.0 / (n + 1), [], None
    for v in values:
        e = v if e is None else v * k + e * (1 - k)
        out.append(e)
    return out


def atr(rows, n=14):
    out, trs, prev = [], [], None
    for t, o, h, l, c in rows:
        tr = h - l if prev is None else max(h - l, abs(h - prev), abs(l - prev))
        trs.append(tr); prev = c
        w = trs[-n:]
        out.append(sum(w) / len(w))
    return out


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


# ───────── التحميل (مخزَّن) ─────────
BASE_CACHE = os.path.join(HERE, "cache_base.pkl")


def _rows(db, period):
    return [tuple(map(float, r)) for r in db.execute(
        "select period_start, open, high, low, close from candles_history where symbol=? and period=? "
        "order by period_start", (SYMBOL, period))]


def _build_base():
    db = sqlite3.connect(DB, uri=True)
    MT, MO, MH, ML, MC = (array("d") for _ in range(5))
    for t, o, h, l, c in db.execute(
            "select period_start, open, high, low, close from candles_history where symbol=? and period='M1' "
            "order by period_start", (SYMBOL,)):
        MT.append(float(t)); MO.append(float(o)); MH.append(float(h)); ML.append(float(l)); MC.append(float(c))
    log("دقيقة: %d (%s ⟶ %s)" % (len(MT), fmt(MT[0]), fmt(MT[-1])))
    m5 = _rows(db, "M5")
    T5 = array("d", [r[0] for r in m5]); A5 = array("d", atr(m5))
    sw5 = swings_idx(m5, 300)
    SW5 = {"H": [(c, p, m5[i][0]) for c, p, h, i in sw5 if h], "L": [(c, p, m5[i][0]) for c, p, h, i in sw5 if not h]}
    del m5, sw5
    log("5 د")
    m15 = _rows(db, "M15")
    sw15 = swings_idx(m15, 900)
    S15 = {"H": [(c, p) for c, p, h, i in sw15 if h], "L": [(c, p) for c, p, h, i in sw15 if not h]}
    del m15, sw15
    log("ربع ساعة")
    h1 = _rows(db, "H1")
    TH1 = array("d", [r[0] for r in h1]); CH1 = array("d", [r[4] for r in h1]); EH1 = array("d", ema([r[4] for r in h1]))
    swh = swings_idx(h1, 3600)
    SH1 = {"H": [(c, p, i) for c, p, h, i in swh if h], "L": [(c, p, i) for c, p, h, i in swh if not h]}
    h4 = _rows(db, "H4")
    TH4 = array("d", [r[0] for r in h4]); CH4 = array("d", [r[4] for r in h4]); EH4 = array("d", ema([r[4] for r in h4]))
    d1 = _rows(db, "D1")
    TD1 = array("d", [r[0] for r in d1]); AD1 = array("d", atr(d1))
    db.close()
    base = dict(MT=MT, MO=MO, MH=MH, ML=ML, MC=MC, T5=T5, A5=A5, SW5=SW5, S15=S15, TH1=TH1, CH1=CH1, EH1=EH1,
                SH1=SH1, TH4=TH4, CH4=CH4, EH4=EH4, TD1=TD1, AD1=AD1)
    with open(BASE_CACHE, "wb") as f:
        pickle.dump(base, f, protocol=pickle.HIGHEST_PROTOCOL)
    return base


if os.path.exists(BASE_CACHE):
    with open(BASE_CACHE, "rb") as _f:
        B = pickle.load(_f)
    log("الأساس من المخزن")
else:
    B = _build_base()

MT, MO, MH, ML, MC = B["MT"], B["MO"], B["MH"], B["ML"], B["MC"]
T5, A5 = B["T5"], B["A5"]
TH1, CH1, EH1, TH4, CH4, EH4, TD1, AD1 = (B[k] for k in ("TH1", "CH1", "EH1", "TH4", "CH4", "EH4", "TD1", "AD1"))
CH1np = np.frombuffer(CH1, dtype=np.float64)
END = MT[-1]
NM1 = len(MT)
SPLIT = START + 0.7 * (END - START)

# القمم/القيعان مصفوفاتٍ مرتّبة بوقت التأكيد
SW5H_c = array("d", [x[0] for x in B["SW5"]["H"]]); SW5H_p = [x[1] for x in B["SW5"]["H"]]; SW5H_s = [x[2] for x in B["SW5"]["H"]]
SW5L_c = array("d", [x[0] for x in B["SW5"]["L"]]); SW5L_p = [x[1] for x in B["SW5"]["L"]]; SW5L_s = [x[2] for x in B["SW5"]["L"]]
LV = {}
for side in ("H", "L"):
    c15 = np.array([x[0] for x in B["S15"][side]]); p15 = np.array([x[1] for x in B["S15"][side]])
    ch1 = np.array([x[0] for x in B["SH1"][side]]); ph1 = np.array([x[1] for x in B["SH1"][side]])
    LV[side] = ((c15, p15), (ch1, ph1))
ZS = {}
for side in ("H", "L"):
    ZS[side] = (array("d", [x[0] for x in B["SH1"][side]]), [x[1] for x in B["SH1"][side]], [x[2] for x in B["SH1"][side]])


def sgn(x):
    return 1 if x > 0 else -1 if x < 0 else 0


# ───────── الجلسات ─────────
SESS = {
    #        دالّة الفرق        الافتتاح  القرار  النهاية  النهاية_القصوى (دقائق محلّيّة)
    "ny": (new_york_offset_h, 570, 585, 780, 810),
    "lon": (london_offset_h, 480, 495, 660, 690),
    "his": (lambda t: 0, 315, 330, 420, 420),
}


def count_bars(a, b):
    """عدد شموع الدقيقة التي تبدأ في [a، b)."""
    return bisect.bisect_left(MT, b) - bisect.bisect_left(MT, a)


def session_days(kind):
    fn, o_m, d_m, e_m, x_m = SESS[kind]
    out, tally = [], Counter()
    d = datetime.fromtimestamp(START, timezone.utc).date()
    end_d = datetime.fromtimestamp(END, timezone.utc).date()
    while d <= end_d:
        if d.weekday() < 5:
            naive0 = calendar.timegm((d.year, d.month, d.day, 0, 0, 0))
            off = fn(naive0 + 12 * 3600)
            base = naive0 - off * 3600
            O, D, E, X = (base + m * 60 for m in (o_m, d_m, e_m, x_m))
            tally["أيّام_عمل"] += 1
            if X > END:
                tally["بعد_النهاية"] += 1
            elif count_bars(O - 3600, O) < 45 or count_bars(O, D) < 10 or count_bars(D, E) < 0.6 * (E - D) / 60:
                tally["بيانات_ناقصة"] += 1
            else:
                sd = {"id": "%s_%s" % (kind, d.isoformat()), "date": d.isoformat(), "kind": kind,
                      "O": O, "D": D, "E": E, "X": X}
                sd.update(directions(sd))
                out.append(sd)
                tally["صالحة"] += 1
        d += timedelta(days=1)
    return out, dict(tally)


def directions(sd):
    O, D, E = sd["O"], sd["D"], sd["E"]
    kD = bisect.bisect_right(MT, D - 60) - 1
    assert MT[kD] + 60 <= D
    C_D = MC[kD]
    kpre = bisect.bisect_left(MT, O - 3600); kO = bisect.bisect_left(MT, O)
    assert MT[kpre] + 60 <= D and MT[kO] + 60 <= D
    j1 = sgn(C_D - MO[kpre]); j2 = sgn(C_D - MO[kO])
    ih = bisect.bisect_right(SW5H_c, D) - 1; il = bisect.bisect_right(SW5L_c, D) - 1
    j3 = 0
    if ih >= 0 and il >= 0 and SW5H_s[ih] >= O - 7200 and SW5L_s[il] >= O - 7200:
        assert SW5H_c[ih] <= D and SW5L_c[il] <= D
        j3 = 1 if C_D > SW5H_p[ih] else -1 if C_D < SW5L_p[il] else 0
    i1, i4 = closed_index(TH1, 3600, D), closed_index(TH4, 14400, D)
    j4 = 0
    if i1 >= 20 and i4 >= 20:
        assert TH1[i1] + 3600 <= D and TH4[i4] + 14400 <= D
        up = CH1[i1] > EH1[i1] and CH4[i4] > EH4[i4]
        dn = CH1[i1] < EH1[i1] and CH4[i4] < EH4[i4]
        j4 = 1 if up else -1 if dn else 0
    kE = bisect.bisect_right(MT, E - 60) - 1
    js = sgn(MC[kE] - C_D)            # العرّاف: من المستقبل — للعلم وحده
    return {"C_D": C_D, "dir": {"ج1": j1, "ج2": j2, "ج3": j3, "ج4": j4, "ج★": js}}


# ───────── المناطق ─────────
def zones_at(t, buy, tol, ndays, wmin):
    """مناطق الساعة الفعّالة عند اللحظة t (ساعة كاملة): للشراء مقاوماتٌ كُسرت فصارت دعمًا، وللبيع العكس."""
    conf, px, bi = ZS["H" if buy else "L"]
    lim = t - ndays * 86400
    i = bisect.bisect_right(conf, t) - 1
    cands = []
    while i >= 0 and conf[i] >= lim:
        if TH1[bi[i]] >= lim:
            cands.append((px[i], bi[i]))
        i -= 1
    if len(cands) < 2:
        return []
    cands.sort()
    j = closed_index(TH1, 3600, t)
    assert TH1[j] + 3600 <= t
    zones = []

    def flush(g):
        if len(g) < 2:
            return
        lo, hi = g[0][0], g[-1][0]
        ilast = max(b for _, b in g)
        c = (lo + hi) / 2.0
        if hi - lo < wmin * c:
            lo, hi = c - wmin * c / 2.0, c + wmin * c / 2.0
        seg = CH1np[ilast + 1:j + 1]
        if not seg.size:
            return
        up = np.flatnonzero(seg > hi); dn = np.flatnonzero(seg < lo)
        lu = up[-1] if up.size else -1
        ld = dn[-1] if dn.size else -1
        if (lu > ld) if buy else (ld > lu):
            zones.append((lo, hi, ilast))

    g = [cands[0]]
    for p in cands[1:]:
        if p[0] - g[0][0] <= tol * g[0][0]:
            g.append(p)
        else:
            flush(g); g = [p]
    flush(g)
    return zones


# ───────── الأحداث (كلّ زنادٍ مرشّح، مستقلٌّ عن الجهة والعدد) ─────────
BASEP = {"tol": 0.0020, "ndays": 14, "wmin": 0.0010, "m": 30}


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


def build_events(spans, P=None, track="نقاط"):
    """spans: قوائم {id, D, X, C_D}. يُرجع {id: [حدث…]} مرتّبةً بالزمن (الشراء أوّلًا عند التساوي).
    الحدث: (tc, buy, slap, choke, ratio, entry, stop, risk, target, net, k, zlo, zhi, reason, cost, f)."""
    P = dict(BASEP, **(P or {}))
    tol, ndays, wmin, m = P["tol"], P["ndays"], P["wmin"], P["m"]
    zc = {}
    out = {}
    tally = Counter()
    for sp in spans:
        f = (sp["C_D"] / P_REF) if track == "نسبيّ" else 1.0
        floor_, cap_, buf_, marg_, cost_ = 10.0 * f, 50.0 * f, 1.0 * f, 2.0 * f, COST * f
        k_from = max(bisect.bisect_right(MT, sp["D"] - 60), 3)
        k_to = bisect.bisect_right(MT, sp["X"] - 60) - 1
        evs = []
        for k in range(k_from, k_to + 1):
            tc = MT[k] + 60
            hb = tc - (tc % 3600)
            for buy in (True, False):
                key = (hb, buy)
                zl = zc.get(key)
                if zl is None:
                    zl = zc[key] = zones_at(hb, buy, tol, ndays, wmin)
                if not zl:
                    continue
                if buy:
                    ext = min(ML[k - 2], ML[k - 1], ML[k])
                    best = None
                    for z in zl:
                        w = z[1] - z[0]
                        if z[0] - 0.5 * w <= ext <= z[1] and (best is None or z[1] > best[1]):
                            best = z
                else:
                    ext = max(MH[k - 2], MH[k - 1], MH[k])
                    best = None
                    for z in zl:
                        w = z[1] - z[0]
                        if z[0] <= ext <= z[1] + 0.5 * w and (best is None or z[0] < best[0]):
                            best = z
                if best is None:
                    continue
                tally["لمس"] += 1
                zlo, zhi = best[0], best[1]
                w = zhi - zlo
                kw = bisect.bisect_left(MT, tc - m * 60)
                istar = k
                if buy:
                    ex = ML[k]
                    for i in range(k - 1, kw - 1, -1):
                        if ML[i] < ex:
                            ex = ML[i]; istar = i
                else:
                    ex = MH[k]
                    for i in range(k - 1, kw - 1, -1):
                        if MH[i] > ex:
                            ex = MH[i]; istar = i
                if istar < k - 2:
                    tally["القاع_ليس_حديثًا"] += 1
                    continue
                ia5 = bisect.bisect_right(T5, tc - 300) - 1
                assert T5[ia5] + 300 <= tc
                a5 = A5[ia5]
                if a5 <= 0:
                    continue
                if buy:
                    move = max(MH[kw:istar + 1]) - ML[istar]
                else:
                    move = MH[istar] - min(ML[kw:istar + 1])
                ratio = move / a5
                o, h, lo_, c = MO[k], MH[k], ML[k], MC[k]
                rng = h - lo_
                if buy:
                    slap = (zlo - 0.5 * w <= lo_ <= zhi) and rng >= 0.5 * a5 and (c - lo_) >= 0.6 * rng and c >= zlo
                    choke = (istar in (k - 1, k - 2) and c > MH[k - 1] and c >= zlo
                             and (istar == k - 1 or MC[k - 1] <= MH[k - 2]))
                else:
                    slap = (zlo <= h <= zhi + 0.5 * w) and rng >= 0.5 * a5 and (h - c) >= 0.6 * rng and c <= zhi
                    choke = (istar in (k - 1, k - 2) and c < ML[k - 1] and c <= zhi
                             and (istar == k - 1 or MC[k - 1] >= ML[k - 2]))
                if not (slap or choke):
                    continue
                tally["زناد"] += 1
                entry = c
                stop = (ext - buf_) if buy else (ext + buf_)
                risk = abs(entry - stop)
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
                tally[reason or "صالح"] += 1
                evs.append((tc, buy, slap, choke, ratio, entry, stop, risk, target, net, k, zlo, zhi, reason,
                            cost_, f))
        out[sp["id"]] = evs
    return out, dict(tally)


# ───────── الإدارة: R.thirds حرفًا على المصفوفات ─────────
def thirds(entry, stop, target, buy, k, cost=COST, cap_t=None):
    """R.thirds حرفًا (الكلفة معامل) + المرحلة. cap_t (للعلم فقط): يُغلق الباقي بافتتاح أوّل شمعةٍ تبدأ ≥ cap_t."""
    risk, span, sgn_ = abs(entry - stop), abs(target - entry), (1 if buy else -1)
    t1_, t2_ = entry + sgn_ * span / 3, entry + sgn_ * 2 * span / 3
    cur, rem, real, stage = stop, 1.0, 0.0, 0
    while k < NM1:
        t, o, h, lo = MT[k], MO[k], MH[k], ML[k]
        if cap_t is not None and t >= cap_t:
            return real + rem * ((o - entry) * sgn_ / risk) - cost / risk, t, -stage - 1
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


def sim(ev, cost_mult=1.0, cap_t=None):
    k = ev[10]
    assert MT[k + 1] >= ev[0] if k + 1 < NM1 else True
    key = (k, ev[1], ev[5], ev[6], ev[8], ev[14] * cost_mult, cap_t)
    if key not in _SIM:
        _SIM[key] = thirds(ev[5], ev[6], ev[8], ev[1], k + 1, ev[14] * cost_mult, cap_t)
    return _SIM[key]


# ───────── تشغيل تركيبة ─────────
DMODES = ("ج0", "ج1", "ج2", "ج3", "ج4")


def run(sessions, evmap, dmode, trig, K, maxn, end_key="E", cost_mult=1.0, cap_fn=None):
    """صفقات التركيبة: (tc, r, kind, buy, risk_pts_equiv, exit_t, entry, stop, target, stage, k, f, oracle, bps)."""
    trades, busy, tally = [], 0.0, Counter()
    for sd in sessions:
        d = 0 if dmode == "ج0" else sd["dir"][dmode]
        if dmode != "ج0" and d == 0:
            tally["بلا_جهة"] += 1
            continue
        n = 0
        lim = sd[end_key]
        cap_t = cap_fn(sd) if cap_fn else None
        for ev in evmap.get(sd["id"], ()):
            if ev[0] > lim or n >= maxn:
                break
            if ev[0] < busy:
                continue
            if d and ev[1] != (d > 0):
                continue
            if not (ev[2] if trig == "أ" else ev[3]):
                continue
            if ev[4] < K:
                continue
            if ev[8] is None:
                tally[ev[13]] += 1
                continue
            res = sim(ev, cost_mult, cap_t)
            if res is None:
                tally["نهاية_البيانات"] += 1
                continue
            r, exit_t, stage = res
            trades.append((ev[0], r, sd["kind"], ev[1], ev[7] / ev[15], exit_t, ev[5], ev[6], ev[8], stage, ev[10],
                           ev[15], sd["dir"]["ج★"], ev[7] / ev[5] * 1e4))
            busy = exit_t + 60
            n += 1
        tally["أيّام_بجهة"] += 1
    return trades, dict(tally)


# ───────── الإحصاء ─────────
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
    """أنصاف السنة التي يغطّي الاختبار منها ≥ 91 يومًا."""
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


def pack(tr):
    L = [x for x in tr if x[0] < SPLIT]; T = [x for x in tr if x[0] >= SPLIT]
    out = {"تعلّم": stats(L, START, SPLIT), "اختبار": stats(T, SPLIT, END), "كلّه": stats(tr, START, END)}
    out["معيار_المالك"] = owner_pass(out["اختبار"])
    return out


def owner_pass(T):
    halves = T.get("أنصاف") or {}
    pos = sum(1 for k in TEST_HALVES if halves.get(k, 0.0) > 0)
    checks = {"اختبار_R/صفقة>0": (T.get("R/صفقة") or -1) > 0,
              "اختبار_معامل≥1.15": (T.get("معامل") or 0) >= 1.15,
              "أنصاف_الاختبار_الموجبة≥80٪": pos >= 0.8 * len(TEST_HALVES),
              "اختبار_n≥30": T.get("n", 0) >= 30}
    return {"شروط": checks, "أنصاف_موجبة": "%d/%d" % (pos, len(TEST_HALVES)), "يجتاز": all(checks.values())}


def cache_path(name):
    return os.path.join(HERE, name)


def cached(name, fn):
    p = cache_path(name)
    if os.path.exists(p):
        with open(p, "rb") as f:
            return pickle.load(f)
    v = fn()
    with open(p, "wb") as f:
        pickle.dump(v, f, protocol=pickle.HIGHEST_PROTOCOL)
    return v
