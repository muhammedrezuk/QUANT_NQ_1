"""٢٠٢٦-١٠-٠٢ (ختم المالك «صلح كامل nq») — حرّاس إصلاح المُنذِر (1.1.0).

المقيس قبل الإصلاح: الكنس يمحو كلّ إنذارٍ صمت ساعة ويعلنه «مستردًّا» بلا حدث نجاح
(`atom.py:191-207` يومها). فالنسخ الاحتياطيّ بلا نجاحٍ منذ ٠٩-١٨ ولا إنذار له في
الحالة الحيّة؛ وأحداث فشل مسار التنفيذ (صحّة النواة · رفض مصدر التغذية · رفض تأكيد
التنفيذ) لا يسمعها أحد.
"""
from __future__ import annotations

import importlib.util
import inspect
import json
import sys
from pathlib import Path

import yaml

FOLDER = Path(__file__).resolve().parents[1]
ROOT = Path(__file__).resolve().parents[4]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.contracts.atom import AtomContext  # noqa: E402

_spec = importlib.util.spec_from_file_location("_atom831_fix_b", FOLDER / "atom.py")
mod = importlib.util.module_from_spec(_spec)
sys.modules["_atom831_fix_b"] = mod
_spec.loader.exec_module(mod)

MANIFEST = yaml.safe_load((FOLDER / "manifest.yaml").read_text(encoding="utf-8"))


class _Bus:
    def __init__(self):
        self.published = []
        self.handlers = {}

    def subscribe(self, name, handler):
        self.handlers.setdefault(name, []).append(handler)

    async def publish(self, name, payload=None):
        self.published.append((name, payload))
        for handler in self.handlers.get(name, []):
            result = handler(payload)
            if inspect.isawaitable(result):
                await result

    def of(self, name):
        return [p for n, p in self.published if n == name]


class _Null:
    def __getattr__(self, name):
        return lambda *a, **k: None


async def _atom(tmp_path):
    bus = _Bus()
    atom = mod.Atom()
    await atom.initialize(AtomContext(831, {
        "cooldown_seconds": 300, "expiry_seconds": 3600,
        "state_file": str(tmp_path / "system_alerts.json"), "severity_overrides": {}},
        _Null(), bus.publish, bus.subscribe))
    await atom.start()
    return atom, bus


def _file(tmp_path):
    return json.loads((tmp_path / "system_alerts.json").read_text(encoding="utf-8"))


async def test_daily_failure_survives_a_day_of_silence(tmp_path):
    """فشل النسخ يُنشر مرّةً في اليوم — يبقى بعد يومٍ من الصمت، ولا «استرداد» كاذب."""
    atom, bus = await _atom(tmp_path)
    await bus.publish("tools.backup.failed", {"reason": "partial copy"})
    atom._active["tools.backup.failed"]["last_at"] -= 25 * 3600
    for _ in range(3):
        await bus.publish(mod.EVENT_SWEEP, {})
    assert bus.of(mod.EVENT_RECOVERED) == []
    # ٢٠٢٦-١٠-٠٩ (ختم المالك «NQ» — الصيانة في استراحة السوق): الملفّ يُكتب في خيط — يُنتظر قبل قراءته.
    await atom.flush_state()
    on_disk = _file(tmp_path)["alerts"]["tools.backup.failed"]
    assert on_disk["aged"] is True and on_disk["display_severity"] == "warning"
    assert on_disk["severity"] == "critical" and on_disk["detail"] == "partial copy"
    # تكرارٌ جديد يعيده إلى درجته.
    await bus.publish("tools.backup.failed", {"reason": "again"})
    await atom.flush_state()
    assert _file(tmp_path)["alerts"]["tools.backup.failed"]["aged"] is False


async def test_success_event_clears_only_its_own_failure(tmp_path):
    atom, bus = await _atom(tmp_path)
    await bus.publish("tools.backup.failed", {"reason": "x"})
    await bus.publish("tools.file_archive.failed", {"reason": "y"})
    await bus.publish("tools.backup.completed", {"path": "p"})
    recovered = bus.of(mod.EVENT_RECOVERED)
    assert len(recovered) == 1 and recovered[0]["recovered"] == ["tools.backup.failed"]
    assert recovered[0]["by"] == "tools.backup.completed"
    assert set(atom._active) == {"tools.file_archive.failed"}


