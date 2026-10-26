from __future__ import annotations

import time
from collections import deque
from typing import Any

from core.contracts.atom import AtomBase, AtomContext, HealthState, HealthStatus
from extraction_persistence import restore as restore_state, snapshot as snapshot_state
from extraction_retry import retry as retry_failed
from extraction_positions import update_legs
# ٢٠٢٦-١٠-٠١ (ختم المالك «Nq») — نُقل من هذا الملفّ **حرفيًّا** لحدّ ٤٠٠ سطرٍ فعليّ
# (م٩/ملف٤)، صفر تغيير سلوك: الأدوات المشتركة (الرقم · التذكرة · مفتاح الطلب المعلَّق)
# إلى `extraction_common`، وتأكيدُ الاستخراج من حدث الوسيط (`_on_trade`) إلى
# `extraction_confirmation` — وبقي هنا تفويضًا، و`_confirm` و`_fail_pending` في مكانهما.
from extraction_common import SEP, _number, _pending_key, _ticket
from extraction_confirmation import on_trade as confirm_trade
from shared.broker_refusals import retryable as refusal_retryable
from shared.market_hours import CLOSED, market_state

ATOM_VERSION = "5.5.0"
# 🔴 ٢٠٢٦-١٠-٢٦ (قانون صفقات المالك، ختم «NQ»: «صفقات انا بفتحها مالها علاقة بل منظومة ابدا») — مركز المالك لا يُستخرج
# منه. كانت `extraction_positions.update_legs` تعدّ كلّ مركزٍ في صورة ٦٠٩ ساقًا، ومعه صفقة المالك اليدويّة، فيُختار
# رابحًا ويُرسل عليه `CLOSE` أو `CLOSE_PARTIAL` بسحر المنظومة، ولا يوقفه إلّا حارس الملكيّة ٥٧٥. الآن يُسقط بالتمييز الواحد
# في `shared/owner_trades.py` (بسحر هذه الذرّة من إعدادها).
# 🔴 ٢٠٢٦-١٠-٠٥ (ختم المالك «إصلاحها NQ») — ثلاث عللٍ في طلب الذهب m0 (370$) العالق
# `FAILED` منذ ٠٩-٢٧، مقيسةٌ من جسر الإكسبرت:
#   ١) أمر الجني `CLOSE_PARTIAL 0.12` على التذكرة 1966966966 نُفّذ (`DONE OK` 22:16:02)
#      وأغلق المركز **كلّه** بعد ثانيتين من فتحه بربح 0.72$ — لأنّ `frac = 370/0.72`
#      يُحصر بواحد. فالرابح الذي لا يغطّي المبلغ صار انتظارًا لا إغلاقًا (`_covering`).
#   ٢) حدث الإغلاق وصل بلا `request_id`: الإكسبرت يكتبه فارغًا لكلّ `PARTIAL`/`CLOSED`
#      (`mt5/QUANT_NQ.mq5` `WriteEvent(…, reason, "", …)`)، فلم يُؤكَّد استخراجٌ واحد قطّ
#      وانتهى كلُّها بالمهلة. التأكيد صار بالتذكرة والحجم وسبب الإغلاق `SYSTEM` حين
#      يغيب الرقم (`extraction_confirmation.py`).
#   ٣) الطلب لا يُلغى حين يزول سببه: 524 يُلغي الآن مرحلةً نزل الربح الإجماليّ دونها
#      وينشر قائمتها حالةً (`asset.extraction.withdrawn.state`)، فيُسحب هنا من الانتظار
#      ومن الفاشل — ولو وصلت القائمة قبل الاستعادة (5.4.1: إقلاع 20:35 أثبت السباق).
# 🔴 ٢٠٢٦-٠٩-٢٦ (ختم المالك «Nq») — رفضُ الوسيط العابر انتظارٌ لا فشل، والسوق المغلق
# لا يُطرق.
#
# الذهب m0 (370$) أُرسل 09-25 15:30:08 على التذكرة 1965649602 فردّه الوسيط
# `RETCODE_10029` («مركزٌ مجمَّد»)، وأُغلقت التذكرة بوقفها بعد ثانية. فبقي هنا `FAILED`
# ولا يُعاد إلّا بطلبٍ صريح لا ناشر له، والشارتان صفراوان حتى اليوم. الآن الرفضُ المؤكَّد
# العابر (قائمته ومصدرها في `shared/broker_refusals.py`) يُحرّر التذكرة ويعيد الطلب إلى
# `_deferred` بمهلةٍ تتضاعف من دقيقة إلى ساعة، فيُنفَّذ على أوّل مركزٍ رابح. وما لم يثبت
# أنّه لم يُنفَّذ (المهلة 10012 نُفّذت فعلًا في ٠٩-٠٦) يبقى فشلًا يراه المالك.
# ومعه: لا يُرسل استخراجٌ على رمزٍ سوقُه مغلقة بجلسات الوسيط (`shared/market_hours.py`)،
# والتذكرة المشغولة بطلبٍ آخر تُتخطّى إلى رابحٍ غيرها بدل إعلان فشل، والحجمُ بخطوة الرمز
# من مواصفاته (كانت 0.01 للكلّ، وخطوة المؤشّرات 0.1).
#
# 🔴 ٢٠٢٦-٠٩-٢٥ (ختم المالك «Nq كل إصلاحات» وأمره «اقفل كل مشاكل») — الاستخراج ينتظر
# مركزًا رابحًا ولا يفشل لغيابه.
#
# كان طلب الاستخراج الجزئيّ الذي لا يجد مركزًا رابحًا مفتوحًا يُعلن `FAILED` بسبب
# `NO_PROFITABLE_OPEN_LEG` ويُرمى، ولا ناشرَ لـ`asset.extraction.retry_requested` —
# فيبقى عالقًا عند 524 إلى الأبد. مقيس ٢٠٢٦-٠٩-٢٥ 08:32:34: الذهب بلغ ربحًا إجماليًّا
# 1,330.87$ على ميزانية 740$، فطُلب استخراج 370$ لحظةَ أُغلقت الصفقة الرابحة نفسها،
# فلم يبقَ مركزٌ مفتوح يُستخرج منه. الآن يُحفظ الطلب في `_deferred` (ويُحفظ في اللقطة)،
# ويُنفَّذ مع أوّل صورة مراكز فيها مركزٌ رابح للرمز نفسه.

