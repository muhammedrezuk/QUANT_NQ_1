# -*- coding: utf-8 -*-
"""«الكمّيّ على الشارت كاملًا» — معايرة مولِّد الوقف والهدف من حركة الناسداك المقيسة (قياسٌ لا بناء).

فوق المرجع الحيّ (البطاقة 414 بالقلب المشترك والأسواق المرتبطة = `card_final_check`)، تغييرٌ واحد في كلّ تجربة:
  ١ الضجيج  : n في (الدخول − n×مدى5) يصير المئين p من «أقصى ذهابٍ ضدّ» (بوحدات مدى5) قبل أن يمضي السعر نصف R معه.
  ٢ المسافة : c في (الهدف ≤ c×مدى اليوم) يصير بحيث السقف = المئين q من «أقصى ما يقطعه السعر في الجهة خلال 4 ساعات» (بوحدات مدى5).
  ٣ التمدّد : شرط |z| ≤ Z لعمق الارتداد الحاليّ مقابل آخر K موجة على 5 د (≈ يوم تداول).
  ٤ الاجتماع: لمن أضاف منها خارج العيّنة.

الأحداث المصدر للتوزيعين (١ و٢): كلّ زنادٍ بنيويّ (قمّة ثمّ قاعٌ بعدها ثمّ إغلاق 5 د فوق القمّة، أو عكسه) في نافذتي المالك،
خارج منع الخبر، بالجهتين (بلا شرط الاتّجاه ولا الارتباط ليكبر العدد). الوقف المرجعيّ للحدث R_ref = max(الدخول−القاع، 2×مدى5).
النافذة الماضية: آخر 60 يوم تداول (60 شمعة يوميّة مغلقة) قبل اللحظة، والحدث لا يدخل إلّا إن اكتمل قياسه قبل اللحظة.
النظام: ثلث «مدى اليوم» (متوسّط المدى 14 يوميّ) بين قيم آخر 60 يومًا. أقلّ عيّنة 30 في الخانة (جلسة×نظام)،
وإلّا الجلسة كلّها، وإلّا العيار المرجعيّ (n=2 · c=1.5).
العيار يُختار على أوّل 70٪ (R/صفقة في التعلّم) ويُحكم عليه بآخر 30٪.
"""
import bisect
import json
import sys
import time

import numpy as np

sys.path.insert(0, r"C:\Users\NQ\QUANT_NQ")
import card_replay as R
import card_replay_shared as S
import card_variants as V
import card_final_check as F
from shared import card_trend as CT
from shared.owner_windows import owner_window

H = 4 * 3600          # عمر الصفقة النموذجيّ لتوزيع المسافة (يُطبع وسيط أعمار صفقات المرجع للتحقّق)
WIN_DAYS = 60         # النافذة الماضية بأيّام التداول
MIN_N = 30            # أقلّ عيّنة للخانة
WARM = 150 * 86400    # تاريخٌ قبل البداية لملء النافذة الماضية
T0 = time.time()


def log(*a):
    print("[%5.0fث]" % (time.time() - T0), *a, flush=True)


def bars_range(period, since, until):
    return [tuple(map(float, r)) for r in R.db.execute(
        "select period_start, open, high, low, close from candles_history where symbol='USTEC' and period=? "
        "and period_start>=? and period_start<? order by period_start", (period, int(since), int(until)))]


# ── سلاسل ممتدّة إلى ما قبل البداية (للنافذة الماضية وحدها؛ الصفقات تبقى على سلاسل المرجع) ──
m1e = bars_range("M1", R.START - WARM, R.m1[0][0]) + R.m1
m5e = bars_range("M5", R.START - WARM, R.m5[0][0]) + R.m5
t1e = [r[0] for r in m1e]
a5e = R.atr(m5e)
sw5e = R.swings(m5e, 300)
sw5e_t = [s[0] for s in sw5e]
log("ممتدّ: دقيقة=%d 5د=%d قمم/قيعان=%d" % (len(m1e), len(m5e), len(sw5e)))


def day_index(t):
    return R.closed_index(R.td1, 86400, t)


# ── موجات 5 د (للتجربة ٣): عند كلّ قمّة/قاع مؤكَّد، عمقه عن آخر نقيضٍ قبله ──
legs_t, legs_d = [], []
_hi = _lo = None
for ts, px, is_hi in sw5e:
    if is_hi:
        if _lo is not None:
            legs_t.append(ts); legs_d.append(abs(px - _lo))
        _hi = px
    else:
        if _hi is not None:
            legs_t.append(ts); legs_d.append(abs(_hi - px))
        _lo = px
