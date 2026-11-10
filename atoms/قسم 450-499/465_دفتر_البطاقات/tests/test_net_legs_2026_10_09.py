"""٢٠٢٦-١٠-٠٩ (ختم المالك «NQ» — الصفقة صافيةً بأجزائها): البطاقة لا تُغلق إلّا بالإغلاق الأخير لتذكرتها.

«لازم ينحسب: إذا ضرب الهدف الأوّل ورجع ضرب الدخول، أو هدف ثاني ثمّ ضرب التأمين على الهدف الأوّل — يعني إغلاق
صفقة على صافي كم R ربح». سيناريوهات المالك بالأرقام على عقدٍ واحد: دخول 100 · وقف مرسَل 99 · هدف مرسَل 103
· مبلغ المخاطرة 100$ (نقطةٌ واحدة × 100$ للعقد) — فالهدف الأوّل 101 والثاني 102 والثالث 103.

⛔ كلُّ مخزنٍ هنا في `tmp_path` — كما في `test_atom.py`. و552 و563 يُمثَّلان بكتابة أعمدتهما على المخزن.
"""
import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[4]
FOLDER = Path(__file__).resolve().parents[1]
for _path in (str(ROOT), str(ROOT / "clock"), str(FOLDER)):
    if _path not in sys.path:
        sys.path.insert(0, _path)

_spec = importlib.util.spec_from_file_location("_t465_net", FOLDER / "atom.py")
m = importlib.util.module_from_spec(_spec)
sys.modules["_t465_net"] = m
_spec.loader.exec_module(m)

from shared.trade_card import CardStore  # noqa: E402


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

    def names(self, event):
        return [p for n, p in self.published if n == event]


async def _filled(tmp_path, monkeypatch, volume=1.0, risk=100.0, ticket="T1", levels=(100.0, 99.0, 103.0)):
    """بطاقةٌ وُلدت وأُرسلت ونُفّذت (تأكيد 563)، وعليها ما يكتبه 552: المخاطرة والوقف والهدف المرسَلان."""
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
    await atom._on_passed({"symbol": "NQ", "decision_side": "buy", "decision_id": "D1",
                           "gate_request_id": "G1"})
    await atom._on_ack({"status": "ACK", "symbol": "NQ", "ticket": ticket, "side": "BUY",
                        "entry_price": 100.0, "volume": volume})
    card_no = atom._live["NQ"]["card_no"]
    await atom._flush()
    fill, sent_stop, sent_target = levels
    atom._store.update(card_no, {"risk_amount": risk, "sent_stop": sent_stop, "sent_target": sent_target,
                                 "fill_price": fill, "volume": volume})
    return atom, bus, card_no


def _leg(event, volume, price, profit, reason="SYSTEM", commission=0.0, ticket="T1", entry=100.0):
    """حدث 563 على `market.outcome.realized` لجزءٍ واحد — بأرقام الوسيط."""
    return {"symbol": "NQ", "event_type": event, "ticket": ticket, "volume": volume,
            "entry_price": entry, "exit_price": price, "profit": profit,
            "commission": commission, "swap": 0.0, "fee": 0.0, "reason": reason, "side": "BUY",
            "result": "WIN" if profit > 0 else "LOSS" if profit < 0 else "BREAKEVEN"}


async def _card(atom, card_no):
    await atom._flush()
    return CardStore(atom._store.path).card(card_no)


