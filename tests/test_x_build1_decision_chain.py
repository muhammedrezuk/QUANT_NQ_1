"""ورقة X — البناء ١: إحياء سلسلة القرار — اختبارات القبول.

مقاييس الورقة الخمسة، منقولًا إلى عمليّات قابلة للتشغيل هنا:
  ١ · 451 يترك NO_CYCLES_YET وعدّاد الدورات > صفر        (المقياس ١)
  ٢ · يظهر decision.aggregated.state                     (المقياس ٢)
  ٣ · تصل السلسلة إلى decision.scored.state              (المقياس ٣)
  ٤ · cycle_id عند 453 = cycle_id عند القسم المغذّي       (المقياس ٤)
  ٥ · صفر خطأ جديد في الناقل                              (المقياس ٥ — في الجهاز
       الحيّ يُقرأ من var/logs/errors-*.log؛ هنا من عدّادات الناقل)

والسيناريو الأهمّ — إحياء عطل الجهاز الحيّ نفسه: تِكّة بلا sequence من مصدر
ترقيميّ (613 قبل 2.4.0 كان يُسقطها) — يجب أن تُفتح الدورة رغم ذلك عبر سلسلة
احتياط هوية المحوّل القانوني.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

import pytest

from core.contracts.atom import AtomContext
from core.event_bus import EventBus
from shared.tick_contract import as_validated_tick

ROOT = Path(__file__).resolve().parents[1]
from build_registry.paths import RegistryAtomRoot
ATOM_ROOT = RegistryAtomRoot(ROOT)



class _Log:
    def __getattr__(self, _name: str):
        return lambda *a, **k: None


def load_atom(atom_id: int):
    folder = next((ATOM_ROOT).glob(f"{atom_id}_*/atom.py"))
    sys.path.insert(0, str(folder.parent))
    try:
        spec = importlib.util.spec_from_file_location(f"x_build1_atom_{atom_id}", folder)
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path.pop(0)


class Harness:
    """ناقل حقيقي + ذرّات حقيقيّة على مسار التغذية الحيّ (613 ← 112)."""

    # ٢٠٢٦-١٠-٠٧ (ختم المالك «NQ»): خرجت 451/452/453 من الحزام — أُرشفت مع فكّ الأقسام عن القرار؛ يبقى مسار التغذية.
    def __init__(self):
        self.bus = EventBus()
        self.modules = {i: load_atom(i) for i in (613, 112)}
        self.atoms: dict[int, Any] = {}

    async def start(self) -> None:
        configs = {
            613: {"routes": {"feed.ctrader.tick": "market.tick",
                              "feed.mt5.tick": "market.tick"},
                  "provider_timeout_s": 30, "max_input_silence_seconds": 60,
                  "preferred_provider": "CTRADER"},
            112: {},
        }
        for atom_id, module in self.modules.items():
            atom = module.Atom()
            self.atoms[atom_id] = atom
            await atom.initialize(AtomContext(
                atom_id, configs[atom_id], _Log(),
                lambda name, payload, aid=atom_id: self.bus.publish(name, payload, publisher=str(aid)),
                lambda name, handler, aid=atom_id: self.bus.subscribe(name, handler, subscriber=str(aid))))
            await atom.start()

    def rows(self, event: str) -> list[dict]:
        collected: list[dict] = []
        self.bus.subscribe(event, lambda p: collected.append(p), subscriber="probe")
        return collected  # يُملأ لاحقًا بالأحداث القادمة فقط — لذا نستخدم grab


# ٢٠٢٦-١٠-٠٧ (ختم المالك «NQ»): خرج اختبار test_measure_1_and_2_chain_opens_and_publishes_with_sequence — يختبر سلسلة القرار 451 المؤرشفة مع فكّ الأقسام عن القرار.
# ٢٠٢٦-١٠-٠٧ (ختم المالك «NQ»): خرج اختبار test_live_failure_repro_unnumbered_tick_still_opens_cycle — يختبر فتح دورة 451 المؤرشفة مع فكّ الأقسام عن القرار.
# ٢٠٢٦-١٠-٠٧ (ختم المالك «NQ»): خرج اختبار test_measure_3_and_4_chain_reaches_scoring_with_same_cycle_id — يختبر سلسلة 451←452←453 المؤرشفة مع فكّ الأقسام عن القرار.
# ٢٠٢٦-١٠-٠٧ (ختم المالك «NQ»): خرج اختبار test_measure_5_no_new_bus_errors_across_the_chain — يختبر ناقل سلسلة القرار القديمة وبطاقة القسم 150 المؤرشفتين مع فكّ الأقسام عن القرار.
# (وخرج معها مساعداها feed_622_style وبطاقتا القسمين analysis_card/strategy_card — لا مستعمل لها بعدها.)


def test_determinism_same_tick_same_cycle_id():
    """شرط البناء ٢ قبل أن يبدأ: هوية الدورة حتميّة — نفس التِكّة مرّتين =
    نفس المعرّف، بمصدر مرقّم وغير مرقّم معًا."""
    base = {"account_id": "A", "broker": "BR", "symbol": "NQ",
            "bid": 100.0, "ask": 100.2, "price": 100.1,
            "timestamp": 5.0, "exchange_timestamp": 5.0}
    numbered = as_validated_tick({**base, "sequence": "9"})
    numbered_again = as_validated_tick({**base, "sequence": "9"})
    bare = as_validated_tick(base)
    bare_again = as_validated_tick(base)
    assert numbered["cycle_id"] == numbered_again["cycle_id"]
    assert bare["cycle_id"] == bare_again["cycle_id"]


@pytest.mark.asyncio
async def test_613_now_forwards_sequence_identity():
    """المسار (ب): 613 لا يُسقط sequence بعد اليوم — يمرّرها كما أرسلها 622."""
    h = Harness(); await h.start()
    forwarded: list[dict] = []
    h.bus.subscribe("market.tick", forwarded.append, subscriber="probe")
    await h.bus.publish("feed.ctrader.tick", {
        "account_id": "A", "broker": "BR", "symbol": "NQ", "provider": "CTRADER",
        "bid": 1.0, "ask": 1.2, "price": 1.1, "volume": 3,
        "timestamp": 7.0, "exchange_timestamp": 7.0, "sequence": "424242"},
        publisher="test_622")
    # (nq seal 2026-08-25: async bus -- drain before reading deliveries.)
    assert await h.bus.drain(timeout_s=10.0)
    assert forwarded and forwarded[-1].get("sequence") == "424242"
