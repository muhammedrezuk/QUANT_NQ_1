# -*- coding: utf-8 -*-
"""المرحلة 1: القمم/القيعان والمرشّحون والجلسات والأحداث (مخزَّنة). لا نتائج صفقات هنا."""
import sys
sys.dont_write_bytecode = True
sys.stdout.reconfigure(encoding="utf-8")
import os
from collections import Counter
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import oc2_core as C

C.log("البداية %s · الحدّ %s · النهاية %s · أنصاف الاختبار %s" % (C.fmt(C.START), C.fmt(C.SPLIT), C.fmt(C.END),
                                                                   C.TEST_HALVES))
C.swing_tables()
CAND = C.candidates()
C.log("قيعان/قمم الربع ساعة بتأكيدٍ بعد أخذها (تُركت):", C.BADCONF[0])
for buy in (True, False):
    C.log("شراء" if buy else "بيع", "S1", len(CAND[("S1", buy)]), "S2", len(CAND[("S2", buy)]), CAND[("S2tally", buy)])
for kind in ("lon", "ny"):
    ss = C.cached("sess2_%s.pkl" % kind, lambda: C.load_sessions(kind))
    cnt = Counter((s["dir"]["هـ1"], s["dir"]["هـ2"]) for s in ss)
    C.log(kind, "جلسات", len(ss), "توزيع (هـ1، هـ2):", dict(cnt))
    for track, tag in (("نقاط", "pts"), ("نسبيّ", "rel")):
        ev, tl = C.cached("ev2_%s_%s_n5.pkl" % (kind, tag), lambda: C.build_events(ss, track, 5))
        C.log(kind, track, "ن5", "أحداث", sum(len(v) for v in ev.values()), tl)
    for nd in (2, 10):
        ev, tl = C.cached("ev2_%s_pts_n%d.pkl" % (kind, nd), lambda: C.build_events(ss, "نقاط", nd))
        C.log(kind, "نقاط", "ن%d" % nd, "أحداث", sum(len(v) for v in ev.values()), tl)
C.log("تمّ")
