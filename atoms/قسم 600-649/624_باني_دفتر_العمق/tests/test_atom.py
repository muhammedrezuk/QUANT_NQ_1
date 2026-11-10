"""اختبارات باني دفتر العمق 624 — العقد: يبني ولا يحكم."""
from __future__ import annotations

import asyncio
import importlib.util
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))

_spec = importlib.util.spec_from_file_location(
    "atom_624", Path(__file__).resolve().parents[1] / "atom.py")
mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mod)


class Bus:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict]] = []

    async def publish(self, name: str, payload: dict | None = None) -> None:
        self.events.append((name, payload or {}))

    def subscribe(self, name: str, handler: Any) -> None:
        pass

    def of(self, name: str) -> list[dict]:
        return [p for n, p in self.events if n == name]


def build():
    from core.contracts.atom import AtomContext
    bus = Bus()
    atom = mod.Atom()
    ctx = AtomContext(atom_id=624, config={"state_every": 1000}, logger=None,
                      publish=bus.publish, subscribe=bus.subscribe,
                      subscribe_all=lambda h: None)
    asyncio.run(atom.initialize(ctx))
    asyncio.run(atom.start())
    return atom, bus


def raw(seq: int, entries: list[dict], snapshot: bool = False) -> dict:
    return {"provider": "CTRADER", "account_id": "52992818",
            "broker": "Raw Trading Ltd", "symbol": "BTCUSD",
            "timestamp": 1788790000.0 + seq, "sequence": seq,
            "sequence_gap": 0, "out_of_order": False, "fabric_gap": False,
            "entries": entries, "is_snapshot": snapshot,
            "exchange_timestamp": 1788790000.0 + seq}


def feed(atom, payload):
    asyncio.run(atom._on_raw(payload))


def test_snapshot_builds_the_ladder():
    atom, bus = build()
    feed(atom, raw(1, [
        {"entry_type": "0", "entry_id": "b1", "price": 100.0, "size": 5, "action": "0"},
        {"entry_type": "1", "entry_id": "a1", "price": 101.0, "size": 5, "action": "0"}],
        snapshot=True))
    out = bus.of("market.depth")[-1]
    assert out["best_bid"] == 100.0 and out["best_ask"] == 101.0
    assert out["bids"] and out["asks"]
    print("OK — اللقطة تبني السلّم")


def test_incremental_updates_the_existing_book():
    atom, bus = build()
    feed(atom, raw(1, [
        {"entry_type": "0", "entry_id": "b1", "price": 100.0, "size": 5, "action": "0"}],
        snapshot=True))
    feed(atom, raw(2, [
        {"entry_type": "0", "entry_id": "b2", "price": 102.0, "size": 3, "action": "0"}]))
    out = bus.of("market.depth")[-1]
    assert out["best_bid"] == 102.0, "المستوى الأعلى صار القمّة"
    assert len(out["bids"]) == 2, "التزايديّ لا يمسح ما قبله"
    print("OK — التزايديّ يبني فوق القائم")


def test_snapshot_clears_before_rebuilding():
    atom, bus = build()
    feed(atom, raw(1, [
        {"entry_type": "0", "entry_id": "b1", "price": 100.0, "size": 5, "action": "0"}],
        snapshot=True))
    feed(atom, raw(2, [
        {"entry_type": "0", "entry_id": "z9", "price": 50.0, "size": 1, "action": "0"}],
        snapshot=True))
    out = bus.of("market.depth")[-1]
    assert len(out["bids"]) == 1 and out["best_bid"] == 50.0, "اللقطة تمسح ثم تبني"
    print("OK — اللقطة تمسح ما قبلها")


def test_delete_empties_the_book_and_declares_it():
    atom, bus = build()
    feed(atom, raw(1, [
        {"entry_type": "0", "entry_id": "b1", "price": 100.0, "size": 5, "action": "0"}],
        snapshot=True))
    feed(atom, raw(2, [
        {"entry_type": "0", "entry_id": "b1", "price": 0, "size": 0, "action": "2"}]))
    out = bus.of("market.depth")[-1]
    assert out["book_empty"] is True, "الدفتر خلا ⇒ يُعلَن لا يُكتم"
    assert out["best_bid"] is None and out["best_ask"] is None
    print("OK — الدفتر الخالي حالة تُعلَن")


