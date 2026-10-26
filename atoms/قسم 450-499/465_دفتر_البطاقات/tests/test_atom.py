"""اختبارات ٤٦٥ — دفتر البطاقات (v1.30.1: أوّلُ ملفّ اختبارٍ للذرّة).

⛔ كلُّ مخزنٍ هنا في `tmp_path`. إعدادُ المانيفست يشير إلى المخزن الحيّ
(`var/store/trade_cards.db` تحت `forex_runtime`)، فلا يُبنى الدفتر بمساراته
أبدًا — ويُفحص ذلك صراحةً قبل كلّ شيء (`test_config_never_points_at_live_store`).
و`movement_floor` يُستبدل بلا شيء كي لا يُقرأ ملفّ قياسٍ حيّ من داخل اختبار.
"""
import asyncio
import importlib.util
import sqlite3
import sys
import time
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[4]
FOLDER = Path(__file__).resolve().parents[1]
for _path in (str(ROOT), str(ROOT / "clock"), str(FOLDER)):
    if _path not in sys.path:
        sys.path.insert(0, _path)

_spec = importlib.util.spec_from_file_location("_t465", FOLDER / "atom.py")
m = importlib.util.module_from_spec(_spec)
sys.modules["_t465"] = m
_spec.loader.exec_module(m)

from core.contracts.atom import HealthState  # noqa: E402
from shared.trade_card import CardStore  # noqa: E402

MANIFEST = yaml.safe_load((FOLDER / "manifest.yaml").read_text(encoding="utf-8"))


class _NullLogger:
    def __getattr__(self, name):
        return lambda *args, **kwargs: None


class FakeBus:
    def __init__(self):
        self.published = []
        self.subscribed = []

    def subscribe(self, name, handler):
        self.subscribed.append((name, handler))

    async def publish(self, name, payload=None):
        self.published.append((name, payload))

    def names(self, event):
        return [p for n, p in self.published if n == event]


def _config(tmp_path):
    """كلّ مفاتيح المانيفست — والمسار في `tmp_path` لا في المخزن الحيّ."""
    return {"store_path": str(tmp_path / "cards.db"), "dead_target_ttl_s": 4740.0,
            "max_open_age_s": 86400.0, "max_dispatch_age_s": 900.0, "min_rr": 3.0,
            "reversal_cooldown_s": 30.0, "flush_every_s": 5.0}


async def _started(tmp_path, monkeypatch):
    monkeypatch.setattr(m.card_ledger_birth, "movement_floor", lambda symbol: None)
    bus = FakeBus()
    atom = m.Atom()
    await atom.initialize(m.AtomContext(465, _config(tmp_path), _NullLogger(),
                                        bus.publish, bus.subscribe))
    # حارس المسار: الدفتر يكتب في `tmp_path` وحده.
    assert Path(atom._store.path) == tmp_path / "cards.db"
    await atom.start()
    return atom, bus


def _approval(**over):
    body = {"symbol": "NQ", "approved": True, "decision_side": "buy",
            "decision_id": "D1", "account_id": "A1", "broker": "BR"}
    body.update(over)
    return body


def _setup(**over):
    body = {"symbol": "NQ", "side": "buy", "entry_reference": 100.0,
            "invalidation_price": 99.0, "target_price": 104.0,
            "setup_owner": "406", "setup_id": "S1",
            "invalidation_reason": "تحت القاع", "target_reason": "القمّة السابقة"}
    body.update(over)
    return body


async def _drain(atom):
    """ينتظر عمل النبضة المملوك حتّى يكتمل — كما ينتظره `stop`."""
    tasks = list(atom._pulse_tasks)
    if tasks:
        await asyncio.wait(tasks, timeout=10)
    for _ in range(5):
        await asyncio.sleep(0)


def _count_setup(atom):
    """يعدّ كلّ دخولٍ إلى `_on_setup` — والنداء الذاتيّ يمرّ من الذرّة نفسها."""
    calls = []
    inner = atom._on_setup

    async def counted(payload):
        calls.append(payload.get("symbol"))
        # بلا الحارس يعود بلا قاع حتّى ينهار المفسّر — فيُقطع هنا بحكمٍ مقروء.
        assert len(calls) < 10, "عَودٌ بلا قاع في `_on_setup` — حارس v1.30.0 سقط"
        await inner(payload)

    atom._on_setup = counted
    return calls


