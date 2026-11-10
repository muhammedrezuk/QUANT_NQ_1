"""415 The comprehensive combination: the owner's sealed strategy card (owner seals 2026-10-17 and 2026-10-18, "NQ").

Direction: Dow theory on four hours (209, readings.four_hours.trend), and the owner's EMA 5/10/50 order on the quarter
hour must point the same way (5 above 10 above 50 is rising, the mirror is falling). The decision is taken at every live
quarter-hour close, inside the asset's trading window and after its first minutes (shared.red_lines), with no open
position on the symbol and not before fifteen minutes after the last one closed. Stop: behind the last external swing
of 202 on 5m, then 15m, then 1m, inside the stop band (Nasdaq 20-45 pips). Target: 3R net of the spread; the owner's
thirds (574) close the first third at 1R with the stop to entry and half the rest at 2R with the stop to 1R. News, the
closing line and the time-enough rule stay with the gate (555) and the closer (565). It sends exactly like the facts
strategies: strategy.setup.proposed then decision.approved.state. It sends only while shared/strategy_switch.json names it.
Measured in the backtest page on 2023 (Nasdaq): +5.75% with a 15-pip minimum stop, +10.8% with 20.
"""
from __future__ import annotations

import asyncio
import sqlite3
import time
from pathlib import Path
from typing import Any

from core.contracts.atom import AtomBase, AtomContext, HealthState, HealthStatus
from shared import facts_strategies as FS
from shared import red_lines, strategy_switch
from shared.pips import from_pips, to_pips
from shared.trade_setup import build_setup
# ٢٠٢٦-١٠-٢٦ (قانون صفقات المالك وجوابه، ختم «NQ»): الرموز المفتوحة هنا مراكز المنظومة وحدها. كانت مراكز المالك تدخلها،
# فلا تقترح البطاقة على رمزه، وتعدّ إغلاقه إغلاقًا لها فتنتظر بعده ربع ساعة. ومنعُ الدخول على رمزٍ عليه صفقةٌ للمالك
# موضعه الواحد طالب الدخول ٥٥٥.
from shared import owner_trades

ATOM_ID = "415"
ATOM_VERSION = "1.3.0"
EV_CANDLE = "market_data.candle_closed"
EV_TICK = "market.tick.validated"
EV_ACCOUNT = "platform.account.state"
EV_POSITIONS = "platform.positions.state"
EV_STRUCTURE = "structure.external.state"
EV_DOW = "structure.dow.state"
EV_SETUP = "strategy.setup.proposed"
EV_APPROVED = "decision.approved.state"
NAME = "comprehensive_combination"
NAME_AR = "التوليفة الشاملة"
SETUP_TYPE = "TREND_CONTINUATION_PULLBACK"
FRAME, FRAME_S = "15m", 900.0
EMA_PERIODS = (5, 10, 50)
EMA_WARM_BARS = 150
KEEP_BARS = 600
DOW_READING = "four_hours"
RISING, FALLING, NONE = "rising", "falling", "none"
WAIT_AFTER_CLOSE_S = 900.0
FACT_DELAY_S = 2.0
SETUP_TTL_S = 120.0
#: The gate (555) re-checks (reward - spread) / (risk + spread) >= 3 at the send price, seconds after the build. A move of d
#: toward the target in between costs that ratio: it holds while target >= 3R + 4(d + spread). Owner seal 2026-10-19 "NQ":
#: build on the executable price and leave room for a move of a tenth of the stop (US500 2026-10-19: 0.85 on 10.4).
SEND_DRIFT_FRACTION = 0.10
#: The EMAs need 150 quarter-hour closes; a reload empties memory and the chart provider (107) replays only at boot, so the card
#: reads the last closes itself from the same read-only history store 107 replays from (2026-10-19).
HISTORY_DB = Path(__file__).resolve().parents[3] / "forex_runtime" / "var" / "history" / "ctrader_history.db"
DEFAULT_SYMBOLS = ("USTEC", "US30", "US500", "XAUUSD", "BTCUSD", "EURUSD", "GBPUSD")
#: The owner's 20-pip Nasdaq floor (seal 2026-10-17); the same band is in facts_strategies.STOP_PIPS, live after a restart.
STOP_BAND_PIPS = dict(FS.STOP_PIPS, USTEC=(20.0, 45.0))