def test_abandonment_dial_reaches_every_book():
    """عيار المالك يصل الدفتر — لا يبقى حبيس المانيفست.

    ٢٠٢٦-٠٩-٠٩ (ختم `NQ`): عمر هجر المستوى صار عيارًا لأنّ سي‑تريدر لا يُقلّم
    (صفر لقطة `W` على 200 ثانية · الحذف لا يطال إلا قيدًا عمره ≤ 0.4ث · 474
    من 502 قيدٍ بقيت حيّة). حارسٌ بنيويّ: لو انقطع السلك بين المانيفست
    والدفتر لعاد الاختناق صامتًا — القبول كان 12% ولا شيء يشتكي.
    """
    from core.contracts.atom import AtomContext
    bus = Bus()
    atom = mod.Atom()
    ctx = AtomContext(atom_id=624, config={"state_every": 1000,
                                           "crossed_stale_after_s": 3.5},
                      logger=None, publish=bus.publish, subscribe=bus.subscribe,
                      subscribe_all=lambda h: None)
    asyncio.run(atom.initialize(ctx))
    asyncio.run(atom.start())
    feed(atom, raw(1, [{"entry_type": "0", "entry_id": "b1", "price": 100.0,
                        "size": 5, "action": "0"}], snapshot=True))
    book = atom._books["BTCUSD"]
    assert book._stale_after_s == 3.5, "العيار لم يصل الدفتر"


def test_book_falls_back_to_the_declared_default_without_the_dial():
    """بلا عيار يبقى الافتراضيّ المعلَن في الدفتر — لا صفر ولا بلا حدّ."""
    from shared.fix_session import _CROSSED_STALE_AFTER_S
    atom, _bus = build()
    feed(atom, raw(1, [{"entry_type": "0", "entry_id": "b1", "price": 100.0,
                        "size": 5, "action": "0"}], snapshot=True))
    assert atom._books["BTCUSD"]._stale_after_s == _CROSSED_STALE_AFTER_S


def test_crossed_book_is_built_not_judged():
    """سبريد مقلوب حدث سوق. الباني يبني ولا يحكم — 106 و112 يحكمان."""
    atom, bus = build()
    feed(atom, raw(1, [
        {"entry_type": "0", "entry_id": "b1", "price": 101.0, "size": 5, "action": "0"},
        {"entry_type": "1", "entry_id": "a1", "price": 99.0, "size": 5, "action": "0"}],
        snapshot=True))
    out = bus.of("market.depth")[-1]
    assert out["best_bid"] == 101.0 and out["best_ask"] == 99.0
    print("OK — السبريد المقلوب يُبنى ويُنشر")


def test_identity_and_sequence_fields_survive():
    atom, bus = build()
    feed(atom, raw(7, [
        {"entry_type": "0", "entry_id": "b1", "price": 100.0, "size": 5, "action": "0"}],
        snapshot=True))
    out = bus.of("market.depth")[-1]
    for key in ("account_id", "broker", "provider", "sequence",
                "sequence_gap", "out_of_order", "fabric_gap",
                "exchange_timestamp"):
        assert key in out, f"حقل الهويّة/التتبّع ضاع: {key}"
    assert out["sequence"] == 7
    print("OK — الهويّة والتتبّع يعبران")


def test_every_update_publishes_depth():
    atom, bus = build()
    for i in range(5):
        feed(atom, raw(i + 1, [
            {"entry_type": "0", "entry_id": f"b{i}", "price": 100.0 + i,
             "size": 1, "action": "0"}]))
    assert len(bus.of("market.depth")) == 5, "كل تحديث ينشر عمقًا"
    assert atom._published == 5 and atom._applied == 5
    print("OK — خمسة تحديثات ⇒ خمسة أعماق")


def test_malformed_is_counted_not_swallowed():
    atom, bus = build()
    feed(atom, {"symbol": "BTCUSD"})            # بلا entries
    feed(atom, raw(1, []))                       # قائمة فارغة تُنشر بدفتر خالٍ
    assert atom._malformed == 1
    print("OK — الحمولة العاجزة تُحصى")


