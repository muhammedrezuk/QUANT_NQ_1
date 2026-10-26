# -*- coding: utf-8 -*-
"""§5 / C — حاوية حالة `Account×Symbol` (المالك الساخن).

## العقد (ورقة البناء §٤ و§٥ و§١٧ و§٢٥)

مالكٌ واحدٌ لكلّ `Account×Symbol`، ولا مدخلَ يدخله مرّتين، ولا ترتيبَ يُكسَر
داخله. وليس طابورًا فحسب: هو **حاوية الحالة الساخنة** لعشر خانات —
السوق والمؤشّرات والبنية والسيولة والإحصاء والاحتمالات والاستراتيجيّة
والقرار والمخاطر ونيّة التنفيذ.

## ما لا يقع هنا

    ⛔ لا دمجٌ دلاليّ للمدخل (§٢٥): `tick N+1` لا يحلّ محلّ `tick N`.
       الدمج الذي أثبتناه في `EventBus` للحالات القديمة **لا ينتقل** إلى
       ناقل المدخل الجديد. فقدُ مدخلٍ = فشلُ تكافؤ.
    ⛔ لا `json` ولا `pickle` ولا حدثٌ مشتقّ داخل الدورة (§١٤).
    ⛔ لا `uuid` لكلّ انتقال (§١٣): الهويّة في المدخل أصلًا.
    ⛔ ولا كتابةَ ذرّةِ رمزٍ في حالة رمزٍ آخر (§٦) — العابر للرموز يُقرأ
       من خدمته لقطةً للقراءة فقط.

## الملكيّة ليست من صنعنا

`OwnershipKey` و`partition_for` موجودان في `transport/ownership.py` بعقدٍ
مكتوب: فاصل `|`، و`blake2b(digest_size=8) % 64`. نستوردهما ولا نعيد
اشتقاقهما — مفتاحٌ ثانٍ بصيغةٍ ثانية يعني ملكيّتين، وهو عين ما تمنعه §٤.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from transport.ownership import (  # noqa: E402
    LOGICAL_PARTITIONS, OwnershipKey, OwnershipRegistry, ownership_key,
)

#: خانات الحالة العشر (§٥). أسماءٌ ثابتةٌ كي يقارَن مالكٌ بمالك.
STATE_SLOTS = (
    "market", "indicator", "structure", "liquidity", "statistics",
    "probability", "strategy", "decision", "risk", "execution_intent",
)


class OwnershipError(RuntimeError):
    """خرقُ ملكيّةٍ أو ترتيب. يُرفَع ولا يُبتلع — §٢٤: لا إخفاءَ لفشل."""


def partition_of(key: OwnershipKey, group: int = 0) -> int:
    """القسم المنطقيّ — **العقد القائم حرفًا**، لا اشتقاقٌ جديد."""
    return OwnershipRegistry.partition_for(key, group)


class Cell:
    """مالكُ `Account×Symbol` واحد: حالتُه وترتيبُه ومصيرُ مدخلاته.

    ولا يعرف عاملًا ولا نواةً: `القسم ← العامل` خريطةٌ فوقه، فتغيّرُ عدد
    العمّال لا يمسّ ملكيّة بياناته (§٣).
    """

    __slots__ = ("key", "partition", "state", "committed", "commits",
                 "last_sequence", "accepted", "rejected_out_of_order",
                 "rejected_foreign", "failures", "_seen")

    def __init__(self, key: OwnershipKey) -> None:
        self.key = key
        self.partition = partition_of(key)
        #: عشر خاناتٍ حيّة — معاجم عادية، بلا تجميدٍ ولا نسخٍ لكلّ قراءة.
        self.state: dict[str, dict[str, Any]] = {slot: {} for slot in STATE_SLOTS}
        #: لقطةُ نهاية الدورة السابقة — وحدها ما تقرؤه الحافّة الراجعة.
        self.committed: dict[str, dict[str, Any]] = {}
        self.commits = 0
        self.last_sequence: int | None = None
        self.accepted = 0
        self.rejected_out_of_order = 0
        self.rejected_foreign = 0
        self.failures = 0
        #: تسلسلاتٌ رُئيت — يمنع دخول المدخل مرّتين (§١٧).
        self._seen: set[int] = set()

    # ── القبول ───────────────────────────────────────────────────────────

    def owns(self, payload: dict) -> bool:
        return ownership_key(payload) == self.key

    def admit(self, sequence: int, payload: dict) -> None:
        """يقبل مدخلًا **مرّةً واحدة وبالترتيب**، أو يرفع.

        ⛔ لا يُدمَج ولا يُستبدَل ولا يُسقَط صامتًا: الرفض يُعدّ ويُرفَع.
        """
        if not self.owns(payload):
            self.rejected_foreign += 1
            raise OwnershipError(
                "مدخلٌ لغير مالكه: %s ⟵ %s"
                % (self.key.text, (ownership_key(payload) or "؟")))
        sequence = int(sequence)
        if sequence in self._seen:
            self.rejected_out_of_order += 1
            raise OwnershipError("تسلسلٌ مكرّر على %s: %d"
                                 % (self.key.text, sequence))
        if self.last_sequence is not None and sequence < self.last_sequence:
            self.rejected_out_of_order += 1
            raise OwnershipError(
                "ترتيبٌ مكسور على %s: %d بعد %d"
                % (self.key.text, sequence, self.last_sequence))
        self._seen.add(sequence)
        self.last_sequence = sequence
        self.accepted += 1

    # ── الحالة ───────────────────────────────────────────────────────────

    def write(self, slot: str, values: dict[str, Any]) -> None:
        if slot not in self.state:
            raise OwnershipError("خانةٌ غير معروفة: %s" % slot)
        self.state[slot].update(values)

    def read(self, slot: str) -> dict[str, Any]:
        if slot not in self.state:
            raise OwnershipError("خانةٌ غير معروفة: %s" % slot)
        return self.state[slot]

    # ── الحالة الملتزمة: ما تقرؤه الحافّة الراجعة ────────────────────────
    #
    # ختم المالك `NQ — ACCEPT FEEDBACK 367→452`:
    #
    #     decision[t]  لا يقرأ  evidence المنتَج في الدورة t
    #     بل آخر evidence **ملتزَم** من دورةٍ سابقة
    #
    # فالحالة الحيّة تُكتب داخل الدورة، والحالة **الملتزمة** لا تتحرّك إلّا
    # عند `commit()` في نهايتها. وقارئُ الحافّة الراجعة يقرأ الملتزمة وحدها،
    # فيستحيل بالبناء أن يرى دليلَ دورته هو.

    def read_committed(self, slot: str) -> dict[str, Any]:
        """ما تقرؤه الحافّة الراجعة — **لقطةُ دورةٍ سابقة**، لا الحيّة."""
        if slot not in self.state:
            raise OwnershipError("خانةٌ غير معروفة: %s" % slot)
        return self.committed.get(slot, {})

    def commit(self) -> int:
        """يُنهي الدورة: الحيّةُ تصير ملتزمة. يُنادى مرّةً في نهاية الدورة."""
        self.committed = {slot: dict(values)
                          for slot, values in self.state.items()}
        self.commits += 1
        return self.commits

    def snapshot(self) -> dict[str, Any]:
        """لقطةٌ **للقراءة خارج المسار** — لوحةٌ أو تخزين، لا دورةٌ ساخنة."""
        return {
            "key": self.key.text,
            "partition": self.partition,
            "last_sequence": self.last_sequence,
            "commits": self.commits,
            "accepted": self.accepted,
            "rejected_out_of_order": self.rejected_out_of_order,
            "rejected_foreign": self.rejected_foreign,
            "failures": self.failures,
            "state": {slot: dict(values) for slot, values in self.state.items()},
        }


class CellMap:
    """كلّ المالكين في عاملٍ واحد: مالكٌ واحدٌ لكلّ مفتاح، لا أكثر (§٤)."""

    def __init__(self) -> None:
        self._cells: dict[OwnershipKey, Cell] = {}
        self.created = 0
        self.dispatched = 0

    def cell_for(self, key: OwnershipKey) -> Cell:
        cell = self._cells.get(key)
        if cell is None:
            cell = self._cells[key] = Cell(key)
            self.created += 1
        return cell

    def dispatch(self, sequence: int, payload: dict) -> Cell:
        """يوجّه مدخلًا إلى مالكه **مرّةً واحدة** ويعيده.

        ⛔ ولا يُعيده إلى الناقل ثمّ إلى المالك ثانيةً (§١٧).
        """
        key = ownership_key(payload)
        if key is None:
            raise OwnershipError("مدخلٌ بلا مفتاح ملكيّة — لا حسابَ ولا رمز")
        cell = self.cell_for(key)
        cell.admit(sequence, payload)
        self.dispatched += 1
        return cell

    def keys(self) -> list[OwnershipKey]:
        return list(self._cells)

    def partitions(self) -> dict[int, list[str]]:
        out: dict[int, list[str]] = {}
        for key, cell in self._cells.items():
            out.setdefault(cell.partition, []).append(key.text)
        for names in out.values():
            names.sort()
        return out

    def stats(self) -> dict[str, Any]:
        return {
            "cells": len(self._cells),
            "created": self.created,
            "dispatched": self.dispatched,
            "logical_partitions": LOGICAL_PARTITIONS,
            "partitions_used": len({c.partition for c in self._cells.values()}),
            "rejected_foreign": sum(c.rejected_foreign for c in self._cells.values()),
            "rejected_out_of_order": sum(c.rejected_out_of_order
                                         for c in self._cells.values()),
        }
