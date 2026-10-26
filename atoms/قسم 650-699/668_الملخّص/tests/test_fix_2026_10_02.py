# ٢٠٢٦-١٠-٠٢ (ختم المالك «صلح كامل nq»): ٦٦٨ كان يشترك داخل `start`، فكلُّ إيقافٍ ثمّ
# بدءٍ يضاعف مستمعيه. الاختبار يعدّ المستمعين الفعليّين على ناقلٍ يحفظهم، عبر ثلاث جولات.
import importlib.util as _ilu
import sys
from pathlib import Path as _Path

_ROOT = _Path(__file__).resolve().parents[4]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


def _load(name, path):
    spec = _ilu.spec_from_file_location(name, path)
    mod = _ilu.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


M668 = _load("_atom668_fix_2026_10_02", _Path(__file__).resolve().parents[1] / "atom.py")


class _Log:
    def __getattr__(self, name):
        return lambda *a, **k: None


class Bus:
    def __init__(self):
        self.handlers = {}
        self.out = []

    def subscribe(self, name, handler):
        self.handlers.setdefault(name, []).append(handler)

    async def publish(self, name, payload):
        self.out.append((name, payload))
        for handler in list(self.handlers.get(name, [])):
            await handler(payload)


async def _new(m668=None):
    m668 = m668 or M668
    bus = Bus()
    atom = m668.Atom()
    await atom.initialize(m668.AtomContext(668, {}, _Log(), bus.publish, bus.subscribe))
    return atom, bus


async def test_restart_does_not_double_subscriptions(m668=None):
    m668 = m668 or M668
    atom, bus = await _new(m668)
    for _ in range(3):
        await atom.start()
        await atom.stop()
    await atom.start()
    for event in m668.EVENTS:
        assert len(bus.handlers.get(event, [])) == 1, (event, len(bus.handlers.get(event, [])))
    assert len(bus.handlers.get(m668.EVENT_PULSE, [])) == 1


async def test_parts_ignored_while_stopped_and_stored_while_running(m668=None):
    m668 = m668 or M668
    atom, bus = await _new(m668)
    await bus.publish(m668.EVENT_COMPONENTS, {"accounts": [{"account_id": "A"}]})
    assert atom._parts == {}, "قبل البدء لا يُخزَّن شيء"
    await atom.start()
    await bus.publish(m668.EVENT_COMPONENTS, {"accounts": [{"account_id": "A"}]})
    await bus.publish("SYS_SECOND", {"sequence": 1, "pulse_id": "SYS_SECOND|1"})
    overview = [p for n, p in bus.out if n == m668.EVENT_OUT]
    assert len(overview) == 1 and overview[0]["count_accounts"] == 1
    await atom.stop()
    await bus.publish(m668.EVENT_COMPONENTS, {"accounts": [{"account_id": "B"}]})
    assert atom._parts[m668.EVENT_COMPONENTS]["accounts"][0]["account_id"] == "A", "بعد الإيقاف لا يُخزَّن"
