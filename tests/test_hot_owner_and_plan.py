# -*- coding: utf-8 -*-
"""§5 / A–E — حرّاس المالك والمُجمِّع.

عقدُ الورقة: §٤ ملكيّةٌ واحدة · §٧ ترتيبٌ لا يُكسَر · §١٩ دورةٌ ترفض
الإقلاع · §٢٠ ثلاثُ سياساتٍ ولا «مجهولٌ يُفترَض محلّيًّا» · §٢٥ لا دمجَ
للمدخل · §٢٨ ثباتُ القسم عبر أعداد العمّال · §٢٩ حتميّةُ التجميع.
"""
from __future__ import annotations

import pytest

from hot import planner
from hot.cell import Cell, CellMap, OwnershipError, STATE_SLOTS, partition_of
from transport.ownership import LOGICAL_PARTITIONS, OwnershipKey, OwnershipRegistry


def _payload(symbol: str = "XAUUSD", account: str = "52992818", **over) -> dict:
    row = {"account_id": account, "symbol": symbol, "bid": 2650.1,
           "ask": 2650.4, "sequence": 1}
    row.update(over)
    return row


# ── §٢٨: الملكيّة والقسم ─────────────────────────────────────────────────

def test_the_same_key_always_lands_in_the_same_partition():
    key = OwnershipKey("52992818", "XAUUSD")
    first = partition_of(key)
    assert all(partition_of(OwnershipKey("52992818", "XAUUSD")) == first
               for _ in range(50))
    assert 0 <= first < LOGICAL_PARTITIONS


def test_the_partition_does_not_move_when_the_worker_count_changes():
    """⛔ جوهر §٣: تغييرُ عدد العمّال ≠ تغييرُ ملكيّة البيانات."""
    key = OwnershipKey("52992818", "XAUUSD")
    fixed = partition_of(key)
    workers = {}
    for count in (1, 2, 4, 6, 12, 24, 48):
        registry = OwnershipRegistry(count)
        assert registry.partition_for(key) == fixed, "انتقل القسم بتغيّر العمّال"
        workers[count] = registry.owner_for(key)
    assert len(set(workers.values())) > 1, "الخريطة لم تتغيّر أصلًا — لا معنى للفحص"


def test_the_key_text_uses_the_existing_separator():
    """المفتاح عقدٌ قائم: `account|SYMBOL` — ولا نخترع صيغةً ثانية."""
    assert OwnershipKey("52992818", "XAUUSD").text == "52992818|XAUUSD"


def test_different_symbols_are_different_owners():
    a = OwnershipKey("52992818", "XAUUSD")
    b = OwnershipKey("52992818", "EURUSD")
    assert a != b
    cells = CellMap()
    cells.dispatch(1, _payload("XAUUSD"))
    cells.dispatch(1, _payload("EURUSD"))
    assert len(cells.keys()) == 2


# ── §٤ و§٧ و§١٧: ملكيّةٌ واحدة، ترتيبٌ محفوظ، مرّةٌ واحدة ────────────────

def test_a_payload_never_enters_a_foreign_owner():
    cell = Cell(OwnershipKey("52992818", "XAUUSD"))
    with pytest.raises(OwnershipError):
        cell.admit(1, _payload("EURUSD"))
    assert cell.rejected_foreign == 1
    assert cell.accepted == 0


def test_order_is_preserved_inside_one_owner():
    cell = Cell(OwnershipKey("52992818", "XAUUSD"))
    for seq in (1, 2, 3):
        cell.admit(seq, _payload())
    with pytest.raises(OwnershipError) as err:
        cell.admit(2, _payload())          # N ثمّ N+2 ثمّ N+1
    assert "مكرّر" in str(err.value) or "مكسور" in str(err.value)
    assert cell.accepted == 3


def test_a_sequence_that_goes_backwards_is_refused():
    cell = Cell(OwnershipKey("52992818", "XAUUSD"))
    cell.admit(10, _payload())
    with pytest.raises(OwnershipError):
        cell.admit(9, _payload())
    assert cell.rejected_out_of_order == 1


def test_the_same_input_never_enters_twice():
    """§١٧: مدخلٌ واحد ⟵ توجيهٌ واحد ⟵ انتقالُ حالةٍ واحد."""
    cells = CellMap()
    cells.dispatch(7, _payload())
    with pytest.raises(OwnershipError):
        cells.dispatch(7, _payload())
    assert cells.dispatched == 1


def test_input_is_never_coalesced(tmp_path):
    """⛔ §٢٥: `tick N+1` لا يحلّ محلّ `tick N` في ناقل المدخل الجديد."""
    cell = Cell(OwnershipKey("52992818", "XAUUSD"))
    for seq in range(1, 501):
        cell.admit(seq, _payload(bid=2650.0 + seq))
    assert cell.accepted == 500
    assert cell.last_sequence == 500


def test_a_payload_without_a_key_is_refused():
    cells = CellMap()
    with pytest.raises(OwnershipError):
        cells.dispatch(1, {"bid": 1.0})


def test_the_owner_carries_the_ten_state_slots():
    cell = Cell(OwnershipKey("52992818", "XAUUSD"))
    assert len(STATE_SLOTS) == 10
    assert set(cell.state) == set(STATE_SLOTS)
    cell.write("decision", {"side": "buy"})
    assert cell.read("decision")["side"] == "buy"
    with pytest.raises(OwnershipError):
        cell.write("خانةٌ مخترَعة", {})


