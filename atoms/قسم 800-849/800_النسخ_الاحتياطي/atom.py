from __future__ import annotations

import asyncio
import os
from pathlib import Path
import sqlite3
import tarfile
from typing import Any

from catchup import decide
from core.contracts.atom import AtomBase, AtomContext, HealthState, HealthStatus
from storage_policy import run_in_background
# ٢٠٢٦-١٠-٠٢ (ختم المالك «صلح كامل nq»): النسخة المتّسقة وفحصها والتدريج في وحدةٍ
# شقيقة (حدّ الأربع مئة سطر) — والأسماء تُستورد هنا فتبقى سطحَ هذه الوحدة.
from backup_copy import _DEFAULT_FULL_CHECK_MAX_BYTES, _JOURNAL_SUFFIXES, _RUN_PREFIX
from backup_copy import _online_copy, _set_aside, _stamp, _verify_copy
from backup_copy import count_incomplete, set_aside_orphans
from shared.owner_windows import MAINTENANCE_RERUN_SLACK_S, MaintenanceGate

ATOM_VERSION = "2.9.0"

_SECONDS_PER_DAY = 86400.0
#: ٢٠٢٦-١٠-١٢: النسخة الفائتة تُؤخذ بعد الإقلاع بهذه المهلة (يستقرّ الإقلاع والعمليّة الباردة أوّلًا).
BOOT_CATCHUP_DELAY_S = 600.0
# صفحةُ sqlite المقيسة على كلّ قواعد المنصّة ٢٠٢٦-٠٩-١٩: ٤٠٩٦ بايت. تُستعمل
# لتقدير حجم النسخة من عدد الصفحات بلا لمس القرص مرّةً ثانية.
_PAGE_BYTES_HINT = 4096

EVENT_DAY = "SYS_DAY"
EVENT_PULSE = "SYS_SECOND"
EVENT_DONE = "tools.backup.completed"
EVENT_FAILED = "tools.backup.failed"

REASON_NOT_STARTED = "NOT_STARTED"
REASON_NEVER_RAN = "NO_BACKUP_YET"


# ٢٠٢٦-١٠-٠٢ (ختم المالك «صلح كامل nq»): أُزيلت `_page_count` ومقارنتُها. مساواةُ
# عدد صفحات النسخة بعدد صفحات **الأصل الحيّ بعد النسخ** كانت «فحصًا قاطعًا» على قاعدةٍ
# ساكنة، وعلى مخزنٍ يُكتب كلّ ثوانٍ رفضت كلّ نسخةٍ منذ ٠٩-١٨. الحكم الآن فحصُ النسخة
# نفسها (`backup_copy._verify_copy`).


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
    code_root = _code_root()
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


def _code_root() -> Path | None:
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "shared" / "runtime_paths.py").is_file():
            return parent
    return None


def _anchor(source: str) -> str:
    """مصدرٌ نسبيّ لا يُحلّ نسبةً إلى مجلد التشغيل — أبدًا.

    مسارات ``var/`` يلصقها مالك المسارات بجذر الـruntime. وما بقي نسبيًّا
    (``config``) كان يُحلّ نسبةً إلى مجلد العمل: نجح لأنّ هذه العمليّة تصادف
    أن تُشغَّل من جذر المستودع، وتكسِرُه أيُّ ``chdir`` — وقد كسر المُشغِّلُ
    الموحَّد مساراتٍ نسبيّةً بهذا الوجه من قبل. فيُرسى على جذر الكود، وهو
    الجذر نفسه الذي تُقرأ منه ``config`` اليوم: ثمانية ملفّات، لم يتغيّر منها
    شيء (مقيس ٢٠٢٦-٠٩-١٩).
    """
    path = Path(source)
    if path.is_absolute():
        return str(path)
    root = _code_root()
    return str((root / path).resolve()) if root is not None else source


