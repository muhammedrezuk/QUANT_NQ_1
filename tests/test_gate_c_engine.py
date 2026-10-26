# -*- coding: utf-8 -*-
"""§5 / Gate C — المحرّك الجديد مقابل المرجع، وأسنانُ البوّابة.

⛔ بابٌ يمرّ دائمًا لا يقيس شيئًا. فنصفُ هذا الملفّ يُثبت أنّ البوّابة
**تسقط** حين تُعطَب الملكيّة عمدًا — وإلّا فالحكم `CLOSED` بلا معنى.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from hot import frame, parity, planner, runtime          # noqa: E402
from tools.gate_b import read_single_run                 # noqa: E402
from tools.gate_c import new_engine, reference           # noqa: E402
from transport.ownership import OwnershipKey             # noqa: E402

TAPE = (_ROOT / "forex_runtime" / "var" / "parity" / "frozen"
        / "tape-20260918-154724.jsonl")
#: الشريط الذي ختمه المالك لـGate B — **هو نفسه** لا شريطٌ جديد.
TAPE_SHA = "8a53220cf8ba2d41ecdfdc50d6b19fdd"


@pytest.fixture(scope="module")
def plan():
    return planner.compile_plan(known_external=planner.external_events())


@pytest.fixture(scope="module")
def blobs():
    if not TAPE.exists():
        pytest.skip("لا شريطَ مجمَّدٌ على هذا الجهاز")
    rows = read_single_run(TAPE)
    return [frame.encode(c) for c in frame.batches(rows, max_records=512)]


@pytest.fixture(scope="module")
def oracle(blobs, tmp_path_factory):
    return reference(blobs, tmp_path_factory.mktemp("c") / "oracle.jsonl")


def _verdict(oracle_rows, engine_rows, stats) -> tuple[bool, dict]:
    result = parity.compare_axes(oracle_rows, engine_rows)
    ok = (result["mismatches"] == 0
          and result["output_count_match"]
          and result["only_left_count"] == 0
          and result["only_right_count"] == 0
          and result["shared"] > 0
          and not result["self_comparison"]
          and stats["dropped_no_owner"] == 0
          and stats["foreign_cycles"] == 0
          and stats["cycles_in_two_workers"] == 0)
    return ok, result


# ── ما تقف عليه البوّابة بنيويًّا ────────────────────────────────────────

def test_the_plan_is_a_dag_and_carries_the_parity_chain_in_order(plan):
    """الترتيب يُثبَت من الخطّة لا من الشريط: `112 ⟶ 414 ⟶ 467`.

    ٢٠٢٦-١٠-٠٧ (ختم المالك «NQ»): خرج `decision.room.state` من السلسلة المقيسة — ناشره 451
    (و466 من بعده) أُرشفا مع فكّ الأقسام عن القرار؛ والموافقة اليوم من 414.
    """
    assert planner.strongly_connected(
        {a: set(v) for a, v in plan.depends_on.items()}) == []
    position = {atom: i for i, atom in enumerate(plan.order)}
    chain = []
    for event in (parity.TICK_EVENT,
                  parity.APPROVED_EVENT, parity.DISPATCH_EVENT):
        makers = plan.producers.get(event, ())
        assert makers, "حدثُ تكافؤٍ بلا ناشرٍ في الخطّة: %s" % event
        chain.append(min(position[a] for a in makers))
    assert chain == sorted(chain), "سلسلةُ التكافؤ ليست مرتَّبةً في الخطّة"
    assert chain[0] < chain[-1]


def test_the_engine_ranks_events_from_the_plan_not_from_a_written_list(plan,
                                                                      tmp_path):
    """الرتبةُ مشتقّةٌ من `plan.order` — تتبدّل بتبدّله بلا لمسِ كود."""
    engine = runtime.HotEngine(plan, tmp_path, workers=2)
    position = {atom: i for i, atom in enumerate(plan.order)}
    for event, rank in engine.rank.items():
        assert rank == min(position[a] for a in plan.producers[event])
    assert engine.rank[parity.TICK_EVENT] < engine.rank[parity.APPROVED_EVENT]


# ── Gate C نفسها ────────────────────────────────────────────────────────

def test_the_frozen_tape_is_the_one_the_owner_sealed():
    import hashlib
    if not TAPE.exists():
        pytest.skip("لا شريطَ مجمَّدٌ على هذا الجهاز")
    digest = hashlib.sha256()
    with open(TAPE, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    assert digest.hexdigest().startswith(TAPE_SHA)


def test_the_new_engine_matches_the_oracle_on_every_axis(plan, blobs, oracle,
                                                         tmp_path):
    """جوهرُ Gate C: نفسُ البايتات، مالكون وأقسامٌ وعمّال ⟶ **صفر اختلاف**."""
    engine, stats = new_engine(blobs, tmp_path / "six", plan, workers=6)
    ok, result = _verdict(oracle, engine, stats)
    assert result["mismatches"] == 0, parity.format_axes(result)
    assert len(engine) == len(oracle) == 4897
    assert result["only_left_count"] == result["only_right_count"] == 0
    assert not result["self_comparison"]
    assert ok


def test_every_record_finds_an_owner_and_no_cycle_lands_in_two_workers(
        plan, blobs, tmp_path):
    """عقد §٤: مالكٌ واحدٌ لكلّ دورة. خرقُه يُعدّ ولا يُبتلع."""
    _engine, stats = new_engine(blobs, tmp_path / "own", plan, workers=6)
    assert stats["dropped_no_owner"] == 0
    assert stats["foreign_cycles"] == 0
    assert stats["cycles_in_two_workers"] == 0
    assert sum(w["records"] for w in stats["per_worker"]) == stats["fed"]
    # ولكلّ عاملٍ مالكوه وحدهم — لا مالكَ في عاملَين
    owners = sum(w["owners"] for w in stats["per_worker"])
    assert owners == 7, "عددُ المالكين على الشريط سبعةٌ مقيسة"


@pytest.mark.parametrize("workers", [1, 2, 3, 6, 12])
def test_the_result_does_not_move_with_the_worker_count(plan, blobs, oracle,
                                                        tmp_path, workers):
    """§٢١ نصًّا: «نفس الملكية · نفس الأقسام» على ٦ أنوية أو ١٢ أو ٢٤.

    وهذا هو الإثبات المباشر: العدد يتبدّل والصفوف **لا تتحرّك**.
    """
    engine, stats = new_engine(blobs, tmp_path / ("w%d" % workers), plan,
                               workers=workers)
    ok, result = _verdict(oracle, engine, stats)
    assert ok, parity.format_axes(result)
    assert len(engine) == len(oracle)


# ── الأسنان: البوّابة يجب أن تسقط ───────────────────────────────────────

def test_a_key_that_splits_a_cycle_across_owners_is_caught(plan, blobs, oracle,
                                                           tmp_path,
                                                           monkeypatch):
    """⛔ عطبٌ متعمَّد: الموافقة في مالكٍ والبوّابة في آخر.

    ولو مرّ هذا لكان الحكم `CLOSED` بلا معنى.
    """
    original = runtime.ownership_key

    def split(payload):
        key = original(payload)
        if key is None:
            return None
        return OwnershipKey(key.account_id,
                            key.symbol + ("A" if "approved" in payload else "B"))

    monkeypatch.setattr(runtime, "ownership_key", split)
    engine, stats = new_engine(blobs, tmp_path / "split", plan, workers=6)
    ok, result = _verdict(oracle, engine, stats)
    assert not ok, "البوّابة عمياء عن فصل الدورة بين مالكَين"
    assert result["mismatches"] > 0
    assert stats["cycles_in_two_workers"] > 0


def test_a_finer_key_that_keeps_the_cycle_whole_still_passes(plan, blobs,
                                                             oracle, tmp_path,
                                                             monkeypatch):
    """والمقابل: مفتاحٌ **أدقّ** لا يفصل دورةً يمرّ — فالبوّابة تقيس الفصل
    لا مجرّدَ تبدّل المفتاح. `trace_id` ثابتٌ داخل الدورة، فتقسيمُه أدقُّ
    ولا يكسر شيئًا.
    """
    original = runtime.ownership_key

    def finer(payload):
        key = original(payload)
        if key is None:
            return None
        return OwnershipKey(
            key.account_id,
            key.symbol + str(payload.get("trace_id") or "")[-1:])

    monkeypatch.setattr(runtime, "ownership_key", finer)
    engine, stats = new_engine(blobs, tmp_path / "finer", plan, workers=6)
    ok, _result = _verdict(oracle, engine, stats)
    assert ok
    assert stats["cycles_in_two_workers"] == 0


def test_a_lost_cycle_is_caught(plan, blobs, oracle, tmp_path):
    """وفقدُ دورةٍ واحدة يسقط الباب — لا تُبتلع صامتة."""
    engine, stats = new_engine(blobs, tmp_path / "lost", plan, workers=6)
    trimmed = dict(engine)
    trimmed.pop(sorted(trimmed)[0])
    ok, result = _verdict(oracle, trimmed, stats)
    assert not ok
    assert result["only_left_count"] == 1


# ── حدُّ ما يشهد به الباب — يُثبَّت كي لا يُنسى ─────────────────────────

def test_the_cold_tape_does_not_preserve_publication_order(plan, blobs,
                                                           tmp_path):
    """⚠️ الرتبةُ تُقاس ولا تُغلِق — والسبب مقيسٌ لا مُدَّعى.

    تِكّةٌ لا تُنشَر بعد القرار الذي سبّبته، ومع ذلك يخالف الشريط رتبةَ
    الخطّة مئاتِ المرّات. فالمخالفة في **ترتيب وصول الصندوق البارد**،
    وعليه لا يصحّ أن يكون ترتيبُ الشريط معيارَ إغلاق.
    """
    _engine, stats = new_engine(blobs, tmp_path / "rank", plan, workers=6)
    assert stats["rank_violations"] > 0, (
        "لو صار الشريط يحفظ الترتيب فهذا خبرٌ يُقرأ، لا حارسٌ يُحذف")
    assert stats["ticks_rejected"] > 0
    # ومع ذلك: صفرُ اختلافٍ — لأنّ المرجع لا يفترض ترتيبًا أصلًا
    assert stats["dropped_no_owner"] == 0


# ── المحرّك وحده، بلا شريط ──────────────────────────────────────────────

def test_a_record_without_an_account_or_symbol_is_counted_not_routed(plan,
                                                                     tmp_path):
    engine = runtime.HotEngine(plan, tmp_path, workers=3)
    engine.feed(parity.TICK_EVENT, {"sequence": 1})
    assert engine.dropped_no_owner == 1
    assert engine.fed == 1
    assert sum(w.records for w in engine.workers) == 0


def test_an_event_outside_the_six_is_ignored(plan, tmp_path):
    engine = runtime.HotEngine(plan, tmp_path, workers=3)
    engine.feed("risk.asset_ledger.state",
                {"account_id": "1", "symbol": "XAUUSD"})
    assert engine.fed == 0


def test_the_same_owner_always_lands_on_the_same_worker(plan, tmp_path):
    """ثباتُ الملكيّة: مفتاحٌ واحدٌ ⟶ عاملٌ واحدٌ مهما تكرّر."""
    engine = runtime.HotEngine(plan, tmp_path, workers=6)
    key = OwnershipKey("52992818", "XAUUSD")
    first = engine.worker_for(key).index
    for _ in range(50):
        assert engine.worker_for(key).index == first
