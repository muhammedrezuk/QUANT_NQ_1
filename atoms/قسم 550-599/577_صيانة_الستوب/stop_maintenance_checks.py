"""٥٧٧ — فحص الوقف قبل إرساله: قراءة الأرقام، ومواصفات الوسيط، وهل الوقف في جهته الصحيحة.

٢٠٢٦-١٠-٠٢ (ختم المالك «صلح كامل nq»): نُقلت **حرفيًّا** من `atom.py` لأنّ 1.12.0 (فحص جهة الوقف
من سعر ميتاتريدر بحدّ الوسيط) رفعه إلى ٤٣٧ سطرًا فعليًّا فوق حدّ الأربع مئة (المادة ٩ ملف ٤) —
صفر تغيير في السلوك، الموضعُ وحده. `_on_specs` و`_stop_valid` و`_refuse_stop` كانت طرقًا في
`Atom`: `self` صار الذرّةَ معاملًا أوّل (`atom`)، وبقي في `atom.py` تفويضٌ بالأسماء القديمة؛ و`_to_float`
و`_to_int` و`_norm_side` يستوردها `atom.py` باسمها كما كانت، فلا يفترق تعريفان لاسمٍ واحد.

لا تنشر هذه الوحدة حدثًا: `refuse_stop` يكتب في سجلّ الذرّة وعدّاداتها وحدها، وأمرُ التعديل
يُنشر من `atom.py`.
"""
from __future__ import annotations

from typing import Any


def _to_float(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if result == result else None


def _to_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _norm_side(side: Any) -> str:
    text = str(side).strip().lower()
    if text in ("sell", "short", "1"):
        return "SELL"
    if text in ("buy", "long", "0"):
        return "BUY"
    return ""


async def on_specs(atom, payload: dict[str, Any]) -> None:
    """النقطة وحدّا الوسيط لكلّ رمز — ٢٠٢٦-١٠-٠٢ (ختم المالك «صلح كامل nq»).

    الشكل من ناشره (٦١٨): `payload["symbols"]` قائمةُ صفوف، ولكلّ صفٍّ رمزه.
    """
    if not isinstance(payload, dict) or not isinstance(payload.get("symbols"), list):
        return
    for row in payload["symbols"]:
        if not isinstance(row, dict):
            continue
        symbol = str(row.get("symbol") or "").strip().upper()
        if not symbol:
            continue
        point = _to_float(row.get("point")) or _to_float(row.get("tick_size"))
        if point and point > 0.0:
            atom._point[symbol] = point
        levels = [_to_float(row.get(name)) for name in ("stops_level", "freeze_level")]
        atom._stops_level[symbol] = max([v for v in levels if v is not None and v > 0.0],
                                        default=0.0)


def stop_valid(atom, symbol: Any, side: str, stop: Any, price: Any) -> bool:
    """هل يقبل الوسيط هذا الوقف الآن؟ — ٢٠٢٦-١٠-٠٢ (ختم المالك «صلح كامل nq»).

    وقف الشراء تحت العرض، ووقف البيع فوق الطلب، بحدّ الوسيط
    (`max(stops_level, freeze_level) × point`) ونقطةٍ فوقه. والسعر سعرُ جهة
    المركز (`current_price` من ٦٠٩ أو من تِكّة ميتاتريدر). سعرٌ مجهول = لا إرسال.
    """
    stop_value = _to_float(stop)
    current = _to_float(price)
    if stop_value is None or stop_value <= 0.0 or current is None or current <= 0.0:
        return False
    name = str(symbol or "").strip().upper()
    point = atom._point.get(name, 0.0)
    room = (current - stop_value) if side == "BUY" else (stop_value - current)
    if point <= 0.0:
        return room > 0.0
    return room >= (atom._stops_level.get(name, 0.0) + 1.0) * point - point * 1e-6


def refuse_stop(atom, symbol: str, ticket: int, stop: float, price: Any,
                origin: str) -> None:
    """وقفٌ في غير جهته: لا يُرسل، ويُعدّ ويُسجَّل مرّةً لكلّ تذكرة."""
    if ticket in atom._invalid_tickets:
        return
    atom._invalid_tickets.add(ticket)
    atom._stop_invalid += 1
    atom._last_invalid = "%s tk=%s %s وقف=%s سعر=%s" % (symbol, ticket, origin,
                                                       round(stop, 6), price)
    if atom._context is not None:
        atom._context.logger.warning(
            "577 %s ticket=%s (%s): الوقف %s في غير جهته من سعر التنفيذ %s — "
            "لم يُرسَل (كان سيُردّ 10016)، ويُعاد فحصه مع كلّ سعر",
            symbol, ticket, origin, round(stop, 6), price)
