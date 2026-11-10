# -*- coding: utf-8 -*-
"""فحص توفّر البيانات للفترة غير المرئيّة — قراءة فقط."""
import sys
sys.dont_write_bytecode = True
sys.stdout.reconfigure(encoding="utf-8")
import sqlite3
import calendar
import time
from datetime import datetime, timezone

DB = "file:C:/Users/NQ/QUANT_NQ/forex_runtime/var/history/ctrader_history.db?mode=ro"
CAL = "file:C:/Users/NQ/AppData/Roaming/MetaQuotes/Terminal/Common/Files/nq_calendar_history.db?mode=ro"
ts = lambda s: calendar.timegm(time.strptime(s, "%Y-%m-%d"))
f = lambda t: datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%d %H:%M") if t is not None else None
A, B = ts("2019-10-01"), ts("2024-09-30") + 86400

db = sqlite3.connect(DB, uri=True)
print("tables:", [r[0] for r in db.execute("select name from sqlite_master where type='table'")])
print("schema:", db.execute("select sql from sqlite_master where name='candles_history'").fetchone())
print("indexes:", [r[0] for r in db.execute("select sql from sqlite_master where type='index'")])
for sym in ("USTEC", "US500", "US30"):
    for per, warm in (("M1", 1), ("M5", 30), ("H1", 120), ("H4", 300), ("D1", 400)):
        mn, mx, n = db.execute("select min(period_start), max(period_start), count(*) from candles_history "
                               "where symbol=? and period=?", (sym, per)).fetchone()
        nw = db.execute("select count(*), min(period_start) from candles_history where symbol=? and period=? and period_start>=? and period_start<?",
                        (sym, per, A - warm * 86400, B)).fetchone()
        print("%-6s %-3s كلّه: %s → %s n=%s | الفترة+التحمية: n=%s أوّلها=%s" % (sym, per, f(mn), f(mx), n, nw[0], f(nw[1])), flush=True)

cal = sqlite3.connect(CAL, uri=True)
print("cal tables:", [r[0] for r in cal.execute("select name from sqlite_master where type='table'")])
print("cal schema:", cal.execute("select sql from sqlite_master where name='calendar_history'").fetchone())
mn, mx, n = cal.execute("select min(time_server), max(time_server), count(*) from calendar_history where country_code='US' and importance=3").fetchone()
print("أخبار US عالية: %s → %s n=%s" % (f(mn), f(mx), n))
for y in range(2018, 2027):
    a, b = ts("%d-01-01" % y), ts("%d-01-01" % (y + 1))
    c = cal.execute("select count(*) from calendar_history where country_code='US' and importance=3 and time_server>=? and time_server<?", (a, b)).fetchone()[0]
    print("  %d: %d" % (y, c))
