import asyncio,importlib.util,sys
from pathlib import Path
root=Path(__file__).resolve().parents[4]; folder=Path(__file__).resolve().parents[1];sys.path.insert(0,str(root));s=importlib.util.spec_from_file_location('a584',folder/'atom.py');m=importlib.util.module_from_spec(s);sys.modules['a584']=m;s.loader.exec_module(m)
class L:
 def __getattr__(self,n):return lambda *a,**k:None
class B:
 def __init__(self):self.e=[];self.subs={}
 # الوهمي القديم كان `subscribe(*a):pass` فيبتلع المشترِك — درس ٥٠٠ ٢٠٢٦-٠٩-٠٩.
 def subscribe(self,event,handler):self.subs.setdefault(event,[]).append(handler)
 async def publish(self,n,p):self.e.append((n,p))

SPEC={'account_id':'A','symbol':'X','point':1,'stops_level':2,'volume_min':.1,'volume_step':.1,'volume_max':10}
ORDER={'request_id':'r','account_id':'A','action':'OPEN','symbol':'X','side':'BUY','volume':1,
       'reference_price':100,'stop_loss':99,'take_profit':102}
# ٢٠٢٦-١٠-٠٨ (إصلاح الاختبارات القديمة بأمر المالك): `ORDER` وقفه 1 دون حدّ الوسيط 2 (stops_level 2 × point 1) فيُرفض اليوم ولا يُوسَّع بأمر ٠٩-١٨؛ وهذا أمرٌ شرعيّ وقفه 2 = الحدّ بالضبط وهدفه 1:3 ليُختبر به مسار الإجازة.
LEGAL_ORDER={**ORDER,'stop_loss':98,'take_profit':106}

def _manifest_config():
    """الإعداد من المانيفست نفسه لا من يد الاختبار.

    كان الوهميّ يمرّر `reward_risk: 2` مكتوبًا هنا، فبقي العيار المختوم
    (٣ بحكم المالك ٢٠٢٦-٠٩-١٠) بلا حارس: يتغيّر المانيفست أو لا يتغيّر
    والاختبار أخضر في الحالتين. الآن ينكسر إن انحرف أحدهما عن الآخر.
    """
    import yaml
    path = Path(__file__).resolve().parents[1] / "manifest.yaml"
    cfg = dict(yaml.safe_load(path.read_text(encoding="utf-8"))["config"])
    # السيناريو مصغَّر عمدًا (أسعار 100 لا 78,000) فلا يحتمل أرضيّة ٢٠٠
    # نقطة ولا هامش ٢٠. العيار المحروس هنا هو `reward_risk` وحده — وهو
    # الذي نُقض. الباقي مضبوط للسيناريو.
    return {"stop_buffer": 0, "hard_floor_points": 0, "reward_risk": cfg["reward_risk"]}


async def _wired():
    b=B();a=m.Atom();await a.initialize(m.AtomContext(584,_manifest_config(),L(),b.publish,b.subscribe));await a.start();return b,a
def _last(b,name):
    rows=[p for n,p in b.e if n==name]
    return rows[-1] if rows else None

def test_legality_adjusts_volume_and_stop():
    # ٢٠٢٦-١٠-٠٨ (إصلاح الاختبارات القديمة بأمر المالك): كان يتوقّع توسيع الوقف 99←98 وقصّ الحجم 1←0.5 (`legality_adjusted`)، وذلك نقضه أمر ٠٩-١٨ «الوقف لا يوسَّع · المرفوضة تُرفض ولا تُعدَّل» (atom.py:249-265)؛ فالحارس نفسه باقٍ: وقفٌ دون حدّ الوسيط لا يعبر، والحجم يُقرَّب لخطوة الوسيط.
    async def run():
        b,a=await _wired()
        for h in b.subs[m.EVENT_SPECS]: await h({'symbols':[SPEC]})
        for h in b.subs[m.EVENT_BUILT]: await h(dict(ORDER))
        assert _last(b,m.EVENT_LEGAL) is None, "وقفٌ دون حدّ الوسيط أُجيز"
        r=_last(b,m.EVENT_REJECTED)
        assert r is not None and r['reason']=='STOP_BELOW_FLOOR', r
        assert r['min_stop_distance']==2 and r['requested_distance']==1, r
        assert r['stop_loss']==99 and r['take_profit']==102 and r['volume']==1, "المرفوض عُدِّل: %r" % r
        assert a._floor_rejected==1, a._floor_rejected
        # ٢٠٢٦-١٠-٠٨ (إصلاح الاختبارات القديمة بأمر المالك): والأمر الشرعيّ يعبر بوقفه وهدفه كما وردا، ويُقرَّب حجمه 1.37 لأسفل إلى خطوة 0.1.
        for h in b.subs[m.EVENT_BUILT]: await h({**LEGAL_ORDER,'volume':1.37})
        p=_last(b,m.EVENT_LEGAL)
        assert p is not None and abs(p['volume']-1.3)<1e-9, p
        assert p['stop_loss']==98 and p['take_profit']==106 and p['min_stop_distance']==2, p
    asyncio.run(run())

