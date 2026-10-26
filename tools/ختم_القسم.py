# -*- coding: utf-8 -*-
"""ختمُ قسمٍ وتجميدُه ببصمةٍ من القرص — وإعادةُ التحقّق منها لاحقًا.

**لماذا من القرص لا من `git`:** الذي يتداول بمال المالك هو الملفّ الذي
تقرأه النواة، لا ما في فهرس `git`. وقد قِسنا مرارًا أنّهما يفترقان: ملفٌّ
محفوظٌ غير ملتزم يعمل حيًّا، والتزامٌ لم يُنشر بعدُ لا يعمل. فالبصمة تصف
**الحالة العاملة**، ومعها رقم الإصدار الحيّ لتُقارَن بالمانيفست.

    python tools/ختم_القسم.py ختم   500-599
    python tools/ختم_القسم.py تحقّق 500-599

الختم يكتب ملفًّا في `ورق/١٢_الأوامر_والأختام/`، والتحقّق يعيد
الحساب ويقول أيّ ذرّةٍ تحرّكت بعده. (كان `docs/…` حتى نقل المالك الورقَ
كلّه إلى `ورق/` — ٢٠٢٦-٠٩-٢٣ ٢٢:٥٦؛ صُحّح بختم Nq صلح ٢٠٢٦-٠٩-٢٤.
وكان `ورق/١٢_الأوامر_والأختام/مشترك/` حتى فُكّت مجلّدات «مشترك» في الورق
بختم المالك NQ ٢٠٢٦-١٠-٢٦.)
"""
from __future__ import annotations

import hashlib
import io
import json
import os
import re
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ATOMS = os.path.join(ROOT, "atoms")
SEAL_DIR = os.path.join(ROOT, "ورق", "١٢_الأوامر_والأختام")

#: ما يُبصَم من كلّ ذرّة. `atom.py` هو المنطق، و`manifest.yaml` هو العقد
#: والعيارات — وتغيّرُ أيٍّ منهما يغيّر سلوكها، فكلاهما داخل الختم.
SEALED_FILES = ("atom.py", "manifest.yaml")


# ٢٠٢٦-١٠-٠١ (ختم المالك «Nq» على «صلح كل شي»): والوحدات الشقيقة منطقٌ أيضًا.
# الذرّة التي فاقت ٤٠٠ سطر تُقسَم إلى `atom.py` ووحداتٍ بجانبه (465 · 552 ·
# 579 · 580 · 601 …)، والنواة تحمّلها معها. فكان ختمٌ لا يرى إلّا `atom.py`
# يقول «القسم مجمَّد» وأغلبُ منطق الذرّة قد تغيّر بجانبه. الآن تُبصَم كلُّ
# `*.py` في مجلّد الذرّة نفسه (لا الاختبارات ولا المخبّأ). والذرّة بلا شقيق
# سطرُ بصمتها كما كان حرفًا — فأختام الأقسام التي لا شقيق فيها لا تتحرّك.
def _siblings(atom_dir: str) -> dict:
    out = {}
    for name in sorted(os.listdir(atom_dir)):
        path = os.path.join(atom_dir, name)
        if (name.endswith(".py") and name not in SEALED_FILES
                and os.path.isfile(path)):
            out[name] = _sha(path)
    return out


