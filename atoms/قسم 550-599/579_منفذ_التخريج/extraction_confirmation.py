"""٥٧٩ — تأكيد الاستخراج من حدث الوسيط الفعليّ (`platform.trade_event`).

لا يُحسب الاستخراج حتى يصل حدث الوسيط بالتذكرة والطلب نفسيهما وربحٍ محقّقٍ موجب؛
والكامل لا يُعلَن ولا يُعطَّل أصله إلا بعد إغلاق كلّ أرجله.

٢٠٢٦-١٠-٠١ (ختم المالك «Nq»): نُقلت **حرفيًّا** من `atom.py` (`_on_trade`) لحدّ ٤٠٠
سطرٍ فعليّ (م٩/ملف٤) — صفر تغيير سلوك. والدالّة في الصنف بقيت تفويضًا، و`_confirm`
و`_fail_pending` بقيتا هناك وتُناديان من هنا بأسمائهما.
"""
from __future__ import annotations

from typing import Any

from extraction_common import _number, _pending_key, _ticket

# القيمتان نفساهما في `atom.py` — كما يفعل `extraction_retry.py` بثوابته.
EVENT_DEACTIVATE = "perpetual.asset.deactivate"
STATUS_SUCCESS = "SUCCESS"


async def on_trade(atom: Any, payload: dict[str, Any]) -> None:
    if not atom._running or atom._context is None or not isinstance(payload, dict):
        atom._dropped += 1
        return
    event_type = str(payload.get("event_type") or "").upper()
    if event_type not in ("PARTIAL", "CLOSED"):
        atom._dropped += 1
        return
    account = str(payload.get("account_id") or "")
    ticket = _ticket(payload.get("ticket"))
    request_id = str(payload.get("request_id") or "")
    if not account or not ticket:
        atom._dropped += 1
        return
    pending_key = _pending_key(account, ticket)
    pending = atom._pending_by_ticket.get(pending_key)
    if pending is None:
        atom._dropped += 1
        return
    if not request_id:
        # ٢٠٢٦-١٠-٠٥ (ختم المالك «إصلاحها NQ»): الإكسبرت يكتب `request_id` فارغًا لكلّ
        # `PARTIAL`/`CLOSED` (`mt5/QUANT_NQ.mq5` في `OnTradeTransaction`)، فكان هذا الشرط
        # يرمي كلَّ تأكيد — صفر استخراجٍ مؤكَّد منذ البداية، وكلُّها انتهت بالمهلة. حين يغيب
        # الرقم يُطابَق بما يثبت أنّه أمرنا: التذكرة نفسها، والطلب في الطريق (`EXECUTING`)،
        # والإغلاق بيد الإكسبرت (`SYSTEM` = `DEAL_REASON_EXPERT`)، والحجم حجم الأمر.
        command = pending.get("command") if isinstance(pending.get("command"), dict) else {}
        volume = _number(payload.get("volume"))
        wanted = _number(command.get("volume"))
        if (pending.get("status") != "EXECUTING"
                or str(payload.get("reason") or "").upper() != "SYSTEM"
                or volume is None or wanted is None or abs(volume - wanted) > 1e-6):
            atom._dropped += 1
            return
        request_id = str(pending.get("request_id") or "")
        pending["confirmed_by_ticket"] = True
    if (account != str(pending.get("account_id") or "")
            or str(payload.get("symbol") or "") != str(pending.get("symbol") or "")
            or request_id != str(pending.get("request_id") or "")):
        return
    profit = _number(payload.get("profit"))
    requested = _number(pending.get("requested_amount"))
    actual = profit
    if actual is None or actual <= 0:
        await atom._fail_pending(pending_key, "NO_POSITIVE_REALIZED_AMOUNT")
        return
    pending["status"] = STATUS_SUCCESS
    atom._pending_by_ticket.pop(pending_key, None)
    extraction_id = str(pending["extraction_id"])
    full = atom._pending_full.get(extraction_id)
    if full is not None:
        full["expected"].discard(pending_key)
        full["profits"].append(actual)
        if full["expected"]:
            return
        atom._pending_full.pop(extraction_id, None)
        actual_total = sum(full["profits"])
        body = {"extraction_id": extraction_id, "request_id": extraction_id,
                "account_id": full["account_id"], "symbol": full["symbol"],
                "kind": "full", "actual_amount": actual_total,
                "ticket": payload.get("ticket"), "confirmed_by": "platform.trade_event"}
        await atom._confirm(body)
        await atom._context.publish(EVENT_DEACTIVATE, {
            "account_id": full["account_id"], "symbol": full["symbol"]})
        return
    await atom._confirm({
        **pending, "actual_amount": actual, "ticket": payload.get("ticket"),
        "confirmed_by": "platform.trade_event",
    })
