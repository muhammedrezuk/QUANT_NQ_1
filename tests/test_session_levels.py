"""The page's one test (the owner, 2026-11-01, «nq»): the level the session made, the break then the pullback, the signal as the
decision moment, both sides or the direction's side alone, and the owner's two trades of 26/10 on the real candles."""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
import pytest  # noqa: E402

from backtest import combo_engine as ce  # noqa: E402


def _bars(rows):
    a = np.array(rows, dtype=float)
    return a[:, 0], a[:, 1], a[:, 2], a[:, 3]


def test_three_touches_make_a_ceiling_only_when_all_closed_below():
    o, h, l, c = _bars([[90, 100.0, 89, 95], [95, 101.0, 90, 94], [94, 100.5, 90, 95], [95, 96, 92, 94]])
    sig, lv = ce.session_level_signals(o, h, l, c, 6.0, 3)
    assert not sig and [(x["edge"], x["known"]) for x in lv if x["way"] > 0] == [(101.0, 2)]
    o, h, l, c = _bars([[90, 100.0, 89, 100.0], [95, 101.0, 90, 94], [94, 100.5, 90, 95]])    # the first closed at the band
    assert [x for x in ce.session_level_signals(o, h, l, c, 6.0, 3)[1] if x["way"] > 0] == []


def test_a_grind_upward_makes_no_ceiling():
    rows = [[100 + i, 101.5 + i, 99.5 + i, 101 + i] for i in range(6)]
    o, h, l, c = _bars(rows)
    assert [x for x in ce.session_level_signals(o, h, l, c, 6.0, 3)[1] if x["way"] > 0] == []


def test_pullback_entry_and_confirm_entry():
    rows = [[90, 100.0, 89, 95], [95, 101.0, 90, 94], [94, 100.5, 90, 95],
            [95, 105, 95, 104],                        # the close above the ceiling
            [104, 104.5, 102, 102.5],                  # the first candle against it
            [102.5, 106, 102, 105.5]]                  # the first with it after that
    o, h, l, c = _bars(rows)
    sig = ce.session_level_signals(o, h, l, c, 6.0, 3, "pullback")[0]
    assert [(s["at"], s["side"], s["level"]) for s in sig] == [(4, 1, 101.0)]
    sig = ce.session_level_signals(o, h, l, c, 6.0, 3, "confirm")[0]
    assert [(s["at"], s["side"]) for s in sig] == [(5, 1)]


def test_a_close_back_through_is_a_false_break_and_the_level_stays():
    rows = [[90, 100.0, 89, 95], [95, 101.0, 90, 94], [94, 100.5, 90, 95],
            [95, 105, 95, 104],                        # above
            [104, 104.5, 96, 97],                      # back under: no entry
            [97, 99, 96, 98],                          # nothing
            [98, 106, 98, 105],                        # above again
            [105, 105.5, 103, 103.5]]                  # the pullback
    o, h, l, c = _bars(rows)
    assert [(s["at"], s["side"]) for s in ce.session_level_signals(o, h, l, c, 6.0, 3)[0]] == [(7, 1)]


def test_the_floor_is_the_mirror():
    rows = [[110, 111, 100.0, 105], [105, 110, 99.0, 106], [106, 110, 99.5, 105],
            [105, 105, 95, 96],                        # the close below the floor
            [96, 98, 95.5, 97.5]]                      # the first green
    o, h, l, c = _bars(rows)
    assert [(s["at"], s["side"], s["level"]) for s in ce.session_level_signals(o, h, l, c, 6.0, 3)[0]] == [(4, -1, 99.0)]


def test_nothing_after_the_candle_is_read():
    rows = [[90, 100.0, 89, 95], [95, 101.0, 90, 94], [94, 100.5, 90, 95], [95, 105, 95, 104], [104, 104.5, 102, 102.5], [102.5, 130, 102, 129]]
    o, h, l, c = _bars(rows)
    full = ce.session_level_signals(o, h, l, c, 6.0, 3)[0]
    cut = ce.session_level_signals(o[:5], h[:5], l[:5], c[:5], 6.0, 3)[0]
    assert [s for s in full if s["at"] < 5] == cut


def test_retest_of_a_fixed_level_both_ways():
    o = np.array([99, 99, 101.5, 101.0, 100.8, 99.0, 97.5, 98.0])
    c = np.array([99, 101.5, 101.0, 100.8, 99.0, 97.5, 98.0, 97.0])
    sig = ce.retest_signals(o, c, 100.0, "pullback").tolist()
    assert sig == [0, 0, 1, 0, 0, 0, -1, 0]        # up at 1, its pullback at 2; down at 4, the first green at 6


def test_signal_moments_are_the_minute_closes_one_per_side():
    t0, t1 = 1000 * 60.0, 2000 * 60.0
    ce.load_minutes, keep = (lambda *_: {"t": np.array([1100 * 60.0, 1101 * 60.0]), "h": np.zeros(2), "l": np.zeros(2),
                                         "c": np.array([10.0, 20.0])}), ce.load_minutes
    try:
        m, c, s, k = ce.signal_moments("USTEC", (np.array([1101 * 60.0, 1101 * 60.0, 1101 * 60.0]), np.array([1, 1, -1]),
                                                 np.array(["a", "b", "c"], dtype=object)), t0, t1)
    finally:
        ce.load_minutes = keep
    assert m.tolist() == [1101 * 60.0, 1101 * 60.0] and c.tolist() == [20.0, 20.0] and s.tolist() == [1, -1] and k.tolist() == ["a", "c"]


