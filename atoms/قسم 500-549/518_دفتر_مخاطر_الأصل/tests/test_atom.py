import asyncio,importlib.util,sys,tempfile
from pathlib import Path
root=Path(__file__).resolve().parents[4];folder=Path(__file__).resolve().parents[1];sys.path.insert(0,str(root));sys.path.insert(0,str(folder));spec=importlib.util.spec_from_file_location('_t518',folder/'atom.py');m=importlib.util.module_from_spec(spec);sys.modules['_t518']=m;spec.loader.exec_module(m)
class L:
 def __getattr__(self,n):return lambda *a,**k:None
class B:
 def __init__(self):self.e=[]
 def subscribe(self,*a):pass
 async def publish(self,n,p):self.e.append((n,p))
async def test_broker_scoped_ledger_and_reservations():
 # v4.2.0: was an un-prefixed main() -- invisible to `pytest`/the official
 # governance/scripts/test_atoms.py runner, collectible only by running
 # this file directly as a script. Renamed to a real test_* function so
 # it actually runs under CI; logic and assertions are untouched.
 b=B();a=m.Atom();td=tempfile.TemporaryDirectory();await a.initialize(m.AtomContext(518,{'default_risk_budget':0,'count_realized':True,'max_seen_trades':100,'consumer_db_path':td.name+'/c.db'},L(),b.publish,b.subscribe));await a.start();await a._on_account({'account_id':'A','broker':'BR'});await a._on_specs({'symbols':[{'account_id':'A','symbol':'NQ','tick_size':.25,'tick_value':5}]});await a._on_budget({'account_id':'A','broker':'BR','symbol':'NQ','risk_budget':50});await a._on_positions({'account_id':'A','broker':'BR','source':'609','timestamp':2,'complete':True,'positions':[{'account_id':'A','broker':'BR','symbol':'NQ','ticket':1,'side':'BUY','volume':1,'entry_price':100,'current_price':101}]});row=[p for n,p in b.e if n==m.EVENT_OUT][-1]['ledgers'][0];assert row['floating_economic']==20 and row['broker']=='BR';await a._on_trade({'event_id':'t','account_id':'A','broker':'BR','symbol':'NQ','pnl':10,'gross_pnl':12,'completeness':'COMPLETE'});assert [p for n,p in b.e if n==m.EVENT_OUT][-1]['ledgers'][0]['K']==10;await a._on_order({'account_id':'A','broker':'BR','symbol':'NQ','request_id':'r','action':'OPEN','risk_budget':20});row=[p for n,p in b.e if n==m.EVENT_OUT][-1]['ledgers'][0];assert row['reserved_risk']==20 and row['remaining_risk']<=30;snap=await a.snapshot();c=m.Atom();await c.restore(snap);assert c._reservations;print('518 broker-scoped ledger and reservation tests passed')
async def test_spec_fallback_across_accounts_same_broker():
    """استعادة سلوك احتياطي انقطع بصمت أثناء إعادة هيكلة متعددة الوسطاء (مقيس 2026-08-19
    بمقارنة لقطة 2026-08-15): مواصفة رمز معروفة لحساب آخر بنفس الوسيط ونفس الرمز تُستخدم
    كتقريب آمن ريثما تصل مواصفة هذا الحساب بالذات -- محافظ عمداً: لا يتخطى حدود الوسيط
    نفسه أبداً (لا يُخلط بين وسيطين مختلفين)."""
    b = B(); a = m.Atom(); td = tempfile.TemporaryDirectory()
    await a.initialize(m.AtomContext(518, {'default_risk_budget': 0, 'count_realized': True,
                                            'max_seen_trades': 100, 'consumer_db_path': td.name + '/c2.db'},
                                      L(), b.publish, b.subscribe))
    await a.start()
    await a._on_account({'account_id': 'A', 'broker': 'BR'})
    await a._on_specs({'symbols': [{'account_id': 'A', 'symbol': 'NQ', 'tick_size': .25, 'tick_value': 5}]})
    await a._on_account({'account_id': 'C', 'broker': 'BR'})
    await a._on_budget({'account_id': 'C', 'broker': 'BR', 'symbol': 'NQ', 'risk_budget': 50})
    await a._on_positions({'account_id': 'C', 'broker': 'BR', 'source': '609', 'timestamp': 2, 'complete': True,
                           'positions': [{'account_id': 'C', 'broker': 'BR', 'symbol': 'NQ', 'ticket': 9,
                                         'side': 'BUY', 'volume': 1, 'entry_price': 100, 'current_price': 101}]})
    ledgers = [p for n, p in b.e if n == m.EVENT_OUT][-1]['ledgers']
    c_row = [r for r in ledgers if r['account_id'] == 'C'][0]
    assert c_row['floating_economic'] == 20, (
        "يجب أن يستعمل مواصفة حساب A كتقريب (tick_size=0.25, tick_value=5) بدل الرجوع "
        "لربح الوسيط الخام أو صفر -- floating_economic الفعلي: %r" % (c_row['floating_economic'],))
    assert 'MISSING_SYMBOL_SPECS' not in c_row['warnings'], c_row['warnings']
    print('OK — 518 spec fallback across accounts, same broker only')