def test_config_never_points_at_live_store(tmp_path):
    live = MANIFEST["config"]
    ours = _config(tmp_path)
    assert set(ours) == set(live), "كلّ مفتاحٍ في المانيفست له قيمةٌ في الاختبار"
    for key, value in live.items():
        if key.endswith(("_path", "_db", "_dir", "_file")):
            assert ours[key] != value and ours[key].startswith(str(tmp_path)), key


async def test_lifecycle_owned_pulse_tasks_are_cancelled_on_stop(tmp_path, monkeypatch):
    atom, bus = await _started(tmp_path, monkeypatch)
    # الاشتراك كما يعلنه المانيفست تمامًا — لا حدث زائد ولا ناقص.
    assert {name for name, _ in bus.subscribed} == set(MANIFEST["subscribes"])
    health = await atom.health_check()
    assert health.state == HealthState.HEALTHY, health.message

    # النبضة الثلاثون نبضةُ كنس: يُطلق مهمّةً مملوكة ولا ينتظرها (v1.28.0).
    atom._pulses = 29
    await atom._on_pulse({})
    assert atom._sweeping is True and atom._pulse_tasks
    assert bus.names(m.EVENT_CARD), "النبضة تعلن الدفتر"

    # عملٌ لا ينتهي من تلقائه — `stop` ينتظره بسقفٍ ثمّ يلغيه.
    hang = asyncio.Event()
    atom._spawn_watched(hang.wait(), "465-test-hang")
    held = list(atom._pulse_tasks)
    monkeypatch.setattr(m, "_STOP_WAIT_S", 0.5)
    await atom.stop()
    for _ in range(5):
        await asyncio.sleep(0)
    assert all(task.done() for task in held)
    assert any(task.cancelled() for task in held)
    assert not atom._pulse_tasks, "لا مهمّة تعيش بعد ذرّتها"
    assert atom._sweeping is False
    assert atom._running is False
    health = await atom.health_check()
    assert health.state == HealthState.UNHEALTHY
    assert health.message == m.REASON_NOT_STARTED
    await atom.shutdown()


async def test_happy_path_card_written_and_read_back(tmp_path, monkeypatch):
    atom, bus = await _started(tmp_path, monkeypatch)
    # القرار قبل مستوياته: لا رقم يُصرف بعد (حكم «الرقم للتحليل»).
    await atom._on_approved(_approval())
    assert atom._live == {} and "NQ" in atom._waiting
    await atom._on_setup(_setup())
    assert atom._opened == 1
    opened = bus.names(m.EVENT_OPENED)
    assert len(opened) == 1 and opened[0]["symbol"] == "NQ"
    card_no = opened[0]["card_no"]
    live = atom._live["NQ"]
    assert (live["entry"], live["stop"], live["target"]) == (100.0, 99.0, 104.0)

    # الكتابة نفسها من الكاتب نفسه تُطوى عدًّا ولا تُكتب مرّتين.
    folded = atom._folded
    atom._write("NQ", "466", "side", "buy")
    assert atom._folded == folded + 1

    await atom._on_passed({"symbol": "NQ", "decision_side": "buy",
                           "decision_id": "D1", "gate_request_id": "G1"})
    assert atom._live["NQ"]["state"] == m.STATE_DISPATCHED
    await atom._on_outcome({"symbol": "NQ", "event_type": "CLOSED",
                            "profit": 5.0, "result": "WIN"})
    assert atom._live == {} and atom._closed == 1
    assert bus.names(m.EVENT_CLOSED)[0]["card_no"] == card_no
    await atom._flush()
    assert atom._pending == [] and atom._pending_updates == []

    store = CardStore(str(tmp_path / "cards.db"))
    card = store.card(card_no)
    assert card["state"] == "CLOSED" and card["side"] == "buy"
    assert (card["entry"], card["stop"], card["target"]) == (100.0, 99.0, 104.0)
    assert card["rr"] == pytest.approx(4.0)
    assert card["decision_id"] == "D1" and card["gate_request_id"] == "G1"
    assert card["dispatched_at"] is not None
    assert card["outcome"] == "WIN" and card["profit"] == 5.0
    assert card["reason"].startswith("شراء على NQ")
    writes = {(w["author"], w["field"]): w["value"] for w in store.writes(card_no)}
    # حكمُ ٤٦٦ سبق البطاقة فحُفظ في المسوّدة وخُتم فيها عند الميلاد.
    assert writes[("466", "approved")] is True
    assert writes[("465", "verdict")] == "pass"
    assert writes[("467", "verdict")] == "pass"
    assert writes[("406", "stop")] == 99.0
    published = {name for name, _ in bus.published}
    assert published <= set(MANIFEST["publishes"])
    await atom.stop()


