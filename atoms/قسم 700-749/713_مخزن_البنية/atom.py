from __future__ import annotations

import asyncio
import json
import sqlite3
import threading
from pathlib import Path
from typing import Any

from catchup import decide
from shared.owner_windows import MaintenanceGate
from core.contracts.atom import AtomBase, AtomContext, HealthState, HealthStatus
from storage_policy import enforce_limits, file_lock

ATOM_VERSION = "2.4.0"
MAX_BUFFER_ROWS = 100000

_DB_TIMEOUT_S = 5.0
_BUSY_TIMEOUT_MS = 3000
_SECONDS_PER_DAY = 86400.0

EVENT_IN = "market.structure.updated"
EVENT_DAY = "SYS_DAY"
EVENT_PULSE = "SYS_SECOND"
EVENT_OUT = "storage.structure_saved"

REASON_NOT_STARTED = "NOT_STARTED"
REASON_STORE_UNAVAILABLE = "STORE_UNAVAILABLE"
REASON_NOTHING_STORED = "NOTHING_STORED_YET"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS structure (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol       TEXT,
    occurred_at  REAL,
    payload_json TEXT
)
"""

_INDEXES = (
    "CREATE INDEX IF NOT EXISTS idx_structure_symbol ON structure(symbol, id DESC)",
    "CREATE INDEX IF NOT EXISTS idx_structure_time ON structure(occurred_at)",
)

_INSERT = "INSERT INTO structure (symbol, occurred_at, payload_json) VALUES (?,?,?)"

_PRUNE = "DELETE FROM structure WHERE occurred_at IS NOT NULL AND occurred_at < ?"


def _to_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


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
        self._flush_size = 0
        self._retention_days = 0
        self._flush_interval_s = 30.0
        self._flush_task: asyncio.Task | None = None
        self._max_rows = 0
        self._max_db_bytes = 0
        self._limit_state: dict[str, Any] = {}
        self._last_prune_success: float | None = None
        self._catchup_done = False
        self._catchup_verdict: dict[str, Any] = {}
        # ٢٠٢٦-١٠-٠٩ (ختم المالك «NQ» — الصيانة في استراحة السوق): التشذيب وإنفاذ السقف
        # اليوميّان في نافذة الصيانة وحدها (`shared/owner_windows`) لا على نبض اليوم — 03:00 بتوقيت
        # الجهاز والسوق مفتوح، حيث تجمّدت حلقة المنصّة كلّ ليلة ٠٥–٠٨ تشرين الأوّل.
        self._maintenance = MaintenanceGate()
        self._buffer: list[tuple] = []
        self._store_ready = False
        self._last_error = ""
        self._conn: sqlite3.Connection | None = None
        self._flush_now_task: asyncio.Task | None = None
        self._skipped_while_busy = 0
        self.stored_count = 0
        self.dropped_count = 0

    async def initialize(self, context: AtomContext) -> None:
        self._context = context
        cfg = _rebased_config(context.config)
        self._db_path = str(cfg["db_path"])
        # قفلُ الملفّ لا قفلُ الكائن: ذرّاتٌ أخرى تكتب على القاعدة نفسها
        # في هذه العمليّة (٧١٦ ينظّف · ٧١٤ يؤرشف · الإنفاذ يرحّل). القفل
        # داخل الكائن يُسلسل الذرّة مع نفسها ولا يعبر إلى جارتها — وذاك
        # ما كسر المنصّة ٢٠٢٦-٠٩-١٨ حين خرجت الأعمال الطويلة إلى مهامّ
        # خلفيّة فسقط التسلسل الذي كانت حلقة العامل تفرضه قسرًا.
        self._conn_lock = file_lock(self._db_path)
        self._flush_size = int(cfg["flush_size"])
        self._retention_days = int(cfg["retention_days"])
        self._flush_interval_s = float(cfg.get("flush_interval_s", 30.0))
        self._max_rows = int(cfg.get("max_rows", 0))
        self._max_db_bytes = int(cfg.get("max_db_bytes", 0))
        # ٢٠٢٦-١٠-٠٧ (ختم «NQ»): لا اشتراك في market.structure.updated — ناشره أُرشف مع فكّ الأقسام عن القرار؛ `_on_event` باقٍ لأنّ الاختبارات تستدعيه.
        context.subscribe(EVENT_DAY, self._on_day)
        context.subscribe(EVENT_PULSE, self._on_pulse)
        self._store_ready = self._ensure_store()
        self._initialized = True

    async def start(self) -> None:
        if not self._initialized or self._running or self._context is None:
            return
        self._catchup_done = False
        self._running = True
        self._flush_task = asyncio.create_task(self._flush_loop())

    async def stop(self) -> None:
        self._running = False
        for _name in ("_flush_task", "_flush_now_task"):
            _task = getattr(self, _name)
            setattr(self, _name, None)
            if _task is not None:
                _task.cancel()
                try: await _task
                except asyncio.CancelledError: pass
        if self._buffer:
            await asyncio.to_thread(self._flush)
        # الإغلاق يُجري نقطة تفتيش ويطوي الـWAL — لا يُترك اتصال معلّقًا.
        with self._conn_lock:
            self._close_connection()

    async def _flush_loop(self) -> None:
        try:
            while self._running:
                await asyncio.sleep(self._flush_interval_s)
                if self._running and self._buffer:
                    await self._flush_and_report(None)
        except asyncio.CancelledError:
            pass

    async def shutdown(self) -> None:
        await self.stop()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._db_path, timeout=_DB_TIMEOUT_S,
                                     check_same_thread=False)
        try:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("PRAGMA busy_timeout=%d" % _BUSY_TIMEOUT_MS)
            connection.execute("PRAGMA synchronous=NORMAL")
        except BaseException:
            # أوّل PRAGMA هي التي تقرأ ترويسة الملف: على قاعدة تالفة ترمي
            # بعد إنشاء الاتصال، فيبقى المقبض مفتوحًا والملف ممسوكًا على
            # ويندوز — فيتعذّر إصلاح ما تلف. مقيس ٢٠٢٦-٠٩-٠٩.
            connection.close()
            raise
        return connection

    def _connection(self) -> sqlite3.Connection:
        """الاتصال المعمَّر — يُفتح مرّة ويبقى، تحت قفل.

        كان كلّ دفعةٍ وتشذيبٍ يفتح اتصالًا ويغلقه. والكلفة ليست الاستعلام بل
        **دورة نظام الملفات كاملة**: إنشاء `-wal` و`-shm`، ثمّ نقطة تفتيش
        ومحوهما عند كلّ إغلاق. مقيسة على قاعدة حيّة ٢٠٢٦-٠٩-٠٩ (٧٠٧ v4.4.0):
        **٣٣٫٥٣ م.ث باتّصالٍ جديد مقابل ٤٫٤٩ بمعمَّر** — ×٧٫٥. وقاس قسم
        التغذية النمط نفسه في ٦٠١: **٧٫٥٥ مقابل ٠٫٠٤**.
        """
        if self._conn is None:
            self._conn = self._connect()
        return self._conn

    def _close_connection(self) -> None:
        connection, self._conn = self._conn, None
        if connection is not None:
            try:
                connection.close()
            except sqlite3.Error:
                pass

    def _ensure_store(self) -> bool:
        try:
            Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
            with self._conn_lock:
                connection = self._connection()
                connection.execute(_SCHEMA)
                for statement in _INDEXES:
                    connection.execute(statement)
                connection.commit()
            self._last_error = ""
            return True
        except (sqlite3.Error, OSError) as exc:
            self._last_error = str(exc)
            return False

    def _flush(self) -> int:
        if not self._buffer:
            return 0
        rows, self._buffer = self._buffer, []
        try:
            with self._conn_lock:
                connection = self._connection()
                connection.executemany(_INSERT, rows)
                connection.commit()
            self._last_error = ""
            return len(rows)
        except sqlite3.Error as exc:
            # القاعدة مشكوك فيها: يُطرح الاتصال المعمَّر ويُعاد بناؤه
            # عند المحاولة التالية، بدل بقاء اتصالٍ معطوب إلى الأبد.
            with self._conn_lock:
                self._close_connection()
            self._last_error = str(exc)
            self._buffer = rows + self._buffer
            if len(self._buffer) > MAX_BUFFER_ROWS:
                overflow = len(self._buffer) - MAX_BUFFER_ROWS
                self._buffer = self._buffer[overflow:]
                self.dropped_count += overflow
            return 0

    def _prune(self, now: float) -> int:
        if self._retention_days <= 0:
            return 0
        cutoff = now - self._retention_days * _SECONDS_PER_DAY
        try:
            with self._conn_lock:
                connection = self._connection()
                cursor = connection.execute(_PRUNE, (cutoff,))
                connection.commit()
                return cursor.rowcount or 0
        except sqlite3.Error as exc:
            # القاعدة مشكوك فيها: يُطرح الاتصال المعمَّر ويُعاد بناؤه
            # عند المحاولة التالية، بدل بقاء اتصالٍ معطوب إلى الأبد.
            with self._conn_lock:
                self._close_connection()
            self._last_error = str(exc)
            return 0

    async def _on_event(self, payload: dict[str, Any]) -> None:
        if not self._running or self._context is None:
            return
        if not isinstance(payload, dict):
            return
        symbol = payload.get("symbol")
        if not symbol:
            return
        if not self._store_ready:
            self._store_ready = self._ensure_store()
            if not self._store_ready:
                self.dropped_count += 1
                return
        occurred = _to_float(payload.get("timestamp"))
        self._buffer.append((
            str(symbol), occurred,
            json.dumps(payload, ensure_ascii=False, default=str)))
        if len(self._buffer) >= self._flush_size:
            self._schedule_flush(occurred)

    async def _on_day(self, payload: dict[str, Any]) -> None:
        if not self._running or self._context is None:
            return
        now = _to_float(payload.get("official_time", payload.get("timestamp")))
        self._maintain(now, EVENT_DAY)

    async def _on_pulse(self, payload: dict[str, Any]) -> None:
        if not self._running or not isinstance(payload, dict):
            return
        now = _to_float(payload.get("official_time"))
        if now is None:
            return
        if not self._catchup_done:
            # ٢٠٢٦-١٠-٠٩ (ختم المالك «NQ» — الصيانة في استراحة السوق): حكم اللحاق يُحسب
            # عند الإقلاع ويُعلن، والتشذيب ينتظر نافذة الصيانة.
            self._catchup_done = True
            self._catchup_verdict = decide({"last_success": self._last_prune_success}, now)
        self._maintain(now, "MAINTENANCE_WINDOW")

    def _maintain(self, now: float | None, trigger: str) -> None:
        """٢٠٢٦-١٠-٠٩ (ختم المالك «NQ» — الصيانة في استراحة السوق): التشذيب وإنفاذ السقف
        مرّةً في كلّ نافذة صيانة، وخارجها لا شيء؛ نبضة اليوم (03:00 بتوقيت الجهاز) تُعدّ ولا تُشغّل.
        يُعلَّم المفتاح بعد أن تُجدوَل الدورة فعلًا — فدورةٌ لم تُجدوَل تُسأل في النبضة التالية."""
        key = self._maintenance.due(now, self._last_prune_success, held=trigger == EVENT_DAY)
        if key is not None and self._schedule_flush(now, prune_at=now):
            self._maintenance.mark(key, now)

    def _schedule_flush(self, stamp, prune_at=None) -> bool:
        """الكتابة تخرج من مسار الحدث — رحلةُ خيطٍ لا تُنتظَر في معالج.

        مقيس ٢٠٢٦-٠٩-١٦: تسليم الناقل يمضي بالتتابع على مسار العامل، فما
        يُنتظَر في معالجٍ يحجب كلّ ما خلفه — وميزانية المعالج ٠٫٠٥ ث بينما
        الدفعة رحلةُ خيطٍ كاملة. نفس علاج ٧١٢ v2.8.0 و٧١٨ v2.3.0: مهمّة
        خلفيّة بحارس «واحدة في آنٍ»، والنداء الثاني أثناء كتابةٍ جارية يُعدّ
        ولا يتراكم. والذاكرة ليست في خطر: حدّ البفر محروس، وحلقة `_flush_loop`
        تكتب دوريًّا على كلّ حال — فالجدولة تعجّل الكتابة ولا تكون شرطًا لها.
        """
        if self._flush_now_task is not None and not self._flush_now_task.done():
            self._skipped_while_busy += 1
            return False
        self._flush_now_task = asyncio.create_task(
            self._flush_and_report(stamp, prune_at=prune_at))
        return True

    def _enforce_limits_locked(self) -> dict[str, Any]:
        """الإنفاذ تحت قفل الإدراج — كاتبٌ واحد من هذه الذرّة في أيّ لحظة.

        ‏⛔ وقايةٌ من انحدارٍ سبّبتُه أنا. حين عمَّرتُ الاتّصال (٢٠٢٦-٠٩-١٦)
        بقي `enforce_limits` يفتح **اتّصاله الثاني** ويكتب على القاعدة نفسها،
        **خارج قفل الإدراج** — فصار ممكنًا أن يتداخل مع `_flush`. وقبل
        التعمير كان `_flush` يفتح ويغلق مع كلّ دفعة فلا يلتقيان.

        ⚠️ والآلية مقيسة لا مظنونة (قاعدة ٤١ م.ب بـWAL حقيقيّ): المقبض
        المعمَّر **وحده بريء** — خاملًا أو بعد `commit` ينكمش الملف ٤١ م.ب
        ← ٠٫٣٥. والقاتل **معاملةٌ مفتوحة** لحظة الإنفاذ: معاملة كتابة ⟵
        `database is locked`، ومعاملة قراءة ⟵ لا ينكمش و٦٨٫٨ ثانية صامتة.
        و`sqlite3` يفتح معاملةً ضمنيّة مع كلّ كتابة حتى `commit`.

        وقد قتل هذا المنصّة في ٧١٢ ليلة ٢٠٢٦-٠٩-١٨، وكان أشدّ هناك لأنّها
        وحدها تُنادي بـ`shrink=True`. وهذه لا تُفرغ، فيكفيها **التسلسل**:
        القفل نفسه يمنع التداخل، ولا يُسلَّم الاتّصال فتبقى فائدة التعمير.
        """
        with self._conn_lock:
            return enforce_limits(
                self._db_path, "structure",
                max_rows=self._max_rows, max_db_bytes=self._max_db_bytes)

    async def _flush_and_report(
        self, stamp: float | None, prune_at: float | None = None
    ) -> None:
        if self._context is None:
            return
        written = await asyncio.to_thread(self._flush)
        self.stored_count += written
        pruned = 0
        if prune_at is not None:
            self._last_error = ""
            pruned = await asyncio.to_thread(self._prune, prune_at)
            if not self._last_error:
                self._last_prune_success = prune_at
        try:
            self._limit_state = await asyncio.to_thread(self._enforce_limits_locked)
        except (OSError, sqlite3.Error, ValueError) as exc:
            self._last_error = str(exc)
        if written == 0 and prune_at is None:
            return
        body: dict[str, Any] = {
            "rows": written, "total": self.stored_count, "pruned": pruned}
        if stamp is not None:
            body["timestamp"] = stamp
        await self._context.publish(EVENT_OUT, body)

    async def snapshot(self) -> dict[str, Any]:
        return {"version": ATOM_VERSION, "buffer": list(self._buffer[-MAX_BUFFER_ROWS:]),
                "dropped_count": self.dropped_count, "stored_count": self.stored_count,
                "last_prune_success": self._last_prune_success,
                **self._maintenance.snapshot()}

    async def restore(self, state: dict[str, Any]) -> None:
        rows = state.get("buffer") if isinstance(state, dict) else None
        if not isinstance(rows, list) or not all(isinstance(row, (list, tuple)) for row in rows):
            raise ValueError("INVALID_STORAGE_BUFFER_STATE")
        self._buffer = [tuple(row) for row in rows[-MAX_BUFFER_ROWS:]]
        self.dropped_count = int(state.get("dropped_count") or 0)
        self.stored_count = int(state.get("stored_count") or 0)
        self._last_prune_success = _to_float(state.get("last_prune_success"))
        self._maintenance.restore(state)

    async def health_check(self) -> HealthStatus:
        """٢٠٢٦-١٠-٠٩ (ختم المالك «NQ» — الصيانة في استراحة السوق): الصحّة كما كانت،
        ومعها متى صانت آخر مرّة ومتى القادمة — في الرسالة، فالتفاصيل تُقصّ عند حدود النواة."""
        status = await self._health_core()
        return self._maintenance.announce(status) if self._running else status

    async def _health_core(self) -> HealthStatus:
        if not self._running:
            return HealthStatus(state=HealthState.UNHEALTHY, message=REASON_NOT_STARTED)
        details = {
            "stored": self.stored_count, "dropped": self.dropped_count,
            "buffered": len(self._buffer), "db_path": self._db_path,
            "last_error": self._last_error, "limits": dict(self._limit_state),
            "last_prune_success": self._last_prune_success,
            "catchup": dict(self._catchup_verdict)}
        if not self._store_ready:
            return HealthStatus(
                state=HealthState.DEGRADED,
                message=self._last_error or REASON_STORE_UNAVAILABLE, details=details)
        if self._last_error:
            return HealthStatus(state=HealthState.DEGRADED, message=self._last_error, details=details)
        if self._limit_state.get("breached"):
            return HealthStatus(state=HealthState.DEGRADED, message="STORAGE_LIMIT_ENFORCED", details=details)
        if self.stored_count == 0 and not self._buffer:
            return HealthStatus(
                state=HealthState.DEGRADED, message=REASON_NOTHING_STORED, details=details)
        return HealthStatus(
            state=HealthState.HEALTHY,
            message="stored=%d buffered=%d" % (self.stored_count, len(self._buffer)),
            details=details)
