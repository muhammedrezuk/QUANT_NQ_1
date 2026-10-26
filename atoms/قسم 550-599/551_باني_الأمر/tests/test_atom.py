import asyncio
import os
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from pathlib import Path as _Path
sys.path.insert(0, str(_Path(__file__).resolve().parents[4]))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.contracts.atom import AtomContext, HealthState  # noqa: E402
import importlib.util as _ilu  # noqa: E402
import pytest  # noqa: E402

_spec = _ilu.spec_from_file_location(
    "_atom551", _Path(__file__).resolve().parents[1] / "atom.py")
_mod = _ilu.module_from_spec(_spec)
sys.modules["_atom551"] = _mod
_spec.loader.exec_module(_mod)
Atom = _mod.Atom
EVENT_OUT = _mod.EVENT_OUT
EVENT_SKIPPED = _mod.EVENT_SKIPPED

def _manifest_config() -> dict:
    """الإعداد من المانيفست نفسه لا من يد الاختبار.

    ⚖️ ٢٠٢٦-٠٩-١٨ — كان هنا `reward_risk: 2.0` مكتوبًا بيد الاختبار
    والمانيفست يحمل `3.0` منذ ٢٠٢٦-٠٩-١٠. فالاختبارات كلّها تجرّب عيارًا
    **لا وجود له في المنصّة**، وتخرج خضراء في الحالين: يتغيّر المانيفست أو
    لا يتغيّر ولا ينكسر شيء.

    وهو الدرس نفسه الذي أُصلح في ٥٨٤ (`_manifest_config` هناك) وبقي هنا —
    وأخطر ما فيه أنّ العيار المدهوس هو مضاعف المكافأة: كل اختبار هدفٍ في
    هذا الملفّ كان يقيس 1:2 بينما الحيّ 1:3.
    """
    import yaml
    path = _Path(__file__).resolve().parents[1] / "manifest.yaml"
    cfg = dict(yaml.safe_load(path.read_text(encoding="utf-8"))["config"])
    # ٢٠٢٦-١٠-٠٨ (إصلاح الاختبارات القديمة بأمر المالك): `reward_risk` حُذف من المانيفست والكود معًا بأمر ٠٩-١٩ «ولا هدف احتياطي أو هدف صلب» (الالتزام 26f5209f)، فكان `cfg["reward_risk"]` يرمي KeyError ويمنع جمع الملفّ كلّه؛ والإعداد يُمرَّر الآن كما في المانيفست حرفيًّا والحارس أدناه يمنع عودة المضاعف خفيةً.
    assert "reward_risk" not in cfg, "مضاعف هدفٍ صلب عاد إلى إعداد ٥٥١: %r" % cfg
    return cfg


CFG = _manifest_config()


async def test_realised_loss_never_passes_the_cap():
    """حكم المالك ٢٠٢٦-٠٩-٠٦: «ما يتجاوز 100 أبدًا».

    القاعدة تصير حارسًا لا وعدًا: عند **أقصى** زيادة مقيسة على المسافة
    المخطَّطة (27.88 ⇒ 0.00035 من السعر) تبقى الخسارة تحت السقف الصلب.
    سقط هذا مرّتين حيًّا قبل الحارس: 125.07$ و108.42$.
    """
    print("\n--- الخسارة الواقعة لا تتجاوز السقف ---")
    price = 80000.0
    cap = 100.0
    tail = price * _mod.TAIL_SLIPPAGE_FRAC
    allowance = price * _mod.EXCESS_ALLOWANCE_FRAC
    for distance in (20.0, 25.0, 30.0, 40.0, 60.0):
        size = {"risk_amount": cap * _mod.UTILISATION_CEILING,
                "max_trade_loss": cap * _mod.UTILISATION_CEILING,
                "hard_trade_loss_cap": cap,
                "tick_value": 0.01, "tick_size": 0.01,
                "volume_step": 0.01, "volume_min": 0.01, "volume_max": 10.0,
                "spread": 0.0, "slippage_reserve": 0.0,
                "execution_allowance": allowance, "tail_slippage": tail}
        lot = _mod.Atom._lot_for_stop(size, distance)
        assert lot is not None, distance
        worst = lot * (distance + allowance + tail)
        usual = lot * (distance + allowance)
        assert worst <= cap + 1e-9, f"مسافة {distance}: أسوأ {worst:.2f} فوق السقف"
        print(f"  وقف={distance:5.1f}  لوت={lot:5.2f}  معتادة={usual:6.2f}$  أسوأ={worst:6.2f}$ ✓")
    # وبلا بدل ذيل معلن، الحارس لا يخترع رقمًا ولا يقصّ.
    size = {"risk_amount": 80.0, "max_trade_loss": 80.0, "hard_trade_loss_cap": 100.0,
            "tick_value": 0.01, "tick_size": 0.01, "volume_step": 0.01,
            "volume_min": 0.01, "volume_max": 10.0, "spread": 0.0,
            "slippage_reserve": 0.0, "execution_allowance": 0.0}
    assert _mod.Atom._lot_for_stop(size, 40.0) == 2.0, "الحارس تدخّل بلا بدل مقيس"
    print("  بلا بدل ذيل: لا تقليص ✓")


