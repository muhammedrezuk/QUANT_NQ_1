# -*- coding: utf-8 -*-
"""٢٠٢٦-١٠-٠٧ (تدقيق الإغلاق — ورقة النقاش ٤-ب/١٩): حكم 552 يُكتب على بطاقة القرار نفسه وحدها.

كانت البطاقة الحيّة للرمز تُكتب أيًّا كان قرارها، فحملت البطاقة #86470 «رُفض» على صفقةٍ رابحة،
ودخولين ووقفين من أمرين. والآن: رقم القرار في الأمر ≠ رقم قرار البطاقة ⟸ لا كتابة، ويُعدّ."""
import asyncio
import importlib.util
import sys
from pathlib import Path

FOLDER = Path(__file__).resolve().parents[1]
ROOT = Path(__file__).resolve().parents[4]
for _path in (str(ROOT), str(FOLDER)):
    if _path not in sys.path:
        sys.path.insert(0, _path)
_spec = importlib.util.spec_from_file_location("_t552_card_writer", FOLDER / "order_card_writer.py")
writer = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(writer)


class _Store:
    def __init__(self, decision_id):
        self.card = {"card_no": 7, "symbol": "USTEC", "decision_id": decision_id}
        self.updates, self.noted = [], []

    def live_card(self, symbol):
        return self.card if symbol == "USTEC" else None

    def update(self, number, fields):
        self.updates.append((number, dict(fields)))

    def notes(self, rows):
        self.noted.extend(rows)


class _Atom:
    def __init__(self, store):
        self._cards = store
        self._card_writes = self._card_missing = self._card_other_decision = 0
        self._card_error = ""


def _write(atom, decision_id):
    asyncio.run(writer.write_card(atom, "USTEC", {"verdict_552": "رُفض: X"}, "552", decision_id))


def test_verdict_lands_on_its_own_decisions_card():
    atom = _Atom(_Store("414:USTEC:100"))
    _write(atom, "414:USTEC:100")
    assert atom._cards.updates == [(7, {"verdict_552": "رُفض: X"})] and atom._card_writes == 1


def test_verdict_of_another_decision_is_counted_not_written():
    atom = _Atom(_Store("414:USTEC:100"))
    _write(atom, "414:USTEC:400")
    assert atom._cards.updates == [] and atom._card_other_decision == 1 and atom._card_writes == 0


def test_unknown_decision_keeps_todays_behaviour():
    # أمرٌ بلا رقم قرار، أو بطاقةٌ بلا رقم ⟸ السلوك القائم (تُكتب) — لا يُطفأ سجلٌّ بلا دليل.
    atom = _Atom(_Store(None))
    _write(atom, "414:USTEC:400")
    _write(atom, "")
    assert len(atom._cards.updates) == 2 and atom._card_other_decision == 0
