from __future__ import annotations

import asyncio
import json
import os
import sqlite3
import time
from typing import Any
from core.contracts.atom import AtomBase, AtomContext, HealthState, HealthStatus
from pathlib import Path
# ٢٠٢٦-٠٩-٢٣ (v4.4.2): فُصلت طبقة SQLite (`brain_bridge_db.py`) وقراءات الجسر
# (`brain_bridge_reads.py`) إلى وحدتين شقيقتين، حرفيًّا وبلا تغيير سلوك، لحدّ
# ٤٠٠ سطرٍ فعليّ. وكلّ اسمٍ نُقل يُعاد تصديره هنا باسمه نفسه، فيبقى فضاءُ
# أسماء هذه الوحدة كما كان لكلّ من يقرؤه (اختبارًا أو أداة).
import brain_bridge_db
import brain_bridge_reads
from brain_bridge_db import _CURSOR_SCHEMA, _BUSY_TIMEOUT_MS, _CONNECT_TIMEOUT_S, _WRITE_ATTEMPTS, _WRITE_RETRY_BACKOFF_S  # noqa: F401
from brain_bridge_db import _SCHEMA, _INDEX, _DISPLAY_SCHEMA, _DISPLAY_SEED, _HEARTBEAT_SQL, _INSERT_SQL, _CANCEL_SQL  # noqa: F401
from brain_bridge_db import _resolve_db, _connect, _has_column, _load_durable_cursor, _save_durable_cursor  # noqa: F401
from brain_bridge_reads import _RESULT_BATCH_LIMIT, _TIMEOUT_SETTLE_S, _OPEN_STUCK_AFTER_S, _PENDING_UNKNOWN, _to_number  # noqa: F401

ATOM_VERSION = "4.6.0"
# v4.2.0 (2026-08-25): the result cursor is DURABLE. Measured gap: a cold
# boot baselined the cursor at MAX(done_at,id), so every EA result written
# while python was down (including the EA's own STALE_ON_STARTUP /
# UNKNOWN_AFTER_CRASH verdicts) was swallowed -- 578 never heard its leg
# fail across a restart. The durable cursor resumes exactly where the last
# life stopped; the snapshot cursor is still honored when it is FURTHER
# ahead (prevents the restore-lag double-publish window too).
BARE_CURSOR_DB = "var/store/bridge_cursor_601.db"
_CURSOR_DB = (lambda _p=Path(__file__).resolve(): __import__("shared.runtime_paths", fromlist=["anchored_state_path"]).anchored_state_path(BARE_CURSOR_DB, code_root=_p))()
# `_CURSOR_SCHEMA` ⟵ brain_bridge_db.py (٢٠٢٦-٠٩-٢٣)

# NQ seal, item 22, package T (T1): the decision identity thread crosses the
# bridge INSIDE params_json -- an internal metadata column this writer already
# fills with a variable, optional-key JSON object. The agreed external table
# shape (columns) and every key the EA actually parses are untouched; the EA
# ignores keys it does not look for. Reading params_json back from our own
# rows lets the result events carry the same identity after any reboot.
IDENTITY_FIELDS = ("decision_id", "gate_request_id",
                   "parent_decision_id", "owner_command_id",
                   # ٢٠٢٦-٠٩-٠٦ — ورقة ملكية الصفقة (§٢٢): هوية الفكرة
                   # تعبر الجسر مع هوية القرار، فتصير كل صفقة قابلة
                   # لإعادة البناء من صفّها وحده: من أنشأ الفكرة؟ ولماذا؟
                   # وأين إبطالها؟ وهل بدّله أحد بعد المالك؟
                   "setup_id", "setup_owner", "setup_type",
                   "analysis_invalidation", "analysis_target",
                   "invalidation_source", "invalidation_reason",
                   "target_source", "target_reason",
                   "execution_stop", "execution_stop_reason")

