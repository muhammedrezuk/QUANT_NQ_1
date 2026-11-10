# -*- coding: utf-8 -*-
"""مدير الموارد — §٩ · §١٩ · §٢٥ · §٢٦ من ورقة المصنع.

المقيس الذي تُبنى عليه الحالات (٢٠٢٦-٠٩-١٧ · نافذة ١٣٠ ث):
    معالج النواة 105% من نواة · عالميّ 11% · BTCUSD 26.7% · XAUUSD 22.8%
"""
from __future__ import annotations

import pytest

from transport.resource_manager import (
    MIN_WORKERS,
    PEAK_MARGIN,
    POLICY_EMERGENCY,
    POLICY_NORMAL,
    POLICY_PRESSURE,
    POLICY_TARGET,
    LoadMeasurement,
    Resources,
    load_state,
    plan_workers,
    policy,
)

#: الحمل كما قِيس فعلًا على هذه الشجرة.
MEASURED = LoadMeasurement(
    core_cpu_ratio=1.05,
    global_ratio=0.11,
    per_symbol={"BTCUSD": 0.267, "XAUUSD": 0.228, "USTEC": 0.194,
                "GBPUSD": 0.067, "EURUSD": 0.050, "US30": 0.045, "US500": 0.035},
)


def test_no_core_count_is_hard_coded_anywhere() -> None:
    """§٨ و§٣٣: «لا يوجد رقم ثابت للمعالج داخل الكود»."""
    import inspect
    import transport.resource_manager as mod
    src = inspect.getsource(mod)
    body = "\n".join(l for l in src.splitlines()
                     if not l.strip().startswith(("#", '"', "'")))
    for forbidden in (" 6", " 12", " 24"):
        assert "cpu_count() %s" % forbidden not in body
    assert "os.cpu_count()" in src            # يُكتشف
    assert "physical_cores" in src            # ولا يُخمَّن


def test_physical_cores_are_not_guessed() -> None:
    """`cpu_count` يُرجع الخيوط. الأنوية الفيزيائية تبقى `None` لا تخمينًا."""
    res = Resources.discover()
    assert res.logical_threads >= 1
    assert res.physical_cores is None


def test_usable_threads_reserve_half_the_machine() -> None:
    """§١٩: الهدف ≤ ٥٠٪ والاحتياط ≥ ٥٠٪."""
    assert Resources(logical_threads=12).usable_threads == 6
    assert Resources(logical_threads=1).usable_threads == 1      # لا صفر


def test_plan_is_derived_from_measured_load_not_from_the_machine() -> None:
    """§٢٥ و§٢٦: العدد من الحمل وقدرة الوحدة، لا من قسمة الأنوية."""
    plan = plan_workers(Resources(logical_threads=12), MEASURED)
    # 1.05 × 2.0 = 2.10 حملًا عند الذروة  ·  ÷ 0.50 = 4.2  ⟶  5 عمّال
    assert plan.workers == 5
    # ⚠️ والوحدة واحدة في الطرفين: حملٌ مقابل حملٍ مسموح، لا سعةٌ خام.
    assert plan.required_capacity == pytest.approx(2.10, abs=1e-3)
    assert plan.available_capacity == pytest.approx(2.50, abs=1e-3)
    assert plan.fits
    assert "حمل 1.05" in plan.reason and "ذروة 2.0" in plan.reason


def test_the_same_load_on_a_bigger_machine_does_not_change_the_need() -> None:
    """§٢١: نفس الكود ونفس الحمل — يتغيّر السقف لا الحاجة."""
    small = plan_workers(Resources(logical_threads=4), MEASURED)
    big = plan_workers(Resources(logical_threads=64), MEASURED)
    assert big.workers == 5, "الحاجة من الحمل لا من الجهاز"
    assert small.workers == 2, "الجهاز الصغير يحدّ — ويُعلَن"
    assert any("الجهاز نفسه هو الحدّ" in w for w in small.warnings)