async def test_recursion_guard_failed_open_does_not_reenter(tmp_path, monkeypatch):
    atom, bus = await _started(tmp_path, monkeypatch)
    calls = _count_setup(atom)
    attempts = []

    def locked(*args, **kwargs):
        attempts.append(args[0])
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(atom._store, "open_card", locked)
    await atom._on_approved(_approval())
    # الفتح يفشل بقفل: محاولةٌ واحدة ولا عَود (كان ٩٥٠ `RecursionError`).
    await atom._on_setup(_setup())
    assert calls == ["NQ"] and attempts == ["NQ"]
    assert atom._live == {} and atom._lock_waits == 1
    assert atom._store_ready is True, "القفل العابر لا يُسقط المخزن"
    assert atom._waiting["NQ"]["setup"]["setup_id"] == "S1", "الإعداد بقي منتظرًا"

    # مسار الموافقة: الإعداد سبق، والفتح يفشل ثانيةً — ولا نداء لـ`_on_setup`.
    await atom._on_approved(_approval(decision_id="D2"))
    assert attempts == ["NQ", "NQ"] and calls == ["NQ"]

    # القفل زال: الموافقة التالية تُولد البطاقة، والعَود مرّةً واحدة فقط.
    monkeypatch.undo()
    monkeypatch.setattr(m.card_ledger_birth, "movement_floor", lambda symbol: None)
    await atom._on_approved(_approval(decision_id="D3"))
    assert "NQ" in atom._live and atom._opened == 1
    assert calls == ["NQ", "NQ"]
    assert atom._live["NQ"]["entry"] == 100.0

    # إعدادٌ لرمزٍ حيّ يُكتب على بطاقته ولا يعود إلى نفسه ولا يفتح ثانية.
    await atom._on_setup(_setup(target_price=105.0))
    assert calls == ["NQ", "NQ", "NQ"]
    assert atom._opened == 1 and atom._live["NQ"]["target"] == 105.0
    await atom.stop()


async def test_database_locked_is_counted_and_recover_restores_service(tmp_path, monkeypatch):
    atom, bus = await _started(tmp_path, monkeypatch)
    await atom._on_approved(_approval())
    await atom._on_setup(_setup())
    assert "NQ" in atom._live
    store = atom._store

    # ١) قفلٌ عابر أثناء الدفع: يُعدّ، والطابور يعود كما كان، والمخزن حيّ.
    real_update = store.update

    def locked_update(*args, **kwargs):
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(store, "update", locked_update)
    queued = len(atom._pending_updates)
    assert queued > 0
    await atom._flush_safely()
    assert atom._lock_waits == 1 and atom._store_ready is True
    assert len(atom._pending_updates) == queued
    assert "locked" in atom._last_error
    monkeypatch.setattr(store, "update", real_update)
    await atom._flush()
    assert atom._pending_updates == []

    # ٢) عطبٌ حقيقيّ في الكنس يُسقط المخزن — والصحّة تقول ذلك بعدّاداتها.
    real_expire = store.expire

    def broken_expire(*args, **kwargs):
        raise sqlite3.DatabaseError("database disk image is malformed")

    monkeypatch.setattr(store, "expire", broken_expire)
    await atom._sweep(time.time())
    assert atom._store_ready is False
    health = await atom.health_check()
    assert health.state == HealthState.UNHEALTHY
    assert health.message.startswith(m.REASON_NO_STORE)
    assert health.details["lock_waits"] == 1 and health.details["recovered"] == 0

    # ٣) الفحص الأوّل يلقى قفلًا: يبقى ساقطًا، والحارس يُرفع لمحاولةٍ تالية.
    real_ensure = store.ensure

    def locked_ensure():
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(store, "ensure", locked_ensure)
    atom._pulses = 29
    await atom._on_pulse({})
    assert atom._recovering is True and atom._pulse_tasks
    await _drain(atom)
    assert atom._recovering is False and atom._store_ready is False
    assert atom._recovered == 0

    # ٤) الفحص التالي (بعد ثلاثين نبضة) يجد المخزن: تعود الذرّة بلا إقلاع.
    monkeypatch.setattr(store, "ensure", real_ensure)
    monkeypatch.setattr(store, "expire", real_expire)
    for _ in range(30):
        await atom._on_pulse({})
    await _drain(atom)
    assert atom._store_ready is True and atom._recovered == 1
    assert "NQ" in atom._live, "الحيّ يُستعاد من المخزن بعد العودة"
    health = await atom.health_check()
    assert health.state == HealthState.HEALTHY, health.message
    assert health.details["recovered"] == 1 and health.details["lock_waits"] == 1
    await atom.stop()


