from __future__ import annotations

import os
import sqlite3
import time

# ٢٠٢٦-٠٩-٢٣ (v4.4.2) — طبقةُ SQLite لكاتب الجسر، نُقلت **حرفيًّا** من
# `atom.py` ليعود تحت حدّ ٤٠٠ سطرٍ فعليّ (م9/ملف4) — بلا تغيير سلوك:
# مرسى القاعدة والاتّصال، والمخطّط، والمؤشّر الدائم، وكتابة الأمر بإعادة
# القفل العابر، وإلغاء المعلّق عند الإيقاف الطارئ، ونبضة جدول العرض.
# نصوص SQL والأرقام والرسائل ومسارات الاستثناء كما كانت حرفًا بحرف.
# ما كان تابعًا للذرّة (`self`) صار دالّةً تأخذ الذرّة أوّلَ معامل (`atom`)،
# ويبقى في `atom.py` تفويضٌ بالاسم القديم نفسه، فالنداء من الذرّة لم يتغيّر.

_CURSOR_SCHEMA = ("CREATE TABLE IF NOT EXISTS cursor ("
                  " id INTEGER PRIMARY KEY CHECK (id = 1),"
                  " done_at REAL NOT NULL, last_id INTEGER NOT NULL)")
_BUSY_TIMEOUT_MS = 3000
_CONNECT_TIMEOUT_S = 5.0
# إعادة المحاولة عند قفلٍ عابر. `busy_timeout` ينتظر داخل SQLite، وبعده
# كان الأمر يموت نهائيًّا: قرارٌ عبر كلّ الحرّاس يسقط في المتر الأخير على
# ثلاث ثوانٍ من تزاحمٍ لحظيّ. ثلاث محاولات لا أكثر — والتأخّر في الكتابة
# يردّه الوسيط بانحراف السعر، أمّا الضياع فلا يردّه أحد.
_WRITE_ATTEMPTS = 3
_WRITE_RETRY_BACKOFF_S = 0.2  # ثمّ 0.4 — محاذاةً لـ575 في قسم 550-599

_SCHEMA = """CREATE TABLE IF NOT EXISTS commands (
 id INTEGER PRIMARY KEY AUTOINCREMENT, request_id TEXT NOT NULL,
 action TEXT NOT NULL, symbol TEXT NOT NULL, side TEXT, volume REAL,
 price REAL, stop_loss REAL, take_profit REAL, ticket INTEGER,
 trail_dist REAL, trail_step REAL, params_json TEXT,
 magic INTEGER NOT NULL DEFAULT 0, account_id TEXT NOT NULL DEFAULT '', project_build_id TEXT,
 status TEXT NOT NULL DEFAULT 'PENDING', result TEXT,
 created_at REAL NOT NULL, taken_at REAL, done_at REAL)"""
_INDEX = "CREATE INDEX IF NOT EXISTS idx_cmd_status ON commands(status, id)"
_DISPLAY_SCHEMA = """CREATE TABLE IF NOT EXISTS display (
 id INTEGER PRIMARY KEY CHECK (id = 1), daily_pct REAL, wins INTEGER,
 losses INTEGER, trades INTEGER, open_trades INTEGER,
 kill_switch TEXT, updated_at REAL)"""
_DISPLAY_SEED = "INSERT OR IGNORE INTO display (id) VALUES (1)"
_HEARTBEAT_SQL = "UPDATE display SET updated_at = ? WHERE id = 1"
_INSERT_SQL = ("INSERT INTO commands (request_id, action, symbol, side, volume,"
               " price, stop_loss, take_profit, ticket, params_json, magic, account_id, project_build_id, status, created_at)"
               " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'PENDING', ?)")
# ٢٠٢٦-١٠-٠٢ (ختم المالك «صلح كامل nq»): كان الإلغاء على **كلّ** الأفعال، فكان
# كلُّ إيقافٍ طارئ يقتل أوامر الحماية المعلّقة التي كتبها 575 (مقيس في الجسر
# الحيّ: 17 `MODIFY_SL` و1 `CLOSE_PARTIAL` بنتيجة `EMERGENCY_HALT`). وقاعدة 575
# «الإيقاف لا يحجب الخروج». فالإلغاء الآن لأوامر الدخول وحدها (`OPEN`، ومعه
# `PENDING_CREATE` لأنّه دخولٌ معلَّق) — والوقف والإغلاق يبقيان في طريقهما.
_CANCEL_SQL = ("UPDATE commands SET status='CANCELLED', result='EMERGENCY_HALT',"
               " done_at=? WHERE status='PENDING' AND account_id=?"
               " AND action IN ('OPEN','PENDING_CREATE')")


