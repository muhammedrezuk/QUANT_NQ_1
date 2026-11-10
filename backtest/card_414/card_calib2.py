# -*- coding: utf-8 -*-
"""«الكمّيّ على الشارت كاملًا» — معايرة مولِّد الوقف والهدف من حركة الناسداك المقيسة (قياسٌ لا بناء) — النسخة ٢.

الفرق عن `card_calib.py` (الذي كشف أمرين: خانة جلسة×نظام قلّما تبلغ 30 عيّنة في 60 يومًا، وسقف 4 ساعات أدنى من 3R):
  · ١ب: الضجيج بنافذة 120 يوم تداول (لتمتلئ خانة النظام)، إلى جانب ١أ بنافذة 60.
  · ٢ب: المسافة حتّى نهاية يوم التداول (17:00 نيويورك) — «حتّى نهاية الجلسة» — إلى جانب ٢أ بأربع ساعات.
  · تشخيص: نسبة صفقات المرجع التي بلغت الهدف الأوّل/الثاني/الثالث، وتوزيع «R المطلوب» مقابل المسافة المقيسة.
  · الاختيار لكلّ عائلة تجارب على فترة التعلّم وحدها، بين كلّ عياراتها.

فوق المرجع الحيّ (البطاقة 414 بالقلب المشترك والأسواق المرتبطة = `card_final_check`)، تغييرٌ واحد في كلّ تجربة:
  ١ الضجيج  : n في (الدخول − n×مدى5) = المئين p من «أقصى ذهابٍ ضدّ» (بوحدات مدى5) قبل أن يمضي السعر نصف R معه.
  ٢ المسافة : السقف (بدل 1.5×مدى اليوم) = المئين q من «أقصى ما يقطعه السعر في الجهة خلال العمر» (بوحدات مدى5).
  ٣ التمدّد : شرط |z| ≤ Z لعمق الارتداد الحاليّ مقابل آخر K موجة على 5 د (≈ يوم تداول، K من فترة الإحماء).
  ٤ الاجتماع: لمن أضاف منها خارج العيّنة.
الأحداث المصدر: كلّ زنادٍ بنيويّ في نافذتي المالك خارج منع الخبر بالجهتين. R_ref = max(الدخول−القاع، 2×مدى5).
النافذة الماضية: آخر W يوم تداول قبل اللحظة، والحدث لا يدخل إلّا إن اكتمل قياسه قبل اللحظة.
النظام: ثلث مدى اليوم (ATR14 يوميّ) بين قيم آخر W يومًا. أقلّ عيّنة 30 للخانة، وإلّا الجلسة كلّها، وإلّا العيار المرجعيّ.
"""
import bisect
import itertools
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
from shared.owner_windows import owner_window, local_time, new_york_offset_h

H4 = 4 * 3600
MIN_N = 30
WARM = 250 * 86400    # يكفي نافذة 120 يوم تداول قبل البداية
WINS = (60, 120)
T0 = time.time()


def log(*a):
    print("[%5.0fث]" % (time.time() - T0), *a, flush=True)


def bars_range(period, since, until):
    return [tuple(map(float, r)) for r in R.db.execute(
        "select period_start, open, high, low, close from candles_history where symbol='USTEC' and period=? "
        "and period_start>=? and period_start<? order by period_start", (period, int(since), int(until)))]


m1e = bars_range("M1", R.START - WARM, R.m1[0][0]) + R.m1
m5e = bars_range("M5", R.START - WARM, R.m5[0][0]) + R.m5
t1e = [r[0] for r in m1e]
a5e = R.atr(m5e)
sw5e = R.swings(m5e, 300)
sw5e_t = [s[0] for s in sw5e]
log("ممتدّ: دقيقة=%d 5د=%d قمم/قيعان=%d · أوّل يوم في سلسلة اليوم=%s" % (
    len(m1e), len(m5e), len(sw5e), time.strftime("%Y-%m-%d", time.gmtime(R.td1[0]))))


def day_index(t):
    return R.closed_index(R.td1, 86400, t)


def eod(t):
    """17:00 بتوقيت نيويورك من يوم اللحظة (نهاية يوم التداول)."""
    off = new_york_offset_h(t)
    lt = local_time(t, new_york_offset_h)
    end = lt.replace(hour=17, minute=0, second=0, microsecond=0).timestamp() - off * 3600
    return end if end > t else end + 86400


# ── موجات 5 د (للتجربة ٣) ──
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
_W0 = R.START - 150 * 86400
_warm_legs = sum(1 for x in legs_t if _W0 <= x < R.START)
_warm_days = sum(1 for x in R.td1 if _W0 <= x < R.START)
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


