# -*- coding: utf-8 -*-
"""جسم ذرّة الاستراتيجيّة على حقائق الأقسام (404–410) — واحدٌ للسبع، وكلّ ذرّةٍ تسمّي استراتيجيّتها.

يمشي على طريق البطاقة 414 نفسه: `strategy.setup.proposed` ثمّ `decision.approved.state` بالوقف والهدف
⟵ 467 ⟵ 555 ⟵ حرّاس السلامة ⟵ التنفيذ؛ والإدارة أثلاث المالك (574) على الهدف المرسَل (3R).
الزناد إغلاق شمعة الدقيقة (103)، ويُقيَّم بعد مهلةٍ قصيرة كي تصل حقائق لحظتها من الأقسام.
"""
from __future__ import annotations

import asyncio
import time
from typing import Any

from core.contracts.atom import AtomContext, HealthState, HealthStatus
from shared import facts_strategies as FS
from shared import owner_trades
from shared.pips import to_pips
from shared.trade_setup import build_setup

EV_CANDLE = "market_data.candle_closed"
EV_TICK = "market.tick.validated"
EV_ACCOUNT = "platform.account.state"
EV_POSITIONS = "platform.positions.state"
EV_SETUP = "strategy.setup.proposed"
EV_APPROVED = "decision.approved.state"
FACT_DELAY_S = 2.0
SETUP_TTL_S = 120.0


