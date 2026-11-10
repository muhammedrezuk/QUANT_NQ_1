# ٢٠٢٦-١٠-٠٢ (ختم المالك «صلح كامل nq»): إعداد الإنتاج لا يصل تِكّات الإعادة/المحاكاة
# (`feed.replay.tick`) بالمسار الحيّ `market.tick`. كان المسار في `routes` منذ
# ٢٠٢٦-٠٩-٠٧، فتشغيلٌ يدويّ واحد لـ625 أو 630 يضخّ أسعارًا تاريخيّة في القرار.
# الاختبار يقرأ إعداد الإنتاج من المانيفست نفسه على القرص — لا إعدادًا مصنوعًا.
import os
import sys

import yaml

from pathlib import Path as _Path
sys.path.insert(0, str(_Path(__file__).resolve().parents[4]))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.contracts.atom import AtomContext  # noqa: E402
import importlib.util as _ilu  # noqa: E402

_spec = _ilu.spec_from_file_location(
    "_atom613_fix_b", _Path(__file__).resolve().parents[1] / "atom.py")
_mod = _ilu.module_from_spec(_spec)
sys.modules["_atom613_fix_b"] = _mod
_spec.loader.exec_module(_mod)
Atom = _mod.Atom

MANIFEST_613 = str(_Path(__file__).resolve().parents[1] / "manifest.yaml")
SIM_ROUTES = {"feed.replay.tick": "market.tick"}


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


def _production_config():
    with open(MANIFEST_613, encoding="utf-8") as fh:
        return dict(yaml.safe_load(fh)["config"])


async def _new(config):
    bus = _Bus()
    atom = Atom()
    await atom.initialize(AtomContext(atom_id=613, config=config, logger=_Log(),
                                      publish=bus.publish, subscribe=bus.subscribe))
    await atom.start()
    return atom, bus


def _replayed_tick():
    # شكل 625 حرفًا: مزوّد التِكّة المسجَّل (CTRADER) وهويّةٌ حتميّة.
    return {"symbol": "BTCUSD", "provider": "CTRADER", "bid": 65000.0, "ask": 65005.0,
            "price": 65002.5, "timestamp": 1788790000.0, "exchange_timestamp": 1788790000.0,
            "account_id": "52992818", "broker": "Raw Trading Ltd",
            "tick_id": "replay-1", "sequence": "replay-1"}


async def test_production_routes_do_not_carry_the_replay_feed():
    config = _production_config()
    assert "feed.replay.tick" not in config["routes"], config["routes"]
    atom, bus = await _new(config)
    assert "feed.replay.tick" not in bus.handlers, sorted(bus.handlers)
    await bus.deliver("feed.replay.tick", _replayed_tick())
    assert not [n for n, _ in bus.published if n == "market.tick"], bus.published


async def test_live_feeds_still_route_in_production():
    atom, bus = await _new(_production_config())
    live = dict(_replayed_tick(), tick_id="live-1", sequence="live-1")
    await bus.deliver("feed.ctrader.tick", live)
    assert [n for n, _ in bus.published].count("market.tick") == 1, bus.published


async def test_the_route_is_the_only_replay_switch_a_simulation_config_opens_it():
    """إعداد المحاكاة (كما في tests/test_x_build2_simulation.py) يفتح المسار — فالصفر
    أعلاه نتيجةُ الإعداد لا عطبٌ في الموزّع."""
    config = dict(_production_config(), routes=dict(SIM_ROUTES))
    atom, bus = await _new(config)
    await bus.deliver("feed.replay.tick", _replayed_tick())
    assert [n for n, _ in bus.published].count("market.tick") == 1, bus.published