def _resolve_db(configured: str) -> str:
    """مرسى الجسر — من البيئة أوّلًا، ثمّ المانيفست، ومتغيّرات البيئة تُوسَّع.

    ٢٠٢٦-٠٩-٢٣ (ختم NQ): كان المانيفست يحمل المسار المطلق إلى جهاز المالك
    باسمه (`C:/Users/NQ/...`) — أي أنّ اسمَه وجهازَه محفوران في عقد ستّ
    ذرّات. نقلُ المشروع إلى مستخدمٍ آخر كان يُسقطها صامتةً. صار الاحتياطيّ
    `%APPDATA%` ثمّ `MetaQuotes/Terminal/Common/Files` — يُوسَّع هنا فيصحّ
    على أيّ جهاز.

    و`NQ_BRIDGE_DB` يبقى مقدَّمًا (يضبطه `governance/app.py` من مكانٍ واحد)،
    فهذا احتياطيٌّ لا طريقٌ أوّل.
    """
    override = os.path.expandvars(os.environ.get("NQ_BRIDGE_DB", "").strip())
    if override:
        return override
    return os.path.expandvars(configured)


def _connect(path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(path, timeout=_CONNECT_TIMEOUT_S)
    conn.execute(f"PRAGMA busy_timeout={_BUSY_TIMEOUT_MS}")
    # ٢٠٢٦-٠٩-١٩ — **وتصحيحُ ادّعاءٍ لي في الختم `edbab80`.**
    #
    # ادّعيتُ أنّ `PRAGMA journal_mode=WAL` هو سببُ ضياع الأوامر حيًّا.
    # **وهذا خطأ**، كشفه قياسُ قسم ٧٠٠-٧٤٩ وأكّدتُه بيدي:
    #     من WAL    ⟵ WAL : نجح بعد 0.000ث  (لا-عمل · لا يطلب قفلًا)
    #     من DELETE ⟵ WAL : سقط فورًا بعد 0.000ث
    # وقاعدة الجسر الحيّة `journal_mode = wal` أصلًا. فالأمر عليها لا-عمل
    # ولم يكن يسقط قطّ. وسقوطي المقيس (ثلاث محاولات في 0.60ث) كان على
    # قاعدةِ اختبارٍ بنيتُها في نمط `DELETE` — أي في حالة **التحوّل**
    # وحدها، وهي لا تقع على القاعدة الحيّة.
    #
    # فسببُ ضياع الأوامر حيًّا هو **تزاحمُ الكتابة على `INSERT` نفسه**،
    # وعلاجُه الإعادةُ في `_insert_command` لا هذا السطر.
    #
    # ويبقى هذا التعديل لأنّه صحيحٌ في ذاته: النمط صفةٌ محفوظة في ترويسة
    # الملفّ، وكتابتُه كلّ اتّصالٍ عملٌ بلا فائدة يفتح خطرَ التحوّل على
    # قاعدةٍ جديدة. يُقرأ (بلا قفل) ولا يُكتب إلّا إن اختلف.
    try:
        mode = conn.execute("PRAGMA journal_mode").fetchone()
        if not mode or str(mode[0]).lower() != "wal":
            conn.execute("PRAGMA journal_mode=WAL")
    except sqlite3.OperationalError:
        # قاعدةٌ مشغولة لحظةَ الفحص — النمط باقٍ كما ضبطه مالك الملفّ
        # (الإكسبرت)، ولا يُسقَط الاتّصال من أجل صفةٍ لم تتغيّر.
        pass
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


def _has_column(conn: sqlite3.Connection, table: str, column: str) -> bool:
    try:
        return any(str(row[1]) == column for row in conn.execute(f"PRAGMA table_info({table})"))
    except sqlite3.Error:
        return False


def _load_durable_cursor(path: str) -> tuple[float, int] | None:
    try:
        conn = _connect(path)
        try:
            conn.execute(_CURSOR_SCHEMA)
            row = conn.execute("SELECT done_at, last_id FROM cursor WHERE id = 1").fetchone()
        finally:
            conn.close()
        return (float(row[0]), int(row[1])) if row is not None else None
    except (sqlite3.Error, TypeError, ValueError, OSError):
        return None


def _save_durable_cursor(path: str, cursor: tuple[float, int]) -> None:
    try:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        conn = _connect(path)
        try:
            conn.execute(_CURSOR_SCHEMA)
            conn.execute("INSERT OR REPLACE INTO cursor (id, done_at, last_id)"
                         " VALUES (1, ?, ?)", (float(cursor[0]), int(cursor[1])))
            conn.commit()
        finally:
            conn.close()
    except (sqlite3.Error, OSError):
        pass  # التخزين لا يسقط النشر — الفشل يعيدنا لسلوك اللقطة فقط


def ensure_schema(atom) -> None:
    # كان `Atom._ensure_schema` — منقولٌ حرفيًّا، و`self` صار `atom`.
    try:
        conn = _connect(atom._db_path)
        try:
            conn.execute(_SCHEMA)
            if not _has_column(conn, "commands", "params_json"):
                conn.execute("ALTER TABLE commands ADD COLUMN params_json TEXT")
            if not _has_column(conn, "commands", "magic"):
                conn.execute("ALTER TABLE commands ADD COLUMN magic INTEGER NOT NULL DEFAULT 0")
            if not _has_column(conn, "commands", "account_id"):
                conn.execute("ALTER TABLE commands ADD COLUMN account_id TEXT NOT NULL DEFAULT ''")
            if not _has_column(conn, "commands", "project_build_id"):
                conn.execute("ALTER TABLE commands ADD COLUMN project_build_id TEXT")
            conn.execute(_INDEX)
            conn.execute(_DISPLAY_SCHEMA)
            conn.execute(_DISPLAY_SEED)
            conn.commit()
        finally:
            conn.close()
    except sqlite3.Error as exc:
        atom.last_write_success = False
        atom.last_write_error = str(exc)


def is_locked(exc: Exception) -> bool:
    """أقفلٌ عابر هو، أم خطأٌ يجب ألّا يُعاد؟

    يُعاد على القفل وحده. و`DUPLICATE_REQUEST_ID` يخرج كـ`IntegrityError`
    فلا يُلتقط هنا أصلًا — وهو حارسٌ يجب أن يبقى قاطعًا: إعادةُ أمرٍ
    مكتوبٍ مرّةً تفتح مركزًا ثانيًا.
    """
    return isinstance(exc, sqlite3.OperationalError) and (
        "locked" in str(exc).lower() or "busy" in str(exc).lower())


def insert_once(atom, row: tuple) -> None:
    # كان `Atom._insert_once` — منقولٌ حرفيًّا، و`self` صار `atom`.
    conn = _connect(atom._db_path)
    try:
        conn.execute("BEGIN IMMEDIATE")
        if conn.execute("SELECT 1 FROM commands WHERE account_id=? AND request_id=?", (row[11], row[0])).fetchone():
            raise sqlite3.IntegrityError("DUPLICATE_REQUEST_ID")
        conn.execute(_INSERT_SQL, row)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally: conn.close()


def insert_command(atom, row: tuple) -> None:
    """يكتب الأمر، ويعيد المحاولة على القفل العابر وحده.

    ٢٠٢٦-٠٩-١٩ (ختم NQ): كان نداءً واحدًا بلا إعادة. فسقط
    `555-9b813eca1a82` (BTCUSD BUY) على `database is locked` بعد أن عبر
    كلّ حرّاس قسم ٥٠٠-٥٩٩، ولم يصل قاعدة الجسر إطلاقًا — لا صفَّ له.
    وكان الأمر السليم الوحيد في ذلك اليوم.

    يعمل داخل خيطٍ (`asyncio.to_thread`) فـ`sleep` هنا لا يحبس الحلقة.
    """
    # النداء عبر الذرّة (`atom._insert_once` و`atom._is_locked`) كما كان
    # `self.…` — فتبقى نقطتا الاستبدال على الذرّة نفسها لا على هذه الوحدة.
    last: Exception | None = None
    for attempt in range(1, _WRITE_ATTEMPTS + 1):
        try:
            atom._insert_once(row)
            if attempt > 1:
                atom.write_retries += 1
            return
        except Exception as exc:
            if not atom._is_locked(exc) or attempt == _WRITE_ATTEMPTS:
                if atom._is_locked(exc):
                    atom.write_lost_to_lock += 1
                raise
            last = exc
            time.sleep(_WRITE_RETRY_BACKOFF_S * attempt)
    if last is not None:
        raise last


def cancel_pending(atom, account_id: str) -> int:
    # كان `Atom._cancel_pending` — منقولٌ حرفيًّا، و`self` صار `atom`.
    conn = _connect(atom._db_path)
    try: cursor = conn.execute(_CANCEL_SQL, (time.time(), account_id)); conn.commit(); return cursor.rowcount
    finally: conn.close()


def write_heartbeat(atom, stamp: float) -> None:
    # كان `Atom._write_heartbeat` — منقولٌ حرفيًّا، و`self` صار `atom`.
    try:
        conn = _connect(atom._db_path)
        try: conn.execute(_DISPLAY_SCHEMA); conn.execute(_DISPLAY_SEED); conn.execute(_HEARTBEAT_SQL, (float(stamp),)); conn.commit()
        finally: conn.close()
        atom.heartbeat_written += 1
        atom._beats_failing = 0
    except sqlite3.Error:
        atom.heartbeat_failed += 1
        atom._beats_failing += 1
