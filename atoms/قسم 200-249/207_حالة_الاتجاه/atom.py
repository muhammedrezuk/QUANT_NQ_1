from __future__ import annotations

from typing import Any

from core.contracts.atom import AtomBase, AtomContext, HealthState, HealthStatus
from shared.atom_evidence import inherit_evidence
from shared.section_contract import section_atom

ATOM_VERSION = "1.3.0"

EVENT_MSS = "structure.mss.state"
EVENT_TREND151 = "analysis.trend.state"
EVENT_OUT = "structure.trend.state"

METHOD = "mss_governed"
ID_TREND = "structure_trend"

TREND_UP = "uptrend"
TREND_DOWN = "downtrend"
TREND_RANGE = "range"
TREND_TRANS = "transition"

SIGNAL_SHIFT = "shift"
SHIFT_BOS = "bos"
SHIFT_CHOCH = "choch"

DIR_UP = "up"

SRC_MSS = "mss"
SRC_DEFAULT = "trend_151"

STATUS_OK = "ok"
QUALITY_GOOD = "good"

REASON_NOT_STARTED = "NOT_STARTED"
REASON_NO_INPUT = "NO_STRUCTURE_INPUT_YET"

_MAP151 = {"up": TREND_UP, "down": TREND_DOWN, "sideways": TREND_RANGE}
#: 151's flat thresholds (its manifest: flat_slope_pct, flat_distance_pct) and its words for the close vs the fast EMA.
_FLAT_SLOPE_PCT = 0.015
_FLAT_DISTANCE_PCT = 0.04
_POS_ABOVE, _POS_BELOW = "above_fast", "below_fast"


