from __future__ import annotations
import importlib.util
import inspect
import sys
from pathlib import Path
import pytest
from core.contracts.atom import AtomContext

ROOT=Path(__file__).resolve().parents[1]
from build_registry.paths import RegistryAtomRoot
ATOM_ROOT = RegistryAtomRoot(ROOT)

def load(atom_id):
    folder=next((ATOM_ROOT).glob(f"{atom_id}_*"),None)
    if folder is None:
        # ٢٠٢٦-٠٩-١٨ — كان `next(...)` بلا بديل، فيرمي `StopIteration`
        # **وقت الاستيراد** متى أُرشفت ذرّة. وثمنه ليس هذا الملفّ وحده:
        # pytest يوقف الجمع كلّه (`Interrupted`)، فكانت 1,886 اختبارًا
        # تُجمع ولا يُشغَّل منها واحد. رسالةٌ تسمّي الذرّة والملفّ أرخص
        # من نصف يومٍ في تعقّب `StopIteration` عارية.
        raise RuntimeError(
            f"الذرّة {atom_id} غير موجودة تحت {ATOM_ROOT} — أُرشفت؟ "
            f"حدِّث tests/test_market_decision_path.py")
    name=f"paper5_{atom_id}";spec=importlib.util.spec_from_file_location(name,folder/"atom.py");mod=importlib.util.module_from_spec(spec);sys.modules[name]=mod;sys.path.insert(0,str(folder));spec.loader.exec_module(mod);return mod
# ٢٠٢٦-٠٩-١٨ — كانت 454 و578 و579 تُحمَّل هنا ولا يستعملها سطرٌ واحد في
# الملفّ. ثمّ أُرشفت 578 بختم المالك (`25b0cbb`)، فقتل تحميلٌ ميت الجمع
# كلّه. ما لا يُستعمل لا يُحمَّل — والباقي كلّه مستعمَل ومعدود.
M102=load(102);M103=load(103);M105=load(105);M109=load(109);M112=load(112);M115=load(115);M116=load(116);M513=load(513)
class Log:
    def __getattr__(self,n):return lambda *a,**k:None
class Bus:
    def __init__(self):self.events=[];self.handlers={}
    def subscribe(self,n,h):self.handlers.setdefault(n,[]).append(h)
    async def publish(self,n,p):
        self.events.append((n,p))
        for h in list(self.handlers.get(n,[])):
            value=h(p)
            if inspect.isawaitable(value):await value
    def rows(self,n):return [p for name,p in self.events if name==n]
async def start(mod,atom_id,cfg,bus=None):
    bus=bus or Bus();atom=mod.Atom();await atom.initialize(AtomContext(atom_id,cfg,Log(),bus.publish,bus.subscribe));await atom.start();return atom,bus
def tick(**updates):
    value={"account_id":"A","symbol":"NQ","provider":"MT5","bid":100.0,"ask":101.0,"price":100.5,"volume":2.0,"timestamp":10.0,"exchange_timestamp":10.0,"received_at":10.1}
    value.update(updates);return value
async def gate_chain():
    bus=Bus();atoms=[]
    # (nq seal 2026-08-25: 103 v5.3.0 — config key is "timeframes", not "period_s")
    for mod,i,cfg in ((M112,112,{}),(M102,102,{}),(M103,103,{"timeframes":["60s"]}),(M105,105,{}),(M115,115,{"gap_threshold_s":5,"spike_pct":5,"spread_pct":1})):
        atom,_=await start(mod,i,cfg,bus);atoms.append(atom)
    await bus.publish("portfolio.equity.state",{"account_id":"A","broker":"Broker-X","equity":10000});await bus.publish("platform.account.state",{"account_id":"A","broker":"Broker-X"})
    return atoms,bus
