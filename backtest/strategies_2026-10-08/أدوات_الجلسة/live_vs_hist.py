# -*- coding: utf-8 -*-
"""شموع الخمس دقائق من تِكّات سي‑تريدر الحيّة المخزّنة مقابل شموع التاريخ — قراءة فقط."""
import calendar
import json
import sqlite3
import time
from datetime import datetime, timezone

LIVE = sqlite3.connect("file:C:/Users/NQ/QUANT_NQ/forex_runtime/var/store/market_data.db?mode=ro", uri=True)
HIST = sqlite3.connect("file:C:/Users/NQ/QUANT_NQ/forex_runtime/var/history/ctrader_history.db?mode=ro", uri=True)
A = calendar.timegm(time.strptime("2026-10-08 07:30", "%Y-%m-%d %H:%M"))
B = calendar.timegm(time.strptime("2026-10-08 09:20", "%Y-%m-%d %H:%M"))


def first_id_at(t):
    lo, hi = 1, LIVE.execute("select max(id) from market_data").fetchone()[0]
    while lo < hi:
        mid = (lo + hi) // 2
        row = LIVE.execute("select occurred_at from market_data where id>=? order by id limit 1", (mid,)).fetchone()
        if row is None or row[0] >= t:
            hi = mid
        else:
            lo = mid + 1
    return lo


i0, i1 = first_id_at(A - 60), first_id_at(B + 60)
rows = LIVE.execute("select occurred_at, bid, ask, payload_json from market_data where id between ? and ? "
                    "and symbol='USTEC' and provider='CTRADER' order by id", (i0, i1)).fetchall()
print("تِكّات الناسداك الحيّة:", len(rows))
sample = json.loads(rows[len(rows) // 2][3])
print("حقول التِّكّة:", sorted(sample.keys()))
bars = {}
for t, bid, ask, _ in rows:
    k = int(t // 300) * 300
    mid = (bid + ask) / 2
    b = bars.setdefault(k, {"o_bid": bid, "h_bid": bid, "l_bid": bid, "c_bid": bid, "c_mid": mid, "n": 0})
    b["h_bid"] = max(b["h_bid"], bid); b["l_bid"] = min(b["l_bid"], bid); b["c_bid"] = bid; b["c_mid"] = mid
    b["n"] += 1
hist = {int(r[0]): r[1:] for r in HIST.execute(
    "select period_start, open, high, low, close from candles_history where symbol='USTEC' and period='M5' "
    "and period_start between ? and ?", (A, B))}
print("البداية(محلّي)  تاريخ[ق ق إ]  حيّ-عرض[ق ق إ]  حيّ-منتصف-إغلاق  عدد")
for k in sorted(set(bars) | set(hist)):
    if k < A or k > B:
        continue
    loc = datetime.fromtimestamp(k + 3 * 3600, timezone.utc).strftime("%H:%M")
    h = hist.get(k); b = bars.get(k)
    hs = "%.1f %.1f %.1f" % (h[1], h[2], h[3]) if h else "—"
    bs = "%.1f %.1f %.1f" % (b["h_bid"], b["l_bid"], b["c_bid"]) if b else "—"
    print("%s  [%s]  [%s]  %s  %s" % (loc, hs, bs, "%.2f" % b["c_mid"] if b else "—", b["n"] if b else 0))
