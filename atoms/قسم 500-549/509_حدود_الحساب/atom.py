"""Account limits (owner's sealed red lines 2026-10-23, laws 7-10).

The settings -- the initial balance, each pair's trade risk and daily limit, the global daily limit and the total drawdown --
are the owner's, written by hand on the Control page and applied here through the command gate (constitution rule 14): one
bad value refuses the whole change and the old settings stay; the applied ones are kept in the snapshot. Every figure is a
share of the *initial* balance, by the one formula the backtest uses too (`shared.account_limits`).

2026-10-26 (owner's law, seal "NQ": "the trades I open have nothing to do with the system, ever -- it does not measure them,
record them or count them"; and his answer, seal "NQ": "I know how to run these things: the daily drawdown is 5%, I put 4
for you and 1 for me"): every limit here is the system's own. The owner's positions are dropped where the positions arrive,
by the one rule in `shared.owner_trades`, and the expert writes trade events for the system's magic only. Per account:
- today's realized result: the system's own trade events of the day with their costs -- opens (the entry commission),
  partial closes and closes (611), deduplicated by row; the day starts 00:00 Turkey;
- a pair's daily limit: that symbol's realized today plus its open positions' floating (profit and swap) -> that
  symbol's positions are closed and the symbol refused until 00:00;
- global daily limit (4%): the system's loss today, realized plus floating, from its own day base -- the higher of its own
  balance and its own equity where the day begins, as the funder computes its day, so a position crossing 00:00 counts
  once -> every open position of the system is closed, every entry refused until 00:00. The owner's 1% of the funder's 5%
  is his own to run;
- total drawdown (8%): the system's own equity -- its own balance (the account's balance when this rule began, less the
  owner's result of that day, then moved by the system's trade events alone) plus its floating -- at or under initial x
  (1 - total%) -> everything closed and refused, across midnight and restarts, until the owner releases it by hand.
  The owner did not name the total drawdown in his answer: it follows his law's general rule.
Measured on 2026-10-26: the owner's two manual Nasdaq trades (17:27-17:52, floating down to -610$) locked USTEC and the
whole account until 00:00, while the system had lost about 16$ that day. A book kept from before this rule (`rule`
missing) is reviewed once, as soon as the positions and the figures are known: a locked pair with no system trade today
and no system position, and a daily lock the system's own loss has not reached, are released (each in the error log),
then judged again at once on the system's figures; a total-drawdown stop is never released here.
The entry gate (555) refuses by `risk.account_limits.state`; 513 sizes each trade on the pair's fixed trade risk from it.
The owner's own positions are never closed here.

2026-10-26 (owner seal "nq", after the project audit): a guard that does not know must refuse.
- An account is known only while its balance and equity are fresh: measured (`measured_at`, official clock, from 619 via
  653/654) within `TRUTH_MAX_AGE_S`. The expert stamps the account row every second even when nothing changes, so a
  minute of silence is a frozen reader, not a quiet market. Unknown -> 555 refuses every entry on it; a limit already
  reached stays reached.
- 806's pulse silent past `PULSE_MAX_AGE_S` -> 003's heartbeat (the clock's other owner) judges the limits instead, and
  the health says so (DEGRADED: the fault is the clock atom's).
"""
from __future__ import annotations

import time
from typing import Any

from core.contracts.atom import AtomBase, HealthState, HealthStatus
from shared import account_limits as al
from shared import owner_trades
from shared.financial_truth import FinancialTruth, bind_truth

