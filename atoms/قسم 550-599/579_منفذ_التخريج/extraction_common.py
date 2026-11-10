"""٥٧٩ — أدواتٌ صغيرة يتقاسمها `atom.py` ووحدةُ التأكيد: قراءةُ الرقم، والتذكرة،
ومفتاحُ الطلب المعلَّق (`حساب|تذكرة`).

٢٠٢٦-١٠-٠١ (ختم المالك «Nq»): نُقلت **حرفيًّا** من `atom.py` لحدّ ٤٠٠ سطرٍ فعليّ
(م٩/ملف٤) — صفر تغيير سلوك. و`atom.py` يستوردها بأسمائها، فيبقى سطحُ وحدته كما كان.
"""
from __future__ import annotations

from typing import Any

SEP = "|"


def _number(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if result == result else None


def _ticket(value: Any) -> str:
    return str(value or "").strip()


def _pending_key(account: Any, ticket: Any) -> str:
    return str(account or "").strip() + SEP + _ticket(ticket)
