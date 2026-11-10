from __future__ import annotations

from typing import Any

from core.contracts.atom import AtomBase, AtomContext, HealthState, HealthStatus
from shared.broker_refusals import retryable as refusal_retryable

ATOM_VERSION = "3.5.1"
# 🔴 ٢٠٢٦-١٠-٠٥ (ختم المالك «إصلاحها NQ») — مرحلةٌ نزل الربح الإجماليّ دونها تُلغى.
# طلب الذهب m0 (370$ من ربحٍ إجماليّ 1,330.87$ على ميزانية 740$) بقي هنا `FAILED` منذ
# ٠٩-٢٧ والربح الإجماليّ اليوم −1,006.60$: الربح الذي وُجد ليُستخرج لم يعد موجودًا. وأخطر
# من الشارة الصفراء أنّه **حيّ**: لو صُفّر دفتر الأصل وظهر مركزٌ رابح، يُستخرج 370$ من
# دفترٍ جديد فيرفع `X` فوق `G` ويستهلك نصف الميزانية (`518/ledger_support.py:202`). الآن
# كلُّ صورة دفتر تُلغي طلبًا جزئيًّا مرحلتُه فوق الربح الإجماليّ القائم: يُسحب من الطلبات،
# وتُحرَّر المرحلة لتُصدر من جديد إن عاد الربح إليها، وتُنشر قائمة الملغى حالةً
# (`asset.extraction.withdrawn.state`) فيسحبه 579 من انتظاره ومن فاشله — ولو اشترك بعدنا.
# وفشلٌ يصل متأخّرًا عن طلبٍ أُلغي لا يُحييه.
# 🔴 ٢٠٢٦-٠٩-٢٦ (ختم المالك «Nq») — وردُّ الوسيط العابر انتظارٌ كذلك. طلب الذهب m0 عالقٌ
# هنا `FAILED` بـ`RETCODE_10029` («مركزٌ مجمَّد» — كانت التذكرة تُغلق بوقفها) منذ ٢٥ أيلول
# 15:30، ولا يُعاد لأنّ سببه ليس في `_WAITING_REASONS`. الآن يُعاد إصداره مرّةً كذلك متى
# كان سببه ردًّا مؤكَّدًا لم يُنفَّذ فيه شيء وعابرًا بطبعه (`shared/broker_refusals.py`)،
# ويأخذه 579 منتظرًا مركزًا رابحًا. والمهلة (10012) لا تُعاد: قد تكون نُفّذت.
#
# 🔴 ٢٠٢٦-٠٩-٢٥ (ختم المالك «Nq كل إصلاحات» وأمره «اقفل كل مشاكل») — «لا مركز رابح»
# انتظارٌ لا فشل. كان 579 يُعلنه `FAILED` فيبقى الطلب هنا عالقًا وتصفرّ الشارة إلى
# الأبد (الذهب m0: 370$ منذ 08:32:34). والآن 579 يحفظ الطلب حتى يظهر مركزٌ رابح، وما
# علق قبله بهذا السبب يُعاد إصداره هنا مرّةً واحدة فيأخذه 579 وينتظر.
_WAITING_REASONS = frozenset({"NO_PROFITABLE_OPEN_LEG"})
# v3.1.0 (2026-08-27, item 16/27 of the 27-atom review -- "silent restore
# on data corruption"): restore() silently RETURNED on a non-dict state
# (leaving self at its empty __init__ defaults, no error, no log) and
# then mutated self._issued/_confirmed/_pending/... through a sequence of
# field parses that could each raise -- a failure partway through left a
# torn mix of old and new milestone-issuance bookkeeping. That bookkeeping
# is what stops a milestone from being extracted twice; silently losing
# or tearing it on a corrupt snapshot risks re-issuing (real money)
# extraction requests for milestones already issued or even confirmed in
# the prior run. Fixed the same shape as 520: non-dict state now raises,
# and every field is built into a local first, committed to self only
# once ALL of them parse successfully.

