"""Shared, bounded SQLite retention policy for storage atoms."""
from __future__ import annotations

import contextlib
import os
import re
import sqlite3
import sys
import threading
from pathlib import Path
from typing import Any

# ─── قفلٌ على الملفّ لا على الكائن ────────────────────────────────────────────
#
# ⛔ درسٌ دفعته المنصّة مرّتين في يوم ٢٠٢٦-٠٩-١٨.
#
# مخازن ٧٠٠-٧٤٩ تعمل كلّها في **عمليّة واحدة** (`cold_process`)، وأكثر من ذرّة
# تكتب على القاعدة نفسها: ٧١٢ يُدرج في `analysis.db` بينما ٧١٦ يحذف منها
# تكرارات، و٧٠٧ يُدرج في `decisions.db` بينما الإنفاذ يرحّل منها إلى الأرشيف.
#
# وكان لكلّ ذرّةٍ `threading.Lock` **داخل كائنها** — وهو يُسلسل الذرّة مع
# نفسها ولا يعبر إلى جارتها. فما دامت الأعمال الطويلة تجري **داخل معالج
# الحدث** كانت حلقةُ العامل الواحدة تُسلسلها قسرًا، فلا تلتقي كتابتان.
# ولمّا أخرجتُها إلى مهامّ خلفيّة (٢٠٢٦-٠٩-١٨) — وهو إصلاحٌ صحيح في ذاته —
# **سقط التسلسل العرضيّ** فالتقتا:
#
#     ٢١:٢٧  ٧١٦ ينظّف ويحذف ٤٬٥١٥ صفًّا
#     ٢١:٢٨  ٧١٢ معطّل: database is locked
#     ٢١:٣٣  ٧١٢ معطّل: database is locked
#     ٢١:٣٤  ٧١٢ معطّل: database is locked
#     ٢٢:٥٧  ٧٠٧: قرار لم يُخزَّن — سبب=database is locked (٩١ إخفاقًا)
#
# فصار القفل **على مسار الملفّ**: كلّ من يكتب على قاعدةٍ في هذه العمليّة
# يأخذ قفلها هي، أيًّا كانت ذرّته. والمفتاح مسارٌ مُطلقٌ مُوحَّد الحالة كي لا
# يفترق قفلان لملفٍّ واحد بسبب `\\` و`/` أو اختلاف حرف السواقة.
#
# ⚠️ وحدُّه معروف: يُسلسل داخل العمليّة الواحدة فقط. كاتبٌ من عمليّةٍ أخرى
# (أداةٌ خارجيّة، أو قسمٌ في عمليّةٍ ثانية) يبقى خارجه — وحارسه `busy_timeout`.
# ⚠️ **`RLock` لا `Lock` — وقد علّقت الاختبارات حتى عرفتُ لماذا.**
# الذرّة تأخذ قفل الملفّ ثمّ تنادي `enforce_limits`، و`enforce_limits` تأخذ
# **القفل نفسه** — فخيطٌ واحد يطلب قفلًا يملكه: جمودٌ تامّ. والمعاوِد يسمح
# لصاحب القفل بإعادة أخذه ويمنع غيره، وهو المطلوب بالضبط.
_FILE_LOCKS: dict[str, "threading.RLock"] = {}
_REGISTRY_LOCK = threading.Lock()


def file_lock(path: str):
    """قفلُ هذا الملفّ — مشتركٌ بين كلّ من يكتب عليه في هذه العمليّة."""
    key = os.path.normcase(os.path.abspath(str(path)))
    lock = _FILE_LOCKS.get(key)
    if lock is None:
        with _REGISTRY_LOCK:
            lock = _FILE_LOCKS.get(key)
            if lock is None:
                lock = _FILE_LOCKS[key] = threading.RLock()
    return lock