def _sha(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _version(atom_py: str) -> str:
    try:
        text = io.open(atom_py, encoding="utf-8", errors="replace").read()
    except OSError:
        return "?"
    found = re.search(r'ATOM_VERSION\s*=\s*"([^"]+)"', text)
    return found.group(1) if found else "-"


def _sections(span: str) -> list[str]:
    """مجلّدات الأقسام التي يغطّيها المدى، مثل `500-599`."""
    low, high = (int(part) for part in span.split("-"))
    out = []
    for name in sorted(os.listdir(ATOMS)):
        found = re.search(r"(\d+)-(\d+)", name)
        if not found:
            continue
        start, end = int(found.group(1)), int(found.group(2))
        if start >= low and end <= high:
            out.append(os.path.join(ATOMS, name))
    return out


def collect(span: str) -> dict:
    rows = []
    for folder in _sections(span):
        for entry in sorted(os.listdir(folder)):
            atom_dir = os.path.join(folder, entry)
            if not os.path.isdir(atom_dir):
                continue
            number = entry.split("_")[0]
            if not number.isdigit():
                continue
            files = {}
            for name in SEALED_FILES:
                path = os.path.join(atom_dir, name)
                files[name] = _sha(path) if os.path.exists(path) else None
            rows.append({
                "atom": number,
                "name": entry,
                "version": _version(os.path.join(atom_dir, "atom.py")),
                "files": files,
                "siblings": _siblings(atom_dir),
            })
    rows.sort(key=lambda r: r["atom"])
    # بصمةُ القسم: تجزئةُ السطور المرتّبة. ترتيبٌ ثابت ⟹ رقمٌ قابل للإعادة،
    # وأيُّ حرفٍ في أيّ ذرّة يغيّره.
    spine = "\n".join(
        "%s %s %s" % (r["atom"], r["files"].get("atom.py"),
                      r["files"].get("manifest.yaml"))
        + "".join(" %s=%s" % item for item in sorted(r["siblings"].items()))
        for r in rows)
    return {
        "span": span,
        "sealed_at": time.time(),
        "sealed_at_text": time.strftime("%Y-%m-%d %H:%M:%S"),
        "atom_count": len(rows),
        "section_fingerprint": hashlib.sha256(spine.encode("utf-8")).hexdigest(),
        "atoms": rows,
    }


def _seal_path(span: str) -> str:
    return os.path.join(SEAL_DIR, "ختم-تجميد-%s.json" % span)


def seal(span: str) -> None:
    data = collect(span)
    os.makedirs(SEAL_DIR, exist_ok=True)
    with io.open(_seal_path(span), "w", encoding="utf-8", newline="\n") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)
    print("جُمِّد القسم %s — %d ذرّة" % (span, data["atom_count"]))
    print("بصمة القسم: %s" % data["section_fingerprint"])
    print("الملفّ: %s" % _seal_path(span).replace(ROOT + os.sep, ""))


def verify(span: str) -> int:
    path = _seal_path(span)
    if not os.path.exists(path):
        print("لا ختم للقسم %s — اختمه أوّلًا." % span)
        return 2
    old = json.load(io.open(path, encoding="utf-8"))
    new = collect(span)
    print("ختمٌ بتاريخ %s · %d ذرّة" % (old["sealed_at_text"], old["atom_count"]))
    if old["section_fingerprint"] == new["section_fingerprint"]:
        print("✔ القسم مجمَّد كما خُتم — بصمته %s"
              % new["section_fingerprint"][:16])
        return 0

    before = {r["atom"]: r for r in old["atoms"]}
    after = {r["atom"]: r for r in new["atoms"]}
    print("🔴 تحرّك القسم بعد ختمه.\n")
    for number in sorted(set(before) | set(after)):
        a, b = before.get(number), after.get(number)
        if a and not b:
            print("   %s  أُزيلت  (%s)" % (number, a["name"]))
        elif b and not a:
            print("   %s  أُضيفت  (%s v%s)" % (number, b["name"], b["version"]))
        elif a["files"] != b["files"] or a.get("siblings", {}) != b["siblings"]:
            # ختمٌ أقدم من بصمة الأشقّاء لا يحمل مفتاحها — فيظهر كلُّ شقيقٍ «تغيّر».
            old_sib = a.get("siblings", {})
            changed = [n for n in SEALED_FILES
                       if a["files"].get(n) != b["files"].get(n)]
            changed += [n for n in sorted(set(old_sib) | set(b["siblings"]))
                        if old_sib.get(n) != b["siblings"].get(n)]
            arrow = ("v%s ⟶ v%s" % (a["version"], b["version"])
                     if a["version"] != b["version"] else "النسخة كما هي")
            print("   %s  تغيّر: %-24s %s   [%s]"
                  % (number, ", ".join(changed), arrow, b["name"]))
    print("\nالبصمة الآن: %s" % new["section_fingerprint"])
    return 1


def main() -> int:
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    action, span = sys.argv[1], sys.argv[2]
    if action in ("ختم", "seal"):
        seal(span)
        return 0
    if action in ("تحقّق", "تحقق", "verify"):
        return verify(span)
    print("لا أعرف الأمر «%s» — استعمل: ختم | تحقّق" % action)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
