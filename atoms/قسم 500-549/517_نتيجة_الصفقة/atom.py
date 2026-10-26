from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import clock
from core.contracts.atom import AtomBase, AtomContext, HealthState, HealthStatus
from shared.financial_truth import EVENT_SHORTAGE, FinancialTruth, bind_truth
from shared.durable_execution_journal import Journal
from shared.financial_scope import text
# ٢٠٢٦-١٠-٠٢ (ختم المالك «صلح كامل nq»): 4.5.0 رفع هذا الملفّ إلى ٥٥٣ سطرًا فعليًّا فوق حدّ الأربع
# مئة (المادة ٩ ملف ٤)، فنُقل منه **حرفيًّا** — صفر تغيير في السلوك، الموضعُ وحده — إلى ثلاثة أشقّاء:
#   trade_outcome_common.py — المفردات المشتركة: `EVENT_OUT` · `COSTS` · `LEG_*` · `STATUS_OPEN` ·
#       `CONSUMER` · `number` · `_digest` (ومعها شرح الأرجل ٢٠٢٦-٠٩-٢٤).
#   trade_outcome_legs.py — الأرجل والنتيجة: `IDENTITY_FIELDS` · `_leg_key` · `_leg_known` ·
#       `_output` · `_adopt_legacy` · `_sum_legs` · `_merge`.
#   trade_outcome_entry_costs.py — عمولة صفقة الدخول (ومعها شرحها): `ENTRY_FROM_*` · `_VOL_EPS` ·
#       `_entry_basis` وأختاها · `_mirror` · `_on_trade_event` · `_on_positions` · `_try_entry_from_view`.
# الطرق بقي لها هنا تفويضٌ بأسمائها، وكلّ اسمٍ كان على مستوى هذه الوحدة يُستورد باسمه كما كان.
from trade_outcome_common import CONSUMER, COSTS, EVENT_OUT, LEG_CLOSED, LEG_LEGACY, LEG_PARTIAL
from trade_outcome_common import STATUS_OPEN, _digest, number
from trade_outcome_legs import IDENTITY_FIELDS, WARNING_IDENTITY, _leg_key, _leg_known
from trade_outcome_entry_costs import ENTRY_FROM_DEAL, ENTRY_FROM_POSITION, _VOL_EPS
from trade_outcome_entry_costs import _EntryNotProven, _entry_basis, _key_volume
import trade_outcome_entry_costs
import trade_outcome_legs

ATOM_VERSION = "4.5.0"
EVENT_OUTCOME = "market.outcome.realized"
EVENT_ACCOUNT = "platform.account.state"
# ٢٠٢٦-١٠-٠٢ (ختم المالك «صلح كامل nq»): عمولة صفقة الدخول من حدث الفتح ومن صورة المركز —
# الشرح والجسد في trade_outcome_entry_costs.py، والاشتراكان هنا في `initialize`.
EVENT_TRADE = "platform.trade_event"
EVENT_POSITIONS = "platform.positions.state"
# العدّادات جزء من الحالة لا زينة فوقها.  بدون حفظها تُستعاد ثمانون نتيجة
# معالَجة ويبقى العدّاد صفرًا، فتقول الصحّة «بانتظار أوّل نتيجة» أبدًا بينما
# ٥٥٠ يعدّ ٨٠ و٥١٨ يسجّل خسارة محقّقة (مقيس ٢٠٢٦-٠٩-٠٩).
COUNTERS = ("outcomes", "emitted", "duplicates", "dropped_identity",
            "incomplete", "completed", "identity_incomplete", "late_legs",
            "entry_added", "entry_missing", "entry_late")
MIN_TIMEOUT_S = 0.05
WATCHDOG_MAX_SLEEP_S = 0.1
WATCHDOG_MIN_SLEEP_S = 0.01
WATCHDOG_DIVISOR = 4.0


