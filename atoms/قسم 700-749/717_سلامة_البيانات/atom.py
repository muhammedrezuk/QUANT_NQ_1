from __future__ import annotations

import asyncio
import re
import sqlite3
from pathlib import Path
from typing import Any

import clock
from core.contracts.atom import AtomBase, AtomContext, HealthState, HealthStatus


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

EVENT_IN = "storage.trading_data_cleaned"
EVENT_OUT = "storage.trading_data_integrity_checked"

VERDICT_SOUND = "SOUND"
VERDICT_SUSPECT = "SUSPECT"

FLAG_UNREADABLE = "UNREADABLE"
FLAG_CORRUPT = "INTEGRITY_FAILED"
FLAG_NO_STAMP = "ROWS_WITHOUT_STAMP"
FLAG_FUTURE = "ROWS_IN_THE_FUTURE"
FLAG_EMPTY = "TABLE_EMPTY"

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
        self._stores: list[dict[str, str]] = []
        self._warn_on_empty = False
        self._runs = 0
        self._last_report: dict[str, dict[str, Any]] = {}
        self._last_flags: list[str] = []
        self._check_task: asyncio.Task | None = None
        self._skipped_while_busy = 0

    async def initialize(self, context: AtomContext) -> None:
        self._context = context
        cfg = _rebased_config(context.config)
        self._stores = [dict(s) for s in cfg["stores"]]
        self._warn_on_empty = bool(cfg["warn_on_empty_table"])
        # ٢٠٢٦-٠٩-٠١ (توحيد الشغلين): هذا السطر كان محذوفًا في النسخة الواردة
        # مع إصلاح الساعة، فصارت الذرّة **طرشاء**: لا تشترك على حدث دخلها
        # إطلاقًا، فلا تُشغَّل ولا تنشر تقرير سلامة واحدًا — أي حارس بيانات
        # قائم على الورق وغائب فعليًّا. (مقيس: `test_16_integrity_guard_...`
        # يسقط بـ`IndexError` لأن `EVENT_OUT` لم يُنشَر قطّ.) أُعيد كما كان.
        context.subscribe(EVENT_IN, self._on_cleaned)
        self._initialized = True

    async def start(self) -> None:
        if not self._initialized or self._running or self._context is None:
            return
        self._running = True

    async def stop(self) -> None:
        self._running = False
        # الفحص قراءةٌ فقط، فقطعُه لا يُفسد قاعدةً — لكنّه يترك تقريرًا نصفَ
        # مبنيّ يُنشَر أو لا يُنشَر. يُمهَل حتى ينتهي؛ لا يطول بلا حدّ.
        task, self._check_task = self._check_task, None
        if task is not None and not task.done():
            try:
                await task
            except Exception:  # noqa: BLE001 — الإيقاف لا يُسقطه خطأ دورة
                pass

    async def shutdown(self) -> None:
        await self.stop()

    def _check_one(self, store: dict[str, str], now: float | None) -> dict[str, Any]:
        source = store.get("db_path", "")
        table = store.get("table", "")
        time_col = store.get("time_column", "occurred_at")
        result: dict[str, Any] = {"rows": 0, "flags": []}
        if not source or not _IDENT.match(table) or not _IDENT.match(time_col):
            result["flags"].append(FLAG_UNREADABLE)
            return result
        if not Path(source).is_file():
            result["flags"].append(FLAG_UNREADABLE)
            return result
        try:
            connection = sqlite3.connect(source, timeout=_DB_TIMEOUT_S)
            connection.execute("PRAGMA busy_timeout=%d" % _BUSY_TIMEOUT_MS)
            try:
                verdict = connection.execute("PRAGMA integrity_check").fetchone()
                if not verdict or str(verdict[0]).lower() != "ok":
                    result["flags"].append(FLAG_CORRUPT)
                rows = connection.execute("SELECT COUNT(*) FROM %s" % table).fetchone()[0]
                result["rows"] = rows
                if rows == 0:
                    if self._warn_on_empty:
                        result["flags"].append(FLAG_EMPTY)
                    return result
                missing = connection.execute(
                    "SELECT COUNT(*) FROM %s WHERE %s IS NULL"
                    % (table, time_col)).fetchone()[0]
                if missing:
                    result["without_stamp"] = missing
                    result["flags"].append(FLAG_NO_STAMP)
                if now is not None:
                    ahead = connection.execute(
                        "SELECT COUNT(*) FROM %s WHERE %s > ?"
                        % (table, time_col), (now,)).fetchone()[0]
                    if ahead:
                        result["in_the_future"] = ahead
                        result["flags"].append(FLAG_FUTURE)
            finally:
                connection.close()
        except (sqlite3.Error, OSError) as exc:
            result["error"] = str(exc)
            result["flags"].append(FLAG_UNREADABLE)
        return result

    def _run(self, now: float | None) -> dict[str, dict[str, Any]]:
        return {store.get("table", "?"): self._check_one(store, now)
                for store in self._stores}

    async def _on_cleaned(self, payload: dict[str, Any]) -> None:
        """الفحص يُجدوَل ولا يُنتظَر — عملُ نصف دقيقةٍ لا يقع في معالج.

        مقيس ٢٠٢٦-٠٩-١٦ من عدّاد الناقل: **أسوأ مدّة معالجٍ لـ٧١٧ = ٣٠٫٠٣
        ثانية** مقابل ميزانية ٠٫٠٥ — والعمل معروف: عدٌّ وفحصُ سلامةٍ عبر كلّ
        المخازن، وأحدها تجاوز الجيجا. وتسليم الناقل يمضي بالتتابع على مسار
        العامل، فهذا الحجب يقع على كلّ ما خلفه. نفس علاج ٧١٤ v3.3.0 و٧١٥
        v3.1.0: مهمّة خلفيّة بحارس «واحدة في آنٍ».
        """
        if not self._running or self._context is None:
            return
        if self._check_task is not None and not self._check_task.done():
            self._skipped_while_busy += 1
            return
        self._check_task = asyncio.create_task(self._check_and_report())

    async def _check_and_report(self) -> None:
        if self._context is None:
            return
        # NEVER derive "now" from the event's delivery timestamp: that stamp
        # describes publication history, not the current wall-clock authority.
        now = clock.now()
        report = await asyncio.to_thread(self._run, now)
        flags = sorted({f for r in report.values() for f in r["flags"]})
        self._runs += 1
        self._last_report = report
        self._last_flags = flags
        body: dict[str, Any] = {
            "tables": len(report),
            "rows_total": sum(r.get("rows", 0) for r in report.values()),
            "per_table": {k: dict(v) for k, v in report.items()},
            "flags": flags,
            "verdict": VERDICT_SUSPECT if flags else VERDICT_SOUND,
            "official_time": now,
            "clock_quality": clock.quality(),
        }
        await self._context.publish(EVENT_OUT, body)

    async def health_check(self) -> HealthStatus:
        if not self._running:
            return HealthStatus(state=HealthState.UNHEALTHY, message=REASON_NOT_STARTED)
        details = {
            "runs": self._runs,
            "flags": list(self._last_flags),
            "stores": len(self._stores),
            "clock": clock.state(),
            "last_report": {k: dict(v) for k, v in self._last_report.items()},
        }
        if self._runs == 0:
            return HealthStatus(
                state=HealthState.HEALTHY,
                message="READY_AWAITING_FIRST_CLEANUP_EVENT | runs=0",
                details=details)
        if self._last_flags:
            return HealthStatus(
                state=HealthState.DEGRADED, message=",".join(self._last_flags),
                details=details)
        return HealthStatus(
            state=HealthState.HEALTHY,
            message="runs=%d verdict=%s" % (self._runs, VERDICT_SOUND), details=details)