ATOM_VERSION = "1.2.0"
#: The book's rule: the system's own positions and trade events only (owner's law and answer, 2026-10-26).
LIMITS_RULE = "system_only"
#: The once-only review waits this long after a start, so a close already on its way from 611 is in the book first.
REVIEW_AFTER_S = 30.0
#: The events already on the system's own balance, by row -- a memory bound, kept across midnight (a row stamped
#: yesterday may arrive after the new day's first pulse, and a row is published again when its costs arrive).
APPLIED_MAX = 500
#: Trade events that arrive before the first pulse after a start, kept for it -- a memory bound.
EARLY_MAX = 1000
EVENT_PULSE = "SYS_SECOND"
EVENT_BACKUP_PULSE = "kernel.clock.heartbeat"
PULSE_MAX_AGE_S = 10.0
TRUTH_MAX_AGE_S = 60.0
TRUTH_FIELDS = ("balance", "equity")
WHY_STALE = "TRUTH_STALE"
WHY_MISSING = "TRUTH_MISSING"
PULSE_STALE = "PULSE_STALE"
EVENT_POSITIONS = "platform.positions.state"
EVENT_TRADE = "platform.trade_event"
EVENT_COMMAND = "risk.account_limits.command"
EVENT_STATE = "risk.account_limits.state"
EVENT_INTENT = "execution.manage.intent"
ACTION_CLOSE = "CLOSE"
SIDES = ("BUY", "SELL")
ORIGIN = "account_limits"
#: The day's realized events: the open carries the entry commission, the closes their result and costs.
REALIZED_EVENTS = ("OPENED", "CLOSED", "PARTIAL")
COST_FIELDS = ("commission", "swap", "fee")
FLOATING_FIELDS = ("profit", "swap")
COMMAND_SET = "SET"
COMMAND_RELEASE = "RELEASE_TOTAL"
DEFAULT_MAGIC = owner_trades.SYSTEM_MAGIC
DEFAULT_RESEND_S = 30.0
STATE_EVERY_S = 30.0
_DP = 2


