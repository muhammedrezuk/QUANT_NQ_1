# ٢٠٢٦-١٠-٠٢ (ختم المالك «صلح كامل nq») — إثبات إصلاحَي كاتب الجسر 601 (ب):
#   ١) التجميد بعد ردّ الوسيط: كان كلُّ `RETCODE_100xx` (ومنها 10019 «لا مال» و10016
#      «وقف غير صالح») يجمّد كلّ دخولٍ على كلّ رمزٍ ولكلّ حساب 15 دقيقة. الآن:
#      «مجهول المصير» و«التداول معطّل» يجمّدان الحساب نفسه، و«السوق مغلق» و«وقف غير
#      صالح» يجمّدان رمزهما وحده، وما عداها (10019…) لا يجمّد شيئًا.
#   ٢) فحص «فتحٌ معلّق» ثمّ الكتابة كانا خطوتين بينهما `await`، فقراران متزامنان على
#      رمزين يمرّان معًا (حالة 2026-09-10). الآن العدّ والإدراج تحت قفلٍ واحد.
# كلّ اختبارٍ هنا يسقط على 4.5.0 وينجح على 4.6.0 (عدا الحرّاس المسمّاة «حارس»).
import asyncio
import os
import sqlite3
import sys
import tempfile
import time
from pathlib import Path as _Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, str(_Path(__file__).resolve().parents[4]))
sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))

os.environ.pop("NQ_BRIDGE_DB", None)  # قاعدة مؤقّتة صريحة — لا جسر حيّ

import importlib.util as _ilu  # noqa: E402

from core.contracts.atom import AtomContext  # noqa: E402

_spec = _ilu.spec_from_file_location(
    "_atom601_fix_2026_10_02b", _Path(__file__).resolve().parents[1] / "atom.py")
_mod = _ilu.module_from_spec(_spec)
sys.modules["_atom601_fix_2026_10_02b"] = _mod
_spec.loader.exec_module(_mod)

DEMO = "52992818"
OTHER = "11112222"


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

    def named(self, name):
        return [p for n, p in self.published if n == name]


async def _new(tmp, accounts=(DEMO,)):
    db = os.path.join(tmp, "nq_brain.db")
    bus = _Bus()
    atom = _mod.Atom()
    await atom.initialize(AtomContext(atom_id=601, config={
        "account_id": "CURRENT_ACCOUNT", "db_path": db, "heartbeat_interval_s": 60.0,
        "magic": 20260801, "blocked_account_ids": [], "cursor_db": db + ".cursor"},
        logger=_Log(), publish=bus.publish, subscribe=bus.subscribe))
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE IF NOT EXISTS account_v2(account_id TEXT PRIMARY KEY)")
    conn.execute("CREATE TABLE IF NOT EXISTS trade_events_v2(id INTEGER PRIMARY KEY,"
                 " request_id TEXT, ticket INTEGER, event_type TEXT)")
    for account in accounts:
        conn.execute("INSERT OR IGNORE INTO account_v2 VALUES (?)", (account,))
    conn.commit()
    conn.close()
    await atom.start()
    return atom, bus, db


def _seed_reject(db, result, symbol="USTEC", account=DEMO, age_s=60.0, request_id=None):
    """أمر فتحٍ ردّه الوسيط قبل `age_s` ثانية — كما يختمه الإكسبرت (`FAILED` + الرمز)."""
    stamp = time.time() - age_s
    conn = sqlite3.connect(db)
    conn.execute(
        "INSERT INTO commands (request_id, action, symbol, side, volume, magic, account_id,"
        " status, result, created_at, taken_at, done_at)"
        " VALUES (?, 'OPEN', ?, 'BUY', 1.0, 20260801, ?, 'FAILED', ?, ?, ?, ?)",
        (request_id or "seed-%s-%s" % (result, symbol), symbol, account, result,
         stamp, stamp, stamp))
    conn.commit()
    conn.close()


def _settle_done(db, request_id):
    conn = sqlite3.connect(db)
    conn.execute("UPDATE commands SET status='DONE', result='OK', done_at=? WHERE request_id=?",
                 (time.time(), request_id))
    conn.commit()
    conn.close()


