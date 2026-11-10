"""إقلاع سوق الفوركس مع لوحة مستقلة."""
from __future__ import annotations
import argparse, os, socket, subprocess, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# ── حارس المفسّر — يمنع تسرّب بايثون النظام ────────────────────────────
# كل عمليّة فرعيّة هنا تُولَد بـ`sys.executable`، فالمفسّر الذي يبدأ عند هذه
# النقطة يسري على الشجرة كلّها: النواة والحوكمة واللوحة وتلغرام.
# قِيس ٢٠٢٦-٠٩-٠١: نواة الفوركس عملت ١٦٫٥ ساعة على بايثون النظام لأنّها
# أُطلقت به — وينقصه `deep-translator`، وغيابه مبتلَع بالتصميم
# (`except Exception: return`) فتبقى عناوين الأخبار إنكليزيّة بلا إنذار.
# الحارس يعيد الإطلاق بالمفسّر المتنقّل بدل أن يشتغل ناقصًا بصمت،
# و`-s` يقطع مجلّد user-site فلا تدخل مكتبة من خارج المشروع أبدًا.
VENDOR_PY = ROOT / "vendor" / "python" / "runtime" / "python.exe"
if VENDOR_PY.exists() and Path(sys.executable).resolve() != VENDOR_PY.resolve():
    print(f"[حارس المفسّر] أُطلقت بـ: {sys.executable}")
    print(f"[حارس المفسّر] أُعيد الإطلاق بالمفسّر المتنقّل: {VENDOR_PY}")
    sys.exit(subprocess.run(
        [str(VENDOR_PY), "-s", str(Path(__file__).resolve()), *sys.argv[1:]]
    ).returncode)

MARKETS = {
    "forex": {"core": "run_forex.py", "core_port": 8010, "gov_port": 8092, "ui_port": 8090},
}
MARKET_AR = {"forex": "الفوركس"}

def listening(port: int) -> bool:
    with socket.socket() as s:
        s.settimeout(.15); return s.connect_ex(("127.0.0.1", port)) == 0

# ── حارس النواة الثانية (٢٠٢٦-١٠-٢٦، ختم المالك «NQ») ─────────────────────
# المنفذ وحده لا يشهد بغياب النواة: بين ولادتها وفتح 8010 من 13 إلى 40 ثانية
# (core.log ٢٦/١٠ 00:34:28 ← 00:34:41، و١٢/١٠ أربعون ثانية)، وإن وجدته محجوزًا
# تكمل التداول بلا منفذ (run_core.py:1155-1158). فقبل إقلاع نواةٍ تُقرأ قائمة
# العمليّات: مُقلِع نواةٍ حيّ، أو ابنٌ متعدّد العمليّات من المشروع ماتت أمّه — العمليّة
# الباردة اليتيمة تكتب في المخازن نفسها. و«لا أعرف» رفضٌ، لا «لا نواة».
#: ما يُعرف به المُقلِع في سطر أوامر النواة — المعيار نفسه في stop_all.py:48.
CORE_ENTRYPOINTS = ("run_core.py", "run_forex.py")
#: سطر أوامر العمليّة الباردة الحيّة (مقيس ٢٦/١٠): «… -c from multiprocessing.spawn import
#: spawn_main; spawn_main(parent_pid=…) --multiprocessing-fork» — العلامتان معًا.
CHILD_MARKS = ("spawn_main(", "--multiprocessing-fork")

def live_core_processes() -> list[str]:
    """سطرٌ عربيّ لكلّ ما يمنع إقلاع نواة؛ والقائمة الفارغة وحدها تسمح."""
    try:
        import psutil
    except ImportError:
        return ["مكتبة قراءة العمليّات غير مثبتة، فلا أعرف هل في الجهاز نواة — شغّل زرّ التهيئة."]
    try:
        me = psutil.Process()
        mine = {me.pid} | {p.pid for p in me.parents()}
        root_s = str(ROOT).lower()
        found: list[str] = []
        for p in psutil.process_iter(["pid", "name", "cmdline", "create_time"]):
            info = p.info
            if info["pid"] in mine or not (info["name"] or "").lower().startswith("python"):
                continue
            born = time.strftime("%H:%M:%S %d/%m", time.localtime(info["create_time"] or 0))
            if info["cmdline"] is None:
                found.append(f"عمليّة بايثون {info['pid']} (وُلدت {born}) لا يُقرأ سطر أوامرها، فلا أعرف أهي نواة.")
                continue
            cmd = " ".join(info["cmdline"]).lower()
            if any(name in cmd for name in CORE_ENTRYPOINTS):
                found.append(f"نواةٌ حيّة: العمليّة {info['pid']} (وُلدت {born}).")
            elif all(mark in cmd for mark in CHILD_MARKS) and root_s in cmd and p.parent() is None:
                found.append(f"عمليّةٌ باردة يتيمة محتملة: العمليّة {info['pid']} (وُلدت {born}) من المشروع، وأمّها ماتت.")
        return found
    except Exception:
        return ["تعذّرت قراءة قائمة العمليّات، فلا أعرف هل في الجهاز نواة."]