class FactsStrategy:
    """تُورَث: `STRATEGY = "404"` … ."""

    STRATEGY = ""

    def __init__(self) -> None:
        self._context: AtomContext | None = None
        self._running = False
        self._book = FS.FactBook()
        self._prev: dict[tuple[str, str], int] = {}
        self._account: dict[str, Any] = {}
        self._open: set[str] = set()
        self._positions_seen = False
        self._symbols: set[str] | None = None
        self._tally: dict[str, int] = {}
        self._tasks: set[asyncio.Task] = set()
        self._clock = time.time
        self._spread: dict[str, float] = {}       # آخر سبريد (العرض − الطلب) لكلّ رمز — للهدف الصافي (١٠-١٤)

    async def initialize(self, context: AtomContext) -> None:
        self._context = context
        syms = (context.config or {}).get("symbols")
        self._symbols = {str(s).upper() for s in syms} if isinstance(syms, list) and syms else None
        context.subscribe(EV_CANDLE, self._on_candle)
        context.subscribe(EV_TICK, self._on_tick)
        context.subscribe(EV_ACCOUNT, self._on_account)
        context.subscribe(EV_POSITIONS, self._on_positions)
        context.subscribe("structure.external.state", self._fact("structure.external.state"))
        for ev in FS.NEEDS[self.STRATEGY]:
            context.subscribe(ev, self._fact(ev))

    def _fact(self, event: str):
        async def handler(payload: Any) -> None:
            if isinstance(payload, dict):
                self._book.put(event, payload, self._clock())
        return handler

    async def start(self) -> None:
        self._running = True

    async def stop(self) -> None:
        self._running = False
        for t in list(self._tasks):
            t.cancel()

    async def shutdown(self) -> None:
        await self.stop()

    async def _on_account(self, p: Any) -> None:
        if isinstance(p, dict) and p.get("account_id"):
            self._account = {"account_id": p.get("account_id"), "broker": p.get("broker") or self._account.get("broker")}

    async def _on_positions(self, p: Any) -> None:
        # ٢٠٢٦-١٠-٢٦ (قانون صفقات المالك، ختم «NQ»): الرموز المفتوحة للمنظومة وحدها، بالتمييز الواحد — كما ٤١٥. ومنع الدخول
        # على رمزٍ عليه صفقةٌ للمالك موضعه الواحد طالب الدخول ٥٥٥.
        if isinstance(p, dict) and isinstance(p.get("positions"), list):
            self._positions_seen = True
            self._open = {str(r.get("symbol") or "").upper() for r in owner_trades.system_rows(p["positions"]) if isinstance(r, dict)}

    async def _on_tick(self, p: Any) -> None:
        if not isinstance(p, dict):
            return
        bid, ask = FS.num(p.get("bid")), FS.num(p.get("ask"))
        symbol = str(p.get("symbol") or "").upper()
        if symbol and bid is not None and ask is not None and ask > bid:
            self._spread[symbol] = ask - bid

    def _bump(self, k: str) -> None:
        self._tally[k] = self._tally.get(k, 0) + 1

    async def _on_candle(self, p: Any) -> None:
        if not self._running or not isinstance(p, dict) or str(p.get("timeframe")) != "1m" or p.get("history"):
            return
        symbol = str(p.get("symbol") or "").upper()
        close, start = FS.num(p.get("close")), FS.num(p.get("period_start"))
        if not symbol or close is None or start is None or (self._symbols and symbol not in self._symbols):
            return
        task = asyncio.ensure_future(self._later(symbol, start + 60.0, close))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _later(self, symbol: str, m: float, close: float) -> None:
        await asyncio.sleep(FACT_DELAY_S)
        if self._running:
            await self._evaluate(symbol, m, close)

    async def _evaluate(self, symbol: str, m: float, close: float) -> None:
        sess = FS.session_of(m, symbol)
        for tf in FS.STRATEGIES[self.STRATEGY]["frames"]:
            s = FS.signal(self.STRATEGY, self._book, symbol, tf, self._clock(), close)
            prev = self._prev.get((symbol, tf), 0)
            self._prev[(symbol, tf)] = s
            if s == 0 or s == prev:
                continue
            if sess is None:
                self._bump("OUT_OF_SESSION")
                continue
            if symbol in self._open or not self._positions_seen:
                self._bump("POSITION_OPEN" if symbol in self._open else "POSITIONS_UNKNOWN")
                continue
            ok, got, total = FS.confirmed(self.STRATEGY, self._book, symbol, tf, s, close)
            if not ok:
                self._bump("FACTORS_SHORT")
                continue
            hit = FS.stop_for(self._book, symbol, s, close)
            if hit is None:
                self._bump("NO_STOP_IN_RANGE")
                continue
            facts = FS.decision_facts(self.STRATEGY, self._book, symbol, tf, s, close, *hit)
            await self._send(symbol, tf, sess, s, close, *hit, m, factors="%d/%d" % (got, total), facts=facts)

    async def _send(self, symbol: str, tf: str, sess: str, s: int, entry: float, stop: float, risk: float,
                    stop_tf: str, m: float, factors: str = "", facts: dict[str, Any] | None = None) -> None:
        if self._context is None:
            return
        account, broker = self._account.get("account_id"), self._account.get("broker")
        if not account or not broker:
            self._bump("ACCOUNT_UNKNOWN")
            return
        spread = self._spread.get(symbol)
        if spread is None:
            self._bump("SPREAD_UNKNOWN")         # بلا سبريدٍ مقيس لا هدفٌ صافٍ — كانت 555 ستحجبه
            return
        side = "buy" if s > 0 else "sell"
        target = entry + s * FS.target_distance(risk, spread)
        meta = FS.STRATEGIES[self.STRATEGY]
        sid = "%s:%s:%s:%d" % (self.STRATEGY, symbol, tf, int(m))
        stop_src = "202:%s_swing_%s" % (stop_tf, "low" if s > 0 else "high")
        setup = build_setup(
            owner=self.STRATEGY, setup_type=meta["setup"], side=side, entry_reference=entry,
            invalidation_price=stop, invalidation_source=stop_src,
            invalidation_reason="خلف آخر %s خارجيّ على %s (202) — %.1f بِب" % ("قاع" if s > 0 else "قمّة", stop_tf, to_pips(risk, symbol)),
            target_price=target, target_source="%s:%gR_net" % (self.STRATEGY, FS.TARGET_R),
            target_reason="%gR صافيةً بعد السبريد (%.5g) — أثلاث المالك عند 1R و2R (574)" % (FS.TARGET_R, spread),
            account_id=account, broker=broker, symbol=symbol, cycle_id=sid, period_start=m - 60.0,
            evidence={"frame": tf, "session": sess, "strategy": meta["name"], "factors": factors,
                      "facts": dict(facts or {}, spread_at_build=spread)},  # ١٠-١٢ «NQ»: أرقام القرار ⟵ البطاقة (465)
            created_at=self._clock(),
            ttl_s=SETUP_TTL_S)
        identity = {"account_id": account, "broker": broker, "symbol": symbol, "timeframe": "1m",
                    "period_start": m - 60.0, "decision_id": sid}
        await self._context.publish(EV_SETUP, {**setup, **identity, "setup_id": sid, "id": meta["name"],
                                               "strategy": self.STRATEGY, "direction": side, "entry_price": entry,
                                               "rr": FS.TARGET_R, "frame": tf, "session": sess})
        await self._context.publish(EV_APPROVED, {
            **identity, "id": "facts_strategy_approval", "status": "ok", "approved": True, "decision_side": side,
            "signal": side, "cycle_id": sid, "strategy": self.STRATEGY, "warnings": [],
            "metadata": {"method": "facts_" + meta["name"], "timeframe": tf, "direction": side, "decision_side": side,
                         "approved": True, "reason": None, "request_id": sid, "session": sess},
            "invalidation_price": stop, "target_price": target, "setup_id": sid, "invalidation_source": stop_src})
        self._bump("SENT")

    async def snapshot(self) -> dict[str, Any]:
        return {"tally": dict(self._tally)}

    async def restore(self, state: Any) -> None:
        if isinstance(state, dict) and isinstance(state.get("tally"), dict):
            self._tally = {str(k): int(v) for k, v in state["tally"].items()}

    async def health_check(self) -> HealthStatus:
        if not self._running:
            return HealthStatus(state=HealthState.UNHEALTHY, message="NOT_STARTED")
        tally = " ".join("%s=%d" % kv for kv in sorted(self._tally.items())) or "—"
        return HealthStatus(state=HealthState.HEALTHY, message="%s %s · %s" % (
            self.STRATEGY, FS.STRATEGIES[self.STRATEGY]["ar"], tally), details={"tally": dict(self._tally)})