def test_one_owner_failure_does_not_touch_another():
    """§٢٤: العزل بالملكيّة — سقوطُ مالكٍ لا يُسقط جاره."""
    cells = CellMap()
    cells.dispatch(1, _payload("XAUUSD"))
    cells.dispatch(1, _payload("EURUSD"))
    with pytest.raises(OwnershipError):
        cells.dispatch(1, _payload("XAUUSD"))          # مكرّر
    ok = cells.cell_for(OwnershipKey("52992818", "EURUSD"))
    ok.admit(2, _payload("EURUSD"))
    assert ok.accepted == 2


# ── §٢٠: ثلاثُ سياساتٍ ولا رابع ──────────────────────────────────────────

@pytest.mark.parametrize("atom_id,expected", [
    ("111", planner.CENTRAL), ("150", planner.CENTRAL),
    ("300", planner.CENTRAL), ("450", planner.CENTRAL),
    ("601", planner.CENTRAL),
    ("160", planner.CROSS_SYMBOL), ("161", planner.CROSS_SYMBOL),
    ("307", planner.CROSS_SYMBOL),
    ("151", planner.LOCAL), ("404", planner.LOCAL), ("466", planner.LOCAL),
])
def test_each_atom_gets_its_declared_policy(atom_id, expected):
    assert planner.policy_for(atom_id) == expected


def test_an_undeclared_dependency_is_never_assumed_local():
    """⛔ §٢٠: اعتمادٌ غير مُعلَنٍ **لا يصير `LOCAL`** ولا حافّةَ له.

    ⚠️ وكان هذا الحارس يطلب استثناءً من المسار العاديّ، فكشف أنّ فرع
    `unknown` صار ميّتًا بعد تصنيف `DANGLING` — فأُزيل الفرع وصار
    الحارس يطالب بما يقع فعلًا: تسميةٌ وعدٌّ، ورفضٌ في الوضع الصارم.
    """
    rows = [
        {"atom_id": "401", "name": "a", "section": 401,
         "subscribes": ("لا-ناشرَ-له",), "publishes": ("x.state",)},
    ]
    plan = planner.compile_plan(rows, known_external=("مسموحٌ آخر",))
    assert plan.policies["401"] == planner.LOCAL      # سياسةُ العقدة
    assert plan.depends_on["401"] == ()               # ولا اعتمادَ مفترَض
    assert plan.dangling == {"لا-ناشرَ-له": ("401",)}
    with pytest.raises(planner.CompileError):
        planner.compile_plan(rows, known_external=("مسموحٌ آخر",),
                             strict_dangling=True)


def test_a_declared_external_event_is_accepted():
    rows = [{"atom_id": "401", "name": "a", "section": 401,
             "subscribes": ("SYS_SECOND",), "publishes": ("x.state",)}]
    plan = planner.compile_plan(rows, known_external=("SYS_SECOND",))
    assert plan.external_inputs == ("SYS_SECOND",)
    assert plan.dangling == {}


def test_a_subscription_with_no_publisher_anywhere_is_named_not_assumed():
    """اشتراكٌ بلا ناشر = **معلَّق**، يُسمَّى ويُعدّ ولا يُبنى عليه اعتماد."""
    rows = [{"atom_id": "401", "name": "a", "section": 401,
             "subscribes": ("حدثٌ-يتيم",), "publishes": ("x.state",)}]
    plan = planner.compile_plan(rows)
    assert plan.dangling == {"حدثٌ-يتيم": ("401",)}
    assert plan.depends_on["401"] == ()
    with pytest.raises(planner.CompileError):
        planner.compile_plan(rows, strict_dangling=True)


# ── §١٩: دورةٌ ترفض الإقلاع، ولا تُكسَر صامتًا ───────────────────────────

def test_a_real_cycle_refuses_the_plan_and_names_itself():
    rows = [
        {"atom_id": "401", "name": "a", "section": 401,
         "subscribes": ("c.state",), "publishes": ("a.state",)},
        {"atom_id": "402", "name": "b", "section": 402,
         "subscribes": ("a.state",), "publishes": ("b.state",)},
        {"atom_id": "403", "name": "c", "section": 403,
         "subscribes": ("b.state",), "publishes": ("c.state",)},
    ]
    with pytest.raises(planner.CompileError) as err:
        planner.compile_plan(rows)
    text = str(err.value)
    assert "دورة" in text
    for atom_id in ("401", "402", "403"):
        assert atom_id in text, "الدورة لم تُسمَّ كاملةً"


def test_the_named_cycle_reads_in_the_direction_of_the_flow():
    """⛔ حارسٌ وُلد من خطأٍ في تقريري: كان المسار يُطبَع مقلوبًا.

    `remaining[a]` هو مَن تعتمد عليه `a` — أي الأسلاف. وطباعتُه كما هو
    تجعل القارئ يقرأ الدورة بالاتّجاه المعكوس فيحكم على غير ما وقع.
    """
    rows = [
        {"atom_id": "401", "name": "a", "section": 401,
         "subscribes": ("b.state",), "publishes": ("a.state",)},
        {"atom_id": "402", "name": "b", "section": 402,
         "subscribes": ("a.state",), "publishes": ("b.state",)},
    ]
    with pytest.raises(planner.CompileError) as err:
        planner.compile_plan(rows)
    path = [p.strip() for p in str(err.value).split(":")[-1].split("→")]
    by = {r["atom_id"]: r for r in rows}
    for left, right in zip(path, path[1:]):
        shared = set(by[left]["publishes"]) & set(by[right]["subscribes"])
        assert shared, "الحافّة %s ⟶ %s بلا حدثٍ يصلها" % (left, right)


def test_a_plan_without_a_cycle_orders_producers_before_consumers():
    rows = [
        {"atom_id": "403", "name": "c", "section": 403,
         "subscribes": ("b.state",), "publishes": ("c.state",)},
        {"atom_id": "401", "name": "a", "section": 401,
         "subscribes": (), "publishes": ("a.state",)},
        {"atom_id": "402", "name": "b", "section": 402,
         "subscribes": ("a.state",), "publishes": ("b.state",)},
    ]
    plan = planner.compile_plan(rows)
    assert plan.order == ("401", "402", "403")
    assert plan.depends_on["403"] == ("402",)
    assert plan.dependents["401"] == ("402",)


