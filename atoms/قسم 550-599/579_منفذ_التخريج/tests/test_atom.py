import asyncio
import importlib.util
import sys
from pathlib import Path

root=Path(__file__).resolve().parents[4]; folder=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root)); sys.path.insert(0,str(folder)); spec=importlib.util.spec_from_file_location("_atom579_final",folder/"atom.py"); mod=importlib.util.module_from_spec(spec); sys.modules["_atom579_final"]=mod; spec.loader.exec_module(mod)
class L:
    def debug(self,*a,**k):pass
    def info(self,*a,**k):pass
    def warning(self,*a,**k):pass
    def error(self,*a,**k):pass
    def critical(self,*a,**k):pass
class B:
    def __init__(self):self.e=[]
    def subscribe(self,*a):pass
    async def publish(self,n,p):self.e.append((n,p))
    def c(self):return mod.AtomContext(579,{"lot_step":.01},L(),self.publish,self.subscribe)
def ev(b,n):return [p for x,p in b.e if x==n]
async def new():
    b=B();a=mod.Atom();await a.initialize(b.c());await a.start();return a,b
async def positions(a):
    await a._on_positions({"positions":[
        {"account_id":"A","symbol":"X","ticket":1,"side":"BUY","volume":1,"profit":100},
        {"account_id":"A","symbol":"X","ticket":2,"side":"SELL","volume":2,"profit":10},
    ]})