class _NullLogger:
    def debug(self, *a): pass
    def info(self, *a): pass
    def warning(self, *a): pass
    def error(self, *a): pass
    def critical(self, *a): pass


class FakeEventBus:
    def __init__(self):
        self.published = []
        self._handlers = {}

    def subscribe(self, name, handler):
        self._handlers.setdefault(name, []).append(handler)

    async def publish(self, name, payload):
        self.published.append((name, payload))

    def make_context(self, config):
        return AtomContext(atom_id=551, config=config, logger=_NullLogger(),
                           publish=self.publish, subscribe=self.subscribe)


def _size(symbol="NQ100", price=100.0, buy_lot=0.1, buy_stop=99.0,
          sell_lot=0.1, sell_stop=101.0):
    return {"account_id": "ACC", "broker": "BR", "symbol": symbol, "metadata": {"price": price, "buy_lot": buy_lot,
            "buy_stop": buy_stop, "sell_lot": sell_lot, "sell_stop": sell_stop}}


def _val(side, approved=True, symbol="NQ100", request_id="R1"):
    return {"request_id": request_id, "account_id": "ACC", "broker": "BR", "symbol": symbol, "side": side,
            "approved": approved, "reason": "", "kill_switch_state": False}


async def _new(cfg=None):
    bus = FakeEventBus()
    atom = Atom()
    await atom.initialize(bus.make_context(cfg or dict(CFG)))
    await atom.start()
    return atom, bus


def _outs(bus):
    return [p for n, p in bus.published if n == EVENT_OUT]


def _skips(bus):
    return [p for n, p in bus.published if n == EVENT_SKIPPED]


async def test_direct_path_derives_the_target_when_none_arrives():
    """المسار المباشر لا يمرّر هدفًا فارغًا — يشتقّه من وقف الأمر نفسه.

    ٢٠٢٦-٠٩-٠٩ (ختم `NQ`): الحلقة التي منعت أوّل مركز. المقيس حيًّا
    `555 emitted=3` · `551 built=2` · **`584 legal=0 rejected=2
    INCOMPLETE_ORDER`** — لأنّ `take_profit=None` وصل كما ورد. ولا يصل هدف
    محسوب أصلًا: 526 يحتاج وقفًا من 512 المشتقّ من مركزٍ قائم
    (`published=0 · blocked=208,038 · NO_STOP_PRICE` مع `positions=0`).
    """
    atom, bus = await _new()
    order = atom._direct_order({
        "request_id": "555-abc", "account_id": "ACC", "broker": "BR",
        "action": "OPEN", "symbol": "BTCUSD", "side": "SELL", "volume": 0.21,
        "reference_price": 78978.92, "stop_loss": 79373.8146,
        "take_profit": None})
    assert order is not None
    # ٢٠٢٦-١٠-٠٨ (إصلاح الاختبارات القديمة بأمر المالك): الاسم تاريخيّ؛ اشتقاق الهدف من الوقف × المضاعف (`REWARD_MULTIPLE_FALLBACK`) حُذف بأمر ٠٩-١٩ «ولا هدف احتياطي أو هدف صلب، احذفو» (الالتزام 26f5209f)، فالمحروس الآن عكسه: لا هدف يُخترع، والوقف يعبر كما ورد، و٥٢٥ يرفض الناقص بـINCOMPLETE_ORDER.
    assert order["take_profit"] is None and order["target_source"] is None, order
    assert order["stop_loss"] == 79373.8146 and order["reference_price"] == 78978.92, order


async def test_direct_path_keeps_a_target_that_did_arrive():
    """هدفٌ محسوب يعلو الاحتياطيّ — الاحتياط لا يزاحم مصدرًا حقيقيًّا."""
    atom, bus = await _new()
    order = atom._direct_order({
        "request_id": "555-def", "account_id": "ACC", "broker": "BR",
        "action": "OPEN", "symbol": "BTCUSD", "side": "BUY", "volume": 0.1,
        "reference_price": 100.0, "stop_loss": 99.0, "take_profit": 103.0})
    assert order["take_profit"] == 103.0 and order["target_source"] == "REQUEST"


