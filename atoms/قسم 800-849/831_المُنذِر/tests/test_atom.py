import asyncio
import inspect
import json
import os
import sys
import tempfile
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.contracts.atom import AtomContext, HealthState  # noqa: E402
import importlib.util as _ilu  # noqa: E402

_spec = _ilu.spec_from_file_location(
    "_atom831", Path(__file__).resolve().parents[1] / "atom.py")
_mod = _ilu.module_from_spec(_spec)
sys.modules["_atom831"] = _mod
_spec.loader.exec_module(_mod)
Atom = _mod.Atom
EVENT_ALERT = _mod.EVENT_ALERT
EVENT_STATE = _mod.EVENT_STATE
EVENT_RECOVERED = _mod.EVENT_RECOVERED
EVENT_SWEEP = _mod.EVENT_SWEEP
MONITORED = _mod._MONITORED

# نفس رموز الحارس في core/event_bus — تُكرَّر هنا عمدًا (لا اعتماد على نواة
# داخل اختبار ذرة) كي يبقى اختبار «أسماء النشر آمنة» مفعّلًا ولو تغيّرت النواة
# فتنبيهنا يُخزَّن ويُعاد (حالة) ولا يُحجز أبدًا (أمر).
_COMMAND_MARKERS = (
    "order", ".buy", ".sell", ".execute", ".cancel",
    "final_decision", "command", ".submit", ".send",
)


class _NullLogger:
    def debug(self, *a): pass
    def info(self, *a): pass
    def warning(self, *a): pass
    def error(self, *a): pass
    def critical(self, *a): pass


class FakeEventBus:
    def __init__(self):
        self.published = []
        self._handlers = {}

    def subscribe(self, name, handler):
        self._handlers.setdefault(name, []).append(handler)

    async def publish(self, name, payload):
        self.published.append((name, payload))
        for handler in self._handlers.get(name, []):
            result = handler(payload)
            if inspect.isawaitable(result):
                await result

    def make_context(self, config, atom_id=831):
        return AtomContext(atom_id=atom_id, config=config, logger=_NullLogger(),
                           publish=self.publish, subscribe=self.subscribe)


async def _make_atom(tmp_dir: str, **overrides):
    bus = FakeEventBus()
    atom = Atom()
    config = {
        "cooldown_seconds": 300,
        "expiry_seconds": 3600,
        "state_file": str(Path(tmp_dir) / "state" / "system_alerts.json"),
        "severity_overrides": {},
    }
    config.update(overrides)
    await atom.initialize(bus.make_context(config))
    await atom.start()
    return bus, atom


def _alerts_of(bus):
    return [p for n, p in bus.published if n == EVENT_ALERT]


def _states_of(bus):
    return [p for n, p in bus.published if n == EVENT_STATE]


def _read_state_file(tmp_dir: str):
    with open(Path(tmp_dir) / "state" / "system_alerts.json", encoding="utf-8") as fh:
        return json.load(fh)


async def test_subscription_contract():
    """تستمع إلى كل أحداث الإخفاق المدرَجة + نبضة الكنس، ولا شيء آخر."""
    print("\n--- test_subscription_contract ---")
    with tempfile.TemporaryDirectory() as tmp:
        bus, _atom = await _make_atom(tmp)
    # ٢٠٢٦-١٠-٠٢ (ختم المالك «صلح كامل nq»): وأحداث النجاح التي وحدها تمحو الإنذار.
    expected = set(MONITORED) | set(_mod._RECOVERY) | {EVENT_SWEEP}
    assert set(bus._handlers) == expected, "عقد الاشتراك في المانيفست نفسه"
    assert len(bus._handlers[EVENT_SWEEP]) == 1
    print(f"OK — {len(expected)} اشتراكًا كما في المانيفست")


