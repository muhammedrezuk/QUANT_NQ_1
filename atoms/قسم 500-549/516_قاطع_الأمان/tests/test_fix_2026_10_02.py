# -*- coding: utf-8 -*-
"""اختبارات إصلاح ٢٠٢٦-١٠-٠٢ (ختم المالك «صلح كامل nq») — 516 قاطع الأمان.

ح-1 من تدقيق ٢٠٢٦-١٠-٠٢: القاطع كان يمسك سببًا واحدًا، فخرقُ الخسارة اليوميّة
تحت `MAX_EXPOSURE` يضيع، ثمّ يفكّ 508 قفله آليًّا فيعود التداول فوق حدٍّ مخروق.
ح١ من تدقيق الخريطة: طلب الإيقاف بلا `account_id` (زرّ «الإيقاف الطارئ الشامل»)
كان يُرمى بصمت. كلّ اختبارٍ هنا يسقط على الإصدار 5.9.3 وينجح على 5.10.0.
"""
import json
import sys
from pathlib import Path as _Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, str(_Path(__file__).resolve().parents[4]))
sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))

import importlib.util as _ilu

_spec = _ilu.spec_from_file_location(
    "_atom516_fix_2026_10_02", _Path(__file__).resolve().parents[1] / "atom.py")
_mod = _ilu.module_from_spec(_spec)
sys.modules["_atom516_fix_2026_10_02"] = _mod
_spec.loader.exec_module(_mod)
Atom = _mod.Atom

from core.contracts.atom import AtomContext  # noqa: E402

HALT, RESET, VALIDATED = _mod.EVENT_HALT, _mod.EVENT_RESET, _mod.EVENT_VALIDATED


class _NullLogger:
    def __getattr__(self, name):
        return lambda *a, **k: None


class FakeEventBus:
    def __init__(self):
        self.published = []

    def subscribe(self, name, handler):
        pass

    async def publish(self, name, payload):
        self.published.append((name, payload))


async def _new(db_path):
    bus = FakeEventBus()
    atom = Atom()
    cfg = {"max_daily_loss_pct": 5, "max_consecutive_losses": 3,
           "max_daily_trades": 20, "max_open_trades": 5,
           "consumer_db_path": str(db_path)}
    await atom.initialize(AtomContext(atom_id=516, config=cfg, logger=_NullLogger(),
                                      publish=bus.publish, subscribe=bus.subscribe))
    await atom.start()
    return atom, bus


async def _seed_account(atom, account="A", broker="BR", equity=1000.0):
    await atom._on_truth_equity({"account_id": account, "broker": broker, "equity": equity})
    await atom._on_account({"account_id": account, "broker": broker})
    await atom._on_terminal({"account_id": account, "connected": True,
                             "trade_allowed": True, "expert_allowed": True})


def _events(bus, name, account=None):
    return [p for n, p in bus.published
            if n == name and (account is None or p.get("account_id") == account)]


async def _validate(atom, bus, account):
    await atom._on_validate({"account_id": account, "broker": "BR", "request_id": "v-" + account,
                             "symbol": "NQ", "action": "OPEN", "risk_budget": 1})
    return _events(bus, VALIDATED, account)[-1]


async def test_fix_1_system_halt_trips_every_book_and_new_accounts(tmp_path):
    """الإيقاف بلا حساب (حمولة اللوحة `{}` وحمولة العقد `scope=SYSTEM`) يوقف الكلّ ومن يأتي بعده."""
    for payload in ({}, {"scope": "SYSTEM"}):
        atom, bus = await _new(tmp_path / ("t1_%d.db" % len(payload)))
        await _seed_account(atom, "A")
        await _seed_account(atom, "B")
        await atom._on_halt_request(dict(payload, origin="901", reason="OWNER_COMMAND",
                                         operator="owner", command_id=7))
        for account in ("A", "B"):
            book = atom.book(account)
            assert book["kill"] is True and book["reason"] == "OWNER_COMMAND", (payload, book)
            halts = _events(bus, HALT, account)
            assert halts and halts[-1]["reason"] == "OWNER_COMMAND", (payload, halts)
            assert halts[-1]["reasons"] == ["OWNER_COMMAND"], halts[-1]
        assert atom._identity_rejections == 0, "الإيقاف الشامل ما زال يُرمى رفضَ هويّة"

        # حسابٌ يظهر بعد الإيقاف يولد موقوفًا ويُعلَن لتابعيه، ويُرفض أمره.
        await _seed_account(atom, "C")
        assert atom.book("C")["kill"] is True, atom.book("C")
        assert _events(bus, HALT, "C"), "الحساب الجديد لم يُعلَن موقوفًا للتابعين"
        verdict = await _validate(atom, bus, "C")
        assert verdict["approved"] is False and verdict["reason"] == "KILL_SWITCH", verdict

        # اليوم الجديد والإفراج الآليّ لا يمسّان الإيقاف الشامل.
        await atom._on_day({"pulse_id": "SYS_MARKET_DAY|9", "bucket_start": 9})
        await atom._on_reset({"account_id": "A", "auto_rearm": True,
                              "reason": "OWNER_COMMAND", "origin": "508"})
        assert atom.book("A")["kill"] is True, "إفراجٌ آليّ أو يومٌ جديد فكّ الإيقاف الشامل"


