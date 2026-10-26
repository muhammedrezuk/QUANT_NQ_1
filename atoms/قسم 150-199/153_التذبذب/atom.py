from __future__ import annotations

import asyncio
import os
import sqlite3
import time
from pathlib import Path

import math
from collections import deque
from typing import Any

from core.contracts.atom import AtomBase, AtomContext, HealthState, HealthStatus
from shared.live_analysis import live_analyzer
from shared.section_contract import section_atom
from shared.cycle_identity import cycle_key_of

ATOM_VERSION = "2.5.0"


#: نافذة متوسّط المدى الثابتة التي قيست عليها البطاقة 414 (٢٠٢٦-١٠-٠٨).
ATR_FIXED_WINDOW = 14
#: الأطر التي تُغلق شمعتها نادرًا فتُعاد حقيقتها المحفوظة عند الإقلاع (٢٠٢٦-١٠-٠٨).
#: مهلة إعادة النشر بعد البدء — بعد اكتمال الإقلاع كلّه (٢٠٢٦-١٠-٠٨).
BOOT_REPUBLISH_DELAY_S = 30.0
_REPUBLISH_AT_BOOT = ("1d", "4h")

# ٢٠٢٦-١٠-٠٩ (ختم المالك «NQ» — إلغاء مفاتيح السرعة إلى الأرشيف): النوافذ أرقام المانيفست حرفيًّا — كانت
# تُضرب في 50/السرعة (الحيّ ×1.32: المدى 16⟵21 · الأساس 32⟵42 · الانحراف 20⟵26 · أقلّ الشموع 16⟵21).
# و`atr_14` الذي تقرؤه البطاقة 414 لم يمسّه المفتاح يومًا — نافذته ثابتة 14 — فلا يتغيّر.

EVENT_IN = "market_data.candle_closed"
EVENT_OUT = "analysis.volatility.state"

METHOD = "atr_relative"

LEVEL_LOW = "low"
LEVEL_NORMAL = "normal"
LEVEL_HIGH = "high"

STATUS_OK = "ok"
STATUS_INSUFFICIENT = "insufficient_data"

QUALITY_GOOD = "good"
QUALITY_LOW = "low"

WARN_INSUFFICIENT = "insufficient_candles"

REASON_NOT_STARTED = "NOT_STARTED"
REASON_NO_CANDLES = "NO_CANDLES_YET"

_PERCENT = 100.0
_SCORE_MAX = 100.0
_ATR_PCT_SCALE = 120.0


