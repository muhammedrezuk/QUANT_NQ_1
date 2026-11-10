# -*- coding: utf-8 -*-
"""استكشاف ٢: عيّنات الأحداث الكبرى (الشهريّ/السنويّ واللاحقة #2) وأوقاتها بغرينتش (قراءة فقط)."""
import sqlite3
import sys
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

sys.stdout.reconfigure(encoding="utf-8")
NY = ZoneInfo("America/New_York")
BR = "file:C:/Users/NQ/AppData/Roaming/MetaQuotes/Terminal/Common/Files/nq_brain.db?mode=ro"
con = sqlite3.connect(BR, uri=True, timeout=5)
NAMES = ["CPI", "Core CPI", "Nonfarm Payrolls", "Unemployment Rate", "Initial Jobless Claims", "Retail Sales",
         "Core Retail Sales", "PPI", "Core PPI", "GDP", "Core PCE Price Index", "Core PCE Prices", "ISM Manufacturing PMI",
         "ISM Non-Manufacturing PMI", "Fed Interest Rate Decision", "PCE price index", "PCE Price index"]
for nm in NAMES:
    rows = con.execute("select id, event_date, time_et, scheduled_at, actual, consensus, previous, fetched_at from econ_calendar "
                       "where country='United States' and event_name=? order by scheduled_at", (nm,)).fetchall()
    print("==== %s  n=%d" % (nm, len(rows)))
    for r in rows[:6] + [("...",)] + rows[-4:]:
        if r[0] == "...":
            print("   ..."); continue
        at = r[3]
        s = datetime.fromtimestamp(at, timezone.utc).strftime("%Y-%m-%d %H:%M UTC") if at else "None"
        ny = datetime.fromtimestamp(at, NY).strftime("%H:%M NY") if at else ""
        print("   %-60s | %s %s | a=%s c=%s p=%s" % (r[0][:60], s, ny, r[4], r[5], r[6]))
# المكرّرات
print("==== ids with #2 (US)")
for r in con.execute("select event_name, count(*) from econ_calendar where country='United States' and id like '%#%' group by event_name order by 2 desc limit 40"):
    print("  ", r)
# كم صفًّا بلا scheduled_at
print("no time:", con.execute("select count(*) from econ_calendar where country='United States' and scheduled_at is null").fetchone())
# فحص: هل time_et يطابق scheduled_at بنيويورك
bad = 0; tot = 0
for i, d, t, at in con.execute("select id, event_date, time_et, scheduled_at from econ_calendar where country='United States' and scheduled_at is not null"):
    tot += 1
    loc = datetime.fromtimestamp(at, NY)
    if loc.strftime("%Y-%m-%d") != d or loc.strftime("%H:%M") != t:
        bad += 1
        if bad < 5: print("mismatch", i, d, t, loc)
print("time_et vs scheduled_at mismatch: %d / %d" % (bad, tot))
print("progress:", con.execute("select count(*), min(event_date), max(event_date) from econ_calendar_backfill").fetchone())
