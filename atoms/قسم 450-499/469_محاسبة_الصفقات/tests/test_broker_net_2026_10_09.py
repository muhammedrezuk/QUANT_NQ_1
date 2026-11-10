"""٢٠٢٦-١٠-٠٩ (ختم المالك «NQ» — الصفقة صافيةً بأجزائها): الصافي من سجلّ الوسيط نفسه، لا من البطاقة.

«نحن نشتغل نجمع R — كم R خسرنا مقابل كم ربحنا صافي… R عنّا 100 دولار» و«إذا ضرب الهدف الأوّل ورجع ضرب الدخول، أو
هدف ثاني ثمّ ضرب التأمين على الهدف الأوّل — إغلاق صفقة على صافي كم R ربح». كلّ سيناريو من سيناريوهات المالك تذكرةٌ
بأحداث الوسيط (`trade_events_v2` بمخطّط الجسر الحيّ حرفيًّا) وبطاقةٌ تحمل ما سجّله 465 القديم (الجزء الأوّل وحده).
عقدٌ واحد: دخول 100 · وقف مرسَل 99 · هدف مرسَل 103 · مخاطرة 100$ — فالهدف الأوّل 101 والثاني 102 والثالث 103.

⛔ كلُّ قاعدةٍ هنا في `tmp_path` — لا يُقرأ الدفتر الحيّ ولا الجسر الحيّ من اختبار (`conftest.py` يرفع `NQ_BRIDGE_DB`).
"""
import asyncio
import calendar
import importlib.util
import sqlite3
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[4]
FOLDER = Path(__file__).resolve().parents[1]
for _path in (str(ROOT), str(FOLDER)):
    if _path not in sys.path:
        sys.path.insert(0, _path)

_spec = importlib.util.spec_from_file_location("_t469_broker", FOLDER / "atom.py")
m = importlib.util.module_from_spec(_spec)
sys.modules["_t469_broker"] = m
_spec.loader.exec_module(m)

import accountability_broker as broker  # noqa: E402
import accountability_text as report  # noqa: E402
from core.contracts.atom import AtomContext, HealthState  # noqa: E402
from shared.trade_card import CardStore, STATE_CLOSED  # noqa: E402

LONDON = calendar.timegm(time.strptime("2026-10-07 07:20", "%Y-%m-%d %H:%M"))
NY = calendar.timegm(time.strptime("2026-10-07 13:45", "%Y-%m-%d %H:%M"))
#: مخطّط الجسر الحيّ كما قرأته من `nq_brain.db` (٢٠٢٦-١٠-٠٩) — حرفيًّا.
BRIDGE_SCHEMA = (
    "CREATE TABLE trade_events_v2 (id INTEGER PRIMARY KEY AUTOINCREMENT, account_id TEXT NOT NULL,"
    "event_type TEXT NOT NULL,ticket INTEGER,symbol TEXT NOT NULL,side TEXT NOT NULL,volume REAL NOT NULL,"
    "entry_price REAL,exit_price REAL,open_time REAL,close_time REAL,reason TEXT,request_id TEXT,"
    "profit REAL,commission REAL,swap REAL,fee REAL,written_at REAL NOT NULL)")
ACCOUNT = "52992818"


class _Null:
    def __getattr__(self, name):
        return lambda *args, **kwargs: None


class _Bus:
    def __init__(self):
        self.published = []
        self.subscribed = []

    def subscribe(self, name, handler):
        self.subscribed.append((name, handler))

    async def publish(self, name, payload=None):
        self.published.append((name, payload))


def _bridge(path, tickets):
    """قاعدة جسرٍ مؤقّتة: لكلّ تذكرة صفُّ فتحٍ ثمّ أجزاؤها بترتيبها (`written_at` يتقدّم دقيقةً لكلّ صفّ)."""
    connection = sqlite3.connect(str(path))
    connection.execute(BRIDGE_SCHEMA)
    for ticket, symbol, side, volume, entry, at, legs in tickets:
        connection.execute(
            "INSERT INTO trade_events_v2 (account_id,event_type,ticket,symbol,side,volume,entry_price,"
            "open_time,commission,swap,fee,written_at,request_id) VALUES (?,?,?,?,?,?,?,?,0,0,0,?,?)",
            (ACCOUNT, "OPENED", ticket, symbol, side, volume, entry, at, at, "555-x"))
        for index, (event, leg_volume, price, profit, reason, commission) in enumerate(legs, start=1):
            connection.execute(
                "INSERT INTO trade_events_v2 (account_id,event_type,ticket,symbol,side,volume,entry_price,"
                "exit_price,open_time,close_time,reason,profit,commission,swap,fee,written_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,0,0,?)",
                (ACCOUNT, event, ticket, symbol, side, leg_volume, entry, price, at, at + 60 * index,
                 reason, profit, commission, at + 60 * index))
    connection.commit()
    connection.close()


