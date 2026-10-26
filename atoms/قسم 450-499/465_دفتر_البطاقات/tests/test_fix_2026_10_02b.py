"""٢٠٢٦-١٠-٠٢ (ختم المالك «صلح كامل nq») — نداء الانعكاس يُعدّ ولا يُنشر في الفراغ (v1.32.1).

`decision.card.reversed` لم يشترك فيه أحدٌ قطّ (الاسم في 465 وحده)، والشارة الحيّة
`نداء_انعكاس=27963`. والمستمع مؤجَّلٌ بأمر المالك ٢٠٢٦-٠٩-١٨ («خدها واحتفظ فيها تحت
دراسة»). فالنداء صار عدّادًا في الصحّة وسطرًا على البطاقة، بلا نشر.

⛔ كلُّ مخزنٍ هنا في `tmp_path` — كما في `test_atom.py`.
"""
import importlib.util
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[4]
FOLDER = Path(__file__).resolve().parents[1]
for _path in (str(ROOT), str(ROOT / "clock"), str(FOLDER)):
    if _path not in sys.path:
        sys.path.insert(0, _path)

_spec = importlib.util.spec_from_file_location("_t465_fix_b", FOLDER / "atom.py")
m = importlib.util.module_from_spec(_spec)
sys.modules["_t465_fix_b"] = m
_spec.loader.exec_module(m)

MANIFEST = yaml.safe_load((FOLDER / "manifest.yaml").read_text(encoding="utf-8"))
REVERSED = "decision.card.reversed"


class _Null:
    def __getattr__(self, name):
        return lambda *args, **kwargs: None


class _Bus:
    def __init__(self):
        self.published = []

    def subscribe(self, name, handler):
        pass

    async def publish(self, name, payload=None):
        self.published.append((name, payload))


async def _dispatched_card(tmp_path, monkeypatch):
    monkeypatch.setattr(m.card_ledger_birth, "movement_floor", lambda symbol: None)
    bus = _Bus()
    atom = m.Atom()
    await atom.initialize(m.AtomContext(465, {
        "store_path": str(tmp_path / "cards.db"), "dead_target_ttl_s": 4740.0,
        "max_open_age_s": 86400.0, "max_dispatch_age_s": 900.0, "min_rr": 3.0,
        "reversal_cooldown_s": 30.0, "flush_every_s": 5.0}, _Null(), bus.publish, bus.subscribe))
    assert Path(atom._store.path) == tmp_path / "cards.db"
    await atom.start()
    await atom._on_approved({"symbol": "NQ", "approved": True, "decision_side": "buy",
                             "decision_id": "D1", "account_id": "A1", "broker": "BR"})
    await atom._on_setup({"symbol": "NQ", "side": "buy", "entry_reference": 100.0,
                          "invalidation_price": 99.0, "target_price": 104.0,
                          "setup_owner": "406", "setup_id": "S1",
                          "invalidation_reason": "تحت القاع", "target_reason": "القمّة"})
    await atom._on_passed({"symbol": "NQ", "decision_side": "buy",
                           "decision_id": "D1", "gate_request_id": "G1"})
    card = atom._live["NQ"]
    assert card["state"] == m.STATE_DISPATCHED
    # محصّلة 413 تؤيّد الجهة الجديدة (البيع) — الشرط الثاني للنداء.
    card.setdefault("seen", {})["413.direction"] = -0.6
    return atom, bus


async def test_reversal_is_counted_and_written_but_not_published(tmp_path, monkeypatch):
    atom, bus = await _dispatched_card(tmp_path, monkeypatch)
    await atom._on_approved({"symbol": "NQ", "approved": True, "decision_side": "sell",
                             "decision_id": "D2", "account_id": "A1", "broker": "BR"})
    assert atom._reversals == 1, "الحرّاس الثلاثة تحقّقت — النداء يُعدّ"
    assert [p for n, p in bus.published if n == REVERSED] == [], "لا نشر في الفراغ"
    writes = [w for w in atom._pending if w[1] == "465" and w[2] == "reversal_called"]
    assert writes and writes[0][3].startswith("buy←sell"), atom._pending[-3:]
    health = await atom.health_check()
    assert health.details["reversals"] == 1 and health.details["reversal_published"] is False
    assert "نداء_انعكاس(يُعدّ_بلا_نشر_لا_مستمع)=1" in health.message
    # والمهلة بين نداءين ما زالت تحرس العدّاد.
    await atom._on_approved({"symbol": "NQ", "approved": True, "decision_side": "sell",
                             "decision_id": "D3", "account_id": "A1", "broker": "BR"})
    assert atom._reversals == 1
    await atom.stop()


def test_manifest_no_longer_declares_the_unheard_event():
    assert REVERSED not in MANIFEST["publishes"]
    assert m.ATOM_VERSION == "1.32.1"