async def test_a_first_target_then_back_to_entry(tmp_path, monkeypatch):
    """(أ) الهدف الأوّل ثمّ عودةٌ إلى الدخول: ثلث العقد +33$ ثمّ الباقي على وقف التعادل 0$ ⟸ +0.33R."""
    atom, bus, card_no = await _filled(tmp_path, monkeypatch)
    await atom._on_outcome(_leg("PARTIAL", 0.33, 101.0, 33.0))
    # الجزئيّ لا يُغلق: البطاقة حيّة «منفَّذة»، ونتيجتها «مفتوحة جزئيًّا» بربح الجزء.
    assert atom._live["NQ"]["state"] == "FILLED" and bus.names(m.EVENT_CLOSED) == []
    open_card = await _card(atom, card_no)
    assert open_card["state"] == "FILLED" and open_card["outcome"] == "PARTIAL"
    assert open_card["profit"] == pytest.approx(33.0)
    assert open_card["body"]["net"]["status"] == "partial_open"
    assert [leg["stage"] for leg in open_card["body"]["legs"]] == ["first_target"]
    await atom._on_outcome(_leg("CLOSED", 0.67, 100.0, 0.0, reason="SL"))
    assert "NQ" not in atom._live
    card = await _card(atom, card_no)
    assert card["state"] == "CLOSED" and card["outcome"] == "WIN"
    assert card["profit"] == pytest.approx(33.0)
    net = card["body"]["net"]
    assert net["net_r"] == pytest.approx(0.33) and net["exit"] == "breakeven"
    assert [leg["stage"] for leg in card["body"]["legs"]] == ["first_target", "breakeven"]
    closed = bus.names(m.EVENT_CLOSED)
    assert len(closed) == 1 and closed[0]["net_r"] == pytest.approx(0.33)
    assert closed[0]["profit"] == pytest.approx(33.0) and closed[0]["legs"] == 2
    writes = {(w["author"], w["field"]): w["value"] for w in CardStore(atom._store.path).writes(card_no)}
    assert writes[("465", "partial_1")].startswith("الهدف الأوّل: 0.33 @101")
    assert writes[("465", "net")].startswith("صافي +33.00$ = +0.33R على 2 أجزاء · على التعادل")
    await atom.stop()


async def test_b_two_targets_then_protective_stop_on_first(tmp_path, monkeypatch):
    """(ب) الهدف الأوّل ثمّ الثاني ثمّ وقف التأمين على الهدف الأوّل، وعمولة دولارٍ على كلّ جزء:
    +33 + 68 + 33 − 3 = +131$ ⟸ +1.31R."""
    atom, bus, card_no = await _filled(tmp_path, monkeypatch)
    await atom._on_outcome(_leg("PARTIAL", 0.33, 101.0, 33.0, commission=-1.0))
    await atom._on_outcome(_leg("PARTIAL", 0.34, 102.0, 68.0, commission=-1.0))
    assert (await _card(atom, card_no))["profit"] == pytest.approx(99.0)        # جاريًا: 101 − 2
    await atom._on_outcome(_leg("CLOSED", 0.33, 101.0, 33.0, reason="SL", commission=-1.0))
    card = await _card(atom, card_no)
    net = card["body"]["net"]
    assert card["profit"] == pytest.approx(131.0) and net["net_r"] == pytest.approx(1.31)
    assert (net["gross_usd"], net["costs_usd"]) == (pytest.approx(134.0), pytest.approx(-3.0))
    assert [leg["stage"] for leg in card["body"]["legs"]] == [
        "first_target", "second_target", "protective_stop"]
    assert net["exit_ar"] == "على وقف التأمين"
    assert atom._partials == 2
    await atom.stop()


async def test_c_all_three_targets(tmp_path, monkeypatch):
    """(ج) الأهداف الثلاثة: +33 + 68 + 99 = +200$ ⟸ +2.00R، والأخير على الهدف (أبلغ الوسيط TP)."""
    atom, bus, card_no = await _filled(tmp_path, monkeypatch)
    await atom._on_outcome(_leg("PARTIAL", 0.33, 101.0, 33.0))
    await atom._on_outcome(_leg("PARTIAL", 0.34, 102.0, 68.0))
    await atom._on_outcome(_leg("CLOSED", 0.33, 103.0, 99.0, reason="TP"))
    card = await _card(atom, card_no)
    assert card["profit"] == pytest.approx(200.0) and card["body"]["net"]["net_r"] == pytest.approx(2.0)
    assert card["body"]["net"]["exit"] == "target"
    assert bus.names(m.EVENT_CLOSED)[0]["exit"] == "target"
    await atom.stop()


