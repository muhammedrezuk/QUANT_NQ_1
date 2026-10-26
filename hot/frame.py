# -*- coding: utf-8 -*-
"""§5 — إطارُ الدفعة الثنائيّ: `bytes ⟷ سجلّات إدخالٍ مُصادَقة`.

## العقد (ورقة المالك ٢٠٢٦-٠٩-١٨، §٤ و§١١ و§٢٠)

الإطار يحمل **المدخل الخام وحده**. لا يحمل نتائج ذرّات، ولا `decision.*`
كبدائل للمدخل، ولا يستدعي ذرّةً، ولا يُنتج حدثًا مشتقًّا. وظيفة فاكّه:

    bytes ⟶ validated input records

ويحفظ خمسة أشياء أو يرفض:

    هويّة المجرى · ترتيب الوصول · هويّة الحدث · الحمولة · اتّصال التسلسل

**والدفعُ ليس دمجًا** (`Batching ≠ semantic coalescing`): الإطار لا يُسقط
واقعةً ولا يستبدل واقعةً بأحدث منها. فقدُ مدخلٍ = فشلُ تكافؤ، لا تحسين.

## لماذا صيغةٌ خاصّة

المسار القديم دفع كلفةً **لكلّ رسالة**: `pickle` وتوجيهُ مشترِكٍ وصندوقُ
بريدٍ وإعادةُ نشر. فوحدةُ النقل هنا **دفعة** لا حدثٌ مشتقّ. ولا `pickle`:
حمولاتُ الشريط بنًى ورقيّة (معجم/قائمة/قياسيّ)، و`json` القياسيّ يرمّزها
**مرّةً للدفعة كلّها** لا مرّةً للواقعة.

والجهاز لا يملك `msgpack` ولا `orjson` ولا `zstandard` — مقيسٌ لا مفترَض.
فالبناء على `struct` و`zlib` وحدهما، وهما من المكتبة القياسيّة.

## الشكل

    ┌─ ترويسة 40 بايت ─────────────────────────────────────────────┐
    │ سحر 4 │ نسخة 2 │ رايات 2 │ عدد 4 │ أوّل i 8 │ آخر i 8       │
    │ أسماء 2 │ طول الجسم 4 │ crc32 للجسم 4 │ حشو 2               │
    └──────────────────────────────────────────────────────────────┘
    ┌─ جدول الأسماء ─┐  اسمُ الحدث يُكتب مرّةً لا مع كلّ واقعة.
    ┌─ الجسم ────────┐  مضغوطًا: (i، فهرس الاسم، طول، حمولة)…

و`crc32` على الجسم **قبل** الضغط: يكشف تلفَ النقل وتلفَ فكّ الضغط معًا.
"""
from __future__ import annotations

import json
import struct
import zlib
from typing import Any, Iterable, Sequence

MAGIC = b"NQF1"
VERSION = 1

#: راياتٌ في الترويسة. `1` = الجسم مضغوطٌ بـ`zlib`.
FLAG_DEFLATE = 1

_HEADER = struct.Struct("<4sHHIQQHIIH")
HEADER_SIZE = _HEADER.size          # ٤٠ بايتًا

#: سقفُ أمانٍ على الفكّ — إطارٌ مشوّهٌ لا يُصرَف عليه ذاكرةً بلا حدّ.
MAX_RECORDS = 5_000_000
MAX_BODY = 512 * 1024 * 1024


class FrameError(ValueError):
    """إطارٌ لا يُصدَّق. يُرفَض ولا يُصلَح — التصحيح الصامت يكذب على التكافؤ."""


def _varint(value: int, out: bytearray) -> None:
    if value < 0:
        raise FrameError("قيمةٌ سالبة لا تُرمَّز: %d" % value)
    while True:
        byte = value & 0x7F
        value >>= 7
        out.append(byte | (0x80 if value else 0))
        if not value:
            return