@contextlib.contextmanager
def background_io():
    """قراءةٌ وكتابةٌ بأولويّة الخلفيّة لهذا الخيط ما دام داخل الكتلة (ويندوز).

    ٢٠٢٦-٠٩-٢٥ (ختم المالك «Nq صلح كل امور»): بعد إقلاع 17:36 كانت العمليّة
    الباردة تفحص سلامة أرشيفٍ بسبعة عشر غيغا (714) وتنسخ `var/store` كلّه (800)
    معًا، وطابور القرص 8–17 — فانتظرت كلُّ عمليّة ملفٍّ على حلقة المنصّة:
    43 مهلة دورة على 465 وعشرة تجمّدات أسوؤها 13.9ث، وعيّناتها في `_connect`
    و`getmtime` و`journal.record`. وضعُ الخلفيّة (`THREAD_MODE_BACKGROUND_BEGIN`)
    يضع طلبات هذا الخيط في آخر طابور القرص، فيخدم القرصُ المنصّةَ أوّلًا
    ويُكمل الصيانةَ بما يبقى. لا يُستعمل مع ما يحتجز قفل كتابة (`VACUUM`):
    إبطاؤه يطيل انتظار الكاتب. وعلى غير ويندوز، أو إن رُفض الطلب، لا شيء يتغيّر.
    """
    kernel32 = _kernel32()
    if kernel32 is None:
        yield
        return
    thread = kernel32.GetCurrentThread()
    entered = bool(kernel32.SetThreadPriority(thread, 0x00010000))  # BACKGROUND_BEGIN
    try:
        yield
    finally:
        if entered:
            kernel32.SetThreadPriority(thread, 0x00020000)  # BACKGROUND_END


_KERNEL32: Any = None


def _kernel32():
    """نسخةٌ خاصّة من kernel32 بأنواعٍ صريحة — المقبض عرضُ مؤشّر، لا `int`.

    بالأنواع الافتراضيّة يُقصّ مقبضُ الخيط الزائف (-2) إلى 32 بتًّا على نظام
    64 بتًّا فيفشل الطلب صامتًا — وهكذا فشل أوّل ما كتبتُه، وكشفه الفحص.
    ونسخةٌ خاصّة لا تبدّل أنواع `ctypes.windll.kernel32` على غيرها في العمليّة.
    """
    global _KERNEL32
    if sys.platform != "win32":
        return None
    if _KERNEL32 is None:
        import ctypes
        from ctypes import wintypes
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.GetCurrentThread.restype = wintypes.HANDLE
        kernel32.GetCurrentThread.argtypes = []
        kernel32.SetThreadPriority.restype = wintypes.BOOL
        kernel32.SetThreadPriority.argtypes = [wintypes.HANDLE, ctypes.c_int]
        _KERNEL32 = kernel32
    return _KERNEL32


def run_in_background(function, *args):
    """يُنادى من `asyncio.to_thread`: الدالّة كلّها بأولويّة الخلفيّة."""
    with background_io():
        return function(*args)


_IDENT = re.compile(r"^[A-Za-z0-9_]+$")
_DB_TIMEOUT_S = 5.0
_BUSY_TIMEOUT_MS = 3000
# دفعة الحذف الواحدة. مقيس ٢٠٢٦-٠٩-٠٩ على نسخة من `decisions.db` (٩٥٤ م.ب،
# ٥٧٢٬٦٦٩ صفًّا): ١٬٠٠٠ صفّ = ١٢ ms · ٥٬٠٠٠ = ٦٠ ms · ٢٠٬٠٠٠ = ٢٬١١٨ ms ·
# ١١٤٬٥٣٣ (خُمس الجدول، وهو ما كان يُحذف دفعةً) = **٣٬٥٩٣ ms** قفلًا متّصلًا
# للكاتب داخل معالج حدث. الدفعة الصغيرة مع `commit` بينها تُفرج عن القفل
# فتمرّ الإدراجات، والمجموع الكلّي أسرع لا أبطأ (٢٣ × ٦٠ ms).
_DELETE_BATCH = 5000


def database_bytes(path: str) -> int:
    return sum(Path(path + suffix).stat().st_size
               for suffix in ("", "-wal", "-shm")
               if Path(path + suffix).is_file())


#: ٢٠٢٦-٠٩-٢٥ (ختم المالك «Nq صلح كل امور»): أدنى رقمٍ قد يبقى تحته صفٌّ غير
#: محميّ — لكلّ (ملفّ، جدول) في هذه العمليّة. انظر `_delete_protected`.
_SCAN_FLOOR: dict[str, int] = {}


