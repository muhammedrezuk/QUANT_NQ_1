"""2026-10-23 (owner seal NQ, sealed red lines laws 7-10): the owner's account limits pass the command gate to 509 --
SET with a settings mapping, or RELEASE_TOTAL; anything else is refused here (509 refuses a bad value itself)."""
import os
import sys
from pathlib import Path as _Path

sys.path.insert(0, str(_Path(__file__).resolve().parent))
import test_fix_2026_10_02 as F  # noqa: E402

tmp = F.tmp


async def test_account_limits_reach_509(tmp):
    db = os.path.join(tmp, "limits.db")
    F._insert(db, "account_limits", 990.0, {"command": "SET", "settings": {"initial_balance": 9031.78}})
    F._insert(db, "account_limits", 990.0, {"command": "RELEASE_TOTAL", "account_id": "52992818"})
    F._insert(db, "account_limits", 990.0, {"command": "SET", "settings": 5})
    F._insert(db, "account_limits", 990.0, {"command": "WIPE"})
    bus = await F._pulse(db, 1000.0)
    sent = bus.named(F._mod.EVENT_ACCOUNT_LIMITS)
    assert [p["command"] for p in sent] == ["SET", "RELEASE_TOTAL"], sent
    assert sent[0]["settings"] == {"initial_balance": 9031.78} and sent[0]["operator"] == "dashboard"
    assert F._statuses(db) == ["DONE", "DONE", "REJECTED", "REJECTED"]