async def test_d_original_stop_directly(tmp_path, monkeypatch):
    """(د) الوقف الأصليّ مباشرةً، وتجاوزه بخمس سنتات: −105$ ⟸ −1.05R — والهدف يموت (حارس 465 كما كان)."""
    atom, bus, card_no = await _filled(tmp_path, monkeypatch)
    await atom._on_outcome(_leg("CLOSED", 1.0, 98.95, -105.0, reason="SL"))
    card = await _card(atom, card_no)
    assert card["state"] == "CLOSED" and card["outcome"] == "LOSS"
    assert card["body"]["net"]["net_r"] == pytest.approx(-1.05)
    assert card["body"]["net"]["exit"] == "original_stop"
    assert "NQ" in atom._dead_target
    await atom.stop()


async def test_e_small_contract_exits_whole_at_third_target(tmp_path, monkeypatch):
    """(هـ) عقدٌ صغير لا يتجزّأ (0.01) يمضي إلى الهدف الثالث ويُغلقه النظام كاملًا: +3$ على مخاطرة 1$ ⟸ +3R."""
    atom, bus, card_no = await _filled(tmp_path, monkeypatch, volume=0.01, risk=1.0)
    await atom._on_outcome(_leg("CLOSED", 0.01, 103.0, 3.0, reason="SYSTEM"))
    card = await _card(atom, card_no)
    assert card["body"]["net"]["legs"] == 1 and card["body"]["net"]["partials"] == 0
    assert card["body"]["net"]["net_r"] == pytest.approx(3.0)
    assert card["body"]["net"]["exit"] == "target"                 # إغلاق النظام عند الهدف المرسَل كاملًا
    await atom.stop()


@pytest.mark.parametrize("ticket, volume, risk, levels, legs, net, r, stages", [
    # البطاقة 86470: 0.4 بـ+30.72 · 0.4 بـ+59.64 · 0.5 TP بـ+113.15 على مخاطرة 92.60$ ⟸ +2.20R (البطاقة القديمة +0.33R).
    ("1993419479", 1.3, 92.6, (30936.4, 30861.71734675, 31161.718609),
     (("PARTIAL", 0.4, 31013.2, 30.72, "SYSTEM"), ("PARTIAL", 0.4, 31085.5, 59.64, "SYSTEM"),
      ("CLOSED", 0.5, 31162.7, 113.15, "TP")), 203.51, 2.1977, ["first_target", "second_target", "target"]),
    # البطاقة 86426: 3.0 بـ+66.60 ثمّ 6.2 SL بـ+65.10 على مخاطرة 90.06$ ⟸ +1.46R (القديمة +0.74R) — الوقف +0.96 في الربح.
    ("1992552417", 9.2, 90.06, (31108.5, 31097.611241, 31205.916336),
     (("PARTIAL", 3.0, 31130.7, 66.6, "SYSTEM"), ("CLOSED", 6.2, 31119.0, 65.1, "SL")),
     131.7, 1.4624, ["first_target", "protective_stop"]),
])
async def test_live_tickets_replay(tmp_path, monkeypatch, ticket, volume, risk, levels, legs, net, r, stages):
    """التذكرتان الحيّتان بأرقام الوسيط كما قُرئت من `trade_events_v2` ٢٠٢٦-١٠-٠٩."""
    atom, bus, card_no = await _filled(tmp_path, monkeypatch, volume=volume, risk=risk, ticket=ticket,
                                       levels=levels)
    for event, leg_volume, price, profit, reason in legs:
        await atom._on_outcome(_leg(event, leg_volume, price, profit, reason, ticket=ticket, entry=levels[0]))
    card = await _card(atom, card_no)
    assert card["profit"] == pytest.approx(net)
    assert card["body"]["net"]["net_r"] == pytest.approx(r, abs=1e-4)
    assert [leg["stage"] for leg in card["body"]["legs"]] == stages
    await atom.stop()


