# -*- coding: utf-8 -*-
"""استراتيجيّة «منطقة الضجيج» للزخم داخل اليوم (زاراتيني وعزيز وباربون ٢٠٢٤) — قياسٌ فقط بمسطرة البطاقة 414.

التعريف (القرار عند إغلاق شمعة 5 د j، t_close = m5[j][0] + 300، ولا يُستعمل إلّا ما أُغلق حتّى t_close):
  الافتتاح  : «نيويورك» = فتح شمعة 5 د التي تبدأ 09:30 بتوقيت نيويورك (zoneinfo) — للنافذة «افتتاح أمريكا».
              «لندن» (البديل) = فتح شمعة 5 د التي تبدأ 08:00 بتوقيت لندن — لنافذة «ذروة لندن».
              اليوم الصالح = يوم عملٍ محلّيّ توجد فيه شمعة الافتتاح.
  عمر الجلسة: ك = (t_close − الافتتاح) ÷ 60 دقيقة (5، 10، …).
  الضجيج σ  : متوسّط |إغلاق 5 د عند العمر ك ÷ افتتاح ذلك اليوم − 1| على آخر «ي» يومًا صالحًا **قبل اليوم**
              (يومٌ بلا شمعةٍ عند ك يُسقط من المتوسّط؛ ويلزم ≥ 70٪ من ي قيمًا، وإلّا لا قرار).
  الحدّان   : الأعلى = الافتتاح × (1 + م × σ) · الأدنى = الافتتاح × (1 − م × σ)   (م = مضاعف الحدّ).
  الإشارة   : إغلاق الشمعة j فوق الأعلى ⟸ شراء · تحت الأدنى ⟸ بيع (حالةٌ لا عبور — كالورقة: خارج المنطقة ⟸ دخول).
  السياق    : «أيّ» أو «اتّفاق» (إغلاق الساعة والأربع ساعات المغلقتين في جهة الإشارة مقابل متوسّط 20 — كـ414).
  الوقف     : «مقابل» = الحدّ المقابل عند العمر نفسه · «افتتاح» = افتتاح الجلسة ·
              (ضابطٌ للعلم لا يدخل الاختيار: «مرجّح» = متوسّط السعر المرجّح بالحجم من الافتتاح حتّى t_close بـtick_volume)
              وأبعد من ن × مدى 5 د من الإغلاق (ن = 2 كـ414) · وقفٌ < 3 ن.أ ⟸ لا دخول.
  الهدف     : أقرب قمّة/قاع مؤكَّد على الساعة أو 4 س حتّى t_close (آخر 200 لكلّ إطار كسلّم 201) أو قمّة/قاع
              اليوم السابق المغلق، بنسبةٍ صافية (المسافة − 1.5) ÷ (الخطر + 1.5) ≥ 3، وفي المتناول ≤ ج × مدى اليوم 14.
  الوقت     : نوافذ المالك owner_window · منع الخبر ±15 د (R.news_block) · مركزٌ واحد (busy = exit_t + 60).
  الإدارة   : أثلاث المالك (thirds) من أوّل دقيقة بعد الإغلاق (كلفة 1.5).
"""
import sys
import os

sys.dont_write_bytecode = True
sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, r"C:\Users\NQ\QUANT_NQ")
sys.path.insert(0, HERE)

import bisect
import calendar
import itertools
import json
import math
import time
from array import array
from collections import Counter
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

T0 = time.time()
MODE = os.environ.get("NOISE_MODE", "two")          # two = السنتان (تعلّم/اختبار) · five = الخمس غير المرئيّة
if MODE == "five":
    os.environ.setdefault("NOISE_START", "2019-10-01")
    os.environ.setdefault("NOISE_END", "2024-10-01")
import pdata as P
from shared import card_trend as CT
from shared.owner_windows import (owner_window, new_york_offset_h, london_offset_h,
                                  WINDOW_LONDON_PEAK, WINDOW_NY_OPEN)

