"""2026-10-26 (owner's law, seal "NQ"): the one rule that tells the owner's manual trade from the system's -- a known magic
that is not the system's. A row without a known magic is the system's, as 565, 509 and 577 read it before."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from shared import owner_trades as ot  # noqa: E402


def test_the_owners_manual_trade_is_a_known_other_magic():
    assert ot.is_owner({"magic": 0}) and ot.is_owner({"magic": "0"}) and ot.is_owner({"magic": 7.0})
    assert ot.is_owner(0) and not ot.is_system({"magic": 0})


def test_the_systems_magic_and_a_missing_one_are_the_systems():
    for row in ({"magic": 20260801}, {"magic": "20260801"}, {"magic": 20260801.0}, {}, {"magic": None},
                {"magic": ""}, {"magic": "  "}, {"magic": "abc"}, {"magic": True}, {"magic": float("nan")}):
        assert ot.is_system(row) and not ot.is_owner(row), row


def test_another_system_magic_from_an_atoms_config():
    assert ot.is_owner({"magic": 20260801}, system_magic=7) and ot.is_system({"magic": 7}, system_magic="7")


def test_system_rows_keep_order_and_what_is_not_a_row():
    rows = [{"ticket": 1, "magic": 20260801}, {"ticket": 2, "magic": 0}, "x", {"ticket": 3}]
    assert ot.system_rows(rows) == [{"ticket": 1, "magic": 20260801}, "x", {"ticket": 3}]