def test_atoms_needed():
    spec = {"direction": {"source": "fact", "atom": "209", "frame": "15m", "key": "x"},
            "conditions": [{"atom": "ema", "frame": "", "key": "order.15m"}, {"atom": "301", "frame": "5m", "key": "y"}],
            "entry": {"triggers": [{"atom": "254"}]}, "stop": {"method": "structure"}}
    assert ce.atoms_needed(spec) == {"209", "301", "254", "202"}
    assert ce.atoms_needed({"direction": {"source": "signal"}, "stop": {"method": "fixed"}}) == set()


@pytest.mark.skipif(not ce.HISTORY_DB.exists(), reason="no history here")
def test_the_owners_two_trades_of_26_october():
    """His sell at 29,176 near 17:27 and buy at 29,236 near 17:40 (Turkey): the two are the session's own levels and the first
    pullback after the break, within three points of what he got. This is the tool's check on an example he knows."""
    t0 = datetime(2026, 10, 26, tzinfo=timezone.utc).timestamp()
    if not ce._bars_db("USTEC", "M1", t0 + 14 * 3600, t0 + 15 * 3600):
        pytest.skip("no candles of that day here")
    found = ce.look_at_day({"symbol": "USTEC", "day": "2026-10-26",
                            "entry": {"levels": {"source": "session", "candle": "M1", "tolerance_pips": 6.0, "touches": 3}}})
    assert found["ok"]
    by_time = {s["at"]: s for s in found["signals"]}
    assert by_time["17:27"]["side"] == "بيع" and abs(by_time["17:27"]["price"] - 29176) <= 3
    assert by_time["17:40"]["side"] == "شراء" and abs(by_time["17:40"]["price"] - 29236) <= 3
    assert any(x["kind"] == "سقف" and abs(x["price"] - 29220) <= 1 for x in found["levels"])


def _plan_store_exists(year: str) -> bool:
    return ce.store_for("USTEC", "%s-01-01" % year, "%d-01-01" % (int(year) + 1), {"202", "209"}) is not None


@pytest.mark.skipif(not ce.HISTORY_DB.exists() or not _plan_store_exists("2023"), reason="no store here")
def test_both_sides_and_the_directions_side_on_a_real_week(tmp_path, monkeypatch):
    monkeypatch.setattr(ce, "OUT_ROOT", tmp_path)
    monkeypatch.setattr(ce, "news_times", lambda *a, **k: np.zeros(0))
    store = ce.store_for("USTEC", "2023-01-01", "2024-01-01", {"202", "209"})
    lv = {"source": "session", "candle": "M1", "tolerance_pips": 6.0, "touches": 3, "entry_on": "pullback"}
    base = {"symbol": "USTEC", "from": "2023-03-06", "to": "2023-03-11", "store": str(store), "decision_frame": "signal",
            "entry": {"levels": lv}, "stop": {"method": "structure"}, "scale_with_price": False}
    both = ce.run(ce.merged({**base, "direction": {"source": "signal"}}), log=lambda s: None)
    with_dir = ce.run(ce.merged({**base, "direction": {"source": "fact", "atom": "209", "frame": "15m", "key": "readings.four_hours.trend"}}),
                      log=lambda s: None)
    assert both["moments"] == with_dir["moments"] > 0
    assert with_dir["candidates"] <= both["candidates"]
    assert with_dir["filtered"].get("against_signal", 0) + with_dir["filtered"].get("no_direction", 0) > 0
    for t in both["trades"]["التوليفة"]:
        assert t["level"] == ce.SESSION_KIND


@pytest.mark.skipif(not ce.HISTORY_DB.exists() or not _plan_store_exists("2023"), reason="no store here")
def test_the_plan_writes_the_owners_table_and_says_what_it_could_not_run(tmp_path, monkeypatch):
    monkeypatch.setattr(ce, "OUT_ROOT", tmp_path)
    monkeypatch.setattr(ce, "news_times", lambda *a, **k: np.zeros(0))
    lv = {"source": "session", "candle": "M1", "tolerance_pips": 6.0, "touches": 3}
    exp = lambda label, d: {"label": label, "spec": {"decision_frame": "signal", "direction": d, "entry": {"levels": lv},
                                                     "stop": {"method": "structure"}, "scale_with_price": False}}
    folder = ce.plan_run({"name": "تجربة", "symbols": ["USTEC"], "years": [["2023-03-06", "2023-03-11"]],
                          "experiments": [exp("الجهتان", {"source": "signal"}),
                                          {"label": "بلا مخزن", "spec": {"decision_frame": "15m", "direction": {"source": "fact", "atom": "999", "frame": "15m", "key": "x"}}}]},
                         log=lambda s: None)
    text = (folder / "النتيجة.md").read_text(encoding="utf-8")
    summary = json.loads((folder / "summary.json").read_text(encoding="utf-8"))
    assert summary["kind"] == "plan" and "هدف أوّل" in text and "لم يُقس" in text
    assert (folder / "الاختبار.md").exists()
