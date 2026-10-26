"""Phase 4-4 — transport loss and reconnect, against the REAL atoms.

A disconnect is not an event anyone publishes: it is the ABSENCE of events while
the clock keeps moving. So the danger is never a loud failure -- it is silence
being read as health, and old data being carried forward as if it were live.

Three real atoms hold the verdict and are driven here, not simulated:

    521  the reference -- must declare STALE when its data ages out, and must
         rebuild from the NEW tick after reconnect, not from the price it froze.
    619  the account -- must keep speaking and say how old it is (item 55).
    414  the decision card -- must not approve during the silence, must not read
         the pre-cut candle that the candle builder closes late on reconnect, must
         not revive an older candle, and must decide from the post-cut facts.
         (٢٠٢٦-١٠-٠٧، ختم المالك «NQ»: حلّت محلّ 581 المؤرشفة مع فكّ الأقسام عن القرار.)

And the point that matters most: losing the connection must never become an
order, nor an implicit approval.

Exit 1 on any divergence. Nothing is fixed here.
"""
from __future__ import annotations

import asyncio
import importlib.util
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import yaml  # noqa: E402

from core.contracts.atom import AtomContext  # noqa: E402

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from build_registry.paths import RegistryAtomRoot
ATOMS = RegistryAtomRoot(ROOT)
FOLDERS = {p.name.split("_")[0]: p.name for p in ATOMS.iterdir() if p.is_dir()}
FORBIDDEN = ("execution.order.requested", "trading.final_decision", "brain_signal.written")
ACC, SYM = "A", "BTCUSD"
PRICE, VPU, STOP_FRAC, BUDGET = 63000.0, 1.0, 0.0055, 100.0
T0 = 1_000_000.0
BEFORE_CYCLE, AFTER_CYCLE = "BTCUSD|60s|1000", "BTCUSD|60s|2000"


class _Logger:
    def __getattr__(self, name):
        return lambda *a, **k: None


class Bus:
    def __init__(self):
        self.log = []
        self.wired = {}

    def subscribe(self, name, handler):
        self.wired.setdefault(name, []).append(handler)

    async def publish(self, name, payload):
        self.log.append((name, dict(payload) if isinstance(payload, dict) else payload))

    def last(self, name):
        rows = [p for n, p in self.log if n == name]
        return rows[-1] if rows else None

    def count(self, name):
        return sum(1 for n, _ in self.log if n == name)


def card(atom_id: str) -> dict:
    return yaml.safe_load(
        (ATOMS / FOLDERS[atom_id] / "manifest.yaml").read_text(encoding="utf-8"))


