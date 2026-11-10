# ٢٠٢٦-١٠-٠٢ (ختم المالك «صلح كامل nq»): ٦١٨ كان يصرّف تِكّات ميتاتريدر مرّةً في الثانية.
#
# حلقة `_run` كانت تمرّر `self._official_time or time.time()` إلى `_pump`، و`_official_time`
# يتحرّك مع `SYS_SECOND` وحده — فالفارق صفرٌ طوال الثانية و`_pump` يخرج قبل القراءة. الاختبار
# يشغّل الحلقة الحقيقيّة على جسرٍ مؤقّت، ونبضةُ ثانيةٍ حيّة تختم `official_time` كالنواة، وكاتبٌ
# يُدرج 38 تِكّة على ~0.4ث: الصحيح دفعاتٌ صغيرةٌ كثيرة، والمعطوب دفعةٌ أو اثنتان.
import asyncio
import importlib.util as _ilu
import math
import sqlite3
import sys
import time
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


M618 = _load("_atom618_fix_2026_10_02", _Path(__file__).resolve().parents[1] / "atom.py")

TICKS = 38
SPAN_S = 0.4
LAST = {}


class _Log:
    def __getattr__(self, name):
        return lambda *a, **k: None


class _Bus:
    def __init__(self):
        self.ticks = []

    def subscribe(self, name, handler):
        pass

    async def publish(self, name, payload):
        if name == "feed.mt5.tick":
            self.ticks.append(payload)


def _bridge(db):
    conn = sqlite3.connect(str(db))
    # الجسر الحيّ `wal` — وبه لا يكلّف الحذفُ بعد القراءة مزامنةَ قرصٍ كلّ دورة.
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("CREATE TABLE ticks_v2 (id INTEGER PRIMARY KEY AUTOINCREMENT, account_id TEXT,"
                 " symbol TEXT, bid REAL, ask REAL, last REAL, volume REAL, tick_ms REAL)")
    conn.execute("CREATE TABLE symbol_specs_v2 (account_id TEXT, symbol TEXT, contract_size REAL,"
                 " tick_value REAL, tick_size REAL)")
    conn.commit()
    conn.close()


def _writer(db):
    # كاتبٌ واحد مقيم كالإكسبرت، بلا مزامنة قرص — كي يقيس الاختبارُ إيقاعَ ٦١٨ لا القرص.
    conn = sqlite3.connect(str(db))
    conn.execute("PRAGMA synchronous=OFF")
    return conn


def _insert(conn, i):
    conn.execute("INSERT INTO ticks_v2 (account_id, symbol, bid, ask, tick_ms) VALUES (?,?,?,?,?)",
                 ("52992818", "US500", 6000.0 + i * 0.25, 6000.5 + i * 0.25, time.time() * 1000.0))
    conn.commit()


async def measure(m618, tmp_path, monkeypatch):
    """يعيد أحجام الدفعات غير الفارغة التي قرأها ٦١٨ من الجسر."""
    db = tmp_path / "nq_brain_fix618.db"
    monkeypatch.setenv("NQ_BRIDGE_DB", str(db))      # الجسر المؤقّت وحده
    _bridge(db)
    bus = _Bus()
    atom = m618.Atom()
    cfg = {"db_path": str(db), "table_name": "ticks_v2", "spec_table": "symbol_specs_v2",
           "spec_refresh_s": 300, "poll_interval_s": 0.01, "batch_limit": 500,
           "delete_consumed": True, "max_age_s": 30}      # إعداد المانيفست الحيّ
    await atom.initialize(AtomContext(atom_id=618, config=cfg, logger=_Log(),
                                      publish=bus.publish, subscribe=bus.subscribe))
    batches = []
    fetch = atom._fetch

    def counted():
        rows = fetch()
        if rows:
            batches.append(len(rows))
        return rows

    atom._fetch = counted
    running = True

    async def second_pulse():
        # `SYS_SECOND` كما تنشره النواة: ختمٌ بالثانية يتحرّك مرّةً في الثانية.
        while running:
            await atom._on_pulse({"official_time": float(math.floor(time.time()))})
            await asyncio.sleep(0.02)

    pulse = asyncio.create_task(second_pulse())
    await asyncio.sleep(0.05)
    await atom.start()
    writer = _writer(db)
    try:
        started = time.monotonic()
        for i in range(TICKS):
            _insert(writer, i)
            # موعدٌ مطلق لكلّ تِكّة: 38 على 0.4ث مهما خشُنت مؤقّتة النظام.
            await asyncio.sleep(max(0.0, started + (i + 1) * SPAN_S / TICKS - time.monotonic()))
        LAST["span_s"] = time.monotonic() - started
        deadline = time.monotonic() + 3.0
        while len(bus.ticks) < TICKS and time.monotonic() < deadline:
            await asyncio.sleep(0.01)
    finally:
        writer.close()
        running = False
        await atom.stop()
        await pulse
        await asyncio.sleep(0.1)      # قراءةٌ في خيطٍ قد تكون في طريقها
    assert len(bus.ticks) == TICKS, (len(bus.ticks), batches)
    return batches


async def test_ticks_drained_every_poll_not_once_per_second(tmp_path, monkeypatch):
    batches = await measure(M618, tmp_path, monkeypatch)
    print("618 دفعات:", len(batches), batches)
    assert sum(batches) == TICKS
    assert len(batches) >= 10, "دفعاتٌ قليلة = تصريفٌ بإيقاع الثانية: %s" % batches
    assert max(batches) <= TICKS // 4, batches


async def test_official_time_still_stamps_specs(tmp_path, monkeypatch):
    # `_official_time` يبقى للختم: المواصفات تُختم بالثانية الرسميّة لا بالرتيبة.
    db = tmp_path / "nq_brain_fix618_specs.db"
    monkeypatch.setenv("NQ_BRIDGE_DB", str(db))
    _bridge(db)
    conn = sqlite3.connect(str(db))
    conn.execute("INSERT INTO symbol_specs_v2 VALUES ('52992818','US500',1.0,0.01,0.01)")
    conn.commit()
    conn.close()
    published = []

    class Bus(_Bus):
        async def publish(self, name, payload):
            published.append((name, payload))

    bus = Bus()
    atom = M618.Atom()
    cfg = {"db_path": str(db), "table_name": "ticks_v2", "spec_table": "symbol_specs_v2",
           "spec_refresh_s": 300, "poll_interval_s": 0.01, "batch_limit": 500,
           "delete_consumed": True, "max_age_s": 30}
    await atom.initialize(AtomContext(atom_id=618, config=cfg, logger=_Log(),
                                      publish=bus.publish, subscribe=bus.subscribe))
    await atom._on_pulse({"official_time": 1_786_791_577.0})
    await atom._refresh_specs()
    specs = [p for n, p in published if n == "market.symbol_specs"]
    assert specs and specs[0]["published_at"] == 1_786_791_577.0
