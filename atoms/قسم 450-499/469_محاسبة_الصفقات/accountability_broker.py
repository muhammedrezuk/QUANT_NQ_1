"""469 — سجلّ الوسيط نفسه (`trade_events_v2` في قاعدة الجسر) للقراءة فقط: أجزاء كلّ تذكرةٍ لها بطاقة وصافيها.

٢٠٢٦-١٠-٠٩ (ختم المالك «NQ» — الصفقة صافيةً بأجزائها): «نحن نشتغل نجمع R — كم R خسرنا مقابل كم ربحنا صافي…
R عنّا 100 دولار». وكانت المحاسبة تقرأ الربح من البطاقة، و465 كان يُغلق البطاقة عند أوّل جزء: فالبطاقة 86470
قالت +0.33R والوسيط +2.20R، و738 بطاقةً حملت 645 تذكرةً فقط (563 يكتب أجزاء التذكرة على بطاقة الرمز الحيّة أيًّا
كانت، فتوزّعت أجزاءُ صفقةٍ واحدة على بطاقات). فالصافي هنا من الوسيط لا من البطاقة:
  الصفقة  = تذكرةٌ لها إغلاقٌ أخير (`CLOSED`) وبطاقةٌ تملكها.
  الصافي  = مجموع (الربح + العمولة + المبادلة + الرسوم) على أجزائها (`PARTIAL` و`CLOSED`)، والصفّ المكرَّر مرّةً.
  R       = الصافي ÷ مبلغ المخاطرة على البطاقة المالكة (552 `risk_amount`) — وبلا مبلغٍ تُعدّ بالدولار «بلا R».
  المالكة = البطاقة التي سمعت تأكيد تنفيذ التذكرة (`563.filled` منذ ٠٩-٢٥) وإلّا أصغر بطاقةٍ تحمل التذكرة في
            عمودها ولا تملك تذكرةً غيرها بالتأكيد.
والقراءة `mode=ro` في خيطٍ لا على الحلقة، والحساب نفسه (المفتاح · الصافي · اسم المرحلة) في `shared/trade_net.py`.
"""

from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path
from typing import Any

from shared import trade_net
from accountability_ledger import (LIVE_STATES, SIDE_NAMES, WINDOW_OUTSIDE, _body, excursion, real,
                                   strategy_of, text)
from shared.owner_windows import owner_window

BRIDGE_TABLE = "trade_events_v2"
#: مرسى الجسر في البيئة يسبق المعطى — عقد قرّاء الجسر كلّهم (118 · 121 · 601 …)؛ والاختبار يرفعه (`conftest.py`).
BRIDGE_ENV = "NQ_BRIDGE_DB"
_TABLE_SQL = "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?"
_EVENTS_SQL = ("SELECT id, account_id, event_type, ticket, symbol, side, volume, entry_price, exit_price, "
               "reason, profit, commission, swap, fee, written_at FROM trade_events_v2 "
               "WHERE event_type IN ('OPENED', 'PARTIAL', 'CLOSED') ORDER BY id")
EVENT_OPENED = "OPENED"
#: حجم البطاقة (552) وحجم فتح التذكرة يتطابقان إلى هذا — وإلّا فمبلغ المخاطرة على البطاقة لأمرٍ آخر.
VOLUME_EPS = 1e-6
#: فرق R بين البطاقة والوسيط دونه سنتُ تقريب لا فرق.
R_DIFF_EPS = 0.005
RISK_OK, RISK_MISSING, RISK_OTHER_ORDER = "", "no_risk_amount", "volume_mismatch"


class BrokerUnavailable(Exception):
    """قاعدة الجسر غائبةٌ أو لا تُقرأ — يُعلَن سببه، وتعود المحاسبة إلى البطاقات معلنةً ذلك."""


def resolve_bridge_path(configured: str | None) -> str:
    return os.environ.get(BRIDGE_ENV, "").strip() or os.path.expandvars(configured or "")