def test_health_reports_counters():
    atom, bus = build()
    feed(atom, raw(1, [
        {"entry_type": "0", "entry_id": "b1", "price": 100.0, "size": 5, "action": "0"}],
        snapshot=True))
    health = asyncio.run(atom.health_check())
    assert health.state.name == "HEALTHY"
    assert "published=1" in health.message and "books=1" in health.message
    print("OK — الصحّة تعلن العدّادات")


def test_snapshot_does_not_persist_the_book():
    """سلّم مُعاد من لقطة قديمة سلّمٌ يكذب — يُعاد البناء من أوّل W."""
    atom, bus = build()
    feed(atom, raw(1, [
        {"entry_type": "0", "entry_id": "b1", "price": 100.0, "size": 5, "action": "0"}],
        snapshot=True))
    snap = asyncio.run(atom.snapshot())
    assert "books" not in snap and "bids" not in snap
    fresh, _ = build()
    asyncio.run(fresh.restore(snap))
    assert fresh._published == 1 and not fresh._books
    print("OK — الدفتر لا يُحفظ، العدّادات تعود")


def _build_with(**config):
    from core.contracts.atom import AtomContext
    bus = Bus()
    atom = mod.Atom()
    cfg = {"state_every": 1000}
    cfg.update(config)
    ctx = AtomContext(atom_id=624, config=cfg, logger=None,
                      publish=bus.publish, subscribe=bus.subscribe,
                      subscribe_all=lambda h: None)
    asyncio.run(atom.initialize(ctx))
    asyncio.run(atom.start())
    return atom, bus


def _wide(levels: int) -> list[dict]:
    """سلّم عريض: `levels` عرضًا و`levels` طلبًا حول 100/101."""
    rows = []
    for i in range(levels):
        rows.append({"entry_type": "0", "entry_id": f"b{i}",
                     "price": 100.0 - i, "size": 1, "action": "0"})
        rows.append({"entry_type": "1", "entry_id": f"a{i}",
                     "price": 101.0 + i, "size": 1, "action": "0"})
    return rows


def test_publish_levels_cuts_the_wire_not_the_book():
    """القصّ عرضٌ لا حذف: الدفتر يبقى كاملًا والقمّة تُقرأ منه كاملًا.

    ٢٠٢٦-٠٩-٠٩ — القياس الحيّ: رسالة عمق واحدة = 57,487 بايتًا (1,767 عرضًا
    و357 طلبًا) تُنشر 1.7/ث وتُنسخ لكل مشترك، ومستهلكها الوحيد للسلّم (106)
    سقفه عشرة مستويات. فالمنشور يُقصّ، والمحفوظ لا.
    """
    atom, bus = _build_with(publish_levels=5)
    feed(atom, raw(1, _wide(40), snapshot=True))
    out = bus.of("market.depth")[-1]
    assert len(out["bids"]) == 5 and len(out["asks"]) == 5, "المنشور لم يُقصّ"
    assert len(atom._books["BTCUSD"].bids) == 40, "الدفتر المحفوظ مُسّ — ممنوع"
    assert len(atom._books["BTCUSD"].asks) == 40
    assert out["best_bid"] == 100.0 and out["best_ask"] == 101.0, "القمّة تبدّلت"
    print("OK — القصّ عرضٌ لا حذف")


def test_cut_keeps_the_best_levels_in_order():
    """المقصوص هو الأفضل لا الأوّل الذي وصل — والترتيب ترتيب السلّم."""
    atom, bus = _build_with(publish_levels=3)
    feed(atom, raw(1, _wide(30), snapshot=True))
    out = bus.of("market.depth")[-1]
    assert [row["price"] for row in out["bids"]] == [100.0, 99.0, 98.0]
    assert [row["price"] for row in out["asks"]] == [101.0, 102.0, 103.0]
    print("OK — يُقصّ الأبعد لا الأفضل")


def test_cut_declares_what_it_left_behind():
    """ما يُرمى بصمت لا يُرى: العدد الأصليّ يخرج مع الحمولة."""
    atom, bus = _build_with(publish_levels=4)
    feed(atom, raw(1, _wide(25), snapshot=True))
    out = bus.of("market.depth")[-1]
    assert out["bid_levels_total"] == 25 and out["ask_levels_total"] == 25
    assert out["publish_levels"] == 4
    print("OK — المقصوص معلَن لا مكتوم")


