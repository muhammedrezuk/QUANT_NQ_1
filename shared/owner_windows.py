"""نوافذ المالك الحرجة للناسداك — طبقة الوقت (ورقة النقاش ٢٠٢٦-١٠-٠٧، ٤-د/٢ و٤-س-٢).

المالك: «نحن على الناسداك: الفترات الحرجة — ذروة لندن وافتتاح أمريكا؛ ما معقول ناخد صفقة ونحن
بسوق آسيا». والساعات بالتوقيت المحلّيّ للمدينتين لا بغرينتش الثابت — فالثابت يخطئ ساعةً نصف السنة
(ذرّة 412 قبل ٢٠٢٦-١٠-٠٧ كانت لندن 7 ونيويورك 13 غرينتش طول السنة).

  ذروة لندن      08:00–11:00 بتوقيت لندن        (london_peak)
  افتتاح أمريكا   09:30–12:00 بتوقيت نيويورك     (ny_open)
  أيّام العمل وحدها (الاثنين–الجمعة بتوقيت كلّ مدينة).

التوقيت الصيفيّ بقاعدتيه الرسميّتين مكتوبتين هنا — بايثون المشروع لا يحمل قاعدة المناطق الزمنيّة
(`zoneinfo` بلا `tzdata`)، فلا اعتماد خارجيّ:
  أوروبا : من آخر أحدٍ في آذار 01:00 غرينتش إلى آخر أحدٍ في تشرين الأوّل 01:00 غرينتش  (لندن +1)
  أمريكا : من ثاني أحدٍ في آذار 02:00 محلّيّ (07:00 غرينتش) إلى أوّل أحدٍ في تشرين الثاني
           02:00 محلّيّ (06:00 غرينتش)                                                (نيويورك −4، وإلّا −5)

دالّةٌ واحدة يقرؤها الحيّ (412 ⟵ البطاقة 414) والقياس (إعادة البطاقة على التاريخ) — فلا يختلف تعريفان.
"""
from __future__ import annotations

import calendar
import dataclasses
import time
from datetime import datetime, timedelta, timezone

WINDOW_LONDON_PEAK = "london_peak"
WINDOW_NY_OPEN = "ny_open"


def _sunday(year: int, month: int, nth: int) -> int:
    """يوم الشهر لأحدٍ بترتيبه (nth ≥ 1) أو الأخير (nth = −1)."""
    days = calendar.monthrange(year, month)[1]
    sundays = [d for d in range(1, days + 1) if calendar.weekday(year, month, d) == 6]
    return sundays[nth - 1] if nth > 0 else sundays[-1]


def _utc(year: int, month: int, day: int, hour: int) -> float:
    return calendar.timegm((year, month, day, hour, 0, 0))


def london_offset_h(epoch_s: float) -> int:
    year = datetime.fromtimestamp(epoch_s, timezone.utc).year
    start = _utc(year, 3, _sunday(year, 3, -1), 1)
    end = _utc(year, 10, _sunday(year, 10, -1), 1)
    return 1 if start <= epoch_s < end else 0


def new_york_offset_h(epoch_s: float) -> int:
    year = datetime.fromtimestamp(epoch_s, timezone.utc).year
    start = _utc(year, 3, _sunday(year, 3, 2), 7)
    end = _utc(year, 11, _sunday(year, 11, 1), 6)
    return -4 if start <= epoch_s < end else -5


def broker_day_offset_s(epoch_s: float) -> int:
    """فرق ساعة يوم الوسيط عن غرينتش بالثواني — يومٌ يُغلق مع إغلاق نيويورك 17:00 (ساعة الخادم = نيويورك + 7).

    ٢٠٢٦-١٠-٠٨ (تدقيق الإغلاق — «الحيّ = المقيس»): قاعدة تاريخ سي‑تريدر تبني الأربع ساعات واليوم على هذه
    الساعة (تبدأ 01/05/09… غرينتش صيفًا، و02/06… شتاءً؛ واليوم 21:00/22:00)، وعليها قيست البطاقة 414 وعليها
    شارت المالك. +3 ساعات صيفًا و+2 شتاءً."""
    return (new_york_offset_h(epoch_s) + 7) * 3600


#: (اسم النافذة، دالّة فرق التوقيت، البداية بالدقائق المحلّيّة، النهاية)
WINDOWS = (
    (WINDOW_LONDON_PEAK, london_offset_h, 8 * 60, 11 * 60),
    (WINDOW_NY_OPEN, new_york_offset_h, 9 * 60 + 30, 12 * 60),
)


def local_time(epoch_s: float, offset_fn) -> datetime:
    return datetime.fromtimestamp(float(epoch_s), timezone.utc) + timedelta(hours=offset_fn(float(epoch_s)))


def owner_window(epoch_s: float) -> str | None:
    """اسم نافذة المالك التي تقع فيها اللحظة (ثوانٍ يونكس بغرينتش) — أو لا شيء."""
    for name, offset_fn, start, end in WINDOWS:
        local = local_time(epoch_s, offset_fn)
        if local.weekday() >= 5:
            continue
        minute = local.hour * 60 + local.minute
        if start <= minute < end:
            return name
    return None


