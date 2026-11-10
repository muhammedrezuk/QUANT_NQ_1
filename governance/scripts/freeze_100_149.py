#!/usr/bin/env python3
"""مفاتيح تجميد قسم 100-149 (البيانات) — توليد وتحقّق.

بأمر المالك ٢٠٢٦-٠٩-١٩: القسم مختومٌ ومجمّد، يُمنع لمسه أو تعديل حرف فيه.
هذه الأداة تُثبت التجميد بالقياس لا بالثقة:

    python governance/scripts/freeze_100_149.py --seal   # توليد المفاتيح
    python governance/scripts/freeze_100_149.py          # تحقّق

كل ملفّ يحمل بصمة SHA-256 مستقلّة، وفوقها بصمة جذر واحدة للقسم كلّه.
تعديل حرف واحد يكسر بصمة ملفّه وبصمة الجذر معًا، فيظهر الملفّ باسمه.

⚠️ **والبصمة لا تعرف الحياة** — وهذا القسم يختلف عن 700-749 في مصدر الحياة:

  * 700-749 قسمٌ باردٌ لا يُحمَّل ساخنًا، فالحيّ يُقرأ من **اللقطة**.
  * وهذا القسم **ساخن**: حفظ `atom.py` نشرٌ حيّ لحظةَ الحفظ (مقيس ٢٠٢٦-٠٩-١٠)،
    لكنّ **ثلاث عشرة ذرّة من أربع عشرة لا تُعرّف `snapshot()` أصلًا** فلا
    لقطةَ تُقرأ منها. فالحيُّ هنا يُقرأ من النواة مباشرة
    (`/api/atoms/<id>`)، وإن لم تُجب سُجّل ذلك صراحةً ولم يُدَّعَ علمٌ ليس
    عندنا.

⚠️ **وفارقٌ ثانٍ خاصٌّ بهذا القسم:** `atom.py` يصل حيًّا فور حفظه، **و`config`
من المانيفست لا يصل بلا إقلاع** (مقيس ٢٠٢٦-٠٩-١٦ على ١٠٩: عيارات المالك
المختومة كانت على القرص ولم تبلغ السوق، والشارة خضراء). فمطابقةُ الإصدار
لا تعني أنّ العيارات الحيّة هي المختومة.

⚠️ **و١٠٧ معطّلة بقرار المالك** (`startup_mode: manual`، ولا ناشر لـ
`market.trade`). فغيابها عن النواة **ليس انحرافًا**، ولا يُصرخ عليه: حارسٌ
يكذب مرّةً يُدرَّب على تجاهله في الثانية.
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SECTION = ROOT / "atoms" / "قسم 100-149"
# ٢٠٢٦-٠٩-٢٤ (ختم Nq صلح): نقل المالك الورقَ كلّه إلى `ورق/` ٢٢:٥٦ فذهب
# `ورق/أختام/` إلى السلّة — والمكان الواحد للأختام قسم ١٢ من الورق.
KEYS = ROOT / "ورق" / "١٢_الأوامر_والأختام" / "أختام التجميد" / "أختام" / "تجميد_قسم_100-149.json"
CORE_API = "http://127.0.0.1:8010/api/atoms/%s"
CORE_TIMEOUT_S = 4.0
SKIP = {"__pycache__", ".pytest_cache"}

#: ما لا يُعدّ انحرافًا في الإصدار — غيابٌ مقصود لا خلل
_MANUAL = "معطّلة بقرار المالك (manual)"
_NO_CORE = "⛔ النواة لا تُجيب"
_EXPECTED_NO_LIVE = (_MANUAL, _NO_CORE)


def files() -> list[Path]:
    out = [p for p in SECTION.rglob("*")
           if p.is_file() and not any(part in SKIP for part in p.parts)
           # ٢٠٢٦-٠٩-٢٣: بقايا بايتكود `*.pyc.tmp` ليست من القسم (نظير ١٥٠-١٩٩).
           and not p.name.endswith(".pyc.tmp")]
    return sorted(out, key=lambda p: p.relative_to(SECTION).as_posix())


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _folders() -> list[Path]:
    return sorted(d for d in SECTION.iterdir()
                  if d.is_dir() and (d / "manifest.yaml").exists())


def _is_manual(folder: Path) -> bool:
    text = (folder / "manifest.yaml").read_text(encoding="utf-8", errors="replace")
    return re.search(r'^\s*startup_mode:\s*manual\s*$', text, re.M) is not None


def live_versions() -> dict:
    """الإصدار العامل فعلًا لكلّ ذرّة — من النواة لا من الكود.

    يُكتب داخل الختم كي لا يُقرأ «مختومٌ سليم» على أنّه «مختومٌ حيّ».
    """
    out: dict[str, str] = {}
    for folder in _folders():
        atom_id = folder.name.split("_")[0]
        try:
            with urllib.request.urlopen(CORE_API % atom_id,
                                        timeout=CORE_TIMEOUT_S) as response:
                body = json.loads(response.read().decode("utf-8"))
            out[atom_id] = str(body.get("version") or "؟")
        except (urllib.error.HTTPError, urllib.error.URLError, OSError,
                ValueError, TimeoutError):
            out[atom_id] = _MANUAL if _is_manual(folder) else _NO_CORE
    return out


def code_versions() -> dict:
    """الإصدار المكتوب في `atom.py` — يُقارَن بالحيّ فيظهر فارقٌ إن وُجد."""
    out: dict[str, str] = {}
    for folder in _folders():
        source = folder / "atom.py"
        if not source.is_file():
            continue
        text = source.read_text(encoding="utf-8", errors="replace")
        match = re.search(r'^ATOM_VERSION\s*=\s*"([^"]+)"', text, re.M)
        out[folder.name.split("_")[0]] = match.group(1) if match else "؟"
    return out


def build() -> dict:
    entries = {p.relative_to(SECTION).as_posix(): digest(p) for p in files()}
    root = hashlib.sha256(
        "\n".join(f"{k}:{v}" for k, v in entries.items()).encode("utf-8")
    ).hexdigest()
    atoms = sorted(d.name for d in _folders())
    return {"section": "قسم 100-149", "frozen": True,
            "authority": "أمر المالك المباشر ٢٠٢٦-٠٩-١٩",
            "atom_count": len(atoms), "file_count": len(entries),
            "atoms": atoms, "root": root, "files": entries}


def _drift(code: dict, live: dict) -> dict:
    return {a: {"كود": code.get(a), "حيّ": live.get(a)}
            for a in code
            if live.get(a) not in (code.get(a), None) + _EXPECTED_NO_LIVE}


def seal() -> int:
    data = build()
    live = live_versions()
    code = code_versions()
    data["code_versions"] = code
    data["live_versions"] = live
    drift = _drift(code, live)
    data["version_drift"] = drift
    KEYS.parent.mkdir(parents=True, exist_ok=True)
    KEYS.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n",
                    encoding="utf-8")
    print("🔒 خُتم قسم 100-149")
    print(f"   ذرّات : {data['atom_count']}")
    print(f"   ملفّات: {data['file_count']}")
    print(f"   الجذر : {data['root']}")
    print(f"   المفاتيح: {KEYS.relative_to(ROOT)}")
    unseen = [a for a, v in live.items() if v == _NO_CORE]
    if unseen:
        print("   ⚠️ لم تُقرأ حيًّا (النواة لا تُجيب): " + " · ".join(unseen))
    if drift:
        print("   ⚠️ إصداراتٌ على القرص لا تعمل حيًّا — الختم يسجّلها ولا يخفيها:")
        for atom_id, pair in drift.items():
            print(f"      {atom_id}: كود {pair['كود']} · حيّ {pair['حيّ']}")
    else:
        print("   ✔ كلّ إصدارٍ مختومٍ هو العامل حيًّا")
    return 0


def _git_knows(path: Path) -> bool:
    """هل يتتبّع المستودعُ هذا المسار؟ (سؤالٌ عن الفهرس لا عن القرص)"""
    try:
        return subprocess.run(
            ["git", "ls-files", "--error-unmatch", "--", str(path)],
            cwd=ROOT, capture_output=True).returncode == 0
    except OSError:
        return False


def verify() -> int:
    if not KEYS.is_file():
        # ٢٠٢٦-٠٩-١٩ — كان الردّ واحدًا: «لا مفاتيح — شغّل `--seal` أوّلًا».
        #
        # وهو **دعوةٌ إلى الختم الأعمى**: ختمٌ زال من الشجرة يُقرأ «لم
        # يُختم بعد»، فيختم القارئُ على حالةٍ لم يراجعها أحد فيُثبّت ما
        # تغيّر في غيابه ويدفنه. وقعتُ فيها اليوم بنفسي حين اختفت أختام
        # أربعة أقسام من مسارها ولم أعرف: أزائلةٌ هي أم لم تُكتب قطّ.
        #
        # والمستودع يعرف الفرق، فيُسأل. (الفكرة من جلسة 700-749،
        # ونُقلت إلى هنا لأنّ الأداتين من أصلٍ واحد وترثان العطب نفسه.)
        if _git_knows(KEYS):
            print("🚨 الختم زال من الشجرة — والمستودع يعرفه.")
            print(f"   المفقود: {KEYS.relative_to(ROOT)}")
            print("   استرجعه، ولا تختم على حالةٍ لم تُراجَع:")
            print(f'      git checkout -- "{KEYS.relative_to(ROOT).as_posix()}"')
            print("   ⛔ ولا تشغّل --seal قبل التحقّق: إعادةُ الختم على شجرةٍ")
            print("      تغيّرت في غيابك تُثبّت التغيير وتدفنه بدل أن تكشفه.")
            return 1
        print("❌ لا مفاتيح — القسم لم يُختم بعد. شغّل --seal")
        return 2
    saved = json.loads(KEYS.read_text(encoding="utf-8"))
    now = build()

    changed = [k for k, v in now["files"].items()
               if k in saved["files"] and saved["files"][k] != v]
    added = [k for k in now["files"] if k not in saved["files"]]
    removed = [k for k in saved["files"] if k not in now["files"]]

    if now["root"] == saved["root"]:
        print("🔒 قسم 100-149 مجمّد وسليم — مطابق للختم.")
        print(f"   {saved['atom_count']} ذرّة · {saved['file_count']} ملفًّا")
        print(f"   الجذر: {saved['root']}")
        # والبصمة لا تعرف الحياة: يُقارَن المختوم بالعامل الآن
        drift = _drift(saved.get("code_versions") or {}, live_versions())
        if drift:
            print("   ⚠️ الملفّات مطابقة لكنّ الحيّ يعمل بإصدارٍ آخر:")
            for atom_id, pair in drift.items():
                print(f"      {atom_id}: مختوم {pair['كود']} · حيّ {pair['حيّ']}")
        return 0

    print("❌ الختم مكسور — القسم مجمّد ولا يُمسّ.")
    print(f"   الجذر المختوم: {saved['root']}")
    print(f"   الجذر الحالي : {now['root']}")
    for label, items in (("تُغيّرت", changed), ("أُضيفت", added),
                         ("حُذفت", removed)):
        for item in items:
            print(f"   {label}: {item}")
    return 1


if __name__ == "__main__":
    raise SystemExit(seal() if "--seal" in sys.argv else verify())
