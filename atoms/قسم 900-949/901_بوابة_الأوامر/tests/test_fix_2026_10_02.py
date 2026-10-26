# ٢٠٢٦-١٠-٠٢ (ختم المالك «صلح كامل nq») — إثبات إصلاحات بوّابة الأوامر 901:
#   ١) الإيقاف لا ينتهي أبدًا (كان EXPIRED بلا نشر بعد 120 ث).
#   ٢) الإيقاف بلا حساب يُنشر بنطاق SYSTEM (إيقاف كلّ الحسابات).
#   ٣) إعدادات المحلّل: كلّ قيمة تُفحص لا الأولى وحدها (`break` كان خارج الشرط).
#   ٤) إلغاء تفعيل أصل يصل مستلِمًا حيًّا: أمر أصل PAUSE يُخرج الرمز من قائمة 468.
# كلّ اختبار هنا سقط على الكود قبل الإصلاح (مقيس: proof_before.json في مجلّد الوكيل).
import json
import os
import sqlite3
import sys
from pathlib import Path as _Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, str(_Path(__file__).resolve().parents[4]))

import importlib.util as _ilu  # noqa: E402

import pytest  # noqa: E402

from core.contracts.atom import AtomContext  # noqa: E402

_spec = _ilu.spec_from_file_location(
    "_atom901_fix_2026_10_02", _Path(__file__).resolve().parents[1] / "atom.py")
_mod = _ilu.module_from_spec(_spec)
sys.modules["_atom901_fix_2026_10_02"] = _mod
_spec.loader.exec_module(_mod)

_A468 = _Path(__file__).resolve().parents[3] / "قسم 450-499" / "468_التحكم_بالأصول" / "atom.py"


class _Log:
    def __init__(self):
        self.warnings = []

    def debug(self, *a): pass
    def info(self, *a): pass
    def error(self, *a): pass
    def critical(self, *a): pass

    def warning(self, *a):
        self.warnings.append(a)


class _Bus:
    def __init__(self):
        self.published = []
        self.log = _Log()

    def subscribe(self, name, handler):
        pass

    async def publish(self, name, payload):
        self.published.append((name, payload))

    def named(self, name):
        return [p for n, p in self.published if n == name]


@pytest.fixture
def tmp(tmp_path):
    return str(tmp_path)


def _insert(db, action, requested_at, payload=None, operator="dashboard"):
    conn = sqlite3.connect(db)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS commands (id INTEGER PRIMARY KEY AUTOINCREMENT, "
        "action TEXT NOT NULL, operator TEXT NOT NULL, requested_at REAL NOT NULL, "
        "status TEXT NOT NULL DEFAULT 'PENDING', executed_at REAL, payload_json TEXT)")
    conn.execute("INSERT INTO commands (action, operator, requested_at, payload_json) "
                 "VALUES (?, ?, ?, ?)",
                 (action, operator, requested_at, None if payload is None else json.dumps(payload)))
    conn.commit()
    conn.close()


def _statuses(db):
    conn = sqlite3.connect(db)
    try:
        return [r[0] for r in conn.execute("SELECT status FROM commands ORDER BY id")]
    finally:
        conn.close()


async def _pulse(db, now):
    bus = _Bus()
    atom = _mod.Atom()
    await atom.initialize(AtomContext(atom_id=901, config={
        "db_path": db, "max_age_s": 120, "batch_limit": 20}, logger=bus.log,
        publish=bus.publish, subscribe=bus.subscribe))
    await atom.start()
    await atom._on_pulse({"official_time": now})
    await atom.stop()
    return bus


async def test_late_halt_is_never_expired(tmp):
    db = os.path.join(tmp, "late.db")
    _insert(db, "halt", 100.0, {"scope": "SYSTEM"})   # عمره 900 ث > 120
    bus = await _pulse(db, 1000.0)
    halts = bus.named(_mod.EVENT_HALT_REQUEST)
    assert len(halts) == 1, "الإيقاف المتأخّر يُنفَّذ ولا يُرمى"
    assert halts[0]["scope"] == "SYSTEM" and halts[0]["command_id"] == 1
    assert _statuses(db) == ["DONE"]
    assert bus.log.warnings, "التأخّر يُسجَّل تحذيرًا لا يُكتم"