@pytest.mark.asyncio
@pytest.mark.parametrize("bad",[{"bid":float("nan")},{"ask":float("inf")},{"ask":99},{"bid":-1},{"timestamp":None},{"account_id":None}])
async def test_invalid_ticks_are_rejected(bad):
    _,bus=await gate_chain();await bus.publish("market.tick",tick(**bad));assert bus.rows(M112.EVENT_INVALID);assert not bus.rows(M112.EVENT_VALID)
@pytest.mark.asyncio
async def test_valid_contract_is_flat_and_identical():
    _,bus=await gate_chain();raw=tick();await bus.publish("market.tick",raw);valid=bus.rows(M112.EVENT_VALID)[-1]
    for field in M112.CONTRACT_FIELDS:assert valid.get(field)==raw.get(field)
    assert valid["broker"]=="Broker-X" and "payload" not in valid and "data" not in valid
@pytest.mark.asyncio
async def test_full_tick_to_candle_path():
    # (nq seal 2026-08-25: 103 v5.3.0 frame factory — _period_start() removed;
    # the same 60s boundary intent is asserted from the closed candle and the
    # open frame state: a tick at t=70 belongs to the period starting at 60.)
    atoms,bus=await gate_chain();await bus.publish("market.tick",tick(timestamp=10,exchange_timestamp=10));await bus.publish("market.tick",tick(timestamp=70,exchange_timestamp=70,bid=102,ask=103,price=102.5));c=bus.rows(M103.EVENT_OUT)[-1];assert c["account_id"]=="A" and c["broker"]=="Broker-X" and c["symbol"]=="NQ";assert c["timeframe"]=="60s" and c["period_start"]==0.0;assert atoms[2]._candles[("A","Broker-X","NQ",60.0)]["period_start"]==60.0
@pytest.mark.asyncio
async def test_receivers_only_use_validated_channel():
    atoms,bus=await gate_chain();await bus.publish("market.tick.validated",tick(broker="Broker-X"));assert atoms[0].checked_count==0;assert bus.rows(M102.EVENT_OUT) and bus.rows(M105.EVENT_OUT)
@pytest.mark.asyncio
async def test_quality_monitor_stays_on_raw_and_sees_corruption():
    _,bus=await gate_chain();await bus.publish("market.tick",tick(ask=99));states=bus.rows(M115.EVENT_STATE);assert states[-1]["status"]=="INVALID";assert not bus.rows(M112.EVENT_VALID)
@pytest.mark.asyncio
async def test_validator_stop_is_announced():
    atom,bus=await start(M112,112,{});await atom.stop();assert bus.rows(M112.EVENT_STATE)[-1]["status"]=="STOPPED"
@pytest.mark.asyncio
async def test_calendar_restart_keeps_future_and_drops_expired():
    # 109 v3.2.0 (ختم NQ ٢٠٢٦-٠٩-١٠): `keep_past_seconds` صار يُحترم.
    # هذا الاختبار كان يمرّر 3600 ثمّ يتوقّع الحذف عند 1001 — أي يوثّق
    # تجاهل الإعداد لا العقد. الآن: يبقى داخل النافذة ويُحذف بعدها.
    cfg={"source_event":"market.calendar","alert_before_seconds":900,"keep_past_seconds":3600,"min_impact":"LOW"}
    atom,bus=await start(M109,109,cfg);await bus.publish("market.calendar",{"id":"cpi","title":"CPI","scheduled_at":1000,"impact_level":"HIGH"});snap=await atom.snapshot();after,bus2=await start(M109,109,cfg);await after.restore(snap)
    await bus2.publish("SYS_SECOND",{"official_time":500});assert "cpi" in after._events,"حدث مستقبليّ يبقى"
    await bus2.publish("SYS_SECOND",{"official_time":1001});assert "cpi" in after._events,"مرّ للتوّ — يبقى ضمن keep_past_seconds"
    await bus2.publish("SYS_SECOND",{"official_time":1000+3601});assert "cpi" not in after._events,"بعد النافذة يُحذف"
