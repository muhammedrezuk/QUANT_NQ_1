"""Start the isolated Forex/MT5+cTrader stack from the unified release."""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) in sys.path:
    sys.path.remove(str(ROOT))
sys.path.insert(0, str(ROOT))

from governance.network_preflight import validate_market  # noqa: E402

validate_market("forex")

# الجذر القانوني لكلّ حالة حيّة تُديره `shared/runtime_paths.py` (مالك المسارات).
# المتغيّرات الثلاثة هنا هي **عقد الإقلاع** الذي يقرأه المالك: `QUANT_RUNTIME_ROOT`
# (جذر البيانات) و`QUANT_CORE_STATE_ROOT` (journal/snapshots) و
# `QUANT_ANALYSIS_SETTINGS_DB` (سجلّ المعايرة) — ولا مسار يُحسب موازيًا له هنا،
# وإلا خالفه `governance/checks/check_path_authority.py` (البند ٨).

# ٢٠٢٦-٠٩-٠٧ (قرار المالك): «بلاها مرايا وشي زيادة ما له لزوم — هي انضافت
# بعد ما ضفت السوق الثاني». صحيح: المرايا (نسخ `shared` و`core`…
# داخل الـruntime) وُجدت ليعمل **سوقان** من شجرة كود واحدة، كلٌّ من مجلّده
# عبر `chdir`. وبعد إخراج الشجرة الثانية صار السوق واحدًا فسقط سببها.
#
# وهذا يُكمل حكمك ٢٠٢٦-٠٩-٠٥ («لازم يكون في نسخة وحدة بس») الذي نقل تحميل
# الذرّات إلى الجذر بعد أن قِيس تحميل وحدات مشتركة **مرّتين** في العملية
# نفسها. بقي `chdir` أثرًا أخيرًا من عهد السوقين، فأُزيل: الكود يعمل من
# جذر المشروع، وعزل البيانات يبقى كما هو عبر المتغيّرات أدناه — `var/`
# والحالة الحيّة تحت الـruntime بلا تغيير حرف.
os.chdir(ROOT)
os.environ.setdefault("QUANT_CORE_CONFIG", str(ROOT / "config" / "core_forex.yaml"))
# ٢٠٢٦-٠٩-٠٣ (مالك جذور المسارات): الـruntime هو الجذر القانوني لكلّ حالة حيّة
# — data-root (var/)، سجلّ المعايرة، journal، snapshots — فلا يعود أيّ منها
# يعيش تحت جذر المشروع بينما يكتب أخوه داخل الـruntime.
# ٢٠٢٦-٠٩-٠٥ (حكم المالك: «لازم يكون في نسخة وحدة بس»): كانت الذرّات
# تُحمَّل من forex_runtime/atoms بينما النواة وshared تُحمَّلان من الجذر
# (sys.path[0] أعلاه) — فصار النظام يخلط شجرتين. والأخطر أن ثلاث وحدات
# مشتركة حُمِّلت **مرّتين** في العملية نفسها، مقيسًا بـ__pycache__:
#   shared/…/position_delta_recompute.pyc              21:11:56
#   forex_runtime/shared/…/position_delta_recompute.pyc 21:12:10
# نسختان من قانون واحد في ذاكرة واحدة: تعديلٌ في إحداهما يترك النصف
# الآخر يعمل بالقديم بلا خطأ ولا تحذير.
#
# الذرّات صارت تُحمَّل من الجذر — مصدر واحد للكود. وعزل البيانات يبقى
# كما هو: var/ والحالة الحيّة تحت الـruntime بلا تغيير (البند ٨ من
# check_path_authority يخصّ جذور البيانات لا جذر الكود).
os.environ.setdefault("QUANT_ATOMS_ROOT", str(ROOT / "atoms"))
os.environ.setdefault("QUANT_RUNTIME_ROOT", str(ROOT / "forex_runtime"))
os.environ.setdefault("QUANT_CORE_STATE_ROOT", str(ROOT / "forex_runtime" / "var"))
os.environ.setdefault("QUANT_CORE_DOMAIN", "forex")
os.environ.setdefault("QUANT_ANALYSIS_SETTINGS_DB",
                      str(ROOT / "forex_runtime" / "var" / "store" / "analysis_settings.db"))
os.environ.setdefault("NQ_NEWS_DB", str(Path(os.environ.get("APPDATA", "")) / "MetaQuotes" / "Terminal" / "Common" / "Files" / "nq_brain.db"))
# NQ_BRIDGE_DB مقصوص عمدًا: ذرّات جسر MetaTrader (618/619/601) لازم تقرأ/تكتب
# nq_brain.db في مجلّد MetaTrader المشترك حيث يكتب الـEA، لا bridge.db المعزولة
# الفارغة — تعيينه كان يخفي ticks_v2/account_v2 ويعطب التنفيذ (درس server.py:615).

from governance.scripts.run_core import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
