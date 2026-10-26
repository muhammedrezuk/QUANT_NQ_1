# -*- coding: utf-8 -*-
"""التحقّق النهائيّ: القلب المشترك `card_trend.evaluate` بالأسواق المرتبطة (peers) — الحيّ = المقيس."""
import bisect
import json
import sys

sys.path.insert(0, r"C:\Users\NQ\QUANT_NQ")
import card_replay as R
import card_replay_shared as S
import card_variants as V
from shared import card_trend as CT
from shared.owner_windows import owner_window


def peer_fact(pack, seconds, t):
    rows, e, times = pack
    i = R.closed_index(times, seconds, t)
    return None if i < 20 else {"close": rows[i][4], "ema_slow_value": e[i]}


def run():
    trades, busy, tally = [], 0.0, {}
    for j in range(1, len(R.m5)):
        t_close = R.m5[j][0] + 300
        if t_close < R.START or t_close < busy:
            continue
        idd = R.closed_index(R.td1, 86400, t_close)
        peers = {sym: (peer_fact(h1, 3600, t_close), peer_fact(h4, 14400, t_close)) for sym, (h1, h4) in V.REF.items()}
        card = CT.evaluate(at=t_close, close=R.m5[j][4], prev_close=R.m5[j - 1][4],
                           trend_1h=S.fact_trend(R.h1, R.e_h1, R.th1, 3600, t_close),
                           trend_4h=S.fact_trend(R.h4, R.e_h4, R.th4, 14400, t_close),
                           atr_5m=R.a5[j], atr_1d=R.ad1[idd] if idd >= 0 else None,
                           ladder=S.ladder_at(t_close, S.frames), window=owner_window(t_close),
                           news_blocked=R.news_block(t_close), peers=peers)
        tally[card["status"]] = tally.get(card["status"], 0) + 1
        if card["status"] != CT.OPEN:
            continue
        buy = card["side"] == CT.BUY
        k1 = bisect.bisect_right(R.t1, t_close - 60)
        r, exit_t = R.thirds(card["entry"], card["stop"], card["target"], buy, k1)
        if r is None:
            break
        trades.append((t_close, r, card["window"], buy, card["risk"] / card["entry"] * 1e4))
        busy = exit_t + 60
    return trades, tally


if __name__ == "__main__":
    tr, tally = run()
    split = R.START + 0.7 * (R.END - R.START)
    out = {"كلّه": R.stats(tr), "تعلّم": R.stats([x for x in tr if x[0] < split]),
           "اختبار": R.stats([x for x in tr if x[0] >= split]),
           "لندن": R.stats([x for x in tr if x[2] == "london_peak"]),
           "نيويورك": R.stats([x for x in tr if x[2] == "ny_open"]), "حالات_البطاقات": tally}
    print(json.dumps(out, ensure_ascii=False))
    json.dump(out, open("card_final_check.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