class Atom(AtomBase):
    def __init__(self) -> None:
        self._context: AtomContext | None = None
        self._initialized = False
        self._running = False
        self._backup_dir = ""
        self._source_dirs: list[str] = []
        self._keep_last_n = 1
        self._interval_days = 1
        self._min_bytes = 0
        self._last_success: float | None = None
        self._last_source_bytes = 0
        self._last_error = ""
        self._catchup_done = False
        self._catchup_verdict: dict[str, Any] = {}
        self.backup_count = 0
        self._backup_task: asyncio.Task | None = None
        # كم نداءً وجد نسخةً جاريةً فتخطّى. نموُّه يعني أنّ النسخة أبطأ من
        # وتيرة النداء — خبرٌ يُقرأ، لا صمتٌ يُخمَّن.
        self.backup_skipped = 0
        # يتامى النسخ المقتولة: كم مُسح وكم بايتًا حُرّر — يُنشران
        # فيُقرأ النزيف بدل أن يتراكم صامتًا.
        self.orphans_cleared = 0
        self.orphan_bytes_cleared = 0
        self._exclude: list[str] = []
        # كم ملفًّا استُثني في آخر نسخة — يُنشر فلا يكون الاستثناء صامتًا.
        self.last_excluded = 0
        # ٢٠٢٦-١٠-٠٢ (ختم المالك «صلح كامل nq»): مجلّد التدريج المعلَن، وعيار الفحص،
        # وحكمُ فحص النسخ، وما نُحّي من تشغيلاتٍ لم تكتمل، وآخر ساعةٍ رسميّة سُمعت.
        self._staging_dir = ""
        self._full_check_max_bytes = _DEFAULT_FULL_CHECK_MAX_BYTES
        self.last_skipped_journals = 0
        self._last_checks: dict[str, Any] = {}
        self._last_failure_at: float | None = None
        self._last_set_aside = ""
        self._incomplete: dict[str, Any] = {"dirs": 0, "bytes": 0}
        self._official_now: float | None = None
        # ٢٠٢٦-١٠-٠٩ (ختم المالك «NQ» — الصيانة في استراحة السوق): النسخة تقع في نافذة الصيانة
        # اليوميّة وحدها (`shared/owner_windows`) لا على نبض اليوم (03:00 بتوقيت الجهاز والسوق مفتوح)
        # ولا فور الإقلاع. مقيس: إقلاع ٠٨-١٠ 02:13 بدأ نسخةً امتدّت إلى 04:13 فوق تجمّدات 03:00.
        self._maintenance = MaintenanceGate()
        self._pending_catchup = ""

    async def initialize(self, context: AtomContext) -> None:
        self._context = context
        cfg = _rebased_config(context.config)
        self._backup_dir = str(cfg["backup_dir"])
        self._source_dirs = [_anchor(str(s)) for s in cfg["source_dirs"]]
        self._keep_last_n = int(cfg["keep_last_n"])
        self._interval_days = int(cfg["interval_days"])
        self._min_bytes = int(cfg["min_source_bytes"])
        self._exclude = [str(p) for p in (cfg.get("exclude_patterns") or [])]
        self._staging_dir = str(cfg.get("staging_dir") or "")
        self._full_check_max_bytes = int(
            cfg.get("full_check_max_bytes") or _DEFAULT_FULL_CHECK_MAX_BYTES)
        context.subscribe(EVENT_DAY, self._on_day)
        context.subscribe(EVENT_PULSE, self._on_pulse)
        self._initialized = True

    async def start(self) -> None:
        if not self._initialized or self._running or self._context is None:
            return
        self._catchup_done = False
        self._running = True
        self.orphans_cleared = self._clear_orphans()

    def _staging_root(self) -> Path:
        """مجلّد التدريج المعلَن في المانيفست، واحتياطُه `<backup_dir>/staging`.

        ٢٠٢٦-١٠-٠٢ (ختم المالك «صلح كامل nq»): كان `tempfile.TemporaryDirectory()` في
        مؤقّتات النظام، فتركت ثلاث تشغيلاتٍ قُتلت يوم ٠٩-٢٥ ‏48.6 ج.ب في `%TEMP%`
        (`tmpa62vtxb2` · `tmpjfi3mkex` · `tmpjsk7mxje`) لا يراها `_clear_orphans`.
        """
        if self._staging_dir:
            return Path(self._staging_dir).resolve()
        return Path(self._backup_dir).resolve() / "staging"

    def _count_incomplete(self) -> None:
        self._incomplete = count_incomplete(self._staging_root())

    def _clear_orphans(self) -> int:
        """يتامى النسخ المقتولة — تُنحّى عند الإقلاع إلى `incomplete-*`، ولا تُمسح.

        ⚠️ **نزيفٌ مقيس: ٣٫٦١ جيجابايت في يومين.** تنظيفي مكتوبٌ في
        `except BaseException` داخل `_run_backup`، **وهو لا يُنفَّذ حين تُقتل
        العمليّة نفسها** — والنسخة تستغرق أطول من الفاصل بين الإقلاعات، فثلاثة
        إقلاعاتٍ يوم ٢٠٢٦-٠٩-٢٣ قتلت ثلاثًا وتركت ثلاثة أيتام (أكبرها ١٬٣٣١
        ميغابايت). وكلُّ إقلاعٍ يزيدها ولا يُنقصها.

        ٢٠٢٦-١٠-٠٢ (ختم المالك «صلح كامل nq»): صارت تُنقل ولا تُمسح — مجلّد تشغيلةٍ
        مقتولة (`run-*`) يصير `incomplete-*`، ويتيمُ المسار القديم (`.backup.*.tar.gz.tmp`)
        يُنقل إلى `incomplete-legacy-*`. والحذف بيد المالك. والتشغيلة المقتولة فشلٌ
        يُنطق: سطر `ERROR` وصحّةٌ متدهورة بسببها حتّى تنجح نسخة.
        """
        try:
            cleared, size, interrupted = set_aside_orphans(
                Path(self._backup_dir), self._staging_root())
        except OSError:
            cleared, size, interrupted = 0, 0, []
        self.orphan_bytes_cleared += size
        self._count_incomplete()
        if interrupted:
            self._last_error = ("PREVIOUS_RUN_INTERRUPTED: set aside as %s"
                                % ", ".join(interrupted))
            if self._context is not None:
                self._context.logger.error(
                    "BACKUP_RUN_INTERRUPTED partial_output=%s", ", ".join(interrupted))
        return cleared

    async def stop(self) -> None:
        self._running = False
        # نسخةٌ جاريةٌ الآن تُنتظَر: قطعُها يترك ملفًّا مؤقّتًا نصفَ مكتوب.
        task = self._backup_task
        self._backup_task = None
        if task is not None and not task.done():
            try:
                await task
            except Exception:  # noqa: BLE001 — الإغلاق لا يُسقطه خطأُ نسخة
                pass

    async def shutdown(self) -> None:
        await self.stop()

    def _run_backup(self, now: float) -> tuple[str, int, int, int]:
        backup_dir = Path(self._backup_dir).resolve()
        backup_dir.mkdir(parents=True, exist_ok=True)
        sources = [Path(src).resolve() for src in self._source_dirs if Path(src).is_dir()]
        if len(sources) != len(self._source_dirs):
            raise FileNotFoundError("one or more backup sources are missing")
        archive = backup_dir / ("backup_%d.tar.gz" % int(now))
        # ٢٠٢٦-١٠-٠٢ (ختم المالك «صلح كامل nq»): كلّ تشغيلةٍ في مجلّدها داخل مجلّد
        # التدريج المعلَن — الأرشيف الجزئيّ والنسخةُ الجارية معًا. تنجح ⟵ يُنقل الأرشيف
        # إلى `backup_dir` ويُزال المجلّد الفارغ؛ تفشل ⟵ يُنحّى المجلّد كلّه
        # `incomplete-<الزمن>`؛ تُقتل ⟵ يُنحّى عند الإقلاع التالي (`_clear_orphans`).
        staging = self._staging_root()
        staging.mkdir(parents=True, exist_ok=True)
        run_dir = staging / (_RUN_PREFIX + _stamp(now))
        serial = 1
        while run_dir.exists():
            serial += 1
            run_dir = staging / ("%s%s-%d" % (_RUN_PREFIX, _stamp(now), serial))
        run_dir.mkdir()
        tmp_name = run_dir / "backup.tar.gz.tmp"
        file_count = 0
        byte_count = 0
        excluded = 0
        journals = 0
        checks: dict[str, Any] = {"checked": 0, "integrity_check": 0,
                                  "quick_check": 0, "failed": {}}
        self._last_set_aside = ""
        try:
            with tarfile.open(tmp_name, "w:gz") as tar:
                stage = run_dir
                for source_index, src in enumerate(sources):
                    root_name = "%d_%s" % (source_index, src.name)
                    for root, dirs, files in os.walk(src):
                        root_path = Path(root).resolve()
                        dirs[:] = [d for d in dirs if not any(
                                   (root_path / d).resolve().is_relative_to(own)
                                   for own in (backup_dir, staging))]
                        if any(root_path.is_relative_to(own)
                               for own in (backup_dir, staging)):
                            continue
                        for name in files:
                            full = (root_path / name).resolve()
                            if any(full.is_relative_to(own)
                                   for own in (backup_dir, staging)):
                                continue
                            # ٢٠٢٦-١٠-٠٢ (ختم المالك «صلح كامل nq»): السجلّ المرافق
                            # لا يُنسخ خامًا — النسخة المتّسقة تحمل ما فيه.
                            if name.lower().endswith(_JOURNAL_SUFFIXES):
                                journals += 1
                                continue
                            # ⚠️ **أرشيفٌ مغلقٌ لا يُنسخ كلّ يوم.** مقيس
                            # ٢٠٢٦-٠٩-٢٣: `var/store` **٢٦٫٤ ج.ب** منها
                            # **١٠٫٤٨ في اثني عشر ملفّ `archive.closed.*`**،
                            # ونما ٧٫٤ ج.ب في يومٍ واحد. وكلّما كبر المصدر
                            # طالت النسخة وزاد احتمال قتلها بإقلاع — وطال
                            # تزاحمُها مع مخازني: قفز `sqlite` إلى ٤٫٨ ثانية
                            # للإدراج الواحد، فامتلأ بفر ٧٠٧ عند ١٠٬٠٠٠
                            # **وأُسقط ١٬٣٤٩ قرارًا**. فالنسخ كان يكلّف قرارات.
                            # وهذه ملفّاتٌ **مغلقة لا تتغيّر**، فنسخُها يوميًّا
                            # تكرارٌ بلا فائدة. تُستثنى بنمطٍ من المانيفست لا
                            # برقمٍ في الكود — والعيار للمالك.
                            if any(full.match(pattern)
                                   for pattern in self._exclude):
                                excluded += 1
                                continue
                            rel = full.relative_to(src)
                            arcname = (Path(root_name) / rel).as_posix()
                            if full.suffix.lower() == ".db":
                                # ٢٠٢٦-١٠-٠٢ (ختم المالك «صلح كامل nq»): نسخةٌ متّسقة
                                # ثمّ فحصُها هي — لا مقارنةٌ بأصلٍ حيّ تحرّك بعدها.
                                staged = stage / (str(file_count) + ".db")
                                pages, page_size = _online_copy(full, staged)
                                mode, verdict = _verify_copy(
                                    staged, self._full_check_max_bytes)
                                checks["checked"] += 1
                                checks[mode] += 1
                                if verdict != "ok":
                                    checks["failed"][arcname] = "%s: %s" % (mode, verdict)
                                    raise sqlite3.DatabaseError(
                                        "copy failed %s: %s — %s" % (mode, arcname, verdict))
                                tar.add(staged, arcname=arcname)
                                # نسختُها صارت في الأرشيف — فلا تبقى نسختان على القرص.
                                staged.unlink()
                                byte_count += pages * (page_size or _PAGE_BYTES_HINT)
                            else:
                                tar.add(full, arcname=arcname)
                                byte_count += full.stat().st_size
                            file_count += 1
            if file_count == 0:
                raise OSError("backup would be empty")
            # ⚠️ **العدد لا يحرس.** حرسَ `file_count == 0` ثلاثةَ أسابيع بينما
            # كلّ نسخةٍ خرجت صدفةً فارغة: خمسون ملفًّا من شجرةٍ شبحيّة مجموعها
            # ١٫٠ م.ب بدل ١٥٫١ جيجابايت — والعدّاد سعيدٌ لأنّ خمسين ليست صفرًا.
            # فصار المقياس بايتًا، وبعتبةٍ من المانيفست لا من اجتهادي.
            if byte_count < self._min_bytes:
                raise OSError("backup too small: %d بايت دون العتبة %d"
                              % (byte_count, self._min_bytes))
            with tarfile.open(tmp_name, "r:gz") as check:
                members = check.getmembers()
                if len(members) != file_count:
                    raise tarfile.TarError("backup member count mismatch")
            self.last_excluded = excluded
            self.last_skipped_journals = journals
            self._last_checks = checks
            os.replace(tmp_name, archive)
            try:
                run_dir.rmdir()
            except OSError:
                _set_aside(run_dir, _stamp(now) + "-leftover")
            size = archive.stat().st_size
            self._enforce_retention()
            return str(archive), size, file_count, byte_count
        except BaseException:
            # ٢٠٢٦-١٠-٠٢ (ختم المالك «صلح كامل nq»): مخرَج الفشل يُنحّى ولا يُمسح.
            self._last_checks = checks
            moved = _set_aside(run_dir, _stamp(now))
            self._last_set_aside = str(moved) if moved is not None else str(run_dir)
            self._count_incomplete()
            raise

    def _enforce_retention(self) -> None:
        # ٢٠٢٦-١٠-١٢ (أمر المالك «NQ»: «أكثر من 7 لقطات ما لازم يضلّ موجود عنده»): السقف على النسخ اليوميّة وعلى لقطات
        # لوحة الحوكمة (`snapshot_*.zip`) معًا — كلٌّ أحدثُ `keep_last_n`. الأسماء تحمل زمنها فترتيبها ترتيبُ عمرها.
        for prefix, suffix in (("backup_", ".tar.gz"), ("snapshot_", ".zip")):
            try:
                backups = sorted(
                    (f for f in os.listdir(self._backup_dir)
                     if f.startswith(prefix) and f.endswith(suffix)), reverse=True)
            except OSError:
                return
            for old in backups[self._keep_last_n:]:
                try:
                    os.remove(os.path.join(self._backup_dir, old))
                except OSError:
                    pass

    def _due(self, now: float) -> bool:
        if self._last_success is None:
            return True
        age = now - self._last_success
        # ٢٠٢٦-١٠-٠٩ (ختم المالك «NQ» — الصيانة في استراحة السوق): نافذتان يوميّتان تبعدان 24 ساعة
        # والنسخة قد تبدأ في أيّ دقيقة من ساعتها — فيُقبل عمرٌ أقصر من الفاصل بهامش النافذة المسمّى.
        return age < 0 or age >= self._interval_days * _SECONDS_PER_DAY - MAINTENANCE_RERUN_SLACK_S

    def _schedule_backup(self, now: float, trigger: str) -> bool:
        """النسخ يُجدوَل ولا يُنتظَر — مهمّةٌ واحدة في آنٍ.

        ⚠️ **هذا عطبٌ سبّبتُه أنا، وكلّف خمسة أيّام بلا نسخةٍ واحدة.**
        قبل ٢٠٢٦-٠٩-١٩ كانت النسخة ٢٧ كيلوبايت من شجرةٍ شبحيّة فارغة،
        فانتظارُها في المعالج لا يُحسّ. ثمّ وجّهتُها إلى المخزن الحقيقيّ
        (**١٥٫١ جيجابايت**) وتركتُها تُنتظَر — فصار كلُّ نداءٍ يحجب حلقة
        الأحداث دقائق. المقيس ٢٠٢٦-٠٩-٢٣:

            handler timeout subscriber=800   ×٣ اليوم (SYS_SECOND · SYS_DAY)
            آخر نجاح                         ٢٠٢٦-٠٩-١٨ ١٣:٥٩  ← خمسة أيّام
            backup_count                     ١٠، لم يتحرّك

        أي أنّ الإصلاح صوّب الوجهة وقتل العمليّة: النسخة لا تكتمل أبدًا.
        والنمط هو الرابع من نوعه في أربعة أيّام — عملٌ ثقيل يُنتظَر في
        معالجٍ ميزانيّته ٥٠ م.ث. فيُجدوَل، ويبقى حارسُ «واحدة في آنٍ» كي
        لا تتراكم نُسخٌ متوازية على القرص نفسه.
        """
        task = self._backup_task
        if task is not None and not task.done():
            self.backup_skipped += 1
            return False
        try:
            self._backup_task = asyncio.create_task(self._execute(now, trigger))
        except RuntimeError:
            self._backup_task = None
            return False
        return True

    async def _execute(self, now: float, trigger: str) -> None:
        if not self._running or self._context is None or not self._due(now):
            return
        try:
            # 2.7.0 (٢٠٢٦-٠٩-٢٥، ختم المالك «Nq صلح كل امور»): النسخة بأولويّة الخلفيّة.
            # تصويرُ العمليّة الباردة 17:42 وجدها جاريةً مع فحص سلامة الأرشيف وطابورُ
            # القرص 8–17، فتجمّدت حلقة المنصّة حتّى 13.9ث. تبقى النسخة كما هي،
            # وتأخذ من القرص ما يفضل عن المنصّة.
            path, size, count, sources = await asyncio.to_thread(
                run_in_background, self._run_backup, now)
        except Exception as exc:  # noqa: BLE001 — ٢٠٢٦-١٠-٠٢: كلّ فشلٍ يُنطق، لا ثلاثة أنواعٍ وحدها
            # ٢٠٢٦-١٠-٠٢ (ختم المالك «صلح كامل nq»): كان الفشل حدثًا بلا سطر سجلّ،
            # فأربعة عشر يومًا بلا نسخة لم تترك أثرًا يُقرأ. الآن سطر `ERROR` بالسبب
            # وبمكان المخرَج المُنحّى، والصحّة متدهورة بالسبب حتّى تنجح نسخة.
            self._last_error = "%s: %s" % (type(exc).__name__, exc)
            self._last_failure_at = now
            self._context.logger.error(
                "BACKUP_FAILED trigger=%s reason=%s partial_output=%s",
                trigger, self._last_error, self._last_set_aside or "-")
            await self._context.publish(EVENT_FAILED, {
                "reason": self._last_error, "timestamp": now, "trigger": trigger,
                "partial_output": self._last_set_aside,
                "checks": dict(self._last_checks)})
            return
        self._last_success = now
        self._last_error = ""
        self._last_source_bytes = sources
        self.backup_count += 1
        await self._context.publish(EVENT_DONE, {
            "path": path, "size_bytes": size, "file_count": count,
            "source_bytes": sources,
            "timestamp": now, "trigger": trigger,
            "last_success": self._last_success,
            "checks": dict(self._last_checks),
            "skipped_journals": self.last_skipped_journals})

    def _maintain(self, now: float, trigger: str) -> None:
        """٢٠٢٦-١٠-٠٩ (ختم المالك «NQ» — الصيانة في استراحة السوق): النسخة تُجدوَل داخل نافذة
        الصيانة اليوميّة وحدها، مرّةً في كلّ نافذة. خارجها لا شيء — ونبضة اليوم تُعدّ ولا تُشغّل."""
        key = self._maintenance.due(
            now, self._last_success, self._interval_days * _SECONDS_PER_DAY,
            held=trigger == EVENT_DAY)
        if key is None:
            return
        why = self._pending_catchup or trigger
        if self._schedule_backup(now, why):
            self._maintenance.mark(key, now)
            self._pending_catchup = ""

    async def _on_day(self, payload: dict[str, Any]) -> None:
        if not self._running or self._context is None or not isinstance(payload, dict):
            return
        now = _to_float(payload.get("official_time", payload.get("timestamp")))
        if now is not None:
            self._maintain(now, EVENT_DAY)

    async def _on_pulse(self, payload: dict[str, Any]) -> None:
        if not self._running or not isinstance(payload, dict):
            return
        now = _to_float(payload.get("official_time"))
        if now is None:
            return
        # ٢٠٢٦-١٠-٠٢ (ختم المالك «صلح كامل nq»): آخر ساعةٍ رسميّة — تحكم بها الصحّة
        # على عمر آخر نجاح (التشغيلة المقتولة لا تمرّ بمسار الفشل أبدًا).
        self._official_now = now
        if not self._catchup_done:
            # ٢٠٢٦-١٠-٠٩ (ختم المالك «NQ» — الصيانة في استراحة السوق): حكمُ اللحاق يُحسب عند الإقلاع
            # ويُعلن، والتنفيذ ينتظر النافذة — ويحمل سببه («لحاق») إلى أوّل نسخةٍ فيها.
            self._catchup_done = True
            self._first_pulse_at = now
            verdict = decide({"last_success": self._last_success}, now)
            self._catchup_verdict = verdict
            self._pending_catchup = verdict["status"] if verdict["run"] else ""
        # ٢٠٢٦-١٠-١٢ (تفويض المالك الكامل «NQ»: «إذا السستم كان واقف لحظة اللقطة، لازم مع أوّل إقلاع ياخد لقطة»): النسخة
        # الفائتة تُؤخذ بعد إقلاعٍ بعشر دقائق، لا في نافذة الليلة القادمة. خطرُ ٠٨-١٠ (نسخةٌ امتدّت ساعتين فوق تجمّدات
        # 03:00) سببه مخزنٌ بـ46 ج.ب — صُفّر إلى الأرشيف اليوم (1.9 ج.ب)، والنسخة بأولويّة الخلفيّة.
        if self._pending_catchup and now - getattr(self, "_first_pulse_at", now) >= BOOT_CATCHUP_DELAY_S:
            if self._schedule_backup(now, "BOOT_" + self._pending_catchup):
                self._pending_catchup = ""
        self._maintain(now, "MAINTENANCE_WINDOW")

    async def snapshot(self) -> dict[str, Any]:
        return {"version": ATOM_VERSION, "last_success": self._last_success,
                "backup_count": self.backup_count,
                "backup_running": self._backup_task is not None
                and not self._backup_task.done(),
                "backup_skipped": self.backup_skipped,
                "orphans_cleared": self.orphans_cleared,
                "orphan_bytes_cleared": self.orphan_bytes_cleared,
                "last_excluded": self.last_excluded,
                "source_bytes": self._last_source_bytes,
                # ٢٠٢٦-١٠-٠٢ (ختم المالك «صلح كامل nq»): سببُ الفشل يُحفظ فيعبر الإقلاع
                # (كان يضيع فتعود الصحّة «سليمة» وآخر نجاحٍ قبل أسبوعين)، ومعه حكمُ فحص
                # النسخ وما نُحّي من مخرَجٍ لم يكتمل — حجمًا يقرؤه المالك قبل أن يحذف.
                "last_error": self._last_error,
                "last_failure_at": self._last_failure_at,
                "last_skipped_journals": self.last_skipped_journals,
                "checks": dict(self._last_checks),
                "incomplete": dict(self._incomplete),
                # ٢٠٢٦-١٠-٠٩ (ختم المالك «NQ» — الصيانة في استراحة السوق): وقت آخر صيانة يعبر الإقلاع
                # للإعلان. وإقلاعٌ داخل النافذة لا يعيد نسخةً نجحت (يمنعه عمر آخر نجاح) ويعيد المقتولة.
                **self._maintenance.snapshot()}

    async def restore(self, state: dict[str, Any]) -> None:
        if not isinstance(state, dict):
            raise ValueError("INVALID_BACKUP_STATE")
        value = state.get("last_success", state.get("last_run"))
        self._last_success = _to_float(value)
        self.backup_count = int(state.get("backup_count") or 0)
        self._last_source_bytes = int(state.get("source_bytes") or 0)
        self._last_error = str(state.get("last_error") or "")
        self._last_failure_at = _to_float(state.get("last_failure_at"))
        self._maintenance.restore(state)

    def _stale_reason(self) -> str:
        """آخر نجاحٍ أقدم من ضعفي الفاصل بالساعة الرسميّة ⟵ سببٌ يُعلَن، وإلّا فراغ."""
        if self._last_success is None or self._official_now is None:
            return ""
        age = self._official_now - self._last_success
        if age <= 2 * self._interval_days * _SECONDS_PER_DAY:
            return ""
        return "BACKUP_STALE: last success %.1f days ago" % (age / _SECONDS_PER_DAY)

    async def health_check(self) -> HealthStatus:
        if not self._running:
            return HealthStatus(state=HealthState.UNHEALTHY, message=REASON_NOT_STARTED)
        details = {"backups": self.backup_count,
                   "last_success": self._last_success,
                   "backup_dir": self._backup_dir,
                   "source_dirs": list(self._source_dirs),
                   "source_bytes": self._last_source_bytes,
                   "last_error": self._last_error,
                   "last_failure_at": self._last_failure_at,
                   "staging_dir": str(self._staging_root()),
                   "checks": dict(self._last_checks),
                   "skipped_journals": self.last_skipped_journals,
                   "incomplete": dict(self._incomplete),
                   "catchup": dict(self._catchup_verdict),
                   "maintenance_held_outside": self._maintenance.held_outside}
        # ٢٠٢٦-١٠-٠٩ (ختم المالك «NQ» — الصيانة في استراحة السوق): متى صانت آخر مرّة ومتى القادمة —
        # في الرسالة نفسها، فالتفاصيل تُقصّ عند حدود النواة.
        window = " · " + self._maintenance.describe()
        if self._last_error:
            return HealthStatus(
                state=HealthState.DEGRADED, message=self._last_error + window, details=details)
        stale = self._stale_reason()
        if stale:
            return HealthStatus(state=HealthState.DEGRADED, message=stale + window, details=details)
        if self.backup_count == 0:
            status = self._catchup_verdict.get("status")
            if status == "SKIPPED":
                message = ("READY - previous backup within window (%s) | backups=0"
                           % str(self._catchup_verdict.get("reason", "")).strip())
            else:
                message = "READY_AWAITING_FIRST_BACKUP_RUN | backups=0"
            return HealthStatus(
                state=HealthState.HEALTHY, message=message.strip() + window, details=details)
        return HealthStatus(
            state=HealthState.HEALTHY,
            message="backups=%d" % self.backup_count + window, details=details)
