# -*- coding: utf-8 -*-
"""فحص بنية قاعدة الشموع (قراءة فقط) — هل فيها حجمٌ أو عدّ تِكّات أو سبريد؟"""
import sqlite3

db = sqlite3.connect("file:C:/Users/NQ/QUANT_NQ/forex_runtime/var/history/ctrader_history.db?mode=ro", uri=True)
for n, s in db.execute("select name, sql from sqlite_master where type in ('table','index')"):
    print(n, "|", s)
for row in db.execute("select symbol, period, count(*), min(period_start), max(period_start) from candles_history "
                      "where symbol in ('USTEC','US500','US30') group by symbol, period"):
    print(row)
cols = [r[1] for r in db.execute("pragma table_info(candles_history)")]
print("أعمدة:", cols)
for c in cols:
    if c in ("volume", "tick_volume", "tick_count", "spread", "real_volume"):
        print(c, db.execute("select count(*), sum(%s>0), max(%s) from candles_history where symbol='USTEC' and period='M5'" % (c, c)).fetchone())