def _read_varint(blob: bytes, pos: int) -> tuple[int, int]:
    value = shift = 0
    while True:
        if pos >= len(blob):
            raise FrameError("الجسم انتهى داخل عددٍ متغيّر الطول")
        byte = blob[pos]
        pos += 1
        value |= (byte & 0x7F) << shift
        if not byte & 0x80:
            return value, pos
        shift += 7
        if shift > 63:
            raise FrameError("عددٌ متغيّر الطول أطول من المسموح")


def encode(records: Sequence[tuple[int, str, Any]], *, stream_id: int = 0,
           compress: bool = True) -> bytes:
    """يرمّز دفعةً واحدة. `records` = `(رقم الوصول، اسم الحدث، الحمولة)`.

    الترتيب يُحفظ كما وصل — لا يُفرَز هنا ولا يُعاد ترتيبه. ورقمُ الوصول
    يُكتب مع كلّ واقعة، فالفاكّ يثبت الترتيب بالرقم لا بموضع البايت.
    """
    if not records:
        raise FrameError("دفعةٌ فارغة لا تُرمَّز — الفراغ ليس إطارًا")
    if len(records) > MAX_RECORDS:
        raise FrameError("عدد الوقائع فوق السقف: %d" % len(records))

    names: dict[str, int] = {}
    body = bytearray()
    for index, name, payload in records:
        name = str(name)
        slot = names.get(name)
        if slot is None:
            slot = names[name] = len(names)
        raw = json.dumps(payload, ensure_ascii=False, sort_keys=True,
                         separators=(",", ":"), default=str).encode("utf-8")
        _varint(int(index), body)
        _varint(slot, body)
        _varint(len(raw), body)
        body += raw

    table = bytearray()
    for name in names:                      # المعجم يحفظ ترتيب الإدراج
        raw = name.encode("utf-8")
        _varint(len(raw), table)
        table += raw

    payload_block = bytes(table) + bytes(body)
    crc = zlib.crc32(payload_block) & 0xFFFFFFFF
    flags = 0
    if compress:
        squeezed = zlib.compress(payload_block, 6)
        if len(squeezed) < len(payload_block):
            payload_block, flags = squeezed, FLAG_DEFLATE

    header = _HEADER.pack(MAGIC, VERSION, flags, len(records),
                          int(records[0][0]), int(records[-1][0]),
                          len(names), len(payload_block), crc, 0)
    return header + payload_block


def decode(blob: bytes) -> tuple[dict[str, Any], list[tuple[int, str, Any]]]:
    """`bytes ⟶ (ترويسة، سجلّات)`. يرفع `FrameError` ولا يُصلح شيئًا.

    ⛔ ولا يُنتج حدثًا مشتقًّا ولا يستدعي ذرّة: هذه وظيفةُ فكٍّ لا تنفيذ.
    """
    if len(blob) < HEADER_SIZE:
        raise FrameError("أقصر من ترويسة")
    (magic, version, flags, count, first_i, last_i,
     name_count, body_len, crc, _pad) = _HEADER.unpack_from(blob, 0)
    if magic != MAGIC:
        raise FrameError("سحرٌ غير معروف: %r" % magic)
    if version != VERSION:
        raise FrameError("نسخةٌ غير مدعومة: %d" % version)
    if body_len > MAX_BODY:
        raise FrameError("جسمٌ فوق السقف: %d" % body_len)
    body = blob[HEADER_SIZE:HEADER_SIZE + body_len]
    if len(body) != body_len:
        raise FrameError("الجسم مبتورٌ: %d من %d" % (len(body), body_len))
    if flags & FLAG_DEFLATE:
        try:
            body = zlib.decompress(body)
        except zlib.error as exc:
            raise FrameError("تعذّر فكّ الضغط: %s" % exc) from exc
    if (zlib.crc32(body) & 0xFFFFFFFF) != crc:
        raise FrameError("بصمة الجسم لا تطابق — الإطار تالف")

    pos = 0
    names: list[str] = []
    for _ in range(name_count):
        size, pos = _read_varint(body, pos)
        names.append(body[pos:pos + size].decode("utf-8"))
        pos += size

    out: list[tuple[int, str, Any]] = []
    for _ in range(count):
        index, pos = _read_varint(body, pos)
        slot, pos = _read_varint(body, pos)
        size, pos = _read_varint(body, pos)
        chunk = body[pos:pos + size]
        if len(chunk) != size:
            raise FrameError("حمولةٌ مبتورة عند الواقعة %d" % index)
        pos += size
        if slot >= len(names):
            raise FrameError("فهرسُ اسمٍ خارج الجدول: %d" % slot)
        out.append((index, names[slot], json.loads(chunk.decode("utf-8"))))
    if pos != len(body):
        raise FrameError("بقيةٌ غير مقروءة في الجسم: %d بايت" % (len(body) - pos))
    if out and (out[0][0] != first_i or out[-1][0] != last_i):
        raise FrameError("حدّا الترويسة لا يطابقان الوقائع")

    header = {"version": version, "flags": flags, "count": count,
              "first_i": first_i, "last_i": last_i, "names": name_count,
              "body_len": body_len, "crc32": crc, "stream_id": 0}
    return header, out


