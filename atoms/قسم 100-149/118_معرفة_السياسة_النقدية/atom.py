"""معرفة السياسة النقديّة (118) — حقائق خام عن الفيدراليّ والأخبار الأمريكيّة الكبرى: ماضيها وحاضرها ومواعيدها، بلا حكم.

٢٠٢٦-١٠-٠٨ (ختم المالك «NQ» — المعرفة أوّلًا): «قبل كلّ شي لازم يعرف النظام هاد الشي ثمّ الباقي» ·
«لازم يعرف شو صار بالماضي، وإيمتى مواعيد المستقبل، شو جاي».
الذرّة تعرف ولا تقرّر: لا تدخل قرار الدخول، ولا في حمولتها جهةٌ ولا وزنٌ ولا ثقة (عقد الحقائق ١٠-٠٧).
تنشر `knowledge.monetary.state` بعد ~30 ث من الإقلاع ومع كلّ `SYS_5MIN`.

المصادر — قراءةً فقط وفي خيطٍ جانبيّ (`monetary_sources.py`):
  · تقويم ميتاتريدر المحفوظ `nq_calendar_history.db` (المزامنة كلّ ساعة: 30 يومًا ماضية و180 قادمة).
  · جدول `calendar` في قاعدة الجسر `nq_brain.db` — القيمة الفعليّة لحظة صدورها لما لم تبلغه المزامنة بعد.
  · جدول `econ_calendar` في قاعدة الجسر (تقويم ناسداك، يكتبه بوت الأخبار) — **المصدر الأوّل** للفعليّ والإجماع
    الحقيقيّ (`monetary_consensus.py`)؛ وغيابه لا يغيّر شيئًا (`econ_calendar_available: false` بسببه).
والحساب دوالّ صافية (`monetary_facts.py`). التعرّف برمز الحدث مع `country_code='US'` لا بالاسم وحده (الرمز نفسه
تحمله دولٌ أخرى: آخر «consumer-price-index-ex-food-energy-mm» بلا تصفية الدولة كان أوروبيًّا 2026-10-02).
«المتوقَّع» توقّع الوسيط لا الإجماع (مقيس سابقًا: طابق مرّة من عشر) — فاسم الفرق «فرق الفعليّ عن توقّع الوسيط».
حدٌّ معلن: لا تسعير للقرار القادم — يحتاج مصدرًا لم يأذن به المالك (`fed_pricing_available: false`).
"""
from __future__ import annotations

import asyncio
import os
from typing import Any

import clock
import monetary_consensus
import monetary_facts
import monetary_sources
from core.contracts.atom import AtomBase, AtomContext, HealthState, HealthStatus

ATOM_VERSION = "1.0.0"
ATOM_ID = "118"
SYMBOL = "USTEC"
PAYLOAD_ID = "monetary_policy_knowledge"
SOURCE_NAME = ("mt5_calendar_history (nq_calendar_history.db) + bridge calendar (nq_brain.db) "
               "+ nasdaq econ_calendar (nq_brain.db)")
EV_PULSE = "SYS_5MIN"
EV_OUT = "knowledge.monetary.state"

STATUS_OK = "ok"
STATUS_UNAVAILABLE = "unavailable"
COMPUTE_FAILED = "COMPUTE_FAILED"
REASON_AR = {monetary_sources.NO_FILE: "قاعدة تقويم ميتاتريدر غير موجودة",
             monetary_sources.READ_FAILED: "تعذّرت قراءة قاعدة التقويم",
             COMPUTE_FAILED: "تعذّر حساب الحقائق من القاعدة"}
BAD_PULSE = "bad_pulse"
BUSY = "busy_skip"

DEFAULT_DB = r"%APPDATA%\MetaQuotes\Terminal\Common\Files\nq_calendar_history.db"
DEFAULT_BRIDGE_DB = r"%APPDATA%\MetaQuotes\Terminal\Common\Files\nq_brain.db"
DB_ENV = "NQ_CALENDAR_HISTORY_DB"                 # يسبق `config` (للاختبار أو مسارٍ آخر)
BRIDGE_ENV = "NQ_BRIDGE_DB"                       # مرسى الجسر في المشروع (يضبطه الإقلاع) يسبق `config`
BOOT_DELAY_S = 30.0                               # بعد اكتمال الإقلاع كلّه (مقيس ~7 ث) — كما 153
EA_SYNC_MODE = "hourly_ea"
SYNC_STALE_MIN = 150                              # المزامنة كلّ ساعة: أكثر من ساعتين ونصف بلا تحديث ⟸ توقّفت
DETAIL_CHARS = 160
WINDOW_H = monetary_facts.WINDOW_H


def resolve_db_path(configured: str | None) -> str:
    return os.environ.get(DB_ENV) or os.path.expandvars(configured or DEFAULT_DB)


def resolve_bridge_path(configured: str | None) -> str:
    return os.environ.get(BRIDGE_ENV) or os.path.expandvars(configured or DEFAULT_BRIDGE_DB)