NY, LON = ZoneInfo("America/New_York"), ZoneInfo("Europe/London")
N_NOISE, MIN_BPS, NET_MIN, SPREAD = 2.0, 3.0, 3.0, P.COST
MIN_FRAC = 0.7
NAN = float("nan")
m5, v5 = P.m5, P.v5
N5 = len(m5)
IDX5 = {r[0]: j for j, r in enumerate(m5)}
END_DEC = P.END_FIXED                                # الخمس: لا قرار عند/بعد النهاية · السنتان: كالأصل
print("تحميل: %.0f ث" % (time.time() - T0), flush=True)

LEG_DEF = {"ny": (NY, 9, 30, WINDOW_NY_OPEN, new_york_offset_h),
           "lon": (LON, 8, 0, WINDOW_LONDON_PEAK, london_offset_h)}
NS = (10, 14, 20)


def build_leg(name):
    tz, hh, mm, win, off = LEG_DEF[name]
    d = datetime.fromtimestamp(P.t5[0], timezone.utc).date()
    last = datetime.fromtimestamp(P.t5[-1], timezone.utc).date()
    days = []
    while d <= last:
        if d.weekday() < 5:
            a = int(datetime(d.year, d.month, d.day, hh, mm, tzinfo=tz).timestamp())
            # تطابق zoneinfo مع قاعدتَي الصيفيّ المكتوبتين في المشروع
            assert a == calendar.timegm((d.year, d.month, d.day, hh, mm, 0)) - off(a) * 3600, (name, d)
            eod = int(datetime(d.year, d.month, d.day, 16, 0, tzinfo=NY).timestamp())
            if a in IDX5:
                days.append((d, a, eod))
        d += timedelta(days=1)
    smax = max((eod - a) // 300 for _, a, eod in days)
    opens, moves, vwap, prevc = [], [], [], []
    for i, (d, a, eod) in enumerate(days):
        o = m5[IDX5[a]][1]
        mv, vw = array("d", [NAN] * smax), array("d", [NAN] * smax)
        pv = tv = 0.0
        for s in range(smax):
            st = a + s * 300
            if st >= eod:
                break
            j = IDX5.get(st)
            if j is not None:
                mv[s] = abs(m5[j][4] / o - 1.0)
                tp = (m5[j][2] + m5[j][3] + m5[j][4]) / 3.0
                pv += tp * v5[j]; tv += v5[j]
            if tv > 0:
                vw[s] = pv / tv
        opens.append(o); moves.append(mv); vwap.append(vw)
        pj = IDX5.get(days[i - 1][2] - 300) if i > 0 else None
        prevc.append(m5[pj][4] if pj is not None else NAN)
    sig = {}
    for n in NS:
        need = math.ceil(MIN_FRAC * n)
        rows = []
        for i in range(len(days)):
            arr = array("d", [NAN] * smax)
            past = moves[max(0, i - n):i]          # الأيّام الماضية وحدها
            if len(past) >= need:
                for s in range(smax):
                    vals = [p[s] for p in past if p[s] == p[s]]
                    if len(vals) >= need:
                        arr[s] = sum(vals) / len(vals)
            rows.append(arr)
        sig[n] = rows
    dec = []
    for i, (d, a, eod) in enumerate(days):
        s = 0
        while True:
            tc = a + (s + 1) * 300
            if owner_window(tc) != win:
                break
            if tc >= P.START and (END_DEC is None or tc < END_DEC):
                j = IDX5.get(tc - 300)
                if j is not None:
                    dec.append((j, name, i, s))
            s += 1
    return {"days": days, "open": opens, "moves": moves, "vwap": vwap, "prevc": prevc, "sig": sig,
            "dec": dec, "win": win, "smax": smax}


LEGD = {name: build_leg(name) for name in LEG_DEF}
DEC = sorted(LEGD["ny"]["dec"] + LEGD["lon"]["dec"])
assert len({x[0] for x in DEC}) == len(DEC)
print("أيّام صالحة: نيويورك=%d لندن=%d · قرارات: نيويورك=%d لندن=%d · %.0f ث" % (
    len(LEGD["ny"]["days"]), len(LEGD["lon"]["days"]), len(LEGD["ny"]["dec"]), len(LEGD["lon"]["dec"]),
    time.time() - T0), flush=True)

NEWS, IDD, DIR = {}, {}, {}
for j, leg, i, s in DEC:
    tc = m5[j][0] + 300
    assert owner_window(tc) == LEGD[leg]["win"]
    NEWS[j] = P.news_block(tc)
    IDD[j] = P.closed_index(P.td1, 86400, tc)
    DIR[j] = CT.direction_of(P.fact_trend(P.h1, P.e_h1, P.th1, 3600, tc),
                             P.fact_trend(P.h4, P.e_h4, P.th4, 14400, tc))
print("الحقائق: %.0f ث" % (time.time() - T0), flush=True)

_TG = {}


def target_prices(j, tc, buy):
    keys = P.ladder_keys(tc)
    idd = IDD[j]
    key = (keys, idd, buy)
    v = _TG.get(key)
    if v is None:
        pr = P.ladder_prices(keys, buy)
        if idd >= 0:
            pr.append(P.d1[idd][2] if buy else P.d1[idd][3])
        v = array("d", sorted(pr))
        _TG[key] = v
    return v


def find_target(j, tc, buy, cl, risk, reach):
    pr = target_prices(j, tc, buy)
    if buy:
        a, b = bisect.bisect_right(pr, cl), bisect.bisect_right(pr, cl + reach + 1.0)
    else:
        a, b = bisect.bisect_left(pr, cl - reach - 1.0), bisect.bisect_left(pr, cl)
    cands = [(p, tc) for p in pr[a:b]]
    return CT.nearest_target(cands, buy, cl, risk, reach, tc, rr=NET_MIN + 4.0 * SPREAD / risk)


def target_source(j, tc, buy, target):
    lv = P.ladder_detail(tc, buy)
    idd = IDD[j]
    if idd >= 0:
        lv.append((P.d1[idd][2] if buy else P.d1[idd][3], P.td1[idd] + 86400, "يوم_سابق"))
    return next(x for x in lv if x[0] == target and x[1] <= tc)


def manage_alt(mode, entry, stop, target, buy, k, leg, i, n, mult, hi_base, lo_base):
    """أدوات الورقة (للعلم وحده): paper = وقفٌ زاحف عند max(الحدّ القريب، المرجّح) على إغلاقات 5 د + إغلاق 16:00
    نيويورك · thirds_eod = الأثلاث + إغلاق آخر اليوم · fixed_eod = الوقف الأصليّ + إغلاق آخر اليوم بلا هدف."""
    G = LEGD[leg]
    a, eod = G["days"][i][1], G["days"][i][2]
    risk, sgn = abs(entry - stop), (1 if buy else -1)
    th, trail = mode == "thirds_eod", mode == "paper"
    if th:
        span = abs(target - entry)
        t1_, t2_ = entry + sgn * span / 3, entry + sgn * 2 * span / 3
    cur, rem, real, stage = stop, 1.0, 0.0, 0
    sigrow, vwrow = G["sig"][n][i], G["vwap"][i]
    T1, O1, H1, L1, C1 = P.T1, P.O1, P.H1, P.L1, P.C1
    nn = len(T1)
    while k < nn:
        t, o, h, lo, c = T1[k], O1[k], H1[k], L1[k], C1[k]
        if t >= eod:
            return real + rem * ((o - entry) * sgn / risk) - SPREAD / risk, t
        if (lo <= cur) if buy else (h >= cur):
            px = min(o, cur) if buy else max(o, cur)
            return real + rem * ((px - entry) * sgn / risk) - SPREAD / risk, t
        if th:
            hit = (lambda v: h >= v) if buy else (lambda v: lo <= v)
            if stage < 1 and hit(t1_):
                real += (rem / 3) * (span / 3 / risk); rem -= rem / 3; cur = entry; stage = 1
            if stage < 2 and hit(t2_):
                real += (rem / 2) * (2 * span / 3 / risk); rem -= rem / 2; cur = t1_; stage = 2
            if hit(target):
                return real + rem * (span / risk) - SPREAD / risk, t
        if trail and (t + 60 - a) % 300 == 0:
            s = int((t + 60 - a) // 300) - 1
            if 0 <= s < len(sigrow):
                sg, vw = sigrow[s], vwrow[s]
                lv = []
                if sg == sg:
                    lv.append(hi_base * (1 + mult * sg) if buy else lo_base * (1 - mult * sg))
                if vw == vw:
                    lv.append(vw)
                if lv:
                    level = max(lv) if buy else min(lv)
                    if (c < level) if buy else (c > level):
                        return real + rem * ((c - entry) * sgn / risk) - SPREAD / risk, t
        k += 1
    return None, None


def run(cfg, legs, manage="thirds", trigger="state", gap=False, semi=False, need_target=True, detail=False):
    n, mult, stop_mode, ctx, c = cfg
    trades, busy, tally = [], 0.0, Counter()
    for j, leg, i, s in DEC:
        if leg not in legs:
            continue
        tc = m5[j][0] + 300
        if NEWS[j]:
            continue
        if semi and tc % 1800 != 0:
            continue
        G = LEGD[leg]
        sg = G["sig"][n][i][s]
        if sg != sg:
            tally["بلا_ضجيج"] += 1
            continue
        o = G["open"][i]
        hb = lb_ = o
        if gap:
            pc = G["prevc"][i]
            if pc == pc:
                hb, lb_ = max(o, pc), min(o, pc)
        ub, lb = hb * (1 + mult * sg), lb_ * (1 - mult * sg)
        cl = m5[j][4]
        if cl > ub:
            buy = True
        elif cl < lb:
            buy = False
        else:
            continue
        if trigger == "cross":
            if s > 0:
                pj = IDX5.get(m5[j][0] - 300)
                ps = G["sig"][n][i][s - 1]
                if pj is None or ps != ps:
                    continue
                prev = m5[pj][4]
                if (prev > hb * (1 + mult * ps)) if buy else (prev < lb_ * (1 - mult * ps)):
                    continue
        tally["إشارة"] += 1
        if ctx == "اتّفاق" and DIR[j] != (1 if buy else -1):
            tally["سياق_مخالف"] += 1
            continue
        if tc < busy:
            tally["مشغول"] += 1
            continue
        idd = IDD[j]
        adr = P.ad1[idd] if idd >= 0 else None
        if not adr or adr <= 0:
            tally["بلا_مدى_يوم"] += 1
            continue
        a5 = P.a5[j]
        if stop_mode == "مقابل":
            struct = lb if buy else ub
        elif stop_mode == "افتتاح":
            struct = o
        else:
            struct = G["vwap"][i][s]
            if struct != struct or ((struct >= cl) if buy else (struct <= cl)):
                tally["المرجّح_في_غير_جهته"] += 1
                continue
        stop = min(struct, cl - N_NOISE * a5) if buy else max(struct, cl + N_NOISE * a5)
        risk = abs(cl - stop)
        if risk <= 0:
            tally["خطر_غير_موجب"] += 1
            continue
        bps = risk / cl * 1e4
        if bps < MIN_BPS:
            tally["وقف<3ن.أ"] += 1
            continue
        target = None
        if need_target:
            target = find_target(j, tc, buy, cl, risk, c * adr)
            if target is None:
                tally["بلا_هدف"] += 1
                continue
            net = (abs(target - cl) - SPREAD) / (risk + SPREAD)
            assert net >= NET_MIN - 1e-9 and abs(target - cl) <= c * adr + 1e-9
        k1 = bisect.bisect_right(P.T1, tc - 60)
        if manage == "thirds":
            r, exit_t = P.thirds(cl, stop, target, buy, k1)
        else:
            r, exit_t = manage_alt(manage, cl, stop, target, buy, k1, leg, i, n, mult, hb, lb_)
        if r is None:
            tally["نهاية_البيانات"] += 1
            break
        tally["صفقة"] += 1
        row = (tc, r, G["win"], buy, bps, exit_t)
        if detail:
            a = G["days"][i][1]
            src = target_source(j, tc, buy, target) if target is not None else (None, None, None)
            i1, i4 = P.closed_index(P.th1, 3600, tc), P.closed_index(P.th4, 14400, tc)
            row = row + ({"j": j, "leg": leg, "day": str(G["days"][i][0]), "anchor_t": a, "k_min": (s + 1) * 5,
                          "decision_bar_start": m5[j][0], "open": o, "sigma": sg, "ub": ub, "lb": lb,
                          "sigma_days": [str(G["days"][x][0]) for x in range(max(0, i - n), i)],
                          "sigma_last_past_bar_close": G["days"][i - 1][1] + (s + 1) * 300 if i > 0 else None,
                          "entry": cl, "struct": struct, "stop": stop, "target": target, "risk": risk,
                          "target_src": src[2], "target_confirm_t": src[1],
                          "adr_day_close_t": P.td1[idd] + 86400, "adr": adr, "a5": a5,
                          "h1_close_t": P.th1[i1] + 3600, "h4_close_t": P.th4[i4] + 14400,
                          "vwap_last_bar_close": a + (s + 1) * 300, "first_mgmt_bar": P.T1[k1],
                          "net": (abs(target - cl) - SPREAD) / (risk + SPREAD) if target is not None else None},)
        trades.append(row)
        busy = exit_t + 60
    return trades, tally


def weekdays(a, b):
    return sum(1 for d in range(int(a // 86400), int(b // 86400) + 1)
               if datetime.fromtimestamp(d * 86400, timezone.utc).weekday() < 5)


def blocks(tr):
    """أنصافٌ من 6 أشهر مبدؤها 2019-10-01 (للخمس): عشرة بالضبط."""
    out = {}
    for t, r, *_ in tr:
        dt = datetime.fromtimestamp(t, timezone.utc)
        m = (dt.year - 2019) * 12 + (dt.month - 10)
        b = m // 6
        y0, m0 = 2019 + (9 + 6 * b) // 12, (9 + 6 * b) % 12 + 1
        key = "%d-%02d" % (y0, m0)
        out[key] = out.get(key, 0.0) + r
    return {k: round(v, 1) for k, v in sorted(out.items())}


def audit(tr):
    """فحصٌ آليّ: كلّ مدخلات القرار مغلقة قبل لحظته، والإدارة بعدها."""
    bad = Counter()
    for x in tr:
        tc, d = x[0], x[6]
        bad["شمعة_القرار"] += d["decision_bar_start"] + 300 != tc
        bad["الافتتاح_بعد_القرار"] += d["anchor_t"] > tc - 300
        bad["أيّام_الضجيج_ليست_ماضية"] += any(s_ >= d["day"] for s_ in d["sigma_days"])
        bad["آخر_شمعة_ضجيج_بعد_الافتتاح"] += (d["sigma_last_past_bar_close"] or 0) > d["anchor_t"]
        bad["مستوى_الهدف_بعد_القرار"] += d["target_confirm_t"] is not None and d["target_confirm_t"] > tc
        bad["مدى_اليوم_غير_مغلق"] += d["adr_day_close_t"] > tc
        bad["ساعة_غير_مغلقة"] += d["h1_close_t"] > tc
        bad["4س_غير_مغلقة"] += d["h4_close_t"] > tc
        bad["المرجّح_بعد_القرار"] += d["vwap_last_bar_close"] > tc
        bad["الإدارة_قبل_القرار"] += d["first_mgmt_bar"] < tc or x[5] < tc
        bad["خارج_النافذة"] += owner_window(tc) != x[2]
        bad["وقت_خبر"] += P.news_block(tc)
        bad["وقف<3"] += x[4] < MIN_BPS - 1e-9
        bad["صافي<3"] += d["net"] is not None and d["net"] < NET_MIN - 1e-9
    return {"صفقات": len(tr), "مخالفات": {k: v for k, v in bad.items()}, "سليم": sum(bad.values()) == 0}


GRID = list(itertools.product(NS, (1.0, 1.25), ("مقابل", "افتتاح"), ("أيّ", "اتّفاق"), (1.0, 1.5)))
CONTROL = list(itertools.product(NS, (1.0, 1.25), ("مرجّح",), ("أيّ", "اتّفاق"), (1.0, 1.5)))
assert len(GRID) == 48
LEGSETS = {"نيويورك": ("ny",), "لندن": ("lon",), "كلاهما": ("ny", "lon")}
WD = weekdays(P.START, P.END)


def cfg_dict(g):
    return {"ي": g[0], "م": g[1], "الوقف": g[2], "السياق": g[3], "ج": g[4]}


def mean(xs):
    return sum(xs) / len(xs) if xs else float("-inf")


def dump_trades(tr, name):
    json.dump([[x[0], x[5], round(x[1], 5), x[2], x[3], round(x[4], 3)] for x in tr],
              open(os.path.join(HERE, name), "w", encoding="utf-8"), ensure_ascii=False)


def info_tables(g, legs):
    """أدوات الورقة ومتغيّرات الدخول — للعلم وحده على المختارة نفسها (لا تدخل الاختيار)."""
    n, mult, sm, ctx, c = g
    variants = {
        "البطاقة (أثلاث المالك)": dict(),
        "أثلاث + إغلاق آخر اليوم 16:00 نيويورك": dict(manage="thirds_eod"),
        "وقف ثابت + إغلاق آخر اليوم بلا هدف": dict(manage="fixed_eod"),
        "وقف الورقة الزاحف (الحدّ القريب/المرجّح) + إغلاق آخر اليوم": dict(manage="paper"),
        "دخول بالعبور فقط (لا بالحالة)": dict(trigger="cross"),
        "حدّا الورقة بفجوة الإغلاق السابق": dict(gap=True),
        "فحص كلّ نصف ساعة فقط (كالورقة)": dict(semi=True),
        "الورقة الخالصة: حالة+فجوة+نصف ساعة+وقف زاحف+آخر اليوم، بلا هدف ولا سياق": dict(
            manage="paper", gap=True, semi=True, need_target=False, _ctx="أيّ"),
    }
    out = {}
    for name, kw in variants.items():
        kw = dict(kw)
        gg = (n, mult, sm, kw.pop("_ctx", ctx), c)
        tr, tally = run(gg, legs, **kw)
        out[name] = {**period_pack(tr), "صفقات/يوم": round(len(tr) / WD, 3), "عدّاد": dict(tally)}
    return out


if MODE == "two":
    SPLIT = P.START + 0.7 * (P.END - P.START)
    WD_L, WD_T = weekdays(P.START, SPLIT), None
    WD_T = WD - WD_L

    def period_pack(tr):
        return {"تعلّم": P.stats([x for x in tr if x[0] < SPLIT]), "اختبار": P.stats([x for x in tr if x[0] >= SPLIT]),
                "كلّه": P.stats(tr), "لندن": P.stats([x for x in tr if x[2] == WINDOW_LONDON_PEAK]),
                "نيويورك": P.stats([x for x in tr if x[2] == WINDOW_NY_OPEN])}

    def owner_pass(s):
        T, A = s["اختبار"], s["كلّه"]
        halves = A.get("أنصاف") or {}
        pos = sum(1 for v in halves.values() if v > 0)
        checks = {"اختبار_R/صفقة>0": (T.get("R/صفقة") or -1) > 0,
                  "اختبار_معامل≥1.15": (T.get("معامل") or 0) >= 1.15,
                  "اختبار_n≥30": T.get("n", 0) >= 30,
                  "أنصاف_موجبة≥4من5": pos >= 4 and len(halves) >= 5}
        return {"شروط": checks, "أنصاف_موجبة": "%d/%d" % (pos, len(halves)), "يجتاز": all(checks.values())}
else:
    def period_pack(tr):
        s = P.stats(tr)
        s["أنصاف_6أشهر"] = blocks(tr)
        return {"كلّه": s, "لندن": P.stats([x for x in tr if x[2] == WINDOW_LONDON_PEAK]),
                "نيويورك": P.stats([x for x in tr if x[2] == WINDOW_NY_OPEN])}

    def owner_pass(s):
        A = s["كلّه"]
        bl = A.get("أنصاف_6أشهر") or {}
        pos = sum(1 for v in bl.values() if v > 0)
        checks = {"R/صفقة>0": (A.get("R/صفقة") or -1) > 0, "معامل≥1.15": (A.get("معامل") or 0) >= 1.15,
                  "أنصاف_موجبة≥7من10": pos >= 7 and len(bl) == 10}
        return {"شروط": checks, "أنصاف_موجبة": "%d/%d" % (pos, len(bl)), "يجتاز": all(checks.values())}


def line(label, g, s):
    if MODE == "two":
        L, T, A = s["تعلّم"], s["اختبار"], s["كلّه"]
        return "%-7s ي=%d م=%.2f وقف=%-6s سياق=%-6s ج=%.1f | تعلّم n=%s R/ص=%s | اختبار n=%s R/ص=%s معامل=%s | كلّه n=%s R=%s سحب=%s أنصاف=%s | %.0f ث" % (
            label, g[0], g[1], g[2], g[3], g[4], L.get("n"), L.get("R/صفقة"), T.get("n"), T.get("R/صفقة"), T.get("معامل"),
            A.get("n"), A.get("R"), A.get("سحب_R"), A.get("أنصاف"), time.time() - T0)
    A = s["كلّه"]
    return "%-7s ي=%d م=%.2f وقف=%-6s سياق=%-6s ج=%.1f | خمس n=%s R=%s R/ص=%s معامل=%s سحب=%s أنصاف6=%s | %.0f ث" % (
        label, g[0], g[1], g[2], g[3], g[4], A.get("n"), A.get("R"), A.get("R/صفقة"), A.get("معامل"), A.get("سحب_R"),
        A.get("أنصاف_6أشهر"), time.time() - T0)


if __name__ == "__main__":
    out = {"تعريف": __doc__, "الوضع": MODE,
           "ثوابت": {"ن": N_NOISE, "أدنى_وقف_ن.أ": MIN_BPS, "صافي≥": NET_MIN, "سبريد": SPREAD,
                     "أدنى_نسبة_أيّام_الضجيج": MIN_FRAC, "KEEP_سلّم": P.KEEP},
           "البداية": datetime.fromtimestamp(P.START, timezone.utc).isoformat(),
           "النهاية": datetime.fromtimestamp(P.END, timezone.utc).isoformat(),
           "أيّام_عمل": WD, "أيّام_صالحة": {k: len(v["days"]) for k, v in LEGD.items()},
           "قرارات": {k: len(v["dec"]) for k, v in LEGD.items()}}
    if MODE == "two":
        out["حدّ_التعلّم"] = datetime.fromtimestamp(SPLIT, timezone.utc).isoformat()
        out["أيّام_عمل_تعلّم_اختبار"] = [WD_L, WD_T]
        selected = {}
        for lname, legs in LEGSETS.items():
            rows, best, best_key = [], None, None
            for g in GRID + CONTROL:
                tr, tally = run(g, legs)
                s = period_pack(tr)
                in_grid = g in GRID
                rows.append({**cfg_dict(g), "في_الشبكة": in_grid, **s, "عدّاد": dict(tally),
                             "صفقات/يوم": round(len(tr) / WD, 3), "معيار_المالك": owner_pass(s)})
                lm = mean([x[1] for x in tr if x[0] < SPLIT])
                if in_grid and s["تعلّم"].get("n", 0) >= 60 and (best is None or lm > best_key):
                    best, best_key = g, lm
                print(line(lname, g, s), flush=True)
            tests = [r["اختبار"].get("R/صفقة") for r in rows if r["في_الشبكة"] and r["اختبار"].get("n", 0) >= 10]
            res = {"التركيبات": rows,
                   "ثبات_الشبكة": {"تركيبات_باختبار≥10": len(tests), "اختبار_موجب": sum(1 for v in tests if v > 0),
                                   "وسيط_اختبار_R/صفقة": sorted(tests)[len(tests) // 2] if tests else None}}
            if best is not None:
                tr, tally = run(best, legs, detail=True)
                s = period_pack(tr)
                res["المختارة"] = {**cfg_dict(best), **s, "عدّاد": dict(tally),
                                   "صفقات/يوم": round(len(tr) / WD, 3),
                                   "صفقات/يوم_تعلّم": round(s["تعلّم"].get("n", 0) / WD_L, 3),
                                   "صفقات/يوم_اختبار": round(s["اختبار"].get("n", 0) / WD_T, 3),
                                   "معيار_المالك": owner_pass(s),
                                   "شراء": P.stats([x for x in tr if x[3]]), "بيع": P.stats([x for x in tr if not x[3]]),
                                   "مصدر_الهدف": dict(Counter(x[6]["target_src"] for x in tr)),
                                   "مدّة_الصفقة_د_وسيط": sorted((x[5] - x[0]) / 60 for x in tr)[len(tr) // 2] if tr else None,
                                   "تدقيق_التسريب": audit(tr)}
                res["أدوات_الورقة_للعلم"] = info_tables(best, legs)
                suffix = {"نيويورك": "", "لندن": "_london", "كلاهما": "_both"}[lname]
                dump_trades(tr, "trades_best%s.json" % suffix)
                json.dump([{**x[6], "t_close": x[0], "exit_t": x[5], "r": x[1], "window": x[2], "buy": x[3]} for x in tr],
                          open(os.path.join(HERE, "trades_best%s_detail.json" % suffix), "w", encoding="utf-8"),
                          ensure_ascii=False)
                selected[lname] = list(best)
                print("المختارة %s: %s" % (lname, json.dumps({k: res["المختارة"][k] for k in (
                    "ي", "م", "الوقف", "السياق", "ج", "تعلّم", "اختبار", "كلّه", "معيار_المالك", "صفقات/يوم")},
                    ensure_ascii=False)), flush=True)
            else:
                print("%s: لا تركيبة بـ≥ 60 صفقة تعلّم" % lname, flush=True)
            out[lname] = res
        out["المختارات"] = selected
        json.dump(out, open(os.path.join(HERE, "results_two.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    else:
        two = json.load(open(os.path.join(HERE, "results_two.json"), encoding="utf-8"))
        selected = {k: tuple(v) for k, v in two["المختارات"].items()}
        for lname, legs in LEGSETS.items():
            res = {}
            if lname in selected:
                g = selected[lname]
                tr, tally = run(g, legs, detail=True)
                s = period_pack(tr)
                res["المختارة_بلا_تعديل"] = {**cfg_dict(g), **s, "عدّاد": dict(tally),
                                             "صفقات/يوم": round(len(tr) / WD, 3), "معيار_المالك": owner_pass(s),
                                             "شراء": P.stats([x for x in tr if x[3]]),
                                             "بيع": P.stats([x for x in tr if not x[3]]),
                                             "مصدر_الهدف": dict(Counter(x[6]["target_src"] for x in tr)),
                                             "تدقيق_التسريب": audit(tr)}
                print(line(lname + "*", g, s), flush=True)
                suffix = {"نيويورك": "", "لندن": "_london", "كلاهما": "_both"}[lname]
                dump_trades(tr, "trades_five%s.json" % suffix)
                res["أدوات_الورقة_للعلم"] = info_tables(g, legs)
            # للعلم: الشبكة كلّها على الخمس (لا اختيار هنا)
            rows = []
            for g in GRID:
                tr, tally = run(g, legs)
                s = period_pack(tr)
                rows.append({**cfg_dict(g), **s, "صفقات/يوم": round(len(tr) / WD, 3), "معيار_المالك": owner_pass(s)})
                print(line(lname, g, s), flush=True)
            vals = [r["كلّه"].get("R/صفقة") for r in rows if r["كلّه"].get("n", 0) >= 30]
            res["الشبكة_للعلم"] = rows
            res["ثبات_الشبكة"] = {"تركيبات_n≥30": len(vals), "موجبة": sum(1 for v in vals if v > 0),
                                  "وسيط_R/صفقة": sorted(vals)[len(vals) // 2] if vals else None,
                                  "تجتاز_معيار_الخمس": sum(1 for r in rows if r["معيار_المالك"]["يجتاز"])}
            out[lname] = res
        json.dump(out, open(os.path.join(HERE, "results_five.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("انتهى: %.0f ث" % (time.time() - T0), flush=True)
