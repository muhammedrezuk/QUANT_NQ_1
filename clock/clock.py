"""Process-wide official clock outside the sealed Core.

Only atom 003 is allowed to call ``accept_sample``. Readers (806/111 and
business atoms) consume the singleton through the read-only module functions.
Timeouts use ``mono``; event timestamps use non-decreasing ``now``.
"""
from __future__ import annotations

import math
import threading
import time
from collections import deque
from dataclasses import dataclass
from typing import Any, Callable

#: سقف نوبات الساعة المحفوظة. محدودٌ عمدًا: تشخيصٌ بلا سقف يصير مسارَ
#: تخزينٍ جديدًا. عشرون تكفي لقراءة نمطٍ خلال يوم، ولا تزن شيئًا.
_EPISODE_CAP = 20

SYNCED = "SYNCED"
STALE = "STALE"
LOCAL_FALLBACK = "LOCAL_FALLBACK"
INVALID = "INVALID"
_WRITER_ID = "003"
_EPSILON = 1e-9

@dataclass(slots=True)
class ClockConfig:
    max_accepted_offset_s: float = 5.0
    max_sample_age_s: float = 30.0
    stale_after_s: float = 900.0
    max_slew_per_second: float = 0.05

class OfficialClock:
    def __init__(self, wall: Callable[[], float] = time.time,
                 monotonic: Callable[[], float] = time.monotonic) -> None:
        self._wall = wall; self._monotonic = monotonic
        self._lock = threading.RLock(); self._config = ClockConfig()
        self._effective_offset = 0.0; self._target_offset = 0.0
        self._last_slew_mono = monotonic(); self._accepted_mono: float | None = None
        self._measured_at: float | None = None; self._last_official: float | None = None
        self._sequence = 0; self._last_rejection = ""; self._backward_clamps = 0
        self._last_sample_id: Any = None
        # أعلى جدارٍ خامٍ رُئي، وعدّاد الإمساك بالانزلاق — انظر `now()`.
        self._max_wall: float | None = None; self._slew_holds = 0
        # ── مسجِّل النوبات — تشخيصٌ خالص، صفر تغيير سلوك ─────────────────
        #
        # ⛔ **ما فرضه، مقيسًا ٢٠٢٦-٠٩-١٦:** `backward_clamps` رقمٌ تراكميّ
        # بلا تاريخ، و`_last_rejection` نصٌّ واحد يُدهس. فحين سُئل «كم دامت
        # كلّ نوبةٍ من الثماني؟» لم يكن في الكود ما يجيب — واستُدلّ عليها من
        # سجلّ الصفقات: خمسة عناقيد وأطولها 276 ثانية.
        #
        # وذلك الاستدلال **حدٌّ أدنى لا قياس**، لسببين:
        #   ١) أوّل رفضٍ ليس بدء النوبة — النوبة تبدأ عند الارتداد.
        #   ٢) نوبةٌ لا يقع فيها أمرٌ **لا تترك أثرًا إطلاقًا** — ولهذا خمسة
        #      عناقيد مقابل ثمانية ارتدادات: ثلاثٌ وقعت في صمت.
        #
        # فيُسجَّل هنا ما لا يتركه أثرٌ خارجيّ: البدء، والانحراف عنده،
        # والنهاية عند أوّل `accept_sample`، والمدّة بينهما.
        #
        # ⚠️ **والحلقة محدودة عمدًا** (`_EPISODE_CAP`): تشخيصٌ بلا سقف يصير
        # مسارَ تخزينٍ جديدًا — وهو العطب نفسه الذي أُغلق في ٥٥٠ اليوم
        # (سجلٌّ لا يُقلَّم بلغ 1.77 م.ب و4.4% من حلقة النواة).
        self._episodes: deque[dict[str, Any]] = deque(maxlen=_EPISODE_CAP)
        self._open_episode: dict[str, Any] | None = None

    def configure(self, *, max_accepted_offset_s: float, max_sample_age_s: float,
                  stale_after_s: float, max_slew_per_second: float) -> None:
        values = (max_accepted_offset_s, max_sample_age_s, stale_after_s, max_slew_per_second)
        if not all(isinstance(v, (int, float)) and math.isfinite(float(v)) and float(v) > 0 for v in values):
            raise ValueError("invalid clock configuration")
        with self._lock:
            self._config = ClockConfig(*(float(v) for v in values))

    def mono(self) -> float: return self._monotonic()

    def _slew_locked(self, mono_now: float) -> None:
        elapsed = max(0.0, mono_now - self._last_slew_mono)
        allowance = elapsed * self._config.max_slew_per_second
        delta = self._target_offset - self._effective_offset
        if abs(delta) <= allowance: self._effective_offset = self._target_offset
        elif allowance > 0: self._effective_offset += math.copysign(allowance, delta)
        self._last_slew_mono = mono_now

    def now(self) -> float:
        with self._lock:
            mono_now = self._monotonic(); self._slew_locked(mono_now)
            wall_now = self._wall()
            candidate = wall_now + self._effective_offset
            if not math.isfinite(candidate):
                self._last_rejection = "NON_FINITE_WALL_CLOCK"
                candidate = self._last_official if self._last_official is not None else 0.0
            # ٢٠٢٦-٠٩-٢٤ (ختم المالك «Nq»): **ليس كلّ نزولٍ للمجموع رجوعًا للجدار.**
            # جدار ويندوز يتقدّم بدرجاتٍ من 15.625 م.ث، والإزاحة تنزلق باستمرار
            # على الساعة الرتيبة. فإذا جاءت عيّنة NTP أصغر من الإزاحة الحاليّة،
            # ولو بـ10 م.ث، نزل `wall + offset` بين درجتين والجدارُ لم يرجع.
            # كان ذلك يُقرأ `BACKWARD_WALL_CLOCK` فتصير الساعة INVALID حتى العيّنة
            # التالية (300ث)، ويردّ 552 كلّ أمرٍ بـ`CLOCK_NOT_SYNCED`. مقيس بعد إقلاع
            # 13:44: 31 رفضًا من 34 وصفر أمرٍ مرّ؛ ومعاد إنتاجه بهذا الملفّ نفسه
            # (0.50⟵0.49 ⇒ INVALID بـ10,373 ارتدادًا في 3ث)؛ و28.45 مليون قراءة
            # لـ`time.time()` بلا خطوةٍ واحدة إلى الوراء.
            # الآن: الوقت المعلَن يُمسَك عند آخر قيمة في الحالين، فيبقى غير متناقص،
            # لكنّ الإبطال لا يقع إلّا إذا كان الجدار الخامُ نفسه دون أعلى ما بلغه.
            # فالرجوع الحقيقيّ يُبطل ويُعدّ كما كان، بما فيه قراءاتُه ما دام متأخّرًا.
            if (self._last_official is not None and candidate < self._last_official
                    and math.isfinite(wall_now) and self._max_wall is not None
                    and wall_now >= self._max_wall):
                self._slew_holds += 1
                candidate = self._last_official
            elif self._last_official is not None and candidate < self._last_official:
                self._backward_clamps += 1
                self._last_rejection = "BACKWARD_WALL_CLOCK"
                # نوبةٌ واحدة لكلّ فترة حجب، لا سطرٌ لكلّ ارتداد: الارتداد
                # قد يتكرّر مرارًا داخل النوبة نفسها، وما يُقاس مدّةُ الحجب
                # من أوّل ارتدادٍ إلى أوّل عيّنةٍ تقبله.
                if self._open_episode is None:
                    self._open_episode = {
                        "reason": "BACKWARD_WALL_CLOCK",
                        "started_wall": self._wall(),
                        "started_mono": mono_now,
                        "offset_at_start_s": self._effective_offset,
                        "backward_at_start": self._backward_clamps,
                        "clamps_in_episode": 0,
                    }
                self._open_episode["clamps_in_episode"] += 1
                candidate = self._last_official
            if math.isfinite(wall_now) and (self._max_wall is None or wall_now > self._max_wall):
                self._max_wall = wall_now
            self._last_official = candidate
            return candidate

    def quality(self) -> str:
        # Refresh the public reading before classifying it so a wall-clock
        # rollback cannot slip through an exposure gate merely because no
        # pulse happened between the rollback and the order.
        self.now()
        with self._lock:
            if self._last_rejection in ("NON_FINITE_WALL_CLOCK", "BACKWARD_WALL_CLOCK"):
                return INVALID
            if self._accepted_mono is None: return LOCAL_FALLBACK
            age = self._monotonic() - self._accepted_mono
            return SYNCED if 0 <= age <= self._config.stale_after_s else STALE

    def accept_sample(self, sample: dict[str, Any], *, writer: str) -> tuple[bool, str]:
        if writer != _WRITER_ID: return False, "WRITER_NOT_AUTHORIZED"
        try:
            offset = float(sample["median_offset_s"]); measured_at = float(sample["measured_at"])
        except (KeyError, TypeError, ValueError): return False, "MALFORMED_SAMPLE"
        if not math.isfinite(offset) or not math.isfinite(measured_at): return False, "NON_FINITE_SAMPLE"
        wall_now = self._wall(); age = wall_now - measured_at
        if age < -1.0 or age > self._config.max_sample_age_s: return False, "STALE_OR_FUTURE_SAMPLE"
        if abs(offset) > self._config.max_accepted_offset_s: return False, "OFFSET_OUTSIDE_BOUND"
        if sample.get("quorum") is not True: return False, "NO_QUORUM"
        sample_id = sample.get("sample_id")
        with self._lock:
            if sample_id is not None and sample_id == self._last_sample_id:
                return False, "DUPLICATE_SAMPLE"
            mono_now = self._monotonic(); self._slew_locked(mono_now)
            self._target_offset = offset; self._accepted_mono = mono_now
            self._measured_at = measured_at; self._last_sample_id = sample_id
            self._sequence += 1; self._last_rejection = ""
            # نهاية النوبة: هذا هو الموضع الوحيد الذي يمسح `_last_rejection`،
            # فهو بالضبط لحظة انقشاع `INVALID`. تُختم النوبة هنا لا في مكانٍ
            # آخر، كي تكون المدّة المقيسة هي مدّة الحجب الفعليّة بعينها.
            episode = self._open_episode
            if episode is not None:
                self._open_episode = None
                episode["ended_wall"] = wall_now
                episode["duration_s"] = round(mono_now - episode["started_mono"], 3)
                episode["offset_at_end_s"] = offset
                episode["sample_id"] = sample_id
                episode.pop("started_mono", None)
                self._episodes.append(episode)
        self.now()  # establish/clamp the public value immediately
        return True, "ACCEPTED"

    def state(self) -> dict[str, Any]:
        with self._lock:
            mono_now = self._monotonic(); self._slew_locked(mono_now)
            age = None if self._accepted_mono is None else max(0.0, mono_now - self._accepted_mono)
            return {"offset_s": self._effective_offset, "target_offset_s": self._target_offset,
                "sync_age_s": age, "quality": self.quality(), "sequence": self._sequence,
                "measured_at": self._measured_at, "monotonic_time": mono_now,
                "backward_clamps": self._backward_clamps,
                "slew_holds": self._slew_holds,
                "last_rejection": self._last_rejection,
                # النوبات المنتهية، وآخرُها أحدثها. والمفتوحة تُعرض منفصلةً
                # كي لا تُقرأ مدّتُها صفرًا وهي لم تنتهِ بعد.
                "episodes": [dict(row) for row in self._episodes],
                "open_episode": (None if self._open_episode is None else {
                    key: value for key, value in self._open_episode.items()
                    if key != "started_mono"}),
                "open_episode_age_s": (None if self._open_episode is None else
                                       round(mono_now - self._open_episode["started_mono"], 3))}

    def reset_for_tests(self) -> None:
        with self._lock:
            self._effective_offset = self._target_offset = 0.0
            self._last_slew_mono = self._monotonic(); self._accepted_mono = None
            self._measured_at = self._last_official = None; self._sequence = 0
            self._last_rejection = ""; self._backward_clamps = 0; self._last_sample_id = None
            self._episodes.clear(); self._open_episode = None
            self._max_wall = None; self._slew_holds = 0

