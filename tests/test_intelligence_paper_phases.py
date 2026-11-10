# -*- coding: utf-8 -*-
"""ورقة الذكاء (منظومة المراقبة الذاتية والتكيّف الآمن) — قبول الأطوار.

كل طور يُقاس على بوّاباته الخمس (وظيفيّ · سلامة بيانات · أداء · أمان · أثريّة)
بأحداث حقيقيّة على ناقل النواة — والقياس الحتميّ للمحاكاة (بناء ٢) هو أرضيّة
عدم التراجع (§31): نفس المقطع مرّتين مع الطبقة التكيّفيّة كاملة = نفس القرارات.
"""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path
from typing import Any

import pytest

from core.contracts.atom import AtomContext
from core.event_bus import EventBus

ROOT = Path(__file__).resolve().parents[1]
from build_registry.paths import RegistryAtomRoot
ATOM_ROOT = RegistryAtomRoot(ROOT)



class _Log:
    def __getattr__(self, _n: str):
        return lambda *a, **k: None


def load_atom(atom_id: int):
    folder = next((ATOM_ROOT).glob(f"{atom_id}_*/atom.py"))
    sys.path.insert(0, str(folder.parent))
    try:
        spec = importlib.util.spec_from_file_location(f"intel_atom_{atom_id}", folder)
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path.pop(0)


class AdaptiveStack:
    """الناقل + ذرّات الورقة الستّ (810→860).

    ٢٠٢٦-١٠-٠٧ (ختم المالك «NQ»): خرجت سلسلة القرار القديمة (150·166·451) من الحزمة — أُرشفت
    مع فكّ الأقسام عن القرار؛ تبقى طبقة القياس والتكيّف التي تقيسها الورقة.
    """

    def __init__(self, tmp: Path):
        self.tmp = tmp
        self.bus = EventBus()
        self.modules = {i: load_atom(i) for i in (810, 820, 830, 840, 850, 860)}
        self.atoms: dict[int, Any] = {}
        self.captured: dict[str, list[dict]] = {}

    def on(self, event: str, bucket: str) -> None:
        self.captured.setdefault(bucket, []).clear()
        self.bus.subscribe(event, self.captured[bucket].append, subscriber="probe")

    async def start(self) -> None:
        configs = {
            810: {"out_dir": str(self.tmp / "telemetry"), "batch_size": 5,
                  "flush_interval_s": 1.0, "max_files": 4, "max_buffer": 100},
            820: {"window": 50, "stale_after_s": 60, "warming_min": 2},
            830: {"entry_threshold": 70, "exit_threshold": 45,
                  "confirmation_window": 3, "min_duration_s": 0.0,
                  "volatility_high": 75},
            840: {"warmup_windows": 2, "drift_threshold": 0.5},
            850: {"min_evidence_windows": 1, "max_change_per_step": 0.25,
                  "max_change_per_day": 0.5, "max_active_experiments": 2,
                  "min_dwell_s": 0.0, "cooldown_s": 0.0, "max_changes_per_window": 5},
            860: {"critical_drift": 1.0, "latency_budget_ms": 50.0},
        }
        for atom_id, module in self.modules.items():
            atom = module.Atom()
            self.atoms[atom_id] = atom
            await atom.initialize(AtomContext(
                atom_id, configs[atom_id], _Log(),
                lambda name, payload, aid=atom_id: self.bus.publish(name, payload, publisher=str(aid)),
                lambda name, handler, aid=atom_id: self.bus.subscribe(name, handler, subscriber=str(aid)),
                subscribe_all=self.bus.subscribe_all))
            await atom.start()

    async def feed_tick(self, sequence: str, price: float = 100.0, ts: float = 1.0) -> None:
        await self.bus.publish("market.tick.validated", {
            "account_id": "A", "broker": "BR", "symbol": "NQ",
            "timeframe": "tick", "sequence": sequence,
            "timestamp": ts, "price": price}, publisher="112")
        # (nq seal 2026-08-25: EventBus 1.18.0 enqueues to per-handler mailboxes;
        # drain() replaces sleep(0) so delivery completes before the next feed.)
        await self.bus.drain()

    async def feed_analysis_card(self, ts: float, ready: bool = True) -> None:
        await self.bus.publish("analysis.section.live", {
            "account_id": "A", "broker": "BR", "symbol": "NQ", "section_id": "150",
            "status": "ok", "signal": "up", "score": 70, "confidence": 72,
            "quality": "good", "state": "READY" if ready else "ANALYZING",
            "ready": ready, "timestamp": ts,
            "unified": {"state": "READY" if ready else "ANALYZING",
                        "direction": 60.0, "strength": 70.0, "weight": 16.66,
                        "weight_effect": 16.66 if ready else 0.0}}, publisher="150")
        await self.bus.drain()  # (nq seal 2026-08-25: async mailbox delivery)


