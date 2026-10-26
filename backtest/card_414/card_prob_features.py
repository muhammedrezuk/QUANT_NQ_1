# -*- coding: utf-8 -*-
"""احتمال نجاح البطاقة — المرحلة ١: خصائص كلّ صفقة **وقت القرار فقط** + نتيجتها.

الإعادة نفسها التي في `card_final_check.py` (القلب المشترك `shared/card_trend.evaluate` بالأسواق المرتبطة)،
مع فرقين لا يغيّران النتيجة:
  · الشموع خارج نافذة المالك لا يُبنى لها سلّم المستويات (البطاقة ترفضها أوّل سطر: NO_WINDOW) — للسرعة.
  · محاكاة الأثلاث نسخةٌ حرفيّة من `card_replay.thirds` تُرجع أيضًا المرحلة التي بلغتها (0 وقف · 1 الهدف الأوّل
    · 2 الثاني · 3 النهائيّ)؛ وتُطابَق مع الأصل صفقةً صفقة.
`run(take)` يقبل مرشّحًا على الخصائص (للمرحلة ٣: لا دخول تحت احتمالٍ ما) — الصفقة المتروكة لا تشغل الوقت.
"""
import bisect
import json
import sys
from datetime import datetime, timezone

sys.path.insert(0, r"C:\Users\NQ\QUANT_NQ")
import card_replay as R
import card_replay_shared as S
import card_variants as V
import card_final_check as F
from shared import card_trend as CT
from shared.owner_windows import owner_window, local_time, WINDOWS

A_H1, A_H4 = R.atr(R.h1), R.atr(R.h4)
PEER_ATR = {sym: (R.atr(h1[0]), R.atr(h4[0])) for sym, (h1, h4) in V.REF.items()}
OPEN_AT = {name: (fn, start) for name, fn, start, end in WINDOWS}

# متوسّط مدى 5 د لكلّ شمعةٍ داخل كلّ نافذة — لنظام التذبذب (مقارنةً بالنافذة نفسها في الأسابيع الأربعة الماضية)
WIN5 = {}
for _j in range(1, len(R.m5)):
    _t = R.m5[_j][0] + 300
    _w = owner_window(_t)
    if _w:
        WIN5.setdefault(_w, ([], []))
        WIN5[_w][0].append(_t)
        WIN5[_w][1].append(R.a5[_j])


def ext(pack_rows, ema_vals, atr_vals, times, seconds, t, sgn):
    """بعد إغلاق آخر شمعةٍ مغلقة عن متوسّطها 20، بوحدات متوسّط مداها 14، في جهة الصفقة (موجبٌ = مع الجهة)."""
    i = R.closed_index(times, seconds, t)
    return sgn * (pack_rows[i][4] - ema_vals[i]) / atr_vals[i]


def center_index(confirm):
    """فهرس شمعة 5 د المركزيّة لقمّةٍ/قاعٍ مؤكَّد (التأكيد = بداية الشمعة +2 بعد المركز + 300)."""
    k = bisect.bisect_left(R.t5, confirm - 300)
    return k - 2 if k < len(R.t5) and R.t5[k] == confirm - 300 else None


def features(j, t, card, ladder):
    buy = card["side"] == CT.BUY
    sgn = 1 if buy else -1
    entry, stop, target, risk = card["entry"], card["stop"], card["target"], card["risk"]
    a5, ad = card["atr_5m"], card["atr_1d"]
    win = card["window"]
    fn, start = OPEN_AT[win]
    loc = local_time(t, fn)
    utc = datetime.fromtimestamp(t, timezone.utc)
    hi, lo = CT.last_swings(ladder["5m"]["highs"], ladder["5m"]["lows"], t)
    broken, pull = (hi, lo) if buy else (lo, hi)
    cp, cb = center_index(pull[1]), center_index(broken[1])
    # نظام التذبذب: موقع متوسّط مدى 5 د الآن بين قيم النافذة نفسها في الـ28 يومًا الماضية (قبل اللحظة تمامًا)
    ts, vs = WIN5[win]
    past = vs[bisect.bisect_left(ts, t - 28 * 86400):bisect.bisect_left(ts, t)]
    vol_pct = sum(v < a5 for v in past) / len(past) if past else None
    idd = R.closed_index(R.td1, 86400, t)
    pd = R.ad1[max(0, idd - 120):idd]
    atrd_pct = sum(v < R.ad1[idd] for v in pd) / len(pd) if pd else None
    k = bisect.bisect_right(R.news, t)
    since = (t - R.news[k - 1]) / 60 if k > 0 else None
    to = (R.news[k] - t) / 60 if k < len(R.news) else None
    f = {"t": t, "date": utc.strftime("%Y-%m-%d %H:%M"), "window": win, "buy": buy,
         "hour_utc": utc.hour, "min_in_window": loc.hour * 60 + loc.minute - start, "weekday": loc.weekday(),
         "entry": entry, "stop": stop, "target": target,
         "rr": card["rr"], "risk_bps": risk / entry * 1e4, "risk_atr5": risk / a5, "tgt_atrd": abs(target - entry) / ad,
         "ext_nq_h1": ext(R.h1, R.e_h1, A_H1, R.th1, 3600, t, sgn),
         "ext_nq_h4": ext(R.h4, R.e_h4, A_H4, R.th4, 14400, t, sgn),
         "pull_depth_atr5": abs(broken[0] - pull[0]) / a5,
         "pull_age_bars": (j - cp) if cp is not None else None,
         "leg_age_bars": (j - cb) if cb is not None else None,
         "vol_pct": vol_pct, "vol_tercile": None if vol_pct is None else (0 if vol_pct < 1 / 3 else 1 if vol_pct < 2 / 3 else 2),
         "atrd_pct": atrd_pct,
         "news_since_min": since, "news_to_min": to}
    for sym, (h1, h4) in V.REF.items():
        tag = {"US500": "sp", "US30": "dj"}[sym]
        f["ext_%s_h1" % tag] = ext(h1[0], h1[1], PEER_ATR[sym][0], h1[2], 3600, t, sgn)
        f["ext_%s_h4" % tag] = ext(h4[0], h4[1], PEER_ATR[sym][1], h4[2], 14400, t, sgn)
    f["agree_min"] = min(f[k_] for k_ in ("ext_nq_h1", "ext_nq_h4", "ext_sp_h1", "ext_sp_h4", "ext_dj_h1", "ext_dj_h4"))
    return f


