"""٧٠٧ — طبقة sqlite: المخطّط والهجرة والإدراج والترحيل والاتّصال المعمَّر.

v4.20.1 (٢٠٢٦-١٠-٠١، ختم المالك «Nq»): نُقلت **حرفيًّا** من `atom.py` ليبقى تحت حدّ
الأربع مئة سطر فعليّ (المادة ٩ ملف ٤). كلُّ نصّ SQL واسمِ جدولٍ وعمود، والهجرةُ،
وترحيلُ سبب الرفض بشرط `4.20.0` (ينتهي حين ينتهي ما يُرحَّل) — كما كانت حرفًا بحرف.
كلّ دالّةٍ هنا تأخذ الذرّة أوّلًا (`atom`) مكان `self`، و`atom.py` يُبقي اسمها القديم
بوّابةً رفيعة — فكلّ نداءٍ `atom._x(...)` يمرّ من الذرّة كما كان.
"""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path
from typing import Any

from decision_store_stages import STAGE_DECISION_FINALIZED

_DB_TIMEOUT_S = 20.0
# مهلة انتظار الكاتب حين تكون القاعدة مقفلة. رُفعت من ٣ ثوانٍ إلى ٢٠ بعد
# قياس حيّ ٢٠٢٦-٠٩-١٠: أربعة إخفاقات `database is locked` في ثلاث عشرة ساعة
# (٠٧:١٦ · ١٠:٠٩ · ١١:٢١ · ١٣:٢٤) والعدّاد من ٣٦ إلى ٤٢ — أي **قرارات ضاعت
# لأنّ كاتبًا آخر أمسك القاعدة أطول من ثلاث ثوانٍ**. القرار الضائع لا يُعوَّض،
# والانتظار يقع في خيط `to_thread` لا في حلقة الأحداث فلا يجمّد شيئًا.
# والقافل حُدِّد بعدها بالمطابقة: **هذه الذرّة نفسها** (`enforce_limits`
# باتصال ثانٍ) — لا ٧١٤ ولا ٧١٦؛ وعولج بقفل الإدراج المشترك في `4.8.0`.
# المهلة تبقى حاجزًا أخيرًا أمام كاتبٍ من خارج الذرّة.
_BUSY_TIMEOUT_MS = 20000
# وإن انتهت المهلة رغم ذلك: محاولة أخيرة قبل أن يُعلَن القرار ضائعًا.
_LOCK_RETRY = 1
_LOCK_RETRY_SLEEP_S = 0.5
# أقصى ما يُسمح للمعالج أن ينتظره على قفل الملفّ. المقيس ٢٠٢٦-٠٩-١٩ من تشريحي
# الحيّ: عملُ sqlite نفسه **٠٫٥٤٧ م.ث** وسطًا، والانتظار على القفل **٤٦١٫٨٣٣**
# وأسوأه **١١٬٤٧١٫٨** — أي ٢٢٩ ضعف ميزانية المعالج (٥٠ م.ث). فخمس مئاتٍ من
# الثانية تكفي كلَّ إدراجٍ غير متنازَع عليه بتسعة أضعاف، ولا تُقارب الميزانية.
_HANDLER_LOCK_WAIT_S = 0.005


class _LockBusy(Exception):
    """القفل بيد جارٍ الآن — لا يُنتظَر في المعالج، يُؤجَّل إلى الدفعة."""


_SCHEMA = """
CREATE TABLE IF NOT EXISTS decisions (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    stage        TEXT NOT NULL,
    request_id   TEXT,
    account_id   TEXT,
    symbol       TEXT,
    direction    TEXT,
    approved     INTEGER,
    reason       TEXT,
    confidence   REAL,
    strategy_id  TEXT,
    model_id     TEXT,
    volume       REAL,
    stop_loss    REAL,
    take_profit  REAL,
    payload_json TEXT,
    decided_at   REAL,
    decision_id  TEXT,
    gate_request_id TEXT,
    rejection_reason TEXT,
    recorded_at  REAL
)
"""

