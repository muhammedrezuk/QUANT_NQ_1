# -*- coding: utf-8 -*-
"""مزوّد الشارت: التِّكّة الأولى تسجّل الرمز فقط، والنبضة تنشر المغلق وحده من المخزن بترتيبه، أطرًا كاملة ضمن حصّة كلّ نبضة،
بعلامة الماضي، مرّةً واحدة لكلّ رمز — ولا يُعدّ الرمز «مُعطًى» إلّا بعد آخر إطار، والقراءة الفاشلة تُعاد.

٢٠٢٦-١٠-١٢ (ختم المالك «NQ»): كان النشر كلّه (3600 شمعة) داخل معالج التِّكّة، فتقطعه النواة عند مهلة الدورة (5 ث)
ويبقى الرمز «مُعطًى» بلا أطره الصغرى — سجلّ النواة في إقلاعات 20:47 و21:33 و22:03.
"""
import asyncio
import importlib.util
import pathlib
import sqlite3
import sys

ROOT = pathlib.Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
from core.contracts.atom import AtomContext  # noqa: E402

spec = importlib.util.spec_from_file_location("_t602", pathlib.Path(__file__).resolve().parents[1] / "atom.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

TICK = {"symbol": "ustec", "account_id": "A", "broker": "B", "bid": 1.0, "ask": 1.1,
        "timestamp": 1000 + 60 * 4 + 30}                   # وقت السوق من التِّكّة: منتصف الدقيقة الخامسة


class _Log:
    def __getattr__(self, _):
        return lambda *a, **k: None


def _store(path):
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE candles_history (symbol TEXT, period TEXT, period_seconds INTEGER, period_start INTEGER, "
                "open REAL, high REAL, low REAL, close REAL, tick_volume INTEGER)")
    for i in range(5):                                   # خمس دقائق؛ الأخيرة لم تكتمل بعد
        con.execute("INSERT INTO candles_history VALUES ('USTEC','M1',60,?,?,?,?,?,7)",
                    (1000 + 60 * i, 1.0 + i, 2.0 + i, 0.5 + i, 1.5 + i))
    con.execute("INSERT INTO candles_history VALUES ('USTEC','H1',3600,-3600,1,2,0,1,9)")
    con.commit()
    con.close()


async def _atom(db, out, pub=None, **cfg):
    async def collect(n, p):
        out.append((n, p))
    ctx = AtomContext(atom_id=602, config={"db_path": db, "symbols": ["USTEC"], "bars_per_frame": 3,
                                           "fetch_every_s": 0, **cfg}, logger=_Log(), publish=pub or collect,
                      subscribe=lambda n, h: None)
    atom = mod.Atom()
    await atom.initialize(ctx)
    await atom.start()
    return atom


def test_tick_registers_and_pulse_publishes_closed_history_once_in_order(tmp_path):
    db = str(tmp_path / "h.db")
    _store(db)

    async def run():
        out = []
        atom = await _atom(db, out)
        await atom._on_tick(TICK)
        await atom._on_tick(TICK)                          # التِّكّة الثانية لا تعيد الطلب
        await atom._on_tick({"symbol": "EURUSD", "timestamp": 1.0})   # رمزٌ خارج القائمة
        assert out == [] and list(atom._requested) == ["USTEC"]       # لا نشر داخل معالج التِّكّة
        for _ in range(3):
            await atom._on_pulse({"official_time": 5000.0})
        frames = [(p["timeframe"], p["period_start"]) for _, p in out]
        assert frames == [("1h", -3600.0), ("1m", 1060.0), ("1m", 1120.0), ("1m", 1180.0)]
        assert all(p["history"] is True and p["account_id"] == "A" and p["symbol"] == "USTEC" for _, p in out)
        assert all(n == "market_data.candle_closed" for n, _ in out)
        health = await atom.health_check()
        assert health.details["published"] == 4 and health.details["served"] == ["USTEC"]
        assert "USTEC:4" in health.message and "waiting=-" in health.message
        await atom._on_tick(TICK)                          # بعد الإعطاء لا طلب جديد
        assert atom._requested == {}
    asyncio.run(run())


def test_whole_frames_within_the_pulse_budget(tmp_path):
    db = str(tmp_path / "h.db")
    _store(db)

    async def run():
        out = []
        atom = await _atom(db, out, replay_bars_per_pulse=1)
        await atom._on_tick(TICK)
        await atom._on_pulse({"official_time": 5000.0})    # النبضة الأولى تقرأ المخزن ولا تنشر
        assert out == [] and "USTEC" in atom._sending
        await atom._on_pulse({"official_time": 5001.0})    # إطار الساعة كاملًا
        assert [p["timeframe"] for _, p in out] == ["1h"] and "USTEC" not in atom._served
        await atom._on_pulse({"official_time": 5002.0})    # إطار الدقيقة كاملًا رغم أنّ الحصّة 1: الإطار لا يُقسم
        assert [p["timeframe"] for _, p in out] == ["1h", "1m", "1m", "1m"] and "USTEC" in atom._served
    asyncio.run(run())


def test_failed_read_is_retried_up_to_max_attempts(tmp_path):
    async def run():
        out = []
        atom = await _atom(str(tmp_path / "missing" / "h.db"), out, max_attempts=2)
        for second in range(4):
            await atom._on_tick(TICK)
            await atom._on_pulse({"official_time": 5000.0 + second})
        health = await atom.health_check()
        assert health.details["errors"] == 2 and health.details["attempts"] == {"USTEC": 2}
        assert atom._requested == {} and out == [] and "errors=2" in health.message
    asyncio.run(run())


def test_a_cut_frame_is_republished_whole(tmp_path):
    db = str(tmp_path / "h.db")
    _store(db)

    async def run():
        out = []
        calls = {"n": 0}

        async def flaky(n, p):
            calls["n"] += 1
            if calls["n"] == 2:                            # النواة تقطع الدورة في منتصف إطار الدقيقة
                raise asyncio.CancelledError()
            out.append((n, p))
        atom = await _atom(db, out, pub=flaky)
        await atom._on_tick(TICK)
        await atom._on_pulse({"official_time": 5000.0})
        try:
            await atom._on_pulse({"official_time": 5001.0})
        except asyncio.CancelledError:
            pass
        assert atom._replaying is False and "USTEC" not in atom._served
        await atom._on_pulse({"official_time": 5002.0})
        assert [p["timeframe"] for _, p in out] == ["1h", "1m", "1m", "1m"] and "USTEC" in atom._served
    asyncio.run(run())


def test_replay_waits_for_the_first_fetch_or_its_cap(tmp_path):
    """١٠-١٢: كان الإرسال يسبق جلب الإقلاع فأخذ الإس آند بي ماضيًا من ١٠-٠٨. الآن ينتظر أوّل جلب أو سقف الانتظار."""
    db = str(tmp_path / "h.db")
    _store(db)

    async def run():
        out = []
        atom = await _atom(db, out, fetch_every_s=3600, replay_wait_s=10)

        async def slow(at):
            return True                                    # جلبٌ لم ينتهِ بعد
        atom.fetch_once = slow
        await atom._on_tick(TICK)
        for t in (5000.0, 5005.0):
            await atom._on_pulse({"official_time": t})
        assert out == [] and list(atom._requested) == ["USTEC"]
        atom._fetches = 1                                  # انتهى الجلب ⟸ يبدأ الإرسال فورًا
        await atom._on_pulse({"official_time": 5006.0})
        await atom._on_pulse({"official_time": 5007.0})
        assert len(out) == 4
        fresh = await _atom(db, [], fetch_every_s=3600, replay_wait_s=10)
        fresh.fetch_once = slow
        await fresh._on_tick(TICK)
        for t in (5000.0, 5009.0, 5010.0, 5011.0):        # جلبٌ عالق ⟸ يبدأ بعد السقف (10 ث) لا قبله
            await fresh._on_pulse({"official_time": t})
        assert fresh._published == 4
    asyncio.run(run())


def test_fetch_runs_on_pulse_not_before_its_time():
    async def run():
        ctx = AtomContext(atom_id=602, config={"fetch_every_s": 3600}, logger=_Log(), publish=None,
                          subscribe=lambda n, h: None)
        atom = mod.Atom()
        calls = []

        async def fake(at):
            calls.append(at)
            atom._fetching = False
            return True
        atom.fetch_once = fake
        await atom.initialize(ctx)
        await atom.start()
        for t in (5000.0, 5001.0, 8599.0, 8600.0):      # الجلب عند أوّل نبضة ثمّ بعد ساعةٍ من وقتها الرسميّ
            await atom._on_pulse({"official_time": t})
            await asyncio.sleep(0)
        assert calls == [5000.0, 8600.0]
    asyncio.run(run())
