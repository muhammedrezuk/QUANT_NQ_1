"""Dow theory on the owner's nine frames, with his adopted direction readings (owner seals 2026-10-17).

Frames in three groups: secondary (1m, 5m, 15m) - sub (30m, 1h, 4h) - primary (day, week, month). The week and the month
are not in the live feed: the week is built from the day candles, the month from the stored months plus the day candles.
On every live quarter-hour close it publishes, per index: Dow's facts on each frame (shared.dow_theory: the trend on
closes, legs, the give-back of the last leg, volume up vs down), each group's agreement, the confirmation of the other
indices on the day frame, and the adopted readings ("secondary agree", "four hours", "primary agree") with their measured
record and their live record -- every New York session close scores the readings asked from 09:45 to 15:45 that day,
so the record grows with time. Raw facts, no judgment.
"""
from __future__ import annotations

from typing import Any

from core.contracts.atom import AtomBase, HealthState, HealthStatus
from shared import dow_theory

ATOM_VERSION = "1.1.1"
EVENT_CANDLE = "market_data.candle_closed"
EVENT_OUT = "structure.dow.state"
DEFAULT_GROUPS = {"secondary": ["1m", "5m", "15m"], "sub": ["30m", "1h", "4h"], "primary": ["1d", "1w", "1mo"]}
DEFAULT_ASK_FRAME = "15m"
DEFAULT_DAY_FRAME = "1d"
DEFAULT_MAX_BARS = 450
ASK_FRAME_S = 900
BUILT_FRAMES = (dow_theory.WEEK, dow_theory.MONTH)


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
        self._group: list[str] = []
        self._groups = {k: list(v) for k, v in DEFAULT_GROUPS.items()}
        self._ask_frame = DEFAULT_ASK_FRAME
        self._day_frame = DEFAULT_DAY_FRAME
        self._max_bars = DEFAULT_MAX_BARS
        self._span = dow_theory.PIVOT_SPAN
        self._bars: dict[tuple[str, str], dict[float, tuple]] = {}
        self._pending: dict[str, dict[str, Any]] = {}
        self._live: dict[str, dict[str, dict[str, int]]] = {}
        self._published = 0
        self._failed = 0
        self._dropped = 0
        self._unscored_days = 0
        self._last_error = ""

    async def initialize(self, context: Any) -> None:
        self._context = context
        cfg = context.config or {}
        self._symbols = {str(s).upper() for s in cfg.get("symbols") or []}
        self._group = [str(s).upper() for s in cfg.get("confirmation_group") or []]
        groups = cfg.get("groups")
        if isinstance(groups, dict) and groups:
            self._groups = {str(k): [str(f) for f in v] for k, v in groups.items() if isinstance(v, list)}
        self._ask_frame = str(cfg.get("ask_frame") or DEFAULT_ASK_FRAME)
        self._day_frame = str(cfg.get("day_frame") or DEFAULT_DAY_FRAME)
        self._max_bars = int(cfg.get("max_bars", DEFAULT_MAX_BARS))
        self._span = int(cfg.get("pivot_span", dow_theory.PIVOT_SPAN))
        context.subscribe(EVENT_CANDLE, self._on_candle)

    async def start(self) -> None:
        self._running = True

    async def stop(self) -> None:
        self._running = False

    async def shutdown(self) -> None:
        await self.stop()

    def _fed_frames(self) -> set[str]:
        return {f for frames in self._groups.values() for f in frames if f not in BUILT_FRAMES} | {self._day_frame,
                                                                                                    self._ask_frame}

    def _keep(self, key: tuple[str, str], start: float, row: tuple) -> None:
        store = self._bars.setdefault(key, {})
        store[start] = row
        if len(store) > self._max_bars:
            for old in sorted(store)[: len(store) - self._max_bars]:
                store.pop(old, None)

    def _rows(self, symbol: str, frame: str, now_s: float) -> list[tuple]:
        days = [row for _, row in sorted(self._bars.get((symbol, self._day_frame), {}).items())]
        if frame == dow_theory.WEEK:
            return dow_theory.aggregate(days, dow_theory.WEEK, now_s)
        if frame == dow_theory.MONTH:
            return dow_theory.month_candles(symbol, days, now_s)
        return [row for _, row in sorted(self._bars.get((symbol, frame), {}).items())]

    def _facts(self, symbol: str, frame: str, now_s: float) -> dict[str, Any]:
        return {"frame": frame, **dow_theory.frame_facts(self._rows(symbol, frame, now_s)[-self._max_bars:], self._span)}

    def _body(self, symbol: str, now_s: float) -> dict[str, Any]:
        frames = {f: self._facts(symbol, f, now_s) for fs in self._groups.values() for f in fs}
        trends = {f: facts.get("dow_trend", dow_theory.NONE) for f, facts in frames.items()}
        groups = {name: {"frames": fs, "agree": dow_theory.agree([trends[f] for f in fs])} for name, fs in self._groups.items()}
        readings = {}
        for name, spec in dow_theory.adopted().get("readings", {}).items():
            listed = [f for f in spec.get("frames", []) if f in trends]
            readings[name] = {"frames": listed, "trend": dow_theory.agree([trends[f] for f in listed]) if listed else None,
                              "measured": spec.get("measured") if symbol == dow_theory.adopted().get("symbol_measured") else None,
                              "live": self._live.get(symbol, {}).get(name, {"right": 0, "wrong": 0, "flat": 0, "days": 0})}
        others = {s: self._facts(s, self._day_frame, now_s) for s in self._group if s != symbol}
        confirmation = dow_theory.agreement(frames.get(self._day_frame, {}), others) if symbol in self._group else None
        return {"frames": frames, "groups": groups, "readings": readings, "confirmation": confirmation}

    def _track(self, symbol: str, close_s: float, price: float, readings: dict[str, Any]) -> None:
        """Ask the adopted readings 09:45-15:45 New York; at 16:00 score them against the session close."""
        clock = dow_theory.ny_clock(close_s)
        if clock is None:
            return
        day, minute = clock
        pending = self._pending.get(symbol)
        if pending and pending["day"] != day:
            self._unscored_days += 1 if pending["asks"] else 0                  # no 16:00 close that day: not scored
            pending = None
        pending = pending or {"day": day, "asks": []}
        self._pending[symbol] = pending
        if dow_theory.ASK_FROM_MIN <= minute <= dow_theory.ASK_TO_MIN:
            pending["asks"] += [[name, r["trend"], price] for name, r in readings.items()
                                if r["trend"] in (dow_theory.RISING, dow_theory.FALLING)]
        elif minute == dow_theory.SESSION_CLOSE_MIN and pending["asks"]:
            live = self._live.setdefault(symbol, {})
            for name, cell in dow_theory.score(pending["asks"], price).items():
                total = live.setdefault(name, {"right": 0, "wrong": 0, "flat": 0, "days": 0})
                for key, count in cell.items():
                    total[key] += count
                total["days"] += 1
            pending["asks"] = []

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
        if payload.get("history") or frame != self._ask_frame:
            return
        close_s = start + ASK_FRAME_S
        try:
            body = self._body(symbol, close_s)
            self._track(symbol, close_s, values[3], body["readings"])
            for name, reading in body["readings"].items():                # the 16:00 close carries its own score
                reading["live"] = dict(self._live.get(symbol, {}).get(name, reading["live"]))
        except Exception as exc:  # noqa: BLE001 -- a bad candle set must not stop the feed; counted and shown
            self._failed += 1
            self._last_error = "%s %s: %s" % (symbol, type(exc).__name__, exc)
            return
        await self._context.publish(EVENT_OUT, {"id": "dow_theory", "symbol": symbol, "account_id": payload.get("account_id"),
                                                "broker": payload.get("broker"), "timeframe": frame,
                                                "period_start": start, **body})
        self._published += 1

    async def snapshot(self) -> dict[str, Any]:
        return {"version": ATOM_VERSION, "published": self._published, "failed": self._failed, "live": self._live,
                "pending": self._pending, "unscored_days": self._unscored_days}

    async def restore(self, state: Any) -> None:
        if not isinstance(state, dict):
            return
        self._published = int(_num(state.get("published")) or 0)
        self._failed = int(_num(state.get("failed")) or 0)
        self._unscored_days = int(_num(state.get("unscored_days")) or 0)
        if isinstance(state.get("live"), dict):
            self._live = state["live"]
        if isinstance(state.get("pending"), dict):
            self._pending = state["pending"]

    async def health_check(self) -> HealthStatus:
        if not self._running:
            return HealthStatus(state=HealthState.UNHEALTHY, message="NOT_STARTED")
        fed = sorted(self._fed_frames())
        held = " ".join("%s:%s" % (s, "/".join(str(len(self._bars.get((s, f), {}))) for f in fed))
                        for s in sorted({k[0] for k in self._bars})) or "-"
        live = " ".join("%s:%s" % (s, ",".join("%s=%d/%d" % (n, c["right"], c["right"] + c["wrong"]) for n, c in r.items()))
                        for s, r in sorted(self._live.items())) or "-"
        return HealthStatus(state=HealthState.HEALTHY, message="published=%d failed=%d dropped=%d unscored_days=%d "
                            "bars(%s) %s live %s %s" % (self._published, self._failed, self._dropped, self._unscored_days,
                                                        "/".join(fed), held, live, self._last_error))