async def test_critical_failure_publishes_alert_and_state():
    print("\n--- test_critical_failure_publishes_alert_and_state ---")
    with tempfile.TemporaryDirectory() as tmp:
        bus, atom = await _make_atom(tmp)
        await bus.publish("tools.backup.failed", {"error": "disk full"})
        await atom.flush_state()   # ٢٠٢٦-١٠-٠٩: الملفّ يُكتب في خيط — يُنتظر قبل قراءته
        alerts = _alerts_of(bus)
        assert len(alerts) == 1, "إخفاق واحد = تنبيه واحد"
        a = alerts[0]
        assert a["severity"] == "critical"
        assert a["source_event"] == "tools.backup.failed"
        assert a["source_atom"] == 800
        assert a["count"] == 1
        assert a["detail"] == "disk full"
        states = _states_of(bus)
        assert len(states) == 1 and states[0]["total"] == 1
        assert states[0]["alerts"]["tools.backup.failed"]["count"] == 1
        on_disk = _read_state_file(tmp)
        assert on_disk["total"] == 1 and "tools.backup.failed" in on_disk["alerts"]
    print("OK — system.alert + system.alert.state + ملف الحالة")


async def test_warning_default_severity():
    print("\n--- test_warning_default_severity ---")
    with tempfile.TemporaryDirectory() as tmp:
        bus, _atom = await _make_atom(tmp)
        await bus.publish("tools.storage.low", {"used_pct": 81.5})
        a = _alerts_of(bus)[0]
        assert a["severity"] == "warning", "الأحداث التحذيرية warning افتراضيًا"
        assert a["source_atom"] == 6
    print("OK — tools.storage.low = warning")


async def test_cooldown_suppresses_repeat():
    print("\n--- test_cooldown_suppresses_repeat ---")
    with tempfile.TemporaryDirectory() as tmp:
        bus, _atom = await _make_atom(tmp)
        await bus.publish("tools.backup.failed", {"error": "x"})
        await bus.publish("tools.backup.failed", {"error": "y"})
        alerts = _alerts_of(bus)
        assert len(alerts) == 1, "التكرار داخل التهدئة لا يرسّش"
        assert _states_of(bus)[-1]["alerts"]["tools.backup.failed"]["count"] == 2
        assert _states_of(bus)[-1]["alerts"]["tools.backup.failed"]["detail"] == "y"
    print("OK — تنبيه واحد، العدّاد 2")


async def test_zero_cooldown_emits_every_time():
    print("\n--- test_zero_cooldown_emits_every_time ---")
    with tempfile.TemporaryDirectory() as tmp:
        bus, _atom = await _make_atom(tmp, cooldown_seconds=0)
        await bus.publish("tools.backup.failed", {})
        await bus.publish("tools.backup.failed", {})
        assert len(_alerts_of(bus)) == 2, "تهدئة صفرية = بلا كبح"
    print("OK — cooldown=0 يرسل كل مرة")


async def test_severity_override_config():
    print("\n--- test_severity_override_config ---")
    with tempfile.TemporaryDirectory() as tmp:
        bus, _atom = await _make_atom(
            tmp, severity_overrides={"tools.storage.low": "critical"})
        await bus.publish("tools.storage.low", {})
        a = _alerts_of(bus)[0]
        assert a["severity"] == "critical", "المالك يرفع أي حدث إلى critical"
    print("OK — التعديل عبر config ينعكس")


async def test_sweep_ages_but_never_recovers():
    # ٢٠٢٦-١٠-٠٢ (ختم المالك «صلح كامل nq»): كان هذا الاختبار يثبّت المحو بعد ساعة
    # صمت — وهو العيب نفسه: فشلٌ يوميّ يظهر ساعةً ثمّ يُعلَن «مستردًّا» وهو قائم.
    # العقد الآن: الصمت يُشيّخ الإنذار ويُخفّض عرضه، والمحو بحدث النجاح وحده.
    print("\n--- test_sweep_ages_but_never_recovers ---")
    with tempfile.TemporaryDirectory() as tmp:
        bus, atom = await _make_atom(tmp)
        await bus.publish("tools.backup.failed", {})
        atom._active["tools.backup.failed"]["last_at"] -= 7200  # صمت > expiry
        await bus.publish(EVENT_SWEEP, {})
        assert [p for n, p in bus.published if n == EVENT_RECOVERED] == []
        state = _states_of(bus)[-1]
        assert state["total"] == 1
        alert = state["alerts"]["tools.backup.failed"]
        assert alert["aged"] is True and alert["display_severity"] == "warning"
        assert alert["severity"] == "critical"
        await atom.flush_state()
        assert _read_state_file(tmp)["total"] == 1
        await bus.publish("tools.backup.completed", {"path": "x"})
        rec = [p for n, p in bus.published if n == EVENT_RECOVERED]
        assert len(rec) == 1 and rec[0]["recovered"] == ["tools.backup.failed"]
        await atom.flush_state()
        assert _read_state_file(tmp)["total"] == 0
    print("OK — صمت طويل → شيخوخة بلا محو · ونجاح النسخ → استرداد")