@pytest.mark.asyncio
async def test_calendar_restore_failure_is_unknown():
    atom,_=await start(M109,109,{"source_event":"market.calendar","alert_before_seconds":900,"keep_past_seconds":3600,"min_impact":"LOW"})
    with pytest.raises(ValueError):
        await atom.restore({"events":"bad"})
    assert atom._valid_received==0
@pytest.mark.asyncio
async def test_feed_states_never_seen_dead_recovered():
    # 116 v4.0.0 (ختم NQ ٢٠٢٦-٠٩-١٠): الحالة تُبنى على المصدر المعتمد للتحليل
    # وحده. نبضة ميتاتريدر لم تعد توقظ الحارس — وهذا هو المقصود.
    src=M116._ANALYST_SOURCE
    atom,bus=await start(M116,116,{"max_silence_seconds":10,"dead_after_seconds":20});await bus.publish("SYS_SECOND",{"official_time":100});assert atom._state=="NEVER_SEEN";await bus.publish(src,{"account_id":"A"});await bus.publish("SYS_SECOND",{"official_time":121});assert atom._state=="DEAD";await bus.publish(src,{"account_id":"A"});assert bus.rows(M116.EVENT_RECOVERED)
@pytest.mark.asyncio
async def test_secondary_feed_never_wakes_the_guard():
    """ميتاتريدر وحده لا يجعل 116 يرى — تغذية المحلّلين سي‑تريدر حصرًا."""
    atom,bus=await start(M116,116,{"max_silence_seconds":10,"dead_after_seconds":20})
    await bus.publish("SYS_SECOND",{"official_time":100})
    for t in (105,110,115,121):
        await bus.publish("feed.mt5.tick",{"account_id":"A"});await bus.publish("SYS_SECOND",{"official_time":t})
    assert atom._state=="NEVER_SEEN",atom._state
@pytest.mark.asyncio
async def test_position_specs_are_account_broker_scoped():
    cfg={"risk_per_trade_pct":1,"default_stop_pct":1,"min_lot":.01,"max_lot":10,"lot_step":.01};a,b=await start(M513,513,cfg)
    for account,broker,value in (("A","B1",20),("B","B2",2)):
        await b.publish("portfolio.equity.state",{"account_id":account,"broker":broker,"equity":10000});await b.publish(M513.EVENT_ACCOUNT,{"account_id":account,"broker":broker});await b.publish(M513.EVENT_SPECS,{"symbols":[{"account_id":account,"symbol":"NQ","tick_value":value,"tick_size":.25}]});await b.publish(M513.EVENT_IN,{"account_id":account,"broker":broker,"symbol":"NQ","timeframe":"tick","sequence":"0","timestamp":1.0,"price":100})
    rows=b.rows(M513.EVENT_OUT);assert len(rows)==2 and rows[0]["metadata"]["lot"]!=rows[1]["metadata"]["lot"]
@pytest.mark.asyncio
async def test_missing_specs_is_explicit_rejection():
    cfg={"risk_per_trade_pct":1,"default_stop_pct":1,"min_lot":.01,"max_lot":10,"lot_step":.01};_,b=await start(M513,513,cfg);await b.publish("portfolio.equity.state",{"account_id":"A","broker":"B","equity":100});await b.publish(M513.EVENT_ACCOUNT,{"account_id":"A","broker":"B"});await b.publish(M513.EVENT_IN,{"account_id":"A","broker":"B","symbol":"NQ","timeframe":"tick","sequence":"0","timestamp":1.0,"price":100});assert b.rows(M513.EVENT_REJECTED)[-1]["reason"]=="SIZING_UNAVAILABLE_FOR_SYMBOL"
