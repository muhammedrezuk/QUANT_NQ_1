# ٢٠٢٦-١٠-٠٥ (ختم المالك «nq اعتمدناها»): ٥٧٢ يتنحّى عن تذاكر ٥٧٤ المُدارة على مستويات
# التحليل — التعادل فيها عند أوّل مستوى لا عند 1R — ويبقى على كلّ صفقةٍ غيرها كما كان.
import os
import sys

from pathlib import Path as _Path
sys.path.insert(0, str(_Path(__file__).resolve().parents[4]))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.contracts.atom import AtomContext  # noqa: E402
import importlib.util as _ilu  # noqa: E402

_spec = _ilu.spec_from_file_location(
    "_atom572_levels", _Path(__file__).resolve().parents[1] / "atom.py")
_mod = _ilu.module_from_spec(_spec)
sys.modules["_atom572_levels"] = _mod
_spec.loader.exec_module(_mod)
_mod.PLAN_GRACE_CYCLES = 1   # 2026-10-23 (law 6): primed away here; tested in `test_law6_2026_10_23.py`


class _Log:
    def __getattr__(self, _name):
        return lambda *a, **k: None


class _Bus:
    def __init__(self):
        self.published = []
        self.handlers = {}

    def subscribe(self, name, handler):
        self.handlers.setdefault(name, []).append(handler)

    async def publish(self, name, payload):
        self.published.append((name, payload))

    async def deliver(self, name, payload):
        for handler in self.handlers.get(name, []):
            await handler(payload)


def _pos(ticket, current):
    return {"account_id": "A", "ticket": ticket, "symbol": "XAUUSD", "side": "BUY",
            "volume": 0.3, "entry_price": 4000.0, "current_price": current,
            "stop_loss": 3990.0, "take_profit": 4100.0}


async def test_plan_ticket_is_left_to_574_and_others_get_breakeven():
    bus = _Bus()
    atom = _mod.Atom()
    await atom.initialize(AtomContext(atom_id=572, config={"breakeven_at_r": 1.0}, logger=_Log(),
                                      publish=bus.publish, subscribe=bus.subscribe))
    await atom.start()
    await bus.deliver(_mod.EVENT_PLAN, {"tickets": ["1"]})
    # كلاهما عند 2R: التذكرة 1 في الخطّة فلا تعادل لها هنا، والتذكرة 2 تأخذه كما كانت.
    await atom._on_positions({"positions": [_pos(1, 4020.0), _pos(2, 4020.0)]})
    sent = [p["ticket"] for n, p in bus.published if n == _mod.EVENT_OUT]
    assert sent == [2], sent
    assert len(atom._plan_yielded) == 1
    # وإن خرجت التذكرة من الخطّة (قائمةٌ جديدة بلاها) يعود التعادل يحرسها.
    await bus.deliver(_mod.EVENT_PLAN, {"tickets": []})
    await atom._on_positions({"positions": [_pos(1, 4020.0), _pos(2, 4020.0)]})
    sent = [p["ticket"] for n, p in bus.published if n == _mod.EVENT_OUT]
    assert sent == [2, 1], sent
