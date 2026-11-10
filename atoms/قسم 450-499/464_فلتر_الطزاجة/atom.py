from __future__ import annotations

import os
import time
from typing import Any

from core.contracts.atom import AtomBase, AtomContext, HealthState, HealthStatus

ATOM_VERSION = "1.2.1"
# سقف أسماء الرموز البايتة في رسالة الصحّة — الرسالة تُعرض على اللوحة فلا
# تُترك تكبر بلا حدّ؛ ما يفيض يُعلن عددًا لا يُكتم.
_MAX_NAMED_STALE = 8
# v1.2.0 (2026-09-09, قسم 450-499) — مسار الاستطلاع القرصي كان ميّتًا مرّتين،
# فأُزيل بالكامل وبقي مقياس التِكّة الحيّة وحده:
#
# ١) المصدر مجمَّد. الإعداد كان `table_name: "prices"` على `nq_brain.db`،
#    وجدول `prices` فيه صفر صف: الإكسبرت انتقل إلى جداول `_v2` عمدًا، حتى
#    أنّ `governance/scripts/proof_bridges.py` يبرهن أنّ لا كتابة إليه، وفهرس
#    الأعطال يقول «لا تقرأ — مجمّدة». كل قرّاء الجسر (٦٠٩ · ٦١١ · ٦١٨ · ٦١٩)
#    نُقلوا إلى `_v2`؛ ٤٦٤ وحده تُرك خلفهم. مقيس حيًّا على المنصّة العاملة:
#    `reads=0 live=17533` — أي أنّ `_check_once` لم ينتج حكمًا واحدًا منذ
#    الإقلاع، والصحّة كانت تقول «سليم».
#
# ٢) وحتى لو امتلأ الجدول، حكمه كان يُلغى. المسار القرصي ينشر بحساب `"*"`،
#    والمسار الحيّ ينشر بحساب التِكّة الحقيقي. و٤٥٤ يدمج النطاقات بترتيب
#    `_symbol_records`: `("*", symbol)` أوّلًا ثم `(account, symbol)` — فالأخير
#    يطغى. وما دامت التِكّات الحيّة تجري، فحكم `"*"` لا يصل إلى أي قرار.
#
# ولا مصدر بديل صحيح: `ticks_v2` طابور يستهلكه ٦١٨ ويحذف منه
# (`delete_consumed: true` — ٢٣ صفًّا وقت القياس)، وهو تِكّات ميتاتريدر وحدها
# بينما سلسلة القرار تُغذّى من سي‑تريدر. فالمقارنة عبر الرموز صارت تُشتقّ من
# التِكّة الحيّة نفسها (`_newest_seen`) بلا قاعدة بيانات، وتُنشر مع كل حكم
# لتقرأها اللوحة، دون أن تصير حاجزًا ثانيًا بنطاق مهجور.
#
# ومكسب جانبي مقيس: توقّف فتحُ اتصال ومسحُ جدول كامل على ملف الجسر (٦٩٫٩ م.ب)
# كل خمس ثوانٍ، وهو الملف نفسه الذي يكتب فيه الإكسبرت.

EVENT_OUT = "decision.filter.freshness.state"
EVENT_PULSE = "SYS_SECOND"
EVENT_TICK = "market.tick.validated"

METHOD_LIVE = "live_tick_source_age"
ID_FILTER = "freshness_filter"
SIGNAL_PASS = "pass"
SIGNAL_BLOCK = "block"
STATUS_OK = "ok"
QUALITY_GOOD = "good"
QUALITY_LOW = "low"
REASON_NOT_STARTED = "NOT_STARTED"
REASON_NO_DATA = "NO_TICK_YET"


def _to_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if result == result else None