def _num(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if result == result else None
_CONF_DIR = 1.0
_CONF_TENTATIVE = 0.5
_CONFIRM_SCORE = 20.0
_SCORE_MAX = 100.0


@section_atom("200", "207")
class Atom(AtomBase):
    def __init__(self) -> None:
        self._context: AtomContext | None = None
        self._running = False
        self._state: dict[tuple, dict[str, Any]] = {}
        self._mss_seen = 0
        self._emitted = 0
        self._flat_slope = _FLAT_SLOPE_PCT
        self._flat_distance = _FLAT_DISTANCE_PCT

    async def initialize(self, context: AtomContext) -> None:
        self._context = context
        cfg = context.config or {}
        self._flat_slope = float(cfg.get("trend151_flat_slope_pct", _FLAT_SLOPE_PCT))
        self._flat_distance = float(cfg.get("trend151_flat_distance_pct", _FLAT_DISTANCE_PCT))
        context.subscribe(EVENT_MSS, self._on_mss)
        context.subscribe(EVENT_TREND151, self._on_trend151)

    async def start(self) -> None:
        self._running = True

    async def stop(self) -> None:
        self._running = False

    async def shutdown(self) -> None:
        await self.stop()

    def _get(self, key: tuple) -> dict[str, Any]:
        st = self._state.get(key)
        if st is None:
            st = {"official": TREND_RANGE, "has_mss": False,
                  "default": TREND_RANGE, "dir": None, "confirms": 0}
            self._state[key] = st
        return st

    async def _on_trend151(self, payload: dict[str, Any]) -> None:
        if not self._running or not isinstance(payload, dict):
            return
        symbol = payload.get("symbol")
        if not symbol:
            return
        meta = payload.get("metadata") or {}
        key = (str(symbol), str(meta.get("timeframe", "")))
        st = self._get(key)
        # 2026-10-18 (owner seal "NQ"): 151's word is stripped by the facts contract, so it is rebuilt from 151's own
        # published numbers with 151's own rule -- otherwise the state before the first shift is "range" forever.
        word = payload.get("signal") if payload.get("signal") in _MAP151 else self._word151(meta)
        mapped = _MAP151.get(word, TREND_RANGE)
        st["default"] = mapped
        if not st["has_mss"]:
            st["official"] = mapped

    def _word151(self, meta: dict[str, Any]) -> str:
        """151's rule on its facts: fast vs slow EMA; then the slow slope or the close beyond the fast must agree, and
        two flat EMAs (close together and a flat slope) are sideways."""
        fast, slow, slope = (_num(meta.get(k)) for k in ("ema_fast_value", "ema_slow_value", "ema_slope"))
        if None in (fast, slow, slope) or not slow or fast == slow:
            return "sideways"
        dist = (fast - slow) / slow * 100.0                      # unrounded, as 151 compares it
        up = fast > slow
        slope_ok = slope > self._flat_slope if up else slope < -self._flat_slope
        price_ok = meta.get("price_position") == (_POS_ABOVE if up else _POS_BELOW)
        if (abs(dist) < self._flat_distance and abs(slope) < self._flat_slope) or not (slope_ok or price_ok):
            return "sideways"
        return "up" if up else "down"

    async def _on_mss(self, payload: dict[str, Any]) -> None:
        if not self._running or self._context is None or not isinstance(payload, dict):
            return
        symbol = payload.get("symbol")
        if not symbol:
            return
        symbol = str(symbol)
        self._mss_seen += 1
        cycle_id = str(payload.get("cycle_id", ""))
        meta_in = payload.get("metadata") or {}
        timeframe = str(payload.get("timeframe", "") or meta_in.get("timeframe", ""))
        st = self._get((symbol, timeframe))
        # ٢٠٢٦-١٠-٠٥ (ختم المالك «ما بدي ولا قسم ما يشارك ل صفقة nq»): العمق موروثٌ من دورة
        # التحوّل (206 ⟵ 204/205 ⟵ 202 ⟵ 201). كانت هذه الوحدة الإلزاميّة بلا عمقٍ ولا كلمة
        # اتّجاهٍ يعرفها العقد («uptrend» مجهولة) فتُختم `NOT_READY` دائمًا. والكلمات أُضيفت
        # إلى قاموس العقد نفسه.
        st["evidence"] = inherit_evidence(payload)
        if payload.get("signal") == SIGNAL_SHIFT:
            st["has_mss"] = True
            shift_type = meta_in.get("shift_type")
            if shift_type == SHIFT_BOS:
                # ٢٠٢٦-١٠-٠٧ (عقد الحقائق، ختم المالك «NQ»): جانب الكسر (فوق/تحت) أوّلًا — «up/down» تُنزع في الختم.
                side = meta_in.get("break_side")
                up = side == "above" if side in ("above", "below") else meta_in.get("direction") == DIR_UP
                new_dir = TREND_UP if up else TREND_DOWN
                if new_dir == st["dir"]:
                    st["confirms"] += 1
                else:
                    st["dir"] = new_dir
                    st["confirms"] = 1
                st["official"] = new_dir
            elif shift_type == SHIFT_CHOCH:
                st["official"] = TREND_TRANS
                st["confirms"] = 0
        elif not st["has_mss"]:
            st["official"] = st["default"]
        source = SRC_MSS if st["has_mss"] else SRC_DEFAULT
        await self._emit(symbol, timeframe, cycle_id, st, source)

    async def _emit(self, symbol: str, timeframe: str, cycle_id: str,
                    st: dict[str, Any], source: str) -> None:
        if self._context is None:
            return
        official = st["official"]
        if official == TREND_UP or official == TREND_DOWN:
            confidence = _CONF_DIR if st["has_mss"] else _CONF_TENTATIVE
            score = int(min(_SCORE_MAX, st["confirms"] * _CONFIRM_SCORE))
        elif official == TREND_TRANS:
            confidence = _CONF_TENTATIVE
            score = 0
        else:
            confidence = 0.0
            score = 0
        meta = {"method": METHOD, "timeframe": timeframe,
                "confirmations": st["confirms"], "source": source}
        await self._context.publish(EVENT_OUT, {
            **st.get("evidence", {}),
            "symbol": symbol, "id": ID_TREND, "cycle_id": cycle_id,
            "timeframe": timeframe,
            "status": STATUS_OK, "signal": official, "score": score,
            "confidence": confidence, "quality": QUALITY_GOOD, "warnings": [],
            "metadata": meta})
        self._emitted += 1

    async def health_check(self) -> HealthStatus:
        if not self._running:
            return HealthStatus(state=HealthState.UNHEALTHY, message=REASON_NOT_STARTED)
        if self._mss_seen == 0:
            return HealthStatus(state=HealthState.DEGRADED, message=REASON_NO_INPUT,
                                details={"tracked": len(self._state)})
        return HealthStatus(
            state=HealthState.HEALTHY,
            message="mss=%d emitted=%d tracked=%d" % (
                self._mss_seen, self._emitted, len(self._state)),
            details={"mss": self._mss_seen, "emitted": self._emitted,
                     "tracked": len(self._state)})
