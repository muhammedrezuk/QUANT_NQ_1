# -*- coding: utf-8 -*-
"""حرّاس اشتقاق الخروج — القاعدة متعدّية، ومصبّها من النواة لا من قائمة."""
from __future__ import annotations

import textwrap
from pathlib import Path

from engine.egress_graph import (classify, money_closure, money_sinks,
                                 read_declared_graph)

MANIFEST = """
id: {id}
name: "{name}"
version: "1.0.0"
core_version: ">=1.0.0,<2.0.0"
critical: false
entrypoint: "atom:Atom"
dependencies: []
publishes: {publishes}
subscribes: {subscribes}
startup_mode: auto
health: {{interval_ms: 5000, timeout_ms: 2000, failure_threshold: 3,
         restart_on_failure: false, max_restarts: 1, restart_backoff_ms: 1000}}
config_schema: {{type: object, properties: {{}}, additionalProperties: false}}
config: {{}}
"""


def _atoms(tmp_path: Path, rows) -> Path:
    root = tmp_path / "atoms"
    for index, (aid, name, subs, pubs) in enumerate(rows):
        directory = root / ("%d_%s" % (aid, name))
        directory.mkdir(parents=True)
        (directory / "manifest.yaml").write_text(
            textwrap.dedent(MANIFEST).format(
                id=aid, name=name, subscribes=list(subs), publishes=list(pubs)),
            encoding="utf-8")
    return root


def test_sinks_come_from_the_sealed_core_classification() -> None:
    names = {"execution.order.built", "trading.final_decision", "bridge.send.state",
             "analysis.trend.state", "telemetry.snapshot.state", "SYS_SECOND"}
    sinks = money_sinks(names)
    assert "execution.order.built" in sinks
    assert "trading.final_decision" in sinks
    assert "bridge.send.state" in sinks
    assert "analysis.trend.state" not in sinks
    assert "telemetry.snapshot.state" not in sinks
    assert "SYS_SECOND" not in sinks


def test_a_five_hop_chain_to_an_order_is_money_when_the_root_reads_it(tmp_path: Path) -> None:
    """التعدّي يقرّر **العجلة**؛ والقارئ بالاسم يقرّر **العبور**.

    ٢٠٢٦-٠٩-١٨: أوّل صياغةٍ جعلت المال = الإغلاق كلّه، فصار 241 اسمًا من 368
    (61٪) — ومالٌ يعني ستّين بالمئة لا يعني شيئًا: حصّة النقل 0.23 ⟵ 0.43
    والعرض إلى صفر. فصار الشرطان معًا.
    """
    root = _atoms(tmp_path, [
        (101, "a", ["market.tick"], ["analysis.trend.state"]),
        (102, "b", ["analysis.trend.state"], ["stats.mean.state"]),
        (103, "c", ["stats.mean.state"], ["probability.edge.state"]),
        (104, "d", ["probability.edge.state"], ["decision.room.state"]),
        (105, "e", ["decision.room.state"], ["execution.order.built"]),
        (900, "z", ["market.tick"], ["telemetry.snapshot.state"]),
    ])
    chain = ["market.tick", "analysis.trend.state", "stats.mean.state",
             "probability.edge.state", "decision.room.state", "execution.order.built"]
    # الجذر يقرأ السلسلة كلّها ⟵ كلّها مال
    result = classify(root, hot_events=chain)
    for name in chain:
        assert name in result["money"], name
    assert "telemetry.snapshot.state" not in result["money"]

    # ولا يقرأ منها إلّا الطرف ⟵ وحده يعبر مالًا
    narrow = classify(root, hot_events=["execution.order.built"])
    assert narrow["money"] == {"execution.order.built"}
    assert "analysis.trend.state" not in narrow["money"]


def test_a_dead_end_branch_never_becomes_money(tmp_path: Path) -> None:
    root = _atoms(tmp_path, [
        (101, "a", ["market.tick"], ["measurement.health.state"]),
        (800, "t", ["measurement.health.state"], ["telemetry.rollup.state"]),
    ])
    result = classify(root)
    assert "measurement.health.state" not in result["money"]
    assert "telemetry.rollup.state" not in result["money"]
    assert "market.tick" not in result["money"]


