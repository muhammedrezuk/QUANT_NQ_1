# -*- coding: utf-8 -*-
"""حارس عقود مخازن ٧٠٠-٧٥٠: لا ذرّة تسقط بصمت لأنّ مانيفستها اعتلّ.

⛔ وُلد من علّتين دفع ثمنهما قسمان في يومين:

  ١. **عندي ٢٠٢٦-٠٩-١٦:** مفتاحٌ في `config` غائبٌ عن `config_schema`
     و`additionalProperties: false` ⟹ رفضت النواة ٧١٤ واستبعدت ٧١٥،
     **تسعًا وثلاثين دقيقة توقّفًا** ولا سطر خطأ يقول لماذا.
  ٢. **عند قسم ٤٠٠-٤٤٩ ٢٠٢٦-٠٩-١٨:** مانيفست صار **صفر بايت** بخطأ
     كتابة، فحذفت النواة الذرّة — **ولا شيء قال ذلك حتى سُئل**.

والجامع بينهما أنّ العطب في **الورقة لا في الكود**، فلا اختبارَ ذرّةٍ
يمسّه ولا سجلَّ أخطاء يذكره: الذرّة تختفي، والباقي يبدو أخضر.

⚠️ **وهذا الحارس نفسه وُلد من طفرةٍ نجت**: صيغته الأولى (أداةً في مجلّد
مؤقّت) كانت تطبع «لا config» ثمّ `continue` **بلا زيادة العدّاد** — فمانيفست
جُرّد من `config` كان يخرج بـ«المشاكل = 0». عُطّب عمدًا فظهر ذلك، وصار كلّ
اعتلالٍ يُعدّ لا يُطبع فقط. وانتقل إلى المستودع: أداةٌ في مجلّدٍ مؤقّت
ليست حارسًا — تموت بموت الجلسة.

يُشغَّل بلا وسائط. يخرج بـ1 عند أوّل اعتلال.
"""
from __future__ import annotations

import os
import re
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

try:
    import yaml
except ImportError:  # pragma: no cover
    print("⛔ PyYAML غير متاح — لا فحص")
    raise SystemExit(1)

try:
    import jsonschema
except ImportError:  # pragma: no cover
    print("⛔ jsonschema غير متاح — لا فحص")
    raise SystemExit(1)

ROOT = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), "atoms", "قسم 700-749")

_VERSION = re.compile(r'^ATOM_VERSION = "([^"]+)"', re.M)


def audit() -> list[tuple[str, str]]:
    problems: list[tuple[str, str]] = []

    def bad(atom: str, why: str) -> None:
        problems.append((atom, why))

    for name in sorted(os.listdir(ROOT)):
        folder = os.path.join(ROOT, name)
        if not os.path.isdir(folder):
            continue
        manifest = os.path.join(folder, "manifest.yaml")
        atom_py = os.path.join(folder, "atom.py")
        if not os.path.isfile(atom_py):
            continue  # مجلّد ليس ذرّة
        if not os.path.isfile(manifest):
            bad(name, "لا manifest.yaml — الذرّة لا تُحمَّل")
            continue
        if os.path.getsize(manifest) == 0:
            bad(name, "مانيفست **صفر بايت** — تُحذف الذرّة بصمت")
            continue

        try:
            with open(manifest, encoding="utf-8") as handle:
                loaded = yaml.safe_load(handle)
        except yaml.YAMLError as exc:
            bad(name, "YAML لا يُقرأ: %s" % str(exc).splitlines()[0][:70])
            continue
        # ملفٌّ فيه تعليقات فقط يُحمَّل `None` — ولا ينهار الحارس عليه.
        if not isinstance(loaded, dict):
            bad(name, "مانيفست لا يُنتج قاموسًا (نوعه %s)" % type(loaded).__name__)
            continue

        version = loaded.get("version")
        if not version:
            bad(name, "لا `version` في المانيفست")

        schema = loaded.get("config_schema")
        config = loaded.get("config")
        if schema is None:
            bad(name, "لا `config_schema` — لا عقد يُفحص به")
        elif config is None:
            bad(name, "لا `config` مع وجود `config_schema`")
        else:
            try:
                jsonschema.validate(config, schema)
            except jsonschema.ValidationError as exc:
                where = "/".join(str(x) for x in exc.absolute_path) or "(الجذر)"
                bad(name, "`config` يخالف عقده عند %s: %s" % (where, exc.message[:90]))
            except jsonschema.SchemaError as exc:
                bad(name, "`config_schema` نفسه معتلّ: %s" % str(exc)[:90])

        found = _VERSION.search(open(atom_py, encoding="utf-8").read())
        code_version = found.group(1) if found else None
        if code_version is None:
            bad(name, "لا `ATOM_VERSION` في atom.py")
        elif version and code_version != str(version):
            bad(name, "الإصدار مختلف: atom=%s · manifest=%s" % (code_version, version))

    return problems


def main() -> int:
    problems = audit()
    total = sum(1 for n in os.listdir(ROOT)
                if os.path.isfile(os.path.join(ROOT, n, "atom.py")))
    print("=" * 74)
    print("حارس عقود المانيفست — مخازن ٧٠٠-٧٥٠")
    print("=" * 74)
    if not problems:
        print("سليم: %d ذرّة — كلّ مانيفست يُقرأ، وله عقدٌ يجتازه،" % total)
        print("      وإصداره يطابق كوده.")
        print("\nالاعتلالات = 0")
        return 0
    for atom, why in problems:
        print("  ⛔ %-26s %s" % (atom[:26], why))
    print("\nالاعتلالات = %d" % len(problems))
    print("⚠️ العطب في الورقة لا في الكود: لا اختبار ذرّةٍ يمسّه،")
    print("   والذرّة تختفي من الإقلاع بلا سطر خطأ واحد.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
