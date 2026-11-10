"""٥٦٣ — قياس الانزلاق على الإقرار: السعر المطلوب مقابل المنفَّذ، بنقاطه وكلفته.

v3.4.2 (٢٠٢٦-١٠-٠١، ختم `Nq`): نُقلت من `atom.py` **حرفيًّا** كي ينزل تحت حدّ
المادة 9 (٤٠٠ سطر فعليّ). `_slippage` كان تابعًا في صنف الذرّة، والفرقُ الوحيد أنّ
`self` صار `atom` — والتابعُ باسمه باقٍ في `atom.py` يُحيل إلى هنا. و`number`
و`SIDE_BUY` و`_PRICE_DP` نُقلت كما هي لأنّ القياس يقرؤها، و`atom.py` يستوردها
بأسمائها (البطاقة والطلب والنتيجة تقرأ `number` هناك). لا سلوك جديد.
"""
from __future__ import annotations

import math
from typing import Any

SIDE_BUY = "BUY"
_PRICE_DP = 6


def number(value: Any) -> float | None:
    if isinstance(value, bool): return None
    try: result = float(value)
    except (TypeError, ValueError): return None
    return result if math.isfinite(result) else None


def slippage(atom, requested: dict[str, Any] | None, filled: float | None,
              volume: float | None) -> dict[str, Any]:
    if requested is None or filled is None:
        atom._unmatched += 1
        return {"slippage_measured": False, "slippage_usable": False,
                "slippage_reason": "NO_REQUESTED_PRICE",
                "slippage_blocks_decisions": True}
    point = number(requested.get("point")); asked = number(requested.get("requested_price"))
    if point is None or point <= 0 or asked is None:
        atom._unmatched += 1
        return {"slippage_measured": False, "slippage_usable": False,
                "slippage_reason": "NO_SCOPED_POINT_SPEC",
                "slippage_blocks_decisions": True,
                "requested_price": asked, "executed_price": filled}
    adverse = (filled - asked) * (1.0 if requested.get("side") == SIDE_BUY else -1.0)
    tick_value = number(requested.get("tick_value")); tick_size = number(requested.get("tick_size"))
    vpu = tick_value / tick_size if tick_value and tick_size else None
    atom._measured += 1
    return {"slippage_measured": True, "slippage_usable": True,
            "slippage_blocks_decisions": False,
            "requested_price": round(asked, _PRICE_DP),
            "executed_price": round(filled, _PRICE_DP),
            "slippage_price": round(adverse, _PRICE_DP),
            "slippage_points": round(adverse / point, 1),
            "slippage_cost": round(adverse * vpu * volume, 2) if vpu and volume else None,
            "slippage_adverse": adverse > 0, "spec_digest": requested.get("spec_digest")}
