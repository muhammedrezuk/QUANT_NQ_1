"""555 -- the waits after a trade (owner seal 2026-10-17, steps 10 and 11; sealed red lines 2026-10-23, laws 11 and 12).

Step 10 / law 12: after a trade on an asset ends in full (stop, target, red line or hand), no new entry on that asset in that
account for 75 minutes (15 until 2026-10-23) -- every asset keeps its own clock.
Step 11 / law 11 (the funder's rule, WeMasterTrade 3.3, one hour, plus our quarter): while a losing position on a symbol is open
in one account, no entry on that symbol in any *other* account; and after a losing trade closes, 75 minutes (one hour until
2026-10-23) before that symbol is traded in any other account.

The close moment is our official clock when 611 relays the broker's event (its `timestamp`), never the broker's own
`close_time` -- that one is the broker server clock, published as if UTC (measured +10,799 s on 2026-10-17).
"""
from __future__ import annotations

import time
from typing import Any

from shared import account_limits
from shared import owner_trades

SECONDS_PER_MINUTE = 60
#: 2026-10-23 (sealed red lines, laws 11-12): an hour and a quarter after every trade on the asset, and after a loss before the
#: symbol trades in another account -- "instead of an hour, an hour and a quarter, so no breach costs me an account".
WAIT_MINUTES = 75
AFTER_TRADE_WAIT_S = WAIT_MINUTES * SECONDS_PER_MINUTE
LOSS_OTHER_ACCOUNT_WAIT_S = WAIT_MINUTES * SECONDS_PER_MINUTE
EVENT_CLOSED = "CLOSED"
#: The reason names carry the length (the panel maps them to Arabic): "_15M" / "_1H" until 2026-10-23.
REASON_AFTER_TRADE = "WAIT_AFTER_TRADE_75M"
REASON_LOSS_OTHER_ACCOUNT = "WAIT_AFTER_LOSS_OTHER_ACCOUNT_75M"
REASON_LOSING_OPEN_OTHER = "LOSING_POSITION_OPEN_OTHER_ACCOUNT"
#: 2026-10-26 (owner's law and answer, seal "NQ": "it must know the owner's trades and open nothing on any pair that has a
#: trade of mine"): the one place the owner's trades are read -- any side, any account.
REASON_OWNER_POSITION = "OWNER_POSITION_OPEN"
#: Step 25's time-enough check (the target within the measured movement before the nearest red line) was dropped on
#: 2026-10-25 (owner seal, law 21): no new entry in the last hour of the window instead, in `shared.red_lines.entry_block`.
SEP = "|"
_COST_FIELDS = ("commission", "swap", "fee")
#: 2026-10-26 (owner seal "nq", after the project audit): a guard that does not know must refuse. The time and news gate
#: (`shared.red_lines.entry_block`, `shared.market_clock.no_trade_day`) failing to import let every entry through; and a
#: stalled official pulse (806) froze every time rule on its last second.
REASON_GATE_MISSING = "RED_LINES_GATE_MISSING"
REASON_PULSE_STALE = "CLOCK_PULSE_STALE"
#: The pulse is every second and the core cycle deadline is 5 s: twice that is a stalled clock, not a slow cycle.
PULSE_MAX_AGE_S = 10.0


