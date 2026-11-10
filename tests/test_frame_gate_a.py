# -*- coding: utf-8 -*-
"""§5 / Gate A — حرّاس إطار الدفعة الثنائيّ.

القاعدة الحاكمة (ورقة المالك §١١ و§٢٢): **فقدُ مدخلٍ = فشلُ تكافؤ.** فلا
يكفي أن يعمل الإطار في الحالة الطبيعيّة؛ يجب أن **يرفض** التلف بدل أن
يُصلحه صامتًا، وأن يكشف كلّ تغييرٍ متعمَّد في الترتيب أو الهويّة أو الحمولة.
"""
from __future__ import annotations

import json

import pytest

from hot import frame


def _rows(count: int = 40, start: int = 0):
    out = []
    for k in range(count):
        out.append((start + k, "decision.room.state" if k % 3 else
                    "market.tick.validated",
                    {"symbol": "XAUUSD" if k % 2 else "EURUSD",
                     "trace_id": "t-%d" % k, "price": 2650.25 + k * 0.01,
                     "flag": bool(k % 2), "none": None,
                     "nested": {"a": [1, 2, {"ب": "قيمةٌ عربيّة"}]}}))
    return out


# ── الأمانة ──────────────────────────────────────────────────────────────

def test_a_round_trip_returns_the_input_exactly():
    rows = _rows(300)
    back = frame.round_trip(rows, max_records=64)
    assert back == rows
    assert frame.identical(rows, back)["identical"] is True


def test_arabic_floats_none_and_nesting_survive():
    """الحمولة تعود كما دخلت — لا تحويلَ ولا تسويةً صامتة."""
    rows = [(0, "market.tick.validated",
             {"نصّ": "عربيّةٌ بتشكيل", "f": 1.0000001, "z": 0.0,
              "neg": -3.5, "big": 9007199254740993, "n": None,
              "t": True, "list": [None, "", 0, False]})]
    _header, back = frame.decode(frame.encode(rows))
    assert back == rows
    assert back[0][2]["big"] == 9007199254740993
    assert back[0][2]["n"] is None and back[0][2]["t"] is True


def test_the_header_carries_the_batch_bounds():
    rows = _rows(10, start=700)
    header, _back = frame.decode(frame.encode(rows))
    assert header["count"] == 10
    assert header["first_i"] == 700
    assert header["last_i"] == 709
    assert header["names"] == 2


def test_the_name_is_written_once_not_per_record():
    """اسمُ الحدث في جدول — وهو نصفُ سببِ وجود الدفعة."""
    one = frame.encode([(0, "decision.room.state", {"a": 1})])
    many = frame.encode([(i, "decision.room.state", {"a": 1}) for i in range(200)])
    assert len(many) < len(one) * 30, "الاسم يُكرَّر مع كلّ واقعة"


def test_batches_never_reorder_or_drop():
    rows = _rows(1000)
    chunks = list(frame.batches(rows, max_records=128))
    assert sum(len(c) for c in chunks) == len(rows)
    flat = [row for chunk in chunks for row in chunk]
    assert flat == rows


# ── الرفض: التلف يُرفَض ولا يُصلَح ───────────────────────────────────────

def test_an_empty_batch_is_refused():
    with pytest.raises(frame.FrameError):
        frame.encode([])


def test_a_wrong_magic_is_refused():
    blob = bytearray(frame.encode(_rows(5)))
    blob[0:4] = b"XXXX"
    with pytest.raises(frame.FrameError):
        frame.decode(bytes(blob))


def test_a_truncated_frame_is_refused():
    blob = frame.encode(_rows(20))
    with pytest.raises(frame.FrameError):
        frame.decode(blob[:-5])
    with pytest.raises(frame.FrameError):
        frame.decode(blob[:10])