async def test_other_late_commands_still_expire(tmp):
    db = os.path.join(tmp, "late_other.db")
    _insert(db, "kill_switch_reset", 100.0)
    _insert(db, "execution_gate", 100.0, {"gate": "552", "enabled": True})
    bus = await _pulse(db, 1000.0)
    assert not bus.named(_mod.EVENT_RESET) and not bus.named(_mod.EVENT_GATE_COMMAND)
    assert _statuses(db) == ["EXPIRED", "EXPIRED"]


async def test_halt_without_account_carries_system_scope(tmp):
    db = os.path.join(tmp, "scope.db")
    _insert(db, "halt", 999.0)                                   # كاتب قديم بلا حمولة
    _insert(db, "halt", 999.0, {})                               # اللوحة قبل الإصلاح
    _insert(db, "halt", 999.0, {"account_id": "52992818"})      # إيقاف حسابٍ بعينه
    bus = await _pulse(db, 1000.0)
    halts = bus.named(_mod.EVENT_HALT_REQUEST)
    assert [h.get("scope") for h in halts] == ["SYSTEM", "SYSTEM", None], halts
    assert halts[2]["account_id"] == "52992818"


async def test_every_analysis_setting_value_is_validated(tmp):
    db = os.path.join(tmp, "analysis.db")
    first, second = sorted(_mod._ANALYSIS_TUNABLE)[:2]
    base = {"account_id": "52992818", "symbol": "XAUUSD",
            "analyzer_id": sorted(_mod._ANALYSIS_WEIGHT_KEYS)[0]}
    _insert(db, "analysis_setting", 999.0, {**base, "settings": {first: 50, second: "not-a-number"}})
    _insert(db, "analysis_setting", 999.0, {**base, "settings": {first: 50, second: 1e9}})
    _insert(db, "analysis_setting", 999.0, {**base, "settings": {first: 50, second: 60}})
    bus = await _pulse(db, 1000.0)
    assert _statuses(db) == ["REJECTED", "REJECTED", "DONE"]
    assert len(bus.named(_mod.EVENT_ANALYSIS_SETTINGS)) == 1


async def test_deactivate_reaches_asset_control_468(tmp):
    db = os.path.join(tmp, "deactivate.db")
    _insert(db, "deactivate_asset", 999.0, {"account_id": "52992818", "symbol": "XAUUSD"})
    bus = await _pulse(db, 1000.0)
    assert _statuses(db) == ["DONE"]
    assert len(bus.named(_mod.EVENT_DEACTIVATE)) == 1
    commands = bus.named(_mod.EVENT_ASSET_COMMAND)
    assert len(commands) == 1 and commands[0]["command"] == "PAUSE"
    assert commands[0]["account_id"] == "52992818" and commands[0]["symbol"] == "XAUUSD"
    # المستلِم الحقيقيّ: 468 يُخرج الرمز من قائمة ذلك الحساب.
    spec = _ilu.spec_from_file_location("_atom468_for_901_fix", _A468)
    m468 = _ilu.module_from_spec(spec)
    spec.loader.exec_module(m468)
    sink = _Bus()
    a468 = m468.Atom()
    await a468.initialize(AtomContext(atom_id=468, config={"allowed_symbols": ["BTCUSD"]},
                                      logger=sink.log, publish=sink.publish,
                                      subscribe=sink.subscribe))
    await a468.start()
    await a468._on_activate({"account_id": "52992818", "symbol": "XAUUSD", "budget": 100})
    assert "XAUUSD" in a468._allowed_by_account["52992818"]
    await a468._on_asset_command(commands[0])
    assert "XAUUSD" not in a468._allowed_by_account["52992818"]
    assert "BTCUSD" in a468._allowed_by_account["52992818"], "لا يمسّ رمزًا آخر"