def _delete_oldest(connection: sqlite3.Connection, table: str, count: int,
                   protect_where: str = "", archived: bool = False,
                   max_batches: int = 0, floor_key: str = "") -> int:
    """إخراج الأقدم على دفعات — لا قفلة واحدة طويلة.

    `protect_where` شرطٌ اختياريّ: ما يطابقه لا يخرج مهما بلغ السقف. وُضع
    لأنّ الإخراج بالأقدميّة وحدها أعمى — مقيس ٢٠٢٦-٠٩-٠٩ أنّ `TARGET_STATE`
    تشكّل ٨٣٪ من `decisions.db`، فطوفانُها يطرد تذاكر التنفيذ النادرة
    (٤ إشعارات وسيط · ٤٩ طلب أمر) وهي التي لا تُعوَّض.

    `archived=True` يعني أنّ قاعدة أرشيف مربوطة باسم ``archive``: الصفوف
    تُنسخ إليها **قبل** إزالتها، في معاملة واحدة لكل دفعة — فإمّا وصلت
    الأرشيف وخرجت، أو بقيت مكانها. لا يسقط صفٌّ بين الاثنين.
    """
    if protect_where:
        return _delete_protected(connection, table, count, protect_where,
                                 archived, max_batches, floor_key)
    keep = ""
    removed = 0
    batches = 0
    while removed < count:
        if max_batches and batches >= max_batches:
            # حدٌّ لطول النداء الواحد: المخزن الذي يحتجز قفل الإدراج أثناء
            # الإنفاذ يجب أن يُفرج عنه سريعًا، والباقي يُكمَل في النداء التالي.
            break
        batches += 1
        take = min(_DELETE_BATCH, count - removed)
        pick = (f"SELECT id FROM {table}{keep} ORDER BY id LIMIT {int(take)}")
        if archived:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                f"INSERT INTO archive.{table} SELECT * FROM main.{table} "
                f"WHERE id IN ({pick})")
        cursor = connection.execute(
            f"DELETE FROM {table} WHERE id IN ({pick})")
        deleted = cursor.rowcount or 0
        connection.commit()
        if deleted <= 0:
            break
        removed += deleted
    return removed


def _delete_protected(connection: sqlite3.Connection, table: str, count: int,
                      protect_where: str, archived: bool, max_batches: int,
                      floor_key: str) -> int:
    """إخراجُ الأقدم غير المحميّ — من حيث انتهى الإخراج السابق، لا من أوّل الجدول.

    ٢٠٢٦-٠٩-٢٥ (ختم المالك «Nq صلح كل امور»): `SELECT id … WHERE NOT (<الحماية>)
    ORDER BY id LIMIT n` يقرأ الجدول من أوّله حتّى يجد غيرَ المحميّ. ولمّا صار
    المحميّ وحده فوق السقف — مقيس في `decisions.db`: 3.64 GiB بلا صفحاتٍ حرّة،
    وعيّناتٌ في ثماني نقاطٍ على ١٦ يومًا كلّها `DISPATCH` و`APPROVED` و`ORDER_*` —
    صار غيرُ المحميّ كلُّه في ذيل الجدول، فكلُّ إنفاذٍ (كلّ ثلاثين ثانية) يقرأ
    الجدول كلّه مرّتين أو ثلاثًا ليصل إليه. العمليّة الباردة كانت تقرأ حتّى
    790 م.ب/ث والقرص مشبَعًا (طابور 2–10)، فتعطّلت قواعد المنصّة معه.

    والإخراج بترتيب الرقم، والرقم يتصاعد (`AUTOINCREMENT`)، فما تحت آخرِ رقمٍ
    أُخرج لم يبقَ فيه غيرُ محميّ. يُحفظ ذلك الرقم في `_SCAN_FLOOR` ويبدأ البحث
    بعده؛ وأوّلُ نداءٍ في العمليّة يأخذه من الأرشيف (`MAX(id)` بالمفتاح، بلا
    مسح) إن كان مربوطًا، وإلّا من الصفر مرّةً واحدة. والمعاملة والترتيب كما
    كانا: النسخ والإزالة معًا لكلّ دفعة، ولا يسقط صفٌّ بينهما.
    """
    floor = _SCAN_FLOOR.get(floor_key, -1) if floor_key else -1
    if floor < 0:
        floor = 0
        if archived:
            top = connection.execute(f"SELECT MAX(id) FROM archive.{table}").fetchone()
            floor = int(top[0] or 0) if top else 0
    removed = 0
    batches = 0
    while removed < count:
        if max_batches and batches >= max_batches:
            break
        batches += 1
        take = min(_DELETE_BATCH, count - removed)
        if archived:
            connection.execute("BEGIN IMMEDIATE")
        ids = [int(row[0]) for row in connection.execute(
            f"SELECT id FROM {table} WHERE id > ? AND NOT ({protect_where}) "
            f"ORDER BY id LIMIT {int(take)}", (floor,))]
        if not ids:
            connection.commit()
            break
        marks = ",".join("?" * len(ids))
        if archived:
            connection.execute(
                f"INSERT INTO archive.{table} SELECT * FROM main.{table} "
                f"WHERE id IN ({marks})", ids)
        cursor = connection.execute(
            f"DELETE FROM {table} WHERE id IN ({marks})", ids)
        deleted = cursor.rowcount or 0
        connection.commit()
        if deleted <= 0:
            break
        floor = ids[-1]
        if floor_key:
            _SCAN_FLOOR[floor_key] = floor
        removed += deleted
    return removed


