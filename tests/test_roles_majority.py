"""The roles by majority (the owner, 2026-11-09: «أغلبيّة», sealed «ىض»): a role passes where more than half of its atoms that
have a reading say yes; a word that says nothing does not vote; the direction role gives the side; the entry's atoms of one
minute keep the side most of them said."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backtest import combo_engine as ce  # noqa: E402
from backtest import full_panel as fp  # noqa: E402


def _words(*ws: str, read: list[bool] | None = None) -> dict:
    words = np.array(ws, dtype=object)
    r = ~np.isin(words, ce.NO_READING_WORDS) if read is None else np.array(read)
    return {"atom": "x", "frame": "4h", "key": "signal", "_words": words, "_read": r}


def test_direction_role_takes_more_than_half_of_those_that_read():
    conds = [_words("rising", "rising", "none", "flat"), _words("up", "down", "none", "flat"),
             _words("rising", "falling", "none", "none")]
    side = ce.role_side(conds, 4)
    # 3 of 3 up · 1 up and 2 down · nobody reads · two read «flat» and point nowhere
    assert side[0] == 1
    assert side[1] == -1
    assert side[2] == 0
    assert side[3] == 0


def test_an_atom_without_the_fact_in_a_store_keeps_quiet():
    # 2026-11-10: 356 has no «signal» on the quarter hour in the Dow's store -- it keeps quiet there, the measure goes on
    quiet = {"atom": "356", "frame": "15m", "key": "signal", "_silent": True,
             "_read": np.zeros(2, dtype=bool), "_yes": np.zeros(2, dtype=bool)}
    assert ce.role_side([_words("up", "down"), quiet], 2).tolist() == [1, -1]
    assert ce.role_pass([_words("up", "up"), quiet], np.array([1, -1])).tolist() == [True, False]


def test_a_tie_gives_no_side():
    conds = [_words("up"), _words("down")]
    assert ce.role_side(conds, 1)[0] == 0


def test_role_passes_on_majority_and_not_without_a_reading():
    yes = {"atom": "y", "frame": "15m", "key": "signal", "_yes": np.array([True, True, False, False]),
           "_read": np.array([True, True, True, False])}
    no = {"atom": "z", "frame": "15m", "key": "signal", "_yes": np.array([True, False, False, False]),
          "_read": np.array([True, True, True, False])}
    same = _words("up", "up", "down", "none")
    got = ce.role_pass([yes, no, same], np.array([1, 1, 1, 1]))
    assert got.tolist() == [True, True, False, False]   # 3/3 · 2/3 · 0/3 · no reading at all


def test_entry_majority_keeps_the_side_most_atoms_said():
    t = np.array([30.0, 40.0, 50.0, 130.0])            # three fire in the first minute, one in the second
    s = np.array([1, 1, -1, -1])
    moments = np.array([60.0, 60.0, 180.0])
    sides = np.array([1, -1, -1])
    assert ce.entry_majority((t, s), moments, sides).tolist() == [True, False, True]


def test_sections_are_counted_for_the_seed():
    seed = next(s for s in fp.SEED_SETTINGS if s["name"].startswith("كلّ الأقسام بأدوارها"))
    spec = seed["experiments"][0]["spec"]
    sec = ce.atoms_by_section(spec)
    total = sum(len(v) for v in sec.values())
    assert total == 18                                   # the seventeen voters and 202 for the stop behind the structure
    assert sec["التحليل"] == ["151", "157", "165"]
    assert "202" in sec["البنية"] and "254" in sec["السيولة"]


def _trade(exit_: str, stage: int):
    tr = ce.Trade("x", 1, 0.0, 100.0, 99.0, [(1.0, 1 / 3), (2.0, 1 / 3), (3.0, 1 / 3)], 1, 2, 1.0, 0.0)
    tr.exit, tr.stage = exit_, stage
    return tr


def test_the_day_law_counts_only_a_full_stop_or_every_target():
    # the owner, 2026-11-10: «اذا صفقة بتضرب تامين ما بتنحسب»
    assert _trade("stop", 0).counted() == "وقف"
    assert _trade("target", 3).counted() == "أهداف"
    assert _trade("stop", 1).counted() == ""          # the first target, then the stop at the entry
    assert _trade("stop", 2).counted() == ""          # two targets, then the trailed stop
    assert _trade("session_end", 1).counted() == ""
    assert ce.DEFAULTS["day_counted"] == 2


def test_law_days_closes_on_any_two():
    rows = [{"day": "2023-01-02", "counted": "وقف"}, {"day": "2023-01-02", "counted": "وقف"},
            {"day": "2023-01-03", "counted": ""}, {"day": "2023-01-03", "counted": "أهداف"}, {"day": "2023-01-03", "counted": "أهداف"},
            {"day": "2023-01-04", "counted": "وقف"}, {"day": "2023-01-04", "counted": "أهداف"},
            {"day": "2023-01-05", "counted": "وقف"}, {"day": "2023-01-05", "counted": ""}]
    got = ce.law_days(rows, 6)
    assert got == {"أيّام_التداول": 6, "وقفان": 1, "الأهداف_مرّتين": 1, "وقف_وأهداف": 1, "لم_يكتمل": 1, "بلا_صفقة": 2}


def test_the_live_as_it_is_keeps_no_day_law_yet():
    live = next(s for s in fp.SEED_SETTINGS if s["name"] == "التوليفة الحيّة كما هي")
    assert live["experiments"][0]["spec"]["day_counted"] == 0


def test_the_seed_names_every_role_and_four_entry_atoms():
    seed = next(s for s in fp.SEED_SETTINGS if s["name"].startswith("كلّ الأقسام بأدوارها"))
    spec = seed["experiments"][0]["spec"]
    roles = {c["role"] for c in spec["conditions"]}
    assert roles == {"الجهة", "حالة السوق", "المكان"} and roles <= set(ce.ROLES)
    assert [t["atom"] for t in spec["entry"]["triggers"]] == ["204", "205", "206", "254"]
    assert spec["direction"] == {"source": "role", "role": "الجهة"}
    assert "بالأغلبيّة" in ce.describe(ce.merged(spec), {})