def test_an_indivisible_heavy_symbol_is_announced_not_hidden() -> None:
    """§٢٢ و§٢٣: زيادة العمّال لا تقسم وحدة. يُقال بالاسم."""
    heavy = LoadMeasurement(core_cpu_ratio=1.05, global_ratio=0.11,
                            per_symbol={"BTCUSD": 0.90, "EURUSD": 0.10})
    plan = plan_workers(Resources(logical_threads=12), heavy)
    assert plan.heaviest_unit > POLICY_TARGET
    assert any("لا تنقسم" in w and "AnalysisGroup" in w for w in plan.warnings)


def test_todays_heaviest_symbol_already_exceeds_the_target() -> None:
    """⚠️ والمقيس اليوم **يقع في هذه الحالة**: 26.7% × ذروة 2 = 53.4%."""
    plan = plan_workers(Resources(logical_threads=12), MEASURED)
    assert plan.heaviest_unit == pytest.approx(1.05 * 0.267 * PEAK_MARGIN, abs=1e-3)
    assert plan.heaviest_unit > POLICY_TARGET
    assert plan.warnings, "سقف التوازي بلغ الهدف ولم يُعلَن"


def test_a_heavy_backbone_is_announced_because_splitting_will_not_help() -> None:
    """§١١: ما يمرّ بالعمود الفقريّ لا يخفّفه التقسيم بالرمز."""
    fat = LoadMeasurement(core_cpu_ratio=1.0, global_ratio=0.70,
                          per_symbol={"EURUSD": 1.0})
    assert any("العمود الفقريّ" in w for w in
               plan_workers(Resources(logical_threads=12), fat).warnings)


def test_measured_backbone_is_light_so_no_such_warning() -> None:
    """والمقيس اليوم ١١٪ — فالتقسيم بالرمز مجدٍ، وهذا ما حسمته §٢٤-٢."""
    plan = plan_workers(Resources(logical_threads=12), MEASURED)
    assert not any("العمود الفقريّ" in w for w in plan.warnings)


@pytest.mark.parametrize("ratio,expected", [
    (0.00, "NORMAL"), (0.39, "NORMAL"),
    (0.40, "TARGET"), (0.49, "TARGET"),
    (0.50, "PRESSURE"), (0.69, "PRESSURE"),
    (0.70, "EMERGENCY"), (0.79, "EMERGENCY"),
    (0.80, "FAILED"), (1.20, "FAILED"),
])
def test_load_policy_thresholds_are_declared_and_exact(ratio, expected) -> None:
    """الحدّ يُختبر **عنده** لا في وسطه."""
    assert load_state(ratio) == expected


def test_policy_is_published_by_name() -> None:
    """§٣٠: أيّ أفضلية تُضاف تظهر بالاسم، وإلّا صارت عمًى جديدًا."""
    p = policy()
    assert p["normal"] == POLICY_NORMAL and p["target"] == POLICY_TARGET
    assert p["pressure"] == POLICY_PRESSURE and p["emergency"] == POLICY_EMERGENCY
    assert p["min_workers"] == MIN_WORKERS


def test_negative_load_is_refused_not_clamped() -> None:
    with pytest.raises(ValueError):
        LoadMeasurement(core_cpu_ratio=-1.0)
    with pytest.raises(ValueError):
        LoadMeasurement(core_cpu_ratio=1.0, global_ratio=1.5)


# ── حدود الزمن — بند بوّابة §٣٦ ───────────────────────────────────────────

def test_the_time_ladder_never_inverts() -> None:
    """العطب الذي وقع: الصامت (15 ث) سبق المسمّى (30 ث) فابتلعه."""
    from transport.resource_manager import (
        TIME_COORDINATOR_SWEEP_S, TIME_INFLIGHT_CEILING_S,
        TIME_WORKER_DRAIN_S, _assert_time_ladder)
    assert TIME_WORKER_DRAIN_S < TIME_COORDINATOR_SWEEP_S < TIME_INFLIGHT_CEILING_S
    _assert_time_ladder()


