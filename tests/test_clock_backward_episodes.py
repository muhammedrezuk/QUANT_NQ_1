"""نوبات ارتداد ساعة الجدار — تشخيصٌ يُقاس، وسلوكٌ لا يُمَسّ.

**ختم المالك ٢٠٢٦-٠٩-١٦:** «ازرع المسجّل، لكن تشخيصيًا فقط… المسجّل نعم،
تغيير السلوك لا.»

## ⛔ ما فرض المسجِّل

`CLOCK_NOT_SYNCED` ثاني أكبر أسباب رفض الأوامر (15.1%). وتتبّعُه انتهى إلى
`clock.py`: ارتدادٌ في ساعة الجدار يكتب `_last_rejection`، و`quality()`
تُرجع `INVALID` ما دام مكتوبًا، **ولا يُمسح إلّا بـ`accept_sample`** —
ودورة العيّنات ٣٠٠ ثانية.

ولمّا سُئل «كم دامت كلّ نوبة؟» لم يكن في الكود ما يجيب: `backward_clamps`
رقمٌ تراكميّ بلا تاريخ، و`_last_rejection` نصٌّ واحد يُدهس. فاستُدلّ عليها
من سجلّ الصفقات — خمسة عناقيد، أطولها ٢٧٦ ثانية — وذاك **حدٌّ أدنى لا
قياس**:

    ١) أوّل رفضٍ ليس بدء النوبة؛ النوبة تبدأ عند الارتداد.
    ٢) نوبةٌ لا يقع فيها أمرٌ **لا تترك أثرًا** — ولهذا خمسة عناقيد مقابل
       ثمانية ارتدادات: ثلاثٌ وقعت في صمت.

## والعقد الذي خُتم

    BACKWARD_WALL_CLOCK
        ↓  يُسجَّل: البدء · الانحراف · أوّل accept_sample · المدّة
        ↓  ولا يُغيَّر: quality() · ٥٥٢ · شرط فتح التعرّض · event_id

والسجلّ **محدود** — تشخيصٌ بلا سقف يصير مسار تخزينٍ جديدًا، وهو العطب
نفسه الذي أُغلق في ٥٥٠ اليوم (سجلٌّ لا يُقلَّم بلغ ١٫٧٧ م.ب).
"""

from __future__ import annotations

import pytest

import clock
from clock.clock import _EPISODE_CAP, OfficialClock


class _Wall:
    """ساعة جدارٍ تُقاد — الارتداد يُحقن ولا يُنتظر."""

    def __init__(self, start: float = 1_000_000.0) -> None:
        self.value = start

    def __call__(self) -> float:
        return self.value

    def step(self, delta: float) -> None:
        self.value += delta


class _Mono:
    def __init__(self, start: float = 500.0) -> None:
        self.value = start

    def __call__(self) -> float:
        return self.value

    def advance(self, delta: float) -> None:
        self.value += delta


def _clock() -> tuple[OfficialClock, _Wall, _Mono]:
    wall, mono = _Wall(), _Mono()
    instance = OfficialClock(wall=wall, monotonic=mono)
    instance.configure(max_accepted_offset_s=5.0, max_sample_age_s=60.0,
                       stale_after_s=900.0, max_slew_per_second=0.05)
    return instance, wall, mono


def _sample(instance: OfficialClock, wall: _Wall, offset: float = 0.0,
            sample_id: str = "s1") -> tuple[bool, str]:
    return instance.accept_sample(
        {"median_offset_s": offset, "measured_at": wall.value,
         "sample_id": sample_id, "quorum": True}, writer="003")


# ══ السلسلة الحاسمة التي فرضها المالك ═══════════════════════════════════════

