"""هويّة القرار على الأمر (T1) — تُكمَّل من اللقطة نفسها أو تُعلَن ناقصة.

٢٠٢٦-٠٩-٢٣ (ختم `nq`): نُقلت الدالّة وثابتاها من `atom.py` **حرفيًّا** لأنّه
تجاوز حدّ ٤٠٠ سطرٍ فعليّ (م٩/ملف٤) — صفر تغيير في السلوك. `self` صار الذرّةَ
معاملًا أوّل، وبقي في `atom.py` تفويضٌ بالاسم القديم (`_resolve_identity`).
"""
from __future__ import annotations

from typing import Any

from shared.financial_scope import text

# T1: the mandated identity pair threaded through the whole execution chain.
IDENTITY_FIELDS = ("decision_id", "gate_request_id")
WARNING_IDENTITY = "identity_incomplete"


def resolve_identity(atom, body: dict[str, Any]) -> None:
    """T1: the identity pair rides the order when the builder kept it; a
    value the builder dropped is recovered from the exact snapshot the
    order itself names (snapshot_id is immutable, so this is the recorded
    value of that very snapshot -- not a guess). Whatever remains absent
    passes as None and is declared."""
    record = atom._snapshots.get(text(body.get("snapshot_id")))
    recovered = False
    for field in IDENTITY_FIELDS:
        if not body.get(field) and record is not None and record.get(field):
            body[field] = record[field]; recovered = True
    if recovered:
        atom._identity_recovered += 1
        body["identity_from_snapshot"] = True
    missing = [field for field in IDENTITY_FIELDS if not body.get(field)]
    if missing:
        atom._identity_incomplete += 1
        body["identity_missing"] = missing
        body["identity_warnings"] = [WARNING_IDENTITY]
