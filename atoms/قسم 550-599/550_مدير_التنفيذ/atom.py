from __future__ import annotations

import time
from typing import Any

from core.contracts.atom import AtomBase, AtomContext, HealthState, HealthStatus
# ٢٠٢٦-١٠-٠١ (ختم المالك «Nq») — وحدةٌ شقيقة نُقل إليها جسدان من هذا الملفّ حرفيًّا
# لحدّ ٤٠٠ سطرٍ فعليّ (م٩/ملف٤)، صفر تغيير في السلوك: execution_manager_views —
# الحالة المنشورة (`_state`) والشارة (`health_check`) ونافذتها `_IDENTITY_ALERT_WINDOW_S`.
# الاسم يُستورد هنا كما كان، والطريقتان بقيتا في `Atom` تفويضًا بأسمائهما.
from execution_manager_views import _IDENTITY_ALERT_WINDOW_S
import execution_manager_views

ATOM_VERSION = "2.8.1"

EVENT_BUILT = "execution.order.built"
EVENT_FINAL = "trading.final_decision"
EVENT_REJECTED = "execution.order.rejected"
EVENT_SKIPPED = "execution.order.skipped"
EVENT_BRIDGE_WRITTEN = "platform.brain_signal.written"
EVENT_BRIDGE_FAILED = "platform.brain_signal.write_failed"
EVENT_ACK = "execution.command.ack"
EVENT_COMMAND_FAILED = "execution.command.failed"
EVENT_TRADE = "platform.trade_event"
EVENT_MANAGE_CMD = "execution.manage.command"
EVENT_MANAGE_WRITTEN = "execution.manage.written"
EVENT_OUTCOME = "market.outcome.realized"
EVENT_HALT = "emergency.halt"
EVENT_RESET = "risk.kill_switch.reset_requested"
EVENT_OUT = "execution.unified.state"

STAGE_BUILT = "ORDER_BUILT"
STAGE_FINALIZED = "DECISION_FINALIZED"
STAGE_QUEUED = "QUEUED_TO_BRIDGE"
STAGE_ACK = "BROKER_ACKNOWLEDGED"
STAGE_FAILED = "BROKER_COMMAND_FAILED"
STAGE_REJECTED = "ORDER_REJECTED"
STAGE_SKIPPED = "ORDER_SKIPPED"
STAGE_FILLED_OPEN = "FILLED_OPEN"
STAGE_FILLED_PARTIAL = "FILLED_PARTIAL"
STAGE_FILLED_CLOSED = "FILLED_CLOSED"

