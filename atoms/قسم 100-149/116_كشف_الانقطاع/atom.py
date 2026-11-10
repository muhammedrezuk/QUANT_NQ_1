from __future__ import annotations

import math
from typing import Any

from core.contracts.atom import AtomBase, AtomContext, HealthState, HealthStatus

ATOM_VERSION = "4.1.0"

EVENT_TIME = "SYS_SECOND"
EVENT_INTERRUPTED = "market_data.feed_interrupted"
EVENT_RECOVERED = "market_data.feed_recovered"
EVENT_STATE = "market_data.feed.state"

REASON_NOT_STARTED = "NOT_STARTED"
REASON_NO_TIME = "NO_TIME_INPUT"

STATE_ACTIVE = "ACTIVE"
STATE_STALE = "STALE"
STATE_DEAD = "DEAD"
STATE_NEVER_SEEN = "NEVER_SEEN"
_SILENT_STATES = {STATE_STALE, STATE_DEAD}

# ٢٠٢٦-٠٩-٠٧ — هذه أسماء **مصادر** التغذية لا مخرجاتها. كان الاسم الثاني
# `feed.ctrader.tick`، وهو بعد فصل الدفتر لم يعد مصدرًا: صار مشتقًّا من قمّة
# الدفتر عبر 624 ثمّ 623. فأيّ عطل في إحداهما كان يظهر هنا **انقطاع تغذية**
# وهو ليس كذلك، والتغذية سليمة. المصدر الحقيقيّ هو `feed.ctrader.raw` من
# 622 نفسه — انقطاعه وحده انقطاع.
_FEED_EVENTS = ("feed.mt5.tick", "feed.ctrader.raw")
_DEAD_FACTOR = 2.0

# ٢٠٢٦-٠٩-١٠ (ختم NQ) — **الحالة تُحسب من سي‑تريدر وحده.**
#
# ما كان قائمًا: المصدران يتقاسمان عدّاد نشاط واحدًا (`_last_activity`)، فأيّ
# نبضة من أيّهما تُبقي الحالة `ACTIVE`. ولمّا كان ميتاتريدر أعلى معدّلًا —
# مقيس ٢٠٢٦-٠٩-١٠: **66 نبضة مقابل 24** في دقيقتين — فإنّ سقوط سي‑تريدر
# وحده لم يكن يُعلَن أبدًا: ميتاتريدر يغطّي عليه.
#
# وسي‑تريدر هو **المصدر الوحيد المعتمد للتحليل** بحكم المالك المختوم
# ٢٠٢٦-٠٨-٣١ («ما بصير ميتاتريدر يغذّي المحلّلين»)، ينفّذه 613 بـ
# `DEFAULT_ANALYST_SOURCES = ("CTRADER",)` ويحوّل ميتاتريدر إلى
# `market.broker_tick` — قناة عرض لا تبلغ محلّلًا. فحارسٌ يرتاح لنبض
# ميتاتريدر يحرس بابًا مهجورًا ويترك الباب الحيّ بلا عين.
#
# القاعدة الآن: `status` — وهو ما يقرؤه 454 و520 و704 — يُبنى على
# `_ANALYST_SOURCE` وحده. وحال المصدر الآخر لا تُكتم: تُعلن في `sources`
# كي يُرى صمته دون أن يزوّر الحكم. والأثر المقصود: **انقطاعات أكثر**،
# لأنّ ما كان يُخفى صار يُقال.
_ANALYST_SOURCE = "feed.ctrader.raw"