async def test_fix_1b_system_halt_survives_restart_until_owner_release(tmp_path):
    """العلم الشامل دائم: يعبر الإقلاع من المخزن، ولا يفكّه إلّا زرّ المالك بلا حساب."""
    db = tmp_path / "t1b.db"
    atom, bus = await _new(db)
    await _seed_account(atom, "A")
    await atom._on_halt_request({"origin": "901", "reason": "OWNER_COMMAND"})

    restarted, bus2 = await _new(db)
    assert restarted._global_reasons == {"OWNER_COMMAND"}, restarted._global_reasons
    assert restarted.book("A")["kill"] is True, restarted.book("A")
    await _seed_account(restarted, "D")
    assert restarted.book("D")["kill"] is True, "حسابٌ جديد بعد الإقلاع لم يرث الإيقاف الشامل"

    # فكّ المالك على حسابٍ بعينه لا يرفع الشامل (يفشل مغلقًا).
    await restarted._on_reset({"account_id": "D", "origin": "901", "reason": "OWNER_COMMAND"})
    assert restarted.book("D")["kill"] is True, restarted.book("D")

    # زرّ المالك كما ترسله اللوحة (`{}` عبر 901): يفكّ الشامل وكلّ دفتر.
    await restarted._on_reset({"origin": "901", "reason": "OWNER_COMMAND", "command_id": 8})
    assert not restarted._global_reasons
    for account in ("A", "D"):
        assert restarted.book(account)["kill"] is False, restarted.book(account)
        assert _events(bus2, RESET, account), "الفكّ لم يُعلَن للتابعين"
    await _seed_account(restarted, "E")
    assert restarted.book("E")["kill"] is False, restarted.book("E")

    again, _ = await _new(db)
    assert not again._global_reasons and again.book("A")["kill"] is False, again.book("A")


async def test_fix_2_exposure_release_keeps_daily_loss_halt(tmp_path):
    """MAX_EXPOSURE ثمّ خسارة يوم فوق الحدّ ثمّ إفراج 508 الآليّ ⟸ يبقى موقوفًا."""
    atom, bus = await _new(tmp_path / "t2.db")
    await _seed_account(atom, "A")
    await atom._on_halt_request({"account_id": "A", "reason": "MAX_EXPOSURE", "origin": "508"})
    assert atom.book("A")["reason"] == "MAX_EXPOSURE"

    await atom._on_loss({"event_id": "loss:day", "account_id": "A", "loss_pct": 6.0,
                         "completeness": "COMPLETE", "is_loss": True})
    book = atom.book("A")
    assert book["reasons"] == ["RISK_DAILY_LIMIT", "MAX_EXPOSURE"], book
    assert book["reason"] == "RISK_DAILY_LIMIT", "السبب الأشدّ لا يُعلَن أوّلًا"
    assert _events(bus, HALT, "A")[-1]["reason"] == "RISK_DAILY_LIMIT", "الخرق الجديد لم يُعلَن"

    # خرق جلسة من 506 يُضاف كذلك (كان `_trip` يعود صامتًا والمفتاح مرفوع).
    await atom._on_halt_request({"account_id": "A", "reason": "SESSION_LOSS_LIMIT", "origin": "506"})
    assert "SESSION_LOSS_LIMIT" in atom.book("A")["reasons"], atom.book("A")

    resets_before = len(_events(bus, RESET, "A"))
    await atom._on_reset({"account_id": "A", "reason": "MAX_EXPOSURE", "origin": "508",
                          "auto_rearm": True})
    book = atom.book("A")
    assert book["kill"] is True, "إفراج التعرّض الآليّ أعاد التداول فوق حدّ خسارةٍ مخروق"
    assert "MAX_EXPOSURE" not in book["reasons"], book
    assert len(_events(bus, RESET, "A")) == resets_before, "أُعلن فكٌّ والمفتاح ما زال مرفوعًا"
    verdict = await _validate(atom, bus, "A")
    assert verdict["approved"] is False and verdict["reason"] == "KILL_SWITCH", verdict


async def test_fix_3_owner_reset_clears_every_reason(tmp_path):
    atom, bus = await _new(tmp_path / "t3.db")
    await _seed_account(atom, "A")
    await atom._on_halt_request({"account_id": "A", "reason": "MAX_EXPOSURE", "origin": "508"})
    await atom._on_loss({"event_id": "loss:x", "account_id": "A", "loss_pct": 6.0,
                         "completeness": "COMPLETE", "is_loss": True})
    await atom._on_reset({"origin": "901", "reason": "OWNER_COMMAND"})
    book = atom.book("A")
    assert book["kill"] is False and book["reasons"] == [] and book["reason"] == "", book
    assert book["daily_loss_pct"] == 0.0 and book["consecutive_losses"] == 0, book
    assert _events(bus, RESET, "A")[-1]["reason"] == "OWNER_RELEASE"


