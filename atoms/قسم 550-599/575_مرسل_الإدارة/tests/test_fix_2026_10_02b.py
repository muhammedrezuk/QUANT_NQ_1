# ٢٠٢٦-١٠-٠٢ (ختم المالك «صلح كامل nq») — إثبات حارس مسافة الوقف في 575.
#
# 601 يرفض وقفًا أبعد من 5٪ عن مرساته (`STOP_LOSS_TOO_FAR`) منذ حادثة 09-05 (وقف 39,677 على
# دخول 79,677)، لكنّ أوامر `MODIFY_SL` من 570/577/579 تمرّ عبر 575 الذي لم يفحص إلّا أنّ
# الوقف موجب. مقيس في الجسر الحيّ: 34 أمر `MODIFY_SL` أبعد من 5٪ عن دخول مركزه، كلّها بتكوين
# 09-05/09-06، ومنها 31 نُفّذ `DONE`. الآن الحارس نفسه هنا، بالثابت نفسه، و`CLOSE`/`CLOSE_PARTIAL`
# لا يُفحصان أبدًا.
# كلّ اختبارٍ هنا يسقط على 2.11.0 وينجح على 2.12.0 (عدا الحرّاس المسمّاة «حارس»).
import ast
import asyncio
import os
import sqlite3
import sys
import tempfile
from pathlib import Path as _Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, str(_Path(__file__).resolve().parents[4]))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.pop("NQ_BRIDGE_DB", None)  # قاعدة مؤقّتة صريحة — لا جسر حيّ

from core.contracts.atom import AtomContext  # noqa: E402
import importlib.util as _ilu  # noqa: E402

_spec = _ilu.spec_from_file_location(
    "_atom575_fix_b", _Path(__file__).resolve().parents[1] / "atom.py")
_mod = _ilu.module_from_spec(_spec)
sys.modules["_atom575_fix_b"] = _mod
_spec.loader.exec_module(_mod)

ACC = "52992818"


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


async def _new(tmp, entry, current, ticket=7, symbol="BTCUSD"):
    db = os.path.join(tmp, "nq_brain.db")
    bus = _Bus()
    atom = _mod.Atom()
    await atom.initialize(AtomContext(atom_id=575, config={
        "enabled": True, "db_path": db, "magic": 20260801},
        logger=_Log(), publish=bus.publish, subscribe=bus.subscribe))
    conn = sqlite3.connect(db)
    # شكل `positions_v2` كما يبنيه الإكسبرت (الأعمدة التي تُقرأ هنا).
    conn.execute("CREATE TABLE positions_v2(account_id TEXT, ticket INTEGER, symbol TEXT,"
                 " side TEXT, volume REAL, entry_price REAL, current_price REAL, magic INTEGER)")
    conn.execute("INSERT INTO positions_v2 VALUES (?,?,?,?,?,?,?,?)",
                 (ACC, ticket, symbol, "BUY", 0.5, entry, current, 20260801))
    conn.commit()
    conn.close()
    await atom.start()
    await atom._on_pulse({"official_time": 1000.0})
    return atom, bus, db


def _cmd(action, **over):
    body = {"account_id": ACC, "magic": 20260801, "action": action, "ticket": 7,
            "symbol": "BTCUSD", "side": "BUY"}
    body.update(over)
    return body


def _rows(db):
    conn = sqlite3.connect(db)
    try:
        return conn.execute("SELECT action, stop_loss, status FROM commands").fetchall()
    except sqlite3.Error:
        return []
    finally:
        conn.close()


async def test_incident_stop_far_from_entry_and_price_is_refused():
    """حادثة 09-05 بأرقامها: دخول 79,677.15 والسعر حوله، والوقف 39,677.15 (50٪)."""
    with tempfile.TemporaryDirectory() as tmp:
        atom, bus, db = await _new(tmp, entry=79677.15, current=79650.0)
        await atom._on_command(_cmd("MODIFY_SL", stop_loss=39677.15))
        assert _rows(db) == [], "وقفٌ بلا حماية لا يُكتب"
        reason = bus.named(_mod.EVENT_FAILED)[-1]["reason"]
        assert reason.startswith("STOP_LOSS_TOO_FAR"), reason


async def test_breakeven_far_from_price_but_at_entry_is_written():
    """حارس: نقل الوقف إلى الدخول بعد ربحٍ 6٪ — بعيدٌ عن السعر قريبٌ من الدخول ⟸ يُكتب."""
    with tempfile.TemporaryDirectory() as tmp:
        atom, bus, db = await _new(tmp, entry=80000.0, current=85000.0)
        await atom._on_command(_cmd("MODIFY_SL", stop_loss=80000.0))
        assert _rows(db) == [("MODIFY_SL", 80000.0, "PENDING")]


async def test_trailing_far_from_entry_but_near_price_is_written():
    """حارس: وقفٌ متتبّع بعد ربحٍ 10٪ — بعيدٌ عن الدخول قريبٌ من السعر ⟸ يُكتب."""
    with tempfile.TemporaryDirectory() as tmp:
        atom, bus, db = await _new(tmp, entry=80000.0, current=88000.0)
        await atom._on_command(_cmd("MODIFY_SL", stop_loss=87000.0))
        assert _rows(db) == [("MODIFY_SL", 87000.0, "PENDING")]


async def test_close_and_partial_are_never_checked():
    """حارس: الإغلاق لا يُحجب أبدًا، ولو حمل حقل وقفٍ عبثيًّا."""
    with tempfile.TemporaryDirectory() as tmp:
        atom, bus, db = await _new(tmp, entry=79677.15, current=79650.0)
        await atom._on_command(_cmd("CLOSE_PARTIAL", volume=0.2, stop_loss=1.0))
        await atom._on_command(_cmd("CLOSE", stop_loss=1.0))
        assert [r[0] for r in _rows(db)] == ["CLOSE_PARTIAL", "CLOSE"]


async def test_position_without_prices_is_refused_no_anchor():
    with tempfile.TemporaryDirectory() as tmp:
        atom, bus, db = await _new(tmp, entry=None, current=None)
        await atom._on_command(_cmd("MODIFY_SL", stop_loss=79000.0))
        assert _rows(db) == []
        assert bus.named(_mod.EVENT_FAILED)[-1]["reason"] == "STOP_LOSS_NO_ANCHOR"


async def test_same_constant_as_601():
    """الحدّ نفسه في البوّابتين التوأمين — يُقرأ من مصدر 601 لا يُنسخ رقمه في الاختبار."""
    source = (_Path(__file__).resolve().parents[3] / "قسم 600-649" / "601_كاتب_جسر_الدماغ"
              / "atom.py").read_text(encoding="utf-8")
    values = [node.value.value for node in ast.parse(source).body
              if isinstance(node, ast.Assign) and any(getattr(t, "id", "") == "MAX_SL_FRAC"
                                                      for t in node.targets)]
    assert values and _mod.MAX_SL_FRAC == values[0] == 0.05, values


def _run_all():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and asyncio.iscoroutinefunction(fn):
            asyncio.run(fn())
            print("OK", name)
    print("575 fix 2026-10-02b: كلّ الاختبارات خضراء")


if __name__ == "__main__":
    _run_all()
