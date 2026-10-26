from __future__ import annotations

import asyncio
import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

from core.contracts.atom import AtomBase, AtomContext, HealthState, HealthStatus
from storage_policy import enforce_limits, file_lock
# ٢٠٢٦-١٠-٠١ (ختم المالك «Nq») — وحداتٌ شقيقة نُقلت إليها كتلٌ من هذا الملفّ **حرفيًّا**
# لحدّ الأربع مئة سطر فعليّ (م٩/ملف٤)، صفر تغيير سلوك: أسماءُ المراحل وسياستُها (ما يحميه
# السقف وما يُؤجَّل وما يُقصّ أوّلًا) · طبقةُ sqlite (المخطّط والهجرة والإدراج والترحيل
# والاتّصال) · بناءُ الصفّ وما يُنطق عنه. وتُستورد أسماؤها هنا كلُّها كي يبقى سطحُ هذه
# الوحدة كما كان (`_mod.STAGE_TARGET` · `M707._SCHEMA` …)، وأسماءُ الدوالّ المنقولة بقيت
# بوّاباتٍ رفيعة فلم يتغيّر نداءٌ واحد. وما بقي هنا فعمدًا: المعالج والإنفاذ والحلقتان
# و`_STAGES` — تقرؤها حرّاسٌ واختباراتٌ من هذا الملفّ بعينه.
from decision_store_stages import STAGE_APPROVED, STAGE_TARGET, STAGE_DISPATCH
from decision_store_stages import STAGE_ORDER_REQUESTED, STAGE_ORDER_BUILT, STAGE_ORDER_REJECTED
from decision_store_stages import STAGE_DECISION_FINALIZED, STAGE_QUEUED, STAGE_BRIDGE_FAILED
from decision_store_stages import STAGE_ACKNOWLEDGED, STAGE_COMMAND_FAILED
from decision_store_stages import STAGE_FILLED_OPEN, STAGE_FILLED_PARTIAL, STAGE_FILLED_CLOSED
from decision_store_stages import _PROTECTED_STAGES, _PROTECTED_WHERE, _BUFFERED_STAGES, _is_deferrable
from decision_store_stages import _BUFFERED_FLUSH_S, _BUFFER_MAX_ROWS, _BUFFER_HARD_CAP
from decision_store_sqlite import _DB_TIMEOUT_S, _BUSY_TIMEOUT_MS, _LOCK_RETRY, _LOCK_RETRY_SLEEP_S
from decision_store_sqlite import _HANDLER_LOCK_WAIT_S, _LockBusy
from decision_store_sqlite import _SCHEMA, _INDEXES, _MIGRATION_COLUMNS, _COLUMNS, _INSERT_SQL
from decision_store_sqlite import _BACKFILL_BATCH, _BACKFILL_SQL
from decision_store_rows import _FUTURE_STAMP_TOLERANCE_S, _STAMP_LOG_EVERY_S, _FAILURE_LOG_EVERY_S
from decision_store_rows import _to_float, _text, _clock_skew
import decision_store_rows
import decision_store_sqlite
import decision_store_stages

ATOM_VERSION = "4.21.0"

