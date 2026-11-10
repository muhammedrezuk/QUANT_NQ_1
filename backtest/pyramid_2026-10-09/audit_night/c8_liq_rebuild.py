# -*- coding: utf-8 -*-
"""فحص 8: إعادة بناء صفقات «الكسر الكاذب 5د عرض 2 بلا مرشّح» باستقلال، والتحقّق من أنّ high/low في حدث الكنس
هما طرفا الشمعة الكانسة نفسها (لا مستقبليّة) وأنّ الجهة صحيحة."""
import bisect
import json
import sqlite3
import statistics as st
import sys
from collections import defaultdict
from datetime import datetime
from zoneinfo import ZoneInfo

SB = r"C:\Users\NQ\AppData\Local\Temp\claude\C--\500dc279-a556-4c4c-881e-d017738aae39\scratchpad\structure_bench"
sys.path.insert(0, SB)
import eval_structure as E  # noqa: E402

LON, NY = ZoneInfo("Europe/London"), ZoneInfo("America/New_York")
db = sqlite3.connect(r"file:C:\Users\NQ\QUANT_NQ\forex_runtime\var\history\ctrader_history.db?mode=ro", uri=True)
C5 = {t + 300: (h, l, c) for t, h, l, c in db.execute("select period_start, high, low, close from candles_history where symbol='USTEC' and period='M5' and period_start>=1512086400")}

rows = []
bad_hl = bad_side = 0
for line in open(SB + r"\liq\5m_lb2.jsonl", encoding="utf-8"):
    if '"e": "sweep"' not in line:
        continue
    r = json.loads(line)
    if r["t"] < E.START:
        continue
    h, l, c = C5[r["t"]]
    bad_hl += abs(h - r["high"]) > 1e-6 or abs(l - r["low"]) > 1e-6
    if r["direction"] == "buy_side":
        bad_side += not (h >= r["price"])
    else:
        bad_side += not (l <= r["price"])
    rows.append((r, c))
print("أحداث الكنس منذ 2018:", len(rows), "· طرفا الشمعة مخالفان:", bad_hl, "· جهة مخالفة:", bad_side, flush=True)


def wkey(t):
    for name, tz, a, b in (("london", LON, 495, 660), ("ny", NY, 585, 780)):
        lt = datetime.fromtimestamp(t - 1, tz)
        if lt.weekday() < 5 and a <= lt.hour * 60 + lt.minute < b:
            return name + lt.date().isoformat()
    return None


trades, busy, per = [], 0.0, defaultdict(int)
for r, c in sorted(rows, key=lambda x: x[0]["t"]):
    t = r["t"]
    if t < busy:
        continue
    k = wkey(t)
    if k is None or per[k] >= 2:
        continue
    high_taken = r["direction"] == "buy_side"
    if not ((c < r["price"]) if high_taken else (c > r["price"])):
        continue
    buy = not high_taken
    stop = r["low"] - 1 if buy else r["high"] + 1
    risk = (c - stop) if buy else (stop - c)
    if not 15 <= risk <= 50:
        continue
    R, stage, tx = E.thirds(c, stop, c + 3 * risk if buy else c - 3 * risk, buy, t)
    if R is None:
        continue
    per[k] += 1
    busy = tx
    trades.append((t, buy, R))
theirs = json.load(open(SB + r"\liq_trades.json", encoding="utf-8"))["5m_lb2_false_break_none"]
same = len({(a, b) for a, b, _ in trades} & {(x["t"], x["buy"]) for x in theirs})
print("عندي", len(trades), "عندهم", len(theirs), "مشترك", same,
      "· R تعلّم", round(st.mean(x[2] for x in trades if x[0] < E.SPLIT), 4),
      "· R اختبار", round(st.mean(x[2] for x in trades if x[0] >= E.SPLIT), 4), flush=True)