def thirds_stage(entry, stop, target, buy, k):
    """نسخةٌ حرفيّة من `card_replay.thirds` تُرجع أيضًا المرحلة المبلوغة قبل الخروج."""
    m1, cost = R.m1, R.COST
    risk, span, sgn = abs(entry - stop), abs(target - entry), (1 if buy else -1)
    t1_, t2_ = entry + sgn * span / 3, entry + sgn * 2 * span / 3
    cur, rem, real, stage = stop, 1.0, 0.0, 0
    while k < len(m1):
        t, o, h, lo, c = m1[k]
        if (lo <= cur) if buy else (h >= cur):
            px = min(o, cur) if buy else max(o, cur)
            return real + rem * ((px - entry) * sgn / risk) - cost / risk, t, stage
        hit = (lambda v: h >= v) if buy else (lambda v: lo <= v)
        if stage < 1 and hit(t1_):
            real += (rem / 3) * (span / 3 / risk); rem -= rem / 3; cur = entry; stage = 1
        if stage < 2 and hit(t2_):
            real += (rem / 2) * (2 * span / 3 / risk); rem -= rem / 2; cur = t1_; stage = 2
        if hit(target):
            return real + rem * (span / risk) - cost / risk, t, 3
        k += 1
    return None, None, None


def run(take=None):
    trades, busy, skipped, mismatch = [], 0.0, 0, 0
    for j in range(1, len(R.m5)):
        t_close = R.m5[j][0] + 300
        if t_close < R.START or t_close < busy:
            continue
        win = owner_window(t_close)
        if not win:
            continue                      # = NO_WINDOW في البطاقة (أوّل فحص فيها)
        ladder = S.ladder_at(t_close, S.frames)
        idd = R.closed_index(R.td1, 86400, t_close)
        peers = {sym: (F.peer_fact(h1, 3600, t_close), F.peer_fact(h4, 14400, t_close)) for sym, (h1, h4) in V.REF.items()}
        card = CT.evaluate(at=t_close, close=R.m5[j][4], prev_close=R.m5[j - 1][4],
                           trend_1h=S.fact_trend(R.h1, R.e_h1, R.th1, 3600, t_close),
                           trend_4h=S.fact_trend(R.h4, R.e_h4, R.th4, 14400, t_close),
                           atr_5m=R.a5[j], atr_1d=R.ad1[idd] if idd >= 0 else None,
                           ladder=ladder, window=win, news_blocked=R.news_block(t_close), peers=peers)
        if card["status"] != CT.OPEN:
            continue
        f = features(j, t_close, card, ladder)
        if take is not None and not take(f):
            skipped += 1
            continue
        buy = card["side"] == CT.BUY
        k1 = bisect.bisect_right(R.t1, t_close - 60)
        r, exit_t, stage = thirds_stage(card["entry"], card["stop"], card["target"], buy, k1)
        if r is None:
            break
        r0, e0 = R.thirds(card["entry"], card["stop"], card["target"], buy, k1)
        if abs(r0 - r) > 1e-9 or e0 != exit_t:
            mismatch += 1
        f.update({"r": r, "stage": stage, "hit1": stage >= 1, "hit_final": stage == 3,
                  "exit_t": exit_t, "hold_min": (exit_t - t_close) / 60})
        trades.append(f)
        busy = exit_t + 60
    return trades, skipped, mismatch


def as_tuples(tr):
    return [(x["t"], x["r"], x["window"], x["buy"], x["risk_bps"]) for x in tr]


if __name__ == "__main__":
    tr, skipped, mismatch = run()
    split = R.START + 0.7 * (R.END - R.START)
    tt = as_tuples(tr)
    out = {"كلّه": R.stats(tt), "تعلّم": R.stats([x for x in tt if x[0] < split]),
           "اختبار": R.stats([x for x in tt if x[0] >= split]), "عدم_تطابق_المحاكاة": mismatch,
           "split": split, "START": R.START, "END": R.END}
    print(json.dumps(out, ensure_ascii=False), flush=True)
    json.dump({"meta": out, "trades": tr}, open("card_prob_trades.json", "w", encoding="utf-8"), ensure_ascii=False, indent=0)
