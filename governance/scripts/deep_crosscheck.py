#!/usr/bin/env python3
"""تدقيق عميق — المانيفست ضدّ الكود ضدّ الورق.

الجرد السابق قرأ كل مصدر وحده. هذا يقارن المصادر بعضها ببعض، لأنّ العطل
الحقيقيّ يسكن **الفجوة بينها**: مانيفست يَعِد بما لا يفعله الكود، أو كود
يفعل ما لا يعلنه، أو ورقة تصف عقدًا زال.

مقيس ٢٠٢٦-٠٩-٠٧: 581 كان يشترك بـ`strategy.setup.proposed` في الكود
(`atom.py:224`) والمانيفست لا يعلنه — فبدا الحدث يتيمًا وهو موصول.

    python3 governance/scripts/deep_crosscheck.py
    python3 governance/scripts/deep_crosscheck.py --json
"""
from __future__ import annotations

import ast
import json
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
ATOMS = ROOT / "atoms"
SKIP = {"__pycache__", ".pytest_cache"}

_SUB = re.compile(r'subscribe(?:_all)?\(\s*(?:EVENT_\w+|"[^"]+"|\'[^\']+\')')
_PUB = re.compile(r'publish\(\s*(?:EVENT_\w+|"[^"]+"|\'[^\']+\')')
_DYNAMIC = "<dynamic>"
_NAME = re.compile(r'(?:EVENT_\w+|"([^"]+)"|\'([^\']+)\')')


def constants(source: str) -> dict[str, str]:
    """ثوابت الوحدة النصّية — لحلّ `EVENT_X` إلى اسم الحدث."""
    out: dict[str, str] = {}
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return out
    for node in tree.body:
        if not isinstance(node, ast.Assign) or not isinstance(node.value, ast.Constant):
            continue
        if not isinstance(node.value.value, str):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name):
                out[target.id] = node.value.value
    return out


def _resolve(token: str, consts: dict[str, str]) -> str | None:
    token = token.strip()
    if token.startswith(('"', "'")):
        return token.strip("\"'")
    return consts.get(token)


def events_in_code(source: str, consts: dict[str, str]) -> tuple[set[str], set[str]]:
    """أسماء الأحداث كما يستعملها الكود فعلًا — لا كما يعلنها المانيفست."""
    subs: set[str] = set()
    pubs: set[str] = set()
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return subs, pubs
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not node.args:
            continue
        func = node.func
        name = (func.attr if isinstance(func, ast.Attribute)
                else func.id if isinstance(func, ast.Name) else "")
        if name not in ("subscribe", "subscribe_all", "publish"):
            continue
        first = node.args[0]
        value: str | None = None
        dynamic = False
        if isinstance(first, ast.Constant) and isinstance(first.value, str):
            value = first.value
        elif isinstance(first, ast.Name):
            value = consts.get(first.id)
            dynamic = value is None
        else:
            # `self._source_event` أو عنصر حلقة: الاسم يُحسم وقت التشغيل،
            # فلا يمكن استخراجه نصًّا. تُرفع راية بدل ادّعاء الغياب.
            dynamic = True
        if dynamic:
            (subs if name.startswith("subscribe") else pubs).add(_DYNAMIC)
            continue
        if not value:
            continue
        (subs if name.startswith("subscribe") else pubs).add(value)
    return subs, pubs


def config_keys(source: str) -> set[str]:
    """مفاتيح الإعداد التي يقرؤها الكود: `config["x"]` أو `cfg.get("x")`."""
    found: set[str] = set()
    # `cfg.get("x", default)` و`config["x"]` و`cfg.get("x")` — والقيمة
    # الافتراضيّة لا تُنهي النمط، فلا يُغلق القوس عند الاقتباس.
    for match in re.finditer(r'(?:config|cfg|context\.config)'
                             r'(?:\[["\']([^"\']+)["\']\]'
                             r'|\.get\(\s*["\']([^"\']+)["\'])', source):
        found.add(match.group(1) or match.group(2))
    return found


def declared_version(source: str) -> str | None:
    match = re.search(r'^ATOM_VERSION\s*=\s*["\']([^"\']+)["\']', source, re.M)
    return match.group(1) if match else None


def doc_events(text: str) -> set[str]:
    return set(re.findall(r'`([a-z][a-z0-9_]*(?:\.[a-z0-9_]+)+)`', text))


