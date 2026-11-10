"""Chart provider: replays the cTrader history store as closed candles after boot and refreshes the store on the pulse.

The first tick of a symbol only registers it. The replay runs on the pulse: the store is read in one pulse, then
whole frames (largest first) are published within a per-pulse bar budget, so no single bus cycle carries thousands
of candles. A frame is never split, a symbol counts as served only once all its frames are out, and a failed read
is retried on a later tick up to `max_attempts`.
"""
from __future__ import annotations

import asyncio
import sqlite3
import sys
from collections import deque
from pathlib import Path
from typing import Any

from core.contracts.atom import AtomBase, AtomContext, HealthState, HealthStatus

ATOM_VERSION = "1.3.2"
EVENT_TICK = "market.tick.validated"
EVENT_PULSE = "SYS_SECOND"
EVENT_OUT = "market_data.candle_closed"
PROVIDER = "ctrader_history"
ROOT = Path(__file__).resolve().parents[3]
DEFAULT_DB = ROOT / "forex_runtime" / "var" / "history" / "ctrader_history.db"
FETCH_TOOL = ROOT / "tools" / "جلب_تاريخ_سي_تريدر.py"  # cTrader history fetch tool (read-only)
DEFAULT_SYMBOLS = ("USTEC", "US30", "US500", "XAUUSD", "BTCUSD")
DEFAULT_BARS = 300
DEFAULT_BARS_PER_PULSE = 300
DEFAULT_MAX_ATTEMPTS = 3
DEFAULT_REPLAY_WAIT_S = 600.0
DEFAULT_FETCH_EVERY_S = 3600.0
DEFAULT_FETCH_TIMEOUT_S = 1800.0
# store period -> candle builder timeframe, largest first so higher-frame context is filled before lower frames
FRAMES = (("D1", "1d"), ("H12", "12h"), ("H4", "4h"), ("H1", "1h"), ("M30", "30m"), ("M15", "15m"),
          ("M10", "10m"), ("M5", "5m"), ("M4", "4m"), ("M3", "3m"), ("M2", "2m"), ("M1", "1m"))


def closed_bars(db_path: str, symbol: str, period: str, limit: int, market_now: float) -> list[tuple]:
    """Last `limit` bars whose period ended at or before `market_now`, oldest first."""
    con = sqlite3.connect("file:%s?mode=ro" % db_path, uri=True, timeout=10.0)
    try:
        rows = con.execute(
            "SELECT period_start, open, high, low, close, tick_volume FROM candles_history "
            "WHERE symbol=? AND period=? AND period_start + period_seconds <= ? "
            "ORDER BY period_start DESC LIMIT ?", (symbol, period, int(market_now), int(limit))).fetchall()
    finally:
        con.close()
    rows.reverse()
    return rows


def load_frames(db_path: str, symbol: str, limit: int, market_now: float) -> list[tuple[str, list[tuple]]]:
    """Every frame of one symbol, largest first, each oldest first; frames without bars are dropped."""
    frames = [(frame, closed_bars(db_path, symbol, period, limit, market_now)) for period, frame in FRAMES]
    return [(frame, rows) for frame, rows in frames if rows]


