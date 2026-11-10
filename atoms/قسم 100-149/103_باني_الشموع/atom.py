from __future__ import annotations

import math
from typing import Any

from core.contracts.atom import AtomBase, AtomContext, HealthState, HealthStatus
from shared.owner_windows import broker_day_offset_s

ATOM_VERSION = "5.5.0"
# ٢٠٢٦-١٠-٠٨ (تدقيق الإغلاق — «الحيّ = المقيس»): الأطر الأطول من الساعة (الأربع ساعات واليوم) تُبنى على يوم
# الوسيط (إغلاق نيويورك 17:00 — ساعة الخادم = نيويورك + 7) لا على غرينتش: عليه قاعدة تاريخ سي‑تريدر التي قيست
# بها البطاقة 414، وعليه شارت المالك. مقيس: البطاقة بشموع غرينتش +19.2R (التعلّم 0.046، نصفان سالبان) مقابل
# +28.3R بشموع الوسيط؛ وغرينتش يصنع «يوم أحدٍ» من ساعتين يشوّه مدى اليوم. الساعة وما دونها لا تتغيّر.
_BROKER_ALIGNED_ABOVE_S = 3600.0


def frame_period_start(timestamp: float, frame_seconds: float) -> float:
    """بداية فترة الإطار للحظة — غرينتش للساعة وما دونها، ويوم الوسيط لما فوقها."""
    if frame_seconds > _BROKER_ALIGNED_ABOVE_S:
        shifted = timestamp + broker_day_offset_s(timestamp)
        return timestamp - (shifted % frame_seconds)
    return timestamp - (timestamp % frame_seconds)
EVENT_IN = "market.tick.validated"
EVENT_PULSE = "SYS_SECOND"
EVENT_OUT = "market_data.candle_closed"
REASON_NOT_STARTED = "NOT_STARTED"
REASON_NO_CANDLES = "NO_CANDLES_YET"
# Campaign 1-449, batch A (owner order 2026-08-23): the candle builder becomes
# a FRAME FACTORY per the owner's vision -- the SAME ticks build every
# configured timeframe simultaneously ("tick, 5 seconds, a minute, 15 minutes,
# an hour, 4 hours, a day ... each release is a batch -- every consumer takes
# the candle that suits it"). A frame is data, never code: enable or disable
# a timeframe by config alone. The default keeps the historical single 60s
# frame -- zero behavior change until the owner dials more frames in.
DEFAULT_TIMEFRAMES = ("60s",)

_TIMEFRAME_UNITS = {"s": 1.0, "m": 60.0, "h": 3600.0, "d": 86400.0}

# ٢٠٢٦-٠٩-١٠ (ختم NQ) — `_closed_periods` كان ينمو بلا حدّ: مجموعة تُضاف
# إليها كلّ فترة أُغلقت ولا يُنظَّف منها شيء أبدًا. بإطار 60s وسبعة رموز
# فذلك 1,440 عنصرًا لكلّ رمز يوميًّا، ويتضاعف مع كلّ إطار يُفعّله المالك.
# غرضها الوحيد كشف الشمعة المتأخّرة (`late_dropped`)، والتأخّر يُقاس
# بفترات قليلة لا بيوم كامل — فيكفي أن يُحفظ آخر ما أُغلق.
_CLOSED_MEMORY = 64


def _to_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _timeframe_seconds(text_value: Any) -> float | None:
    text = str(text_value or "").strip().lower()
    if len(text) < 2 or text[-1] not in _TIMEFRAME_UNITS:
        return None
    try:
        amount = float(text[:-1])
    except ValueError:
        return None
    seconds = amount * _TIMEFRAME_UNITS[text[-1]]
    return seconds if seconds > 0 else None