def excursions(t, close, buy, fav, horizon_end):
    """(أقصى ضدّ قبل بلوغ fav معه أو None، وقت البلوغ، أقصى معه حتّى horizon_end)."""
    k = bisect.bisect_left(t1e, t)
    adv = mfe = 0.0
    win_t = mae = None
    while k < len(m1e) and m1e[k][0] < horizon_end:
        _, o, h, l, c = m1e[k]
        a = (close - l) if buy else (h - close)
        f = (h - close) if buy else (close - l)
        if win_t is None:
            adv = max(adv, a)            # الأسوأ أوّلًا داخل الشمعة
            if f >= fav:
                win_t, mae = m1e[k][0] + 60, adv
        mfe = max(mfe, f)
        k += 1
    return mae, win_t, mfe


END_M1 = t1e[-1]
events = []
for j in range(1, len(m5e)):
    t = m5e[j][0] + 300
    e_end = eod(t)
    if max(t + H4, e_end) > END_M1:
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
    mae, win_t, mfe4 = excursions(t, close, buy, 0.5 * risk_ref, t + H4)
    _, _, mfe_d = excursions(t, close, buy, float("inf"), e_end)
    events.append({"t": t, "w": w, "buy": buy, "a5": a5, "ad1": R.ad1[idd],
                   "mae": None if mae is None else mae / a5, "mae_done": win_t,
                   "4h": mfe4 / a5, "4h_done": t + H4, "eod": mfe_d / a5, "eod_done": e_end})
ev_t = [e["t"] for e in events]
_won = [e for e in events if e["mae"] is not None]
log("أحداث الزناد البنيويّ=%d (قبل البداية %d) · بلغ نصف R معه=%d (%.0f٪)" % (
    len(events), sum(1 for e in events if e["t"] < R.START), len(_won), 100.0 * len(_won) / max(1, len(events))))
DESC = {}
for w in ("london_peak", "ny_open"):
    ms = [e["mae"] for e in _won if e["w"] == w and e["t"] >= R.START]
    f4 = [e["4h"] for e in events if e["w"] == w and e["t"] >= R.START]
    fd = [e["eod"] for e in events if e["w"] == w and e["t"] >= R.START]
    DESC[w] = {"عدد": len(f4), "ضدّ_مئين60/70/80/90": np.round(np.percentile(ms, [60, 70, 80, 90]), 2).tolist(),
               "مسافة4س_مئين50/60/70/80/90": np.round(np.percentile(f4, [50, 60, 70, 80, 90]), 2).tolist(),
               "مسافة_لنهاية_اليوم_مئين50/60/70/80/90": np.round(np.percentile(fd, [50, 60, 70, 80, 90]), 2).tolist()}
    log("  %s (السنتان، بوحدات مدى5): %s" % (w, DESC[w]))


def regime(v, cuts):
    return 0 if v <= cuts[0] else 1 if v <= cuts[1] else 2


def pools(t, w, win):
    """لهذه اللحظة من الماضي وحده: {mae, 4h, eod} ⟵ (القيم، المصدر)."""
    idd = day_index(t)
    ws = R.td1[idd - win + 1]
    cuts = np.percentile(R.ad1[idd - win + 1: idd + 1], [100.0 / 3, 200.0 / 3])
    reg = regime(R.ad1[idd], cuts)
    i0, i1 = bisect.bisect_left(ev_t, ws), bisect.bisect_left(ev_t, t)
    acc = {k: ([], []) for k in ("mae", "4h", "eod")}
    for e in events[i0:i1]:
        if e["w"] != w:
            continue
        same = regime(e["ad1"], cuts) == reg
        for key in acc:
            v, done = e[key], e[key + "_done"]
            if v is None or done is None or done >= t:
                continue
            acc[key][1].append(v)
            if same:
                acc[key][0].append(v)
    out = {}
    for key, (b, s) in acc.items():
        out[key] = (np.array(b), "خانة") if len(b) >= MIN_N else (np.array(s), "جلسة") if len(s) >= MIN_N else (None, "مرجع")
    return out


# ── لحظات الزناد على المرجع (لا تتعلّق بالعيار) ──
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
    kk = bisect.bisect_left(legs_t, pull_conf)
    ref = np.array(legs_d[max(0, kk - K_LEGS):kk])
    z = float((depth - ref.mean()) / ref.std()) if len(ref) >= 10 and ref.std() > 0 else None
    triggers.append({"t": t, "kw": kw, "z": z, "depth": depth, "pools": {win: pools(t, w, win) for win in WINS}})
log("لحظات زنادٍ للبطاقة (بلا شرط الانشغال)=%d" % len(triggers))


