"""٢٠٢٦-١٠-٠٩ (ختم المالك «NQ» — الصيانة في استراحة السوق) — حرّاس نافذة الصيانة اليوميّة.

أمر المالك: «لازم يكون توقيت عند فترة إغلاق السوق من ساعة — مثال 12 إلى ساعة 1 — هون النظام لازم
ينظّف، يريّح، يوقّف ويجهّز ليوم جديد». والمقيس قبله: تجمّد الحلقة 25–63 ث كلّ ليلة ٠٥–٠٨ تشرين الأوّل
بين 03:00 و03:17 بتوقيت الجهاز = منتصف ليل غرينتش، موعد نبض اليوم (806) الذي كانت الصيانة كلّها عليه.

النافذة: 17:00–18:00 بتوقيت نيويورك (استراحة الوسيط) الإثنين–الخميس، ومن الجمعة 17:00 إلى الأحد 18:00
نافذةٌ واحدة. صيفًا = 00:00–01:00 بتوقيت الجهاز، وشتاءً = 01:00–02:00.
"""
from __future__ import annotations

import calendar
from dataclasses import dataclass

import pytest

from shared.owner_windows import (
    MAINTENANCE_RERUN_SLACK_S, MaintenanceGate, maintenance_window, maintenance_window_bounds)


def utc(*parts: int) -> float:
    return float(calendar.timegm(parts + (0,) * (6 - len(parts))))


HOUR = 3600.0
DAY = 86_400.0


@pytest.mark.parametrize("label, moment, key", [
    # صيفًا (نيويورك −4): 21:00–22:00 غرينتش = 00:00–01:00 بتوقيت الجهاز (+3)
    ("الإثنين 17:00 نيويورك صيفًا — أوّل النافذة", utc(2026, 10, 5, 21, 0), "2026-10-05"),
    ("الإثنين 17:59 نيويورك صيفًا", utc(2026, 10, 5, 21, 59), "2026-10-05"),
    ("الإثنين 16:59 نيويورك — قبلها", utc(2026, 10, 5, 20, 59), None),
    ("الإثنين 18:00 نيويورك — بعدها (السوق يفتح)", utc(2026, 10, 5, 22, 0), None),
    ("03:00 بتوقيت الجهاز (منتصف ليل غرينتش) — موعد التجمّدات", utc(2026, 10, 8, 0, 0), None),
    ("الخميس 17:30 نيويورك", utc(2026, 10, 8, 21, 30), "2026-10-08"),
    # شتاءً (نيويورك −5): 22:00–23:00 غرينتش = 01:00–02:00 بتوقيت الجهاز (+3)
    ("الثلاثاء 17:30 نيويورك شتاءً", utc(2026, 12, 1, 22, 30), "2026-12-01"),
    ("الثلاثاء 21:30 غرينتش شتاءً = 16:30 نيويورك — قبلها", utc(2026, 12, 1, 21, 30), None),
    ("الثلاثاء 22:59 غرينتش شتاءً", utc(2026, 12, 1, 22, 59), "2026-12-01"),
    ("الثلاثاء 23:00 غرينتش شتاءً — بعدها", utc(2026, 12, 1, 23, 0), None),
    # الجمعة ⟵ الأحد نافذةٌ واحدة بمفتاح الجمعة
    ("الجمعة 16:59 نيويورك — قبل إغلاق الأسبوع", utc(2026, 10, 9, 20, 59), None),
    ("الجمعة 17:00 نيويورك — إغلاق الأسبوع", utc(2026, 10, 9, 21, 0), "2026-10-09"),
    ("السبت ظهرًا", utc(2026, 10, 10, 12, 0), "2026-10-09"),
    ("الأحد 17:59 نيويورك", utc(2026, 10, 11, 21, 59), "2026-10-09"),
    ("الأحد 18:00 نيويورك — يفتح الأسبوع", utc(2026, 10, 11, 22, 0), None),
])
def test_window_summer_winter_and_weekend(label, moment, key):
    assert maintenance_window(moment) == key, label