def test_an_injected_rollback_is_recorded_from_start_to_sample() -> None:
    """⛔ الاختبار الذي فرضه الحكم — السلسلة كاملةً لا وجود السجلّ.

        ارتداد محقون ⟶ بداية مسجَّلة ⟶ INVALID ⟶ accept_sample
                     ⟶ نهاية مسجَّلة ⟶ duration = end − start
    """
    instance, wall, mono = _clock()
    assert _sample(instance, wall, 0.0, "s0")[0] is True
    mono.advance(1.0)
    instance.now()
    assert instance.quality() == clock.SYNCED

    # ← الارتداد
    wall.step(-2.0)
    mono.advance(0.5)
    instance.now()
    assert instance.quality() == clock.INVALID, "الارتداد لم يُبطل الجودة"

    opened = instance.state()["open_episode"]
    assert opened is not None, "لم تُفتح نوبة عند الارتداد"
    assert opened["reason"] == "BACKWARD_WALL_CLOCK"
    assert instance.state()["episodes"] == [], "خُتمت النوبة قبل أوانها"

    # ← العيّنة التالية بعد 37 ثانية
    mono.advance(37.0)
    wall.step(40.0)
    assert _sample(instance, wall, 0.01, "s1")[0] is True
    assert instance.quality() == clock.SYNCED, "لم تنقشع بعد العيّنة"

    state = instance.state()
    assert state["open_episode"] is None, "بقيت النوبة مفتوحة بعد العيّنة"
    assert len(state["episodes"]) == 1
    episode = state["episodes"][0]
    # 37.0 لا 37.5: النوبة تبدأ عند الارتداد (mono 501.5) لا قبله. حسبتُ
    # نصف الثانية مرّتين في أوّل كتابة، فصحّح الاختبارُ حسابي لا العكس.
    assert episode["duration_s"] == pytest.approx(37.0, abs=0.01), episode
    assert episode["ended_wall"] > episode["started_wall"]
    assert episode["sample_id"] == "s1"
    assert "offset_at_start_s" in episode and "offset_at_end_s" in episode


def test_the_open_episode_reports_its_age_not_a_zero_duration() -> None:
    """نوبةٌ لم تنتهِ لا تُقرأ صفرًا — وإلّا بدا الحجب بلا مدّة."""
    instance, wall, mono = _clock()
    _sample(instance, wall, 0.0, "s0")
    wall.step(-1.0)
    instance.now()
    mono.advance(12.0)
    state = instance.state()
    assert state["open_episode"] is not None
    assert state["open_episode_age_s"] == pytest.approx(12.0, abs=0.01)
    assert all("duration_s" not in row for row in state["episodes"])


def test_repeated_rollbacks_inside_one_blackout_stay_one_episode() -> None:
    """ما يُقاس مدّة الحجب لا عدد الارتدادات — فالنوبة واحدة."""
    instance, wall, mono = _clock()
    _sample(instance, wall, 0.0, "s0")
    for _ in range(5):
        wall.step(-0.5)
        mono.advance(1.0)
        instance.now()
    state = instance.state()
    # ⚠️ **وسلوكٌ علّمنيه الاختبار:** ما دام الجدار متأخّرًا فكلّ **قراءة**
    # تُثبِّت أيضًا — و`state()` تقرأ. فالعدد ≥ المحقون لا يساويه، وهو صادق:
    # العدّاد يعدّ التثبيتات لا الأحداث الخارجيّة.
    assert state["open_episode"]["clamps_in_episode"] >= 5
    assert state["episodes"] == []

    mono.advance(3.0)
    wall.step(20.0)
    _sample(instance, wall, 0.0, "s1")
    episodes = instance.state()["episodes"]
    assert len(episodes) == 1, "خمسة ارتدادات أعطت أكثر من نوبة"
    assert episodes[0]["clamps_in_episode"] >= 5
    # 7.0 لا 8.0: النوبة تبدأ عند **أوّل** تثبيت (mono 501) لا قبل الحلقة.
    # أخطأتُ الحساب مرّتين في هذا الملفّ، وفي المرّتين كان الكود هو الصادق.
    assert episodes[0]["duration_s"] == pytest.approx(7.0, abs=0.01)


def test_a_read_while_the_wall_is_behind_clamps_too() -> None:
    """السلوك الذي كشفه سقوطُ اختباري — يُثبَّت كي لا يُقرأ مفاجأةً.

    ما دام الجدار متأخّرًا عن الوقت المعلَن، فكلّ نداءِ `now()` — ومنه ما
    تناديه `state()` و`quality()` — يُثبِّت ويزيد العدّاد. فالعدد يصف
    **التثبيتات** لا قفزات الساعة، ولا يُقرأ «كم مرّة ارتدّت الساعة».
    """
    instance, wall, mono = _clock()
    _sample(instance, wall, 0.0, "s0")
    wall.step(-3.0)
    mono.advance(0.1)
    instance.now()
    first = instance.state()["backward_clamps"]
    for _ in range(4):
        mono.advance(0.1)
        instance.now()
    assert instance.state()["backward_clamps"] > first, (
        "قراءةٌ والجدار متأخّر لم تُثبِّت — تغيّر سلوك الحماية")


