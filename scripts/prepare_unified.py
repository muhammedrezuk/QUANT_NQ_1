"""Create/repair the shared-atom links in a unified QUANT_NQ checkout.

Windows uses directory junctions (no administrator privilege is normally
needed); POSIX uses relative symlinks. The original ``atoms/`` tree is never
copied or modified.

العقد (فصل ٢٣ من تقرير المسارات، ٢٠٢٦-٠٩-٠٣): وجود مجلّد **حقيقيّ** مكان وصلة
معلَنة ليس «حالة مقبولة» — هو مصدر الانفصال: النسخة الحقيقية تُقِلع على
``<mirror>/shared`` فتقرأ المحرّكات جذرًا، وتقرأ اللوحة (التي تحسب
``ROOT.parent/<runtime>``) جذرًا آخر. لذلك:

* ``--verify-only`` صار صارمًا: مجلّد حقيقيّ محلّ وصلة = فشل، مع تشخيص إن كان
  محتواه مطابقًا للهدف (وعندها يصلحه ``--convert-identical``) أو منصرفًا.
* ``--convert-identical``: يحوّل المجلّد الحقيقيّ إلى وصلة **فقط** إذا طابق
  محتواه الهدف بايت-ببايت، ويُبقي النسخة القديمة بجانبه تحت
  ``<name>.pre-junction-backup/`` — لا حذف ولا مسح لبيانات حيّة.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LAYOUT = ROOT / "config" / "unified_layout.json"
BACKUP_SUFFIX = ".pre-junction-backup"


def _atom_dir(root: Path, atom_id: int) -> Path:
    matches = sorted(root.glob(f"{atom_id:03d}_*"))
    if not matches:
        matches = sorted(root.glob(f"{atom_id}_*"))
    if not matches:
        raise FileNotFoundError(f"atom {atom_id} is missing under {root}")
    return matches[0]


def _is_link(path: Path) -> bool:
    if path.is_symlink():
        return True
    is_junction = getattr(path, "is_junction", None)      # Python 3.12+
    try:
        return bool(is_junction()) if is_junction is not None else False
    except OSError:
        return False


def _remove(path: Path) -> None:
    if path.is_symlink() or path.is_file():
        path.unlink()
    elif path.exists():
        shutil.rmtree(path)


def _tree_digest(root: Path) -> tuple[str | None, int, str]:
    """بصمة شجرة (hash لكل ملفّ نسبيًا). يرجع (digest|None عند اختلاف، عدد، أول الفرق)."""
    files: dict[str, str] = {}
    for p in sorted(root.rglob("*")):
        rel = p.relative_to(root).as_posix()
        if p.is_symlink():
            return None, 0, f"symlink:{rel}"
        if not p.is_file():
            continue
        h = hashlib.sha256()
        with p.open("rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 20), b""):
                h.update(chunk)
        files[rel] = h.hexdigest()
    return files, len(files), "identical"


def _compare_trees(target: Path, link: Path) -> tuple[bool, str]:
    """هل شجرة ``link`` مطابقة لـ``target`` في كل ملفّاتها؟ (زيادات link مسموحة:
    لقطة سلامة/أصول UI مبنية — المقصود «لم يَنفصل محتوى مشترك»)."""
    t_files, t_n, why = _tree_digest(target)
    if t_files is None:
        return False, f"target has {why} under {target}"
    l_files, l_n, _ = _tree_digest(link)
    if l_files is None:
        return False, f"symlink found inside {link}"
    for rel, digest in t_files.items():
        got = l_files.get(rel)
        if got is None:
            return False, f"missing in copy: {rel}"
        if got != digest:
            return False, f"drift: {rel}"
    return True, f"{t_n} files match ({l_n} present)"


def _make_link(link: Path, target: Path, *, convert_identical: bool = False) -> str:
    link.parent.mkdir(parents=True, exist_ok=True)
    if link.is_symlink() or _is_link(link):
        if link.resolve() == target.resolve():
            return "kept"
        _remove(link)
    elif link.is_dir():
        # مجلّد حقيقيّ محلّ وصلة: مسموح فقط بالتحويل اللا-تخريبيّ وبعد مطابقة كاملة
        same, why = _compare_trees(target, link)
        if not convert_identical:
            raise RuntimeError(
                "real directory where a link is contracted "
                f"(content {'identical' if same else 'DIFFERS'} — {why}); "
                "rerun with --convert-identical to replace it with a link "
                "(the current copy is kept as a backup, nothing is deleted)")
        if not same:
            raise RuntimeError(
                f"refusing to convert: content diverged from target ({why})")
        backup = link.with_name(link.name + BACKUP_SUFFIX)
        if backup.exists():
            raise RuntimeError(f"backup already exists, resolve first: {backup}")
        link.rename(backup)
    elif link.exists():
        _remove(link)

    _converted = "backup" in locals()
    relative = os.path.relpath(target, link.parent)
    if os.name == "nt":
        # Junctions work on standard Windows installations without requiring
        # Developer Mode or a SeCreateSymbolicLink privilege.
        result = subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(link), str(target)],
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or result.stdout.strip())
    else:
        link.symlink_to(relative, target_is_directory=True)
    return "converted" if _converted else "created"


def _link_status(link: Path, target: Path) -> str:
    """"ok" | "missing" | "junction" | "real-dir-drift" | "real-dir-identical"."""
    if not link.exists():
        return "missing"
    if link.is_symlink() or _is_link(link):
        return "ok" if link.resolve() == target.resolve() else "junction"
    if link.is_dir():
        same, _why = _compare_trees(target, link)
        return "real-dir-identical" if same else "real-dir-drift"
    return "junction"


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare the forex runtime links")
    parser.add_argument("--verify-only", action="store_true")
    parser.add_argument("--convert-identical", action="store_true",
                        help="replace real directories that are byte-identical to their "
                             "target with the contracted link (non-destructive backup)")
    args = parser.parse_args()

    data = json.loads(LAYOUT.read_text(encoding="utf-8"))
    atoms = ROOT / "atoms"
    # ٢٠٢٦-٠٩-٠٧ (قرار المالك): سوق واحد. حُذفت الشجرة الثانية
    # وروابطها المشتركة — مشروع مستقلّ على جهاز آخر.
    failures: list[str] = []
    notes: list[str] = []
    created = kept = converted = 0

    # Relative runtime paths used by the shared atoms (for example 007's
    # watched_dirs and the storage atoms' var/store paths) are namespaced per
    # market working directory. These links expose only the selected market's
    # atom root plus read-only code; databases still live below each
    # runtime's own working directory.
    runtime_targets = {"forex_runtime": "atoms"}
    runtime_common = [
        "transport", "security", "clock", "catchup", "scripts", "tools",
        "shared", "governance", "config", "mt5", "core",
    ]
    for runtime_name, atom_target in runtime_targets.items():
        runtime = ROOT / runtime_name
        runtime.mkdir(parents=True, exist_ok=True)
        for name in ["atoms", *runtime_common]:
            target = ROOT / (atom_target if name == "atoms" else name)
            link = runtime / name
            try:
                if args.verify_only:
                    status = _link_status(link, target)
                    if status == "ok":
                        continue
                    if status == "real-dir-identical":
                        notes.append(
                            f"{link}: نسخة كاملة مطابقة للهدف ({name}) — العقد وصلة؛ "
                            "الإصلاح بـ«--convert-identical» (يبقى احتياط بجانبها)")
                        failures.append(
                            f"[{status}] {link} -> {target}  (identical — --convert-identical)")
                        continue
                    failures.append(f"[{status}] {link} -> {target}")
                    continue
                result = _make_link(link, target, convert_identical=args.convert_identical)
                if result == "created":
                    created += 1
                elif result == "converted":
                    converted += 1
                else:
                    kept += 1
            except Exception as exc:  # noqa: BLE001
                failures.append(f"{link}: {exc}")

    if failures:
        print("Unified-link preparation failed:")
        for failure in failures:
            print("  " + failure)
        for note in notes:
            print("  ℹ " + note)
        return 2
    print(f"Unified links OK: {created} created, {converted} converted, {kept} already present")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
