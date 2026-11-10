"""Every frame up or down by the owner's rule (owner seal 2026-10-22), on his nine frames, for every symbol.

A rising candle makes a higher high and a higher low than the one before it; a falling candle the mirror. A frame turns
up after `run` rising candles in a row and stays up until `run` falling candles in a row (shared.direction_rule, the
same calculation the backtest page measured). The week and the month are not in the live feed: they are built from the
day candles as the Dow atom builds them. On every live candle close of a fed frame it publishes, for that symbol, each
frame's trend and how many candles it has lasted. Raw facts for the direction board; no trade.
"""
from __future__ import annotations

from typing import Any

from core.contracts.atom import AtomBase, HealthState, HealthStatus
from shared import direction_rule, dow_theory

ATOM_VERSION = "1.0.0"
EVENT_CANDLE = "market_data.candle_closed"
EVENT_OUT = "structure.direction.state"
DEFAULT_FRAMES = ["1m", "5m", "15m", "30m", "1h", "4h", "1d", "1w", "1mo"]
DEFAULT_DAY_FRAME = "1d"
DEFAULT_MAX_BARS = 450
FRAME_S = {"1m": 60, "5m": 300, "15m": 900, "30m": 1800, "1h": 3600, "4h": 14400, "1d": 86400}
BUILT_FRAMES = (dow_theory.WEEK, dow_theory.MONTH)
TREND_WORD = {direction_rule.UP: "up", direction_rule.DOWN: "down", direction_rule.UNKNOWN: None}


def _num(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if result == result else None


class Atom(AtomBase):

    def __init__(self) -> None:
        self._context = None
        self._running = False
        self._symbols: set[str] = set()
        self._frames = list(DEFAULT_FRAMES)
        self._day_frame = DEFAULT_DAY_FRAME
        self._max_bars = DEFAULT_MAX_BARS
        self._run = direction_rule.DEFAULT_RUN
        self._bars: dict[tuple[str, str], dict[float, tuple]] = {}
        self._last: dict[str, dict[str, Any]] = {}
        self._published = 0
        self._failed = 0
        self._dropped = 0
        self._last_error = ""

    async def initialize(self, context: Any) -> None:
        self._context = context
        cfg = context.config or {}
        self._symbols = {str(s).upper() for s in cfg.get("symbols") or []}
        self._frames = [str(f) for f in cfg.get("frames") or DEFAULT_FRAMES]
        self._day_frame = str(cfg.get("day_frame") or DEFAULT_DAY_FRAME)
        self._max_bars = int(cfg.get("max_bars", DEFAULT_MAX_BARS))
        self._run = int(cfg.get("run", direction_rule.DEFAULT_RUN))
        context.subscribe(EVENT_CANDLE, self._on_candle)

    async def start(self) -> None:
        self._running = True

    async def stop(self) -> None:
        self._running = False

    async def shutdown(self) -> None:
        await self.stop()

    def _fed_frames(self) -> set[str]:
        return {f for f in self._frames if f not in BUILT_FRAMES} | {self._day_frame}

    def _keep(self, key: tuple[str, str], start: float, row: tuple) -> None:
        store = self._bars.setdefault(key, {})
        store[start] = row
        if len(store) > self._max_bars:
            for old in sorted(store)[: len(store) - self._max_bars]:
                store.pop(old, None)

    def _rows(self, symbol: str, frame: str, now_s: float) -> list[tuple]:
        if frame in BUILT_FRAMES:
            days = [row for _, row in sorted(self._bars.get((symbol, self._day_frame), {}).items())]
            if frame == dow_theory.WEEK:
                return dow_theory.aggregate(days, dow_theory.WEEK, now_s)
            return dow_theory.month_candles(symbol, days, now_s)
        return [row for _, row in sorted(self._bars.get((symbol, frame), {}).items())]

    def _frame_state(self, symbol: str, frame: str, now_s: float) -> dict[str, Any]:
        rows = self._rows(symbol, frame, now_s)[-self._max_bars:]
        if not rows:
            return {"trend": None, "since_bars": 0, "since": None, "bars": 0}
        state = direction_rule.directions([r[2] for r in rows], [r[3] for r in rows], self._run)
        lasted = direction_rule.since(state)
        last = int(state[-1])
        since_bars = int(lasted[-1]) if last != direction_rule.UNKNOWN else 0
        return {"trend": TREND_WORD[last], "since_bars": since_bars,
                "since": rows[-since_bars][0] if since_bars else None, "bars": len(rows), "last_start": rows[-1][0]}

    async def _on_candle(self, payload: Any) -> None:
        if not self._running or self._context is None or not isinstance(payload, dict):
            return
        symbol = str(payload.get("symbol") or "").upper()
        frame = str(payload.get("timeframe") or "")
        if frame not in self._fed_frames() or (self._symbols and symbol not in self._symbols):
            return                                                    # other frames and symbols are not ours
        start = _num(payload.get("period_start"))
        values = [_num(payload.get(k)) for k in ("open", "high", "low", "close")]
        if not symbol or start is None or None in values:
            self._dropped += 1                                        # malformed candle: counted, shown in health
            return
        self._keep((symbol, frame), start, (start, *values, _num(payload.get("volume"))))
        if payload.get("history"):
            return
        close_s = start + FRAME_S.get(frame, 0)
        try:
            frames = {f: self._frame_state(symbol, f, close_s) for f in self._frames}
        except Exception as exc:  # noqa: BLE001 -- a bad candle set must not stop the feed; counted and shown
            self._failed += 1
            self._last_error = "%s %s: %s" % (symbol, type(exc).__name__, exc)
            return
        self._last[symbol] = {f: s["trend"] for f, s in frames.items()}
        await self._context.publish(EVENT_OUT, {"id": "frame_direction", "symbol": symbol,
                                                "account_id": payload.get("account_id"), "broker": payload.get("broker"),
                                                "timeframe": frame, "period_start": start, "run": self._run,
                                                "frames": frames})
        self._published += 1

    async def snapshot(self) -> dict[str, Any]:
        return {"version": ATOM_VERSION, "published": self._published, "failed": self._failed, "last": self._last}

    async def restore(self, state: Any) -> None:
        if not isinstance(state, dict):
            return
        self._published = int(_num(state.get("published")) or 0)
        self._failed = int(_num(state.get("failed")) or 0)

    async def health_check(self) -> HealthStatus:
        if not self._running:
            return HealthStatus(state=HealthState.UNHEALTHY, message="NOT_STARTED")
        mark = {"up": "+", "down": "-", None: "?"}
        trends = " ".join("%s:%s" % (s, "".join(mark[t] for t in states.values()))
                          for s, states in sorted(self._last.items())) or "-"
        fed = sorted(self._fed_frames())
        held = " ".join("%s:%s" % (s, "/".join(str(len(self._bars.get((s, f), {}))) for f in fed))
                        for s in sorted({k[0] for k in self._bars})) or "-"
        return HealthStatus(state=HealthState.HEALTHY, message="published=%d failed=%d dropped=%d run=%d frames=%s "
                            "trends(%s) bars(%s) %s %s" % (self._published, self._failed, self._dropped, self._run,
                                                           "/".join(self._frames), trends, "/".join(fed), held,
                                                           self._last_error))
