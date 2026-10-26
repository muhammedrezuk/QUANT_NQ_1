from __future__ import annotations

import asyncio
import re
import sqlite3
from pathlib import Path
from typing import Any

from core.contracts.atom import AtomBase, AtomContext, HealthState, HealthStatus
from storage_policy import file_lock


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


ATOM_VERSION = "2.3.0"

_DB_TIMEOUT_S = 5.0
_BUSY_TIMEOUT_MS = 3000

EVENT_IN = "storage.archived"
EVENT_OUT = "storage.trading_data_cleaned"

REASON_NOT_STARTED = "NOT_STARTED"

_IDENT = re.compile(r"^[A-Za-z0-9_]+$")


def _to_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


class Atom(AtomBase):
    def __init__(self) -> None:
        self._context: AtomContext | None = None
        self._initialized = False
        self._running = False
        self._stores: list[dict[str, Any]] = []
        self._vacuum = False
        self._runs = 0
        self._removed_total = 0
        self._reclaimed_bytes = 0
        self._last_error = ""
        self._last_report: dict[str, int] = {}
        self._next_store_index = 0
        self._last_success: float | None = None
        self._clean_task: asyncio.Task | None = None
        self._skipped_while_busy = 0

    async def initialize(self, context: AtomContext) -> None:
        self._context = context
        cfg = _rebased_config(context.config)
        self._stores = [dict(s) for s in cfg["stores"]]
        self._vacuum = bool(cfg["vacuum_after_cleanup"])
        context.subscribe(EVENT_IN, self._on_archived)
        self._initialized = True

    async def start(self) -> None:
        if not self._initialized or self._running or self._context is None:
            return
        self._running = True

    async def stop(self) -> None:
        self._running = False
        # تنظيفٌ جارٍ يُمهَل ولا يُلغى: قطعُه في منتصف حذفٍ أو `VACUUM` يترك
        # قاعدةً نصفَ منظَّفة وملفًّا مؤقّتًا بجانبها.
        task, self._clean_task = self._clean_task, None
        if task is not None and not task.done():
            try:
                await task
            except Exception:  # noqa: BLE001 — الإيقاف لا يُسقطه خطأ دورة
                pass

    async def shutdown(self) -> None:
        await self.stop()

    def _clean_one(self, store: dict[str, Any]) -> tuple[int, int]:
        source = str(store.get("db_path", ""))
        table = str(store.get("table", ""))
        columns = [str(c) for c in store.get("dedup_columns", [])]
        if not source or not _IDENT.fullmatch(table) or not columns:
            raise ValueError("bad store spec: %s" % store)
        if not all(_IDENT.fullmatch(c) for c in columns):
            raise ValueError("bad column in: %s" % store)
        if not Path(source).is_file():
            raise FileNotFoundError(source)
        try:
            before = Path(source).stat().st_size
            # ‏⛔ قفل الملفّ — لا قفل هذه الذرّة. هذا الحذف يجري على قاعدةٍ
            # **يكتب فيها صاحبها في الوقت نفسه**: ٧١٢ يُدرج في `analysis.db`
            # و٧٠٧ في `decisions.db`. وما كان يمنع الاصطدام هو أنّ هذا العمل
            # كان يجري **داخل معالج الحدث** فتُسلسله حلقةُ العامل الواحدة
            # قسرًا. ولمّا أخرجتُه إلى مهمّة خلفيّة (`2.2.0`) سقط ذلك التسلسل:
            #
            #     ٢١:٢٧  ٧١٦ ينظّف ويحذف ٤٬٥١٥ صفًّا
            #     ٢١:٢٨  ٧١٢ معطّل: database is locked
            #     ٢٢:٥٧  ٧٠٧: قرار لم يُخزَّن — سبب=database is locked
            #
            # فيؤخذ قفل القاعدة نفسها، وهو الذي يأخذه كاتبوها في هذه العمليّة.
            with file_lock(source):
                connection = sqlite3.connect(source, timeout=_DB_TIMEOUT_S)
                connection.execute("PRAGMA busy_timeout=%d" % _BUSY_TIMEOUT_MS)
                try:
                    cursor = connection.execute(
                        "DELETE FROM %s WHERE id NOT IN ("
                        " SELECT MIN(id) FROM %s GROUP BY %s)"
                        % (table, table, ", ".join(columns)))
                    removed = cursor.rowcount or 0
                    connection.commit()
                    if removed and self._vacuum:
                        connection.execute("VACUUM")
                finally:
                    connection.close()
            after = Path(source).stat().st_size
            return removed, max(0, before - after)
        except (sqlite3.Error, OSError) as exc:
            raise RuntimeError("%s: %s" % (table, exc)) from exc

    def _run(self) -> tuple[dict[str, int], int]:
        report: dict[str, int] = {}
        reclaimed = 0
        for index in range(self._next_store_index, len(self._stores)):
            store = self._stores[index]
            removed, freed = self._clean_one(store)
            reclaimed += freed
            if removed:
                report[str(store.get("table", "?"))] = removed
            self._next_store_index = index + 1
        return report, reclaimed

    async def _on_archived(self, payload: dict[str, Any]) -> None:
        """التنظيف يُجدوَل ولا يُنتظَر — عملُ نصف دقيقةٍ لا يقع في معالج.

        مقيس ٢٠٢٦-٠٩-١٦ من عدّاد الناقل: **أسوأ مدّة معالجٍ لـ٧١٦ = ٣٠٫٠١
        ثانية** مقابل ميزانية ٠٫٠٥ — والعمل معروف: حذف تكرارات عبر المخازن،
        ومعه `VACUUM` حين يُطلب (مقيس على قاعدة ١٫٩ جيجا: **٢٥١٬٨٨٧ م.ث**).
        وتسليم الناقل يمضي بالتتابع على مسار العامل، فهذا الحجب يقع على كلّ
        ما خلفه. نفس علاج ٧١٤ v3.3.0 و٧١٥ v3.1.0 و٧١٧ v2.2.0: مهمّة خلفيّة
        بحارس «واحدة في آنٍ».
        """
        if not self._running or self._context is None:
            return
        if self._clean_task is not None and not self._clean_task.done():
            self._skipped_while_busy += 1
            return
        self._clean_task = asyncio.create_task(self._clean_and_report(payload))

    async def _clean_and_report(self, payload: dict[str, Any]) -> None:
        if self._context is None:
            return
        now = _to_float(payload.get("timestamp") if isinstance(payload, dict) else None)
        try:
            report, reclaimed = await asyncio.to_thread(self._run)
        except (OSError, ValueError, RuntimeError) as exc:
            self._last_error = str(exc)
            body: dict[str, Any] = {"removed": 0, "total": self._removed_total,
                "per_table": {}, "reclaimed_bytes": 0, "status": "FAILED",
                "reason": str(exc), "next_store_index": self._next_store_index,
                "last_success": self._last_success}
            if now is not None: body["timestamp"] = now
            await self._context.publish(EVENT_OUT, body)
            return
        removed = sum(report.values())
        self._runs += 1; self._removed_total += removed
        self._reclaimed_bytes += reclaimed; self._last_report = report
        self._last_error = ""; self._next_store_index = 0; self._last_success = now
        body = {"removed": removed, "total": self._removed_total,
                "per_table": dict(report), "reclaimed_bytes": reclaimed,
                "status": "CLEANED", "last_success": self._last_success}
        if now is not None: body["timestamp"] = now
        await self._context.publish(EVENT_OUT, body)

    async def snapshot(self) -> dict[str, Any]:
        return {"version": ATOM_VERSION, "next_store_index": self._next_store_index,
                "last_success": self._last_success, "runs": self._runs,
                "removed_total": self._removed_total,
                "reclaimed_bytes": self._reclaimed_bytes}

    async def restore(self, state: dict[str, Any]) -> None:
        if not isinstance(state, dict): raise ValueError("INVALID_DEDUPE_STATE")
        index = int(state.get("next_store_index") or 0)
        if index < 0 or index > len(self._stores): raise ValueError("INVALID_DEDUPE_STATE")
        self._next_store_index=index;self._last_success=_to_float(state.get("last_success"))
        self._runs=int(state.get("runs") or 0);self._removed_total=int(state.get("removed_total") or 0)
        self._reclaimed_bytes=int(state.get("reclaimed_bytes") or 0)

    async def health_check(self) -> HealthStatus:
        if not self._running:
            return HealthStatus(state=HealthState.UNHEALTHY, message=REASON_NOT_STARTED)
        details = {"runs": self._runs, "removed": self._removed_total,
                   "reclaimed_bytes": self._reclaimed_bytes, "stores": len(self._stores),
                   "last_report": dict(self._last_report), "last_error": self._last_error,
                   "next_store_index": self._next_store_index,
                   "last_success": self._last_success}
        if self._last_error:
            return HealthStatus(
                state=HealthState.DEGRADED, message=self._last_error, details=details)
        if self._runs == 0:
            index = self._next_store_index
            if index > 0:
                where = (str(self._stores[index].get("table") or "?")
                         if index < len(self._stores) else "?")
                message = ("READY - previous round incomplete; resume from store %s"
                           " (%d of %d) on next archive event | runs=0 resume=%d"
                           % (where, index + 1, len(self._stores), index))
            else:
                message = "READY_AWAITING_FIRST_ARCHIVE_EVENT | runs=0"
            return HealthStatus(
                state=HealthState.HEALTHY, message=message, details=details)
        return HealthStatus(
            state=HealthState.HEALTHY,
            message="runs=%d removed=%d" % (self._runs, self._removed_total),
            details=details)