_CLOCK = OfficialClock()
def now() -> float: return _CLOCK.now()
def mono() -> float: return _CLOCK.mono()
def quality() -> str: return _CLOCK.quality()
def state() -> dict[str, Any]: return _CLOCK.state()
def configure(**kwargs) -> None: _CLOCK.configure(**kwargs)
def accept_sample(sample: dict[str, Any], *, writer: str) -> tuple[bool, str]:
    return _CLOCK.accept_sample(sample, writer=writer)


def adopt_owner_sample(sample: dict[str, Any]) -> tuple[bool, str]:
    """يطبّق قرار **مالك الوقت الوحيد** (الذرّة 003) في مفسّرٍ تابع.

    ⛔ لا يُنادى في عمليّة المالك: هناك الذرّة 003 هي التي تنادي
    `accept_sample` مباشرةً، وهذه تكرارٌ لا لزوم له.

    **لماذا وُجدت (٢٠٢٦-٠٩-١٨، بلاغ قسم 450):** النواة الموزّعة تُقلع
    `[[100, 599]]` في مفسّراتٍ مستقلّة، والذرّة 003 رقمها ثلاثة — خارج المدى.
    فساعة كلّ مفسّرٍ تابع بقيت بلا عيّنةٍ قطّ (`LOCAL_FALLBACK`)، والذرّة 552
    تعيش هناك فرفضت **١٥٣ أمرًا من ١٥٣** بـ`CLOCK_NOT_SYNCED`: صفر صفقة منذ
    ١٧:٢٥ من ٢٠٢٦-٠٩-١٧، و٣٬٩٩٠ أمرًا مرفوضًا، ٩٨٫٤٪ منها بالساعة.

    وهذه **ليست مالكًا ثانيًا للوقت**: العيّنة نفسها التي قبلها 003 في الجذر
    تُطبَّق هنا بحرفها. فالقرار واحد، والتطبيق حيث يُقرأ الوقت. ولو اخترنا
    إقلاع 003 في كلّ محرّك لصار في النظام أربعة مالكين يعاينون NTP — وهو
    بالضبط ما يمنعه العقد.
    """
    return _CLOCK.accept_sample(sample, writer=_WRITER_ID)
def reset_for_tests() -> None: _CLOCK.reset_for_tests()
