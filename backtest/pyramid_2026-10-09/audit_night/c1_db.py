# -*- coding: utf-8 -*-
"""فحص 1: وحدة period_start ومحاذاة الأطر وتطابقها مع الدقيقة (هل الطابع بداية الشمعة؟)."""
import sqlite3
from collections import Counter
from datetime import datetime, timezone

db = sqlite3.connect(r"file:C:\Users\NQ\QUANT_NQ\forex_runtime\var\history\ctrader_history.db?mode=ro", uri=True)
print(db.execute("select sql from sqlite_master where name='candles_history'").fetchone()[0])
for p in ("M1", "M5", "M15", "H1", "H4", "D1"):
    r = db.execute("select min(period_start), max(period_start), count(*) from candles_history where symbol='USTEC' and period=?", (p,)).fetchone()
    print(p, datetime.fromtimestamp(r[0], timezone.utc), datetime.fromtimestamp(r[1], timezone.utc), r[2])
# محاذاة الساعات
for p, sec in (("H4", 14400), ("D1", 86400)):
    rows = db.execute("select period_start from candles_history where symbol='USTEC' and period=? and period_start>=1514764800", (p,)).fetchall()
    c = Counter(datetime.fromtimestamp(t, timezone.utc).strftime("%H:%M") for (t,) in rows)
    print(p, "ساعات البداية (غرينتش):", c.most_common(8))

M1 = {t: (o, h, l, c) for t, o, h, l, c in db.execute(
    "select period_start, open, high, low, close from candles_history where symbol='USTEC' and period='M1' and period_start between 1700000000 and 1710000000")}


def agg(ps, sec):
    ks = [t for t in range(int(ps), int(ps + sec), 60) if t in M1]
    if not ks:
        return None
    return (M1[ks[0]][0], max(M1[k][1] for k in ks), min(M1[k][2] for k in ks), M1[ks[-1]][3], len(ks))


for p, sec in (("M5", 300), ("M15", 900), ("H1", 3600), ("H4", 14400), ("D1", 86400)):
    rows = db.execute("select period_start, open, high, low, close from candles_history where symbol='USTEC' and period=? and period_start between 1701000000 and 1709000000 order by period_start", (p,)).fetchall()
    ok_start = ok_shift = n = 0
    diffs = []
    for ps, o, h, l, c in rows[:: max(1, len(rows) // 400)]:
        a = agg(ps, sec)            # بداية = الطابع
        b = agg(ps - sec, sec)      # لو كان الطابع نهاية الشمعة
        if a is None or b is None:
            continue
        n += 1
        ea = abs(a[0] - o) + abs(a[1] - h) + abs(a[2] - l) + abs(a[3] - c)
        eb = abs(b[0] - o) + abs(b[1] - h) + abs(b[2] - l) + abs(b[3] - c)
        ok_start += ea < 1e-6 + 0.5
        ok_shift += eb < 1e-6 + 0.5
        diffs.append(ea)
    diffs.sort()
    print(f"{p}: عيّنة {n} · تطابق بالطابع=بداية {ok_start} · بالطابع=نهاية {ok_shift} · وسيط فرق {diffs[len(diffs)//2] if diffs else None} · أقصى {diffs[-1] if diffs else None}")