def spawn(cmd: list[str], port: int, env: dict[str, str], label: str) -> None:
    if listening(port): print(f"{label}: يعمل مسبقًا على {port}"); return
    # ويندوز: CREATE_NEW_PROCESS_GROUP ضروريّ لاستقبال CTRL_BREAK_EVENT
    kwargs = {"cwd": ROOT, "env": env, "close_fds": (os.name != "nt")}
    if os.name == "nt":
        import subprocess
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    subprocess.Popen(cmd, **kwargs)
    print(f"{label}: بدأ على {port}")

def wait(port: int) -> bool:
    for _ in range(100):
        if listening(port): return True
        time.sleep(.15)
    return listening(port)

def start(market: str) -> list[int]:
    c = MARKETS[market]; env = dict(os.environ)
    env.update(PYTHONUTF8="1", QUANT_LOCAL_MODE=env.get("QUANT_LOCAL_MODE", "1"))
    py = sys.executable
    spawn([py, str(ROOT / "scripts" / c["core"])], c["core_port"], env, f"نواة {market}")
    gov_env = dict(env); gov_env["QUANT_GOV_MARKET"] = market
    spawn([py, str(ROOT / "scripts" / "run_governance.py"), "--market", market, "--port", str(c["gov_port"])], c["gov_port"], gov_env, f"حوكمة {market}")
    hub_env = dict(env); hub_env.update(QUANT_HUB_PORT=str(c["ui_port"]), QUANT_HUB_DEFAULT_MARKET=market)
    spawn([py, str(ROOT / "governance" / "unified_hub.py")], c["ui_port"], hub_env, f"لوحة {market}")
    return [c["core_port"], c["gov_port"], c["ui_port"]]

# ٦١٠ — تلغرام: منصّة المالك المتنقّلة. نسخة واحدة بقفل المنفذ 8098، والتوكن من
# الخزنة المشفّرة حصرًا. كانت تُشغَّل من `launch_unified.py` وحده، وهو يشترط
# `api.host=0.0.0.0` ومفتاحًا — فالزرّ المحلّي كان يترك تلغرام مطفأة دائمًا
# (ختم NQ ٢٠٢٦-٠٨-٣١: «شغّل كل شي موجود عنا»). بلا توكن تخرج بهدوء ولا تؤثّر
# على بقيّة الستاك، لذلك حالتها تُطبع ولا تُسقِط رمز الخروج.
TELEGRAM_PORT = 8098

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--market", choices=["forex"], default="forex")
    ap.add_argument("--no-telegram", action="store_true", help="لا تشغّل منصّة تلغرام ٦١٠")
    args = ap.parse_args()
    markets = [args.market]
    for m in markets:
        port = MARKETS[m]["core_port"]
        if listening(port):
            continue
        blockers = live_core_processes()
        if blockers:
            print(f"⛔ رفضتُ إقلاع {MARKET_AR[m]}: لم يُقلَع شيء — لا نواة ولا حوكمة ولا لوحة ولا تلغرام.")
            print(f"   منفذ النواة {port} مغلق، لكن في الجهاز ما يمنع نواةً ثانية:")
            for line in blockers:
                print(f"   • {line}")
            print("   نواةٌ ثانية تكتب في مخازن الأولى نفسها. إن كانت المنظومة تُقلع فانتظر دقيقةً ثمّ أعد الزرّ؛")
            print("   وإلّا فأوقفها بزرّ «إيقاف النظام» ثمّ أقلعها من «غرفة القيادة».")
            return 3
    ports = [p for m in markets for p in start(m)]
    if not args.no_telegram:
        tg_env = dict(os.environ); tg_env["PYTHONUTF8"] = "1"
        spawn([sys.executable, str(ROOT / "governance" / "telegram.py")],
              TELEGRAM_PORT, tg_env, "تلغرام ٦١٠")
    ready = {p: wait(p) for p in ports}
    for p, ok in ready.items(): print(f"port {p}: {'READY' if ok else 'NOT READY'}")
    for m in markets: print(f"لوحة {m}: http://127.0.0.1:{MARKETS[m]['ui_port']}")
    if not args.no_telegram:
        print(f"تلغرام ٦١٠: {'READY' if wait(TELEGRAM_PORT) else 'NOT READY — راجع تبويب الأمان'} (قفل {TELEGRAM_PORT})")
    return 0 if all(ready.values()) else 2

if __name__ == "__main__": raise SystemExit(main())