def read_calendar(path: str, now: float, bridge_path: str = "") -> dict[str, Any]:
    """يُستدعى في `asyncio.to_thread`: التاريخ، ثمّ فعليّ الجسر، ثمّ فعليّ ناسداك وإجماعه (المصدر الأوّل) —
    وكلّ غيابٍ سببٌ مسمًّى لا استثناء. ٢٠٢٦-١٠-٠٨ (ختم المالك «NQ» — «عدّة مصادر تحت سقفٍ واحد»)."""
    raw = monetary_sources.read_sources(path, bridge_path, now, monetary_facts.RELEASE_CODES)
    if not raw.get("error"):
        groups = [raw["fed"], raw["past"], raw["ahead"], *raw["releases"].values()]
        raw["econ"] = monetary_consensus.merge(groups, monetary_consensus.read_econ(bridge_path, now))
    return raw


def build_payload(raw: dict[str, Any], now: float) -> dict[str, Any]:
    base = {"id": PAYLOAD_ID, "symbol": SYMBOL, "computed_at": now, "source": SOURCE_NAME}
    error = raw.get("error")
    if not error:
        try:
            facts = monetary_facts.build_facts(raw, now)
            return {**base, "status": STATUS_OK, "facts": facts, "summary_ar": monetary_facts.summary_ar(facts)}
        except (KeyError, TypeError, ValueError, IndexError, ZeroDivisionError) as exc:
            error, raw = COMPUTE_FAILED, {"detail": "%s: %s" % (type(exc).__name__, exc)}
    facts = {"source_available": False, "unavailable_reason": error,
             "unavailable_detail": str(raw.get("detail") or "")[:DETAIL_CHARS],
             "fed_pricing_available": False, "fed_pricing_unavailable_reason": monetary_facts.PRICING_REASON_AR}
    return {**base, "status": STATUS_UNAVAILABLE, "facts": facts,
            "summary_ar": "معرفة السياسة النقديّة غير متاحة: %s" % REASON_AR.get(error, error)}