def _decision(symbol, request_id, account=DEMO):
    return {"account_id": account, "magic": 20260801, "request_id": request_id,
            "symbol": symbol, "side": "BUY", "volume": 0.1, "reference_price": 100.0,
            "stop_loss": 99.0, "take_profit": 104.0}


def _written(db, request_id):
    conn = sqlite3.connect(db)
    try:
        return conn.execute("SELECT COUNT(*) FROM commands WHERE request_id=?",
                            (request_id,)).fetchone()[0] == 1
    finally:
        conn.close()


def _last_failure(bus):
    failed = bus.named(_mod.EVENT_WRITE_FAILED)
    return failed[-1]["reason"] if failed else ""


async def test_no_money_reject_freezes_nothing():
    """10019 «لا مال» ردٌّ قاطع لم يُنفَّذ — لا يجمّد رمزًا آخر ولا رمزه (كان: كلّ شيء 15 د)."""
    with tempfile.TemporaryDirectory() as tmp:
        atom, bus, db = await _new(tmp)
        _seed_reject(db, "RETCODE_10019", "USTEC")
        await atom._on_final_decision(_decision("XAUUSD", "r-x"))
        assert _written(db, "r-x"), _last_failure(bus)
        _settle_done(db, "r-x")   # نفّذه الإكسبرت — وإلّا يحجب ما بعده بصفته فتحًا معلّقًا (حارسٌ قائم)
        await atom._on_final_decision(_decision("USTEC", "r-u"))
        await atom.stop()
        assert _written(db, "r-u"), _last_failure(bus)


async def test_invalid_stops_freezes_its_symbol_only():
    with tempfile.TemporaryDirectory() as tmp:
        atom, bus, db = await _new(tmp)
        _seed_reject(db, "RETCODE_10016", "USTEC")
        await atom._on_final_decision(_decision("USTEC", "r-u"))
        assert not _written(db, "r-u")
        assert _last_failure(bus).startswith("OPEN_PENDING_AT_BROKER"), _last_failure(bus)
        await atom._on_final_decision(_decision("XAUUSD", "r-x"))
        await atom.stop()
        assert _written(db, "r-x"), _last_failure(bus)


async def test_market_closed_freezes_its_symbol_only():
    with tempfile.TemporaryDirectory() as tmp:
        atom, bus, db = await _new(tmp)
        _seed_reject(db, "RETCODE_10018", "US30")
        await atom._on_final_decision(_decision("US30", "r-1"))
        await atom._on_final_decision(_decision("BTCUSD", "r-2"))
        await atom.stop()
        assert not _written(db, "r-1") and _written(db, "r-2")


async def test_timeout_still_freezes_the_whole_account():
    """حارس: المهلة 10012 مجهولة المصير (نُفّذت أربعتها يوم 09-06) — تبقى تجمّد الحساب."""
    with tempfile.TemporaryDirectory() as tmp:
        atom, bus, db = await _new(tmp)
        _seed_reject(db, "RETCODE_10012", "USTEC")
        await atom._on_final_decision(_decision("XAUUSD", "r-x"))
        await atom.stop()
        assert not _written(db, "r-x")
        assert _last_failure(bus).startswith("OPEN_PENDING_AT_BROKER"), _last_failure(bus)


async def test_unknown_after_crash_freezes_the_whole_account():
    """الإكسبرت يختم ما التقطه قبل انهياره `FAILED/UNKNOWN_AFTER_CRASH` دون سؤال الوسيط —
    مصيرٌ مجهول كالمهلة (كان لا يُعدّ لأنّه ليس `RETCODE_100%`)."""
    with tempfile.TemporaryDirectory() as tmp:
        atom, bus, db = await _new(tmp)
        _seed_reject(db, "UNKNOWN_AFTER_CRASH", "BTCUSD")
        await atom._on_final_decision(_decision("XAUUSD", "r-x"))
        await atom.stop()
        assert not _written(db, "r-x"), "مصيرٌ مجهول لا يُفتح فوقه"