# ── §٢٩: حتميّة التجميع ──────────────────────────────────────────────────

def test_compiling_the_same_manifests_twice_gives_the_same_plan():
    rows = [
        {"atom_id": "402", "name": "b", "section": 402,
         "subscribes": ("a.state",), "publishes": ("b.state",)},
        {"atom_id": "401", "name": "a", "section": 401,
         "subscribes": (), "publishes": ("a.state",)},
        {"atom_id": "404", "name": "d", "section": 404,
         "subscribes": ("a.state",), "publishes": ("d.state",)},
    ]
    first = planner.compile_plan(rows)
    second = planner.compile_plan(list(reversed(rows)))
    assert first.order == second.order, "الترتيب تبدّل بتبدّل ترتيب القراءة"
    assert first.fingerprint() == second.fingerprint()
    assert first.depends_on == second.depends_on
    assert first.policies == second.policies


def test_the_fingerprint_moves_when_the_graph_moves():
    base = [{"atom_id": "401", "name": "a", "section": 401,
             "subscribes": (), "publishes": ("a.state",)}]
    other = [{"atom_id": "401", "name": "a", "section": 401,
              "subscribes": (), "publishes": ("z.state",)}]
    assert (planner.compile_plan(base).fingerprint()
            != planner.compile_plan(other).fingerprint())


def test_a_duplicate_atom_id_is_refused():
    rows = [{"atom_id": "401", "name": "a", "section": 401,
             "subscribes": (), "publishes": ("a.state",)}] * 2
    with pytest.raises(planner.CompileError):
        planner.compile_plan(rows)


def test_an_empty_manifest_set_is_refused():
    with pytest.raises(planner.CompileError):
        planner.compile_plan([])


# ── الاشتقاق من الرسم لا من قائمةٍ بيد ───────────────────────────────────

def test_external_events_are_derived_not_hand_written():
    """قانون المالك: التصنيف يُشتقّ من الرسم أو من النواة، لا يُكتب بالأسماء."""
    external = planner.external_events()
    assert "SYS_SECOND" in external and "SYS_DAY" in external
    assert "core.atom.started" in external
    # أحداثٌ تنشرها ذرّاتٌ خارج النطاق الساخن
    assert any(e.startswith("feed.") for e in external)
    assert len(external) > 50


def test_the_hot_range_excludes_what_is_outside_it():
    rows = planner.read_manifests()
    assert rows, "لا مانيفستات — الفحص بلا معنى"
    for row in rows:
        assert planner.HOT_RANGE[0] <= row["section"] <= planner.HOT_RANGE[1]


# ── ختم `NQ — ACCEPT FEEDBACK 367→452` ──────────────────────────────────

def _loop_rows():
    """حلقةٌ صغيرةٌ بشكل حلقة التعلّم: منتِجٌ يعود دليلُه إلى مستهلكه."""
    return [
        {"atom_id": "452", "name": "قرار", "section": 452,
         "subscribes": ("learning.model.evidence",),
         "publishes": ("decision.evaluated.state",)},
        {"atom_id": "360", "name": "تسجيل", "section": 360,
         "subscribes": ("decision.evaluated.state",),
         "publishes": ("learning.outcome.recorded",)},
        {"atom_id": "367", "name": "دليل", "section": 367,
         "subscribes": ("learning.outcome.recorded",),
         "publishes": ("learning.model.evidence",)},
    ]


def test_without_the_feedback_declaration_the_loop_stops_the_plan():
    """الحلقة تُوقف الخطّة — وهذا ما جعل الإعلان لازمًا أصلًا.

    ⚠️ ونُزع الإعلانان معًا: بعد ختم «Temporal SCC» صار الحدث وحده كافيًا،
    فحذفُ الحافّة المُعلَنة لا يُعيد الحلقة ما دام حدثها في `FEEDBACK_EVENTS`.
    وكانت هذه الصيغةُ تمرّ وهي لا تفحص شيئًا.
    """
    with pytest.raises(planner.CompileError) as err:
        planner.compile_plan(_loop_rows(), feedback_edges=(), feedback_events=())
    assert "دورة" in str(err.value)


def test_the_declared_feedback_edge_breaks_no_graph_and_is_listed():
    """⛔ الإعلان **لا يحذف الاعتماد**: يُستثنى من ترتيب التِكّة ويُعرَض."""
    plan = planner.compile_plan(
        _loop_rows(),
        feedback_edges=[("367", "452", "learning.model.evidence")])
    assert plan.feedback == (("367", "452", "learning.model.evidence"),)
    assert plan.feedback_stale == ()
    assert "367" not in plan.depends_on["452"], "دخلت اعتمادًا داخل التِكّة"
    # والرسم العاديّ صار بلا دورة، بالترتيب الذي ختمه المالك
    assert plan.order == ("452", "360", "367")


def test_the_feedback_edge_is_per_event_not_per_pair():
    """⛔ دقّةٌ دفعتُ ثمنها: الحدّ `(منتِج، مستهلك، **حدث**)` لا زوجٌ وحده.

    زوجٌ يصل بينهما حدثان: إعلانُ أحدهما راجعًا يترك الآخر اعتمادًا حقيقيًّا
    — وهو الصواب. ولو كان الإعلان بالزوج لأسقط الاعتمادَ الثاني صامتًا.
    """
    rows = [
        {"atom_id": "506", "name": "a", "section": 506,
         "subscribes": ("risk.kill_switch.reset_requested",),
         "publishes": ("risk.halt.requested", "risk.release.requested")},
        {"atom_id": "516", "name": "b", "section": 516,
         "subscribes": ("risk.halt.requested", "risk.release.requested"),
         "publishes": ("risk.kill_switch.reset_requested",)},
    ]
    with pytest.raises(planner.CompileError) as err:
        planner.compile_plan(
            rows, feedback_edges=[("506", "516", "risk.halt.requested")])
    assert "اعتمادًا داخل التِكّة" in str(err.value)