# ── نافذة الصيانة اليوميّة ──────────────────────────────────────────────────────
# ٢٠٢٦-١٠-٠٩ (ختم المالك «NQ» — الصيانة في استراحة السوق): أمر المالك «لازم يكون توقيت عند فترة
# إغلاق السوق من ساعة — مثال 12 إلى ساعة 1 — هون النظام لازم ينظّف، يريّح، يوقّف ويجهّز ليوم جديد».
#
# المقيس قبله: نبض اليوم (806) يقع على منتصف ليل غرينتش = 03:00 بتوقيت الجهاز صيفًا، فكانت الصيانة
# كلّها (نسخ 800 · تدوير الأرشيف 714 وضغطه · تشذيب المخازن 701…718 · 802 · 803) تجري والسوق مفتوح،
# وتجمّدت حلقة المنصّة 25–63 ث مرّاتٍ كلّ ليلة من ٠٥ إلى ٠٨ تشرين الأوّل بين 03:00 و03:17.
#
# الاستراحة اليوميّة عند الوسيط 17:00–18:00 بتوقيت نيويورك = 00:00–01:00 بتوقيت الجهاز صيفًا و01:00–02:00
# شتاءً، تتحرّك وحدها بقاعدة نيويورك أعلاه (`new_york_offset_h`). والجمعة 17:00 نيويورك حتّى الأحد 18:00
# نافذةٌ واحدة: صيانة الجمعة في عطلة الأسبوع. ومفتاح كلّ نافذة تاريخُ نيويورك ليوم افتتاحها، فـ«مرّة
# واحدة في كلّ نافذة» تعني مرّةً في اليوم، ومرّةً واحدة للعطلة كلّها.
#
# هذا المكان الوحيد الذي يُعرَّف فيه وقت الصيانة؛ كلّ مهمّة صيانة تقرؤه عبر `MaintenanceGate`.
MAINTENANCE_OPEN_NY_MIN = 17 * 60
MAINTENANCE_CLOSE_NY_MIN = 18 * 60
MAINTENANCE_INTERVAL_S = 86_400.0
#: نافذتان يوميّتان تبعدان 24 ساعة بتوقيت نيويورك، والمهمّة قد تبدأ في أيّ دقيقة من ساعة النافذة
#: (أو بعد إقلاعٍ داخلها)؛ فيُقبل من عمر آخر نجاح ما نقص عن اليوم بساعتين — وإلّا قفزت المهمّة يومًا.
MAINTENANCE_RERUN_SLACK_S = 2 * 3600.0
_MINUTES_PER_HOUR = 60
_SECONDS_PER_HOUR = 3600
_FRIDAY, _SATURDAY, _SUNDAY = 4, 5, 6
#: يومان من الجمعة إلى الأحد — طرفا نافذة العطلة.
_WEEKEND_SPAN_DAYS = 2
#: يُبحث عن النافذة من قبل يومين (العطلة الجارية) إلى أسبوعٍ قادم.
_SEARCH_BACK_DAYS = 2
_SEARCH_AHEAD_DAYS = 8