def ema_order(closes: list[float]) -> str:
    """Order of the EMAs 5/10/50 after the last close, built as the backtest builds it (seeded on the first close)."""
    if len(closes) < EMA_WARM_BARS:
        return NONE
    alphas = [2.0 / (n + 1.0) for n in EMA_PERIODS]
    vals = [closes[0]] * len(EMA_PERIODS)
    for c in closes[1:]:
        vals = [a * c + (1.0 - a) * v for a, v in zip(alphas, vals)]
    if vals[0] > vals[1] > vals[2]:
        return RISING
    if vals[0] < vals[1] < vals[2]:
        return FALLING
    return NONE


def stop_for(book: FS.FactBook, symbol: str, side: int, entry: float) -> tuple[float, float, str] | None:
    """Behind the last external swing low/high (202) on 5m, then 15m, then 1m, inside the stop band; else no trade."""
    lo_p, hi_p = STOP_BAND_PIPS.get(symbol, FS.STOP_PIPS_DEFAULT)
    lo, hi = from_pips(lo_p, symbol), from_pips(hi_p, symbol)
    pad = from_pips(FS.STOP_PAD_PIPS.get(symbol, FS.STOP_PAD_PIPS_DEFAULT), symbol)
    for tf in FS.STOP_FRAMES:
        lvl = FS.num(book.at("202", symbol, tf, "swing_low" if side > 0 else "swing_high"))
        if lvl is None:
            continue
        stop = lvl - pad if side > 0 else lvl + pad
        risk = (entry - stop) * side
        if lo <= risk <= hi:
            return stop, risk, tf
    return None