EVENT_LEDGER = "risk.asset_ledger.state"
EVENT_STATE = "asset.extraction.state"
EVENT_PARTIAL = "asset.extraction.requested"
EVENT_FULL = "asset.full_extraction.requested"
EVENT_CONFIRM = "asset.extraction.confirmed"
EVENT_FAILED = "asset.extraction.failed"
EVENT_EXTRACTED = "risk.asset_profit.extracted"
# حالةٌ لا حدث: الناقل يعيد آخر `.state` لكلّ مشتركٍ متأخّر. مقيسٌ في إقلاع ٢٠٢٦-١٠-٠٥
# 20:35: 524 بدأ وألغى m0 قبل أن يُهيّأ 579 (الإقلاع ذرّةً ذرّة: تهيئة ثمّ استعادة ثمّ بدء)،
# فضاع الإعلان وبقي الطلب فاشلًا هناك. والاسم بلا `cancel`: الناقل يعدّ `.cancel` أمرًا
# (`core/event_bus.py` ‎_COMMAND_VERBS) والأمر لا يُعاد أبدًا.
EVENT_WITHDRAWN = "asset.extraction.withdrawn.state"
REASON_MILESTONE_LOST = "MILESTONE_NO_LONGER_MET"
#: سقف ذاكرة الطلبات الملغاة — حدُّ ذاكرةٍ لا قيمةَ تداول.
_CANCELLED_CAP = 256

KIND_PARTIAL = "partial"
KIND_FULL = "full"

REASON_NOT_STARTED = "NOT_STARTED"
REASON_NO_DATA = "NO_LEDGER_YET"

SEP = "|"
MONEY_DP = 4
LOOP_CAP = 60