async def test_direct_path_invents_no_target_without_a_stop():
    """بلا وقف لا مسافة ولا هدف — ولا رقم يُخترع؛ 584 يحرس شرعيّته."""
    atom, bus = await _new()
    order = atom._direct_order({
        "request_id": "555-ghi", "account_id": "ACC", "broker": "BR",
        "action": "OPEN", "symbol": "BTCUSD", "side": "BUY", "volume": 0.1,
        "reference_price": 100.0, "stop_loss": None, "take_profit": None})
    assert order["take_profit"] is None and order["target_source"] is None


async def test_direct_path_refuses_to_derive_from_an_inverted_stop():
    """وقف على الجهة الخطأ لا يُصلَّح هنا — يُرفض عند 584 بسببه الصريح."""
    atom, bus = await _new()
    order = atom._direct_order({
        "request_id": "555-jkl", "account_id": "ACC", "broker": "BR",
        "action": "OPEN", "symbol": "BTCUSD", "side": "BUY", "volume": 0.1,
        "reference_price": 100.0, "stop_loss": 101.0, "take_profit": None})
    assert order["take_profit"] is None and order["target_source"] is None


# ٢٠٢٦-١٠-٠٨ (ختم المالك «nq»): المسار المحجَّم مغلق في الكود (`_SIZED_PATH_CLOSED`)؛ والاختبارات التي تحرس منطقه الداخليّ تفتحه صراحةً بهذا المساعد — تحرس منطقًا مغلقًا لو فُتح يومًا، ويعود العلم مغلقًا بعد كلّ اختبار.
def _open_sized_path(monkeypatch):
    monkeypatch.setattr(_mod, "_SIZED_PATH_CLOSED", False)


def _assert_sized_path_refused(atom, bus, count):
    # ٢٠٢٦-١٠-٠٨ (ختم المالك «nq»): الرفض المعلَن: لا أمر ولا حالة مرغوبة، والسبب INCOMPLETE_SIZE_DATA، والعدّاد يزيد ويُعدّ في الأسباب.
    assert not _outs(bus), "المسار المحجَّم المغلق بنى أمرًا: %r" % _outs(bus)
    assert not [p for n, p in bus.published if n == _mod.EVENT_DESIRED], bus.published
    assert _skips(bus)[-1]["reason"] == _mod.REASON_INCOMPLETE_SIZE_DATA, _skips(bus)[-1]
    assert atom._sized_closed == count, atom._sized_closed
    assert atom._skip_reasons.get(_mod.REASON_INCOMPLETE_SIZE_DATA) == count, atom._skip_reasons


async def test_build_buy(monkeypatch):
    print("\n--- test_build_buy ---")
    atom, bus = await _new()
    await atom._on_account({"account_id": "ACC", "broker": "BR"})
    await atom._on_size(_size())
    # ٢٠٢٦-١٠-٠٨ (ختم المالك «nq»): بالإعداد الافتراضيّ المسار مغلق — طلبٌ بلا حجم ولا سعر مرجعيّ يُرفض معلَنًا ولو حمل وقفًا وهدفًا، ويظهر العدّاد في الشارة.
    await atom._on_validated({**_val("BUY"), "take_profit": 103.0})
    _assert_sized_path_refused(atom, bus, 1)
    h = await atom.health_check()
    assert h.details["sized_path_closed"] == 1 and "محجَّم_مغلق=1" in h.message, h.message
    # ٢٠٢٦-١٠-٠٨ (ختم المالك «nq»): ومنطقه لو فُتح: بلا هدف من التحليل لا أمر ولا هدف 102 مصنوع (أمر ٠٩-١٩)، والهدف الوارد يُبنى كما هو بلا مضاعف.
    _open_sized_path(monkeypatch)
    await atom._on_validated(_val("BUY", request_id="R2"))
    assert not _outs(bus), "بُني أمرٌ بلا هدف من التحليل"
    assert _skips(bus)[-1]["reason"] == "NO_ANALYSIS_TARGET", _skips(bus)[-1]
    await atom._on_validated({**_val("BUY", request_id="R3"), "take_profit": 103.0})
    o = _outs(bus)[-1]
    assert o["side"] == "BUY" and o["volume"] == 0.1
    assert o["stop_loss"] == 99.0
    assert o["take_profit"] == 103.0 and o["target_source"] == "REQUEST", o
    assert o["reward_multiple"] is None, o
    assert o["account_id"] == "ACC"
    assert atom._sized_closed == 1, "المفتوح لا يُعدّ رفضًا"
    print("OK — BUY: مغلقٌ برفضٍ معلَن؛ ولو فُتح lot=0.1 stop=99 target=103 من الطلب")


