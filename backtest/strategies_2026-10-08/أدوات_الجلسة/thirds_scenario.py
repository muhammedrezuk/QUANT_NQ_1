# سيناريو يدويّ: ما تفعله 574 فعلًا عند كلّ هدف — قراءة فقط، على نسخةٍ في الذاكرة لا على الحيّ.
import asyncio
import sys
from decimal import Decimal, ROUND_FLOOR
from pathlib import Path
import importlib.util as ilu

ROOT = Path(r"C:\Users\NQ\QUANT_NQ")
ATOM_DIR = ROOT / "atoms" / "قسم 550-599" / "574_الإغلاق_الجزئي"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ATOM_DIR))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from core.contracts.atom import AtomContext  # noqa: E402

spec = ilu.spec_from_file_location("_a574_scn", ATOM_DIR / "atom.py")
mod = ilu.module_from_spec(spec)
sys.modules["_a574_scn"] = mod
spec.loader.exec_module(mod)
import partial_levels  # noqa: E402
import stage_apply  # noqa: E402


class Log:
    def __getattr__(self, _n):
        return lambda *a, **k: None


class Bus:
    def __init__(self):
        self.published, self.handlers = [], {}

    def subscribe(self, n, h):
        self.handlers.setdefault(n, []).append(h)

    async def publish(self, n, p):
        self.published.append((n, p))

    async def deliver(self, n, p):
        for h in self.handlers.get(n, []):
            await h(p)


async def new(symbol, vmin, step):
    bus = Bus()
    a = mod.Atom()
    await a.initialize(AtomContext(atom_id=574, config={"partial_at_r": 1.0, "partial_fraction": 0.5,
                                                        "min_partial_lot": 0.01},
                                   logger=Log(), publish=bus.publish, subscribe=bus.subscribe))
    await a.start()
    await a._on_specs({"symbols": [{"symbol": symbol, "volume_min": vmin, "volume_step": step,
                                    "tick_value": 0.01, "tick_size": 0.01, "point": 0.01,
                                    "stops_level": 0, "freeze_level": 0}]})
    return a, bus


def outs(bus, seen):
    rows = [p for n, p in bus.published if n == mod.EVENT_OUT]
    new_rows = rows[seen[0]:]
    seen[0] = len(rows)
    return new_rows


def fmt(rows):
    if not rows:
        return "لا أمر"
    parts = []
    for p in rows:
        if p["action"] == "MODIFY_SL":
            parts.append("نقل الوقف إلى %s (%s)" % (p["stop_loss"], p["reason"]))
        else:
            parts.append("%s %s لوت (مرحلة %s)" % ("إغلاق جزئي" if p["action"] == "CLOSE_PARTIAL" else "خروج كامل",
                                               p["volume"], p["stage"]))
    return " ؛ ".join(parts)


async def run(title, entry, stop, target, volume, path, symbol="USTEC", vmin=0.1, step=0.1, spread=1.0):
    print("\n=== %s ===" % title)
    print("شراء %s · دخول %s · وقف %s (%.1f نقطة) · هدف %s (1:%g) · حجم %s" % (
        symbol, entry, stop, entry - stop, target, (target - entry) / (entry - stop), volume))
    span = target - entry
    print("المتوقَّع بنصّ المالك: هدف1 %.2f · هدف2 %.2f · هدف3 %.2f" % (
        entry + span / 3, entry + 2 * span / 3, target))
    a, bus = await new(symbol, vmin, step)
    seen = [0]
    vol, sl = volume, stop
    pos = lambda price: {"positions": [{"account_id": "A", "ticket": 1, "symbol": symbol, "side": "BUY",
                                        "volume": vol, "entry_price": entry, "current_price": price,
                                        "stop_loss": sl, "take_profit": target}]}
    await bus.deliver("feed.mt5.tick", {"account_id": "A", "symbol": symbol, "bid": entry - spread, "ask": entry})
    await a._on_positions(pos(entry - spread))
    outs(bus, seen)
    for kind, price in path:
        if kind == "tick":
            await bus.deliver("feed.mt5.tick", {"account_id": "A", "symbol": symbol, "bid": price, "ask": price + spread})
            label = "تِكّة عرض %s" % price
        else:
            label = "دورة مراكز عند %s (الحجم على المنصّة %s، الوقف %s)" % (price, vol, sl)
            await a._on_positions(pos(price))
        rows = outs(bus, seen)
        print("  %-62s ⟵ %s" % (label, fmt(rows)))
        for p in rows:  # المنصّة تنفّذ: الحجم ينقص والوقف ينتقل
            if p["action"] == "CLOSE_PARTIAL":
                vol = round(vol - p["volume"], 2)
            elif p["action"] == "CLOSE":
                vol = 0.0
            elif p["action"] == "MODIFY_SL":
                sl = p["stop_loss"]
    st = a._tracked.get("1", {})
    print("  حالة الذرّة: مرحلة=%s منتهية=%s هدف_واحد=%s | الحجم الباقي %s والوقف %s" % (
        st.get("stage"), st.get("done"), st.get("single"), vol, sl))
    return vol, sl


