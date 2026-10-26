# -*- coding: utf-8 -*-
"""حارس العمليّة الباردة (المرحلة F) — عمليّةٌ حقيقيّة لا محاكاة.

ذرّةٌ باردة مصطنعة (701) تعيش في العمليّة الابنة: تستهلك `cold.in` وتنشر
`cold.out`. المحرّك في الأمّ يودع `cold.in`، ويجب أن يصله `cold.out` جذرًا،
ولا يُعاد `cold.out` إلى الابنة (كشف الصدى)، وتُقفل نظيفًا.
"""
from __future__ import annotations

import asyncio
import os
import textwrap
from pathlib import Path

import pytest

from engine import ColdProcess, NQEngine
from transport.owned_event_bus import OwnedEventBus

pytestmark = pytest.mark.slow

ATOM_SRC = '''
from core.contracts.atom import AtomBase, AtomContext

class Atom(AtomBase):
    async def initialize(self, context: AtomContext) -> None:
        self._context = context
        self.seen = 0
        context.subscribe("cold.in", self._on_in)
        context.subscribe("cold.out", self._on_out)

    async def start(self) -> None:
        pass

    async def stop(self) -> None:
        pass

    async def _on_in(self, payload):
        self.seen += 1
        await self._context.publish("cold.out", {"n": payload.get("n"), "seen": self.seen})

    async def _on_out(self, payload):
        # لو عاد إلينا ما نشرناه لصار هنا عدّادٌ صاعد — الحارس يراقبه عبر seen.
        pass
'''

MANIFEST = '''
id: 701
name: "Cold Echo Store"
version: "1.0.0"
core_version: ">=1.0.0,<2.0.0"
critical: false
entrypoint: "atom:Atom"
dependencies: []
publishes: ["cold.out"]
subscribes: ["cold.in", "cold.out"]
startup_mode: auto
health:
  interval_ms: 5000
  timeout_ms: 2000
  failure_threshold: 3
  restart_on_failure: false
  max_restarts: 1
  restart_backoff_ms: 1000
config_schema: {type: object, properties: {}, additionalProperties: false}
config: {}
'''


def _write_cold_atom(root: Path) -> None:
    directory = root / "701_cold_echo"
    directory.mkdir(parents=True)
    (directory / "manifest.yaml").write_text(textwrap.dedent(MANIFEST), encoding="utf-8")
    (directory / "atom.py").write_text(textwrap.dedent(ATOM_SRC), encoding="utf-8")


@pytest.mark.asyncio
async def test_cold_process_round_trip_without_echo(tmp_path: Path) -> None:
    atoms = tmp_path / "atoms"
    _write_cold_atom(atoms)
    cold_bus = OwnedEventBus(worker_count=2, cold_sections=[[700, 749]])
    engine = NQEngine(cold_bus=cold_bus, cadence_sections=[[150, 499]], cold_sections=[[700, 749]])
    received: list[dict] = []

    async def on_out(payload: dict) -> None:
        received.append(dict(payload))

    engine.subscribe("cold.out", on_out, subscriber="101")

    proc = ColdProcess(atom_ids=[701], atoms_root=str(atoms), snapshot_dir=str(tmp_path / "snap"),
                       journal_path=None, inbox_max=1000, outbox_max=1000, lanes=2)
    proc.spawn()
    proc.start_flusher()
    engine.cold_process = proc
    engine.cold_sink = proc.send
    pump = asyncio.create_task(proc.pump_outbound(engine.publish, mark_inbound=engine.mark_cold_inbound))
    try:
        report = await proc.wait_booted(timeout_s=120.0)
        assert report["loaded"] == [701], report
        for n in range(5):
            await engine.publish("cold.in", {"n": n}, publisher="test")
        deadline = asyncio.get_running_loop().time() + 30.0
        while len(received) < 5 and asyncio.get_running_loop().time() < deadline:
            await asyncio.sleep(0.1)
        assert [p["n"] for p in received] == [0, 1, 2, 3, 4]
        assert [p["seen"] for p in received] == [1, 2, 3, 4, 5]     # لا صدى: كلّ دخولٍ مرّة
        stats = engine.transport_stats()
        eng = stats["engine"]
        assert eng["cold_process_sent"] >= 5
        assert eng["cold_process_echo_skipped"] >= 5              # cold.out عاد ولم يُرسَل ثانيةً
        assert stats["cold_process"]["returned"] >= 5
        assert stats["cold_process"]["alive"] is True
        # إحصاءات الابنة تصل دوريًّا
        for _ in range(80):
            if proc.last_stats.get("counters"):
                break
            await asyncio.sleep(0.25)
        assert proc.last_stats.get("counters", {}).get("inbound", 0) >= 5
    finally:
        pump.cancel()
        try:
            await pump
        except (asyncio.CancelledError, Exception):
            pass
        await proc.stop(timeout_s=30.0)
        await engine.close()
    assert proc.is_alive() is False
