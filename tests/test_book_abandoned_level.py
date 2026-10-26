# -*- coding: utf-8 -*-
"""دفتر العمق: المستوى الذي هجره الوسيط يُسقط بالزمن، لا بعدد التحديثات وحده.

الحلقة التي أغلقت النظام على نفسه (مقيسة ٢٠٢٦-٠٩-٠٩ 02:0x):
الهجر كان يُقاس بعدد التحديثات (2,000 ≈ خمسون ثانية عند 40 تحديثًا/ث).
وحين يهدأ الرمز ليلًا يتباطأ العدّاد فلا يبلغ العتبة أبدًا ⇒ يخلد المستوى
المهجور ⇒ يبقى الدفتر مقلوبًا ⇒ تُرفض كل تِكّة بـ`crossed_spread` ⇒ ولا حركة
تُنضج العدّاد. القبول رجع من 100% إلى 12.1% و`crossed` يصعد بلا توقّف.

فصار الحكم بالزمن أوّلًا وبالعدّاد ثانيًا — **أيّهما تحقّق كفى**.
"""
from shared.fix_session import Book


class Clock:
    """ساعة يدويّة — القياس لا يُترك لسرعة الجهاز."""

    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def _book(**kw) -> tuple[Book, Clock]:
    clock = Clock()
    return Book(clock=clock, **kw), clock


def _add(book: Book, entry_id: str, side: str, price: float) -> None:
    book.apply("0" if side == "bid" else "1", entry_id, price, 5.0, "0")


def test_live_crossing_is_still_built_not_judged():
    """عقد 624 محفوظ: تقاطع لحظيّ بين مستويين حيّين يبقى في الدفتر."""
    book, _clock = _book()
    _add(book, "b1", "bid", 101.0)
    _add(book, "a1", "ask", 99.0)
    assert book.top() == (101.0, 99.0), "الباني يبني ولا يحكم"
    assert book.crossed_dropped == 0


def test_abandoned_level_drops_by_time_even_when_the_symbol_is_quiet():
    """الرمز الهادئ: تحديثان فقط بعد الهجر — والعدّاد لا يبلغ 2,000 أبدًا."""
    book, clock = _book()
    _add(book, "a1", "ask", 99.0)          # مستوًى سيهجره الوسيط
    clock.advance(300.0)                    # خمس دقائق بلا تحديث عليه
    _add(book, "b1", "bid", 101.0)          # السوق تجاوزه ⇒ تقاطع
    assert book.crossed_dropped == 1, "المهجور بقي رغم خمس دقائق"
    assert book.top() == (101.0, None)
    assert book._seq < 2_000, "الإثبات: العدّاد لم يقترب من عتبته"


def test_time_threshold_is_not_reached_before_it_is_due():
    """أقلّ من العتبة بقليل ⇒ يبقى: لا إسقاط قبل موعده.

    ٢٠٢٦-٠٩-٠٩: العتبة صارت **ثانيتين** لا ثلاثين — دورة حذف الوسيط 0.4ث
    مقيسة، فثلاثون ثانية كانت تترك الدفتر مقلوبًا طوالها والقبول 12%.
    """
    book, clock = _book()
    _add(book, "a1", "ask", 99.0)
    clock.advance(1.9)                      # دون الثانيتين المعلنتين
    _add(book, "b1", "bid", 101.0)
    assert book.crossed_dropped == 0
    assert book.top() == (101.0, 99.0)


def test_threshold_matches_the_venue_delete_cycle():
    """العتبة عيارٌ مشتقّ من قياس لا رقمٌ مزروع — وتُحرَس صراحةً."""
    from shared.fix_session import _CROSSED_STALE_AFTER_S
    assert 1.0 <= _CROSSED_STALE_AFTER_S <= 5.0, (
        "دورة حذف الوسيط 0.4ث مقيسة؛ عتبة خارج [1، 5] إمّا تقتل التقاطع "
        "اللحظيّ أو تترك المهجور يخنق التغذية")


def test_count_threshold_still_works_when_the_market_pours():
    """السوق المنهمر: الزمن لم يمرّ، والعدّاد وحده يكشف الهجر."""
    book, _clock = _book(stale_after=10)
    _add(book, "a1", "ask", 99.0)
    for i in range(12):                     # تحديثات كثيفة في اللحظة نفسها
        _add(book, "b%d" % i, "bid", 90.0 + i * 0.1)
    _add(book, "bx", "bid", 101.0)          # ثمّ تجاوزَ السوقُ الطرفَ المهجور
    assert book.crossed_dropped >= 1
    assert book.top()[1] is None


def test_the_newer_side_survives_the_drop():
    """يُسقط الأقدم وحده — لا الطرفان، ولا الحيّ."""
    book, clock = _book()
    _add(book, "b_old", "bid", 101.0)
    clock.advance(300.0)
    _add(book, "a_new", "ask", 99.0)
    assert book.crossed_dropped == 1
    assert book.top() == (None, 99.0), "الحيّ باقٍ والمهجور ساقط"


def test_delete_and_clear_leave_no_timestamp_behind():
    """لا نموّ خفيّ خلف الدفتر: خرائط العمر تُنظَّف مع الحذف والمسح."""
    book, _clock = _book()
    _add(book, "b1", "bid", 100.0)
    _add(book, "a1", "ask", 101.0)
    book.apply("", "b1", None, None, "2")           # حذف
    assert "b1" not in book._touched and "b1" not in book._seen
    book.clear()
    assert book._touched == {} and book._seen == {}


def test_dropping_repeats_until_the_book_is_sane():
    """مستويان مهجوران متتاليان ⇒ يُسقطان كلاهما، والحلقة تنتهي."""
    book, clock = _book()
    _add(book, "a1", "ask", 98.0)
    _add(book, "a2", "ask", 99.0)
    clock.advance(300.0)
    _add(book, "b1", "bid", 101.0)
    assert book.crossed_dropped == 2
    assert book.top() == (101.0, None)


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
    print("\nدفتر العمق: كل الاختبارات خضراء")