async def test_duplicate_leg_counts_once_and_563_overwrite_is_undone(tmp_path, monkeypatch):
    """الإكسبرت يكتب الجزء مرّتين أحيانًا، و563 يكتب ربح كلّ جزءٍ وحده فوق البطاقة — والصافي لا يتبدّل."""
    atom, bus, card_no = await _filled(tmp_path, monkeypatch)
    await atom._on_outcome(_leg("PARTIAL", 0.33, 101.0, 33.0))
    await atom._flush()
    atom._store.update(card_no, {"profit": 33.0, "outcome": "WIN"})            # 563 يكتب الجزء نفسه ثانيةً
    await atom._on_outcome(_leg("PARTIAL", 0.33, 101.0, 33.0))
    assert atom._dup_legs == 1 and len(atom._live["NQ"]["legs"]) == 1
    card = await _card(atom, card_no)
    assert card["profit"] == pytest.approx(33.0) and card["outcome"] == "PARTIAL"
    await atom.stop()


async def test_foreign_and_late_legs_never_close_the_wrong_card(tmp_path, monkeypatch):
    """جزءُ تذكرةٍ أخرى لا يُغلق البطاقة؛ وجزءٌ يصل بعد إغلاق بطاقة تذكرته يعود إليها (إغلاقان بينهما ثانية)."""
    atom, bus, card_no = await _filled(tmp_path, monkeypatch)
    await atom._on_outcome(_leg("CLOSED", 0.5, 99.0, -50.0, reason="SL", ticket="OTHER"))
    assert "NQ" in atom._live and atom._foreign_legs == 1 and bus.names(m.EVENT_CLOSED) == []
    # إغلاقان للتذكرة (مقيس على 29 تذكرة): 0.28 بالنظام ثمّ 0.72 بالهدف.
    await atom._on_outcome(_leg("CLOSED", 0.28, 101.0, 28.0, reason="SYSTEM"))
    assert "NQ" not in atom._live and len(bus.names(m.EVENT_CLOSED)) == 1
    await atom._on_outcome(_leg("CLOSED", 0.72, 103.0, 216.0, reason="TP"))
    assert atom._late_legs == 1
    card = await _card(atom, card_no)
    assert card["profit"] == pytest.approx(244.0) and card["body"]["net"]["net_r"] == pytest.approx(2.44)
    await atom.stop()


async def test_extra_fill_ticket_is_foreign_and_partials_survive_reboot(tmp_path, monkeypatch):
    """مركزٌ ثانٍ على الرمز لا تتبنّاه البطاقة؛ وأجزاءُ صفقةٍ مفتوحة جزئيًّا تُستعاد بعد الإقلاع."""
    atom, bus, card_no = await _filled(tmp_path, monkeypatch)
    await atom._on_ack({"status": "ACK", "symbol": "NQ", "ticket": "T2", "side": "BUY",
                        "entry_price": 100.5, "volume": 1.0})
    assert "T2" in atom._foreign_tickets
    await atom._on_outcome(_leg("PARTIAL", 0.33, 101.0, 33.0))
    await atom.stop()
    fresh = m.Atom()
    await fresh.initialize(m.AtomContext(465, {
        "store_path": str(tmp_path / "cards.db"), "dead_target_ttl_s": 4740.0,
        "max_open_age_s": 86400.0, "max_dispatch_age_s": 900.0, "min_rr": 3.0,
        "reversal_cooldown_s": 30.0, "flush_every_s": 5.0}, _Null(), _Bus().publish, _Bus().subscribe))
    await fresh.start()
    live = fresh._live["NQ"]
    assert live["card_no"] == card_no and [leg["stage"] for leg in live["legs"]] == ["first_target"]
    await fresh._on_outcome(_leg("CLOSED", 0.67, 100.0, 0.0, reason="SL"))
    card = await _card(fresh, card_no)
    assert card["profit"] == pytest.approx(33.0) and card["body"]["net"]["legs"] == 2
    health = await fresh.health_check()
    assert "أجزاء=0" in health.message                       # العدّاد للحياة الجديدة وحدها
    await fresh.stop()
