"""٨٠٠ — النسخة المتّسقة وفحصها، ومجلّدات التدريج وما يُنحّى منها.

٢٠٢٦-١٠-٠٢ (ختم المالك «صلح كامل nq»): وحدةٌ شقيقة في مجلّد الذرّة (حدّ الأربع مئة
سطر فعليّ، المادة ٩ ملف ٤)، كما فعلت ٧٠٧ و٤٦٥. لا تلمس ناقلًا ولا حالة ذرّة: دوالّ
ملفّاتٍ وقواعد صِرفة، يناديها `atom.py` داخل خيط النسخ.

لماذا لم تنجح نسخةٌ منذ ٢٠٢٦-٠٩-١٨ 13:59 UTC — مقيسًا لا مخمَّنًا:
  ١) بعد `backup()` كان يُقرأ عددُ صفحات **الأصل الحيّ الآن** ويُقارن بالنسخة. وقراءةٌ
     فقط للمخزن الحيّ كلّ ثلاثين ثانية (٢٠٢٦-١٠-٠٢ 20:34–20:37): `archive.db` +448
     صفحة، `decisions.db` +94، `tilt_rules.db` +26، `structure.db` و`liquidity.db` +11
     — والنسخة تستغرق دقائق. فتُرمى كلّها «partial copy». وأُعيد إنتاجه على نسخةٍ
     مؤقّتة من خمس قواعد صغيرة حقيقيّة وكاتبٍ حيّ: القديم سقط ٣/٣ بـ«partial copy»،
     والجديد نجح.
  ٢) والتشغيلات التي لم تبلغ ذلك قتلها إقلاعٌ وهي تنسخ: ٠٩-٢٥ (10:32 · 10:57 · 17:36)
     تركت 48.6 ج.ب في `%TEMP%` (`0.db`…`7.db`، و`7.db` هو `archive.db` الحيّ)، و٠٩-٢٩
     16:50، و١٠-٠٢ 15:11 (1.18 ج.ب في 6.5 د قبل إقلاع 15:18).
"""
from __future__ import annotations

import os
import sqlite3
import time
from pathlib import Path
from typing import Any

# ملفّات السجلّ المرافقة لا تُنسخ خامًا. نسخةُ واجهة النسخ لقطةٌ متّسقة تضمّ ما في سجلّ
# WAL لحظتَها؛ و`-wal` خامًا من لحظةٍ أخرى بجوارها تُعاد إطاراتُه فوقها عند أوّل فتح.
# مقيس: `analysis.db-wal` ‏1,907 م.ب كان يدخل كلّ نسخةٍ بجوار نسخته المتّسقة.
_JOURNAL_SUFFIXES = ("-wal", "-shm", "-journal")
# ما دون هذا الحجم يُفحص `integrity_check` كاملًا، وما فوقه `quick_check` (يقرأ كلّ
# صفحة ولا يطابق الفهارس بمحتواها). العيار في المانيفست (`full_check_max_bytes`).
_DEFAULT_FULL_CHECK_MAX_BYTES = 268_435_456
_RUN_PREFIX = "run-"
_INCOMPLETE_PREFIX = "incomplete-"


def _stamp(moment: float) -> str:
    """طابعٌ مقروء لاسم المجلّد — من زمنٍ ممرَّر (الساعة الرسميّة أو زمن الملفّ)."""
    try:
        return time.strftime("%Y%m%dT%H%M%SZ", time.gmtime(float(moment)))
    except (OverflowError, OSError, ValueError):
        return "%d" % int(moment)


def _online_copy(source: Path, target: Path) -> tuple[int, int]:
    """نسخةٌ متّسقة لقاعدةٍ حيّة بواجهة النسخ — (عدد الصفحات، حجم الصفحة).

    `backup()` بخطوةٍ واحدة (`pages=-1`) ينسخ تحت معاملة قراءة واحدة، فالنسخة لقطةٌ
    للحظةٍ واحدة ولو كتب غيرُنا أثناءها. ولا يُقرأ الأصل بعدها: الحكم فحصُ النسخة
    نفسها (`_verify_copy`) لا مقارنتُها بأصلٍ تحرّك.
    """
    source_db = sqlite3.connect(source.as_uri() + "?mode=ro", uri=True, timeout=5)
    target_db = sqlite3.connect(str(target))
    try:
        source_db.backup(target_db)
        pages = int(target_db.execute("PRAGMA page_count").fetchone()[0])
        page_size = int(target_db.execute("PRAGMA page_size").fetchone()[0])
    finally:
        target_db.close()
        source_db.close()
    return pages, page_size


