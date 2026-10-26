# -*- coding: utf-8 -*-
"""Market Regime Engine (830) — intelligence paper Phase 4.

A state carrier, NEVER a trading signal (§12/§14): it publishes the regime
state and its transitions with hysteresis — it does not touch weights or
parameters, directly or indirectly.

Inputs (existing live events, nothing new):
  * structure.trend.state (201) — trend direction value
  * analysis.volatility.state (153) — volatility percent

Hysteresis (§13): ENTRY_THRESHOLD / EXIT_THRESHOLD / CONFIRMATION_WINDOW /
MIN_DURATION_S / TRANSITION — no flip-flopping on every jitter.
"""

from __future__ import annotations

from typing import Any

from core.contracts.atom import AtomBase, AtomContext, HealthState, HealthStatus

ATOM_VERSION = "1.1.0"

# ٢٠٢٦-١٠-٠٢ (ختم المالك «صلح كامل nq»): النظام السوقيّ **لكلّ رمز**.
# كان `_trend` و`_volatility` قيمتين مفردتين يكتبهما أيّ رمزٍ وصل آخرًا، والحمولة
# بلا `symbol` — فيحفظها 166 و200 تحت «*» ويطبّقانها على كلّ الرموز: اتّجاه
# اليورو قد يُطفئ محلّلًا على الذهب. الآن الحالة مفتاحها الرمز (`payload["symbol"]`)
# وتُنشر به، و166 و200 يقرآن `symbol` أصلًا (`_on_regime`) فيأخذ كلٌّ نظام رمزه
# بلا تعديل عندهما. وحدثٌ بلا رمز لا يُعمَّم: يُعدّ ويُرمى (`SYMBOL_MISSING`).
# و`transitions` في الحمولة يبقى العدّاد الكلّيّ كما كان (840 يقرؤه عدّادًا متصاعدًا)،
# وعدّاد الرمز في `symbol_transitions`.

DEFAULT_ENTRY_THRESHOLD = 70.0
DEFAULT_EXIT_THRESHOLD = 45.0
DEFAULT_CONFIRMATION_WINDOW = 5
DEFAULT_MIN_DURATION_S = 60.0
DEFAULT_VOLATILITY_HIGH = 75.0
TREND_FLOOR = -100.0
TREND_CEILING = 100.0
VOLATILITY_CEILING = 100.0
CONFIDENCE_FULL_AT_SAMPLES = 20

EVENT_OUT = "market.regime.state"
EVENT_TREND = "structure.trend.state"
EVENT_VOLATILITY = "analysis.volatility.state"

REGIME_TRENDING = "TRENDING"
REGIME_RANGING = "RANGING"
REGIME_TRANSITION = "TRANSITION"

REASON_NOT_STARTED = "NOT_STARTED"
REASON_NO_INPUT = "NO_REGIME_INPUT_YET"