_INDEXES = (
    "CREATE INDEX IF NOT EXISTS idx_decisions_request ON decisions(request_id)",
    "CREATE INDEX IF NOT EXISTS idx_decisions_account ON decisions(account_id, id DESC)",
    "CREATE INDEX IF NOT EXISTS idx_decisions_stage ON decisions(stage, id DESC)",
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_decisions_dedupe ON decisions(stage, account_id, request_id) WHERE request_id IS NOT NULL",
)

# T5 (tail item, seal 22): the two link columns a pre-existing live database
# lacks. Added via ALTER TABLE ADD COLUMN (NULL default, no data loss) only
# when PRAGMA table_info shows them missing -- safe to run on every startup,
# including a database that already has them (idempotent, no error).
# ٢٠٢٦-٠٩-٠٩: ومعهما عمودان جديدان — سبب الرفض الحقيقي، وساعة الاستلام.
_MIGRATION_COLUMNS = {
    "decision_id": "TEXT",
    "gate_request_id": "TEXT",
    "rejection_reason": "TEXT",
    "recorded_at": "REAL",
}

_COLUMNS = ("stage", "request_id", "account_id", "symbol", "direction", "approved",
            "reason", "confidence", "strategy_id", "model_id", "volume", "stop_loss",
            "take_profit", "payload_json", "decided_at", "decision_id", "gate_request_id",
            "rejection_reason", "recorded_at")

_INSERT_SQL = "INSERT OR IGNORE INTO decisions (%s) VALUES (%s)" % (
    ", ".join(_COLUMNS), ", ".join("?" for _ in _COLUMNS))

# ترحيل سبب الرفض للصفوف التي سبقت العمود. الحمولة تحملها منذ البداية، لكنّ
# العمود أُضيف ٢٠٢٦-٠٩-٠٩ فبقيت ٧٢٬٦٦٦ رفضة قديمة بـNULL — واللوحة تقرأ
# العمود. يجري بدفعات صغيرة في الحلقة الدوريّة، تحت قفل الإدراج، فلا يقفل
# القاعدة طويلًا ولا يُبطئ الإقلاع. يتوقّف من نفسه حين لا يبقى شيء.
_BACKFILL_BATCH = 2000
# 🔴 4.20.0 (٢٠٢٦-٠٩-٢٥، ختم المالك «Nq صلح كل امور»): «يتوقّف من نفسه» لم يكن
#    يتوقّف. قراراتٌ `APPROVED` في حمولتها كلمة `"rejection"` بلا سبب (مقيس:
#    `json_extract(…, '$.rejection')` نفسه NULL من الرقم 5,786,921) — يطابقها
#    الشرط، ويكتب فيها التحديثُ NULL فوق NULL، ويعدّها `rowcount` «مُرحَّلة».
#    فلا يصير `moved` صفرًا أبدًا: ألفا صفٍّ تُعاد كتابتها كلّ ثلاثين ثانية بلا
#    نهاية، وقد التقطها تصويرُ العمليّة الباردة 17:42 جاريةً. الشرطُ صار يطلب
#    سببًا موجودًا فعلًا، فينتهي الترحيل حين ينتهي ما يُرحَّل.
_BACKFILL_SQL = (
    "UPDATE decisions SET rejection_reason = "
    "json_extract(payload_json, '$.rejection.reason') "
    "WHERE id IN (SELECT id FROM decisions "
    "             WHERE rejection_reason IS NULL "
    "               AND payload_json LIKE '%\"rejection\"%' "
    "               AND json_extract(payload_json, '$.rejection.reason') IS NOT NULL "
    "             LIMIT ?)")


