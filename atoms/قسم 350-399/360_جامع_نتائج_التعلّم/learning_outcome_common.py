"""٣٦٠ — ثوابتُ مجمّع النتائج ومساعداته الصِّرفة: مشتركةٌ بين `atom.py` ووحدة المطابقة.

v1.8.1 (٢٠٢٦-١٠-٠١، ختم المالك «Nq»): نُقلت **حرفيًّا** من `atom.py` ليبقى تحت حدّ
الأربع مئة سطر فعليّ (المادة ٩ ملف ٤). لا اسمَ ولا رقمَ ولا منطقَ تبدّل — الموضعُ وحده.
وهي هنا لا في `atom.py` لأنّ مطابقة النتيجة صارت في وحدةٍ شقيقة تقرؤها أيضًا، والنسخةُ
الواحدة من كلّ ثابتٍ تمنع أن يفترق تعريفان.
"""

from __future__ import annotations

from typing import Any

SEP = "\x1f"

# Local arrival clock, not the payload timestamp: broker stamps run on server
# time (+3h here), so ageing on them would prune the wrong rows.  Stripped from
# the published record -- it is bookkeeping, not evidence.
FIELD_RECEIVED = "pending_received_at"

# الحقول التي قد تحمل هويّة القرار على نتيجة الوسيط -- مصدرٌ واحد للبحث
# وللتصنيف معًا، فلا يفترقان.
_OUTCOME_IDENTITY = ("decision_id", "request_id", "cycle_id", "gate_request_id")


def num(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if result == result else None


def key(account_id: Any, symbol: Any) -> str:
    return str(account_id or "") + SEP + str(symbol or "")


def _text(value: Any) -> str:
    return str(value or "").strip()
