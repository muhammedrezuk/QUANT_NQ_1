# -*- coding: utf-8 -*-
"""فحص فرز الشهريّ من السنويّ: الحالات التي خالف فيها الاستمرارُ الحجمَ — هل الاستمرار محقّ؟"""
import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, r"C:\Users\NQ\QUANT_NQ\backtest\news_surprise_2026-10-09")
import events as E
from collections import defaultdict

rows = E.load_rows()
by = defaultdict(lambda: defaultdict(list))
for nm, at, a, c, p, src, rid in rows:
    if E.COMP[nm][2]:
        by[nm][at].append((E.parse(a), E.parse(c), E.parse(p), a, c, p))
series, diag = E.classify(rows)
chosen = {(nm, r[0]): r for nm, res in series.items() for r in res}
for nm, slots in by.items():
    prev = None
    for at in sorted(slots):
        cand = slots[at]
        if len(cand) >= 2:
            mag = lambda r: abs(r[0] or 0) + abs(r[2] or 0)
            by_mag = cand[0] if mag(cand[0]) <= mag(cand[1]) else cand[1]
            ch = chosen.get((nm, at))
            if ch is not None and (ch[1], ch[2], ch[3]) != by_mag[:3]:
                print(nm, E.fmt(at), "الأزواج:", [(x[3], x[4], x[5]) for x in cand], "⟸ الشهريّ المختار:", ch[6], ch[7],
                      "| السابق:", prev)
            if ch is not None:
                prev = (ch[6], ch[7])
