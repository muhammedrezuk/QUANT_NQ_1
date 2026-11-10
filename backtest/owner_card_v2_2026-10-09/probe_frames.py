# -*- coding: utf-8 -*-
"""فحص بنية البيانات وحدها (لا صفقات ولا نتائج): اتّساق الربع ساعة مع الخمس والدقيقة، وعدد القمم/القيعان."""
import sys
sys.dont_write_bytecode = True
sys.stdout.reconfigure(encoding="utf-8")
import sqlite3, bisect
import numpy as np

DB = "file:C:/Users/NQ/QUANT_NQ/forex_runtime/var/history/ctrader_history.db?mode=ro"
db = sqlite3.connect(DB, uri=True)


def rows(p):
    return np.array(db.execute("select period_start, open, high, low, close from candles_history where symbol='USTEC' and period=? order by period_start", (p,)).fetchall(), dtype=float)


m15 = rows("M15"); m5 = rows("M5"); m1 = rows("M1")
print("M15", len(m15), "M5", len(m5), "M1", len(m1))
T5 = m5[:, 0]; T1 = m1[:, 0]
bad_h = bad_l = miss = n = 0
gap5 = 0
for i in range(0, len(m15), 7):
    t, o, h, l, c = m15[i]
    a, b = bisect.bisect_left(T5, t), bisect.bisect_left(T5, t + 900)
    if b - a == 0:
        miss += 1
        continue
    if b - a < 3:
        gap5 += 1
    n += 1
    if abs(m5[a:b, 2].max() - h) > 1e-6:
        bad_h += 1
    if abs(m5[a:b, 3].min() - l) > 1e-6:
        bad_l += 1
print("عيّنة M15:", n, "بلا M5:", miss, "أقلّ من 3 شموع M5:", gap5, "قمّة≠أعلى الخمس:", bad_h, "قاع≠أدنى الخمس:", bad_l)
bad_h = bad_l = n = 0
for i in range(0, len(m15), 7):
    t, o, h, l, c = m15[i]
    a, b = bisect.bisect_left(T1, t), bisect.bisect_left(T1, t + 900)
    if b - a == 0:
        continue
    n += 1
    if abs(m1[a:b, 2].max() - h) > 1e-6:
        bad_h += 1
    if abs(m1[a:b, 3].min() - l) > 1e-6:
        bad_l += 1
print("عيّنة M15 مقابل M1:", n, "قمّة≠:", bad_h, "قاع≠:", bad_l)
# عدد القمم/القيعان على الربع ساعة (look=2)
H, L = m15[:, 2], m15[:, 3]
nh = nl = 0
for i in range(2, len(m15) - 2):
    w = H[i - 2:i + 3]
    if H[i] == w.max() and (w < H[i]).sum() == 4:
        nh += 1
    w = L[i - 2:i + 3]
    if L[i] == w.min() and (w > L[i]).sum() == 4:
        nl += 1
print("قمم الربع ساعة:", nh, "قيعانه:", nl)
