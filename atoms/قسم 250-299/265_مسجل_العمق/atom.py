"""Depth recorder (265): keeps one row per minute of the order book so depth gets a history that can be measured.

Per minute it writes the last fact of every (symbol, book analyzer) from the four depth analyzers into `depth_facts`,
and since 1.1.0 the last raw book of every symbol (best `book_levels` per side, as published by 624) into
`depth_book`. It reads published events only and never touches section 600. Time is the event stamp, never the clock.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from core.contracts.atom import AtomBase, AtomContext, HealthState, HealthStatus

ATOM_VERSION = "1.1.0"
EVENTS = {"liquidity.depth.state": "depth", "liquidity.microprice.state": "microprice",
          "liquidity.ofi.state": "ofi", "liquidity.price_impact.state": "price_impact"}
EVENT_BOOK = "market.depth"
DEFAULT_DIR = r"M:\QUANT_NQ_DATA"
FALLBACK_DIR = Path(__file__).resolve().parents[3] / "forex_runtime" / "var" / "store"
DEFAULT_BOOK_LEVELS = 10
MAX_TEXT = 40
SECONDS_PER_MINUTE = 60
DB_TIMEOUT_S = 10.0


def _flat(prefix: str, obj: Any, out: dict[str, Any]) -> None:
    if isinstance(obj, dict):
        for k, v in obj.items():
            _flat(f"{prefix}{k}.", v, out)
    elif isinstance(obj, (bool, int, float)) or (isinstance(obj, str) and len(obj) <= MAX_TEXT):
        out[prefix[:-1]] = obj


def _num(value: Any) -> float | None:
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return f if f == f else None


def _count(value: Any) -> int | None:
    return int(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None


class Atom(AtomBase):
    def __init__(self) -> None:
        self._context: AtomContext | None = None
        self._running = False
        self._db: sqlite3.Connection | None = None
        self._path = ""
        self._pending: dict[tuple[str, str], tuple[float, str]] = {}
        self._books: dict[str, tuple] = {}
        self._book_levels = DEFAULT_BOOK_LEVELS
        self._minute = 0
        self._seen = self._written = self._errors = 0
        self._book_seen = self._book_written = 0

    async def initialize(self, context: AtomContext) -> None:
        self._context = context
        cfg = context.config or {}
        self._book_levels = int(cfg.get("book_levels") or DEFAULT_BOOK_LEVELS)
        base = Path(str(cfg.get("data_dir") or DEFAULT_DIR))
        try:
            base.mkdir(parents=True, exist_ok=True)
        except OSError:
            base = FALLBACK_DIR
            base.mkdir(parents=True, exist_ok=True)
        self._path = str(base / "depth_facts.db")
        self._db = sqlite3.connect(self._path, timeout=DB_TIMEOUT_S, check_same_thread=False)
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.execute("CREATE TABLE IF NOT EXISTS depth_facts (minute INTEGER NOT NULL, symbol TEXT NOT NULL, "
                         "analyzer TEXT NOT NULL, at REAL NOT NULL, facts TEXT NOT NULL, "
                         "PRIMARY KEY(minute, symbol, analyzer))")
        self._db.execute("CREATE TABLE IF NOT EXISTS depth_book (minute INTEGER NOT NULL, symbol TEXT NOT NULL, "
                         "at REAL NOT NULL, best_bid REAL, best_ask REAL, bid_levels_total INTEGER, "
                         "ask_levels_total INTEGER, bids TEXT NOT NULL, asks TEXT NOT NULL, "
                         "PRIMARY KEY(minute, symbol))")
        self._db.commit()
        for event, name in EVENTS.items():
            context.subscribe(event, self._make(name))
        context.subscribe(EVENT_BOOK, self._on_book)

    def _roll(self, at: float) -> None:
        """A newer minute flushes the previous one; a late event joins the current minute."""
        minute = int(at // SECONDS_PER_MINUTE)
        if self._minute and minute > self._minute:
            self._flush()
        if minute > self._minute:
            self._minute = minute

    def _make(self, name: str):
        async def handler(payload: Any) -> None:
            if not self._running or not isinstance(payload, dict):
                return
            symbol = str(payload.get("symbol") or "").upper()
            at = _num(payload.get("timestamp"))
            if not symbol or at is None:
                return
            row: dict[str, Any] = {}
            _flat("", {k: v for k, v in payload.items() if k not in ("symbol", "metadata")}, row)
            _flat("m.", payload.get("metadata") or {}, row)
            self._seen += 1
            self._roll(at)
            self._pending[(symbol, name)] = (at, json.dumps(row, ensure_ascii=False, default=str))
        return handler

    async def _on_book(self, payload: Any) -> None:
        if not self._running or not isinstance(payload, dict):
            return
        symbol = str(payload.get("symbol") or "").upper()
        at = _num(payload.get("timestamp"))
        bids, asks = payload.get("bids"), payload.get("asks")
        if not symbol or at is None or not isinstance(bids, list) or not isinstance(asks, list):
            return
        self._book_seen += 1
        self._roll(at)
        self._books[symbol] = (at, _num(payload.get("best_bid")), _num(payload.get("best_ask")),
                               _count(payload.get("bid_levels_total")), _count(payload.get("ask_levels_total")),
                               bids[:self._book_levels], asks[:self._book_levels])

    def _flush(self) -> None:
        if self._db is None or not (self._pending or self._books):
            return
        facts = [(self._minute, s, a, at, js) for (s, a), (at, js) in self._pending.items()]
        books = [(self._minute, s, at, bb, ba, bt, at_, json.dumps(b, default=str), json.dumps(a, default=str))
                 for s, (at, bb, ba, bt, at_, b, a) in self._books.items()]
        try:
            self._db.executemany("INSERT OR REPLACE INTO depth_facts VALUES (?,?,?,?,?)", facts)
            self._db.executemany("INSERT OR REPLACE INTO depth_book VALUES (?,?,?,?,?,?,?,?,?)", books)
            self._db.commit()
            self._written += len(facts)
            self._book_written += len(books)
        except sqlite3.Error:
            self._errors += 1
        self._pending.clear()
        self._books.clear()

    async def start(self) -> None:
        self._running = True

    async def stop(self) -> None:
        self._running = False
        self._flush()

    async def shutdown(self) -> None:
        await self.stop()
        if self._db is not None:
            self._db.close()
            self._db = None

    async def health_check(self) -> HealthStatus:
        if not self._running:
            return HealthStatus(state=HealthState.UNHEALTHY, message="NOT_STARTED")
        msg = "seen=%d written=%d book_seen=%d book_written=%d errors=%d %s" % (
            self._seen, self._written, self._book_seen, self._book_written, self._errors, self._path)
        ok = (self._seen or self._book_seen) and not self._errors
        return HealthStatus(state=HealthState.HEALTHY if ok else HealthState.DEGRADED, message=msg, details={
            "seen": self._seen, "written": self._written, "book_seen": self._book_seen,
            "book_written": self._book_written, "errors": self._errors})
