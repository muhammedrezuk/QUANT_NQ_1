"""٤٦٥ — الصفقة صافيةً بأجزائها: كلُّ إغلاقٍ جزئيّ جزءٌ على البطاقة، والإغلاقُ الأخير وحده يُغلقها.

٢٠٢٦-١٠-٠٩ (ختم المالك «NQ» — الصفقة صافيةً بأجزائها): كان `card_ledger_trade.on_outcome` يُغلق البطاقة عند
**أوّل** نتيجة. و563 ينشر على `market.outcome.realized` كلَّ جزءٍ بنوعه (`event_type`: `PARTIAL` للجزئيّ و`CLOSED`
للأخير) فلم يكن يُفرَّق بينهما: تُسجَّل الصفقة بربح جزئها الأوّل وحده، ويتحرّر الرمز فتولد بطاقةٌ جديدة يكتب عليها
563 ما بقي من أجزاء التذكرة الأولى (563 يكتب على بطاقة الرمز الحيّة أيًّا كانت). مقيسٌ بسجلّ الوسيط: البطاقة 86470
قالت +30.72$ (+0.33R) والتذكرة 1993419479 ثلاثة أجزاء صافيها +203.51$ (+2.20R)؛ و738 بطاقةً تحمل 645 تذكرةً فقط.

الآن: الجزئيّ يُضاف (`body.legs` وسطرٌ باسم 465) والبطاقة تبقى «منفَّذة» ونتيجتها `PARTIAL` (مفتوحة جزئيًّا)،
والأخيرُ يُغلقها بصافي الأجزاء كلّها ÷ مبلغ المخاطرة الذي كتبه 552 (`risk_amount`). ولا تُخترع حالةٌ جديدة: «منفَّذة»
من الحالات الحيّة التي يحرسها الفهرس الفريد، و«مفتوحة جزئيًّا» تُقال في النتيجة والجسم.
والحساب نفسه (المفتاح · الصافي · اسم المرحلة) في `shared/trade_net.py` — هو ما يقرأ به 469 سجلّ الوسيط.
"""

from __future__ import annotations

import asyncio
import sqlite3
import time
from typing import Any

from shared import trade_net
from shared.trade_card import STATE_FILLED
from card_ledger_common import _text

#: تذاكرُ أُغلقت بطاقاتها أو عُرفت لمركزٍ آخر، تُحفظ لجزءٍ يصل بعد ذلك. مقيس ٢٠٢٦-١٠-٠٩: 29 تذكرةً من 1006
#: حملت إغلاقين (`CLOSED`) بينهما ثوانٍ؛ وما يُحفظ أكثر من آخر أربعٍ وستّين ذكرى بلا حاجة.
MEMORY = 64
#: نتيجةُ بطاقةٍ ما زالت صفقتها مفتوحة بعد جزءٍ أو أكثر — «مفتوحة جزئيًّا».
OUTCOME_PARTIAL = "PARTIAL"
STATUS_OPEN, STATUS_CLOSED = "partial_open", "closed"


def ticket_of(payload: dict[str, Any]) -> str:
    return _text(payload.get("ticket"))


def remember(memory: dict[str, Any], key: str, value: Any) -> None:
    """ذاكرةٌ بسقف: الأحدث يُدرج آخرًا، والأقدم يسقط أوّلًا."""
    memory.pop(key, None)
    memory[key] = value
    while len(memory) > MEMORY:
        memory.pop(next(iter(memory)))


def _leg(payload: dict[str, Any], moment: float, seq: int) -> dict[str, Any]:
    return trade_net.make_leg(
        payload.get("event_type"), payload.get("volume"), payload.get("exit_price"),
        payload.get("profit"), payload.get("commission"), payload.get("swap"), payload.get("fee"),
        payload.get("reason"), moment, payload.get("entry_price"), seq)


async def _row(atom, card_no: int) -> dict[str, Any]:
    """صفّ البطاقة: مبلغ المخاطرة (552) والوقف والهدف المرسَلان — يُقرأ في خيط، وتعذّرُه لا يُسقط شيئًا."""
    if atom._store is None:
        return {}
    try:
        row = await asyncio.to_thread(atom._store.card, card_no)
    except (OSError, sqlite3.Error) as exc:
        atom._last_error = str(exc)
        return {}
    return row or {}


def summarize(card: dict[str, Any], row: dict[str, Any]) -> dict[str, Any]:
    """يسمّي الأجزاء بمراحلها ويجمعها — والوقف المرسَل أوّلًا، فوقفُ التحليل إن غاب."""
    stop = row.get("sent_stop") if row.get("sent_stop") is not None else row.get("stop")
    target = row.get("sent_target") if row.get("sent_target") is not None else row.get("target")
    card["legs"] = trade_net.label_legs(card.get("legs") or [], card.get("side"),
                                        row.get("fill_price"), stop, target, row.get("risk_amount"))
    return trade_net.summarize(card["legs"], row.get("risk_amount"))


def body(card: dict[str, Any], summary: dict[str, Any], status: str) -> dict[str, Any]:
    return {"legs": [dict(leg) for leg in card.get("legs") or []], "net": {**summary, "status": status}}


