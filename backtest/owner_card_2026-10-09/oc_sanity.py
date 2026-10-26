# -*- coding: utf-8 -*-
"""فحص سلامة: المناطق والأحداث حول لحظاتٍ من سجلّ المالك (لا نتائج صفقات)."""
import sys
sys.dont_write_bytecode = True
sys.stdout.reconfigure(encoding="utf-8")
import os, calendar, bisect
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import oc_core as C

P = C.BASEP
for (y, mo, d, hh, mm, side, px, off) in [(2026, 6, 10, 5, 47, "شراء", 28915.45, 45), (2026, 3, 18, 14, 27, "شراء", 24619.39, 0),
                                           (2026, 6, 1, 14, 16, "شراء", 30346.45, 45), (2026, 3, 13, 10, 33, "شراء", 24564.32, 0)]:
    t = calendar.timegm((y, mo, d, hh, mm, 0))
    hb = t - t % 3600
    print("==", C.fmt(t), side, px, "⟵ عندنا", px - off)
    for buy in (True, False):
        z = C.zones_at(hb, buy, P["tol"], P["ndays"], P["wmin"])
        print("  مناطق", "دعم(شراء)" if buy else "مقاومة(بيع)", [(round(a, 1), round(b, 1), C.fmt(C.TH1[i])) for a, b, i in z])
    k = bisect.bisect_left(C.MT, t)
    for kk in range(k - 3, k + 2):
        print("   ", C.fmt(C.MT[kk]), C.MO[kk], C.MH[kk], C.ML[kk], C.MC[kk])
    sp = [{"id": "x", "D": t - 3600, "X": t + 1800, "C_D": px - off}]
    ev, tl = C.build_events(sp)
    for e in ev["x"]:
        print("   حدث", C.fmt(e[0]), "شراء" if e[1] else "بيع", "صفعة" if e[2] else "", "اختناق" if e[3] else "",
              "نسبة=%.2f" % e[4], "دخول=%.2f وقف=%.2f خطر=%.1f هدف=%s صافي=%s منطقة=%.1f–%.1f %s" % (
                  e[5], e[6], e[7], e[8], None if e[9] is None else round(e[9], 2), e[11], e[12], e[13]))
    print("  ", tl)
