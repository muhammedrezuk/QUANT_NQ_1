"""Read-only payload primitives for the low-copy event transport.

These classes intentionally remain ``dict``/``list`` subclasses so existing
atoms keep their current contracts (``isinstance(value, dict)`` continues to
work).  They are built once at ingress and then shared by read-only consumers.
Any attempted mutation fails loudly instead of corrupting another consumer's
view of an event.
"""

from __future__ import annotations

import copy
import datetime
import decimal
import uuid
from collections import deque
from enum import Enum
from typing import Any

#: الأنواع القياديّة في الحمولات: نصّ ورقم ومنطق. فحصٌ واحد بالجدول أسرع
#: من سلسلة `isinstance`، وهو المسار الذي تسلكه الغالبية العظمى من الأوراق.
_PLAIN_LEAF = frozenset({str, int, float, bool, type(None), bytes})

#: أنواع لا تتبدّل، فتمرّ بلا نسخ ولا خطر مشاركة.
_IMMUTABLE_LEAF = (
    datetime.datetime, datetime.date, datetime.time, datetime.timedelta,
    decimal.Decimal, uuid.UUID, frozenset, complex, Enum,
)

#: كم مرّة لزم عزلُ كائنٍ تطبيقيّ متغيّر داخل حمولة.
#:
#: ٢٠٢٦-٠٩-١٠: قبل اليوم كانت `_fast_copy` تنسخ الشجرة كلّها عميقًا قبل
#: التجميد، فأيّ كائن تطبيقيّ داخلها يصل المشترِك **نسخةً**. وبعد إزالة تلك
#: النسخة المزدوجة صار لا بدّ من عزل هذا الكائن وحده هنا، وإلّا تشارك
#: الناشرُ والمشترِكُ كائنًا حيًّا واحدًا.
#:
#: والعدّاد ليس زينة: صفرٌ دائم يعني أنّ الحمولات ورقيّة بحتة كما يفترض
#: العقد، ورقمٌ يكبر يسمّي — بالرقم لا بالظنّ — أنّ ناشرًا يمرّر كائنًا حيًّا
#: في حدث. يُقرأ من `transport_stats`.
isolated_objects = 0


class ReadOnlyDict(dict):
    """A recursively read-only dict compatible with the existing atom API."""

    def __init__(self, source: Any = ()) -> None:
        dict.__init__(self)
        if hasattr(source, "items"):
            items = source.items()
        else:
            items = source
        for key, value in items:
            dict.__setitem__(self, key, freeze_payload(value))

    @staticmethod
    def _readonly() -> None:
        raise TypeError("event payload is read-only; create a derived payload instead")

    __setitem__ = _readonly
    __delitem__ = _readonly
    clear = _readonly
    pop = _readonly
    popitem = _readonly
    setdefault = _readonly
    update = _readonly
    __ior__ = _readonly

    def __reduce__(self):
        return (ReadOnlyDict, (dict(self),))

    def __deepcopy__(self, memo: dict[int, Any]):
        clone = ReadOnlyDict()
        memo[id(self)] = clone
        for key, value in self.items():
            dict.__setitem__(clone, key, freeze_payload(value))
        return clone


class ReadOnlyList(list):
    """A recursively read-only list compatible with list consumers."""

    def __init__(self, source: Any = ()) -> None:
        list.__init__(self, (freeze_payload(value) for value in source))

    @staticmethod
    def _readonly(*_args: Any, **_kwargs: Any) -> None:
        raise TypeError("event payload is read-only; create a derived payload instead")

    __setitem__ = _readonly
    __delitem__ = _readonly
    __iadd__ = _readonly
    __imul__ = _readonly
    append = _readonly
    clear = _readonly
    extend = _readonly
    insert = _readonly
    pop = _readonly
    remove = _readonly
    reverse = _readonly
    sort = _readonly

    def __reduce__(self):
        return (ReadOnlyList, (list(self),))

    def __deepcopy__(self, memo: dict[int, Any]):
        clone = ReadOnlyList()
        memo[id(self)] = clone
        list.extend(clone, (freeze_payload(value) for value in self))
        return clone


def freeze_payload(value: Any) -> Any:
    """Return one recursively immutable view of JSON-like event data.

    الحمولات الطبيعية بنى ورقيّة (dict/list/scalar). و`deque` تتحوّل قائمةً
    للقراءة لأنّها حاوية متغيّرة خارج عقد الأحداث.

    والكائن التطبيقيّ المتغيّر **يُعزَل بنسخة خاصّة به** (`_isolate`) ويُعدّ
    في `isolated_objects` — لأنّ تمريره بالإشارة يجعل الناشر والمشترِك
    يتقاسمان كائنًا حيًّا واحدًا بعد إزالة النسخة العميقة من مسار النشر.
    """
    if type(value) in _PLAIN_LEAF:
        return value
    if isinstance(value, ReadOnlyDict | ReadOnlyList):
        return value
    if isinstance(value, dict):
        return ReadOnlyDict(value)
    if isinstance(value, list):
        return ReadOnlyList(value)
    if isinstance(value, tuple):
        return tuple(freeze_payload(item) for item in value)
    if isinstance(value, deque):
        return ReadOnlyList(value)
    if isinstance(value, set):
        return frozenset(value)
    if isinstance(value, _IMMUTABLE_LEAF):
        return value
    return _isolate(value)


def _isolate(value: Any) -> Any:
    """يعزل كائنًا تطبيقيًّا متغيّرًا — هو وحده، لا الشجرة كلّها."""
    global isolated_objects
    isolated_objects += 1
    try:
        return copy.deepcopy(value)
    except Exception:  # noqa: BLE001 — كائن لا يُنسخ يمرّ كما كان، كما قبل
        return value
