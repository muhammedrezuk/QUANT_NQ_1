"""٥٧٧ — مرساتا الوقف الزاحف: آخر قاعٍ وقمّةٍ بنيويّين لكلّ رمز، وإبطالُ الإعداد مرجعًا للملكيّة.

٢٠٢٦-١٠-٠٢ (ختم المالك «صلح كامل nq»): نُقلت **حرفيًّا** من `atom.py` مع `stop_maintenance_checks.py`
وللسبب نفسه (٤٣٧ سطرًا فعليًّا فوق حدّ الأربع مئة) — صفر تغيير في السلوك. `_on_setup` و`_on_structure`
كانتا طريقتين في `Atom`: `self` صار الذرّةَ معاملًا أوّل (`atom`)، وبقي في `atom.py` تفويضٌ بالاسمين
(والاشتراكات في `initialize` عليهما). تكتبان في دفتري الذرّة (`_setup_stop` و`_structure`) وحدهما،
ويقرؤهما الزحف البنيويّ في `atom.py`.
"""
from __future__ import annotations

from typing import Any

from stop_maintenance_checks import _to_float


async def on_setup(atom, payload: dict[str, Any]) -> None:
    """يحفظ إبطال الإعداد لكل رمز — مرجعًا لا يُستبدل بمنطق آخر."""
    if not atom._running or not isinstance(payload, dict):
        return
    symbol = str(payload.get("symbol") or "").strip().upper()
    stop = _to_float(payload.get("invalidation_price"))
    side = str(payload.get("side") or "").upper()
    setup_id = str(payload.get("setup_id") or "")
    if not symbol or stop is None or side not in ("BUY", "SELL") or not setup_id:
        return
    atom._setup_stop[symbol] = (setup_id, side, stop)


async def on_structure(atom, payload: dict[str, Any]) -> None:
    """يحفظ آخر قاع وآخر قمّة بنيويّين — مرساتا الوقف الزاحف."""
    if not atom._running or not isinstance(payload, dict):
        return
    symbol = str(payload.get("symbol") or "").strip().upper()
    if not symbol:
        return
    meta = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
    signal = str(payload.get("signal") or "").lower()
    book = atom._structure.setdefault(symbol, {})
    # المرجع الذي يُصنَّف به المستوى: سعر إغلاق الدورة التي نشرته.
    reference = (_to_float(meta.get("close")) or _to_float(meta.get("price"))
                 or _to_float(payload.get("price")))
    low = _to_float(meta.get("swing_low"))
    high = _to_float(meta.get("swing_high"))
    if low is None and signal == "swing_low":
        low = _to_float(meta.get("price")) or _to_float(payload.get("price"))
    if high is None and signal == "swing_high":
        high = _to_float(meta.get("price")) or _to_float(payload.get("price"))
    # مستويات الذرّات الأخرى: مستوى الاختراق وحدّا الفجوة وسعر البركة
    # — تُصنَّف قاعًا أو قمّةً بموضعها من مرجع دورتها.
    if reference and reference > 0:
        for field in ("level", "gap_bottom", "gap_top", "price"):
            value = _to_float(meta.get(field))
            if value is None or value <= 0 or value == reference:
                continue
            if value < reference and (low is None or value > low):
                low = value
            elif value > reference and (high is None or value < high):
                high = value
    if low and low > 0:
        book["low"] = low
    if high and high > 0:
        book["high"] = high