class Atom(AtomBase):

    def __init__(self) -> None:
        self._context: AtomContext | None = None
        self._running = False
        self._symbols: set[str] = set(DEFAULT_SYMBOLS)
        self._book = FS.FactBook()
        self._bars: dict[str, dict[float, float]] = {}
        self._dow: dict[str, tuple[float, str]] = {}
        self._account: dict[str, Any] = {}
        self._open: set[str] = set()
        self._positions_seen = False
        self._closed_at: dict[str, float] = {}
        self._spread: dict[str, float] = {}
        self._quote: dict[str, tuple[float, float]] = {}
        self._drift = SEND_DRIFT_FRACTION
        self._tally: dict[str, int] = {}
        self._last: dict[str, dict[str, Any]] = {}
        self._tasks: set[asyncio.Task] = set()
        self._last_error = ""
        self._clock = time.time

    async def initialize(self, context: AtomContext) -> None:
        self._context = context
        self._drift = float((context.config or {}).get("send_drift_fraction", SEND_DRIFT_FRACTION))
        syms = (context.config or {}).get("symbols")
        if isinstance(syms, list) and syms:
            self._symbols = {str(s).upper() for s in syms}
        if (context.config or {}).get("seed_history", True):
            self._seed_history()
        context.subscribe(EV_CANDLE, self._on_candle)
        context.subscribe(EV_TICK, self._on_tick)
        context.subscribe(EV_ACCOUNT, self._on_account)
        context.subscribe(EV_POSITIONS, self._on_positions)
        context.subscribe(EV_STRUCTURE, self._on_structure)
        context.subscribe(EV_DOW, self._on_dow)

    def _seed_history(self) -> None:
        try:
            con = sqlite3.connect("file:%s?mode=ro" % HISTORY_DB, uri=True, timeout=5)
            try:
                for symbol in self._symbols:
                    rows = con.execute("select period_start, close from candles_history where symbol=? and period=? and "
                                       "period_start<=? order by period_start desc limit ?",
                                       (symbol, "M15", self._clock() - FRAME_S, KEEP_BARS)).fetchall()
                    bars = self._bars.setdefault(symbol, {})
                    for start, close in rows:
                        bars.setdefault(float(start), float(close))
            finally:
                con.close()
        except sqlite3.Error as exc:  # no store: the bars come from the feed as before
            self._last_error = "history seed: %s" % exc

    async def start(self) -> None:
        self._running = True

    async def stop(self) -> None:
        self._running = False
        for task in list(self._tasks):
            task.cancel()

    async def shutdown(self) -> None:
        await self.stop()

    def _bump(self, key: str) -> None:
        self._tally[key] = self._tally.get(key, 0) + 1

    async def _on_account(self, p: Any) -> None:
        if isinstance(p, dict) and p.get("account_id"):
            self._account = {"account_id": p.get("account_id"), "broker": p.get("broker") or self._account.get("broker")}

    async def _on_positions(self, p: Any) -> None:
        if not isinstance(p, dict) or not isinstance(p.get("positions"), list):
            return
        now = {str(r.get("symbol") or "").upper() for r in owner_trades.system_rows(p["positions"]) if isinstance(r, dict)}
        if self._positions_seen:
            for symbol in self._open - now:
                self._closed_at[symbol] = self._clock()
        self._open, self._positions_seen = now, True

    async def _on_tick(self, p: Any) -> None:
        if not isinstance(p, dict):
            return
        bid, ask = FS.num(p.get("bid")), FS.num(p.get("ask"))
        symbol = str(p.get("symbol") or "").upper()
        if symbol and bid is not None and ask is not None and ask > bid:
            self._spread[symbol] = ask - bid
            self._quote[symbol] = (bid, ask)

    async def _on_structure(self, p: Any) -> None:
        if isinstance(p, dict):
            self._book.put(EV_STRUCTURE, p, self._clock())

    async def _on_dow(self, p: Any) -> None:
        if not isinstance(p, dict):
            return
        symbol, start = str(p.get("symbol") or "").upper(), FS.num(p.get("period_start"))
        reading = ((p.get("readings") or {}).get(DOW_READING) or {}).get("trend")
        if symbol and start is not None:
            self._dow[symbol] = (start, str(reading or NONE))

    async def _on_candle(self, p: Any) -> None:
        if not isinstance(p, dict) or str(p.get("timeframe")) != FRAME:
            return
        symbol = str(p.get("symbol") or "").upper()
        close, start = FS.num(p.get("close")), FS.num(p.get("period_start"))
        if not symbol or close is None or start is None or symbol not in self._symbols:
            return
        bars = self._bars.setdefault(symbol, {})
        bars[start] = close
        if len(bars) > KEEP_BARS:
            for old in sorted(bars)[: len(bars) - KEEP_BARS]:
                bars.pop(old, None)
        if p.get("history") or not self._running:
            return
        task = asyncio.ensure_future(self._later(symbol, start, close))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _later(self, symbol: str, start: float, close: float) -> None:
        await asyncio.sleep(FACT_DELAY_S)
        if not self._running:
            return
        try:
            await self._evaluate(symbol, start, close)
        except Exception as exc:  # noqa: BLE001 -- one bad evaluation must not stop the card; counted and shown
            self._bump("ERROR")
            self._last_error = "%s %s: %s" % (symbol, type(exc).__name__, exc)

    def _skip(self, row: dict[str, Any], why: str) -> None:
        row["why"] = why
        self._bump(why)

    async def _evaluate(self, symbol: str, start: float, close: float) -> None:
        m = start + FRAME_S
        closes = [c for t, c in sorted(self._bars.get(symbol, {}).items()) if t <= start]
        dow = self._dow.get(symbol)
        trend = dow[1] if dow is not None and dow[0] >= start else None
        order = ema_order(closes)
        row: dict[str, Any] = {"at": m, "close": close, "dow_4h": trend, "ema_15m": order, "bars": len(closes)}
        self._last[symbol] = row
        if not strategy_switch.active(ATOM_ID):
            return self._skip(row, "PAUSED_BY_OWNER")
        if trend is None:
            return self._skip(row, "DOW_NOT_FRESH")
        if trend not in (RISING, FALLING):
            return self._skip(row, "DOW_NO_TREND")
        if len(closes) < EMA_WARM_BARS:
            return self._skip(row, "EMA_WARMING")
        if order != trend:
            return self._skip(row, "EMA_NOT_SAME_WAY")
        side = 1 if trend == RISING else -1
        if not red_lines.in_trading_window(m, symbol):
            return self._skip(row, "OUTSIDE_WINDOW")
        if red_lines.in_first_minutes(m, symbol):
            return self._skip(row, "FIRST_MINUTES")
        if red_lines.in_last_hour(m, symbol):          # 2026-10-25 (law 21): nothing new in the window's last hour
            return self._skip(row, "LAST_HOUR")
        if not self._positions_seen:
            return self._skip(row, "POSITIONS_UNKNOWN")
        if symbol in self._open:
            return self._skip(row, "POSITION_OPEN")
        if self._clock() - self._closed_at.get(symbol, float("-inf")) < WAIT_AFTER_CLOSE_S:
            return self._skip(row, "WAIT_AFTER_CLOSE")
        quote = self._quote.get(symbol)
        entry = (quote[1] if side > 0 else quote[0]) if quote else close     # the executable price, as the gate sees it
        hit = stop_for(self._book, symbol, side, entry)
        if hit is None:
            return self._skip(row, "NO_STOP_IN_BAND")
        why = await self._send(symbol, side, entry, *hit, m, trend, order)
        self._skip(row, why)

    async def _send(self, symbol: str, side: int, entry: float, stop: float, risk: float, stop_tf: str, m: float,
                    trend: str, order: str) -> str:
        if self._context is None:
            return "NO_CONTEXT"
        account, broker = self._account.get("account_id"), self._account.get("broker")
        if not account or not broker:
            return "ACCOUNT_UNKNOWN"
        spread = self._spread.get(symbol)
        if spread is None:
            return "SPREAD_UNKNOWN"
        direction = "buy" if side > 0 else "sell"
        target = entry + side * (FS.target_distance(risk, spread) + 4.0 * self._drift * risk)
        sid = "%s:%s:%s:%d" % (ATOM_ID, symbol, FRAME, int(m))
        stop_src = "202:%s_swing_%s" % (stop_tf, "low" if side > 0 else "high")
        setup = build_setup(
            owner=ATOM_ID, setup_type=SETUP_TYPE, side=direction, entry_reference=entry,
            invalidation_price=stop, invalidation_source=stop_src,
            invalidation_reason="خلف آخر %s خارجيّ على %s (202) — %.1f بِب" % (
                "قاع" if side > 0 else "قمّة", stop_tf, to_pips(risk, symbol)),
            target_price=target, target_source="%s:%gR_net" % (ATOM_ID, FS.TARGET_R),
            target_reason="%gR صافيةً بعد السبريد (%.5g) وهامش حركةٍ قبل الإرسال %.0f٪ من الوقف — أثلاث المالك عند 1R و2R (574)" % (
                FS.TARGET_R, spread, 100 * self._drift),
            account_id=account, broker=broker, symbol=symbol, cycle_id=sid, period_start=m - FRAME_S,
            evidence={"frame": FRAME, "strategy": NAME, "name_ar": NAME_AR, "dow_4h": trend, "ema_5_10_50_15m": order,
                      "facts": {"stop_pips": round(to_pips(risk, symbol), 1), "stop_frame": stop_tf,
                                "spread_at_build": spread}},
            created_at=self._clock(), ttl_s=SETUP_TTL_S)
        identity = {"account_id": account, "broker": broker, "symbol": symbol, "timeframe": FRAME,
                    "period_start": m - FRAME_S, "decision_id": sid}
        await self._context.publish(EV_SETUP, {**setup, **identity, "setup_id": sid, "id": NAME, "strategy": ATOM_ID,
                                               "direction": direction, "entry_price": entry, "rr": FS.TARGET_R,
                                               "frame": FRAME})
        await self._context.publish(EV_APPROVED, {
            **identity, "id": "combination_approval", "status": "ok", "approved": True, "decision_side": direction,
            "signal": direction, "cycle_id": sid, "strategy": ATOM_ID, "warnings": [],
            "metadata": {"method": NAME, "timeframe": FRAME, "direction": direction, "decision_side": direction,
                         "approved": True, "reason": None, "request_id": sid},
            "invalidation_price": stop, "target_price": target, "setup_id": sid, "invalidation_source": stop_src})
        return "SENT"

    async def snapshot(self) -> dict[str, Any]:
        return {"version": ATOM_VERSION, "tally": dict(self._tally), "closed_at": dict(self._closed_at)}

    async def restore(self, state: Any) -> None:
        if not isinstance(state, dict):
            return
        if isinstance(state.get("tally"), dict):
            self._tally = {str(k): int(v) for k, v in state["tally"].items()}
        if isinstance(state.get("closed_at"), dict):
            self._closed_at = {str(k): float(v) for k, v in state["closed_at"].items()}

    async def health_check(self) -> HealthStatus:
        if not self._running:
            return HealthStatus(state=HealthState.UNHEALTHY, message="NOT_STARTED")
        tally = " ".join("%s=%d" % kv for kv in sorted(self._tally.items())) or "-"
        last = " ".join("%s:%s/%s/%s" % (s, r.get("dow_4h"), r.get("ema_15m"), r.get("why"))
                        for s, r in sorted(self._last.items())) or "-"
        return HealthStatus(state=HealthState.HEALTHY, message="415 %s | %s | %s" % (tally, last, self._last_error),
                            details={"tally": dict(self._tally), "last": dict(self._last),
                                     "bars": {s: len(b) for s, b in self._bars.items()}})