def _to_float(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if result == result else None


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _stddev(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    avg = _mean(values)
    return math.sqrt(sum((v - avg) ** 2 for v in values) / len(values))


@section_atom("150", "153")
@live_analyzer("volatility", EVENT_OUT)
class Atom(AtomBase):
    def __init__(self) -> None:
        self._context: AtomContext | None = None
        self._running = False
        self._atr_window = 14
        self._baseline_window = 50
        self._stddev_window = 20
        self._high_mult = 1.5
        self._low_mult = 0.6
        self._min_candles = 20
        self._state: dict[tuple, dict[str, Any]] = {}
        self._candles_seen = 0
        self._emitted = 0

    async def initialize(self, context: AtomContext) -> None:
        self._context = context
        cfg = context.config
        self._atr_window = int(cfg["atr_window"])
        self._baseline_window = int(cfg["baseline_window"])
        self._stddev_window = int(cfg["stddev_window"])
        self._high_mult = float(cfg["high_mult"])
        self._low_mult = float(cfg["low_mult"])
        self._min_candles = int(cfg["min_candles"])
        context.subscribe(EVENT_IN, self._on_candle)

    def _memory(self) -> int:
        """٢٠٢٦-١٠-٠٩ (ختم المالك «NQ» — إلغاء مفاتيح السرعة إلى الأرشيف): ذاكرة المدى والإغلاقات = أطول
        نافذةٍ تُقرأ منها (الأساس · الانحراف · المدى الثابت 14) — كانت `الأساس×5` لتتّسع لأبطأ سرعة."""
        return max(self._baseline_window, self._stddev_window, ATR_FIXED_WINDOW)

    async def start(self) -> None:
        self._running = True
        # الإقلاع يبدأ الذرّات واحدةً بعد واحدة بترتيب أرقامها — فالنشر فورًا يسبق اشتراك البطاقة 414.
        # يُؤجَّل حتّى يكتمل الإقلاع كلّه (قِيس ~7 ث).
        self._seeded_daily = self._seed_daily_from_history()
        if any(timeframe in _REPUBLISH_AT_BOOT for (_, timeframe) in self._state):
            self._republish_task = asyncio.ensure_future(self._deferred_republish())

    async def _deferred_republish(self) -> None:
        try:
            await asyncio.sleep(BOOT_REPUBLISH_DELAY_S)
            if self._running:
                await self._republish_restored()
        except asyncio.CancelledError:
            pass

    def _seed_daily_from_history(self) -> int:
        """٢٠٢٦-١٠-٠٨ (تدقيق الإغلاق — «الحيّ = المقيس»): لقطة هذه الذرّة كانت تحمل 8 شموع يوم فقط للناسداك
        (بدأ تاريخها من جديد) — و«مدى اليوم على 14» لا يُنشر قبل 14 ⟸ البطاقة 414 بلا سقف هدفها المقيس
        (ثمّ «حقيقة ناقصة»). تُبذر شموع اليوم المكتملة من قاعدة تاريخ سي‑تريدر نفسها التي قيست بها البطاقة
        (يوم الوسيط — وعليه صار باني الشموع)، قراءةً فقط، ويُسقط آخرها (قد يكون جُلب وسط يومه)."""
        if os.environ.get("QUANT_REPLAY_NO_WARM", "").strip() == "1":
            return 0
        path = Path(os.environ.get("QUANT_HISTORY_DB") or
                    Path(__file__).resolve().parents[3] / "forex_runtime" / "var" / "history" / "ctrader_history.db")
        symbols = sorted({symbol for (symbol, timeframe), st in self._state.items()})
        needy = [s for s in symbols if len((self._state.get((s, "1d")) or {}).get("tr") or ()) < ATR_FIXED_WINDOW]
        if not needy or not path.is_file():
            return 0
        seeded = 0
        try:
            con = sqlite3.connect("file:%s?mode=ro" % path.as_posix(), uri=True, timeout=3)
            try:
                for symbol in needy:
                    rows = con.execute(
                        "SELECT high, low, close FROM candles_history WHERE symbol=? AND period='D1' "
                        "AND period_start + 86400 <= ? ORDER BY period_start DESC LIMIT ?",
                        (symbol, time.time(), self._memory() + 1)).fetchall()
                    rows = list(reversed(rows))                 # المكتملة وحدها: يومٌ لم ينتهِ لا يُبذر
                    if len(rows) < ATR_FIXED_WINDOW + 1:
                        continue
                    tr: deque = deque(maxlen=self._memory())
                    closes: deque = deque(maxlen=self._memory())
                    prev = None
                    for high, low, close in rows:
                        tr.append(high - low if prev is None else max(high - low, abs(high - prev), abs(low - prev)))
                        closes.append(close)
                        prev = close
                    self._state[(symbol, "1d")] = {"tr": tr, "closes": closes, "prev_close": prev,
                                                   "seeded_from": "ctrader_history.D1"}
                    seeded += 1
            finally:
                con.close()
        except sqlite3.Error:
            return seeded
        return seeded

    async def _republish_restored(self) -> None:
        # ٢٠٢٦-١٠-٠٨ (تدقيق الإغلاق): شمعة اليوم تُغلق مرّةً في اليوم (يوم الوسيط 21:00 غرينتش) — فبعد إقلاعٍ
        # تبقى البطاقة 414 بلا «مدى اليوم» حتّى الإغلاق التالي، أي نافذتَي يومٍ كامل بلا صفقة («حقيقة ناقصة»).
        # التاريخ المحفوظ يحمل آخر مدى محسوب ⟸ يُعاد نشر حقيقته الثابتة (`atr_14`) للأطر الطويلة عند الإقلاع.
        if self._context is None:
            return
        for (symbol, timeframe), st in list(self._state.items()):
            if timeframe not in _REPUBLISH_AT_BOOT:
                continue
            all_tr = list(st["tr"])
            if len(all_tr) < ATR_FIXED_WINDOW:
                continue
            await self._context.publish(EVENT_OUT, {
                "symbol": symbol, "id": "volatility", "timeframe": timeframe,
                "cycle_id": "restored|%s|%s" % (symbol, timeframe), "status": STATUS_OK,
                "warnings": ["RESTORED_AT_BOOT"],
                "metadata": {"method": METHOD, "timeframe": timeframe, "restored": True,
                             "atr_14": round(_mean(all_tr[-ATR_FIXED_WINDOW:]), 5)}})
            self._emitted += 1

    async def stop(self) -> None:
        self._running = False
        task = getattr(self, "_republish_task", None)
        if task is not None and not task.done():
            task.cancel()

    async def shutdown(self) -> None:
        await self.stop()

    # Owner stamp 2026-08-21: the live wrapper used to REPLACE snapshot/
    # restore outright, wiping this atom's true-range and close history on
    # every restart. Measured effect: `min_candles` (20 by default) closed
    # candles are required before it leaves insufficient_data, so a reboot
    # silenced volatility for 20 candles every time. The wrapper now chains
    # both states -- "live_analysis" for its own tick memory, "atom" for
    # this history -- so this one survives a restart.
    async def snapshot(self) -> dict[str, Any]:
        return {
            "candles_seen": self._candles_seen,
            "emitted": self._emitted,
            "scopes": [{"symbol": symbol, "timeframe": timeframe,
                        "tr": list(st["tr"]), "closes": list(st["closes"]),
                        "prev_close": st["prev_close"]}
                       for (symbol, timeframe), st in self._state.items()],
        }

    async def restore(self, state: dict[str, Any]) -> None:
        if not isinstance(state, dict):
            return
        self._candles_seen = int(state.get("candles_seen") or 0)
        self._emitted = int(state.get("emitted") or 0)
        self._state = {}
        for row in state.get("scopes") or []:
            if not isinstance(row, dict):
                continue
            symbol = str(row.get("symbol") or "")
            if not symbol:
                continue
            tr: deque = deque(maxlen=self._memory())
            for value in row.get("tr") or []:
                number = _to_float(value)
                if number is not None:
                    tr.append(number)
            closes: deque = deque(maxlen=self._memory())
            for value in row.get("closes") or []:
                number = _to_float(value)
                if number is not None:
                    closes.append(number)
            self._state[(symbol, str(row.get("timeframe") or ""))] = {
                "tr": tr, "closes": closes,
                "prev_close": _to_float(row.get("prev_close")),
            }

    async def _on_candle(self, payload: dict[str, Any]) -> None:
        if not self._running or self._context is None or not isinstance(payload, dict):
            return
        symbol = payload.get("symbol")
        high = _to_float(payload.get("high"))
        low = _to_float(payload.get("low"))
        close = _to_float(payload.get("close"))
        if not symbol or high is None or low is None or close is None:
            return
        symbol = str(symbol)
        timeframe = str(payload.get("timeframe", ""))
        period_start = payload.get("period_start", payload.get("timestamp", ""))
        cycle_id = cycle_key_of(payload, symbol=symbol, timeframe=timeframe, period_start=period_start)
        key = (symbol, timeframe)
        st = self._state.get(key)
        if st is None:
            st = {"tr": deque(maxlen=self._memory()),
                  "closes": deque(maxlen=self._memory()), "prev_close": None}
            self._state[key] = st
        prev_close = st["prev_close"]
        if prev_close is None:
            true_range = high - low
        else:
            true_range = max(high - low, abs(high - prev_close), abs(low - prev_close))
        st["tr"].append(true_range)
        st["closes"].append(close)
        st["prev_close"] = close
        self._candles_seen += 1
        await self._emit(symbol, timeframe, cycle_id, close, high, low, st, _to_float(period_start))

    async def _emit(self, symbol: str, timeframe: str, cycle_id: str, close: float,
                    high: float, low: float, st: dict[str, Any],
                    period_start: float | None = None) -> None:
        if self._context is None:
            return
        base = {"symbol": symbol, "id": "volatility", "cycle_id": cycle_id,
                "timeframe": timeframe}
        # ٢٠٢٦-١٠-٠٨ (ختم المالك «صلح NQ»): بداية الشمعة التي حُسب منها المدى — تعرف بها البطاقة 414 أنّ
        # مدى الخمس دقائق هو مدى شمعة الزناد نفسها (تعريف القياس) لا الشمعة التي قبلها.
        meta = {"method": METHOD, "timeframe": timeframe, "period_start": period_start}
        tr = list(st["tr"])[-self._baseline_window:]
        # ٢٠٢٦-١٠-٠٨ (تدقيق الإغلاق — «الحيّ = المقيس»): البطاقة 414 قيست على متوسّط مدى **14** شمعة، ونافذة
        # هذا المحلّل كانت تُمدّ بمفتاح السرعة (16 × 50/38 = 21 حيًّا) — فكان وقف البطاقة وسقف هدفها في الحيّ غير
        # المقيس (مقيس: بمدى 21 نصفان سالبان وخارج العيّنة 0.139 بدل 0.171). حقيقةٌ خام مسمّاة بنافذتها الثابتة:
        # متوسّط المدى الحقيقيّ لآخر 14 شمعة (تعريف القياس نفسه).
        all_tr = list(st["tr"])
        if len(all_tr) >= ATR_FIXED_WINDOW:
            meta["atr_14"] = round(_mean(all_tr[-ATR_FIXED_WINDOW:]), 5)
        if len(tr) < self._min_candles:
            await self._context.publish(EVENT_OUT, {
                **base, "status": STATUS_INSUFFICIENT, "signal": LEVEL_NORMAL,
                "score": 0, "confidence": 0.0, "quality": QUALITY_LOW,
                "warnings": [WARN_INSUFFICIENT], "metadata": meta})
            self._emitted += 1
            return
        current_atr = _mean(tr[-self._atr_window:])
        baseline_atr = _mean(tr)
        ratio = current_atr / baseline_atr if baseline_atr > 0 else 1.0
        if ratio >= self._high_mult:
            level = LEVEL_HIGH
        elif ratio <= self._low_mult:
            level = LEVEL_LOW
        else:
            level = LEVEL_NORMAL
        atr_pct = current_atr / close * _PERCENT if close > 0 else 0.0
        score = int(round(min(_SCORE_MAX, atr_pct * _ATR_PCT_SCALE)))
        confidence = round(min(1.0, len(tr) / self._baseline_window), 2)
        stddev = _stddev(list(st["closes"])[-self._stddev_window:])
        meta.update({"atr": round(current_atr, 5), "atr_pct": round(atr_pct, 4),
                     "baseline_atr": round(baseline_atr, 5), "ratio": round(ratio, 2),
                     "range": round(high - low, 5), "stddev": round(stddev, 5)})
        await self._context.publish(EVENT_OUT, {
            **base, "status": STATUS_OK, "signal": level, "score": score,
            "confidence": confidence, "quality": QUALITY_GOOD, "warnings": [],
            "metadata": meta})
        self._emitted += 1

    async def health_check(self) -> HealthStatus:
        if not self._running:
            return HealthStatus(state=HealthState.UNHEALTHY, message=REASON_NOT_STARTED)
        if self._candles_seen == 0:
            return HealthStatus(state=HealthState.DEGRADED, message=REASON_NO_CANDLES,
                                details={"tracked": len(self._state)})
        return HealthStatus(
            state=HealthState.HEALTHY,
            message="candles=%d emitted=%d tracked=%d" % (
                self._candles_seen, self._emitted, len(self._state)),
            details={"candles": self._candles_seen, "emitted": self._emitted,
                     "tracked": len(self._state)})