class Atom(AtomBase):
    def __init__(self) -> None:
        self._context: AtomContext | None = None
        self._running = False
        self._db_config = DEFAULT_DB
        self._bridge_config = DEFAULT_BRIDGE_DB
        self._boot_delay_s = BOOT_DELAY_S
        self._clock = clock.now               # الساعة الرسميّة؛ والنبضة تحمل وقتها فيُقدَّم
        self._boot_task: asyncio.Future | None = None
        self._busy = False
        self._last: dict[str, Any] | None = None
        self._horizon: float | None = None
        self._exported: float | None = None
        self._sync_mode: str | None = None
        self._published = 0
        self._read_errors = 0
        self._rejected: dict[str, int] = {}

    async def initialize(self, context: AtomContext) -> None:
        self._context = context
        cfg = context.config or {}
        self._db_config = str(cfg.get("db_path") or DEFAULT_DB)
        self._bridge_config = str(cfg.get("bridge_db_path") or DEFAULT_BRIDGE_DB)
        self._boot_delay_s = float(cfg.get("boot_delay_s", BOOT_DELAY_S))
        context.subscribe(EV_PULSE, self._on_pulse)

    async def start(self) -> None:
        self._running = True
        # الإقلاع يبدأ الذرّات بترتيب أرقامها — فالنشر فورًا يسبق اشتراك من يسمع. يُؤجَّل كما 153.
        self._boot_task = asyncio.ensure_future(self._boot_refresh())
        self._boot_task.add_done_callback(self._task_done)

    async def stop(self) -> None:
        self._running = False
        if self._boot_task is not None and not self._boot_task.done():
            self._boot_task.cancel()

    async def shutdown(self) -> None:
        await self.stop()

    def _task_done(self, task: asyncio.Future) -> None:
        if not task.cancelled() and task.exception() is not None and self._context is not None:
            self._context.logger.error("118 boot refresh failed: %s", task.exception())

    async def _boot_refresh(self) -> None:
        try:
            await asyncio.sleep(self._boot_delay_s)
            if self._running:
                await self.refresh(self._clock())
        except asyncio.CancelledError:
            pass

    def _reject(self, reason: str) -> None:
        self._rejected[reason] = self._rejected.get(reason, 0) + 1

    async def _on_pulse(self, payload: dict[str, Any]) -> None:
        if not self._running or self._context is None:
            return
        if not isinstance(payload, dict):
            self._reject(BAD_PULSE)
            return
        await self.refresh(monetary_sources.num(payload.get("official_time")) or self._clock())

    async def refresh(self, now: float) -> dict[str, Any] | None:
        """قراءةٌ في خيطٍ جانبيّ ثمّ نشر. قراءةٌ لم تنتهِ بعد ⟸ النبضة تُعدّ وتُترك (لا تتراكم القراءات)."""
        if self._busy:
            self._reject(BUSY)
            return None
        self._busy = True
        try:
            raw = await asyncio.to_thread(read_calendar, resolve_db_path(self._db_config), now,
                                          resolve_bridge_path(self._bridge_config))
        finally:
            self._busy = False
        payload = build_payload(raw, now)
        ok = payload["status"] == STATUS_OK
        meta = raw.get("meta") or {}
        self._horizon = raw.get("horizon") if ok else None
        self._exported = monetary_sources.num(meta.get("exported_at_utc")) if ok else None
        self._sync_mode = meta.get("sync_mode") if ok else None
        if not ok:
            self._read_errors += 1
        self._last = payload
        if self._running and self._context is not None:
            await self._context.publish(EV_OUT, payload)
            self._published += 1
        return payload

    async def snapshot(self) -> dict[str, Any]:
        return {"version": ATOM_VERSION, "last": self._last, "published": self._published,
                "read_errors": self._read_errors, "rejected": dict(self._rejected)}

    async def restore(self, state: dict[str, Any]) -> None:
        if not isinstance(state, dict):
            return
        last = state.get("last")
        if isinstance(last, dict) and last.get("id") == PAYLOAD_ID and isinstance(last.get("facts"), dict):
            self._last = last
        self._published = int(monetary_sources.num(state.get("published")) or 0)
        self._read_errors = int(monetary_sources.num(state.get("read_errors")) or 0)
        rejected = state.get("rejected")
        if isinstance(rejected, dict):
            self._rejected = {str(k): int(monetary_sources.num(v) or 0) for k, v in rejected.items()}

    def _problems(self) -> list[str]:
        """ما يجعل المعرفة متدهورة: أفقٌ انقضى، أو مزامنةٌ ساعيّة توقّفت."""
        now = self._clock()
        out = []
        if self._horizon is not None and self._horizon <= now:
            out.append("أفق التقويم انتهى")
        if self._sync_mode == EA_SYNC_MODE and (self._exported is None or now - self._exported > SYNC_STALE_MIN * 60):
            out.append("مزامنة التقويم الساعيّة متوقّفة منذ %s د" % (
                "؟" if self._exported is None else int((now - self._exported) // 60)))
        return out

    async def health_check(self) -> HealthStatus:
        if not self._running:
            return HealthStatus(state=HealthState.UNHEALTHY, message="NOT_STARTED")
        counters = "نشرات=%d · أخطاء قراءة=%d · نبضات متروكة=%s" % (
            self._published, self._read_errors,
            " ".join("%s=%d" % kv for kv in sorted(self._rejected.items())) or "0")
        details = {"published": self._published, "read_errors": self._read_errors,
                   "rejected": dict(self._rejected), "db_path": resolve_db_path(self._db_config),
                   "bridge_db_path": resolve_bridge_path(self._bridge_config)}
        last = self._last
        if last is None:
            return HealthStatus(state=HealthState.DEGRADED, details=details,
                                message="لم يُقرأ تقويم ميتاتريدر بعد (القراءة الأولى بعد ~%d ث من الإقلاع) · %s" % (
                                    int(self._boot_delay_s), counters))
        facts = last.get("facts") or {}
        if last.get("status") != STATUS_OK:
            return HealthStatus(state=HealthState.DEGRADED, details=details,
                                message="%s · %s" % (last.get("summary_ar"), counters))
        bridge = ("الجسر: صفوف 3 أيّام=%s بقيمة=%s ومُلئ منه=%s" % (
            facts.get("bridge_rows_3d"), facts.get("bridge_rows_3d_with_actual"), facts.get("actuals_from_bridge"))
                  if facts.get("bridge_available") else "الجسر غير متاح (%s)" % facts.get("bridge_unavailable_reason"))
        bridge += (" · ناسداك: صفوف=%s مطابَقة=%s غير مطابَقة=%s عمرها %s د خلافات=%d" % (
            facts.get("econ_calendar_rows"), facts.get("econ_calendar_matched"), facts.get("econ_calendar_unmatched"),
            facts.get("econ_calendar_age_minutes"), len(facts.get("sources_disagree") or []))
                   if facts.get("econ_calendar_available")
                   else " · ناسداك غير متاح (%s)" % facts.get("econ_calendar_unavailable_reason"))
        message = ("الفائدة %s · قرارات=%s · الاجتماع القادم %s · عالية الأهمّيّة في %d س=%s · خطابات=%s · "
                   "ما هو جاي في 30 يومًا=%s · صدر في 30 يومًا=%s · المزامنة=%s قبل %s د وأفقها %s (%s يومًا) · %s · %s") % (
            facts.get("fed_rate_current"), facts.get("fed_decisions_count"),
            facts.get("next_fomc_date_utc") or "غير معروف في المصدر", WINDOW_H,
            facts.get("high_impact_next_48h_count"), facts.get("fed_speeches_next_48h_count"),
            facts.get("coming_30d_count"), (facts.get("last_30d_high_impact") or {}).get("n"),
            facts.get("sync_mode") or "تصديرٌ لمرّة", facts.get("sync_age_minutes"),
            facts.get("calendar_horizon_utc"), facts.get("calendar_days_ahead"), bridge, counters)
        problems = self._problems()
        if problems:
            return HealthStatus(state=HealthState.DEGRADED, details=details,
                                message=" · ".join(problems) + " — " + message)
        return HealthStatus(state=HealthState.HEALTHY, message=message, details=details)
