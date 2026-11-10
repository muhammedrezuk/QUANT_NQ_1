# -*- coding: utf-8 -*-
"""توقيت التقويم شتاءً وصيفًا (الوظائف غير الزراعيّة 08:30 نيويورك · قرار الفائدة 14:00 نيويورك) — قراءة فقط."""
import sys
sys.dont_write_bytecode = True
sys.stdout.reconfigure(encoding="utf-8")
import sqlite3
from collections import Counter
from datetime import datetime, timezone

CAL = "file:C:/Users/NQ/AppData/Roaming/MetaQuotes/Terminal/Common/Files/nq_calendar_history.db?mode=ro"
cal = sqlite3.connect(CAL, uri=True)
for nm in ("قوائم الرواتب غير الزراعية", "قرار سعر فائدة بنك الإحتياطي الفيدرالي", "مطالبات البطالة الأولية"):
    rows = cal.execute("select time_server from calendar_history where country_code='US' and event_name=? order by time_server", (nm,)).fetchall()
    c = Counter()
    for (t,) in rows:
        d = datetime.fromtimestamp(t, timezone.utc)
        c[(d.year, "شتاء" if d.month in (1, 2, 12) else "صيف" if d.month in (6, 7, 8) else "انتقال", d.strftime("%H:%M"))] += 1
    print(nm, len(rows))
    for k, v in sorted(c.items()):
        if k[1] != "انتقال":
            print("   ", k, v)