def batches(records: Iterable[tuple[int, str, Any]], *, max_records: int = 512,
            ) -> Iterable[Sequence[tuple[int, str, Any]]]:
    """يقسّم مجرًى إلى دفعاتٍ **بحدٍّ أعلى للعدد وحده**.

    ⚠️ لا حدَّ زمنيًّا هنا: هذا مسار الشريط (إعادةُ تشغيل)، والزمن حكمُ
    التشغيل الحيّ لا حكمُ الإعادة. وخلطُهما يجعل الإعادة غير حتميّة.
    """
    chunk: list[tuple[int, str, Any]] = []
    for row in records:
        chunk.append(row)
        if len(chunk) >= max_records:
            yield chunk
            chunk = []
    if chunk:
        yield chunk


def round_trip(records: Sequence[tuple[int, str, Any]], *,
               max_records: int = 512) -> list[tuple[int, str, Any]]:
    """يرمّز ثمّ يفكّ مجرًى كاملًا — أداةُ إثبات أمانة الإطار (Gate A)."""
    out: list[tuple[int, str, Any]] = []
    for chunk in batches(records, max_records=max_records):
        _header, decoded = decode(encode(chunk))
        out.extend(decoded)
    return out


def identical(left: Sequence[tuple[int, str, Any]],
              right: Sequence[tuple[int, str, Any]]) -> dict[str, Any]:
    """يقارن مجريين واقعةً بواقعة على أربعة أوجه — ولا يُسقط صفًّا مخالفًا.

    العدّ · الترتيب · الهويّة · الحمولة. وأوّل اختلافٍ يُسمّى بموضعه، فلا
    يُقال «٩٩٫٩٪» ثمّ يُحسب الباقي.
    """
    report: dict[str, Any] = {
        "left": len(left), "right": len(right),
        "count_match": len(left) == len(right),
        "order_mismatch": 0, "identity_mismatch": 0, "payload_mismatch": 0,
        "first_mismatch": None,
    }
    for position, (a, b) in enumerate(zip(left, right)):
        kind = ""
        if a[0] != b[0]:
            report["order_mismatch"] += 1
            kind = "order"
        elif a[1] != b[1]:
            report["identity_mismatch"] += 1
            kind = "identity"
        elif a[2] != b[2]:
            report["payload_mismatch"] += 1
            kind = "payload"
        if kind and report["first_mismatch"] is None:
            report["first_mismatch"] = {"at": position, "kind": kind,
                                        "left": a[:2], "right": b[:2]}
    report["identical"] = bool(
        report["count_match"] and not report["order_mismatch"]
        and not report["identity_mismatch"] and not report["payload_mismatch"]
        and len(left) > 0)
    return report
