from __future__ import annotations

from collections import deque
from typing import Any

from core.contracts.atom import AtomBase, AtomContext, HealthState, HealthStatus
from shared.section_contract import section_atom
from shared.atom_evidence import window_evidence
from shared.cycle_identity import cycle_key_of

ATOM_VERSION = "1.6.1"

# ٢٠٢٦-١٠-٠٩ (ختم المالك «NQ» — إلغاء مفاتيح السرعة إلى الأرشيف): نافذة القمّة/القاع رقم المانيفست حرفيًّا
# (`lookback` = 2 ⟸ 5 شموع) — كانت تُضرب في 50/السرعة (الحيّ ×1.32: 2⟵3 ⟸ 7 شموع)، والذاكرة نافذة واحدة
# بعد أن كانت `lookback×5×2+1`. وسلّم المستويات (`LADDER_SIDE`) لم يتبع المفتاح يومًا — فلا يتغيّر.

EVENT_IN = "market_data.candle_closed"
EVENT_OUT = "structure.swing.state"

METHOD = "fractal_center"
ID_SWING = "swing"

SIGNAL_HIGH = "swing_high"
SIGNAL_LOW = "swing_low"
SIGNAL_NONE = "none"

STATUS_OK = "ok"
STATUS_INSUFFICIENT = "insufficient_data"

QUALITY_GOOD = "good"
QUALITY_LOW = "low"

WARN_INSUFFICIENT = "insufficient_candles"

REASON_NOT_STARTED = "NOT_STARTED"
REASON_NO_CANDLES = "NO_CANDLES_YET"
REASON_ALL_REJECTED = "ALL_CANDLES_REJECTED_SO_FAR"

_SCORE_MAX = 100.0
_PRICE_DP = 4
_PROM_DP = 4
# Bound only (external feed boundary -- a malformed/garbage symbol name is
# untrusted input, unlike the internal 201->251 contract): once this many
# distinct rejected symbols are tracked, a new symbol's rejections still
# count toward the total but stop getting their own breakdown entry.
_MAX_TRACKED_REJECTED_SYMBOLS = 64

# ════════ سلّم المستويات — أمر المالك بختم «Nq» ٢٠٢٦-٠٩-٢٨ ════════
#
# «بدنا ناخد ادق ستوب واكبر هدف» · «هدف صفقة لا يقل عن 1/3» · «ابنيهم وثبتهم بل ورق».
# الوقف والهدف صارا من قمم البنية وقيعانها على الفريمات الكبيرة لا من نافذة
# الاستراتيجيّة، وهذه الذرّة مصدرُها: تحفظ لكلّ رمزٍ القممَ والقيعان **المؤكَّدة**
# على الربع ساعة والساعة و4س واليوم، وتنشرها سلّمًا كاملًا في حدثٍ واحد.
#
# ⛔ التعريف ثابتٌ كما قِيس (ورقة الخطوة الثالثة): شمعةٌ أعلى/أدنى **بصرامة** من
#    الشمعتين قبلها والشمعتين بعدها، ولا تُعرف إلّا بعد إغلاق الثانية بعدها — فلا
#    نظرٌ في المستقبل. ولم يتبع مفتاح السرعة كما كانت تتبعه النافذة أعلاه (أُرشف المفتاح ٢٠٢٦-١٠-٠٩):
#    القياس الذي بُني عليه الوقف والهدف كان بشمعتين، ورقمٌ يتبدّل مع مفتاحٍ لم يُقس عليه قالبٌ.
# ⛔ السلّم حدثٌ واحدٌ كامل لكلّ رمز: أحداث الحالة تُدمج في الناقل بلا فريم، فقمّةُ
#    يومٍ منشورةٌ وحدها كان يطويها حدثُ العشر ثوانٍ عند مستهلكٍ متأخّر.
# ⛔ الحدث القائم `structure.swing.state` لم يتغيّر بحرف — وعليه قسم البنية كلّه.
EVENT_LADDER = "structure.levels.state"
ID_LADDER = "levels"
#: ٢٠٢٦-١٠-٠٦ 15:4x — **والخمس دقائق** بختم المالك «NQ»: وقف الناسداك وتتبّعه عليها
#: (`shared/structure_exits.STOP_FRAME_BY_SYMBOL`) — التعريف نفسه، شمعتان قبلها وشمعتان بعدها.
LADDER_FRAMES = {"5m": 300.0, "15m": 900.0, "1h": 3600.0, "4h": 14400.0, "1d": 86400.0}
LADDER_SIDE = 2
#: أعمق ما يُحفظ لكلّ جهة — ما يقرؤه المستهلك (`shared/structure_exits.DEPTH`).
LADDER_KEEP = {"5m": 100, "15m": 100, "1h": 200, "4h": 200, "1d": 200}
#: إغلاقات اليوم المحفوظة لكلّ رمز — أطول متوسّطٍ يُقرأ منها 20، والباقي هامش.
DAILY_CLOSES_KEEP = 60

