# -*- coding: utf-8 -*-
"""طبقات البطاقة الإضافيّة على السنتين — كلّ طبقةٍ وحدها ثمّ معًا (تغييرٌ واحد في كلّ مرّة):
  أساس      : البطاقة 414 كما هي حيّة.
  خبر+انتظار: لا دخول من 15 د قبل خبرٍ أمريكيّ عالٍ حتّى 60 د بعده (قانون المالك: نتداول بعد الخبر).
  ارتباط    : الإس آند بي والداو كلاهما في جهة الناسداك على الساعة والأربع ساعات (إغلاقٌ مقابل متوسّط 20).
  كلاهما    : الطبقتان معًا.
"""
import bisect
import json
import sys

sys.path.insert(0, r"C:\Users\NQ\QUANT_NQ")
import card_replay as R
import card_replay_shared as S
from shared import card_trend as CT
from shared.owner_windows import owner_window


def load(sym):
    R.SYMBOL = sym
    h1, h4 = R.bars("H1", R.START - 120 * 86400), R.bars("H4", R.START - 300 * 86400)
    return (h1, R.ema([r[4] for r in h1]), [r[0] for r in h1]), (h4, R.ema([r[4] for r in h4]), [r[0] for r in h4])


REF = {s: load(s) for s in ("US500", "US30")}
R.SYMBOL = "USTEC"


def side(pack, seconds, t):
    rows, e, times = pack
    i = R.closed_index(times, seconds, t)
    if i < 20:
        return 0
    return 1 if rows[i][4] > e[i] else -1 if rows[i][4] < e[i] else 0


def corr_ok(t, d):
    for sym, (h1, h4) in REF.items():
        if not (side(h1, 3600, t) == d and side(h4, 14400, t) == d):
            return False
    return True


def news_wait(t, before=900, after=3600):
    i = bisect.bisect_left(R.news, t - after)
    return i < len(R.news) and R.news[i] <= t + before


def run(news_after=False, corr=False):
    trades, busy = [], 0.0
    for j in range(1, len(R.m5)):
        t_close = R.m5[j][0] + 300
        if t_close < R.START or t_close < busy:
            continue
        idd = R.closed_index(R.td1, 86400, t_close)
        blocked = news_wait(t_close) if news_after else R.news_block(t_close)
        card = CT.evaluate(at=t_close, close=R.m5[j][4], prev_close=R.m5[j - 1][4],
                           trend_1h=S.fact_trend(R.h1, R.e_h1, R.th1, 3600, t_close),
                           trend_4h=S.fact_trend(R.h4, R.e_h4, R.th4, 14400, t_close),
                           atr_5m=R.a5[j], atr_1d=R.ad1[idd] if idd >= 0 else None,
                           ladder=S.ladder_at(t_close, S.frames), window=owner_window(t_close),
                           news_blocked=blocked)
        if card["status"] != CT.OPEN:
            continue
        buy = card["side"] == CT.BUY
        if corr and not corr_ok(t_close, 1 if buy else -1):
            continue
        k1 = bisect.bisect_right(R.t1, t_close - 60)
        r, exit_t = R.thirds(card["entry"], card["stop"], card["target"], buy, k1)
        if r is None:
            break
        trades.append((t_close, r, card["window"], buy, card["risk"] / card["entry"] * 1e4))
        busy = exit_t + 60
    return trades


if __name__ == "__main__":
    split = R.START + 0.7 * (R.END - R.START)
    out = {}
    for name, kw in (("أساس", {}), ("خبر+انتظار", {"news_after": True}), ("ارتباط", {"corr": True}),
                     ("كلاهما", {"news_after": True, "corr": True})):
        tr = run(**kw)
        out[name] = {"كلّه": R.stats(tr), "تعلّم": R.stats([x for x in tr if x[0] < split]),
                     "اختبار": R.stats([x for x in tr if x[0] >= split])}
        s = out[name]
        print("%-10s | كلّه n=%s R=%s R/ص=%s معامل=%s سحب=%s أنصاف=%s | تعلّم R/ص=%s | اختبار R/ص=%s معامل=%s" % (
            name, s["كلّه"]["n"], s["كلّه"]["R"], s["كلّه"]["R/صفقة"], s["كلّه"]["معامل"], s["كلّه"]["سحب_R"],
            s["كلّه"]["أنصاف"], s["تعلّم"]["R/صفقة"], s["اختبار"]["R/صفقة"], s["اختبار"]["معامل"]), flush=True)
    json.dump(out, open("card_variants.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