def _number(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if result == result else None


def _key(account: Any, symbol: Any) -> str:
    return str(account or "") + SEP + str(symbol or "")


class Atom(AtomBase):

    def __init__(self) -> None:
        self._context = None
        self._running = False
        self._mult = 2.0
        self._fraction = 0.5
        self._full_targets: dict[str, float] = {}
        self._default_full = 0.0
        self._issued: dict[str, set[int]] = {}
        self._confirmed: dict[str, set[int]] = {}
        self._pending: dict[str, dict[str, Any]] = {}
        self._full_issued: set[str] = set()
        self._last_ledgers: dict[str, dict[str, Any]] = {}
        self._last_state: dict[str, Any] | None = None
        self._partials = 0
        self._fulls = 0
        self._confirmations = 0
        self._updates = 0
        self._failures = 0
        self._failure_ids: set[str] = set()
        self._reissued = 0
        self._cancelled_ids: list[str] = []
        self._cancelled = 0

    async def initialize(self, context: AtomContext) -> None:
        self._context = context
        cfg = context.config
        self._mult = float(cfg.get("milestone_mult", 2.0))
        self._fraction = float(cfg.get("extract_fraction", 0.5))
        self._default_full = _number(cfg.get("default_full_target")) or 0.0
        raw = cfg.get("full_targets") if isinstance(cfg.get("full_targets"), dict) else {}
        for k, value in raw.items():
            amount = _number(value)
            if amount is not None and amount > 0:
                self._full_targets[str(k)] = amount
        context.subscribe(EVENT_LEDGER, self._on_ledger)
        context.subscribe(EVENT_CONFIRM, self._on_confirm)
        context.subscribe(EVENT_FAILED, self._on_failed)

    async def start(self) -> None:
        self._running = True
        if self._cancelled_ids:
            # القائمة المستعادة تُعلَن مع البدء — فيستلمها 579 حين يشترك ولو بعدنا.
            await self._publish_withdrawn(None)

    async def _publish_withdrawn(self, last: dict[str, Any] | None) -> None:
        if self._context is not None:
            await self._context.publish(EVENT_WITHDRAWN, {
                "withdrawn": list(self._cancelled_ids), "count": self._cancelled, "last": last})

    async def stop(self) -> None:
        self._running = False

    async def shutdown(self) -> None:
        await self.stop()

    def _full_target(self, key: str) -> float:
        return self._full_targets.get(key, self._default_full)

    def _highest(self, gross: float, budget: float) -> int:
        if gross < budget or budget <= 0 or self._mult <= 1:
            return -1
        level = budget
        highest = -1
        for _ in range(LOOP_CAP):
            if gross < level:
                break
            highest += 1
            level *= self._mult
        return highest

    def _request_id(self, account: str, symbol: str, k: int) -> str:
        return "extract-%s-%s-m%d" % (account, symbol, k)

    async def _reissue_waiting(self) -> None:
        """يعيد إصدار طلبٍ جزئيّ عُدّ فاشلًا لسببٍ هو انتظار — مرّةً، ثمّ يعود «مطلوبًا»."""
        for request in list(self._pending.values()):
            reason = request.get("failure_reason")
            if (request.get("status") != "FAILED" or request.get("kind") != KIND_PARTIAL
                    or (reason not in _WAITING_REASONS and not refusal_retryable(reason))):
                continue
            for field in ("failure_reason", "attempts", "last_attempt_at", "ticket"):
                request.pop(field, None)
            request["status"] = "REQUESTED"
            request["reissued"] = int(request.get("reissued") or 0) + 1
            self._reissued += 1
            await self._context.publish(EVENT_PARTIAL, dict(request))

    async def _on_ledger(self, payload: dict[str, Any]) -> None:
        if not self._running or self._context is None or not isinstance(payload, dict):
            return
        rows = payload.get("ledgers")
        if not isinstance(rows, list):
            return
        await self._reissue_waiting()
        levels: list[dict[str, Any]] = []
        for led in rows:
            if not isinstance(led, dict):
                continue
            symbol = str(led.get("symbol") or led.get("asset_canonical") or "")
            if not symbol:
                continue
            account = str(led.get("account_id") or "")
            k = _key(account, symbol)
            self._last_ledgers[k] = dict(led)
            budget = _number(led.get("R", led.get("risk_budget", led.get("budget"))))
            gross = _number(led.get("realized_gross", led.get("gross_profit")))
            if gross is None:
                gross = _number(led.get("realized_net", led.get("realized_pnl")))
                if gross is None and "floating_economic" not in led and "floating" not in led:
                    gross = _number(led.get("net"))
            if not led.get("budgeted") or budget is None or budget <= 0 or gross is None:
                levels.append(self._level(led, -1, budget, gross, False))
                continue
            await self._cancel_lost_milestones(account, symbol, budget, gross)
            highest = self._highest(max(0.0, gross), budget)
            for milestone_k in range(highest + 1):
                await self._issue_partial_if_needed(account, symbol, budget, gross, milestone_k)
            await self._issue_full_if_needed(account, symbol, budget, gross)
            levels.append(self._level(led, highest, budget, gross, True))

        out = {"levels": levels, "requests": [dict(v) for v in self._pending.values()],
               "count": len(levels), "request_count": len(self._pending),
               "confirmed_count": self._confirmations}
        if payload.get("timestamp") is not None:
            out["timestamp"] = payload.get("timestamp")
        self._last_state = out
        self._updates += 1
        await self._context.publish(EVENT_STATE, out)

    def _level(self, led: dict[str, Any], highest: int, budget: float | None,
               gross: float | None, eligible: bool) -> dict[str, Any]:
        account = str(led.get("account_id") or "")
        symbol = str(led.get("symbol") or led.get("asset_canonical") or "")
        k = _key(account, symbol)
        issued = sorted(self._issued.get(k, set()))
        confirmed = sorted(self._confirmed.get(k, set()))
        next_value = (budget * (self._mult ** (highest + 1))
                      if budget is not None and budget > 0 else None)
        return {
            "account_id": account, "symbol": symbol,
            "R": budget, "budget": budget,
            "gross_profit": None if gross is None else round(gross, MONEY_DP),
            "K": led.get("K"), "X": led.get("X"),
            "highest_milestone": highest, "next_milestone": next_value,
            "issued_milestones": issued, "confirmed_milestones": confirmed,
            "pending": [dict(v) for v in self._pending.values()
                        if _key(v.get("account_id"), v.get("symbol")) == k],
            "full_target": self._full_target(k),
            "full_issued": k in self._full_issued,
            "eligible": eligible,
        }

    async def _cancel_lost_milestones(self, account: str, symbol: str, budget: float,
                                      gross: float) -> None:
        """طلبٌ جزئيّ لم يُؤكَّد ومرحلتُه فوق الربح الإجماليّ القائم — يُلغى ويُحرَّر."""
        k = _key(account, symbol)
        for request_id, request in list(self._pending.items()):
            if (request.get("kind") != KIND_PARTIAL or request.get("status") == "CONFIRMED"
                    or _key(request.get("account_id"), request.get("symbol")) != k):
                continue
            milestone_k = request.get("milestone_k")
            milestone = _number(request.get("milestone"))
            if milestone is None and isinstance(milestone_k, (int, float)):
                milestone = budget * (self._mult ** int(milestone_k))
            if milestone is None or gross >= milestone:
                continue
            self._pending.pop(request_id, None)
            if isinstance(milestone_k, (int, float)):
                self._issued.get(k, set()).discard(int(milestone_k))
            if request_id not in self._cancelled_ids:
                self._cancelled_ids.append(request_id)
            del self._cancelled_ids[:-_CANCELLED_CAP]
            self._cancelled += 1
            await self._publish_withdrawn({
                "extraction_id": request_id, "request_id": request_id,
                "account_id": account, "symbol": symbol, "kind": KIND_PARTIAL,
                "milestone_k": milestone_k, "milestone": milestone,
                "gross_profit": round(gross, MONEY_DP), "previous_status": request.get("status"),
                "reason": REASON_MILESTONE_LOST})

    async def _issue_partial_if_needed(self, account: str, symbol: str, budget: float,
                                       gross: float, milestone_k: int) -> None:
        k = _key(account, symbol)
        issued = self._issued.setdefault(k, set())
        if milestone_k in issued:
            return
        request_id = self._request_id(account, symbol, milestone_k)
        if request_id in self._pending:
            return
        milestone = budget * (self._mult ** milestone_k)
        amount = self._fraction * milestone
        if request_id in self._cancelled_ids:
            # عاد الربح إلى مرحلةٍ أُلغيت: تخرج من القائمة **قبل** الطلب الجديد، فلا تسحبه 579.
            self._cancelled_ids.remove(request_id)
            await self._publish_withdrawn(None)
        request = {
            "extraction_id": request_id, "request_id": request_id,
            "account_id": account, "symbol": symbol, "kind": KIND_PARTIAL,
            "amount": round(amount, MONEY_DP), "milestone_k": milestone_k,
            "milestone": round(milestone, MONEY_DP),
            "gross_profit": round(gross, MONEY_DP), "status": "REQUESTED",
        }
        issued.add(milestone_k)
        self._pending[request_id] = dict(request)
        self._partials += 1
        await self._context.publish(EVENT_PARTIAL, request)

    async def _issue_full_if_needed(self, account: str, symbol: str, budget: float,
                                    gross: float) -> None:
        k = _key(account, symbol)
        target = self._full_target(k)
        if target <= 0 or gross < target or k in self._full_issued:
            return
        request_id = "extract-full-%s-%s" % (account, symbol)
        if request_id in self._pending:
            return
        request = {"extraction_id": request_id, "request_id": request_id,
                   "account_id": account, "symbol": symbol, "kind": KIND_FULL,
                   "target": target, "amount": target,
                   "gross_profit": round(gross, MONEY_DP), "status": "REQUESTED"}
        self._full_issued.add(k)
        self._pending[request_id] = dict(request)
        self._fulls += 1
        await self._context.publish(EVENT_FULL, request)

    async def _on_failed(self, payload: dict[str, Any]) -> None:
        if not self._running or self._context is None or not isinstance(payload, dict):
            return
        request_id = str(payload.get("extraction_id") or payload.get("request_id") or "")
        if not request_id:
            return
        failure_id = str(payload.get("failure_id") or "%s:%s:%s" % (
            request_id, payload.get("ticket"), payload.get("reason")))
        if failure_id in self._failure_ids:
            return
        request = self._pending.get(request_id)
        if request is None and request_id in self._cancelled_ids:
            # فشلٌ متأخّر عن طلبٍ أُلغي (مهلة أمرٍ كان في الطريق) — لا يُحييه طلبًا فاشلًا.
            return
        self._failure_ids.add(failure_id); self._failures += 1
        if request is None:
            request = {"extraction_id": request_id, "request_id": request_id,
                       "account_id": payload.get("account_id"),
                       "symbol": payload.get("symbol"), "kind": payload.get("kind")}
            self._pending[request_id] = request
        request.update({"status": "FAILED", "failure_reason": payload.get("reason"),
                        "attempts": payload.get("attempts"),
                        "last_attempt_at": payload.get("last_attempt_at"),
                        "ticket": payload.get("ticket")})
        await self._context.publish(EVENT_STATE, {
            "failure": dict(request), "status": "FAILED",
            "reason": payload.get("reason"),
            "requests": [dict(value) for value in self._pending.values()],
            "failed_count": self._failures, "confirmed_count": self._confirmations})

    async def _on_confirm(self, payload: dict[str, Any]) -> None:
        if not self._running or self._context is None or not isinstance(payload, dict):
            return
        request_id = str(payload.get("extraction_id") or payload.get("request_id") or "")
        request = self._pending.get(request_id)
        if request is None or request.get("status") == "CONFIRMED":
            return
        actual = _number(payload.get("actual_amount", payload.get("amount")))
        if actual is None or actual <= 0:
            return
        amount = min(actual, _number(request.get("amount")) or actual)
        request["status"] = "CONFIRMED"
        request["confirmed_amount"] = round(amount, MONEY_DP)
        request["confirmed_at"] = payload.get("timestamp")
        self._pending.pop(request_id, None)
        self._confirmed.setdefault(_key(request.get("account_id"), request.get("symbol")), set()).add(
            int(request.get("milestone_k", -1))) if request.get("kind") == KIND_PARTIAL else None
        self._confirmations += 1
        await self._context.publish(EVENT_EXTRACTED, {
            "extraction_id": request_id, "request_id": request_id,
            "account_id": request.get("account_id"), "symbol": request.get("symbol"),
            "amount": round(amount, MONEY_DP), "milestone_k": request.get("milestone_k"),
            "kind": request.get("kind"), "confirmed": True,
            "actual_ticket": payload.get("ticket"),
        })
        await self._context.publish(EVENT_STATE, {
            "confirmation": dict(request), "confirmed_count": self._confirmations,
            "requests": [dict(v) for v in self._pending.values()],
        })

    async def health_check(self) -> HealthStatus:
        if not self._running:
            return HealthStatus(state=HealthState.UNHEALTHY, message=REASON_NOT_STARTED)
        failed = sum(1 for value in self._pending.values() if value.get("status") == "FAILED")
        details = {"updates": self._updates, "partials": self._partials,
                   "fulls": self._fulls, "confirmations": self._confirmations,
                   "failures": self._failures, "failed_pending": failed,
                   "pending": len(self._pending), "cancelled": self._cancelled}
        if self._last_state is None:
            return HealthStatus(state=HealthState.DEGRADED, message=REASON_NO_DATA, details=details)
        if failed:
            return HealthStatus(state=HealthState.DEGRADED,
                                message="EXTRACTION_FAILED_PENDING", details=details)
        if self._pending:
            return HealthStatus(state=HealthState.HEALTHY,
                                message="waiting_for_actual_confirmation=%d" % len(self._pending),
                                details=details)
        return HealthStatus(state=HealthState.HEALTHY,
                            # ٢٠٢٦-٠٩-١٦ (فحص شامل ٤٥٠–٥٩٩): `failures` و`failed_pending` في
            # `details` وحدها والنواة تحذفها — فتفشل عمليّات تخريج ولا يظهر
            # إلّا `confirmed=0`، وهو رقمٌ يُقرأ «لم يبدأ» لا «فشل».
            message="confirmed=%d%s" % (
                self._confirmations,
                " ⚠ فشل=%d" % self._failures if self._failures else ""),
            details=details)

    async def snapshot(self) -> dict[str, Any]:
        return {
            "version": ATOM_VERSION,
            "issued": {k: sorted(v) for k, v in self._issued.items()},
            "confirmed": {k: sorted(v) for k, v in self._confirmed.items()},
            "pending": list(self._pending.values()),
            "full_issued": sorted(self._full_issued),
            "failure_ids": sorted(self._failure_ids), "failures": self._failures,
            "cancelled_ids": list(self._cancelled_ids), "cancelled": self._cancelled,
        }

    async def restore(self, state: dict[str, Any]) -> None:
        if not isinstance(state, dict):
            raise ValueError("INVALID_EXTRACTION_STATE")
        new_issued = {str(k): {int(v) for v in values if isinstance(v, (int, float))}
                      for k, values in (state.get("issued") or {}).items()
                      if isinstance(values, list)}
        new_confirmed = {str(k): {int(v) for v in values if isinstance(v, (int, float))}
                         for k, values in (state.get("confirmed") or {}).items()
                         if isinstance(values, list)}
        new_pending = {str(v.get("extraction_id")): dict(v)
                       for v in state.get("pending", [])
                       if isinstance(v, dict) and v.get("extraction_id")}
        new_full_issued = {str(k) for k in state.get("full_issued", [])}
        new_failure_ids = {str(value) for value in state.get("failure_ids", [])}
        new_failures = int(state.get("failures") or 0)
        raw_cancelled = state.get("cancelled_ids")
        new_cancelled_ids = [str(value) for value in (raw_cancelled if isinstance(raw_cancelled, list) else [])
                             if value][-_CANCELLED_CAP:]
        new_cancelled = int(state.get("cancelled") or 0)
        self._cancelled_ids = new_cancelled_ids
        self._cancelled = new_cancelled
        self._issued = new_issued
        self._confirmed = new_confirmed
        self._pending = new_pending
        self._full_issued = new_full_issued
        self._failure_ids = new_failure_ids
        self._failures = new_failures