try:  # البذرة عقدٌ جديد في `shared/` — تعذّرُه يترك السلّم يُبنى من الحيّ وحده.
    from shared.structure_exits import load_seed as _load_seed
except Exception:  # noqa: BLE001
    _load_seed = None


def _to_float(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if result == result else None


def _merge_ladders(seed: dict[str, Any], snap: dict[str, Any]) -> dict[str, Any]:
    """البذرة تحت اللقطة: اتّحادُ المستويات بمفتاح بداية شمعتها، واللقطة تغلب على الشمعة نفسها،
    ثمّ الترتيب بلحظة التأكيد وأحدث `LADDER_KEEP` — فلا يمحو الأحدثُ الأعمقَ ولا العكس."""
    merged: dict[str, Any] = {}
    for symbol in set(seed) | set(snap):
        for frame in LADDER_FRAMES:
            for side in ("highs", "lows"):
                rows: dict[float, list[float]] = {}
                for book in (seed, snap):
                    for row in ((book.get(symbol) or {}).get(frame) or {}).get(side) or []:
                        rows[float(row[2])] = [float(v) for v in row[:3]]
                if rows:
                    ordered = sorted(rows.values(), key=lambda r: (r[1], r[2]))
                    merged.setdefault(symbol, {}).setdefault(
                        frame, {"highs": [], "lows": []})[side] = ordered[-LADDER_KEEP[frame]:]
    return merged


@section_atom("200", "201")
class Atom(AtomBase):
    def __init__(self) -> None:
        self._context: AtomContext | None = None
        self._running = False
        self._lookback = 2
        self._window_size = 5
        self._state: dict[tuple, dict[str, Any]] = {}
        self._candles_seen = 0
        self._emitted = 0
        self._swings_found = 0
        self._rejected_candles = 0
        self._rejected_by_symbol: dict[str, int] = {}
        # سلّم المستويات: رمز ⟵ فريم ⟵ {"highs"/"lows": [[السعر، وقت التأكيد، بداية الشمعة]]}
        self._ladder: dict[str, dict[str, dict[str, list[list[float]]]]] = {}
        # آخر خمس شموعٍ لكلّ (رمز، فريم) — [البداية، الأعلى، الأدنى] — كي لا ينقطع
        # التأكيد عبر الإقلاع.
        self._ladder_bars: dict[tuple[str, str], deque] = {}
        self._ladder_announced: set[str] = set()
        self._ladder_published = 0
        self._ladder_source = "حيّ"
        # ٢٠٢٦-١٠-٠٦: إغلاقات اليوم (بدايته ⟵ إغلاقه) لإذن الاتّجاه اليوميّ في `structure_exits` —
        # من البذرة (العنصر الرابع) ومن شمعة 103 اليوميّة المغلقة. تُنشر مع السلّم.
        self._daily_closes: dict[str, dict[float, float]] = {}

    async def initialize(self, context: AtomContext) -> None:
        self._context = context
        self._lookback = int(context.config["lookback"])
        self._window_size = self._lookback * 2 + 1
        self._seed_ladder()
        context.subscribe(EVENT_IN, self._on_candle)

    async def start(self) -> None:
        self._running = True

    async def stop(self) -> None:
        self._running = False

    async def shutdown(self) -> None:
        await self.stop()

    async def _on_candle(self, payload: dict[str, Any]) -> None:
        if not self._running or self._context is None or not isinstance(payload, dict):
            return
        symbol = payload.get("symbol")
        high = _to_float(payload.get("high"))
        low = _to_float(payload.get("low"))
        close = _to_float(payload.get("close"))
        if not symbol or high is None or low is None or close is None:
            self._rejected_candles += 1
            reject_key = str(symbol) if symbol else "UNKNOWN"
            if reject_key in self._rejected_by_symbol or \
                    len(self._rejected_by_symbol) < _MAX_TRACKED_REJECTED_SYMBOLS:
                self._rejected_by_symbol[reject_key] = self._rejected_by_symbol.get(reject_key, 0) + 1
            return
        symbol = str(symbol)
        timeframe = str(payload.get("timeframe", ""))
        period_start = payload.get("period_start", payload.get("timestamp", ""))
        cycle_id = cycle_key_of(payload, symbol=symbol, timeframe=timeframe, period_start=period_start)
        key = (symbol, timeframe)
        st = self._state.get(key)
        if st is None:
            st = {"window": deque(maxlen=self._window_size)}
            self._state[key] = st
        st["window"].append({"high": high, "low": low, "close": close,
                             "period_start": period_start})
        self._candles_seen += 1
        await self._emit(symbol, timeframe, cycle_id, close, st)
        await self._on_ladder_candle(payload, symbol, timeframe, period_start, high, low)

    async def _emit(self, symbol: str, timeframe: str, cycle_id: str,
                    close: float, st: dict[str, Any]) -> None:
        if self._context is None:
            return
        # The manifest's lookback drives the swing-high/low window -- the
        # source of the whole structure section (202-208 derive from these
        # swings).
        w_look = self._lookback
        need = self._window_size
        window = list(st["window"])[-need:]
        base = {"symbol": symbol, "id": ID_SWING, "cycle_id": cycle_id,
                "timeframe": timeframe,
                **window_evidence(have=len(window), need=need)}
        meta = {"method": METHOD, "timeframe": timeframe,
                "lookback": w_look, "close": close}
        if len(window) < need:
            await self._context.publish(EVENT_OUT, {
                **base, "status": STATUS_INSUFFICIENT, "signal": SIGNAL_NONE,
                "score": 0, "confidence": 0.0, "quality": QUALITY_LOW,
                "warnings": [WARN_INSUFFICIENT], "metadata": meta})
            self._emitted += 1
            return
        center = window[w_look]
        others = [window[i] for i in range(len(window)) if i != w_look]
        highest_other = max(c["high"] for c in others)
        lowest_other = min(c["low"] for c in others)
        signal = SIGNAL_NONE
        price = 0.0
        gap = 0.0
        if center["high"] > highest_other:
            signal = SIGNAL_HIGH
            price = center["high"]
            gap = center["high"] - highest_other
        elif center["low"] < lowest_other:
            signal = SIGNAL_LOW
            price = center["low"]
            gap = lowest_other - center["low"]
        if signal == SIGNAL_NONE:
            await self._context.publish(EVENT_OUT, {
                **base, "status": STATUS_OK, "signal": SIGNAL_NONE, "score": 0,
                "confidence": 0.0, "quality": QUALITY_GOOD, "warnings": [],
                "metadata": meta})
            self._emitted += 1
            return
        win_high = max(c["high"] for c in window)
        win_low = min(c["low"] for c in window)
        span = win_high - win_low
        prominence = gap / span if span > 0 else 0.0
        score = int(round(min(1.0, prominence) * _SCORE_MAX))
        meta.update({"price": round(price, _PRICE_DP),
                     "swing_time": center["period_start"],
                     "prominence": round(prominence, _PROM_DP)})
        await self._context.publish(EVENT_OUT, {
            **base, "status": STATUS_OK, "signal": signal, "score": score,
            "confidence": 1.0, "quality": QUALITY_GOOD, "warnings": [],
            "metadata": meta})
        self._emitted += 1
        self._swings_found += 1

    # ─── سلّم المستويات ───────────────────────────────────────────────────
    def _ladder_push(self, symbol: str, frame: str, start: float,
                     high: float, low: float) -> int:
        """شمعةٌ مغلقة على فريمٍ كبير ⟵ كم مستوىً تأكّد بها (0 أو 1 أو 2)."""
        seconds = LADDER_FRAMES[frame]
        bars = self._ladder_bars.setdefault((symbol, frame), deque(maxlen=2 * LADDER_SIDE + 1))
        if bars and start <= bars[-1][0]:
            return 0  # مكرّرة أو متأخّرة عن آخر ما رُئي — لا تُعاد
        bars.append((start, high, low))
        if len(bars) < 2 * LADDER_SIDE + 1:
            return 0
        center = bars[LADDER_SIDE]
        others = [bar for index, bar in enumerate(bars) if index != LADDER_SIDE]
        confirmed_at = bars[-1][0] + seconds
        book = self._ladder.setdefault(symbol, {}).setdefault(frame, {"highs": [], "lows": []})
        found = 0
        if all(center[1] > bar[1] for bar in others):
            book["highs"].append([center[1], confirmed_at, center[0]])
            del book["highs"][:-LADDER_KEEP[frame]]
            found += 1
        if all(center[2] < bar[2] for bar in others):
            book["lows"].append([center[2], confirmed_at, center[0]])
            del book["lows"][:-LADDER_KEEP[frame]]
            found += 1
        return found

    def _close_push(self, symbol: str, start: float, close: float) -> None:
        book = self._daily_closes.setdefault(symbol, {})
        book[float(start)] = float(close)
        for old in sorted(book)[:-DAILY_CLOSES_KEEP]:
            del book[old]

    async def _on_ladder_candle(self, payload: dict[str, Any], symbol: str, timeframe: str,
                                period_start: Any, high: float, low: float) -> None:
        start = _to_float(period_start)
        fresh = timeframe in LADDER_FRAMES and start is not None
        repeat = False
        if fresh:
            seen = self._ladder_bars.get((symbol, timeframe))
            repeat = bool(seen) and start <= seen[-1][0]
            self._ladder_push(symbol, timeframe, start, high, low)
            close = _to_float(payload.get("close"))
            if timeframe == "1d" and close is not None:
                self._close_push(symbol, start, close)
        # يُنشر السلّم عند كلّ شمعةٍ كبيرة، وعند أوّل شمعةٍ من أيّ فريم بعد الإقلاع —
        # فالمستهلك لا ينتظر ربع ساعةٍ ليعرف ما استُعيد أو بُذر.
        # 1.6.1 (2026-10-14, owner seal): a replayed history candle or a repeated/late candle adds nothing a live
        # reader waits for, yet the whole ladder was republished for each one -- during the chart provider's history
        # replay that multiplied the events held in one core cycle. The ladder is still published on every new live
        # closed candle (card 414 syncs on `frame_closed`) and once on the first candle after boot.
        live_new = fresh and not repeat and not payload.get("history")
        if live_new or symbol not in self._ladder_announced:
            await self._publish_ladder(payload, symbol,
                                       {"frame": timeframe, "period_start": start} if live_new else None)

    async def _publish_ladder(self, payload: dict[str, Any], symbol: str,
                              closed: dict[str, Any] | None = None) -> None:
        if self._context is None:
            return
        frames = {frame: {"highs": [row[:2] for row in sides.get("highs", [])],
                          "lows": [row[:2] for row in sides.get("lows", [])]}
                  for frame, sides in (self._ladder.get(symbol) or {}).items()}
        await self._context.publish(EVENT_LADDER, {
            "symbol": symbol, "id": ID_LADDER, "timeframe": "ladder",
            "account_id": payload.get("account_id"), "broker": payload.get("broker"),
            "status": STATUS_OK, "signal": SIGNAL_NONE,
            "quality": QUALITY_GOOD if frames else QUALITY_LOW,
            "frames": frames,
            "daily_closes": [[start, close] for start, close in
                             sorted((self._daily_closes.get(symbol) or {}).items())[-DAILY_CLOSES_KEEP:]],
            "definition": {"method": METHOD, "side_candles": LADDER_SIDE,
                           "confirmed": "after the second candle on the far side closes"},
            # ٢٠٢٦-١٠-٠٨ (ختم المالك «صلح NQ»): الشمعة التي حدّثت السلّم (إطارها وبدايتها) — تعرف بها البطاقة
            # 414 أنّ مستويات الساعة/الأربع ساعات المؤكَّدة عند لحظة الزناد وصلت قبل أن تختار هدفها.
            "frame_closed": closed,
            "source": self._ladder_source})
        self._ladder_announced.add(symbol)
        self._ladder_published += 1

    def _seed_ladder(self) -> None:
        """بذرةٌ من شموع سي‑تريدر المخزَّنة — تُمرَّر على التعريف نفسه، ولقطةُ الذرّة
        (إن وُجدت) تُدمج فوقها بعد التهيئة (`_merge_ladders`) — لا تحلّ محلّها منذ 1.5.0."""
        seed = _load_seed() if _load_seed is not None else None
        if not seed:
            return
        loaded = 0
        for symbol, frames in seed.get("symbols", {}).items():
            if not isinstance(frames, dict):
                continue
            for frame in LADDER_FRAMES:
                for bar in frames.get(frame) or []:
                    if isinstance(bar, (list, tuple)) and len(bar) >= 3:
                        start, high, low = _to_float(bar[0]), _to_float(bar[1]), _to_float(bar[2])
                        if start is not None and high is not None and low is not None:
                            self._ladder_push(str(symbol), frame, start, high, low)
                            loaded += 1
                            close = _to_float(bar[3]) if len(bar) >= 4 else None
                            if frame == "1d" and close is not None:
                                self._close_push(str(symbol), start, close)
        if loaded:
            self._ladder_source = "بذرة %s" % seed.get("built_at_text", "")

    async def snapshot(self) -> dict[str, Any]:
        return {"version": ATOM_VERSION,
                "ladder": self._ladder,
                "daily_closes": {s: [[k, v] for k, v in sorted(book.items())]
                                 for s, book in self._daily_closes.items()},
                "bars": {"%s|%s" % key: [list(bar) for bar in bars]
                         for key, bars in self._ladder_bars.items()}}

    async def restore(self, state: dict[str, Any]) -> None:
        if not isinstance(state, dict) or not isinstance(state.get("ladder"), dict):
            return
        ladder: dict[str, dict[str, dict[str, list[list[float]]]]] = {}
        for symbol, frames in state["ladder"].items():
            if not isinstance(frames, dict):
                continue
            for frame, sides in frames.items():
                if frame not in LADDER_FRAMES or not isinstance(sides, dict):
                    continue
                for side in ("highs", "lows"):
                    rows = [[float(v) for v in row[:3]] for row in sides.get(side) or []
                            if isinstance(row, (list, tuple)) and len(row) >= 3
                            and all(_to_float(v) is not None for v in row[:3])]
                    ladder.setdefault(str(symbol), {}).setdefault(
                        frame, {"highs": [], "lows": []})[side] = rows[-LADDER_KEEP[frame]:]
        bars: dict[tuple[str, str], deque] = {}
        for joined, rows in (state.get("bars") or {}).items():
            symbol, _, frame = str(joined).rpartition("|")
            if frame not in LADDER_FRAMES or not symbol or not isinstance(rows, list):
                continue
            clean = [tuple(float(v) for v in row[:3]) for row in rows
                     if isinstance(row, (list, tuple)) and len(row) >= 3
                     and all(_to_float(v) is not None for v in row[:3])]
            bars[(symbol, frame)] = deque(clean[-(2 * LADDER_SIDE + 1):], maxlen=2 * LADDER_SIDE + 1)
        # ٢٠٢٦-١٠-٠٦ (ختم المالك «NQ صلاحية كاملة» على «الدمج: … تُدمج اللقطة فوق البذرة العميقة،
        # فيبقى أحدث ما في اللقطة وأعمق ما في البذرة»): كانت اللقطة تستبدل البذرة كلّها، ولقطةٌ
        # بُنيت على بذرةٍ ضحلة تمحو أيّ بذرةٍ أعمق منها. الشمعة نفسها في الاثنين ⟵ ما بناه الحيّ.
        seeded = bool(self._ladder)
        self._ladder = _merge_ladders(self._ladder, ladder)
        for key, rows in bars.items():
            old = self._ladder_bars.get(key)
            if not old or (rows and rows[-1][0] >= old[-1][0]):
                self._ladder_bars[key] = rows
        self._ladder_source = ("لقطة فوق %s" % self._ladder_source) if seeded else "لقطة"
        for symbol, rows in (state.get("daily_closes") or {}).items():
            for row in rows if isinstance(rows, list) else []:
                if isinstance(row, (list, tuple)) and len(row) >= 2:
                    start, close = _to_float(row[0]), _to_float(row[1])
                    if start is not None and close is not None:
                        self._close_push(str(symbol), start, close)   # اليوم نفسه في الاثنين ⟵ الحيّ

    def _ladder_summary(self) -> str:
        parts = []
        for symbol in sorted(self._ladder):
            frames = self._ladder[symbol]
            parts.append("%s %s" % (symbol, " ".join(
                "%s=%d/%d" % (frame, len(frames[frame]["highs"]), len(frames[frame]["lows"]))
                for frame in LADDER_FRAMES if frame in frames)))
        return " | سلّم[%s] مصدره=%s نُشر=%d" % (" · ".join(parts[:7]) or "فارغ",
                                                  self._ladder_source, self._ladder_published)

    async def health_check(self) -> HealthStatus:
        if not self._running:
            return HealthStatus(state=HealthState.UNHEALTHY, message=REASON_NOT_STARTED)
        if self._candles_seen == 0:
            if self._rejected_candles > 0:
                return HealthStatus(
                    state=HealthState.DEGRADED, message=REASON_ALL_REJECTED,
                    details={"tracked": len(self._state), "rejected": self._rejected_candles,
                             "rejected_by_symbol": dict(self._rejected_by_symbol)})
            return HealthStatus(state=HealthState.DEGRADED, message=REASON_NO_CANDLES,
                                details={"tracked": len(self._state), "rejected": 0})
        return HealthStatus(
            state=HealthState.HEALTHY,
            message="candles=%d emitted=%d swings=%d tracked=%d rejected=%d" % (
                self._candles_seen, self._emitted, self._swings_found, len(self._state),
                self._rejected_candles) + self._ladder_summary(),
            details={"candles": self._candles_seen, "emitted": self._emitted,
                     "swings": self._swings_found, "tracked": len(self._state),
                     "rejected": self._rejected_candles,
                     "rejected_by_symbol": dict(self._rejected_by_symbol),
                     "ladder_published": self._ladder_published})