async def test_realized_loss_reaches_the_guard():
    """حكم المالك ٢٠٢٦-٠٨-١٣ (م١٣): الخسارة المحقّقة تسافر في مسارها إلى `u`.

    `make_state` نفّذه، ثمّ كان `_ledger_payload` يدهس `u` بنسبة الطافي وحده
    فتختفي الخسارة من الحارس.  مقيس حيًّا ٢٠٢٦-٠٩-٠٩ على BTCUSD:
    `u_realized=5.2985` و`u=0.0` و`breached=False` و`remaining_risk=100.0`
    فوق خسارة ٥٢٩٫٨٥$ مقابل ميزانية ١٠٠$.  الأرقام هنا هي أرقام تلك اللحظة.
    """
    b = B(); a = m.Atom(); td = tempfile.TemporaryDirectory()
    await a.initialize(m.AtomContext(518, {'default_risk_budget': 0, 'count_realized': True,
                                           'max_seen_trades': 100, 'consumer_db_path': td.name + '/c3.db'},
                                     L(), b.publish, b.subscribe))
    await a.start()
    await a._on_account({'account_id': 'A', 'broker': 'BR'})
    await a._on_specs({'symbols': [{'account_id': 'A', 'symbol': 'BTCUSD', 'tick_size': .01, 'tick_value': .01}]})
    await a._on_budget({'account_id': 'A', 'broker': 'BR', 'symbol': 'BTCUSD', 'risk_budget': 100})
    await a._on_trade({'event_id': 'loss-1', 'account_id': 'A', 'broker': 'BR', 'symbol': 'BTCUSD',
                       'pnl': -529.85, 'gross_pnl': -529.85, 'completeness': 'COMPLETE'})
    row = [p for n, p in b.e if n == m.EVENT_OUT][-1]['ledgers'][0]
    assert row['realized_net'] == -529.85, row['realized_net']
    assert round(row['u_realized'], 4) == 5.2985, row['u_realized']
    assert row['u'] is not None and round(row['u'], 4) == 5.2985, (
        "الخسارة المحقّقة لم تبلغ u — الدهس عاد: u=%r u_realized=%r" % (row['u'], row['u_realized']))
    assert row['breached'] is True, "ميزانية متجاوَزة ٥ أضعاف تُقرأ سليمة"
    assert row['warning'] is True, row['warning']
    assert row['remaining_risk'] == 0.0, (
        "«متبقٍّ» فوق ميزانية مخترقة: %r" % (row['remaining_risk'],))
    print('OK — الخسارة المحقّقة تبلغ الحارس: u=%.4f breached=%s remaining=%s'
          % (row['u'], row['breached'], row['remaining_risk']))


async def test_floating_exposure_still_drives_u_when_it_is_worse():
    """الطافي لم يُمَسّ: حين يكون أسوأ من المحقَّق فهو الذي يقود `u`."""
    b = B(); a = m.Atom(); td = tempfile.TemporaryDirectory()
    await a.initialize(m.AtomContext(518, {'default_risk_budget': 0, 'count_realized': True,
                                           'max_seen_trades': 100, 'consumer_db_path': td.name + '/c4.db'},
                                     L(), b.publish, b.subscribe))
    await a.start()
    await a._on_account({'account_id': 'A', 'broker': 'BR'})
    await a._on_specs({'symbols': [{'account_id': 'A', 'symbol': 'NQ', 'tick_size': .25, 'tick_value': 5}]})
    await a._on_budget({'account_id': 'A', 'broker': 'BR', 'symbol': 'NQ', 'risk_budget': 100})
    # مركز خاسر طافيًا: (99-100) * 1 * (5/0.25) = -20
    await a._on_positions({'account_id': 'A', 'broker': 'BR', 'source': '609', 'timestamp': 2, 'complete': True,
                           'positions': [{'account_id': 'A', 'broker': 'BR', 'symbol': 'NQ', 'ticket': 1,
                                          'side': 'BUY', 'volume': 1, 'entry_price': 100, 'current_price': 99}]})
    row = [p for n, p in b.e if n == m.EVENT_OUT][-1]['ledgers'][0]
    assert row['loss_exposure'] == 20.0, row['loss_exposure']
    assert round(row['u'], 4) == 0.2, row['u']
    assert row['breached'] is False and row['warning'] is False
    assert row['remaining_risk'] == 80.0, row['remaining_risk']
    print('OK — الطافي يقود u حين يكون الأسوأ: u=%.2f remaining=%s' % (row['u'], row['remaining_risk']))