def net_text(summary: dict[str, Any], legs: list[dict[str, Any]]) -> str:
    """«صافي +203.51$ = +2.20R على 3 أجزاء · خروج على الهدف | الهدف الأوّل: … | …» — سطرُ الإغلاق."""
    r = summary.get("net_r")
    return "صافي %+.2f$ = %s على %d أجزاء · %s | %s" % (
        summary["net_usd"], "بلا R (لا مبلغ مخاطرة)" if r is None else "%+.2fR" % r,
        summary["legs"], summary.get("exit_ar") or "—",
        " | ".join(trade_net.leg_text(leg) for leg in legs))


async def reassert(atom, card: dict[str, Any]) -> None:
    """563 يكتب كلّ جزءٍ على بطاقة الرمز الحيّة أيًّا كانت — فتُعاد إليها قيمُها هي، باسم 465."""
    legs = card.get("legs") or []
    total = trade_net.summarize(legs) if legs else {}
    fields: dict[str, Any] = {"profit": total.get("net_usd"),
                              "outcome": OUTCOME_PARTIAL if legs else None,
                              "exit_price": legs[-1].get("price") if legs else None}
    if card.get("ticket"):
        fields["ticket"] = _text(card["ticket"])
    if card.get("fill") is not None:
        fields["fill_price"] = card["fill"]
    await atom._update(card["card_no"], fields)


async def record_leg(atom, symbol: str, card: dict[str, Any],
                     payload: dict[str, Any]) -> tuple[bool, dict[str, Any]]:
    """يضيف الجزء إلى البطاقة الحيّة؛ يُرجع (أهو الإغلاق الأخير، المجموع).

    الجزئيّ يُكتب هنا كاملًا وتبقى البطاقة حيّة؛ والأخيرُ يُرجَع مجموعُه لـ`on_outcome` الذي يُغلقها.
    وجزءٌ مكرَّر بلا مالٍ جديد لا يُعدّ مرّتين: يُعدّ (`dup_legs`) وتُعاد قيم البطاقة التي كتب فوقها 563.
    """
    legs = card.setdefault("legs", [])
    if not card.get("ticket") and ticket_of(payload):
        card["ticket"] = ticket_of(payload)
    leg = _leg(payload, time.time(), len(legs))
    before = len(legs)
    if not trade_net.merge_leg(legs, leg):
        atom._dup_legs += 1
        await reassert(atom, card)
        return False, {}
    final = leg["event"] != trade_net.EVENT_PARTIAL
    summary = summarize(card, await _row(atom, card["card_no"]))
    if final:
        return True, summary
    fields: dict[str, Any] = {"profit": summary["net_usd"], "outcome": OUTCOME_PARTIAL}
    if card.get("state") != STATE_FILLED:
        card["state"] = fields["state"] = STATE_FILLED
    await atom._update(card["card_no"], fields, body(card, summary, STATUS_OPEN))
    if len(legs) > before:
        atom._partials += 1
        atom._write(symbol, "465", "partial_%d" % summary["partials"], trade_net.leg_text(leg))
    atom._changed = True
    await atom._announce(symbol, card)
    return False, summary


def closing(atom, symbol: str, card: dict[str, Any], summary: dict[str, Any]) -> dict[str, Any]:
    """الإغلاق الأخير: سطرُ الصافي على البطاقة، والتذكرةُ تُحفظ لجزءٍ متأخّر — ويُرجع ما يُضاف إلى الإعلان."""
    atom._write(symbol, "465", "net", net_text(summary, card.get("legs") or []))
    if card.get("ticket"):
        remember(atom._final_tickets, _text(card["ticket"]),
                 {"card_no": card["card_no"], "side": card.get("side"), "legs": card.get("legs") or []})
    return {"ticket": _text(card.get("ticket")) or None, "legs": summary["legs"],
            "partials": summary["partials"], "gross_usd": summary["gross_usd"],
            "costs_usd": summary["costs_usd"], "net_usd": summary["net_usd"],
            "net_r": summary["net_r"], "risk_usd": summary["risk_usd"], "exit": summary["exit"]}


async def late_leg(atom, symbol: str, ticket: str, payload: dict[str, Any]) -> None:
    """جزءٌ وصل بعد إغلاق بطاقة تذكرته: يُضاف إلى تلك البطاقة (صافيها يتبدّل) ولا يمسّ بطاقة الرمز الحيّة."""
    memo = atom._final_tickets[ticket]
    moment = time.time()
    leg = _leg(payload, moment, len(memo["legs"]))
    if not trade_net.merge_leg(memo["legs"], leg):
        atom._dup_legs += 1
    else:
        summary = summarize(memo, await _row(atom, memo["card_no"]))
        await atom._update(memo["card_no"], {"profit": summary["net_usd"], "outcome": summary["result"]},
                           body(memo, summary, STATUS_CLOSED))
        atom._pending.append((memo["card_no"], "465", "late_leg_%d" % summary["legs"],
                              net_text(summary, memo["legs"]), moment))
        atom._late_legs += 1
    live = atom._live.get(symbol)
    if live is not None:
        await reassert(atom, live)


async def foreign_leg(atom, symbol: str, card: dict[str, Any], ticket: str,
                      payload: dict[str, Any]) -> None:
    """جزءُ تذكرةٍ ليست تذكرة البطاقة (مركزٌ آخر على الرمز): يُسمّى عليها ولا يُغلقها ولا يُضاف إلى صافيها."""
    atom._foreign_legs += 1
    atom._write(symbol, "465", "foreign_leg", "%s %s %s$" % (
        ticket, _text(payload.get("event_type")) or "-", payload.get("profit")))
    await reassert(atom, card)
