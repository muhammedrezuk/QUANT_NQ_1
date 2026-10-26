# ٢٠٢٦-١٠-٠٢ (ختم المالك «صلح كامل nq») — النظام السوقيّ لكلّ رمز.
# كان قيمةً واحدة يكتبها آخر رمزٍ وصل، والحمولة بلا رمز ⇒ يطبّقها 166 و200 على
# الجميع. رمزان متعاكسان هنا: الذهب في اتّجاه واليورو في مدى — ولا يلوّث أحدهما
# الآخر. يسقط على الكود القديم وينجح على الجديد.
import sys
from pathlib import Path as _Path

sys.path.insert(0, str(_Path(__file__).resolve().parents[4]))

from core.contracts.atom import AtomContext  # noqa: E402
import importlib.util as _ilu  # noqa: E402

_spec = _ilu.spec_from_file_location(
    "_atom830_fix02b", _Path(__file__).resolve().parents[1] / "atom.py")
_mod = _ilu.module_from_spec(_spec)
sys.modules["_atom830_fix02b"] = _mod
_spec.loader.exec_module(_mod)
Atom = _mod.Atom


class _Log:
    def __getattr__(self, _n):
        return lambda *a, **k: None


class _Ctx:
    def __init__(self):
        self.handlers = {}
        self.out = []

    def subscribe(self, event, handler):
        self.handlers[event] = handler

    async def publish(self, event, payload):
        self.out.append(payload)


async def _new():
    ctx = _Ctx()
    atom = Atom()
    await atom.initialize(AtomContext(830, {"entry_threshold": 70, "exit_threshold": 45,
                                            "confirmation_window": 3, "min_duration_s": 0,
                                            "volatility_high": 75}, _Log(),
                                      ctx.publish, ctx.subscribe))
    await atom.start()
    return atom, ctx


async def test_regime_is_per_symbol_and_published_with_symbol():
    atom, ctx = await _new()
    trend = ctx.handlers["structure.trend.state"]
    for _ in range(3):
        await trend({"symbol": "XAUUSD", "direction": 90})
    for _ in range(3):
        await trend({"symbol": "EURUSD", "direction": 10})
    last = {}
    for payload in ctx.out:
        assert payload.get("symbol") in ("XAUUSD", "EURUSD"), payload
        last[payload["symbol"]] = payload
    # كان: اليورو يقلب النظام الواحد إلى RANGING فيصير الذهب «مدًى» أيضًا.
    assert last["XAUUSD"]["regime"] == "TRENDING", last["XAUUSD"]
    assert last["EURUSD"]["regime"] == "RANGING", last["EURUSD"]
    assert last["XAUUSD"]["vector"]["trend"] == 90, last["XAUUSD"]["vector"]
    assert last["EURUSD"]["vector"]["trend"] == 10, last["EURUSD"]["vector"]
    # `transitions` العدّاد الكلّيّ كما كان (840 يقرؤه)، وعدّاد الرمز بجانبه.
    assert last["EURUSD"]["transitions"] == 1 and last["EURUSD"]["symbol_transitions"] == 0
    health = await atom.health_check()
    assert health.details["regimes"] == {"EURUSD": "RANGING", "XAUUSD": "TRENDING"}, health.details


async def test_volatility_of_one_symbol_does_not_label_another():
    atom, ctx = await _new()
    await ctx.handlers["analysis.volatility.state"]({"symbol": "BTCUSD", "score": 95})
    for _ in range(3):
        await ctx.handlers["structure.trend.state"]({"symbol": "XAUUSD", "direction": 90})
    # تذبذب البتكوين العالي لا يجعل اتّجاه الذهب «عالي التذبذب».
    assert ctx.out[-1]["symbol"] == "XAUUSD" and ctx.out[-1]["regime"] == "TRENDING", ctx.out[-1]


async def test_symbolless_event_is_counted_not_generalised():
    atom, ctx = await _new()
    await ctx.handlers["structure.trend.state"]({"direction": 90})
    assert ctx.out == [], ctx.out
    assert atom._drop_reasons.get("SYMBOL_MISSING") == 1, atom._drop_reasons
