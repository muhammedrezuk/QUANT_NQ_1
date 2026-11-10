"""2026-10-17: the red lines read the clock (03:00-22:00 on the owner's clock), so every other test here would pass or fail by the
hour it runs at. The window is held open for them; `test_red_lines_2026_10_17.py` drives the real window with explicit moments."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from shared import account_limits, red_lines  # noqa: E402
import entry_request_lines  # noqa: E402

REAL_SESSION_STATE = red_lines.session_state
#: 2026-10-25 (law 21): the last hour of the window reads the clock too; held clear here, driven for real in
#: `test_red_lines_2026_10_17.py` and `test_red_lines_2026_10_25.py` with explicit moments.
REAL_IN_LAST_HOUR = red_lines.in_last_hour
#: 2026-10-23: read at import, before the fixture below holds the account limits clear; the limits are driven for real in
#: `test_account_limits_2026_10_23.py` with this.
REAL_LIMITS_BLOCK = account_limits.entry_block
#: 2026-10-26 (owner seal "nq"): an unknown calendar and a stalled official pulse refuse entries; held known and fresh
#: here, driven for real in `test_guards_2026_10_26.py` with these.
REAL_NEWS_UNKNOWN = red_lines.news_unknown
REAL_PULSE_AGE = entry_request_lines.pulse_age_s


@pytest.fixture(autouse=True)
def _window_open(monkeypatch):
    monkeypatch.setattr(red_lines, "session_state", lambda epoch_s, symbol=None: (True, None))   # open, not in its first 15 min
    monkeypatch.setattr(red_lines, "in_last_hour", lambda epoch_s, symbol=None: False)            # and not in its last hour
    monkeypatch.setattr(red_lines, "news_unknown", lambda *a, **k: False)                         # and the calendar known
    monkeypatch.setattr(entry_request_lines, "pulse_age_s", lambda atom: 0.0)                    # and the pulse fresh
    # 2026-10-23 (laws 7-10): every other test here runs with 509's limits clear, as the window is held open above.
    monkeypatch.setattr(account_limits, "entry_block", lambda *a, **k: ("", {}))