async def main():
    print("الشارة:", (await (await new("USTEC", 0.1, 0.1))[0].health_check()).message.split("|")[0][:40])
    print("المسار الحيّ: LEVEL_PLAN_ON=%s PROTECT_SYMBOLS=%s STAGES=%s" % (
        partial_levels.LEVEL_PLAN_ON, sorted(partial_levels.PROTECT_SYMBOLS), mod.STAGES))
    E, S, T = 20000.0, 19970.0, 20090.0
    # أ) يبلغ الأهداف الثلاثة
    await run("أ) ناسداك يبلغ الثلاثة", E, S, T, 3.3, [
        ("cycle", 20010.0), ("tick", 20029.9), ("tick", 20030.0), ("tick", 20031.0), ("cycle", 20031.0),
        ("tick", 20059.9), ("tick", 20060.0), ("cycle", 20061.0), ("tick", 20089.9), ("tick", 20090.0)])
    # ب) يبلغ الأوّل ثمّ يرتدّ إلى التعادل
    vol, sl = await run("ب) يبلغ الأوّل ثمّ يرتدّ إلى التعادل", E, S, T, 3.3, [
        ("tick", 20030.0), ("cycle", 20031.0), ("tick", 20045.0), ("tick", 20015.0), ("tick", 20000.5),
        ("cycle", 20000.5)])
    print("  ⟵ الوسيط يضرب الوقف %s عند ارتداد العرض إليه: الباقي %s لوت يخرج عند الدخول (0$)، والمقبوض 1.1×30 = +33$" % (sl, vol))
    # ج) يبلغ الثاني ثمّ يرتدّ إلى الهدف الأوّل
    vol, sl = await run("ج) يبلغ الثاني ثمّ يرتدّ إلى الهدف الأوّل", E, S, T, 3.3, [
        ("tick", 20030.0), ("cycle", 20031.0), ("tick", 20060.0), ("cycle", 20061.0), ("tick", 20040.0),
        ("tick", 20030.5)])
    print("  ⟵ الوسيط يضرب الوقف %s: الباقي %s لوت يخرج عند الهدف الأوّل؛ المجموع 1.1×30 + 1.1×60 + 1.1×30 = +132$" % (sl, vol))
    # د) هدف 1:5 — الأثلاث من مسافة الهدف لا من 1R
    await run("د) هدف 1:5 (الهدف الأوّل عند 1.67R لا 1R)", E, S, 20150.0, 3.3, [
        ("tick", 20030.0), ("tick", 20049.9), ("tick", 20050.0), ("cycle", 20051.0), ("tick", 20100.0),
        ("cycle", 20101.0), ("tick", 20150.0)])

    # هـ) مسح أحجام: هل «ثلث العقد» و«نصف الباقي» يُحسبان كما يُقصد عند خطوة اللوت؟
    print("\n=== هـ) مسح الأحجام: ما يُغلقه الكود مقابل الحساب العشريّ الدقيق بالقصّ نفسه ===")
    for step in (0.1, 0.01):
        bad = []
        n = 0
        v = Decimal("0.10") if step == 0.1 else Decimal("0.03")
        while v <= Decimal("10.0"):
            n += 1
            vol = float(v)
            for stage, frac in ((1, 1.0 / 3.0), (2, 0.5)):
                code = round(vol * frac, 2)
                code = round(int(code / step // 1) * step, 2)
                import math
                code = round(math.floor(round(vol * frac, 2) / step) * step, 2)
                exact_r = Decimal(str(round(vol * frac, 2)))
                exact = float((exact_r / Decimal(str(step))).to_integral_value(rounding=ROUND_FLOOR) * Decimal(str(step)))
                if abs(code - exact) > 1e-9:
                    bad.append((float(v), stage, round(vol * frac, 2), code, exact))
            v += Decimal(str(step))
        print("خطوة %s: %d حجمًا مفحوصًا · مرحلةٌ تُغلق خطوةً أقلّ من المقصود: %d" % (step, n, len(bad)))
        for row in bad[:12]:
            print("   حجم %-5s مرحلة %d: المقصود %s ⟵ الكود يُغلق %s (الصحيح %s)" % (row[0], row[1], row[2], row[3], row[4]))

    # و) تأكيد على الذرّة الحقيقيّة: ناسداك 2.1 لوت
    await run("و) ناسداك 2.1 لوت — ثلثه 0.7 بالضبط", E, S, T, 2.1, [
        ("tick", 20030.0), ("cycle", 20031.0), ("tick", 20060.0), ("cycle", 20061.0), ("tick", 20090.0)])
    await run("ز) ناسداك 0.9 لوت — ثلثه 0.3 بالضبط", E, S, T, 0.9, [
        ("tick", 20030.0), ("cycle", 20031.0), ("tick", 20060.0), ("cycle", 20061.0), ("tick", 20090.0)])


if __name__ == "__main__":
    asyncio.run(main())
