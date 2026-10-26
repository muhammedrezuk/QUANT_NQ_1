import asyncio
import importlib.util
import sys
from pathlib import Path
root=Path(__file__).resolve().parents[4]; folder=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root)); spec=importlib.util.spec_from_file_location("_atom521_work",folder/"atom.py")
mod=importlib.util.module_from_spec(spec); sys.modules["_atom521_work"]=mod; spec.loader.exec_module(mod)

# ٢٠٢٦-٠٩-٠١: الذرّة صارت تقرأ «الآن» من السلطة الزمنيّة لا من حمولة النبضة.
# تُحقن هنا ساعةٌ مضبوطة في مساحة أسماء هذه الذرّة وحدها، فتبقى الطوابع
# صغيرة مقروءة (11 · 12 …) ولا تُمَسّ الساعة العامّة.
class _Clock:
    value = 12.0
    def now(self): return self.value
    def mono(self): return self.value
    def quality(self): return "SYNCED"
    def state(self): return {"quality": "SYNCED"}
CLOCK = _Clock(); mod.clock = CLOCK
class Log:
    def debug(self,*a,**k): pass
    def info(self,*a,**k): pass
    def warning(self,*a,**k): pass
    def error(self,*a,**k): pass
    def critical(self,*a,**k): pass
class Bus:
    def __init__(self): self.events=[]
    def subscribe(self,*a): pass
    async def publish(self,n,p): self.events.append((n,p))
    def ctx(self): return mod.AtomContext(521,{"symbols":[],"max_data_age_s":5,"fallback_max_age_s":30,"max_sane_spread":2,"max_tick_jump":10,"min_dwell_s":0},Log(),self.publish,self.subscribe)
async def main():
    b=Bus(); a=mod.Atom(); await a.initialize(b.ctx()); await a.start()
    await a._on_primary({"symbol":"NQ","bid":99.5,"ask":100.5,"price":100,"exchange_timestamp":10}); await a._on_pulse({"official_time":10})
    assert a.state("NQ")["state"]=="HEALTHY"
    await a._on_primary({"symbol":"NQ","bid":149.5,"ask":150.5,"price":150,"exchange_timestamp":11})
    assert a.state("NQ")["primary"]["reason"]=="TICK_JUMP"
    print("521 P1 tests passed")
# ٢٠٢٦-٠٩-٠١: كان سكربتًا بلا دالّة `test_`، فيجمع منه pytest صفرًا ويعلن
# «no tests ran» — ذرّةٌ حارسةٌ للمرجع بلا تغطية فعليّة وهي تبدو مغطّاة.
def test_521_reference_health(): asyncio.run(main())



async def _health_scenario():
    """الصحّة كانت تقول «reference_available» بمجرّد أن يصلح رمزٌ واحد.

    مقيس ٢٠٢٦-٠٩-١٠: ثمانية رموز من تسعة `STALE` والشارة خضراء، بينما ٥٥٢
    يرفض كل أمرٍ لتلك الثمانية بـ`REFERENCE_NOT_USABLE`. الرسالة يجب أن
    تحمل الحصيلة والأسماء — `details` تُحذف بالنواة فلا تبلغ اللوحة.
    """
    b=Bus(); a=mod.Atom(); await a.initialize(b.ctx()); await a.start()
    CLOCK.value=12.0
    await a._on_primary({"symbol":"OLD","bid":99.5,"ask":100.5,"price":100,"exchange_timestamp":10})
    assert a.state("OLD")["state"]=="HEALTHY", a.state("OLD")["state"]
    h=await a.health_check()
    assert h.message=="تداول=1/1", h.message
    # تمضي الساعة: OLD يتجاوز عتبتَي 5ث و30ث، ويصل رمزٌ طازج
    CLOCK.value=200.0
    await a._on_primary({"symbol":"FRESH","bid":49.5,"ask":50.5,"price":50,"exchange_timestamp":199})
    await a._on_pulse({"official_time":200})
    assert a.state("OLD")["state"]=="STALE", a.state("OLD")["state"]
    assert a.state("FRESH")["state"]=="HEALTHY", a.state("FRESH")["state"]
    h=await a.health_check()
    assert h.state is mod.HealthState.HEALTHY
    assert "تداول=1/2" in h.message, ("الرسالة تخفي البائت: %r" % h.message)
    assert "OLD" in h.message, ("الرمز البائت بلا اسم: %r" % h.message)
    assert "FRESH" not in h.message, h.message
    print("OK — 521 يعلن الحصيلة والأسماء: %s" % h.message)


def test_521_health_reports_unusable_symbols_by_name():
    asyncio.run(_health_scenario())


SPLIT_CFG={"symbols":[],"max_data_age_s":5,"fallback_max_age_s":30,
           "reference_max_age_s":90,"trading_symbols":["EURUSD"],
           "max_sane_spread":2,"max_tick_jump":10,"min_dwell_s":0}


class SplitBus(Bus):
    def ctx(self): return mod.AtomContext(521,SPLIT_CFG,Log(),self.publish,self.subscribe)


async def _split_scenario():
    """حكم المالك ٢٠٢٦-٠٩-١٠: «مؤشّرات مرجعيّة، مو صالح لا تداول».

    ٦٢٠ ينشر كل ٣٠ ثانية وعتبة الاحتياطي كانت ٣٠ — أي تساوي الدورة —
    فيصل المؤشّر ثمّ يبيت قبل أن يُستعمل. الفصل يعطيه ٩٠ ويُبقي رموز
    التداول على ٥ث/٣٠ث بلا مساس.
    """
    b=SplitBus(); a=mod.Atom(); await a.initialize(b.ctx()); await a.start()
    CLOCK.value=100.0
    await a._on_fallback({"symbol":"^VIX","price":17.5,"timestamp":40})    # عمره 60ث
    await a._on_fallback({"symbol":"EURUSD","price":1.16,"timestamp":40})  # عمره 60ث
    assert a.ages("^VIX")==(90.0,90.0), a.ages("^VIX")
    assert a.ages("EURUSD")==(5.0,30.0), a.ages("EURUSD")
    assert a.state("^VIX")["state"]=="FALLBACK", a.state("^VIX")["state"]
    assert a.state("EURUSD")["state"]=="STALE", a.state("EURUSD")["state"]
    h=await a.health_check()
    assert "تداول=0/1" in h.message, h.message
    assert "مرجعيّة=1/1" in h.message, h.message
    assert "EURUSD" in h.message and "^VIX" not in h.message, h.message
    print("OK — 521 يفصل: %s" % h.message)


def test_521_reference_symbols_get_their_own_freshness():
    asyncio.run(_split_scenario())


async def _legacy_scenario():
    """إعداد بلا `trading_symbols` يبقى على السلوك القديم حرفًا."""
    b=Bus(); a=mod.Atom(); await a.initialize(b.ctx()); await a.start()
    assert a.ages("ANY")==(5.0,30.0), a.ages("ANY")
    print("OK — بلا قائمة تداول، لا شيء يتغيّر")


def test_521_without_trading_list_behaviour_is_unchanged():
    asyncio.run(_legacy_scenario())
if __name__=="__main__": asyncio.run(main())
