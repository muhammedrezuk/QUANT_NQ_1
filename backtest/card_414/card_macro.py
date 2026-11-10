# -*- coding: utf-8 -*-
"""الخطوة ٤-ف/٧ — بقيّة المراجع: الدولار · الخوف · عائد العشر سنين (ياهو، الساعة منذ ٢٠٢٤-١٠-٠٨).
كلّ مرجعٍ تغييرٌ واحد فوق البطاقة المعتمدة (الإس آند بي والداو في جهتها).
القاعدة مثبّتة قبل القياس (العلاقة الاقتصاديّة المعروفة، لا تنقيب): شراء الناسداك يشترط المرجع **هابطًا**
(إغلاقه تحت متوسّط 20 على الساعة والأربع ساعات معًا)، والبيع يشترطه **صاعدًا**. والمرجع الغائب = لا صفقة.
الأربع ساعات تُبنى من شموع الساعة في دلاء غرينتش؛ الدلو مغلق حين تُغلق آخر ساعةٍ فيه — لا نظر للمستقبل."""
import bisect
import json
import sqlite3
import sys

sys.path.insert(0, r"C:\Users\NQ\QUANT_NQ")
sys.path.insert(0, __import__("os").path.dirname(__import__("os").path.abspath(__file__)))
import card_replay as R
import card_replay_shared as S
import card_variants as V
from shared import card_trend as CT
from shared.owner_windows import owner_window

Y = sqlite3.connect(r"file:C:\Users\NQ\QUANT_NQ\forex_runtime\var\history\yahoo_refs.db?mode=ro", uri=True)
REFS = {"الدولار": "DX-Y.NYB", "الخوف": "^VIX", "العشر_سنين": "^TNX"}


def pack(symbol):
    h1 = [(float(ts), c) for ts, c in Y.execute(
        "select ts_utc, close from candles where symbol=? and interval='1h' and close is not null order by ts_utc",
        (symbol,))]
    buckets = {}
    for ts, c in h1:
        b = int(ts // 14400) * 14400
        end = ts + 3600
        if b not in buckets or end >= buckets[b][0]:
            buckets[b] = (end, c)
    h4 = sorted(buckets.values())                       # (وقت الإغلاق، الإغلاق)
    out = {}
    for name, rows in (("1h", [(ts + 3600, c) for ts, c in h1]), ("4h", h4)):
        closes = [c for _, c in rows]
        out[name] = ([t for t, _ in rows], closes, R.ema(closes))
    return out


def side(p, frame, t):
    times, closes, e = p[frame]
    i = bisect.bisect_right(times, t) - 1          # آخر شمعةٍ وقتُ إغلاقها ≤ t
    if i < 20:
        return None
    return 1 if closes[i] > e[i] else -1 if closes[i] < e[i] else 0


PACKS = {name: pack(sym) for name, sym in REFS.items()}
START = max(R.START, *(p["4h"][0][20] for p in PACKS.values()))   # كلّ المراجع لها حقيقة


def pack_ctrader(symbol):
    """الذهب من تاريخ سي‑تريدر نفسه (الساعة والأربع ساعات) — وقت الإغلاق = البداية + الطول."""
    out = {}
    for name, period, seconds in (("1h", "H1", 3600), ("4h", "H4", 14400)):
        rows = [(float(t) + seconds, float(c)) for t, c in R.db.execute(
            "select period_start, close from candles_history where symbol=? and period=? and period_start>=? "
            "order by period_start", (symbol, period, int(R.START - 300 * 86400)))]
        closes = [c for _, c in rows]
        out[name] = ([t for t, _ in rows], closes, R.ema(closes))
    return out


if len(sys.argv) > 1 and sys.argv[1] == "gold":
    REFS = {"الذهب": "XAUUSD"}
    PACKS = {"الذهب": pack_ctrader("XAUUSD")}


def macro_ok(name, t, d):
    s1, s4 = side(PACKS[name], "1h", t), side(PACKS[name], "4h", t)
    if s1 is None or s4 is None:
        return False
    return s1 == -d and s4 == -d


def run(ref=None):
    trades, busy = [], 0.0
    for j in range(1, len(R.m5)):
        t_close = R.m5[j][0] + 300
        if t_close < START or t_close < busy:
            continue
        idd = R.closed_index(R.td1, 86400, t_close)
        peers = {sym: (_peer(h1, 3600, t_close), _peer(h4, 14400, t_close)) for sym, (h1, h4) in V.REF.items()}
        card = CT.evaluate(at=t_close, close=R.m5[j][4], prev_close=R.m5[j - 1][4],
                           trend_1h=S.fact_trend(R.h1, R.e_h1, R.th1, 3600, t_close),
                           trend_4h=S.fact_trend(R.h4, R.e_h4, R.th4, 14400, t_close),
                           atr_5m=R.a5[j], atr_1d=R.ad1[idd] if idd >= 0 else None,
                           ladder=S.ladder_at(t_close, S.frames), window=owner_window(t_close),
                           news_blocked=R.news_block(t_close), peers=peers)
        if card["status"] != CT.OPEN:
            continue
        buy = card["side"] == CT.BUY
        if ref and not macro_ok(ref, t_close, 1 if buy else -1):
            continue
        k1 = bisect.bisect_right(R.t1, t_close - 60)
        r, exit_t = R.thirds(card["entry"], card["stop"], card["target"], buy, k1)
        if r is None:
            break
        trades.append((t_close, r, card["window"], buy, card["risk"] / card["entry"] * 1e4))
        busy = exit_t + 60
    return trades


def _peer(p, seconds, t):
    rows, e, times = p
    i = R.closed_index(times, seconds, t)
    return None if i < 20 else {"close": rows[i][4], "ema_slow_value": e[i]}


if __name__ == "__main__":
    split = R.START + 0.7 * (R.END - R.START)          # الحدّ نفسه الذي اختير به العيار
    out = {"بداية": START}
    for name in (None, *REFS):
        tr = run(name)
        key = name or "أساس_معتمد"
        out[key] = {"كلّه": R.stats(tr), "تعلّم": R.stats([x for x in tr if x[0] < split]),
                    "اختبار": R.stats([x for x in tr if x[0] >= split]),
                    "لندن": R.stats([x for x in tr if x[2] == "london_peak"]),
                    "نيويورك": R.stats([x for x in tr if x[2] == "ny_open"])}
        s = out[key]
        print("%-12s | كلّه n=%s R=%s R/ص=%s معامل=%s سحب=%s أنصاف=%s | تعلّم R/ص=%s | اختبار n=%s R/ص=%s معامل=%s" % (
            key, s["كلّه"].get("n"), s["كلّه"].get("R"), s["كلّه"].get("R/صفقة"), s["كلّه"].get("معامل"),
            s["كلّه"].get("سحب_R"), s["كلّه"].get("أنصاف"), s["تعلّم"].get("R/صفقة"), s["اختبار"].get("n"),
            s["اختبار"].get("R/صفقة"), s["اختبار"].get("معامل")), flush=True)
    json.dump(out, open("card_macro_%s.json" % ("gold" if "الذهب" in REFS else "yahoo"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
