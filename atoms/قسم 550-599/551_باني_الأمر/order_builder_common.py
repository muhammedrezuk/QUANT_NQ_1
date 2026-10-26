"""٥٥١ — ثوابتُ باني الأمر ومساعدُه الصِّرف: مشتركةٌ بين `atom.py` و`order_builder_sizing.py`.

٢٠٢٦-١٠-٠١ (ختم المالك «Nq»): نُقلت **حرفيًّا** من `atom.py` ليبقى تحت حدّ الأربع
مئة سطرٍ فعليّ (المادة ٩ ملف ٤). لا اسمَ ولا رقمَ ولا منطقَ تبدّل — الموضعُ وحده.
وهي هنا لا في `atom.py` لأنّ حساب الحجم في الوحدة الشقيقة يقرؤها أيضًا، والنسخةُ
الواحدة من الرقم تمنع أن يفترق رقمان لمعنًى واحد. و`atom.py` يستوردها بأسمائها،
فسطحُ تلك الوحدة كما كان.
"""

from __future__ import annotations

from typing import Any

SIDE_BUY = "BUY"
SIDE_SELL = "SELL"

REASON_LOSS_ABOVE_CAP = "LOSS_ABOVE_CAP"
# ٢٠٢٦-٠٩-١٧ — هامش المالك ٥٪ نقصًا أو زيادة (كان ٢٪).
# سقف مخاطرة صلب: لا سماح فوق ميزانية الصفقة.
_RISK_TOLERANCE = 1.0

_PRICE_DP = 6
_VOLUME_DP = 2
_VOLUME_EPSILON = 1e-12   # هامش عائم عند مقارنة الحجم بحدّ الوسيط الأدنى


def _to_float(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if result == result else None