def thirds_stage(entry, stop, target, buy, k):
    """نسخة تشخيصيّة من `R.thirds`: أبعد مرحلةٍ بلغتها الصفقة (0 وقف قبل الأوّل · 1 · 2 · 3 الهدف)."""
    risk, span, sgn = abs(entry - stop), abs(target - entry), (1 if buy else -1)
    t1_, t2_ = entry + sgn * span / 3, entry + sgn * 2 * span / 3
    cur, stage = stop, 0
    while k < len(R.m1):
        t, o, h, lo, c = R.m1[k]
        if (lo <= cur) if buy else (h >= cur):
            return stage
        hit = (lambda v: h >= v) if buy else (lambda v: lo <= v)
        if stage < 1 and hit(t1_):
            cur = entry; stage = 1
        if stage < 2 and hit(t2_):
            cur = t1_; stage = 2
        if hit(target):
            return 3
        k += 1
    return None


def run(p=None, q=None, z=None, win=60, hz="4h", diag=False):
    trades, busy, src, stages = [], 0.0, {}, []
    for tr in triggers:
        t = tr["t"]
        if t < busy:
            continue
        kw = tr["kw"]
        pl = tr["pools"][win]
        n, c = CT.N_NOISE, CT.C_REACH
        if p is not None:
            arr, s = pl["mae"]
            src["وقف:" + s] = src.get("وقف:" + s, 0) + 1
            if arr is not None:
                n = float(np.percentile(arr, p))
        if q is not None:
            arr, s = pl[hz]
            src["هدف:" + s] = src.get("هدف:" + s, 0) + 1
            if arr is not None:
                c = float(np.percentile(arr, q)) * kw["atr_5m"] / kw["atr_1d"]
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
        if diag:
            stages.append((card["window"], thirds_stage(card["entry"], card["stop"], card["target"], buy, k1),
                           abs(card["target"] - card["entry"]) / kw["atr_5m"], card["risk"] / kw["atr_5m"]))
        trades.append((t, r, card["window"], buy, card["risk"] / card["entry"] * 1e4,
                       card["risk"], abs(card["target"] - card["entry"]), exit_t - t, n))
        busy = exit_t + 60
    return (trades, src, stages) if diag else (trades, src)


SPLIT = R.START + 0.7 * (R.END - R.START)


def summary(tr, src=None):
    learn = [x for x in tr if x[0] < SPLIT]
    test = [x for x in tr if x[0] >= SPLIT]
    med = lambda xs: round(float(np.median(xs)), 2) if xs else None
    out = {"كلّه": R.stats(tr), "تعلّم": R.stats(learn), "اختبار": R.stats(test),
           "لندن": R.stats([x for x in tr if x[2] == "london_peak"]),
           "نيويورك": R.stats([x for x in tr if x[2] == "ny_open"]),
           "وسيط_الوقف_نقاط": {"لندن": med([x[5] for x in tr if x[2] == "london_peak"]),
                               "نيويورك": med([x[5] for x in tr if x[2] == "ny_open"])},
           "وسيط_الهدف_نقاط": {"لندن": med([x[6] for x in tr if x[2] == "london_peak"]),
                               "نيويورك": med([x[6] for x in tr if x[2] == "ny_open"])},
           "وسيط_العمر_دقائق": med([x[7] / 60 for x in tr]),
           "وسيط_n_الفعليّ": {"لندن": med([x[8] for x in tr if x[2] == "london_peak"]),
                             "نيويورك": med([x[8] for x in tr if x[2] == "ny_open"])}}
    if src:
        out["مصدر_العيار"] = src
    return out


def line(name, s):
    a, l, te = s["كلّه"], s["تعلّم"], s["اختبار"]
    return "%-22s | n=%s R=%s R/ص=%s معامل=%s سحب=%s أنصاف=%s | تعلّم n=%s R/ص=%s | اختبار n=%s R/ص=%s معامل=%s | وقف=%s هدف=%s n_فعليّ=%s" % (
        name, a.get("n"), a.get("R"), a.get("R/صفقة"), a.get("معامل"), a.get("سحب_R"), list(a.get("أنصاف", {}).values()),
        l.get("n"), l.get("R/صفقة"), te.get("n"), te.get("R/صفقة"), te.get("معامل"),
        s["وسيط_الوقف_نقاط"], s["وسيط_الهدف_نقاط"], s["وسيط_n_الفعليّ"])


REF = None


def accept(s):
    a, l, te = s["كلّه"], s["تعلّم"], s["اختبار"]
    r = REF
    checks = {"اختبار_أعلى": (te.get("R/صفقة") or -9) > r["اختبار"]["R/صفقة"],
              "تعلّم_لا_يسوء": (l.get("R/صفقة") or -9) >= r["تعلّم"]["R/صفقة"],
              "الأنصاف_الخمسة_موجبة": len(a.get("أنصاف", {})) == 5 and all(v > 0 for v in a.get("أنصاف", {}).values()),
              "السحب_لا_يسوء": (a.get("سحب_R") if a.get("سحب_R") is not None else 99) <= r["كلّه"]["سحب_R"],
              "العدد_فوق_النصف": a.get("n", 0) > r["كلّه"]["n"] / 2}
    return all(checks.values()), checks