def test_zero_publishes_the_whole_ladder():
    """صفر = السلوك قبل العيار حرفيًّا — لا قصّ ولا مفاجأة."""
    atom, bus = _build_with(publish_levels=0)
    feed(atom, raw(1, _wide(30), snapshot=True))
    out = bus.of("market.depth")[-1]
    assert len(out["bids"]) == 30 and len(out["asks"]) == 30
    assert out["bid_levels_total"] == 30
    print("OK — صفر ينشر الكلّ")


def test_absent_dial_behaves_like_zero():
    """مانيفست بلا العيار = السلوك الأوّل — لا كسر لنسخة لم تُحدَّث."""
    atom, bus = build()
    feed(atom, raw(1, _wide(12), snapshot=True))
    out = bus.of("market.depth")[-1]
    assert len(out["bids"]) == 12 and atom._publish_levels == 0
    print("OK — غياب العيار لا يقصّ")


def test_cut_does_not_touch_the_crossed_contract():
    """السبريد المقلوب يُبنى ويُنشر حتى مع القصّ — العقد لم يتبدّل."""
    atom, bus = _build_with(publish_levels=2)
    feed(atom, raw(1, [
        {"entry_type": "0", "entry_id": "b1", "price": 101.0, "size": 5, "action": "0"},
        {"entry_type": "1", "entry_id": "a1", "price": 99.0, "size": 5, "action": "0"}],
        snapshot=True))
    out = bus.of("market.depth")[-1]
    assert out["best_bid"] == 101.0 and out["best_ask"] == 99.0
    print("OK — القصّ لا يحكم على سعر")


def test_health_declares_the_deepest_ladder_and_the_dial():
    """اللوحة تقرأ التضخّم بالرقم — لا تكتشفه من بطء."""
    atom, bus = _build_with(publish_levels=5)
    feed(atom, raw(1, _wide(20), snapshot=True))
    health = asyncio.run(atom.health_check())
    assert "deepest=40" in health.message, health.message
    assert "cut=5" in health.message
    assert health.details["deepest_ladder"] == 40
    print("OK — الصحّة تعلن عمق السلّم والعيار")


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
    print("\n624: كل الاختبارات خضراء")


def test_cap_trims_the_book_itself_from_the_far_side():
    """سقف الدفتر يُسقط الأبعد عن القمّة — والقمّة لا تُمسّ.

    أمر المالك ٢٠٢٦-٠٩-٠٩ («حط حد ينظفها»). العلّة المقيسة: سي‑تريدر لا
    يحذف ما هجره، فالسلّم بلغ 1,767 عرضًا، ثمّ 1,724 مستوًى في دقائق حين
    تضاعف التدفّق — والطرف المتضخّم يتجاوزه السعر فيتقاطع ويُرفض كل شيء.
    """
    atom, bus = _build_with(max_book_levels=5)
    feed(atom, raw(1, _wide(40), snapshot=True))
    book = atom._books["BTCUSD"]
    assert len(book.bids) == 5 and len(book.asks) == 5, "الدفتر لم يُقلَّم"
    out = bus.of("market.depth")[-1]
    assert out["best_bid"] == 100.0 and out["best_ask"] == 101.0, "القمّة مُسّت"
    # الباقي هو الأقرب إلى القمّة لا الأبعد
    assert sorted((p for p, _ in book.bids.values()), reverse=True) == [
        100.0, 99.0, 98.0, 97.0, 96.0]
    assert sorted(p for p, _ in book.asks.values()) == [
        101.0, 102.0, 103.0, 104.0, 105.0]
    assert atom._trimmed == 70, atom._trimmed
    print("OK — السقف يقلّم من البعيد لا من القمّة")


def test_cap_cleans_the_bookkeeping_behind_it():
    """`_seen` و`_touched` يُنظَّفان مع المُسقَط — وإلّا نمَوَا خلف الدفتر.

    تسريبة صامتة مكان تسريبة مرئيّة: الدفتر يبدو مقلَّمًا والذاكرة تكبر.
    """
    atom, _bus = _build_with(max_book_levels=6)
    feed(atom, raw(1, _wide(50), snapshot=True))
    book = atom._books["BTCUSD"]
    assert len(book._seen) == len(book.bids) + len(book.asks) == 12
    assert len(book._touched) == 12
    print("OK — لا شيء ينمو خلف الدفتر")