#: ٢٠٢٦-١٠-٠٧ (ختم «NQ»): ناشرو هذه الأحداث أُرشفوا مع فكّ الأقسام عن القرار.
_ARCHIVED_FEEDS = (
    "decision.filter.conditions.state", "decision.filter.confidence.state",
    "decision.filter.position.state", "decision.filter.timing.state",
    "decision.filtered.state", "decision.resolved.state", "decision.scored.state",
    "market.liquidity.updated", "probability.confidence.state", "probability.merged.state",
    "strategy.aggregate.state", "strategy.breakout.state", "strategy.liquidity.state",
    "strategy.momentum.state", "strategy.pullback.state", "strategy.range.state",
    "strategy.reversal.state", "strategy.trend.state")


async def test_archived_feeds_are_not_heard_and_414_card_is_stamped(tmp_path, monkeypatch):
    """لا اشتراك في حدثٍ أُرشف ناشره، والبوّابتان الباقيتان (464 · 468) تُسمعان،
    وحكمُ بطاقة استمرار الاتّجاه (414) يُختم رأيًا على البطاقة لحظة ميلادها."""
    atom, bus = await _started(tmp_path, monkeypatch)
    heard = {name for name, _ in bus.subscribed}
    for dropped in _ARCHIVED_FEEDS:
        assert dropped not in heard, dropped
        assert dropped not in MANIFEST["subscribes"], dropped
    for kept in ("decision.filter.freshness.state", "decision.filter.asset.state",
                 "strategy.setup.proposed", "strategy.card.state"):
        assert kept in heard, kept
    handler = dict(bus.subscribed)["strategy.card.state"]
    await handler({"symbol": "NQ", "direction": 1, "status": "OPEN", "card_id": "414:NQ:1"})
    await atom._on_approved(_approval())
    await atom._on_setup(_setup())
    rows = [w for w in atom._pending if w[1] == "414" and w[2] == "رأي"]
    assert rows and rows[0][3].startswith("بطاقة استمرار الاتّجاه · شراء"), atom._pending[-5:]
    assert "OPEN" in rows[0][3]
    await atom.stop()


async def test_every_section_fact_is_stamped_on_the_trade_by_name(tmp_path, monkeypatch):
    """٢٠٢٦-١٠-٠٨ (أمر المالك «أوصل كلّ الأقسام بالاستراتيجيّات… والنماذج»): بعد عقد الحقائق لا رأي لقسم —
    فتُختم حقيقته (أرقامه الخام) على الصفقة لحظة ولادتها باسمه، ومعها الأقسام الأربعة التي كانت شهودًا."""
    atom, bus = await _started(tmp_path, monkeypatch)
    heard = dict(bus.subscribed)
    for event in ("structure.trend.state", "structure.phase.state", "stats.outlier.state", "stats.quality.state"):
        assert event in heard, event
    handlers = [h for n, h in bus.subscribed if n == "analysis.trend.state"]
    for handler in handlers:
        await handler({"symbol": "NQ", "contract": "facts.v1", "timeframe": "1h",
                       "metadata": {"method": "ema", "close": 30000.0, "ema_slow_value": 29500.123456,
                                    "candles": 200}})
    await atom._on_approved(_approval())
    await atom._on_setup(_setup())
    rows = [w for w in atom._pending if w[1] == "151" and w[2] == "حقيقة"]
    assert rows, atom._pending[-8:]
    assert rows[0][3].startswith("الاتجاه · ") and "close=30000.0" in rows[0][3] and "ema_slow_value=29500.1235" in rows[0][3]
    assert "method=" not in rows[0][3]
    assert not [w for w in atom._pending if w[1] == "151" and w[2] == "رأي"]   # لا رأي بلا حكم
    await atom.stop()


