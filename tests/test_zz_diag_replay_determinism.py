"""تشخيص: هل منبع الإعادة (625) حتميّ، أم اللاحتميّة أسفل السلسلة؟

٢٠٢٦-٠٩-١٠ — أبلغت جلسة «قسم ٣٥٠–٤٠٠» أنّ اختبار الحتميّة يسقط و625/613
ضمن المحمَّلين فيه. هذا الاختبار يفصل: يقارن **ما يبثّه 625** بين تشغيلين
متطابقين قبل أن ينظر إلى ما يقرّره 453. إن تطابق البثّ واختلف القرار،
فالمنبع سليم والعلّة أسفل السلسلة.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_spec = importlib.util.spec_from_file_location(
    "_sim_x2", Path(__file__).with_name("test_x_build2_simulation.py"))
_sim = importlib.util.module_from_spec(_spec)
sys.modules["_sim_x2"] = _sim
_spec.loader.exec_module(_sim)
SimChain, make_replay_db, as_validated_tick = (
    _sim.SimChain, _sim.make_replay_db, _sim.as_validated_tick)


@pytest.mark.asyncio
async def test_replay_source_is_deterministic(tmp_path):
    db = tmp_path / "market_data.db"
    make_replay_db(db)

    runs = []
    for tag in ("a", "b"):
        run = SimChain(db, store_root=tmp_path / "store_sim" / f"run-{tag}")
        await run.start()
        await run.run_replay()
        runs.append(run)

    a, b = runs
    src_a = [t.get("cycle_id") or t.get("tick_id") for t in a.replay_ticks]
    src_b = [t.get("cycle_id") or t.get("tick_id") for t in b.replay_ticks]
    val_a = [as_validated_tick(t)["cycle_id"] for t in a.validated]
    val_b = [as_validated_tick(t)["cycle_id"] for t in b.validated]
    # ٢٠٢٦-١٠-٠٧ (ختم المالك «NQ»): خرج سطر «453 يقرّر» — 453 أُرشفت مع فكّ الأقسام عن القرار.

    print("\n625 يبثّ   : a=%d  b=%d  %s" % (len(src_a), len(src_b), "متطابق" if src_a == src_b else "مختلف"))
    print("112 يصادق  : a=%d  b=%d  %s" % (len(val_a), len(val_b), "متطابق" if val_a == val_b else "مختلف"))
    if src_a != src_b:
        print("  a: %s" % [str(x)[-9:] for x in src_a[:9]])
        print("  b: %s" % [str(x)[-9:] for x in src_b[:9]])

    assert src_a == src_b, "منبع الإعادة (625) غير حتميّ — العلّة في قسم التغذية"
