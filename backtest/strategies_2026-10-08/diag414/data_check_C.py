# -*- coding: utf-8 -*-
"""سلامة بيانات الفترة ج (2014-09 ⟶ 2019-10) — أعداد وفجوات فقط، لا نتائج."""
import sys
sys.dont_write_bytecode = True
sys.stdout.reconfigure(encoding="utf-8")
import sqlite3
from datetime import datetime, timezone

DB = "file:C:/Users/NQ/QUANT_NQ/forex_runtime/var/history/ctrader_history.db?mode=ro"
CAL = "file:C:/Users/NQ/AppData/Roaming/MetaQuotes/Terminal/Common/Files/nq_calendar_history.db?mode=ro"
db = sqlite3.connect(DB, uri=True)
a, b = 1409529600, 1569888000    # 2014-09-01 ⟶ 2019-10-01
f = lambda t: datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%d %H:%M")
for sym, per in (("USTEC", "M1"), ("USTEC", "M5"), ("USTEC", "H1"), ("US500", "H1"), ("US500", "H4"), ("USTEC", "D1")):
    ts = [r[0] for r in db.execute("select period_start from candles_history where symbol=? and period=? and "
                                   "period_start>=? and period_start<? order by period_start", (sym, per, a, b))]
    yrs = {}
    for t in ts:
        y = datetime.fromtimestamp(t, timezone.utc).year
        yrs[y] = yrs.get(y, 0) + 1
    big = [(f(x), round((y - x) / 86400, 1)) for x, y in zip(ts, ts[1:]) if y - x > 3.2 * 86400]
    mid = []
    for x, y in zip(ts, ts[1:]):
        d = datetime.fromtimestamp(x, timezone.utc)
        if 1800 < y - x <= 2 * 86400 and d.weekday() < 5 and 7 <= d.hour < 17:
            mid.append((f(x), int((y - x) / 60)))
    print("%s %s n=%d سنويًّا=%s فجوات>3.2يوم=%s فجوات 30د–2يوم (07–17 غرينتش)=%d %s" % (
        sym, per, len(ts), yrs, big, len(mid), mid[:12] if per in ("M1", "M5") else ""))
cal = sqlite3.connect(CAL, uri=True)
news = [t for (t,) in cal.execute("select time_server from calendar_history where country_code='US' and importance=3")]
yrs = {}
for t in news:
    y = datetime.fromtimestamp(t - 10800, timezone.utc).year
    yrs[y] = yrs.get(y, 0) + 1
print("أخبار US عالية سنويًّا:", dict(sorted(yrs.items())))
