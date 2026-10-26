import asyncio
import os
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from pathlib import Path as _Path
sys.path.insert(0, str(_Path(__file__).resolve().parents[4]))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.contracts.atom import AtomContext, HealthState  # noqa: E402
import importlib.util as _ilu  # noqa: E402

_spec = _ilu.spec_from_file_location(
    "_atom161", _Path(__file__).resolve().parents[1] / "atom.py")
_mod = _ilu.module_from_spec(_spec)
sys.modules["_atom161"] = _mod
_spec.loader.exec_module(_mod)
Atom = _mod.Atom
EVENT_OUT = _mod.EVENT_OUT


class _NullLogger:
    def debug(self, *a): pass
    def info(self, *a): pass
    def warning(self, *a): pass
    def error(self, *a): pass
    def critical(self, *a): pass


class FakeEventBus:
    def __init__(self):
        self.published = []

    def subscribe(self, name, handler):
        pass

    async def publish(self, name, payload):
        self.published.append((name, payload))

    def make_context(self, config):
        return AtomContext(atom_id=161, config=config, logger=_NullLogger(),
                           publish=self.publish, subscribe=self.subscribe)


CFG = {"window": 3, "strong_pct": 0.66, "weak_pct": 0.33}

# 3 symbols over 6 periods: USTEC rises, EURUSD flat, BTCUSD falls
_SERIES = {
    "USTEC":  [100, 101, 102, 103, 104, 105],
    "EURUSD": [100, 100, 100, 100, 100, 100],
    "BTCUSD": [100,  99,  98,  97,  96,  95],
}


def _candle(symbol, close, period, tf="60s"):
    return {"symbol": symbol, "close": close, "timeframe": tf, "period_start": period}


async def _run():
    bus = FakeEventBus()
    atom = Atom()
    await atom.initialize(bus.make_context(dict(CFG)))
    await atom.start()
    for p in range(6):
        for sym, closes in _SERIES.items():
            await atom._on_candle(_candle(sym, closes[p], p + 1))
    return bus


def _last_ok(bus, symbol):
    xs = [p for n, p in bus.published
          if n == EVENT_OUT and p["symbol"] == symbol and p["status"] == "ok"]
    return xs[-1]


async def test_strong_leader():
    print("\n--- test_strong_leader ---")
    o = _last_ok(await _run(), "USTEC")  # highest return
    # ٢٠٢٦-١٠-٠٧ (عقد الحقائق، ختم المالك «NQ»): «strong» كلمة قوّةٍ نُزعت؛ الصدارة تُقرأ من الترتيب والمئين والعائد الخامّ.
    assert "signal" not in o, (o.get("signal"), o["metadata"])
    md = o["metadata"]
    assert md["rank"] == md["peers"] - 1 and md["peers"] == 3, md
    assert md["percentile"] >= CFG["strong_pct"], md["percentile"]
    assert md["window_return"] > 0, md
    print(f"OK — متصدّر: pct={md['percentile']} rank={md['rank']}/{md['peers']}")


async def test_weak_laggard():
    print("\n--- test_weak_laggard ---")
    o = _last_ok(await _run(), "BTCUSD")  # lowest return
    # ٢٠٢٦-١٠-٠٧ (عقد الحقائق، ختم المالك «NQ»): «weak» كلمة قوّةٍ نُزعت؛ التأخّر يُقرأ من الترتيب والمئين والعائد الخامّ.
    assert "signal" not in o, (o.get("signal"), o["metadata"])
    md = o["metadata"]
    assert md["rank"] == 0 and md["peers"] == 3, md
    assert md["percentile"] <= CFG["weak_pct"], md["percentile"]
    assert md["window_return"] < 0, md
    print(f"OK — متأخّر: pct={md['percentile']} rank={md['rank']}/{md['peers']}")


async def test_neutral_middle():
    print("\n--- test_neutral_middle ---")
    o = _last_ok(await _run(), "EURUSD")  # middle return
    # ٢٠٢٦-١٠-٠٧ (عقد الحقائق، ختم المالك «NQ»): «neutral» كلمة جهةٍ نُزعت؛ الوسط يُقرأ من الترتيب والمئين الخامّين بين العتبتين.
    assert "signal" not in o, (o.get("signal"), o["metadata"])
    md = o["metadata"]
    assert md["rank"] == 1 and md["peers"] == 3, md
    assert CFG["weak_pct"] < md["percentile"] < CFG["strong_pct"], md["percentile"]
    print(f"OK — وسط: pct={md['percentile']} rank={md['rank']}/{md['peers']}")


