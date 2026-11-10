from __future__ import annotations

from typing import Any

from shared.financial_scope import text

# Campaign 450-901 batch B: state-input handlers (margin verdicts, snapshots,
# reconciliation, exposure, reference feeds) extracted verbatim.
#
# Item 25 (27-atom review, 2026-08-27): found completely unwired -- atom.py
# had kept its own inline copies of every function below instead of calling
# out to this module, and this file still carried a bug atom.py itself had
# already fixed a day after this extraction (see below). Fixed here first,
# with the same rigor as live code -- dead code that still LOOKS correct is
# exactly what a future "wire this in to shrink atom.py" pass would trust
# without re-auditing. Wired into atom.py (v5.5.0) only after that fix was
# proven behavior-preserving: the atom's own 11-scenario suite plus a
# 90-case old-vs-new differential simulation (9 contexts x 10 order shapes)
# matched exactly, run outside the project's own test tooling. atom.py's
# five state-handler methods now delegate here instead of duplicating.
#
# Two real bugs were closed before wiring, both against atom.py's then-
# current (post v5.4.1) code:
#
# (1) `if not atom._running or not isinstance(...)` on every handler below
# was atom.py's OWN gate before v5.4.0/v5.4.1 (2026-08-25) -- removed there
# after it caused two separate MEASURED LIVE incidents: the symbol whitelist
# arriving before this atom's start() was silently dropped (six orders died
# SYMBOL_NOT_ALLOWED while the correct whitelist had already arrived), then
# the same pattern recurred as a dropped reconciliation state
# (RECONCILIATION_NOT_MATCHED). atom.py's fix: state handlers never gate on
# _running -- only command/decision handlers do. This file still had the
# PRE-fix gate on all five functions; removed to match atom.py exactly.
#
# (2) `_remember()` here had no eviction bound at all -- atom.py's own
# `_remember()` (same name, same job) caps tracked records at
# `_MAX_TRACKED=4096` and evicts the oldest past that count (memory bound
# only, not a trading value -- same family as 467's tracked-decision bound).
# This copy would grow the three registries it feeds without limit.

import time

_MAX_TRACKED = 4096


def _remember(registry: dict, key: Any, record: dict) -> None:
    if key not in registry and len(registry) >= _MAX_TRACKED:
        registry.pop(next(iter(registry)))
    registry[key] = record


async def on_margin_verdict(atom, payload: dict[str, Any]) -> None:
    """T3 (c): remember 526's margin verdict per (account, request)."""
    if not isinstance(payload, dict): return  # state handler: no running gate (v5.4.1)
    account = text(payload.get("account_id")); request_id = text(payload.get("request_id"))
    if not account or not request_id: return
    _remember(atom._margin_verdicts, (account, request_id), {
        "approved": payload.get("approved") is True,
        "reason": text(payload.get("reason")),
        "required_margin": payload.get("required_margin"),
        "free_margin": payload.get("free_margin"),
        "measured_at": time.time()})


async def on_snapshot(atom, payload: dict[str, Any]) -> None:
    """T3 (d) + T1: remember 583's snapshot verdict keyed by snapshot_id."""
    if not isinstance(payload, dict): return  # state handler: no running gate (v5.4.1)
    snapshot_id = text(payload.get("snapshot_id"))
    if not snapshot_id: return
    _remember(atom._snapshots, snapshot_id, {
        "decision_id": payload.get("decision_id"),
        "gate_request_id": payload.get("gate_request_id"),
        "snapshot_status": text(payload.get("snapshot_status")),
        "usable_for_new_exposure": payload.get("usable_for_new_exposure") is True,
        "usable_for_protection": payload.get("usable_for_protection") is True,
        "produced_at": payload.get("produced_at"),
        "measured_at": time.time()})


