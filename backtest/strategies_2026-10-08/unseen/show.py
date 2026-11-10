# -*- coding: utf-8 -*-
"""عرض مختصر لنتائج الفترة — قراءة فقط."""
import sys
sys.dont_write_bytecode = True
sys.stdout.reconfigure(encoding="utf-8")
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
RES = json.load(open(os.path.join(HERE, sys.argv[1] if len(sys.argv) > 1 else "results.json"), encoding="utf-8"))
print(RES["الفترة"], RES["بيانات"])


def show(name, s):
    a = s["كلّه"]
    print("\n■ %s: n=%s R=%s R/ص=%s معامل=%s سحب=%s فوز=%s ص/يوم=%s أنصاف+=%s يثبت=%s %s" % (
        name, a.get("n"), a.get("R"), a.get("R/صفقة"), a.get("معامل"), a.get("سحب_R"), a.get("فوز%"),
        s.get("صفقات/يوم"), s.get("أنصاف_موجبة"), s.get("يثبت"),
        ("من الأخرى %s" % s["من_الأخرى"]) if "من_الأخرى" in s else ""))
    print("   أنصاف:", " · ".join("%s:%+.1f(%d)" % (k[:7], v["R"], v["n"]) for k, v in s.get("أنصاف_عشرة", {}).items()))
    print("   سنويًّا:", " · ".join("%s:%+.1f/%d" % (y, v.get("R", 0), v.get("n", 0)) for y, v in s.get("سنويًّا", {}).items()))
    print("   لندن:", s.get("لندن"), "| نيويورك:", s.get("نيويورك"))
    print("   شراء:", s.get("شراء"), "| بيع:", s.get("بيع"))


for k, s in RES["استراتيجيّات"].items():
    show(k, s)
for sec in ("414_صيغتا_الارتباط",):
    if sec in RES:
        for k, s in RES[sec].items():
            if isinstance(s, dict):
                show("414 " + k, s)
for sec in ("دمج", "دمج_بالصيغة_أ_للعلم"):
    for k, s in RES.get(sec, {}).items():
        show(k, s)
print("\nعدّادات:", json.dumps(RES.get("عدّادات"), ensure_ascii=False))