@pytest.mark.asyncio
async def test_phase1_observability_contract(tmp_path: Path):
    """الطور ١ — عقد المشاهدة: الظرف الثماني عشر حقلًا، والمجهول معلَن بالاسم."""
    from shared.observability_contract import (ENVELOPE_FIELDS, core_state_of,
                                               stamp_observability)
    card = stamp_observability({"signal": "up"}, atom_id="150", section_id="150",
                               latency_ms=1.2)
    assert card["signal"] == "up"
    env = card["observability"]
    assert env["atom_id"] == "150" and env["latency_ms"] == 1.2
    # غير المقيس معلَن بالاسم — لا صفر مخترع (قاعدة §9)
    assert "regime_id" in card["observability_unknown"]
    assert "calibration_version" in card["observability_unknown"]
    assert set(ENVELOPE_FIELDS) >= {"atom_id", "section_id", "regime_id",
                                    "calibration_version", "technical_health"}
    # خريطة الحالات العشر → حدود النواة الأربع (قرار المراجعة — النواة لا تُمسّ)
    assert core_state_of("WARMING") == "DEGRADED"
    assert core_state_of("INSUFFICIENT_DATA") == "UNKNOWN"
    assert core_state_of("HEALTHY") == "HEALTHY"


@pytest.mark.asyncio
async def test_phase2_telemetry_batches_never_touch_hot_path(tmp_path: Path):
    """الطور ٢ — ناقل القياس: دفعات تُكتب خارج مخازن الإنتاج، والذاكرة محدودة."""
    stack = AdaptiveStack(tmp_path); await stack.start()
    stack.on("telemetry.batch.closed", "batches")

    for i in range(12):
        await stack.feed_analysis_card(ts=1.0 + i)
        await stack.feed_tick(sequence=str(i), ts=1.0 + i)
    await stack.atoms[810]._flush()
    # (nq seal 2026-08-25: batch.closed is enqueued by the sealed bus — drain
    # before asserting the probe captured it.)
    await stack.bus.drain()

    # ٢٠٢٦-١٠-٠٧ (ختم المالك «NQ»): خرج شطر «القرار صدر رغم طبقة القياس» — شاهده 451 مؤرشف مع فكّ الأقسام عن القرار.
    # بوابة سلامة البيانات: دفعة مكتوبة خارج var/store وبصمة أثر محفوظة
    assert stack.captured["batches"] and stack.captured["batches"][-1]["rows"] > 0
    tel_dir = tmp_path / "telemetry"
    assert tel_dir.is_dir() and list(tel_dir.rglob("*.jsonl.gz"))
    assert not any((ROOT / "var" / "store").rglob("telemetry-*"))
    # بوابة الأداء: العازلة محدودة السقف والترياق معدود
    health = await stack.atoms[810].health_check()
    assert health.details["buffered"] <= 100


# ٢٠٢٦-١٠-٠٧ (ختم المالك «NQ»): خرج اختبار test_phase3_measurement_three_levels_unknown_declared — يختبر قياس 820 لصحّة بطاقة القسم 150 (analysis.section.live) المؤرشفة مع فكّ الأقسام عن القرار.


@pytest.mark.asyncio
async def test_phase4_regime_hysteresis_no_flip_flop(tmp_path: Path):
    """الطور ٤ — محرك النظام: الحسميات تمنع التذبذب، ولا صلاحية له على شيء."""
    stack = AdaptiveStack(tmp_path); await stack.start()
    stack.on("market.regime.state", "regime")

    async def trend(value: float):
        await stack.bus.publish("structure.trend.state", {
            "symbol": "NQ", "direction": value, "score": value}, publisher="201")
        await stack.bus.drain()  # (nq seal 2026-08-25: async mailbox delivery)

    await trend(80)   # فوق عتبة الدخول — تأكيد 1/3
    await trend(80)   # 2/3
    await trend(80)   # 3/3 → TRANSITION يكتمل إلى TRENDING
    states = [p["regime"] for p in stack.captured["regime"]]
    assert "TRENDING" in states, states
    # اهتزاز تحت عتبة الخروج مرّتين فقط — لا يرتد فورًا (نافذة التأكيد)
    await trend(50); await trend(50)
    latest = stack.captured["regime"][-1]
    assert latest["regime"] in ("TRENDING", "TRANSITION"), latest
    # §14: الناقل يعلن في حمولته نفسها أنه بلا صلاحية
    assert "OBSERVATION_ONLY" in latest["authority"]


