# ٢٠٢٦-١٠-٠٢ (ختم المالك «صلح كامل nq»): تشغيل 625 بإعداد الإنتاج لا يبلغ
# `market.tick.validated`، والتِكّة المُعادة لا تحمل هويّة الحساب الحيّ.
#
# الإثبات على السلسلة الحقيقيّة: 625 ⟵ 613 ⟵ 112 بإعداداتها من المانيفستات على
# القرص نفسها (لا إعداداتٍ مصنوعة)، والمخزن نسخةٌ مؤقّتة بشكل `market_data.db`
# الحيّ (CTRADER · 52992818 · Raw Trading Ltd في كلّ صفّ، مقيس).
import json
import os
import sqlite3
import sys
import tempfile

import yaml

from pathlib import Path as _Path
sys.path.insert(0, str(_Path(__file__).resolve().parents[4]))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.contracts.atom import AtomContext  # noqa: E402
import importlib.util as _ilu  # noqa: E402

_spec = _ilu.spec_from_file_location(
    "_atom625_fix_b", _Path(__file__).resolve().parents[1] / "atom.py")
_mod = _ilu.module_from_spec(_spec)
sys.modules["_atom625_fix_b"] = _mod
_spec.loader.exec_module(_mod)
Atom = _mod.Atom

_SECTION = _Path(__file__).resolve().parents[2]                   # قسم 600-649
_ATOMS = _SECTION.parent
MANIFEST_625 = str(_Path(__file__).resolve().parents[1] / "manifest.yaml")
MANIFEST_613 = str(_SECTION / "613_تغذية_السوق" / "manifest.yaml")
ATOM_613 = str(_SECTION / "613_تغذية_السوق" / "atom.py")
ATOM_112 = str(_ATOMS / "قسم 100-149" / "112_مدقق_البيانات" / "atom.py")
LIVE_ACCOUNT = "52992818"


class _Log:
    def __getattr__(self, _name):
        return lambda *a, **k: None


class _Bus:
    """ناقلٌ متزامن صغير: كلّ نشرٍ يُسلَّم فورًا لمشتركيه بالاسم، ويُسجَّل."""

    def __init__(self):
        self.published = []
        self.handlers = {}

    def subscribe(self, name, handler):
        self.handlers.setdefault(name, []).append(handler)

    async def publish(self, name, payload):
        self.published.append((name, payload))
        for handler in list(self.handlers.get(name, [])):
            await handler(payload)

    def count(self, name):
        return sum(1 for n, _ in self.published if n == name)


def _load(path, name):
    spec = _ilu.spec_from_file_location(name, path)
    module = _ilu.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _config(path):
    with open(path, encoding="utf-8") as fh:
        return dict(yaml.safe_load(fh)["config"])


def _recorded_db(folder, rows=5):
    path = os.path.join(folder, "market_data.db")
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE market_data (id INTEGER PRIMARY KEY, symbol TEXT, provider TEXT,"
                " bid REAL, ask REAL, occurred_at REAL, payload_json TEXT)")
    for i in range(1, rows + 1):
        price = 65000.0 + i
        con.execute("INSERT INTO market_data VALUES (?,?,?,?,?,?,?)",
                    (i, "BTCUSD", "CTRADER", price - 2.5, price + 2.5, 1788790000.0 + i,
                     json.dumps({"account_id": LIVE_ACCOUNT, "broker": "Raw Trading Ltd",
                                 "symbol": "BTCUSD", "price": price,
                                 "exchange_timestamp": 1788790000.0 + i, "volume": 1})))
    con.commit()
    con.close()
    return path


async def _chain(routes_613=None):
    tmp = tempfile.TemporaryDirectory()
    bus = _Bus()
    cfg_625 = dict(_config(MANIFEST_625), db_path=_recorded_db(tmp.name))
    cfg_613 = _config(MANIFEST_613)
    if routes_613 is not None:
        cfg_613["routes"] = routes_613
    atoms = []
    for module, atom_id, cfg in ((_load(ATOM_112, "_atom112_fix_b"), 112, {}),
                                 (_load(ATOM_613, "_atom613_fix_b_chain"), 613, cfg_613),
                                 (_mod, 625, cfg_625)):
        atom = module.Atom()
        await atom.initialize(AtomContext(atom_id=atom_id, config=cfg, logger=_Log(),
                                          publish=bus.publish, subscribe=bus.subscribe))
        await atom.start()
        atoms.append(atom)
    await bus.publish("replay.session.start", {})
    tmp.cleanup()
    return bus, atoms


async def test_production_identity_is_not_a_live_account():
    cfg = _config(MANIFEST_625)
    assert cfg["account_id"] != LIVE_ACCOUNT and not str(cfg["account_id"]).isdigit(), cfg
    assert cfg["broker"] != "Raw Trading Ltd", cfg


async def test_configured_identity_wins_over_the_recorded_one():
    tmp = tempfile.TemporaryDirectory()
    out = []

    async def pub(name, payload):
        out.append((name, payload))

    atom = Atom()
    await atom.initialize(AtomContext(625, {"db_path": _recorded_db(tmp.name, rows=2),
                                            "account_id": "SIM-A", "broker": "SIM-B"},
                                      _Log(), pub, lambda *a: None))
    await atom.start()
    await atom._on_start({})
    ticks = [p for n, p in out if n == "feed.replay.tick"]
    tmp.cleanup()
    assert len(ticks) == 2
    assert {(t["account_id"], t["broker"]) for t in ticks} == {("SIM-A", "SIM-B")}, ticks


async def test_starting_625_in_the_live_config_cannot_reach_validated_ticks():
    bus, atoms = await _chain()
    assert bus.count("feed.replay.tick") == 5, "625 لم يبثّ — الإثبات بلا موضوع"
    assert bus.count("market.tick") == 0, "تِكّةٌ مُعادة بلغت مسار المحلّلين"
    assert bus.count("market.tick.validated") == 0, "تِكّةٌ مُعادة صارت سعرًا مُعتمدًا"
    assert atoms[0].checked_count == 0


async def test_a_simulation_route_does_reach_them_so_the_zero_is_the_config():
    bus, _atoms = await _chain(routes_613={"feed.replay.tick": "market.tick"})
    assert bus.count("market.tick.validated") == 5, bus.count("market.tick.validated")
    validated = [p for n, p in bus.published if n == "market.tick.validated"]
    assert all(p.get("account_id") != LIVE_ACCOUNT for p in validated), validated[:1]
