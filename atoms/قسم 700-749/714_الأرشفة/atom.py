from __future__ import annotations

import asyncio
import os
import pathlib
import re
import sqlite3
import time
from pathlib import Path
from typing import Any

from core.contracts.atom import AtomBase, AtomContext, HealthState, HealthStatus
from storage_policy import file_lock, run_in_background
from catchup import decide, outcome
from shared.owner_windows import MaintenanceGate

ATOM_VERSION = "3.6.0"

EVENT_PULSE = "SYS_SECOND"

_DB_TIMEOUT_S = 5.0
_BUSY_TIMEOUT_MS = 3000
_SECONDS_PER_DAY = 86400.0
# v3.5.0: انتظارُ من يمسك ملفّ الأرشيف عند إعادة تسميته (`_replace_when_free`).
_RENAME_WAIT_S = 3600.0
_RENAME_RETRY_S = 60.0
_WINERROR_SHARING = 32

EVENT_DAY = "SYS_DAY"
EVENT_OUT = "storage.archived"

REASON_NOT_STARTED = "NOT_STARTED"
REASON_AWAITING_PULSE = "AWAITING_FIRST_PULSE"

_IDENT = re.compile(r"^[A-Za-z0-9_]+$")


def _to_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _connect(path: str) -> sqlite3.Connection:
    connection = sqlite3.connect(path, timeout=_DB_TIMEOUT_S)
    try:
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA busy_timeout=%d" % _BUSY_TIMEOUT_MS)
    except BaseException:
        # أوّل PRAGMA تقرأ ترويسة الملف: على قاعدة تالفة ترمي بعد إنشاء
        # الاتصال فيبقى المقبض مفتوحًا والملف ممسوكًا. مقيس ٢٠٢٦-٠٩-٠٩.
        connection.close()
        raise
    return connection


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
        self._stores: list[dict[str, str]] = []
        self._archive_path = ""
        self._archive_after_days = 0
        self._batch_limit = 0
        self._runs = 0
        self._archived_total = 0
        self._last_error = ""
        self._last_success: float | None = None
        self._catchup_done = False
        self._catchup_verdict: dict[str, Any] = {}
        self._last_outcome: dict[str, Any] = {}
        self._last_report: dict[str, int] = {}
        self._last_closed_path: str | None = None
        self._rotation_counter = 0
        self._rename_waits = 0
        self._archive_task: asyncio.Task | None = None
        # ٢٠٢٦-١٠-٠٩ (ختم المالك «NQ» — الصيانة في استراحة السوق): الأرشفة وتدوير الأرشيف (فحصا سلامةٍ
        # على ملفٍّ بخمسة غيغا وأكثر، ثمّ ضغطه عند 715) في نافذة الصيانة اليوميّة وحدها. مقيس: ملفّات
        # `archive.closed.<منتصف ليل غرينتش>` وضغطها كُتبت 03:00–03:23 بتوقيت الجهاز كلّ ليلة والسوق مفتوح.
        self._maintenance = MaintenanceGate()
        self._pending_catchup = ""

    async def initialize(self, context: AtomContext) -> None:
        self._context = context
        cfg = _rebased_config(context.config)
        self._stores = [dict(s) for s in cfg["stores"]]
        self._archive_path = str(cfg["archive_db_path"])
        self._archive_after_days = int(cfg["archive_after_days"])
        self._batch_limit = int(cfg["batch_limit"])
        context.subscribe(EVENT_DAY, self._on_day)
        context.subscribe(EVENT_PULSE, self._on_pulse)
        self._initialized = True

    async def start(self) -> None:
        if not self._initialized or self._running or self._context is None:
            return
        self._catchup_done = False
        self._running = True

    async def stop(self) -> None:
        self._running = False
        # أرشفةٌ جارية تُمهَل حتى تنتهي: قطعُها في منتصف نقلِ صفوفٍ بين قاعدتين
        # يترك الصفّ في الاثنتين أو في لا واحدة. الخطوات نفسها محميّة داخلها،
        # فالانتظار هنا هو الطريق الآمن — والإلغاء لا يُستعمل.
        task, self._archive_task = self._archive_task, None
        if task is not None and not task.done():
            try:
                await task
            except Exception:  # noqa: BLE001 — الإيقاف لا يُسقطه خطأ دورة
                pass

    async def shutdown(self) -> None:
        await self.stop()

    def _archive_one(self, store: dict[str, str], cutoff: float) -> int:
        source = store.get("db_path", ""); table = store.get("table", ""); time_col = store.get("time_column", "occurred_at")
        if not source or not _IDENT.fullmatch(table) or not _IDENT.fullmatch(time_col):
            raise ValueError("bad store spec")
        # عمود زمنيّ احتياطيّ لصفوف لا يُملأ عمودها الأوّل أبدًا. مقيس
        # ٢٠٢٦-٠٩-٠٩: ٧٥ صفقة `kind=OPENED` بلا `closed_at` (وهو صحيح — لم
        # تُغلق)، و٥٬٢٩٧ صفّ تحليل بلا `occurred_at` لأنّ الناشر لم يضع طابعًا.
        # بلا احتياطيّ تبقى هذه الصفوف خارج الأرشفة إلى الأبد.
        fallback = store.get("fallback_time_column") or ""
        if fallback and not _IDENT.fullmatch(fallback):
            raise ValueError("bad store spec")
        age_expr = "COALESCE(%s, %s)" % (time_col, fallback) if fallback else time_col
        if not Path(source).is_file():
            raise FileNotFoundError(source)
        Path(self._archive_path).parent.mkdir(parents=True, exist_ok=True)
        # ‏⛔ قفل الملفّ — لا قفل هذه الذرّة. `BEGIN IMMEDIATE` يحتجز الكتابة
        # على قاعدةٍ **يكتب فيها صاحبها في الوقت نفسه** (٧١٢ و٧٠٧). وما كان
        # يمنع الاصطدام أنّ الأرشفة كانت تجري **داخل معالج الحدث** فتُسلسلها
        # حلقة العامل قسرًا؛ ولمّا أخرجتُها إلى مهمّة خلفيّة (`3.3.0`) سقط
        # ذلك التسلسل. فيؤخذ قفل القاعدة نفسها الذي يأخذه كاتبوها.
        with file_lock(source):
            return self._archive_one_locked(source, table, age_expr, cutoff)

    def _archive_one_locked(self, source: str, table: str, age_expr: str,
                            cutoff: float) -> int:
        connection = _connect(source)
        try:
            # v3.5.0 (٢٠٢٦-٠٩-٢٥، ختم المالك «Nq صلح كل امور»): المخازن تُكتب
            # بترتيب زمنها، فأقدمُ صفٍّ بالرقم أقدمُها عمرًا. فإن كان أحدثَ من
            # الحدّ فلا شيء يُؤرشف — بلا مسحٍ وبلا قفل كتابة. كان البحثُ عن
            # أقدم من ستين يومًا (بلا فهرس على الزمن) يمسح الجدول كلّه وهو يحتجز
            # `BEGIN IMMEDIATE`، وأقدمُ صفٍّ في المخازن التسعة عمره عشرون يومًا:
            # ~11 غيغا تُقرأ بعد كلّ إقلاع وكلّ يوم بلا صفٍّ واحد يُنقل، وكتّابُها
            # (٧٠٧ و٧١٢ …) ينتظرون قفلها.
            first = connection.execute(
                f"SELECT {age_expr} FROM main.{table} ORDER BY id LIMIT 1").fetchone()
            if first is None:
                return 0
            oldest = _to_float(first[0])
            if oldest is not None and oldest >= cutoff:
                return 0
            connection.execute("ATTACH DATABASE ? AS archive", (self._archive_path,))
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(f"CREATE TABLE IF NOT EXISTS archive.{table} AS SELECT * FROM main.{table} WHERE 0")
            ids = [row[0] for row in connection.execute(
                f"SELECT id FROM main.{table} WHERE {age_expr} IS NOT NULL AND {age_expr} < ? ORDER BY id LIMIT ?",
                (cutoff, self._batch_limit)).fetchall()]
            if not ids:
                connection.rollback(); return 0
            marks=','.join('?' for _ in ids)
            connection.execute(f"INSERT INTO archive.{table} SELECT * FROM main.{table} WHERE id IN ({marks})", ids)
            deleted=connection.execute(f"DELETE FROM main.{table} WHERE id IN ({marks})",ids).rowcount or 0
            if deleted != len(ids): raise sqlite3.DatabaseError("archive/delete count mismatch")
            connection.commit(); return deleted
        except BaseException:
            connection.rollback(); raise
        finally:
            connection.close()

    def _run(self, cutoff: float) -> dict[str, int]:
        """كل مخزن معزول عن جاره — مخزنٌ عاطل لا يوقف أرشفة الباقين.

        مقيس ٢٠٢٦-٠٩-٠٩: `analysis.db` تالفة وهي الخامسة في الترتيب، فكانت
        ترمي فتُلغى أرشفة `structure` و`liquidity` و`trades` و`decisions`
        بعدها — والأخيرة أكبر مخزن في النظام. الأخطاء تُجمع وتُعلَن كلّها،
        ولا تُبتلع: `_last_error` يحملها، والذرّة تبقى `degraded`.
        """
        report: dict[str, int] = {}
        failures: list[str] = []
        for store in self._stores:
            table = str(store.get("table") or "?")
            try:
                moved = self._archive_one(store, cutoff)
            except (sqlite3.Error, OSError, ValueError) as exc:
                failures.append("%s: %s" % (table, exc))
                continue
            if moved:
                report[table] = moved
        self._last_error = " | ".join(failures)
        return report

    @staticmethod
    def _verify_database(path: Path) -> None:
        connection = sqlite3.connect(path, timeout=_DB_TIMEOUT_S)
        try:
            verdict = connection.execute("PRAGMA integrity_check").fetchone()
            if not verdict or str(verdict[0]).lower() != "ok":
                raise sqlite3.DatabaseError("rotated archive integrity check failed")
            checkpoint = connection.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
            if checkpoint and int(checkpoint[0]) != 0:
                raise sqlite3.OperationalError("archive database is still busy")
        finally:
            connection.close()

    def _archive_row_count(self, path: Path) -> int:
        if not path.is_file():
            return 0
        connection = sqlite3.connect(path, timeout=_DB_TIMEOUT_S)
        try:
            total = 0
            for store in self._stores:
                table = str(store.get("table") or "")
                if not _IDENT.fullmatch(table):
                    continue
                exists = connection.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
                ).fetchone()
                if exists:
                    total += int(connection.execute(
                        f"SELECT COUNT(*) FROM {table}").fetchone()[0])
            return total
        finally:
            connection.close()

    def _archive_has_rows(self, path: Path) -> bool:
        """أفي الأرشيف النشط صفٌّ واحد؟ — سؤالُ التدوير بلا عدّ.

        v3.5.0: كان القرار بـ`_archive_row_count` — `COUNT(*)` كاملًا على أرشيفٍ
        بلغ 16 غيغا (10.5 مليون قرار) — ثمّ يُعدّ ثانيةً داخل التدوير. والقرار
        لا يحتاج إلّا وجودَ صفّ؛ والعدُّ الدقيق باقٍ حيث يُحتاج (`closed_rows`).
        """
        if not path.is_file():
            return False
        connection = sqlite3.connect(path, timeout=_DB_TIMEOUT_S)
        try:
            for store in self._stores:
                table = str(store.get("table") or "")
                if not _IDENT.fullmatch(table):
                    continue
                exists = connection.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
                ).fetchone()
                if exists and connection.execute(
                        f"SELECT 1 FROM {table} LIMIT 1").fetchone():
                    return True
            return False
        finally:
            connection.close()

    def _replace_when_free(self, active: Path, closed: Path) -> None:
        """إعادةُ تسمية الأرشيف — تنتظر من يمسك الملفّ بدل أن تُسقط الدورة كلّها.

        v3.5.0: مقيس 18:17:49 — «[WinError 32] The process cannot access the file
        because it is being used by another process» بعد فحص سلامةٍ دام عشرين
        دقيقة، والنسخةُ الاحتياطيّة (800) تنسخ `var/store` كلّه منذ 17:59 ومعه هذا
        الملفّ. وويندوز لا يعيد تسمية ملفٍّ مفتوح؛ فكانت الدورة تفشل بعد عملها
        الثقيل كلّه، وتعيده بعد كلّ إقلاعٍ وكلّ يوم. الآن: إعادةُ المحاولة كلّ
        دقيقة حتّى ساعة، في خيط الدورة نفسه، وتكفّ فورًا إن أُوقفت الذرّة.
        """
        deadline = time.monotonic() + _RENAME_WAIT_S
        while True:
            try:
                os.replace(active, closed)
                return
            except PermissionError as exc:
                if (getattr(exc, "winerror", None) != _WINERROR_SHARING
                        or not self._running or time.monotonic() >= deadline):
                    raise
                self._rename_waits += 1
            time.sleep(_RENAME_RETRY_S)

    def _closed_name(self, now: float) -> Path:
        active = Path(self._archive_path)
        suffix = active.suffix or ".db"
        stem = active.stem if active.suffix else active.name
        while True:
            self._rotation_counter += 1
            candidate = active.with_name(
                f"{stem}.closed.{int(now)}.{self._rotation_counter}{suffix}")
            if not candidate.exists():
                return candidate

    def _rotate_archive(self, now: float) -> tuple[str, int]:
        active = Path(self._archive_path)
        if not active.is_file():
            raise FileNotFoundError(self._archive_path)
        self._verify_database(active)
        closed_rows = self._archive_row_count(active)
        if closed_rows <= 0:
            raise sqlite3.DatabaseError("refusing to rotate an empty archive")
        for suffix in ("-wal", "-shm"):
            sidecar = Path(str(active) + suffix)
            if sidecar.exists() and sidecar.stat().st_size:
                raise sqlite3.OperationalError("active archive sidecar remains: " + str(sidecar))
        closed = self._closed_name(now)
        closed.parent.mkdir(parents=True, exist_ok=True)
        self._replace_when_free(active, closed)
        try:
            connection = sqlite3.connect(active, timeout=_DB_TIMEOUT_S)
            connection.close()
            self._verify_database(closed)
        except BaseException:
            Path(active).unlink(missing_ok=True)
            os.replace(closed, active)
            raise
        self._last_closed_path = str(closed)
        return str(closed), closed_rows

    def _schedule_archive(self, now: float | None, trigger: str) -> bool:
        """الأرشفة تخرج من مسار الحدث — عملُ دقائقَ لا يُنتظَر في معالج.

        مقيس ٢٠٢٦-٠٩-١٦ من عدّاد الناقل: **أسوأ مدّة معالجٍ في المنصّة كلّها
        كانت لـ٧١٤ — ٣٠٫٠١ ثانية** مقابل ميزانية ٠٫٠٥. والسبب أنّ `_on_day`
        و`_on_pulse` كانتا تنتظران `_archive` كاملةً: نسخُ صفوفٍ بين قاعدتين،
        ثمّ عدُّها، ثمّ تدوير ملفّ الأرشيف. وتسليم الناقل يمضي بالتتابع على
        مسار العامل، فمشترِكٌ يحجب ثلاثين ثانية **يحجب كلّ ما خلفه** — وهذه
        الذرّة تشترك في `SYS_SECOND`، أي أنّ الحجب يقع على نبض النظام نفسه.
        العلاج نفس علاج ٧١٢: مهمّة خلفيّة بحارس «واحدة في آنٍ»، فالنداء
        الثاني أثناء جريان الأولى يُهمَل بدل أن يتراكم.
        """
        if self._archive_task is not None and not self._archive_task.done():
            return False
        self._archive_task = asyncio.create_task(self._archive(now, trigger))
        return True

    def _maintain(self, now: float | None, trigger: str) -> None:
        """٢٠٢٦-١٠-٠٩ (ختم المالك «NQ» — الصيانة في استراحة السوق): مرّةً في كلّ نافذة صيانة، وخارجها
        لا شيء. نبضة اليوم (03:00 بتوقيت الجهاز) تُعدّ ولا تُشغّل."""
        key = self._maintenance.due(now, self._last_success, held=trigger == EVENT_DAY)
        if key is None:
            return
        if self._schedule_archive(now, self._pending_catchup or trigger):
            self._maintenance.mark(key, now)
            self._pending_catchup = ""

    async def _on_day(self, payload: dict[str, Any]) -> None:
        if not self._running:
            return
        now = _to_float(payload.get("official_time", payload.get("timestamp")))
        self._maintain(now, EVENT_DAY)

    async def _on_pulse(self, payload: dict[str, Any]) -> None:
        if not self._running:
            return
        now = _to_float((payload or {}).get("official_time"))
        if now is None:
            return
        if not self._catchup_done:
            # حكم اللحاق يُحسب عند الإقلاع ويُعلن، والتنفيذ ينتظر النافذة ويحمل سببه إليها.
            self._catchup_done = True
            verdict = decide({"last_success": self._last_success}, now)
            self._catchup_verdict = verdict
            self._pending_catchup = verdict["status"] if verdict["run"] else ""
        self._maintain(now, "MAINTENANCE_WINDOW")

    async def _archive(self, now: float | None, trigger: str) -> None:
        if not self._running or self._context is None:
            return
        if now is None or self._archive_after_days <= 0:
            return
        cutoff = now - self._archive_after_days * _SECONDS_PER_DAY
        started = now
        closed_path: str | None = None
        closed_rows = 0
        report: dict[str, int] = {}
        moved = 0
        try:
            # v3.5.0: الخطوات الثلاث بأولويّة الخلفيّة (`run_in_background`) — فحصُ
            # سلامة أرشيفٍ بسبعة عشر غيغا لا يزاحم المنصّة على القرص بعد اليوم.
            report = await asyncio.to_thread(run_in_background, self._run, cutoff)
            moved = sum(report.values())
            active_rows = await asyncio.to_thread(
                run_in_background, self._archive_has_rows, Path(self._archive_path))
            if active_rows:
                closed_path, closed_rows = await asyncio.to_thread(
                    run_in_background, self._rotate_archive, now)
            copied = True
        except Exception as exc:
            self._last_error = str(exc)
            copied, closed_path, closed_rows = False, None, 0
        verified = copied and not self._last_error and (moved == 0 or closed_path is not None)
        result = outcome(copied, verified, self._source_intact(), started, now)
        if result["persist_last_success"]:
            self._last_success = result["last_success"]
        self._runs += 1
        self._archived_total += moved
        self._last_report = report
        self._last_outcome = result
        # v3.5.0: الفشل يُكتب في السجلّ. آخرُ نجاحٍ قبل ~4.3 أيّام (لقطة الذرّة)
        # وسببُه لم يُعرف: ذرّات العمليّة الباردة لا تظهر في `/api/atoms`، والحدث
        # `storage.archived` لا يحفظه مخزن — فكانت كلُّ دورةٍ فاشلة تمضي بلا أثر.
        if self._last_error:
            self._context.logger.warning(
                "714 archive %s failed (status=%s): %s",
                trigger, result.get("status"), self._last_error[:500])
        await self._context.publish(EVENT_OUT, {
            "rows": closed_rows, "moved_rows": moved,
            "total": self._archived_total, "per_table": dict(report),
            "cutoff": cutoff, "archive_path": closed_path, "timestamp": now,
            "active_archive_path": self._archive_path,
            "trigger": trigger, "status": result["status"],
            "last_success": self._last_success, "reason": result["reason"]})

    def _source_intact(self) -> bool:
        if not self._stores:
            return True
        return all(pathlib.Path(str(s.get("db_path") or "")).is_file()
                   for s in self._stores)

    async def snapshot(self) -> dict[str, Any]:
        return {"version": ATOM_VERSION, "last_success": self._last_success,
                **self._maintenance.snapshot()}

    async def restore(self, state: dict[str, Any]) -> None:
        if isinstance(state, dict):
            self._last_success = _to_float(state.get("last_success"))
            self._maintenance.restore(state)

    async def health_check(self) -> HealthStatus:
        if not self._running:
            return HealthStatus(state=HealthState.UNHEALTHY, message=REASON_NOT_STARTED)
        details = {"runs": self._runs, "archived": self._archived_total,
                   "stores": len(self._stores), "last_report": dict(self._last_report),
                   "last_error": self._last_error,
                   "last_success": self._last_success,
                   "active_archive_path": self._archive_path,
                   "last_closed_path": self._last_closed_path,
                   "catchup": dict(self._catchup_verdict),
                   "last_outcome": dict(self._last_outcome),
                   "rename_waits": self._rename_waits,
                   "maintenance_held_outside": self._maintenance.held_outside}
        # ٢٠٢٦-١٠-٠٩ (ختم المالك «NQ» — الصيانة في استراحة السوق): متى صانت آخر مرّة ومتى القادمة.
        window = " · " + self._maintenance.describe()
        if self._runs == 0:
            status = self._catchup_verdict.get("status")
            reason = self._catchup_verdict.get("reason")
            if status == "SKIPPED" and reason == "WITHIN_WINDOW":
                age = _to_float(self._catchup_verdict.get("age_s"))
                age_text = "%.1f" % (age / 3600.0) if age is not None else "?"
                return HealthStatus(
                    state=HealthState.HEALTHY,
                    message="READY - last successful archive %s hours ago at startup"
                            " (within 24h window) | WITHIN_WINDOW runs=0" % age_text + window,
                    details=details)
            if self._pending_catchup:
                # لحاقٌ مطلوب ينتظر النافذة بقرار المالك — انتظارٌ معلن لا عطل.
                return HealthStatus(
                    state=HealthState.HEALTHY,
                    message="%s — ينتظر نافذة الصيانة%s" % (self._pending_catchup, window),
                    details=details)
            if status == "SKIPPED":
                message = "SKIPPED_WINDOW %s" % (reason or "")
            elif status:
                message = str(status)
            else:
                message = (REASON_AWAITING_PULSE
                           + " - no official time pulse yet; catch-up decision unresolved")
            return HealthStatus(state=HealthState.DEGRADED,
                                message=message.strip() + window, details=details)
        if self._last_error:
            return HealthStatus(
                state=HealthState.DEGRADED, message=self._last_error + window, details=details)
        return HealthStatus(
            state=HealthState.HEALTHY,
            message="runs=%d archived=%d" % (self._runs, self._archived_total) + window,
            details=details)
