# -*- coding: utf-8 -*-
"""يضيف فحص الصدفة للقرب من المناطق إلى results.json."""
import json, os
HERE = os.path.dirname(os.path.abspath(__file__))
R = json.load(open(os.path.join(HERE, "results.json"), encoding="utf-8"))
R["التشابه_مع_سجلّه"]["فحص_الصدفة_للقرب_≤20"] = json.load(open(os.path.join(HERE, "zonebase.json"), encoding="utf-8"))
json.dump(R, open(os.path.join(HERE, "results.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("تمّ")
