# -*- coding: utf-8 -*-
"""استكشاف جدول econ_calendar (قراءة فقط): الأسماء الأمريكيّة الكبرى، تغطيتها، وأوقاتها."""
import sqlite3
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone

sys.stdout.reconfigure(encoding="utf-8")
BR = "file:C:/Users/NQ/AppData/Roaming/MetaQuotes/Terminal/Common/Files/nq_brain.db?mode=ro"
con = sqlite3.connect(BR, uri=True, timeout=5)
print(con.execute("select sql from sqlite_master where name='econ_calendar'").fetchone()[0])
print("rows", con.execute("select count(*), min(event_date), max(event_date) from econ_calendar").fetchone())
print("countries", con.execute("select country, count(*) from econ_calendar group by country order by 2 desc limit 15").fetchall())
rows = con.execute("select event_name, count(*), sum(consensus<>'' and consensus is not null), sum(actual<>'' and actual is not null), "
                   "min(event_date), max(event_date), group_concat(distinct time_et) from econ_calendar "
                   "where country='United States' group by event_name order by 2 desc").fetchall()
print("US names:", len(rows))
for r in rows:
    if r[2] and r[2] >= 5:
        print("%-55s n=%-4d cons=%-4d act=%-4d %s..%s  t=%s" % (r[0][:55], r[1], r[2], r[3], r[4], r[5], (r[6] or "")[:40]))
