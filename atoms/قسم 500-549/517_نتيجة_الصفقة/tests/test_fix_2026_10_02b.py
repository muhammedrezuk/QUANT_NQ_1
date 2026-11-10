# ٢٠٢٦-١٠-٠٢ (ختم المالك «صلح كامل nq»): عمولة صفقة الدخول تدخل نتيجة المركز مرّةً واحدة.
#
# المقيس قبل الإصلاح (الجسر قراءةً فقط): 880 حدث فتح كلّها بعمولةٍ فارغة، وعمولات
# الإغلاق وحدها في النتيجة — الذهب 3.50$/لوت لكلّ اتّجاه ⟸ نحو 812$ غائبة.
# الأرقام هنا بعيار الذهب نفسه: لوتٌ واحد ⟸ 3.50$ دخولًا و3.50$ خروجًا.
import os
import sys
import tempfile

from pathlib import Path as _Path
sys.path.insert(0, str(_Path(__file__).resolve().parents[4]))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.contracts.atom import AtomContext  # noqa: E402
import importlib.util as _ilu  # noqa: E402

_spec = _ilu.spec_from_file_location(
    "_atom517_fix_b", _Path(__file__).resolve().parents[1] / "atom.py")
_mod = _ilu.module_from_spec(_spec)
sys.modules["_atom517_fix_b"] = _mod
_spec.loader.exec_module(_mod)
Atom = _mod.Atom
EVENT_OUT = _mod.EVENT_OUT


class _Log:
    def __getattr__(self, _name):
        return lambda *a, **k: None


class _Bus:
    def __init__(self):
        self.published = []

    def subscribe(self, name, handler):
        pass

    async def publish(self, name, payload):
        self.published.append((name, payload))


async def _new(db_path=None):
    bus = _Bus()
    atom = Atom()
    if db_path is None:
        atom._test_tmp = tempfile.TemporaryDirectory()
        db_path = os.path.join(atom._test_tmp.name, "consumer.db")
    await atom.initialize(AtomContext(atom_id=517, config={"consumer_db_path": db_path},
                                      logger=_Log(), publish=bus.publish,
                                      subscribe=bus.subscribe))
    await atom.start()
    await atom._on_account({"account_id": "ACC", "broker": "BR"})
    await atom._on_truth_equity({"account_id": "ACC", "broker": "BR", "equity": 1000.0})
    return atom, bus, db_path


def _opened(commission=None, volume=1.0, row=100, ticket=7):
    # شكل ٦١١ حرفًا: بلا وسيط ولا event_id، ومعرّف الصفّ في `source_row_id`.
    return {"event_type": "OPENED", "ticket": ticket, "symbol": "XAUUSD", "side": "BUY",
            "volume": volume, "entry_price": 4000.0, "account_id": "ACC", "profit": None,
            "request_id": "555-abc", "source_row_id": row, "commission": commission,
            "swap": None if commission is None else 0.0,
            "fee": None if commission is None else 0.0}


def _positions(volume, commission, ticket=7):
    return {"account_id": "ACC", "broker": "BR", "source": "609",
            "positions": [{"ticket": ticket, "symbol": "XAUUSD", "side": "BUY",
                           "volume": volume, "commission": commission,
                           "commission_status": "AVAILABLE",
                           "account_id": "ACC", "broker": "BR"}]}


def _leg(kind, volume, profit, commission, row, ticket=7):
    return {"event_id": "execution-confirm:%s:%d" % (kind, row), "account_id": "ACC",
            "broker": "BR", "symbol": "XAUUSD", "ticket": ticket, "trade_identity": str(ticket),
            "event_type": kind, "volume": volume, "exit_price": 4010.0 + row,
            "profit": profit, "commission": commission, "swap": 0.0, "fee": 0.0}


def _results(bus):
    return [p for n, p in bus.published if n == EVENT_OUT]


async def test_old_expert_entry_commission_comes_from_the_position_snapshot():
    """الإكسبرت 3.17: حدث الفتح بلا عمولة — تُقرأ من صورة ٦٠٩ (−3.5 للوت)."""
    atom, bus, _ = await _new()
    await atom._on_trade_event(_opened(commission=None))
    await atom._on_positions(_positions(1.0, -3.5))
    await atom._on_outcome(_leg("CLOSED", 1.0, 10.0, -3.5, 1))
    out = _results(bus)
    assert len(out) == 1, out
    # قبل الإصلاح: 10 − 3.5 = 6.5 (نصف الدورة غائب)
    assert out[0]["pnl"] == 3.0, out[0]["pnl"]
    assert out[0]["commission"] == -7.0, out[0]["commission"]
    assert out[0]["entry_costs_included"] is True
    assert out[0]["entry_costs_source"] == "POSITION_SNAPSHOT"
    assert out[0]["costs_complete"] is True and out[0]["completeness"] == "COMPLETE"