# فحص السقف دوريًّا لا مع كل إدراج. مقيس ٢٠٢٦-٠٩-٠٩ على القاعدة الحيّة
# (٩٥٤ م.ب · ٥٧٢٬٦٦٩ صفًّا): النداء الواحد **١٠–١٢ ms** (اتصال جديد +
# `COUNT(*)` كامل + ثلاث PRAGMA)، ومعدّل الإدراج **٤٫٤ صفّ/ثانية** — أي
# ٤٨ ms من العمل كل ثانية تُدفع في مسار المعالج بلا فائدة: القاعدة تنمو
# ٠٫٢ م.ب في الثلاثين ثانية، فالفحص الدوريّ يكفيها بفارق أمان واسع.
_LIMIT_INTERVAL_S = 30.0
# لكن الدوريّة وحدها تكسر عقدًا: `tests/test_store_extended_contract.py` يطلب
# أن يقصّ سقفُ الصفوف **فورًا**، لا بعد ثلاثين ثانية. فبدل الفحص مع كل إدراج
# (١٠–١٢ ms لكلٍّ) يُقدَّر العدد بلا لمس القاعدة: عدد آخر فحص + ما أُدرج بعده.
# والفحص الفوريّ لا يقع إلّا حين يتجاوز التقدير السقفَ بهامشٍ من ألفه — فعلى
# القاعدة الحيّة (سقف مليون) يعني فحصًا كل ألف إدراج عند بلوغ السقف، وعلى
# سقفٍ صغير (اختبار) يعني فورًا. العقد محفوظ والتوفير محفوظ.
_ROW_SLACK_DIVISOR = 1000
# سقف دفعات الإخراج في النداء الواحد. الإنفاذ يحتجز قفل الإدراج (v4.8.0)،
# فطولُه يصير زمنَ انتظارٍ في معالج الحدث — ومقيس ٢٠٢٦-٠٩-١٠ من عدّاد الناقل
# أنّ ٧٠٧ سجّل **١٬٦٥٠ تجاوزًا وأسوأ مدّة ٢٫١٩ ثانية** مقابل ميزانية ٠٫٠٥.
# دفعتان (١٠٬٠٠٠ صفّ ≈ ١٢٠ ms مقيسة) تكفيان بمعدّل ٤٫٤ صفّ/ثانية وفحصٍ كل
# ثلاثين، والباقي يُكمَل في النداء التالي بلا فقد.
_ENFORCE_MAX_BATCHES = 2

EVENT_APPROVED = "decision.approved.state"
# ٢٠٢٦-١٠-٠٧ (ختم «NQ»): خرج perpetual.target.state من الاشتراك — ناشره (٥٨١) أُرشف؛ ومرحلة TARGET_STATE تبقى مسموحة لصفوفها القديمة.
EVENT_DISPATCH = "decision.dispatch.state"
EVENT_ORDER_REQUESTED = "execution.order.requested"
EVENT_ORDER_BUILT = "execution.order.built"
EVENT_ORDER_REJECTED = "execution.order.rejected"
EVENT_FINAL = "trading.final_decision"
EVENT_BRIDGE_WRITTEN = "platform.brain_signal.written"
EVENT_BRIDGE_FAILED = "platform.brain_signal.write_failed"
EVENT_ACK = "execution.command.ack"
EVENT_COMMAND_FAILED = "execution.command.failed"
EVENT_TRADE = "platform.trade_event"
EVENT_OUT = "storage.decisions_saved"

REASON_NOT_STARTED = "NOT_STARTED"
REASON_STORE_UNAVAILABLE = "STORE_UNAVAILABLE"
REASON_NO_ACTIVITY = "NO_DECISIONS_YET"

_STAGES = (
    (EVENT_APPROVED, STAGE_APPROVED),
    (EVENT_DISPATCH, STAGE_DISPATCH),
    (EVENT_ORDER_REQUESTED, STAGE_ORDER_REQUESTED),
    (EVENT_ORDER_BUILT, STAGE_ORDER_BUILT),
    (EVENT_ORDER_REJECTED, STAGE_ORDER_REJECTED),
    (EVENT_FINAL, STAGE_DECISION_FINALIZED),
    (EVENT_BRIDGE_WRITTEN, STAGE_QUEUED),
    (EVENT_BRIDGE_FAILED, STAGE_BRIDGE_FAILED),
    (EVENT_ACK, STAGE_ACKNOWLEDGED),
    (EVENT_COMMAND_FAILED, STAGE_COMMAND_FAILED),
)

_ALLOWED_STAGES = frozenset(stage for _, stage in _STAGES) | {
    STAGE_FILLED_OPEN, STAGE_FILLED_PARTIAL, STAGE_FILLED_CLOSED,
    STAGE_TARGET,  # بلا حدث منذ ٢٠٢٦-١٠-٠٧؛ يبقى مسموحًا لسياسة الدفعة والسقف على صفوفه القديمة.
}


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
    import sys as _sys
    if str(code_root) not in _sys.path:
        _sys.path.insert(0, str(code_root))
    try:
        from shared.runtime_paths import manifest_config_rebase
        return manifest_config_rebase(raw_cfg, code_root=code_root)
    except Exception:  # noqa: BLE001 — لا يُعطَّل الإقلاع بأزمة مسار
        return raw_cfg