def test_cap_zero_leaves_the_book_untouched():
    """صفر = السلوك قبل السقف حرفيًّا."""
    atom, _bus = _build_with(max_book_levels=0)
    feed(atom, raw(1, _wide(40), snapshot=True))
    assert len(atom._books["BTCUSD"].bids) == 40
    assert atom._trimmed == 0
    print("OK — صفر لا يقلّم")


def test_cap_survives_a_book_without_private_bookkeeping():
    """دفترٌ لا يعرف `_seen`/`_touched` لا يُسقط الطريق الحيّ.

    درس ٢٠٢٦-٠٩-٠٩: التحميل الحارّ يُبقي `shared` مخبّأً، وتوقيعٌ مفقود
    هناك كان يرمي على كل رسالة (9.5 خطأ/ثانية وصفر عمق).
    """
    atom, _bus = _build_with(max_book_levels=3)
    feed(atom, raw(1, _wide(20), snapshot=True))
    book = atom._books["BTCUSD"]
    del book._seen
    del book._touched
    atom._trim_book(book)                     # لا يرمي
    assert len(book.bids) == 3 and len(book.asks) == 3
    print("OK — غياب الدفاتر الخاصّة لا يكسر التقليم")


def test_health_declares_the_cap_and_what_it_trimmed():
    atom, _bus = _build_with(max_book_levels=4)
    feed(atom, raw(1, _wide(30), snapshot=True))
    health = asyncio.run(atom.health_check())
    assert "cap=4" in health.message and "trimmed=" in health.message, health.message
    assert health.details["max_book_levels"] == 4
    assert health.details["trimmed"] == atom._trimmed > 0
    print("OK — الصحّة تعلن السقف وما قُلّم")


def test_rate_matching_drops_the_intermediate_not_the_data():
    """مواءمة المعدّل تُسقط نشرةً وسيطة — ولا تُسقط مستوًى واحدًا.

    ٢٠٢٦-٠٩-٠٩: الوسيط 10 رسائل/ث وما خلف 624 يهضم 3.5/ث، فالفارق يتراكم
    حتى بلغ عمرُ الطابع عند التِكّة 211–262 ثانية بينما هو 13–25 عند المصدر.
    """
    atom, bus = _build_with(min_publish_interval_s=99.0)
    feed(atom, raw(1, [{"entry_type": "0", "entry_id": "b1", "price": 100.0,
                        "size": 1, "action": "0"}], snapshot=True))
    assert len(bus.of("market.depth")) == 1, "اللقطة تُنشر دائمًا"

    for i in range(5):                     # خمس تزايديّات داخل النافذة
        feed(atom, raw(i + 2, [{"entry_type": "0", "entry_id": f"b{i}",
                                "price": 90.0 + i, "size": 1, "action": "0"}]))
    assert len(bus.of("market.depth")) == 1, "نُشرت نشرة وسيطة رغم النافذة"
    assert atom._coalesced == 5
    # وكلّها طُبِّقت على الدفتر — لا بيانات ضاعت. خمسة قيود لا ستّة: القيد
    # `b1` من اللقطة استبدله التزايديّ الحامل للمعرّف نفسه — وهذا هو
    # السلوك الصحيح (المعرّف يخاطب مستوًى بعينه، لا يضيف جديدًا).
    assert len(atom._books["BTCUSD"].bids) == 5
    assert atom._applied == 6
    print("OK — تُسقط النشرة الوسيطة لا المستوى")


def test_snapshot_is_never_coalesced():
    """اللقطة إعادة بناء لا خطوة وسيطة — تمرّ مهما كانت النافذة."""
    atom, bus = _build_with(min_publish_interval_s=99.0)
    feed(atom, raw(1, [{"entry_type": "0", "entry_id": "b1", "price": 100.0,
                        "size": 1, "action": "0"}], snapshot=True))
    feed(atom, raw(2, [{"entry_type": "0", "entry_id": "z9", "price": 50.0,
                        "size": 1, "action": "0"}], snapshot=True))
    assert len(bus.of("market.depth")) == 2, "كُتمت لقطة"
    assert bus.of("market.depth")[-1]["best_bid"] == 50.0