# K = متوسّط الموجات في يوم تداول، محسوبٌ على فترة الإحماء وحدها (قبل البداية) فلا نظر للمستقبل
_warm_legs = sum(1 for x in legs_t if x < R.START)
_warm_days = sum(1 for x in R.td1 if R.START - WARM <= x < R.START)
K_LEGS = max(20, int(round(_warm_legs / max(1, _warm_days))))
log("موجات 5 د=%d · K (موجات/يوم تداول في الإحماء)=%d" % (len(legs_t), K_LEGS))


def last_hl(t):
    i = bisect.bisect_left(sw5e_t, t) - 1
    hi = lo = None
    while i >= 0 and (hi is None or lo is None):
        ts, px, is_hi = sw5e[i]
        if is_hi and hi is None:
            hi = (px, ts)
        if not is_hi and lo is None:
            lo = (px, ts)
        i -= 1
    return hi, lo


# ── الأحداث المصدر: كلّ زنادٍ بنيويّ في نافذة المالك خارج منع الخبر، بالجهتين ──
END_M1 = t1e[-1]
events = []   # dict
for j in range(1, len(m5e)):
    t = m5e[j][0] + 300
    if t + H > END_M1:
        break
    w = owner_window(t)
    if not w or R.news_block(t):
        continue
    hi, lo = last_hl(t)
    if hi is None or lo is None:
        continue
    close, prev = m5e[j][4], m5e[j - 1][4]
    if lo[1] > hi[1] and close > hi[0] and prev <= hi[0]:
        buy, pull = True, lo[0]
    elif hi[1] > lo[1] and close < lo[0] and prev >= lo[0]:
        buy, pull = False, hi[0]
    else:
        continue
    a5 = a5e[j]
    idd = day_index(t)
    if a5 <= 0 or idd < 0:
        continue
    risk_ref = max((close - pull) if buy else (pull - close), 2.0 * a5)
    fav = 0.5 * risk_ref
    k = bisect.bisect_left(t1e, t)
    adv = mfe = 0.0
    win_t = mae = None
    while k < len(m1e) and m1e[k][0] < t + H:
        _, o, h, l, c = m1e[k]
        a = (close - l) if buy else (h - close)
        f = (h - close) if buy else (close - l)
        if win_t is None:
            adv = max(adv, a)                 # الذهاب ضدّ يُحسب قبل المضيّ معه في الشمعة نفسها (الأسوأ أوّلًا)
            if f >= fav:
                win_t, mae = m1e[k][0] + 60, adv
        mfe = max(mfe, f)
        k += 1
    events.append({"t": t, "w": w, "buy": buy, "a5": a5, "ad1": R.ad1[idd],
                   "mae": None if mae is None else mae / a5, "mae_done": win_t,
                   "mfe": mfe / a5, "mfe_done": t + H})
ev_t = [e["t"] for e in events]
_won = [e for e in events if e["mae"] is not None]
log("أحداث الزناد البنيويّ=%d (منها قبل البداية %d) · بلغ نصف R معه=%d (%.0f٪)" % (
    len(events), sum(1 for e in events if e["t"] < R.START), len(_won), 100.0 * len(_won) / max(1, len(events))))
for w in ("london_peak", "ny_open"):
    ms = [e["mae"] for e in _won if e["w"] == w]
    fs = [e["mfe"] for e in events if e["w"] == w]
    log("  %s: أقصى ضدّ (مدى5) مئين60/70/80/90 = %s · المسافة 4س (مدى5) مئين50/60/70/80 = %s" % (
        w, np.round(np.percentile(ms, [60, 70, 80, 90]), 2).tolist(), np.round(np.percentile(fs, [50, 60, 70, 80]), 2).tolist()))


def regime(v, cuts):
    return 0 if v <= cuts[0] else 1 if v <= cuts[1] else 2


def pools(t, w):
    """توزيعا الضجيج والمسافة لهذه اللحظة: (القيم، المصدر) لكلٍّ — من الماضي وحده."""
    idd = day_index(t)
    ws = R.td1[idd - WIN_DAYS + 1]
    cuts = np.percentile(R.ad1[idd - WIN_DAYS + 1: idd + 1], [100.0 / 3, 200.0 / 3])
    reg = regime(R.ad1[idd], cuts)
    i0, i1 = bisect.bisect_left(ev_t, ws), bisect.bisect_left(ev_t, t)
    mb, ms, fb, fs = [], [], [], []
    for e in events[i0:i1]:
        if e["w"] != w:
            continue
        same = regime(e["ad1"], cuts) == reg
        if e["mae"] is not None and e["mae_done"] < t:
            ms.append(e["mae"])
            if same:
                mb.append(e["mae"])
        if e["mfe_done"] < t:
            fs.append(e["mfe"])
            if same:
                fb.append(e["mfe"])

    def pick(b, s):
        if len(b) >= MIN_N:
            return np.array(b), "خانة"
        if len(s) >= MIN_N:
            return np.array(s), "جلسة"
        return None, "مرجع"
    return pick(mb, ms), pick(fb, fs), reg


