"""ذاكرة الناسداك الموسميّة (119) — ما يعرفه النظام عن «اليوم والشهر والساعة» من تاريخ الناسداك نفسه.

٢٠٢٦-١٠-٠٨ (ختم المالك «NQ» — المعرفة أوّلًا): «قبل كلّ شي لازم يعرف النظام هاد الشي ثمّ الباقي» — الوقت
والمواسم والعطل. حقائق خامٌ تُختم على كلّ صفقة ولا تدخل قرار الدخول (عقد الحقائق ١٠-٠٧: لا جهة ولا وزن).

تبني ذاكرتها عند الإقلاع (بعد مهلة `boot_delay_s`، في خيطٍ منفصل فلا تحجز الحلقة) ومرّةً كلّ يوم (SYS_DAY)،
وتنشر `knowledge.seasonal.state` عند البناء ومع كلّ SYS_HOUR:
  اليوم من الأسبوع (كلّ التاريخ وآخر 3 سنوات) · الشهر · الساعة بتوقيت نيويورك · الأيّام الخاصّة (قبل العطلة
  وبعدها · قرار الفائدة · الجمعة الثالثة · آخر الشهر وأوّله) · مدى اليوم حتّى آخر ساعة مغلقة مقابل متوسّط يومه.
لا نظر إلى المستقبل: الذاكرة من الأيّام المغلقة قبل يوم الوسيط الجاري وحدها؛ وإن جاءت لحظةٌ أقدم من الذاكرة
(إعادةٌ تاريخيّة) أُعيد البناء عندها قبل النشر. الحساب كلّه في `seasonal_memory.py` و`seasonal_facts.py`.
"""
from __future__ import annotations

import asyncio
import math
import os
import time
from pathlib import Path
from typing import Any

from core.contracts.atom import AtomBase, AtomContext, HealthState, HealthStatus
import seasonal_facts
import seasonal_memory

ATOM_VERSION = "1.0.0"
ATOM_ID = "119"
PAYLOAD_ID = "nasdaq_seasonal_memory"

EV_HOUR = "SYS_HOUR"
EV_DAY = "SYS_DAY"
EV_OUT = "knowledge.seasonal.state"

SOURCE = "ctrader_history.candles_history (D1+H1) · nq_calendar_history.calendar_history"
DEFAULT_SYMBOL = "USTEC"
DEFAULT_HISTORY_DB = "forex_runtime\\var\\history\\ctrader_history.db"
DEFAULT_CALENDAR_DB = "%APPDATA%\\MetaQuotes\\Terminal\\Common\\Files\\nq_calendar_history.db"
DEFAULT_HISTORY_FROM = "2014-09-22"
#: جذر المشروع — المسار النسبيّ في البيان يُقرأ منه (atoms/قسم/الذرّة/atom.py).
PROJECT_ROOT = Path(__file__).resolve().parents[3]
BOOT_TASK = "boot"


def _resolve(raw: Any) -> str:
    text = os.path.expandvars(str(raw or "").strip())
    if not text:
        return ""
    path = Path(text)
    return str(path if path.is_absolute() else PROJECT_ROOT / path)


def _official(payload: Any) -> float | None:
    """الساعة الرسميّة من نبضة الوقت — وبلاها يُرمى المدخل ويُعدّ."""
    if not isinstance(payload, dict):
        return None
    try:
        value = float(payload.get("official_time"))
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) and value > 0 else None