# سقفُ نافذة الفشل — حدُّ ذاكرةٍ لا قيمةَ تداول.
_MAX_FAILURES = 2048
#: مهلة إعادة ما ردّه الوسيط ردًّا عابرًا — تتضاعف مع كلّ رفضٍ من دقيقة إلى ساعة،
#: فرفضٌ يتكرّر لا يطرق الوسيط مع كلّ صورة مراكز.
_REFUSAL_RETRY_MIN_S = 60.0
_REFUSAL_RETRY_MAX_S = 3600.0
#: حقول الانتظار التي تبقى على الطلب إن أعاد 524 إصداره وهو منتظرٌ هنا.
_DEFER_FIELDS = ("refusals", "last_refusal", "refused_ticket", "retry_at")

EVENT_PARTIAL_REQ = "asset.extraction.requested"
EVENT_FULL_REQ = "asset.full_extraction.requested"
EVENT_POSITIONS = "platform.positions.state"
EVENT_TRADE = "platform.trade_event"
EVENT_MANAGE = "execution.manage.command"
EVENT_PENDING = "asset.extraction.execution_requested"
EVENT_DEACTIVATE = "perpetual.asset.deactivate"
EVENT_CONFIRMED = "asset.extraction.confirmed"
EVENT_FAILED = "asset.extraction.failed"
EVENT_PULSE = "SYS_SECOND"
EVENT_CMD_FAILED = "execution.command.failed"
EVENT_REJECTED = "execution.order.rejected"
EVENT_RETRY = "asset.extraction.retry_requested"
EVENT_SPECS = "market.symbol_specs"
# قائمة 524 للمراحل الملغاة — حالةٌ يعيدها الناقل لمن يشترك متأخّرًا (انظر 524).
EVENT_WITHDRAWN = "asset.extraction.withdrawn.state"

