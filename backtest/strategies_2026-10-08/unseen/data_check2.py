# -*- coding: utf-8 -*-
"""فحص اكتمال البيانات شهرًا بشهر ومحاذاة الأيّام والأربع ساعات وتوقيت التقويم — قراءة فقط."""
import sys
sys.dont_write_bytecode = True
sys.stdout.reconfigure(encoding="utf-8")
import sqlite3
import calendar
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone

DB = "file:C:/Users/NQ/QUANT_NQ/forex_runtime/var/history/ctrader_history.db?mode=ro"
CAL = "file:C:/Users/NQ/AppData/Roaming/MetaQuotes/Terminal/Common/Files/nq_calendar_history.db?mode=ro"
ts = lambda s: calendar.timegm(time.strptime(s, "%Y-%m-%d"))
f = lambda t: datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%d %H:%M")
A, B = ts("2019-09-01"), ts("2026-10-06")
db = sqlite3.connect(DB, uri=True)


def times(sym, per):
    return [r[0] for r in db.execute("select period_start from candles_history where symbol=? and period=? and period_start>=? and period_start<? order by period_start",
                                     (sym, per, A - 400 * 86400, B))]


# اكتمال شهريّ: عدد شموع الدقيقة و5 د للناسداك
for per, step in (("M1", 60), ("M5", 300)):
    tt = times("USTEC", per)
    mon = Counter(datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m") for t in tt if t >= A)
    print("USTEC %s شهريًّا:" % per, " ".join("%s:%d" % (k, v) for k, v in sorted(mon.items())), flush=True)
    gaps = [(tt[i - 1], tt[i]) for i in range(1, len(tt)) if tt[i] >= A and tt[i] - tt[i - 1] > 3.2 * 86400]
    print("  فجوات > 3.2 يوم:", [(f(a), f(b), round((b - a) / 86400, 1)) for a, b in gaps], flush=True)
    # فجوات داخل أيّام العمل في نوافذ المالك (> 30 د)
    big = [(tt[i - 1], tt[i]) for i in range(1, len(tt)) if tt[i] >= A and 1800 < tt[i] - tt[i - 1] < 2 * 86400
           and datetime.fromtimestamp(tt[i - 1], timezone.utc).weekday() < 5
           and 7 <= datetime.fromtimestamp(tt[i - 1], timezone.utc).hour < 17]
    print("  فجوات 30د–2يوم في 07–17 غرينتش أيّام العمل: %d" % len(big), [(f(a), round((b - a) / 60)) for a, b in big[:40]], flush=True)

# محاذاة بداية شموع اليوم والأربع ساعات سنويًّا
for sym in ("USTEC", "US500", "US30"):
    for per in ("D1", "H4"):
        tt = times(sym, per)
        by = defaultdict(Counter)
        for t in tt:
            d = datetime.fromtimestamp(t, timezone.utc)
            by[d.year][d.hour] += 1
        print("%s %s ساعات البداية سنويًّا:" % (sym, per), {y: dict(c) for y, c in sorted(by.items())}, flush=True)
    for per, step in (("H1", 3600), ("H4", 14400), ("M5", 300)):
        tt = times(sym, per)
        mon = Counter(datetime.fromtimestamp(t, timezone.utc).strftime("%Y") for t in tt if t >= A)
        gaps = [(tt[i - 1], tt[i]) for i in range(1, len(tt)) if tt[i] >= A and tt[i] - tt[i - 1] > 3.2 * 86400]
        print("%s %s سنويًّا: %s · فجوات>3.2يوم: %s" % (sym, per, dict(sorted(mon.items())), [(f(a), f(b)) for a, b in gaps]), flush=True)

# توقيت التقويم: الوظائف غير الزراعيّة (08:30 نيويورك) وقرار الفائدة (14:00 نيويورك) — شتاءً وصيفًا
cal = sqlite3.connect(CAL, uri=True)
for name_like in ("%Nonfarm Payrolls%", "%Fed Interest Rate Decision%", "%CPI%"):
    rows = cal.execute("select event_name, time_server from calendar_history where country_code='US' and importance=3 and event_name like ? "
                       "and time_server>=? and time_server<? order by time_server", (name_like, ts("2019-10-01"), ts("2026-10-01"))).fetchall()
    hours = Counter()
    for nm, t in rows:
        d = datetime.fromtimestamp(t, timezone.utc)
        hours[(d.month in (12, 1, 2), d.strftime("%H:%M"))] += 1
    print("تقويم %s n=%d (شتاء؟، ساعة الخادم):" % (name_like, len(rows)), dict(sorted(hours.items())), flush=True)
    for nm, t in rows[:3] + rows[-3:]:
        print("   ", nm, f(t))
print("أسماء أخبار US عالية (عيّنة):", Counter(r[0] for r in cal.execute(
    "select event_name from calendar_history where country_code='US' and importance=3 and time_server>=? and time_server<?",
    (ts("2019-10-01"), ts("2024-10-01")))).most_common(40))
for y in range(2019, 2027):
    for half, (a, b) in (("أ", ("%d-01-01" % y, "%d-07-01" % y)), ("ب", ("%d-07-01" % y, "%d-01-01" % (y + 1)))):
        c = cal.execute("select count(*) from calendar_history where country_code='US' and importance=3 and time_server>=? and time_server<?",
                        (ts(a), ts(b))).fetchone()[0]
        print("  أخبار %d%s: %d" % (y, half, c), end="")
    print()
print("export_meta:", cal.execute("select * from export_meta").fetchall()[:10])