def insert_many(atom, rows: list[dict[str, Any]]) -> int:
    params = [tuple(row.get(name) for name in _COLUMNS) for row in rows]
    with atom._conn_lock:
        t_sql = time.perf_counter()
        for attempt in range(_LOCK_RETRY + 1):
            try:
                connection = atom._connection()
                cursor = connection.executemany(_INSERT_SQL, params)
                connection.commit()
                atom._span_add("sqlite دفعة", time.perf_counter() - t_sql)
                written = cursor.rowcount
                return len(params) if written < 0 else written
            except sqlite3.OperationalError as exc:
                if attempt < _LOCK_RETRY and "locked" in str(exc).lower():
                    time.sleep(_LOCK_RETRY_SLEEP_S)
                    continue
                if "locked" in str(exc).lower():
                    raise
                atom._close_connection()
                atom._store_ready = False
                raise
            except sqlite3.Error:
                atom._close_connection()
                atom._store_ready = False
                raise
        return 0


def backfill_once(atom) -> int:
    """دفعة ترحيل واحدة لسبب الرفض — تحت قفل الإدراج، وبلا حذف."""
    with atom._conn_lock:
        try:
            connection = atom._connection()
            cursor = connection.execute(_BACKFILL_SQL, (_BACKFILL_BATCH,))
            moved = cursor.rowcount or 0
            connection.commit()
            return moved
        except sqlite3.Error as exc:
            # الترحيل رفاهية لا ضرورة: يُسجَّل ولا يُسقط المخزن.
            atom._last_error = "BACKFILL: %s" % exc
            return 0


def persistent_connection(atom) -> sqlite3.Connection:
    """الاتصال المعمَّر — يُفتح مرّة ويبقى، تحت قفل.

    مقيس ٢٠٢٦-٠٩-٠٩ على نسخة من القاعدة الحيّة (٩٥٤ م.ب، ٣٠٠ إدراجًا):
    اتصال جديد لكل صفّ **٣٣٫٥٣ ms** · اتصال معمَّر **٤٫٤٩ ms** — الفارق
    **×٧٫٥**، أي **١٢٧٫٧ ms من العمل تُهدَر كل ثانية** بمعدّل الإدراج
    المقيس (٤٫٤ صفّ/ث). الكلفة ليست الاستعلام بل دورة نظام الملفات
    كاملة: إنشاء `-wal` و`-shm`، ثمّ نقطة تفتيش ومحوهما عند كل إغلاق.
    (دلَّ على ذلك غيابُ `-wal`/`-shm` بجانب القاعدة الحيّة — أثرُ إغلاقٍ
    بعد كل صفّ.) والـWAL يستقرّ عند ~٤ م.ب بنقطة التفتيش التلقائية.
    """
    if atom._conn is None:
        atom._conn = atom._connect()
    return atom._conn


def close_connection(atom) -> None:
    connection, atom._conn = atom._conn, None
    if connection is not None:
        try:
            connection.close()
        except sqlite3.Error:
            pass


