# -*- coding: utf-8 -*-
"""المرحلة 1: الأساس + الجلسات + الأحداث (مخزَّنة). لا نتائج صفقات هنا."""
import sys
sys.dont_write_bytecode = True
sys.stdout.reconfigure(encoding="utf-8")
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import oc_core as C

C.log("البداية %s · الحدّ %s · النهاية %s · أنصاف الاختبار %s" % (C.fmt(C.START), C.fmt(C.SPLIT), C.fmt(C.END),
                                                                   C.TEST_HALVES))
for kind in ("lon", "ny", "his"):
    sess, tally = C.cached("sess_%s.pkl" % kind, lambda: C.session_days(kind))
    C.log(kind, "جلسات", len(sess), tally)
    if kind == "his":
        continue
    for track in ("نقاط", "نسبيّ"):
        name = "ev_%s_%s_base.pkl" % (kind, "pts" if track == "نقاط" else "rel")
        evmap, et = C.cached(name, lambda: C.build_events(sess, None, track))
        C.log(kind, track, "أحداث", sum(len(v) for v in evmap.values()), et)
