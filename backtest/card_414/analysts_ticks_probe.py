# -*- coding: utf-8 -*-
"""مدى تاريخ التِّكّات (عرض/طلب) في القاعدة — من جدول التقدّم وحده (قراءة فقط)."""
import sqlite3
from datetime import datetime, timezone

db = sqlite3.connect("file:C:/Users/NQ/QUANT_NQ/forex_runtime/var/history/ctrader_history.db?mode=ro", uri=True)
for sym, side, old, new, req, note in db.execute(
        "select symbol, side, oldest_ms, newest_ms, requests, note from tick_progress order by symbol, side"):
    f = lambda ms: datetime.fromtimestamp(ms / 1000, timezone.utc).strftime("%Y-%m-%d") if ms else None
    print(sym, side, f(old), f(new), req, note)