def test_a_silent_episode_is_recorded_even_with_no_orders() -> None:
    """⛔ هذا هو ما لم يكن يُقاس: ثلاث نوبات وقعت بلا أمرٍ فلم تترك أثرًا."""
    instance, wall, mono = _clock()
    _sample(instance, wall, 0.0, "s0")
    wall.step(-0.2)
    mono.advance(0.1)
    instance.now()                       # لا أمر · لا رفض · لا سطر في أيّ سجلّ
    mono.advance(4.0)
    wall.step(10.0)
    _sample(instance, wall, 0.0, "s1")
    assert len(instance.state()["episodes"]) == 1, "النوبة الصامتة ضاعت"


# ══ الحدّ: تشخيصٌ لا يصير مخزنًا ════════════════════════════════════════════

def test_the_episode_log_is_capped() -> None:
    """⚠️ تشخيصٌ بلا سقف يصير مسار تخزينٍ جديدًا — وهو عطب ٥٥٠ نفسه."""
    instance, wall, mono = _clock()
    _sample(instance, wall, 0.0, "s0")
    for index in range(_EPISODE_CAP * 3):
        wall.step(-0.1)
        mono.advance(0.1)
        instance.now()
        mono.advance(0.1)
        wall.step(5.0)
        _sample(instance, wall, 0.0, "s%d" % index)
    assert len(instance.state()["episodes"]) == _EPISODE_CAP


def test_the_newest_episode_is_last() -> None:
    """ترتيبٌ معلَن: آخر الصفوف أحدثها — وإلّا قُرئ القديم حاضرًا."""
    instance, wall, mono = _clock()
    _sample(instance, wall, 0.0, "s0")
    for index in range(3):
        wall.step(-0.1)
        mono.advance(0.1)
        instance.now()
        mono.advance(1.0 + index)
        wall.step(5.0)
        _sample(instance, wall, 0.0, "n%d" % index)
    episodes = instance.state()["episodes"]
    assert [row["sample_id"] for row in episodes] == ["n0", "n1", "n2"]
    assert episodes[-1]["duration_s"] > episodes[0]["duration_s"]


# ══ ⛔ وما لم يتغيّر — نصّ الحكم ════════════════════════════════════════════

def test_quality_is_untouched_by_the_recorder() -> None:
    """السلوك لا يُمَسّ: المسجِّل يقرأ ولا يقرّر.

    `INVALID` تبقى `INVALID` حتّى العيّنة، ولا يجعلها المسجِّل تنقشع مبكّرًا
    ولا يُطيلها. هذا هو معنى «تشخيصيًّا فقط» بالضبط.
    """
    instance, wall, mono = _clock()
    _sample(instance, wall, 0.0, "s0")
    wall.step(-1.0)
    instance.now()
    for _ in range(10):
        mono.advance(30.0)
        assert instance.quality() == clock.INVALID, "المسجِّل قصّر مدّة الحجب"
    mono.advance(1.0)
    wall.step(50.0)
    _sample(instance, wall, 0.0, "s1")
    assert instance.quality() == clock.SYNCED, "المسجِّل أطال مدّة الحجب"


def test_a_clean_clock_records_nothing() -> None:
    """بلا ارتدادٍ لا نوبة — ولا كلفة على المسار السليم."""
    instance, wall, mono = _clock()
    for index in range(5):
        mono.advance(10.0)
        wall.step(10.0)
        _sample(instance, wall, 0.0, "c%d" % index)
        instance.now()
    state = instance.state()
    assert state["episodes"] == []
    assert state["open_episode"] is None
    assert state["backward_clamps"] == 0


def test_the_clamp_still_protects_the_reading() -> None:
    """والحماية نفسها لم تُمَسّ: الوقت المعلَن لا يرتدّ."""
    instance, wall, mono = _clock()
    _sample(instance, wall, 0.0, "s0")
    mono.advance(1.0)
    before = instance.now()
    wall.step(-5.0)
    mono.advance(0.1)
    after = instance.now()
    assert after >= before, "الوقت المعلَن ارتدّ — الحماية سقطت"