def _rebased_config(raw_cfg: dict) -> dict:
    """config المانيفست على يد مالك المسارات — نسبةً لجذر الـruntime.

    الذرّة لا تعرف أين شُغِّلت: قراءة القيمة النسبية من المانيفست نسبةً إلى
    مجلد التشغيل كانت تُنشئ شجرة ``var/store`` موازية تحت جذر المشروع لا
    يقرأها أحد. لذلك تُحلَّ القيمة عند مالك المسارات: يُتقدَّم جذرُ تشغيل
    صالح (فيه ``shared/runtime_paths.py`` — نسخة الـruntime أو الجذر العام)،
    ثم تُمرَّر config إليه. المسار المطلق (``C:\\…`` في جسر المنصّة) يمرّ
    حرفيًّا — إعادة صياغته قرار نشر لا تصحيح مسار. وتعذُّر الحلّ يرجع
    config كما هي: لا يُعطَّل إقلاع ذرّة بأزمة مسار.
    """
    here = Path(__file__).resolve()
    code_root = None
    for parent in here.parents:
        if (parent / "shared" / "runtime_paths.py").is_file():
            code_root = parent
            break
    if code_root is None:
        return raw_cfg
    # ٢٠٢٦-٠٩-٢٣ — رُفع حقنُ `sys.path` من هنا: وزنٌ ميّت لا حماية.
    # `scripts/run_forex.py:9-11` ثمّ `governance/scripts/run_core.py:19-22`
    # يضعان جذرَ المشروع في رأس المسار عند كلّ إقلاع، وهو بعينه
    # `code_root` أدناه — فالشرطُ لا يتحقّق أبدًا. ونصُّ النواة صريح
    # (`core/bootloader.py:252`): لا حاجة لأن تحقن الذرّة المسارَ بنفسها.
    try:
        from shared.runtime_paths import manifest_config_rebase
        return manifest_config_rebase(raw_cfg, code_root=code_root)
    except Exception:  # noqa: BLE001 — لا يُعطَّل الإقلاع بأزمة مسار
        return raw_cfg