def _attach_archive(connection: sqlite3.Connection, table: str,
                    archive_db_path: str) -> bool:
    """يربط قاعدة الأرشيف ويضمن وجود الجدول فيها بنفس المخطط."""
    Path(archive_db_path).parent.mkdir(parents=True, exist_ok=True)
    connection.execute("ATTACH DATABASE ? AS archive", (archive_db_path,))
    connection.execute(
        f"CREATE TABLE IF NOT EXISTS archive.{table} AS "
        f"SELECT * FROM main.{table} WHERE 0")
    connection.commit()
    return True


def enforce_limits(path: str, table: str, *, max_rows: int = 0,
                   max_db_bytes: int = 0, shrink: bool = False,
                   protect_where: str = "",
                   archive_db_path: str = "",
                   max_batches: int = 0) -> dict[str, Any]:
    """إنفاذ سقوف المخزن.

    `archive_db_path`: بدل أن يُتلف السقفُ الأقدمَ، يُرحَّل إلى قاعدة أرشيف
    ثم يُزال من المخزن — بأمر المالك ٢٠٢٦-٠٩-١٠، وعلى قاعدته: لا حذف، أرشفة.
    المقيس قبله على `decisions.db`: `stored=1,573,939` والباقي ٥٢٨٬٠٧٥ ⇒ نحو
    **مليون صفّ أُتلف**، وأقدم قرار عمره يومٌ واحد بينما جاراته تحفظ ٤٫٩.
    والنقل والإزالة في معاملة واحدة لكل دفعة، فلا يسقط صفّ بينهما. وتعذُّرُ
    ربط الأرشيف **يوقف الإنفاذ** ولا يحذف: `archive_error` في النتيجة،
    والمخزن يتجاوز سقفه معلنًا بدل أن يُتلف بصمت.

    `shrink=False` (المسار الساخن — كل flush): حذف الأقدم + checkpoint سلبي
    فقط. الحذف وحده يوقف نموّ الملف (الصفحات المحرَّرة يعيد SQLite استعمالها)،
    أمّا `VACUUM` وسط سيل الكتابة فكان يقفل الكاتب دقائق («database is
    locked») ويخسر السباق، و`TRUNCATE` checkpoint يفشل ما دام للوحة قارئ
    دائم — فانفلت الـWAL بالجيغابايتات (مقيس 2026-08-19: ~9GB/ساعة).
    `shrink=True` (الدورة اليومية الهادئة فقط): يضيف قصّ الـWAL وVACUUM
    لإرجاع المساحة فعليًّا للقرص.
    """
    if not _IDENT.fullmatch(table):
        raise ValueError("INVALID_STORAGE_TABLE")
    if not Path(path).is_file():
        return {"breached": False, "pruned": 0, "rows": 0, "db_bytes": 0}
    # الإنفاذ يكتب — حذفًا وترحيلًا وربّما `VACUUM` — فيأخذ قفل الملفّ لا قفل
    # ذرّته. وهو الذي كان ينقص: كاتبان من ذرّتين على قاعدةٍ واحدة.
    with file_lock(path):
        return _enforce_locked(path, table, max_rows=max_rows,
                               max_db_bytes=max_db_bytes, shrink=shrink,
                               protect_where=protect_where,
                               archive_db_path=archive_db_path,
                               max_batches=max_batches)