async def test_owner_reset_starts_a_fresh_ledger():
    """أمر المالك ٢٠٢٦-٠٩-١٠: «صفّر الخسارة ورجّعه للعمل».

    الخسارة المحقّقة تراكمية ولا يزيلها شيء، فتبقى `u` فوق الواحد ويبقى
    الأصل مجمّدًا عبر ٥١٩ مهما رُفعت الميزانية دون مبلغها — مقيس: BTCUSD
    ٦١١٫٩٣$ مقابل ٥٠٠$ ⇒ u=1.22 ⇒ FROZEN.
    """
    b = B(); a = m.Atom(); td = tempfile.TemporaryDirectory()
    await a.initialize(m.AtomContext(518, {'default_risk_budget': 0, 'count_realized': True,
                                           'max_seen_trades': 100, 'consumer_db_path': td.name + '/c5.db'},
                                     L(), b.publish, b.subscribe))
    await a.start()
    await a._on_account({'account_id': 'A', 'broker': 'BR'})
    await a._on_specs({'symbols': [{'account_id': 'A', 'symbol': 'BTCUSD', 'tick_size': .01, 'tick_value': .01}]})
    await a._on_budget({'account_id': 'A', 'broker': 'BR', 'symbol': 'BTCUSD', 'risk_budget': 500})
    await a._on_trade({'event_id': 'loss-2', 'account_id': 'A', 'broker': 'BR', 'symbol': 'BTCUSD',
                       'pnl': -611.93, 'gross_pnl': -611.93, 'completeness': 'COMPLETE'})
    row = [p for n, p in b.e if n == m.EVENT_OUT][-1]['ledgers'][0]
    assert round(row['u'], 2) == 1.22 and row['breached'] is True, row['u']

    await a._on_ledger_reset({'account_id': 'A', 'broker': 'BR', 'symbol': 'BTCUSD', 'reason': 'OWNER_RESET'})
    row = [p for n, p in b.e if n == m.EVENT_OUT][-1]['ledgers'][0]
    assert row['realized_net'] == 0.0, row['realized_net']
    assert row['u'] == 0.0 and row['breached'] is False and row['warning'] is False, row
    assert row['remaining_risk'] == 500.0, row['remaining_risk']
    assert a._ledger_resets == 1
    print('OK — الدفتر صُفّر بأمر صريح: u=%s breached=%s' % (row['u'], row['breached']))


async def test_reset_needs_an_explicit_scope():
    """لا تصفير شامل بالخطأ: الحساب والرمز شرطان."""
    b = B(); a = m.Atom(); td = tempfile.TemporaryDirectory()
    await a.initialize(m.AtomContext(518, {'default_risk_budget': 0, 'count_realized': True,
                                           'max_seen_trades': 100, 'consumer_db_path': td.name + '/c6.db'},
                                     L(), b.publish, b.subscribe))
    await a.start()
    await a._on_account({'account_id': 'A', 'broker': 'BR'})
    await a._on_specs({'symbols': [{'account_id': 'A', 'symbol': 'BTCUSD', 'tick_size': .01, 'tick_value': .01}]})
    await a._on_budget({'account_id': 'A', 'broker': 'BR', 'symbol': 'BTCUSD', 'risk_budget': 500})
    await a._on_trade({'event_id': 'loss-3', 'account_id': 'A', 'broker': 'BR', 'symbol': 'BTCUSD',
                       'pnl': -611.93, 'gross_pnl': -611.93, 'completeness': 'COMPLETE'})
    await a._on_ledger_reset({'account_id': 'A', 'broker': 'BR'})      # بلا رمز
    await a._on_ledger_reset({'symbol': 'BTCUSD'})                      # بلا حساب
    row = [p for n, p in b.e if n == m.EVENT_OUT][-1]['ledgers'][0]
    assert row['realized_net'] == -611.93, "صُفّر بلا نطاق صريح"
    assert a._ledger_resets == 0
    print('OK — التصفير يرفض النطاق الناقص')

if __name__=='__main__':asyncio.run(test_broker_scoped_ledger_and_reservations());asyncio.run(test_spec_fallback_across_accounts_same_broker());asyncio.run(test_realized_loss_reaches_the_guard());asyncio.run(test_floating_exposure_still_drives_u_when_it_is_worse());asyncio.run(test_owner_reset_starts_a_fresh_ledger());asyncio.run(test_reset_needs_an_explicit_scope())