def _ny_epoch(day, minute: int) -> float:
    """ساعة حائط نيويورك (يوم + دقيقة) ⟵ ثوانٍ يونكس. 17:00 و18:00 لا تقعان في ساعة التحويل أبدًا."""
    naive = calendar.timegm((day.year, day.month, day.day,
                             minute // _MINUTES_PER_HOUR, minute % _MINUTES_PER_HOUR, 0))
    # ما قبل 1970 (أيّام البحث الخلفيّ لطوابع الاختبار الصغيرة) شتاءٌ: يُقرأ فرقُ أوّل ثانية، وويندوز
    # يرفض الطابع السالب.
    epoch = naive - new_york_offset_h(max(naive, 0)) * _SECONDS_PER_HOUR
    return float(naive - new_york_offset_h(max(epoch, 0)) * _SECONDS_PER_HOUR)


def maintenance_window_bounds(epoch_s: float) -> tuple[float, float, str]:
    """(بداية، نهاية، مفتاح) نافذة الصيانة الجارية — أو القادمة إن كانت اللحظة خارجها."""
    stamp = float(epoch_s)
    today = local_time(stamp, new_york_offset_h).date()
    for shift in range(-_SEARCH_BACK_DAYS, _SEARCH_AHEAD_DAYS):
        day = today + timedelta(days=shift)
        weekday = day.weekday()
        if weekday in (_SATURDAY, _SUNDAY):
            continue                       # أيّام العطلة داخل نافذة جمعتها
        close_day = day + timedelta(days=_WEEKEND_SPAN_DAYS) if weekday == _FRIDAY else day
        start = _ny_epoch(day, MAINTENANCE_OPEN_NY_MIN)
        end = _ny_epoch(close_day, MAINTENANCE_CLOSE_NY_MIN)
        if stamp < end:
            return start, end, day.isoformat()
    raise ValueError("no maintenance window ahead")    # لا يقع: في كلّ أسبوعٍ خمس نوافذ


def maintenance_window(epoch_s: float) -> str | None:
    """مفتاح نافذة الصيانة التي تقع فيها اللحظة (تاريخ نيويورك ليوم افتتاحها) — أو لا شيء."""
    start, end, key = maintenance_window_bounds(epoch_s)
    return key if start <= float(epoch_s) < end else None


def _device_clock(epoch_s: float | None) -> str:
    """وقتٌ يقرؤه المالك بساعة جهازه (عرضٌ فقط؛ الحكم كلّه بنيويورك أعلاه)."""
    if epoch_s is None:
        return "—"
    return time.strftime("%m-%d %H:%M", time.localtime(float(epoch_s)))


class MaintenanceGate:
    """حارس «مرّةٌ واحدة في كلّ نافذة صيانة» لمهمّة صيانة، وما يُعلَن عنها في صحّة ذرّتها.

    `due` يسأل ولا يغيّر؛ و`mark` يُنادى بعد أن تُجدوَل المهمّة فعلًا — فمهمّةٌ لم تُجدوَل (سابقتها
    ما زالت تجري) تُسأل ثانيةً في النبضة التالية داخل النافذة نفسها بدل أن تضيع ليومها.
    """

    def __init__(self) -> None:
        self.last_key: str | None = None
        self.last_at: float | None = None
        #: نداءاتٌ وقعت خارج النافذة فأُمسكت (نبضة اليوم وما يشبهها) — عدٌّ معلن لا صمت.
        self.held_outside = 0
        self._bounds: tuple[float, float, str] | None = None
        self._bounds_from: float | None = None
        self._seen: float | None = None

    def _window(self, stamp: float) -> tuple[float, float, str]:
        """حدود النافذة محفوظةً بين النبضات: تُحسب مرّةً لكلّ نافذة لا كلّ ثانية."""
        bounds, since = self._bounds, self._bounds_from
        if bounds is None or since is None or not since <= stamp < bounds[1]:
            bounds = self._bounds = maintenance_window_bounds(stamp)
            self._bounds_from = stamp
        return bounds

    def due(self, now: float | None, last_success: float | None = None,
            interval_s: float = MAINTENANCE_INTERVAL_S, *, held: bool = False) -> str | None:
        """مفتاح النافذة إن كانت المهمّة مستحقّةً الآن — وإلّا لا شيء. يسأل ولا يجدول.

        `held=True` لنداءٍ كان يُشغّل المهمّة قبل اليوم (نبضة اليوم): إن وقع خارج النافذة عُدّ.
        """
        if now is None:
            return None
        stamp = float(now)
        self._seen = stamp
        start, end, key = self._window(stamp)
        if not start <= stamp < end:
            self.held_outside += 1 if held else 0
            return None
        if key == self.last_key:
            return None
        if last_success is not None:
            age = stamp - float(last_success)
            if 0 <= age < interval_s - MAINTENANCE_RERUN_SLACK_S:
                self.last_key = key        # صِينت قبل قليل (إقلاعٌ داخل النافذة): لا تكرار فيها
                return None
        return key

    def mark(self, key: str, now: float) -> None:
        self.last_key, self.last_at = key, float(now)

    def describe(self) -> str:
        """«صيانة: آخرها … · القادمة …» بساعة الجهاز — يُلحق برسالة الصحّة (التفاصيل تُقصّ عند النواة)."""
        upcoming = "—"
        if self._seen is not None:
            start, end, key = self._window(self._seen)
            if key == self.last_key:
                start, end, _ = maintenance_window_bounds(end)
            upcoming = "%s–%s" % (_device_clock(start), _device_clock(end)[-5:])
        return "صيانة: آخرها %s · القادمة %s" % (_device_clock(self.last_at), upcoming)

    def announce(self, status):
        """صحّة الذرّة كما هي، ومعها «متى صانت آخر مرّة ومتى القادمة» ملحقًا برسالتها."""
        return dataclasses.replace(
            status, message="%s · %s" % (status.message or "", self.describe()))

    def snapshot(self) -> dict:
        """وقت آخر صيانة وحده يعبر الإقلاع — للإعلان. ومفتاح النافذة لا يعبر عمدًا: عقد المالك
        (٢٠٢٦-٠٨-١٦) «فشلت في المنتصف ⟸ يعيد المحاولة عند الإقلاع التالي». فالتكرار بعد نجاحٍ يمنعه
        عمرُ آخر نجاح الذي تحفظه الذرّة (`due(…, last_success)`)، والتشغيلةُ المقتولة تُعاد."""
        return {"maintenance_at": self.last_at}

    def restore(self, state: dict | None) -> None:
        if not isinstance(state, dict):
            return
        try:
            at = state.get("maintenance_at")
            self.last_at = float(at) if at is not None else None
        except (TypeError, ValueError):
            self.last_at = None