def read_broker(path: str, timeout_s: float) -> dict[str, dict[str, Any]]:
    """تذكرة ⟵ {الرمز · الجهة · الفتح · الأجزاء} من سجلّ الوسيط — للقراءة فقط، ويُنادى في خيط."""
    file = Path(path) if path else None
    if file is None or not file.is_file():
        raise BrokerUnavailable("قاعدة الجسر غير موجودة: %s" % (path or "—"))
    try:
        connection = sqlite3.connect(file.resolve().as_uri() + "?mode=ro", uri=True, timeout=timeout_s)
    except sqlite3.Error as exc:
        raise BrokerUnavailable("تعذّر فتح قاعدة الجسر: %s" % exc) from exc
    try:
        if connection.execute(_TABLE_SQL, (BRIDGE_TABLE,)).fetchone() is None:
            raise BrokerUnavailable("لا جدول %s في قاعدة الجسر" % BRIDGE_TABLE)
        rows = connection.execute(_EVENTS_SQL).fetchall()
    except sqlite3.Error as exc:
        raise BrokerUnavailable("تعذّرت قراءة سجلّ الوسيط: %s" % exc) from exc
    finally:
        connection.close()
    tickets: dict[str, dict[str, Any]] = {}
    for (row_id, account, event, ticket, symbol, side, volume, entry, exit_price, reason, profit,
         commission, swap, fee, written_at) in rows:
        key = text(ticket)
        if not key:
            continue
        item = tickets.setdefault(key, {"ticket": key, "symbol": text(symbol).upper(),
                                        "side": text(side).upper(), "account": text(account),
                                        "opened": None, "legs": []})
        if text(event).upper() == EVENT_OPENED:
            item["opened"] = {"volume": real(volume), "entry": real(entry), "at": real(written_at)}
            continue
        trade_net.merge_leg(item["legs"], trade_net.make_leg(
            event, volume, exit_price, profit, commission, swap, fee, reason, written_at, entry, row_id))
    return tickets


def filled_tickets(rows: list[tuple[Any, Any]]) -> dict[str, int]:
    """«1993419479 buy @30936.4» (سطر 563 `filled` على البطاقة) ⟵ تذكرة ⟵ رقم البطاقة (الأصغر إن تكرّرت)."""
    out: dict[str, int] = {}
    for card_no, raw in rows:
        try:
            value = json.loads(raw) if raw is not None else ""
        except (TypeError, ValueError):
            value = raw
        parts = text(value).split()
        if parts and parts[0].isdigit():
            out[parts[0]] = min(int(card_no), out.get(parts[0], int(card_no)))
    return out


def owners(cards: list[dict[str, Any]], filled: dict[str, int]) -> dict[str, dict[str, Any]]:
    """تذكرة ⟵ البطاقة المالكة: تأكيد التنفيذ أوّلًا، ثمّ أصغر بطاقةٍ تحملها ولا تملك غيرها بالتأكيد."""
    by_no = {int(card["card_no"]): card for card in cards}
    owned = set(filled.values())
    out = {ticket: by_no[number] for ticket, number in filled.items() if number in by_no}
    for card in sorted(cards, key=lambda c: int(c["card_no"])):
        ticket = text(card.get("ticket"))
        if ticket and ticket not in out and int(card["card_no"]) not in owned:
            out[ticket] = card
    return out


def _leg_view(leg: dict[str, Any]) -> dict[str, Any]:
    return {"stage": leg.get("stage"), "stage_ar": leg.get("stage_ar"), "event": leg.get("event"),
            "reason": leg.get("reason"), "volume": leg.get("volume"), "exit_price": leg.get("price"),
            "profit_usd": leg.get("profit"), "costs_usd": round(trade_net.leg_net(leg) - (leg.get("profit") or 0.0), 2),
            "net_usd": round(trade_net.leg_net(leg), 2), "r": leg.get("r"), "move_r": leg.get("move_r"),
            "target_frac": leg.get("target_frac"), "closed_at": leg.get("at")}