def _num(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


class Atom(AtomBase):
    def __init__(self) -> None:
        self._context: AtomContext | None = None
        self._running = False
        self._db = str(DEFAULT_DB)
        self._symbols: set[str] = set()
        self._bars = DEFAULT_BARS
        self._bars_per_pulse = DEFAULT_BARS_PER_PULSE
        self._max_attempts = DEFAULT_MAX_ATTEMPTS
        self._replay_wait = DEFAULT_REPLAY_WAIT_S
        self._first_pulse: float | None = None
        self._fetch_every = DEFAULT_FETCH_EVERY_S
        self._fetch_timeout = DEFAULT_FETCH_TIMEOUT_S
        self._requested: dict[str, dict[str, Any]] = {}
        self._sending: dict[str, dict[str, Any]] = {}
        self._queue: deque[tuple[str, str, list[tuple]]] = deque()
        self._served: set[str] = set()
        self._attempts: dict[str, int] = {}
        self._replaying = False
        self._published = 0
        self._by_symbol: dict[str, int] = {}
        self._fetches = self._fetch_fail = self._errors = 0
        self._last_fetch: float | None = None
        self._next_fetch: float | None = None
        self._fetching = False
        self._tasks: set[asyncio.Task] = set()

    async def initialize(self, context: AtomContext) -> None:
        self._context = context
        cfg = context.config or {}
        self._db = str(cfg.get("db_path") or DEFAULT_DB)
        self._symbols = {str(s).upper() for s in cfg.get("symbols") or DEFAULT_SYMBOLS}
        self._bars = int(cfg.get("bars_per_frame") or DEFAULT_BARS)
        self._bars_per_pulse = int(cfg.get("replay_bars_per_pulse") or DEFAULT_BARS_PER_PULSE)
        self._max_attempts = int(cfg.get("max_attempts") or DEFAULT_MAX_ATTEMPTS)
        self._replay_wait = float(cfg.get("replay_wait_s", DEFAULT_REPLAY_WAIT_S))
        self._fetch_every = float(cfg.get("fetch_every_s", DEFAULT_FETCH_EVERY_S))
        self._fetch_timeout = float(cfg.get("fetch_timeout_s") or DEFAULT_FETCH_TIMEOUT_S)
        context.subscribe(EVENT_TICK, self._on_tick)
        context.subscribe(EVENT_PULSE, self._on_pulse)

    async def start(self) -> None:
        self._running = True

    async def stop(self) -> None:
        self._running = False
        for task in list(self._tasks):
            task.cancel()

    async def shutdown(self) -> None:
        await self.stop()

    async def _on_tick(self, payload: Any) -> None:
        if not self._running or not isinstance(payload, dict):
            return
        symbol = str(payload.get("symbol") or "").upper()
        market_now = _num(payload.get("timestamp"))
        if not symbol or symbol not in self._symbols or market_now is None:
            return
        if symbol in self._served or symbol in self._requested or symbol in self._sending:
            return
        if self._attempts.get(symbol, 0) >= self._max_attempts:
            return
        self._requested[symbol] = {"account_id": payload.get("account_id"), "broker": payload.get("broker"),
                                   "at": market_now}

    async def _on_pulse(self, payload: Any) -> None:
        if not self._running or not isinstance(payload, dict):
            return
        now = _num(payload.get("official_time"))
        if now is not None and self._first_pulse is None:
            self._first_pulse = now
        self._schedule_fetch(now)
        if self._replaying:
            return
        self._replaying = True
        try:
            await self.replay_step(now)
        finally:
            self._replaying = False

    def _waiting_for_fetch(self, now: float | None) -> bool:
        """The boot replay waits for the first store refresh (or `replay_wait_s`), so it never replays a stale store."""
        if self._fetch_every <= 0 or self._fetches > 0:
            return False
        return now is None or self._first_pulse is None or now - self._first_pulse < self._replay_wait

    def _schedule_fetch(self, now: float | None) -> None:
        if self._fetch_every <= 0 or self._fetching or now is None:
            return
        if self._next_fetch is not None and now < self._next_fetch:
            return
        self._next_fetch = now + self._fetch_every
        self._fetching = True
        task = asyncio.ensure_future(self.fetch_once(now))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def replay_step(self, now: float | None = None) -> int:
        """One pulse of replay: load the next requested symbol, or publish whole frames within the bar budget."""
        if self._waiting_for_fetch(now):
            return 0
        if not self._queue:
            if self._requested:
                await self._load(next(iter(self._requested)))
            return 0
        sent = 0
        while self._queue and sent < self._bars_per_pulse:
            symbol, frame, rows = self._queue[0]
            await self._publish_frame(symbol, frame, rows)
            self._queue.popleft()
            sent += len(rows)
            if not any(queued == symbol for queued, _, _ in self._queue):
                self._sending.pop(symbol, None)
                self._served.add(symbol)
        return sent

    async def _load(self, symbol: str) -> None:
        request = self._requested.pop(symbol)
        try:
            frames = await asyncio.to_thread(load_frames, self._db, symbol, self._bars, request["at"])
        except (sqlite3.Error, OSError):
            self._errors += 1
            self._attempts[symbol] = self._attempts.get(symbol, 0) + 1
            return
        if not frames:
            self._served.add(symbol)
            return
        self._sending[symbol] = request
        self._by_symbol[symbol] = 0
        for frame, rows in frames:
            self._queue.append((symbol, frame, rows))

    async def _publish_frame(self, symbol: str, frame: str, rows: list[tuple]) -> None:
        request = self._sending[symbol]
        for start, o, h, low, c, vol in rows:
            await self._context.publish(EVENT_OUT, {
                "account_id": request.get("account_id"), "broker": request.get("broker"), "provider": PROVIDER,
                "symbol": symbol, "open": o, "high": h, "low": low, "close": c, "volume": vol,
                "tick_count": vol, "fabric_gap": False, "timeframe": frame,
                "period_start": float(start), "timestamp": float(start), "history": True})
        self._published += len(rows)
        self._by_symbol[symbol] = self._by_symbol.get(symbol, 0) + len(rows)

    async def fetch_once(self, started_at: float) -> bool:
        periods = ",".join(p for p, _ in FRAMES)
        try:
            proc = await asyncio.create_subprocess_exec(
                sys.executable, str(FETCH_TOOL), "--symbols", ",".join(sorted(self._symbols)),
                "--periods", periods, "--db", self._db, cwd=str(ROOT),
                stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
            code = await asyncio.wait_for(proc.wait(), timeout=self._fetch_timeout)
        except (OSError, asyncio.TimeoutError):
            code = -1
        finally:
            self._fetching = False
        self._fetches += 1
        if code == 0:
            self._last_fetch = started_at
            return True
        self._fetch_fail += 1
        return False

    async def health_check(self) -> HealthStatus:
        if not self._running:
            return HealthStatus(state=HealthState.UNHEALTHY, message="NOT_STARTED")
        waiting = sorted(set(self._requested) | set(self._sending))
        return HealthStatus(state=HealthState.HEALTHY, message=(
            "history_bars=%d symbols=%s waiting=%s fetches=%d failed=%d errors=%d" % (
                self._published, ",".join("%s:%d" % kv for kv in sorted(self._by_symbol.items())) or "-",
                ",".join(waiting) or "-", self._fetches, self._fetch_fail, self._errors)), details={
            "published": self._published, "by_symbol": dict(self._by_symbol), "waiting": waiting,
            "served": sorted(self._served), "fetches": self._fetches, "fetch_failures": self._fetch_fail,
            "last_fetch": self._last_fetch, "errors": self._errors, "attempts": dict(self._attempts)})