async def test_build_sell(monkeypatch):
    print("\n--- test_build_sell ---")
    atom, bus = await _new()
    await atom._on_size(_size())
    # ٢٠٢٦-١٠-٠٨ (ختم المالك «nq»): بالإعداد الافتراضيّ رفضٌ معلَن معدود لا أمر.
    await atom._on_validated({**_val("SELL"), "take_profit": 97.0})
    _assert_sized_path_refused(atom, bus, 1)
    # ٢٠٢٦-١٠-٠٨ (ختم المالك «nq»): ولو فُتح: لا هدف 98 مصنوعًا من المضاعف، والهدف الوارد يُبنى كما هو.
    _open_sized_path(monkeypatch)
    await atom._on_validated(_val("SELL", request_id="R2"))
    assert not _outs(bus) and _skips(bus)[-1]["reason"] == "NO_ANALYSIS_TARGET", _skips(bus)
    await atom._on_validated({**_val("SELL", request_id="R3"), "take_profit": 97.0})
    o = _outs(bus)[-1]
    assert o["side"] == "SELL" and o["stop_loss"] == 101.0
    assert o["take_profit"] == 97.0 and o["target_source"] == "REQUEST", o
    print("OK — SELL: مغلقٌ برفضٍ معلَن؛ ولو فُتح stop=101 target=97 من الطلب")


async def test_close_without_ticket_never_becomes_an_open_order():
    """٢٠٢٦-١٠-٠٨ (ختم المالك «nq»): طلب إغلاقٍ بلا تذكرة لا يصير أمر فتح."""
    # ٢٠٢٦-١٠-٠٨ (ختم المالك «nq»): المسار المباشر يردّه لغياب التذكرة، وكان المسار المحجَّم يبنيه ACTION_OPEN بوقف 513؛ الآن رفضٌ معلَن ولا أمر.
    atom, bus = await _new()
    await atom._on_account({"account_id": "ACC", "broker": "BR"})
    await atom._on_size(_size())
    close = {**_val("BUY"), "action": "CLOSE", "volume": 0.1, "reference_price": 100.0,
             "stop_loss": 99.0, "take_profit": 103.0}
    assert atom._direct_order(dict(close)) is None, "المسار المباشر قبل إغلاقًا بلا تذكرة"
    await atom._on_validated(close)
    _assert_sized_path_refused(atom, bus, 1)
    assert not [p for n, p in bus.published if n == EVENT_OUT and p.get("action") == "OPEN"]
    print("OK — إغلاقٌ بلا تذكرة لا يصير أمر فتح")


async def test_skip_not_approved():
    print("\n--- test_skip_not_approved ---")
    atom, bus = await _new()
    await atom._on_size(_size())
    await atom._on_validated(_val("BUY", approved=False))
    assert len(_outs(bus)) == 0, "غير معتمَد لا يُبنى"
    # قبل الإصلاح: تجاهل صامت تمامًا، ولا حدث ولا سبب. الآن لازم ينشر سببه
    # المحدَّد — لا يُخلط بأي سبب تجاهل آخر بالذرّة.
    s = _skips(bus)[-1]
    assert s["reason"] == "UPSTREAM_REJECTED", s["reason"]
    print("OK — غير معتمَد → لا أمر، وسبب UPSTREAM_REJECTED منشور")


async def test_skip_no_size(monkeypatch):
    print("\n--- test_skip_no_size ---")
    # ٢٠٢٦-١٠-٠٨ (ختم المالك «nq»): يحرس منطق المسار المحجَّم المغلق لو فُتح — فيُفتح صراحةً.
    _open_sized_path(monkeypatch)
    atom, bus = await _new()
    await atom._on_validated(_val("BUY"))
    assert len(_outs(bus)) == 0, "بلا تحجيم لا يُبنى"
    s = _skips(bus)[-1]
    assert s["reason"] == "NO_SIZE_YET", s["reason"]
    print("OK — بلا تحجيم → لا أمر، وسبب NO_SIZE_YET منشور")


async def test_skip_bad_stop_side(monkeypatch):
    print("\n--- test_skip_bad_stop_side ---")
    # ٢٠٢٦-١٠-٠٨ (ختم المالك «nq»): يحرس منطق المسار المحجَّم المغلق لو فُتح؛ ومغلقًا يخرج السبب نفسه من الإغلاق لا من الوقف الغائب، فيُفتح ليُختبر الوقف.
    _open_sized_path(monkeypatch)
    atom, bus = await _new()
    # buy_stop above price -> invalid buy stop -> None from 513 normally; simulate missing
    await atom._on_size(_size(buy_lot=None, buy_stop=None))
    await atom._on_validated(_val("BUY"))
    assert len(_outs(bus)) == 0, "ستوب شراء غائب لا يُبنى"
    s = _skips(bus)[-1]
    assert s["reason"] == "INCOMPLETE_SIZE_DATA", s["reason"]
    print("OK — ستوب غائب → لا أمر، وسبب INCOMPLETE_SIZE_DATA منشور — مختلف عن NO_SIZE_YET")