# ── لحظات الزناد على المرجع (القلب المشترك نفسه، بالأسواق المرتبطة) — لا تتعلّق بالعيار ──
triggers = []
for j in range(1, len(R.m5)):
    t = R.m5[j][0] + 300
    if t < R.START:
        continue
    w = owner_window(t)
    if not w:
        continue
    idd = day_index(t)
    peers = {sym: (F.peer_fact(h1, 3600, t), F.peer_fact(h4, 14400, t)) for sym, (h1, h4) in V.REF.items()}
    kw = dict(at=t, close=R.m5[j][4], prev_close=R.m5[j - 1][4],
              trend_1h=S.fact_trend(R.h1, R.e_h1, R.th1, 3600, t),
              trend_4h=S.fact_trend(R.h4, R.e_h4, R.th4, 14400, t),
              atr_5m=R.a5[j], atr_1d=R.ad1[idd] if idd >= 0 else None,
              ladder=S.ladder_at(t, S.frames), window=w, news_blocked=R.news_block(t), peers=peers)
    card = CT.evaluate(**kw)
    if card["status"] not in (CT.OPEN, CT.NO_TARGET, CT.BAD_RISK):
        continue
    buy = CT.direction_of(kw["trend_1h"], kw["trend_4h"]) > 0
    five = kw["ladder"]["5m"]
    hi, lo = CT.last_swings(five["highs"], five["lows"], t)
    depth = hi[0] - lo[0]
    pull_conf = lo[1] if buy else hi[1]
    kk = bisect.bisect_left(legs_t, pull_conf)        # موجاتٌ اكتملت قبل قاع/قمّة هذا الارتداد
    ref = np.array(legs_d[max(0, kk - K_LEGS):kk])
    z = float((depth - ref.mean()) / ref.std()) if len(ref) >= 10 and ref.std() > 0 else None
    (mp, msrc), (fp, fsrc), reg = pools(t, w)
    triggers.append({"t": t, "kw": kw, "z": z, "depth": depth, "mae": mp, "mae_src": msrc,
                     "mfe": fp, "mfe_src": fsrc, "reg": reg, "ref_status": card["status"]})
log("لحظات زنادٍ للبطاقة (بلا شرط الانشغال)=%d" % len(triggers))


def run(p=None, q=None, z=None):
    trades, busy, src = [], 0.0, {}
    for tr in triggers:
        t = tr["t"]
        if t < busy:
            continue
        kw = tr["kw"]
        n, c = CT.N_NOISE, CT.C_REACH
        if p is not None:
            src["وقف:" + tr["mae_src"]] = src.get("وقف:" + tr["mae_src"], 0) + 1
            if tr["mae"] is not None:
                n = float(np.percentile(tr["mae"], p))
        if q is not None:
            src["هدف:" + tr["mfe_src"]] = src.get("هدف:" + tr["mfe_src"], 0) + 1
            if tr["mfe"] is not None:
                c = float(np.percentile(tr["mfe"], q)) * kw["atr_5m"] / kw["atr_1d"]
        card = CT.evaluate(**kw, n=n, c=c)
        if card["status"] != CT.OPEN:
            continue
        if z is not None and (tr["z"] is None or abs(tr["z"]) > z):
            continue
        buy = card["side"] == CT.BUY
        k1 = bisect.bisect_right(R.t1, t - 60)
        r, exit_t = R.thirds(card["entry"], card["stop"], card["target"], buy, k1)
        if r is None:
            break
        trades.append((t, r, card["window"], buy, card["risk"] / card["entry"] * 1e4,
                       card["risk"], abs(card["target"] - card["entry"]), exit_t - t, n))
        busy = exit_t + 60
    return trades, src


SPLIT = R.START + 0.7 * (R.END - R.START)


def summary(tr, src=None):
    learn = [x for x in tr if x[0] < SPLIT]
    test = [x for x in tr if x[0] >= SPLIT]
    med = lambda xs: round(float(np.median(xs)), 1) if xs else None
    out = {"كلّه": R.stats(tr), "تعلّم": R.stats(learn), "اختبار": R.stats(test),
           "لندن": R.stats([x for x in tr if x[2] == "london_peak"]),
           "نيويورك": R.stats([x for x in tr if x[2] == "ny_open"]),
           "وسيط_الوقف_نقاط": {"لندن": med([x[5] for x in tr if x[2] == "london_peak"]),
                               "نيويورك": med([x[5] for x in tr if x[2] == "ny_open"])},
           "وسيط_الهدف_نقاط": {"لندن": med([x[6] for x in tr if x[2] == "london_peak"]),
                               "نيويورك": med([x[6] for x in tr if x[2] == "ny_open"])},
           "وسيط_العمر_دقائق": med([x[7] / 60 for x in tr]),
           "وسيط_n_الفعليّ": med([x[8] for x in tr])}
    if src:
        out["مصدر_العيار"] = src
    return out