class Atom(AtomBase):

    def __init__(self) -> None:
        self._context: AtomContext | None = None
        self._running = False
        self._task: asyncio.Task | None = None
        self._brokers: dict[str, str] = {}
        self._truth = FinancialTruth("517")
        self._processed_event_ids: set[str] = set()
        self._pending: dict[str, dict[str, Any]] = {}
        self._deadlines: dict[str, float] = {}
        self._timeout_s = 30.0
        self._journal: Journal | None = None
        self._storage_error = ""
        self._outcomes = 0
        self._emitted = 0
        self._duplicates = 0
        self._dropped_identity = 0
        self._incomplete = 0
        self._completed = 0
        self._identity_incomplete = 0
        self._late_legs = 0
        #: مراكز لها أرجل جزئيّة تنتظر رِجل إغلاقها (حالتها في المخزن الدائم).
        self._open: set[str] = set()
        # ٢٠٢٦-١٠-٠٢ (ختم المالك «صلح كامل nq»): عمولة الدخول — انظر رأس الملفّ.
        self._entry_added = 0
        self._entry_missing = 0
        self._entry_late = 0
        #: مراكز تنتظر عمولة دخولها: النطاق ⟵ (حجم الفتح، أحجام الأجزاء، عمولاتها).
        self._awaiting_entry: dict[str, tuple[float, float, float]] = {}
        #: آخر صورةٍ من ٦٠٩ لكلّ مركز: (الحجم، العمولة) — تُفحص حين يصل الفتح بعدها.
        self._position_view: dict[str, tuple[float, float]] = {}

    async def initialize(self, context: AtomContext) -> None:
        self._context = context
        cfg = _rebased_config(context.config)
        self._timeout_s = max(MIN_TIMEOUT_S, float(context.config.get("cost_wait_timeout_s", 30.0)))
        path = str(cfg.get("consumer_db_path") or        # cfg مُ rebased — لا تُقرأ config خامًا
                   "var/store/risk_outcome_consumer_517.db")
        self._journal = Journal(path)
        try:
            self._journal.ensure()
            for scope, state in self._journal.consumer_states(CONSUMER).items():
                if state.get("status") == "PARTIAL":
                    self._pending[scope] = state
                    self._deadlines[scope] = clock.mono() + max(
                        0.0, float(state.get("remaining_s", self._timeout_s)))
                elif state.get("status") == STATUS_OPEN:
                    self._open.add(scope)
                self._mirror(scope, state)
        except Exception as exc:
            self._storage_error = type(exc).__name__
        context.subscribe(EVENT_OUTCOME, self._on_outcome)
        context.subscribe(EVENT_ACCOUNT, self._on_account)
        context.subscribe(EVENT_TRADE, self._on_trade_event)
        context.subscribe(EVENT_POSITIONS, self._on_positions)
        bind_truth(self, context, self._truth, ("equity",))

    async def start(self) -> None:
        self._running = True
        await self._flush_outbox()
        self._task = asyncio.create_task(self._watchdog())

    async def stop(self) -> None:
        self._running = False
        if self._task is not None and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._task = None

    async def shutdown(self) -> None:
        await self.stop()

    async def _flush_outbox(self) -> None:
        if self._context is None or self._journal is None or self._storage_error:
            return
        try:
            for output_id, event_name, payload in self._journal.pending_outputs():
                await self._context.publish(event_name, payload)
                self._journal.mark_emitted(output_id)
                self._emitted += 1
        except Exception as exc:
            self._storage_error = type(exc).__name__

    async def _on_account(self, payload: dict[str, Any]) -> None:
        if not self._running or not isinstance(payload, dict):
            return
        account = text(payload.get("account_id")); broker = text(payload.get("broker"))
        if account and broker:
            self._brokers[account] = broker
            if not self._truth.has(account, "equity") and self._context is not None:
                await self._context.publish(EVENT_SHORTAGE, self._truth.shortage_body(
                    account, "equity", broker=broker, detail="517 trade outcome"))

    def _scope(self, payload: dict[str, Any]) -> tuple[str, str, str, str] | None:
        account = text(payload.get("account_id"))
        broker = text(payload.get("broker")) or self._brokers.get(account, "")
        # ٢٠٢٦-٠٩-٢٤ — المركز بتذكرته أوّلًا: أرجلُه كلّها تحملها. رقمُ الطلب قد
        # يحمله بعضها دون بعض فيشقّ المركز نطاقين لا تصل أحدَهما رِجلُ إغلاق.
        # (مقيس اليوم: 400 رِجل، هويّة الصفقة فيها كلّها هي التذكرة.)
        trade = text(payload.get("ticket") or payload.get("trade_identity") or
                     payload.get("trade_id") or payload.get("order_id") or
                     payload.get("request_id"))
        event_id = text(payload.get("event_id"))
        if not account or not broker or not trade or not event_id:
            return None
        return account, broker, trade, event_id

    # ٢٠٢٦-١٠-٠٢ (ختم المالك «صلح كامل nq»): أجساد الأربع في trade_outcome_legs.py حرفيًّا —
    # تفويضٌ بالاسم: بناءُ النتيجة، وتبنّي حالةٍ قديمة بلا أرجل، وجمعُ الأرجل، ودمجُ رِجلٍ في المركز.
    def _output(self, state: dict[str, Any], completeness: str) -> dict[str, Any]:
        return trade_outcome_legs.output(self, state, completeness)

    @staticmethod
    def _adopt_legacy(state: dict[str, Any]) -> dict[str, Any]:
        return trade_outcome_legs.adopt_legacy(state)

    @staticmethod
    def _sum_legs(state: dict[str, Any]) -> None:
        trade_outcome_legs.sum_legs(state)

    def _merge(self, state: dict[str, Any], payload: dict[str, Any],
               account: str, broker: str, trade: str, remaining: float):
        return trade_outcome_legs.merge(self, state, payload, account, broker, trade, remaining)

    async def _on_outcome(self, payload: dict[str, Any]) -> None:
        if not self._running or not isinstance(payload, dict):
            return
        self._outcomes += 1
        identity = self._scope(payload)
        if identity is None:
            self._dropped_identity += 1
            return
        if self._journal is None or self._storage_error:
            return
        account, broker, trade, event_id = identity
        scope = account + "|" + broker + "|" + trade
        deadline = self._deadlines.get(scope, clock.mono() + self._timeout_s)
        remaining = max(0.0, deadline-clock.mono())
        initial = {"status": "PARTIAL", "remaining_s": self._timeout_s,
                   "account_id": account, "broker": broker, "trade_identity": trade}
        try:
            fresh, state = self._journal.reduce_consumer_event(
                event_id, account, "OUTCOME_REVISION", trade, payload, CONSUMER,
                scope, initial,
                lambda current: self._merge(current, payload, account, broker, trade, remaining))
        except Exception as exc:
            self._storage_error = type(exc).__name__
            return
        if not fresh:
            self._duplicates += 1
            return
        self._processed_event_ids.add(event_id)
        # ٢٠٢٦-١٠-٠٢: جزءٌ سُجّل يغيّر ما يُطرح من صورة المركز، وإغلاقٌ يُنهي الانتظار.
        self._mirror(scope, state)
        if state.get("status") in {"COMPLETE","INCOMPLETE"}:
            self._pending.pop(scope, None); self._deadlines.pop(scope, None)
            self._open.discard(scope); self._position_view.pop(scope, None)
            if state.get("status")=="COMPLETE" and state.get("terminal_input_id")==event_id:
                self._completed += 1
                if isinstance(state.get("entry"), dict):
                    self._entry_added += 1
                else:
                    self._entry_missing += 1
        elif state.get("status") == STATUS_OPEN:
            # المفتوح لا ينتظر تكاليف — ينتظر رِجل إغلاقه، فلا يدخل المهلة.
            self._pending.pop(scope, None); self._deadlines.pop(scope, None)
            self._open.add(scope)
        else:
            self._open.discard(scope)
            self._pending[scope] = state; self._deadlines[scope] = deadline
        await self._flush_outbox()
        if scope in self._awaiting_entry:
            await self._try_entry_from_view(scope)

    # ── ٢٠٢٦-١٠-٠٢ (ختم المالك «صلح كامل nq»): عمولة صفقة الدخول ─────────────
    # أجساد الأربع في trade_outcome_entry_costs.py حرفيًّا — تفويضٌ بالاسم.

    def _mirror(self, scope: str, state: dict[str, Any]) -> None:
        trade_outcome_entry_costs.mirror(self, scope, state)

    async def _on_trade_event(self, payload: dict[str, Any]) -> None:
        await trade_outcome_entry_costs.on_trade_event(self, payload)

    async def _on_positions(self, payload: dict[str, Any]) -> None:
        await trade_outcome_entry_costs.on_positions(self, payload)

    async def _try_entry_from_view(self, scope: str) -> None:
        await trade_outcome_entry_costs.try_entry_from_view(self, scope)

    async def _expire(self, scope: str) -> None:
        if self._journal is None or scope not in self._pending:
            return
        state = self._pending[scope]; account = str(state.get("account_id") or "")
        timeout_id = "outcome-timeout:" + _digest(scope)
        def reduce(current):
            if current.get("status") != "PARTIAL":
                return current, []
            current["status"] = "INCOMPLETE"; current["remaining_s"] = 0.0
            if isinstance(current.get("legs"), dict):
                current["emitted_legs"] = sorted(current["legs"])
            output_id = "trade-result:" + _digest(scope)
            return current, [(output_id, EVENT_OUT, self._output(current, "INCOMPLETE"))]
        try:
            fresh, final = self._journal.reduce_consumer_event(
                timeout_id, account, "OUTCOME_TIMEOUT", scope, state, CONSUMER,
                scope, state, reduce)
        except Exception as exc:
            self._storage_error = type(exc).__name__
            return
        self._pending.pop(scope, None); self._deadlines.pop(scope, None)
        if fresh:
            self._incomplete += 1
        await self._flush_outbox()

    async def _watchdog(self) -> None:
        try:
            while self._running:
                now = clock.mono()
                for scope, deadline in list(self._deadlines.items()):
                    if now >= deadline:
                        await self._expire(scope)
                await asyncio.sleep(min(WATCHDOG_MAX_SLEEP_S, max(WATCHDOG_MIN_SLEEP_S, self._timeout_s/WATCHDOG_DIVISOR)))
        except asyncio.CancelledError:
            pass

    async def snapshot(self) -> dict[str, Any]:
        now = clock.mono()
        return {"version": ATOM_VERSION, "brokers": dict(self._brokers),
                "processed_event_ids": sorted(self._processed_event_ids),
                "financial_truth": self._truth.export(),
                "counters": {name: getattr(self, "_"+name) for name in COUNTERS},
                "pending": [{**state, "scope": scope,
                             "remaining_s": max(0.0, self._deadlines.get(scope, now)-now)}
                            for scope, state in self._pending.items()]}

    async def restore(self, state: dict[str, Any]) -> None:
        if not isinstance(state, dict):
            raise ValueError("INVALID_TRADE_OUTCOME_STATE")
        self._brokers = {str(key): str(value) for key, value in (state.get("brokers") or {}).items()}
        self._processed_event_ids = {str(item) for item in state.get("processed_event_ids", [])}
        self._truth.load(state.get("financial_truth"))
        counters = state.get("counters")
        if isinstance(counters, dict):
            for name in COUNTERS:
                value = counters.get(name)
                if isinstance(value, int) and value >= 0:
                    setattr(self, "_"+name, value)
        # لقطة أقدم من هذا الإصدار لا تحمل عدّادات: وكلّ معرّف معالَج نتيجةٌ
        # مرّت فعلًا، فهو أرضية صادقة تمنع «بانتظار أوّل نتيجة» فوق ثمانين.
        if not self._outcomes:
            self._outcomes = len(self._processed_event_ids)
        for item in state.get("pending", []):
            if not isinstance(item, dict) or not item.get("scope"):
                continue
            scope = str(item["scope"]); body = dict(item); body.pop("scope", None)
            remaining = max(0.0, float(body.get("remaining_s", self._timeout_s)))
            self._pending[scope] = body; self._deadlines[scope] = clock.mono()+remaining
            if self._journal is not None and not self._storage_error:
                try: self._journal.save_consumer_state(CONSUMER, scope, body, "snapshot-restore")
                except Exception as exc: self._storage_error = type(exc).__name__

    async def health_check(self) -> HealthStatus:
        details = {"outcomes": self._outcomes, "emitted": self._emitted,
                   "complete": self._completed, "pending": len(self._pending),
                   "duplicates": self._duplicates, "dropped_identity": self._dropped_identity,
                   "incomplete": self._incomplete, "capital_scopes": self._truth.accounts,
                   "identity_incomplete": self._identity_incomplete,
                   "entry_added": self._entry_added, "entry_missing": self._entry_missing,
                   "entry_late": self._entry_late,
                   "awaiting_entry": len(self._awaiting_entry),
                   "storage_error": self._storage_error}
        if not self._running:
            return HealthStatus(state=HealthState.UNHEALTHY, message="NOT_STARTED", details=details)
        if self._storage_error:
            return HealthStatus(state=HealthState.UNHEALTHY,
                                message="DURABLE_CONSUMER_UNAVAILABLE", details=details)
        if self._pending or self._incomplete or self._dropped_identity:
            return HealthStatus(state=HealthState.DEGRADED,
                                message="OUTCOME_PARTIAL_OR_INCOMPLETE", details=details)
        if not self._outcomes:
            return HealthStatus(state=HealthState.HEALTHY,
                                message="READY_AWAITING_FIRST_TRADE_OUTCOME | outcomes=0",
                                details=details)
        return HealthStatus(state=HealthState.HEALTHY,
                            # ٢٠٢٦-٠٩-١٦ (فحص شامل ٤٥٠–٥٩٩): `storage_error` و`dropped_identity`
            # في `details` وحدها والنواة تحذفها — فنتيجة صفقةٍ قد لا تُخزَّن
            # أو تُرمى بلا هويّة، والشارة تقول `complete=N` فيُظنّ كل شيء
            # محفوظًا. وهذه أرقام مال المالك لا عدّادات تشغيل.
            # ٢٠٢٦-٠٩-٢٤ — والمراكز التي تنتظر رِجل إغلاقها تُعدّ ظاهرةً: ربحُ
            # أجزائها لم يدخل بعدُ دفترًا، ولا يُقرأ غيابُه صفرًا.
            # ٢٠٢٦-١٠-٠٢: عمولة الدخول تُعدّ ظاهرةً — مضافةٌ أو غائبة أو وصلت بعد النتيجة.
            message="complete=%d · مراكز_مفتوحة=%d · أرجل_متأخّرة=%d · عمولة_دخول: مضافة=%d غائبة=%d بعد_النتيجة=%d%s%s" % (
                self._completed, len(self._open), self._late_legs,
                self._entry_added, self._entry_missing, self._entry_late,
                " ⚠ تخزين=%s" % self._storage_error if self._storage_error else "",
                " بلا هويّة=%d" % self._dropped_identity if self._dropped_identity else ""),
            details=details)