async def test_sweep_keeps_fresh_alerts():
    print("\n--- test_sweep_keeps_fresh_alerts ---")
    with tempfile.TemporaryDirectory() as tmp:
        bus, _atom = await _make_atom(tmp)
        await bus.publish("tools.backup.failed", {})
        await bus.publish(EVENT_SWEEP, {})
        assert [p for n, p in bus.published if n == EVENT_RECOVERED] == []
        assert _states_of(bus)[-1]["total"] == 1, "إخفاق حيّ لا يُكنس"
    print("OK — الكنس لا يمسّ الإخفاق الحيّ")


async def test_stop_blocks_and_start_resumes():
    print("\n--- test_stop_blocks_and_start_resumes ---")
    with tempfile.TemporaryDirectory() as tmp:
        bus, atom = await _make_atom(tmp)
        await atom.stop()
        await bus.publish("tools.backup.failed", {})
        assert _alerts_of(bus) == [], "موقوفة = صامتة"
        await atom.start()
        await bus.publish("tools.backup.failed", {})
        assert len(_alerts_of(bus)) == 1, "البدء من جديد يعيد السمع"
    print("OK — stop قابل للعكس كما في العقد")


async def test_file_write_failure_degrades_but_keeps_alerting():
    print("\n--- test_file_write_failure_degrades_but_keeps_alerting ---")
    with tempfile.TemporaryDirectory() as tmp:
        blocker = Path(tmp) / "blocker"
        blocker.write_text("x", encoding="utf-8")
        bus, atom = await _make_atom(
            tmp, state_file=str(blocker / "sub" / "x.json"))
        await bus.publish("tools.backup.failed", {"error": "boom"})
        assert len(_alerts_of(bus)) == 1, "الفشل على القرص لا يسكّت التنبيه"
        await atom.flush_state()
        h = await atom.health_check()
        assert h.state == HealthState.DEGRADED, "الصحّة تعكس فشل الكتابة"
        # رجوع القرص: مسار سليم → healthy من جديد
        atom._state_file = str(Path(tmp) / "state" / "ok.json")
        await bus.publish("tools.backup.failed", {"error": "boom2"})
        await atom.flush_state()
        h2 = await atom.health_check()
        assert h2.state == HealthState.HEALTHY, "الكتابة رجعت = healthy"
    print("OK — DEGRADED بلا انهيار، ثم عودة لـ HEALTHY")


async def test_snapshot_restore_roundtrip():
    print("\n--- test_snapshot_restore_roundtrip ---")
    with tempfile.TemporaryDirectory() as tmp:
        bus, atom = await _make_atom(tmp)
        await bus.publish("tools.backup.failed", {"error": "e"})
        snap = await atom.snapshot()
        assert snap["version"] == _mod.ATOM_VERSION
        assert "tools.backup.failed" in snap["active"]
        atom2 = Atom()
        await atom2.initialize(FakeEventBus().make_context({
            "cooldown_seconds": 300, "expiry_seconds": 3600,
            "state_file": str(Path(tmp) / "s2.json"), "severity_overrides": {}}))
        await atom2.restore(snap)
        assert atom2._active == atom._active
        h = await atom2.health_check()
        assert h.state == HealthState.HEALTHY and "1 active" in h.message
    print("OK — لقطة/استعادة متماثلتان")


async def test_restore_invalid_raises():
    print("\n--- test_restore_invalid_raises ---")
    atom = Atom()
    for bad in (None, {"version": "9.9.9"}, {"version": _mod.ATOM_VERSION,
                "active": "nope"},
                {"version": _mod.ATOM_VERSION,
                 "active": {"tools.backup.failed": "nope"}}):
        try:
            await atom.restore(bad)
        except ValueError:
            pass
        else:
            raise AssertionError(f"restore({bad!r}) كان لازم يرمي ValueError")
    print("OK — الحالة الفاسدة مرفوضة")


