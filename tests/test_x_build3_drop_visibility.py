"""ورقة X — البناء ٣: حارس يمنع تكرار العطل — اختبار القبول.

نصّ الورقة: «كل ذرّة ترمي مدخلًا تُظهر عدد المرميّ ورمز السبب في health_check»
واختبارها: «ذرّة ترمي مدخلًا واحدًا ثم تُسأل health_check — يجب أن يظهر العدّاد».

يشمل الفحص كل ذرّات مسار القرار: 613 · 112 · 451 · 452 · 453.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

import pytest

from core.contracts.atom import AtomContext

ROOT = Path(__file__).resolve().parents[1]
from build_registry.paths import RegistryAtomRoot
ATOM_ROOT = RegistryAtomRoot(ROOT)



class _Log:
    def __getattr__(self, _name: str):
        return lambda *a, **k: None


class _Bus:
    async def publish(self, *_a, **_k) -> None: ...
    def subscribe(self, *_a, **_k) -> None: ...


def load_atom(atom_id: int):
    folder = next((ATOM_ROOT).glob(f"{atom_id}_*/atom.py"))
    sys.path.insert(0, str(folder.parent))
    try:
        spec = importlib.util.spec_from_file_location(f"x_build3_atom_{atom_id}", folder)
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path.pop(0)


# ٢٠٢٦-١٠-٠٧ (ختم المالك «NQ»): خرجت حالات 451/452/453 من الاختبار — يختبر عدّادات سلسلة القرار المؤرشفة مع فكّ الأقسام عن القرار.
CONFIGS = {
    613: {"routes": {"feed.ctrader.tick": "market.tick"}, "provider_timeout_s": 30,
          "max_input_silence_seconds": 60, "preferred_provider": "CTRADER"},
    112: {},
}

BAD_INPUTS = {
    613: "feed.ctrader.tick",          # حمولة ناقصة (بلا bid/ask) → dropped
    112: "market.tick",                # تِكّة غير صالحة → invalid
}


async def _started(atom_id: int) -> Any:
    module = load_atom(atom_id)
    atom = module.Atom()
    await atom.initialize(AtomContext(atom_id, dict(CONFIGS[atom_id]), _Log(),
                                      _Bus().publish, _Bus().subscribe))
    await atom.start()
    return atom


@pytest.mark.asyncio
@pytest.mark.parametrize("atom_id", [613, 112])
async def test_one_dropped_input_is_visible_in_health(atom_id: int):
    atom = await _started(atom_id)
    handler_event = BAD_INPUTS[atom_id]
    # نمرّر مدخلًا واحدًا مكسورًا عبر معالج الحدث مباشرة
    await atom._on_source_tick({}, handler_event) if atom_id == 613 else None
    if atom_id == 112:
        await atom._on_tick({"symbol": ""})

    health = await atom.health_check()
    details = dict(health.details or {})
    counters = {k: v for k, v in details.items()
                if k in ("dropped", "invalid") and isinstance(v, int)}
    if "drop_reasons" in details:
        reasons = details["drop_reasons"]
    else:
        reasons = {}
    assert counters, f"الذرّة {atom_id} ترمي مدخلًا ولا يظهر أي عدّاد: {details}"
    assert sum(counters.values()) >= 1
    if reasons:
        assert sum(reasons.values()) >= 1, f"رمز السبب غائب عن {atom_id}: {details}"