def _card(store, ticket, *, opened_at=LONDON, side="buy", entry=100.0, stop=99.0, target=103.0,
          volume=1.0, risk=100.0, recorded=None, symbol="USTEC", body=None, filled=False):
    """بطاقةٌ كما كتبها 465 و552 و563 القديم: التذكرة، والمخاطرة، وربح **الجزء الأوّل وحده** (`recorded`)."""
    card_no, fresh = store.open_card(symbol, ACCOUNT, "Raw Trading Ltd", side, at=opened_at, body={})
    assert fresh
    store.update(card_no, {"entry": entry, "stop": stop, "target": target,
                           "stop_points": abs(entry - stop), "fill_price": entry, "sent_stop": stop,
                           "sent_target": target, "risk_amount": risk, "volume": volume,
                           "ticket": None if filled == "only" else str(ticket),
                           "dispatched_at": opened_at + 5}, body=body, at=opened_at)
    if filled:
        store.note(card_no, "563", "filled", "%s %s @%s" % (ticket, side, entry), at=opened_at + 6)
    store.set_state(card_no, STATE_CLOSED, at=opened_at + 600,
                    outcome="WIN" if (recorded or 0) > 0 else "LOSS", profit=recorded)
    return card_no


WIN_BODY = {"setup_id": "414:USTEC:1791300000", "setup_type": "TREND_CONTINUATION_PULLBACK",
            "invalidation_reason": "تحت قاع الارتداد", "target_reason": "أقرب مستوى ساعة"}

#: (التذكرة، الأجزاء) لكلّ سيناريو — (النوع، الحجم، السعر، الربح، سبب الوسيط، العمولة).
SCENARIOS = {
    "a": (1001, [("PARTIAL", 0.33, 101.0, 33.0, "SYSTEM", 0.0), ("CLOSED", 0.67, 100.0, 0.0, "SL", 0.0)]),
    "b": (1002, [("PARTIAL", 0.33, 101.0, 33.0, "SYSTEM", -1.0), ("PARTIAL", 0.34, 102.0, 68.0, "SYSTEM", -1.0),
                 ("CLOSED", 0.33, 101.0, 33.0, "SL", -1.0)]),
    "c": (1003, [("PARTIAL", 0.33, 101.0, 33.0, "SYSTEM", 0.0), ("PARTIAL", 0.34, 102.0, 68.0, "SYSTEM", 0.0),
                 ("CLOSED", 0.33, 103.0, 99.0, "TP", 0.0)]),
    "d": (1004, [("CLOSED", 1.0, 98.95, -105.0, "SL", 0.0)]),
    "e": (1005, [("CLOSED", 0.01, 103.0, 3.0, "SYSTEM", 0.0)]),
}


def _book(tmp_path):
    """الدفتر والجسر بالسيناريوهات الخمسة، ثمّ صفقتا ٠٩-١٠ الحيّتان بأرقامهما."""
    store = CardStore(str(tmp_path / "cards.db"))
    store.ensure()
    rows, cards = [], {}
    for index, (name, (ticket, legs)) in enumerate(sorted(SCENARIOS.items())):
        volume = 0.01 if name == "e" else 1.0
        at = LONDON + index * 3600
        cards[name] = _card(store, ticket, opened_at=at, volume=volume, risk=1.0 if name == "e" else 100.0,
                            recorded=legs[0][3], body=WIN_BODY if name in "abc" else None)
        rows.append((ticket, "USTEC", "BUY", volume, 100.0, at, legs))
    # 86470 / 1993419479 و 86426 / 1992552417 — أرقام الوسيط والبطاقة كما قُرئت من الحيّ.
    cards["86470"] = _card(store, 1993419479, opened_at=NY, entry=30936.4, stop=30861.71734675,
                           target=31161.718609, volume=1.3, risk=92.6, recorded=30.72, filled=True)
    rows.append((1993419479, "USTEC", "BUY", 1.3, 30936.4, NY, [
        ("PARTIAL", 0.4, 31013.2, 30.72, "SYSTEM", 0.0), ("PARTIAL", 0.4, 31085.5, 59.64, "SYSTEM", 0.0),
        ("CLOSED", 0.5, 31162.7, 113.15, "TP", 0.0)]))
    cards["86426"] = _card(store, 1992552417, opened_at=NY + 3600, entry=31108.5, stop=31097.611241,
                           target=31205.916336, volume=9.2, risk=90.06, recorded=66.6)
    rows.append((1992552417, "USTEC", "BUY", 9.2, 31108.5, NY + 3600, [
        ("PARTIAL", 3.0, 31130.7, 66.6, "SYSTEM", 0.0), ("CLOSED", 6.2, 31119.0, 65.1, "SL", 0.0)]))
    _bridge(tmp_path / "bridge.db", rows)
    return store, cards


