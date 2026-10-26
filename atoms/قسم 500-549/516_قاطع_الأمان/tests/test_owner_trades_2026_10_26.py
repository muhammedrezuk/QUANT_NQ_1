# -*- coding: utf-8 -*-
"""٢٠٢٦-١٠-٢٦ (قانون صفقات المالك، ختم «NQ»): عدد المراكز المفتوحة في القاطع للمنظومة وحدها — مركز المالك اليدويّ لا يُعدّ،
والحساب يبقى معروفًا بصفرٍ إن لم يبقَ فيه إلّا مراكز المالك."""
import importlib.util as _ilu
import sys
import tempfile
from pathlib import Path as _Path

_spec = _ilu.spec_from_file_location("_t516_fix_owner", _Path(__file__).resolve().parent / "test_fix_2026_10_02.py")
F = _ilu.module_from_spec(_spec)
sys.modules["_t516_fix_owner"] = F
_spec.loader.exec_module(F)


def _row(ticket, magic):
    return {"account_id": "A1", "ticket": ticket, "symbol": "USTEC", "side": "BUY", "volume": 1.0, "magic": magic}


async def test_the_owners_positions_are_not_counted_open():
    atom, _ = await F._new(_Path(tempfile.mkdtemp()) / "c.db")
    await atom._on_positions({"account_id": "A1", "positions": [_row(1, 20260801), _row(2, 0), _row(3, 0)]})
    assert atom.book("A1")["open_trade_count"] == 1
    await atom._on_positions({"account_id": "A1", "positions": [_row(2, 0), _row(3, 0)]})
    assert atom.book("A1")["open_trade_count"] == 0, "the system's last close left a stale count"
    await atom._on_positions({"account_id": "A1", "positions": [dict(_row(4, None))]})   # a row without a magic is ours
    assert atom.book("A1")["open_trade_count"] == 1


async def test_the_daily_loss_share_is_of_the_owners_initial_balance():
    """جواب المالك «NQ»: «تراجع يومي 5 % انا بسجل 4 الكم و1 الي» — المقام الرصيد الابتدائيّ، لا حقوقٌ يحرّكها المالك."""
    atom, _ = await F._new(_Path(tempfile.mkdtemp()) / "c.db")
    # Before 509's state: 517's share stays as it was.
    assert atom._loss_pct({"pnl": -90.0, "loss_pct": 0.9}) == 0.9
    await atom._on_limits({"settings": {"initial_balance": 9000.0}})
    # The owner's +700 had lifted the equity to 9,740 (517 says 0.924%): the share is 90 of 9,000.
    assert atom._loss_pct({"pnl": -90.0, "loss_pct": 0.924}) == 1.0
    assert atom._loss_pct({"pnl": None, "loss_pct": None}) is None
    await atom._on_limits({"settings": {"initial_balance": 0}})          # a bad figure is not taken
    assert atom._initial_balance == 9000.0