SUBSECOND_CLOCK_REASON = "bridge row write time must be real wall time, not a one-second pulse"
EVENT_FINAL_DECISION = "trading.final_decision"
EVENT_HALT = "emergency.halt"
EVENT_WRITTEN = "platform.brain_signal.written"
EVENT_WRITE_FAILED = "platform.brain_signal.write_failed"
EVENT_HALTED = "platform.brain_signal.halted"
EVENT_TIME = "SYS_SECOND"
EVENT_CMD_ACK = "execution.command.ack"
EVENT_CMD_FAILED = "execution.command.failed"
_RESULT_STATUS_OK = ("DONE",)
_RESULT_STATUS_FAILED = ("FAILED", "CANCELLED", "EXPIRED")
# ٢٠٢٦-٠٩-٢٣: `_RESULT_BATCH_LIMIT` و`_TIMEOUT_SETTLE_S` و`_OPEN_STUCK_AFTER_S`
# و`_PENDING_UNKNOWN` ⟵ brain_bridge_reads.py؛ و`_BUSY_TIMEOUT_MS`
# و`_CONNECT_TIMEOUT_S` و`_WRITE_ATTEMPTS` و`_WRITE_RETRY_BACKOFF_S` ونصوص
# SQL (`_SCHEMA` … `_CANCEL_SQL`) ⟵ brain_bridge_db.py — بقيمها وتعليقاتها.
_BEAT_FAILURES_BEFORE_FAULT = 3
PROJECT_BUILD_ID = "QUANT_NQ_FULL_212"


# `_resolve_db` ⟵ brain_bridge_db.py (٢٠٢٦-٠٩-٢٣)


MAX_SL_FRAC = 0.05

# ٢٠٢٦-١٠-٠٢ (ختم المالك «صلح كامل nq»): فصل التجريبيّ عن الحقيقيّ — يفشل مغلقًا.
# في وضع `CURRENT_ACCOUNT` كان 601 يكتب أمر دخولٍ لأيّ حسابٍ يعلنه الإكسبرت في
# `account_v2`؛ فتركيبُ الإكسبرت على حسابٍ حقيقيّ يبدأ التداول فورًا بعيارات
# الاختبار. الآن لا يُكتب **دخول** (`OPEN` · `PENDING_CREATE`) إلّا لحسابٍ في هذه
# القائمة. القائمة هنا في الكود عمدًا لا في المانيفست: الحساب الحقيقيّ يضيفه
# المالك بيده صراحةً هنا. الحساب المسمّى صراحةً في الإعداد (`account_id` غير
# `CURRENT_ACCOUNT`، أو `NQ_ACCOUNT_ID`) تسميةٌ صريحة من المالك فيُقبل كذلك.
# أوامر الخروج والحماية (`MODIFY_SL` · `CLOSE` · `CLOSE_PARTIAL` · …) تمرّ لأيّ
# حساب: منعُها يترك مركزًا مفتوحًا بلا حماية.
ALLOWED_OPEN_ACCOUNT_IDS = frozenset({"52992818"})  # IC Markets تجريبيّ (ICMarketsSC-Demo)
_ENTRY_ACTIONS = ("OPEN", "PENDING_CREATE")


# ٢٠٢٦-٠٩-٢٣: `_to_number` ⟵ brain_bridge_reads.py؛ و`_connect` و`_has_column`
# و`_load_durable_cursor` و`_save_durable_cursor` ⟵ brain_bridge_db.py.


