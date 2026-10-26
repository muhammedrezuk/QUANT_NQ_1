from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Any

from core.contracts.atom import AtomBase, AtomContext, HealthState, HealthStatus

ATOM_VERSION = "1.2.0"

EVENT_DECISION = "trading.final_decision"
EVENT_MANAGE = "execution.manage.command"
EVENT_EXTRACT = "asset.extraction.requested"
EVENT_FULL = "asset.full_extraction.requested"
EVENT_WRITTEN = "platform.brain_signal.written"
EVENT_TRADE = "platform.trade_event"
EVENT_PORTFOLIO = "asset.portfolio.state"
# ٢٠٢٦-٠٩-٢٣ (ختم `nq`): رُفع `perpetual.owner.escalation` — ناشره الوحيد ٥٧٨
# أُرشف بختم المالك (٢٠٢٦-٠٩-١٨)، واللوحة رفعته من محرّكها يومها للسبب نفسه.
EVENT_OUT = "audit.trail.state"

REASON_NOT_STARTED = "NOT_STARTED"

_KEY_SEP = "|"
_PUBLISH_TAIL = 50
_FIELDS = ("account_id", "symbol", "side", "volume", "action", "ticket",
           "stop_loss", "amount", "milestone", "origin", "request_id",
           "state", "prev_state", "protection_intent", "reason",
           "event_type", "profit", "target")


def _summary(payload: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for field in _FIELDS:
        if field in payload and payload[field] is not None:
            out[field] = payload[field]
    return out


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
    # ٢٠٢٦-٠٩-٢٣ — رُفع حقنُ `sys.path` من هنا: وزنٌ ميّت لا حماية.
    # `scripts/run_forex.py:9-11` ثمّ `governance/scripts/run_core.py:19-22`
    # يضعان جذرَ المشروع في رأس المسار عند كلّ إقلاع، وهو بعينه
    # `code_root` أدناه — فالشرطُ لا يتحقّق أبدًا. ونصُّ النواة صريح
    # (`core/bootloader.py:252`): لا حاجة لأن تحقن الذرّة المسارَ بنفسها.
    try:
        from shared.runtime_paths import manifest_config_rebase
        return manifest_config_rebase(raw_cfg, code_root=code_root)
    except Exception:  # noqa: BLE001 — لا يُعطَّل الإقلاع بأزمة مسار
        return raw_cfg


class Atom(AtomBase):
    def __init__(self) -> None:
        self._context: AtomContext | None = None
        self._running = False
        self._log_path = ""
        self._max_memory = 100
        self._recent: list[dict[str, Any]] = []
        self._seq = 0
        self._write_failures = 0

    async def initialize(self, context: AtomContext) -> None:
        self._context = context
        cfg = _rebased_config(context.config)
        self._log_path = str(cfg.get("log_path", os.path.join("var", "audit", "perpetual.jsonl")))
        self._max_memory = int(cfg.get("max_memory", 100))
        parent = os.path.dirname(self._log_path)
        if parent:
            try:
                os.makedirs(parent, exist_ok=True)
            except OSError as exc:
                context.logger.warning("522 makedirs failed: %s", exc)
        context.subscribe(EVENT_DECISION, self._on_decision)
        context.subscribe(EVENT_MANAGE, self._on_manage)
        context.subscribe(EVENT_EXTRACT, self._on_extract)
        context.subscribe(EVENT_FULL, self._on_full)
        context.subscribe(EVENT_WRITTEN, self._on_written)
        context.subscribe(EVENT_TRADE, self._on_trade)
        context.subscribe(EVENT_PORTFOLIO, self._on_portfolio)

    async def start(self) -> None:
        self._running = True

    async def stop(self) -> None:
        self._running = False

    async def shutdown(self) -> None:
        await self.stop()

    def _append_disk(self, line: str) -> None:
        with open(self._log_path, "a", encoding="utf-8") as handle:
            handle.write(line + "\n")

    async def _record(self, kind: str, payload: dict[str, Any]) -> None:
        if self._context is None:
            return
        self._seq += 1
        entry: dict[str, Any] = {"seq": self._seq, "kind": kind}
        entry.update(_summary(payload))
        stamp = payload.get("timestamp")
        if stamp is not None:
            entry["ts"] = stamp
        self._recent.append(entry)
        if len(self._recent) > self._max_memory:
            self._recent = self._recent[-self._max_memory:]
        try:
            await asyncio.to_thread(self._append_disk, json.dumps(entry, ensure_ascii=False))
        except OSError as exc:
            self._write_failures += 1
            self._context.logger.warning("522 audit write failed: %s", exc)
        tail = min(self._max_memory, _PUBLISH_TAIL)
        await self._context.publish(EVENT_OUT, {"recent": self._recent[-tail:], "total": self._seq})

    async def _on_decision(self, payload: dict[str, Any]) -> None:
        if self._running and isinstance(payload, dict):
            await self._record("order", payload)

    async def _on_manage(self, payload: dict[str, Any]) -> None:
        if self._running and isinstance(payload, dict):
            await self._record("manage", payload)

    async def _on_extract(self, payload: dict[str, Any]) -> None:
        if self._running and isinstance(payload, dict):
            await self._record("extract", payload)

    async def _on_full(self, payload: dict[str, Any]) -> None:
        if self._running and isinstance(payload, dict):
            await self._record("full_extract", payload)

    async def _on_written(self, payload: dict[str, Any]) -> None:
        if self._running and isinstance(payload, dict):
            await self._record("written", payload)

    async def _on_trade(self, payload: dict[str, Any]) -> None:
        if self._running and isinstance(payload, dict):
            await self._record("trade_event", payload)

    async def _on_portfolio(self, payload: dict[str, Any]) -> None:
        if not self._running or not isinstance(payload, dict):
            return
        portfolios = payload.get("portfolios")
        if not isinstance(portfolios, list):
            return
        for pf in portfolios:
            if isinstance(pf, dict) and pf.get("changed"):
                await self._record("state_change", pf)

    async def health_check(self) -> HealthStatus:
        if not self._running:
            return HealthStatus(state=HealthState.UNHEALTHY, message=REASON_NOT_STARTED)
        details = {"recorded": self._seq, "write_failures": self._write_failures,
                   "log_path": self._log_path}
        if self._write_failures > 0 and self._seq == 0:
            return HealthStatus(state=HealthState.DEGRADED, message="audit disk unwritable",
                                details=details)
        return HealthStatus(state=HealthState.HEALTHY,
                            # ٢٠٢٦-٠٩-١٦ (فحص شامل ٤٥٠–٥٩٩): `write_failures` كان في
            # `details` وحدها — والنواة تحذفها. فسجلّ التدقيق قد يفشل في
            # الكتابة مرارًا والشارة تقول `recorded=N` كأنّ شيئًا لم يكن.
            # سجلٌّ لا يُكتب أسوأ من سجلٍّ لا يوجد: يُظنّ موجودًا.
            message="recorded=%d%s" % (
                self._seq,
                " ⚠ فشل كتابة=%d" % self._write_failures if self._write_failures else ""),
            details=details)
