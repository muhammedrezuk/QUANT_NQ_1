"""٤٦٥ — ثوابتُ الدفتر ومساعداته الصِّرفة: مشتركةٌ بين `atom.py` ووحداته الشقيقة.

v1.30.1 (٢٠٢٦-٠٩-٢٣، ختم `nq`): نُقلت **حرفيًّا** من `atom.py` ليبقى تحت حدّ
الأربع مئة سطر (المادة ٩ ملف ٤). لا اسمَ ولا رقمَ ولا منطقَ تبدّل — الموضعُ وحده.
وأحداثُ النشر هنا لا في `atom.py` لأنّ من ينشرها صار في الوحدات الشقيقة، والنسخةُ
الواحدة من الاسم تمنع أن يفترق اسمان لحدثٍ واحد.
"""

from __future__ import annotations

from typing import Any

EVENT_OPENED = "decision.card.opened"
EVENT_CLOSED = "decision.card.closed"
#: انتقالُ حالةٍ واحد لكلّ مستهلك — فلا تقرأ ذرّةٌ مخزن ذرّةٍ أخرى.
#: طلبه قسم ٣٥٠-٣٩٩ ٢٠٢٦-٠٩-١٨ ليطابق نتائجه بالبطاقة عبر الناقل.
EVENT_CHANGED = "decision.card.changed"
#: نداءُ الانعكاس — حكم المالك ٢٠٢٦-٠٩-١٨: «تحليل إذا انعكس بنص صفقة،
#: انت بدك تخبر مال إنّه اتّجاه تغيّر وصفقة عم تتحوّل». فالبطاقة ترافق
#: الصفقة إلى نهايتها، ومرافقتُها ليست تسجيلًا صامتًا: من يرى الانعكاس
#: أوّلًا عليه أن ينادي، لا أن يكتبه ليُقرأ بعد الخسارة.
EVENT_REVERSED = "decision.card.reversed"

SIDE_BUY = "buy"
SIDE_SELL = "sell"
_SIDES = (SIDE_BUY, SIDE_SELL)

#: سقف كتّاب المسوّدة لكلّ رمز — المسوّدة ذاكرةٌ لا مخزن، وما فاض يُسقط
#: أقدمه لا أحدثه (الأحدث هو الذي صنع القرار).
_DRAFT_CAP = 24
#: سقف الرموز المتتبَّعة في المسوّدة — أكثر من ذلك يعني رموزًا لا تتداول.
_DRAFT_SYMBOLS = 32

#: أصغرُ تغيّرٍ في مضاعف المخاطرة يستحقّ قرصًا — الذروة تتحرّك بالتِكّة،
#: وحفظ كلّ حركةٍ كتابةٌ بلا نهاية. عُشر المخاطرة يكفي لقراءة المسار.
_PEAK_STEP_R = 0.1
#: عيّنةُ هامش الحسم المحفوظة لقياس عرض نطاق الحياد — عيّنةٌ لا سجلّ،
#: فالمطلوب شكل التوزيع لا كلّ قيمة.
_MARGIN_SAMPLE = 4000


def _text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _real(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if result == result and result not in (float("inf"), float("-inf")) else None


def _side_of(payload: dict[str, Any]) -> str:
    for name in ("decision_side", "side", "direction", "signal"):
        candidate = _text(payload.get(name)).lower()
        if candidate in _SIDES:
            return candidate
    return ""


def _meta(payload: dict[str, Any]) -> dict[str, Any]:
    value = payload.get("metadata")
    return value if isinstance(value, dict) else {}
