# -*- coding: utf-8 -*-
"""حارس فصل سياق التنفيذ — مسار المال لا ينتظر تصريف البارد.

المقيس ٢٠٢٦-٠٩-١٨ (شلّال المراحل): المحرّك ينهي تِكّة ← قرار في ٢٠–٣٠ مِلّي
ثانية، ثمّ يرى الجذر الأحداث نفسها عند ٠٫٤٩٥ ث. و٤٦٧ مِلّي ثانية أقلّ بقليلٍ
من نصف الثانية — وهي بالضبط مهلة `_drain` للتخزين والعرض.

والسبب: المضخّات الثلاث كانت تنادي `asyncio.to_thread` — مُنفِّذ الحلقة
**المشترك**. فستّة خيوطٍ مركونة نصف ثانية لكلّ محرّكاتٍ ثلاثة، تزاحمها
العمليّة الباردة والذرّات التي تقرأ sqlite. فمضخّة المال تنتظر خيطًا حرًّا.
"""
from __future__ import annotations

import asyncio
import time

import pytest

from engine import SymbolEngine


def _engine(group: str = "g0") -> SymbolEngine:
    return SymbolEngine(group=group, symbols=["XAUUSD"], atom_ids=[],
                        atoms_root=".", inbox_max=64, outbox_max=64)


def test_money_and_cold_have_separate_pools() -> None:
    engine = _engine()
    try:
        assert engine._money_pool is not engine._cold_pool
        assert engine._money_pool._max_workers == 1, "المال يشارك خيطه مع أحد"
        assert engine._cold_pool._max_workers >= 1
    finally:
        engine._money_pool.shutdown(wait=False)
        engine._cold_pool.shutdown(wait=False)


@pytest.mark.asyncio
async def test_a_parked_cold_drain_cannot_delay_money() -> None:
    """الحارس الحاسم: البارد يركن خيوطه نصف ثانية، والمال يمرّ فورًا."""
    engine = _engine("g1")
    loop = asyncio.get_running_loop()
    try:
        # البارد يركن كلّ خيوطه — تمامًا كما يفعل `_drain(..., 0.5, ...)`
        parked = [loop.run_in_executor(engine._cold_pool, time.sleep, 0.5)
                  for _ in range(engine._cold_pool._max_workers + 2)]
        await asyncio.sleep(0.02)                     # حتّى تُشغَل البركة فعلًا
        started = time.perf_counter()
        await loop.run_in_executor(engine._money_pool, lambda: None)
        elapsed = time.perf_counter() - started
        assert elapsed < 0.05, "المال انتظر البارد %.4f ث" % elapsed
        await asyncio.gather(*parked)
    finally:
        engine._money_pool.shutdown(wait=False)
        engine._cold_pool.shutdown(wait=False)


@pytest.mark.asyncio
async def test_money_does_not_ride_the_shared_loop_executor() -> None:
    """ولا تزاحمه الذرّات: بركة الحلقة الافتراضيّة مشغولة والمال يمرّ."""
    engine = _engine("g2")
    loop = asyncio.get_running_loop()
    try:
        busy = [asyncio.create_task(asyncio.to_thread(time.sleep, 0.4))
                for _ in range(24)]
        await asyncio.sleep(0.02)
        started = time.perf_counter()
        await loop.run_in_executor(engine._money_pool, lambda: None)
        elapsed = time.perf_counter() - started
        assert elapsed < 0.05, "المال انتظر بركة الحلقة %.4f ث" % elapsed
        await asyncio.gather(*busy)
    finally:
        engine._money_pool.shutdown(wait=False)
        engine._cold_pool.shutdown(wait=False)