async def test_core_health_alarm_clears_per_atom_not_per_event(tmp_path):
    atom, bus = await _atom(tmp_path)
    await bus.publish("core.atom.unhealthy", {"atom_id": 575})
    await bus.publish("core.atom.unhealthy", {"atom_id": 577})
    await bus.publish("core.atom.restarted", {"atom_id": 575})
    assert "core.atom.unhealthy" in atom._active, "استرداد 575 لا يمحو إنذار 577"
    assert atom._active["core.atom.unhealthy"]["subjects"] == ["577"]
    await bus.publish("core.atom.started", {"atom_id": 12})      # ذرّةٌ لا إنذار لها
    assert "core.atom.unhealthy" in atom._active
    await bus.publish("core.atom.started", {"atom_id": 577})
    assert "core.atom.unhealthy" not in atom._active
    assert bus.of(mod.EVENT_RECOVERED)[-1]["subject"] == "577"


async def test_execution_path_failures_are_heard(tmp_path):
    atom, bus = await _atom(tmp_path)
    cases = {
        "core.atom.failed": ({"atom_id": 601, "error": "boom"}, "critical", 0),
        "core.critical_atom.unhealthy": ({"atom_id": 516}, "critical", 0),
        "core.atom.restarts_exhausted": ({"atom_id": 577}, "critical", 0),
        "core.atom.restart_failed": ({"atom_id": 575, "error": "x"}, "critical", 0),
        "market.feed.source_rejected": ({"provider": "YAHOO", "reason": "NOT_ANALYST"}, "warning", 613),
        "execution.confirmation.rejected": ({"reason": "MISSING_DURABLE_EVENT_ID_OR_SCOPE"}, "critical", 563),
    }
    for event, (payload, severity, source) in cases.items():
        await bus.publish(event, payload)
        alert = [a for a in bus.of(mod.EVENT_ALERT) if a["source_event"] == event]
        assert alert and alert[0]["severity"] == severity and alert[0]["source_atom"] == source, event
    # مستثناة بقرارٍ مقيس: حالةٌ لا فشل (582)، وما يستردّ نفسه مئة مرّةٍ يوميًّا (613 · 116).
    for excluded in ("execution.reference_divergence.state", "market.feed.provider_down",
                     "market_data.feed_interrupted"):
        assert excluded not in mod._MONITORED, excluded


async def test_success_without_alarm_publishes_nothing(tmp_path):
    """`core.atom.started` يصل بالمئات عند كلّ إقلاع — بلا إنذارٍ قائم لا نشر."""
    atom, bus = await _atom(tmp_path)
    for atom_id in range(230):
        await bus.publish("core.atom.started", {"atom_id": atom_id})
    assert [n for n, _ in bus.published if n != "core.atom.started"] == []


async def test_live_1_0_snapshot_is_restored_after_the_version_bump(tmp_path):
    """رفضُ لقطة 1.0 كان يُسقط إقلاع 831 — شكلُها هو المقيس حيًّا ٢٠٢٦-١٠-٠٢."""
    live = {"version": "1.0.4", "active": {"market_data.validation_failed": {
        "severity": "critical", "count": 99413, "first_at": 1790753342.07,
        "last_at": 1790962090.17, "last_emitted": 1790962077.73, "detail": "crossed_spread"}},
        "file_error": None}
    atom, _bus = await _atom(tmp_path)
    await atom.restore(live)
    assert atom._active["market_data.validation_failed"]["count"] == 99413
    again = mod.Atom()
    await again.restore(await atom.snapshot())
    assert again._active == atom._active


def test_manifest_declares_every_subscription():
    expected = set(mod._MONITORED) | set(mod._RECOVERY) | {mod.EVENT_SWEEP}
    assert set(MANIFEST["subscribes"]) == expected
    for failures in mod._RECOVERY.values():
        assert set(failures) <= set(mod._MONITORED)


async def test_archived_section_validation_failures_are_not_heard(tmp_path):
    """٢٠٢٦-١٠-٠٧ (ختم «NQ»): ناشرا فشل التحقّق في البنية (209) والسيولة (259) أُرشفا.

    لا اشتراك ولا مراقبة، وإنذارٌ قائمٌ لهما في لقطةٍ حيّة قديمة تُسقطه الاستعادة
    بلا رفضٍ يُفشل الإقلاع — والباقي (فشل تحقّق بيانات السوق 112) يُستعاد كما كان.
    """
    atom, bus = await _atom(tmp_path)
    for dropped in ("structure.validation_failed", "liquidity.validation_failed"):
        assert dropped not in mod._MONITORED, dropped
        assert dropped not in bus.handlers, dropped
        assert dropped not in MANIFEST["subscribes"], dropped
    assert "market_data.validation_failed" in bus.handlers
    old = {"version": "1.0.4", "file_error": None, "active": {
        "structure.validation_failed": {"severity": "critical", "count": 3,
                                        "first_at": 1.0, "last_at": 2.0, "last_emitted": 2.0},
        "market_data.validation_failed": {"severity": "critical", "count": 5,
                                          "first_at": 1.0, "last_at": 2.0, "last_emitted": 2.0}}}
    await atom.restore(old)
    assert set(atom._active) == {"market_data.validation_failed"}
