# -*- coding: utf-8 -*-
"""يكتب أرقام adopt_day.json في بيانات الذرّات (أمر المالك «NQ اعتمدهم الأرقام كلّها» ٢٠٢٦-١٠-٠٩ 23:10).
يغيّر سطر المفتاح داخل كتلة config فقط، ولا يرفع رقم النسخة (يُحمَّل بالإقلاع التالي).
الاستعمال: python write_adopt.py 3      ⟵ الذرّات التي يبدأ رقمها بـ3
"""
import json
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import calib_day as C  # noqa: E402

prefix = sys.argv[1]
source = sys.argv[2] if len(sys.argv) > 2 else "adopt_day.json"     # adopt_month.json لاعتماد الشهر
cat = C.catalog()
for o in json.loads((pathlib.Path(__file__).resolve().parent / source).read_text(encoding="utf-8")):
    if not o["atom"].startswith(prefix) or not o["changes"]:
        continue
    m = cat[o["atom"]]["dir"] / "manifest.yaml"
    lines = m.read_text(encoding="utf-8").split("\n")
    start = lines.index("config:")
    done = []
    for k, (old, new) in o["changes"].items():
        for i in range(start + 1, len(lines)):
            if lines[i] and not lines[i].startswith(" "):
                break
            if re.match(rf"^  {re.escape(k)}:\s", lines[i]):
                lines[i] = f"  {k}: {new}"
                done.append(f"{k} {old}→{new}")
                break
    m.write_text("\n".join(lines), encoding="utf-8")
    print(o["atom"], " · ".join(done))
