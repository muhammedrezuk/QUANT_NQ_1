#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""حارس أزرار اللوحة — لا زرّ يشير إلى عدم، ولا زرّ بلا بطاقة، ويُعلَن كلّ حارسٍ بلا زرّ.

لماذا
=====
حكم المالك ٢٠٢٦-٠٩: «فحص شامل، نصّ أزرار كذب». وقِيس يوم ٢٠٢٦-٠٩-١٦ زرّان
يكذبان بطريقتين متعاكستين:

* **زرٌّ بلا ملفّ** — «فحص تغذية سي-تريدر» كان يشغّل
  ``governance/scripts/check_ctrader.py`` وقد حُذف في ``0a576b9`` (ختم ``NQ``).
  يضغطه المالك فيأتيه فشلٌ لا معنى له، ووصفُه يَعِد بفحص معماريّةٍ ماتت.
* **حارسٌ بلا زرّ** — ``arabic_ui`` معرَّف في ``TOOLS`` بالخادم وبلا بطاقة في
  «فحوصات الحوكمة»، فالحارس الذي يمنع تسرّب الإنكليزيّة إلى شاشة المالك لم
  يكن بيده. وحكمه مسجَّل: «حرّاس بلا مفاتيح = فشل».

فهذا الفحص يقارن الطرفين آليًّا:
  أ) كل مدخل في ``TOOLS`` ملفّه الأوّل موجود على القرص.
  ب) كل مدخل في ``TOOLS`` له بطاقة في ``Scripts.tsx``، والعكس بالعكس.
  ج) ٢٠٢٦-١٠-٠٢ (ختم المالك «صلح كامل nq»): كلّ ``governance/checks/check_*.py`` لا مدخل
     له في ``TOOLS`` يُعدّ ويُسمّى. كان رأس هذا الملفّ يقول «ولا حارس بلا مفتاح» والكود لا
     يرى إلّا ما في ``TOOLS`` — فـ47 حارسًا من 81 بلا زرّ ولا يراها أحد (تدقيق ٢٠٢٦-١٠-٠٢ م-03).
     القائمة إعلانٌ لا رسوب: ربطُ كلٍّ منها بزرّ أو أرشفتُه قرار المالك.

⚠️ العنصر الأوّل وحده هو الملفّ؛ ما بعده وسائط (``freeze_core.py verify``) —
وقد رفع هذا الفحصُ خرقًا كاذبًا على ``seal`` قبل التمييز بينهما.
"""
from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError, ValueError):
        pass

SERVER = ROOT / "governance" / "server.py"
CARDS = ROOT / "governance" / "ui" / "src" / "sections" / "Scripts.tsx"
CHECKS = ROOT / "governance" / "checks"


def guards_without_button(entries: dict[str, str | None]) -> tuple[list[str], int]:
    """حرّاس `check_*.py` لا يشير إليها أيّ زرّ في `TOOLS` — والعدد الكلّيّ."""
    wired = {Path(p).name for p in entries.values()
             if p and Path(p).parent.as_posix() == "governance/checks"}
    guards = sorted(p.name for p in CHECKS.glob("check_*.py"))
    return [name for name in guards if name not in wired], len(guards)

# أزرار يُقصد ألّا تكون بطاقةً في «فحوصات الحوكمة» — تُذكر بسببها، لا تُبتلع.
CARDLESS_BY_DESIGN: dict[str, str] = {}


def tools_dict() -> ast.Dict | None:
    tree = ast.parse(SERVER.read_text(encoding="utf-8", errors="replace"))
    for node in ast.walk(tree):
        # `TOOLS` معرَّف بتعليق نوع (AnnAssign) لا بإسناد عاديّ.
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) \
                and node.target.id == "TOOLS" and isinstance(node.value, ast.Dict):
            return node.value
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Dict):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id == "TOOLS":
                    return node.value
    return None


def main() -> int:
    node = tools_dict()
    if node is None:
        print("❌ لم يُعثر على TOOLS في خادم الحوكمة — تغيّر شكلُه، والفحص يتوقّف.")
        return 2

    entries: dict[str, str | None] = {}
    for key, value in zip(node.keys, node.values):
        if not (isinstance(key, ast.Constant) and isinstance(key.value, str)):
            continue
        script: str | None = None
        if isinstance(value, ast.Tuple) and value.elts and isinstance(value.elts[0], ast.List):
            head = value.elts[0].elts[0] if value.elts[0].elts else None
            if isinstance(head, ast.Constant) and isinstance(head.value, str):
                script = head.value
        entries[key.value] = script

    card_ids = set(re.findall(r"id:\s*'([A-Za-z_0-9]+)'", CARDS.read_text(encoding="utf-8", errors="replace")))

    missing_file = [(n, p) for n, p in entries.items() if not p or not (ROOT / p).is_file()]
    cardless = [n for n in entries if n not in card_ids and n not in CARDLESS_BY_DESIGN]
    orphan_cards = sorted(card_ids - set(entries))

    print("حارس أزرار اللوحة")
    print(f"أزرار الخادم: {len(entries)}  ·  بطاقات اللوحة: {len(card_ids)}")
    print()

    if CARDLESS_BY_DESIGN:
        print("بلا بطاقة بقرار معلن:")
        for name, why in sorted(CARDLESS_BY_DESIGN.items()):
            print(f"  · {name} — {why}")
        print()

    bad = 0
    if missing_file:
        bad += len(missing_file)
        print(f"❌ زرّ يشير إلى ملفّ غير موجود ({len(missing_file)}):")
        for name, path in missing_file:
            print(f"   {name} → {path or 'بلا مسار'}")
    if cardless:
        bad += len(cardless)
        print(f"❌ حارس بلا مفتاح — زرّ في الخادم بلا بطاقة للمالك ({len(cardless)}):")
        for name in sorted(cardless):
            print(f"   {name}")
    if orphan_cards:
        bad += len(orphan_cards)
        print(f"❌ بطاقة بلا زرّ — تُعرض للمالك ولا شيء خلفها ({len(orphan_cards)}):")
        for name in orphan_cards:
            print(f"   {name}")

    orphans, total = guards_without_button(entries)
    print()
    print(f"⚠️ حرّاس بلا زرّ في اللوحة: {len(orphans)} من {total} — لا يشغّلها المالك بضغطة"
          " (إعلانٌ لا رسوب؛ ربطها أو أرشفتها قراره):")
    for name in orphans:
        print(f"   · {name}")
    print()

    if bad:
        return 1
    print(f"✅ كل زرّ له ملفّ موجود وبطاقة، ولا بطاقة بلا شيء خلفها؛ وحرّاسٌ بلا زرّ: {len(orphans)} (أعلاه).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