def _num(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if result == result else None


def _key(account: Any, symbol: Any) -> str:
    return str(account or "").strip() + SEP + str(symbol or "").strip().upper()


def ensure(atom: Any) -> None:
    if not hasattr(atom, "_closed_at"):
        atom._closed_at = {}
        atom._lost_at = {}
        atom._losing_open = {}


def on_trade(atom: Any, payload: Any, now: float) -> None:
    """A full close starts the asset's 75-minute wait; a losing one also the 75-minute wait for the other accounts."""
    ensure(atom)
    if not isinstance(payload, dict) or str(payload.get("event_type") or "").upper() != EVENT_CLOSED:
        return
    account, symbol = payload.get("account_id"), payload.get("symbol")
    if not str(account or "").strip() or not str(symbol or "").strip():
        return
    stamp = _num(payload.get("timestamp")) or now
    key = _key(account, symbol)
    atom._closed_at[key] = stamp
    profit = _num(payload.get("profit"))
    if profit is not None and profit + sum(_num(payload.get(f)) or 0.0 for f in _COST_FIELDS) < 0.0:
        atom._lost_at[key] = stamp


def on_positions(atom: Any, payload: Any) -> None:
    """Which symbols the system holds at a loss, per account. The owner's positions are not counted here (2026-10-26,
    owner's law and answer): they are read in one place only, `entry_request_inputs.owner_on`."""
    ensure(atom)
    if not isinstance(payload, dict) or not isinstance(payload.get("positions"), list):
        return
    account = str(payload.get("account_id") or "").strip()
    losing: dict[str, set[str]] = {}
    for row in owner_trades.system_rows(payload["positions"]):
        if not isinstance(row, dict):
            continue
        owner = str(row.get("account_id") or account).strip()
        profit = _num(row.get("profit"))
        if owner and profit is not None and profit < 0.0:
            losing.setdefault(owner, set()).add(str(row.get("symbol") or "").strip().upper())
    if account:
        atom._losing_open[account] = losing.get(account, set())
    else:
        atom._losing_open = losing


def owner_on(atom: Any, symbol: Any) -> int:
    """The owner's open trades on the symbol, in every account (`entry_request_inputs.on_positions` keeps them apart)."""
    sym = str(symbol or "").strip()
    return sum(per_symbol.get(sym, 0) for per_symbol in getattr(atom, "_owner_by_account", {}).values())


def pulse_age_s(atom: Any) -> float | None:
    """Seconds since the last official pulse reached this atom (an internal age, the constitution's `received_at` kind),
    or None before the first one."""
    seen = getattr(atom, "_pulse_seen_at", 0.0)
    return time.monotonic() - seen if seen else None


def gate_block(atom: Any) -> str:
    """2026-10-26: the reason the time gate itself cannot judge this entry, or "" -- a missing gate module, or no
    official pulse within `PULSE_MAX_AGE_S` (none yet after a start counts as stale)."""
    if getattr(atom, "_gate_missing", False):
        return REASON_GATE_MISSING
    age = pulse_age_s(atom)
    if age is None or age > PULSE_MAX_AGE_S:
        return REASON_PULSE_STALE
    return ""


def wait_block(atom: Any, account: Any, symbol: Any, now: float) -> tuple[str, dict[str, Any]]:
    """The wait that blocks this entry, or ("", {}).

    2026-10-23 (sealed red lines, laws 7-10): first the account limits from 509 -- the total drawdown (until the owner
    releases it), the global daily limit and the pair's daily limit (until 00:00 Turkey); a missing or stale state, or an
    account whose figures are not known, refuses as well (`shared.account_limits.entry_block`)."""
    ensure(atom)
    limit, detail = account_limits.entry_block(getattr(atom, "_limits", None), account, symbol, now)
    if limit:
        return limit, detail
    owner_open = owner_on(atom, symbol)
    if owner_open:
        return REASON_OWNER_POSITION, {"owner_positions": owner_open}
    acc = str(account or "").strip()
    sym = str(symbol or "").strip().upper()
    closed = atom._closed_at.get(_key(acc, sym))
    if closed is not None and now - closed < AFTER_TRADE_WAIT_S:
        return REASON_AFTER_TRADE, {"remaining_s": round(AFTER_TRADE_WAIT_S - (now - closed), 1)}
    for other, symbols in atom._losing_open.items():
        if other != acc and sym in symbols:
            return REASON_LOSING_OPEN_OTHER, {"other_account": other}
    for key, lost in atom._lost_at.items():
        other, _, lost_sym = key.partition(SEP)
        if other != acc and lost_sym == sym and now - lost < LOSS_OTHER_ACCOUNT_WAIT_S:
            return REASON_LOSS_OTHER_ACCOUNT, {"other_account": other,
                                               "remaining_s": round(LOSS_OTHER_ACCOUNT_WAIT_S - (now - lost), 1)}
    return "", {}


def snapshot(atom: Any) -> dict[str, Any]:
    ensure(atom)
    return {"closed_at": dict(atom._closed_at), "lost_at": dict(atom._lost_at)}


def restore(atom: Any, state: Any, now: float) -> None:
    """Waits survive a restart; the expired ones are dropped."""
    ensure(atom)
    if not isinstance(state, dict):
        return
    for name, horizon in (("closed_at", AFTER_TRADE_WAIT_S), ("lost_at", LOSS_OTHER_ACCOUNT_WAIT_S)):
        raw = state.get(name)
        if not isinstance(raw, dict):
            continue
        kept = {str(k): float(v) for k, v in raw.items() if _num(v) is not None and now - float(v) < horizon}
        getattr(atom, "_" + name).update(kept)