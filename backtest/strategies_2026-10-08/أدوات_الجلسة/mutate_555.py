"""فحص طفرات على نسخةٍ في المسودّة فقط: هل تسقط الاختبارات المحدّثة حين يُكسر حارس؟"""
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(r"C:\Users\NQ\QUANT_NQ")
SRC = next((ROOT / "atoms" / "قسم 550-599").glob("555_*"))
SCRATCH = Path(__file__).resolve().parent / "mut555"
PY = str(ROOT / "vendor" / "python" / "runtime" / "python.exe")

MUTATIONS = {
    "fallback_stop": ("        if stop is None or stop <= 0.0:\n            await self._decline(REASON_NO_STOP",
                      "        if stop is None and price:\n            stop = price - 0.5 if side == SIDE_BUY else price + 0.5\n        if stop is None or stop <= 0.0:\n            await self._decline(REASON_NO_STOP"),
    "positions_unknown_open": ("        if not self._positions_seen:", "        if False:"),
    "no_inflight_guard": ("        flying = self._inflight_for(symbol)", "        flying = 0"),
    "send_economics_off": ("        if why:\n            self._send_blocked", "        if False:\n            self._send_blocked"),
    "stop_from_513": ("        if stop is None or stop <= 0.0:\n            await self._decline(REASON_NO_STOP",
                      "        stop = _number(size.get('buy_stop' if side == SIDE_BUY else 'sell_stop')) or stop\n        if stop is None or stop <= 0.0:\n            await self._decline(REASON_NO_STOP"),
    "no_resize": ("            volume = resized\n", "            pass\n"),
}

for name, (old, new) in MUTATIONS.items():
    target = SCRATCH / name / "555"
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(SRC, target, ignore=shutil.ignore_patterns("__pycache__"))
    atom = target / "atom.py"
    text = atom.read_text(encoding="utf-8")
    assert old in text, name
    atom.write_text(text.replace(old, new, 1), encoding="utf-8")
    env = dict(os.environ, PYTHONPATH=str(ROOT))
    out = subprocess.run([PY, "-m", "pytest", "-q", "-p", "no:cacheprovider", "--tb=no",
                          str(target / "tests" / "test_atom.py")],
                         cwd=str(ROOT), env=env, capture_output=True, text=True,
                         encoding="utf-8", errors="replace")
    failed = [l.split("::")[-1] for l in out.stdout.splitlines() if l.startswith("FAILED")]
    summary = out.stdout.strip().splitlines()[-1] if out.stdout.strip() else out.stderr[-300:]
    print("==", name, "->", summary)
    for f in failed:
        print("     ", f)