def decorator_events() -> set[str]:
    """أحداث تشترك بها المُغلِّفات المشتركة نيابةً عن الذرّة.

    `@live_analyzer` و`@section_live` ينادِيان `context.subscribe` داخل
    `shared/`، فالذرّة تعلن الحدث في مانيفستها بحقّ وإن خلا `atom.py` منه.
    اعتبار ذلك «معلن بلا استعمال» خطأ قياس لا خطأ ذرّة.
    """
    found: set[str] = set()
    for name in ("live_analysis.py", "section_live.py", "section_contract.py"):
        path = ROOT / "shared" / name
        if not path.is_file():
            continue
        source = path.read_text(encoding="utf-8")
        consts = constants(source)
        subs, pubs = events_in_code(source, consts)
        found |= (subs | pubs)
    found.discard(_DYNAMIC)
    return found


def audit() -> dict:
    inherited = decorator_events()
    rows: list[dict] = []
    for manifest_path in sorted(ATOMS.rglob("manifest.yaml")):
        if any(part in SKIP for part in manifest_path.parts):
            continue
        folder = manifest_path.parent
        atom_file = folder / "atom.py"
        if not atom_file.is_file():
            continue
        try:
            manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError:
            rows.append({"atom": folder.name, "manifest_unreadable": True})
            continue
        source = atom_file.read_text(encoding="utf-8")
        consts = constants(source)
        code_subs, code_pubs = events_in_code(source, consts)
        man_subs = {str(e) for e in (manifest.get("subscribes") or [])}
        man_pubs = {str(e) for e in (manifest.get("publishes") or [])}
        # اشتراك/نشر باسم يُحسم وقت التشغيل يُبطل المقارنة النصّية لهذه
        # الذرّة: لا يصحّ ادّعاء أنّ المعلن «بلا استعمال» وهو قد يكون
        # مستعملًا عبر حقل أو حلقة أو مُغلِّف.
        sub_dynamic = _DYNAMIC in code_subs
        pub_dynamic = _DYNAMIC in code_pubs
        code_subs.discard(_DYNAMIC)
        code_pubs.discard(_DYNAMIC)
        # ما يشترك به المُغلِّف نيابةً عن الذرّة يُحتسب استعمالًا.
        # مُغلِّفات ورابطات تشترك نيابةً عن الذرّة داخل `shared/`، فاسم
        # الحدث لا يظهر في `atom.py` وإن كان الاشتراك قائمًا. `bind_truth`
        # منها: يربط حقول الحقيقة الماليّة بأحداث أصحابها (مقيس ٢٠٢٦-٠٩-٠٧
        # على 585 — بدا «يَعِد ولا يفعل» وهو يقرأ عبر الرابط).
        uses_decorator = any(token in source for token in (
            "live_analyzer", "section_live", "section_atom", "bind_truth"))

        explainer = folder / "الشرح.md"
        history = folder / "التاريخ.md"
        expl_text = explainer.read_text(encoding="utf-8") if explainer.is_file() else ""
        hist_text = history.read_text(encoding="utf-8") if history.is_file() else ""

        code_version = declared_version(source)
        man_version = str(manifest.get("version") or "")
        doc_version = None
        match = re.search(r'\|\s*الإصدار\s*\|\s*`([^`]+)`', expl_text)
        if match:
            doc_version = match.group(1)

        schema = manifest.get("config_schema") or {}
        schema_props = set((schema.get("properties") or {}).keys())
        cfg_declared = set((manifest.get("config") or {}).keys())
        cfg_used = config_keys(source)

        rows.append({
            "atom": folder.name,
            "section": folder.parent.name,
            "id": manifest.get("id"),
            # الكود يفعل ما لا يعلنه المانيفست
            "dynamic_events": sub_dynamic or pub_dynamic,
            "sub_in_code_only": sorted(code_subs - man_subs),
            "pub_in_code_only": sorted(code_pubs - man_pubs),
            # المانيفست يَعِد بما لا يفعله الكود
            "sub_in_manifest_only": [] if (sub_dynamic or uses_decorator)
                                    else sorted(man_subs - code_subs),
            "pub_in_manifest_only": [] if (pub_dynamic or uses_decorator)
                                    else sorted(man_pubs - code_pubs),
            # الإعداد
            # مسارات تُشتقّ من جذر التشغيل (`anchored_state_path`): إعلانها
            # بقيمة ثابتة في المانيفست يكسر الاشتقاق ويثبّت مسارًا خاطئًا
            # عند نقل المشروع. تبقى تجاوزًا اختياريًّا يُقرأ إن وُجد.
            "config_used_not_declared": sorted(
                cfg_used - cfg_declared - {"db_path", "cursor_db", "pair_store_path"}),
            # عيارات `DIAL_DEFAULTS` في `shared/live_analysis.py` تُقرأ عبر
            # المُغلِّف لا من `cfg` مباشرة، فالذرّة تعلنها بحقّ وإن خلا
            # `atom.py` منها (مقيس ٢٠٢٦-٠٩-٠٧ على 25 ذرّة بدت «تعلن ولا
            # تقرأ» وهي تُقرأ من اللوحة فعلًا).
            "config_declared_not_used": [] if uses_decorator else sorted(
                cfg_declared - cfg_used),
            "schema_mismatch": sorted(
                (cfg_declared ^ schema_props) - {"cursor_db", "pair_store_path"}),
            # الإصدارات
            "version_code": code_version,
            "version_manifest": man_version,
            "version_doc": doc_version,
            "version_mismatch": bool(
                code_version and man_version and code_version != man_version),
            "doc_version_stale": bool(
                doc_version and man_version and doc_version != man_version),
            # الورق
            "has_history": history.is_file(),
            "has_explainer": explainer.is_file(),
            "doc_events_gone": sorted(
                doc_events(expl_text) & set()
                if not expl_text else
                {e for e in doc_events(expl_text)
                 if e not in man_pubs and e not in man_subs
                 and (e.startswith(("market.", "feed.", "analysis.", "decision.",
                                    "risk.", "execution.", "storage."))
                      )}),
            "history_lines": len([l for l in hist_text.split("\n")
                                  if l.strip().startswith("|")]),
        })
    return {"atoms": rows}