def _build(tmp_path, bridge="bridge.db"):
    return report.build_payload(str(tmp_path / "cards.db"), time.time(), 10, 10, 5.0,
                                str(tmp_path / bridge) if bridge else None)


def _trade(payload, card_no):
    return next(row for row in payload["facts"]["trades"] if row["card_no"] == card_no)


def test_owner_scenarios_net_from_broker(tmp_path):
    _, cards = _book(tmp_path)
    payload = _build(tmp_path)
    facts = payload["facts"]
    assert payload["status"] == "ok" and facts["net_source"] == "broker"
    expected = {"a": (0.33, ["first_target", "breakeven"]),
                "b": (1.31, ["first_target", "second_target", "protective_stop"]),
                "c": (2.0, ["first_target", "second_target", "target"]),
                "d": (-1.05, ["original_stop"]),
                "e": (3.0, ["target"])}
    for name, (r, stages) in expected.items():
        row = _trade(payload, cards[name])
        assert row["net_r"] == pytest.approx(r), name
        assert [leg["stage"] for leg in row["legs"]] == stages, name
    b = _trade(payload, cards["b"])
    assert b["net_usd"] == pytest.approx(131.0) and b["card_r"] == pytest.approx(0.33)
    assert b["r_diff"] == pytest.approx(0.98)                       # البطاقة حملت الجزء الأوّل وحده


def test_live_tickets_give_plus_2_20r_and_plus_1_46r(tmp_path):
    _, cards = _book(tmp_path)
    payload = _build(tmp_path)
    one = _trade(payload, cards["86470"])
    two = _trade(payload, cards["86426"])
    assert (one["net_usd"], round(one["net_r"], 2), round(one["card_r"], 2)) == (203.51, 2.2, 0.33)
    assert (two["net_usd"], round(two["net_r"], 2), round(two["card_r"], 2)) == (131.7, 1.46, 0.74)
    assert [leg["stage"] for leg in two["legs"]] == ["first_target", "protective_stop"]   # +0.96 من الوقف


def test_won_lost_net_totals_and_card_comparison(tmp_path):
    _book(tmp_path)
    facts = _build(tmp_path)["facts"]
    totals = facts["totals"]
    won = 0.33 + 1.31 + 2.0 + 3.0 + 203.51 / 92.6 + 131.7 / 90.06
    assert totals["won_r"] == pytest.approx(won, abs=1e-3) and totals["lost_r"] == pytest.approx(-1.05)
    assert totals["total_r"] == pytest.approx(won - 1.05, abs=1e-3)
    assert (totals["n"], totals["wins"], totals["n_without_r"]) == (7, 6, 0)
    compare = facts["card_vs_broker"]
    cards_r = 0.33 + 0.33 + 0.33 - 1.05 + 3.0 + 30.72 / 92.6 + 66.6 / 90.06
    assert compare["cards_total_r"] == pytest.approx(cards_r, abs=1e-3)
    assert compare["broker_total_r"] == pytest.approx(won - 1.05, abs=1e-3)
    assert compare["diff_r"] == pytest.approx(won - 1.05 - cards_r, abs=1e-3)
    assert compare["trades_card_differs"] == 4                   # ب · ج · 86470 · 86426
    # ولكلّ مجموعةٍ وحقيقة: ربحنا · خسرنا · الصافي.
    assert facts["by_strategy"]["414:TREND_CONTINUATION_PULLBACK"]["won_r"] == pytest.approx(3.64)
    assert facts["by_side"]["long"]["lost_r"] == pytest.approx(-1.05)
    assert set(facts["by_window"]) == {"london_peak", "ny_open", "outside"}
    assert facts["by_window"]["ny_open"]["won_r"] == pytest.approx(203.51 / 92.6 + 131.7 / 90.06, abs=1e-3)
    summary = _build(tmp_path)["summary_ar"]
    assert "ربحنا +%.2fR · خسرنا -1.05R" % won in summary and "البطاقات القديمة قالت" in summary