async def test_skip_bad_symbol_or_side():
    print("\n--- test_skip_bad_symbol_or_side ---")
    atom, bus = await _new()
    await atom._on_size(_size())
    bad = _val("HOLD")  # اتجاه مو شراء ولا بيع، وما بيدخل المسار المباشر أصلًا
    await atom._on_validated(bad)
    assert len(_outs(bus)) == 0
    s = _skips(bus)[-1]
    assert s["reason"] == "BAD_SYMBOL_OR_SIDE", s["reason"]
    print("OK — جهة غير صالحة → سبب BAD_SYMBOL_OR_SIDE منشور")


async def test_skip_invalid_risk_distance(monkeypatch):
    print("\n--- test_skip_invalid_risk_distance ---")
    # ٢٠٢٦-١٠-٠٨ (ختم المالك «nq»): يحرس منطق المسار المحجَّم المغلق لو فُتح — فيُفتح صراحةً.
    _open_sized_path(monkeypatch)
    atom, bus = await _new()
    # ستوب الشراء فوق السعر (بالمقلوب) → مسافة مخاطرة سالبة، سبب فيزيائي
    # مختلف عن كل الأسباب التانية — لازم يميّز لحاله.
    await atom._on_size(_size(buy_stop=101.0))
    await atom._on_validated(_val("BUY"))
    assert len(_outs(bus)) == 0
    s = _skips(bus)[-1]
    assert s["reason"] == "INVALID_RISK_DISTANCE", s["reason"]
    print("OK — مسافة مخاطرة غير صالحة → سبب INVALID_RISK_DISTANCE منشور")


async def test_skip_reasons_breakdown_in_health(monkeypatch):
    print("\n--- test_skip_reasons_breakdown_in_health ---")
    # ٢٠٢٦-١٠-٠٨ (ختم المالك «nq»): يحرس منطق المسار المحجَّم المغلق لو فُتح (NO_SIZE_YET) — فيُفتح صراحةً.
    _open_sized_path(monkeypatch)
    atom, bus = await _new()
    await atom._on_validated(_val("BUY"))               # NO_SIZE_YET
    await atom._on_validated(_val("BUY", approved=False))  # UPSTREAM_REJECTED
    h = await atom.health_check()
    breakdown = h.details["skip_reasons"]
    assert breakdown.get("NO_SIZE_YET") == 1, breakdown
    assert breakdown.get("UPSTREAM_REJECTED") == 1, breakdown
    assert h.details["skipped"] == 2
    print("OK — health_check يفصّل الأسباب لا رقمًا واحدًا أعمى:", breakdown)


async def test_skip_no_size_carries_513_reason(monkeypatch):
    print("\n--- test_skip_no_size_carries_513_reason ---")
    # ٢٠٢٦-١٠-٠٨ (ختم المالك «nq»): يحرس منطق المسار المحجَّم المغلق لو فُتح — فيُفتح صراحةً.
    _open_sized_path(monkeypatch)
    atom, bus = await _new()
    await atom._on_account({"account_id": "ACC", "broker": "BR"})
    # T2: 513 rejects sizing for this scope with a real reason it actually
    # emits (atoms/513: STALE_ACCOUNT_SYMBOL_SPECS) -- never invented here.
    await atom._on_size_rejected({"account_id": "ACC", "broker": "BR",
                                   "symbol": "NQ100", "reason": "STALE_ACCOUNT_SYMBOL_SPECS",
                                   "status": "REJECTED", "usable_for_order": False})
    await atom._on_validated(_val("BUY"))
    assert len(_outs(bus)) == 0
    s = _skips(bus)[-1]
    assert s["reason"] == "NO_SIZE_YET", s["reason"]
    assert s["sizing_reason"] == "STALE_ACCOUNT_SYMBOL_SPECS", s
    print("OK — رفض 513 (STALE_ACCOUNT_SYMBOL_SPECS) لا يضيع: يمرّ كـsizing_reason فوق NO_SIZE_YET")


async def test_skip_no_size_without_upstream_reason_stays_honest(monkeypatch):
    print("\n--- test_skip_no_size_without_upstream_reason_stays_honest ---")
    # ٢٠٢٦-١٠-٠٨ (ختم المالك «nq»): يحرس منطق المسار المحجَّم المغلق لو فُتح — فيُفتح صراحةً.
    _open_sized_path(monkeypatch)
    atom, bus = await _new()
    await atom._on_validated(_val("BUY"))
    s = _skips(bus)[-1]
    assert s["reason"] == "NO_SIZE_YET", s["reason"]
    assert "sizing_reason" not in s, s
    print("OK — بلا رفض 513 مسجَّل: لا sizing_reason مخترع")


