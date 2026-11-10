"""٢٠٢٦-١٠-٠٢ (ختم المالك «صلح كامل nq») — سجلّ الأخطاء يستقبل سطور المحرّك عبر الناقل (1.2.0).

719 لا تسمع حدثًا: تعلّق لاقطها على مسجّلات عمليّتها. ومنذ نُقلت إلى العمليّة الباردة
(٢٠٢٦-٠٩-١٨) لا يصلها سطرٌ من المحرّك (عدّ مصادر `errors-*.log`). الآن تسمع
`system.log.record` وتكتبه بالسقف وحصّة الأخطاء نفسيهما.
"""
from __future__ import annotations

import importlib.util
import inspect
import logging
import sys
from pathlib import Path

import yaml

FOLDER = Path(__file__).resolve().parents[1]
ROOT = Path(__file__).resolve().parents[4]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.contracts.atom import AtomContext  # noqa: E402

_spec = importlib.util.spec_from_file_location("_atom719_fix_b", FOLDER / "atom.py")
mod = importlib.util.module_from_spec(_spec)
sys.modules["_atom719_fix_b"] = mod
_spec.loader.exec_module(mod)

MANIFEST = yaml.safe_load((FOLDER / "manifest.yaml").read_text(encoding="utf-8"))
EVENT = "system.log.record"


class _Bus:
    def __init__(self):
        self.handlers = {}

    def subscribe(self, name, handler):
        self.handlers.setdefault(name, []).append(handler)

    async def publish(self, name, payload=None):
        for handler in self.handlers.get(name, []):
            result = handler(payload)
            if inspect.isawaitable(result):
                await result


class _Null:
    def __getattr__(self, name):
        return lambda *a, **k: None


async def _atom(tmp_path, cap=20000):
    bus = _Bus()
    atom = mod.Atom()
    await atom.initialize(AtomContext(719, {
        "dir": str(tmp_path), "file_prefix": "errors", "min_level": "WARNING",
        "include_root": False, "max_lines_per_day": cap}, _Null(), bus.publish, bus.subscribe))
    await atom.start()
    return atom, bus


def _lines(tmp_path):
    files = sorted(tmp_path.glob("errors-*.log"))
    assert files, "ما كُتب ملفّ"
    return files[-1].read_text(encoding="utf-8").splitlines()[1:]


async def test_engine_line_reaches_the_error_log(tmp_path):
    atom, bus = await _atom(tmp_path)
    assert EVENT in bus.handlers, "719 تسمع سطور المحرّك"
    await bus.publish(EVENT, {"level": "ERROR", "logger": "quant_nq.core.atom.577",
                              "atom_id": 577, "message": "577 stop tighten failed",
                              "created": 1790960000.0, "repeats": 1, "process": "hot"})
    await bus.publish(EVENT, {"level": "WARNING", "logger": "quant_nq.core.atom.453",
                              "atom_id": 453, "message": "453 silent EURUSD",
                              "created": 1790960001.0, "repeats": 37, "process": "hot"})
    lines = _lines(tmp_path)
    assert len(lines) == 2, lines
    assert "| ERROR | ATOM 577 @hot | quant_nq.core.atom.577 | 577 stop tighten failed" in lines[0]
    assert lines[1].endswith("453 silent EURUSD (×37)"), lines[1]
    health = await atom.health_check()
    assert health.details["forwarded_received"] == 2
    await atom.stop()


async def test_below_level_and_malformed_are_counted_not_written(tmp_path):
    atom, bus = await _atom(tmp_path)
    await bus.publish(EVENT, {"level": "INFO", "message": "noise"})
    await bus.publish(EVENT, {"level": "BOGUS", "message": "x"})
    await bus.publish(EVENT, "not a dict")
    assert not list(tmp_path.glob("errors-*.log"))
    assert atom.forwarded_rejected == 2 and atom.forwarded_received == 0
    await atom.stop()


async def test_forwarded_lines_share_the_daily_cap_and_error_reserve(tmp_path):
    atom, bus = await _atom(tmp_path, cap=100)
    for i in range(150):
        await bus.publish(EVENT, {"level": "WARNING", "message": "w%d" % i, "created": 1.0})
    await bus.publish(EVENT, {"level": "ERROR", "message": "the real one", "created": 2.0})
    lines = _lines(tmp_path)
    assert sum(1 for line in lines if "| WARNING |" in line) == 90, "العُشر الأخير للأخطاء"
    assert any("the real one" in line for line in lines), "الخطأ لا يطرده تحذير"
    await atom.stop()


def test_manifest_declares_the_subscription():
    assert MANIFEST["subscribes"] == [EVENT]
