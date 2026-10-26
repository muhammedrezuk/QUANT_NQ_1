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

ATOM_VERSION = "2.6.0"

_DB_TIMEOUT_S = 5.0
_BUSY_TIMEOUT_MS = 3000
_SECONDS_PER_DAY = 86400.0
_ROW_WIDTH = 7

EVENT_IN = "portfolio.summary"
EVENT_OVERVIEW = "portfolio.overview.state"
EVENT_DAY = "SYS_DAY"
EVENT_PULSE = "SYS_SECOND"
EVENT_OUT = "storage.portfolio_saved"

REASON_NOT_STARTED = "NOT_STARTED"
REASON_STORE_UNAVAILABLE = "STORE_UNAVAILABLE"
REASON_NOTHING_STORED = "NOTHING_STORED_YET"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS portfolio (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id   TEXT,
    equity       REAL,
    balance      REAL,
    realised_pnl REAL,
    open_count   INTEGER,
    occurred_at  REAL,
    payload_json TEXT
)
"""

_INDEXES = (
    "CREATE INDEX IF NOT EXISTS idx_portfolio_account ON portfolio(account_id, id DESC)",
    "CREATE INDEX IF NOT EXISTS idx_portfolio_time ON portfolio(occurred_at)",
)

_INSERT = (
    "INSERT INTO portfolio (account_id, equity, balance, realised_pnl, open_count,"
    " occurred_at, payload_json) VALUES (?,?,?,?,?,?,?)"
)

_PRUNE = "DELETE FROM portfolio WHERE occurred_at IS NOT NULL AND occurred_at < ?"


def _to_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _to_int(value: Any) -> int | None:
    try:
        return int(value)
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
        self._min_interval_s = 0.0
        self._retention_days = 0
        self._max_rows = 0
        self._limit_state: dict[str, Any] = {}
        self._last_prune_success: float | None = None
        self._catchup_done = False
        self._catchup_verdict: dict[str, Any] = {}
        # ٢٠٢٦-١٠-٠٩ (ختم المالك «NQ» — الصيانة في استراحة السوق): التشذيب وإنفاذ السقف
        # اليوميّان في نافذة الصيانة وحدها (`shared/owner_windows`) لا على نبض اليوم — 03:00 بتوقيت
        # الجهاز والسوق مفتوح، حيث تجمّدت حلقة المنصّة كلّ ليلة ٠٥–٠٨ تشرين الأوّل.
        self._maintenance = MaintenanceGate()
        self._last_written: dict[str, float] = {}
        self._store_ready = False
        self._last_error = ""
        self._conn: sqlite3.Connection | None = None
        self.stored_count = 0
        self.skipped_count = 0
        self.dropped_count = 0
        self._pending: list[tuple] = []
        self._write_task: asyncio.Task | None = None
        self._daily_task: asyncio.Task | None = None
        self._skipped_while_busy = 0

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
        self._min_interval_s = float(cfg["min_write_interval_s"])
        self._retention_days = int(cfg["retention_days"])
        self._max_rows = int(cfg.get("max_rows", 0))
        context.subscribe(EVENT_IN, self._on_summary)
        context.subscribe(EVENT_OVERVIEW, self._on_summary)
        context.subscribe(EVENT_DAY, self._on_day)
        context.subscribe(EVENT_PULSE, self._on_pulse)
        self._store_ready = self._ensure_store()
        self._initialized = True

    async def start(self) -> None:
        if not self._initialized or self._running or self._context is None:
            return
        self._catchup_done = False
        self._running = True

    async def stop(self) -> None:
        self._running = False
        # مهامٌّ مجدولة تُمهَل، وما بقي في `_pending` يُكتب — التأجيل ليس فقدًا.
        for name in ("_write_task", "_daily_task"):
            task = getattr(self, name)
            setattr(self, name, None)
            if task is not None and not task.done():
                try:
                    await task
                except Exception:  # noqa: BLE001 — الإيقاف لا يُسقطه خطأ دورة
                    pass
        if self._pending:
            await asyncio.to_thread(self._write_pending)
        # الإغلاق يُجري نقطة تفتيش ويطوي الـWAL — لا يُترك اتصال معلّقًا.
        with self._conn_lock:
            self._close_connection()

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

    def _write_pending(self) -> int:
        if not self._pending: return 0
        rows = list(self._pending)
        try:
            with self._conn_lock:
                connection = self._connection()
                connection.executemany(_INSERT, rows); connection.commit()
            del self._pending[:len(rows)]; self._last_error = ""; return len(rows)
        except sqlite3.Error as exc:
            # القاعدة مشكوك فيها: يُطرح الاتصال المعمَّر ويُعاد بناؤه.
            with self._conn_lock:
                self._close_connection()
            self._last_error = str(exc); return 0

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
            # القاعدة مشكوك فيها: يُطرح الاتصال المعمَّر ويُعاد بناؤه.
            with self._conn_lock:
                self._close_connection()
            self._last_error = str(exc)
            return 0

    async def _on_summary(self, payload: dict[str, Any]) -> None:
        if not self._running or self._context is None or not isinstance(payload, dict): return
        raw_accounts = payload.get("accounts")
        accounts = raw_accounts if isinstance(raw_accounts, list) else [payload]
        accepted = 0
        for item in accounts:
            if not isinstance(item, dict): continue
            account_id = str(item.get("account_id") or "")
            if not account_id: self.dropped_count += 1; continue
            occurred = _to_float(item.get("timestamp", payload.get("timestamp")))
            if occurred is not None and account_id in self._last_written and occurred - self._last_written[account_id] < self._min_interval_s:
                self.skipped_count += 1; continue
            self._pending.append((account_id, _to_float(item.get("equity")),
                _to_float(item.get("balance")), _to_float(item.get("realised_pnl")),
                _to_int(item.get("open_count")), occurred,
                json.dumps(item, ensure_ascii=False, default=str)))
            if occurred is not None: self._last_written[account_id] = occurred
            accepted += 1
        if not accepted and not self._pending: return
        self._schedule_write(accounts)

    def _schedule_write(self, accounts: list) -> bool:
        """الكتابة تخرج من مسار الحدث — رحلةُ خيطٍ لا تُنتظَر في معالج.

        مقيس ٢٠٢٦-٠٩-١٦: تسليم الناقل يمضي بالتتابع على مسار العامل وميزانية
        المعالج ٠٫٠٥ ث، بينما هذا المسار رحلتا خيطٍ (كتابة ثمّ إنفاذ سقف).
        نفس علاج ٧١٢ و٧١٨: مهمّة خلفيّة بحارس «واحدة في آنٍ». والصفوف تنتظر
        في `_pending` — لا تضيع — فالنداء المُهمَل يكتبها في الدورة التالية.
        """
        if self._write_task is not None and not self._write_task.done():
            self._skipped_while_busy += 1
            return False
        self._write_task = asyncio.create_task(self._write_and_report(accounts))
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
                self._db_path, "portfolio", max_rows=self._max_rows)

    async def _write_and_report(self, accounts: list) -> None:
        if self._context is None:
            return
        if not self._store_ready: self._store_ready = self._ensure_store()
        if not self._store_ready: return
        written = await asyncio.to_thread(self._write_pending)
        if not written: return
        self.stored_count += written
        try:
            self._limit_state = await asyncio.to_thread(self._enforce_limits_locked)
        except (OSError, sqlite3.Error, ValueError) as exc:
            self._last_error = str(exc)
        await self._context.publish(EVENT_OUT, {"rows": written, "total": self.stored_count,
            "accounts": sorted(str(item.get("account_id")) for item in accounts
                               if isinstance(item, dict) and item.get("account_id")),
            "skipped": self.skipped_count})

    def _schedule_daily(self, now: float) -> bool:
        """دورة اليوم تخرج من مسار الحدث — تشذيبٌ وإنفاذُ سقف، رحلتا خيط."""
        if self._daily_task is not None and not self._daily_task.done():
            self._skipped_while_busy += 1
            return False
        self._daily_task = asyncio.create_task(self._run_daily(now))
        return True

    async def _on_day(self, payload: dict[str, Any]) -> None:
        if not self._running or self._context is None:
            return
        now = _to_float(payload.get("official_time", payload.get("timestamp")))
        if now is None:
            return
        self._maintain(now, EVENT_DAY)

    async def _run_daily(self, now: float) -> None:
        if self._context is None:
            return
        self._last_error = ""
        pruned = await asyncio.to_thread(self._prune, now)
        if not self._last_error:
            self._last_prune_success = now
        try:
            self._limit_state = await asyncio.to_thread(self._enforce_limits_locked)
        except (OSError, sqlite3.Error, ValueError) as exc:
            self._last_error = str(exc)
        await self._context.publish(EVENT_OUT, {
            "rows": 0, "total": self.stored_count, "pruned": pruned, "timestamp": now})

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
        if key is not None and self._schedule_daily(now):
            self._maintenance.mark(key, now)

    async def snapshot(self) -> dict[str, Any]:
        return {"version": ATOM_VERSION, "pending": [list(row) for row in self._pending],
                "last_written": dict(self._last_written), "stored": self.stored_count,
                "skipped": self.skipped_count, "dropped": self.dropped_count,
                "last_prune_success": self._last_prune_success,
                **self._maintenance.snapshot()}

    async def restore(self, state: dict[str, Any]) -> None:
        rows = state.get("pending") if isinstance(state, dict) else None
        if not isinstance(rows, list): raise ValueError("INVALID_PORTFOLIO_STORE_STATE")
        self._pending = [tuple(row) for row in rows if isinstance(row, list) and len(row) == _ROW_WIDTH]
        self._last_written = {str(k): float(v) for k,v in (state.get("last_written") or {}).items()}
        self.stored_count = int(state.get("stored") or 0); self.skipped_count = int(state.get("skipped") or 0); self.dropped_count = int(state.get("dropped") or 0)
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
        details = {"stored": self.stored_count, "skipped": self.skipped_count,
                   "dropped": self.dropped_count, "accounts": len(self._last_written),
                   "db_path": self._db_path, "last_error": self._last_error,
                   "limits": dict(self._limit_state),
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
        if self.stored_count == 0:
            return HealthStatus(
                state=HealthState.DEGRADED, message=REASON_NOTHING_STORED, details=details)
        return HealthStatus(
            state=HealthState.HEALTHY,
            message="stored=%d skipped=%d" % (self.stored_count, self.skipped_count),
            details=details)
