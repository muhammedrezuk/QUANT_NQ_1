#!/usr/bin/env python3
"""حارسٌ يمنع النمط الذي تكرّر أربع مرّات: عملٌ ثقيل يُنتظَر في معالج.

المعالج ميزانيّته **٥٠ م.ث** (`handler timeout` في ناقل النواة). وأربع مرّات
في أربعة أيّام وقع النمط نفسه في نطاق المخازن — ثلاثًا في ٧٠٧ وواحدةً في ٨٠٠:

    ٧٠٧ v4.16.0  انتظارُ قفلٍ مشترك عند الإدراج      ١١٬٤٧١٫٨ م.ث
    ٧٠٧ v4.17.0  انتظارُ دفعةٍ ممتلئة                ٢٥٬٥٣٤٫٤
    ٧٠٧ v4.18.0  انتظارُ الإنفاذ على القفل نفسه      ٢٦٬٢٥٦٫٥
    ٨٠٠ v2.4.0   انتظارُ نسخةٍ احتياطيّة ١٥ ج.ب      ← خمسة أيّام بلا نسخة

ولم يُكتشف أيٌّ منها بحارسٍ عندي — اكتُشفت ببلاغٍ من جلسةٍ أخرى بعد وقوعها.
فهذا يُغلق البابَ بدل أن يُصلح عطبًا بعد عطب.

    python governance/checks/check_handler_waits.py

**القاعدة:** دالّةٌ على مسار الحدث (مشترَكٌ بها في `manifest.yaml`، أو
`_on_*`/`_store`/`handler`) لا تحوي `await` على عملٍ ثقيل: قفلٌ مشترك
(`file_lock` · `_conn_lock` · `acquire`) أو قرصٌ (`sqlite3` · `tarfile` ·
`enforce_limits` · `_run_backup` · `_flush_buffer`).

**والمسموح بيان:** `to_thread` على دالّةٍ تطلب القفل **بمهلة** ثمّ تتخطّى
(نمطُ `_LockBusy`/`enforce_skipped`)، و`create_task` لأنّه لا يُنتظَر.
"""
from __future__ import annotations

import ast
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
SECTIONS = ("قسم 700-749", "قسم 800-849")

#: أسماءٌ تدلّ على عملٍ ثقيل إن وقعت تحت `await` في معالج
HEAVY = ("enforce_limits", "_enforce_limits", "_run_backup", "_flush_buffer",
         "_insert_many", "_archive_one", "_clean_one", "_ensure_store",
         "backup", "vacuum", "_execute")
#: وما يدلّ على قفلٍ مشترك
LOCKS = ("file_lock", "_conn_lock", "acquire", "_lock")
#: أسماءُ المعالِجات — ما يُنادى من الناقل
HANDLER_HINTS = ("_on_", "_store", "handler", "_handle")
#: ما يُعفى: جدولةٌ لا تُنتظَر، أو انتظارٌ بمهلة
SAFE_CALLS = ("create_task", "ensure_future")


def _name(node: ast.AST) -> str:
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Call):
        return _name(node.func)
    return ""


def _is_handler(fn: ast.AsyncFunctionDef) -> bool:
    return any(hint in fn.name for hint in HANDLER_HINTS)


def _bounded_waiters(tree: ast.AST) -> set[str]:
    """دوالُّ تطلب القفل **بمهلة** ثمّ تتخطّى — فانتظارُها محدودٌ بالتصميم.

    ⚠️ **بلا هذا يصرخ الحارس على ما أُصلح.** ٧٠٧ يُنادى فيه `_enforce_limits`
    من المعالج، لكنّ `_enforce_limits_locked` صار `acquire(timeout=...)`
    ويعود فورًا إن كان القفل مشغولًا — فالانتظار سقفُه خمس مئاتٍ من الثانية
    لا ثلاثون. وحارسٌ يكذب مرّةً يُدرَّب على تجاهله في الثانية؛ وقعتُ في هذا
    مع أداة التجميد (٧١٧ و٧١٩ «بلا لقطة») فلا أُعيده.

    والنمطُ المعترَف به: `acquire(timeout=…)` داخل جسم الدالّة. وما عداه —
    `with lock:` المجرّد — انتظارٌ مفتوح.
    """
    safe: set[str] = set()
    for fn in ast.walk(tree):
        if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for node in ast.walk(fn):
            if (isinstance(node, ast.Call) and _name(node) == "acquire"
                    and any(kw.arg == "timeout" for kw in node.keywords)):
                safe.add(fn.name)
                break
    return safe


def _resolve(name: str, tree: ast.AST, bounded: set[str]) -> bool:
    """هل هذا النداء — أو ما يناديه مباشرةً — محدودُ الانتظار؟"""
    if name in bounded:
        return True
    for fn in ast.walk(tree):
        if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if fn.name != name:
            continue
        for node in ast.walk(fn):
            if isinstance(node, ast.Call):
                inner = _name(node)
                if inner == "to_thread" and node.args:
                    inner = _name(node.args[0])
                if inner in bounded:
                    return True
    return False


def audit(path: pathlib.Path) -> list[tuple[int, str, str]]:
    """كلّ `await` ثقيل داخل معالجٍ في هذا الملفّ."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
    except SyntaxError as exc:
        return [(exc.lineno or 0, "⛔ صياغة", str(exc))]
    found: list[tuple[int, str, str]] = []
    bounded = _bounded_waiters(tree)
    for fn in ast.walk(tree):
        if not isinstance(fn, ast.AsyncFunctionDef) or not _is_handler(fn):
            continue
        for node in ast.walk(fn):
            if not isinstance(node, ast.Await):
                continue
            call = node.value
            if not isinstance(call, ast.Call):
                continue
            label = _name(call)
            if label in SAFE_CALLS:
                continue
            # `to_thread(fn, …)` — يُقرأ اسمُ ما يُشغَّل لا اسمُ الغلاف
            inner = label
            if label == "to_thread" and call.args:
                inner = _name(call.args[0])
            blob = ast.dump(call)
            heavy = any(h in inner for h in HEAVY)
            locked = any(k in blob for k in LOCKS)
            if not (heavy or locked):
                continue
            if _resolve(inner, tree, bounded):
                continue                      # انتظارٌ محدودٌ بمهلة — لا يُحجب
            found.append((node.lineno, fn.name, inner or label or "?"))
    return found


def main() -> int:
    problems = 0
    checked = 0
    for section in SECTIONS:
        base = ROOT / "atoms" / section
        if not base.is_dir():
            continue
        for atom_dir in sorted(base.iterdir()):
            source = atom_dir / "atom.py"
            if not source.is_file():
                continue
            checked += 1
            hits = audit(source)
            if not hits:
                continue
            problems += len(hits)
            print("⛔ %s" % atom_dir.name)
            for line, fn, what in hits:
                print("      %s:%d  في `%s` يُنتظَر `%s`"
                      % (source.name, line, fn, what))
    print()
    print("ذرّات فُحصت: %d · انتظارٌ ثقيل في معالج: %d" % (checked, problems))
    if problems:
        print("القاعدة: العمل الثقيل يُجدوَل (`create_task`) أو يُطلب القفل")
        print("         بمهلةٍ ثمّ يُتخطّى — ولا يُنتظَر في معالج.")
        return 1
    print("✔ لا معالجَ ينتظر قفلًا مشتركًا ولا كتابةَ قرص.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