def test_a_feedback_edge_used_as_a_same_cycle_dependency_fails_compilation():
    """حارسُ المالك الصريح: من أعادها حافّةً عاديّةً يفشل تجميعُه."""
    rows = [
        {"atom_id": "367", "name": "a", "section": 367,
         "subscribes": (), "publishes": ("learning.model.evidence", "x.state")},
        {"atom_id": "452", "name": "b", "section": 452,
         "subscribes": ("learning.model.evidence", "x.state"),
         "publishes": ("decision.evaluated.state",)},
    ]
    with pytest.raises(planner.CompileError) as err:
        planner.compile_plan(
            rows, feedback_edges=[("367", "452", "learning.model.evidence")])
    assert "حافّةٌ راجعة" in str(err.value)


def test_a_stale_feedback_declaration_is_named_not_silent():
    """إعلانٌ لحافّةٍ لم تعد في المانيفستات يُسمَّى — لا يُسكَت عنه."""
    rows = [{"atom_id": "401", "name": "a", "section": 401,
             "subscribes": (), "publishes": ("a.state",)}]
    plan = planner.compile_plan(
        rows, feedback_edges=[("999", "998", "حدثٌ-اختفى")])
    assert plan.feedback == ()
    assert plan.feedback_stale == (("999", "998", "حدثٌ-اختفى"),)


def test_the_fingerprint_changes_when_a_feedback_edge_changes():
    rows = _loop_rows()
    with_edge = planner.compile_plan(
        rows, feedback_edges=[("367", "452", "learning.model.evidence")])
    other = planner.compile_plan(
        rows + [{"atom_id": "368", "name": "c", "section": 368,
                 "subscribes": ("learning.outcome.recorded",),
                 "publishes": ("learning.model.evidence",)}],
        feedback_edges=[("367", "452", "learning.model.evidence"),
                        ("368", "452", "learning.model.evidence")])
    assert with_edge.fingerprint() != other.fingerprint()
    assert len(other.feedback) == 2


def test_the_sealed_edges_are_declared_in_code_with_their_events():
    """الحدود التي ختمها المالك مكتوبةٌ بحدثها، لا في رأسي.

    ⚠️ وحقلان في جدوله كانا منقولين، فصُحِّحا **بقاعدته لا بحرفه**:
    الزوج ٥٥٢ ⟶ ٥٦٣ يحمل `trading.final_decision` لا النتيجة المتحقّقة
    (وحاملُها ٥٦٣ ⟶ ٥١٧ عبر `market.outcome.realized`)، والزوج ٥٥١ ⟶ ٥١٨
    يحمل `execution.order.built` لا `risk.asset_ledger.state` (وهو ما
    يُخرجه ٥١٨ لا ما يدخله).
    """
    # ٢٠٢٦-١٠-٠٧ (ختم المالك «NQ»): خرجت `367 ⟶ 452` و`523 ⟶ 581` — 452 و581 أُرشفتا مع فكّ
    # الأقسام عن القرار، فكانتا إعلانًا بائتًا يكسر `feedback_stale == ()`.
    assert planner.FEEDBACK_EDGES == (
        ("516", "506", "risk.kill_switch.reset_requested"),
        ("518", "524", "risk.asset_ledger.state"),
        ("551", "518", "execution.order.built"),
        ("563", "517", "market.outcome.realized"),
        # ⚠️ كتبه المالك `552 ⟶ 516`، والناشر في المانيفست **٥٨٥**.
        # ٢٠٢٦-١٠-٠٢ (ختم المالك «صلح كامل nq»): ٥٨٥ نُقلت إلى الهويّة ٥٢٦ (`ef230e1`،
        # ٢٠٢٦-٠٩-٢٣) والمخطِّط تبعها (`hot/planner.py`: «كان ٥٨٥ — نُقل ٢٠٢٦-٠٩-٢٣»).
        ("526", "516", "risk.margin.validation.completed"),
    )
    rows = {r["atom_id"]: r for r in planner.read_manifests()}
    for producer, consumer, event in planner.FEEDBACK_EDGES:
        assert event in rows[producer]["publishes"],             "%s لا ينشر %s" % (producer, event)
        assert event in rows[consumer]["subscribes"],             "%s لا يشترك في %s" % (consumer, event)


# ── Temporal SCC: الإعلان بالحدث والاشتقاق من الرسم ─────────────────────
#
# ختم المالك ٢٠٢٦-٠٩-١٨:
#
#     EVENT = FEEDBACK
#       ↓ كلّ رجوعٍ منه إلى العقدة التي سبقت إنتاجه
#       ↓ INTER-CYCLE
#
# والحكم: `حدثُ الحافّة راجعٌ` **و** `الحافّة تعود إلى سلف` ⟶ FEEDBACK.
# والشرطان معًا لا أحدهما — وهذا ما تُثبته الحرّاس أدناه.


