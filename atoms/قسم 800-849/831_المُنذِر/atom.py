from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
import tempfile
import time
from typing import Any

from core.contracts.atom import AtomBase, AtomContext, HealthState, HealthStatus

ATOM_VERSION = "1.1.0"
# ٢٠٢٦-١٠-٠٢ (ختم المالك «صلح كامل nq»): شكلُ السجلّ في 1.1 هو شكلُ 1.0 وزيادة حقولٍ
# اختياريّة (`aged` · `aged_at` · `subjects`)، فلقطة 1.0 تُستعاد كما هي. رفضُها كان
# يُسقط إقلاع 831 في العمليّة الباردة (كما وقع ٢٠٢٦-٠٩-٢٣ 19:36 مع رفع 1.0.3).
_COMPATIBLE_LINES = ("1.0", "1.1")


def _version_line(value: object) -> str:
    """«1.0.4» ⟵ «1.0»: خطّ الإصدار الذي يحمل شكل السجلّ نفسه."""
    parts = str(value or "").split(".")
    return ".".join(parts[:2]) if len(parts) >= 2 else ""

EVENT_ALERT = "system.alert"
EVENT_STATE = "system.alert.state"
EVENT_RECOVERED = "system.alert.recovered"
EVENT_SWEEP = "SYS_5MIN"

_SEVERITY_CRITICAL = "critical"
_SEVERITY_WARNING = "warning"
_SEVERITY_INFO = "info"
_SEVERITIES = (_SEVERITY_CRITICAL, _SEVERITY_WARNING, _SEVERITY_INFO)

# source event -> (default severity, publisher atom id)
# publisher ids verified against each manifest `publishes` (2026-08-24)
_MONITORED: dict[str, tuple[str, int]] = {
    "storage.persistence.save_failed": (_SEVERITY_CRITICAL, 706),
    "tools.integrity.violation": (_SEVERITY_CRITICAL, 7),
    "tools.backup.failed": (_SEVERITY_CRITICAL, 800),
    "tools.file_archive.failed": (_SEVERITY_CRITICAL, 802),
    "tools.file_cleanup.failed": (_SEVERITY_CRITICAL, 803),
    "market_data.validation_failed": (_SEVERITY_CRITICAL, 112),
    # ٢٠٢٦-١٠-٠٧ (ختم «NQ»): خرج structure.validation_failed (209) وliquidity.validation_failed (259) —
    # ناشراهما أُرشفا مع فكّ الأقسام عن القرار؛ وإنذارٌ قائمٌ لهما في لقطةٍ قديمة تُسقطه الاستعادة.
    "time.utc.stale": (_SEVERITY_CRITICAL, 608),
    "time.ntp.drift": (_SEVERITY_WARNING, 608),
    # ٢٠٢٦-٠٩-٢٣ (ختم `nq`): حارس الهامش صار 526 (كان 585) بختم `nq 525+526+527`.
    "financial.truth.shortage": (_SEVERITY_CRITICAL, 526),
    "core.integrity.alert": (_SEVERITY_CRITICAL, 1),
    "tools.storage.low": (_SEVERITY_WARNING, 6),
    "market_data.quality_alert": (_SEVERITY_WARNING, 115),
    "time.clock.divergence": (_SEVERITY_WARNING, 111),
    "storage.symbol.unmapped": (_SEVERITY_WARNING, 708),
    # ٢٠٢٦-١٠-٠٢ (ختم المالك «صلح كامل nq»): أحداث فشلٍ بلا مستمع أو لا يسمعها إلّا
    # الخطّ الزمنيّ 704 (خريطة الأحداث ١-د) — ما تقول حمولتُه «فشل» بلا تأويل وحده.
    # الناشر 0 = النواة نفسها (`core/health_manager.py` · `core/bootloader.py` · `core/api`).
    "core.atom.failed": (_SEVERITY_CRITICAL, 0),
    "core.atom.unhealthy": (_SEVERITY_WARNING, 0),
    "core.critical_atom.unhealthy": (_SEVERITY_CRITICAL, 0),
    "core.atom.restarts_exhausted": (_SEVERITY_CRITICAL, 0),
    "core.atom.restart_failed": (_SEVERITY_CRITICAL, 0),
    "market.feed.source_rejected": (_SEVERITY_WARNING, 613),
    "execution.confirmation.rejected": (_SEVERITY_CRITICAL, 563),
    # ولم يُضف `execution.reference_divergence.state` (582): حالةٌ تُنشر مع كلّ تحديث
    # لا حدثُ فشل، و`observe_only`، وأغلبها `STALE` (٩٨٫٧٪ مقيسًا ٠٩-١٦)؛ والمالك
    # تركه بلا مستمع عمدًا «حتى يقرّر» (`governance/checks/check_events.py:86-88`).
    # ولا `market.feed.provider_down` (613) ولا `market_data.feed_interrupted` (116):
    # يسمعهما الخطّ الزمنيّ 704، ويستردّان أنفسهما خلال دقيقتين — مقيس في 704 من ٠٩-١٦
    # إلى ١٠-٠٢: ‏599 سقوطًا مقابل 597 عودة (يوميًّا 20:59→21:01 UTC)، و1,684 انقطاعًا
    # مقابل 1,675 عودة (≈١٠٥ يوميًّا). إنذارٌ حرجٌ يظهر ويختفي مئة مرّةٍ في اليوم يُعلَّم
    # تجاهله — وهو ما يُطفئ الإنذار الحقيقيّ.
}