async def test_fix_4_day_roll_clears_only_the_daily_reason(tmp_path):
    """حكم ٠٩-١٨: الحدّ اليوميّ لا يعيش بعد يومه — وحده؛ المتتاليات وأمر المالك يبقيان."""
    atom, bus = await _new(tmp_path / "t4.db")
    await _seed_account(atom, "A")
    await atom._on_loss({"event_id": "loss:d", "account_id": "A", "loss_pct": 6.0,
                         "completeness": "COMPLETE", "is_loss": True})
    await atom._on_halt_request({"account_id": "A", "reason": "OWNER_COMMAND", "origin": "901"})
    for i in range(3):
        await atom._on_loss({"event_id": "loss:c%d" % i, "account_id": "A", "loss_pct": 0.0,
                             "completeness": "COMPLETE", "is_loss": True})
    assert set(atom.book("A")["reasons"]) == {"RISK_DAILY_LIMIT", "OWNER_COMMAND",
                                             "MAX_CONSECUTIVE_LOSSES"}, atom.book("A")
    await atom._on_day({"pulse_id": "SYS_MARKET_DAY|1", "bucket_start": 1})
    book = atom.book("A")
    assert book["kill"] is True and set(book["reasons"]) == {"OWNER_COMMAND",
                                                            "MAX_CONSECUTIVE_LOSSES"}, book

    lone, _ = await _new(tmp_path / "t4b.db")
    await _seed_account(lone, "A")
    await lone._on_loss({"event_id": "loss:d", "account_id": "A", "loss_pct": 6.0,
                         "completeness": "COMPLETE", "is_loss": False})
    await lone._on_day({"pulse_id": "SYS_MARKET_DAY|1", "bucket_start": 1})
    assert lone.book("A")["kill"] is False, "حكم ٠٩-١٨ انكسر: القفل اليوميّ وحده لم يسقط مع اليوم"


async def test_fix_5_snapshot_round_trip_carries_the_set(tmp_path):
    atom, bus = await _new(tmp_path / "t5.db")
    await _seed_account(atom, "A")
    await atom._on_halt_request({"account_id": "A", "reason": "MAX_EXPOSURE", "origin": "508"})
    await atom._on_loss({"event_id": "loss:s", "account_id": "A", "loss_pct": 6.0,
                         "completeness": "COMPLETE", "is_loss": True})
    await atom._on_halt_request({"scope": "SYSTEM", "reason": "OWNER_COMMAND", "origin": "901"})
    snap = json.loads(json.dumps(await atom.snapshot()))   # كما تخزّنه النواة
    restored = Atom()
    await restored.restore(snap)
    book = restored.book("A")
    assert book["kill"] is True and book["reasons"] == ["OWNER_COMMAND", "RISK_DAILY_LIMIT",
                                                        "MAX_EXPOSURE"], book
    assert restored._global_reasons == {"OWNER_COMMAND"}, restored._global_reasons
    assert restored.book("Z")["kill"] is True, "الإيقاف الشامل لم يعبر اللقطة"


async def test_fix_6_old_single_reason_snapshot_converts_fail_closed(tmp_path):
    base = {"broker": "BR", "daily_loss_pct": 0.0, "consecutive_losses": 0,
            "daily_trade_count": 0, "open_trade_count": 0,
            "account_status": "HEALTHY", "system_status": "HEALTHY", "equity": 1000.0}
    old = {"version": "5.9.3", "books": {
        "A": dict(base, kill=True, reason="MAX_EXPOSURE"),
        "B": dict(base, kill=True, reason=""),
        "C": dict(base, kill=False, reason=""),
        "D": dict(base, kill=False, reason="", reasons="garbled"),
        "E": dict(base, kill=False, reason="", reasons=5)}}
    restored = Atom()
    await restored.restore(old)
    assert restored.book("A")["reasons"] == ["MAX_EXPOSURE"] and restored.book("A")["kill"] is True
    assert restored.book("B")["reasons"] == ["RISK_HALT"] and restored.book("B")["kill"] is True
    assert restored.book("C")["reasons"] == [] and restored.book("C")["kill"] is False
    assert restored.book("D")["kill"] is True, "حالة تالفة فُتحت"
    assert restored.book("E")["kill"] is True and restored.book("E")["reasons"] == ["RISK_HALT"]
    assert not restored._global_reasons

    # والمحوَّل يعمل كأيّ مجموعة: إفراج 508 يفكّ دفترًا قديمًا ممسوكًا بالتعرّض وحده.
    live, bus = await _new(tmp_path / "t6.db")
    await live.restore(old)
    await live._on_reset({"account_id": "A", "reason": "MAX_EXPOSURE", "origin": "508",
                          "auto_rearm": True})
    assert live.book("A")["kill"] is False, live.book("A")
    await live._on_reset({"account_id": "B", "reason": "MAX_EXPOSURE", "origin": "508",
                          "auto_rearm": True})
    assert live.book("B")["kill"] is True, "إفراجٌ آليّ فكّ قفلًا مجهول السبب"