async def main():
    a,b=await new();await positions(a)
    await a._on_partial({"extraction_id":"e1","account_id":"A","symbol":"X","amount":50})
    assert ev(b,mod.EVENT_PENDING) and str(ev(b,mod.EVENT_MANAGE)[-1]["ticket"])=="1" and not ev(b,mod.EVENT_CONFIRMED)
    await a._on_trade({"event_type":"PARTIAL","ticket":1,"account_id":"A","symbol":"X","request_id":"e1-1-a1","profit":50})
    assert ev(b,mod.EVENT_CONFIRMED)[-1]["actual_amount"]==50
    print("OK — الأمر لا يُحسب تخريجًا حتى يصل حدث الوسيط الفعلي")

    # ٢٠٢٦-١٠-٠٥ (5.4.0): رابحٌ لا يغطّي المبلغ (10$ من 20$) لا يُغلق كلّه — كان يُغلق
    # فحقّق ذهبُ ٠٩-٢٧ 0.72$ من 370$ وقتل صفقةً للتوّ فُتحت. ينتظر رابحًا يغطّيه.
    a2,b2=await new();await a2._on_positions({"positions":[{"account_id":"A","symbol":"X","ticket":9,"side":"BUY","volume":1,"profit":10}]})
    await a2._on_partial({"extraction_id":"e2","account_id":"A","symbol":"X","amount":20})
    assert not ev(b2,mod.EVENT_MANAGE) and "e2" in a2._deferred and a2._short_holds==1
    await a2._on_positions({"positions":[{"account_id":"A","symbol":"X","ticket":9,"side":"BUY","volume":1,"profit":40}]})
    assert ev(b2,mod.EVENT_MANAGE)[-1]["volume"]==0.5 and "e2" not in a2._deferred
    print("OK — الرابح الذي لا يغطّي المبلغ ينتظر، ثمّ يُغلق منه ما يحقّقه حين يغطّيه")

    # منذ 5.2.0 (ختم ٢٠٢٦-٠٩-٢٥): غياب الرابح انتظارٌ لا فشل — والخاسرة لا تُغلق.
    a3,b3=await new();await a3._on_positions({"positions":[{"account_id":"A","symbol":"X","ticket":9,"side":"BUY","volume":1,"profit":0}]})
    await a3._on_partial({"extraction_id":"e3","account_id":"A","symbol":"X","amount":20})
    assert not ev(b3,mod.EVENT_MANAGE) and not ev(b3,mod.EVENT_FAILED) and "e3" in a3._deferred
    print("OK — لا يغلق رجلًا خاسرة: الطلب ينتظر ولا يفشل")

    a4,b4=await new();await positions(a4)
    await a4._on_full({"extraction_id":"full1","account_id":"A","symbol":"X","amount":200})
    assert len(ev(b4,mod.EVENT_MANAGE))==2 and not ev(b4,mod.EVENT_DEACTIVATE)
    await a4._on_trade({"event_type":"CLOSED","ticket":1,"account_id":"A","symbol":"X","request_id":"full1-1-a1","profit":100})
    assert not ev(b4,mod.EVENT_DEACTIVATE)
    await a4._on_trade({"event_type":"CLOSED","ticket":2,"account_id":"A","symbol":"X","request_id":"full1-2-a1","profit":10})
    assert ev(b4,mod.EVENT_CONFIRMED) and ev(b4,mod.EVENT_DEACTIVATE)
    print("OK — التخريج الكامل ينتظر إغلاق كل الأرجل الفعلي قبل التعطيل")

    a5,b5=await new();assert (await a5.health_check()).state==mod.HealthState.HEALTHY
    print("OK — الصحة")

    # ٢٠٢٦-١٠-٠٥ (5.4.0): الإكسبرت يكتب `request_id` فارغًا في كلّ إغلاق — يُطابَق بالتذكرة
    # والحجم وسبب الإكسبرت `SYSTEM`، وإغلاقٌ بالوقف على التذكرة نفسها ليس تأكيدًا.
    a6,b6=await new();await positions(a6)
    await a6._on_partial({"extraction_id":"e6","account_id":"A","symbol":"X","amount":50})
    vol=ev(b6,mod.EVENT_MANAGE)[-1]["volume"]
    await a6._on_trade({"event_type":"PARTIAL","ticket":1,"account_id":"A","symbol":"X","request_id":"","reason":"SL","volume":vol,"profit":50})
    assert not ev(b6,mod.EVENT_CONFIRMED), "إغلاق الوقف عُدّ تأكيدًا"
    await a6._on_trade({"event_type":"PARTIAL","ticket":1,"account_id":"A","symbol":"X","request_id":"","reason":"SYSTEM","volume":vol+0.01,"profit":50})
    assert not ev(b6,mod.EVENT_CONFIRMED), "حجمٌ غير حجم الأمر عُدّ تأكيدًا"
    await a6._on_trade({"event_type":"PARTIAL","ticket":1,"account_id":"A","symbol":"X","request_id":"","reason":"SYSTEM","volume":vol,"profit":50})
    assert ev(b6,mod.EVENT_CONFIRMED)[-1]["actual_amount"]==50 and not a6._pending_by_ticket
    print("OK — التأكيد بلا رقم الطلب: التذكرة والحجم وإغلاق الإكسبرت معًا، لا أقلّ")

    # إلغاء 524 (قائمةٌ حالةً): يُسحب المنتظر والفاشل، ويبقى ما في الطريق إلى الوسيط.
    a7,b7=await new()
    a7._deferred["e7"]={"extraction_id":"e7","account_id":"A","symbol":"X","amount":10}
    a7._pending_by_ticket["A|5"]={"extraction_id":"e8","status":mod.STATUS_FAILED,"account_id":"A"}
    a7._pending_by_ticket["A|6"]={"extraction_id":"e8","status":mod.STATUS_EXECUTING,"account_id":"A"}
    await a7._on_withdrawn({"withdrawn":["e7","e8"]})
    assert "e7" not in a7._deferred and "A|5" not in a7._pending_by_ticket and "A|6" in a7._pending_by_ticket
    assert a7._cancelled==2
    print("OK — الإلغاء يسحب المنتظر والفاشل، ولا يمسّ أمرًا في الطريق")

    # 5.4.1 — سباق إقلاع ٢٠٢٦-١٠-٠٥ 20:35: القائمة تصل مع الاشتراك قبل الاستعادة،
    # والاستعادة تعيد الطلب الفاشل. فيُسحب بعدها كذلك.
    a8,b8=await new()
    await a8._on_withdrawn({"withdrawn":["extract-A-X-m0"]})
    await a8.restore({"pending":[{"extraction_id":"extract-A-X-m0","account_id":"A","symbol":"X",
        "kind":"partial","ticket":"1966966966","status":mod.STATUS_FAILED,
        "failure_reason":"EXTRACTION_CONFIRMATION_TIMEOUT"}]})
    assert not a8._pending_by_ticket, a8._pending_by_ticket
    assert (await a8.health_check()).state==mod.HealthState.HEALTHY
    print("OK — قائمةٌ وصلت قبل الاستعادة تسحب ما أعادته الاستعادة")
if __name__=="__main__":asyncio.run(main())