# ٢٠٢٦-١٠-٠٢ (ختم المالك «صلح كامل nq»): الإنذار لا يُمحى بمرور الساعة — يُمحى بحدث
# نجاح ناشره نفسه. كان الكنس يعلن «استردادًا» بعد ساعة صمت، فالفشل اليوميّ (النسخ)
# يظهر ساعةً ثمّ يختفي وهو قائم: أربعة عشر يومًا بلا نسخة ولا إنذار في الحالة الحيّة.
# حدث النجاح ⟵ ما يمحوه. كلّ زوجٍ مقروءٌ من كود ناشره لا مفترض.
_RECOVERY: dict[str, tuple[str, ...]] = {
    "tools.backup.completed": ("tools.backup.failed",),                 # 800
    "tools.file_archive.completed": ("tools.file_archive.failed",),     # 802
    "tools.file_cleanup.completed": ("tools.file_cleanup.failed",),     # 803
    "tools.storage.recovered": ("tools.storage.low",),                  # 006
    "core.atom.started": ("core.atom.failed", "core.atom.unhealthy",
                          "core.critical_atom.unhealthy",
                          "core.atom.restarts_exhausted", "core.atom.restart_failed"),
    "core.atom.restarted": ("core.atom.failed", "core.atom.unhealthy",
                            "core.critical_atom.unhealthy",
                            "core.atom.restarts_exhausted", "core.atom.restart_failed"),
}
# موضوعُ الإنذار في الحمولة: ذرّةٌ بعينها. استردادُ ذرّةٍ لا يمحو إنذار جارتها —
# يُمحى الإنذار حين لا يبقى له موضوعٌ قائم.
_SUBJECT_KEY: dict[str, str] = {
    "core.atom.failed": "atom_id", "core.atom.unhealthy": "atom_id",
    "core.critical_atom.unhealthy": "atom_id", "core.atom.restarts_exhausted": "atom_id",
    "core.atom.restart_failed": "atom_id",
}
_SUBJECTS_MAX = 64
# الإنذار القديم بلا تكرار يُخفَّض في العرض درجةً ولا يُمحى.
_AGED_DISPLAY = {_SEVERITY_CRITICAL: _SEVERITY_WARNING,
                 _SEVERITY_WARNING: _SEVERITY_INFO, _SEVERITY_INFO: _SEVERITY_INFO}

_DEFAULT_COOLDOWN_S = 300.0
_DEFAULT_EXPIRY_S = 3600.0
BARE_STATE_FILE = "var/alerts/system_alerts.json"
_DEFAULT_STATE_FILE = (lambda _p=Path(__file__).resolve(): __import__("shared.runtime_paths", fromlist=["anchored_state_path"]).anchored_state_path(BARE_STATE_FILE, code_root=_p))()

