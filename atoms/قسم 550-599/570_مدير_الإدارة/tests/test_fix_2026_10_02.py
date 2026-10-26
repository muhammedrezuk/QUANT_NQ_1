# ٢٠٢٦-١٠-٠٢ (ختم المالك «صلح كامل nq»): إعادة أوامر الإدارة كانت ميّتة.
#
# ٥٧٠ يعيد الأمر الفاشل بالمعرّف نفسه، و٥٧٥ يردّ كلَّ معرّفٍ في جدول الجسر الدائم
# `DUPLICATE_REQUEST_ID` مهما كانت حالته — فلم تبلغ إعادةٌ واحدة الوسيط (US500 تذكرة
# 1977026413: الجزء الأوّل `STALE_2s` ثمّ لا إعادة، ثمّ الوقف كاملًا −94.35$).
#
# هذه الاختبارات تشغّل ٥٧٠ و**٥٧٥ الحقيقيّ** معًا على قاعدة جسرٍ مؤقّتة (لا الحيّة):
#   ١· الإعادة بعد `STALE_2s` تصل الجسر بمعرّفٍ جديد `<rid>-a2` وتُكتب `PENDING`.
#   ٢· حارس ٥٧٥ باقٍ: المحاولة نفسها مكرّرةً تُردّ `DUPLICATE_REQUEST_ID`.
#   ٣· لا إعادة والمحاولة في الجسر (`PENDING`/`TAKEN`)، ولا إعادة على فشلٍ متأخّر لمحاولةٍ سابقة.
#   ٤· لا إعادة لما لم يثبت أنّه لم يُنفَّذ (`RETCODE_10012` · `UNKNOWN_AFTER_CRASH` · التكرار).
#   ٥· تأكيد أيّ محاولةٍ يُتمّ الأمر.
import importlib.util as _ilu
import sqlite3
import sys
from pathlib import Path as _Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

_ROOT = _Path(__file__).resolve().parents[4]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from core.contracts.atom import AtomContext  # noqa: E402


def _load(name, path):
    spec = _ilu.spec_from_file_location(name, path)
    mod = _ilu.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


M570 = _load("_atom570_fix_2026_10_02", _Path(__file__).resolve().parents[1] / "atom.py")
M575 = _load("_atom575_fix_2026_10_02",
             _Path(__file__).resolve().parents[2] / "575_مرسل_الإدارة" / "atom.py")

ACCOUNT = "A"
TICKET = 1977026413
MAGIC = 20260801


class _Log:
    def __init__(self):
        self.errors = []

    def debug(self, *a): pass
    def info(self, *a): pass
    def warning(self, *a): pass
    def critical(self, *a): pass

    def error(self, *a):
        self.errors.append(a)


class Bus:
    """ناقلٌ يوصل النشرة إلى مشتركيها فعلًا — ٥٧٠ ⟵⟶ ٥٧٥ كما في الحيّ."""

    def __init__(self):
        self.published = []
        self.handlers = {}

    def subscribe(self, name, handler):
        self.handlers.setdefault(name, []).append(handler)

    async def publish(self, name, payload):
        self.published.append((name, dict(payload)))
        for handler in list(self.handlers.get(name, [])):
            await handler(dict(payload))

    def context(self, atom_id, config, log):
        return AtomContext(atom_id=atom_id, config=config, logger=log,
                           publish=self.publish, subscribe=self.subscribe)

    def of(self, name):
        return [p for n, p in self.published if n == name]


def _bridge(db):
    conn = sqlite3.connect(str(db))
    conn.execute("CREATE TABLE IF NOT EXISTS positions_v2(account_id TEXT, ticket INTEGER,"
                 " symbol TEXT, magic INTEGER)")
    conn.execute("INSERT INTO positions_v2 VALUES (?,?,?,?)", (ACCOUNT, TICKET, "US500", MAGIC))
    conn.commit()
    conn.close()


def _rows(db):
    conn = sqlite3.connect(str(db))
    try:
        return conn.execute("SELECT request_id, status, result FROM commands ORDER BY id").fetchall()
    finally:
        conn.close()


