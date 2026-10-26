from __future__ import annotations

import sys

import asyncio
import importlib.util
import json
import sqlite3
from pathlib import Path
from typing import Any

import clock
import pytest
import yaml

from shared.live_analysis import (
    AnalysisSettingsStore,
    DEFAULT_WEIGHTS,
    EVENT_SETTING_CHANGED,
    EVENT_SETTINGS,
    EVENT_TICK,
    LiveAnalyzerKernel,
    STATE_ANALYZING,
    STATE_NOT_READY,
    STATE_READY,
    STATE_STALE,
)

ROOT = Path(__file__).resolve().parents[1]
from build_registry.paths import RegistryAtomRoot
ATOM_ROOT = RegistryAtomRoot(ROOT)

ANALYZERS = {
    151: "trend", 152: "momentum", 153: "volatility", 154: "volume",
    155: "spread", 156: "candle", 157: "gap", 158: "session", 159: "time",
    160: "correlation", 161: "relative_strength", 162: "velocity",
    163: "acceleration", 164: "volume_quality", 165: "noise",
}
EVENTS = {
    "trend": "analysis.trend.state", "momentum": "analysis.momentum.state",
    "volatility": "analysis.volatility.state", "volume": "analysis.volume.state",
    "spread": "analysis.spread.state", "candle": "analysis.candle.state",
    "gap": "analysis.gap.state", "session": "analysis.session.state",
    "time": "analysis.time.state", "velocity": "analysis.velocity.state",
    "acceleration": "analysis.acceleration.state",
    "volume_quality": "analysis.volume_quality.state", "noise": "analysis.noise.state",
    "correlation": "analysis.correlation.state",
    "relative_strength": "analysis.relative_strength.state",
}