def test_each_symbol_has_its_own_window():
    """نافذة رمزٍ لا تكتم رمزًا آخر — وإلّا جوّع الرمزُ النشط جارَه."""
    atom, bus = _build_with(min_publish_interval_s=99.0)
    for sym in ("BTCUSD", "XAUUSD", "EURUSD"):
        p = raw(1, [{"entry_type": "0", "entry_id": "b1", "price": 100.0,
                     "size": 1, "action": "0"}])
        p["symbol"] = sym
        feed(atom, p)
    assert len(bus.of("market.depth")) == 3
    assert atom._coalesced == 0


def test_zero_publishes_every_update():
    """صفر = السلوك قبل المواءمة حرفيًّا."""
    atom, bus = _build_with(min_publish_interval_s=0.0)
    for i in range(6):
        feed(atom, raw(i + 1, [{"entry_type": "0", "entry_id": f"b{i}",
                                "price": 100.0 + i, "size": 1, "action": "0"}]))
    assert len(bus.of("market.depth")) == 6 and atom._coalesced == 0
    print("OK — صفر ينشر كل تحديث")


def test_health_declares_what_was_coalesced():
    atom, _bus = _build_with(min_publish_interval_s=99.0)
    for i in range(4):
        feed(atom, raw(i + 1, [{"entry_type": "0", "entry_id": f"b{i}",
                                "price": 100.0 + i, "size": 1, "action": "0"}]))
    health = asyncio.run(atom.health_check())
    assert "coalesced=3" in health.message, health.message
    assert health.details["coalesced"] == 3


def test_every_arrival_is_counted_even_when_dropped():
    """كل وصول يُعدّ — وإلّا صار «لم يصلني» و«رميتُه» وجهًا واحدًا.

    ٢٠٢٦-٠٩-٠٩: قِيس على الناقل 15.15 رسالة/ث تُنشر و3.09 تخرج من هنا،
    ولم يكن ثمّة عدّاد يفصل السببين — فادّعيتُ مواكبةً كاذبة. باب
    `not self._running` كان يرجع بلا أثر، وهو أوّل المشتبهين عند اختلال
    المرور (نسخة موقوفة تبقى مشتركة بعد تحميل حارّ).
    """
    atom, bus = build()
    feed(atom, raw(1, [{"entry_type": "0", "entry_id": "b1", "price": 100.0,
                        "size": 1, "action": "0"}], snapshot=True))
    assert atom._received == 1 and atom._skipped_stopped == 0

    asyncio.run(atom.stop())
    for i in range(4):
        feed(atom, raw(i + 2, [{"entry_type": "0", "entry_id": f"b{i}",
                                "price": 100.0, "size": 1, "action": "0"}]))
    assert atom._received == 5, "الوصول لا يُعدّ حين تكون الذرّة موقوفة"
    assert atom._skipped_stopped == 4
    assert atom._published == 1, "نشرت وهي موقوفة"
    assert len(bus.of("market.depth")) == 1
    print("OK — الوصول يُعدّ ولو رُمي")


def test_health_declares_arrivals_against_publishes():
    """اللوحة تقرأ نسبة التمرير بالرقم — لا تستنتجها من بطء المستهلك."""
    atom, _bus = build()
    for i in range(3):
        feed(atom, raw(i + 1, [{"entry_type": "0", "entry_id": f"b{i}",
                                "price": 100.0 + i, "size": 1, "action": "0"}]))
    health = asyncio.run(atom.health_check())
    assert "rcv=3" in health.message and "stopped=0" in health.message, health.message
    assert health.details["received"] == 3


def test_the_manifest_ships_with_no_delay_at_all():
    """⛔ حارس حكم المالك: لا تأخير في المنشور — ولو كسب جودةً.

    ٢٠٢٦-٠٩-٠٩، حرفيًّا: «بتعرف بتخرّب بيتي؟ هي بالسوق الأمريكي على ناسداك
    إذا في خبر». عند خبر يقطع السعر مئات النقاط في أجزاء من الثانية،
    فنشرُ «أحدث حالة كل ثانيتين» قرارٌ على سعرٍ مات. الدمج كسب قبولًا من
    ٩٤.٩٪ إلى ٩٩.٥٪ — ولا يساوي ثانيتين على خبر.

    من يرفع هذا العيار في المانيفست يُسقط هذا الاختبار، فيقرأ الحكم قبل
    أن ينقضه.
    """
    import yaml
    from pathlib import Path
    manifest = Path(__file__).resolve().parents[1] / "manifest.yaml"
    cfg = yaml.safe_load(manifest.read_text(encoding="utf-8"))["config"]
    assert cfg.get("min_publish_interval_s", 0) == 0, (
        "عاد التأخير إلى المنشور — اقرأ حكم المالك في المانيفست قبل تغييره")
    print("OK — لا تأخير في المنشور")