async def build(atom_id: str, bus: Bus, overrides: dict | None = None):
    directory = ATOMS / FOLDERS[atom_id]
    spec = importlib.util.spec_from_file_location("_p44_%s" % atom_id, directory / "atom.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    sys.path.insert(0, str(directory))
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path.remove(str(directory))
    config = dict(card(atom_id).get("config") or {})
    config.update(overrides or {})
    atom = module.Atom()
    await atom.initialize(AtomContext(atom_id=int(atom_id), config=config, logger=_Logger(),
                                      publish=bus.publish, subscribe=bus.subscribe))
    await atom.start()
    return atom


def show(label, ok, detail=""):
    print("   %-46s %-32s %s" % (label, detail, "✓" if ok else "✗"))
    return 0 if ok else 1


# ٢٠٢٦-١٠-٠٨ (إصلاح الاختبارات القديمة بأمر المالك): 521 (٢٠٢٦-٠٩-٠١) و619 (٢٠٢٦-٠٨-٣١، ختم NQ) صارتا تقرآن «الآن» من الساعة المركزيّة `clock.now()` لا من النبضة.
# ٢٠٢٦-١٠-٠٨ (إصلاح الاختبارات القديمة بأمر المالك): فكان الفحص يحرّك ساعةً لا تقرؤها الذرّة (`_now` وطابع النبضة) وتقرأ الذرّة ساعة الجهاز، فيبدو كلّ شيء «متقادمًا» على T0.
# ٢٠٢٦-١٠-٠٨ (إصلاح الاختبارات القديمة بأمر المالك): الآن تُستبدل الساعة التي تقرؤها الذرّة نفسها (اسم `clock` داخل وحدتها وحدها) بساعةٍ يقودها الفحص؛ وبقيّة دوالّ الساعة تمرّ إلى الحقيقيّة.
class _StepClock:
    def __init__(self, real, start):
        self._real = real
        self.value = float(start)

    def now(self):
        return self.value

    def __getattr__(self, name):
        return getattr(self._real, name)


def drive_clock(atom, start):
    module = sys.modules[type(atom).__module__]
    step = _StepClock(module.clock, start)
    module.clock = step
    return step


async def reference() -> int:
    print("\nأ) المرجع 521 — الصمت لا يُقرأ صحّة")
    bad = 0
    bus = Bus()
    atom = await build("521", bus, {"symbols": [SYM]})
    max_age = float((card("521").get("config") or {}).get("max_data_age_s") or 5.0)
    # ٢٠٢٦-١٠-٠٨ (إصلاح الاختبارات القديمة بأمر المالك): الساعة التي يقرؤها 521 فعلًا (`clock.now()`) هي التي تتحرّك، لا `_now` الذي صار للمراقبة فقط.
    step = drive_clock(atom, T0)

    async def tick(price, stamp):
        step.value = stamp
        await atom._on_primary({"symbol": SYM, "bid": price - 0.5, "ask": price + 0.5,
                                "price": price, "timestamp": stamp})

    await tick(PRICE, T0)
    live = bus.last("reference.health.state")
    bad += show("١· قبل القطع: مرجع صالح",
                bool(live) and live.get("state") in ("HEALTHY", "FALLBACK"),
                "%s · %s" % ((live or {}).get("state"), (live or {}).get("selected_price")))

    # 2+3: the cut. No ticks arrive, but the clock keeps advancing.
    step.value = T0 + max_age * 4
    await atom._publish(SYM)
    cut = bus.last("reference.health.state")
    bad += show("٣· أثناء القطع: لا يُبنى مرجع من القديم",
                bool(cut) and cut.get("state") not in ("HEALTHY", "FALLBACK"),
                "%s · عمر=%.0fs" % ((cut or {}).get("state"), (cut or {}).get("data_age_s") or 0))

    # 4+5+6: reconnect with a DIFFERENT price.
    await tick(PRICE + 500.0, T0 + max_age * 4 + 1.0)
    back = bus.last("reference.health.state")
    bad += show("٦· بعد العودة: الحالة من الجديد لا القديم",
                bool(back) and back.get("state") in ("HEALTHY", "FALLBACK")
                and back.get("selected_price") == PRICE + 500.0,
                "%s · %s" % ((back or {}).get("state"), (back or {}).get("selected_price")))
    return bad


async def account() -> int:
    print("\nب) الحساب 619 — يقول عمره بدل أن يصمت")
    bad = 0
    with tempfile.TemporaryDirectory() as tmp:
        db = str(Path(tmp) / "acct.db")

        # ٢٠٢٦-١٠-٠٨ (إصلاح الاختبارات القديمة بأمر المالك): 619 يقرأ `account_v2` وحده (الجدول القديم `account` ممنوع: LEGACY_ACCOUNT_TABLE_FORBIDDEN)، فكان الفحص يكتب في جدولٍ لا يُقرأ.
        # ٢٠٢٦-١٠-٠٨ (إصلاح الاختبارات القديمة بأمر المالك): الصفّ بمخطّط الإكسبرت نفسه (`mt5/QUANT_NQ.mq5` — حسابٌ لكلّ صفّ بمفتاحه).
        def write(stamp):
            conn = sqlite3.connect(db)
            conn.execute("CREATE TABLE IF NOT EXISTS account_v2 ("
                         "account_id TEXT PRIMARY KEY, balance REAL, equity REAL, margin REAL,"
                         " free_margin REAL, margin_level REAL, currency TEXT, leverage INTEGER,"
                         " open_count INTEGER, updated_at REAL, connected INTEGER, trade_allowed INTEGER,"
                         " expert_allowed INTEGER, bridge_beat REAL, broker TEXT, account_server TEXT,"
                         " margin_mode INTEGER, expert_id TEXT, expert_version TEXT, project_build_id TEXT)")
            conn.execute("DELETE FROM account_v2")
            conn.execute("INSERT INTO account_v2 (account_id, balance, equity, margin, free_margin,"
                         " margin_level, currency, leverage, open_count, updated_at, connected,"
                         " trade_allowed, expert_allowed, bridge_beat, broker, account_server, margin_mode)"
                         " VALUES (?,644.84,644.84,0.0,644.84,0.0,'USD',5000,0,?,1,1,1,?,'B','S',2)",
                         (ACC, stamp, stamp))
            conn.commit()
            conn.close()

        write(T0 - 10.0)
        bus = Bus()
        atom = await build("619", bus, {"db_path": db, "max_age_s": 300.0})
        await atom.stop()
        step = drive_clock(atom, T0)
        step.value = T0
        for handler in bus.wired.get("SYS_SECOND", []):
            await handler({"official_time": T0})
        await atom._read_once()
        fresh_state = bus.last("platform.account.state")
        bad += show("١· قبل القطع: حديث", bool(fresh_state) and fresh_state.get("stale") is False,
                    "عمر=%s" % (fresh_state or {}).get("age_s"))

        bus.log.clear()
        step.value = T0 + 4000.0
        for handler in bus.wired.get("SYS_SECOND", []):
            await handler({"official_time": T0 + 4000.0})     # clock moves, row does not
        await atom._read_once()
        cut = bus.last("platform.account.state")
        bad += show("٣· أثناء القطع: يعلن تقادمه ولا يصمت",
                    bool(cut) and cut.get("stale") is True,
                    "عمر=%s · متقادم=%s" % ((cut or {}).get("age_s"), (cut or {}).get("stale")))

        write(T0 + 4100.0)
        bus.log.clear()
        step.value = T0 + 4101.0
        for handler in bus.wired.get("SYS_SECOND", []):
            await handler({"official_time": T0 + 4101.0})
        await atom._read_once()
        back = bus.last("platform.account.state")
        bad += show("٦· بعد العودة: يعود حديثًا من الصفّ الجديد",
                    bool(back) and back.get("stale") is False,
                    "عمر=%s" % (back or {}).get("age_s"))
    return bad


CARD_SYM = "USTEC"


async def decision() -> int:
    """٢٠٢٦-١٠-٠٧ (ختم المالك «NQ» — فكّ الأقسام عن القرار): القرار الآن من البطاقة 414 (581 مؤرشفة).
    واقعة الانقطاع كما يصنعها باني الشموع 103: يُغلق الشمعة عند أوّل تِكّةٍ من الفترة التالية ⟸
    عند العودة تصل شمعةُ ما قبل القطع متأخّرةً، وقد تسبق حقيقةُ الوقت أو تتأخّر عنها."""
    print("\nج) القرار — البطاقة 414: الصمت ليس موافقة، والشمعة القديمة لا تُقرأ ولا تُبعث")
    bad = 0
    bus = Bus()
    atom = await build("414", bus, {"symbols": [CARD_SYM]})
    now = [T0 + 1.0]
    atom._clock = lambda: now[0]

    async def candle(close, start):
        await atom._on_candle({"symbol": CARD_SYM, "timeframe": "5m", "period_start": start, "close": close})

    async def time_fact():
        await atom._on_session({"symbol": CARD_SYM, "owner_window": "london_peak", "window_at": now[0]})

    await atom._on_account({"account_id": ACC, "broker": "B"})
    await atom._on_positions({"positions": []})
    for frame in ("1h", "4h"):
        await atom._on_trend({"symbol": CARD_SYM, "timeframe": frame,
                              "metadata": {"close": 30000.0, "ema_slow_value": 29500.0}})
        for peer in ("US500", "US30"):
            await atom._on_trend({"symbol": peer, "timeframe": frame,
                                  "metadata": {"close": 7000.0, "ema_slow_value": 6500.0}})
    await atom._on_vol({"symbol": CARD_SYM, "timeframe": "5m", "metadata": {"atr_14": 10.0}})
    await atom._on_vol({"symbol": CARD_SYM, "timeframe": "1d", "metadata": {"atr_14": 400.0}})
    await atom._on_ladder({"symbol": CARD_SYM, "frames": {
        "5m": {"highs": [[30010.0, T0 - 1800]], "lows": [[29980.0, T0 - 900]]},
        "1h": {"highs": [[30200.0, T0 - 7200]], "lows": []}, "4h": {"highs": [], "lows": []}}})
    await time_fact()
    await candle(30005.0, T0 - 600)
    await candle(30015.0, T0 - 300)          # يكسر قمّة الارتداد ⟸ بطاقةٌ مفتوحة
    approved = bus.count("decision.approved.state")
    bad += show("١· قبل القطع: بطاقةٌ مفتوحة وموافقةٌ واحدة", approved == 1,
                str((bus.last("strategy.card.state") or {}).get("status")))

    for _ in range(5):                       # الصمت: لا يصل شيء أبدًا
        await asyncio.sleep(0)
    bad += show("٨· الصمت لا يُنتج قرارًا ولا موافقة", bus.count("decision.approved.state") == approved,
                "موافقات %d" % bus.count("decision.approved.state"))

    now[0] = T0 + 1800.0                     # نصف ساعة انقطاع — الساعة تمشي والحقائق واقفة
    await candle(30030.0, T0)                # شمعة ما قبل القطع تُغلق عند أوّل تِكّةٍ بعد العودة
    late = bus.last("strategy.card.state") or {}
    bad += show("٣· عند العودة: شمعة ما قبل القطع لا تكون زنادًا",
                late.get("status") == "CANDLE_LATE" and bus.count("decision.approved.state") == approved,
                "%s · تأخّر=%ss" % (late.get("status"), late.get("late_s")))

    await candle(30035.0, T0 + 1500.0)       # شمعةٌ حيّة لكنّ حقيقة الوقت ما زالت من قبل القطع
    # ٢٠٢٦-١٠-٠٨ (ختم المالك «صلح NQ»): البطاقة تنتظر حقيقة الوقت عند لحظة الشمعة نفسها (الحيّ = المقيس عند
    # حدود الإطارات)، وما لم يصل خلال المهلة ⟸ «حقيقة متأخّرة» بلا صفقة (كانت: «خارج النافذة»). والمهلة
    # تُختصر هنا بحسمها مباشرة. الحراسة نفسها: لا موافقة على حقيقة وقتٍ قديمة.
    held = CARD_SYM in atom._pending and bus.count("decision.approved.state") == approved
    await atom._expire(CARD_SYM, T0 + 1800.0)
    stale = bus.last("strategy.card.state") or {}
    bad += show("٤· حقيقة الوقت القديمة لا تفتح صفقة",
                held and stale.get("status") == "FACT_LATE" and "412" in (stale.get("late") or [])
                and bus.count("decision.approved.state") == approved,
                "%s %s" % (stale.get("status"), stale.get("late")))

    cards = bus.count("strategy.card.state")
    await candle(30015.0, T0 - 300)          # شمعة الزناد القديمة تُعاد
    bad += show("٧· شمعة ما قبل القطع لا تُبعث بعده",
                bus.count("strategy.card.state") == cards and bus.count("decision.approved.state") == approved,
                "بطاقات %d ⟶ %d" % (cards, bus.count("strategy.card.state")))

    now[0] = T0 + 2100.0
    await time_fact()                        # حقيقة الوقت تعود حيّة
    await candle(30040.0, T0 + 1800.0)
    fresh = bus.last("strategy.card.state") or {}
    bad += show("٥+٦· بعد العودة: تُقيَّم من الجديد لا القديم",
                fresh.get("at") == T0 + 2100.0 and fresh.get("close") == 30040.0
                and fresh.get("status") not in ("CANDLE_LATE", "CANDLE_OLD", "OUTSIDE_OWNER_WINDOW"),
                "%s · إغلاق=%s" % (fresh.get("status"), fresh.get("close")))

    for name in FORBIDDEN:
        bad += show("٨· لا حدث %s" % name, bus.count(name) == 0, str(bus.count(name)))
    return bad


async def main_async() -> int:
    print("=" * 96)
    print("٤-٤ · انقطاع الناقل وإعادة الاتّصال — على الذرات الحقيقيّة")
    print("=" * 96)
    bad = await reference() + await account() + await decision()
    print("\n" + "=" * 96)
    print("الاختلافات = %d" % bad)
    if bad == 0:
        print("سليم: الصمت يُعلَن ولا يُقرأ صحّة · والعودة تُبنى من الجديد · ولا موافقة ضمنيّة.")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(asyncio.run(main_async()))
