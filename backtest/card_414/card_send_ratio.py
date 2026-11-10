# -*- coding: utf-8 -*-
"""طالب الدخول 555 يحكم عند الإرسال بنسبةٍ صافية بعد السبريد: (العائد − س) ÷ (الخطر + س) ≥ 3.
والبطاقة تختار أقرب هدفٍ ≥ 3R قبل السبريد. كم يُردّ؟ وما البديل؟
  أ) الحيّ كما هو: البطاقة كما هي، والمردودة صافيًا لا تُفتح.
  ب) البطاقة تختار أقرب مستوى يعطي 3 صافية: المسافة ≥ 3·الخطر + 4·س (وفي المتناول)."""
import bisect
import json
import sys
import os

sys.path.insert(0, r"C:\Users\NQ\QUANT_NQ")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import card_replay as R
import card_replay_shared as S
import card_variants as V
from shared import card_trend as CT
from shared.owner_windows import owner_window
from card_final_check import peer_fact


def run(mode, spread):
    trades, busy, rejected = [], 0.0, 0
    for j in range(1, len(R.m5)):
        t_close = R.m5[j][0] + 300
        if t_close < R.START or t_close < busy:
            continue
        idd = R.closed_index(R.td1, 86400, t_close)
        peers = {sym: (peer_fact(h1, 3600, t_close), peer_fact(h4, 14400, t_close)) for sym, (h1, h4) in V.REF.items()}
        ladder = S.ladder_at(t_close, S.frames)
        card = CT.evaluate(at=t_close, close=R.m5[j][4], prev_close=R.m5[j - 1][4],
                           trend_1h=S.fact_trend(R.h1, R.e_h1, R.th1, 3600, t_close),
                           trend_4h=S.fact_trend(R.h4, R.e_h4, R.th4, 14400, t_close),
                           atr_5m=R.a5[j], atr_1d=R.ad1[idd] if idd >= 0 else None,
                           ladder=ladder, window=owner_window(t_close),
                           news_blocked=R.news_block(t_close), peers=peers)
        if card["status"] != CT.OPEN:
            continue
        buy = card["side"] == CT.BUY
        entry, risk, target = card["entry"], card["risk"], card["target"]
        net = (abs(target - entry) - spread) / (risk + spread)
        if net + 1e-9 < 3.0:
            if mode == "a":
                rejected += 1
                continue
            levels = []
            for frame in ("1h", "4h"):
                levels.extend(((ladder or {}).get(frame) or {}).get("highs" if buy else "lows") or [])
            target = CT.nearest_target(levels, buy, entry, risk, card["reach"], t_close, rr=3.0 + 4.0 * spread / risk)
            if target is None:
                rejected += 1
                continue
        k1 = bisect.bisect_right(R.t1, t_close - 60)
        r, exit_t = R.thirds(entry, card["stop"], target, buy, k1)
        if r is None:
            break
        trades.append((t_close, r, card["window"], buy, risk / entry * 1e4))
        busy = exit_t + 60
    return trades, rejected


if __name__ == "__main__":
    split = R.START + 0.7 * (R.END - R.START)
    out = {}
    for mode in ("a", "b"):
        for spread in (1.0, 1.5):
            tr, rej = run(mode, spread)
            key = "%s س=%.1f" % ("أ_الحيّ_كما_هو" if mode == "a" else "ب_هدفٌ_صافٍ", spread)
            out[key] = {"مردود": rej, "كلّه": R.stats(tr), "تعلّم": R.stats([x for x in tr if x[0] < split]),
                        "اختبار": R.stats([x for x in tr if x[0] >= split]),
                        "لندن": R.stats([x for x in tr if x[2] == "london_peak"]),
                        "نيويورك": R.stats([x for x in tr if x[2] == "ny_open"])}
            s = out[key]
            print("%s | مردود=%d | n=%s R=%s R/ص=%s معامل=%s سحب=%s أنصاف=%s | تعلّم %s | اختبار n=%s %s معامل=%s" % (
                key, rej, s["كلّه"].get("n"), s["كلّه"].get("R"), s["كلّه"].get("R/صفقة"), s["كلّه"].get("معامل"),
                s["كلّه"].get("سحب_R"), s["كلّه"].get("أنصاف"), s["تعلّم"].get("R/صفقة"), s["اختبار"].get("n"),
                s["اختبار"].get("R/صفقة"), s["اختبار"].get("معامل")), flush=True)
    json.dump(out, open("card_send_ratio.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