def test_an_inverted_ladder_is_refused_at_import(monkeypatch) -> None:
    import transport.resource_manager as mod
    monkeypatch.setattr(mod, "TIME_WORKER_DRAIN_S", 99.0)
    with pytest.raises(AssertionError) as caught:
        mod._assert_time_ladder()
    assert "مقلوب" in str(caught.value)


def test_a_budget_that_reaches_the_sweep_is_refused(monkeypatch) -> None:
    """ميزانيةٌ تبلغ الكنس تُعيد العطب نفسه — تُرفض لا تُقبل."""
    import transport.resource_manager as mod
    monkeypatch.setattr(mod, "TIME_WORK_BUDGET_S", 30.0)
    with pytest.raises(AssertionError):
        mod._assert_time_ladder()


def test_bounds_are_published_and_say_the_budget_is_off() -> None:
    from transport.resource_manager import time_bounds
    b = time_bounds()
    assert b["worker_drain_s"] == 15.0 and b["coordinator_sweep_s"] == 30.0
    assert b["inflight_ceiling_s"] == 60.0
    # ⚠️ الميزانية **مطفأة** حتى تُشتقّ من ٥٬٠٠٠ عيّنة — ويُقال صراحةً.
    assert b["work_budget_s"] == 0.0 and b["budget_active"] is False


# (٢٠٢٦-٠٩-١٧) حارس «الحدود المعلَنة تطابق منفّذيها» أُرشف مع المزرعة:
# منفّذوها (analysis_farm · atom_host · symbol_coordinator) في archive/experimental/farm/.


# ── عدد الأقسام المنطقيّة ومفتاح الملكيّة — بند بوّابة §٣٦ الأخير ─────────

def test_measured_load_proves_the_finer_key_is_now_needed() -> None:
    """§٢٣ كانت مؤجَّلة «حتى يثبت القياس». والقياس أثبت.

    BTCUSD 26.7% من حمل 1.05 نواة، × ذروة 2 = **53.4% > هدف 50%**.
    """
    from transport.resource_manager import plan_partitions
    out = plan_partitions(MEASURED, symbols=7, logical_partitions=64)
    assert out["heaviest_unit_at_peak"] > POLICY_TARGET
    assert out["groups_required"] == 2
    assert out["unit_after_split"] <= POLICY_TARGET
    assert out["key"] == "Account × Symbol × AnalysisGroup"


def test_sixty_four_partitions_remain_sufficient_after_the_split() -> None:
    """§٢٦: الرقم لا يُعتمد بلا قياس — وهذا يقيسه: 7 × 2 = 14 ≪ 64."""
    from transport.resource_manager import plan_partitions
    out = plan_partitions(MEASURED, symbols=7, logical_partitions=64)
    assert out["partitions_needed"] == 14
    assert out["partitions_sufficient"] is True


def test_a_light_load_keeps_the_simple_ownership_key() -> None:
    """ولا يُوسَّع المفتاح بلا حاجة — §٢٣: «لا يُنفّذ الآن قبل القياس»."""
    from transport.resource_manager import plan_partitions
    light = LoadMeasurement(core_cpu_ratio=0.40, global_ratio=0.10,
                            per_symbol={"EURUSD": 0.5, "GBPUSD": 0.5})
    out = plan_partitions(light, symbols=2, logical_partitions=64)
    assert out["groups_required"] == 1
    assert out["key"] == "Account × Symbol"


def test_too_few_partitions_are_announced_not_silently_accepted() -> None:
    from transport.resource_manager import plan_partitions
    out = plan_partitions(MEASURED, symbols=7, logical_partitions=16)
    assert out["partitions_needed"] == 14
    assert out["partitions_sufficient"] is False, "14 × هامش 2 = 28 > 16"
