#!/usr/bin/env python3
"""حارسٌ مستقلّ لأنماط «المُعلَّب يُحسب ولا يُستعمل» (جولة ٢٣ — قياس المالك على ويندوز).

لا يمسّ الحراس القائمة ولا عقود المانيفست. يفحص خمسة أنماط، صفرُ مخالفاتها هي القاعدة:
  م1  ذرّة تحسب `_rebased_config(context.config)` ثم لا تستعمل الناتج أبدًا.
  م2  `cfg = context.config` خام في initialize (بلا معلِّب) مع وجود مفاتيح مسار نسبية في المانيفست.
  م3  مسار نسبي داخل `config` المانيفست (بما فيه قوائم القواميس) بلا معلِّب في atom.py.
  م4  ثابت وحدة على مستوى المودول بقيمة "var/…" أو "var\\…" (لا يراه المعلِّب بحكم التصميم).
  م5  `ATOM_VERSION` ≠ `version:` في المانيفست (النسخة المزدوجة).
"""
from __future__ import annotations
import re, sys
from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parents[2]
# سوق واحد — الفوركس (أمر المالك «امسح» 2026-09-09): أُزيلت أشجار الكريبتو
# (`atoms_crypto` · `crypto_runtime/*`) فلم يعد لها وجود على القرص.
TREES = ("atoms", "forex_runtime/atoms")
PATHISH = re.compile(r"(?:^|_)(?:path|dir|file)$")
RELVAR = re.compile(r'^["\']var[/\\\\]')


def _nested_rel_paths(node, prefix=""):
    """يُخرِج مسارات var/ النسبية في أي عمق (dict/list)."""
    found = []
    if isinstance(node, dict):
        for k, v in node.items():
            if isinstance(v, str) and isinstance(k, str) and (PATHISH.search(k) or k == "dir") and v.strip().startswith(("var/", "var\\")):
                found.append(f"{prefix}{k}")
            else:
                found += _nested_rel_paths(v, f"{prefix}{k}.")
    elif isinstance(node, list):
        for i, item in enumerate(node):
            found += _nested_rel_paths(item, f"{prefix}[{i}].")
    return found


def main() -> int:
    m1, m2, m3, m4, m5, m6 = [], [], [], [], [], []
    checked = 0
    for tree in TREES:
        base = ROOT / tree
        if not base.is_dir():
            continue
        for adir in sorted(p for p in base.rglob("*") if p.is_dir() and re.match(r"^\d{3}_", p.name)):
            afile = adir / "atom.py"
            mfile = adir / "manifest.yaml"
            if not afile.is_file():
                continue
            checked += 1
            try:
                text = afile.read_text(encoding="utf-8")
            except Exception as exc:
                m1.append(f"{afile}: لا يُقرأ ({exc})"); continue
            has_helper = "def _rebased_config" in text
            # م1
            for mm in re.finditer(r'^(\s*)(\w+) = _rebased_config\((\w+(?:\.\w+)*)\.config\)', text, re.M):
                var = mm.group(2)
                if len(re.findall(rf'\b{re.escape(var)}\b', text)) <= 1:
                    m1.append(f"{afile}:{text[:mm.start()].count(chr(10))+1}: `{var}` يُحسب ولا يُستعمل")
            # م2
            for mm in re.finditer(r'^\s*\w+ = (?:context|c|ctx)\.config\s*$', text, re.M):
                var = mm.group(0).strip().split()[0]
                try:
                    man = yaml.safe_load(mfile.read_text(encoding="utf-8")) or {} if mfile.is_file() else {}
                except Exception:
                    man = {}
                rels = _nested_rel_paths((man.get("config") or {}))
                if rels and not has_helper and "_runtime_paths" not in text and "runtime_root" not in text:
                    m2.append(f"{afile}: `{var} = …config` خام · {len(rels)} مسارًا نسبيًّا في المانيفست")
            # م3
            if mfile.is_file():
                try:
                    man = yaml.safe_load(mfile.read_text(encoding="utf-8")) or {}
                except Exception as exc:
                    man = {}
                rels = _nested_rel_paths(man.get("config") or {})
                if rels and not has_helper and "runtime_root" not in text:
                    m3.append(f"{mfile}: {len(rels)} مسارًا نسبيًّا ({', '.join(rels[:3])}…) وatom.py بلا معلِّب")
            # م4: ثوابت الوحدة (خارج دالة، على مستوى المودول) — مسموحة إن كان لها مُرسٍّ
            anchored = "runtime_var" in text              # دالة مرساة في هذا الملف نفسه
            for i, line in enumerate(text.splitlines(), 1):
                mm = re.match(r'^([A-Z_][A-Z0-9_]*)\s*(:[^=]+)?= ', line)
                if not mm or not RELVAR.match(line.split("=", 1)[1].strip()):
                    continue
                name = mm.group(1)
                if name.startswith("BARE_"):               # بقعة رجوع موثّقة تُستهلك داخل المُرسِّي فقط
                    continue
                if anchored and re.search(rf'^{name}\s*=\s*_\w*\(\)\s*$', line):
                    continue
                m4.append(f"{afile}:{i}: {line.strip()[:96]}")
            # م6: قراءة مسار خام من config داخل initialize مع وجود مُعلِّب (الناتج مُهمَل عمليًّا)
            if has_helper:
                body = text
                for mm in re.finditer(r'(?:context|c|ctx)\.config\s*(?:\.get\(\s*|\[)\s*["\']([A-Za-z0-9_]+)["\']', body):
                    key = mm.group(1)
                    if PATHISH.search(key) or key == "dir":
                        ln = body[:mm.start()].count("\n") + 1
                        m6.append(f"{afile}:{ln}: `{key}` يُقرأ من config الخام مع وجود مُعلِّب — المسار يبقى نسبيًّا")
            # م5
            mv = re.search(r'ATOM_VERSION = "([\d.]+)"', text)
            pv = re.search(r'(?m)^version:\s*"?([\d.]+)"?', mfile.read_text(encoding="utf-8")) if mfile.is_file() else None
            if mv and pv and mv.group(1) != pv.group(1):
                m5.append(f"{adir.name}: كود {mv.group(1)} ≠ مانيفست {pv.group(1)}")
    print(f"فحص إعادة تلقيم المسارات في config — {checked} ذرّة")
    for name, rows in (("م1 ناتجٌ محسوب ومُهمَل", m1), ("م2 config خام مع مسارات نسبية", m2),
                       ("م3 مسارات متداخلة بلا معلِّب", m3), ("م4 ثابت وحدة نسبي", m4),
                       ("م5 نسخة مزدوجة", m5), ("م6 مسارٌ خام مع مُعلِّب موجود", m6)):
        if rows:
            print(f"\n  ✗ {name} — {len(rows)}")
            for r in rows[:12]:
                print(f"      {r}")
    total = len(m1) + len(m2) + len(m3) + len(m4) + len(m5) + len(m6)
    print("\n  لا مخالفات — المُعلَّب محسوب ومستعمل، ولا ثابتٌ نسبيّ يفلت." if total == 0 else f"\n🛑 المخالفات: {total}")
    return 1 if total else 0


if __name__ == "__main__":
    sys.exit(main())