async def test_insufficient_peers():
    print("\n--- test_insufficient_peers ---")
    bus = FakeEventBus()
    atom = Atom()
    await atom.initialize(bus.make_context(dict(CFG)))
    await atom.start()
    for p in range(6):  # only one symbol -> can't rank
        await atom._on_candle(_candle("USTEC", 100 + p, p + 1))
    xs = [p for n, p in bus.published if n == EVENT_OUT]
    assert xs and all(r["status"] == "insufficient_data" for r in xs)
    print("OK — رمز واحد → insufficient (لا ترتيب)")


async def test_contract_shape():
    print("\n--- test_contract_shape ---")
    o = _last_ok(await _run(), "USTEC")
    # ٢٠٢٦-١٠-٠٧ (عقد الحقائق، ختم المالك «NQ»): الحقول المطلوبة صارت ختم الحقيقة، وحقول الحكم ممنوعة.
    # ٢٠٢٦-١٠-٠٧ (عقد الحقائق، ختم المالك «NQ»): «signal» خرج من المطلوب إلى الممنوع — قيمته كلمة قوّةٍ تُنزع.
    for f in ("symbol", "id", "cycle_id", "status", "warnings", "metadata",
              "as_of", "computed_on", "section_id", "atom_id", "contract"):
        assert f in o, f"حقل ناقص بالعقد: {f}"
    for judged in ("signal", "score", "confidence", "quality"):
        assert judged not in o, f"حقل حكمٍ ظهر: {judged}"
    for f in ("method", "window_return", "rank", "peers", "percentile"):
        assert f in o["metadata"], f"metadata ناقص: {f}"
    assert o["id"] == "relative_strength"
    assert o["contract"] == "facts.v1"
    assert o["section_id"] == "150" and o["atom_id"] == "161"
    print("OK — عقد الحقائق كامل")


async def test_health_states():
    print("\n--- test_health_states ---")
    bus = FakeEventBus()
    atom = Atom()
    await atom.initialize(bus.make_context(dict(CFG)))
    assert (await atom.health_check()).state == HealthState.UNHEALTHY
    await atom.start()
    assert (await atom.health_check()).state == HealthState.DEGRADED
    await atom._on_candle(_candle("USTEC", 100, 1))
    assert (await atom.health_check()).state == HealthState.HEALTHY
    print("OK — الصحة: UNHEALTHY→DEGRADED→HEALTHY")


async def test_state_survives_restart():
    print("\n--- test_state_survives_restart ---")
    bus = FakeEventBus()
    atom = Atom()
    await atom.initialize(bus.make_context(dict(CFG)))
    await atom.start()
    for p in range(6):
        for sym, closes in _SERIES.items():
            await atom._on_candle(_candle(sym, closes[p], p + 1))
    key = ("USTEC", "60s")
    before = dict(atom._state[key])
    saved = await atom.snapshot()
    assert "live_analysis" in saved, "الغلاف الحيّ لازم يبقى محفوظًا"
    assert "atom" in saved, "تاريخ الإغلاقات لازم يُحفظ بجانبه — لا يُدهَس"

    revived = Atom()
    bus2 = FakeEventBus()
    await revived.initialize(bus2.make_context(dict(CFG)))
    await revived.restore(saved)
    await revived.start()
    after = revived._state[key]
    assert list(after["closes"]) == list(before["closes"])
    assert after["ret"] == before["ret"]
    assert revived._candles_seen == atom._candles_seen

    for sym, closes in _SERIES.items():
        await revived._on_candle(_candle(sym, closes[-1] + 1, 7))
    fresh = [p for n, p in bus2.published
             if n == EVENT_OUT and p["symbol"] == "USTEC"]
    assert fresh and fresh[-1]["status"] == "ok", fresh[-1]["status"]
    print(f"OK — تاريخ الإغلاقات نجا الإقلاع: "
          f"window_return={fresh[-1]['metadata']['window_return']} بلا إحماء جديد")


async def main():
    tests = [test_strong_leader, test_weak_laggard, test_neutral_middle,
             test_insufficient_peers, test_contract_shape, test_health_states,
             test_state_survives_restart]
    failed = []
    for t in tests:
        try:
            await t()
        except AssertionError as e:
            failed.append((t.__name__, str(e)))
            print(f"FAILED: {t.__name__}: {e}")
        except Exception as e:
            failed.append((t.__name__, repr(e)))
            print(f"ERROR: {t.__name__}: {e!r}")
    print("\n" + "=" * 60)
    if failed:
        print(f"فشل {len(failed)} من أصل {len(tests)}")
        sys.exit(1)
    print(f"نجح كل الاختبارات ({len(tests)}/{len(tests)})")


if __name__ == "__main__":
    asyncio.run(main())
