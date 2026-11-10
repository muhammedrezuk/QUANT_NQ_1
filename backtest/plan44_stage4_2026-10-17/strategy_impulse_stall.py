# -*- coding: utf-8 -*-
"""Stage 6, attempt 1a/1b (rules declared in the attempts ledger before running): the core of the owner's recorded method --
"the price falls fiercely, then it chokes ... there I enter" -- at the six levels, against random levels with the same rules.

Impulse: within the 30 minutes up to the touch bar the price moved toward the level by >= A x ref (ref = median session range
of the previous five days). Stall: the two bars after the touch do not exceed the touch bar's extreme. Entry: close of the
second stall bar, against the impulse. Stop: beyond the touch extreme + 0.03 x ref, at least 9 pips. Target: 3 x risk.
Cost 1 pip. Entries 09:45-15:30 New York; the enough-time rule from the expected-move table; flat at 16:00; stop first when
stop and target fall in one bar; at most three trades a day and 15 minutes after each. Build and test only.
"""
from __future__ import annotations

import json
import random
import statistics
import sys
import time
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import measure as m1  # noqa: E402
import measure2 as m2  # noqa: E402

ROOT = HERE.parents[1]
TABLE = json.loads((ROOT / "shared" / "expected_move_table.json").read_text(encoding="utf-8"))["symbols"]["USTEC"]
ENTRY_FROM, ENTRY_UNTIL = m1.FIRST15_END, 15 * 60 + 30
IMPULSE_BARS = 6
STALL_BARS = 2
PAD_REF = 0.03
MIN_STOP = 9.0
TARGET_R = 3.0
COST = 1.0
MAX_PER_DAY = 3
WAIT_AFTER_MIN = 15
A_VALUES = (0.15, 0.25)
RANDOM_PER_DAY = 6


def expected(side_up: bool, minute: int, minutes_left: float, ref: float) -> float | None:
    usable = [h for h in TABLE["horizons"] if h <= minutes_left]
    if not usable:
        return None
    slot_min = minute - minute % 30
    cell = TABLE["slots"].get("%02d:%02d" % (slot_min // 60, slot_min % 60), {}).get(str(usable[-1]))
    if not cell:
        return None
    return (cell["up"] if side_up else cell["down"]) * ref


def simulate(after, i_entry, side_up, entry, stop, target):
    """Returns (R, exit_minute)."""
    risk = abs(entry - stop)
    for b in after[i_entry + 1:]:
        hit_stop = b[3] <= stop if side_up else b[2] >= stop
        hit_target = b[2] >= target if side_up else b[3] <= target
        if hit_stop:
            return -1.0 - COST / risk, b[0]
        if hit_target:
            return TARGET_R - COST / risk, b[0]
    last = after[-1][4]
    move = (last - entry) if side_up else (entry - last)
    return move / risk - COST / risk, after[-1][0]


def day_trades(day_bars, levels, p0, ref, a_value):
    after = m1.window(day_bars, m1.FIRST15_END, m1.RTH_CLOSE)
    candidates = []
    for name, level in levels.items():
        above = level > p0
        touch = next((i for i, b in enumerate(after) if (b[2] >= level if above else b[3] <= level)), None)
        if touch is None or touch + STALL_BARS >= len(after):
            continue
        start = max(0, touch - IMPULSE_BARS + 1)
        window = after[start:touch + 1]
        approach = (level - min(b[3] for b in window)) if above else (max(b[2] for b in window) - level)
        if approach < a_value * ref:
            continue
        extreme = after[touch][2] if above else after[touch][3]
        stall = after[touch + 1:touch + 1 + STALL_BARS]
        if any((b[2] > extreme) if above else (b[3] < extreme) for b in stall):
            continue
        i_entry = touch + STALL_BARS
        minute = after[i_entry][0] + 5
        if not ENTRY_FROM <= minute <= ENTRY_UNTIL:
            continue
        entry = after[i_entry][4]
        side_up = not above                     # against the impulse
        stop = extreme + PAD_REF * ref if above else extreme - PAD_REF * ref
        risk = abs(entry - stop)
        if risk < MIN_STOP or (above and stop <= entry) or (not above and stop >= entry):
            continue
        target = entry + TARGET_R * risk if side_up else entry - TARGET_R * risk
        move = expected(side_up, minute, m1.RTH_CLOSE - minute, ref)
        if move is None or TARGET_R * risk > move:
            continue                            # the enough-time rule
        candidates.append((minute, name, i_entry, side_up, entry, stop, target))
    candidates.sort()
    taken, free_at = [], 0
    for minute, name, i_entry, side_up, entry, stop, target in candidates:
        if len(taken) >= MAX_PER_DAY or minute < free_at:
            continue
        r, exit_min = simulate(after, i_entry, side_up, entry, stop, target)
        taken.append((name, r))
        free_at = exit_min + 5 + WAIT_AFTER_MIN
    return taken


def summary(rs):
    if not rs:
        return {"n": 0}
    return {"n": len(rs), "avg_r": round(statistics.mean(rs), 3), "total_r": round(sum(rs), 1),
            "win_pct": round(100.0 * sum(1 for r in rs if r > 0) / len(rs), 1)}


def main():
    began = time.time()
    days = m2.load_bars_vol()
    order = sorted(d for d in days if m1.valid_day(d, days[d]))
    ranges = {d: m2.session_range(days[d]) for d in order}
    refs = {}
    for i, d in enumerate(order):
        prev = [ranges[x] for x in order[max(0, i - m2.REF_DAYS):i]]
        if len(prev) == m2.REF_DAYS:
            refs[d] = statistics.median(prev)
    out = {}
    for a_value in A_VALUES:
        rng = random.Random(20261017)
        res = defaultdict(lambda: defaultdict(list))
        for idx, day in enumerate(order):
            sp = m1.split_of(day)
            ref = refs.get(day)
            if sp is None or not ref or idx == 0:
                continue
            before = m1.window(days[day], m1.RTH_OPEN, m1.FIRST15_END)
            if not before:
                continue
            p0 = before[-1][4]
            real = m1.level_map(days, order, idx)
            fake = {"random_%d" % i: p0 + (1 if i % 2 == 0 else -1) * rng.uniform(0.05, 0.5) * ref
                    for i in range(RANDOM_PER_DAY)}
            for kind, levels in (("levels", real), ("random", fake)):
                for name, r in day_trades(days[day], levels, p0, ref, a_value):
                    res[sp][kind].append(r)
                    res[sp]["%s|%d" % (kind, day.year)].append(r)
        out["A=%.2f" % a_value] = {sp: {k: summary(v) for k, v in sorted(t.items())} for sp, t in res.items()}
    out["seconds"] = round(time.time() - began, 1)
    (HERE / "result_strategy.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print("done", out["seconds"])


if __name__ == "__main__":
    main()