@pytest.mark.asyncio
async def test_below_min_volume_rejected_not_raised():
    cfg={"risk_per_trade_pct":.01,"default_stop_pct":50,"min_lot":.01,"max_lot":10,"lot_step":.01};_,b=await start(M513,513,cfg);await b.publish("portfolio.equity.state",{"account_id":"A","broker":"B","equity":100});await b.publish(M513.EVENT_ACCOUNT,{"account_id":"A","broker":"B"});await b.publish(M513.EVENT_SPECS,{"symbols":[{"account_id":"A","symbol":"NQ","tick_value":10,"tick_size":.01}]});await b.publish(M513.EVENT_IN,{"account_id":"A","broker":"B","symbol":"NQ","timeframe":"tick","sequence":"0","timestamp":1.0,"price":100});assert b.rows(M513.EVENT_REJECTED)[-1]["reason"]=="VOLUME_BELOW_BROKER_MIN"
def test_data_section_is_not_on_the_decision_route():
    """قسم البيانات لا يصدر قرارًا ولا يستهلكه — بأيّ ذرّة كانت.

    ٢٠٢٦-٠٩-١٦: كان هذا الاختبار يفتح مجلّدَي 113 و114 بالاسم، فسقط
    بـStopIteration يوم أزالهما المالك بيده. والعِلّة أنّه كان يحرس
    **ذرّتين** بينما المعنى المقصود يخصّ **القسم**: طريق القرار يُقاس
    بالأحداث القرارية لا بأسماء الملفّات.

    فصار يمسح القسم كلّه: لا تُكسره إزالة ذرّة ولا إضافتها، ويتّسع
    تلقائيًّا لأيّ ذرّة جديدة تدخل 100-149.
    """
    decision_events = ("decision.aggregated.state", "decision.scored.state",
                       "decision.eligibility.buy.state",
                       "decision.eligibility.sell.state", "trading.final_decision")
    # ATOM_ROOT جذر الذرّات كلّها لا القسم — يُحصر هنا صراحةً في 100-149،
    # وإلّا مسح المنصّة بأسرها وسقط على ذرّات أقسام أخرى لها حقّ أن تقرأ
    # أحداث القرار (360 مثلًا).
    section = ROOT / "atoms" / "قسم 100-149"
    manifests = sorted(section.glob("*/manifest.yaml"))
    assert manifests, "لم يُعثر على ذرّات القسم 100-149"
    for manifest in manifests:
        text = manifest.read_text(encoding="utf-8")
        for decision_event in decision_events:
            assert decision_event not in text, (manifest.parent.name, decision_event)


def test_removed_side_path_chain_stays_removed():
    """113 و114 أُزيلتا بيد المالك ٢٠٢٦-٠٩-١٦ — والحدثان بلا ناشر.

    كانت السلسلة `113 ← 114` تنتهي إلى `market_data.normalized` الذي
    لا يشترك فيه أحد في المشروع كلّه (مقيس من خمسة مصادر: مسح الكود ·
    عدّاد `no_subscribers` في الناقل · توثيق الأحداث الرسميّ · فاحص
    `check_orphan_events` · ورقة فحص القسم). وثمنها مقيس على النقل:
    `market_data.cleaned` كان أعلى حدث مُسقَط في المنصّة (338,118)،
    و114 أعلى ذرّة مُسقِطة (79,986).

    هذا الحارس يمنع عودتهما صامتةً: لو أُعيدتا فليكن ذلك بقرار معلن
    يُسقط هذا الاختبار عمدًا، لا بنسخٍ عائد من فرع قديم.
    """
    section = ROOT / "atoms" / "قسم 100-149"
    for atom_id in (113, 114):
        assert not list(section.glob(f"{atom_id}_*")), f"الذرّة {atom_id} عادت"
    # والحدثان بلا ناشر ولا مشترك في المنصّة كلّها — لا في القسم وحده
    for event in ("market_data.cleaned", "market_data.normalized"):
        for manifest in (ROOT / "atoms").glob("*/*/manifest.yaml"):
            text = manifest.read_text(encoding="utf-8")
            assert event not in text, (manifest.parent.name, event)
