# -*- coding: utf-8 -*-
"""فحص سلامة بالعين: أحداثٌ حول لحظاتٍ من سجلّ المالك، وتفصيل حدثين عشوائيّين بشموعهما (لا نتائج صفقات)."""
import sys
sys.dont_write_bytecode = True
sys.stdout.reconfigure(encoding="utf-8")
import os, calendar, bisect, random
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import oc2_core as C

S = C.swing_tables()
for (y, mo, d, hh, mm, side, px, off) in [(2026, 6, 10, 5, 47, "شراء", 28915.45, 45), (2026, 3, 18, 14, 27, "شراء", 24619.39, 0)]:
    t = calendar.timegm((y, mo, d, hh, mm, 0))
    print("==", C.fmt(t), side, "سعرنا", px - off, "جهة الساعة (هـ1، هـ2):", C.hour_dirs(t))
    sp = [{"id": "x", "D": t - 3 * 3600, "X": t + 3600, "C_D": px - off}]
    ev, tl = C.build_events(sp)
    for e in ev["x"]:
        print("   ", C.fmt(e[0]), "شراء" if e[1] else "بيع", "S%d" % e[2], "دخول=%.2f وقف=%.2f خطر=%.1f هدف=%s" % (e[3], e[4], e[5], e[6]),
              "عمق=%.1f مدّة=%ds اندفاع=%.2f أعضاء=%s حجب=%s خطّ=%.2f %s" % (e[12], e[13], e[14], (e[15], e[16]), (e[17], e[18]), e[21], e[11]))
    print("   ", tl)

random.seed(7)
for typ in ("S1", "S2"):
    lst = C.CAND[(typ, True)]
    for c in random.sample(lst, 2):
        print("==", typ, "شراء", C.fmt(c[0]), "خطّ", c[3], "k0/kt", C.fmt(C.MT[c[4]]), "k", C.fmt(C.MT[c[5]]), "ext", c[6], c[7:10])
        sw = S["L" if typ == "S1" else "H"]
        j = c[2]
        print("   القمّة/القاع: بدء شمعة الربع", C.fmt(sw["start"][j]), "تأكيد", C.fmt(sw["conf"][j]), "سعر", sw["px"][j],
              "الطرف الآخر لشمعة الخمس", sw["other"][j], "أُخذ", C.fmt(sw["takeT"][j]) if sw["takeT"][j] < 1e18 else "-")
        if typ == "S2":
            print("   الكسر", C.fmt(c[10]), "السقوط", C.fmt(c[11]) if c[11] < 1e18 else "-")
        for kk in range(c[4] - 2, c[5] + 2):
            print("     ", C.fmt(C.MT[kk]), C.MO[kk], C.MH[kk], C.ML[kk], C.MC[kk])
