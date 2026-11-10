# ٢٠٢٦-١٠-٠٢ (ختم المالك «صلح كامل nq») — إثبات إصلاحات كاتب الجسر 601:
#   ١) الإيقاف الطارئ يلغي أوامر الدخول المعلّقة وحدها؛ أوامر الحماية والخروج
#      (`MODIFY_SL` · `CLOSE_PARTIAL` · `CLOSE`) تبقى PENDING (كانت تُلغى كلّها).
#   ٢) نطاق SYSTEM يوقف كلّ الحسابات ولو حمل الحدث حسابًا.
#   ٣) فصل التجريبيّ عن الحقيقيّ: في وضع الحساب الحاليّ لا يُكتب دخولٌ لحسابٍ
#      خارج القائمة (52992818 وحده)، والخروج والحماية يمرّان لأيّ حساب.
# كلّ اختبار هنا سقط على الكود قبل الإصلاح (مقيس: proof_before.json في مجلّد الوكيل).
import os
import sqlite3
import sys
import tempfile
from pathlib import Path as _Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, str(_Path(__file__).resolve().parents[4]))
sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))

os.environ.pop("NQ_BRIDGE_DB", None)  # قاعدة مؤقّتة صريحة — لا جسر حيّ

import importlib.util as _ilu  # noqa: E402

from core.contracts.atom import AtomContext  # noqa: E402

_spec = _ilu.spec_from_file_location(
    "_atom601_fix_2026_10_02", _Path(__file__).resolve().parents[1] / "atom.py")
_mod = _ilu.module_from_spec(_spec)
sys.modules["_atom601_fix_2026_10_02"] = _mod
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


async def _new(tmp, accounts, account_cfg="CURRENT_ACCOUNT"):
    db = os.path.join(tmp, "nq_brain.db")
    bus = _Bus()
    atom = _mod.Atom()
    await atom.initialize(AtomContext(atom_id=601, config={
        "account_id": account_cfg, "db_path": db, "heartbeat_interval_s": 1.0,
        "magic": 20260801, "blocked_account_ids": [], "cursor_db": db + ".cursor"},
        logger=_Log(), publish=bus.publish, subscribe=bus.subscribe))
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE IF NOT EXISTS account_v2(account_id TEXT PRIMARY KEY)")
    for account in accounts:
        conn.execute("INSERT OR IGNORE INTO account_v2 VALUES (?)", (account,))
    conn.commit()
    conn.close()
    await atom.start()
    return atom, bus, db


def _rows(db):
    conn = sqlite3.connect(db)
    try:
        return [tuple(r) for r in conn.execute(
            "SELECT account_id, action, status FROM commands ORDER BY id")]
    finally:
        conn.close()


def _seed_pending(db, account):
    conn = sqlite3.connect(db)
    for action in ("OPEN", "MODIFY_SL", "CLOSE_PARTIAL", "CLOSE"):
        conn.execute(
            "INSERT INTO commands (request_id, action, symbol, side, volume, magic, account_id,"
            " status, created_at) VALUES (?,?,?,?,?,?,?, 'PENDING', 1.0)",
            ("seed-%s-%s" % (account, action), action, "XAUUSD", "BUY", 0.1, 20260801, account))
    conn.commit()
    conn.close()


def _decision(account, **over):
    base = {"account_id": account, "magic": 20260801, "request_id": "r-open",
            "symbol": "XAUUSD", "side": "BUY", "volume": 0.1, "reference_price": 100.0,
            "stop_loss": 99.0, "take_profit": 102.0}
    base.update(over)
    return base


async def test_halt_cancels_entries_only_never_protection():
    with tempfile.TemporaryDirectory() as tmp:
        atom, bus, db = await _new(tmp, [DEMO])
        _seed_pending(db, DEMO)
        await atom._on_emergency_halt({"scope": "SYSTEM", "reason": "OWNER_COMMAND"})
        await atom.stop()
        assert _rows(db) == [(DEMO, "OPEN", "CANCELLED"), (DEMO, "MODIFY_SL", "PENDING"),
                             (DEMO, "CLOSE_PARTIAL", "PENDING"), (DEMO, "CLOSE", "PENDING")]
        halted = bus.named(_mod.EVENT_HALTED)
        assert halted and halted[0]["cancelled_commands"] == 1


async def test_system_scope_with_account_halts_every_account():
    with tempfile.TemporaryDirectory() as tmp:
        atom, bus, db = await _new(tmp, [DEMO, OTHER])
        _seed_pending(db, DEMO)
        _seed_pending(db, OTHER)
        await atom._on_emergency_halt({"scope": "SYSTEM", "account_id": DEMO, "reason": "x"})
        await atom.stop()
        opens = [(a, s) for a, act, s in _rows(db) if act == "OPEN"]
        assert opens == [(DEMO, "CANCELLED"), (OTHER, "CANCELLED")], opens
        assert sorted(bus.named(_mod.EVENT_HALTED)[0]["account_ids"]) == sorted([DEMO, OTHER])


async def test_entry_refused_for_account_outside_allow_list():
    with tempfile.TemporaryDirectory() as tmp:
        atom, bus, db = await _new(tmp, [OTHER])
        await atom._on_final_decision(_decision(OTHER))
        await atom._on_final_decision(_decision(OTHER, action="PENDING_CREATE", request_id="r-pc"))
        await atom.stop()
        assert _rows(db) == [], "لا دخول لحسابٍ خارج القائمة"
        reasons = [p["reason"] for p in bus.named(_mod.EVENT_WRITE_FAILED)]
        assert len(reasons) == 2 and all(r.startswith("ACCOUNT_NOT_ALLOWED_FOR_ENTRY") for r in reasons)


async def test_exits_and_protection_pass_for_any_account():
    with tempfile.TemporaryDirectory() as tmp:
        atom, bus, db = await _new(tmp, [OTHER])
        await atom._on_final_decision(_decision(OTHER, action="MODIFY_SL", request_id="m1",
                                                ticket=7, volume=None))
        await atom._on_final_decision(_decision(OTHER, action="CLOSE", request_id="c1",
                                                ticket=7, volume=None, stop_loss=None))
        await atom._on_final_decision(_decision(OTHER, action="CLOSE_PARTIAL", request_id="p1",
                                                ticket=7, stop_loss=None))
        await atom.stop()
        assert _rows(db) == [(OTHER, "MODIFY_SL", "PENDING"), (OTHER, "CLOSE", "PENDING"),
                             (OTHER, "CLOSE_PARTIAL", "PENDING")]


async def test_demo_account_entry_still_written():
    with tempfile.TemporaryDirectory() as tmp:
        atom, bus, db = await _new(tmp, [DEMO])
        await atom._on_final_decision(_decision(DEMO))
        await atom.stop()
        assert _rows(db) == [(DEMO, "OPEN", "PENDING")]
        assert bus.named(_mod.EVENT_WRITTEN)


async def test_allow_list_lives_in_code_not_config():
    assert _mod.ALLOWED_OPEN_ACCOUNT_IDS == frozenset({DEMO})
