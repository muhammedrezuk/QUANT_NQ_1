# -*- coding: utf-8 -*-
"""فحص امتداد البيانات — قراءة فقط."""
import sys, sqlite3
from datetime import datetime, timezone
sys.stdout.reconfigure(encoding="utf-8")
DB = "file:C:/Users/NQ/QUANT_NQ/forex_runtime/var/history/ctrader_history.db?mode=ro"
db = sqlite3.connect(DB, uri=True)
f = lambda t: datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%d %H:%M") if t else None
print([r for r in db.execute("select name from sqlite_master where type='table'")])
print([r for r in db.execute("pragma table_info(candles_history)")])
for (p,) in db.execute("select distinct period from candles_history where symbol='USTEC'"):
    a, b, n = db.execute("select min(period_start), max(period_start), count(*) from candles_history where symbol='USTEC' and period=?", (p,)).fetchone()
    print(p, f(a), f(b), n)
# فجوات M1 سنويّة
for y in range(2010, 2027):
    a = datetime(y, 1, 1, tzinfo=timezone.utc).timestamp(); b = datetime(y + 1, 1, 1, tzinfo=timezone.utc).timestamp()
    n = db.execute("select count(*) from candles_history where symbol='USTEC' and period='M1' and period_start>=? and period_start<?", (a, b)).fetchone()[0]
    if n:
        print("M1", y, n)
print([r for r in db.execute("select distinct symbol from candles_history")])