async def test_knowledge_facts_are_stamped_on_the_trade(tmp_path, monkeypatch):
    """٢٠٢٦-١٠-٠٨ (ختم المالك «NQ» — «قبل كلّ شي لازم يعرف النظام»): حقائق ذرّات المعرفة (117–120) تصل في `facts`
    وتُختم على الصفقة باسم ذرّتها كأيّ عامل."""
    atom, bus = await _started(tmp_path, monkeypatch)
    heard = dict(bus.subscribed)
    for event in ("knowledge.time.state", "knowledge.monetary.state", "knowledge.seasonal.state", "knowledge.news.state",
                  "knowledge.fed_pricing.state", "knowledge.companies.state"):
        assert event in heard, event
    await heard["knowledge.monetary.state"]({"symbol": "NQ", "id": "monetary_knowledge", "status": "ok",
                                             "facts": {"fed_rate_current": 4.0, "days_to_next_fomc": 41,
                                                       "upcoming": [{"name": "x"}]},
                                             "summary_ar": "الفائدة 4.00٪"})
    await atom._on_approved(_approval())
    await atom._on_setup(_setup())
    rows = [w for w in atom._pending if w[1] == "118" and w[2] == "حقيقة"]
    assert rows and rows[0][3].startswith("السياسة النقديّة · "), atom._pending[-8:]
    assert "fed_rate_current=4.0" in rows[0][3] and "days_to_next_fomc=41" in rows[0][3]
    assert "upcoming" not in rows[0][3]                                            # القوائم لا تُختم
    await atom.stop()


async def test_trade_from_card_414_is_attributed_to_it(tmp_path, monkeypatch):
    """٢٠٢٦-١٠-٠٧ (تدقيق الإغلاق): «كلّ صفقة تنحسب على استراتيجيّتها» — إعداد 414 يُبنى بدالّة العقد
    المشترك ويسبق الموافقة (ترتيب نشر 414)، فتُكتب مستوياته على البطاقة باسم 414 لا «406/410»."""
    from shared.trade_setup import OK, SETUP_TREND_PULLBACK, build_setup, validate_setup
    atom, bus = await _started(tmp_path, monkeypatch)
    setup = build_setup(owner="414", setup_type=SETUP_TREND_PULLBACK, side="buy",
                        entry_reference=30015.0, invalidation_price=29980.0,
                        invalidation_source="414:pullback_low+noise_2.0atr",
                        invalidation_reason="تحت قاع الارتداد على ٥ د",
                        target_price=30200.0, target_source="414:ladder_1h_4h",
                        target_reason="أقرب مستوى ساعة/٤ ساعات بنسبة 1:5.3",
                        account_id="A1", broker="BR", symbol="NQ", ttl_s=300.0)
    assert validate_setup(setup) == OK
    await atom._on_setup(setup)                  # 414 ينشر الإعداد أوّلًا
    await atom._on_approved(_approval())          # ثمّ الموافقة
    card = atom._live["NQ"]
    assert card["stop"] == 29980.0 and card["target"] == 30200.0
    assert any(w[1] == "414" and w[2] == "stop" for w in atom._pending), atom._pending[-8:]
    assert not any(w[1] == "406/410" for w in atom._pending)
    reason = m.card_ledger_writers.compose_reason(atom, "NQ", card)
    assert "بناها بطاقة استمرار الاتّجاه" in reason and "تحت قاع الارتداد" in reason, reason
    await atom.stop()
