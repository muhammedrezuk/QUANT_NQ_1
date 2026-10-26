# -*- coding: utf-8 -*-
"""شكّ: هل «22 من 33 على منطقةٍ لنا» أكثر من الصدفة؟ القرب نفسه لجهته المعاكسة ولدقائق عشوائيّة من أيّامه."""
import sys
sys.dont_write_bytecode = True
sys.stdout.reconfigure(encoding="utf-8")
import os, calendar, random, bisect, json
import importlib.util
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import oc2_core as C

src = open(os.path.join(C.HERE, "oc2_run.py"), encoding="utf-8").read()
start = src.index("def zone_dist(")
end = src.index("selg = {")
ns = {"C": C, "np": C.np, "bisect": bisect, "SW": C.swing_tables()}
exec(src[start:end], ns)
zone_dist = ns["zone_dist"]
OWNER = eval(src[src.index("OWNER = [") + len("OWNER = "):src.index("assert len(OWNER) == 33")])
opp = 0
same = 0
rnd_hit = rnd_n = 0
random.seed(11)
for mo, d, hh, mm, buy, px in OWNER:
    off = 45.0 if mo == 6 else 0.0
    t = calendar.timegm((2026, mo, d, hh, mm, 0))
    ours = px - off
    dz, _ = zone_dist(t, bool(buy), ours)
    same += dz is not None and dz <= 20
    dz, _ = zone_dist(t, not bool(buy), ours)
    opp += dz is not None and dz <= 20
    for _ in range(6):            # دقائق عشوائيّة من يومه نفسه، بسعر إغلاق دقيقتها وجهةٍ عشوائيّة
        tt = calendar.timegm((2026, mo, d, 0, 0, 0)) + random.randrange(1 * 3600, 21 * 3600, 60)
        k = bisect.bisect_right(C.MT, tt - 60) - 1
        dz, _ = zone_dist(tt, random.random() < 0.5, C.MC[k])
        rnd_n += 1
        rnd_hit += dz is not None and dz <= 20
out = {"جهته": "%d من 33" % same, "الجهة_المعاكسة_لصفقاته": "%d من 33" % opp,
       "دقائق_عشوائيّة_من_أيّامه": "%d من %d (%.0f٪)" % (rnd_hit, rnd_n, 100.0 * rnd_hit / rnd_n)}
print(json.dumps(out, ensure_ascii=False))
json.dump(out, open(os.path.join(C.HERE, "zonebase.json"), "w", encoding="utf-8"), ensure_ascii=False)