def open_connection(atom) -> sqlite3.Connection:
    # `check_same_thread=False`: الإدراج يجري في `asyncio.to_thread`، وخيطه
    # ليس ثابتًا. الحماية بالقفل `_conn_lock` لا بانتماء الخيط.
    connection = sqlite3.connect(atom._db_path, timeout=_DB_TIMEOUT_S,
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


def ensure_store_locked(atom) -> bool:
    try:
        Path(atom._db_path).parent.mkdir(parents=True, exist_ok=True)
        # المعمَّر يُغلق أوّلًا: الهجرة (`ALTER TABLE`) تحتاج القاعدة حرّة،
        # وإعادة البناء تبدأ من اتصال نظيف.
        atom._close_connection()
        connection = atom._connect()
        try:
            connection.execute(_SCHEMA)
            existing_columns = {row[1] for row in connection.execute("PRAGMA table_info(decisions)").fetchall()}
            for column, column_type in _MIGRATION_COLUMNS.items():
                if column not in existing_columns:
                    connection.execute("ALTER TABLE decisions ADD COLUMN %s %s"
                                       % (column, column_type))
            connection.execute("UPDATE decisions SET stage=? WHERE stage='SENT'", (STAGE_DECISION_FINALIZED,))
            duplicate_rows = connection.execute(
                "SELECT COALESCE(SUM(c-1),0) FROM (SELECT COUNT(*) c FROM decisions WHERE request_id IS NOT NULL GROUP BY stage,account_id,request_id HAVING c>1)"
            ).fetchone()[0]
            connection.execute(
                "DELETE FROM decisions WHERE request_id IS NOT NULL AND id NOT IN (SELECT MIN(id) FROM decisions WHERE request_id IS NOT NULL GROUP BY stage,account_id,request_id)"
            )
            atom.duplicate_count += int(duplicate_rows or 0)
            for statement in _INDEXES:
                connection.execute(statement)
            connection.commit()
        finally:
            connection.close()
        atom._last_error = ""
        return True
    except (sqlite3.Error, OSError) as exc:
        atom._last_error = str(exc)
        return False


def insert(atom, row: dict[str, Any], queued_at: float | None = None) -> bool:
    params = tuple(row.get(name) for name in _COLUMNS)
    if queued_at is not None:
        atom._span_add("قفزة الخيط", time.perf_counter() - queued_at)
    # ثلاثة أرقام تفصل ثلاثة متّهمين لا يُفرَّق بينها من الخارج: قفزة
    # الخيط (طابور المنفّذ) · انتظار قفل الاتصال (إنفاذ السقف يحتجزه) ·
    # وعمل sqlite نفسه. الفارق بين «إدراج» في `_store` و«sqlite» هنا هو
    # الانتظار، لا العمل.
    t_thread = time.perf_counter()
    # ⚠️ **لا انتظار مفتوح على قفلٍ يملكه غيري.** صار القفل قفلَ الملفّ
    # (٢٠٢٦-٠٩-١٨) ليمنع `database is locked` بين الذرّات — وهو صحيح ويبقى.
    # لكنّه جعل ٧٠٧ ينتظر ٧١٤/٧١٦/٧١٧ وهي تكنس القاعدة، فبلغ المعالج ١١٫٥
    # ثانية وصرخت النواة `handler timeout subscriber=707` ثماني مرّات اليوم.
    # العلاج ليس رفع القفل — بل ألّا يُنتظَر هنا: إن كان مشغولًا يُرفع
    # `_LockBusy` ويُودَع الصفّ في الدفعة، والدفعة تنتظر في مهمّةٍ خلفيّة
    # حيث الانتظار لا يكلّف أحدًا. لا قرار يُفقد، وإنّما يصل بعد جزءٍ من ثانية.
    if not atom._conn_lock.acquire(timeout=_HANDLER_LOCK_WAIT_S):
        atom._span_add("قفلٌ مشغول — أُجِّل", time.perf_counter() - t_thread)
        raise _LockBusy
    try:
        t_sql = time.perf_counter()
        atom._span_add("انتظار القفل", t_sql - t_thread)
        for attempt in range(_LOCK_RETRY + 1):
            try:
                connection = atom._connection()
                cursor = connection.execute(_INSERT_SQL, params)
                connection.commit()
                atom._span_add("sqlite", time.perf_counter() - t_sql)
                return cursor.rowcount > 0
            except sqlite3.OperationalError as exc:
                # القفل ليس عطبًا: القاعدة سليمة وكاتبٌ آخر يمسكها. تُعاد
                # المحاولة ولا يُطرح الاتصال — وإلّا أعدنا بناء المخزن
                # وأسقطنا القرار لسبب عابر.
                if attempt < _LOCK_RETRY and "locked" in str(exc).lower():
                    time.sleep(_LOCK_RETRY_SLEEP_S)
                    continue
                if "locked" in str(exc).lower():
                    raise
                atom._close_connection()
                atom._store_ready = False
                raise
            except sqlite3.Error:
                # القاعدة مشكوك فيها: يُطرح الاتصال ويُعاد بناء المخزن عند
                # الحدث التالي، بدل بقاء اتصال معطوب معمَّرًا إلى الأبد.
                atom._close_connection()
                atom._store_ready = False
                raise
        return False
    finally:
        atom._conn_lock.release()
