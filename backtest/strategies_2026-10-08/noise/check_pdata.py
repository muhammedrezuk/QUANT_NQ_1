# -*- coding: utf-8 -*-
"""تحقّق آليّ: نسختي pdata (بلا ضبط الفترة) = الأصل card_replay حرفًا بحرف — شموعًا ومؤشّراتٍ وإدارة."""
import sys

sys.dont_write_bytecode = True
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, r"C:\Users\NQ\QUANT_NQ")
sys.path.insert(0, r"C:\Users\NQ\QUANT_NQ\backtest\card_414")
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import random
import card_replay as R
import pdata as P

ok = {}
ok["START"] = R.START == P.START
ok["END"] = R.END == P.END
ok["m1"] = len(R.m1) == len(P.T1) and all(
    R.m1[i] == (P.T1[i], P.O1[i], P.H1[i], P.L1[i], P.C1[i]) for i in range(len(R.m1)))
# 5 د: الأصل من −30 يومًا ونسختي من −60؛ القسم المشترك متطابق والمؤشّر على آخر 14 فلا يتغيّر
off = P.t5.index(R.t5[0])
ok["m5"] = P.m5[off:off + len(R.m5)] == R.m5 and len(P.m5) - off == len(R.m5)
ok["a5"] = all(abs(P.a5[off + i] - R.a5[i]) < 1e-9 for i in range(14, len(R.a5)))
for name in ("h1", "h4", "d1", "e_h1", "e_h4", "ad1", "sw_htf", "news", "th1", "th4", "td1"):
    ok[name] = getattr(P, name) == getattr(R, name)
# الإدارة: 400 دخولٍ عشوائيّ بالدالّتين
random.seed(7)
same = 0
for _ in range(400):
    k = random.randrange(1000, len(R.m1) - 5000)
    e = R.m1[k][4]; buy = random.random() < 0.5
    risk = random.uniform(10, 80); sgn = 1 if buy else -1
    st, tg = e - sgn * risk, e + sgn * risk * random.uniform(3, 6)
    same += R.thirds(e, st, tg, buy, k) == P.thirds(e, st, tg, buy, k)
ok["thirds_400"] = same == 400
print(ok)
print("كلّها متطابقة" if all(ok.values()) else "اختلاف!")
