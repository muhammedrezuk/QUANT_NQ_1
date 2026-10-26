#!/usr/bin/env python3
"""جرد موسّع وتدقيق شامل — يقيس الشجرة كلّها بمعايير موضوعيّة.

لا يحكم على جودة منطق، بل يقيس ما يمكن قياسه ويعرضه بلا تجميل:

  ١ · الإسقاط الصامت — `return` بلا عدّاد في معالج حدث.
  ٢ · قاعدة السبريد — أين تُقاس `ask < bid` وأين `ask <= bid`.
  ٣ · الحجم الفعليّ مقابل الحدّ، والاستثناءات.
  ٤ · الأحداث اليتيمة — يُنشر ولا يسمعه أحد.
  ٥ · الأحداث المكسورة — يُشترَك به ولا ينشره أحد.
  ٦ · تغطية الاختبارات والتوثيق لكل ذرّة.
  ٧ · زمن البيانات مقابل ساعة الحائط.

    python3 governance/scripts/full_audit.py            # تقرير نصّي
    python3 governance/scripts/full_audit.py --json     # بيانات خام
"""
from __future__ import annotations

import ast
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
ATOMS = ROOT / "atoms"
SHARED = ROOT / "shared"
SKIP = {"__pycache__", ".pytest_cache"}

COUNTER_HINTS = ("dropped", "rejected", "invalid", "skipped", "unusable",
                 "malformed", "ignored", "orphan", "unknown", "late")
HANDLER_HINTS = ("_on_", "on_tick", "on_candle", "on_depth", "on_raw",
                 "handler", "_handle")
MAX_EFFECTIVE_LINES = 400

EXTERNAL_EVENTS = {
    "core.atom.started", "core.atom.failed", "core.atom.unhealthy",
    "core.atom.stopped", "core.boot.completed", "core.shutdown.started",
    "tools.integrity.violation",
}
EXTERNAL_PREFIXES = ("logs.", "dashboard.", "panel.", "ui.", "telemetry.")


def effective_lines(source: str) -> int:
    return len([ln for ln in source.split("\n")
                if ln.strip() and not ln.strip().startswith("#")])