async def test_size_rejection_cleared_by_fresh_size(monkeypatch):
    print("\n--- test_size_rejection_cleared_by_fresh_size ---")
    # ٢٠٢٦-١٠-٠٨ (ختم المالك «nq»): يحرس منطق المسار المحجَّم المغلق لو فُتح — فيُفتح صراحةً؛ وبعد إصلاح NameError يعود البناء الكامل محروسًا كما كُتب أصلًا.
    _open_sized_path(monkeypatch)
    atom, bus = await _new()
    await atom._on_account({"account_id": "ACC", "broker": "BR"})
    await atom._on_size_rejected({"account_id": "ACC", "broker": "BR",
                                   "symbol": "NQ100", "reason": "NO_ACCOUNT_EQUITY",
                                   "status": "REJECTED"})
    # تحجيم صالح يصل لاحقًا لنفس النطاق -- الرفض القديم لازم ينمحي
    await atom._on_size(_size())
    assert not atom._size_rejections, atom._size_rejections
    await atom._on_validated({**_val("BUY"), "take_profit": 103.0})
    o = _outs(bus)[-1]
    assert o["side"] == "BUY" and o["volume"] == 0.1, o
    assert len(_skips(bus)) == 0, "تحجيم صالح وصل -- ما في تخطّي ولا رفض قديم عالق"
    print("OK — تحجيم صالح لاحق يمسح رفض 513 القديم لنفس النطاق")


async def test_skip_carries_decision_identity():
    print("\n--- test_skip_carries_decision_identity ---")
    atom, bus = await _new()
    v = _val("BUY", approved=False)
    v["decision_id"] = "dec:1"
    v["gate_request_id"] = "gate:1"
    await atom._on_validated(v)
    s = _skips(bus)[-1]
    assert s["decision_id"] == "dec:1" and s["gate_request_id"] == "gate:1", s
    print("OK — التخطّي يحمل هوية القرار كما وصلت (decision_id/gate_request_id)")


async def test_skip_identity_absent_stays_none():
    print("\n--- test_skip_identity_absent_stays_none ---")
    atom, bus = await _new()
    await atom._on_validated(_val("BUY", approved=False))
    s = _skips(bus)[-1]
    assert s["decision_id"] is None and s["gate_request_id"] is None, s
    print("OK — الهوية الغائبة تمرّ None صريحة -- لا اختراع")


async def test_health():
    print("\n--- test_health ---")
    bus = FakeEventBus()
    atom = Atom()
    await atom.initialize(bus.make_context(dict(CFG)))
    assert (await atom.health_check()).state == HealthState.UNHEALTHY
    await atom.start()
    ready = await atom.health_check()
    assert ready.state == HealthState.HEALTHY and ready.message.startswith("READY")
    await atom._on_size(_size())
    await atom._on_validated(_val("BUY"))
    assert (await atom.health_check()).state == HealthState.HEALTHY
    print("OK — الصحة تتدرّج UNHEALTHY→HEALTHY(جاهز، صفر مدخل)→HEALTHY(يعمل)")