def _enforce_locked(path: str, table: str, *, max_rows: int, max_db_bytes: int,
                    shrink: bool, protect_where: str, archive_db_path: str,
                    max_batches: int) -> dict[str, Any]:
    connection = sqlite3.connect(path, timeout=_DB_TIMEOUT_S)
    pruned = 0
    breached = False
    archived = False           # قبل ``try``: ``finally`` يقرؤه مهما حدث
    floor_key = os.path.normcase(os.path.abspath(str(path))) + "|" + table
    try:
        # داخل ``try`` عمدًا: ``sqlite3.connect`` لا يلمس الملف، وأوّل PRAGMA
        # هي التي تقرأ الترويسة. على قاعدة تالفة كانت ترمي هنا — خارج الحماية
        # — فيبقى الاتصال مفتوحًا بلا إغلاق. مقيس ٢٠٢٦-٠٩-٠٩: مقبض مسرَّب مع
        # كل نداء، والملف يصير غير قابل للإزاحة على ويندوز؛ وذلك بالضبط ما
        # يحتاجه إصلاح قاعدة تالفة.
        connection.execute("PRAGMA busy_timeout=%d" % _BUSY_TIMEOUT_MS)
        # حدّ حجم ملف الـWAL عند اكتمال أي checkpoint — بلا رقم جديد: نفس سقف
        # المخزن المصرَّح به هو الحدّ.
        if max_db_bytes > 0:
            connection.execute("PRAGMA journal_size_limit=%d" % max_db_bytes)
        rows = int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
        archive_error = ""
        if archive_db_path:
            try:
                archived = _attach_archive(connection, table, archive_db_path)
            except (sqlite3.Error, OSError) as exc:
                archive_error = str(exc)
        if archive_db_path and not archived:
            # الأرشيف مطلوب ولم يُربط: يُعلَن ولا يُتلف شيء.
            return {"breached": True, "pruned": 0, "rows": rows,
                    "db_bytes": 0, "max_rows": max_rows,
                    "max_db_bytes": max_db_bytes, "archived": 0,
                    "archive_error": archive_error or "ARCHIVE_UNAVAILABLE"}
        if max_rows > 0 and rows > max_rows:
            deleted = _delete_oldest(connection, table, rows - max_rows,
                                     protect_where, archived, max_batches, floor_key)
            pruned += deleted
            rows -= deleted
            breached = True
        def _used_bytes() -> int:
            # بلا VACUUM حجم الملف لا ينكمش أبدًا — القياس الصادق للمسار الساخن
            # هو المحتوى الفعلي: (الصفحات الكلية − الحرّة) × حجم الصفحة، وإلا
            # ظلّت الحلقة تحذف حتى تفرغ الجدول وحجم الملف ثابت.
            page_size = int(connection.execute("PRAGMA page_size").fetchone()[0])
            page_count = int(connection.execute("PRAGMA page_count").fetchone()[0])
            freelist = int(connection.execute("PRAGMA freelist_count").fetchone()[0])
            return max(0, page_count - freelist) * page_size

        size = database_bytes(path) if shrink else _used_bytes()
        rounds = 0
        while max_db_bytes > 0 and size > max_db_bytes and rows > 0 and rounds < 20:
            deleted = _delete_oldest(connection, table, max(1, rows // 5),
                                     protect_where, archived, max_batches, floor_key)
            if deleted <= 0:
                break
            pruned += deleted
            rows -= deleted
            breached = True
            if shrink:
                connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                connection.execute("VACUUM")
                size = database_bytes(path)
            else:
                connection.execute("PRAGMA wal_checkpoint(PASSIVE)")
                size = _used_bytes()
            rounds += 1
        if shrink and breached:
            connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        return {"breached": breached or (max_db_bytes > 0 and size > max_db_bytes),
                "pruned": pruned, "rows": rows, "db_bytes": size,
                "max_rows": max_rows, "max_db_bytes": max_db_bytes,
                # `pruned` يعني «خرج من المخزن»؛ و`archived` يقول إلى أين ذهب.
                "archived": pruned if archived else 0}
    finally:
        if archived:
            try:
                connection.execute("DETACH DATABASE archive")
            except sqlite3.Error:
                pass
        connection.close()