def _num(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _text(value: Any) -> str:
    return str(value or "").strip()


def _new_state() -> dict[str, Any]:
    """حالة نظام رمزٍ واحد — الحقول نفسها التي كانت مفردةً للذرّة كلّها."""
    return {"trend": None, "volatility": None, "regime": REGIME_RANGING,
            "previous": REGIME_RANGING, "since": 0.0, "confirmations": 0,
            "transition_target": None, "transitions": 0, "samples": 0}


class Atom(AtomBase):
    def __init__(self) -> None:
        self._context: AtomContext | None = None
        self._running = False
        self._entry = DEFAULT_ENTRY_THRESHOLD
        self._exit = DEFAULT_EXIT_THRESHOLD
        self._confirm = DEFAULT_CONFIRMATION_WINDOW
        self._min_duration_s = DEFAULT_MIN_DURATION_S
        self._vol_high = DEFAULT_VOLATILITY_HIGH
        # ٢٠٢٦-١٠-٠٢ (ختم المالك «صلح كامل nq»): رمز ⟵ حالته (انظر رأس الملف).
        self._states: dict[str, dict[str, Any]] = {}
        self._last_symbol = ""
        self._transitions = 0
        self._samples = 0
        # Build 3: drops counted with reasons.
        self._dropped = 0
        self._drop_reasons: dict[str, int] = {}

    @property
    def _regime(self) -> str:
        """نظام آخر رمزٍ قُيّم — للشارة وللقراءة القديمة، لا للحكم."""
        state = self._states.get(self._last_symbol)
        return state["regime"] if state else REGIME_RANGING

    def _state_for(self, payload: dict[str, Any]) -> tuple[str, dict[str, Any]] | None:
        symbol = _text(payload.get("symbol")).upper()
        if not symbol:
            self._drop("SYMBOL_MISSING")
            return None
        state = self._states.get(symbol)
        if state is None:
            state = self._states[symbol] = _new_state()
        return symbol, state

    async def initialize(self, context: AtomContext) -> None:
        self._context = context
        cfg = context.config
        self._entry = max(0.0, float(cfg.get("entry_threshold") or DEFAULT_ENTRY_THRESHOLD))
        self._exit = max(0.0, float(cfg.get("exit_threshold") or DEFAULT_EXIT_THRESHOLD))
        self._confirm = max(1, int(cfg.get("confirmation_window") or DEFAULT_CONFIRMATION_WINDOW))
        self._min_duration_s = max(0.0, float(cfg.get("min_duration_s") or DEFAULT_MIN_DURATION_S))
        self._vol_high = max(0.0, float(cfg.get("volatility_high") or DEFAULT_VOLATILITY_HIGH))
        context.subscribe(EVENT_TREND, self._on_trend)
        context.subscribe(EVENT_VOLATILITY, self._on_volatility)

    async def start(self) -> None:
        self._running = True

    async def stop(self) -> None:
        self._running = False

    async def shutdown(self) -> None:
        await self.stop()

    def _drop(self, reason: str) -> None:
        self._dropped += 1
        self._drop_reasons[reason] = self._drop_reasons.get(reason, 0) + 1

    def _label(self, trending: bool, volatility: float | None) -> str:
        if not trending:
            return REGIME_RANGING
        return "TRENDING_HIGH_VOL" if (volatility or 0.0) >= self._vol_high else REGIME_TRENDING

    async def _evaluate(self, symbol: str, state: dict[str, Any], now: float) -> None:
        if self._context is None or state["trend"] is None:
            return
        self._last_symbol = symbol
        self._samples += 1
        state["samples"] += 1
        strength = abs(state["trend"])
        target = self._label(strength >= self._entry, state["volatility"])
        current = state["regime"]
        if current in (REGIME_TRANSITION,):
            current = state["transition_target"] or REGIME_RANGING
        if target != current and state["transition_target"] != target:
            if (now - state["since"]) < self._min_duration_s:
                return  # §13 minimum dwell — no flip-flop
            state["transition_target"] = target
            state["confirmations"] = 0
        if state["transition_target"] is not None:
            # confirmation window: the exit side re-enters before switching
            exit_threshold = (self._exit if state["transition_target"] == REGIME_RANGING
                              else self._entry)
            strength_ok = (strength < exit_threshold
                           if state["transition_target"] == REGIME_RANGING
                           else strength >= exit_threshold)
            state["confirmations"] = state["confirmations"] + 1 if strength_ok else 0
            if state["confirmations"] >= self._confirm:
                state["previous"] = state["regime"]
                state["regime"] = state["transition_target"]
                state["transition_target"] = None
                state["since"] = now
                state["transitions"] += 1
                self._transitions += 1
        await self._publish(symbol, state, now)

    async def _publish(self, symbol: str, state: dict[str, Any], now: float) -> None:
        transition_score = (state["confirmations"] / self._confirm
                            if state["transition_target"] is not None and self._confirm else 0.0)
        confidence = min(1.0, state["samples"] / CONFIDENCE_FULL_AT_SAMPLES)
        await self._context.publish(EVENT_OUT, {
            "symbol": symbol,
            "regime": (state["regime"] if state["transition_target"] is None
                       else REGIME_TRANSITION),
            "previous_regime": state["previous"],
            "transition_target": state["transition_target"],
            "transition_score": round(transition_score, 4),
            "regime_start": state["since"], "regime_confidence": round(confidence, 4),
            "regime_version": ATOM_VERSION,
            "vector": {"trend": state["trend"], "volatility": state["volatility"]},
            "transitions": self._transitions,
            "symbol_transitions": state["transitions"], "samples": state["samples"],
            # §14 reminder carved into the payload itself:
            "authority": "OBSERVATION_ONLY — no weight or parameter authority"})

    async def _on_trend(self, payload: dict[str, Any]) -> None:
        if not self._running or not isinstance(payload, dict):
            return
        import time
        value = _num(payload.get("direction")) if _num(payload.get("direction")) is not None \
            else _num(payload.get("score"))
        if value is None:
            self._drop("TREND_VALUE_MISSING"); return
        found = self._state_for(payload)
        if found is None:
            return
        symbol, state = found
        state["trend"] = max(TREND_FLOOR, min(TREND_CEILING, value))
        await self._evaluate(symbol, state, time.time())

    async def _on_volatility(self, payload: dict[str, Any]) -> None:
        if not self._running or not isinstance(payload, dict):
            return
        value = _num(payload.get("score")) if _num(payload.get("score")) is not None \
            else _num(payload.get("confidence"))
        if value is None:
            self._drop("VOLATILITY_VALUE_MISSING"); return
        found = self._state_for(payload)
        if found is None:
            return
        found[1]["volatility"] = max(0.0, min(VOLATILITY_CEILING, value))

    async def health_check(self) -> HealthStatus:
        if not self._running:
            return HealthStatus(state=HealthState.UNHEALTHY, message=REASON_NOT_STARTED)
        regimes = {symbol: (state["regime"] if state["transition_target"] is None
                            else REGIME_TRANSITION)
                   for symbol, state in sorted(self._states.items())
                   if state["trend"] is not None}
        details = {"regime": self._regime, "regimes": regimes,
                   "transitions": self._transitions,
                   "samples": self._samples, "dropped": self._dropped,
                   "drop_reasons": dict(self._drop_reasons)}
        if not regimes:
            return HealthStatus(state=HealthState.DEGRADED,
                                message=REASON_NO_INPUT, details=details)
        return HealthStatus(state=HealthState.HEALTHY,
                            message="regimes=%s" % " ".join(
                                "%s:%s" % kv for kv in regimes.items()),
                            details=details)
