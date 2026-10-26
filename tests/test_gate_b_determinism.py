# -*- coding: utf-8 -*-
"""§5 / Gate B — حرّاس حتميّة المرجع (ختم `NQ — GATE B`).

المحاور الستّة تُقاس **كلٌّ على حدة**: العدّ، الهويّة، الصنف، القرار،
المخاطر، نيّة الأمر. وحارسُ كلّ محورٍ يزرع اختلافًا في حقلٍ من حقوله
ويطالب بأن يظهر **في محوره هو** لا في غيره — فلا يستر محورٌ محورًا.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from hot import frame, parity

_ROOT = Path(__file__).resolve().parents[1]


def _cycle_id(seq: int) -> str:
    return "52992818|Raw Trading Ltd|XAUUSD|tick|%d" % seq


def _tick(seq: int) -> dict:
    return {"account_id": "52992818", "broker": "Raw Trading Ltd",
            "symbol": "XAUUSD", "sequence": seq, "bid": 2650.10,
            "ask": 2650.40, "price": 2650.25, "timestamp": 1789728431.422,
            "sequence_gap": 0, "out_of_order": False, "provider": "CTRADER",
            "trace_id": "t-%d" % seq}


def _room(seq: int) -> dict:
    return {"account_id": "52992818", "broker": "Raw Trading Ltd",
            "symbol": "XAUUSD", "id": "decision_aggregator", "source": "451",
            "signal": "up", "direction": 12.6047, "confidence": 61.5958,
            "strength": 26.391, "ratio": 59.3496, "readiness_pct": 88.76,
            "room": True, "status": "ok",
            "sections_present": ["150", "200", "250", "300", "350", "400"],
            "trace_id": "trace-%d" % seq}


def _approved(seq: int, *, approved: bool = True) -> dict:
    return {"decision_id": "dec:" + _cycle_id(seq), "account_id": "52992818",
            "broker": "Raw Trading Ltd", "symbol": "XAUUSD",
            "timeframe": "tick", "approved": approved,
            "decision_side": "buy", "score": 50.17, "barriers": [],
            "warnings": [], "rejection": None, "trace_id": "trace-%d" % seq}


def _dispatch(seq: int) -> dict:
    return {"cycle_id": _cycle_id(seq), "account_id": "52992818",
            "symbol": "XAUUSD", "executable": True, "side": "BUY",
            "request_id": "dec:%s:req1" % _cycle_id(seq), "approved": True}


def _stream(count: int = 6) -> list[tuple[int, str, dict]]:
    rows: list[tuple[int, str, dict]] = []
    index = 0
    for seq in range(9000, 9000 + count):
        for name, payload in (
                (parity.TICK_EVENT, _tick(seq)),
                (parity.ROOM_EVENT, _room(seq)),
                (parity.APPROVED_EVENT, _approved(seq, approved=seq % 2 == 0)),
                (parity.DISPATCH_EVENT, _dispatch(seq)),
                (parity.GATE_PASSED_EVENT, {"cycle_id": _cycle_id(seq),
                                            "barriers": [], "approved": True})):
            rows.append((index, name, payload))
            index += 1
    return rows


def _replay(rows, tmp_path, name: str) -> dict[str, dict]:
    out = tmp_path / ("%s.jsonl" % name)
    rec = parity.ParityRecorder(str(out), runtime=name,
                                grace_s=0.0, close_after_s=10 ** 9)
    for chunk in frame.batches(rows, max_records=7):
        _header, records = frame.decode(frame.encode(chunk))
        for _i, event, payload in records:
            rec.observe(event, payload)
    rec.close()
    return parity.load(str(out))


# ── الحتميّة ─────────────────────────────────────────────────────────────

def test_two_replays_of_the_same_frames_are_identical(tmp_path):
    rows = _stream(8)
    left = _replay(rows, tmp_path, "replay-a")
    right = _replay(rows, tmp_path, "replay-b")
    result = parity.compare_axes(left, right)
    assert result["output_count_match"] is True
    assert result["shared"] == len(left) > 0
    assert result["only_left_count"] == result["only_right_count"] == 0
    assert result["self_comparison"] is False
    assert result["mismatches"] == 0, parity.format_axes(result)
    for axis, _fields in parity.AXES:
        assert result["axes"][axis]["mismatches"] == 0, axis


def test_the_frames_fed_to_both_sides_are_byte_identical(tmp_path):
    """نفسُ البايتات حرفًا — وإلّا لم يكن المدخل واحدًا."""
    rows = _stream(5)
    once = b"".join(frame.encode(c) for c in frame.batches(rows, max_records=7))
    twice = b"".join(frame.encode(c) for c in frame.batches(rows, max_records=7))
    assert once == twice


# ── كلّ محورٍ يكشف اختلافه هو ─────────────────────────────────────────────

@pytest.mark.parametrize("axis,field,value", [
    ("cycle_identity", "symbol", "EURUSD"),
    ("decision", "signal", "down"),
    ("decision", "confidence", 1.0),
    ("decision", "approved", None),
    ("decision", "score", 99.9),
    ("risk", "rejection_reason", "FILTER_FAILED"),
    ("risk", "barrier_names", ["asset_filter:FILTER_FAILED"]),
    ("risk", "warnings", ["BLOCKED_UPSTREAM"]),
    ("order_intent", "side", "SELL"),
    ("order_intent", "executable", False),
    ("order_intent", "gate_outcome", "blocked"),
    ("order_intent", "fate", "not_sent"),
])
def test_each_axis_catches_a_difference_in_its_own_field(
        tmp_path, axis, field, value):
    rows = _stream(6)
    left = _replay(rows, tmp_path, "replay-a")
    right = {k: dict(v) for k, v in _replay(rows, tmp_path, "replay-b").items()}
    key = sorted(right)[0]
    assert right[key].get(field) != value, "الزرع لم يغيّر شيئًا: %s" % field
    right[key][field] = value
    result = parity.compare_axes(left, right)
    assert result["mismatches"] > 0
    assert result["axes"][axis]["mismatches"] > 0, "لم يظهر في محوره"
    assert field in result["axes"][axis]["by_field"]
    for other, _fields in parity.AXES:
        if other != axis:
            assert result["axes"][other]["mismatches"] == 0, \
                "تسرّب إلى محور %s" % other


def test_the_kind_axis_catches_a_reclassified_cycle(tmp_path):
    """`cycle_kind` مشتقٌّ من `saw` — فتغييرُه يظهر في محوره وحده."""
    rows = _stream(6)
    left = _replay(rows, tmp_path, "replay-a")
    right = {k: dict(v) for k, v in _replay(rows, tmp_path, "replay-b").items()}
    key = sorted(right)[0]
    right[key]["saw"] = [s for s in right[key]["saw"] if s != "approved"]
    result = parity.compare_axes(left, right)
    assert result["axes"]["cycle_kind"]["mismatches"] == 1
    assert parity.cycle_kind(left[key]) == parity.KIND_DECISION
    assert parity.cycle_kind(right[key]) == parity.KIND_GATE


# ── العدّ والوجود ────────────────────────────────────────────────────────

def test_a_missing_cycle_breaks_the_gate(tmp_path):
    rows = _stream(6)
    left = _replay(rows, tmp_path, "replay-a")
    right = dict(_replay(rows, tmp_path, "replay-b"))
    right.pop(sorted(right)[0])
    result = parity.compare_axes(left, right)
    assert result["output_count_match"] is False
    assert result["only_left_count"] == 1


def test_an_extra_cycle_breaks_the_gate(tmp_path):
    rows = _stream(6)
    left = _replay(rows, tmp_path, "replay-a")
    right = dict(_replay(rows, tmp_path, "replay-b"))
    right["مفتاحٌ مزروع"] = {"cycle_id": "مفتاحٌ مزروع", "runtime": "replay-b"}
    result = parity.compare_axes(left, right)
    assert result["output_count_match"] is False
    assert result["only_right_count"] == 1


def test_comparing_a_run_with_itself_is_flagged(tmp_path):
    """⛔ سجلٌّ يُقارَن بنفسه لا يُثبت حتميّة — يُرفَع العَلَم."""
    rows = _stream(4)
    left = _replay(rows, tmp_path, "replay-a")
    assert parity.compare_axes(left, left)["self_comparison"] is True
    same_runtime = {k: dict(v, runtime="replay-a") for k, v in left.items()}
    assert parity.compare_axes(left, same_runtime)["self_comparison"] is True


def test_two_empty_sides_are_not_a_pass(tmp_path):
    result = parity.compare_axes({}, {})
    assert result["shared"] == 0
    assert result["self_comparison"] is True


# ── لا تسويةَ صامتة (§١٧) ────────────────────────────────────────────────

def test_none_is_not_zero_on_any_axis(tmp_path):
    rows = _stream(4)
    left = _replay(rows, tmp_path, "replay-a")
    right = {k: dict(v) for k, v in _replay(rows, tmp_path, "replay-b").items()}
    key = sorted(right)[0]
    right[key]["score"] = None
    assert left[key]["score"] is not None
    result = parity.compare_axes(left, right)
    assert result["axes"]["decision"]["mismatches"] == 1


def test_a_tiny_float_difference_is_not_swallowed(tmp_path):
    rows = _stream(4)
    left = _replay(rows, tmp_path, "replay-a")
    right = {k: dict(v) for k, v in _replay(rows, tmp_path, "replay-b").items()}
    key = sorted(right)[0]
    right[key]["confidence"] = left[key]["confidence"] + 1e-6
    result = parity.compare_axes(left, right)
    assert result["axes"]["decision"]["mismatches"] == 1


def test_the_report_names_the_field_and_an_example(tmp_path):
    rows = _stream(4)
    left = _replay(rows, tmp_path, "replay-a")
    right = {k: dict(v) for k, v in _replay(rows, tmp_path, "replay-b").items()}
    right[sorted(right)[0]]["side"] = "SELL"
    text = parity.format_axes(parity.compare_axes(left, right))
    assert "order_intent" in text and "side" in text
    assert "mismatches = 1" in text


# ── الأداة ترفض ما يجب أن ترفضه ──────────────────────────────────────────

def test_the_tool_refuses_a_tape_whose_hash_does_not_match(tmp_path):
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "gate_b", str(_ROOT / "tools" / "gate_b.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    tape = tmp_path / "t.jsonl"
    tape.write_text('{"i":0,"name":"x","payload":{}}\n', encoding="utf-8")
    (tmp_path / "t.json").write_text(
        json.dumps({"sha256": "0" * 64, "records": 1, "bytes": 1}),
        encoding="utf-8")
    with pytest.raises(SystemExit) as err:
        mod.verify_tape(tape)
    assert "البصمة" in str(err.value)


def test_the_tool_refuses_a_tape_with_more_than_one_run(tmp_path):
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "gate_b2", str(_ROOT / "tools" / "gate_b.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    tape = tmp_path / "t2.jsonl"
    tape.write_text(
        '{"i":500,"name":"x","payload":{}}\n'
        '{"i":0,"name":"x","payload":{}}\n'
        '{"i":1,"name":"x","payload":{}}\n', encoding="utf-8")
    with pytest.raises(SystemExit) as err:
        mod.read_single_run(tape)
    assert "تشغيلة" in str(err.value)


def test_both_replays_use_one_configuration(tmp_path):
    """نفسُ الإعداد للجانبين — وإلّا لم تكن الحتميّة هي المقيسة."""
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "gate_b3", str(_ROOT / "tools" / "gate_b.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert mod.REPLAY_CONFIG["grace_s"] == 0.0
    assert mod.REPLAY_CONFIG["close_after_s"] >= 10 ** 9