def test_a_flipped_byte_in_the_body_is_caught_by_the_checksum():
    """⛔ التلف الصامت أخطر من التلف الصاخب — البصمة تمنعه."""
    blob = bytearray(frame.encode(_rows(30), compress=False))
    at = frame.HEADER_SIZE + 25
    blob[at] ^= 0x40
    with pytest.raises(frame.FrameError) as err:
        frame.decode(bytes(blob))
    assert "بصمة" in str(err.value) or "تالف" in str(err.value)


def test_a_flipped_byte_in_a_compressed_body_is_caught():
    blob = bytearray(frame.encode(_rows(200), compress=True))
    blob[frame.HEADER_SIZE + 12] ^= 0xFF
    with pytest.raises(frame.FrameError):
        frame.decode(bytes(blob))


def test_an_unknown_version_is_refused():
    blob = bytearray(frame.encode(_rows(5)))
    blob[4:6] = (99).to_bytes(2, "little")
    with pytest.raises(frame.FrameError):
        frame.decode(bytes(blob))


def test_a_negative_index_is_refused():
    with pytest.raises(frame.FrameError):
        frame.encode([(-1, "x", {})])


# ── المقارِن: يكشف كلّ تغييرٍ متعمَّد (§٢١) ──────────────────────────────

def test_the_comparator_catches_a_dropped_record():
    rows = _rows(50)
    report = frame.identical(rows, rows[:-1])
    assert report["identical"] is False
    assert report["count_match"] is False


def test_the_comparator_catches_an_extra_record():
    rows = _rows(50)
    report = frame.identical(rows, rows + [(999, "x", {})])
    assert report["identical"] is False
    assert report["count_match"] is False


def test_the_comparator_catches_a_reorder():
    """إعادةُ ترتيبٍ داخل المالك = فشل (§٧)."""
    rows = _rows(50)
    shuffled = list(rows)
    shuffled[10], shuffled[11] = shuffled[11], shuffled[10]
    report = frame.identical(rows, shuffled)
    assert report["identical"] is False
    assert report["order_mismatch"] > 0
    assert report["first_mismatch"]["at"] == 10
    assert report["first_mismatch"]["kind"] == "order"


def test_the_comparator_catches_a_changed_event_name():
    rows = _rows(50)
    swapped = list(rows)
    index, _name, payload = swapped[7]
    swapped[7] = (index, "decision.approved.state", payload)
    report = frame.identical(rows, swapped)
    assert report["identity_mismatch"] == 1
    assert report["first_mismatch"]["kind"] == "identity"


def test_the_comparator_catches_a_changed_payload():
    rows = _rows(50)
    edited = list(rows)
    index, name, payload = edited[33]
    edited[33] = (index, name, dict(payload, price=0.0))
    report = frame.identical(rows, edited)
    assert report["payload_mismatch"] == 1
    assert report["first_mismatch"]["kind"] == "payload"


def test_the_comparator_refuses_two_empty_streams():
    """فراغٌ ليس تطابقًا — وإلّا مرّت بوّابةٌ لم تُشغَّل."""
    assert frame.identical([], [])["identical"] is False


def test_a_tiny_float_difference_is_not_swallowed():
    """⛔ §١٧: لا تسويةَ عدديّةً غير معلَنة."""
    rows = [(0, "x", {"v": 1.0000001})]
    other = [(0, "x", {"v": 1.0000002})]
    assert frame.identical(rows, other)["payload_mismatch"] == 1


def test_unknown_is_not_turned_into_zero():
    """⛔ §١٧: `None` لا يصير `0`، ولا العكس."""
    assert frame.identical([(0, "x", {"v": None})],
                           [(0, "x", {"v": 0})])["payload_mismatch"] == 1
    assert frame.identical([(0, "x", {"v": 0})],
                           [(0, "x", {"v": None})])["payload_mismatch"] == 1


