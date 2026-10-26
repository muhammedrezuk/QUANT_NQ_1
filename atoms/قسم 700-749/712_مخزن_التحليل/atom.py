from __future__ import annotations

import asyncio
import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

from catchup import decide
from shared.owner_windows import MaintenanceGate
from core.contracts.atom import AtomBase, AtomContext, HealthState, HealthStatus
from storage_policy import enforce_limits, file_lock

ATOM_VERSION = "2.10.0"
MAX_BUFFER_ROWS = 100000
# سقف البفر بالبايت — الحدّ الذي كان ناقصًا. مقيس ٢٠٢٦-٠٨-١٨: صفّ التحليل
# ٢٨ كيلوبايت وسطيًّا، فسقف العدد وحده (١٠٠٬٠٠٠) يعني ٢٫٨ جيجابايت في ذاكرة
# النواة قبل أن يعضّ. ومقيس ٢٠٢٦-٠٩-٠٩ حيًّا: بعد تلف القاعدة ارتدّ البفر
# حتى بلغت لقطته على القرص ١٬١٨٥ ميغابايت — أكبر لقطة في النظام بـ١٢٠ ضعفًا
# عن التالية. البايت هو المقياس الصادق لا العدد.
MAX_BUFFER_BYTES = 64 * 1024 * 1024
# عمر الصفّ في البفر — **بساعة الاستلام المحلّية** (`time.monotonic`) لا
# بطابع الحمولة: طوابع الوسيط بوقت خادمه (فارق ٣ ساعات مقيس)، ونبضة النواة
# تتجمّد وتقفز. والقصّ بالعدد وحده صنع حلقة مغلقة عند ٦٢٤ من قبل. صفٌّ لم
# يُكتب خلال أربعة أضعاف فاصل الدفع فالمخزن معطّل، وحمله ليس تخزينًا.
BUFFER_MAX_AGE_S = 120.0
# اللقطة تُسلسَل JSON كل دورة: بفرٌ ضخم فيها يحجب الحلقة. مقيس على القرص
# ٢٠٢٦-٠٩-٠٩ لهذه الذرّة: ١٫١٨ جيجابايت ≈ ٣٨ ثانية حجب متّصل (كتابة ١٩٫٤ث +
# fsync ٥٫٦ث + تسلسل ~١٢٫٩ث) — والنظام كلّه واقف خلالها. في التشغيل السليم
# البفر ≤ flush_size (٢٠ صفًّا) فلا يعضّ هذا السقف أصلًا.
SNAPSHOT_MAX_BYTES = 1_500_000

_DB_TIMEOUT_S = 5.0
_BUSY_TIMEOUT_MS = 3000
_SECONDS_PER_DAY = 86400.0
# بعد فشل المخزن: لا تُعاد المحاولة مع كل حدث (٦٤ حدثًا/ثانية مقيسة) — بساعة
# الاستلام المحلّية لا بوقت الحمولة، فنبضة النواة تتجمّد وتقفز.
_STORE_RETRY_S = 30.0
_ERROR_LOG_EVERY_S = 60.0

EVENT_IN = "analysis.raw.completed"
EVENT_DAY = "SYS_DAY"
EVENT_PULSE = "SYS_SECOND"
EVENT_OUT = "storage.analysis_saved"