class Atom(AtomBase):
    def __init__(self) -> None:
        self._context: AtomContext | None = None
        self._running = False
        self._threshold_s = 0.0
        self._verdict: dict[tuple[str, str], bool] = {}
        self._newest_seen: dict[str, float] = {}
        self._live_ticks = 0
        self._emitted = 0
        self._no_stamp = 0
        self._official_time = 0.0
        self._blocked_now = 0

    async def initialize(self, context: AtomContext) -> None:
        self._context = context
        self._threshold_s = float(context.config["stale_threshold_s"])
        self._replay_newest = 0.0
        context.subscribe(EVENT_PULSE, self._on_pulse)
        context.subscribe(EVENT_TICK, self._on_tick)

    async def start(self) -> None:
        self._running = True

    async def stop(self) -> None:
        self._running = False

    async def shutdown(self) -> None:
        await self.stop()

    async def _on_pulse(self, payload: dict[str, Any]) -> None:
        if not isinstance(payload, dict):
            return
        stamp = _to_float(payload.get("official_time"))
        if stamp is not None:
            self._official_time = stamp

    async def _on_tick(self, payload: dict[str, Any]) -> None:
        if not self._running or not isinstance(payload, dict):
            return
        symbol = str(payload.get("symbol") or "").strip()
        if not symbol:
            return
        account = str(payload.get("account_id") or "*").strip() or "*"
        broker = str(payload.get("broker") or "").strip()
        source_stamp = _to_float(
            payload.get("exchange_timestamp", payload.get("timestamp"))
        )
        now = self._official_time or _to_float(payload.get("received_at")) or time.time()
        # ⚠️ وضع الإعادة (`QUANT_REPLAY_CLOCK=1`): المرجع هو أحدث طابع بيانات
        # مرّ، لا الساعة الرسمية. مقيس ٢٠٢٦-٠٩-٠٧: مع شريط تاريخي يصير
        # `now - source_stamp` ≈ ٥٫٦ يوم مقابل العتبة ⇒ `passed=False` دائمًا
        # ⇒ 454 `fail=freshness_filter` ⇒ 466 `BLOCKED_UPSTREAM` ⇒ 581
        # `targets=0` ⇒ `601 written=0`.
        # الافتراضي بلا المتغيّر: السلوك السابق حرفًا بحرف.
        if os.environ.get("QUANT_REPLAY_CLOCK", "").strip() == "1":
            if source_stamp is not None and source_stamp > self._replay_newest:
                self._replay_newest = source_stamp
            if self._replay_newest:
                now = self._replay_newest
        age_s = None if source_stamp is None else max(0.0, now - source_stamp)
        passed = age_s is not None and age_s <= self._threshold_s
        self._live_ticks += 1
        if source_stamp is None:
            # A8: قياس حقيقي أو لا شيء — التِكّة بلا طابع تُعدّ ولا تُخترع لها سنّ.
            self._no_stamp += 1
        else:
            if source_stamp > self._newest_seen.get(symbol, 0.0):
                self._newest_seen[symbol] = source_stamp
        self._verdict[(account, symbol)] = passed
        await self._emit(
            symbol, passed, age_s, account=account, broker=broker,
            source_stamp=source_stamp,
        )
        self._refresh_blocked_count()

    def _lag_vs_newest(self, source_stamp: float | None) -> float | None:
        """تأخّر هذا الرمز خلف أحدث رمز مرّ — معلومة للوحة، لا حاجز.

        كان هذا هو منهج `price_staleness_vs_newest` في المسار القرصي المتقاعد.
        يُشتقّ الآن من التِكّات الحيّة نفسها فيغطّي كل رمز تتداوله المنصّة، لا
        الرموز التي يصادف وجودها في جدول جسرٍ مجمَّد."""
        if source_stamp is None or not self._newest_seen:
            return None
        return max(0.0, max(self._newest_seen.values()) - source_stamp)

    def _refresh_blocked_count(self) -> None:
        self._blocked_now = sum(not passed for passed in self._verdict.values())

    async def _emit(
        self, symbol: str, passed: bool, age_s: float | None = None, *,
        account: str = "*", broker: str = "", source_stamp: float | None = None,
    ) -> None:
        if self._context is None:
            return
        await self._context.publish(EVENT_OUT, {
            "account_id": account,
            "broker": broker,
            "symbol": symbol,
            "id": ID_FILTER,
            "cycle_id": "",
            "status": STATUS_OK,
            "signal": SIGNAL_PASS if passed else SIGNAL_BLOCK,
            "score": 0,
            "confidence": 1.0 if passed else 0.0,
            "quality": QUALITY_GOOD if passed else QUALITY_LOW,
            "warnings": [],
            "metadata": {
                "method": METHOD_LIVE,
                "timeframe": "",
                "passed": passed,
                "measured_at": self._official_time or time.time(),
                "age_s": age_s,
                "lag_vs_newest_s": self._lag_vs_newest(source_stamp),
                "stale_threshold_s": self._threshold_s,
            },
        })
        self._emitted += 1

    async def health_check(self) -> HealthStatus:
        if not self._running:
            return HealthStatus(state=HealthState.UNHEALTHY, message=REASON_NOT_STARTED)
        details = {
            "live_ticks": self._live_ticks,
            "emitted": self._emitted,
            "no_stamp": self._no_stamp,
            "blocked_now": self._blocked_now,
            "threshold_s": self._threshold_s,
            "blocked_scopes": [
                list(scope) for scope, passed in self._verdict.items() if not passed
            ],
        }
        if self._live_ticks == 0:
            return HealthStatus(
                state=HealthState.DEGRADED,
                message=REASON_NO_DATA,
                details=details,
            )
        # ما يوضع في `details` يموت عند حدود النواة: `core/api/app.py`
        # (`_serialize_atom`) يُخرج من الصحّة `state` و`message` فقط. فاسم
        # الرمز البايت — وهو الحقيقة الوحيدة القابلة للتصرّف هنا — يُكتب في
        # `message` كي يبلغ اللوحة. `blocked=7` وحده لا يقول أيّها.
        stale = sorted({symbol for (_account, symbol), passed
                        in self._verdict.items() if not passed})
        listed = ",".join(stale[:_MAX_NAMED_STALE])
        if len(stale) > _MAX_NAMED_STALE:
            listed += ",+%d" % (len(stale) - _MAX_NAMED_STALE)
        return HealthStatus(
            state=HealthState.HEALTHY,
            message="live=%d blocked=%d emitted=%d no_stamp=%d%s" % (
                self._live_ticks, self._blocked_now, self._emitted,
                self._no_stamp, (" stale=" + listed) if listed else ""
            ),
            details=details,
        )
