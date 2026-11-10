from __future__ import annotations

import asyncio
import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

from catchup import decide
from shared import owner_trades
from shared.owner_windows import MaintenanceGate
from core.contracts.atom import AtomBase, AtomContext, HealthState, HealthStatus
from storage_policy import enforce_limits, file_lock

ATOM_VERSION = "5.7.0"
MAX_BUFFER_ROWS = 100000

# ٢٠٢٦-١٠-٢٦ (قانون صفقات المالك، ختم «NQ»: «صفقات انا بفتحها مالها علاقة بل منظومة ابدا ولا بصير يقيس عليها ولا
# يسجلها»): ظهور مركز المالك واختفاؤه لا يُحفظان في الخطّ الزمنيّ ولا يُعدّان في `recorded` — بالتمييز الواحد في
# `shared/owner_trades.py`. والترشيح لهذين الحدثين وحدهما: فيهما وحدهما صفقة المالك. أمّا غيرهما فللمنظومة وإن حمل سحرًا
# غير سحرها — ٥٥٢ يردّ أمر المنظومة الذي سحره صفر (`MISSING_MAGIC`)، فلو رُشّح كلّ حدثٍ لغاب عيب المنظومة من خطّها.
# وما حُفظ قبل اليوم يبقى كما هو — لا حذف.
OWNER_POSITION_EVENTS = frozenset({"platform.position.appeared", "platform.position.vanished"})

_DB_TIMEOUT_S = 5.0
_BUSY_TIMEOUT_MS = 3000
_SECONDS_PER_DAY = 86400.0

EVENT_DAY = "SYS_DAY"
EVENT_PULSE = "SYS_SECOND"
EVENT_OUT = "storage.timeline_saved"