REASON_NOT_STARTED = "NOT_STARTED"
REASON_STORE_UNAVAILABLE = "STORE_UNAVAILABLE"
REASON_NOTHING_STORED = "NOTHING_STORED_YET"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS analysis (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol       TEXT,
    occurred_at  REAL,
    payload_json TEXT,
    recorded_at  REAL
)
"""

# ساعة الاستلام تُضاف لقاعدة قائمة بلا فقد بيانات (NULL للصفوف القديمة).
_MIGRATION_COLUMNS = {"recorded_at": "REAL"}

_INDEXES = (
    "CREATE INDEX IF NOT EXISTS idx_analysis_symbol ON analysis(symbol, id DESC)",
    "CREATE INDEX IF NOT EXISTS idx_analysis_time ON analysis(occurred_at)",
    # فهرس على نفس تعبير التشذيب. بدونه `COALESCE` لا يستعمل فهرسًا إطلاقًا —
    # مقيس ٢٠٢٦-٠٩-٠٩ على مليون صفّ: الخطة `SCAN analysis`، وتشذيبٌ لا يجد ما
    # يحذفه (وهي الحالة الغالبة، يوميًّا) يكلّف **٣٠٨٫٣٨ ms** مسحًا كاملًا
    # مقابل **٠٫٠١ ms** بالفهرس. الفارق يكبر مع نموّ الجدول لا يصغر.
    "CREATE INDEX IF NOT EXISTS idx_analysis_age"
    " ON analysis(COALESCE(occurred_at, recorded_at))",
)

_INSERT = ("INSERT INTO analysis (symbol, occurred_at, payload_json, recorded_at)"
           " VALUES (?,?,?,?)")

# التشذيب على `COALESCE`: حدثٌ بلا طابع في حمولته كان **لا يُشذَّب أبدًا** —
# مقيس ٢٠٢٦-٠٩-٠٩: ٥٬٢٩٧ صفًّا من ٢٩٬٠٧٧ (١٨٪) بـ`occurred_at NULL` موزّعة
# على كل الرموز، لأنّ الناشر لا يضع `timestamp` في بعض أحداثه. كانت تتراكم
# إلى الأبد: لا احتفاظ يمسّها ولا أرشفة. ساعة الاستلام تحسم عمرها بصدق.
_PRUNE = ("DELETE FROM analysis WHERE COALESCE(occurred_at, recorded_at) IS NOT NULL"
          " AND COALESCE(occurred_at, recorded_at) < ?")


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
        self._daily_task: asyncio.Task | None = None
        self._flush_now_task: asyncio.Task | None = None
        self._max_rows = 0
        self._max_db_bytes = 0
        self._archive_db_path = ""
        self._limit_state: dict[str, Any] = {}
        self._last_prune_success: float | None = None
        self._catchup_done = False
        self._catchup_verdict: dict[str, Any] = {}
        # ٢٠٢٦-١٠-٠٩ (ختم المالك «NQ» — الصيانة في استراحة السوق): التشذيب وإنفاذ السقف
        # اليوميّان في نافذة الصيانة وحدها (`shared/owner_windows`) لا على نبض اليوم — 03:00 بتوقيت
        # الجهاز والسوق مفتوح، حيث تجمّدت حلقة المنصّة كلّ ليلة ٠٥–٠٨ تشرين الأوّل.
        self._maintenance = MaintenanceGate()
        self._buffer: list[tuple] = []
        self._buffer_bytes = 0
        self._store_ready = False
        self._store_retry_at = 0.0
        self._last_error = ""
        self._conn: sqlite3.Connection | None = None
        self._last_error_log_at = 0.0
        self.stored_count = 0
        self.dropped_count = 0
        self.store_failure_count = 0

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
        # القدرة موجودة، ومعطَّلة في المانيفست المسلَّم بحكم المالك
        # ٢٠٢٦-٠٩-١٠: **هذا المخزن يُتلف ولا يُرحّل** (نموّه ~٢٫٢ جيجا/يوم
        # ومحتواه لحظيّ يُعاد من السوق). فارغًا هنا يعني الإتلاف.
        self._archive_db_path = str(cfg.get("archive_db_path") or "")
        # ٢٠٢٦-١٠-٠٧ (ختم «NQ»): لا اشتراك في analysis.raw.completed — ناشره أُرشف مع فكّ الأقسام عن القرار؛ `_on_event` باقٍ لأنّ الاختبارات تستدعيه.
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
        for attr in ("_flush_task", "_daily_task", "_flush_now_task"):
            task = getattr(self, attr)
            setattr(self, attr, None)
            if task is not None:
                task.cancel()
                try: await task
                except asyncio.CancelledError: pass
                except Exception: pass  # noqa: BLE001 — الإيقاف لا يُسقطه خطأ دورة
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
        """يُغلق الاتصال إن رمت الـPRAGMA — وإلّا سُرِّب المقبض.

        ``sqlite3.connect`` لا يلمس الملف؛ أوّل PRAGMA هي التي تقرأ الترويسة،
        فترمي على قاعدة تالفة **بعد** إنشاء الاتصال. وبلا هذا الإغلاق يبقى
        الملف ممسوكًا على ويندوز ولا يمكن إزاحته — أي يتعذّر إصلاح ما تلف.
        """
        connection = sqlite3.connect(self._db_path, timeout=_DB_TIMEOUT_S,
                                     check_same_thread=False)
        try:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("PRAGMA busy_timeout=%d" % _BUSY_TIMEOUT_MS)
            connection.execute("PRAGMA synchronous=NORMAL")
        except BaseException:
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
                existing = {row[1] for row in
                            connection.execute("PRAGMA table_info(analysis)").fetchall()}
                for column, column_type in _MIGRATION_COLUMNS.items():
                    if column not in existing:
                        connection.execute("ALTER TABLE analysis ADD COLUMN %s %s"
                                           % (column, column_type))
                for statement in _INDEXES:
                    connection.execute(statement)
                connection.commit()
            self._last_error = ""
            return True
        except (sqlite3.Error, OSError) as exc:
            self._last_error = str(exc)
            self._note_store_failure(exc)
            return False

    @staticmethod
    def _row_bytes(row: tuple) -> int:
        payload = row[2] if len(row) > 2 else None
        return len(payload) + 64 if isinstance(payload, str) else 64

    @staticmethod
    def _row_age(row: tuple, now: float) -> float:
        """عمر الصفّ بساعة الاستلام الرتيبة — العنصر الخامس، لا `occurred_at`."""
        received = row[4] if len(row) > 4 else None
        return now - received if isinstance(received, (int, float)) else 0.0

    def _trim_buffer(self) -> None:
        """ثلاثة حدود والأشدّ يفوز: **الزمن أوّلًا**، ثم البايت، ثم العدد.

        الزمن أوّلًا لأنّ الحدّ بالعدد وحده لا يعضّ حين يكبر الصفّ (١٠٠٬٠٠٠ صفّ
        × ٢٨ كيلوبايت = ٢٫٨ جيجابايت)، والحدّ بالبايت لا يخبرنا أنّ الصفّ صار
        بلا معنى. وبساعة الاستلام المحلّية لا بطابع الحمولة: طابع الوسيط بوقت
        خادمه، ونبضة النواة تتجمّد وتقفز.
        """
        now = time.monotonic()
        while self._buffer and self._row_age(self._buffer[0], now) > BUFFER_MAX_AGE_S:
            dropped = self._buffer.pop(0)
            self._buffer_bytes -= self._row_bytes(dropped)
            self.dropped_count += 1
        while self._buffer and (len(self._buffer) > MAX_BUFFER_ROWS
                                or self._buffer_bytes > MAX_BUFFER_BYTES):
            dropped = self._buffer.pop(0)
            self._buffer_bytes -= self._row_bytes(dropped)
            self.dropped_count += 1
        if not self._buffer:
            self._buffer_bytes = 0

    def _note_store_failure(self, exc: object) -> None:
        """عطل المخزن يُنطَق: صحّةٌ صامتة لا يقرأها أحد.

        تلف ``analysis.db`` يوم ٢٠٢٦-٠٩-٠٧ ظلّ ٦١ ساعة بصفر ذكر في
        ``var/logs/errors-*.log`` — معلَنًا في ``health`` وحدها. والخنق
        (مرّة كل دقيقة) لأنّ الفشل يتكرّر مع كل دفعة.
        """
        self.store_failure_count += 1
        now = time.monotonic()
        if now - self._last_error_log_at < _ERROR_LOG_EVERY_S:
            return
        self._last_error_log_at = now
        context = self._context
        if context is None or getattr(context, "logger", None) is None:
            return
        try:
            context.logger.error(
                "712 مخزن التحليل معطّل: %s | db=%s فشل=%d بفر=%d صفّ/%d بايت مُسقَط=%d",
                exc, self._db_path, self.store_failure_count,
                len(self._buffer), self._buffer_bytes, self.dropped_count)
        except Exception:  # noqa: BLE001 — لا يسقط مخزن بسبب سجلّ
            pass

    def _flush(self) -> int:
        if not self._buffer:
            return 0
        rows, self._buffer = self._buffer, []
        taken = sum(self._row_bytes(row) for row in rows)
        self._buffer_bytes -= taken
        try:
            with self._conn_lock:
                connection = self._connection()
                # الأربعة الأولى تُكتب؛ الخامس (الساعة الرتيبة) داخليّ للبفر.
                connection.executemany(_INSERT, [row[:4] for row in rows])
                connection.commit()
            self._last_error = ""
            if self._buffer_bytes < 0 or not self._buffer:
                self._buffer_bytes = sum(self._row_bytes(row) for row in self._buffer)
            return len(rows)
        except sqlite3.Error as exc:
            # القاعدة مشكوك فيها: يُطرح الاتصال المعمَّر ويُعاد بناؤه.
            with self._conn_lock:
                self._close_connection()
            self._last_error = str(exc)
            # القاعدة مشكوك فيها بعد فشل كتابة: تُعاد المحاولة ببناء المخزن
            # (بخنق زمني) بدل بقاء ``_store_ready`` صادقًا إلى الأبد — كان
            # هذا يمنع أيّ تعافٍ حتى لو أُصلح الملف تحت الذرّة.
            self._store_ready = False
            self._store_retry_at = time.monotonic() + _STORE_RETRY_S
            self._note_store_failure(exc)
            self._buffer = rows + self._buffer
            self._buffer_bytes += taken
            self._trim_buffer()
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

    async def _on_event(self, payload: dict[str, Any]) -> None:
        if not self._running or self._context is None:
            return
        if not isinstance(payload, dict):
            return
        symbol = payload.get("symbol")
        if not symbol:
            return
        if not self._store_ready:
            now = time.monotonic()
            if now < self._store_retry_at:
                self.dropped_count += 1
                return
            self._store_retry_at = now + _STORE_RETRY_S
            self._store_ready = await asyncio.to_thread(self._ensure_store)
            if not self._store_ready:
                self.dropped_count += 1
                return
        occurred = _to_float(payload.get("timestamp"))
        # العنصران الأخيران داخليّان: ساعة الحائط تُكتب في `recorded_at`،
        # والرتيبة (`monotonic`) تحكم عمر الصفّ في البفر ولا تُكتب أبدًا.
        row = (str(symbol), occurred,
               json.dumps(payload, ensure_ascii=False, default=str),
               time.time(), time.monotonic())
        self._buffer.append(row)
        self._buffer_bytes += self._row_bytes(row)
        self._trim_buffer()
        if len(self._buffer) >= self._flush_size:
            self._schedule_flush(occurred)

    def _schedule_flush(self, stamp: float | None) -> bool:
        """دفعة الامتلاء تخرج من مسار الحدث — كما خرجت الدورة الهادئة قبلها.

        كانت `_flush_and_report` تُنتظَر **داخل المعالج** عند بلوغ الحجم، وهي
        رحلة `to_thread` لكتابةٍ كاملة ثمّ نشر — مقيس ٢٠٢٦-٠٩-١٦ من عدّاد
        الناقل أنّ ٧١٢ سجّل **٣٬٣٧٢ تجاوزًا لميزانية ٠٫٠٥ ث وأسوأ مدّة ٧٫٠٤
        ثانية**. والعلّة هي نفسها التي عولجت في `_schedule_daily`: مشترِكٌ
        يحجب يحجب كلّ ما خلفه على مسار العامل. والذاكرة ليست في خطر — حدّها
        محروس بـ`_trim_buffer` (صفوفًا وبايتات) قبل هذا السطر بسطرين، وحلقة
        `_flush_loop` تكتب دوريًّا على كلّ حال؛ فالمهمّة الخلفيّة تعجّل
        الكتابة ولا تكون شرطًا لها.
        """
        if self._flush_now_task is not None and not self._flush_now_task.done():
            return False
        self._flush_now_task = asyncio.create_task(self._flush_and_report(stamp))
        return True

    def _schedule_daily(self, now: float | None) -> bool:
        """الدورة الهادئة تخرج من مسار الحدث — لا تُنتظَر فيه أبدًا.

        مقيس ٢٠٢٦-٠٩-١٠ على نسخة متّسقة من القاعدة الحيّة (١٫٩ جيجا):
        `enforce_limits(shrink=True)` — وفيه `VACUUM` — يستغرق **٢٥١٬٨٨٧ ms**،
        أي أربع دقائق وربعًا، بينما ميزانية تسليم المشترِك **٥٠ ms**. وتسليم
        الناقل يمضي بالتتابع على مسار العامل، فمشترِكٌ يحجب هذا القدر **يحجب
        كلّ ما خلفه** — ومنه تِكّات السوق. الباقي في المسار زهيد بالمقارنة:
        الإنفاذ الساخن ١٥ ms · التشذيب ٢ ms · دفعة الكتابة ٢٥ ms.
        """
        if self._daily_task is not None and not self._daily_task.done():
            return False
        self._daily_task = asyncio.create_task(
            self._flush_and_report(now, prune_at=now))
        return True

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
        if key is not None and self._schedule_daily(now):
            self._maintenance.mark(key, now)

    def _enforce_limits_exclusive(self, shrink: bool) -> dict[str, Any]:
        """‏**الإنفاذ يحتاج القاعدة لنفسه — فيُسلَّم الاتّصال المعمَّر قبله.**

        ‏⛔ هذا إصلاح انحدارٍ سبّبتُه أنا في `2.9.0` (٢٠٢٦-٠٩-١٦).

        ⚠️ **والآلية ليست ما ظننتُ أوّلًا.** قلتُ «المقبض المعمَّر يمنع
        `VACUUM`» ثمّ قِستُها فكذّبتني (قاعدة ٤١ م.ب بـWAL حقيقيّ):

            مقبض خامل، أو كتب ثمّ commit  ⟵ ✓ انكمش ٤١ م.ب ← ٠٫٣٥
            **معاملة كتابة مفتوحة**       ⟵ ⛔ database is locked
            معاملة قراءة مفتوحة           ⟵ ⚠ لا ينكمش، و٦٨٫٨ ثانية صامتة

        فالمقبض وحده بريء. القاتل **معاملةٌ مفتوحة** على القاعدة لحظة
        الإنفاذ — و`sqlite3` في بايثون يفتح معاملةً ضمنيّة مع كلّ كتابة
        وتبقى حتى `commit`. وقبل `2.9.0` كان `_flush` يفتح اتّصاله ويغلقه
        مع كلّ دفعة، فلم يكن هناك اتّصالٌ ثانٍ **يمكن أن يكون في معاملة**
        حين يجري الإنفاذ. بعد التعمير صار ذلك ممكنًا — و`enforce_limits`
        كانت تُنادى **خارج** قفل الإدراج، فيتداخل الاثنان.

        ولذلك فالعلاج الحقيقيّ هو **القفل** (تسلسلٌ يمنع التداخل)، وتسليمُ
        الاتّصال عند `shrink` احتياطٌ ثانٍ يكفينا أيضًا شرّ «معاملة القراءة
        المفتوحة» التي لا تُخطئ بل تصمت وتُبطئ.

        وما جرى ليلة ٢٠٢٦-٠٩-١٨:

            ٠٣:٠٠:٠٥  ٧١٢ معطّل: database is locked | analysis.db
            ٠٣:٠١:١٢  handler timeout subscriber=707
            ٠٣:٠١:٢٨  ٧١٢ معطّل: database is locked
            ٠٣:٠٢:٥٧  ٧١٢ معطّل: database is locked
            … ثمّ صمتَ السجلّ ووقفت المنصّة ٠٣:٢٩

        فيجري الإنفاذ تحت `_conn_lock` (فلا يزاحمه إدراج) **وبعد تسليم
        الاتّصال** (فينال الحصريّة)، ويُعاد فتحه تلقائيًّا عند أوّل استعمال.
        وكلفة إعادة الفتح تُدفع مرّةً في الدورة لا مع كلّ صفّ.
        """
        with self._conn_lock:
            # التمييز مقصود: **`VACUUM` وحده يطلب حصريّة القاعدة**، وهو لا
            # يجري إلّا في الدورة الهادئة (`shrink=True`) مرّةً في اليوم.
            # أمّا المسار الساخن فحذفٌ فقط، ويمضي باتّصالٍ ثانٍ في WAL بلا
            # مزاحمة — وهكذا عاش ٧٠٧ أيّامًا. فلو سُلِّم الاتّصال مع كلّ دفعة
            # لعاد فتحٌ وإغلاقٌ لكلّ دورة، وهو الذي عُمِّر الاتّصال لإلغائه.
            if shrink:
                self._close_connection()
            return enforce_limits(
                self._db_path, "analysis",
                max_rows=self._max_rows, max_db_bytes=self._max_db_bytes,
                shrink=shrink, archive_db_path=self._archive_db_path)

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
            self._limit_state = await asyncio.to_thread(
                self._enforce_limits_exclusive, prune_at is not None)
        except (OSError, sqlite3.Error, ValueError) as exc:
            self._last_error = str(exc)
        else:
            # تعذُّر الأرشيف يعني أنّ السقف لم يُنفَّذ — يُنطق ولا يُبتلع.
            problem = self._limit_state.get("archive_error")
            if problem:
                self._last_error = "ARCHIVE: %s" % problem
                self._note_store_failure(self._last_error)
        if written == 0 and prune_at is None:
            return
        body: dict[str, Any] = {
            "rows": written, "total": self.stored_count, "pruned": pruned}
        if stamp is not None:
            body["timestamp"] = stamp
        await self._context.publish(EVENT_OUT, body)

    async def snapshot(self) -> dict[str, Any]:
        """اللقطة تحمل الأحدث ضمن سقف بايتي — لا البفر كلّه.

        قِيس على الحيّ ٢٠٢٦-٠٩-٠٩: ``snapshots\\712.json`` = ١٬١٨٥ ميغابايت
        تُسلسَل كل دورة. البفر ليس حالةً يُعاد بناء المنصّة منها؛ ما يفيض عن
        السقف يُحصى في ``snapshot_omitted`` ولا يُخفى.
        """
        kept: list[tuple] = []
        size = 0
        for row in reversed(self._buffer):
            row_size = self._row_bytes(row)
            if kept and size + row_size > SNAPSHOT_MAX_BYTES:
                break
            # الثلاثي وحده يُصدَّر: ساعة الاستلام `monotonic` تُصفَّر مع
            # العملية فلا معنى لها عبر إعادة التشغيل، وتُختَم من جديد في
            # `restore`. وهذا يُبقي اللقطة متوافقة مع الشكل السابق.
            kept.append(tuple(row[:3]))
            size += row_size
        kept.reverse()
        return {"version": ATOM_VERSION, "buffer": kept,
                "snapshot_omitted": len(self._buffer) - len(kept),
                "snapshot_bytes": size,
                "dropped_count": self.dropped_count, "stored_count": self.stored_count,
                "last_prune_success": self._last_prune_success,
                **self._maintenance.snapshot()}

    async def restore(self, state: dict[str, Any]) -> None:
        rows = state.get("buffer") if isinstance(state, dict) else None
        if not isinstance(rows, list) or not all(isinstance(row, (list, tuple)) for row in rows):
            raise ValueError("INVALID_STORAGE_BUFFER_STATE")
        # ساعة الاستلام تُختَم من جديد: العمر يُحسب من لحظة دخول الصفّ هذه
        # العملية. ولقطة ضخمة موروثة تُقصّ هنا فورًا — مقيس ٢٠٢٦-٠٩-٠٩ أنّ
        # ١٫٢٤ جيجابايت كانت **تُستعاد** لا تُبنى، فإعادة التشغيل لا تنظّفها.
        wall, stamped = time.time(), time.monotonic()
        self._buffer = [tuple(row)[:3] + (wall, stamped)
                        for row in rows[-MAX_BUFFER_ROWS:]]
        self._buffer_bytes = sum(self._row_bytes(row) for row in self._buffer)
        self._trim_buffer()
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
            "buffered": len(self._buffer), "buffered_bytes": self._buffer_bytes,
            "store_failures": self.store_failure_count, "db_path": self._db_path,
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
            message="stored=%d buffered=%d dropped=%d" % (
                self.stored_count, len(self._buffer), self.dropped_count),
            details=details)
