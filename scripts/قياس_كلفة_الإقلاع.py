# -*- coding: utf-8 -*-
"""كم تكلّف كلُّ ذرّةٍ عند الإقلاع — بالقياس المباشر لا بالنسبة.

**لماذا بُنيت:** جُرِّب قياسُ الكلفة بالفارق بين طابعَي `started` متتاليَين
في جورنال النواة، ونُسب الفارقُ إلى الذرّة التي **أنهت** الفجوة. والنتيجة
كانت خاطئةً بآلاف الأضعاف (مقيس ٢٠٢٦-٠٩-٢٢):

```
467  نُسب إليها 20,024 م.ث   ⟸  والحقيقة 2.31 م.ث   (8,700×)
360  نُسب إليها  7,233 م.ث   ⟸  والحقيقة  264 م.ث   (   27×)
```

والسبب بنيويّ: **الفارق بين طابعين ليس كلفةَ مَن أنهاه** — هو كلُّ ما جرى
على الحلقة بينهما (عملُ ذرّاتٍ مجدوَلة، وانتظارُ مهامّ سابقة، وكلفةُ
النواة نفسها). ونسبتُه إلى الأخير تُلصق الكلفةَ بالبريء.

**وهذا يقيس ما يملكه كلُّ واحدٍ فعلًا:** يستورد الذرّة في هذه العمليّة،
ويناديها `initialize` ثمّ `start` ثمّ `restore` **بلقطتها من القرص**،
ويقيس بـ`perf_counter`. لا نواةَ ولا جورنال ولا نسبة.

⛔ ولا يمسّ المنصّة: سياقٌ صامت، ولا اتّصالَ بمخزنٍ حيّ، ولا نشر.
⚠️ وحدُّه معلَن: يقيس **دورة الحياة** لا زمنَ التشغيل. وذرّةٌ رخيصةُ
   الإقلاع قد تكون باهظةً على التِكّة — ذاك قياسٌ آخر.

    python scripts/قياس_كلفة_الإقلاع.py              كلّ الذرّات
    python scripts/قياس_كلفة_الإقلاع.py 467 360 580  ذرّاتٍ بعينها
    python scripts/قياس_كلفة_الإقلاع.py --top 20     أغلى عشرين
"""
from __future__ import annotations

import argparse
import asyncio
import importlib.util
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import yaml  # noqa: E402

SNAPSHOTS = ROOT / "forex_runtime" / "var" / "forex" / "snapshots"


class _Log:
    def __getattr__(self, name):
        return lambda *a, **k: None


class _Ctx:
    """سياقٌ صامت — يبتلع الاشتراك والنشر ولا يمسّ ناقلًا."""

    def __init__(self, config, atom_id=""):
        self.config = config
        self.logger = _Log()
        # بعضُ الذرّات تقرأ هويّتها من السياق — تُعطى ولا تُخترع.
        self.atom_id = atom_id
        self.account_id = ""
        self.broker = ""

    def subscribe(self, name, handler):
        return None

    async def publish(self, name, payload):
        return None


def _folders(ids):
    out = []
    for path in sorted(ROOT.glob("atoms/*/*")):
        if not (path.is_dir() and path.name[:3].isdigit()):
            continue
        if ids and path.name[:3] not in ids:
            continue
        if (path / "atom.py").exists() and (path / "manifest.yaml").exists():
            out.append(path)
    return out