_DETAIL_KEYS = ("error", "message", "reason", "detail")
_DETAIL_MAX = 300


def _subject_of(event: str, payload: Any) -> str:
    """موضوعُ الإنذار من الحمولة (رقم الذرّة) — فراغٌ إن لم يكن له موضوع."""
    key = _SUBJECT_KEY.get(event)
    if not key or not isinstance(payload, dict):
        return ""
    value = payload.get(key)
    return "" if value in (None, "") else str(value).strip()


def _extract_detail(payload: Any) -> str:
    if not isinstance(payload, dict):
        return ""
    for key in _DETAIL_KEYS:
        value = payload.get(key)
        if value in (None, ""):
            continue
        text = str(value).strip()
        if not text:
            continue
        return text[:_DETAIL_MAX]
    return ""


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
        self._running = False
        self._cooldown_s = _DEFAULT_COOLDOWN_S
        self._expiry_s = _DEFAULT_EXPIRY_S
        self._state_file = _DEFAULT_STATE_FILE
        self._severity_overrides: dict[str, str] = {}
        self._active: dict[str, dict[str, Any]] = {}
        self._file_error: str | None = None
        self._last_health = HealthStatus(
            state=HealthState.UNKNOWN, message="NOT_INITIALIZED")
        # ٢٠٢٦-١٠-٠٩ (ختم المالك «NQ» — الصيانة في استراحة السوق): ملفّ الحالة لا يُكتب على الحلقة.
        # هذه الذرّة تبقى في عمليّة النواة الساخنة، وكانت تنشئ ملفًّا وتكتبه وتعيد تسميته **على خيط
        # الحلقة مع كلّ حدث فشل** — ومنها `market_data.validation_failed` (112) و`quality_alert` (115)
        # بالعشرات في الدقيقة (99,413 حدثًا في يومين، لقطة ٠٢-١٠). وحين يختنق القرص ليلًا (03:00)
        # تعلق إعادة التسمية عشرات الثواني فتتجمّد المنصّة، ويُتّهم 112 و115: يتنازلان داخل النشر
        # (`_maybe_yield` في الناقل البارد) فيجري هذا المعالج بينهما ويعودان بعده بالزمن كلّه.
        # الآن: مهمّةٌ واحدة تكتب **الأحدث** في خيط، وما تراكم أثناء كتابتها يُدمج ويُعدّ — والأخير
        # يُكتب دائمًا (ويُنتظر عند الإيقاف)، فلا فقد.
        self._pending_state: dict[str, Any] | None = None
        self._writer: asyncio.Task | None = None
        self.state_writes = 0
        self.state_coalesced = 0

    # ── lifecycle ────────────────────────────────────────────────────────────

    async def initialize(self, context: AtomContext) -> None:
        self._context = context
        config = _rebased_config(context.config)
        self._cooldown_s = float(config.get(
            "cooldown_seconds", _DEFAULT_COOLDOWN_S))
        self._expiry_s = float(config.get("expiry_seconds", _DEFAULT_EXPIRY_S))
        self._state_file = str(_rebased_config(context.config).get("state_file", _DEFAULT_STATE_FILE))
        overrides = config.get("severity_overrides") or {}
        if isinstance(overrides, dict):
            self._severity_overrides = {
                str(event): str(sev)
                for event, sev in overrides.items()
                if str(sev) in _SEVERITIES and str(event) in _MONITORED
            }
        for event in _MONITORED:
            context.subscribe(event, self._handler_for(event))
        # ٢٠٢٦-١٠-٠٢ (ختم المالك «صلح كامل nq»): أحداث النجاح هي وحدها ما يمحو.
        for event in _RECOVERY:
            context.subscribe(event, self._recovery_for(event))
        context.subscribe(EVENT_SWEEP, self._on_sweep)

    async def start(self) -> None:
        self._running = True
        if self._context is not None and self._active:
            await self._publish_state()

    async def stop(self) -> None:
        self._running = False
        await self.flush_state()

    async def shutdown(self) -> None:
        await self.stop()

    async def flush_state(self) -> None:
        """ينتظر حتّى تُكتب آخر حالة — عند الإيقاف وفي الاختبار؛ لا يُنادى من معالج حدث."""
        while self._writer is not None and not self._writer.done():
            # درعٌ: إلغاءُ المنتظِر (سقف دورة الحياة) لا يلغي الكاتب في منتصف كتابته.
            await asyncio.shield(self._writer)

    # ── events ───────────────────────────────────────────────────────────────

    def _handler_for(self, event: str):
        async def _handler(payload: dict[str, Any]) -> None:
            await self._on_failure(event, payload)
        return _handler

    def _severity(self, event: str) -> str:
        override = self._severity_overrides.get(event)
        if override:
            return override
        return _MONITORED.get(event, (_SEVERITY_INFO, 0))[0]

    async def _on_failure(self, event: str, payload: dict[str, Any]) -> None:
        if not self._running or self._context is None:
            return
        now = time.time()
        record = self._active.get(event)
        if record is None:
            record = {"severity": self._severity(event), "count": 0,
                      "first_at": now, "last_at": now,
                      "last_emitted": 0.0, "detail": ""}
            self._active[event] = record
        record["count"] = int(record.get("count", 0)) + 1
        record["last_at"] = now
        # ٢٠٢٦-١٠-٠٢ (ختم المالك «صلح كامل nq»): تكرارٌ جديد يعيد الإنذار إلى درجته،
        # ويُضاف موضوعه (رقم الذرّة) ليُمحى بنجاحه هو لا بنجاح جاره.
        record.pop("aged", None)
        record.pop("aged_at", None)
        subject = _subject_of(event, payload)
        if subject:
            subjects = list(record.get("subjects") or [])
            if subject not in subjects and len(subjects) < _SUBJECTS_MAX:
                subjects.append(subject)
            record["subjects"] = subjects
        detail = _extract_detail(payload)
        if detail:
            record["detail"] = detail
        if now - float(record.get("last_emitted", 0.0)) >= self._cooldown_s:
            record["last_emitted"] = now
            await self._context.publish(EVENT_ALERT, {
                "source_event": event,
                "source_atom": _MONITORED.get(event, (_SEVERITY_INFO, 0))[1],
                "severity": record["severity"],
                "count": record["count"],
                "first_at": record["first_at"],
                "last_at": now,
                "detail": record["detail"],
                "active_total": len(self._active),
                "atom_version": ATOM_VERSION,
            })
        await self._publish_state()

    def _recovery_for(self, event: str):
        async def _handler(payload: dict[str, Any]) -> None:
            await self._on_recovery(event, payload)
        return _handler

    async def _on_recovery(self, event: str, payload: dict[str, Any]) -> None:
        """حدث نجاحٍ من ناشر الفشل نفسه — هو وحده ما يمحو الإنذار.

        ٢٠٢٦-١٠-٠٢ (ختم المالك «صلح كامل nq»): الإنذار ذو الموضوع (رقم الذرّة)
        يُنقص موضوعَ النجاح وحده، ويُمحى حين لا يبقى موضوعٌ قائم. ونجاحٌ لا إنذار له
        لا ينشر شيئًا — `core.atom.started` يصل بالمئات عند كلّ إقلاع.
        """
        if not self._running or self._context is None:
            return
        cleared: list[str] = []
        for failure in _RECOVERY.get(event, ()):
            record = self._active.get(failure)
            if record is None:
                continue
            subjects = list(record.get("subjects") or [])
            if subjects:
                subject = _subject_of(failure, payload)
                if subject not in subjects:
                    continue
                subjects.remove(subject)
                record["subjects"] = subjects
                if subjects:
                    continue
            self._active.pop(failure, None)
            cleared.append(failure)
        if not cleared:
            return
        await self._context.publish(EVENT_RECOVERED, {
            "recovered": sorted(cleared),
            "by": event,
            "subject": _subject_of(cleared[0], payload),
            "total": len(self._active),
            "atom_version": ATOM_VERSION,
        })
        await self._publish_state()

    async def _on_sweep(self, _payload: dict[str, Any]) -> None:
        """الإنذار الصامت يشيخ ولا يُمحى.

        ٢٠٢٦-١٠-٠٢ (ختم المالك «صلح كامل nq»): كان الكنس يمحو ما صمت ساعةً ويعلنه
        «مستردًّا» بلا حدث نجاح (`expiry_seconds`). فشلٌ يُنشر مرّةً في اليوم (النسخ ·
        أرشفة الملفّات) كان يظهر ساعةً ثمّ يختفي وهو قائم — والملفّ المؤقّت المتروك من
        ٠٩-٢٩ يُظهر `tools.file_archive.failed` ثمّ لا شيء. الآن تجاوزُ المهلة يُعلّم
        الإنذار `aged` ويُخفّض درجة عرضه (`display_severity`) ولا يمسّه؛ والمحو بحدث
        النجاح وحده (`_on_recovery`).
        """
        if not self._running or self._context is None:
            return
        now = time.time()
        aged = [event for event, record in self._active.items()
                if not record.get("aged")
                and now - float(record.get("last_at", 0.0)) >= self._expiry_s]
        if not aged:
            return
        for event in aged:
            self._active[event]["aged"] = True
            self._active[event]["aged_at"] = now
        await self._publish_state()

    async def _publish_state(self) -> None:
        if self._context is None:
            return
        state = {
            "atom": self._context.atom_id,
            "atom_version": ATOM_VERSION,
            "total": len(self._active),
            "alerts": {
                event: {
                    "severity": record["severity"],
                    "source_atom": _MONITORED.get(event, (_SEVERITY_INFO, 0))[1],
                    "count": record["count"],
                    "first_at": record["first_at"],
                    "last_at": record["last_at"],
                    "detail": record["detail"],
                    # ٢٠٢٦-١٠-٠٢ (ختم المالك «صلح كامل nq»): الشيخوخة تُخفّض العرض لا الإنذار.
                    "aged": bool(record.get("aged")),
                    "display_severity": (_AGED_DISPLAY.get(record["severity"], _SEVERITY_INFO)
                                         if record.get("aged") else record["severity"]),
                    "subjects": list(record.get("subjects") or []),
                }
                for event, record in sorted(self._active.items())
            },
        }
        await self._context.publish(EVENT_STATE, state)
        self._schedule_persist(state)

    def _schedule_persist(self, state: dict[str, Any]) -> None:
        """٢٠٢٦-١٠-٠٩ (ختم المالك «NQ» — الصيانة في استراحة السوق): يضع الأحدث ويمضي — بلا قرص."""
        if self._pending_state is not None:
            self.state_coalesced += 1
        self._pending_state = state
        if self._writer is None or self._writer.done():
            self._writer = asyncio.get_running_loop().create_task(self._drain_state())

    async def _drain_state(self) -> None:
        """كاتبٌ واحد في آنٍ: يكتب الأحدث في خيط، ثمّ ما جاء أثناءه، حتّى لا يبقى شيء."""
        while self._pending_state is not None:
            state, self._pending_state = self._pending_state, None
            await asyncio.to_thread(self._persist, state)
            self.state_writes += 1

    def _persist(self, state: dict[str, Any]) -> None:
        if self._context is None:
            return
        path = self._state_file
        try:
            parent = os.path.dirname(os.path.abspath(path))
            os.makedirs(parent, exist_ok=True)
            fd, tmp = tempfile.mkstemp(
                prefix=".system_alerts_", suffix=".tmp", dir=parent)
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as fh:
                    json.dump(state, fh, ensure_ascii=False)
                os.replace(tmp, path)
            except BaseException:
                try:
                    os.unlink(tmp)
                except OSError:
                    pass
                raise
            if self._file_error is not None:
                self._file_error = None
                self._context.logger.info(
                    "ALERT_STATE_FILE_RECOVERED path=%s", path)
        except OSError as exc:
            self._file_error = str(exc)
            self._context.logger.error(
                "ALERT_STATE_FILE_WRITE_FAILED path=%s error=%s", path, exc)

    # ── reporting / persistence ──────────────────────────────────────────────

    async def health_check(self) -> HealthStatus:
        if self._context is None:
            return self._last_health
        active = len(self._active)
        # ٢٠٢٦-١٠-٠٩ (ختم المالك «NQ» — الصيانة في استراحة السوق): كم كُتب الملفّ وكم دُمج — معلنًا.
        writes = " · ملفّ الحالة: كُتب %d ودُمج %d" % (self.state_writes, self.state_coalesced)
        details = {"active": active, "state_writes": self.state_writes,
                   "state_coalesced": self.state_coalesced}
        if self._file_error is not None:
            self._last_health = HealthStatus(
                state=HealthState.DEGRADED,
                message=f"ALERT_STATE_FILE_WRITE_FAILED: {self._file_error}" + writes,
                details=details)
        else:
            self._last_health = HealthStatus(
                state=HealthState.HEALTHY,
                message=f"{active} active alert(s)" + writes,
                details=details)
        return self._last_health

    async def snapshot(self) -> dict[str, Any]:
        return {
            "version": ATOM_VERSION,
            "active": {event: dict(record) for event, record in
                       self._active.items()},
            "file_error": self._file_error,
        }

    async def restore(self, state: dict[str, Any]) -> None:
        if not isinstance(state, dict):
            raise ValueError("INVALID_ALERT_AGGREGATOR_STATE")
        # ٢٠٢٦-٠٩-٢٣ (ختم nq، v1.0.4): كان يشترط الإصدار حرفًا، فرفعُ الإصدار
        # إلى 1.0.3 (تصحيح وسمٍ لا يمسّ شكل السجلّ) رمى الاستعادة — والعمليّة
        # الباردة تعدّ رمي الاستعادة فشلَ إقلاع: «فشل [831]» في إقلاع ١٩:٣٦،
        # فبقيت المنصّة بلا مُنذِر. شكلُ السجلّ ثابتٌ في خطّ 1.0، فيُقبل ما كان
        # منه ويُفحص سجلًّا سجلًّا كما هو؛ وما خرج عن الخطّ يُرفض كما كان.
        if _version_line(state.get("version")) not in _COMPATIBLE_LINES:
            raise ValueError("INVALID_ALERT_AGGREGATOR_STATE")
        raw = state.get("active")
        if not isinstance(raw, dict):
            raise ValueError("INVALID_ALERT_AGGREGATOR_STATE")
        restored: dict[str, dict[str, Any]] = {}
        for event, record in raw.items():
            event = str(event)
            if event not in _MONITORED:
                continue
            if not isinstance(record, dict):
                raise ValueError("INVALID_ALERT_AGGREGATOR_STATE")
            severity = str(record.get("severity") or _SEVERITY_INFO)
            if severity not in _SEVERITIES:
                raise ValueError("INVALID_ALERT_AGGREGATOR_STATE")
            count = int(record.get("count", 0))
            first_at = float(record.get("first_at", 0.0))
            last_at = float(record.get("last_at", 0.0))
            last_emitted = float(record.get("last_emitted", 0.0))
            if min(count, first_at, last_at, last_emitted) < 0:
                raise ValueError("INVALID_ALERT_AGGREGATOR_STATE")
            restored[event] = {
                "severity": severity,
                "count": count,
                "first_at": first_at,
                "last_at": last_at,
                "last_emitted": last_emitted,
                "detail": str(record.get("detail") or "")[:_DETAIL_MAX],
            }
            # ٢٠٢٦-١٠-٠٢ (ختم المالك «صلح كامل nq»): حقول 1.1 اختياريّة — لقطة 1.0 بلاها.
            if record.get("aged"):
                restored[event]["aged"] = True
                restored[event]["aged_at"] = float(record.get("aged_at") or last_at)
            subjects = record.get("subjects")
            if isinstance(subjects, list) and subjects:
                restored[event]["subjects"] = [str(s) for s in subjects][:_SUBJECTS_MAX]
        self._active = restored
        file_error = state.get("file_error")
        self._file_error = str(file_error) if file_error else None