@pytest.mark.asyncio
async def test_phase5_and_6_drift_proposal_governor_kill_switch(tmp_path: Path):
    """الطوران ٥ و٦ — الانحراف يقترح، الحاكم يحكم بحدوده، والمفتاح يوقف
    التكيّف وحده والتداول مستمر."""
    stack = AdaptiveStack(tmp_path); await stack.start()
    stack.on("drift.vector.state", "drift")
    stack.on("experiment.state", "experiments")
    stack.on("decision.aggregated.state", "decisions")

    gov = stack.atoms[850]
    drift = stack.atoms[840]

    # بناء خط الأساس ثم تدهور حادّ في الجاهزية
    for i in range(3):
        await stack.atoms[820]._emit("150") if False else None
        await stack.bus.publish("measurement.health.state", {
            "section": "150", "state": "HEALTHY",
            "technical_health": "HEALTHY", "analytical_health": "HEALTHY",
            "trading_utility": "UNKNOWN", "ready_ratio": 0.95, "samples": 10},
            publisher="820")
        await stack.bus.drain()  # (nq seal 2026-08-25: async mailbox delivery)
    for i in range(3):
        await stack.bus.publish("measurement.health.state", {
            "section": "150", "state": "HEALTHY",
            "technical_health": "HEALTHY", "analytical_health": "DEGRADED",
            "trading_utility": "UNKNOWN", "ready_ratio": 0.10, "samples": 10},
            publisher="820")
        await stack.bus.drain()  # (nq seal 2026-08-25: async mailbox delivery)

    assert stack.captured["drift"], "لم يُقس انحراف"
    last = stack.captured["drift"][-1]
    assert last["overall_drift"] is not None and last["overall_drift"] > 0

    # الحاكم حكم: في حدود السلطته — APPROVED_FOR_SHADOW كحدّ أقصى، أو رفض برمز
    assert stack.captured["experiments"]
    verdict = stack.captured["experiments"][-1]
    assert verdict["status"] in ("APPROVED_FOR_SHADOW", "REJECTED")
    assert verdict["max_authority"] == "APPROVED_FOR_SHADOW"
    assert isinstance(verdict["gates"], list) and verdict["gates"]

    # §27: أمر المالك يُسقط المفتاح — والحاكم يرفض كل جديد بعده
    await stack.bus.publish("adaptation.kill_switch.command",
                            {"owner": "owner", "action": "OFF"}, publisher="owner")
    await stack.bus.drain()  # (nq seal 2026-08-25: async mailbox delivery)
    kill = stack.atoms[860]
    assert kill._adaptation_off
    # والتداول مستمر رغم إيقاف التكيّف.
    # ٢٠٢٦-١٠-٠٧ (ختم المالك «NQ» — فكّ الأقسام عن القرار): كان البرهان قرارًا من 451 بعد
    # الإيقاف، و451 أُرشفت. البرهان الآن أقوى من قرارٍ واحد: لا ذرّة على مسار المال الجديد
    # (البطاقة 414 ⟵ 467 ⟵ 555 ⟵ الحرّاس ⟵ 601، والأثلاث 574) تشترك بأيّ حدثٍ تنشره طبقة
    # المراقبة والتكيّف (810–860) — فلا طريق لمفتاح التكيّف إلى أيّ صفقة.
    def _events(atom_id: str, key: str) -> set[str]:
        import yaml
        manifest = yaml.safe_load(next(ATOM_ROOT.glob(f"{atom_id}_*/manifest.yaml")).read_text(encoding="utf-8"))
        return {e if isinstance(e, str) else (e.get("event") or e.get("name")) for e in (manifest.get(key) or [])}
    adaptive = set().union(*(_events(a, "publishes") for a in ("810", "811", "820", "830", "831", "840", "850", "860")))
    assert "adaptation.kill_switch.state" in adaptive
    for atom_id in ("414", "467", "555", "527", "526", "516", "551", "525", "552", "601", "574"):
        assert not (_events(atom_id, "subscribes") & adaptive), f"التداول تأثّر بمفتاح التكيّف عبر {atom_id} — ممنوع"

    # إعادة التسليح بأمر المالك وحده
    await stack.bus.publish("adaptation.kill_switch.command",
                            {"owner": "owner", "action": "ON"}, publisher="owner")
    await stack.bus.drain()  # (nq seal 2026-08-25: async mailbox delivery)
    assert not kill._adaptation_off
    # أمر مجهول الهوية يُرفض ويُحصى — لا تسلّيح خفيًّا
    await stack.bus.publish("adaptation.kill_switch.command",
                            {"action": "OFF"}, publisher="who")
    await stack.bus.drain()  # (nq seal 2026-08-25: async mailbox delivery)
    assert not kill._adaptation_off
    assert kill._drop_reasons.get("KILL_SWITCH_COMMAND_INVALID") == 1


# ٢٠٢٦-١٠-٠٧ (ختم المالك «NQ»): خرج اختبار test_non_regression_full_stack_same_decisions_twice — يختبر حتميّة قرارات 451 (decision.aggregated.state) المؤرشفة مع فكّ الأقسام عن القرار.
