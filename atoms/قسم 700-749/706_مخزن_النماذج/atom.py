from __future__ import annotations

import asyncio
import json
import sqlite3
import threading
from pathlib import Path
from typing import Any

from core.contracts.atom import AtomBase, AtomContext, HealthState, HealthStatus
from storage_policy import enforce_limits, file_lock

ATOM_VERSION = "2.3.0"

_DB_TIMEOUT_S = 5.0
_BUSY_TIMEOUT_MS = 3000

EVENT_PERSIST_REQUESTED = "model.persist_requested"
EVENT_LOAD_REQUESTED = "storage.persistence.load_requested"
EVENT_LOAD_RESPONSE = "storage.persistence.load_response"
EVENT_PERSISTED = "storage.model_saved_confirmed"
EVENT_MODEL_PERSISTED = "model.persisted"
EVENT_PERSIST_FAILED = "storage.persistence.save_failed"

REASON_NOT_STARTED = "NOT_STARTED"
REASON_STORE_UNAVAILABLE = "STORE_UNAVAILABLE"
REASON_NO_ACTIVITY = "NO_ACTIVITY_YET"
REASON_NOT_SERIALISABLE = "NOT_SERIALISABLE"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS model_versions (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    model_name   TEXT NOT NULL,
    version      TEXT NOT NULL,
    data_json    TEXT NOT NULL,
    saved_at     REAL NOT NULL,
    UNIQUE (model_name, version)
)
"""

_INDEX = (
    "CREATE INDEX IF NOT EXISTS idx_model_versions_name"
    " ON model_versions(model_name, id DESC)"
)

_UPSERT = (
    "INSERT INTO model_versions (model_name, version, data_json, saved_at)"
    " VALUES (?, ?, ?, ?)"
    " ON CONFLICT(model_name, version) DO UPDATE SET"
    " data_json=excluded.data_json, saved_at=excluded.saved_at"
)

_PRUNE = (
    "DELETE FROM model_versions WHERE model_name = ? AND id NOT IN ("
    " SELECT id FROM model_versions WHERE model_name = ? ORDER BY id DESC LIMIT ?)"
)


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
        self._keep_versions = 0
        self._max_db_bytes = 0
        self._limit_state: dict[str, Any] = {}
        self._store_ready = False
        self._last_error = ""
        self._conn: sqlite3.Connection | None = None
        self.saved_count = 0
        self.loaded_count = 0
        self.missing_count = 0
        self.failure_count = 0
        self.pruned_count = 0

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
        self._keep_versions = int(cfg["keep_versions_per_model"])
        self._max_db_bytes = int(cfg.get("max_db_bytes", 0))
        context.subscribe(EVENT_PERSIST_REQUESTED, self._on_persist_requested)
        context.subscribe(EVENT_LOAD_REQUESTED, self._on_load_requested)
        self._store_ready = self._ensure_store()
        self._initialized = True

    async def start(self) -> None:
        if not self._initialized or self._running or self._context is None:
            return
        self._running = True
        if not self._store_ready:
            self._store_ready = self._ensure_store()

    async def stop(self) -> None:
        self._running = False
        # الإغلاق يُجري نقطة تفتيش ويطوي الـWAL — لا يُترك اتصال معلّقًا.
        with self._conn_lock:
            self._close_connection()

    async def shutdown(self) -> None:
        await self.stop()

    def _connect(self) -> sqlite3.Connection:
        # `check_same_thread=False`: الكتابة تجري في `asyncio.to_thread` وخيطها
        # ليس ثابتًا. الحماية بالقفل `_conn_lock` لا بانتماء الخيط.
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

    def _ensure_store(self) -> bool:
        try:
            Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
            connection = self._connect()
            try:
                connection.execute(_SCHEMA)
                connection.execute(_INDEX)
                connection.commit()
            finally:
                connection.close()
            self._last_error = ""
            return True
        except (sqlite3.Error, OSError) as exc:
            self._last_error = str(exc)
            return False

    def _connection(self) -> sqlite3.Connection:
        """الاتصال المعمَّر — يُفتح مرّة ويبقى، تحت قفل.

        كان `_write` و`_read` يفتح كلٌّ منهما اتصالًا ويغلقه. والكلفة ليست
        الاستعلام بل **دورة نظام الملفات**: إنشاء `-wal` و`-shm` ثمّ نقطة
        تفتيش ومحوهما عند كلّ إغلاق. مقيسة في ٧٠٧ ٢٠٢٦-٠٩-٠٩: **٣٣٫٥٣ م.ث
        مقابل ٤٫٤٩** بمعمَّر — ×٧٫٥.
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

    def _write(self, model_name: str, version: str, data_json: str,
               saved_at: float) -> int:
        with self._conn_lock:
            connection = self._connection()
            connection.execute(_UPSERT, (model_name, version, data_json, saved_at))
            pruned = 0
            if self._keep_versions > 0:
                cursor = connection.execute(
                    _PRUNE, (model_name, model_name, self._keep_versions))
                pruned = cursor.rowcount or 0
            connection.commit()
            return pruned

    def _read(self, model_name: str, version: str | None) -> dict[str, Any] | None:
        with self._conn_lock:
            connection = self._connection()
            connection.row_factory = sqlite3.Row
            if version:
                cursor = connection.execute(
                    "SELECT version, data_json, saved_at FROM model_versions"
                    " WHERE model_name = ? AND version = ?", (model_name, version))
            else:
                cursor = connection.execute(
                    "SELECT version, data_json, saved_at FROM model_versions"
                    " WHERE model_name = ? ORDER BY id DESC LIMIT 1", (model_name,))
            row = cursor.fetchone()
            return dict(row) if row is not None else None

    async def _on_persist_requested(self, payload: dict[str, Any]) -> None:
        if not self._running or self._context is None or not isinstance(payload, dict):
            return
        model_name = payload.get("model_name")
        version = payload.get("version")
        if not model_name or not version:
            self.failure_count += 1
            return
        try:
            data_json = json.dumps(payload.get("data"), ensure_ascii=False,
                                   sort_keys=True, default=str)
        except (TypeError, ValueError):
            self.failure_count += 1
            await self._context.publish(EVENT_PERSIST_FAILED, {
                "model_name": model_name, "version": version,
                "reason": REASON_NOT_SERIALISABLE})
            return
        if not self._store_ready:
            self._store_ready = self._ensure_store()
        if not self._store_ready:
            self.failure_count += 1
            await self._context.publish(EVENT_PERSIST_FAILED, {
                "model_name": model_name, "version": version,
                "reason": REASON_STORE_UNAVAILABLE})
            return
        saved_at = _to_float(payload.get("timestamp"))
        if saved_at is None:
            saved_at = _to_float(payload.get("registered_at")) or 0.0
        try:
            pruned = await asyncio.to_thread(
                self._write, str(model_name), str(version), data_json, saved_at)
        except sqlite3.Error as exc:
            self.failure_count += 1
            self._last_error = str(exc)
            await self._context.publish(EVENT_PERSIST_FAILED, {
                "model_name": model_name, "version": version, "reason": str(exc)})
            return
        self.saved_count += 1
        try:
            self._limit_state = await asyncio.to_thread(self._enforce_limits_locked)
        except (OSError, sqlite3.Error, ValueError) as exc:
            self._last_error = str(exc)
        self.pruned_count += pruned
        body: dict[str, Any] = {"model_name": model_name, "version": version,
                                "pruned_versions": pruned}
        if saved_at:
            body["timestamp"] = saved_at
        await self._context.publish(EVENT_PERSISTED, body)
        await self._context.publish(EVENT_MODEL_PERSISTED, {**body, "persisted": True})

    async def _on_load_requested(self, payload: dict[str, Any]) -> None:
        if not self._running or self._context is None or not isinstance(payload, dict):
            return
        request_id = payload.get("request_id")
        model_name = payload.get("model_name")
        if not model_name:
            return
        if not self._store_ready:
            self._store_ready = self._ensure_store()
        row = None
        if self._store_ready:
            try:
                row = await asyncio.to_thread(
                    self._read, str(model_name), payload.get("version"))
            except sqlite3.Error as exc:
                self.failure_count += 1
                self._last_error = str(exc)
        if row is not None:
            try:
                data = json.loads(row["data_json"])
            except (TypeError, ValueError):
                row = None
        if row is None:
            self.missing_count += 1
            await self._context.publish(EVENT_LOAD_RESPONSE, {
                "request_id": request_id, "model_name": model_name, "found": False})
            return
        self.loaded_count += 1
        await self._context.publish(EVENT_LOAD_RESPONSE, {
            "request_id": request_id, "model_name": model_name,
            "version": row["version"], "data": data, "found": True,
            "saved_at": row["saved_at"]})

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
                self._db_path, "model_versions",
                max_db_bytes=self._max_db_bytes)

    async def snapshot(self) -> dict[str, Any]:
        return {"version": ATOM_VERSION, "saved": self.saved_count,
                "loaded": self.loaded_count, "missing": self.missing_count,
                "failures": self.failure_count, "pruned": self.pruned_count}

    async def restore(self, state: dict[str, Any]) -> None:
        if not isinstance(state, dict): raise ValueError("INVALID_MODEL_STORE_STATE")
        self.saved_count=int(state.get("saved") or 0);self.loaded_count=int(state.get("loaded") or 0)
        self.missing_count=int(state.get("missing") or 0);self.failure_count=int(state.get("failures") or 0)
        self.pruned_count=int(state.get("pruned") or 0)

    async def health_check(self) -> HealthStatus:
        if not self._running:
            return HealthStatus(state=HealthState.UNHEALTHY, message=REASON_NOT_STARTED)
        details = {"saved": self.saved_count, "loaded": self.loaded_count,
                   "missing": self.missing_count, "pruned": self.pruned_count,
                   "failures": self.failure_count, "store_ready": self._store_ready,
                   "last_error": self._last_error, "limits": dict(self._limit_state)}
        if not self._store_ready:
            return HealthStatus(
                state=HealthState.DEGRADED,
                message=self._last_error or REASON_STORE_UNAVAILABLE, details=details)
        if self._last_error:
            return HealthStatus(state=HealthState.DEGRADED, message=self._last_error, details=details)
        if self._limit_state.get("breached"):
            return HealthStatus(state=HealthState.DEGRADED, message="STORAGE_LIMIT_ENFORCED", details=details)
        if self.saved_count == 0 and self.loaded_count == 0:
            if self.failure_count:
                return HealthStatus(
                    state=HealthState.DEGRADED,
                    message="SUSPECTED_FAULT: %d save/load failures and no successful activity" % self.failure_count,
                    details=details)
            return HealthStatus(
                state=HealthState.HEALTHY,
                message="READY_AWAITING_FIRST_MODEL_SAVE | saved=0 loaded=0",
                details=details)
        return HealthStatus(
            state=HealthState.HEALTHY,
            message="saved=%d loaded=%d" % (self.saved_count, self.loaded_count),
            details=details)
