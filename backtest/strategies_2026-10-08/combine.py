# -*- coding: utf-8 -*-
"""دمج البطاقة 414 (بحكم الإرسال الحيّ، سبريد 1.5) مع صفقات استراتيجيّة أخرى — مركزٌ واحد في الوقت، والأسبق أوّلًا.
تقريب: صفقات الأخرى محسوبة بسلسلتها وحدها؛ ما يحجبه مركز 414 يُترك ولا يُستبدل بإشارةٍ لاحقة."""
import bisect
import json
import os
import sys

sys.path.insert(0, r"C:\Users\NQ\QUANT_NQ")
sys.path.insert(0, r"C:\Users\NQ\QUANT_NQ\backtest\card_414")
import card_replay as R
import card_replay_shared as S
import card_variants as V
from shared import card_trend as CT
from shared.owner_windows import owner_window
from card_final_check import peer_fact

SPREAD = 1.5


def card414():
    trades, busy = [], 0.0
    for j in range(1, len(R.m5)):
        t_close = R.m5[j][0] + 300
        if t_close < R.START or t_close < busy:
            continue
        idd = R.closed_index(R.td1, 86400, t_close)
        peers = {s: (peer_fact(h1, 3600, t_close), peer_fact(h4, 14400, t_close)) for s, (h1, h4) in V.REF.items()}
        card = CT.evaluate(at=t_close, close=R.m5[j][4], prev_close=R.m5[j - 1][4],
                           trend_1h=S.fact_trend(R.h1, R.e_h1, R.th1, 3600, t_close),
                           trend_4h=S.fact_trend(R.h4, R.e_h4, R.th4, 14400, t_close),
                           atr_5m=R.a5[j], atr_1d=R.ad1[idd] if idd >= 0 else None,
                           ladder=S.ladder_at(t_close, S.frames), window=owner_window(t_close),
                           news_blocked=R.news_block(t_close), peers=peers)
        if card["status"] != CT.OPEN:
            continue
        if (abs(card["target"] - card["entry"]) - SPREAD) / (card["risk"] + SPREAD) + 1e-9 < 3.0:
            continue
        buy = card["side"] == CT.BUY
        k1 = bisect.bisect_right(R.t1, t_close - 60)
        r, exit_t = R.thirds(card["entry"], card["stop"], card["target"], buy, k1)
        if r is None:
            break
        trades.append([t_close, exit_t, r, card["window"], buy, card["risk"] / card["entry"] * 1e4])
        busy = exit_t + 60
    return trades


def merge(a, b):
    rows = sorted([(t[0], 0, t) for t in a] + [(t[0], 1, t) for t in b])
    out, busy = [], 0.0
    for t_close, src, t in rows:
        if t_close < busy:
            continue
        out.append((t_close, t[2], t[3], t[4], t[5], src))
        busy = t[1] + 60
    return out


if __name__ == "__main__":
    base = card414()
    split = R.START + 0.7 * (R.END - R.START)
    days = (R.END - R.START) / 86400 * 5 / 7
    report = {"414": base}
    out = {}
    def summary(tr):
        return {"كلّه": R.stats(tr), "تعلّم": R.stats([x for x in tr if x[0] < split]),
                "اختبار": R.stats([x for x in tr if x[0] >= split]), "صفقات/يوم": round(len(tr) / days, 2)}
    out["414 وحدها"] = summary([(t[0], t[2], t[3], t[4], t[5]) for t in base])
    for name in sys.argv[1:]:
        other = json.load(open(os.path.join(name, "trades_best.json"), encoding="utf-8"))
        merged = merge(base, other)
        out["414 + " + name] = summary(merged)
        out["414 + " + name]["من الأخرى"] = sum(1 for x in merged if x[5] == 1)
    print(json.dumps(out, ensure_ascii=False, indent=1))
    json.dump(out, open("combine.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