async def test_direct_path_unguarded_stop_is_caught_by_584_downstream():
    """Item 22/27 of the 27-atom review ("2 payload shapes + an unguarded
    stop on one path -- adjusted later by 584"): _direct_order() builds an
    order from an already-priced/sized validated payload with ZERO
    validation on stop_loss -- payload.get("stop_loss") passes straight
    through, even as None or on the wrong side of reference_price (the
    sized path DOES validate this via risk_dist <= 0.0; the direct path
    never does). Traced the real pipeline wiring in the manifests, not
    assumed: 552 and 601 (the atom that actually writes to the broker
    bridge) subscribe only to 584's execution.order.legal /
    trading.final_decision -- never to this atom's raw
    execution.order.built. So 584 genuinely gates real execution; this
    end-to-end test proves it with the real 551+584 code, not a
    hand-simulated payload."""
    print("\n--- test_direct_path_unguarded_stop_is_caught_by_584_downstream ---")
    import importlib.util as ilu
    root584 = _Path(__file__).resolve().parents[3] / "قسم 500-549" / "525_شرعية_الستوب"
    spec584 = ilu.spec_from_file_location("_cross22_584", root584 / "atom.py")
    mod584 = ilu.module_from_spec(spec584)
    sys.modules["_cross22_584"] = mod584
    spec584.loader.exec_module(mod584)

    class _DispatchBus:
        def __init__(self):
            self.published = []
            self._handlers = {}

        def subscribe(self, name, handler):
            self._handlers.setdefault(name, []).append(handler)

        async def publish(self, name, payload):
            self.published.append((name, payload))
            for h in list(self._handlers.get(name, [])):
                await h(payload)

        def make_context(self, atom_id, config):
            return AtomContext(atom_id=atom_id, config=config, logger=_NullLogger(),
                               publish=self.publish, subscribe=self.subscribe)

    bus = _DispatchBus()
    atom551 = Atom()
    await atom551.initialize(bus.make_context(551, dict(CFG)))
    await atom551.start()

    atom584 = mod584.Atom()
    await atom584.initialize(bus.make_context(584, {"stop_buffer": 0, "reward_risk": 2.0}))
    await atom584.start()
    await atom584._on_specs({"symbols": [{"account_id": "ACC", "symbol": "NQ100",
                                          "point": 1.0, "stops_level": 2,
                                          "volume_min": 0.1, "volume_step": 0.1,
                                          "volume_max": 10}]})

    # مسار مباشر: الحمولة تحمل volume+reference_price جاهزَين، فـ_direct_order
    # تبني الأمر بلا أي نظرة على stop_loss إطلاقاً -- مُسقَط عمدًا هنا.
    direct_payload = {
        "request_id": "R-direct", "account_id": "ACC", "broker": "BR",
        "symbol": "NQ100", "side": "BUY", "action": "OPEN",
        "approved": True, "reason": "", "kill_switch_state": False,
        "volume": 1.0, "reference_price": 100.0,
    }
    await atom551._on_validated(direct_payload)

    built = [p for n, p in bus.published if n == EVENT_OUT]
    assert built and built[-1]["stop_loss"] is None, (
        "551 يجب أن يبني الأمر بلا أي تحقّق من الستوب على المسار المباشر: %r" % built)
    legal = [p for n, p in bus.published if n == mod584.EVENT_LEGAL]
    rejected = [p for n, p in bus.published if n == mod584.EVENT_REJECTED]
    assert not legal, "584 لا يجوز أن يُجيز أمراً بستوب غائب: %r" % legal
    assert rejected and rejected[-1]["reason"] == "INCOMPLETE_ORDER", (
        "584 يجب أن يرفض الأمر (ستوب غائب) قبل trading.final_decision: %r" % rejected)
    print("OK — ستوب المسار المباشر غير المحروس بـ٥٥١ يُرفَض فعليًّا بـ٥٨٤ قبل التنفيذ الحقيقي")



async def test_target_comes_from_526_not_the_fixed_multiple(monkeypatch):
    """أمر المالك ٢٠٢٦-٠٩-٠٧: «خُد الهدف ممّن كان يديره وأعطه لـ526»."""
    # ٢٠٢٦-١٠-٠٨ (ختم المالك «nq»): يحرس منطق المسار المحجَّم المغلق لو فُتح (لا هدف مخترع) — فيُفتح صراحةً.
    _open_sized_path(monkeypatch)
    # ٢٠٢٦-١٠-٠٨ (إصلاح الاختبارات القديمة بأمر المالك): نقضه أمر ٠٩-١٩ فأُرشف ٥٢٦ (هدف_الربح) وزال `_on_take_profit` مع اشتراكه (26f5209f)؛ الهدف من طلب التحليل حصرًا، فالمحروس: لا مصدر هدفٍ من ذرّة أخرى ولا مضاعف ثابت يحلّ محلّه.
    atom, bus = await _new()
    assert not hasattr(atom, "_on_take_profit"), "عاد مستمع هدف ٥٢٦ المؤرشف"
    import yaml
    manifest = yaml.safe_load((_Path(__file__).resolve().parents[1] / "manifest.yaml").read_text(encoding="utf-8"))
    assert not [e for e in manifest["subscribes"] if "take_profit" in e or "target" in e], manifest["subscribes"]
    await atom._on_account({"account_id": "ACC", "broker": "BR"})
    await atom._on_size(_size())
    await atom._on_validated(_val("BUY"))
    assert not _outs(bus), "بُني أمرٌ بهدفٍ لم يأتِ من التحليل: %r" % _outs(bus)
    assert _skips(bus)[-1]["reason"] == "NO_ANALYSIS_TARGET", _skips(bus)[-1]
    print("OK — لا هدف من 526 ولا من مضاعف")