def line(name, s):
    a, l, te = s["كلّه"], s["تعلّم"], s["اختبار"]
    return "%-14s | n=%s R=%s R/ص=%s معامل=%s سحب=%s أنصاف=%s | تعلّم n=%s R/ص=%s | اختبار n=%s R/ص=%s معامل=%s | وقف=%s هدف=%s" % (
        name, a.get("n"), a.get("R"), a.get("R/صفقة"), a.get("معامل"), a.get("سحب_R"), list(a.get("أنصاف", {}).values()),
        l.get("n"), l.get("R/صفقة"), te.get("n"), te.get("R/صفقة"), te.get("معامل"),
        s["وسيط_الوقف_نقاط"], s["وسيط_الهدف_نقاط"])


REF = None


def accept(s):
    a, l, te = s["كلّه"], s["تعلّم"], s["اختبار"]
    r = REF
    checks = {"اختبار_أعلى": te.get("R/صفقة", -9) > r["اختبار"]["R/صفقة"],
              "تعلّم_لا_يسوء": l.get("R/صفقة", -9) >= r["تعلّم"]["R/صفقة"],
              "الأنصاف_موجبة": all(v > 0 for v in a.get("أنصاف", {}).values()) and len(a.get("أنصاف", {})) == 5,
              "السحب_لا_يسوء": a.get("سحب_R", 99) <= r["كلّه"]["سحب_R"],
              "العدد_فوق_النصف": a.get("n", 0) > r["كلّه"]["n"] / 2}
    return all(checks.values()), checks


if __name__ == "__main__":
    results, trials = {}, 0
    tr, _ = run()
    REF = summary(tr)
    results["مرجع"] = REF
    log(line("مرجع", REF))
    log("أعمار صفقات المرجع (دقائق): وسيط=%.0f · مئين75=%.0f · مئين90=%.0f" % tuple(
        np.percentile([x[7] / 60 for x in tr], [50, 75, 90])))
    grids = {"١_ضجيج": [("p", v) for v in (60, 70, 80, 90)],
             "٢_مسافة": [("q", v) for v in (50, 60, 70, 80)],
             "٣_تمدّد": [("z", v) for v in (1.5, 2.0)]}
    chosen = {}
    for exp, grid in grids.items():
        best = None
        for key, val in grid:
            trials += 1
            tr, src = run(**{key: val})
            s = summary(tr, src)
            s["قبول"], s["فحوص"] = accept(s)
            name = "%s %s=%s" % (exp, key, val)
            results[name] = s
            log(line(name, s), "| مصدر:", src, "| قبول:", s["قبول"])
            score = s["تعلّم"].get("R/صفقة", -9)
            if s["تعلّم"].get("n", 0) > REF["تعلّم"]["n"] / 2 and (best is None or score > best[0]):
                best = (score, key, val, name)
        chosen[exp] = best
        log("◀ المختار بالتعلّم لـ%s: %s (تعلّم R/ص=%s) ⟵ اختبار R/ص=%s قبول=%s" % (
            exp, best[3], best[0], results[best[3]]["اختبار"].get("R/صفقة"), results[best[3]]["قبول"]))
    adders = [exp for exp, b in chosen.items() if b and results[b[3]]["اختبار"].get("R/صفقة", -9) > REF["اختبار"]["R/صفقة"]]
    log("أضاف خارج العيّنة:", adders)
    combos = []
    if len(adders) >= 2:
        import itertools
        for k in range(2, len(adders) + 1):
            combos.extend(itertools.combinations(adders, k))
    for combo in combos:
        trials += 1
        kw = {chosen[e][1]: chosen[e][2] for e in combo}
        tr, src = run(**kw)
        s = summary(tr, src)
        s["قبول"], s["فحوص"] = accept(s)
        name = "٤_اجتماع " + "+".join("%s=%s" % (chosen[e][1], chosen[e][2]) for e in combo)
        results[name] = s
        log(line(name, s), "| قبول:", s["قبول"])
    results["_meta"] = {"العيارات_المجرّبة": trials, "المختار_بالتعلّم": {k: v[3] for k, v in chosen.items() if v},
                        "أضاف_خارج_العيّنة": adders, "K_موجات": K_LEGS, "H_ثواني": H, "نافذة_أيّام": WIN_DAYS,
                        "أقلّ_عيّنة": MIN_N, "أحداث": len(events), "لحظات_زناد": len(triggers),
                        "حدّ_التعلّم": time.strftime("%Y-%m-%d %H:%M", time.gmtime(SPLIT))}
    log("العيارات المجرّبة (بلا المرجع):", trials)
    json.dump(results, open("card_calib.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    log("كُتب card_calib.json")
