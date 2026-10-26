"""Red lines (owner seal 2026-10-17; sealed red lines 2026-10-23): every open position of ours is closed in full, at any
price, on its asset's red line; the owner's own (foreign magic) are left alone.

A red line is (1) the end of the asset's own exchange window and all the time after it until the next one -- Saturday and
Sunday included for every symbol, bitcoin too (law 23) -- or (2) a red news window of a currency the asset holds, 15 minutes
either side, USD for every symbol (laws 24-25), as atom 109 announces it in `blocked_currencies`. The rule itself lives in
`shared.red_lines`, the same function the entry gate (555) refuses entries with. The close goes out as a management intent;
570 owns the command, its retries and its ownership checks.

2026-10-26 (owner seal "nq", after the project audit): the lines were judged on 806's second pulse alone, so a stalled
pulse froze them on its last second -- no close at a window's end or before a red news. When 806 has been silent for
`PULSE_MAX_AGE_S`, 003's heartbeat (the clock's other owner, every second, the same official time) judges them instead,
and the health says so (DEGRADED: the fault is the clock atom's, restarting this one would not mend it).

2026-10-26 (owner seal "NQ": "it no longer has access to the calendar and agenda -- close every trade and stop"): a calendar
that does not know -- no state, older than two minutes, or 109 saying it does not know -- is a red line too
(`NEWS_CALENDAR_UNKNOWN`): every position of ours is closed, and 555 refuses every entry on the same rule. Not in the first
`UNKNOWN_GRACE_S` after a start: 109's first state may still be on its way, and a boot must not close what a restart found.

2026-10-26 (owner's law, seal "NQ": "the trades I open have nothing to do with the system, ever -- it does not measure them,
record them or count them"): the owner's positions were kept here, counted in `open_positions` and tallied as `foreign`, and
only skipped at the close. Now they are dropped where the positions arrive, by the one rule in `shared.owner_trades`: never
closed, never kept, never counted.
"""
from __future__ import annotations

import time
from typing import Any

from core.contracts.atom import AtomBase, HealthState, HealthStatus
from shared import owner_trades
from shared.red_lines import REASON_NEWS, REASON_NEWS_UNKNOWN, REASON_WINDOW, news_unknown, red_line

ATOM_VERSION = "1.4.0"
UNKNOWN_GRACE_S = 120.0
EVENT_PULSE = "SYS_SECOND"
EVENT_BACKUP_PULSE = "kernel.clock.heartbeat"
PULSE_MAX_AGE_S = 10.0
PULSE_STALE = "PULSE_STALE"
EVENT_POSITIONS = "platform.positions.state"
EVENT_CALENDAR = "market_data.calendar.state"
EVENT_INTENT = "execution.manage.intent"
EVENT_STATE = "risk.red_line.state"
ACTION_CLOSE = "CLOSE"
SIDES = ("BUY", "SELL")
ORIGIN = "red_line"
LINE_CLEAR = "CLEAR"
DEFAULT_MAGIC = owner_trades.SYSTEM_MAGIC
DEFAULT_RESEND_S = 30.0
STATE_EVERY_S = 30.0


