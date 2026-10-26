# ٢٠٢٦-١٠-٠٢ (ختم المالك «صلح كامل nq») — تِكّةٌ متأخّرة من فترةٍ أقدم من الشمعة
# الجارية لم تُفتح قطّ: لا تُغلق الجارية ولا تُفتح بها شمعةٌ ماضية، وتُعدّ باسمها.
# السيناريو بعينه من إعادة إنتاج المدقّق: تِكّات 1 ثمّ 125 ثمّ 70 ثمّ 130 ثمّ 190.
# يسقط على الكود القديم (نُشرت 0 ثمّ 120 بتِكّة واحدة ثمّ 60 بعدها) وينجح على الجديد.
import importlib.util
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))
_spec = importlib.util.spec_from_file_location(
    "_t103_fix02b", Path(__file__).resolve().parents[1] / "atom.py")
m = importlib.util.module_from_spec(_spec)
sys.modules["_t103_fix02b"] = m
_spec.loader.exec_module(m)


class _Log:
    def __getattr__(self, _n):
        return lambda *a, **k: None


class _Bus:
    def __init__(self):
        self.e = []

    def subscribe(self, *_a):
        pass

    async def publish(self, n, p):
        self.e.append((n, p))


async def test_late_tick_of_unopened_past_period_is_dropped_and_named():
    bus = _Bus()
    atom = m.Atom()
    await atom.initialize(m.AtomContext(103, {"timeframes": ["60s"]}, _Log(),
                                        bus.publish, bus.subscribe))
    await atom.start()
    base = {"account_id": "A", "broker": "BR", "provider": "CT", "symbol": "XAUUSD"}
    for ts, bid in ((1, 100.0), (125, 101.0), (70, 50.0), (130, 102.0), (190, 103.0)):
        await atom._on_tick({**base, "bid": bid, "ask": bid + 0.5, "timestamp": ts})
    closed = [p for n, p in bus.e if n == m.EVENT_OUT]
    starts = [p["period_start"] for p in closed]
    assert starts == [0.0, 120.0], starts                    # لا شمعة 60 بعد 120
    candle_120 = closed[1]
    assert candle_120["tick_count"] == 2, candle_120         # 125 و130 معًا
    assert candle_120["close"] == 102.25 and candle_120["low"] == 101.25, candle_120
    assert atom.late_dropped == 1, atom.late_dropped
    assert atom.late_unopened_dropped == 1, atom.late_unopened_dropped
    health = await atom.health_check()
    assert health.details["late_unopened_dropped"] == 1, health.details