async def test_fixed_multiple_stays_as_fallback(monkeypatch):
    """بلا هدف من 526 لا يقف الأمر — يعود إلى المضاعف الثابت."""
    # ٢٠٢٦-١٠-٠٨ (ختم المالك «nq»): يحرس منطق المسار المحجَّم المغلق لو فُتح (لا هدف ⟸ رفض) — فيُفتح صراحةً.
    _open_sized_path(monkeypatch)
    # ٢٠٢٦-١٠-٠٨ (إصلاح الاختبارات القديمة بأمر المالك): الاسم تاريخيّ؛ أمر ٠٩-١٩ «ولا هدف احتياطي أو هدف صلب، احذفو» أسقط الاحتياط في المسارين، فالمحروس عكسه: بلا هدف لا أمر ولا 102 مصنوع، بسببٍ معلن.
    atom, bus = await _new()
    await atom._on_account({"account_id": "ACC", "broker": "BR"})
    await atom._on_size(_size())
    await atom._on_validated(_val("BUY"))
    assert not _outs(bus), "عاد الهدف الاحتياطيّ: %r" % _outs(bus)
    assert _skips(bus)[-1]["reason"] == "NO_ANALYSIS_TARGET", _skips(bus)[-1]
    assert atom._skip_reasons.get("NO_ANALYSIS_TARGET") == 1, atom._skip_reasons
    direct = atom._direct_order({
        "request_id": "555-fb", "account_id": "ACC", "broker": "BR",
        "action": "OPEN", "symbol": "NQ100", "side": "BUY", "volume": 0.1,
        "reference_price": 100.0, "stop_loss": 99.0, "take_profit": None})
    assert direct["take_profit"] is None and direct["target_source"] is None, direct
    print("OK — لا احتياط: بلا هدف لا أمر")


async def test_incomputable_target_is_ignored(monkeypatch):
    # ٢٠٢٦-١٠-٠٨ (ختم المالك «nq»): يحرس منطق المسار المحجَّم المغلق لو فُتح (هدفٌ غير صالح لا يُستبدل) — فيُفتح صراحةً.
    _open_sized_path(monkeypatch)
    # ٢٠٢٦-١٠-٠٨ (إصلاح الاختبارات القديمة بأمر المالك): مصدر «الهدف غير القابل للحساب» كان ٥٢٦ المؤرشف (`_on_take_profit` زال)؛ ونظيره اليوم هدفُ طلبٍ على الجهة الخطأ: يُتجاهل ولا يُصلَّح ولا يُستبدل بمضاعف، والأمر يُرفض.
    atom, bus = await _new()
    await atom._on_account({"account_id": "ACC", "broker": "BR"})
    await atom._on_size(_size())
    await atom._on_validated({**_val("BUY"), "take_profit": 99.5})
    assert not _outs(bus), "بُني أمرٌ على هدفٍ تحت سعر الشراء: %r" % _outs(bus)
    assert _skips(bus)[-1]["reason"] == "NO_ANALYSIS_TARGET", _skips(bus)[-1]
    print("OK — هدف غير صالح يُتجاهل ولا يُخترع بديله")

async def main():
    tests = [test_realised_loss_never_passes_the_cap,
             test_build_buy,
        test_target_comes_from_526_not_the_fixed_multiple,
        test_fixed_multiple_stays_as_fallback,
        test_incomputable_target_is_ignored, test_build_sell, test_skip_not_approved,
             test_skip_no_size, test_skip_bad_stop_side, test_health,
             test_skip_bad_symbol_or_side, test_skip_invalid_risk_distance,
             test_skip_reasons_breakdown_in_health,
             test_skip_no_size_carries_513_reason,
             test_skip_no_size_without_upstream_reason_stays_honest,
             test_size_rejection_cleared_by_fresh_size,
             test_skip_carries_decision_identity,
             test_skip_identity_absent_stays_none,
             test_direct_path_unguarded_stop_is_caught_by_584_downstream,
             test_close_without_ticket_never_becomes_an_open_order]
    failed = []
    import inspect
    for t in tests:
        # ٢٠٢٦-١٠-٠٨ (ختم المالك «nq»): المشغّل المباشر يعطي كلّ اختبارٍ يطلب `monkeypatch` نسخةً يتراجع عنها بعده، فيعود المسار المحجَّم مغلقًا.
        patch = pytest.MonkeyPatch()
        try:
            if "monkeypatch" in inspect.signature(t).parameters:
                await t(patch)
            else:
                await t()
        except AssertionError as e:
            failed.append((t.__name__, str(e)))
            print(f"FAILED: {t.__name__}: {e}")
        except Exception as e:
            failed.append((t.__name__, repr(e)))
            print(f"ERROR: {t.__name__}: {e!r}")
        finally:
            patch.undo()
    print("\n" + "=" * 60)
    if failed:
        print(f"فشل {len(failed)} من أصل {len(tests)}")
        sys.exit(1)
    print(f"نجح كل الاختبارات ({len(tests)}/{len(tests)})")


if __name__ == "__main__":
    asyncio.run(main())