def derive_broker_trade(card: dict[str, Any], data: dict[str, Any]) -> dict[str, Any]:
    """أرقام صفقةٍ واحدة من أجزائها عند الوسيط، ومعها ما قالته بطاقتها — حسابٌ لا تقدير."""
    body = _body(card)
    side = data.get("side") or text(card.get("side")).upper()
    opened = data.get("opened") or {}
    risk = real(card.get("risk_amount"))
    card_volume, opened_volume = real(card.get("volume")), real(opened.get("volume"))
    note = RISK_OK
    if risk is None or risk <= 0:
        note = RISK_MISSING
    elif card_volume is not None and opened_volume is not None and abs(card_volume - opened_volume) > VOLUME_EPS:
        note = RISK_OTHER_ORDER
    unit_risk = risk if note == RISK_OK else None
    legs = data["legs"]
    entry = next((leg["entry"] for leg in legs if leg.get("entry") is not None), real(opened.get("entry")))
    stop = real(card.get("sent_stop")) if card.get("sent_stop") is not None else real(card.get("stop"))
    target = real(card.get("sent_target")) if card.get("sent_target") is not None else real(card.get("target"))
    legs = trade_net.label_legs(legs, side, entry, stop, target, unit_risk)
    summary = trade_net.summarize(legs, unit_risk)
    card_profit = real(card.get("profit"))
    card_r = card_profit / risk if card_profit is not None and risk else None
    sign = 1.0 if side == "BUY" else -1.0 if side == "SELL" else None
    reach = excursion({**card, "fill_price": entry}, sign)
    opened_at = real(card.get("opened_at"))
    last = legs[-1]
    return {
        "card_no": int(card.get("card_no") or 0), "ticket": data["ticket"],
        "symbol": data.get("symbol") or text(card.get("symbol")).upper(), "state": text(card.get("state")),
        "side": SIDE_NAMES.get(side.lower(), ""), "opened_at": opened_at, "closed_at": last.get("at"),
        "strategy": strategy_of(body),
        "window": (owner_window(opened_at) if opened_at is not None else None) or WINDOW_OUTSIDE,
        "profit_usd": summary["net_usd"], "gross_usd": summary["gross_usd"], "costs_usd": summary["costs_usd"],
        "risk_usd": unit_risk, "card_risk_usd": risk, "result_r": summary["net_r"], "risk_note": note,
        "card_profit_usd": card_profit, "card_r": None if card_r is None else round(card_r, 4),
        "r_diff": (round(summary["net_r"] - card_r, 4)
                   if summary["net_r"] is not None and card_r is not None else None),
        "legs": [_leg_view(leg) for leg in legs], "legs_n": summary["legs"], "partials": summary["partials"],
        "exit_kind": summary["exit"], "exit_ar": summary["exit_ar"],
        "exit_move_r": last.get("move_r"), "exit_target_frac": last.get("target_frac"), "recorded_share": None,
        "max_favorable_r": None if reach["favorable_r"] is None else round(reach["favorable_r"], 4),
        "max_adverse_r": None if reach["adverse_r"] is None else round(reach["adverse_r"], 4),
        "excursion_basis": reach["basis"], "thirds_reached": reach["thirds"],
        "entry": real(card.get("entry")), "stop": real(card.get("stop")), "target": real(card.get("target")),
        "fill_price": entry, "exit_price": last.get("price"), "sent_stop": real(card.get("sent_stop")),
        "sent_target": real(card.get("sent_target")), "rr": real(card.get("rr")),
        "stop_reason": text(body.get("invalidation_reason")), "target_reason": text(body.get("target_reason")),
        "net_source": "broker"}


def broker_trades(ledger: dict[str, Any], broker: dict[str, dict[str, Any]]
                  ) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """الصفقات المغلقة لكلّ تذكرةٍ لها بطاقة — ومعها عدّ ما لم يُحسب ولماذا."""
    filled = filled_tickets(ledger.get("filled_rows") or [])
    owner = owners(ledger["cards"], filled)
    counts = {"broker_tickets_closed": 0, "broker_tickets_without_card": 0, "open_with_partials": 0,
              "card_tickets_not_closed_at_broker": 0, "tickets_by_confirmed_fill": 0}
    trades = []
    for ticket, data in broker.items():
        final = any(leg["event"] != trade_net.EVENT_PARTIAL for leg in data["legs"])
        counts["broker_tickets_closed"] += final
        card = owner.get(ticket)
        if card is None:
            counts["broker_tickets_without_card"] += final
            continue
        if not final:
            counts["open_with_partials"] += bool(data["legs"])
            continue
        counts["tickets_by_confirmed_fill"] += ticket in filled
        trades.append(derive_broker_trade(card, data))
    counts["card_tickets_not_closed_at_broker"] = sum(
        1 for ticket in owner if ticket not in broker
        or not any(leg["event"] != trade_net.EVENT_PARTIAL for leg in broker[ticket]["legs"]))
    return trades, counts


def comparison(cards: list[dict[str, Any]], trades: list[dict[str, Any]]) -> dict[str, Any]:
    """ما تقوله البطاقات القديمة (كما حسبتها المحاسبة قبل اليوم: كلّ بطاقةٍ عليها ربح) مقابل الوسيط — بالـR."""
    old = [card for card in cards if real(card.get("profit")) is not None
           and text(card.get("state")) not in LIVE_STATES]
    old_r = [real(c["profit"]) / real(c["risk_amount"]) for c in old
             if real(c.get("risk_amount")) is not None and real(c["risk_amount"]) > 0]
    new_r = [t["result_r"] for t in trades if t["result_r"] is not None]
    owned = {t["card_no"] for t in trades}
    return {
        "cards_n": len(old), "cards_total_usd": round(sum(real(c["profit"]) for c in old), 2),
        "cards_n_r": len(old_r), "cards_total_r": round(sum(old_r), 3),
        "broker_n": len(trades), "broker_total_usd": round(sum(t["profit_usd"] for t in trades), 2),
        "broker_n_r": len(new_r), "broker_total_r": round(sum(new_r), 3),
        "diff_r": round(sum(new_r) - sum(old_r), 3),
        "diff_usd": round(sum(t["profit_usd"] for t in trades) - sum(real(c["profit"]) for c in old), 2),
        "trades_card_differs": sum(1 for t in trades if t["r_diff"] is not None and abs(t["r_diff"]) > R_DIFF_EPS),
        "cards_not_owning_their_profit": sum(1 for c in old if int(c["card_no"]) not in owned)}
