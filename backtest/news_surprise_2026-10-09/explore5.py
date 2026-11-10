# -*- coding: utf-8 -*-
"""استكشاف ٥: شموع الدقيقة حول وظائف آب 2014 وكثافة الدقائق لكلّ سنة (هل بيانات 2014 صالحة؟)."""
import sqlite3
import sys
from datetime import datetime, timezone

sys.stdout.reconfigure(encoding="utf-8")
h = sqlite3.connect("file:C:/Users/NQ/QUANT_NQ/forex_runtime/var/history/ctrader_history.db?mode=ro", uri=True)
for T in (1406896200, 1409920200, 1444393800, 1546605000):   # 2014-08-01 · 2014-09-05 · 2015-10-09 · 2019-01-04 (12:30/13:30 غ)
    print("==", datetime.fromtimestamp(T, timezone.utc))
    for r in h.execute("select period_start, open, high, low, close, tick_volume from candles_history where symbol='USTEC' and period='M1' "
                       "and period_start between ? and ? order by period_start", (T - 300, T + 300)):
        print("   ", datetime.fromtimestamp(r[0], timezone.utc).strftime("%H:%M"), r[1:])
for y in range(2014, 2027):
    a = int(datetime(y, 1, 1, tzinfo=timezone.utc).timestamp()); b = int(datetime(y + 1, 1, 1, tzinfo=timezone.utc).timestamp())
    n = h.execute("select count(*), avg(high-low), avg(tick_volume) from candles_history where symbol='USTEC' and period='M1' and period_start>=? and period_start<?", (a, b)).fetchone()
    print(y, n)