if __name__ == "__main__":
    results, trials = {"_وصف_التوزيعات": DESC}, 0
    tr, _, stages = run(diag=True)
    REF = summary(tr)
    results["مرجع"] = REF
    log(line("مرجع", REF))
    life = np.percentile([x[7] / 60 for x in tr], [50, 75, 90])
    log("أعمار صفقات المرجع (دقائق): وسيط=%.0f · مئين75=%.0f · مئين90=%.0f" % tuple(life))
    diag = {}
    for w in ("london_peak", "ny_open"):
        st = [s for s in stages if s[0] == w]
        cnt = {k: sum(1 for s in st if s[1] == k) for k in (0, 1, 2, 3)}
        diag[w] = {"عدد": len(st), "وقف_قبل_الأوّل": cnt[0], "بلغ_الأوّل_فقط": cnt[1], "بلغ_الثاني": cnt[2], "بلغ_الهدف": cnt[3],
                   "مسافة_الهدف_بمدى5_وسيط": round(float(np.median([s[2] for s in st])), 2),
                   "الوقف_بمدى5_وسيط": round(float(np.median([s[3] for s in st])), 2)}
        log("  مراحل المرجع %s: %s" % (w, diag[w]))
    results["_مراحل_المرجع"] = diag
    results["_أعمار_المرجع_دقائق"] = np.round(life, 0).tolist()
    families = {"١_ضجيج": [dict(p=v, win=w) for w in WINS for v in (60, 70, 80, 90)],
                "٢_مسافة": [dict(q=v, hz=h) for h in ("4h", "eod") for v in (50, 60, 70, 80)],
                "٣_تمدّد": [dict(z=v) for v in (1.5, 2.0)]}
    chosen = {}
    for fam, grid in families.items():
        best = None
        for cfg in grid:
            trials += 1
            tr, src = run(**cfg)
            s = summary(tr, src)
            s["قبول"], s["فحوص"] = accept(s)
            name = "%s %s" % (fam, " ".join("%s=%s" % kv for kv in cfg.items()))
            s["عيار"] = cfg
            results[name] = s
            log(line(name, s), "| مصدر:", src, "| قبول:", s["قبول"])
            score = s["تعلّم"].get("R/صفقة")
            if score is not None and s["تعلّم"].get("n", 0) > REF["تعلّم"]["n"] / 2 and (best is None or score > best[0]):
                best = (score, cfg, name)
        chosen[fam] = best
        if best:
            log("◀ المختار بالتعلّم لـ%s: %s (تعلّم R/ص=%s) ⟵ اختبار R/ص=%s قبول=%s" % (
                fam, best[2], best[0], results[best[2]]["اختبار"].get("R/صفقة"), results[best[2]]["قبول"]))
        else:
            log("◀ لا عيار في %s يُبقي عدد صفقات التعلّم فوق نصف المرجع" % fam)
    adders = [f for f, b in chosen.items() if b and (results[b[2]]["اختبار"].get("R/صفقة") or -9) > REF["اختبار"]["R/صفقة"]]
    log("أضاف خارج العيّنة (المختار بالتعلّم):", adders)
    for k in range(2, len(adders) + 1):
        for combo in itertools.combinations(adders, k):
            trials += 1
            cfg = {}
            for f in combo:
                cfg.update(chosen[f][1])
            tr, src = run(**cfg)
            s = summary(tr, src)
            s["قبول"], s["فحوص"] = accept(s)
            s["عيار"] = cfg
            name = "٤_اجتماع " + " ".join("%s=%s" % kv for kv in cfg.items())
            results[name] = s
            log(line(name, s), "| قبول:", s["قبول"])
    results["_meta"] = {"العيارات_المجرّبة_في_هذا_الملفّ": trials,
                        "المختار_بالتعلّم": {k: (v[2] if v else None) for k, v in chosen.items()},
                        "أضاف_خارج_العيّنة": adders, "K_موجات": K_LEGS, "أقلّ_عيّنة": MIN_N, "أحداث": len(events),
                        "لحظات_زناد": len(triggers), "حدّ_التعلّم": time.strftime("%Y-%m-%d %H:%M", time.gmtime(SPLIT))}
    log("العيارات المجرّبة في هذا الملفّ (بلا المرجع):", trials)
    json.dump(results, open("card_calib2.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1, default=str)
    log("كُتب card_calib2.json")