def test_spec_riding_the_order_rescues_an_empty_map():
    """٣٤٧ رفضًا بـ«لا مواصفات» فوق مواصفةٍ حاضرة في حمولة الأمر.

    خريطة `_specs` تُملأ كل ٣٠٠ ثانية من دورة ٦١٨ وتُمسح مع كل إعادة تحميل
    ساخنة.  مقيس ٢٠٢٦-٠٩-١٠: `legal=0 rejected=19` ثمّ قفز `legal` إلى ١١
    لحظة وصول الدورة — والمواصفة كانت في يد الذرّة طوال الوقت.
    """
    async def run():
        b,a=await _wired()
        assert not a._specs, "الخريطة يجب أن تبدأ فارغة كما بعد أي إقلاع"
        # ٢٠٢٦-١٠-٠٨ (إصلاح الاختبارات القديمة بأمر المالك): الأمر شرعيّ الوقف الآن، لأنّ `ORDER` القديم يُرفض بـSTOP_BELOW_FLOOR (لا توسيع منذ ٠٩-١٨) فيحجب ما يحرسه هذا الاختبار: المواصفة المرافقة تنقذ الخريطة الفارغة.
        order=dict(LEGAL_ORDER); order['symbol_spec']=dict(SPEC); order['symbol_resolution_status']='RESOLVED'
        for h in b.subs[m.EVENT_BUILT]: await h(order)
        assert _last(b,m.EVENT_REJECTED) is None, "رُفض والمواصفة في حمولته"
        p=_last(b,m.EVENT_LEGAL)
        assert p is not None and p['volume']==1.0 and p['stop_loss']==98, p
        assert a._spec_from_order==1, a._spec_from_order
    asyncio.run(run())

def test_map_wins_over_the_payload_when_both_exist():
    async def run():
        b,a=await _wired()
        for h in b.subs[m.EVENT_SPECS]: await h({'symbols':[SPEC]})
        # ٢٠٢٦-١٠-٠٨ (إصلاح الاختبارات القديمة بأمر المالك): أمرٌ شرعيّ الوقف بدل `ORDER` المرفوض الآن؛ ولو قُرئت مواصفة الحمولة (volume_min 99) لرُفض بـVOLUME_BELOW_MINIMUM.
        order=dict(LEGAL_ORDER); order['symbol_spec']={**SPEC,'volume_min':99}
        for h in b.subs[m.EVENT_BUILT]: await h(order)
        assert a._spec_from_order==0, "الخريطة هي المصدر الأوّل"
        assert _last(b,m.EVENT_REJECTED) is None, _last(b,m.EVENT_REJECTED)
        assert _last(b,m.EVENT_LEGAL)['volume']==1.0
    asyncio.run(run())

def test_a_spec_for_another_symbol_is_refused():
    async def run():
        b,a=await _wired()
        order=dict(ORDER); order['symbol_spec']={**SPEC,'symbol':'OTHER'}
        for h in b.subs[m.EVENT_BUILT]: await h(order)
        r=_last(b,m.EVENT_REJECTED)
        assert r is not None and r['reason']=='NO_SYMBOL_SPECS', r
        assert a._spec_from_order==0
    asyncio.run(run())

def test_no_map_and_no_payload_still_rejects():
    async def run():
        b,a=await _wired()
        for h in b.subs[m.EVENT_BUILT]: await h(dict(ORDER))
        r=_last(b,m.EVENT_REJECTED)
        assert r is not None and r['reason']=='NO_SYMBOL_SPECS', r
    asyncio.run(run())

def test_health_carries_the_numbers():
    async def run():
        b,a=await _wired()
        # ٢٠٢٦-١٠-٠٨ (إصلاح الاختبارات القديمة بأمر المالك): أمرٌ شرعيّ الوقف كي يُعدّ `legal=1`؛ `ORDER` القديم يُرفض الآن دون حدّ الوسيط.
        order=dict(LEGAL_ORDER); order['symbol_spec']=dict(SPEC)
        for h in b.subs[m.EVENT_BUILT]: await h(order)
        h1=await a.health_check()
        assert 'legal=1' in h1.message and 'rejected=0' in h1.message and 'specs=0' in h1.message and 'from_order=1' in h1.message, h1.message
    asyncio.run(run())