def _num(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if result == result else None


def _text(value: Any) -> str:
    return str(value or "").strip()


class Atom(AtomBase):

    def __init__(self) -> None:
        self._context = None
        self._running = False
        self._magic = DEFAULT_MAGIC
        self._resend_s = DEFAULT_RESEND_S
        self._settings = al.normalize()
        self._truth = FinancialTruth("509")
        self._now = 0.0
        self._accounts: set[str] = set()
        self._positions: dict[str, dict[str, dict[str, Any]]] = {}
        self._books: dict[str, dict[str, Any]] = {}
        self._sent: dict[str, float] = {}
        self._last_state_at = 0.0
        self._last_signature: Any = None
        self._applied: dict[str, Any] = {"result": "", "at": 0.0}
        self._intents = 0
        # Monotonic arrivals (internal ages, not stamps): the last 806 pulse, or the start before the first one.
        self._pulse_seen_at = 0.0
        self._started_at = 0.0
        self._pulse_stale = False
        self._backup_judged = 0
        self._stale_truth: list[str] = []
        self._positions_seen: set[str] = set()
        self._released: list[str] = []
        self._early: list[dict[str, Any]] = []

    async def initialize(self, context: Any) -> None:
        self._context = context
        cfg = context.config or {}
        self._magic = int(cfg.get("magic", DEFAULT_MAGIC))
        self._resend_s = float(cfg.get("resend_after_s", DEFAULT_RESEND_S))
        self._settings = al.normalize(cfg)
        context.subscribe(EVENT_PULSE, self._on_pulse)
        context.subscribe(EVENT_BACKUP_PULSE, self._on_backup_pulse)
        context.subscribe(EVENT_POSITIONS, self._on_positions)
        context.subscribe(EVENT_TRADE, self._on_trade)
        context.subscribe(EVENT_COMMAND, self._on_command)
        bind_truth(self, context, self._truth, ("balance", "equity"), after=self._on_truth)

    async def start(self) -> None:
        self._started_at = time.monotonic()
        self._running = True

    async def stop(self) -> None:
        self._running = False

    async def shutdown(self) -> None:
        await self.stop()

    async def _on_truth(self, account: str) -> None:
        self._accounts.add(account)

    def _book(self, account: str) -> dict[str, Any]:
        # `system_balance` crosses midnight (the total drawdown does); the day's figures do not.
        book = self._books.setdefault(account, {"day": None, "base": None, "realized": {}, "daily": False,
                                                "pairs": [], "total": False, "rule": LIMITS_RULE, "review": [],
                                                "review_daily": False, "system_balance": None, "seed": "balance",
                                                "balance_since": None, "applied": {}, "sys_base": None,
                                                "day_balance0": None, "day_equity0": None, "day_tickets": []})
        day = al.turkey_day(self._now) if self._now > 0 else None
        if day is not None and book["day"] != day:
            book.update({"day": day, "base": None, "realized": {}, "daily": False, "pairs": [], "review": [],
                         "review_daily": False, "sys_base": None, "day_balance0": None, "day_equity0": None,
                         "day_tickets": []})
        return book

    async def _on_positions(self, payload: Any) -> None:
        if not isinstance(payload, dict) or not isinstance(payload.get("positions"), list):
            return
        account = _text(payload.get("account_id"))
        rows: dict[str, dict[str, dict[str, Any]]] = {}
        for row in owner_trades.system_rows(payload["positions"], self._magic):   # the owner's never enter
            if isinstance(row, dict) and _text(row.get("ticket")):
                owner = _text(row.get("account_id")) or account
                if owner:
                    rows.setdefault(owner, {})[_text(row.get("ticket"))] = row
        if account:
            self._positions[account] = rows.get(account, {})
            self._positions_seen.add(account)
        else:
            self._positions = rows
            self._positions_seen.update(rows)
        self._accounts.update(self._positions)
        alive = {acc + "|" + ticket for acc, tickets in self._positions.items() for ticket in tickets}
        self._sent = {key: at for key, at in self._sent.items() if key in alive}

    async def _on_trade(self, payload: Any) -> None:
        """Today's realized result per symbol -- opens, partial closes and closes with their costs, deduplicated by row --
        and the same amount on the system's own balance. The expert writes these for the system's magic only."""
        if not isinstance(payload, dict):
            return
        kind = _text(payload.get("event_type")).upper()
        account, symbol = _text(payload.get("account_id")), _text(payload.get("symbol")).upper()
        profit = _num(payload.get("profit"))
        if kind == "OPENED" and profit is None:
            profit = 0.0
        if kind not in REALIZED_EVENTS or not account or not symbol or profit is None:
            return
        if self._now <= 0:
            # Before the first pulse after a start, 611 already relays what it missed: kept, judged on the first pulse.
            if len(self._early) < EARLY_MAX:
                self._early.append(dict(payload))
            return
        stamp = _num(payload.get("timestamp"))
        key = _text(payload.get("source_row_id")) or "%s|%s|%s" % (kind, _text(payload.get("ticket")), stamp)
        net = profit + sum(_num(payload.get(name)) or 0.0 for name in COST_FIELDS)
        book = self._book(account)
        self._accounts.add(account)
        since = book.get("balance_since")
        applied = book.setdefault("applied", {})
        yesterday = stamp is not None and al.turkey_day(stamp) != al.turkey_day(self._now)
        if book["system_balance"] is not None and (key in applied or stamp is None or since is None or stamp >= since):
            # On the system's own balance once per row, whatever its day; a row published again moves it by its difference.
            delta = net - applied.pop(key, 0.0)
            book["system_balance"] = round(book["system_balance"] + delta, 6)
            if yesterday and book.get("sys_base") is not None:
                self._late_row(book, _text(payload.get("ticket")), delta)   # the day before's: not today's loss
            applied[key] = net
            while len(applied) > APPLIED_MAX:
                applied.pop(next(iter(applied)))
        if yesterday:
            return          # yesterday's row: on the balance, not in today's result
        book["realized"].setdefault(symbol, {})[key] = net

    async def _on_command(self, payload: Any) -> None:
        """The owner's hand (via 901): SET the settings, or RELEASE_TOTAL the total-drawdown stop."""
        command = _text(payload.get("command")).upper() if isinstance(payload, dict) else ""
        if command == COMMAND_SET:
            merged, why = al.merge(self._settings, payload.get("settings"))
            if merged is None:
                self._applied = {"result": "REFUSED", "reason": why, "at": self._now}
            else:
                self._settings = merged
                self._applied = {"result": "APPLIED", "at": self._now}
        elif command == COMMAND_RELEASE:
            target = _text(payload.get("account_id"))
            for account, book in self._books.items():
                if not target or account == target:
                    book["total"] = False
            self._applied = {"result": "RELEASED", "account_id": target or None, "at": self._now}
        else:
            self._applied = {"result": "REFUSED", "reason": "UNKNOWN_COMMAND", "at": self._now}
        self._last_signature = None
        await self._publish_state()

    def _truth_age_s(self, account: str) -> float | None:
        """The older of balance's and equity's age on the official clock; None if either was never stamped."""
        stamps = [self._truth.measured_at(account, field) for field in TRUTH_FIELDS]
        if any(stamp is None for stamp in stamps) or self._now <= 0:
            return None
        return self._now - min(stamps)

    def _evaluate(self, account: str) -> dict[str, Any]:
        book = self._book(account)
        balance, equity = self._truth.get(account, "balance"), self._truth.get(account, "equity")
        age = self._truth_age_s(account)
        if age is None or age > TRUTH_MAX_AGE_S:
            # Unknown, not "fine": no limit is judged on a figure of unknown age; one already reached stays reached.
            balance = equity = None
        floating: dict[str, float] = {}
        for row in self._positions.get(account, {}).values():
            symbol = _text(row.get("symbol")).upper()
            floating[symbol] = floating.get(symbol, 0.0) + sum(_num(row.get(name)) or 0.0 for name in FLOATING_FIELDS)
        realized = {symbol: sum(rows.values()) for symbol, rows in book["realized"].items()}
        pair_loss = {symbol: round(-(realized.get(symbol, 0.0) + floating.get(symbol, 0.0)), _DP)
                     for symbol in set(floating) | set(realized)}
        known = balance is not None and equity is not None
        if book["system_balance"] is not None and book.get("sys_base") is None:
            # The system's own day base, as the funder computes its day: the higher of its own balance and its own equity
            # where the day begins -- so a position crossing 00:00 counts once, in the day it was open. Set on the day's
            # first pulse even while the account's figures are unknown: the system's own figures do not need them.
            self._start_day(book, account, floating)
        view = {"known": known, "balance": balance, "equity": equity,
                "pair_loss": pair_loss, "daily_limit": round(al.daily_limit(self._settings), _DP),
                "floor": round(al.total_floor(self._settings), _DP),
                "truth_age_s": round(age, 1) if age is not None else None}
        if not known:
            view["why"] = WHY_MISSING if age is None else WHY_STALE
        if known:
            if book["base"] is None:
                book["base"] = al.day_base(balance, equity)
            if book["system_balance"] is None:
                self._start_system_balance(book, balance)
            system_equity = round(book["system_balance"] + sum(floating.values()), _DP)
            if book.get("sys_base") is None:     # the very first figures of a new book
                self._start_day(book, account, floating)
            day_loss = round(max(0.0, book["sys_base"] - system_equity), _DP)
            view.update({"day_loss": day_loss, "system_balance": round(book["system_balance"], _DP),
                         "system_equity": system_equity, "system_day_base": round(book["sys_base"], _DP)})
            if (account in self._positions_seen and (book.get("review") or book.get("review_daily"))
                    and time.monotonic() - self._started_at >= REVIEW_AFTER_S):
                self._review(account, book, floating, day_loss, view["daily_limit"])
            if day_loss >= view["daily_limit"]:
                book["daily"] = True
            if system_equity <= view["floor"]:
                book["total"] = True
        for symbol, loss in pair_loss.items():
            if loss >= al.pair_daily_limit(self._settings, symbol) and symbol not in book["pairs"]:
                book["pairs"].append(symbol)
        view.update({"day_base": book["base"], "daily_blocked": book["daily"], "total_blocked": book["total"],
                     "blocked_pairs": sorted(book["pairs"]),
                     "pair_limit": {s: round(al.pair_daily_limit(self._settings, s), _DP) for s in pair_loss}})
        return view

    def _start_day(self, book: dict[str, Any], account: str, floating: dict[str, float]) -> None:
        """Where the system's day begins: its own balance, its own equity, and the tickets it held then."""
        book["day_balance0"] = round(book["system_balance"], 6)
        book["day_equity0"] = round(book["system_balance"] + sum(floating.values()), 6)
        book["day_tickets"] = sorted(self._positions.get(account, {}))
        book["sys_base"] = max(book["day_balance0"], book["day_equity0"])

    def _late_row(self, book: dict[str, Any], ticket: str, delta: float) -> None:
        """A row of the day before, arriving after the day began (review 2026-10-26, rounds three and four): it moves the
        day's starting balance; and the starting equity too, unless its position was still open in the day's first
        picture -- then its result was already in that equity as floating."""
        balance0 = book.get("day_balance0")
        equity0 = book.get("day_equity0")
        if balance0 is None or equity0 is None:
            book["sys_base"] = round(book["sys_base"] + delta, 6)
            return
        book["day_balance0"] = round(balance0 + delta, 6)
        if ticket not in (book.get("day_tickets") or []):
            book["day_equity0"] = round(equity0 + delta, 6)
        book["sys_base"] = max(book["day_balance0"], book["day_equity0"])

    def _start_system_balance(self, book: dict[str, Any], balance: float) -> None:
        """The system's own balance where this rule begins. From a day already running (a book kept from before the rule):
        the day's base and the system's own result since it -- the owner's result of the day stays out -- and every later
        row of the day moves it. Otherwise: the balance now, and every later row moves it."""
        if book.get("seed") == "day_base" and book["base"] is not None:
            rows = {key: net for per_symbol in book["realized"].values() for key, net in per_symbol.items()}
            book["system_balance"] = round(book["base"] + sum(rows.values()), 6)
            book["balance_since"] = book["day"] * al.DAY_S - al.TURKEY_OFFSET_S
            book["applied"] = dict(rows)
        else:
            # The rows of the day already seen are in the balance now: on the book as applied, so one published again
            # moves it by its difference only (review 2026-10-26, round three).
            book["system_balance"] = round(balance, 6)
            book["balance_since"] = self._now
            book["applied"] = {key: net for per_symbol in book["realized"].values() for key, net in per_symbol.items()}

    def _review(self, account: str, book: dict[str, Any], floating: dict[str, float], day_loss: float,
                daily_limit: float) -> None:
        """Once, on a book kept from before the system-only rule: a locked pair with no system trade today and no system
        position can only have been locked by the owner's positions, and a daily lock the system's own loss has not
        reached can only have come from the owner's -- they are released and logged; the rest stay. Both are judged
        again right after on the system's figures, so a real system lock comes back at once."""
        logger = getattr(self._context, "logger", None)
        for symbol in list(book["review"]):
            if symbol in book["pairs"] and not book["realized"].get(symbol) and symbol not in floating:
                book["pairs"].remove(symbol)
                self._released.append("%s:%s" % (account, symbol))
                if logger is not None:
                    logger.warning("509 حدّ الزوج %s على الحساب %s فُكّ: لا صفقة للمنظومة عليه اليوم ولا مركز — قفله من "
                                   "صفقات المالك (قانون صفقات المالك وجوابه ٢٦/١٠)", symbol, account)
        if book.get("review_daily") and book["daily"] and day_loss < daily_limit:
            book["daily"] = False
            self._released.append("%s:DAILY" % account)
            if logger is not None:
                logger.warning("509 الحدّ اليوميّ للحساب %s فُكّ: خسارة المنظومة اليوم %.2f$ دون حدّها %.2f$ — قفله من "
                               "صفقات المالك (قانون صفقات المالك وجوابه ٢٦/١٠)", account, day_loss, daily_limit)
        book["review"] = []
        book["review_daily"] = False

    def _reason_for(self, view: dict[str, Any], symbol: str) -> str:
        if view["total_blocked"]:
            return al.REASON_TOTAL
        if view["daily_blocked"]:
            return al.REASON_DAILY
        return al.REASON_PAIR if symbol in view["blocked_pairs"] else ""

    async def _close(self, account: str, view: dict[str, Any]) -> None:
        # Only the system's positions are kept (`_on_positions`): the owner's are never closed here.
        for ticket, row in self._positions.get(account, {}).items():
            symbol = _text(row.get("symbol")).upper()
            side = _text(row.get("side")).upper()
            reason = self._reason_for(view, symbol)
            key = account + "|" + ticket
            last = self._sent.get(key)
            if not reason or side not in SIDES or (last is not None and self._now - last < self._resend_s):
                continue
            self._sent[key] = self._now
            self._intents += 1
            await self._context.publish(EVENT_INTENT, {
                "account_id": account, "ticket": row.get("ticket"), "symbol": _text(row.get("symbol")), "side": side,
                "action": ACTION_CLOSE, "reason": reason, "origin": ORIGIN})

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
        """003's heartbeat judges the limits only while 806's pulse has been silent past `PULSE_MAX_AGE_S`."""
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

    async def _judge(self, official: float) -> None:
        self._now = official
        if self._early:
            early, self._early = self._early, []
            for payload in early:
                await self._on_trade(payload)
        views = {account: self._evaluate(account) for account in sorted(self._accounts)}
        self._stale_truth = sorted(a for a, v in views.items() if not v["known"])
        for account, view in views.items():
            await self._close(account, view)
        signature = {a: (v["known"], v["daily_blocked"], v["total_blocked"], tuple(v["blocked_pairs"]))
                     for a, v in views.items()}
        if signature != self._last_signature or official - self._last_state_at >= STATE_EVERY_S:
            self._last_signature = signature
            await self._publish_state(views)

    async def _publish_state(self, views: dict[str, Any] | None = None) -> None:
        if self._context is None:
            return
        if views is None:
            views = {account: self._evaluate(account) for account in sorted(self._accounts)}
        self._last_state_at = self._now
        await self._context.publish(EVENT_STATE, {
            "id": "account_limits", "official_time": self._now, "settings": self._settings,
            "trade_risk": {s: round(al.trade_risk(self._settings, s), _DP) for s in al.TRADED},
            "accounts": views, "applied": dict(self._applied), "close_intents": self._intents})

    async def snapshot(self) -> dict[str, Any]:
        keys = ("day", "base", "realized", "daily", "pairs", "total", "rule", "review", "review_daily", "system_balance",
                "seed", "balance_since", "applied", "sys_base", "day_balance0", "day_equity0", "day_tickets")
        books = {a: {k: b.get(k) for k in keys} for a, b in self._books.items()}
        return {"version": ATOM_VERSION, "settings": self._settings, "books": books, "intents": self._intents,
                "released": list(self._released)}

    async def restore(self, state: Any) -> None:
        """The owner's settings and today's books survive a restart; the total-drawdown stop and the system's own balance
        survive any day. A book from before the system-only rule is reviewed once (`_review`), and the system's own balance
        starts from its day's base."""
        if not isinstance(state, dict):
            return
        if isinstance(state.get("settings"), dict):
            self._settings = al.normalize(state["settings"])
        for account, book in (state.get("books") or {}).items():
            if isinstance(book, dict):
                pairs = list(book.get("pairs") or [])
                old_rule = book.get("rule") != LIMITS_RULE
                self._books[str(account)] = {
                    "day": book.get("day"), "base": _num(book.get("base")), "realized": dict(book.get("realized") or {}),
                    "daily": bool(book.get("daily")), "pairs": pairs, "total": bool(book.get("total")), "rule": LIMITS_RULE,
                    "review": list(pairs) if old_rule else list(book.get("review") or []),
                    "review_daily": bool(book.get("daily")) if old_rule else bool(book.get("review_daily")),
                    "system_balance": None if old_rule else _num(book.get("system_balance")),
                    "seed": "day_base" if old_rule else str(book.get("seed") or "balance"),
                    "balance_since": None if old_rule else _num(book.get("balance_since")),
                    "applied": {} if old_rule else {str(k): float(v) for k, v in (book.get("applied") or {}).items()
                                                    if _num(v) is not None},
                    # A day already running under the old rule began on the account's own base (no system position
                    # crossed into it unseen); a new book keeps its own.
                    "sys_base": _num(book.get("base")) if old_rule else _num(book.get("sys_base")),
                    "day_balance0": _num(book.get("base")) if old_rule else _num(book.get("day_balance0")),
                    "day_equity0": _num(book.get("base")) if old_rule else _num(book.get("day_equity0")),
                    "day_tickets": [] if old_rule else [str(x) for x in (book.get("day_tickets") or [])]}
                self._accounts.add(str(account))
        self._intents = int(_num(state.get("intents")) or 0)
        self._released = [str(x) for x in (state.get("released") or []) if isinstance(x, str)]

    async def health_check(self) -> HealthStatus:
        if not self._running:
            return HealthStatus(state=HealthState.UNHEALTHY, message="NOT_STARTED")
        stopped = sorted(a for a, b in self._books.items() if b.get("total"))
        daily = sorted(a for a, b in self._books.items() if b.get("daily"))
        message = "initial=%s daily=%s%% total=%s%% accounts=%d total_stop=%s daily_stop=%s intents=%d applied=%s" % (
            self._settings[al.INITIAL_BALANCE], self._settings[al.DAILY_PCT], self._settings[al.TOTAL_PCT],
            len(self._accounts), ",".join(stopped) or "-", ",".join(daily) or "-", self._intents,
            self._applied.get("result") or "-")
        stale_pulse = self._pulse_stale or self._pulse_age_s() > PULSE_MAX_AGE_S
        if self._stale_truth:
            message = "TRUTH_UNKNOWN %s (no entry) | %s" % (",".join(self._stale_truth), message)
        if stale_pulse:
            message = "%s 806 silent %.0fs, judged on 003 x%d | %s" % (
                PULSE_STALE, self._pulse_age_s(), self._backup_judged, message)
        state = (HealthState.DEGRADED if stopped or daily or not self._accounts or self._stale_truth or stale_pulse
                 else HealthState.HEALTHY)
        return HealthStatus(state=state, message=message, details={
            "total_stop": stopped, "daily_stop": daily, "truth_unknown": list(self._stale_truth),
            "pulse_stale": stale_pulse, "backup_judged": self._backup_judged})