def _ea_finish(db, request_id, status, result):
    """الإكسبرت يختم الصفّ (كما في `QUANT_NQ.mq5`: `EXPIRED`+`STALE_2s` حارس العمر)."""
    conn = sqlite3.connect(str(db))
    conn.execute("UPDATE commands SET status=?, result=?, done_at=? WHERE request_id=?",
                 (status, result, 1001, request_id))
    conn.commit()
    conn.close()


async def _wire(tmp_path, monkeypatch, m570=None):
    m570 = m570 or M570
    db = tmp_path / "nq_brain_fix570.db"
    # الجسر المؤقّت وحده — المرسى يغلب المانيفست في ٥٧٥، فيُوجَّه هنا لا إلى الحيّ.
    monkeypatch.setenv("NQ_BRIDGE_DB", str(db))
    _bridge(db)
    bus, log = Bus(), _Log()
    a570, a575 = m570.Atom(), M575.Atom()
    await a570.initialize(bus.context(570, {"magic": MAGIC}, log))
    await a575.initialize(bus.context(575, {"enabled": True, "db_path": str(db), "magic": MAGIC}, log))
    await a570.start()
    await a575.start()
    await bus.publish("SYS_SECOND", {"official_time": 1000.0})
    return a570, a575, bus, db, log


def _partial_intent():
    return {"account_id": ACCOUNT, "ticket": TICKET, "symbol": "US500", "side": "BUY",
            "action": "CLOSE_PARTIAL", "volume": 2.8, "reason": "partial_take"}


async def _bridge_failed(bus, request_id, status, result):
    """ما ينشره ٦٠١ لصفٍّ خُتم فاشلًا (`_drain_results`)."""
    await bus.publish("execution.command.failed", {
        "request_id": request_id, "action": "CLOSE_PARTIAL", "symbol": "US500",
        "ticket": TICKET, "status": status, "result": result,
        "account_id": ACCOUNT, "reason": result or status})


async def test_stale_partial_is_retried_with_new_id_and_reaches_bridge(tmp_path, monkeypatch):
    a570, a575, bus, db, _ = await _wire(tmp_path, monkeypatch)
    await bus.publish("execution.manage.intent", _partial_intent())
    first = bus.of("execution.manage.command")[0]
    rid = first["request_id"]
    assert _rows(db) == [(rid, "PENDING", None)]
    _ea_finish(db, rid, "EXPIRED", "STALE_2s")
    await _bridge_failed(bus, rid, "EXPIRED", "STALE_2s")
    await bus.publish("SYS_SECOND", {"official_time": 1002.0})
    commands = bus.of("execution.manage.command")
    assert len(commands) == 2, commands
    retry = commands[1]
    assert retry["request_id"] == rid + "-a2", retry
    assert retry["parent_request_id"] == rid and retry["attempt"] == 2
    # الإعادة بلغت الجسر فعلًا — لا `DUPLICATE_REQUEST_ID`.
    assert _rows(db) == [(rid, "EXPIRED", "STALE_2s"), (rid + "-a2", "PENDING", None)], _rows(db)
    assert not [f for f in bus.of("execution.command.failed")
                if f.get("reason") == "DUPLICATE_REQUEST_ID"]
    assert [w["request_id"] for w in bus.of("execution.manage.written")] == [rid, rid + "-a2"]
    assert a570._pending[rid]["status"] == "QUEUED_TO_BRIDGE"
    health = await a570.health_check()
    assert "أُعيد=1" in health.message, health.message


async def test_575_duplicate_guard_still_refuses_true_duplicate(tmp_path, monkeypatch):
    a570, a575, bus, db, _ = await _wire(tmp_path, monkeypatch)
    await bus.publish("execution.manage.intent", _partial_intent())
    first = bus.of("execution.manage.command")[0]
    await a575._on_command(dict(first))       # المحاولة نفسها مرّةً ثانية
    assert len(_rows(db)) == 1
    dup = [f for f in bus.of("execution.command.failed") if f.get("reason") == "DUPLICATE_REQUEST_ID"]
    assert len(dup) == 1
    # والتكرار الحقيقيّ لا يُعاد عند ٥٧٠: المحاولة في الجسر فعلًا.
    for t in (1002.0, 1010.0, 1400.0):
        await bus.publish("SYS_SECOND", {"official_time": t})
    assert len(bus.of("execution.manage.command")) == 1
    assert len(_rows(db)) == 1