class _Clock:
    def __init__(self): self.t = 1000.0
    def __call__(self): return self.t


def test_stale_levels_are_dropped_by_silence_not_by_crossing():
    """المستوى الذي سكت عنه الوسيط يُسقَط — تقاطع أو لم يتقاطع.

    ٢٠٢٦-٠٩-١٠: على أربع عشرة دقيقة نما السلّم 14 ⟵ 600 بلا استقرار
    (≈42/دقيقة) وهبط القبول ٩٨.١٪ ⟵ ٨٦.٥٪. حارس التقاطع يُسقط المهجور حين
    يتقاطع فقط، والمهجور الذي لم يتقاطع بعدُ يتراكم حتى يفسد القمّة.
    """
    atom, bus = _build_with(stale_level_after_s=30)
    feed(atom, raw(1, _wide(20), snapshot=True))
    book = atom._books["BTCUSD"]
    clock = _Clock()
    book._clock = clock
    for key in book._touched:
        book._touched[key] = clock.t
    assert len(book.bids) == 20 and len(book.asks) == 20

    clock.t += 31                                   # صمت الوسيط عن الجميع
    feed(atom, raw(2, [{"entry_type": "0", "entry_id": "live",
                        "price": 100.5, "size": 1, "action": "0"}]))
    # القيد الحيّ وحده بقي؛ العشرون المهجورة سقطت من الطرفين
    assert len(book.bids) == 1 and len(book.asks) == 0, (len(book.bids), len(book.asks))
    assert atom._stale_dropped == 40
    out = bus.of("market.depth")[-1]
    assert out["best_bid"] == 100.5
    print("OK — الصمت يُسقط المستوى، لا التقاطع")


def test_a_live_level_is_never_dropped_by_age():
    """المستوى الذي يلمسه الوسيط لا يُسقَط مهما طال عمر جيرانه."""
    atom, _bus = _build_with(stale_level_after_s=30)
    feed(atom, raw(1, _wide(10), snapshot=True))
    book = atom._books["BTCUSD"]
    clock = _Clock()
    book._clock = clock
    for key in book._touched:
        book._touched[key] = clock.t - 100          # الكلّ مهجور
    book._touched["b0"] = clock.t                   # إلّا واحدًا حيًّا
    atom._drop_stale_levels(book)
    assert "b0" in book.bids and len(book.bids) == 1
    print("OK — الحيّ لا يُمسّ")


def test_age_drop_is_off_by_default_and_survives_an_old_shared():
    """صفر = السلوك الأوّل · ودفترٌ بلا `_touched` لا يُسقط الطريق الحيّ."""
    atom, _bus = _build_with(stale_level_after_s=0)
    feed(atom, raw(1, _wide(12), snapshot=True))
    assert len(atom._books["BTCUSD"].bids) == 12 and atom._stale_dropped == 0

    atom2, _b2 = _build_with(stale_level_after_s=5)
    feed(atom2, raw(1, _wide(6), snapshot=True))
    book = atom2._books["BTCUSD"]
    del book._touched                                # نسخة `shared` لا تعرفه
    atom2._drop_stale_levels(book)                   # لا يرمي
    assert len(book.bids) == 6
    print("OK — الغياب لا يكسر")


def test_health_declares_what_silence_dropped():
    atom, _bus = _build_with(stale_level_after_s=30)
    feed(atom, raw(1, _wide(8), snapshot=True))
    book = atom._books["BTCUSD"]
    clock = _Clock(); book._clock = clock
    for key in book._touched:
        book._touched[key] = clock.t - 99
    atom._drop_stale_levels(book)
    health = asyncio.run(atom.health_check())
    assert "stale=16" in health.message, health.message
    assert health.details["stale_dropped"] == 16