def test_duplicate_rows_ownership_and_volume_mismatch(tmp_path):
    """الصفّ المكرَّر مرّة · التأكيد يغلب العمود · بطاقةٌ مخاطرتها لأمرٍ آخر ⟸ بالدولار «بلا R» · وتذكرةٌ بلا بطاقة."""
    store = CardStore(str(tmp_path / "cards.db"))
    store.ensure()
    owner = _card(store, 2001, recorded=None, filled="only")                       # سمعت التأكيد، بلا عمود
    stray = _card(store, 2001, opened_at=LONDON + 900, risk=None, recorded=40.0)   # 563 كتب الجزء الثاني عليها
    other = _card(store, 2002, opened_at=LONDON + 1800, volume=5.0, recorded=-60.0)
    _bridge(tmp_path / "bridge.db", [
        (2001, "USTEC", "BUY", 1.0, 100.0, LONDON, [
            ("PARTIAL", 0.33, 101.0, 33.0, "SYSTEM", 0.0), ("PARTIAL", 0.33, 101.0, 33.0, "SYSTEM", 0.0),
            ("CLOSED", 0.67, 100.6, 40.0, "SL", 0.0)]),
        (2002, "USTEC", "SELL", 2.0, 100.0, LONDON + 1800, [("CLOSED", 2.0, 100.3, -60.0, "SL", -2.0)]),
        (2003, "USTEC", "BUY", 1.0, 100.0, LONDON + 2700, [("CLOSED", 1.0, 99.0, -100.0, "SL", 0.0)])])
    facts = _build(tmp_path)["facts"]
    rows = {row["card_no"]: row for row in facts["trades"]}
    assert set(rows) == {owner, other} and stray not in rows
    assert rows[owner]["net_usd"] == pytest.approx(73.0) and rows[owner]["net_r"] == pytest.approx(0.73)
    assert rows[other]["net_r"] is None and rows[other]["risk_note"] == "volume_mismatch"
    assert facts["totals"]["n_without_r"] == 1 and facts["totals"]["usd_without_r"] == pytest.approx(-62.0)
    assert facts["broker_counts"]["broker_tickets_without_card"] == 1
    assert facts["broker_counts"]["tickets_by_confirmed_fill"] == 1
    assert facts["card_vs_broker"]["cards_not_owning_their_profit"] == 1
    last = facts["last_trade"]
    assert last["card_no"] == other and "⟸ -62.00$ (مبلغ المخاطرة على البطاقة لأمرٍ آخر" in last["explain_ar"]


def test_missing_bridge_falls_back_to_cards_and_says_so(tmp_path):
    _book(tmp_path)
    payload = _build(tmp_path, bridge="absent.db")
    facts = payload["facts"]
    assert facts["net_source"] == "cards" and "غير موجودة" in facts["broker_unavailable_reason"]
    assert facts["card_vs_broker"] is None and "سجلّ الوسيط غير متاح" in payload["summary_ar"]
    assert facts["trades_closed"] == 7
    junk = tmp_path / "junk.db"
    sqlite3.connect(str(junk)).close()
    assert "لا جدول" in _build(tmp_path, bridge="junk.db")["facts"]["broker_unavailable_reason"]


def test_broker_payload_carries_no_forbidden_word(tmp_path):
    """عقد الحقائق ١٠-٠٧: لا كلمة جهةٍ أو حكمٍ في الحمولة — ولا في أجزاء الصفقات وأسباب الوسيط."""
    import re
    _book(tmp_path)
    payload = _build(tmp_path)
    assert set(payload) == {"id", "status", "facts", "computed_at", "summary_ar", "source"}
    words = set(re.findall(r"[a-z]+", repr(payload).lower()))
    banned = {"direction", "signal", "strength", "confidence", "weight", "score", "probability",
              "threshold", "depth", "readiness", "buy", "sell", "bullish", "bearish", "strong", "weak"}
    assert not {w for w in words if w in banned or (w.endswith("s") and w[:-1] in banned)}