def _fan_rows():
    """حدثٌ راجعٌ واحدٌ على حافّتين: راجعةٍ وذاهبة.

        200 ⟶ 201 ⟶ 202 ⟶ 200   (`r.done` يعود إلى ٢٠٠: **سلَف**)
                    202 ⟶ 203    (`r.done` يذهب إلى ٢٠٣: **ليس سلفًا**)

    فلو قُطعت الحافّتان بالاسم لانفصل ٢٠٣ عن منتِجه بلا سبب.
    """
    return [
        {"atom_id": "200", "name": "أ", "section": 200,
         "subscribes": ("r.done",), "publishes": ("a.state",)},
        {"atom_id": "201", "name": "ب", "section": 201,
         "subscribes": ("a.state",), "publishes": ("b.state",)},
        {"atom_id": "202", "name": "ج", "section": 202,
         "subscribes": ("b.state",), "publishes": ("r.done",)},
        {"atom_id": "203", "name": "د", "section": 203,
         "subscribes": ("r.done",), "publishes": ("d.state",)},
    ]


def test_an_event_declaration_alone_breaks_the_loop_without_any_edge():
    """العقد الجديد: الحدث يكفي — ولا تُكتب `202⟶200` بيدٍ أبدًا."""
    plan = planner.compile_plan(_fan_rows(), feedback_events=("r.done",),
                                feedback_edges=())
    assert plan.feedback == (("202", "200", "r.done"),)
    assert plan.feedback_derived == (("202", "200", "r.done"),)
    assert plan.feedback_declared == ()
    assert plan.order == ("200", "201", "202", "203")


def test_the_same_event_going_forward_stays_an_ordinary_edge():
    """⛔ الشرط الثاني هو الحارس: «كلّ حافّةٍ تحمل الحدث راجعة» **خطأ**.

    لو صحّ ذلك لانقطع `202 ⟶ 203` وهو اعتمادٌ مشروعٌ داخل التِكّة — وهي
    عينُ الغلطة التي وقعت في `552 ⟶ 563`.
    """
    plan = planner.compile_plan(_fan_rows(), feedback_events=("r.done",),
                                feedback_edges=())
    assert plan.feedback_forward == (("202", "203", "r.done"),)
    assert "202" in plan.depends_on["203"], "قُطع اعتمادٌ ذاهبٌ مشروع"
    assert plan.order.index("202") < plan.order.index("203")


def test_an_event_not_declared_leaves_its_loop_refused():
    """ولا يُشتَقّ إلّا مِن حدثٍ أعلنه المالك: الاشتقاق ليس كسرًا تلقائيًّا."""
    with pytest.raises(planner.CompileError) as err:
        planner.compile_plan(_fan_rows(), feedback_events=(), feedback_edges=())
    assert "مكوّنٌ من 3 ذرّة" in str(err.value)


def test_the_refusal_names_the_members_and_their_events():
    """الرفض يُختَم منه مباشرةً: أعضاءٌ بأسمائهم وحوافُّ بأحداثها."""
    with pytest.raises(planner.CompileError) as err:
        planner.compile_plan(_fan_rows(), feedback_events=(), feedback_edges=())
    text = str(err.value)
    for atom_id in ("200", "201", "202"):
        assert atom_id in text
    assert "r.done" in text and "a.state" in text and "b.state" in text
    assert "203" not in text, "عقدةٌ خارج المكوّن دخلت الرفض"


def test_a_cycle_with_no_declared_event_is_refused_not_broken():
    """⛔ عمودٌ فيه دورةٌ لا يكسرها إعلان: تُسمَّى ويُرفَض البناء (§١٩).

    وهذا هو الفرق بين مُجمِّعٍ يُثبت ومُجمِّعٍ يختار مدخلًا عشوائيًّا.
    """
    rows = [
        {"atom_id": "300", "name": "أ", "section": 300,
         "subscribes": ("y.state",), "publishes": ("x.state",)},
        {"atom_id": "301", "name": "ب", "section": 301,
         "subscribes": ("x.state",), "publishes": ("y.state",)},
    ]
    with pytest.raises(planner.CompileError) as err:
        planner.compile_plan(rows, feedback_events=planner.FEEDBACK_EVENTS,
                             feedback_edges=())
    assert "ترفض الإقلاع" in str(err.value)


def test_the_derivation_is_independent_of_manifest_order():
    """§٢٩: ترتيبُ قراءة المانيفستات لا يغيّر التصنيف ولا البصمة."""
    rows = _fan_rows()
    first = planner.compile_plan(rows, feedback_events=("r.done",),
                                 feedback_edges=())
    for shuffled in (rows[::-1], [rows[2], rows[0], rows[3], rows[1]]):
        other = planner.compile_plan(shuffled, feedback_events=("r.done",),
                                     feedback_edges=())
        assert other.fingerprint() == first.fingerprint()
        assert other.feedback == first.feedback
        assert other.feedback_forward == first.feedback_forward
        assert other.order == first.order


def test_when_both_directions_are_candidates_the_tie_break_is_the_sorted_name():
    """⛔ حارسٌ وُلد من طفرةٍ نجت: `sorted(candidates)` ⟵ `reversed(...)`.

    كان الحارس السابق يبعثر **صفوف المانيفست**، وهي تُرتَّب داخل المُجمِّع
    قبل أن تُبنى المرشّحات — فلم يكن يفحص ترتيب المرشّحات نفسه أصلًا.

    وهذه حلقةٌ ثلاثيّةٌ **كلُّ** حوافّها بحدثٍ راجع، وأرقامُها مختارةٌ كي
    يختلف ترتيبُ البناء عن الترتيب بالاسم: فآخرُ مَن يُفحَص هو مَن يجد
    سلفَه فيصير راجعًا، وهو يتبدّل بتبدّل الترتيب. فيُثبَّت بالاسم.

    ⚠️ وصيغةٌ أولى بعقدتين مرّت على الطفرة: `reversed` على عنصرين انقلبت
    إلى `sorted` نفسِه صدفةً. فالحارس يحتاج ثلاثةً لا اثنين.
    """
    rows = [
        {"atom_id": "410", "name": "أ", "section": 410,
         "subscribes": ("ج.تمّ",), "publishes": ("أ.تمّ",)},
        {"atom_id": "411", "name": "ب", "section": 411,
         "subscribes": ("ب.تمّ",), "publishes": ("ج.تمّ",)},
        {"atom_id": "412", "name": "ج", "section": 412,
         "subscribes": ("أ.تمّ",), "publishes": ("ب.تمّ",)},
    ]
    plan = planner.compile_plan(
        rows, feedback_events=("أ.تمّ", "ب.تمّ", "ج.تمّ"), feedback_edges=())
    assert plan.feedback == (("412", "411", "ب.تمّ"),)
    assert plan.feedback_forward == (("410", "412", "أ.تمّ"),
                                     ("411", "410", "ج.تمّ"))
    assert plan.order == ("411", "410", "412")