async def test_no_retry_while_attempt_is_in_bridge(tmp_path, monkeypatch):
    a570, a575, bus, db, _ = await _wire(tmp_path, monkeypatch)
    await bus.publish("execution.manage.intent", _partial_intent())
    rid = bus.of("execution.manage.command")[0]["request_id"]
    # `PENDING` ثمّ `TAKEN` في الجسر بلا نتيجة: لا إعادة مهما مرّ الزمن.
    for t in (1002.0, 1100.0):
        await bus.publish("SYS_SECOND", {"official_time": t})
    conn = sqlite3.connect(str(db))
    conn.execute("UPDATE commands SET status='TAKEN' WHERE request_id=?", (rid,))
    conn.commit()
    conn.close()
    for t in (1200.0, 1900.0):
        await bus.publish("SYS_SECOND", {"official_time": t})
    assert len(bus.of("execution.manage.command")) == 1
    # الأولى تُختم وتُعاد، فيصل فشلُ الأولى مرّةً ثانيةً متأخّرًا والثانية في الجسر:
    _ea_finish(db, rid, "EXPIRED", "STALE_2s")
    await _bridge_failed(bus, rid, "EXPIRED", "STALE_2s")
    await bus.publish("SYS_SECOND", {"official_time": 2000.0})
    assert len(bus.of("execution.manage.command")) == 2
    await _bridge_failed(bus, rid, "EXPIRED", "STALE_2s")
    for t in (2100.0, 2500.0):
        await bus.publish("SYS_SECOND", {"official_time": t})
    assert len(bus.of("execution.manage.command")) == 2, "فشلٌ متأخّر لمحاولةٍ سابقة لا يُطلق إعادة"
    assert [r[1] for r in _rows(db)] == ["EXPIRED", "PENDING"]


async def test_unconfirmed_failures_are_not_retried(tmp_path, monkeypatch):
    for result in ("RETCODE_10012", "UNKNOWN_AFTER_CRASH"):
        sub = tmp_path / result
        sub.mkdir()
        a570, a575, bus, db, log = await _wire(sub, monkeypatch)
        await bus.publish("execution.manage.intent", _partial_intent())
        rid = bus.of("execution.manage.command")[0]["request_id"]
        _ea_finish(db, rid, "FAILED", result)
        await _bridge_failed(bus, rid, "FAILED", result)
        for t in (1002.0, 1010.0, 1400.0):
            await bus.publish("SYS_SECOND", {"official_time": t})
        assert len(bus.of("execution.manage.command")) == 1, result
        assert len(_rows(db)) == 1
        assert a570._pending == {} and a570._close_abandoned == 1
        assert log.errors, "إسقاط إغلاقٍ معلَنٌ لا صامت"


async def test_ack_of_any_attempt_completes(tmp_path, monkeypatch):
    a570, a575, bus, db, _ = await _wire(tmp_path, monkeypatch)
    await bus.publish("execution.manage.intent", _partial_intent())
    rid = bus.of("execution.manage.command")[0]["request_id"]
    _ea_finish(db, rid, "EXPIRED", "STALE_2s")
    await _bridge_failed(bus, rid, "EXPIRED", "STALE_2s")
    await bus.publish("SYS_SECOND", {"official_time": 1002.0})
    await bus.publish("execution.command.ack", {"request_id": rid + "-a2", "account_id": ACCOUNT,
                                                "status": "DONE", "ticket": TICKET})
    assert a570._pending == {}
    assert a570._state[ACCOUNT + "|" + str(TICKET)]["partials"] == 1
    for t in (1100.0, 1500.0):
        await bus.publish("SYS_SECOND", {"official_time": t})
    assert len(bus.of("execution.manage.command")) == 2


async def test_unwritten_lock_failure_is_retried():
    # رفض ٥٧٥ قبل أن يكتب (قفلٌ عابر) لا صفّ له في الجسر — يُعاد.
    assert M570.may_retry("database is locked")
    assert M570.may_retry("POSITION_OWNERSHIP_MISMATCH")
    assert M570.may_retry("STALE_2s") and M570.may_retry("RETCODE_10029")
    assert not M570.may_retry("DUPLICATE_REQUEST_ID")
    assert not M570.may_retry("RETCODE_10012")
    assert not M570.may_retry("MANAGEMENT_GATE_DISABLED")
    assert not M570.may_retry("")