class Atom(AtomBase):
    def __init__(self) -> None:
        self._context = None
        self._account_id = ""
        self._configured_account_id = ""
        self._running = False
        self._current_account_mode = False
        self._blocked_account_ids: set[str] = set()
        self._db_path = "nq_brain.db"
        self._beat_interval_s = 0.0
        self._beat_task = None
        self.heartbeat_written = 0
        self.heartbeat_failed = 0
        self._beats_failing = 0
        self.written_count = 0
        self.halted_count = 0
        self.last_write_success = None
        self.last_write_at = None
        self.last_write_error = None
        self._detected_account_id = ""
        self._detected_account_ids: set[str] = set()
        self._account_mismatch = False
        self._result_cursor: tuple[float, int] | None = None
        self._cursor_reconciled = False
        self._results_busy = False
        #: مهامّ أطلقتها النبضة ولم تنتظرها — مملوكة كي لا تُجمَع ولا تُبتلع.
        self._pulse_tasks: set = set()
        self._magic = 0
        self.results_acked = 0
        self.results_failed = 0
        self.identity_incomplete = 0
        self.write_retries = 0
        self.write_lost_to_lock = 0
        # كم مرّةً عجز الحارس عن المعرفة فأُغلق الباب على المجهول.
        self.pending_unknown = 0
        # م-34: مسار مؤشر قابل للضبط — الافتراضي كما كان، والاختبارات وقواعد
        # أخرى تعزله لكل قاعدة فلا يبتلع مؤشرُ قاعدةٍ نتائجَ أخرى.
        self._cursor_db = _CURSOR_DB
        # ٢٠٢٦-١٠-٠٢ (ختم المالك «صلح كامل nq»): عدُّ «فتحٌ معلّق» ثمّ الإدراج كانا خطوتين بينهما
        # `await`، والمحرّك يحجز **النطاق** (حساب×رمز) لا المعالج — فقراران متزامنان على رمزين
        # يدخلان هنا معًا، ويرى كلاهما صفرًا، ويُكتب الاثنان (2026-09-10: فتح USTEC 20:04:21.503
        # لم يُحسم وفتح BTCUSD للحساب نفسه 21.626). القفل يجعل العدّ والإدراج لأوامر الفتح خطوةً
        # واحدة داخل الذرّة. ويُنشأ من جديد في `start()` على حلقة التشغيل نفسها.
        self._open_lock = asyncio.Lock()

    async def initialize(self, context: AtomContext) -> None:
        self._context = context
        configured = str(context.config["account_id"]).strip()
        self._cursor_db = str(context.config.get("cursor_db") or _CURSOR_DB).strip() or _CURSOR_DB
        env_account = os.environ.get("NQ_ACCOUNT_ID", "").strip()
        self._configured_account_id = configured
        self._current_account_mode = not env_account and configured.upper() in {"CURRENT", "CURRENT_ACCOUNT", "AUTO_CURRENT"}
        self._require_symbol_resolution = bool(context.config.get("require_symbol_resolution", False))
        self._account_id = env_account or ("" if self._current_account_mode else configured)
        self._blocked_account_ids = {str(x).strip() for x in context.config.get("blocked_account_ids", []) if str(x).strip()}
        self._db_path = _resolve_db(str(context.config["db_path"]))
        self._beat_interval_s = float(context.config["heartbeat_interval_s"])
        self._magic = int(context.config.get("magic", 20260801))
        context.subscribe(EVENT_FINAL_DECISION, self._on_final_decision)
        context.subscribe(EVENT_HALT, self._on_emergency_halt)
        context.subscribe(EVENT_TIME, self._on_pulse)
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        # ⟵ brain_bridge_db.ensure_schema (منقولٌ حرفيًّا ٢٠٢٦-٠٩-٢٣)
        brain_bridge_db.ensure_schema(self)

    def _count_unsettled_opens(self, account_id: str | None = None, symbol: str | None = None) -> int:
        # أوامر فتحٍ مصيرها مجهول (حارس الفتح المزدوج) — المنطق وتاريخه كاملًا
        # ⟵ brain_bridge_reads.count_unsettled_opens (منقولٌ حرفيًّا ٢٠٢٦-٠٩-٢٣).
        # ٢٠٢٦-١٠-٠٢ (ختم المالك «صلح كامل nq»): ومعه حساب الأمر ورمزه — نطاقُ التجميد هناك.
        return brain_bridge_reads.count_unsettled_opens(self, account_id, symbol)

    def _read_bridge_accounts(self) -> set[str] | None:
        try:
            conn = sqlite3.connect(f"file:{self._db_path}?mode=ro", uri=True, timeout=_CONNECT_TIMEOUT_S)
            try:
                if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='account_v2'").fetchone() is None:
                    return None
                return {str(row[0]) for row in conn.execute(
                    "SELECT account_id FROM account_v2 WHERE account_id IS NOT NULL AND account_id<>''").fetchall()
                    if str(row[0]) not in self._blocked_account_ids}
            finally: conn.close()
        except sqlite3.Error: return None

    def _sync_identity(self, detected: set[str] | None) -> bool:
        if detected is None:
            self._account_mismatch = True
            self.last_write_error = "BRIDGE_ACCOUNTS_UNAVAILABLE"
            return False
        self._detected_account_ids = set(detected)
        self._detected_account_id = next(iter(detected)) if len(detected) == 1 else ""
        if self._current_account_mode:
            self._account_mismatch = not bool(detected)
            if self._account_mismatch: self.last_write_error = "CURRENT_ACCOUNTS_UNAVAILABLE_OR_BLOCKED"
            return not self._account_mismatch
        self._account_mismatch = self._account_id not in detected or self._account_id in self._blocked_account_ids
        if self._account_mismatch: self.last_write_error = "BRIDGE_ACCOUNT_ID_MISMATCH_OR_BLOCKED"
        return not self._account_mismatch

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._open_lock = asyncio.Lock()
        self._sync_identity(await asyncio.to_thread(self._read_bridge_accounts))
        self._beat_task = asyncio.create_task(self._beat_loop())

    async def stop(self) -> None:
        self._running = False
        for _task in list(self._pulse_tasks):
            _task.cancel()
        self._pulse_tasks.clear()
        self._results_busy = False
        if self._beat_task is not None:
            self._beat_task.cancel()
            try: await self._beat_task
            except asyncio.CancelledError: pass
            self._beat_task = None

    def _entry_price(self, ticket):
        # سعر دخول المركز — مرساة فحص مسافة الوقف
        # ⟵ brain_bridge_reads.entry_price (منقولٌ حرفيًّا ٢٠٢٦-٠٩-٢٣).
        return brain_bridge_reads.entry_price(self, ticket)

    async def shutdown(self) -> None:
        await self.stop()

    def _is_mine(self, account_id: Any) -> bool:
        account = str(account_id or "")
        if not account or account in self._blocked_account_ids: return False
        return account in self._detected_account_ids if self._current_account_mode else account == self._account_id

    def _entry_allowed(self, account: str) -> bool:
        # القائمة في الكود، أو حسابٌ سمّاه الإعداد صراحةً (لا وضع الحساب الحاليّ).
        return account in ALLOWED_OPEN_ACCOUNT_IDS or (
            not self._current_account_mode and bool(account) and account == self._account_id)

    def _metadata_json(self, payload: dict[str, Any]) -> str:
        fields = ("cycle_id", "origin", "pair_id", "leg_role", "attempt", "pair_required",
                  "protection_mode", "pair_volume", "purpose", "target_net", "current_net",
                  "delta_net", "risk_budget", "ticket", "logical_symbol", "broker_symbol",
                  "asset_canonical", "symbol_resolution_status", "snapshot_id") + IDENTITY_FIELDS
        data = {field: payload.get(field) for field in fields if payload.get(field) is not None}
        return json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))

    @staticmethod
    def _identity_from_metadata(params_json: Any) -> dict[str, Any]:
        """Recover the identity the command row itself carries (durable across
        any reboot). Absent values pass as None -- never invented."""
        try:
            metadata = json.loads(params_json) if params_json else {}
        except (TypeError, ValueError):
            metadata = {}
        if not isinstance(metadata, dict):
            metadata = {}
        return {field: metadata.get(field) for field in IDENTITY_FIELDS}

    async def _on_final_decision(self, payload: dict) -> None:
        if not self._running or self._context is None or not isinstance(payload, dict): return
        if not self._sync_identity(await asyncio.to_thread(self._read_bridge_accounts)):
            await self._record_failure(self.last_write_error or "ACCOUNT_ID_UNAVAILABLE", payload)
            return
        account_id = payload.get("account_id")
        if not self._is_mine(account_id):
            await self._record_failure("ACCOUNT_ID_MISMATCH" if account_id else "MISSING_ACCOUNT_ID", payload)
            return
        if self._require_symbol_resolution and payload.get("symbol_resolution_status") != "RESOLVED":
            await self._record_failure("SYMBOL_UNRESOLVED", payload)
            return
        request_id = str(payload.get("request_id") or "").strip()
        action = str(payload.get("action") or "OPEN").upper()
        if not request_id or action not in ("OPEN","CLOSE","CLOSE_PARTIAL","MODIFY_SL","MODIFY_TP","PENDING_CREATE","PENDING_DELETE"):
            await self._record_failure("MISSING_REQUEST_ID_OR_BAD_ACTION", payload)
            return
        if action in _ENTRY_ACTIONS and not self._entry_allowed(str(account_id)):
            # ٢٠٢٦-١٠-٠٢ (ختم المالك «صلح كامل nq»): حسابٌ خارج القائمة — لا دخول.
            await self._record_failure("ACCOUNT_NOT_ALLOWED_FOR_ENTRY account=%s" % account_id, payload)
            return
        try: command_magic=int(payload.get("magic"))
        except (TypeError,ValueError): command_magic=0
        if command_magic != self._magic:
            await self._record_failure("MISSING_OR_FOREIGN_MAGIC",payload)
            return
        symbol = payload.get("symbol")
        side = str(payload.get("side") or payload.get("bias") or "").upper()
        if not symbol or side not in ("BUY", "SELL"):
            await self._record_failure(f"bad symbol/side: symbol={symbol!r} side={side!r}", payload)
            return
        # ٢٠٢٦-٠٩-٠٦ (مقيس على لقطة المالك): أمرا سوق عالقان عند الوسيط
        # بحالة `started` والحجم 0.78/0 — أُرسلا 02:37:01 و02:37:05، أي
        # بفارق **أربع ثوانٍ** رغم كبح الخمس والأربعين ثانية. الكبح لا
        # يرى الأوامر العالقة: لا مركز يظهر، فيحسب أن شيئًا لم يحدث
        # ويرسل غيره. وكلٌّ منها يحجز هامشًا (قِيس 248.93$ محجوزًا).
        # لا يُفتح أمرٌ جديد ما دام أمرُ فتحٍ سابق لم يُحسم — لا DONE ولا
        # FAILED — فتُمنع سلسلة الأوامر المتراكمة على وسيط بطيء.
        # ٢٠٢٦-١٠-٠٢ (ختم المالك «صلح كامل nq»): من العدّ إلى الإدراج تحت `_open_lock` لأوامر
        # الفتح — الفحوص بترتيبها كما كانت، لكنّ السبب يُحفظ في `failure` ولا يُنشر إلّا بعد فكّ
        # القفل: نشرٌ داخل القفل قد يعود إلى هذا المعالج في المهمّة نفسها فيقفل نفسه.
        failure = None
        written = False
        lock = self._open_lock if action == "OPEN" else None
        if lock is not None:
            await lock.acquire()
        try:
            if action == "OPEN":
                pending = await asyncio.to_thread(self._count_unsettled_opens, str(account_id), str(symbol))
                if pending == _PENDING_UNKNOWN:
                    # لا يُفتح على مجهول. البابُ يُغلق ويُسمّى سببُه بغير
                    # اسم العالق، فلا يُخلط «عندنا أمرٌ قائم» بـ«لم نستطع
                    # أن نعرف» — وهما حالتان تُعالَجان بطريقين مختلفين.
                    failure = "OPEN_PENDING_UNKNOWN: bridge read failed"
                elif pending:
                    failure = "OPEN_PENDING_AT_BROKER count=%d" % pending
            if failure is None:
                try: valid_volume = float(payload.get("volume")) > 0
                except (TypeError, ValueError): valid_volume = False
                if action not in ("CLOSE", "MODIFY_SL", "MODIFY_TP", "PENDING_DELETE") and not valid_volume:
                    failure = f"missing volume request_id={payload.get('request_id')!r}"
            # ٢٠٢٦-٠٩-٠٥ (مقيس): أمر إدارة وضع وقفًا عند 39,677 على مركز دخوله
            # 79,677 — مسافة 40,000 (نصف السعر) أي مركز بلا حماية. الحارس هنا
            # آخر بوابة قبل الجسر: أي وقف يبعد أكثر من MAX_SL_FRAC عن السعر
            # المرجعي أو سعر الدخول يُرفض بدل أن يُكتب.
            sl_value = _to_number(payload.get("stop_loss"))
            if failure is None and sl_value is not None and sl_value > 0:
                anchor = _to_number(payload.get("reference_price")) or self._entry_price(
                    payload.get("ticket"))
                if anchor is None:
                    # ٢٠٢٦-٠٩-٢٣: كان هذا الحجب على `MODIFY_SL`/`MODIFY_TP`
                    # وحدهما، فكان **أمرُ فتحٍ بوقفٍ بلا مرساة يمرّ بلا فحص**
                    # (الشرط `if anchor and …` يسقط صامتًا عند `None`). وهو
                    # النمط نفسه: غيابُ المرجع يصير «لا مخالفة».
                    # لا مرساة = لا فحص ممكن، فيُرفض للجميع.
                    failure = "STOP_LOSS_NO_ANCHOR"
                elif anchor and abs(anchor - sl_value) / anchor > MAX_SL_FRAC:
                    failure = ("STOP_LOSS_TOO_FAR: sl=%s anchor=%s dist=%.1f%%"
                               % (sl_value, anchor, abs(anchor - sl_value) / anchor * 100.0))
            if failure is None:
                if not any(payload.get(field) for field in IDENTITY_FIELDS):
                    # T1 alert, tonight's style: the command still goes out (nothing is
                    # blocked here -- 552 owns that verdict), but the gap is counted.
                    self.identity_incomplete += 1
                # زمنُ الصفّ يُؤخذ هنا، بعد انتظار القفل — الإكسبرت يقيس عمر الأمر منه.
                row = (request_id, action,
                       str(symbol), side, payload.get("volume"), payload.get("reference_price"),
                       payload.get("stop_loss"), payload.get("take_profit"), payload.get("ticket"),
                       self._metadata_json(payload), command_magic, str(account_id),
                       str(payload.get("project_build_id") or PROJECT_BUILD_ID), time.time())
                try:
                    await asyncio.to_thread(self._insert_command, row)
                    written = True
                except sqlite3.Error as exc:
                    failure = str(exc)
        finally:
            if lock is not None:
                lock.release()
        if not written:
            await self._record_failure(failure or "NOT_WRITTEN", payload)
            return
        self.written_count += 1
        self.last_write_success = True
        self.last_write_at = time.time()
        self.last_write_error = None
        await self._context.publish(EVENT_WRITTEN, {**payload, "side": side, "account_id": str(account_id),
                                                    "detected_account_id": str(account_id)})

    # ── مسار الكتابة ⟵ brain_bridge_db (منقولٌ حرفيًّا ٢٠٢٦-٠٩-٢٣) ──
    # الأسماء الثلاثة باقية على الذرّة، و`insert_command` هناك ينادي
    # `atom._insert_once`/`atom._is_locked` كما كان `self.…` تمامًا.

    @staticmethod
    def _is_locked(exc: Exception) -> bool:
        # قفلٌ عابر يُعاد، و`DUPLICATE_REQUEST_ID` لا يُعاد أبدًا.
        return brain_bridge_db.is_locked(exc)

    def _insert_once(self, row: tuple) -> None:
        brain_bridge_db.insert_once(self, row)

    def _insert_command(self, row: tuple) -> None:
        # يكتب الأمر ويعيد المحاولة على القفل العابر وحده (داخل خيط).
        brain_bridge_db.insert_command(self, row)

    async def _on_emergency_halt(self, payload: dict) -> None:
        if not self._running or self._context is None or not isinstance(payload, dict): return
        target = str(payload.get("account_id") or "")
        # ٢٠٢٦-١٠-٠٢ (ختم المالك «صلح كامل nq»): العقد المشترك — نطاق SYSTEM
        # إيقافٌ لكلّ الحسابات ولو حمل الحدث حسابًا؛ وبلا حساب كان كذلك أصلًا.
        if str(payload.get("scope") or "").upper() == "SYSTEM":
            target = ""
        accounts = ([target] if target and self._is_mine(target)
                    else sorted(self._detected_account_ids) if self._current_account_mode and not target
                    else [self._account_id] if not target and self._account_id else [])
        if not accounts: return
        self.halted_count += 1
        cancelled = 0
        try:
            for account in accounts: cancelled += await asyncio.to_thread(self._cancel_pending, account)
            self.last_write_at = time.time()
        except sqlite3.Error as exc: await self._record_failure(str(exc)); return
        await self._context.publish(EVENT_HALTED, {"account_ids": accounts,
            "account_id": target or None, "reason": payload.get("reason"), "cancelled_commands": cancelled})

    def _cancel_pending(self, account_id: str) -> int:
        # ⟵ brain_bridge_db.cancel_pending (منقولٌ حرفيًّا ٢٠٢٦-٠٩-٢٣)
        return brain_bridge_db.cancel_pending(self, account_id)

    def _read_results(self) -> list[tuple]:
        # دفعة النتائج مع المؤشّر الدائم (v4.2.0)
        # ⟵ brain_bridge_reads.read_results (منقولٌ حرفيًّا ٢٠٢٦-٠٩-٢٣).
        return brain_bridge_reads.read_results(self)

    async def _on_pulse(self, payload: dict) -> None:
        # ٢٠٢٦-٠٩-١٧ — المقيس: سحبُ النتائج داخل النبضة كلّف **20.38 مِلّي
        # ثانية لكلّ نبضة** (2.34 ث في 115). والنبضة مشتركة، فحجزها يؤخّر
        # التغذية والتنفيذ معًا. تُطلَق الآن ولا تُنتظَر، و`_results_busy`
        # يبقى حارس التداخل كما كان.
        if not self._running or self._context is None or self._results_busy:
            return
        self._results_busy = True
        self._spawn_watched(self._drain_results(), "601-results-drain")

    async def _drain_results(self) -> None:
        try:
            rows = await asyncio.to_thread(self._read_results)
        except sqlite3.Error:
            self._results_busy = False
            return
        try:
            for (row_id, request_id, action, symbol, side, volume, ticket,
                 status, result, account_id, done_at, params_json) in rows:
                self._result_cursor = (float(done_at or 0.0), int(row_id))
                body = {"request_id": str(request_id or ""), "action": action,
                        "symbol": symbol, "side": side, "volume": volume,
                        "ticket": ticket, "status": status, "result": result,
                        "account_id": account_id or self._account_id,
                        **self._identity_from_metadata(params_json)}
                if status in _RESULT_STATUS_OK:
                    self.results_acked += 1
                    await self._context.publish(EVENT_CMD_ACK, {
                        **body, "command_id": str(request_id or "")})
                elif status in _RESULT_STATUS_FAILED:
                    self.results_failed += 1
                    await self._context.publish(EVENT_CMD_FAILED, {
                        **body, "reason": str(result or status)})
                else:
                    self.results_failed += 1
                    await self._context.publish(EVENT_CMD_FAILED, {
                        **body, "reason": "UNKNOWN_RESULT_STATUS_%s" % str(status or "")})
            # v4.2.0: المؤشر يثبت دائمًا بعد كل دفعة منشورة.
            if rows and self._result_cursor is not None:
                _save_durable_cursor(self._cursor_db, self._result_cursor)
        finally:
            self._results_busy = False


    def _spawn_watched(self, coro, label: str) -> None:
        """يُطلق عملًا لا تنتظره النبضة — مملوكًا ومراقَبًا لا منفلتًا.

        النبضة نبضةُ الجميع: انتظارُ قراءةِ قاعدةٍ فيها يحجز الحلقة التي تحمل
        التغذية والتنفيذ. فالعمل يُطلق هنا، ومرجعه يُحفظ كي لا يُجمَع، وخطؤه
        يُرفَع في `_last_error` بدل أن يُبتلع.
        """
        import asyncio as _asyncio
        task = _asyncio.get_running_loop().create_task(coro, name=label)
        self._pulse_tasks.add(task)

        def _done(finished: "_asyncio.Task") -> None:
            self._pulse_tasks.discard(finished)
            if finished.cancelled():
                return
            error = finished.exception()
            if error is not None:
                self._last_error = "%s: %s" % (label, error)

        task.add_done_callback(_done)

    def _write_heartbeat(self, stamp: float) -> None:
        # ⟵ brain_bridge_db.write_heartbeat (منقولٌ حرفيًّا ٢٠٢٦-٠٩-٢٣)
        brain_bridge_db.write_heartbeat(self, stamp)

    async def _beat_loop(self) -> None:
        loop = asyncio.get_running_loop()
        deadline = loop.time()
        try:
            while self._running:
                deadline += self._beat_interval_s
                if deadline <= loop.time(): deadline = loop.time() + self._beat_interval_s
                await asyncio.sleep(max(deadline - loop.time(), 0.0))
                self._sync_identity(await asyncio.to_thread(self._read_bridge_accounts))
                await asyncio.to_thread(self._write_heartbeat, time.time())
        except asyncio.CancelledError: pass

    async def _record_failure(self, reason: str, order: dict | None = None) -> None:
        self.last_write_success = False
        self.last_write_error = reason
        if self._context is None: return
        body: dict[str, Any] = {"account_id": (order or {}).get("account_id") or self._account_id or None, "reason": reason}
        if order:
            for field in ("request_id", "symbol", "side", "action", "volume", "pair_id",
                          "leg_role", "attempt") + IDENTITY_FIELDS:
                if order.get(field) is not None: body[field] = order[field]
        await self._context.publish(EVENT_WRITE_FAILED, body)
        self._context.logger.error("601 failed to write %s on %s: %s", body.get("request_id"), body.get("symbol"), reason)

    async def snapshot(self) -> dict[str, Any]:
        return {"version": ATOM_VERSION, "result_cursor": list(self._result_cursor) if self._result_cursor else None}
    async def restore(self, state: dict[str, Any]) -> None:
        cursor = state.get("result_cursor") if isinstance(state, dict) else None
        if cursor is not None and (not isinstance(cursor, list) or len(cursor) != 2):
            raise ValueError("INVALID_RESULT_CURSOR")
        self._result_cursor = (float(cursor[0]), int(cursor[1])) if cursor else None
    async def health_check(self) -> HealthStatus:
        if not self._running: return HealthStatus(state=HealthState.UNHEALTHY, message="NOT_STARTED")
        details = {"account_id": self._account_id, "configured_account_id": self._configured_account_id,
                   "current_account_mode": self._current_account_mode, "detected_account_id": self._detected_account_id,
                   "detected_account_ids": sorted(self._detected_account_ids),
                   "account_mismatch": self._account_mismatch, "written": self.written_count,
                   "heartbeats": self.heartbeat_written, "heartbeat_failures": self.heartbeat_failed,
                   "beats_failing_in_a_row": self._beats_failing,
                   "results_acked": self.results_acked, "results_failed": self.results_failed,
                   "identity_incomplete": self.identity_incomplete,
                   "write_retries": self.write_retries,
                   "write_lost_to_lock": self.write_lost_to_lock,
                   "pending_unknown": self.pending_unknown}
        if self._account_mismatch: return HealthStatus(state=HealthState.UNHEALTHY, message=self.last_write_error or "ACCOUNT_ID_MISMATCH", details=details)
        if self._beats_failing >= _BEAT_FAILURES_BEFORE_FAULT: return HealthStatus(state=HealthState.UNHEALTHY, message=f"heartbeat not reaching bridge for {self._beats_failing} tries", details=details)
        if self.last_write_success is False and not self.heartbeat_written: return HealthStatus(state=HealthState.UNHEALTHY, message=f"last write failed: {self.last_write_error}", details=details)
        if self.last_write_success is False: return HealthStatus(state=HealthState.DEGRADED, message=f"command not written: {self.last_write_error}", details=details)
        # الإعادة والضياع في **الرسالة**: `details` تُقصّ عند حدود النواة،
        # وضياعُ أمرٍ على قفلٍ لا يجوز أن يُعرف من `details` وحدها.
        tail = ""
        if self.write_retries or self.write_lost_to_lock:
            tail = " · قفل: أُعيدت %d · ضاعت %d" % (self.write_retries, self.write_lost_to_lock)
        if self.pending_unknown:
            tail += " · ⛔ حجبٌ على مجهول: %d" % self.pending_unknown
        if self.heartbeat_written or self.last_write_success: return HealthStatus(state=HealthState.HEALTHY, message=f"bridge writable, written={self.written_count}{tail}", details=details)
        return HealthStatus(state=HealthState.DEGRADED, message="no heartbeat yet", details=details)
