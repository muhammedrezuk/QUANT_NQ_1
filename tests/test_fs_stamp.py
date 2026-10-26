# -*- coding: utf-8 -*-
"""حرّاس طابع الحداثة المخزَّن — التكافؤ أوّلًا، ثمّ التوفير.

الحارس الأوّل والأهمّ: **النتيجة لم تتغيّر**. تخزينُ الـ`stat` إن غيّر قيمةً
واحدة من قيم العيارات فهو عطبٌ لا تحسين — وهذه العيارات تدخل وزن المحلّل
وأرضيّة الإبطال، أي تمسّ المال.
"""
from __future__ import annotations

import json
import os
import time

import pytest

from shared import fs_stamp


#: ⛔ هامشٌ خمسةُ أضعافٍ لا عُشر. كان `0.05` مع نومٍ `0.06` — عشرة
#: مِلّي ثانيةٍ فارقًا — فسقط الحارس واحدةً من ثلاث على جهازٍ محمَّل.
#: وحارسٌ يتقلّب حارسٌ يكذب: يصرخ بلا ذئب، فيُهمَل حين يجيء الذئب.
_WINDOW = 0.05


@pytest.fixture(autouse=True)
def _clean():
    fs_stamp.forget()
    yield
    fs_stamp.forget()


# ── التكافؤ ──────────────────────────────────────────────────────────────

def test_stamp_matches_a_direct_stat(tmp_path):
    """الطابع المعاد هو طابع `os.stat` نفسه، لا تقريبه."""
    target = tmp_path / "a.json"
    target.write_text("{}", encoding="utf-8")
    ok, stamp = fs_stamp.file_stamp(target)
    assert ok is True
    assert stamp == os.stat(target).st_mtime


def test_missing_file_reports_failure_like_stat_would(tmp_path):
    """ملفٌّ غائب ⇒ `(False, 0.0)` — فيسلك المستدعي مسلك `OSError` كما كان."""
    ok, stamp = fs_stamp.file_stamp(tmp_path / "ليس-موجودًا.json")
    assert (ok, stamp) == (False, 0.0)


def test_a_file_deleted_within_the_window_is_not_reported_missing(tmp_path):
    """الفشل يُخزَّن كما يُخزَّن النجاح — لا يُقلب الحكم داخل الفترة.

    ⛔ هذا هو الفرق السلوكيّ الوحيد، وهو مقصودٌ ومحدود: سقفُ تأخّرٍ
    قدرُه `recheck_s`، في الاتّجاهين معًا لا في اتّجاه النجاح وحده.
    """
    target = tmp_path / "b.json"
    target.write_text("{}", encoding="utf-8")
    assert fs_stamp.file_stamp(target, recheck_s=30.0)[0] is True
    target.unlink()
    assert fs_stamp.file_stamp(target, recheck_s=30.0)[0] is True   # داخل الفترة
    fs_stamp.forget(target)
    assert fs_stamp.file_stamp(target, recheck_s=30.0)[0] is False  # بعد النسيان


def test_a_created_file_is_seen_once_the_window_passes(tmp_path):
    """والعكس كذلك: غائبٌ ثمّ ظهر — يُرى بعد انقضاء الفترة."""
    target = tmp_path / "c.json"
    assert fs_stamp.file_stamp(target, recheck_s=_WINDOW)[0] is False
    target.write_text("{}", encoding="utf-8")
    time.sleep(_WINDOW * 5)
    assert fs_stamp.file_stamp(target, recheck_s=_WINDOW)[0] is True


def test_a_change_after_the_window_is_seen(tmp_path):
    target = tmp_path / "d.json"
    target.write_text("{}", encoding="utf-8")
    first = fs_stamp.file_stamp(target, recheck_s=_WINDOW)[1]
    time.sleep(_WINDOW * 5)
    os.utime(target, (first + 10.0, first + 10.0))
    assert fs_stamp.file_stamp(target, recheck_s=_WINDOW)[1] == pytest.approx(first + 10.0)


# ── التوفير — وهو سببُ وجود الملفّ ────────────────────────────────────────

def test_repeated_calls_within_the_window_cost_one_syscall(tmp_path):
    """ألفُ نداءٍ ⟶ نداءُ نظامٍ واحد. هذا هو الرقم المطلوب."""
    target = tmp_path / "e.json"
    target.write_text("{}", encoding="utf-8")
    before = fs_stamp.stats()["syscalls"]
    for _ in range(1000):
        fs_stamp.file_stamp(target, recheck_s=30.0)
    assert fs_stamp.stats()["syscalls"] - before == 1


def test_each_path_is_tracked_on_its_own(tmp_path):
    """مسارٌ لا يُخفي مسارًا — ثلاثة ملفّات ثلاثةُ طوابع."""
    paths = []
    for name in ("f", "g", "h"):
        p = tmp_path / ("%s.json" % name)
        p.write_text("{}", encoding="utf-8")
        paths.append(p)
    for p in paths:
        fs_stamp.file_stamp(p, recheck_s=30.0)
    assert fs_stamp.stats()["tracked"] == 3