def test_window_moves_with_new_york_daylight_saving():
    """أوّل أحدٍ في تشرين الثاني 2026 (01-11) تعود نيويورك إلى −5 فتنزاح النافذة ساعةً بتوقيت غرينتش."""
    friday_before = maintenance_window_bounds(utc(2026, 10, 30, 12, 0))
    monday_after = maintenance_window_bounds(utc(2026, 11, 2, 12, 0))
    assert friday_before[0] == utc(2026, 10, 30, 21, 0)       # الجمعة 17:00 صيفيّ
    assert friday_before[1] == utc(2026, 11, 1, 23, 0)        # الأحد 18:00 شتويّ
    assert monday_after[:2] == (utc(2026, 11, 2, 22, 0), utc(2026, 11, 2, 23, 0))
    spring = maintenance_window_bounds(utc(2027, 3, 15, 12, 0))   # بعد ثاني أحدٍ في آذار
    assert spring[:2] == (utc(2027, 3, 15, 21, 0), utc(2027, 3, 15, 22, 0))


def test_bounds_name_the_next_window_when_outside():
    start, end, key = maintenance_window_bounds(utc(2026, 10, 8, 0, 0))   # 03:00 بتوقيت الجهاز
    assert (start, end, key) == (utc(2026, 10, 8, 21, 0), utc(2026, 10, 8, 22, 0), "2026-10-08")
    assert end - start == HOUR


def test_gate_runs_once_inside_and_never_outside():
    gate = MaintenanceGate()
    assert gate.due(utc(2026, 10, 8, 0, 0)) is None                       # 03:00 — خارجها
    assert gate.due(utc(2026, 10, 8, 0, 0), held=True) is None
    assert gate.held_outside == 1
    inside = utc(2026, 10, 8, 21, 5)
    key = gate.due(inside)
    assert key == "2026-10-08"
    gate.mark(key, inside)
    for later in (inside + 60, inside + 30 * 60, inside + 54 * 60):
        assert gate.due(later) is None, "مرّةً واحدة في النافذة"
    assert gate.due(utc(2026, 10, 9, 21, 0)) == "2026-10-09"              # نافذة الجمعة


def test_gate_does_not_skip_a_day_when_last_run_was_late_in_its_window():
    gate = MaintenanceGate()
    late = utc(2026, 10, 5, 21, 58)                       # آخر دقيقةٍ من نافذة الإثنين
    gate.mark(gate.due(late), late)
    next_open = utc(2026, 10, 6, 21, 0)                   # أوّل دقيقةٍ من نافذة الثلاثاء: 23:02 ساعة
    assert next_open - late < DAY
    assert gate.due(next_open, last_success=late) == "2026-10-06"
    assert DAY - MAINTENANCE_RERUN_SLACK_S < next_open - late


def test_gate_skips_a_window_right_after_a_fresh_run():
    """إقلاعٌ داخل النافذة بعد نجاحٍ قبل ساعة (من حالةٍ مستعادة بلا مفتاح) لا يكرّر العمل."""
    gate = MaintenanceGate()
    now = utc(2026, 10, 5, 21, 30)
    assert gate.due(now, last_success=now - HOUR) is None
    assert gate.last_key == "2026-10-05" and gate.due(now + 60) is None


def test_restart_inside_window_retries_a_failed_run_but_not_a_successful_one():
    """عقد المالك ٢٠٢٦-٠٨-١٦: فشلٌ في المنتصف ⟸ يعيد المحاولة عند الإقلاع التالي — ولو في النافذة نفسها.
    ونجاحٌ في النافذة لا يتكرّر بعد إقلاعٍ فيها: يمنعه عمر آخر نجاح."""
    gate = MaintenanceGate()
    now = utc(2026, 10, 5, 21, 10)
    gate.mark(gate.due(now), now)
    again = MaintenanceGate()
    again.restore(gate.snapshot())
    assert again.last_at == now
    assert again.due(now + 20 * 60, last_success=None) == "2026-10-05"      # المقتولة تُعاد
    assert again.due(now + 20 * 60, last_success=now + 60) is None           # الناجحة لا تتكرّر
    again.restore({"maintenance_at": "x"})                                  # حالةٌ مشوّهة لا تُصدَّق
    assert again.last_at is None


def test_describe_and_announce_name_last_and_next():
    @dataclass(frozen=True)
    class Status:
        state: str
        message: str = ""

    gate = MaintenanceGate()
    assert "آخرها —" in gate.describe()
    now = utc(2026, 10, 5, 21, 30)
    gate.mark(gate.due(now), now)
    text = gate.describe()
    assert text.startswith("صيانة: آخرها ") and "القادمة" in text and "—" not in text.split("آخرها")[1][:3]
    announced = gate.announce(Status("healthy", "stored=3"))
    assert announced.message.startswith("stored=3 · صيانة: آخرها ") and announced.state == "healthy"