def test_the_frame_carries_no_derived_events():
    """عقد §٣: الإطار يحمل المدخل الخام، ولا يخترع واقعةً ولا يستدعي ذرّة."""
    rows = _rows(20)
    _header, back = frame.decode(frame.encode(rows))
    assert len(back) == len(rows)
    assert {name for _i, name, _p in back} == {name for _i, name, _p in rows}


def test_compression_is_a_size_choice_not_a_semantic_one():
    rows = _rows(400)
    squeezed = frame.encode(rows, compress=True)
    plain = frame.encode(rows, compress=False)
    assert len(squeezed) < len(plain)
    assert frame.decode(squeezed)[1] == frame.decode(plain)[1] == rows


# ── حرّاسٌ معزولة: الترويسة خارج البصمة، فلها فحوصها ─────────────────────
#
# ⛔ ثلاث طفراتٍ نجت أوّلًا لأنّ فحص البصمة كان يسبقها فيخفيها. والبصمة
#    على **الجسم** وحده، فالترويسة تُعدَّل بلا أن تنكسر — وهذه الحرّاس
#    تعدّلها عمدًا لتصل كلّ فحصٍ إلى بابه.

_OFF_COUNT = 8          # I  عدد الوقائع
_OFF_FIRST = 12         # Q  أوّل i
_OFF_BODY_LEN = 30      # I  طول الجسم


def _patched(blob: bytes, offset: int, raw: bytes) -> bytes:
    out = bytearray(blob)
    out[offset:offset + len(raw)] = raw
    return bytes(out)


def test_a_body_shorter_than_the_header_claims_is_refused():
    """طولٌ مُعلَنٌ أكبر من الموجود — يُرفَض قبل أن تُفحَص البصمة."""
    blob = frame.encode(_rows(20), compress=False)
    _m, _v, _f, _c, _fi, _li, _n, body_len, _crc, _p = \
        frame._HEADER.unpack_from(blob, 0)
    sick = _patched(blob, _OFF_BODY_LEN, (body_len + 64).to_bytes(4, "little"))
    with pytest.raises(frame.FrameError) as err:
        frame.decode(sick)
    assert "مبتور" in str(err.value)


def test_header_bounds_that_disagree_with_the_records_are_refused():
    """`first_i` في الترويسة لا يطابق أوّل واقعة — والبصمة سليمةٌ تمامًا.

    هذا بالضبط شكلُ ترويسةٍ مزوَّرةٍ وجسمٍ صحيح: لو لم تُفحَص الحدود لمرّت
    دفعةٌ تدّعي مدًى غير مداها، وانكسر `sequence continuity` بلا صوت.
    """
    blob = frame.encode(_rows(20, start=500), compress=False)
    sick = _patched(blob, _OFF_FIRST, (999).to_bytes(8, "little"))
    with pytest.raises(frame.FrameError) as err:
        frame.decode(sick)
    assert "حدّا الترويسة" in str(err.value)


def test_unread_trailing_bytes_in_the_body_are_refused():
    """عددٌ أقلّ من الوقائع يترك بقيّةً غير مقروءة — والبصمة سليمة.

    لو تُجوهلت البقيّة لضاعت وقائع **بصمت**، وهو عين ما يمنعه §١١.
    """
    rows = _rows(20)
    blob = frame.encode(rows, compress=False)
    sick = _patched(blob, _OFF_COUNT, (len(rows) - 1).to_bytes(4, "little"))
    with pytest.raises(frame.FrameError) as err:
        frame.decode(sick)
    assert "بقية" in str(err.value) or "بقيّة" in str(err.value)


def test_the_checksum_covers_the_body_not_the_header():
    """يُقال صراحةً: البصمة على الجسم، والترويسة تُحرَس بفحوصها لا بها."""
    blob = frame.encode(_rows(10, start=5), compress=False)
    sick = _patched(blob, _OFF_FIRST, (5).to_bytes(8, "little"))
    header, back = frame.decode(sick)        # لم تتغيّر القيمة فعليًّا
    assert header["first_i"] == 5 and len(back) == 10