def test_a_sealed_edge_is_kept_even_when_its_event_is_undeclared():
    """المختومُ بعينه سندٌ قائمٌ بذاته — لا يسقط بسقوط إعلان الحدث."""
    plan = planner.compile_plan(
        _fan_rows(), feedback_events=(),
        feedback_edges=[("202", "200", "r.done")])
    assert plan.feedback_declared == (("202", "200", "r.done"),)
    assert plan.feedback_derived == ()
    assert plan.feedback_forward == (), "الذاهبةُ لا تُعرَض بلا إعلانِ حدث"
    assert "202" in plan.depends_on["203"]


def test_the_sealed_events_are_written_in_code():
    """`NQ — ACCEPT TEMPORAL SCC BOUNDARIES`: خمسةَ عشرَ حدثًا لا سادسَ عشر."""
    assert planner.FEEDBACK_EVENTS == (
        "learning.model.evidence",
        "market.outcome.realized",
        "execution.order.built",
        "risk.asset_ledger.state",
        "risk.kill_switch.reset_requested",
        "execution.order.rejected",
        "emergency.halt",
        "execution.command.ack",
        "execution.command.failed",
        "execution.manage.written",
        "asset.extraction.confirmed",
        "asset.extraction.failed",
        "risk.margin.validation.completed",
        "learning.model.active.state",
        "dial.profile.state",
    )
    # وكلُّ حافّةٍ مختومةٍ بعينها حدثُها منها — لا سندَ خارجَهما
    for _, _, event in planner.FEEDBACK_EDGES:
        assert event in planner.FEEDBACK_EVENTS
    # ⛔ وما ختمه المالك ذاهبًا لا يُعلَن راجعًا في أيّ موضع
    assert not set(planner.NORMAL_EDGES) & set(planner.FEEDBACK_EDGES)


def test_the_sealed_normal_edges_exist_in_the_graph_with_their_events():
    """المختومُ ذاهبًا يُتحقَّق منه كما يُتحقَّق من الراجع — لا إعلانَ بائت."""
    rows = {r["atom_id"]: r for r in planner.read_manifests()}
    for producer, consumer, event in planner.NORMAL_EDGES:
        assert event in rows[producer]["publishes"],             "%s لا ينشر %s" % (producer, event)
        assert event in rows[consumer]["subscribes"],             "%s لا يشترك في %s" % (consumer, event)


def test_an_edge_sealed_both_ways_is_refused():
    """⛔ راجعةٌ وذاهبةٌ معًا تناقضٌ يُرفَض، ولا يُرجَّح أحدهما صامتًا."""
    with pytest.raises(planner.CompileError) as err:
        planner.compile_plan(
            _fan_rows(), feedback_events=("r.done",),
            feedback_edges=[("202", "200", "r.done")],
            normal_edges=[("202", "200", "r.done")])
    assert "راجعةً وذاهبةً معًا" in str(err.value)


def test_a_stale_normal_declaration_is_named_not_silent():
    rows = [{"atom_id": "401", "name": "a", "section": 401,
             "subscribes": (), "publishes": ("a.state",)}]
    plan = planner.compile_plan(rows, feedback_edges=(),
                                normal_edges=[("9", "8", "حدثٌ-اختفى")])
    assert plan.normal_sealed == ()
    assert plan.normal_stale == (("9", "8", "حدثٌ-اختفى"),)


# ── زوجٌ راجعٌ في الاتّجاهين: الرسم لا يفصل، فلا تفصل الأبجديّة ──────────

def _two_way_rows():
    """`600 ⟷ 601`، وكلا الحدثين راجعٌ مُعلَن. والرسم لا يرجّح."""
    return [
        {"atom_id": "600", "name": "حارس", "section": 600,
         "subscribes": ("رفض.تمّ",), "publishes": ("حكم.تمّ",)},
        {"atom_id": "601", "name": "مدقّق", "section": 601,
         "subscribes": ("حكم.تمّ",), "publishes": ("رفض.تمّ",)},
    ]


def test_a_two_way_candidate_pair_is_refused_not_decided_by_the_alphabet():
    """⛔ الحارس الذي وُلد من مسار مال: `585 ⟷ 552`.

    قطع الفرزُ بالاسم حكمَ الهامش الذاهب إلى المدقّق، فصار المدقّق يوافق
    على هامشِ **دورةٍ ماضية**. ولا يُترَك مثلُ هذا لترتيب الحروف.
    """
    with pytest.raises(planner.CompileError) as err:
        planner.compile_plan(_two_way_rows(),
                             feedback_events=("حكم.تمّ", "رفض.تمّ"),
                             feedback_edges=(), normal_edges=())
    text = str(err.value)
    assert "الاتّجاهين" in text and "NORMAL_EDGES" in text
    assert "حكم.تمّ" in text and "رفض.تمّ" in text