def _show(title: str, rows: list[dict], key: str, limit: int = 14) -> int:
    hits = [(r["atom"], r[key]) for r in rows if r.get(key)]
    print(f"\n{'-' * 66}\n{title}\n{'-' * 66}")
    if not hits:
        print("  ✅ لا شيء")
        return 0
    print(f"  المصاب: {len(hits)} ذرّة")
    for atom, value in hits[:limit]:
        if isinstance(value, bool):
            row = next((r for r in rows if r["atom"] == atom), {})
            if key == "doc_version_stale":
                shown = "شرح=%s ⇄ مانيفست=%s" % (row.get("version_doc"),
                                                  row.get("version_manifest"))
            else:
                shown = "كود=%s ⇄ مانيفست=%s" % (row.get("version_code"),
                                                  row.get("version_manifest"))
        elif isinstance(value, str):
            shown = value
        else:
            shown = " · ".join(map(str, value[:4]))
        print(f"    ⚠ {atom:<30}{shown}")
    if len(hits) > limit:
        print(f"    … و{len(hits) - limit} غيرها")
    return len(hits)


def main() -> int:
    data = audit()
    if "--json" in sys.argv:
        print(json.dumps(data, ensure_ascii=False, indent=1))
        return 0
    rows = data["atoms"]
    print("=" * 66)
    print("تدقيق عميق — المانيفست ضدّ الكود ضدّ الورق")
    print("=" * 66)
    print(f"\nالذرّات: {len(rows)}")

    print("\n### أ · الكود يفعل ما لا يعلنه المانيفست")
    _show("اشتراك في الكود غير معلن", rows, "sub_in_code_only")
    _show("نشر في الكود غير معلن", rows, "pub_in_code_only")

    print("\n### ب · المانيفست يَعِد بما لا يفعله الكود")
    _show("اشتراك معلن بلا استعمال", rows, "sub_in_manifest_only")
    _show("نشر معلن بلا استعمال", rows, "pub_in_manifest_only")

    print("\n### ج · الإعداد")
    _show("مفتاح يقرؤه الكود وغير معلن", rows, "config_used_not_declared")
    _show("مفتاح معلن لا يقرؤه الكود", rows, "config_declared_not_used")
    _show("المخطّط لا يطابق الإعداد", rows, "schema_mismatch")

    print("\n### د · الإصدارات")
    _show("إصدار الكود ≠ إصدار المانيفست", rows, "version_mismatch")
    _show("إصدار الشرح قديم", rows, "doc_version_stale")

    print("\n### هـ · الورق")
    no_hist = [r["atom"] for r in rows if not r["has_history"]]
    no_expl = [r["atom"] for r in rows if not r["has_explainer"]]
    thin = [r["atom"] for r in rows if r["has_history"] and r["history_lines"] <= 2]
    print(f"\n{'-' * 66}\nبلا التاريخ.md: {len(no_hist)}   بلا الشرح.md: {len(no_expl)}"
          f"   تاريخ بلا سطر تغيير: {len(thin)}\n{'-' * 66}")
    for name in (no_hist + no_expl)[:10]:
        print(f"    ⚠ {name}")
    _show("الشرح يذكر حدثًا ليس في عقد الذرّة", rows, "doc_events_gone")
    print("=" * 66)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
