"""٢٠٢٦-١٠-١٢ (ختم المالك «NQ»: «كلّ صفقة تحمل الحقائق التي فُتحت عليها وأرقامها»): أرقام القرار كما أرسلتها
الاستراتيجيّة على إطار صفقتها (`evidence.facts`) تُختم على البطاقة سطرًا واحدًا «حقيقة القرار».

صفقة 405 (١٠-١٠) لم يُعرف كم كانت Z فيها: الدليل لم يُكتب، وختم المحلّلين مفتاحه بلا إطار.
⛔ كلُّ مخزنٍ هنا في `tmp_path` — كما في `test_atom.py`.
"""
import importlib.util
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[4]
FOLDER = Path(__file__).resolve().parents[1]
for _path in (str(ROOT), str(ROOT / "clock"), str(FOLDER)):
    if _path not in sys.path:
        sys.path.insert(0, _path)

_spec = importlib.util.spec_from_file_location("_t465_facts", FOLDER / "atom.py")
m = importlib.util.module_from_spec(_spec)
sys.modules["_t465_facts"] = m
_spec.loader.exec_module(m)

from shared import facts_strategies as FS  # noqa: E402
from shared.trade_card import CardStore  # noqa: E402
from shared.trade_setup import build_setup  # noqa: E402


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


def _book_405(z):
    """Z على إطار الصفقة (5د)، ثمّ إطارٌ آخر (1س) نُشر بعده — والمختوم إطار الصفقة."""
    book = FS.FactBook()
    book.put("stats.zscore.state", {"symbol": "NQ", "timeframe": "5m", "metadata": {"value": z}}, 0.0)
    book.put("stats.zscore.state", {"symbol": "NQ", "timeframe": "1h", "metadata": {"value": 0.3}}, 1.0)
    return book


def test_405_facts_are_from_the_trade_frame():
    facts = FS.decision_facts("405", _book_405(-1.734567891), "NQ", "5m", 1, 100.0, 99.0, 1.0, "5m")
    assert facts["310_value"] == pytest.approx(-1.734568)
    assert (facts["frame"], facts["side"], facts["close"]) == ("5m", 1, 100.0)
    assert (facts["stop"], facts["stop_points"], facts["stop_frame"]) == (99.0, 1.0, "5m")


def test_every_strategy_has_a_trigger_and_every_factor_a_name():
    assert set(FS.TRIGGER) == set(FS.STRATEGIES)
    for strat, fns in FS.FACTORS.items():
        assert len(FS.FACTOR_NAMES[strat]) == len(fns)


def test_408_each_factor_with_its_number():
    book = FS.FactBook()
    book.put("analysis.momentum.state", {"symbol": "NQ", "timeframe": "1m", "metadata": {"roc": 0.001}}, 0.0)
    book.put("analysis.momentum.state", {"symbol": "NQ", "timeframe": "5m", "metadata": {"roc": 0.002}}, 0.0)
    book.put("stats.zscore.state", {"symbol": "NQ", "timeframe": "1m", "metadata": {"value": 2.0}}, 0.0)
    facts = FS.decision_facts("408", book, "NQ", "1m", 1, 100.0, 99.0, 1.0, "5m")
    assert facts["152_roc"] == 0.001 and facts["152_roc_5m"] == 0.002 and facts["310_value"] == 2.0
    assert facts["factor_momentum_higher"] is True and facts["factor_z_not_extreme"] is False
    assert facts["163_ratio"] is None and facts["factor_acceleration"] is False


async def _atom(tmp_path, monkeypatch, bus):
    monkeypatch.setattr(m.card_ledger_birth, "movement_floor", lambda symbol: None)
    atom = m.Atom()
    await atom.initialize(m.AtomContext(465, {
        "store_path": str(tmp_path / "cards.db"), "dead_target_ttl_s": 4740.0,
        "max_open_age_s": 86400.0, "max_dispatch_age_s": 900.0, "min_rr": 3.0,
        "reversal_cooldown_s": 30.0, "flush_every_s": 5.0}, _Null(), bus.publish, bus.subscribe))
    await atom.start()
    await atom._on_approved({"symbol": "NQ", "approved": True, "decision_side": "buy",
                             "decision_id": "D1", "account_id": "A1", "broker": "BR"})
    return atom


def _setup(evidence):
    return {**build_setup(
        owner="405", setup_type="MEAN_REVERSION", side="buy", entry_reference=100.0,
        invalidation_price=99.0, invalidation_source="202:5m_swing_low", invalidation_reason="تحت القاع",
        target_price=103.0, target_source="405:3R", target_reason="3R", account_id="A1", broker="BR",
        symbol="NQ", cycle_id="S1", period_start=0.0, evidence=evidence, created_at=time.time(), ttl_s=120.0),
        "setup_id": "S1"}


async def _writes(atom):
    card_no = atom._live["NQ"]["card_no"]
    await atom._flush()
    return {(w["author"], w["field"]): w["value"] for w in CardStore(atom._store.path).writes(card_no)}


async def test_card_carries_the_decision_facts(tmp_path, monkeypatch):
    atom = await _atom(tmp_path, monkeypatch, _Bus())
    facts = FS.decision_facts("405", _book_405(-1.8), "NQ", "5m", 1, 100.0, 99.0, 1.0, "5m")
    await atom._on_setup(_setup({"frame": "5m", "factors": "0/0", "facts": facts}))
    line = (await _writes(atom))[("405", "حقيقة القرار")]
    assert "310_value=-1.8" in line and "frame=5m" in line and "stop_points=1.0" in line
    await atom.stop()


async def test_setup_without_facts_adds_no_line(tmp_path, monkeypatch):
    atom = await _atom(tmp_path, monkeypatch, _Bus())
    await atom._on_setup(_setup({"frame": "5m"}))
    writes = await _writes(atom)
    assert ("405", "stop") in writes and ("405", "حقيقة القرار") not in writes
    await atom.stop()