REASON_NOT_STARTED = "NOT_STARTED"
REASON_STORE_UNAVAILABLE = "STORE_UNAVAILABLE"
REASON_NO_ACTIVITY = "NO_EVENTS_YET"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS timeline (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id      TEXT,
    event_name   TEXT NOT NULL,
    account_id   TEXT,
    symbol       TEXT,
    occurred_at  REAL,
    payload_json TEXT,
    recorded_at  REAL
)
"""

# ساعة الاستلام تُضاف لقاعدة قائمة بلا فقد بيانات (NULL للصفوف القديمة).
# خطُّ زمنٍ مرتَّب بطابع الناشر وحده يكذب حين تختلف ساعات الناشرين: مقيس
# ٢٠٢٦-٠٩-١٦ أنّ `platform.trade_event` يأتي بساعة خادم الوسيط (**+٢٫٨٣
# ساعة**) فأحد عشر صفًّا هنا بتاريخٍ مستقبليّ بينما كلّ المصادر الأخرى
# نظيفة. الترتيب الصادق يحتاج ساعةً واحدة — ساعتنا.
_MIGRATION_COLUMNS = {"recorded_at": "REAL"}

# فارق يُعدّ طابعًا مستقبليًّا، ودوريّة نطقه.
_FUTURE_STAMP_TOLERANCE_S = 60.0
_STAMP_LOG_EVERY_S = 60.0

_INDEXES = (
    "CREATE INDEX IF NOT EXISTS idx_timeline_event ON timeline(event_name, id DESC)",
    "CREATE INDEX IF NOT EXISTS idx_timeline_account ON timeline(account_id, id DESC)",
    "CREATE INDEX IF NOT EXISTS idx_timeline_time ON timeline(occurred_at)",
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_timeline_event_id ON timeline(event_id) WHERE event_id IS NOT NULL",
    # فهرس على نفس تعبير التشذيب: بدونه لا يُستعمل فهرس عمود مع `COALESCE`،
    # فيُمسح الجدول كلّه في كل دورة (مقيس على جدولٍ مماثل: ٣٠٨ ms مقابل ٠٫٠١).
    "CREATE INDEX IF NOT EXISTS idx_timeline_age"
    " ON timeline(COALESCE(occurred_at, recorded_at))",
)

_INSERT = (
    "INSERT OR IGNORE INTO timeline (event_id, event_name, account_id, symbol,"
    " occurred_at, payload_json, recorded_at)"
    " VALUES (?,?,?,?,?,?,?)"
)

# التشذيب على `COALESCE`: حدثٌ بلا طابع في حمولته لا يُشذَّب أبدًا، وحدثٌ
# بطابعٍ مستقبليّ ينجو من كل عتبة. ساعة الاستلام تحسم عمر الصفّ بصدق.
_PRUNE = ("DELETE FROM timeline WHERE COALESCE(occurred_at, recorded_at) IS NOT NULL"
          " AND COALESCE(occurred_at, recorded_at) < ?")


def _to_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _clock_skew(payload, stamp, now):
    """انحراف ساعة المصدر — أيًّا كان الحقل الذي يحمله.

    عقد `platform.trade_event` تغيّر ٢٠٢٦-٠٩-١٦ (٦١١ v4.1.0): `timestamp`
    صار **بساعتنا**، وطابع الوسيط انتقل إلى `broker_time` ومعه
    `clock_skew_s` جاهزًا. فقياسُ الانحراف من `timestamp` وحده — كما كان —
    **يعمى بعد هذا التغيير**: العدّاد يتوقّف عن الزيادة لا لأنّ العلّة زالت
    بل لأنّ مكانها تبدّل. تُقرأ المصادر الثلاثة بالترتيب، وأوّلُ موجودٍ يفوز:
    الحقل الجاهز · ثمّ `broker_time - timestamp` · ثمّ (توافقًا مع الناشرين
    الذين لم يتحوّلوا بعد) `timestamp - الآن`.
    """
    if not isinstance(payload, dict):
        return None
    ready = _to_float(payload.get("clock_skew_s"))
    if ready is not None:
        return ready
    broker = _to_float(payload.get("broker_time"))
    if broker is not None:
        return broker - (stamp if stamp is not None else now)
    return None if stamp is None else stamp - now


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
        self._watch_events: list[str] = []
        self._flush_size = 0
        self._retention_days = 0.0
        self._flush_interval_s = 5.0
        self._flush_task: asyncio.Task | None = None
        self._immediate_events: set[str] = set()
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
        self._daily_task: asyncio.Task | None = None
        self._skipped_while_busy = 0
        self.recorded_count = 0
        self.future_stamp_count = 0
        self._last_stamp_log_at = 0.0
        self.flushed_count = 0
        self.dropped_count = 0
        self.duplicate_count = 0

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
        self._watch_events = [str(e) for e in cfg["watch_events"]]
        self._flush_size = int(cfg["flush_size"])
        self._retention_days = float(cfg["retention_days"])
        self._flush_interval_s = float(cfg.get("flush_interval_s", 5.0))
        self._immediate_events = {str(e) for e in cfg.get("immediate_events", [])}
        self._max_rows = int(cfg.get("max_rows", 0))
        self._max_db_bytes = int(cfg.get("max_db_bytes", 0))
        for event_name in self._watch_events:
            context.subscribe(event_name, self._make_recorder(event_name))
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
        for name in ("_flush_task", "_daily_task"):
            task = getattr(self, name)
            setattr(self, name, None)
            if task is not None:
                task.cancel()
                try: await task
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
                    self.flushed_count += await asyncio.to_thread(self._flush)
                    await self._enforce_limits()
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
                columns = {str(row[1]) for row in connection.execute("PRAGMA table_info(timeline)")}
                if "event_id" not in columns: connection.execute("ALTER TABLE timeline ADD COLUMN event_id TEXT")
                for column, column_type in _MIGRATION_COLUMNS.items():
                    if column not in columns:
                        connection.execute("ALTER TABLE timeline ADD COLUMN %s %s"
                                           % (column, column_type))
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
                before = connection.total_changes
                connection.executemany(_INSERT, rows)
                inserted = connection.total_changes - before
                connection.commit()
                self.duplicate_count += len(rows) - inserted
            self._last_error = ""
            return inserted
        except sqlite3.Error as exc:
            # القاعدة مشكوك فيها: يُطرح الاتصال المعمَّر ويُعاد بناؤه.
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
            # القاعدة مشكوك فيها: يُطرح الاتصال المعمَّر ويُعاد بناؤه.
            with self._conn_lock:
                self._close_connection()
            self._last_error = str(exc)
            return 0

    def _make_recorder(self, event_name: str):
        async def handler(payload: dict[str, Any]) -> None:
            await self._record(event_name, payload)
        return handler

    async def _record(self, event_name: str, payload: dict[str, Any]) -> None:
        if not self._running or self._context is None:
            return
        if event_name in OWNER_POSITION_EVENTS and owner_trades.is_owner(payload):
            return
        if not self._store_ready:
            self._store_ready = self._ensure_store()
            if not self._store_ready:
                self.dropped_count += 1
                return
        event_id = None
        account_id = None
        symbol = None
        occurred = None
        if isinstance(payload, dict):
            event_id = str(payload.get("event_id") or "").strip() or None
            account_id = payload.get("account_id")
            symbol = payload.get("symbol")
            occurred = _to_float(payload.get("timestamp"))
        try:
            payload_json = json.dumps(payload, ensure_ascii=False, default=str)
        except (TypeError, ValueError):
            payload_json = None
        recorded = time.time()
        skew = _clock_skew(payload, occurred, recorded)
        if skew is not None and skew > _FUTURE_STAMP_TOLERANCE_S:
            self.future_stamp_count += 1
            self._note_future_stamp(event_name, recorded + skew, recorded)
        self._buffer.append((
            event_id,
            event_name,
            str(account_id) if account_id else None,
            str(symbol) if symbol else None,
            occurred,
            payload_json,
            recorded,
        ))
        self.recorded_count += 1
        if event_name in self._immediate_events or len(self._buffer) >= self._flush_size:
            self.flushed_count += await asyncio.to_thread(self._flush)
            await self._enforce_limits()

    def _note_future_stamp(self, event_name: str, stamp: float, now: float) -> None:
        """انحراف ساعة الناشر يُنطق ولا يُصحَّح — بخنق دقيقة."""
        if now - self._last_stamp_log_at < _STAMP_LOG_EVERY_S:
            return
        self._last_stamp_log_at = now
        context = self._context
        if context is None or getattr(context, "logger", None) is None:
            return
        try:
            context.logger.warning(
                "704 الخط الزمني: طابع من المستقبل — حدث=%s فرق=%+.0f ثانية"
                " (%.2f ساعة). يُخزَّن كما جاء في occurred_at، وساعة الاستلام"
                " في recorded_at. مجموع=%d",
                event_name, stamp - now, (stamp - now) / 3600.0,
                self.future_stamp_count)
        except Exception:  # noqa: BLE001 — لا يسقط مخزن بسبب سجلّ
            pass

    async def _enforce_limits(self) -> None:
        try:
            self._limit_state = await asyncio.to_thread(self._enforce_limits_locked)
        except (OSError, sqlite3.Error, ValueError) as exc:
            self._last_error = str(exc)

    def _schedule_daily(self, payload: dict[str, Any]) -> bool:
        """دورة اليوم تخرج من مسار الحدث — دفعٌ وتشذيبٌ وإنفاذُ سقف.

        مقيس ٢٠٢٦-٠٩-١٦: تسليم الناقل يمضي بالتتابع على مسار العامل، وميزانية
        المعالج ٠٫٠٥ ث — بينما هذه الدورة ثلاث رحلات خيطٍ وإنفاذُ سقفٍ على
        قاعدةٍ تكبر. نفس علاج ٧١٢ و٧١٤ و٧١٨: مهمّة خلفيّة بحارس «واحدة في
        آنٍ»، فنداءُ يومٍ ثانٍ أثناء دورةٍ جارية يُهمَل بدل أن يتراكم.
        """
        if self._daily_task is not None and not self._daily_task.done():
            self._skipped_while_busy += 1
            return False
        self._daily_task = asyncio.create_task(self._run_daily(payload))
        return True

    async def _on_day(self, payload: dict[str, Any]) -> None:
        if not self._running or self._context is None:
            return
        self._maintain(_to_float(payload.get("official_time", payload.get("timestamp"))),
                       EVENT_DAY)

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
                self._db_path, "timeline",
                max_rows=self._max_rows, max_db_bytes=self._max_db_bytes)

    async def _run_daily(self, payload: dict[str, Any]) -> None:
        if not self._running or self._context is None:
            return
        self.flushed_count += await asyncio.to_thread(self._flush)
        now = _to_float(payload.get("official_time", payload.get("timestamp")))
        pruned = 0
        if now is not None:
            self._last_error = ""
            pruned = await asyncio.to_thread(self._prune, now)
            if not self._last_error:
                self._last_prune_success = now
        await self._enforce_limits()
        body: dict[str, Any] = {
            "recorded": self.recorded_count, "flushed": self.flushed_count,
            "duplicates": self.duplicate_count,
            "pruned": pruned,
        }
        if now is not None:
            body["timestamp"] = now
        await self._context.publish(EVENT_OUT, body)

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
        if key is not None and self._schedule_daily({"official_time": now}):
            self._maintenance.mark(key, now)

    async def snapshot(self) -> dict[str, Any]:
        return {"version": ATOM_VERSION, "buffer": list(self._buffer[-MAX_BUFFER_ROWS:]),
                "dropped_count": self.dropped_count, "recorded_count": self.recorded_count,
                "flushed_count": self.flushed_count,
                "last_prune_success": self._last_prune_success,
                **self._maintenance.snapshot()}

    async def restore(self, state: dict[str, Any]) -> None:
        rows = state.get("buffer") if isinstance(state, dict) else None
        if not isinstance(rows, list) or not all(isinstance(row, (list, tuple)) for row in rows):
            raise ValueError("INVALID_STORAGE_BUFFER_STATE")
        self._buffer = [tuple(row) for row in rows[-MAX_BUFFER_ROWS:]]
        self.dropped_count = int(state.get("dropped_count") or 0)
        self.recorded_count = int(state.get("recorded_count") or 0)
        self.flushed_count = int(state.get("flushed_count") or 0)
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
            "recorded": self.recorded_count, "flushed": self.flushed_count,
            "duplicates": self.duplicate_count,
            "buffered": len(self._buffer), "dropped": self.dropped_count,
            "watching": len(self._watch_events), "db_path": self._db_path,
            "last_error": self._last_error, "limits": dict(self._limit_state),
            "last_prune_success": self._last_prune_success,
            "catchup": dict(self._catchup_verdict),
        }
        if not self._store_ready:
            return HealthStatus(
                state=HealthState.DEGRADED,
                message=self._last_error or REASON_STORE_UNAVAILABLE, details=details)
        if self._last_error:
            return HealthStatus(state=HealthState.DEGRADED, message=self._last_error, details=details)
        if self._limit_state.get("breached"):
            return HealthStatus(state=HealthState.DEGRADED, message="STORAGE_LIMIT_ENFORCED", details=details)
        if self.recorded_count == 0:
            return HealthStatus(
                state=HealthState.DEGRADED, message=REASON_NO_ACTIVITY, details=details)
        return HealthStatus(
            state=HealthState.HEALTHY,
            message="recorded=%d flushed=%d" % (self.recorded_count, self.flushed_count),
            details=details)