def load_atom(atom_id: int):
    path = next((ATOM_ROOT).glob(f"{atom_id}_*/atom.py"))
    spec = importlib.util.spec_from_file_location(f"analysis_test_atom_{atom_id}", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


class Context:
    def __init__(self, config: dict[str, Any] | None = None, bus=None):
        self.config = config or {}
        self.handlers: dict[str, list] = {}
        self.events: list[tuple[str, dict[str, Any]]] = []
        self.bus = bus

    def subscribe(self, event: str, handler) -> None:
        self.handlers.setdefault(event, []).append(handler)
        if self.bus is not None:
            self.bus.subscribe(event, handler)

    async def publish(self, event: str, payload: dict[str, Any]) -> None:
        self.events.append((event, payload))
        if self.bus is not None:
            await self.bus.publish(event, payload)


class Bus:
    def __init__(self):
        self.handlers: dict[str, list] = {}
        self.events: list[tuple[str, dict[str, Any]]] = []

    def subscribe(self, event: str, handler) -> None:
        self.handlers.setdefault(event, []).append(handler)

    async def publish(self, event: str, payload: dict[str, Any]) -> None:
        self.events.append((event, payload))
        for handler in list(self.handlers.get(event, [])):
            await handler(payload)


@pytest.fixture
def settings_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "analysis_settings.db"
    monkeypatch.setenv("QUANT_ANALYSIS_SETTINGS_DB", str(path))
    return path


@pytest.mark.asyncio
async def test_each_valid_tick_recomputes_without_candle_and_contract_is_bounded(settings_db: Path):
    context = Context()
    kernel = LiveAnalyzerKernel("trend", EVENTS["trend"])
    await kernel.initialize(context)
    kernel.start()
    base = clock.now()
    for index in range(32):
        await kernel.on_tick({"account_id": "A-1", "broker": "BR", "symbol": "NQ", "bid": 20000 + index * 0.5,
                              "ask": 20000.25 + index * 0.5, "price": 20000.125 + index * 0.5,
                              "volume": 10 + index, "timestamp": base + index * 0.01})
    outputs = [payload for event, payload in context.events if event == EVENTS["trend"]]
    assert len(outputs) == 32
    assert [item["sequence"] for item in outputs] == list(range(1, 33))
    assert all(item["analysis_mode"] == "live_tick" and item["timeframe"] == "tick" for item in outputs)
    last = outputs[-1]
    assert -100 <= last["direction"] <= 100
    assert 0 <= last["confidence"] <= 100
    assert 0 <= last["current_depth"] <= 100
    assert 0 <= last["required_depth"] <= 100
    assert last["state"] in {STATE_ANALYZING, STATE_NOT_READY, STATE_READY}
    assert last["source_timestamp"] == pytest.approx(base + 0.31)
    assert "market_data.candle_closed" not in context.handlers
    assert EVENT_TICK in context.handlers


@pytest.mark.asyncio
async def test_analyzers_have_independent_evidence_profiles_not_one_copied_result(settings_db: Path):
    kernels: list[LiveAnalyzerKernel] = []
    contexts: list[Context] = []
    for analyzer_id in ANALYZERS.values():
        context = Context(); kernel = LiveAnalyzerKernel(analyzer_id, EVENTS[analyzer_id])
        await kernel.initialize(context); kernel.start()
        contexts.append(context); kernels.append(kernel)
    base = clock.now()
    price = 20000.0
    for index in range(30):
        price += (0.25 if index % 5 else -0.8) + index * 0.01
        tick = {"account_id": "A", "broker": "BR", "symbol": "NQ", "bid": price,
                "ask": price + (0.2 if index % 3 else 0.5), "price": price + 0.1,
                "volume": 1 + (index % 7) * 3, "timestamp": base + index * 0.01}
        for kernel in kernels:
            await kernel.on_tick(tick)
    directions = [kernel.states[("A", "BR", "NQ")].last_payload["direction"] for kernel in kernels]
    assert len(set(directions)) >= 8
    assert all(kernel.states[("A", "BR", "NQ")].sequence == 30 for kernel in kernels)


@pytest.mark.asyncio
async def test_scope_isolation_and_depth_is_evidence_not_a_fixed_tick_counter(settings_db: Path):
    context = Context()
    kernel = LiveAnalyzerKernel("momentum", EVENTS["momentum"])
    await kernel.initialize(context)
    kernel.start()
    base = clock.now()
    for index in range(28):
        # نفس عدد التكات، لكن الدليل السعري مختلف جذريًا.
        for account, symbol, movement in (("A", "NQ", 0.0), ("B", "ES", (1 if index % 2 else -1) * 2.0)):
            price = 10000 + movement * index
            await kernel.on_tick({"account_id": account, "broker": "BR",
                                  "symbol": symbol, "bid": price,
                                  "ask": price + 0.25, "price": price + 0.125,
                                  "volume": 2, "timestamp": base + index * 0.02})
    a = kernel.states[("A", "BR", "NQ")].last_payload
    b = kernel.states[("B", "BR", "ES")].last_payload
    assert a and b
    assert a["sequence"] == b["sequence"] == 28
    assert a["current_depth"] != b["current_depth"]
    assert set(kernel.states) == {("A", "BR", "NQ"), ("B", "BR", "ES")}
    before = kernel.states[("B", "BR", "ES")].sequence
    await kernel.on_tick({"account_id": "A", "broker": "BR", "symbol": "NQ", "bid": 10001, "ask": 10001.25,
                          "price": 10001.125, "volume": 1, "timestamp": base + 1})
    assert kernel.states[("B", "BR", "ES")].sequence == before


@pytest.mark.asyncio
async def test_threshold_depth_and_weight_are_independent_and_persist_with_audit(settings_db: Path):
    context = Context()
    kernel = LiveAnalyzerKernel("trend", EVENTS["trend"])
    await kernel.initialize(context)
    kernel.start()
    base = clock.now()
    for index in range(26):
        await kernel.on_tick({"account_id": "A", "broker": "BR", "symbol": "NQ", "bid": 20000 + index,
                              "ask": 20000.25 + index, "price": 20000.125 + index,
                              "volume": 5, "timestamp": base + index * 0.01})
    state = kernel.states[("A", "BR", "NQ")]
    baseline = kernel._analyze(("A", "BR", "NQ"), state, state.timestamps[-1])

    await kernel.on_settings({"account_id": "A", "broker": "BR", "symbol": "NQ", "analyzer_id": "trend",
                              "settings": {"required_depth": 0, "confidence_threshold": 0, "weight": 23},
                              "operator": "المالك", "command_id": "cmd-1"})
    ready = kernel._analyze(("A", "BR", "NQ"), state, state.timestamps[-1])
    assert ready["state"] == STATE_READY and ready["weight"] == 23
    assert ready["direction"] == baseline["direction"]
    assert ready["confidence"] == baseline["confidence"]

    await kernel.on_settings({"account_id": "A", "broker": "BR", "symbol": "NQ", "analyzer_id": "trend",
                              "settings": {"confidence_threshold": 100},
                              "operator": "المالك", "command_id": "cmd-2"})
    blocked = kernel._analyze(("A", "BR", "NQ"), state, state.timestamps[-1])
    assert blocked["state"] == STATE_NOT_READY
    assert blocked["direction"] == ready["direction"]
    assert blocked["weight"] == ready["weight"]

    reopened = AnalysisSettingsStore(settings_db).get("A", "BR", "NQ", "trend")
    assert reopened["required_depth"] == 0
    assert reopened["confidence_threshold"] == 100
    assert reopened["weight"] == 23
    with sqlite3.connect(settings_db) as connection:
        audit = connection.execute("SELECT command_id,old_json,new_json FROM analysis_settings_audit ORDER BY audit_id").fetchall()
    # NQ-22 ق٢ (2026-08-20): أمر الوزن `cmd-1` وزّع فرقه بالتساوي على الأربعة
    # عشر الآخرين بنفس المناقلة — صفّ أساس لكل أمر + ١٤ صفّ ":eq" لأمر الوزن.
    primary = [row[0] for row in audit if ":eq:" not in row[0]]
    equalized = [row[0] for row in audit if ":eq:" in row[0]]
    assert primary == ["cmd-1", "cmd-2"]
    assert len(equalized) == 14
    assert all(command.startswith("cmd-1:eq:") for command in equalized)
    assert json.loads(audit[-1][2])["revision"] == 2
    store = AnalysisSettingsStore(settings_db)
    total = sum(store.get("A", "BR", "NQ", analyzer)["weight"] for analyzer in DEFAULT_WEIGHTS)
    assert round(total, 4) == 100.0
    changed = [payload for event, payload in context.events if event == EVENT_SETTING_CHANGED]
    assert len(changed) == 2


@pytest.mark.asyncio
async def test_stale_replaces_ready_and_never_remains_usable(settings_db: Path):
    context = Context()
    kernel = LiveAnalyzerKernel("trend", EVENTS["trend"])
    await kernel.initialize(context)
    kernel.start()
    await kernel.on_settings({"account_id": "A", "broker": "BR", "symbol": "NQ", "analyzer_id": "trend",
                              "settings": {"required_depth": 0, "confidence_threshold": 0},
                              "operator": "المالك", "command_id": "ready"})
    base = clock.now()
    await kernel.on_tick({"account_id": "A", "broker": "BR", "symbol": "NQ", "bid": 100, "ask": 100.1,
                          "price": 100.05, "volume": 1, "timestamp": base})
    assert kernel.states[("A", "BR", "NQ")].last_payload["state"] == STATE_READY
    await kernel.on_second({"official_time": base + 6})
    stale = kernel.states[("A", "BR", "NQ")].last_payload
    assert stale["state"] == STATE_STALE
    assert stale["ready"] is False and stale["status"] == "stale"


# ٢٠٢٦-١٠-٠٧ (ختم المالك «NQ»): خرج اختبار test_manager_and_fusion_use_latest_ready_only_without_waiting_for_all — يختبر مدير التحليل 150 ودمجه 166 المؤرشفين مع فكّ الأقسام عن القرار.
# ٢٠٢٦-١٠-٠٧ (ختم المالك «NQ»): خرج اختبار test_decision_consumer_accepts_only_ready_live_analysis — يختبر غرفة القرار 451 وبطاقة READY المؤرشفتين مع فكّ الأقسام عن القرار.


@pytest.mark.asyncio
async def test_owner_setting_crosses_901_and_reaches_only_target_analyzer(settings_db: Path, tmp_path: Path):
    gateway_module = load_atom(901)
    bus = Bus()
    gateway = gateway_module.Atom()
    command_db = tmp_path / "commands.db"
    await gateway.initialize(Context({"db_path": str(command_db), "max_age_s": 60.0,
                                      "batch_limit": 10}, bus))
    target = LiveAnalyzerKernel("noise", EVENTS["noise"])
    other = LiveAnalyzerKernel("trend", EVENTS["trend"])
    await target.initialize(Context(bus=bus)); await other.initialize(Context(bus=bus))
    await gateway.start(); target.start(); other.start()
    now = clock.now()
    connection = gateway._connect()
    connection.execute("""INSERT INTO commands(action,operator,requested_at,status,payload_json)
        VALUES(?,?,?,?,?)""", ("analysis_setting", "المالك", now, "PENDING", json.dumps({
            "account_id": "A", "broker": "BR", "symbol": "NQ", "analyzer_id": "noise",
            "settings": {"required_depth": 72, "confidence_threshold": 68, "weight": 9},
        })))
    connection.commit()
    await gateway._on_pulse({"official_time": now + 0.1})
    stored = AnalysisSettingsStore(settings_db).get("A", "BR", "NQ", "noise")
    assert (stored["required_depth"], stored["confidence_threshold"], stored["weight"]) == (72, 68, 9)
    # NQ-22 ق٢: الأمر نفسه يصل لمحلّله الهدف وحده — عمق `trend` وعتبته لم
    # يُمسّا — لكن وزنه دفع حصّته المتساوية من فرق وزن `noise` بنفس المناقلة.
    untouched = AnalysisSettingsStore(settings_db).get("A", "BR", "NQ", "trend")
    assert (untouched["required_depth"], untouched["confidence_threshold"]) == (60.0, 60.0)
    assert round(untouched["weight"], 4) == 6.5
    assert untouched["revision"] == 1
    with sqlite3.connect(command_db) as check:
        assert check.execute("SELECT status FROM commands").fetchone()[0] == "DONE"


def test_all_fifteen_manifests_and_sources_have_live_contract():
    manifest_versions = set()
    for atom_id, analyzer_id in ANALYZERS.items():
        folder = next((ATOM_ROOT).glob(f"{atom_id}_*"), None)
        if folder is None:  # ٢٠٢٦-١٠-١٢: 154 · 164 (الحجم) نُقلتا إلى الأرشيف بأمر المالك — العقود بلا حجم
            continue
        manifest = yaml.safe_load((folder / "manifest.yaml").read_text())
        source = (folder / "atom.py").read_text()
        # عقد الحيّ خطّ `2.x`: الرقم الأخير يرتفع كلّما تغيّر الكود — وهو
        # إشارة إعادة التحميل الحارّ في هذا المشروع، ولا يغيّر العقد نفسه.
        # ⛔ تثبيته على `2.0.0` كان يمنع ترقية الذرّة بلا سبب تعاقديّ، ثم
        # تثبيته على `2.0.` منع ارتقاء الخط كلّه معًا (صاروا 2.1.0).
        assert str(manifest["version"]).startswith("2.")
        manifest_versions.add(str(manifest["version"]))
        assert {EVENT_TICK, EVENT_SETTINGS, "SYS_SECOND"}.issubset(manifest["subscribes"])
        assert EVENT_SETTING_CHANGED in manifest["publishes"]
        assert f'@live_analyzer("{analyzer_id}", EVENT_OUT)' in source
        assert 'market_data.candle_closed' in manifest["subscribes"]  # مسار قديم فقط، لا مصدر العقد الحي.
    assert sum(DEFAULT_WEIGHTS.values()) == 100
    # الخطّ موحّد: الخمسة عشر محلّلًا على عقد الحيّ نفسه (`2.x`) — لا يتفرّقون أبدًا.
    # ٢٠٢٦-١٠-٠٢ (ختم المالك «صلح كامل nq»): كان يشترط رقمًا واحدًا حرفًا، و154 وحده ارتقى
    # بإصلاحين له وحده بختم المالك — 2.6.0 (`d4d11a0`، ٢٠٢٦-٠٩-٢٢) و2.8.0 (`b5f1fa5`،
    # ٢٠٢٦-٠٩-٢٣) — والتعليق أعلاه يقول إنّ الرقم الأخير إشارة إعادة تحميل لا عقد. فالموحَّد
    # هو خطّ العقد الرئيسيّ.
    majors = {version.split(".")[0] for version in manifest_versions}
    assert majors == {"2"}, sorted(manifest_versions)