def silent_returns(source: str) -> list[tuple[str, int]]:
    """`return` عارٍ داخل معالج حدث بلا عدّاد يسبقه في الجسم نفسه.

    الحراسة المشروعة (`if not self._running`) تُستثنى: هي منع تشغيل لا
    إسقاط بيانات.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []
    found: list[tuple[str, int]] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef)):
            continue
        if not any(hint in node.name for hint in HANDLER_HINTS):
            continue
        body_src = ast.get_source_segment(source, node) or ""
        for inner in ast.walk(node):
            if not isinstance(inner, ast.Return) or inner.value is not None:
                continue
            line = source.split("\n")[inner.lineno - 1] if inner.lineno else ""
            window = "\n".join(
                source.split("\n")[max(0, inner.lineno - 6):inner.lineno])
            if "_running" in window or "is None" in window and "payload" not in window:
                continue
            if any(hint in window for hint in COUNTER_HINTS):
                continue
            found.append((node.name, inner.lineno))
    return found


def spread_rule(source: str) -> list[tuple[int, str]]:
    hits: list[tuple[int, str]] = []
    for index, line in enumerate(source.split("\n"), start=1):
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        if re.search(r"ask\s*<\s*bid|ask\s*<=\s*bid|"
                     r"best_bid\s*>=\s*best_ask|best_bid\s*>\s*best_ask", stripped):
            kind = "strict" if re.search(r"ask\s*<\s*bid|best_bid\s*>\s*best_ask",
                                         stripped) else "unified"
            hits.append((index, kind))
    return hits


def wall_clock(source: str) -> int:
    return len(re.findall(r"clock\.now\(\)|time\.time\(\)", source))


def load_manifest(path: Path) -> dict:
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (yaml.YAMLError, OSError):
        return {}


def external_subscribers() -> set[str]:
    found: set[str] = set()
    pattern = re.compile(r'subscribe(?:_all)?\(\s*["\']([a-zA-Z0-9_.]+)["\']')
    for root in (ROOT / "governance", ROOT / "core", SHARED):
        if not root.is_dir():
            continue
        for path in root.rglob("*.py"):
            if "__pycache__" in path.parts:
                continue
            try:
                found.update(pattern.findall(path.read_text(encoding="utf-8")))
            except OSError:
                continue
    return found


def audit() -> dict:
    atoms: list[dict] = []
    published: dict[str, list[str]] = defaultdict(list)
    subscribed: dict[str, list[str]] = defaultdict(list)

    for manifest_path in sorted(ATOMS.rglob("manifest.yaml")):
        if any(part in SKIP for part in manifest_path.parts):
            continue
        folder = manifest_path.parent
        atom_file = folder / "atom.py"
        if not atom_file.is_file():
            continue
        manifest = load_manifest(manifest_path)
        source = atom_file.read_text(encoding="utf-8")
        name = folder.name
        section = folder.parent.name

        for event in manifest.get("publishes") or []:
            published[str(event)].append(name)
        for event in manifest.get("subscribes") or []:
            subscribed[str(event)].append(name)

        strict = [ln for ln, kind in spread_rule(source) if kind == "strict"]
        atoms.append({
            "atom": name, "section": section,
            "id": manifest.get("id"),
            "lines_raw": len(source.split("\n")),
            "lines_effective": effective_lines(source),
            "over_limit": effective_lines(source) > MAX_EFFECTIVE_LINES,
            "silent_returns": [f"{fn}:{ln}" for fn, ln in silent_returns(source)],
            "spread_strict_lines": strict,
            "wall_clock_calls": wall_clock(source),
            "has_tests": (folder / "tests" / "test_atom.py").is_file(),
            "has_history": (folder / "التاريخ.md").is_file(),
            "has_explainer": (folder / "الشرح.md").is_file(),
            "startup_mode": manifest.get("startup_mode"),
            "critical": manifest.get("critical"),
        })

    external = external_subscribers()
    heard = set(subscribed) | external | EXTERNAL_EVENTS
    orphan_data, orphan_panel = [], []
    for event, owners in sorted(published.items()):
        if event in heard or event.startswith(EXTERNAL_PREFIXES):
            continue
        row = {"event": event, "publishers": owners}
        (orphan_panel if event.endswith(".state") else orphan_data).append(row)

    broken = [{"event": e, "subscribers": s} for e, s in sorted(subscribed.items())
              if e not in published and e not in EXTERNAL_EVENTS
              and not e.startswith(("SYS_", "kernel.", "core."))]

    shared_files: list[dict] = []
    for path in sorted(SHARED.glob("*.py")):
        source = path.read_text(encoding="utf-8")
        strict = [ln for ln, kind in spread_rule(source) if kind == "strict"]
        if strict or wall_clock(source):
            shared_files.append({
                "file": path.name, "spread_strict_lines": strict,
                "wall_clock_calls": wall_clock(source),
                "lines_effective": effective_lines(source)})

    return {"atoms": atoms, "orphan_data": orphan_data,
            "orphan_panel": orphan_panel, "broken": broken,
            "shared": shared_files}


def report(data: dict) -> None:
    atoms = data["atoms"]
    print("=" * 66)
    print("جرد موسّع وتدقيق شامل — QUANT_NQ")
    print("=" * 66)
    print(f"\nالذرّات المفحوصة: {len(atoms)}")

    sections: dict[str, list[dict]] = defaultdict(list)
    for atom in atoms:
        sections[atom["section"]].append(atom)

    print("\n" + "-" * 66)
    print("١ · الإسقاط الصامت — `return` بلا عدّاد في معالج حدث")
    print("-" * 66)
    print(f"{'القسم':<16}{'ذرّات':>7}{'مصابة':>8}{'مواضع':>8}")
    total_silent = 0
    for name in sorted(sections):
        rows = sections[name]
        hit = [a for a in rows if a["silent_returns"]]
        spots = sum(len(a["silent_returns"]) for a in rows)
        total_silent += spots
        flag = "  ⚠" if len(hit) > len(rows) * 0.5 else ""
        print(f"{name:<16}{len(rows):>7}{len(hit):>8}{spots:>8}{flag}")
    print(f"{'المجموع':<16}{len(atoms):>7}{'':>8}{total_silent:>8}")

    print("\n" + "-" * 66)
    print("٢ · قاعدة السبريد — مواضع لا تزال `ask < bid`")
    print("-" * 66)
    strict_atoms = [a for a in atoms if a["spread_strict_lines"]]
    for atom in strict_atoms:
        print(f"  ⚠ {atom['atom']}  أسطر {atom['spread_strict_lines']}")
    for row in data["shared"]:
        if row["spread_strict_lines"]:
            print(f"  ⚠ shared/{row['file']}  أسطر {row['spread_strict_lines']}")
    if not strict_atoms and not any(r["spread_strict_lines"] for r in data["shared"]):
        print("  ✅ موحّدة في الشجرة كلّها")

    print("\n" + "-" * 66)
    print(f"٣ · الحجم — فوق {MAX_EFFECTIVE_LINES} سطرًا فعليًّا")
    print("-" * 66)
    for atom in sorted((a for a in atoms if a["over_limit"]),
                       key=lambda a: -a["lines_effective"]):
        print(f"  ⚠ {atom['atom']:<28}{atom['lines_effective']:>5} سطر")

    print("\n" + "-" * 66)
    print("٤ · الأحداث اليتيمة — يُنشر ولا يسمعه أحد")
    print("-" * 66)
    print(f"  أحداث بيانات: {len(data['orphan_data'])}   "
          f"حالات لوحة: {len(data['orphan_panel'])} (متوقَّع)")
    for row in data["orphan_data"][:40]:
        owners = " · ".join(row["publishers"][:3])
        more = f" (+{len(row['publishers']) - 3})" if len(row["publishers"]) > 3 else ""
        print(f"    ⚠ {row['event']:<38}← {owners}{more}")

    print("\n" + "-" * 66)
    print("٥ · الأحداث المكسورة — يُشترَك به ولا ينشره أحد")
    print("-" * 66)
    if not data["broken"]:
        print("  ✅ لا شيء")
    for row in data["broken"]:
        subs = " · ".join(row["subscribers"][:3])
        print(f"  ⚠ {row['event']:<38}→ {subs}")

    print("\n" + "-" * 66)
    print("٦ · التغطية — اختبارات وتوثيق")
    print("-" * 66)
    no_tests = [a["atom"] for a in atoms if not a["has_tests"]]
    no_hist = [a["atom"] for a in atoms if not a["has_history"]]
    no_expl = [a["atom"] for a in atoms if not a["has_explainer"]]
    print(f"  بلا اختبارات : {len(no_tests)}")
    for name in no_tests[:10]:
        print(f"      ⚠ {name}")
    print(f"  بلا التاريخ.md: {len(no_hist)}")
    for name in no_hist[:10]:
        print(f"      ⚠ {name}")
    print(f"  بلا الشرح.md  : {len(no_expl)}")
    for name in no_expl[:10]:
        print(f"      ⚠ {name}")

    print("\n" + "-" * 66)
    print("٧ · ساعة الحائط — مواضع تقرأ الزمن الجاري")
    print("-" * 66)
    top = sorted((a for a in atoms if a["wall_clock_calls"]),
                 key=lambda a: -a["wall_clock_calls"])[:12]
    for atom in top:
        print(f"    {atom['atom']:<30}{atom['wall_clock_calls']:>4}")
    print("  ملاحظة: ليست كلّها خطأ — الخطأ حين يُقاس بها عمر **بيانات**.")
    print("=" * 66)


def main() -> int:
    data = audit()
    if "--json" in sys.argv:
        print(json.dumps(data, ensure_ascii=False, indent=1))
        return 0
    report(data)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