STATUS_REQUESTED = "REQUESTED"
STATUS_EXECUTING = "EXECUTING"
STATUS_FAILED = "FAILED"
STATUS_RETRY = "RETRY"
STATUS_SUCCESS = "SUCCESS"
ACTION_PARTIAL = "CLOSE_PARTIAL"
ACTION_CLOSE = "CLOSE"

REASON_NOT_STARTED = "NOT_STARTED"

LOT_DP = 8


class Atom(AtomBase):

    def __init__(self) -> None:
        self._dropped = 0
        self._context = None
        self._running = False
        self._lot_step = 0.01
        self._legs: dict[str, list[dict[str, Any]]] = {}
        self._pending_by_ticket: dict[str, dict[str, Any]] = {}
        self._pending_full: dict[str, dict[str, Any]] = {}
        self._partials = 0
        self._fulls = 0
        self._confirmed = 0
        self._failed = 0
        self._skipped = 0
        self._official_time = 0.0
        self._timeout_s = 30.0
        self._max_attempts = 1
        # ٢٠٢٦-٠٩-١٨ — كانت مجموعةً تُملأ ولا يُحذف منها شيء: كلُّ فشلٍ فريد
        # (`extraction_id:ticket:attempt:reason`) يبقى للأبد. الغرضُ منها
        # ألّا يُعدّ الفشل الواحد مرّتين، وذلك يقع في نفس الدورة — فطابورٌ
        # محدود يكفي، وسقفُه حدُّ ذاكرةٍ لا قيمةَ تداول.
        self._failure_ids: set[str] = set()
        self._failure_order: deque[str] = deque()
        self._magic = 20260801
        #: طلبات استخراجٍ جزئيّ تنتظر مركزًا رابحًا مفتوحًا — بهويّة الاستخراج.
        self._deferred: dict[str, dict[str, Any]] = {}
        self._deferred_total = 0
        #: مواصفات كلّ رمز من الوسيط (خطوة الحجم وجلسات التداول) — بـ`حساب|رمز`.
        self._specs: dict[str, dict[str, Any]] = {}
        self._refusals = 0
        self._last_refusal = ""
        self._closed_holds = 0
        self._migrated = 0
        self._cancelled = 0
        self._short_holds = 0
        self._withdrawn: set[str] = set()

    async def initialize(self, context: AtomContext) -> None:
        self._context = context
        self._lot_step = float(context.config.get("lot_step", 0.01))
        self._timeout_s = max(1.0, float(context.config.get("confirmation_timeout_s", 30.0)))
        self._max_attempts = max(1, int(context.config.get("max_attempts", 1)))
        self._magic = int(context.config.get("magic",20260801))
        context.subscribe(EVENT_POSITIONS, self._on_positions)
        context.subscribe(EVENT_PARTIAL_REQ, self._on_partial)
        context.subscribe(EVENT_FULL_REQ, self._on_full)
        context.subscribe(EVENT_TRADE, self._on_trade)
        context.subscribe(EVENT_PULSE, self._on_pulse)
        context.subscribe(EVENT_CMD_FAILED, self._on_command_failed)
        context.subscribe(EVENT_REJECTED, self._on_command_failed)
        context.subscribe(EVENT_RETRY, self._on_retry)
        context.subscribe(EVENT_SPECS, self._on_specs)
        context.subscribe(EVENT_WITHDRAWN, self._on_withdrawn)

    async def start(self) -> None:
        self._running = True

    async def stop(self) -> None:
        self._running = False

    async def shutdown(self) -> None:
        await self.stop()

    async def _on_positions(self, payload: dict[str, Any]) -> None:
        await update_legs(self, payload)
        await self._release_deferred()

    async def _on_specs(self, payload: dict[str, Any]) -> None:
        """مواصفات الرمز من الوسيط — تُحفظ ولو قبل البدء، فهي ذاكرةٌ لا فعل."""
        if not isinstance(payload, dict):
            return
        rows = payload.get("symbols")
        for row in rows if isinstance(rows, list) else []:
            if not isinstance(row, dict):
                continue
            account = str(row.get("account_id") or payload.get("account_id") or "")
            symbol = str(row.get("symbol") or "")
            if account and symbol:
                self._specs[account + SEP + symbol] = {field: row.get(field) for field in (
                    "volume_step", "trade_sessions", "server_gmt_offset", "trade_mode")}

    def _now(self) -> float:
        return self._official_time if self._official_time > 0 else time.time()

    def _market_closed(self, key: str) -> bool:
        """مغلقٌ بجلسات الوسيط نفسه — والمجهول ليس مغلقًا."""
        return market_state(self._specs.get(key), self._now()) == CLOSED

    def _step(self, key: str) -> float:
        step = _number((self._specs.get(key) or {}).get("volume_step"))
        return step if step is not None and step > 0 else self._lot_step

    def _free_winners(self, account_id: str, key: str) -> list[dict[str, Any]]:
        """المراكز الرابحة التي لا يشغلها طلبٌ آخر."""
        return [leg for leg in self._legs.get(key, [])
                if leg["profit"] > 0 and leg["volume"] > 0
                and _pending_key(account_id, leg["ticket"]) not in self._pending_by_ticket]

    def _covering(self, account_id: str, key: str, amount: float) -> list[dict[str, Any]]:
        """الرابحة الحرّة التي يغطّي ربحُها المبلغ — إغلاقُ جزءٍ منها يحقّقه فعلًا."""
        return [leg for leg in self._free_winners(account_id, key) if leg["profit"] >= amount]

    async def _on_withdrawn(self, payload: dict[str, Any]) -> None:
        """قائمة 524 للمراحل الملغاة (نزل الربح الإجماليّ دونها) — آخرها يحلّ محلّ ما قبله."""
        if not isinstance(payload, dict) or not isinstance(payload.get("withdrawn"), list):
            return
        self._withdrawn = {str(value) for value in payload["withdrawn"] if value}
        self._purge_withdrawn()

    def _purge_withdrawn(self) -> None:
        """يُسحب الملغى من الانتظار ومن الفاشل — والمُرسَل إلى الوسيط (`EXECUTING`) يبقى
        حتّى يُؤكَّد أو تنتهي مهلته، فلا يُنسى أمرٌ في الطريق. ويُنادى بعد الاستعادة أيضًا:
        القائمة تصل مع الاشتراك (قبل الاستعادة)، والاستعادة تعيد ما سُحب."""
        dropped = sum(1 for extraction_id in list(self._deferred)
                      if extraction_id in self._withdrawn
                      and self._deferred.pop(extraction_id, None) is not None)
        for key, row in list(self._pending_by_ticket.items()):
            if (str(row.get("extraction_id") or "") in self._withdrawn
                    and row.get("status") in (STATUS_FAILED, STATUS_RETRY)):
                self._pending_by_ticket.pop(key, None)
                dropped += 1
        self._cancelled += dropped

    async def _release_deferred(self) -> None:
        """ما انتظر مركزًا رابحًا يُنفَّذ حين يظهر — بالمسار نفسه لا بمسارٍ ثانٍ.

        ولا يُطلق قبل مهلته إن كان الوسيط قد ردّه، ولا في سوقٍ مغلقة.
        """
        if not self._running or not self._deferred:
            return
        now = self._now()
        for extraction_id, request in list(self._deferred.items()):
            if (_number(request.get("retry_at")) or 0.0) > now:
                continue
            account = str(request.get("account_id") or "")
            key = account + SEP + str(request.get("symbol") or "")
            if self._market_closed(key):
                continue
            if self._covering(account, key, _number(request.get("amount")) or 0.0):
                self._deferred.pop(extraction_id, None)
                await self._on_partial(request)

    def _defer(self, extraction_id: str, payload: dict[str, Any], why: str) -> None:
        """يحفظ الطلب منتظرًا — ويُعلن ذلك مرّةً لكلّ طلب لا مع كلّ صورة مراكز."""
        if extraction_id not in self._deferred:
            self._deferred_total += 1
            self._context.logger.warning(
                "579 استخراجٌ ينتظر (%s): %s %.2f$ (%s)", why,
                payload.get("symbol"), _number(payload.get("amount")) or 0.0, extraction_id)
        self._deferred[extraction_id] = dict(payload)

    async def _defer_refused(self, pending_key: str, reason: str) -> None:
        """رفضٌ عابرٌ مؤكَّد: تُحرَّر التذكرة ويعود الطلب منتظرًا بمهلةٍ تتضاعف."""
        pending = self._pending_by_ticket.pop(pending_key, None)
        if pending is None or self._context is None:
            return
        extraction_id = str(pending.get("extraction_id") or "")
        refusals = int(pending.get("refusals") or 0) + 1
        delay = min(_REFUSAL_RETRY_MAX_S, _REFUSAL_RETRY_MIN_S * (2 ** min(refusals - 1, 16)))
        self._refusals += 1
        self._last_refusal = reason
        self._deferred[extraction_id] = {
            "extraction_id": extraction_id, "request_id": extraction_id,
            "account_id": pending.get("account_id"), "symbol": pending.get("symbol"),
            "kind": "partial", "amount": pending.get("requested_amount"),
            "refusals": refusals, "last_refusal": reason,
            "refused_ticket": pending.get("ticket"), "retry_at": self._now() + delay}
        self._context.logger.warning(
            "579 ردّ الوسيط الاستخراج بـ%s على التذكرة %s — يعود منتظرًا مركزًا رابحًا"
            " بعد %.0fث (الرفض رقم %d): %s %.2f$ (%s)", reason, pending.get("ticket"),
            delay, refusals, pending.get("symbol"),
            _number(pending.get("requested_amount")) or 0.0, extraction_id)

    def _round_lot(self, volume: float, step: float | None = None) -> float:
        step = step if step is not None and step > 0 else self._lot_step
        stepped = round(volume / step) * step
        return round(stepped, LOT_DP)

    async def _fail_pending(self, pending_key: str, reason: str) -> None:
        pending = self._pending_by_ticket.get(pending_key)
        if pending is None or self._context is None:
            return
        failure_id = "%s:%s:a%s:%s" % (pending.get("extraction_id"), pending_key,
                                           pending.get("attempts"), reason)
        if failure_id in self._failure_ids:
            return
        self._failure_ids.add(failure_id); self._failure_order.append(failure_id)
        while len(self._failure_order) > _MAX_FAILURES:
            self._failure_ids.discard(self._failure_order.popleft())
        self._failed += 1
        pending.update({"status": STATUS_FAILED, "failure_reason": reason,
                        "last_attempt_at": self._official_time})
        extraction_id = str(pending.get("extraction_id") or "")
        full = self._pending_full.get(extraction_id)
        if full is not None:
            full["status"] = STATUS_FAILED; full["failure_reason"] = reason
            for other in full.get("expected", set()):
                if other in self._pending_by_ticket:
                    self._pending_by_ticket[other]["status"] = STATUS_FAILED
                    self._pending_by_ticket[other]["failure_reason"] = reason
        await self._context.publish(EVENT_FAILED, {
            **pending, "reason": reason, "failure_id": failure_id,
            "attempts": int(pending.get("attempts") or 0),
            "last_attempt_at": pending.get("last_attempt_at")})

    async def _on_pulse(self, payload: dict[str, Any]) -> None:
        if not self._running or not isinstance(payload, dict):
            return
        try: self._official_time = float(payload.get("official_time"))
        except (TypeError, ValueError): return
        for ticket, pending in list(self._pending_by_ticket.items()):
            created=_number(pending.get("created_at"))
            if created is None or created <= 0:
                pending["created_at"]=self._official_time;continue
            if (pending.get("status") == STATUS_EXECUTING and
                    self._official_time-created > self._timeout_s):
                await self._fail_pending(ticket, "EXTRACTION_CONFIRMATION_TIMEOUT")

    async def _on_command_failed(self, payload: dict[str, Any]) -> None:
        if not self._running or not isinstance(payload, dict):
            return
        account = str(payload.get("account_id") or "")
        ticket = _ticket(payload.get("ticket"))
        if not account or not ticket:
            return
        key = _pending_key(account, ticket)
        pending = self._pending_by_ticket.get(key)
        if pending is None:
            return
        request_id = str(payload.get("request_id") or "")
        if not request_id or request_id != str(pending.get("request_id") or ""):
            return
        reason = str(payload.get("reason") or "EXTRACTION_COMMAND_FAILED")
        if pending.get("kind") == "partial" and refusal_retryable(reason):
            # ردٌّ مؤكَّدٌ لم يُنفَّذ فيه شيء وعابرٌ بطبعه — انتظارٌ لا فشل.
            await self._defer_refused(key, reason)
            return
        await self._fail_pending(key, reason)

    async def _on_retry(self, payload: dict[str, Any]) -> None:
        await retry_failed(self, payload)

    async def _on_partial(self, payload: dict[str, Any]) -> None:
        if not self._running or self._context is None or not isinstance(payload, dict):
            return
        amount = _number(payload.get("amount"))
        account_id = str(payload.get("account_id") or "")
        symbol = str(payload.get("symbol") or "")
        extraction_id = str(payload.get("extraction_id") or payload.get("request_id") or "")
        if amount is None or amount <= 0 or not account_id or not symbol or not extraction_id:
            return
        # 🔴 ٢٠٢٦-٠٩-٢٦ — طلبٌ واحد لا يُنفَّذ مرّتين. إعادةُ 524 قد تصل والطلب في
        # الطريق إلى الوسيط، فيُهمل هنا بدل أن يُفتح استخراجٌ ثانٍ على تذكرةٍ أخرى.
        if any(str(row.get("extraction_id") or "") == extraction_id
               and row.get("status") in (STATUS_EXECUTING, STATUS_RETRY)
               for row in self._pending_by_ticket.values()):
            return
        if extraction_id in self._deferred:
            # منتظرٌ هنا أصلًا: يُحدَّث بما وصل ويبقى على مهلته، و`_release_deferred`
            # وحده يُطلقه — مسارٌ واحد لا اثنان.
            kept = self._deferred[extraction_id]
            self._deferred[extraction_id] = {
                **payload, **{field: kept[field] for field in _DEFER_FIELDS if field in kept}}
            return
        key = account_id + SEP + symbol
        if self._market_closed(key):
            # لا فشل ولا طرق: السوق مغلقة بجلسات الوسيط، والطلب ينتظر فتحها.
            self._closed_holds += 1
            self._defer(extraction_id, payload, "السوق مغلق")
            return
        winners = self._covering(account_id, key, amount)
        if not winners:
            # لا فشل: يُحفظ الطلب وينتظر أوّل مركزٍ رابح للرمز (`_release_deferred`).
            # والتذكرة المشغولة بطلبٍ آخر تُتخطّى — كانت تُعلن `TICKET_ALREADY_PENDING`
            # فشلًا لا يُعاد. ٢٠٢٦-١٠-٠٥: والرابح الذي لا يغطّي المبلغ ينتظر كذلك —
            # كان يُغلق كلّه (`frac` محصورٌ بواحد) فيحقّق 0.72$ من 370$ ويقتل صفقةً للتوّ فُتحت.
            short = bool(self._free_winners(account_id, key))
            self._short_holds += 1 if short else 0
            self._defer(extraction_id, payload,
                        "الرابح لا يغطّي المبلغ" if short else "لا مركز رابح حرّ")
            return
        best = max(winners, key=lambda leg: leg["profit"])
        frac = amount / best["profit"] if best["profit"] > 0 else 1.0
        frac = min(1.0, max(0.0, frac))
        step = self._step(key)
        close_vol = self._round_lot(best["volume"] * frac, step)
        if close_vol < step:
            close_vol = step
        if close_vol > best["volume"]:
            close_vol = self._round_lot(best["volume"], step)
        if 0.0 < self._round_lot(best["volume"] - close_vol, step) < step:
            close_vol = self._round_lot(best["volume"], step)
        ticket = _ticket(best["ticket"])
        pending_key = _pending_key(account_id, ticket)
        # لاحقةٌ جديدة لكلّ إرسالٍ بعد ردّ: ٥٧٥ يردّ `DUPLICATE_REQUEST_ID` كلَّ رقمٍ
        # سبق في جدول الأوامر، فالإعادة على التذكرة نفسها برقمها الأوّل تُرفض قبل الوسيط.
        attempt = int(_number(payload.get("refusals")) or 0) + 1
        request_id = "%s-%s-a%d" % (extraction_id, ticket, attempt)
        command = {"account_id": account_id, "magic":self._magic, "request_id": request_id,
                   "extraction_id": extraction_id, "action": ACTION_PARTIAL,
                   "ticket": best["ticket"], "symbol": symbol, "side": best["side"],
                   "volume": close_vol, "origin": "perpetual-extract",
                   "target_amount": amount}
        self._pending_by_ticket[pending_key] = {
            "extraction_id": extraction_id, "request_id": request_id,
            "account_id": account_id, "symbol": symbol, "kind": "partial",
            "requested_amount": amount, "ticket": best["ticket"],
            "status": STATUS_EXECUTING, "attempts": 1,
            "created_at": self._official_time, "last_attempt_at": self._official_time,
            "failure_reason": "", "command": command,
            # كم مرّةً ردّه الوسيط قبل هذه — بها تتضاعف المهلة إن رُدّ ثانيةً.
            "refusals": int(_number(payload.get("refusals")) or 0)}
        self._partials += 1
        await self._context.publish(EVENT_PENDING, dict(self._pending_by_ticket[pending_key]))
        await self._context.publish(EVENT_MANAGE, command)

    async def _on_full(self, payload: dict[str, Any]) -> None:
        if not self._running or self._context is None or not isinstance(payload, dict):
            return
        symbol = str(payload.get("symbol") or "")
        extraction_id = str(payload.get("extraction_id") or payload.get("request_id") or "")
        account_id = str(payload.get("account_id") or "")
        if not account_id or not symbol or not extraction_id:
            return
        key = account_id + SEP + symbol
        legs = self._legs.get(key, [])
        if not legs:
            self._skipped += 1
            await self._context.publish(EVENT_FAILED, {
                "extraction_id": extraction_id, "request_id": extraction_id,
                "account_id": account_id, "symbol": symbol,
                "status": STATUS_FAILED, "attempts": 0,
                "last_attempt_at": self._official_time, "reason": "NO_OPEN_LEGS"})
            return
        full = {"extraction_id": extraction_id, "account_id": account_id,
                "symbol": symbol, "expected": set(), "profits": [],
                "status": STATUS_EXECUTING, "failure_reason": ""}
        self._pending_full[extraction_id] = full
        for leg in legs:
            ticket = _ticket(leg["ticket"])
            pending_key = _pending_key(account_id, ticket)
            full["expected"].add(pending_key)
            if pending_key in self._pending_by_ticket:
                await self._fail_pending(pending_key, "TICKET_ALREADY_PENDING")
                self._pending_full.pop(extraction_id, None)
                return
            request_id = "%s-%s-a1" % (extraction_id, ticket)
            command = {"account_id": account_id, "magic":self._magic, "request_id": request_id,
                       "extraction_id": extraction_id, "action": ACTION_CLOSE,
                       "ticket": leg["ticket"], "symbol": symbol, "side": leg["side"],
                       "volume": leg["volume"], "origin": "perpetual-full"}
            self._pending_by_ticket[pending_key] = {
                "extraction_id": extraction_id, "request_id": request_id,
                "account_id": account_id, "symbol": symbol, "kind": "full",
                "requested_amount": _number(payload.get("amount", payload.get("target"))),
                "ticket": leg["ticket"], "status": STATUS_EXECUTING, "attempts": 1,
                "created_at": self._official_time, "last_attempt_at": self._official_time,
                "failure_reason": "", "command": command}
            await self._context.publish(EVENT_PENDING, dict(self._pending_by_ticket[pending_key]))
            await self._context.publish(EVENT_MANAGE, command)
        self._fulls += 1

    async def _on_trade(self, payload: dict[str, Any]) -> None:
        await confirm_trade(self, payload)

    async def _confirm(self, body: dict[str, Any]) -> None:
        self._confirmed += 1
        await self._context.publish(EVENT_CONFIRMED, body)

    async def snapshot(self) -> dict[str, Any]:
        state = snapshot_state(self, ATOM_VERSION)
        # الطلب المنتظر يُحفظ مع اللقطة: إقلاعٌ لا يُضيّع استخراجًا لم يُنفَّذ بعد.
        state["deferred"] = [dict(value) for value in self._deferred.values()]
        return state

    async def restore(self, state: dict[str, Any]) -> None:
        restore_state(self, state)
        deferred: dict[str, dict[str, Any]] = {}
        for row in state.get("deferred", []) if isinstance(state.get("deferred"), list) else []:
            if isinstance(row, dict):
                extraction_id = str(row.get("extraction_id") or row.get("request_id") or "")
                if extraction_id:
                    deferred[extraction_id] = dict(row)
        # 🔴 ٢٠٢٦-٠٩-٢٦ — ما عَلِق قبل 5.3.0 برفضٍ عابرٍ مؤكَّد (الذهب m0 · 10029) يعود
        # منتظرًا عند الإقلاع: تُحرَّر تذكرتُه ولا يُرسل شيءٌ الآن، ويُنفَّذ على أوّل
        # مركزٍ رابح في سوقٍ مفتوحة. والمهلة صفر: الردّ مضى عليه ما يزيد عن ساعتها.
        for key, row in list(self._pending_by_ticket.items()):
            if (row.get("status") != STATUS_FAILED or row.get("kind") != "partial"
                    or not refusal_retryable(row.get("failure_reason"))):
                continue
            extraction_id = str(row.get("extraction_id") or "")
            self._pending_by_ticket.pop(key, None)
            if not extraction_id or extraction_id in deferred:
                continue
            deferred[extraction_id] = {
                "extraction_id": extraction_id, "request_id": extraction_id,
                "account_id": row.get("account_id"), "symbol": row.get("symbol"),
                "kind": "partial", "amount": row.get("requested_amount"),
                "refusals": int(_number(row.get("refusals")) or 0) + 1,
                "last_refusal": row.get("failure_reason"),
                "refused_ticket": row.get("ticket"), "retry_at": 0.0}
            self._migrated += 1
        self._deferred = deferred
        self._purge_withdrawn()

    async def health_check(self) -> HealthStatus:
        if not self._running:
            return HealthStatus(state=HealthState.UNHEALTHY, message=REASON_NOT_STARTED)
        failed = sum(1 for row in self._pending_by_ticket.values()
                     if row.get("status") == STATUS_FAILED)
        details = {"partials": self._partials, "fulls": self._fulls,
                   "confirmed": self._confirmed, "failed": self._failed,
                   "skipped": self._skipped, "pending": len(self._pending_by_ticket),
                   "failed_pending": failed, "max_attempts": self._max_attempts,
                   "deferred": len(self._deferred), "refusals": self._refusals,
                   "last_refusal": self._last_refusal, "closed_holds": self._closed_holds,
                   "migrated": self._migrated, "specs": len(self._specs),
                   "cancelled": self._cancelled, "short_holds": self._short_holds}
        state = HealthState.DEGRADED if self._pending_by_ticket else HealthState.HEALTHY
        message = "EXTRACTION_FAILED_PENDING" if failed else "confirmed=%d pending=%d" % (
            self._confirmed, len(self._pending_by_ticket))
        if self._deferred:
            message += " · ينتظر_مركزًا_رابحًا=%d" % len(self._deferred)
            closed = sum(1 for row in self._deferred.values() if self._market_closed(
                str(row.get("account_id") or "") + SEP + str(row.get("symbol") or "")))
            if closed:
                message += " (سوقه_مغلق=%d)" % closed
        if self._refusals or self._migrated:
            # ما ردّه الوسيط يُسمّى بعدده وآخر رمزه — انتظارٌ معلَن لا صمت.
            message += " · ردّ_الوسيط=%d آخره=%s أُعيد_من_القديم=%d" % (
                self._refusals, self._last_refusal or "-", self._migrated)
        return HealthStatus(state=state, message=message, details=details)
