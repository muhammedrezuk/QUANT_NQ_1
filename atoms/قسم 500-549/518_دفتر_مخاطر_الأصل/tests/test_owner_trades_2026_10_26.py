"""2026-10-26 (owner's law, seal "NQ"): the owner's manual position never enters the asset's ledger -- no floating, no loss
exposure, no use of the system's budget on the symbol."""
import importlib.util
import sys
import tempfile
from pathlib import Path

_spec = importlib.util.spec_from_file_location("_t518_owner", Path(__file__).resolve().parent / "test_atom.py")
T = importlib.util.module_from_spec(_spec)
sys.modules["_t518_owner"] = T
_spec.loader.exec_module(T)
m = T.m


async def _ledger(positions):
    b = T.B(); a = m.Atom(); td = tempfile.TemporaryDirectory()
    await a.initialize(m.AtomContext(518, {'default_risk_budget': 0, 'count_realized': True, 'max_seen_trades': 100,
                                           'consumer_db_path': td.name + '/o.db'}, T.L(), b.publish, b.subscribe))
    await a.start()
    await a._on_account({'account_id': 'A', 'broker': 'BR'})
    await a._on_specs({'symbols': [{'account_id': 'A', 'symbol': 'NQ', 'tick_size': .25, 'tick_value': 5}]})
    await a._on_budget({'account_id': 'A', 'broker': 'BR', 'symbol': 'NQ', 'risk_budget': 50})
    await a._on_positions({'account_id': 'A', 'broker': 'BR', 'source': '609', 'timestamp': 2, 'complete': True,
                           'positions': positions})
    rows = [p for n, p in b.e if n == m.EVENT_OUT][-1]['ledgers']
    return a, [r for r in rows if r['symbol'] == 'NQ']


def _pos(ticket, magic, current=101):
    return {'account_id': 'A', 'broker': 'BR', 'symbol': 'NQ', 'ticket': ticket, 'side': 'BUY', 'volume': 1,
            'entry_price': 100, 'current_price': current, 'magic': magic}


async def test_the_owners_position_is_not_in_the_ledger():
    a, rows = await _ledger([_pos(9, 0, current=90)])                  # the owner's, 40$ down on a 50$ budget
    assert not a._positions
    assert all((r.get('floating_economic') or 0) == 0 and not r.get('breached') for r in rows), rows


async def test_the_systems_position_beside_it_is_counted():
    a, rows = await _ledger([_pos(9, 0, current=90), _pos(1, 20260801)])
    assert len(a._positions) == 1 and rows and rows[0]['floating_economic'] == 20, rows
