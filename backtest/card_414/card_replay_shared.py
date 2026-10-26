# -*- coding: utf-8 -*-
"""إعادة البطاقة على التاريخ بقلبها المشترك `shared/card_trend.py` نفسه الذي يقرؤه الحيّ —
للتحقّق أنّ الحيّ = المقيس. الحقائق تُبنى من الشموع بتعريفات الأقسام: متوسّط 20 (151) · متوسّط المدى 14 (153)
· القمم والقيعان المؤكَّدة (201) · النافذة (`shared/owner_windows`) · الخبر (التقويم ±15 د كـ411)."""
import bisect
import json
import sys

sys.path.insert(0, r"C:\Users\NQ\QUANT_NQ")
import card_replay as R                      # البيانات والأدوات (لا يشغّل شيئًا عند الاستيراد)
from shared import card_trend as CT
from shared.owner_windows import owner_window


KEEP = {"5m": 100, "1h": 200, "4h": 200}   # = LADDER_KEEP في 201


def split(rows):
    hi = [(ts, p) for ts, p, h in rows if h]; lo = [(ts, p) for ts, p, h in rows if not h]
    return (hi, [x[0] for x in hi]), (lo, [x[0] for x in lo])


def ladder_at(t, frames):
    out = {}
    for name, ((hi, hit), (lo, lot)) in frames.items():
        kh, kl = bisect.bisect_right(hit, t), bisect.bisect_right(lot, t)
        out[name] = {"highs": [[p, ts] for ts, p in hi[max(0, kh - KEEP[name]):kh]],
                     "lows": [[p, ts] for ts, p in lo[max(0, kl - KEEP[name]):kl]]}
    return out


sw1 = R.swings(R.h1, 3600); sw4 = R.swings(R.h4, 14400)
frames = {"5m": split(R.sw5), "1h": split(sw1), "4h": split(sw4)}


def fact_trend(rows, ema_vals, times, seconds, t):
    i = R.closed_index(times, seconds, t)
    return None if i < 20 else {"close": rows[i][4], "ema_slow_value": ema_vals[i]}


def run(b=0.0, n=2.0, c=1.5):
    trades, busy, opened = [], 0.0, 0
    for j in range(1, len(R.m5)):
        t_close = R.m5[j][0] + 300
        if t_close < R.START or t_close < busy:
            continue
        idd = R.closed_index(R.td1, 86400, t_close)
        card = CT.evaluate(at=t_close, close=R.m5[j][4], prev_close=R.m5[j - 1][4],
                           trend_1h=fact_trend(R.h1, R.e_h1, R.th1, 3600, t_close),
                           trend_4h=fact_trend(R.h4, R.e_h4, R.th4, 14400, t_close),
                           atr_5m=R.a5[j], atr_1d=R.ad1[idd] if idd >= 0 else None,
                           ladder=ladder_at(t_close, frames), window=owner_window(t_close),
                           news_blocked=R.news_block(t_close), b=b, n=n, c=c)
        if card["status"] != CT.OPEN:
            continue
        buy = card["side"] == CT.BUY
        k1 = bisect.bisect_right(R.t1, t_close - 60)
        r, exit_t = R.thirds(card["entry"], card["stop"], card["target"], buy, k1)
        if r is None:
            break
        trades.append((t_close, r, card["window"], buy, card["risk"] / card["entry"] * 1e4))
        busy = exit_t + 60
    return trades


if __name__ == "__main__":
    tr = run()
    split = R.START + 0.7 * (R.END - R.START)
    out = {"كلّه": R.stats(tr), "تعلّم": R.stats([x for x in tr if x[0] < split]),
           "اختبار": R.stats([x for x in tr if x[0] >= split]),
           "لندن": R.stats([x for x in tr if x[2] == "london_peak"]),
           "نيويورك": R.stats([x for x in tr if x[2] == "ny_open"])}
    print(json.dumps(out, ensure_ascii=False))
    json.dump({"trades": tr, "stats": out}, open("card_shared_trades.json", "w", encoding="utf-8"), ensure_ascii=False)