def num(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


class Atom(AtomBase):
    def __init__(self) -> None:
        self._context: AtomContext | None = None
        self._running = False
        self._stale_after = 0.0
        self._dead_after = 0.0
        self._now = 0.0
        self._last_by_source: dict[str, float] = {}
        self._seen_sources: set[str] = set()
        self._state: str | None = None
        self._interruption_count = 0
        self._state_heartbeat_s = 0.0
        self._last_heartbeat: float | None = None
        self.heartbeats_sent = 0

    @property
    def _seen(self) -> bool:
        """رُئي المصدر المعتمد — لا أيّ مصدر."""
        return _ANALYST_SOURCE in self._seen_sources

    @property
    def _last_activity(self) -> float | None:
        return self._last_by_source.get(_ANALYST_SOURCE)

    async def initialize(self, context: AtomContext) -> None:
        self._context = context
        self._stale_after = float(context.config["max_silence_seconds"])
        self._dead_after = float(context.config.get(
            "dead_after_seconds", self._stale_after * _DEAD_FACTOR))
        self._state_heartbeat_s = float(context.config.get("state_heartbeat_s", 30.0))
        for event in _FEED_EVENTS:
            context.subscribe(event, self._make_feed_handler(event))
        context.subscribe(EVENT_TIME, self._on_time)

    def _make_feed_handler(self, source: str):
        async def handler(payload: Any) -> None:
            await self._on_feed(source, payload)
        return handler

    async def start(self) -> None:
        self._running = True

    async def stop(self) -> None:
        self._running = False

    async def shutdown(self) -> None:
        await self.stop()

    async def _publish_state(self, state: str, elapsed: float | None = None,
                             force: bool = False) -> None:
        # ٢٠٢٦-٠٩-١٦ — `force` ينشر الحالة الراهنة ولو لم تتغيّر.
        #
        # العلّة المقيسة: `market_data.feed.state` حدثُ **حالة** يُنشر عند
        # التغيّر وحده — نُشر مرّتين في تشغيلة كاملة. فمن يفقد الحالة
        # ينتظر التغيّر التالي، وقد لا يأتي ساعات. ووقع ذلك فعلًا اليوم:
        # 454 (فلتر القرار) أُعيد تحميله ساخنًا فسقط إلى `feed_unknown`
        # في **1,199 قرارًا من 1,199** — حجب 100% وهو محقّ في حجبه:
        # قرارٌ على تغذيةٍ مجهولة الحال أسوأ من لا قرار.
        #
        # وإعادة النواة (`replayed`) لا تكفي: قِستُ 3 إعادات مقابل نشرتين
        # — تغطّي المشترك الجديد ولا تغطّي من يُعاد تحميله ساخنًا وقد
        # فاته كل شيء.
        #
        # والنبض لا يكذب: يعيد بثّ ما تعرفه الذرّة **الآن**، لا حالةً
        # محفوظة قد تكون بائتة. ولا يُطلق إنذار انقطاع ولا تعافٍ، لأنّ
        # `previous == state` فشرطاهما لا يتحقّقان.
        if self._context is None or (state == self._state and not force):
            return
        previous = self._state
        if state == previous:
            self.heartbeats_sent += 1
        self._state = state
        body = {
            "status": state,
            "seen": self._seen,
            "stale_after_seconds": self._stale_after,
            "dead_after_seconds": self._dead_after,
            "analyst_source": _ANALYST_SOURCE,
            "sources": self._source_ages(),
        }
        if elapsed is not None:
            body["elapsed_seconds"] = round(elapsed, 1)
        if self._now > 0:
            body["timestamp"] = self._now
        await self._context.publish(EVENT_STATE, body)
        if state in _SILENT_STATES and previous not in _SILENT_STATES:
            self._interruption_count += 1
            await self._context.publish(EVENT_INTERRUPTED, {
                **body, "interruption_count": self._interruption_count})
        elif state == STATE_ACTIVE and previous in _SILENT_STATES:
            await self._context.publish(EVENT_RECOVERED, {
                **body, "interruption_count": self._interruption_count})

    def _heartbeat_due(self, now: float) -> bool:
        """هل حان نبض إعادة بثّ الحالة؟ (بالساعة الرسميّة لا بساعة الجهاز)"""
        if self._state_heartbeat_s <= 0:
            return False
        last = self._last_heartbeat
        if last is None or now < last:
            self._last_heartbeat = now
            return True
        if now - last >= self._state_heartbeat_s:
            self._last_heartbeat = now
            return True
        return False

    def _source_ages(self) -> dict[str, Any]:
        """عمر صمت كل مصدر — يُعلَن ولا يُحكَم به إلّا للمعتمد."""
        ages: dict[str, Any] = {}
        for event in _FEED_EVENTS:
            last = self._last_by_source.get(event)
            if event not in self._seen_sources:
                ages[event] = None
            elif last is None or self._now <= 0:
                ages[event] = 0.0
            else:
                ages[event] = round(max(0.0, self._now - last), 1)
        return ages

    async def _on_feed(self, source: str, payload: Any) -> None:
        if not self._running or not isinstance(payload, dict):
            return
        self._seen_sources.add(source)
        if self._now > 0:
            self._last_by_source[source] = self._now
            if source == _ANALYST_SOURCE:
                await self._publish_state(STATE_ACTIVE, 0.0)

    async def _on_time(self, payload: Any) -> None:
        if not self._running or self._context is None or not isinstance(payload, dict):
            return
        now = num(payload.get("official_time"))
        if now is None:
            return
        self._now = now
        if not self._seen:
            await self._publish_state(STATE_NEVER_SEEN)
            return
        last = self._last_by_source.get(_ANALYST_SOURCE)
        if last is None:
            self._last_by_source[_ANALYST_SOURCE] = now
            await self._publish_state(STATE_ACTIVE, 0.0)
            return
        elapsed = max(0.0, now - last)
        if elapsed > self._dead_after:
            state = STATE_DEAD
        elif elapsed > self._stale_after:
            state = STATE_STALE
        else:
            state = STATE_ACTIVE
        await self._publish_state(state, elapsed, force=self._heartbeat_due(now))

    async def health_check(self) -> HealthStatus:
        if not self._running:
            return HealthStatus(state=HealthState.UNHEALTHY,
                                message=REASON_NOT_STARTED)
        ages = self._source_ages()
        details = {
            "status": self._state or STATE_NEVER_SEEN,
            "seen": self._seen,
            "last_activity": self._last_activity,
            "interruption_count": self._interruption_count,
            "analyst_source": _ANALYST_SOURCE,
            "sources": ages,
        }
        # أعمار المصادر في `message` لا في `details` وحدها: النواة تحذف
        # `details` قبل أن تبلغ اللوحة، فما لا يُكتب هنا لا يراه المالك.
        seen_txt = " ".join(
            "%s=%s" % (event.split(".")[1], "-" if ages[event] is None else ages[event])
            for event in _FEED_EVENTS)
        if self._state in (None, STATE_NEVER_SEEN):
            return HealthStatus(state=HealthState.DEGRADED,
                                message="%s (%s)" % (STATE_NEVER_SEEN, seen_txt),
                                details=details)
        if self._state in _SILENT_STATES:
            return HealthStatus(state=HealthState.DEGRADED,
                                message="%s (%s) انقطاعات=%d" % (
                                    self._state, seen_txt, self._interruption_count),
                                details=details)
        return HealthStatus(state=HealthState.HEALTHY,
                            message="%s (%s) انقطاعات=%d" % (
                                STATE_ACTIVE, seen_txt, self._interruption_count),
                            details=details)