def test_reading_never_writes_either_store(tmp_path):
    _book(tmp_path)
    before = ((tmp_path / "cards.db").read_bytes(), (tmp_path / "bridge.db").read_bytes())
    _build(tmp_path)
    assert ((tmp_path / "cards.db").read_bytes(), (tmp_path / "bridge.db").read_bytes()) == before


def test_shared_net_rules():
    """`shared/trade_net.py` — الحساب الواحد الذي يقرأ به 465 و469: المفتاح والمراجعة والأسماء والموضع."""
    from shared import trade_net as net
    legs = [net.make_leg("PARTIAL", 0.4, 101.0, 30.0, 0.0, 0.0, 0.0, "SYSTEM", 1.0)]
    assert net.merge_leg(legs, net.make_leg("PARTIAL", 0.4, 101.0, 30.0, 0.0, 0.0, 0.0, "SYSTEM", 2.0)) is False
    assert net.merge_leg(legs, net.make_leg("PARTIAL", 0.4, 101.0, 30.0, -1.5, 0.0, 0.0, "SYSTEM", 3.0))
    assert len(legs) == 1 and legs[0]["net"] == pytest.approx(28.5)        # العمولة المراجَعة تغلب
    assert net.exit_stage("SL_RECOVERED", -1.0, None) == net.EXIT_ORIGINAL
    assert net.exit_stage("SL", 0.2, None) == net.EXIT_BREAKEVEN
    assert net.exit_stage("SL", 0.25, None) == net.EXIT_PROTECTIVE
    assert net.exit_stage("SL", None, None) == net.EXIT_STOP
    assert net.exit_stage("TP_RECOVERED", 0.0, 0.1) == net.EXIT_TARGET
    assert net.exit_stage("SYSTEM", 2.0, 0.66) == net.EXIT_SYSTEM
    assert net.exit_stage("MANUAL", 1.0, 1.0) == net.EXIT_MANUAL
    assert net.exit_stage("RETCODE_10016", 1.0, 1.0) == net.EXIT_OTHER
    # بلا وقفٍ معروف: الموضع بالمال — (ربح الجزء ÷ المخاطرة) × (حجم العقد ÷ حجم الجزء).
    rows = net.label_legs([net.make_leg("PARTIAL", 0.5, None, 25.0, at=1.0),
                           net.make_leg("CLOSED", 0.5, None, -50.0, reason="SL", at=2.0)],
                          "BUY", None, None, None, risk=100.0)
    assert [leg["move_r"] for leg in rows] == [0.5, -1.0] and rows[1]["stage"] == net.EXIT_ORIGINAL
    assert net.summarize(rows, 100.0)["net_r"] == pytest.approx(-0.25)
    assert net.summarize(rows)["net_r"] is None and net.result_of(0.004) == net.RESULT_EVEN


def test_bridge_env_anchor_wins_like_every_bridge_reader(monkeypatch):
    monkeypatch.setenv("NQ_BRIDGE_DB", r"C:\iso\bridge.db")
    assert broker.resolve_bridge_path(r"%APPDATA%\x.db") == r"C:\iso\bridge.db"
    monkeypatch.delenv("NQ_BRIDGE_DB")
    monkeypatch.setenv("APPDATA", r"C:\appdata")
    assert broker.resolve_bridge_path(r"%APPDATA%\x.db") == r"C:\appdata\x.db"


async def test_atom_reads_the_bridge_from_its_config(tmp_path):
    _book(tmp_path)
    bus = _Bus()
    atom = m.Atom()
    config = {"store_path": str(tmp_path / "cards.db"), "bridge_db_path": str(tmp_path / "bridge.db"),
              "boot_delay_s": 0.0, "close_settle_s": 0.0, "min_sample": 10, "top_gaps": 10}
    await atom.initialize(AtomContext(469, config, _Null(), bus.publish, bus.subscribe))
    await atom.start()
    for _ in range(50):
        if not atom._tasks:
            break
        await asyncio.gather(*list(atom._tasks), return_exceptions=True)
    payload = [p for n, p in bus.published if n == "knowledge.accountability.state"][-1]
    assert payload["facts"]["net_source"] == "broker"
    health = await atom.health_check()
    assert health.state == HealthState.HEALTHY and "خسرنا -1.05R" in health.message
    assert "من سجلّ الوسيط" in health.message
    state = await atom.snapshot()
    assert state["net_source"] == "broker" and state["lost_r"] == pytest.approx(-1.05)
    await atom.stop()