_STAGE_BY_TRADE = {
    "OPENED": STAGE_FILLED_OPEN,
    "PARTIAL": STAGE_FILLED_PARTIAL,
    "CLOSED": STAGE_FILLED_CLOSED,
}
_STAGE_RANK = {
    STAGE_SKIPPED: 1, STAGE_BUILT: 1, STAGE_FINALIZED: 2, STAGE_QUEUED: 3, STAGE_ACK: 4,
    STAGE_REJECTED: 5, "BRIDGE_WRITE_FAILED": 5, STAGE_FAILED: 5,
    STAGE_FILLED_OPEN: 6, STAGE_FILLED_PARTIAL: 6, STAGE_FILLED_CLOSED: 6,
}
# ══ تقليم سجلّ الأوامر — حكم المالك ٢٠٢٦-٠٩-١٠ ═══════════════════════════
#
# ⛔ العطب المقيس على النواة الحيّة قبل هذا العقد:
#
#     `_orders` لا يُحذف منه شيء أبدًا. بلغ **5,557 أمرًا** فصارت نشرة
#     `execution.unified.state` **1.77 ميغابايت**، و99.8% من عقدها ذلك
#     الحقل وحده. والنشرة الواحدة تكلّف حلقة النواة:
#
#         بناء `_state()`     1.85 م.ث   ⟵ نسخ 5,557 قاموسًا
#         التجميد            20.67 م.ث
#         ترميز البثّ         16.31 م.ث
#         ───────────────────────────
#                            38.83 م.ث   × 1.15 نشرة/ث = **4.5% من الحلقة**
#
#     والأخطر أنّها تنمو: 0.57 أمر/ث مقيسة ⟵ 20.1% عند 25,000 أمر،
#     و80.4% عند 100,000. نموٌّ غير محدود داخل المسار الساخن.
#
#     والحقل لا يقرؤه أحد خارج الذرّة: عقد اللوحة `ExecutionState` يقرأ
#     `counts` و`halted` و`last_order` و`last_outcome` و`reject_reasons`
#     و`skip_reasons` — ولا ذكر لـ`orders` فيه.
#
# ══ الحارس: ثلاثة شروط لا شرطٌ واحد ═══════════════════════════════════════
#
# لا يُزال سجلٌّ إلّا بإثبات الثلاثة معًا:
#
#     ١) **مرحلة نهائيّة** — لا رتبة أعلى تنتظره في `_STAGE_RANK`.
#     ٢) **لا التزام استعادة** — لا تذكرة حيّة عند الوسيط تحتاج معرفتَها
#        بعد الإقلاع. فـ`FILLED_OPEN` و`FILLED_PARTIAL` مركزٌ مفتوح: يبقيان.
#     ٣) **ليس في انتقال طائر** — `QUEUED_TO_BRIDGE` و`BROKER_ACKNOWLEDGED`
#        أمرٌ في الطريق، ومصيره لم يُعرف بعد: يبقيان.
#
# والتصنيف **قِسمةٌ كاملة** على `_STAGE_RANK` لا قائمةَ استثناء — يحرسها
# `_assert_stage_partition()` أدناه. فمرحلةٌ جديدة تُضاف غدًا تُسقِط الاستيراد
# فورًا بدل أن تنزلق صامتةً إلى جانب «يُحذف».
#
# ══ ونافذتا أمان لا نافذة ══════════════════════════════════════════════════
#
#     المرحلة النهائيّة
#       ↓  يبقى السجلّ التفصيليّ كاملًا           `_RETENTION_S`
#       ↓  يُزال التفصيل ويبقى أثر الرتبة         `_TOMBSTONE_S`
#       ↓  يُنسى الأثر
#
# الأثر (`retired_stages`) قاموسٌ **مسطّح** `مفتاح ⟵ رتبة`: عقدةُ تجميدٍ
# واحدة مهما كثر، لا عقدةٌ لكلّ سجلّ. وهو ما يمنع تراجع المرحلة بعد إزالة
# التفصيل: حدثٌ متأخّر برتبةٍ أدنى يُرفض كما كان يُرفض والسجلّ حاضر —
# فالسلوك مطابقٌ قبل التقليم وبعده، لا مجرّد قريب.
#
# مجموع الحماية 20 دقيقة، وأيّ حدثٍ يتأخّر أكثر من ذلك عن مرحلةٍ نهائيّة
# ليس تأخّرًا بل حدثٌ آخر.
_RETENTION_S = 300.0
_TOMBSTONE_S = 900.0
_PRUNE_EVERY_S = 1.0

# نهائيّة: لا تقدّم بعدها، ولا مركز مفتوح، ولا أمر في الطريق.
_TERMINAL_STAGES = frozenset({
    STAGE_SKIPPED, STAGE_REJECTED, "BRIDGE_WRITE_FAILED", STAGE_FAILED,
    STAGE_FILLED_CLOSED,
})
# حيّة: إمّا تنتظر رتبةً أعلى، أو تحمل التزام استعادة (تذكرة مفتوحة).
_LIVE_STAGES = frozenset({
    STAGE_BUILT, STAGE_FINALIZED, STAGE_QUEUED, STAGE_ACK,
    STAGE_FILLED_OPEN, STAGE_FILLED_PARTIAL,
})


def _assert_stage_partition() -> None:
    """كلّ مرحلةٍ مصنَّفة مرّةً واحدة — لا منسيّة ولا مزدوجة."""
    known = set(_STAGE_RANK)
    overlap = _TERMINAL_STAGES & _LIVE_STAGES
    if overlap:
        raise AssertionError("مرحلة مصنَّفة مرّتين: %s" % sorted(overlap))
    missing = known - _TERMINAL_STAGES - _LIVE_STAGES
    if missing:
        raise AssertionError("مرحلة بلا تصنيف: %s" % sorted(missing))
    unknown = (_TERMINAL_STAGES | _LIVE_STAGES) - known
    if unknown:
        raise AssertionError("مرحلة مصنَّفة بلا رتبة: %s" % sorted(unknown))


_assert_stage_partition()