# ── المستدعون الثلاثة — التكافؤ على البيانات الحقيقيّة ────────────────────

def test_movement_scale_is_unchanged_for_every_measured_symbol():
    """القيمة نفسها للرموز المقيسة كلّها — قبل التخزين وبعده."""
    from shared import strategy_contract as sc
    if not sc._SCALE_PATH.exists():
        pytest.skip("لا ملفّ مقياسٍ على هذا الجهاز")
    table = json.loads(sc._SCALE_PATH.read_text(encoding="utf-8")).get("symbols") or {}
    assert table, "الملفّ موجودٌ وفارغ — الاختبار بلا معنى"
    for symbol, row in table.items():
        frac = float(row["frac"])
        fs_stamp.forget()
        expected = 100.0 / frac
        assert sc.movement_scale(symbol, 50_000.0) == pytest.approx(expected)
        assert sc.movement_scale(symbol, 50_000.0) == pytest.approx(expected)  # من الذاكرة


def test_edge_factor_is_unchanged_for_every_pair_in_the_file():
    """القيمة المعادة هي الرقم في الملفّ حرفًا — و`null` يبقى «لا حكم».

    ⚠️ الصيغة الأولى من هذا الحارس افترضت `{"factor": …}` والحقيقة رقمٌ
    عارٍ، فمرّ بصفر مقارنة. العدّاد أدناه هو ما كشفه، فبقي.
    """
    from shared import strategy_contract as sc
    if not sc._EDGE_PATH.exists():
        pytest.skip("لا ملفّ حافّةٍ على هذا الجهاز")
    fs_stamp.forget()
    sc.edge_factor("trend_continuation", "BTCUSD")        # يملأ الجدول
    table = dict(sc._EDGE_CACHE["table"])
    assert table, "الملفّ موجودٌ وفارغ — الاختبار بلا معنى"
    compared = 0
    for name, atom in sc._ATOM_OF.items():
        for symbol, raw in (table.get(atom) or {}).items():
            value = sc.edge_factor(name, symbol)
            if raw is None or isinstance(raw, bool):
                assert value is None
            else:
                number = float(raw)
                assert value == (pytest.approx(number)
                                 if number >= 0.0 else None)
            compared += 1
    assert compared > 0, "لم يُقارَن زوجٌ واحد — الحارس أعمى"


def test_edge_factor_still_reads_a_real_number_through_the_cache(tmp_path, monkeypatch):
    """حارسٌ لا يعتمد على بيانات الجهاز: رقمٌ مزروع يجب أن يعبر كما هو.

    بيانات الجهاز اليوم `null` في كلّ زوج (عيّنةٌ دون الحدّ)، فلو اكتفينا بها
    لكان الحارس يمرّ على دالّةٍ لا تُعيد رقمًا قطّ.
    """
    from shared import strategy_contract as sc
    planted = tmp_path / "edge.json"
    planted.write_text(json.dumps(
        {"derived_weights": {"404": {"BTCUSD": 0.625, "XAUUSD": None}}}),
        encoding="utf-8")
    monkeypatch.setattr(sc, "_EDGE_PATH", planted)
    monkeypatch.setitem(sc._EDGE_CACHE, "mtime", None)
    fs_stamp.forget()
    assert sc.edge_factor("trend_continuation", "BTCUSD") == pytest.approx(0.625)
    assert sc.edge_factor("trend_continuation", "XAUUSD") is None
    before = fs_stamp.stats()["syscalls"]
    for _ in range(50):
        assert sc.edge_factor("trend_continuation", "BTCUSD") == pytest.approx(0.625)
    assert fs_stamp.stats()["syscalls"] == before


def test_floor_frac_is_unchanged_for_every_symbol_in_the_file():
    from shared import trade_setup as ts
    if not ts._FLOOR_PATH.exists():
        pytest.skip("لا ملفّ أرضيّةٍ على هذا الجهاز")
    table = json.loads(ts._FLOOR_PATH.read_text(encoding="utf-8")).get("symbols") or {}
    assert table, "الملفّ موجودٌ وفارغ — الاختبار بلا معنى"
    for symbol in table:
        fs_stamp.forget()
        first = ts._floor_frac(symbol)
        assert first == ts._floor_frac(symbol)            # من الذاكرة
        assert first is not None


def test_the_three_callers_no_longer_stat_on_every_call():
    """الحارس الذي يمنع عودة العطب: نداءان لكلّ دالّة ⟶ `stat` واحد لكلّ ملفّ."""
    from shared import strategy_contract as sc
    from shared import trade_setup as ts
    fs_stamp.forget()
    sc.movement_scale("BTCUSD", 50_000.0)
    sc.edge_factor("trend_continuation", "BTCUSD")
    ts._floor_frac("BTCUSD")
    after_first = fs_stamp.stats()["syscalls"]
    for _ in range(200):
        sc.movement_scale("BTCUSD", 50_000.0)
        sc.edge_factor("trend_continuation", "BTCUSD")
        ts._floor_frac("BTCUSD")
    assert fs_stamp.stats()["syscalls"] == after_first