def _verify_copy(path: Path, full_max_bytes: int) -> tuple[str, str]:
    """يفتح النسخة المُدرَّجة ويفحصها — (نوع الفحص، الحكم). «ok» وحدها نجاح.

    كان التحقّق عدَّ أعضاء الأرشيف بلا فتح قاعدةٍ واحدة. والنسخة تُفتح هنا قراءةً
    وكتابة لأنّها نسختنا لا الأصل: رأسُها WAL (منسوخٌ من الأصل)، والفتح للقراءة وحدها
    يترك `-wal` و`-shm` بجوارها (مقيس)، والفتح العاديّ يزيلهما عند الإغلاق.
    """
    mode = "integrity_check" if path.stat().st_size <= full_max_bytes else "quick_check"
    connection = sqlite3.connect(str(path), timeout=5)
    try:
        rows = connection.execute("PRAGMA %s" % mode).fetchall()
    finally:
        connection.close()
    verdict = "; ".join(str(row[0]) for row in rows[:5]) or "no result"
    return mode, verdict


def _tree_bytes(folder: Path) -> int:
    total = 0
    for root, _dirs, files in os.walk(folder):
        for name in files:
            try:
                total += (Path(root) / name).stat().st_size
            except OSError:
                continue
    return total


def _set_aside(folder: Path, label: str) -> Path | None:
    """يُنحّي مخرَج تشغيلةٍ لم تكتمل إلى `incomplete-<الزمن>` — نقلٌ لا حذف.

    الحذف بيد المالك وحده. ما نُحّي يُعدّ ويُنشر حجمُه في اللقطة والصحّة، فلا يتراكم
    صامتًا كما تراكمت 48.6 ج.ب في `%TEMP%`.
    """
    if not folder.exists():
        return None
    target = folder.parent / (_INCOMPLETE_PREFIX + label)
    serial = 1
    while target.exists():
        serial += 1
        target = folder.parent / ("%s%s-%d" % (_INCOMPLETE_PREFIX, label, serial))
    try:
        folder.rename(target)
    except OSError:
        return None
    return target


def set_aside_orphans(backup_dir: Path, staging: Path) -> tuple[int, int, list[str]]:
    """بقايا التشغيلات المقتولة عند الإقلاع — (عدد، بايت، أسماء التشغيلات المقطوعة).

    مجلّد تشغيلةٍ مقتولة (`run-*`) يصير `incomplete-*`، ويتيمُ المسار القديم
    (`.backup.*.tar.gz.tmp` في `backup_dir`) يُنقل إلى `incomplete-legacy-<زمنه>`.
    """
    moved, size, interrupted = 0, 0, []
    for leftover in (sorted(backup_dir.glob(".backup.*.tar.gz.tmp"))
                     if backup_dir.is_dir() else []):
        try:
            stat = leftover.stat()
            holder = staging / ("%slegacy-%s" % (_INCOMPLETE_PREFIX, _stamp(stat.st_mtime)))
            holder.mkdir(parents=True, exist_ok=True)
            os.replace(leftover, holder / leftover.name)
        except OSError:
            continue
        moved += 1
        size += stat.st_size
    for run in (sorted(staging.glob(_RUN_PREFIX + "*")) if staging.is_dir() else []):
        run_bytes = _tree_bytes(run)
        target = _set_aside(run, run.name[len(_RUN_PREFIX):])
        if target is not None:
            moved += 1
            size += run_bytes
            interrupted.append(target.name)
    return moved, size, interrupted


def count_incomplete(staging: Path) -> dict[str, Any]:
    """كم مجلّدًا نُحّي وكم بايتًا — خبرٌ للمالك قبل أن يحذف بيده."""
    dirs, size = 0, 0
    try:
        for folder in staging.glob(_INCOMPLETE_PREFIX + "*"):
            if folder.is_dir():
                dirs += 1
                size += _tree_bytes(folder)
    except OSError:
        pass
    return {"dirs": dirs, "bytes": size, "folder": str(staging)}