def test_a_read_event_off_the_money_chain_is_not_money(tmp_path: Path) -> None:
    """قراءة الجذر وحدها لا ترفع إلى المال — لا بدّ من بلوغ فعلٍ ماليّ."""
    root = _atoms(tmp_path, [(800, "t", ["x.state"], ["y.state"])])
    result = classify(root, hot_events=["y.state"])
    assert "y.state" not in result["money"]
    assert "y.state" not in result["internal"], "له قارئٌ فلا يُحجب"


def test_storage_is_what_only_the_cold_process_reads(tmp_path: Path) -> None:
    root = _atoms(tmp_path, [
        (101, "a", ["market.tick"], ["execution.order.built"]),
        (700, "s", ["archive.row.state"], []),
    ])
    result = classify(root, cold_events=["archive.row.state", "market.tick"])
    assert result["storage"] == {"archive.row.state"}
    assert "market.tick" in result["money"], "حدثٌ ماليّ لا يُخفَّض لأنّ البارد يقرؤه"


def test_a_cycle_in_the_graph_does_not_hang_the_closure(tmp_path: Path) -> None:
    root = _atoms(tmp_path, [
        (101, "a", ["a.state"], ["b.state"]),
        (102, "b", ["b.state"], ["a.state", "execution.order.built"]),
    ])
    result = classify(root, hot_events=["a.state", "b.state"])
    assert {"a.state", "b.state"} <= result["money"]


def test_the_live_tree_lifts_the_facts_the_decision_card_reads() -> None:
    """على الشجرة الحقيقيّة — وهذا ما أخفق فيه الاشتقاق المباشر.

    ٢٠٢٦-١٠-٠٧ (ختم المالك «NQ»): بعد فكّ الأقسام عن القرار لم تعد البنية المتأرجحة
    والسيولة تبلغ أمرًا (مدراؤها 200/250 أُرشفوا)، فصار الاسم والقراءات على ما تقرؤه
    البطاقة 414 من الحقائق — وهو يبلغ المال تعدّيًا: 414 ⟵ 467 ⟵ 555 ⟵ أمر.
    """
    root = Path(__file__).resolve().parents[1] / "atoms"
    reads = ["structure.levels.state", "analysis.trend.state",
             "analysis.volatility.state", "measurement.latency.state"]
    result = classify(root, hot_events=reads)
    for name in reads[:3]:
        assert name in result["money"], name
    assert "measurement.latency.state" not in result["money"], "قياسٌ صار مالًا"

# ── الداخليّ: ما لا يقرؤه أحدٌ خارج المحرّك لا يعبر الحدّ ────────────────────

def test_an_event_nobody_outside_reads_is_internal(tmp_path: Path) -> None:
    """٢٠٢٦-٠٩-١٨: `internal = 0` كان يعني أنّ كلّ شيءٍ يعبر — حتّى ما
    يستهلكه المحرّك نفسه. فظهر ذيلٌ عند 0.578–0.619 ث لأحداثٍ لا قارئ لها."""
    root = _atoms(tmp_path, [
        (200, "structure", ["market.tick"], ["structure.units.state"]),
        (201, "collector", ["structure.units.state"], ["structure.cycle.collected"]),
    ])
    result = classify(root, hot_events=["structure.cycle.collected"],
                      produced_here=["structure.units.state",
                                     "structure.cycle.collected"])
    assert "structure.units.state" in result["internal"], "يعبر بلا قارئ"
    assert "structure.cycle.collected" not in result["internal"], "الجذر يقرؤه"


def test_money_is_never_downgraded_to_internal(tmp_path: Path) -> None:
    root = _atoms(tmp_path, [
        (101, "a", ["market.tick"], ["decision.room.state"]),
        (102, "b", ["decision.room.state"], ["execution.order.built"]),
    ])
    result = classify(root, hot_events=["decision.room.state", "execution.order.built"],
                      produced_here=["decision.room.state", "execution.order.built"])
    assert not (result["money"] & result["internal"]), "حدثٌ ماليّ صُنّف داخليًّا"
    assert "execution.order.built" not in result["internal"]