async def test_trading_disabled_freezes_the_whole_account():
    """حارس: «التداول الآليّ مطفأ في الطرفيّة» (10027) يبقى يجمّد الحساب كلّه."""
    with tempfile.TemporaryDirectory() as tmp:
        atom, bus, db = await _new(tmp)
        _seed_reject(db, "RETCODE_10027", "USTEC")
        await atom._on_final_decision(_decision("XAUUSD", "r-x"))
        await atom.stop()
        assert not _written(db, "r-x")


async def test_another_accounts_timeout_does_not_freeze_this_account():
    with tempfile.TemporaryDirectory() as tmp:
        atom, bus, db = await _new(tmp)
        _seed_reject(db, "RETCODE_10012", "USTEC", account=OTHER)
        await atom._on_final_decision(_decision("XAUUSD", "r-x"))
        await atom.stop()
        assert _written(db, "r-x"), _last_failure(bus)


async def test_settled_by_ticket_and_window_still_release():
    """حارس: حدثُ تنفيذٍ بتذكرة يحسم المهلة، والنافذة (900 ث) تنتهي كما كانت."""
    with tempfile.TemporaryDirectory() as tmp:
        atom, bus, db = await _new(tmp)
        _seed_reject(db, "RETCODE_10012", "USTEC", request_id="t-1")
        conn = sqlite3.connect(db)
        conn.execute("INSERT INTO trade_events_v2 (request_id, ticket, event_type) VALUES ('t-1', 77, 'OPENED')")
        conn.commit()
        conn.close()
        _seed_reject(db, "RETCODE_10012", "USTEC", age_s=_mod._TIMEOUT_SETTLE_S + 5, request_id="t-2")
        await atom._on_final_decision(_decision("XAUUSD", "r-x"))
        await atom.stop()
        assert _written(db, "r-x"), _last_failure(bus)


async def test_concurrent_opens_on_two_symbols_write_only_one():
    """قراران متزامنان على رمزين (المحرّك يحجز النطاق لا المعالج). يُبطَّأ العدّ في الجسر
    كما على وسيطٍ مزدحم، فيرى كلاهما «لا معلّق» قبل أن يكتب أيٌّ منهما — كان يُكتب الاثنان."""
    with tempfile.TemporaryDirectory() as tmp:
        atom, bus, db = await _new(tmp)
        real = atom._count_unsettled_opens

        def slow_count(*args, **kwargs):
            time.sleep(0.3)
            return real(*args, **kwargs)

        atom._count_unsettled_opens = slow_count
        await asyncio.gather(atom._on_final_decision(_decision("USTEC", "c-1")),
                             atom._on_final_decision(_decision("XAUUSD", "c-2")))
        await atom.stop()
        conn = sqlite3.connect(db)
        opens = conn.execute("SELECT request_id FROM commands WHERE action='OPEN'").fetchall()
        conn.close()
        assert len(opens) == 1, opens
        assert _last_failure(bus).startswith("OPEN_PENDING_AT_BROKER count=1"), _last_failure(bus)


async def test_lock_never_holds_exits_or_a_failed_open():
    """حارس: الخروج لا يمرّ بالقفل، والفتح المرفوض لا يُبقيه مقفولًا."""
    with tempfile.TemporaryDirectory() as tmp:
        atom, bus, db = await _new(tmp)
        _seed_reject(db, "RETCODE_10012", "USTEC")
        await atom._on_final_decision(_decision("XAUUSD", "r-x"))           # يُرفض
        assert not atom._open_lock.locked()
        exit_order = {**_decision("XAUUSD", "m-1"), "action": "MODIFY_SL", "ticket": 7,
                      "volume": None}
        await asyncio.wait_for(atom._on_final_decision(exit_order), timeout=5.0)
        await atom.stop()
        assert _written(db, "m-1")


def _run_all():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and asyncio.iscoroutinefunction(fn):
            asyncio.run(fn())
            print("OK", name)
    print("601 fix 2026-10-02b: كلّ الاختبارات خضراء")


if __name__ == "__main__":
    _run_all()
