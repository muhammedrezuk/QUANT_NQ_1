from __future__ import annotations
from collections import deque
from typing import Any
from core.contracts.atom import AtomBase, AtomContext, HealthState, HealthStatus
from shared.decision_dials import (EVENT_COMMAND as EVENT_DIALS_COMMAND,
                                   apply_command, effective_value)
from shared.section_contract import section_atom
from shared.strategy_contract import StrategyRuntime, clip
from shared.tick_contract import VALIDATED_TICK_EVENT

ATOM_VERSION = "2.3.1"

# ٢٠٢٦-٠٩-٠٤ (ختم NQ §٣٥): أربعة عيارات تُعلن في `DIALS` أنّ مالكها هذه الذرّة
# (`"atom": "411"`)، وهذه الذرّة لم تكن تشترك بـ`decision.settings.command` ولا
# تنادي `apply_command` قطّ. فكل أمر اعتماد لها يسقط بلا مستلِم، ويبقى صفّها في
# السجلّ `source=UNSET` و`status=UNAPPROVED` **إلى الأبد** — لا يصلحه ضغط زرّ ولا
# إعادة تشغيل. واثنان منها (`medium`/`light`) يعلنان مفتاحَي إعداد لم يكونا في
# إعداد الذرّة أصلًا، فأُضيفا للمخطّط بقيمة صفر كما هي في السجلّ.
#
# والأثر لم يكن على الأخبار وحدها: `ParameterRegistry.unapproved()` لا يسأل عن
# صاحب المُعامِل، فمُعامِلٌ واحد غير معتمد يُبقي **كل** بطاقة قسم `provisional`
# بسبب `UNAPPROVED_PARAMETER`. مقيس ٢٠٢٦-٠٩-٠٤: ١٠٢ بطاقة، `weight_effect=0.0`
# في كلٍّ منها وأعماقها فوق المطلوب، و`active_weight=0.0` مقابل
# `available_weight=233.33`، فما أهّل ٤٥٥ مرّة واحدة في ٢٥٤٢ محاولة، وما خرج
# أمرٌ واحد. أربعة عيارات يتيمة أقفلت سلسلة القرار كلّها.
#
# ⛔ ما لا يفعله هذا التعديل: لا يغيّر سلوك حظر التداول حول الأخبار. نافذتا
#    `high` تعملان كما كانتا، و`medium`/`light` تُحفظان وتُعلنان ولا تحظران —
#    قيمتهما في السجلّ صفر، وحكم المالك بالورقة ق٧ صريح: «لا اختراع مدد».
_DIAL_HIGH_BEFORE = "NEWS_HIGH_WINDOW_BEFORE_MIN"
_DIAL_HIGH_AFTER = "NEWS_HIGH_WINDOW_AFTER_MIN"
_DIAL_MEDIUM = "NEWS_MEDIUM_WINDOW_MIN"
_DIAL_LIGHT = "NEWS_LIGHT_WINDOW_MIN"
EVENT_TICK = VALIDATED_TICK_EVENT
EVENT_NEWS = "market_data.news_received"
# ٢٠٢٦-٠٩-٢٣ (ختم `nq`): رُفع الاشتراك بـ`market.news.enriched` — ناشره الوحيد
# ٦١٥ أُرشف بختم المالك (`d77a5c0`، ٢٠٢٦-٠٩-١٩) والحدث بلا ناشر منذها. والذرّة
# لم تعمَ: تتغذّى من `market_data.news_received` (١٠٨) بالمعالج نفسه.
EVENT_OUT = "strategy.news.state"
EVENT_WINDOW = "news.trading_window.state"
COMPONENT_ID = "news_regime"
HIGH = "high"
MEDIUM = "medium"
LIGHT = "light"
UNKNOWN_FEED_CONFIDENCE = 50.0


def number(v):
    try:
        r = float(v)
    except (TypeError, ValueError):
        return None
    return r if r == r else None


def symbols(raw):
    if isinstance(raw, (list, tuple)):
        return [str(x).strip() for x in raw if str(x).strip()]
    return [
        x.strip()
        for x in str(raw or "").split(",")
        if x.strip() and x.strip().upper() != "UNKNOWN"
    ]


