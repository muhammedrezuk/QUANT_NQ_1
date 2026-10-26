"""أدوات العيّنة لكاشف الانحراف — قراءة الرقم، طابع المصدر، المئين، وحالة الرمز.

٢٠٢٦-٠٩-٢٣ (ختم `nq`): نُقلت من `atom.py` **حرفيًّا** لأنّه تجاوز حدّ ٤٠٠ سطرٍ
فعليّ (م٩/ملف٤) — صفر تغيير في السلوك. كلّها صرفة: لا حالة ذرّة ولا ساعة.
وكلّ قراءةٍ لـ`clock` بقيت في `atom.py` عمدًا — اختبار الذرّة يستبدل `clock`
فيه وحده، فلو انتقلت قراءةٌ إلى هنا لقرأت الساعة الحقيقيّة.
"""
from __future__ import annotations

import math
from collections import deque
from typing import Any

_STAMP_KEYS = ("source_timestamp", "exchange_timestamp", "timestamp", "broker_timestamp")


def num(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def source_stamp(tick: dict[str, Any] | None) -> float | None:
    """طابع مجال المصدر. القيمة None لا تسقط إلى صفر ولا إلى clock.now()."""
    if not isinstance(tick, dict):
        return None
    for key in _STAMP_KEYS:
        if key not in tick:
            continue
        value = num(tick.get(key))
        if value is not None:
            return value
    return None


def _percentile(sorted_vals: list[float], pct: float) -> float:
    if not sorted_vals:
        return 0.0
    if len(sorted_vals) == 1:
        return sorted_vals[0]
    rank = (len(sorted_vals) - 1) * pct
    lo = int(math.floor(rank))
    hi = int(math.ceil(rank))
    if lo == hi:
        return sorted_vals[lo]
    weight = rank - lo
    return sorted_vals[lo] * (1.0 - weight) + sorted_vals[hi] * weight


class _SymbolState:
    __slots__ = (
        "ct", "mt", "ct_heard_mono", "mt_heard_mono",
        "ct_prev_price", "mt_prev_price",
        "ct_pending", "mt_pending",
        "last_move", "window", "ratio_abs",
    )

    def __init__(self) -> None:
        self.ct: dict[str, Any] | None = None
        self.mt: dict[str, Any] | None = None
        self.ct_heard_mono = 0.0
        self.mt_heard_mono = 0.0
        self.ct_prev_price: float | None = None
        self.mt_prev_price: float | None = None
        self.ct_pending = False
        self.mt_pending = False
        self.last_move: dict[str, Any] | None = None
        self.window: deque[dict[str, Any]] = deque()
        self.ratio_abs: list[float] = []
