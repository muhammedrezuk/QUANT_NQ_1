# -*- coding: utf-8 -*-
"""حرّاس مرآة الساعة — مالكٌ واحد، وقرارُه يُطبَّق في كلّ مفسّرٍ يقرأ الوقت.

٢٠٢٦-٠٩-١٨ (بلاغ قسم 450): المحرّكات تُقلع `[[100, 599]]` والذرّة 003 رقمها
ثلاثة — خارج المدى — فبقيت ساعة كلّ مفسّرٍ تابع بلا عيّنة، ورفضت 552 ثلاثةً
وخمسين ومئةَ أمرٍ من مثلها بـ`CLOCK_NOT_SYNCED`. صفر صفقة منذ ١٧:٢٥.
"""
from __future__ import annotations

import time

import pytest

import clock


@pytest.fixture(autouse=True)
def _fresh_clock():
    clock.reset_for_tests()
    yield
    clock.reset_for_tests()


def _sample(offset: float = 0.01, sample_id: str = "s1") -> dict:
    return {"median_offset_s": offset, "measured_at": time.time(),
            "quorum": True, "sample_id": sample_id}


def test_without_a_sample_the_clock_is_not_synced() -> None:
    """هذه هي الحالة التي عاشها كلّ محرّك رمزٍ — وسببُ رفض كلّ أمر."""
    assert clock.quality() != clock.SYNCED


def test_adopting_the_owner_sample_makes_a_follower_synced() -> None:
    accepted, reason = clock.adopt_owner_sample(_sample())
    assert accepted, reason
    assert clock.quality() == clock.SYNCED


def test_adoption_is_identical_to_what_atom_003_does() -> None:
    """ليست بابًا خلفيًّا: النتيجة نفسها التي ينتجها المالك بحرفها."""
    accepted_owner, _ = clock.accept_sample(_sample(0.02, "a"), writer="003")
    state_owner = clock.state()
    clock.reset_for_tests()
    accepted_mirror, _ = clock.adopt_owner_sample(_sample(0.02, "a"))
    state_mirror = clock.state()
    assert accepted_owner is accepted_mirror is True
    assert state_owner["target_offset_s"] == state_mirror["target_offset_s"]
    assert state_owner["quality"] == state_mirror["quality"]


def test_a_foreign_writer_is_still_refused() -> None:
    """حارس المالك الواحد لم يُفتَح لأحد."""
    accepted, reason = clock.accept_sample(_sample(), writer="552")
    assert accepted is False and reason == "WRITER_NOT_AUTHORIZED"


def test_a_malformed_or_quorumless_sample_is_refused_by_the_mirror_too() -> None:
    assert clock.adopt_owner_sample({"nonsense": 1})[0] is False
    no_quorum = {**_sample(), "quorum": False}
    assert clock.adopt_owner_sample(no_quorum) == (False, "NO_QUORUM")
    assert clock.quality() != clock.SYNCED


def test_the_same_sample_twice_is_a_duplicate_not_a_second_decision() -> None:
    assert clock.adopt_owner_sample(_sample(0.01, "x"))[0] is True
    assert clock.adopt_owner_sample(_sample(0.01, "x")) == (False, "DUPLICATE_SAMPLE")


def test_the_symbol_engine_declares_the_clock_subscription() -> None:
    """الوصلة نفسها — كي لا يعود المحرّك يُقلع بلا مستهلكٍ للعيّنة."""
    from pathlib import Path
    source = (Path(__file__).resolve().parents[1]
              / "engine" / "symbol_host.py").read_text(encoding="utf-8")
    assert "time.ntp.samples.state" in source, "المحرّك لا يشترك بعيّنة الساعة"
    assert "adopt_owner_sample" in source
    assert 'subscriber="003"' in source
