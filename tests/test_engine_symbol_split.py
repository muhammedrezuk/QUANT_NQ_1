# -*- coding: utf-8 -*-
"""حارس النواة الموزّعة — محرّكا رموزٍ حقيقيّان في عمليّتين.

الذرّة 120 عمدًا **خارج** نطاق الإيقاع (150-499): الاختبار يثبت العزل
بالرمز، لا سياسة «الأحدث يكفي» — تلك لها حارسها في test_engine_core.

ذرّةٌ مصطنعة (200) تعيش في كلّ محرّك: تستهلك `market.tick` وتنشر
`analysis.demo.state` بعدّادٍ محلّيّ. والمطلوب إثباته:

  ١) تِكّة الذهب تذهب إلى محرّكها وحده — والآخر لا يراها (`foreign_symbol`)
  ٢) الحالة محلّيّة: عدّاد كلّ محرّك مستقلّ (لا حالة مشتركة)
  ٣) ما ينتجه المحرّك يعود إلى الجذر جذرًا بهويّته
  ٤) ولا يعود إليه ثانيةً (كشف الصدى)
  ٥) الحدث بلا رمز (العمود الفقريّ) يُبثّ إلى **كلّ** المحرّكات
  ٦) وكلاهما يُقفل نظيفًا
"""
from __future__ import annotations

import asyncio
import textwrap
from pathlib import Path

import pytest

from engine import NQEngine, SymbolEngine, SymbolRouter
from transport.owned_event_bus import OwnedEventBus

pytestmark = pytest.mark.slow

ATOM_SRC = '''
from core.contracts.atom import AtomBase, AtomContext

class Atom(AtomBase):
    async def initialize(self, context: AtomContext) -> None:
        self._context = context
        self.ticks = 0
        self.beats = 0
        context.subscribe("market.tick", self._on_tick)
        context.subscribe("sys.beat", self._on_beat)

    async def start(self) -> None:
        pass

    async def stop(self) -> None:
        pass

    async def _on_tick(self, payload):
        self.ticks += 1
        await self._context.publish("analysis.demo.state", {
            "symbol": payload.get("symbol"), "n": payload.get("n"),
            "local_ticks": self.ticks})

    async def _on_beat(self, payload):
        self.beats += 1
        await self._context.publish("analysis.beat.state", {"beats": self.beats})
'''

MANIFEST = '''
id: 120
name: "Demo Symbol Analyzer"
version: "1.0.0"
core_version: ">=1.0.0,<2.0.0"
critical: false
entrypoint: "atom:Atom"
dependencies: []
publishes: ["analysis.demo.state", "analysis.beat.state"]
subscribes: ["market.tick", "sys.beat"]
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


def _write_atom(root: Path) -> None:
    directory = root / "120_demo"
    directory.mkdir(parents=True)
    (directory / "manifest.yaml").write_text(textwrap.dedent(MANIFEST), encoding="utf-8")
    (directory / "atom.py").write_text(textwrap.dedent(ATOM_SRC), encoding="utf-8")


@pytest.mark.asyncio
async def test_two_symbol_engines_own_their_symbols_and_share_nothing(tmp_path: Path) -> None:
    atoms = tmp_path / "atoms"
    _write_atom(atoms)
    root = NQEngine(cold_bus=OwnedEventBus(worker_count=2), cadence_sections=[[150, 499]])
    seen: list[dict] = []

    async def on_state(payload: dict) -> None:
        seen.append(dict(payload))

    root.subscribe("analysis.demo.state", on_state, subscriber="101")
    root.subscribe("analysis.beat.state", on_state, subscriber="101")

    engines = [
        SymbolEngine(group="g0", symbols=["XAUUSD"], atom_ids=[120], atoms_root=str(atoms),
                     inbox_max=500, outbox_max=500, flush_every_s=0.005),
        SymbolEngine(group="g1", symbols=["BTCUSD"], atom_ids=[120], atoms_root=str(atoms),
                     inbox_max=500, outbox_max=500, flush_every_s=0.005),
    ]
    router = SymbolRouter(engines, broadcast_prefixes=("sys.",))
    root.symbol_router = router
    pumps = []
    try:
        for eng in engines:
            eng.spawn()
            eng.start_flusher()
            pumps.append(asyncio.create_task(
                eng.pump_outbound(root.publish, mark_inbound=root.mark_router_inbound)))
        for eng in engines:
            report = await eng.wait_booted(timeout_s=150.0)
            assert report["loaded"] == [120], report

        for n in range(3):
            await root.publish("market.tick", {"symbol": "XAUUSD", "n": n}, publisher="613")
        for n in range(2):
            await root.publish("market.tick", {"symbol": "BTCUSD", "n": n}, publisher="613")
        await root.publish("sys.beat", {}, publisher="806")

        deadline = asyncio.get_running_loop().time() + 40.0
        while len(seen) < 5 and asyncio.get_running_loop().time() < deadline:
            await asyncio.sleep(0.1)

        gold = [p for p in seen if p.get("symbol") == "XAUUSD"]
        btc = [p for p in seen if p.get("symbol") == "BTCUSD"]
        beats = [p for p in seen if "beats" in p]
        # ١ و٢: كلّ رمزٍ في محرّكه، وعدّاده محلّيّ يبدأ من واحد.
        #
        # ٢٠٢٦-٠٩-١٨: كان الحارس يطالب بالتسلسل كاملًا [1,2,3]. ومع المدخل
        # المباشر () تجتمع حالاتٌ أكثر في الدورة الواحدة فيُدمَج
        # ما بينها — وهو **العقد** لا خللًا (§١٦: الأحدث يكفي للحالة). والذي
        # يثبت أنّ لا تِكّة ضاعت هو أنّ العدّاد **المحلّيّ في المحرّك** بلغ
        # آخر رقم: ثلاثًا للذهب واثنتين للبتكوين. والفعل الماليّ لا يُدمَج
        # أبدًا — يثبته .
        gold_ticks = [p["local_ticks"] for p in gold]
        btc_ticks = [p["local_ticks"] for p in btc]
        assert gold_ticks == sorted(gold_ticks) and gold_ticks[-1] == 3, gold_ticks
        assert btc_ticks == sorted(btc_ticks) and btc_ticks[-1] == 2, btc_ticks
        assert set(gold_ticks) <= {1, 2, 3} and set(btc_ticks) <= {1, 2}
        # ٥: العمود الفقريّ بلغ المحرّكين معًا
        assert len(beats) == 2, beats
        # ٤: لا صدى — ما عاد إلى الجذر لا يُرسَل ثانيةً
        stats = root.transport_stats()
        ts = stats["engine"]
        assert ts["router_echo_skipped"] >= 5
        assert ts["routed_to_symbol_engines"] >= 6
        rstats = stats["symbol_router"]
        assert rstats["routed"] == 5 and rstats["broadcast"] == 1
        assert rstats["owners"] == {"XAUUSD": "g0", "BTCUSD": "g1"}
        # ١ (تأكيد من جهة الابن): لا رمزًا غريبًا دخل أيّ محرّك
        for eng in engines:
            child = eng.last_stats.get("counters") or {}
            assert child.get("foreign_symbol", 0) == 0, (eng.group, child)
    finally:
        for pump in pumps:
            pump.cancel()
        for pump in pumps:
            try:
                await pump
            except (asyncio.CancelledError, Exception):
                pass
        for eng in engines:
            await eng.stop(timeout_s=40.0)
        await root.close()
    for eng in engines:
        assert eng.is_alive() is False
