# -*- coding: utf-8 -*-
"""للعلم (حساسيّة لا اختيار): صفقات أفضل تعلّمٍ داخل عائلة «المتوسّط» وحدها — ك=0.5 ب=0.25 ن=1 ضدّ المتّفق."""
import sys
sys.dont_write_bytecode = True
import json
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import reversion as V   # noqa: E402

tr, tally = V.run("متوسّط", 0.5, 0.25, 1.0, "ضدّ_المتّفق")
json.dump([[x[0], x[5], round(x[1], 4), x[2], x[3], round(x[4], 2)] for x in tr],
          open(os.path.join(V.OUT, "trades_ema_family_best.json"), "w", encoding="utf-8"), ensure_ascii=False)
print(V.line("عائلة_المتوسّط_الأفضل_تعلّمًا", V.block(tr, tally)), tally)