@section_atom("400", "411")
class Atom(AtomBase):
    def __init__(self):
        self._context = None
        self._running = False
        self._rt = StrategyRuntime(COMPONENT_ID, directional=False)
        self._by_symbol = {}
        self._seen_keys = deque(maxlen=1000)
        self._window_s = 3600
        self._before = 900
        self._after = 900
        self._seen = self._emitted = self._duplicates = 0
        self._no_time = 0
        self._no_tick_time = 0
        self._medium_min = 0.0
        self._light_min = 0.0
        self._dials_applied = 0

    async def initialize(self, c):
        self._context = c
        self._rt.configure(c.config)
        self._window_s = int(c.config.get("recent_window_s", 3600))
        # المعتمَد من السجلّ يعلو قيمة المانيفست؛ وغير المعتمَد تبقى المانيفست
        # هي السارية — نفس عقد ١٦٦ حرفيًّا (`effective_value`).
        self._before = effective_value(
            _DIAL_HIGH_BEFORE, float(c.config.get("high_window_before_min", 15))) * 60
        self._after = effective_value(
            _DIAL_HIGH_AFTER, float(c.config.get("high_window_after_min", 15))) * 60
        self._medium_min = effective_value(
            _DIAL_MEDIUM, float(c.config.get("medium_window_min", 0.0)))
        self._light_min = effective_value(
            _DIAL_LIGHT, float(c.config.get("light_window_min", 0.0)))
        c.subscribe(EVENT_TICK, self._on_tick)
        c.subscribe(EVENT_NEWS, self._on_news)
        c.subscribe(EVENT_DIALS_COMMAND, self._on_dial_command)

    async def _on_dial_command(self, payload: dict[str, Any]):
        """يستلم أمر عيارٍ تملكه هذه الذرّة ويطبّقه — بلا هذا المستلِم يسقط الأمر
        بصمت ويبقى العيار `UNAPPROVED` أبدًا (انظر التعليق أعلى الملفّ)."""
        if not self._running or self._context is None:
            return
        applied = apply_command(payload, atom_id="411")
        if applied is None:
            return
        name = applied["name"]
        value = float(applied["value"])
        if name == _DIAL_HIGH_BEFORE:
            self._before = value * 60
        elif name == _DIAL_HIGH_AFTER:
            self._after = value * 60
        elif name == _DIAL_MEDIUM:
            self._medium_min = value
        elif name == _DIAL_LIGHT:
            self._light_min = value
        else:
            return
        self._dials_applied += 1

    async def start(self):
        self._running = True

    async def stop(self):
        self._running = False

    async def shutdown(self):
        await self.stop()

    async def _on_news(self, p: dict[str, Any]):
        if not self._running or not isinstance(p, dict):
            return
        headline = str(
            p.get("headline_src") or p.get("headline_ar") or p.get("headline") or ""
        ).strip()
        if not headline:
            return
        key = " ".join(headline.lower().split())
        if key in self._seen_keys:
            self._duplicates += 1
            return
        self._seen_keys.append(key)
        impact = str(p.get("impact_level") or "").lower()
        grade = (
            HIGH
            if impact in ("high", "\u0639\u0627\u0644\u064a")
            else MEDIUM if impact == "medium" else LIGHT
        )
        # Owner stamp 2026-08-25: a headline with no publish time used to be
        # stamped with the wall clock, so a three-week-old item entered the
        # book looking like it broke this second -- and the high-impact window
        # is exactly a "did this happen within +/- 15 minutes" question.
        # Measured on the bridge table: 20 of 214 rows carry no publish time,
        # and the rows span 2026-08-04 to 2026-08-24. An invented time cannot
        # be told from a measured one, so the time stays UNKNOWN, is counted,
        # and the row is kept for the record but never claims freshness.
        stamp = number(p.get("published_at")) or number(p.get("timestamp"))
        if stamp is None:
            self._no_time += 1
        row = {
            "headline": headline,
            "grade": grade,
            "event_time": stamp,
            "source": p.get("source"),
        }
        for symbol in symbols(p.get("symbols")):
            self._by_symbol.setdefault(symbol, deque(maxlen=200)).appendleft(dict(row))

    async def _on_tick(self, p: dict[str, Any]):
        if not self._running or self._context is None or not isinstance(p, dict):
            return
        item = self._rt.ingest(p)
        if item is None:
            return
        tick, s = item
        self._seen += 1
        symbol = str(tick.get("symbol") or "")
        # Market time only -- never the wall clock. ingest() already refuses a
        # tick without a usable stamp, so the old "or time.time()" fallback was
        # unreachable; it is gone rather than left as a latent clock read.
        now = number(tick.get("source_timestamp")) or number(tick.get("timestamp"))
        if now is None:
            self._no_tick_time += 1
            return
        bucket = self._by_symbol.get(symbol, deque())
        timed = [row for row in bucket if row["event_time"] is not None]
        untimed = len(bucket) - len(timed)
        recent = [
            row
            for row in timed
            if now - row["event_time"] <= self._window_s
            or row["event_time"] - self._before
            <= now
            <= row["event_time"] + self._after
        ]
        high_active = [
            row
            for row in recent
            if row["grade"] == HIGH
            and row["event_time"] - self._before
            <= now
            <= row["event_time"] + self._after
        ]
        factor = 0.0 if high_active else 1.0
        confidence = 100.0 if recent or self._by_symbol else UNKNOWN_FEED_CONFIDENCE
        strength = clip(100.0 - factor * 100.0)
        if high_active:
            active = high_active[0]
            await self._context.publish(
                EVENT_WINDOW,
                {
                    "id": "news_regime_window",
                    "account_id": tick.get("account_id"),
                    "broker": tick.get("broker"),
                    "symbol": symbol,
                    "block": True,
                    "grade": HIGH,
                    "source_timestamp": active["event_time"],
                    # ٢٠٢٦-١٠-٠٢ (ختم المالك «صلح كامل nq»): حدّا النافذة في الحمولة.
                    # كانت تخرج بلا `window_start`/`window_end`، و٤٥٤ يُسقط كلّ نافذةٍ
                    # بلا `window_end` قبل أن يخزّنها — فعيارا المالك المعتمَدان (15 قبل
                    # و15 بعد، `OWNER`/`APPROVED`) لم يحجبا قرارًا واحدًا. والأساس الزمنيّ
                    # واحد: `event_time` هو `published_at` بثوانٍ UTC (`timegm` عند الكاتب؛
                    # ومقيسٌ حيًّا: `written_at − published_at` بين 14ث و81,595ث على آخر
                    # 300 خبر، صفرٌ منها سالب ⟸ لا إزاحة +3 ساعات)، و٤٥٤ يقارن بـ`time.time()`.
                    "window_start": active["event_time"] - self._before,
                    "window_end": active["event_time"] + self._after,
                    "headline": active["headline"],
                },
            )
        card = self._rt.card(
            tick,
            s,
            direction=0,
            strength=strength,
            confidence=confidence,
            signal="high_impact_window" if high_active else "news_context_clear",
            context_factor=factor,
            evidence={
                "news_count": len(recent),
                "high_active": len(high_active),
                "context_factor": factor,
                # Declared, never hidden: headlines held without a usable time.
                "untimed_news": untimed,
            },
        )
        await self._context.publish(EVENT_OUT, card)
        self._emitted += 1

    async def snapshot(self):
        return {
            "runtime": self._rt.snapshot(),
            "by_symbol": {k: list(v) for k, v in self._by_symbol.items()},
            "seen_keys": list(self._seen_keys),
            "seen": self._seen,
            "emitted": self._emitted,
            "duplicates": self._duplicates,
            "no_time": self._no_time,
            "no_tick_time": self._no_tick_time,
        }

    async def restore(self, x):
        if not isinstance(x, dict):
            return
        self._rt.restore(x.get("runtime"))
        self._by_symbol = {
            str(k): deque(v, maxlen=200)
            for k, v in (x.get("by_symbol") or {}).items()
            if isinstance(v, list)
        }
        self._seen_keys = deque((str(v) for v in x.get("seen_keys", [])), maxlen=1000)
        self._seen = int(x.get("seen", 0))
        self._emitted = int(x.get("emitted", 0))
        self._duplicates = int(x.get("duplicates", 0))
        self._no_time = int(x.get("no_time", 0))
        self._no_tick_time = int(x.get("no_tick_time", 0))

    async def health_check(self):
        if not self._running:
            return HealthStatus(state=HealthState.UNHEALTHY, message="NOT_STARTED")
        return HealthStatus(
            state=HealthState.HEALTHY if self._seen else HealthState.DEGRADED,
            message="ticks=%d news=%d no_time=%d"
            % (
                self._seen,
                sum(len(v) for v in self._by_symbol.values()),
                self._no_time,
            ),
            details={
                "ticks": self._seen,
                "emitted": self._emitted,
                "duplicates": self._duplicates,
                "no_time": self._no_time,
                "no_tick_time": self._no_tick_time,
            },
        )
