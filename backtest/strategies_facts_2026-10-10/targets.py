# -*- coding: utf-8 -*-
"""كم صفقة بلغت الهدف الأوّل/الثاني/الثالث وكم R — سؤال المالك ١٠-١٠. يقرأ trades_USTEC.json."""
import json
import pathlib
from collections import defaultdict

D = pathlib.Path(__file__).resolve().parent
tr = json.loads((D / "trades_USTEC.json").read_text(encoding="utf-8"))
names = {"404": "الاتّجاه", "405": "الانعكاس", "406": "الاختراق", "407": "الارتداد", "408": "الزخم", "409": "المدى",
         "410": "السيولة"}


def row(ts):
    n = len(ts)
    st = defaultdict(int)
    for t in ts:
        st[t["stage"]] += 1
    return (n, st[0], st[1], st[2], st[3], round(sum(t["R"] for t in ts), 1), round(sum(t["pts"] for t in ts)))


# 409 تتكرّر نفسها على الأطر الأربعة (كفاءة 165 بنافذة 1600) — تُعدّ مرّةً واحدة (إطار 5m) في المجاميع.
tr = [t for t in tr if t["strategy"] != "409" or t["frame"] == "5m"]
print("الكلّ", row(tr))
g = defaultdict(list)
for t in tr:
    g[(t["strategy"], t["frame"], t["session"])].append(t)
for k, ts in sorted(g.items()):
    print(k[0], names[k[0]], k[1], k[2], row(ts))
s = defaultdict(list)
for t in tr:
    s[t["strategy"]].append(t)
for k, ts in sorted(s.items()):
    print("مجموع", k, names[k], row(ts))