async def test_slow_disk_never_holds_the_loop_and_loses_nothing():
    """٢٠٢٦-١٠-٠٩ (ختم المالك «NQ» — الصيانة في استراحة السوق): قرصٌ عالق (03:00 ليلًا) لا يجمّد الحلقة.

    كانت الحالة تُكتب على خيط الحلقة مع كلّ حدث فشل (112 · 115 بالعشرات في الدقيقة)، فإعادة تسميةٍ عالقة
    تجمّد المنصّة كلّها ويُتّهم 112/115. هنا تُبطَّأ الكتابة 0.6 ث عمدًا: المعالج يعود فورًا، ونبضُ حلقةٍ
    متوازٍ لا يتأخّر، وأربعون حدثًا أثناء الكتابة تُدمج — والأخير هو ما على القرص.
    """
    print("\n--- test_slow_disk_never_holds_the_loop_and_loses_nothing ---")
    import threading
    import time as _time
    with tempfile.TemporaryDirectory() as tmp:
        bus, atom = await _make_atom(tmp, cooldown_seconds=0)
        await atom.flush_state()
        gate = threading.Event()
        real = atom._persist

        def stuck_disk(state):
            gate.wait(timeout=5)           # إعادة تسميةٍ عالقة كالمقيسة ليلًا
            real(state)
        atom._persist = stuck_disk

        lags = []

        async def heartbeat():
            for _ in range(20):
                t0 = _time.perf_counter()
                await asyncio.sleep(0.01)
                lags.append(_time.perf_counter() - t0 - 0.01)
        beat = asyncio.create_task(heartbeat())
        started = _time.perf_counter()
        for index in range(40):
            await bus.publish("market_data.validation_failed",
                              {"reason": "crossed_spread #%d" % index})
        handlers_s = _time.perf_counter() - started
        await asyncio.sleep(0.25)
        gate.set()
        await beat
        await atom.flush_state()
        assert handlers_s < 0.2, "المعالجات انتظرت القرص %.3f ث" % handlers_s
        assert max(lags) < 0.1, "الحلقة تأخّرت %.3f ث والقرص عالق" % max(lags)
        on_disk = _read_state_file(tmp)["alerts"]["market_data.validation_failed"]
        assert on_disk["count"] == 40 and on_disk["detail"] == "crossed_spread #39", on_disk
        assert atom.state_coalesced >= 38 and atom.state_writes <= 3, (
            atom.state_writes, atom.state_coalesced)
        message = (await atom.health_check()).message
        assert "دُمج" in message, message
        print("OK — المعالجات %.4f ث · أقصى تأخّر نبض %.4f ث · كُتب %d ودُمج %d · الأخير على القرص"
              % (handlers_s, max(lags), atom.state_writes, atom.state_coalesced))


async def test_stop_writes_the_last_state():
    print("\n--- test_stop_writes_the_last_state ---")
    with tempfile.TemporaryDirectory() as tmp:
        bus, atom = await _make_atom(tmp)
        await bus.publish("tools.backup.failed", {"error": "last words"})
        await atom.stop()                    # لا قراءة قبل الإيقاف: الإيقاف نفسه ينتظر الكاتب
        assert _read_state_file(tmp)["alerts"]["tools.backup.failed"]["detail"] == "last words"
    print("OK — الإيقاف ينتظر آخر حالة ولا يتركها")


async def test_published_names_command_safe():
    print("\n--- test_published_names_command_safe ---")
    for name in (EVENT_ALERT, EVENT_STATE, EVENT_RECOVERED):
        assert not any(m in name for m in _COMMAND_MARKERS), (
            f"{name} يحمل أثر أمر — الناقل لن يخزّنه/يعيده")
    print("OK — أسماء النشر بلا أثر أمر (قابلة للتخزين والإعادة)")


async def main():
    tests = [
        test_subscription_contract,
        test_critical_failure_publishes_alert_and_state,
        test_warning_default_severity,
        test_cooldown_suppresses_repeat,
        test_zero_cooldown_emits_every_time,
        test_severity_override_config,
        test_sweep_ages_but_never_recovers,
        test_sweep_keeps_fresh_alerts,
        test_stop_blocks_and_start_resumes,
        test_file_write_failure_degrades_but_keeps_alerting,
        test_snapshot_restore_roundtrip,
        test_restore_invalid_raises,
        test_slow_disk_never_holds_the_loop_and_loses_nothing,
        test_stop_writes_the_last_state,
        test_published_names_command_safe,
    ]
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
