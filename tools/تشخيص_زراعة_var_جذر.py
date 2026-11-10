#!/usr/bin/env python3
"""قراءة فقط: «مَن يزرع var/ في جذر المشروع، ولماذا؟» — يُشغَّل من أي مجلد وعلى ويندوز أيضًا.

يقيس ثلاثة مصادر مُتهمة، ولا يكتب شيئًا ولا يمسح شيئًا:
  ١) منطوق core_state_root() في shared/runtime_paths.py (فرع التكرار L249)
  ٢) بقعة رجوع الحوكمة (governance/app.py:56 / vault_ops.py:61 / scripts/start_asset.py:41)
  ٣) مسار system_alerts في governance/server.py (يُحال إلى project_root/rel)
  + يقرأ البيئة: QUANT_CORE_STATE_ROOT / QUANT_RUNTIME_ROOT (setdefault لا يدوس المضبوط)
  + يعرض من داخل var/ الجذر أيّ ذرّة/مُقلِع أنشأه (من أسماء الملفات نفسها)
"""
from __future__ import annotations
import os, sys
from pathlib import Path

HERE = Path(__file__).resolve()
ROOT = HERE.parents[1]                       # <ROOT>/tools/<هذا الملف>
sys.path.insert(0, str(ROOT / "shared"))
sys.path.insert(0, str(ROOT))

def line(tag: str, val) -> None: print(f"  {tag:44s} {val}")

def main() -> int:
    print("═══ تشخيص زراعة var/ في الجذر ═══")
    print(f"  cwd = {Path.cwd()}\n  ROOT = {ROOT}")
    for k in ("QUANT_CORE_STATE_ROOT", "QUANT_RUNTIME_ROOT", "QUANT_CORE_CONFIG", "QUANT_GOV_MARKET",
              "QUANT_ATOMS_ROOT", "NQ_BRIDGE_DB"):
        line(f"env {k}", os.environ.get(k, "غير مضبوط"))
    print("\n── ١) منطوق shared/runtime_paths.core_state_root(code_root=…)")
    try:
        import runtime_paths as rp
    except Exception as exc:
        line("استيراد shared/runtime_paths", f"❌ {exc!r}"); rp = None
    if rp:
        for ctx in [ROOT / "governance", ROOT / "forex_runtime" / "governance", ROOT / "shared"]:
            for mkt in ("", "forex"):
                os.environ.pop("QUANT_CORE_STATE_ROOT", None)
                os.environ.pop("QUANT_RUNTIME_ROOT", None)
                try:
                    got = rp.core_state_root(code_root=ctx, market=mkt)
                except Exception as exc:
                    got = f"🛑 {type(exc).__name__}"
                bad = "🛑 جذرُ المشروع! (var/ سيُنبت هنا)" if Path(str(got)).resolve() == ROOT else ("✓" if str(got) != "🛑" else "⛔")
                line(f"{ctx.relative_to(ROOT)} · market={mkt or '—'}", f"{got}  {bad}")
    print("\n── ٢) بقعات الرجوع في الحوكمة (تُستعمل فقط عند فشل الاستيراد)")
    for f, ln in [("governance/app.py", 56), ("governance/vault_ops.py", 61),
                  ("governance/scripts/start_asset.py", 41), ("governance/server.py", 852)]:
        p = ROOT / f
        if not p.is_file(): line(f, "لا يوجد في هذه الشجرة"); continue
        t = p.read_text(encoding="utf-8").splitlines()
        ctx = [l.strip() for l in t[max(0, ln-4):ln+1]]
        line(f"{f}:{ln}", " ⏎ ".join(x[:60] for x in ctx))
    print("\n── ٣) محتوى var/ الجذر إن وُجد (دليل الفاعل)")
    v = ROOT / "var"
    if not v.is_dir():
        line("var/", "غير موجود ✓")
    else:
        for p in sorted(v.rglob("*")):
            if p.is_file():
                line(str(p.relative_to(v)), f"{p.stat().st_size} ب · {__import__('time').strftime('%Y-%m-%d %H:%M', __import__('time').localtime(p.stat().st_mtime))}")
        print("    ↳ store/*.db ⇒ نواة/ذرّات بمسار نسبي · governance/*.json|log ⇒ حوكمة (app/vault_ops/start_asset)"
              " · snapshots|journal ⇒ run_core/state_root · alerts ⇒ server.py:system_alerts · e2e_*/product_gate_* ⇒ scripts/*")
    print("\n── ٤) هل المرايا تملك شجرة shared/ القانونية (شرط runtime_root)؟")
    for m in ("forex_runtime",):
        for sub in ("shared", "config", "governance"):
            p = ROOT / m / sub
            kind = "وصلة" if p.is_symlink() else ("مجلد" if p.is_dir() else "❌")
            owner = ""
            if sub == "shared" and p.is_dir():
                owner = "· فيه runtime_paths.py" if (p / "runtime_paths.py").is_file() else "· 🛑 بلا runtime_paths.py"
                if (p / "runtime_paths.py").is_file():
                    try:
                        import hashlib
                        a = hashlib.sha256((p / "runtime_paths.py").read_bytes()).hexdigest()[:12]
                        b = hashlib.sha256((ROOT / "shared" / "runtime_paths.py").read_bytes()).hexdigest()[:12]
                        owner += f" · بصمة {a} {'=' if a == b else '≠'} {b}"
                    except Exception: pass
            line(f"{m}/{sub}", f"{kind} {owner}")
    print("\nملاحظة: لا يمسح هذا السكربت var/ ولا يُصلِح شيئًا — قياسٌ فقط.")
    return 0

sys.exit(main())