async def test_new_expert_entry_commission_comes_from_the_opening_deal():
    """الإكسبرت 3.18: حدث الفتح يحمل عمولة صفقة الدخول نفسها."""
    atom, bus, _ = await _new()
    await atom._on_trade_event(_opened(commission=-3.5))
    await atom._on_outcome(_leg("CLOSED", 1.0, 10.0, -3.5, 1))
    out = _results(bus)[-1]
    assert out["pnl"] == 3.0 and out["entry_costs_source"] == "OPENED_DEAL", out


async def test_both_sources_never_add_it_twice():
    atom, bus, _ = await _new()
    await atom._on_trade_event(_opened(commission=-3.5))
    await atom._on_positions(_positions(1.0, -3.5))
    await atom._on_positions(_positions(1.0, -3.5))
    await atom._on_outcome(_leg("CLOSED", 1.0, 10.0, -3.5, 1))
    out = _results(bus)[-1]
    assert out["commission"] == -7.0 and out["pnl"] == 3.0, out


async def test_snapshot_after_an_unrecorded_partial_is_not_used_until_it_is_recorded():
    """صورةٌ بعد جزءٍ لم يصل بعد: عمولتها دخولٌ + خروجُ الجزء — لا تُحسب دخولًا."""
    atom, bus, _ = await _new()
    await atom._on_trade_event(_opened(commission=None))
    # الوسيط أغلق 0.3 (عمولة −1.05) والصورة سبقت حدثه: 0.7 بعمولة −4.55
    await atom._on_positions(_positions(0.7, -4.55))
    assert atom._awaiting_entry, "حُسبت عمولة دخول من صورةٍ لا تثبتها"
    await atom._on_outcome(_leg("PARTIAL", 0.3, 3.0, -1.05, 1))
    # الآن الصورة نفسها تثبت: 0.7 + 0.3 = 1.0 ⟸ الدخول = −4.55 − (−1.05) = −3.5
    assert not atom._awaiting_entry
    await atom._on_outcome(_leg("CLOSED", 0.7, 7.0, -2.45, 2))
    out = _results(bus)[-1]
    assert out["commission"] == -7.0, out["commission"]          # −1.05 −2.45 −3.5
    assert out["pnl"] == 3.0, out["pnl"]                          # 10 − 7


async def test_zero_from_the_deal_is_not_proof_the_snapshot_decides():
    atom, bus, _ = await _new()
    await atom._on_trade_event(_opened(commission=0.0))
    await atom._on_positions(_positions(1.0, -3.5))
    await atom._on_outcome(_leg("CLOSED", 1.0, 10.0, -3.5, 1))
    out = _results(bus)[-1]
    assert out["pnl"] == 3.0 and out["entry_costs_source"] == "POSITION_SNAPSHOT", out


async def test_entry_is_applied_once_across_a_restart():
    atom, bus, db = await _new()
    await atom._on_trade_event(_opened(commission=None))
    await atom._on_positions(_positions(1.0, -3.5))
    await atom.stop()
    # إقلاعٌ جديد على المخزن نفسه، ثمّ يُعاد الحدثان كما يعيدهما الناقل.
    again, bus2, _ = await _new(db)
    await again._on_trade_event(_opened(commission=None))
    await again._on_positions(_positions(1.0, -3.5))
    await again._on_outcome(_leg("CLOSED", 1.0, 10.0, -3.5, 1))
    await again._on_outcome(_leg("CLOSED", 1.0, 10.0, -3.5, 1))   # تكرار الإغلاق
    out = _results(bus2)
    assert len(out) == 1, out
    assert out[0]["commission"] == -7.0 and out[0]["pnl"] == 3.0, out[0]


async def test_old_rows_without_any_entry_source_still_complete():
    """بلا فتحٍ مرئيّ ولا صورة: النتيجة كما كانت — كاملة، والغياب معلَن لا مُصفَّر."""
    atom, bus, _ = await _new()
    await atom._on_outcome(_leg("CLOSED", 1.0, 10.0, -3.5, 1))
    out = _results(bus)[-1]
    assert out["completeness"] == "COMPLETE" and out["pnl"] == 6.5, out
    assert out["entry_costs_included"] is False and out["entry_commission"] is None
    assert atom._entry_missing == 1


async def test_entry_after_the_result_is_kept_not_published_as_a_trade():
    atom, bus, _ = await _new()
    await atom._on_outcome(_leg("CLOSED", 1.0, 10.0, -3.5, 1))
    before = len(_results(bus))
    await atom._on_trade_event(_opened(commission=-3.5))
    assert len(_results(bus)) == before, "عمولةٌ وحدها نُشرت صفقةً عند ٥١٦"
    assert atom._entry_late == 1
    health = await atom.health_check()
    assert "بعد_النتيجة=1" in health.message, health.message