def test_a_normal_seal_resolves_the_pair_in_the_declared_direction():
    """وختمُ الذاهب يفضّه: المختومُ يدخل العمود، فيصير عكسُه راجعًا اشتقاقًا."""
    plan = planner.compile_plan(
        _two_way_rows(), feedback_events=("حكم.تمّ", "رفض.تمّ"),
        feedback_edges=(), normal_edges=[("600", "601", "حكم.تمّ")])
    assert plan.normal_sealed == (("600", "601", "حكم.تمّ"),)
    assert plan.feedback == (("601", "600", "رفض.تمّ"),)
    assert "600" in plan.depends_on["601"], "قُطع الذاهبُ المختوم"
    assert plan.order == ("600", "601")


def test_the_normal_seal_is_inside_the_plan_fingerprint():
    """ختمُ الذاهب جزءٌ من العقد، فيدخل البصمة — لا يُبدَّل صامتًا.

    ⛔ حارسٌ وُلد من طفرةٍ نجت: الصيغةُ الأولى قارنت خطّتين يختلف فيهما
    **الرسم** أيضًا، فكانت البصمة تتبدّل بسبب `depends_on` لا بسبب الختم.

    فالخطّتان هنا متطابقتان حرفًا — الرسمُ والترتيبُ والراجعُ كلُّه — ولا
    يفترقان إلّا في أنّ `202 ⟶ 203` ختمها المالك ذاهبةً أو تركها تُشتَقّ.
    """
    free = planner.compile_plan(_fan_rows(), feedback_events=("r.done",),
                                feedback_edges=(), normal_edges=())
    sealed = planner.compile_plan(_fan_rows(), feedback_events=("r.done",),
                                  feedback_edges=(),
                                  normal_edges=[("202", "203", "r.done")])
    assert sealed.depends_on == free.depends_on
    assert sealed.order == free.order
    assert sealed.feedback == free.feedback
    assert sealed.normal_sealed == (("202", "203", "r.done"),)
    assert free.normal_sealed == ()
    assert sealed.fingerprint() != free.fingerprint()


def test_flipping_the_normal_seal_flips_which_side_is_the_feedback():
    """وقلبُ ختم الذاهب يقلب الراجع — وهو ما يجعل الختم قرارًا لا زينة."""
    other = planner.compile_plan(
        _two_way_rows(), feedback_events=("حكم.تمّ", "رفض.تمّ"),
        feedback_edges=(), normal_edges=[("601", "600", "رفض.تمّ")])
    assert other.feedback == (("600", "601", "حكم.تمّ"),)
    assert other.order == ("601", "600")


# ── الرسم الحيّ تحت الختم النهائيّ ───────────────────────────────────────

def test_the_sealed_contract_dissolves_every_component_on_the_live_graph():
    """العقد المكتمل: **٠ مكوّنات** · ترتيبٌ طوبولوجيٌّ كامل · بصمةٌ ثابتة."""
    external = planner.external_events()
    plan = planner.compile_plan(known_external=external)
    # ⛔ لا يُثبَّت عددُ العقد برقمٍ سحريّ: كان `== 162` فسقط الحارس حين
    #    أضاف المالك ذرّةً (‏163). العددُ خبرٌ يُقرأ لا عقدٌ يُنفَّذ، والعقدُ
    #    هو أن يشمل الترتيبُ كلَّ عقدةٍ ولا يبقى مكوّن.
    assert len(plan.order) == len(plan.nodes)
    # ٢٠٢٦-١٠-٠٧ (ختم المالك «NQ»): أرشفة 36 ذرّة حكم من النطاق الساخن مع فكّ الأقسام عن القرار
    # أنزلت العقد من ~156 إلى 121 — انكماشٌ مقصود قُرئ، فالعتبة تتبعه ولا تثبّت عددًا.
    assert len(plan.nodes) >= 115, "الرسم انكمش فجأةً — خبرٌ يُقرأ"
    assert planner.strongly_connected(
        {a: set(v) for a, v in plan.depends_on.items()}) == []
    assert plan.feedback_stale == (), "إعلانٌ راجعٌ بائت"
    assert plan.normal_stale == (), "إعلانٌ ذاهبٌ بائت"
    # ٢٠٢٦-١٠-٠٢ (ختم المالك «صلح كامل nq»): الخطّة ترتّب الحدود، والإعلان بترتيب كتابته؛
    # تطابقا ما دام الناشر ٥٨٥ آخرَ الترتيب، فلمّا صار ٥٢٦ (`ef230e1`) افترقا ترتيبًا لا محتوًى.
    # العقد: الإعلان كلّه حاضرٌ في الخطّة بلا زيادة ولا نقص.
    assert sorted(plan.feedback_declared) == sorted(planner.FEEDBACK_EDGES)
    assert sorted(plan.normal_sealed) == sorted(planner.NORMAL_EDGES)
    # والاشتقاقُ عمل: أكثرُ الراجع لم يُكتب بيدٍ قطّ
    assert len(plan.feedback_derived) > len(plan.feedback_declared)
    # والذاهبُ لم يُقطَع: الحدث نفسه بقي اعتمادًا حيث لا يعود إلى سلف
    assert len(plan.feedback_forward) > 0
    assert planner.compile_plan(
        known_external=external).fingerprint() == plan.fingerprint()


# ٢٠٢٦-١٠-٠٧ (ختم المالك «NQ»): خرج اختبار test_one_event_cuts_only_the_returning_edge_on_the_live_graph — يختبر الحافّة الراجعة 523 ⟶ 581 وطرفها 581 مؤرشف مع فكّ الأقسام عن القرار.