class Atom(AtomBase):
    def __init__(self) -> None:
        self._context: AtomContext | None = None
        self._initialized = False
        self._running = False
        self._db_path = ""
        self._keep_payload = True
        self._max_rows = 0
        self._max_db_bytes = 0
        self._archive_db_path = ""
        self._limit_state: dict[str, Any] = {}
        self._limit_task: asyncio.Task | None = None
        self._inserts_since_limit = 0
        self._conn: sqlite3.Connection | None = None
        self._conn_lock = threading.Lock()  # مؤقّت حتى يُعرف المسار
        self._store_ready = False
        self._last_error = ""
        self.stored_count = 0
        self.duplicate_count = 0
        self.failure_count = 0
        self.future_stamp_count = 0
        self.backfilled_count = 0
        self._backfill_done = False
        self._last_stamp_log_at = 0.0
        self._last_failure_log_at = 0.0
        self._per_stage: dict[str, int] = {}
        # تشريح زمن المعالج بيدي — لأنّ الرقم الخارجيّ وحده يتّهم ولا يشرح.
        self._span: dict[str, list[float]] = {}
        self._buffer: list[tuple[str, dict[str, Any]]] = []
        self._flush_task: asyncio.Task | None = None
        self._urgent_flush: asyncio.Task | None = None
        self.deferred_by_lock = 0
        # كم مرّةً وجد الإنفاذُ القفلَ بيد جارٍ فتخطّى الدورة. نموُّه يعني
        # تنازعًا لا عطلًا — والسقف يُنفَّذ في `_limit_loop` خلال ثلاثين ثانية.
        self.enforce_skipped = 0
        self.buffered_dropped = 0
        # ٢٠٢٦-١٠-٠٥ (ختم المالك «إصلاحها NQ»): صفوفٌ اصطدمت بقفل القاعدة بعد المهلة
        # والإعادة فعادت إلى الطابور بدل أن تُرمى — و`_lock_error` يجعل نصّ القفل عابرًا.
        self.lock_requeued = 0
        self._lock_error = False

    async def initialize(self, context: AtomContext) -> None:
        self._context = context
        cfg = _rebased_config(context.config)
        self._db_path = str(cfg["db_path"])
        # المسار صار معروفًا: يُستبدل القفل المؤقّت بقفل الملفّ.
        self._conn_lock = file_lock(self._db_path)
        self._keep_payload = bool(cfg["keep_full_payload"])
        self._max_rows = int(cfg.get("max_rows", 0))
        self._max_db_bytes = int(cfg.get("max_db_bytes", 0))
        # بأمر المالك ٢٠٢٦-٠٩-١٠: ما يخرجه السقف يُرحَّل ولا يُتلف.
        self._archive_db_path = str(cfg.get("archive_db_path") or "")
        for event, stage in _STAGES:
            context.subscribe(event, self._make_writer(stage))
        context.subscribe(EVENT_TRADE, self._on_trade)
        self._store_ready = self._ensure_store()
        self._initialized = True

    async def start(self) -> None:
        if not self._initialized or self._running or self._context is None:
            return
        self._running = True
        if not self._store_ready:
            self._store_ready = self._ensure_store()
        self._limit_task = asyncio.create_task(self._limit_loop())
        self._flush_task = asyncio.create_task(self._flush_loop())

    async def stop(self) -> None:
        self._running = False
        # `_urgent_flush` معها: مهمّةٌ قد تكون تكتب الآن، فتُنتظَر قبل الغلق.
        for name in ("_limit_task", "_flush_task", "_urgent_flush"):
            task = getattr(self, name)
            setattr(self, name, None)
            if task is not None:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        # ما بقي في الذاكرة يُكتب قبل الإغلاق — التأجيل ليس فقدًا.
        await self._flush_buffer()
        # الإغلاق يُجري نقطة تفتيش ويطوي الـWAL — لا يُترك اتصال معلّقًا.
        with self._conn_lock:
            self._close_connection()

    def _trim_buffer(self) -> None:
        decision_store_stages.trim_buffer(self)

    def _schedule_flush(self) -> None:
        """تعجيلُ كتابة الدفعة — مهمّةٌ واحدة في آنٍ، ولا تُنتظَر في المعالج.

        بلا هذا ينتظر الصفُّ المؤجَّل دورةَ `_flush_loop` كاملة (ثانية). وبحارس
        «واحدة في آنٍ» لا تتكاثر المهامّ تحت الضغط — وهي حالةُ الضغط نفسها.
        """
        task = self._urgent_flush
        if task is not None and not task.done():
            return
        try:
            self._urgent_flush = asyncio.create_task(self._flush_buffer())
        except RuntimeError:
            # لا حلقة تعمل (إغلاقٌ جارٍ): `stop()` يكتب ما بقي على كلّ حال.
            self._urgent_flush = None

    async def _flush_loop(self) -> None:
        try:
            while self._running:
                await asyncio.sleep(_BUFFERED_FLUSH_S)
                await self._flush_buffer()
        except asyncio.CancelledError:
            pass

    async def _flush_buffer(self) -> None:
        """كتابة ما تجمّع دفعةً واحدة — خارج مسار الحدث.

        رحلة `to_thread` واحدة لخمسمئة صفّ بدل خمسمئة رحلة: الجدولة التي كانت
        ثلثَي زمن المعالج تُدفع مرّة لا مرّةً لكلّ صفّ. والكتابة تقع في هذه
        المهمّة الخلفيّة، فلا تُحتسب على ميزانية أيّ معالج.
        """
        if not self._buffer:
            return
        batch, self._buffer = self._buffer, []
        if not self._store_ready:
            self._store_ready = self._ensure_store()
        if not self._store_ready:
            self.failure_count += len(batch)
            self.buffered_dropped += len(batch)
            self._note_failure(batch[0][0], self._last_error or REASON_STORE_UNAVAILABLE)
            return
        started = time.perf_counter()
        try:
            written = await asyncio.to_thread(self._insert_many, [row for _, row in batch])
        except sqlite3.Error as exc:
            if self._requeue_on_lock(exc, batch, front=True):
                return
            self.failure_count += len(batch)
            self.buffered_dropped += len(batch)
            self._last_error = str(exc)
            self._note_failure(batch[0][0], str(exc))
            return
        self._wrote()
        self._span_add("دفعة", time.perf_counter() - started)
        self.stored_count += written
        self.duplicate_count += len(batch) - written
        self._inserts_since_limit += written
        for stage, _row in batch:
            self._per_stage[stage] = self._per_stage.get(stage, 0) + 1
        if self._due_for_row_check():
            self._inserts_since_limit = 0
            await self._enforce_limits()
        if self._context is None:
            return
        for stage, row in batch:
            body: dict[str, Any] = {"stage": stage, "request_id": row["request_id"],
                                    "account_id": row["account_id"], "symbol": row["symbol"]}
            if row["decided_at"] is not None:
                body["timestamp"] = row["decided_at"]
            await self._context.publish(EVENT_OUT, body)

    def _insert_many(self, rows: list[dict[str, Any]]) -> int:
        return decision_store_sqlite.insert_many(self, rows)

    def _requeue_on_lock(self, exc: BaseException, batch: list, *, front: bool) -> bool:
        """قفلٌ بعد المهلة (٢٠ ث) والإعادة: الصفوف تعود إلى الطابور ولا تُرمى.

        ٢٠٢٦-١٠-٠٥ (ختم المالك «إصلاحها NQ»): كان الصفّ يُعدّ إخفاقًا ويضيع، ونصّ
        القفل يبقى في الصحّة حتّى إعادة التحميل وإن عادت الكتابة بعد ثانية. والقفل
        يقع ليلًا مع صيانة ٠٣:٠٠ (مقيس: ٦١٨ و٨١٠ و٧٠٤ معًا في الدقائق نفسها). فالصفّ
        يُكتب في الدفعة التالية، والنصّ يزول بأوّل كتابةٍ تنجح (`_wrote`). والسقف
        الصلب للطابور باقٍ كما هو: يُقصّ الطوفان المعلَن، لا تذكرة تنفيذ.
        """
        if "locked" not in str(exc).lower():
            self._lock_error = False
            return False
        self._lock_error = True
        self._last_error = str(exc)
        self.lock_requeued += len(batch)
        if front:
            self._buffer[:0] = batch
        else:
            self._buffer.extend(batch)
            self._schedule_flush()
        if len(self._buffer) > _BUFFER_HARD_CAP:
            self._trim_buffer()
        return True

    def _wrote(self) -> None:
        """كتابةٌ نجحت: نصّ القفل العابر يزول — وغيرُه من الأعطال يبقى حتّى يُعالَج."""
        if self._lock_error and "locked" in self._last_error.lower():
            self._last_error = ""
        self._lock_error = False

    async def _limit_loop(self) -> None:
        """السقف يُفحص على مهل — لا في مسار الحدث."""
        try:
            while self._running:
                await asyncio.sleep(_LIMIT_INTERVAL_S)
                if not self._backfill_done and self._running:
                    moved = await asyncio.to_thread(self._backfill_once)
                    self.backfilled_count += moved
                    if moved <= 0:
                        self._backfill_done = True
                if not self._running or self._inserts_since_limit <= 0:
                    continue
                self._inserts_since_limit = 0
                await self._enforce_limits()
        except asyncio.CancelledError:
            pass

    def _due_for_row_check(self) -> bool:
        """هل اقترب عدد الصفوف من سقفه؟ — بالتقدير، بلا لمس القاعدة."""
        if self._max_rows <= 0:
            return False
        known = int(self._limit_state.get("rows") or 0)
        slack = max(1, self._max_rows // _ROW_SLACK_DIVISOR)
        return known + self._inserts_since_limit > self._max_rows + slack

    def _backfill_once(self) -> int:
        return decision_store_sqlite.backfill_once(self)

    def _enforce_limits_locked(self) -> dict[str, Any]:
        """الإنفاذ تحت قفل الإدراج نفسه — كاتبٌ واحد من هذه الذرّة في أيّ لحظة.

        القافل كان الذرّة نفسها: `enforce_limits` تفتح اتصالًا ثانيًا وتكتب
        (حذفًا أو ترحيلًا بدفعات) بينما الاتصال المعمَّر يُدرج، فيصطدمان.
        مقيس ٢٠٢٦-٠٩-١٠: أربعة `database is locked` في ثلاث عشرة ساعة، ولا
        تطابق مع نشاط ٧١٤ (آخر نجاح ٠٤:٣٩) ولا ٧١٦ (أمس) — فبقيت هي. الانتظار
        على قفل بايثون أصدق من الاصطدام بقفل sqlite: لا قرار يُفقد.
        """
        # ⚠️ **ثالثُ انتظارٍ في المعالج — والنمط نفسه للمرّة الثالثة.**
        # مقيس ٢٠٢٦-٠٩-٢٣ بعد `4.17.0`: `handler timeout` صار **صفرًا** اليوم
        # (كان ١١٠ لـ٧٠٧ وحدها أمس)، لكنّ **المعالج كلّه أسوأه ٢٦٬٢٥٦٫٥ م.ث**
        # ولا يفسّره أيُّ عدّادٍ عندي: انتظار القفل ١٨٫٥ · قفلٌ مشغول ٩٥٫٧.
        # فبقي مسارٌ لا يُقاس — وهو هذا: `_enforce_limits` يُنتظَر في المعالج
        # (السطر الذي يلي الإدراج) ويأخذ قفل الملفّ **بلا مهلة**، فينتظر جارًا
        # يكنس القاعدة. والعلاج ليس رفع الإنفاذ بل ألّا يُنتظَر:
        #   • القفل حرّ  ⟹ يُنفَّذ فورًا، والعقد الذي يطلب قصًّا فوريًّا محفوظ
        #     (`tests/test_store_extended_contract.py` — وهو يجري بلا منازع).
        #   • القفل مشغول ⟹ يُتخطّى هذه الدورة، و`_limit_loop` يفعلها خلال
        #     ثلاثين ثانية. السقف يتأخّر ولا يسقط، والمعالج لا يُحجب.
        if not self._conn_lock.acquire(timeout=_HANDLER_LOCK_WAIT_S):
            self.enforce_skipped += 1
            return dict(self._limit_state)
        try:
            return enforce_limits(
                self._db_path, "decisions",
                max_rows=self._max_rows, max_db_bytes=self._max_db_bytes,
                protect_where=_PROTECTED_WHERE,
                archive_db_path=self._archive_db_path,
                max_batches=_ENFORCE_MAX_BATCHES)
        finally:
            self._conn_lock.release()

    async def _enforce_limits(self) -> None:
        try:
            self._limit_state = await asyncio.to_thread(self._enforce_limits_locked)
        except (OSError, sqlite3.Error, ValueError) as exc:
            self._last_error = str(exc)
            # قفلٌ هنا عابرٌ كذلك: `_limit_loop` يعيد الإنفاذ خلال ثلاثين ثانية.
            self._lock_error = "locked" in str(exc).lower()
            return
        # تعذُّر الأرشيف يعني أنّ السقف لم يُنفَّذ — يُنطق ولا يُبتلع.
        problem = self._limit_state.get("archive_error")
        if problem:
            self._last_error = "ARCHIVE: %s" % problem
            self._note_failure("LIMIT", self._last_error)
            return
        self._wrote()

    async def shutdown(self) -> None:
        await self.stop()

    def _connection(self) -> sqlite3.Connection:
        return decision_store_sqlite.persistent_connection(self)

    def _close_connection(self) -> None:
        decision_store_sqlite.close_connection(self)

    def _connect(self) -> sqlite3.Connection:
        return decision_store_sqlite.open_connection(self)

    def _ensure_store(self) -> bool:
        # القفل نفسه الذي يحمي الإدراج: البناء والهجرة لا يتزامنان مع كتابة.
        with self._conn_lock:
            return self._ensure_store_locked()

    def _ensure_store_locked(self) -> bool:
        return decision_store_sqlite.ensure_store_locked(self)

    def _insert(self, row: dict[str, Any], queued_at: float | None = None) -> bool:
        return decision_store_sqlite.insert(self, row, queued_at)

    def _make_writer(self, stage: str):
        async def handler(payload: dict[str, Any]) -> None:
            await self._store(stage, payload)
        return handler

    async def _on_trade(self, payload: dict[str, Any]) -> None:
        if not isinstance(payload, dict):
            return
        stage = {"OPENED": STAGE_FILLED_OPEN, "PARTIAL": STAGE_FILLED_PARTIAL,
                 "CLOSED": STAGE_FILLED_CLOSED}.get(str(payload.get("event_type") or "").upper())
        if stage is not None:
            await self._store(stage, payload)

    def _row(self, stage: str, payload: dict[str, Any]) -> dict[str, Any]:
        return decision_store_rows.build_row(self, stage, payload)

    def _note_future_stamp(self, stage: str, decided_at: float, now: float) -> None:
        decision_store_rows.note_future_stamp(self, stage, decided_at, now)

    def _note_failure(self, stage: str, reason: str) -> None:
        decision_store_rows.note_failure(self, stage, reason)

    def _span_add(self, name: str, seconds: float) -> None:
        """عدّاد مقطعٍ من زمن المعالج: عدد · مجموع · أسوأ.

        الناقل يقول «٧٠٧ تجاوز الميزانية ٩٬٦٢٠ مرّة وأسوأ مدّة ٢٢٫٨٧ ثانية»
        ولا يقول **أين** ذهب الزمن، فيُقرأ الرقم اتّهامًا للإدراج وهو مقيس
        بأقلّ من ميلّي ثانية. هذا التشريح يفصل ثلاثة مقاطع لكلّ حدث —
        الإدراج · إنفاذ السقف · النشر — فيصير الاتّهام قابلًا للفحص من
        اللقطة وحدها بلا أداة خارجية. الكلفة `perf_counter` مرّتين لكلّ
        مقطع: أرخص من أن تُقاس، ومقابلها ألّا نخمّن مرّة أخرى.
        """
        slot = self._span.get(name)
        if slot is None:
            self._span[name] = [1.0, seconds, seconds]
            return
        slot[0] += 1.0
        slot[1] += seconds
        if seconds > slot[2]:
            slot[2] = seconds

    def _span_report(self) -> dict[str, str]:
        out: dict[str, str] = {}
        for name, (count, total, worst) in self._span.items():
            if count <= 0:
                continue
            out[name] = "%d× · متوسّط %.3f م.ث · أسوأ %.1f م.ث" % (
                int(count), 1000.0 * total / count, 1000.0 * worst)
        return out

    async def _store(self, stage: str, payload: dict[str, Any]) -> None:
        if not self._running or self._context is None or not isinstance(payload, dict):
            return
        t_enter = time.perf_counter()
        if stage not in _ALLOWED_STAGES:
            self.failure_count += 1; self._last_error = "INVALID_DECISION_STAGE"
            self._note_failure(stage, "INVALID_DECISION_STAGE")
            return
        if not self._store_ready:
            # ⚠️ يعمل **على حلقة الأحداث** لا في خيط، ويأخذ قفل الملفّ. مسارُ
            # تعافٍ نادر، لكنّه كان غير مقيس — فيُقاس كي يُسمَّى إن ظهر في الأسوأ.
            t_ready = time.perf_counter()
            self._store_ready = self._ensure_store()
            self._span_add("بناء المخزن", time.perf_counter() - t_ready)
        if not self._store_ready:
            self.failure_count += 1
            self._note_failure(stage, self._last_error or REASON_STORE_UNAVAILABLE)
            return
        row = self._row(stage, payload)
        if _is_deferrable(stage, row):
            self._buffer.append((stage, row))
            if len(self._buffer) >= _BUFFER_MAX_ROWS:
                # ⚠️ **كان هنا `await self._flush_buffer()` — وهو آخرُ انتظارٍ
                # بقي في المعالج.** أُصلح مسارُ الإدراج الفوريّ ٢٠٢٦-٠٩-١٩ فظهر
                # ما خلفه: مقيس ٢٠٢٦-٠٩-٢٢ من تشريحي الحيّ — انتظارُ القفل نزل
                # إلى **٠٫٠٩٥ م.ث**، لكنّ **الدفعة** وسطُها **٤٬٢٥٠٫٩ م.ث**
                # وأسوأها **١٦٧٬١٢٠٫٩**، فبلغ المعالج **٢٥٬٥٣٤ م.ث**. وليست
                # sqlite: كتابتها ٢٩٫٨ م.ث وسطًا — الباقي انتظارُ قفل الملفّ
                # المشترك بلا مهلة (وهو صوابٌ في الخلفيّة، خطأٌ في المعالج).
                # فتُجدوَل ولا تُنتظَر.
                self._schedule_flush()
                # والذاكرة تبقى محدودة: الجدولة لا تُفرّغ فورًا، فلو تأخّرت
                # الدفعة نما البفر بلا حدّ. يُقصّ **الأقدم** عند السقف الصلب
                # ويُعلَن العدد — فقدٌ مُعلَنٌ خيرٌ من حجبٍ صامت، والمقصوص
                # مراحلُ الطوفان وحدها (`_is_deferrable`) لا تذكرةُ تنفيذ.
                if len(self._buffer) > _BUFFER_HARD_CAP:
                    self._trim_buffer()
            self._span_add("المعالج كلّه", time.perf_counter() - t_enter)
            return
        t_insert = time.perf_counter()
        try:
            inserted = await asyncio.to_thread(self._insert, row, t_insert)
        except _LockBusy:
            # جارٌ يمسك الملفّ الآن. الصفّ يُودَع ويُكتب في الدفعة التالية —
            # تأخيرٌ بجزءٍ من ثانية بدل حجب حلقة الأحداث ثوانيَ. والتذكرة لا
            # تُفقد: `_flush_buffer` تكتبها، و`stop()` يكتب ما بقي قبل الإغلاق.
            self._buffer.append((stage, row))
            self.deferred_by_lock += 1
            self._schedule_flush()
            self._span_add("المعالج كلّه", time.perf_counter() - t_enter)
            return
        except sqlite3.Error as exc:
            if self._requeue_on_lock(exc, [(stage, row)], front=False):
                self._span_add("المعالج كلّه", time.perf_counter() - t_enter)
                return
            self.failure_count += 1
            self._last_error = str(exc)
            self._note_failure(stage, str(exc))
            return
        self._wrote()
        self._span_add("إدراج", time.perf_counter() - t_insert)
        if not inserted:
            self.duplicate_count += 1
            return
        self.stored_count += 1
        self._inserts_since_limit += 1
        self._per_stage[stage] = self._per_stage.get(stage, 0) + 1
        if self._due_for_row_check():
            self._inserts_since_limit = 0
            t_limit = time.perf_counter()
            await self._enforce_limits()
            self._span_add("إنفاذ", time.perf_counter() - t_limit)
        body: dict[str, Any] = {"stage": stage, "request_id": row["request_id"],
                                "account_id": row["account_id"], "symbol": row["symbol"]}
        if row["decided_at"] is not None:
            body["timestamp"] = row["decided_at"]
        t_publish = time.perf_counter()
        await self._context.publish(EVENT_OUT, body)
        now_done = time.perf_counter()
        self._span_add("نشر", now_done - t_publish)
        self._span_add("المعالج كلّه", now_done - t_enter)

    async def snapshot(self) -> dict[str, Any]:
        # التشريح يُنشَر ولا يُستعاد: قياسُ هذا التشغيل لا تاريخُ ما قبله.
        return {"version": ATOM_VERSION, "stored": self.stored_count,
                "failures": self.failure_count, "duplicates": self.duplicate_count,
                "future_stamps": self.future_stamp_count, "per_stage": dict(self._per_stage),
                "buffered": len(self._buffer), "buffered_dropped": self.buffered_dropped,
            # كم مرّةً وجد المعالجُ القفلَ بيد جارٍ فأودع بدل أن ينتظر. صفرٌ =
            # لا تنازع؛ ونموٌّ سريع = جارٌ يمسك الملفّ طويلًا ويستحقّ القياس.
            "deferred_by_lock": self.deferred_by_lock,
            "enforce_skipped": self.enforce_skipped,
            "lock_requeued": self.lock_requeued,
                "تشريح الزمن": self._span_report()}

    async def restore(self, state: dict[str, Any]) -> None:
        if not isinstance(state, dict): raise ValueError("INVALID_DECISION_STORE_STATE")
        self.stored_count=int(state.get("stored") or 0);self.failure_count=int(state.get("failures") or 0)
        self.future_stamp_count=int(state.get("future_stamps") or 0)
        self._per_stage={str(k):int(v) for k,v in (state.get("per_stage") or {}).items()}

    async def health_check(self) -> HealthStatus:
        if not self._running:
            return HealthStatus(state=HealthState.UNHEALTHY, message=REASON_NOT_STARTED)
        details = {"stored": self.stored_count, "per_stage": dict(self._per_stage),
                   "failures": self.failure_count, "duplicates": self.duplicate_count, "store_ready": self._store_ready,
                   "future_stamps": self.future_stamp_count,
                   "buffered": len(self._buffer),
                   "buffered_dropped": self.buffered_dropped,
                   "lock_requeued": self.lock_requeued,
                   "تشريح الزمن": self._span_report(),
                   "last_error": self._last_error, "limits": dict(self._limit_state)}
        if not self._store_ready:
            return HealthStatus(
                state=HealthState.DEGRADED,
                message=self._last_error or REASON_STORE_UNAVAILABLE, details=details)
        if self._last_error:
            return HealthStatus(state=HealthState.DEGRADED, message=self._last_error, details=details)
        if self._limit_state.get("breached"):
            return HealthStatus(state=HealthState.DEGRADED, message="STORAGE_LIMIT_ENFORCED", details=details)
        if self.stored_count == 0:
            return HealthStatus(
                state=HealthState.DEGRADED, message=REASON_NO_ACTIVITY, details=details)
        return HealthStatus(
            state=HealthState.HEALTHY,
            message="stored=%d" % self.stored_count, details=details)