class Atom(AtomBase):

    def __init__(self) -> None:
        self._context: AtomContext | None = None
        self._running = False
        self._frames: tuple[tuple[str, float], ...] = ()
        # One candle state per (account, broker, symbol, timeframe-seconds).
        self._candles: dict[tuple[str, str, str, float], dict[str, Any]] = {}
        self._closed_periods: dict[tuple[str, str, str, float], set[float]] = {}
        self._last_seq: dict[tuple[str, str, str], int] = {}
        self._last_tick: dict[tuple[str, str, str], tuple] = {}
        self.candles_closed_count = 0
        self.closed_on_time = 0
        self.closed_by_frame: dict[str, int] = {}
        self.batch_releases = 0
        self.out_of_order_dropped = 0
        self.duplicates_dropped = 0
        self.late_dropped = 0
        # ٢٠٢٦-١٠-٠٢ (ختم المالك «صلح كامل nq»): جزءٌ من `late_dropped` — تِكّة
        # فترتها أقدم من الشمعة الجارية ولم تُفتح قطّ (لا تطابق ما أُغلق).
        self.late_unopened_dropped = 0
        self.gap_affected_candles = 0
        self.unusable_dropped = 0
        # ٢٠٢٦-٠٩-١٠ (ختم NQ) — كلّ شمعة تخرج بحجم صفر ولا أحد يعلم.
        # التِكّة تصل بـ`volume = null` دائمًا (مقيس: 3 من 3 تِكّات، و0
        # من 25 حزمة خام من سي‑تريدر)، فـ`max(0.0, volume or 0.0)` تعطي
        # صفرًا في كلّ شمعة — وشموع هذه الذرّة يستهلكها 24 ذرّة، فأيّ
        # تحليل يستند إلى حجم الشمعة يعمل على أصفار ولا يشكو.
        # العلّة فوقنا (لا حجم في تغذية الفوركس)، والعدّ هنا يكشفها بدل
        # أن يُترك الصفر يبدو حقيقةً سوقيّة. و`tick_count` هو البديل
        # الصادق للحجم وهو منشور أصلًا في كلّ شمعة.
        self.ticks_without_volume = 0

    async def initialize(self, context: AtomContext) -> None:
        self._context = context
        raw = context.config.get("timeframes") or list(DEFAULT_TIMEFRAMES)
        frames: list[tuple[str, float]] = []
        seen: set[float] = set()
        for item in raw if isinstance(raw, list) else [raw]:
            seconds = _timeframe_seconds(item)
            if seconds is None or seconds in seen:
                continue
            seen.add(seconds)
            frames.append((str(item).strip().lower(), seconds))
        self._frames = tuple(frames) or (
            (DEFAULT_TIMEFRAMES[0], _timeframe_seconds(DEFAULT_TIMEFRAMES[0]) or 60.0),)
        # ٢٠٢٦-١٠-١٢ (تفويض المالك الكامل «NQ» — نقاش ١٠-١٢ البند 10: «ممكن تكون مختلفة أو متأخّرة أو متقطّعة … بدّي الشارت
        # مثل سي‑تريدر»): (١) سعر الشمعة **العرض** كشارت الوسيط (`price_source: bid` في البيان؛ الافتراض mid للتوافق)، (٢) الشمعة تُغلق
        # **في وقتها** على نبض الثانية (بعد نهاية فترتها بـ`close_grace_s`) لا عند أوّل تِكّةٍ من الفترة التالية.
        self._price_source = str(context.config.get("price_source") or "mid").strip().lower()  # البيان الحيّ: bid
        self._close_grace_s = float(context.config.get("close_grace_s", 1.0))
        context.subscribe(EVENT_IN, self._on_tick)
        context.subscribe(EVENT_PULSE, self._on_pulse)

    async def _on_pulse(self, payload: dict[str, Any]) -> None:
        """يُغلق كلّ شمعةٍ انتهت فترتها — ولو لم تأتِ تِكّةٌ بعدها (السوق الهادئ لا يؤخّر الشموع)."""
        if not self._running or self._context is None or not isinstance(payload, dict):
            return
        now = _to_float(payload.get("official_time", payload.get("timestamp")))
        if now is None:
            return
        for frame_key, current in list(self._candles.items()):
            frame_seconds = frame_key[3]
            if now < current["period_start"] + frame_seconds + self._close_grace_s:
                continue
            name = next((n for n, s in self._frames if s == frame_seconds), str(frame_seconds))
            await self._close_candle(frame_key, name, frame_seconds, current)
            closed = self._closed_periods.setdefault(frame_key, set())
            closed.add(current["period_start"])
            while len(closed) > _CLOSED_MEMORY:
                closed.discard(min(closed))
            del self._candles[frame_key]
            self.closed_on_time += 1

    async def start(self) -> None:
        self._running = True

    async def stop(self) -> None:
        self._running = False

    async def shutdown(self) -> None:
        await self.stop()

    async def _on_tick(self, payload: dict[str, Any]) -> None:
        if not self._running or self._context is None or not isinstance(payload, dict):
            return
        symbol = str(payload.get("symbol") or "").strip()
        account = str(payload.get("account_id") or "").strip()
        broker = str(payload.get("broker") or "").strip()
        bid = _to_float(payload.get("bid"))
        ask = _to_float(payload.get("ask"))
        timestamp = _to_float(payload.get("timestamp"))
        if (not symbol or not account or not broker or bid is None or ask is None
                or timestamp is None or bid <= 0 or ask <= bid or timestamp <= 0):
            # ٢٠٢٦-٠٩-٠٧ — حارس دفاعيّ لا بوّابة كتم: 103 خلف المدقّق 112،
            # فلا يصله إلّا ما اجتاز الفحص. لكنّه كان يُسقط **صامتًا** بينما
            # إخوته الثلاثة (خارج الترتيب · التكرار · المتأخّرة) معدودون —
            # فصار له عدّاده. وبعد رفع الأحكام عن المصادر (618 · 622 · 613)
            # صارت حالات لم تكن تصل من قبل تصل، فالعدّ هنا هو ما يكشفها.
            # `ask <= bid` لا `ask < bid`: السبريد الصفريّ دفتر معطوب، وهو
            # ما يوافق 112 و106 بعد توحيدهما.
            self.unusable_dropped += 1
            return
        key = (account, broker, symbol)
        mid = bid if self._price_source == "bid" else (bid + ask) / 2.0   # الاسم بقي؛ القيمة سعر الشمعة
        volume = _to_float(payload.get("volume"))
        if volume is None:
            self.ticks_without_volume += 1
        fabric = bool(payload.get("fabric_gap"))

        seq = payload.get("sequence")
        if seq is not None:
            try:
                seq_i = int(seq)
            except (TypeError, ValueError):
                seq_i = None
            if seq_i is not None:
                last = self._last_seq.get(key)
                if last is not None and seq_i <= last:
                    self.out_of_order_dropped += 1
                    return
                self._last_seq[key] = seq_i

        tick_id = (timestamp, mid)
        if self._last_tick.get(key) == tick_id:
            self.duplicates_dropped += 1
            return
        self._last_tick[key] = tick_id

        released_this_tick = 0
        for frame_name, frame_seconds in self._frames:
            frame_key = (account, broker, symbol, frame_seconds)
            period_start = frame_period_start(timestamp, frame_seconds)
            if period_start in self._closed_periods.get(frame_key, ()):
                self.late_dropped += 1
                continue
            current = self._candles.get(frame_key)
            # ٢٠٢٦-١٠-٠٢ (ختم المالك «صلح كامل nq»): الحارس أعلاه يرفض الفترة
            # المغلقة **بالمطابقة** وحدها. تِكّةٌ متأخّرة من فترةٍ أقدم من الشمعة
            # الجارية لم تُفتح قطّ (تِكّات 1 ثمّ 125 ثمّ 70) كانت تمرّ فتُغلق
            # الشمعة الجارية مبكرًا وتُنشر شمعةٌ أقدم بعد أحدث وتضيع بقيّة الفترة
            # (مقيس بإعادة إنتاج المدقّق). كلّ فترةٍ أقدم من الجارية ماضٍ لا يُفتح:
            # تُعدّ متأخّرةً وتُرمى، ولها عدّادها باسمها.
            if current is not None and period_start < current["period_start"]:
                self.late_dropped += 1
                self.late_unopened_dropped += 1
                continue
            if current is not None and current["period_start"] != period_start:
                await self._close_candle(frame_key, frame_name, frame_seconds, current)
                closed = self._closed_periods.setdefault(frame_key, set())
                closed.add(current["period_start"])
                while len(closed) > _CLOSED_MEMORY:
                    closed.discard(min(closed))
                released_this_tick += 1
                current = None
            if current is None:
                self._candles[frame_key] = {
                    "period_start": period_start, "open": mid, "high": mid,
                    "low": mid, "close": mid, "tick_count": 1,
                    "volume": max(0.0, volume or 0.0), "provider": payload.get("provider"),
                    "fabric_gap": fabric}
                if fabric:
                    self.gap_affected_candles += 1
            else:
                if fabric and not current.get("fabric_gap"):
                    current["fabric_gap"] = True
                    self.gap_affected_candles += 1
                current["high"] = max(current["high"], mid)
                current["low"] = min(current["low"], mid)
                current["close"] = mid
                current["tick_count"] += 1
                current["volume"] += max(0.0, volume or 0.0)
        if released_this_tick > 1:
            self.batch_releases += 1

    async def _close_candle(self, frame_key: tuple[str, str, str, float],
                            frame_name: str, frame_seconds: float,
                            candle: dict[str, Any]) -> None:
        if self._context is None:
            return
        account, broker, symbol, _ = frame_key
        self.candles_closed_count += 1
        self.closed_by_frame[frame_name] = self.closed_by_frame.get(frame_name, 0) + 1
        await self._context.publish(EVENT_OUT, {
            "account_id": account, "broker": broker, "provider": candle.get("provider"),
            "symbol": symbol, "open": candle["open"], "high": candle["high"],
            "low": candle["low"], "close": candle["close"],
            "volume": candle["volume"], "tick_count": candle["tick_count"],
            "fabric_gap": bool(candle.get("fabric_gap", False)),
            "timeframe": frame_name,
            "period_start": candle["period_start"], "timestamp": candle["period_start"]})

    async def health_check(self) -> HealthStatus:
        if not self._running:
            return HealthStatus(state=HealthState.UNHEALTHY, message=REASON_NOT_STARTED)
        details = {"closed": self.candles_closed_count, "closed_on_time": self.closed_on_time,
                   "frames": [name for name, _ in self._frames],
                   "closed_by_frame": dict(self.closed_by_frame),
                   "batch_releases": self.batch_releases,
                   "out_of_order_dropped": self.out_of_order_dropped,
                   "duplicates_dropped": self.duplicates_dropped,
                   "late_dropped": self.late_dropped,
                   "late_unopened_dropped": self.late_unopened_dropped,
                   "gap_affected_candles": self.gap_affected_candles,
                   "unusable_dropped": self.unusable_dropped,
                   "ticks_without_volume": self.ticks_without_volume,
                   "active_scopes": [list(k) for k in self._candles]}
        if self.candles_closed_count == 0:
            return HealthStatus(state=HealthState.DEGRADED,
                                message=REASON_NO_CANDLES, details=details)
        message = "closed=%d frames=%d batch=%d ooo=%d dup=%d late=%d(unopened=%d) gap=%d unusable=%d" % (
            self.candles_closed_count, len(self._frames), self.batch_releases,
            self.out_of_order_dropped, self.duplicates_dropped,
            self.late_dropped, self.late_unopened_dropped, self.gap_affected_candles,
            self.unusable_dropped)
        if self.ticks_without_volume:
            message += " · بلا حجم=%d (الشموع تُغلق بـvolume=0 — استعمل tick_count)" % (
                self.ticks_without_volume)
        return HealthStatus(state=HealthState.HEALTHY, message=message, details=details)