async def on_reconcile(atom, payload: dict[str, Any]) -> None:
    if not isinstance(payload, dict): return  # state handler: no running gate (v5.4.1)
    account = text(payload.get("account_id")); broker = text(payload.get("broker")) or atom._broker_by_account.get(account, "")
    symbol = text(payload.get("asset_canonical") or payload.get("symbol"))
    if account and broker and symbol:
        atom._reconcile[(account, broker, symbol)] = text(payload.get("status")).upper()
        # ٢٠٢٦-١٠-٠٢ (ختم المالك «صلح كامل nq»): لحظةُ الاستلام **للحساب** لا للنطاق. 520 ينشر
        # نطاقًا حين يتغيّر وحده (مركزٌ فيه أو أمرٌ له)، وينشر للحساب كلّ لقطة مراكز (كلّ ثانية من
        # 609: «*» حين يفرغ، ونطاقات المراكز حين لا يفرغ) — فآخرُ حالةٍ لنطاقٍ ساكن صحيحةٌ ما دام
        # 520 يتكلّم عن الحساب، وعمرُ هذا الطابع هو الذي يقول «صمت» (تدقيق م-5).
        atom._reconcile_at[(account, broker)] = time.monotonic()


async def on_exposure(atom, payload: dict[str, Any]) -> None:
    if not isinstance(payload, dict): return  # state handler: no running gate (v5.4.1)
    account=text(payload.get("account_id"));broker=text(payload.get("broker")) or atom._broker_by_account.get(account,"")
    if account and broker:
        record = dict(payload)
        # ٢٠٢٦-١٠-٠٢ (ختم المالك «صلح كامل nq»): لحظةُ الاستلام تُختم كي يُقاس عمر
        # حالة 508 قبل أن يُبنى عليها سقف التعرّض (تدقيق م-5: «حالات بلا عمر»).
        record["_received_mono"] = time.monotonic()
        atom._exposure[(account,broker)] = record


# ٢٠٢٦-١٠-٠٢ (ختم المالك «صلح كامل nq»): حالة الأصل من 519 — كان 552 لا يسمعها، فتجميدُ
# الأصل ونفادُ ميزانيّته يحجبان مسار 581 وحده (`shared/position_delta_recompute.py:308-311`)
# ويمرّ دخول 555 فوقهما (تدقيق ح-3). وصفُّ 519 يحمل حكمَ دفتر 518 نفسه منسوخًا من كلّ
# دفترٍ يصله (`breached` = ‏`ledger.breached or u >= 1`، و`u` — `519/atom.py:284-312`)،
# فلا يُشترَك في `risk.asset_ledger.state` مباشرةً: ذلك يجعل 518⟷552 زوجًا راجعًا في
# الاتّجاهين (`execution.order.rejected` ذاهبٌ إلى 518) فيرفض مُجمِّع الخطّة الساخنة
# (`hot/planner.py:_refuse_two_way`) البناء — مقيسٌ بتشغيله. والشكلُ شكلُ 581
# (`581/atom.py:269-277`): الصفوف تحت `portfolios` أو الحمولة نفسها، والمفتاح (حساب، رمز).
async def on_portfolio(atom, payload: dict[str, Any]) -> None:
    """519 `asset.portfolio.state` ⟸ حالة كلّ أصل وحكمُ ميزانيّته — حالةٌ لا أمر."""
    if not isinstance(payload, dict): return  # state handler: no running gate (v5.4.1)
    rows = payload.get("portfolios")
    rows = rows if isinstance(rows, list) else ([payload] if payload.get("symbol") else [])
    for row in rows:
        if not isinstance(row, dict): continue
        account = text(row.get("account_id")); symbol = text(row.get("symbol") or row.get("asset_canonical"))
        if account and symbol:
            atom._portfolios[(account, symbol)] = {
                "state": text(row.get("state")).upper() or "UNKNOWN",
                "paused": row.get("paused") is True,
                "breached": row.get("breached") is True, "u": row.get("u"),
                "measured_at": time.time()}


async def on_reference(atom, payload: dict[str, Any]) -> None:
    if not isinstance(payload, dict): return  # state handler: no running gate (v5.4.1)
    symbol = text(payload.get("symbol"))
    if symbol:
        atom._reference[symbol] = text(payload.get("state") or payload.get("status")).upper()
        # ٢٠٢٦-١٠-٠٢ (ختم المالك «صلح كامل nq»): 521 ينشر كلّ رمزٍ مع كلّ نبضة ثانية — فالطابع
        # لكلّ رمز، وصمتُه يُقاس منه.
        atom._reference_at[symbol] = time.monotonic()
