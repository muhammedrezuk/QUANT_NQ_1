from __future__ import annotations
from typing import Any

SIDE_BUY = "BUY"
SIDE_SELL = "SELL"
ACTION_OPEN = "OPEN"
ACTION_CLOSE = "CLOSE"
ACTION_CLOSE_PARTIAL = "CLOSE_PARTIAL"
ACTION_MODIFY_SL = "MODIFY_SL"
ACTION_MODIFY_TP = "MODIFY_TP"
PROTECTION_NEUTRAL_HEDGE = "NEUTRAL_HEDGE"
PROTECTION_PERPETUAL = "PERPETUAL_BUDGET"
ORIGIN_PERPETUAL = "perpetual-delta"

def _to_float(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if result == result else None


def _neutral_pair_contract(order: dict[str, Any]) -> bool:
    """Recognise the shape of a neutral-pair (hedge) leg -- to REFUSE it.

    🔴 ٢٠٢٦-٠٩-٢٣ (ختم `nq`) — إزالة منظومة الهيدج. كان هذا الشكل استثناءً
    يعبر بلا وقف ولا هدف ولا قرارٍ أب، وقد مات منتِجُه (٥٧٦/٥٧٨ في الأرشيف)
    فبقي بابًا مفتوحًا بلا صاحب. صار الشكل نفسه سببَ رفضٍ مسمّى
    (`NEUTRAL_HEDGE_REMOVED`) — فلا يعبر أمرٌ لأنّه قال «أنا ساقُ هيدج».
    """
    mode = str(order.get("protection_mode") or "").upper()
    role = str(order.get("leg_role") or "").upper()
    pair_id = str(order.get("pair_id") or "").strip()
    attempt = _to_float(order.get("attempt"))
    required = order.get("pair_required") is True
    return (
        str(order.get("action") or ACTION_OPEN).upper() == ACTION_OPEN
        and mode == PROTECTION_NEUTRAL_HEDGE
        and required
        and bool(pair_id)
        and role in (SIDE_BUY, SIDE_SELL)
        and attempt is not None and attempt >= 1
        and order.get("stop_loss") in (None, 0, 0.0)
        and order.get("take_profit") in (None, 0, 0.0)
    )


def _perpetual_budget_contract(order: dict[str, Any]) -> str | None:
    """🔴 ٢٠٢٦-٠٩-٢٣ (ختم `nq`) — الرِّجل الدائمة لم تعد استثناءً: تُرفض.

    Returns None when the order is not a perpetual leg (normal rules apply),
    and ``"PERPETUAL_REMOVED"`` when it is one. Its producer (576) is in the
    archive, and a leg excused from the target is a hedge-era door. The name
    stays because the startup gate `check_execution_safety` looks for it --
    removing it would refuse the whole execution phase at boot.

    — ما يلي هو النصّ التاريخيّ للاستثناء كما كان، للقراءة لا للعمل —

    The second, explicitly defined exception -- now a NO-TAKE-PROFIT one.

    Owner's ruling 2026-08-13 (problem 2, option c): the asset budget
    (512/518/519) stays the risk MANAGER, and the broker stop comes back as a
    LAST RESORT.  So a perpetual leg is no longer allowed through without a
    stop; what it is excused from is the TAKE PROFIT, because a perpetual
    position is never closed by a target -- profit leaves through extraction.

    Returns None when the order is not a perpetual leg at all (fall through to
    the normal rules), "" when it is a valid one, or a rejection reason.  The
    shape stays as narrow as the neutral-pair exception: declared mode, the
    perpetual origin, a positive budget the guard can be held to, an empty
    target, and a real stop on the correct side of the price.
    """
    if not (str(order.get("action") or ACTION_OPEN).upper() == ACTION_OPEN
            and str(order.get("protection_mode") or "").upper() == PROTECTION_PERPETUAL
            and str(order.get("origin") or "") == ORIGIN_PERPETUAL):
        return None
    return "PERPETUAL_REMOVED"


def _validate(order: dict[str, Any]) -> str:
    symbol = order.get("symbol")
    action = str(order.get("action") or ACTION_OPEN).upper()
    side = str(order.get("side", "")).upper()
    ref = _to_float(order.get("reference_price"))
    stop = _to_float(order.get("stop_loss"))
    target = _to_float(order.get("take_profit"))
    volume = _to_float(order.get("volume"))
    if action not in (ACTION_OPEN, ACTION_CLOSE, ACTION_CLOSE_PARTIAL, ACTION_MODIFY_SL, ACTION_MODIFY_TP):
        return "BAD_ACTION"
    if not symbol:
        return "NO_SYMBOL"
    if side not in (SIDE_BUY, SIDE_SELL):
        return "BAD_SIDE"
    if volume is None or volume <= 0.0:
        return "BAD_VOLUME"
    if action != ACTION_OPEN:
        return "" if order.get("ticket") not in (None, "", 0) else "NO_TICKET"
    if ref is None or ref <= 0.0:
        return "BAD_PRICE"

    perpetual = _perpetual_budget_contract(order)
    if perpetual is not None:
        return perpetual
    if _neutral_pair_contract(order):
        return "NEUTRAL_HEDGE_REMOVED"
    if stop is None or stop <= 0.0:
        return "NO_STOP"
    if target is None or target <= 0.0:
        return "NO_TARGET"
    if side == SIDE_BUY and not (stop < ref < target):
        return "BUY_LEVELS"
    if side == SIDE_SELL and not (target < ref < stop):
        return "SELL_LEVELS"
    return ""