def test_the_margin_verdict_reaches_the_validator_in_the_same_cycle():
    """⛔ ختم المالك: «ولا نقطع المسار الذاهب إلى المدقّق».

    ٥٨٥ ⟶ ٥٥٢ ذاهبةٌ داخل التِكّة، و٥٨٥ ⟶ ٥١٦ راجعة، و٥٥٢ ⟶ ٥٨٥ راجعةٌ
    اشتقاقًا. فمدقّقُ الأمر يقرأ حكمَ هامش **دورته**، لا دورةً ماضية.
    """
    plan = planner.compile_plan(known_external=planner.external_events())
    margin = "risk.margin.validation.completed"
    # ٢٠٢٦-١٠-٠٢ (ختم المالك «صلح كامل nq»): ٥٨٥ ⟵ ٥٢٦ (`ef230e1`، ٢٠٢٦-٠٩-٢٣) — العقد نفسه.
    assert "526" in plan.depends_on["552"], "المدقّق يقرأ هامشًا بائتًا"
    assert ("526", "552", margin) in plan.normal_sealed
    assert ("526", "516", margin) in plan.feedback_declared
    assert ("552", "526", "execution.order.rejected") in plan.feedback_derived
    assert plan.order.index("526") < plan.order.index("552")


# ── الضمانة الثانية: `decision[t]` لا يقرأ دليل دورته ────────────────────

def test_a_feedback_reader_never_sees_evidence_from_its_own_cycle():
    """⛔ ختم المالك: «وليس التعلّمُ الحاليّ ⟶ القرارُ الحاليّ».

    الحالة الحيّة تُكتب داخل الدورة، والملتزمة لا تتحرّك إلّا عند `commit`.
    فقارئ الحافّة الراجعة يستحيل عليه **بالبناء** أن يرى دليل دورته.
    """
    cell = Cell(OwnershipKey("52992818", "XAUUSD"))
    cell.write("strategy", {"evidence": "دورة-1"})
    assert cell.read_committed("strategy") == {}, "رأى دليل دورته"
    cell.commit()
    cell.write("strategy", {"evidence": "دورة-2"})
    assert cell.read("strategy")["evidence"] == "دورة-2"
    assert cell.read_committed("strategy")["evidence"] == "دورة-1"
    cell.commit()
    assert cell.read_committed("strategy")["evidence"] == "دورة-2"
    assert cell.commits == 2


def test_the_committed_snapshot_is_a_copy_not_a_live_reference():
    """لقطةٌ لا إشارة: كتابةٌ لاحقةٌ لا تتسرّب إلى الملتزَم بأثرٍ رجعيّ."""
    cell = Cell(OwnershipKey("52992818", "XAUUSD"))
    cell.write("risk", {"budget": 100})
    cell.commit()
    cell.write("risk", {"budget": 999})
    assert cell.read_committed("risk")["budget"] == 100


def test_reading_an_unknown_slot_from_committed_is_refused():
    cell = Cell(OwnershipKey("52992818", "XAUUSD"))
    with pytest.raises(OwnershipError):
        cell.read_committed("خانةٌ مخترَعة")


def test_the_fingerprint_itself_includes_the_feedback_edges():
    """⛔ حارسٌ وُلد من طفرةٍ نجت: الحارس السابق قارن خطّتين تختلفان في
    **العقد** أيضًا، فكانت البصمة تتبدّل بسبب العقد لا بسبب الحافّة الراجعة.

    فيُبنى هنا كائنان متطابقان حرفًا إلّا في `feedback` وحدها.
    """
    node = planner.Node(atom_id="401", name="a", section=401,
                        subscribes=(), publishes=("a.state",),
                        policy=planner.LOCAL)
    base = dict(nodes={"401": node}, order=("401",),
                depends_on={"401": ()}, policies={"401": planner.LOCAL})
    without = planner.HotPlan(**base)
    with_edge = planner.HotPlan(
        **base, feedback=(("367", "452", "learning.model.evidence"),))
    assert without.nodes == with_edge.nodes
    assert without.order == with_edge.order
    assert without.depends_on == with_edge.depends_on
    assert without.fingerprint() != with_edge.fingerprint(), \
        "البصمة لا ترى الحافّة الراجعة"


# ── المكوّنات المتّصلة بقوّة: تسمية البنية لا مطاردة الحلقات ──────────────

def test_scc_finds_a_simple_loop():
    assert planner.strongly_connected({"a": {"b"}, "b": {"a"}}) == [["a", "b"]]


def test_scc_ignores_a_pure_chain():
    assert planner.strongly_connected({"a": {"b"}, "b": {"c"}, "c": set()}) == []


def test_scc_separates_two_independent_components():
    graph = {"a": {"b"}, "b": {"a"}, "x": {"y"}, "y": {"z"}, "z": {"x"},
             "lone": set()}
    found = planner.strongly_connected(graph)
    assert [len(c) for c in found] == [3, 2]
    assert found[0] == ["x", "y", "z"] and found[1] == ["a", "b"]


def test_scc_sees_a_mass_where_cycle_hunting_sees_many_loops():
    """⛔ سببُ وجود الدالّة: أربع ذرّاتٍ متبادلةٌ تُنتج حلقاتٍ كثيرة وكتلةً
    واحدة. عدُّ الحلقات يوهم بالتعدّد، والمكوّن يقول الحقيقة برقمٍ واحد.
    """
    members = ["a", "b", "c", "d"]
    graph = {m: {o for o in members if o != m} for m in members}
    found = planner.strongly_connected(graph)
    assert len(found) == 1 and found[0] == members


def test_scc_is_deterministic_and_does_not_recurse_on_depth():
    chain = {str(i): {str(i + 1)} for i in range(400)}
    chain["400"] = {"0"}
    found = planner.strongly_connected(chain)
    assert len(found) == 1 and len(found[0]) == 401
    assert found == planner.strongly_connected(chain)
