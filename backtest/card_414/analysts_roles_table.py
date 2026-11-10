# -*- coding: utf-8 -*-
"""جدولٌ مختصر من analysts_roles.json (لا قياس جديد)."""
import json

d = json.load(open("analysts_roles.json", encoding="utf-8"))
chosen = {(r["الرقم"], r["العيار_المختار_على_التعلّم"]) for r in d["أحكام"]}
for r in d["اختبارات"]:
    a, l, t = r["كلّه"], r["تعلّم"], r["اختبار"]
    h = a.get("أنصاف", {})
    print("|%s %s|%s|%s|%.2f|%s|%s|%s|%s|%s|%s|%s|%s|%s|%s|" % (
        r["الرقم"], r["المحلّل"], r["الدور"], r["العيار"], r["نسبة_السماح_من_لحظات_البطاقة"], a["n"], a.get("R"),
        a.get("R/صفقة"), " ".join("%+.1f" % v for v in h.values()), "%d/5" % sum(v > 0 for v in h.values()),
        l.get("R/صفقة"), t.get("R/صفقة"), t.get("معامل"), a.get("سحب_R"),
        ("مختار" if (r["الرقم"], r["العيار"]) in chosen else "") + (" يجتاز" if r["يجتاز"] else "")))