def _num(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if result == result else None


def _line_for(now: float, calendar: Any, symbol: Any) -> str | None:
    """The asset's own red line; an older shared module still in memory (a reload before the restart) knows only the
    general window -- it is used rather than failing every pulse."""
    try:
        return red_line(now, calendar, symbol)
    except TypeError:
        return red_line(now, calendar)


def _int(value: Any) -> int | None:
    number = _num(value)
    return int(number) if number is not None else None


class Atom(AtomBase):

    def __init__(self) -> None:
        self._context = None
        self._running = False
        self._magic = DEFAULT_MAGIC
        self._resend_s = DEFAULT_RESEND_S
        self._now = 0.0
        self._calendar: dict[str, Any] | None = None
        self._positions: dict[str, dict[str, dict[str, Any]]] = {}
        self._sent: dict[str, float] = {}
        self._line = ""
        self._last_state_at = 0.0
        self._intents = 0
        self._lines = {REASON_WINDOW: 0, REASON_NEWS: 0}
        self._last_close = ""
        # Monotonic arrivals (internal ages, not stamps): the last 806 pulse, or the start before the first one.
        self._pulse_seen_at = 0.0
        self._started_at = 0.0
        self._pulse_stale = False
        self._backup_judged = 0

    async def initialize(self, context: Any) -> None:
        self._context = context
        cfg = context.config or {}
        self._magic = int(cfg.get("magic", DEFAULT_MAGIC))
        self._resend_s = float(cfg.get("resend_after_s", DEFAULT_RESEND_S))
        context.subscribe(EVENT_PULSE, self._on_pulse)
        context.subscribe(EVENT_BACKUP_PULSE, self._on_backup_pulse)
        context.subscribe(EVENT_POSITIONS, self._on_positions)
        context.subscribe(EVENT_CALENDAR, self._on_calendar)

    async def start(self) -> None:
        self._started_at = time.monotonic()
        self._running = True

    async def stop(self) -> None:
        self._running = False

    async def shutdown(self) -> None:
        await self.stop()

    async def _on_calendar(self, payload: Any) -> None:
        if isinstance(payload, dict):
            self._calendar = dict(payload)

    async def _on_positions(self, payload: Any) -> None:
        if not isinstance(payload, dict) or not isinstance(payload.get("positions"), list):
            return
        account = str(payload.get("account_id") or "").strip()
        rows: dict[str, dict[str, dict[str, Any]]] = {}
        for row in owner_trades.system_rows(payload["positions"], self._magic):   # the owner's never enter
            if not isinstance(row, dict):
                continue
            owner = str(row.get("account_id") or account).strip()
            ticket = str(row.get("ticket") or "").strip()
            if owner and ticket:
                rows.setdefault(owner, {})[ticket] = row
        if account:
            self._positions[account] = rows.get(account, {})
        else:
            self._positions = rows
        alive = {acc + "|" + ticket for acc, tickets in self._positions.items() for ticket in tickets}
        self._sent = {key: at for key, at in self._sent.items() if key in alive}

    async def _on_pulse(self, payload: Any) -> None:
        if not self._running or self._context is None or not isinstance(payload, dict):
            return
        official = _num(payload.get("official_time"))
        if official is None or official <= 0:
            return
        self._pulse_seen_at = time.monotonic()
        self._pulse_stale = False
        await self._judge(official)

    def _pulse_age_s(self) -> float:
        return time.monotonic() - (self._pulse_seen_at or self._started_at)

    async def _on_backup_pulse(self, payload: Any) -> None:
        """003's heartbeat judges the lines only while 806's pulse has been silent past `PULSE_MAX_AGE_S`."""
        if not self._running or self._context is None or not isinstance(payload, dict):
            return
        if self._pulse_age_s() <= PULSE_MAX_AGE_S:
            return
        official = _num(payload.get("official_time"))
        if official is None or official <= 0:
            return
        self._pulse_stale = True
        self._backup_judged += 1
        await self._judge(official)

    def _line_now(self, now: float, symbol: Any = None) -> str | None:
        """The red line now -- for the asset when a symbol is given, else the general one shown in the state -- and the
        unknown calendar once the start's grace is over."""
        line = _line_for(now, self._calendar, symbol) if symbol is not None else red_line(now, self._calendar)
        if line:
            return line
        if time.monotonic() - self._started_at > UNKNOWN_GRACE_S and news_unknown(self._calendar, now):
            return REASON_NEWS_UNKNOWN
        return None

    async def _judge(self, official: float) -> None:
        self._now = official
        line = self._line_now(official) or ""
        if line != self._line:
            self._line = line
            if line:
                self._lines[line] = self._lines.get(line, 0) + 1
            await self._publish_state()
        elif official - self._last_state_at >= STATE_EVERY_S:
            await self._publish_state()
        await self._close_all()

    async def _close_all(self) -> None:
        # 2026-10-17 (owner seal, step 6): every position on its own asset's window -- the Nasdaq closes with New York,
        # the euro with London, bitcoin and gold on the general window (shared.red_lines.session_of).
        for account, tickets in self._positions.items():
            for ticket, row in tickets.items():
                key = account + "|" + ticket
                side = str(row.get("side") or "").strip().upper()
                line = self._line_now(self._now, row.get("symbol"))
                if not line or side not in SIDES:
                    continue
                last = self._sent.get(key)
                if last is not None and self._now - last < self._resend_s:
                    continue
                self._sent[key] = self._now
                self._intents += 1
                symbol = str(row.get("symbol") or "")
                self._last_close = "%s %s %s (%s)" % (symbol, side, ticket, line)
                await self._context.publish(EVENT_INTENT, {
                    "account_id": account, "ticket": row.get("ticket"), "symbol": symbol, "side": side,
                    "action": ACTION_CLOSE, "reason": line, "origin": ORIGIN})

    def _open_count(self) -> int:
        return sum(len(tickets) for tickets in self._positions.values())

    async def _publish_state(self) -> None:
        self._last_state_at = self._now
        await self._context.publish(EVENT_STATE, {
            "id": "red_line", "line": self._line or LINE_CLEAR, "active": bool(self._line),
            "open_positions": self._open_count(), "close_intents": self._intents, "official_time": self._now})

    async def snapshot(self) -> dict[str, Any]:
        return {"version": ATOM_VERSION, "intents": self._intents, "lines": dict(self._lines),
                "last_close": self._last_close}

    async def restore(self, state: Any) -> None:
        if not isinstance(state, dict):
            return
        self._intents = _int(state.get("intents")) or 0
        if isinstance(state.get("lines"), dict):
            self._lines.update({str(k): _int(v) or 0 for k, v in state["lines"].items()})
        self._last_close = str(state.get("last_close") or "")

    async def health_check(self) -> HealthStatus:
        if not self._running:
            return HealthStatus(state=HealthState.UNHEALTHY, message="NOT_STARTED")
        message = "line=%s open=%d intents=%d window=%d news=%d last=%s" % (
            self._line or LINE_CLEAR, self._open_count(), self._intents, self._lines.get(REASON_WINDOW, 0),
            self._lines.get(REASON_NEWS, 0), self._last_close or "-")
        stale = self._pulse_stale or self._pulse_age_s() > PULSE_MAX_AGE_S
        if stale:
            message = "%s 806 silent %.0fs, judged on 003 x%d | %s" % (
                PULSE_STALE, self._pulse_age_s(), self._backup_judged, message)
        return HealthStatus(state=HealthState.DEGRADED if stale else HealthState.HEALTHY, message=message,
                            details={"line": self._line or LINE_CLEAR, "intents": self._intents,
                                     "pulse_stale": stale, "backup_judged": self._backup_judged})
