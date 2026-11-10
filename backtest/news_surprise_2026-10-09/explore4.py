# -*- coding: utf-8 -*-
"""استكشاف ٤: أسماء الأحداث في قاعدة القياس القديمة (ما جُلب حتّى الآن) وعيّناتها."""
import sqlite3
import sys

sys.stdout.reconfigure(encoding="utf-8")
con = sqlite3.connect("file:C:/Users/NQ/QUANT_NQ/backtest/news_surprise_2026-10-09/news_old.db?mode=ro", uri=True, timeout=10)
print("fetched:", con.execute("select count(*), min(event_date), max(event_date), sum(n_us) from fetched").fetchone())
pat = ["%CPI%", "%Payroll%", "%Unemployment Rate%", "%Jobless%", "%Retail Sales%", "%PPI%", "GDP%", "%PCE%", "ISM%", "%Interest Rate%"]
for p in pat:
    rows = con.execute("select event_name, count(*), sum(consensus<>''), group_concat(distinct time_et) from econ where event_name like ? group by event_name order by 2 desc", (p,)).fetchall()
    for r in rows:
        print("%-50s n=%-4d cons=%-4d t=%s" % (r[0][:50], r[1], r[2], (r[3] or "")[:50]))
for nm in ("CPI", "Core CPI", "Retail Sales", "ISM Non-Manufacturing PMI", "Nonfarm Payrolls", "Fed Interest Rate Decision"):
    print("==", nm)
    for r in con.execute("select id, scheduled_at, actual, consensus, previous from econ where event_name=? order by scheduled_at limit 6", (nm,)):
        print("   ", r)