async def measure(folder: Path) -> dict:
    num = folder.name[:3]
    row = {"id": num, "name": folder.name[4:28], "init": None, "start": None,
           "restore": None, "total": None, "snapshot_kb": None, "error": ""}
    snap = SNAPSHOTS / ("%s.json" % num)
    if snap.exists():
        row["snapshot_kb"] = snap.stat().st_size / 1024.0
    try:
        manifest = yaml.safe_load((folder / "manifest.yaml").read_text(encoding="utf-8"))
        # ⛔ الذرّةُ تستورد وحداتٍ جانبيّةً من مجلّدها (`rules_store` وأخواتها)،
        #    والنواةُ تضع مجلّدها في المسار عند التحميل. فبلا هذا تسقط سبعُ
        #    ذرّاتٍ بـ`No module named` — ومنها التي نبحث عنها.
        if str(folder) not in sys.path:
            sys.path.insert(0, str(folder))
        spec = importlib.util.spec_from_file_location("boot_%s" % num, folder / "atom.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        atom = module.Atom()
    except Exception as exc:  # noqa: BLE001
        row["error"] = "استيراد: %s" % str(exc)[:60]
        return row
    context = _Ctx(dict(manifest.get("config") or {}), num)
    try:
        mark = time.perf_counter()
        await atom.initialize(context)
        row["init"] = (time.perf_counter() - mark) * 1000.0
        mark = time.perf_counter()
        await atom.start()
        row["start"] = (time.perf_counter() - mark) * 1000.0
    except Exception as exc:  # noqa: BLE001
        row["error"] = "دورة الحياة: %s" % str(exc)[:60]
        return row
    if snap.exists() and hasattr(atom, "restore"):
        try:
            raw = json.loads(snap.read_text(encoding="utf-8"))
            payload = raw.get("state", raw) if isinstance(raw, dict) else raw
            mark = time.perf_counter()
            await atom.restore(payload)
            row["restore"] = (time.perf_counter() - mark) * 1000.0
        except Exception as exc:  # noqa: BLE001
            row["error"] = "استعادة: %s" % str(exc)[:60]
    row["total"] = sum(v for v in (row["init"], row["start"], row["restore"]) if v)
    try:
        await atom.stop()
    except Exception:  # noqa: BLE001
        pass
    return row


async def run(ids, top: int) -> None:
    folders = _folders(set(ids))
    print("=== كلفةُ دورة الحياة — قياسٌ مباشر لا نسبة · %d ذرّة ===" % len(folders))
    rows = []
    for folder in folders:
        rows.append(await measure(folder))
    ok = [r for r in rows if r["total"] is not None]
    bad = [r for r in rows if r["total"] is None]
    ok.sort(key=lambda r: -r["total"])
    shown = ok[:top] if top else ok
    print("\n  %-5s %-26s %9s %9s %9s %10s %s"
          % ("ذرّة", "الاسم", "تهيئة", "إقلاع", "استعادة", "الإجمالي", "لقطة ك.ب"))
    for r in shown:
        print("  %-5s %-26s %8.2f %9.2f %9s %9.2f %10s"
              % (r["id"], r["name"], r["init"] or 0.0, r["start"] or 0.0,
                 ("%.2f" % r["restore"]) if r["restore"] is not None else "—",
                 r["total"], ("%.0f" % r["snapshot_kb"]) if r["snapshot_kb"] else "—"))
    total = sum(r["total"] for r in ok)
    print("\n  مجموعُ الذرّات المقيسة: %.2f م.ث  (%.2f ثانية) من %d ذرّة"
          % (total, total / 1000.0, len(ok)))
    print("  وما زاد على هذا في زمن الإقلاع الحقيقيّ فهو **كلفة النواة نفسها**")
    print("  (اقسمه على `/api/boot-report`: `finished_at` − `started_at`).")
    if bad:
        print("\n  لم تُقَس (%d):" % len(bad))
        for r in bad[:12]:
            print("    %-5s %-26s %s" % (r["id"], r["name"], r["error"]))


def main() -> None:
    parser = argparse.ArgumentParser(description="كلفةُ إقلاع كلّ ذرّة — مباشرةً")
    parser.add_argument("ids", nargs="*", help="أرقام ذرّات؛ الفراغ = الكلّ")
    parser.add_argument("--top", type=int, default=0, help="أغلى N فقط")
    args = parser.parse_args()
    asyncio.run(run(args.ids, args.top))


if __name__ == "__main__":
    main()