_COUNT_KEYS = (
    "built", "order_skipped", "decision_finalized", "queued_to_bridge", "broker_acknowledged",
    "bridge_write_failed", "broker_command_failed", "rejected", "filled_open", "filled_partial",
    "filled_closed", "manage_commands", "manage_queued", "outcomes", "halts",
)


def _number(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if result == result else None


def _text(value: Any) -> str:
    return str(value or "").strip()


class Atom(AtomBase):

    def __init__(self) -> None:
        self._context: AtomContext | None = None
        self._running = False
        self._counts = {key: 0 for key in _COUNT_KEYS}
        self._counts_by_account: dict[str, dict[str, int]] = {}
        self._orders: dict[str, dict[str, Any]] = {}
        self._last_outcome_by_account: dict[str, dict[str, Any]] = {}
        self._halted_accounts: dict[str, str] = {}
        self._reject_reasons: dict[str, int] = {}
        self._skip_reasons: dict[str, int] = {}
        self._restore_error = ""
        self._rehydrated = False
        self._seen = 0
        self._identity_dropped = 0
        self._keyed_by_ticket = 0
        self._identity_dropped_mono = None
        self._identity_dropped_by: dict[str, int] = {}
        # ── التقليم ──
        # ساعةٌ قابلة للاستبدال: الاختبار يقود الزمن ولا ينتظره.
        self._clock = time.monotonic
        self._retired_at: dict[str, float] = {}   # بلغ النهاية — والتفصيل باقٍ
        self._retired: dict[str, int] = {}        # التفصيل أُزيل — والرتبة باقية
        self._retired_born: dict[str, float] = {}
        self._last_prune = 0.0
        self._pruned = 0
        self._forgotten = 0
        self._regression_blocked = 0
        self._resurrected = 0

    async def initialize(self, context: AtomContext) -> None:
        self._context = context
        for event, handler in (
            (EVENT_BUILT, self._on_built), (EVENT_FINAL, self._on_final),
            (EVENT_REJECTED, self._on_rejected), (EVENT_SKIPPED, self._on_skipped),
            (EVENT_BRIDGE_WRITTEN, self._on_bridge_written),
            (EVENT_BRIDGE_FAILED, self._on_bridge_failed),
            (EVENT_ACK, self._on_ack), (EVENT_COMMAND_FAILED, self._on_command_failed),
            (EVENT_TRADE, self._on_trade), (EVENT_MANAGE_CMD, self._on_manage_cmd),
            (EVENT_MANAGE_WRITTEN, self._on_manage_written),
            (EVENT_OUTCOME, self._on_outcome), (EVENT_HALT, self._on_halt),
            (EVENT_RESET, self._on_reset), (EVENT_OUT, self._rehydrate),
        ):
            context.subscribe(event, handler)

    async def start(self) -> None:
        self._running = True

    async def stop(self) -> None:
        self._running = False

    async def shutdown(self) -> None:
        await self.stop()

    @staticmethod
    def _key(account: str, request_id: str) -> str:
        return account + "\x1f" + request_id

    def _account_counts(self, account: str) -> dict[str, int]:
        return self._counts_by_account.setdefault(account, {key: 0 for key in _COUNT_KEYS})

    def _summary(self, payload: dict[str, Any], stage: str) -> dict[str, Any]:
        return {
            "account_id": _text(payload.get("account_id")),
            "broker": _text(payload.get("broker")),
            "request_id": _text(payload.get("request_id") or payload.get("command_id")),
            "stage": stage,
            "symbol": _text(payload.get("symbol")),
            "side": _text(payload.get("side")),
            "action": _text(payload.get("action")),
            "volume": _number(payload.get("volume")),
            "ticket": payload.get("ticket"),
            "reason": _text(payload.get("reason")),
            "timestamp": payload.get("timestamp", payload.get("done_at")),
        }

    async def _record(self, payload: dict[str, Any], stage: str, count_key: str) -> None:
        if not self._running or not isinstance(payload, dict):
            return
        account = _text(payload.get("account_id"))
        request_id = _text(payload.get("request_id") or payload.get("command_id"))
        # ⚖️ ٢٠٢٦-٠٩-١٧ — التذكرة تكفي حين يغيب الطلب.
        #
        # التعليق أدناه كان يعرف الحقيقة ولا يعمل بها: «حدثُ إغلاقٍ بلا
        # `request_id` قد يكون حقيقةً لا عطلًا — صفقة أُغلقت بستوبها عند
        # الوسيط فلا أمرَ منصّةٍ يُنسَب إليها». ثمّ **يُسقط الحدث**.
        #
        # والأثر مقيس على الشارة الحيّة:
        #     MISSING_EXECUTION_IDENTITY | dropped=5 منذ 92s
        #     stage:FILLED_CLOSED/request=4 · stage:FILLED_PARTIAL/request=1
        # أي أنّ الناقص هو `request` وحده — **والتذكرة حاضرة**. فمصير كل
        # صفقة تُغلق بوقفها (وهي الأغلبيّة المقيسة: ٣٠ من ٦٧) كان يختفي من
        # سجلّ مدير التنفيذ، وهو الذرّة التي وظيفتها تتبّع المصير.
        #
        # والتذكرة معرّفٌ كافٍ وأصدق: هي رابط الوسيط نفسه، ويحملها الحدث
        # من ٦١١ كما قرأه من الجسر. فتُستعمل مفتاحًا حين يغيب الطلب،
        # ويبقى الإسقاط لما لا هويّة له أصلًا — لا حساب ولا تذكرة.
        if not request_id and account and payload.get("ticket") is not None:
            request_id = "ticket:%s" % _text(payload.get("ticket"))
            self._keyed_by_ticket = getattr(self, "_keyed_by_ticket", 0) + 1
        if not account or not request_id:
            # ٢٠٢٦-٠٩-١٦: اسم المرحلة وحده لا يكفي للتشخيص. حدثُ إغلاقٍ بلا
            # `request_id` قد يكون **حقيقةً لا عطلًا**: صفقة أُغلقت بستوبها
            # عند الوسيط فلا أمرَ منصّةٍ يُنسَب إليها (مقيس اليوم في سجلّ
            # الصفقات: `TRADE_CLOSED … reason: SL` بعد `POSITION_VANISHED`).
            # أمّا غياب `account_id` فعطبُ هويّةٍ حقيقيّ. الحقل الساقط يُسمّى
            # ليُفصَل الاثنان بالقياس بدل الترجيح — ووجود التذكرة يُعلَن معه،
            # فهو ما يميّز حدثًا حقيقيًّا عن حمولةٍ فارغة.
            missing = []
            if not account:
                missing.append("account")
            if not request_id:
                missing.append("request")
            if payload.get("ticket") is None:
                missing.append("ticket")
            self._note_identity_drop("stage:%s/%s" % (stage, "+".join(missing)))
            return
        order_key = self._key(account, request_id)
        self._admit(order_key, payload, stage)
        self._counts[count_key] += 1
        self._account_counts(account)[count_key] += 1
        self._seen += 1
        await self._emit()

    def _admit(self, order_key: str, payload: dict[str, Any], stage: str) -> None:
        """قبول المرحلة أو رفضها — بالقاعدة نفسها سواء أكان التفصيل باقيًا أم أُزيل.

        القاعدة الأصليّة: يُكتب إن لم يكن ثمّة سجلّ، أو إن كانت الرتبة
        الواردة ≥ رتبة السجلّ. والتقليم لا يغيّرها؛ يغيّر **أين تُقرأ** رتبة
        السابق: من السجلّ التفصيليّ إن كان حاضرًا، ومن أثره إن أُزيل. فحدثٌ
        متأخّر برتبةٍ أدنى يُرفض في الحالتين — وهذا معنى «السلوك مطابق».
        """
        rank = _STAGE_RANK.get(stage, 0)
        current = self._orders.get(order_key)
        if current is not None:
            if rank < _STAGE_RANK.get(str(current.get("stage")), 0):
                self._regression_blocked += 1
                return
        else:
            retired_rank = self._retired.get(order_key)
            if retired_rank is not None:
                if rank < retired_rank:
                    self._regression_blocked += 1
                    return
                # رتبةٌ مساوية أو أعلى بعد إزالة التفصيل: انتقالٌ حقيقيّ
                # (FILLED_CLOSED ⟵ FILLED_OPEN مثلًا). يُبعث السجلّ.
                self._retired.pop(order_key, None)
                self._retired_born.pop(order_key, None)
                self._resurrected += 1
        summary = self._summary(payload, stage)
        # 🔴 ٢٠٢٦-٠٩-٢٣ — الوسيطُ لا يُدهَس بفراغ.
        #
        # مقيسٌ من لقطتي: **‎190‎ من ‎191‎ أمرًا تحمل `broker=''`**، والواحدُ
        # الباقي `ORDER_BUILT` وحده. لأنّ `_summary` تأخذ الوسيطَ من الحمولة
        # الواردة، وحمولاتُ الجسر (`BROKER_ACKNOWLEDGED` · `FILLED_OPEN` ·
        # `FILLED_CLOSED`) تُعرِّف بالتذكرة والحساب ولا تحمل وسيطًا — وهذا
        # صحيحٌ من جهتها. فكان كلُّ أمرٍ يولد بوسيطه ثمّ يفقده عند أوّل
        # مرحلةٍ تالية.
        #
        # والضررُ أنّ الهويّة الماليّة في المشروع ثلاثيّة
        # (حساب، وسيط، رمز) — ومن يقرأ `row["broker"]` مباشرةً من سجلّي
        # يبني نطاقًا لا يطابق نطاقَ أحد: `52992818||BTCUSD` مقابل
        # `52992818|Raw Trading Ltd|BTCUSD`. وثلاثةَ عشرَ مستهلكًا يقرأ
        # `execution.order.*`.
        #
        # ولا يُخترع وسيطٌ ولا يُستنتَج من حسابٍ آخر: يُحمَل **وسيطُ الأمر
        # نفسه** من مرحلته السابقة، وهو معلومٌ لأنّه وُلد به.
        if not summary.get("broker"):
            previous = current if current is not None else {}
            carried = _text(previous.get("broker"))
            if carried:
                summary["broker"] = carried
                self._broker_carried = getattr(self, "_broker_carried", 0) + 1
            else:
                self._broker_unknown = getattr(self, "_broker_unknown", 0) + 1
        self._orders[order_key] = summary
        if stage in _TERMINAL_STAGES:
            self._retired_at[order_key] = self._clock()
        else:
            # عاد إلى الطيران برتبةٍ مساوية — لا يُقلَّم.
            self._retired_at.pop(order_key, None)

    def _prune(self) -> None:
        """نافذتا الأمان — تُنفَّذان مرّةً في الثانية لا مع كلّ حدث."""
        now = self._clock()
        if now - self._last_prune < _PRUNE_EVERY_S:
            return
        self._last_prune = now
        detail_cutoff = now - _RETENTION_S
        for key, at in list(self._retired_at.items()):
            if at > detail_cutoff:
                continue
            record = self._orders.pop(key, None)
            del self._retired_at[key]
            if record is None:
                continue
            self._retired[key] = _STAGE_RANK.get(str(record.get("stage")), 0)
            self._retired_born[key] = now
            self._pruned += 1
        tomb_cutoff = now - _TOMBSTONE_S
        for key, born in list(self._retired_born.items()):
            if born > tomb_cutoff:
                continue
            del self._retired_born[key]
            self._retired.pop(key, None)
            self._forgotten += 1

    async def _on_built(self, payload: dict[str, Any]) -> None:
        await self._record(payload, STAGE_BUILT, "built")

    async def _on_final(self, payload: dict[str, Any]) -> None:
        await self._record(payload, STAGE_FINALIZED, "decision_finalized")

    async def _on_rejected(self, payload: dict[str, Any]) -> None:
        reason = _text(payload.get("reason"))
        if reason:
            self._reject_reasons[reason] = self._reject_reasons.get(reason, 0) + 1
        await self._record(payload, STAGE_REJECTED, "rejected")

    async def _on_skipped(self, payload: dict[str, Any]) -> None:
        reason = _text(payload.get("reason"))
        if reason:
            self._skip_reasons[reason] = self._skip_reasons.get(reason, 0) + 1
        await self._record(payload, STAGE_SKIPPED, "order_skipped")

    async def _on_bridge_written(self, payload: dict[str, Any]) -> None:
        await self._record(payload, STAGE_QUEUED, "queued_to_bridge")

    async def _on_bridge_failed(self, payload: dict[str, Any]) -> None:
        await self._record(payload, "BRIDGE_WRITE_FAILED", "bridge_write_failed")

    async def _on_ack(self, payload: dict[str, Any]) -> None:
        await self._record(payload, STAGE_ACK, "broker_acknowledged")

    async def _on_command_failed(self, payload: dict[str, Any]) -> None:
        await self._record(payload, STAGE_FAILED, "broker_command_failed")

    async def _on_trade(self, payload: dict[str, Any]) -> None:
        if not isinstance(payload, dict):
            return
        stage = _STAGE_BY_TRADE.get(_text(payload.get("event_type")).upper())
        if stage is None:
            return
        await self._record(payload, stage, stage.lower())

    async def _on_manage_cmd(self, payload: dict[str, Any]) -> None:
        if not self._running or not isinstance(payload, dict):
            return
        account = _text(payload.get("account_id"))
        if not account:
            self._note_identity_drop("manage_command")
            return
        self._counts["manage_commands"] += 1
        self._account_counts(account)["manage_commands"] += 1
        self._seen += 1
        await self._emit()

    async def _on_manage_written(self, payload: dict[str, Any]) -> None:
        if not self._running or not isinstance(payload, dict):
            return
        account = _text(payload.get("account_id"))
        if not account:
            self._note_identity_drop("manage_written")
            return
        self._counts["manage_queued"] += 1
        self._account_counts(account)["manage_queued"] += 1
        self._seen += 1
        await self._emit()

    async def _on_outcome(self, payload: dict[str, Any]) -> None:
        if not self._running or not isinstance(payload, dict):
            return
        account = _text(payload.get("account_id"))
        if not account:
            self._note_identity_drop("outcome")
            return
        self._last_outcome_by_account[account] = {
            "account_id": account, "symbol": _text(payload.get("symbol")),
            "profit": _number(payload.get("profit")), "result": payload.get("result")}
        self._counts["outcomes"] += 1
        self._account_counts(account)["outcomes"] += 1
        self._seen += 1
        await self._emit()

    async def _on_halt(self, payload: dict[str, Any]) -> None:
        if not self._running or not isinstance(payload, dict):
            return
        account = _text(payload.get("account_id"))
        if not account:
            self._note_identity_drop("halt")
            return
        self._rehydrated = True
        self._halted_accounts[account] = _text(payload.get("reason")) or "RISK_HALT"
        self._counts["halts"] += 1
        self._account_counts(account)["halts"] += 1
        self._seen += 1
        await self._emit()

    async def _on_reset(self, payload: dict[str, Any]) -> None:
        if not self._running or not isinstance(payload, dict):
            return
        account = _text(payload.get("account_id"))
        if account:
            self._halted_accounts.pop(account, None)
            # فكُّ المالك صريحٌ: علامة «مجهول بعد استعادةٍ فاشلة» تسقط معه،
            # وإلّا حملتها اللقطة التالية إلى كلّ إقلاعٍ بعدها بلا مخرج.
            self._halted_accounts.pop("__UNKNOWN__", None)
            self._rehydrated = True
            await self._emit()

    # ٢٠٢٦-١٠-٠١ (ختم «Nq»): جسدها في execution_manager_views.py — تفويضٌ بالاسم.
    def _state(self) -> dict[str, Any]:
        return execution_manager_views.state(self)

    async def _emit(self) -> None:
        self._prune()
        if self._context is not None:
            await self._context.publish(EVENT_OUT, self._state())

    async def _rehydrate(self, payload: dict[str, Any]) -> None:
        if self._rehydrated:
            return
        self._rehydrated = True
        if not isinstance(payload, dict):
            self._fail_closed()
            return
        try:
            self._load_state(payload)
        except ValueError:
            self._fail_closed()

    def _fail_closed(self) -> None:
        """استعادةٌ فشلت: الإيقاف لا يُقرأ «لا إيقاف» — يُعلَن مجهولًا موقوفًا.

        v2.8.0 (٢٠٢٦-٠٩-٢٣، ختم `nq`): `restore()` كان يرمي ويترك
        `_halted_accounts` فارغًا، فلقطةٌ فاسدة تُعيد الذرّة **مفتوحة** — وحارس
        بقاء الحماية أسقطها بهذا بالضبط. وكان الإغلاق في `_rehydrate` وحده
        وبلا إيقاف. والآن المساران واحد، كنمط ٥١٩: الحسابات المعروفة موقوفة،
        وإن لم يُعرف حسابٌ بعد فـ`__UNKNOWN__` — ويسقط بحالةٍ مستعادة من الشريط
        (`_rehydrate`) أو بفكٍّ صريح من المالك (`_on_reset`). (٥٥٠ للقراءة لا تحجب
        أمرًا؛ الإغلاق هنا صدقُ ما تعرضه.)
        """
        self._restore_error = "RESTORE_FAILED_FAIL_CLOSED"
        known = set(self._counts_by_account) | set(self._halted_accounts)
        self._halted_accounts = {account: "RESTORE_FAILED_FAIL_CLOSED"
                                 for account in known} or {
                                     "__UNKNOWN__": "RESTORE_FAILED_FAIL_CLOSED"}

    def _load_state(self, state: dict[str, Any]) -> None:
        counts = state.get("counts")
        by_account = state.get("counts_by_account")
        orders = state.get("orders")
        halted = state.get("halted_accounts")
        outcomes = state.get("last_outcome_by_account", {})
        if not all(isinstance(value, dict) for value in (counts, by_account, orders, halted, outcomes)):
            raise ValueError("INVALID_EXECUTION_MANAGER_STATE")
        self._counts = {key: int(counts.get(key, 0)) for key in _COUNT_KEYS}
        self._counts_by_account = {
            str(account): {key: int(row.get(key, 0)) for key in _COUNT_KEYS}
            for account, row in by_account.items() if isinstance(row, dict)}
        self._orders = {str(k): dict(v) for k, v in orders.items() if isinstance(v, dict)}
        self._restore_pruning(state)
        self._halted_accounts = {str(k): str(v) for k, v in halted.items()}
        self._last_outcome_by_account = {
            str(k): dict(v) for k, v in outcomes.items() if isinstance(v, dict)}
        reject_reasons = state.get("reject_reasons", {})
        skip_reasons = state.get("skip_reasons", {})
        self._reject_reasons = {str(k): int(v) for k, v in reject_reasons.items()} \
            if isinstance(reject_reasons, dict) else {}
        self._skip_reasons = {str(k): int(v) for k, v in skip_reasons.items()} \
            if isinstance(skip_reasons, dict) else {}
        self._restore_error = ""

    def _restore_pruning(self, state: dict[str, Any]) -> None:
        """الاستعادة تُعيد الحماية لا الحِمل.

        الأثر يُستعاد ويُمنح نافذته كاملةً من الآن — أطول من اللازم عمدًا،
        فالحماية تُشدَّد عند الشكّ لا تُرخى.

        أمّا السجلّات التفصيليّة النهائيّة القادمة من عمرٍ سابق للعمليّة فتُختم
        بزمنٍ منقضٍ، فيُزال تفصيلها في أوّل تقليم ويبقى أثرها. وهذا هو ما
        يُصرِّف الركام الموروث (5,557 سجلًّا) فور الإقلاع بدل أن يُحمَل خمس
        دقائق أخرى. والأوامر **الحيّة** لا تُمَسّ: هي وحدها ما تحتاجه
        الاستعادة، وهي التي تحمل التزام التذكرة المفتوحة.
        """
        retired = state.get("retired_stages", {})
        now = self._clock()
        self._retired = ({str(k): int(v) for k, v in retired.items()}
                         if isinstance(retired, dict) else {})
        self._retired_born = {key: now for key in self._retired}
        self._retired_at = {
            key: now - _RETENTION_S for key, record in self._orders.items()
            if str(record.get("stage")) in _TERMINAL_STAGES}
        self._last_prune = now - _PRUNE_EVERY_S

    async def snapshot(self) -> dict[str, Any]:
        return {"version": ATOM_VERSION, **self._state()}

    async def restore(self, state: dict[str, Any]) -> None:
        if not isinstance(state, dict):
            self._fail_closed()
            raise ValueError("INVALID_EXECUTION_MANAGER_STATE")
        try:
            self._load_state(state)
        except ValueError:
            self._fail_closed()
            raise

    def _note_identity_drop(self, source: str = "") -> None:
        self._identity_dropped += 1
        self._identity_dropped_mono = time.monotonic()
        # ٢٠٢٦-٠٩-١٦: كانت الشارة تقول «سقط اثنان» ولا تقول من أين، وخمسة
        # مسارات تنادي هذه الدالّة. بلا اسم المصدر لا يُعرَف أيّ ناشرٍ يرسل
        # حمولة بلا حساب أو بلا معرّف طلب، فيبقى العمى مُحصًى لا مُشخَّصًا.
        if source:
            self._identity_dropped_by[source] = self._identity_dropped_by.get(source, 0) + 1

    # ٢٠٢٦-١٠-٠١ (ختم «Nq»): جسد الشارة في execution_manager_views.py — تفويضٌ بالاسم.
    async def health_check(self) -> HealthStatus:
        return await execution_manager_views.health_check(self)