class Atom(AtomBase):
    def __init__(self) -> None:
        self._context: AtomContext | None = None
        self._running = False
        self._symbol = DEFAULT_SYMBOL
        self._history_db = ""
        self._calendar_db = ""
        self._history_from = seasonal_memory.parse_date(DEFAULT_HISTORY_FROM)
        self._recent_years = 3
        self._boot_delay_s = 30.0
        self._clock = time.time
        self._memory: dict[str, Any] | None = None
        self._building = False
        self._tasks: dict[str, asyncio.Task] = {}
        self._published = 0
        self._builds = 0
        self._rejected = 0
        self._skipped = 0
        self._failed = 0
        self._last_payload: dict[str, Any] | None = None
        self._last_error = ""

    # ── دورة الحياة ─────────────────────────────────────────────────────
    async def initialize(self, context: AtomContext) -> None:
        self._context = context
        cfg = context.config or {}
        self._symbol = str(cfg.get("symbol", DEFAULT_SYMBOL) or DEFAULT_SYMBOL).upper()
        self._history_db = _resolve(cfg.get("history_db", DEFAULT_HISTORY_DB))
        self._calendar_db = _resolve(cfg.get("calendar_db", DEFAULT_CALENDAR_DB))
        self._history_from = seasonal_memory.parse_date(cfg.get("history_from", DEFAULT_HISTORY_FROM))
        self._recent_years = max(1, int(cfg.get("recent_years", 3)))
        self._boot_delay_s = max(0.0, float(cfg.get("boot_delay_s", 30.0)))
        context.subscribe(EV_HOUR, self._on_hour)
        context.subscribe(EV_DAY, self._on_day)

    async def start(self) -> None:
        self._running = True
        self._spawn(BOOT_TASK, self._boot())

    def _spawn(self, name: str, coro: Any) -> None:
        task = asyncio.create_task(coro)
        self._tasks[name] = task
        task.add_done_callback(self._task_done)

    def _task_done(self, task: asyncio.Task) -> None:
        for name, held in list(self._tasks.items()):
            if held is task:
                self._tasks.pop(name, None)
        if task.cancelled() or task.exception() is None:
            return
        exc = task.exception()
        self._last_error = "%s: %s" % (type(exc).__name__, exc)
        if self._context is not None:
            self._context.logger.warning("119 مهمّة الإقلاع تعثّرت: %s", self._last_error)

    async def stop(self) -> None:
        self._running = False
        for task in list(self._tasks.values()):
            task.cancel()
        self._tasks.clear()

    async def shutdown(self) -> None:
        await self.stop()

    # ── البناء والنشر ───────────────────────────────────────────────────
    async def _boot(self) -> None:
        # الإقلاع يبدأ الذرّات واحدةً بعد واحدة — البناء بعد المهلة، والقراءة الثقيلة في خيطٍ منفصل.
        await asyncio.sleep(self._boot_delay_s)
        if self._running and await self._rebuild(self._clock()):
            await self._publish(self._clock())

    async def _rebuild(self, now: float) -> bool:
        if self._building:
            self._skipped += 1
            return False
        self._building = True
        try:
            memory = await asyncio.to_thread(
                seasonal_memory.build_memory, self._history_db, self._calendar_db, self._symbol,
                self._history_from, self._recent_years, now)
        except Exception as exc:  # noqa: BLE001 — عطلٌ في البناء حقيقة «غير متاح» معلنة لا انهيار
            self._last_error = "%s: %s" % (type(exc).__name__, exc)
            memory = {"status": seasonal_memory.STATUS_UNAVAILABLE, "reason": "build_failed: %s" % self._last_error}
        finally:
            self._building = False
        self._memory = memory
        self._builds += 1
        return True

    async def _publish(self, now: float) -> None:
        memory = self._memory
        if memory is None or self._context is None:
            return
        today = None
        try:
            if memory.get("status") == seasonal_memory.STATUS_OK:
                today = await asyncio.to_thread(seasonal_memory.today_range, self._history_db, self._symbol, now)
            facts, summary, status = seasonal_facts.facts_at(memory, now, today)
        except Exception as exc:  # noqa: BLE001 — الذرّة حيّة: التعثّر يُعدّ ويُعلن في الصحّة ولا يكسر النبضة
            self._failed += 1
            self._last_error = "%s: %s" % (type(exc).__name__, exc)
            return
        payload = {"id": PAYLOAD_ID, "symbol": self._symbol, "status": status, "facts": facts,
                   "computed_at": now, "summary_ar": summary, "source": SOURCE}
        await self._context.publish(EV_OUT, payload)
        self._published += 1
        self._last_payload = payload

    async def _on_hour(self, payload: dict[str, Any]) -> None:
        if not self._running or self._context is None:
            return
        now = _official(payload)
        if now is None:
            self._rejected += 1
            return
        if self._memory is None:
            self._skipped += 1                     # الذاكرة تُبنى بعد مهلة الإقلاع
            return
        stale = self._memory.get("status") != seasonal_memory.STATUS_OK
        if stale or seasonal_memory.broker_day_start(now) < (self._memory.get("cut") or 0.0):
            # مصدرٌ كان غائبًا يُعاد طلبه كلّ ساعة، ولحظةٌ أقدم من الذاكرة تُبنى ذاكرتها عندها (لا مستقبل).
            await self._rebuild(now)
        await self._publish(now)

    async def _on_day(self, payload: dict[str, Any]) -> None:
        if not self._running or self._context is None:
            return
        now = _official(payload)
        if now is None:
            self._rejected += 1
            return
        if await self._rebuild(now):
            await self._publish(now)

    # ── الحالة ──────────────────────────────────────────────────────────
    async def snapshot(self) -> dict[str, Any]:
        # الذاكرة نفسها تُبنى من القاعدة عند كلّ إقلاع؛ يُحفظ ما عرفته آخر مرّة وعدّاداتها.
        return {"version": ATOM_VERSION, "published": self._published, "builds": self._builds,
                "rejected": self._rejected, "skipped": self._skipped, "failed": self._failed,
                "last_payload": self._last_payload}

    async def restore(self, state: dict[str, Any]) -> None:
        if not isinstance(state, dict):
            return
        for key in ("published", "builds", "rejected", "skipped", "failed"):
            try:
                setattr(self, "_" + key, int(state.get(key) or 0))
            except (TypeError, ValueError):
                setattr(self, "_" + key, 0)
        last = state.get("last_payload")
        self._last_payload = last if isinstance(last, dict) else None

    async def health_check(self) -> HealthStatus:
        counters = "نُشرت=%d · بُنيت=%d · مرميّات=%d · مؤجّلة=%d · تعثّرت=%d" % (
            self._published, self._builds, self._rejected, self._skipped, self._failed)
        if self._last_error:
            counters += " (آخر تعثّر: %s)" % self._last_error
        details = {"published": self._published, "builds": self._builds, "rejected": self._rejected,
                   "skipped": self._skipped, "failed": self._failed, "last_error": self._last_error,
                   "history_db": self._history_db, "calendar_db": self._calendar_db}
        if not self._running:
            return HealthStatus(state=HealthState.UNHEALTHY, message="NOT_STARTED", details=details)
        memory = self._memory
        if memory is None:
            return HealthStatus(state=HealthState.DEGRADED, details=details, message=(
                "الذاكرة لم تُبنَ بعد (تُبنى بعد %.0f ث من الإقلاع) · %s" % (self._boot_delay_s, counters)))
        if memory.get("status") != seasonal_memory.STATUS_OK:
            return HealthStatus(state=HealthState.DEGRADED, details=details, message=(
                "غير متاحة: %s · %s" % (memory.get("reason"), counters)))
        try:
            cal = memory["calendar"]
            known = ("تعرف %d يومًا (من %s إلى %s) و%d شمعة ساعة · %s" % (
                memory["days_n"], memory["history_from"], memory["history_through"], memory["hours_n"],
                "%d عطلة و%d قرار فائدة حتّى %s" % (len(cal["holidays"]), len(cal["fomc"]), cal["through"])
                if cal.get("available") else "التقويم غير متاح: %s" % cal.get("reason")))
            details.update({"days_n": memory["days_n"], "hours_n": memory["hours_n"], "build_s": memory["build_s"]})
        except (KeyError, TypeError) as exc:
            return HealthStatus(state=HealthState.DEGRADED, details=details, message=(
                "ذاكرةٌ ناقصة (%s) · %s" % (exc, counters)))
        last = (self._last_payload or {}).get("summary_ar") or ""
        return HealthStatus(state=HealthState.HEALTHY, details=details, message="%s · بُنيت في %.2f ث · %s · %s" % (
            known, memory["build_s"], counters, last))