def test_rebuilt_target_honours_three_to_one():
    """حكم المالك ٢٠٢٦-٠٩-١٠: «ربح صفقة لا يقلّ عن ٣ أضعاف حجم ستوب».

    حين يُزيح ٥٨٤ وقفًا أضيق من حدّ الوسيط، يعيد بناء الهدف من المسافة
    الجديدة. وكان `reward_risk=2.0` هنا بينما ٥٢٦ يحمل ٣٫٠ منذ ٢٠٢٦-٠٩-٠٧،
    فالمسار المباشر ينقض حكمًا يطبّقه المسار الكامل. مقيس على المركز
    المفتوح: وقف ٣٨٨٫٩٥ وهدف ٧٩١٫٧٥ = نسبة ٢٫٠٤.
    """
    # ٢٠٢٦-١٠-٠٨ (إصلاح الاختبارات القديمة بأمر المالك): «إعادة بناء الهدف» لم تعد موجودة لأنّ ٥٢٥ لا يوسّع الوقف أصلًا (أمر ٠٩-١٨)، والنسبة 1:3 الصافية بعد السبريد تُحكم عند الإرسال في ٥٥٥ (`send_economics` · أمر ١٠-٠٢)؛ فالمحروس هنا: الوقف الضيّق يُرفض فلا تنقلب النسبة، والشرعيّ يخرج بنسبته كما بُني.
    async def run():
        b,a=await _wired()
        assert a._reward==3.0, "العيار %r وليس ٣" % a._reward
        for h in b.subs[m.EVENT_SPECS]: await h({'symbols':[SPEC]})
        for h in b.subs[m.EVENT_BUILT]: await h(dict(ORDER))
        assert _last(b,m.EVENT_LEGAL) is None, "وقفٌ دون حدّ الوسيط عبر — والتوسيع يقلب النسبة"
        assert _last(b,m.EVENT_REJECTED)['reason']=='STOP_BELOW_FLOOR'
        for h in b.subs[m.EVENT_BUILT]: await h(dict(LEGAL_ORDER))
        p=_last(b,m.EVENT_LEGAL)
        ref=p['reference_price']; sl=p['stop_loss']; tp=p['take_profit']
        risk=abs(ref-sl); reward=abs(tp-ref)
        assert risk>0 and round(reward/risk,4)==3.0, (
            "النسبة %.2f وليست ٣ (ref=%s sl=%s tp=%s)" % (reward/risk, ref, sl, tp))
        print("OK — %.1f ÷ %.1f = 1:%.0f" % (reward, risk, reward/risk))
    asyncio.run(run())


def test_owned_target_is_never_overwritten():
    """والهدف المملوك من التحليل يعبر كما هو — النسبة احتياطٌ لا مصادرة."""
    # ٢٠٢٦-١٠-٠٨ (إصلاح الاختبارات القديمة بأمر المالك): الهدف يعبر اليوم كما ورد في `take_profit` (لا يُعاد بناؤه)، فيُرسَل هدف التحليل فيه؛ والمرفوض دون حدّ الوسيط يُردّ بمستوياته كما هي لا معدَّلة.
    async def run():
        b,a=await _wired()
        for h in b.subs[m.EVENT_SPECS]: await h({'symbols':[SPEC]})
        order=dict(LEGAL_ORDER); order['analysis_target']=115.0; order['take_profit']=115.0
        for h in b.subs[m.EVENT_BUILT]: await h(order)
        p=_last(b,m.EVENT_LEGAL)
        assert p['take_profit']==115.0 and p['stop_loss']==98 and p['analysis_target']==115.0, p
        narrow=dict(ORDER); narrow['analysis_target']=115.0; narrow['take_profit']=115.0
        for h in b.subs[m.EVENT_BUILT]: await h(narrow)
        r=_last(b,m.EVENT_REJECTED)
        assert r['reason']=='STOP_BELOW_FLOOR' and r['take_profit']==115.0 and r['stop_loss']==99, r
        print("OK — هدف التحليل لم يُمَسّ")
    asyncio.run(run())

if __name__=='__main__':
    for name,fn in sorted(globals().items()):
        if name.startswith('test_'): fn()
    print('584 stop legality tests passed')