def test_storage_is_never_downgraded_to_internal(tmp_path: Path) -> None:
    root = _atoms(tmp_path, [(101, "a", ["market.tick"], ["archive.row.state"])])
    result = classify(root, cold_events=["archive.row.state"],
                      produced_here=["archive.row.state"])
    assert result["storage"] == {"archive.row.state"}
    assert not result["internal"]


def test_nothing_is_internal_without_a_produced_set(tmp_path: Path) -> None:
    """بلا `produced_here` يبقى السلوك السابق حرفًا — لا حجب بالمصادفة."""
    root = _atoms(tmp_path, [(101, "a", ["x.state"], ["y.state"])])
    assert classify(root)["internal"] == set()


def test_the_live_tree_marks_unit_states_internal() -> None:
    """على الشجرة الحقيقيّة: ذيل 0.578–0.619 ث كان من هذه بالضبط."""
    root = Path(__file__).resolve().parents[1] / "atoms"
    from engine.egress_graph import published_by
    engine_ids = [aid for aid in range(100, 600)]
    produced = published_by(root, engine_ids)
    result = classify(root, produced_here=produced)
    assert result["internal"], "لا حدث داخليّ على شجرةٍ فيها 235 ذرّة؟"
    assert not (result["internal"] & result["money"])


def test_the_probe_markers_are_never_hidden(tmp_path: Path) -> None:
    """مسبار تِكّة←قرار يقرأ من مرور الأحداث لا باشتراك.

    ٢٠٢٦-٠٩-١٨: حجب `decision.room.state` بوصفه «داخليًّا» أقفل القياس كلّه —
    `closed = 0` من 4,987 أثرًا مفتوحًا. والبادئات تأتي من المسبار نفسه.
    """
    root = _atoms(tmp_path, [(104, "d", ["x.state"], ["decision.room.state"])])
    hidden = classify(root, produced_here=["decision.room.state"])
    assert "decision.room.state" in hidden["internal"], "بلا حماية يُحجب"
    kept = classify(root, produced_here=["decision.room.state"],
                    keep_visible=("decision.room.", "decision.dispatch."))
    assert "decision.room.state" not in kept["internal"]


def test_probe_markers_ride_the_money_path_not_observation(tmp_path: Path) -> None:
    """⛔ جذر ذيل §٢٩ (مقيس ٢٠٢٦-٠٩-١٨ من مسار الأثر): السلسلة تنتهي عند
    0.16 ث ثمّ صمتٌ 0.69–0.81 ث ثمّ يصل الحدث المُغلِق — لأنّ
    `decision.room.state` كان «عرضًا»: يُدمج ويُصرَّف بمضخّةٍ مهلتها نصف ثانية.
    وحدثٌ يعرّف عقد القبول لا يركب مسارًا كسولًا."""
    root = _atoms(tmp_path, [(451, "agg", ["market.tick"], ["decision.room.state"])])
    lazy = classify(root, produced_here=["decision.room.state"])
    assert "decision.room.state" not in lazy["money"], "بلا عقد المسبار يبقى عرضًا"
    sealed = classify(root, produced_here=["decision.room.state"],
                      keep_visible=("market_data.", "decision.room.", "decision.dispatch."),
                      urgent_markers=("decision.room.", "decision.dispatch."))
    assert "decision.room.state" in sealed["money"], "علامة القياس لم تُرفَع إلى المال"
    assert "decision.room.state" not in sealed["internal"]


def test_the_tick_opener_is_not_swept_into_money(tmp_path: Path) -> None:
    """تصحيحٌ في اليوم نفسه: رفعُ بادئة `market_data.` أصعد اثني عشر حدثًا
    إلى المال وأسقط العرض إلى صفر، فأُغرق مسار المال."""
    root = _atoms(tmp_path, [(101, "a", ["x"], ["market_data.quality.state"])])
    result = classify(root, produced_here=["market_data.quality.state"],
                      keep_visible=("market_data.", "decision.room."),
                      urgent_markers=("decision.room.",))
    assert "market_data.quality.state" not in result["money"]
    assert "market_data.quality.state" not in result["internal"], "مرئيٌّ فلا يُحجب"
