from __future__ import annotations

import math
from typing import Any

import clock
from core.contracts.atom import AtomBase, AtomContext, HealthState, HealthStatus

ATOM_VERSION="3.1.0"
# v3.0.0 (2026-09-16، ختم المالك `NQ`: «شيّلها») — **سعر منصّة التنفيذ
# لا يبوّب أمرًا.** حُذف `feed.mt5.tick` من المرجع الأوّليّ.
#
# v2.3.0 (2026-08-25) كان قد أضافه: بتكوين مرجعُه الوحيد تيّار سي‑تريدر،
# ونقلُه يتشبّع دفعاتٍ (عمر التِكّة 26-45ث مقابل نافذة 5ث)، فماتت ستّة
# أوامرَ مبنيّة على `REFERENCE_NOT_USABLE` داخل نافذة بياتٍ واحدة بينما
# الوسيطُ الذاهبة إليه يبثّ أسعارًا طازجة. الملاحظة صحيحة والعلاج كان
# في الموضع الخطأ.
#
# وحجّة المالك لا تُردّ: «لأنّه ميتاتريدر من وسيط محترم عم تحسّها
# صحيحة — هلّق أجيب وسيط زبالة، صانع سوق داخليّ، متلاعب، نصّاب، كيف
# راح يكون الوضع؟». نظافةُ تِكّاته مقيسةٌ اليوم (ساعة -0.05ث · صفر
# سوقٍ مقلوب في 188 صفًّا) وهي صفةُ **الوسيط الحاليّ** لا صفةُ المعمار.
# ومن يقيس على منصّة تنفيذه يسلّم الوسيطَ مفتاحَ بوّابة أوامره: صانع
# السوق الداخليّ يربح من الطرف الآخر لصفقتك، فتِكّةٌ منه تفتح البوّابة
# أو تغلقها متى شاء.
#
# وثمنُ الحذف معلَن: إذا بات سي‑تريدر خلا الرمزُ من مرجعٍ فانحجب أمره.
# وهذا هو السلوك المكتوب في ٦١٣ نفسه — «التحليل يصمت ولا يتغذّى من سعر
# غير موثوق». صمتٌ خيرٌ من سعرٍ يرسمه غيرك. والبيات يُعالَج في طريق
# سي‑تريدر (توزيع النقل)، لا باستبدال المصدر.
EVENT_PRIMARY="feed.ctrader.tick"
EVENT_FALLBACK="market.reference"
EVENT_PULSE="SYS_SECOND"
EVENT_OUT="reference.health.state"
PRIMARY="primary"
FALLBACK="fallback"
DEFAULT_MAX_AGE=5.0
DEFAULT_FALLBACK_AGE=30.0
# ٦٢٠ ينشر المؤشّرات كل ٣٠ ثانية، فعتبةٌ قدرها ٣٠ تساوي الدورة بالضبط:
# يصل المؤشّر ثمّ يبيت قبل أن يُستعمل. ثلاثة أضعاف الدورة تعطيه هامشًا.
DEFAULT_REFERENCE_AGE=90.0
DEFAULT_MAX_SPREAD=10.0
DEFAULT_MAX_JUMP=100.0
DEFAULT_DWELL=0.0


def num(v: Any)->float|None:
    try:r=float(v)
    except (TypeError,ValueError):return None
    return r if math.isfinite(r) else None

def text(v: Any, default="")->str:
    if v is None:return default
    r=str(v).strip()
    return r or default

def source_stamp(p):
    for k in ("exchange_timestamp","source_timestamp","timestamp","received_at"):
        v=num(p.get(k))
        if v is not None:return v
    return None

class Atom(AtomBase):
    def __init__(self):
        self._context=None
        self._running=False
        self._feeds={}
        self._last_prices={}
        # ٢٠٢٦-٠٩-٠١: يبقى مخزَّنًا للمراقبة فقط — الحكم لا يعتمد عليه.
        self._now=None
        self._states={}
        self._max_age=5.0
        self._fallback_age=30.0
        self._reference_age=DEFAULT_REFERENCE_AGE
        self._trading=set()
        self._max_spread=10.0
        self._max_jump=100.0
        self._dwell=0.0
        self._symbols=set()
        self._seen=0
        self._rejected=0
        self._published=0
        # سلكُ إنذار: يسجّل **اسم المزوّد** الذي وصل على المسار الأوّليّ.
        # بعد v3.0.0 لا يصحّ أن يظهر فيه غير `CTRADER`؛ فإن ظهر مزوّدٌ
        # آخر يومًا، نطقت به رسالةُ الصحّة في اللحظة نفسها بدل أن يتسلّل
        # سعرُ منصّة تنفيذٍ إلى بوّابة الأوامر سنةً بلا أن يُرى.
        # ⚠️ للقراءة فقط: `candidate` و`_publish` لم يُمسّا.
        self._sources={}
    async def initialize(self,context):
        self._context=context
        cfg=context.config
        self._symbols={text(x) for x in cfg.get("symbols",[]) if text(x)}
        self._max_age=num(cfg.get("max_data_age_s")) or DEFAULT_MAX_AGE
        self._fallback_age=num(cfg.get("fallback_max_age_s")) or DEFAULT_FALLBACK_AGE
        self._reference_age=num(cfg.get("reference_max_age_s")) or DEFAULT_REFERENCE_AGE
        self._trading={text(x) for x in cfg.get("trading_symbols",[]) if text(x)}
        self._max_spread=num(cfg.get("max_sane_spread")) or DEFAULT_MAX_SPREAD
        self._max_jump=num(cfg.get("max_tick_jump")) or DEFAULT_MAX_JUMP
        self._dwell=num(cfg.get("min_dwell_s")) or DEFAULT_DWELL
        context.subscribe(EVENT_PRIMARY,self._on_primary)
        context.subscribe(EVENT_FALLBACK,self._on_fallback)
        context.subscribe(EVENT_PULSE,self._on_pulse)
    async def start(self): self._running=True
    async def stop(self): self._running=False
    async def shutdown(self): await self.stop()
    def feed(self,s): return self._feeds.setdefault(s,{PRIMARY:{},FALLBACK:{}})
    def allowed(self,s): return not self._symbols or s in self._symbols
    def fresh(self,f,age):
        """طزاجة العيّنة مقيسةً على السلطة الزمنيّة، لا على حمولة النبضة.

        ٢٠٢٦-٠٩-٠١ (مقيس حيًّا): كان «الآن» يُؤخذ من `official_time` داخل
        نبضة `SYS_SECOND` الواصلة عبر صندوق بريد. القياس على النواة الحيّة:
        النبضة تصل كاملةً (‏`delivered=1,032,593` · `dropped=0`) لكن طابعها
        يتأخّر تأخّرًا تراكميًّا، فيصير أحدث من طابعها **طابعُ التِكّة نفسه**؛
        فيخرج `self._now - ts` **سالبًا** ويسقط شرط `0.0 <= …`، فتُصنَّف كل
        عيّنة «غير طازجة» ويُعلَن `NO_USABLE_REFERENCE` بينما 622 سليمة
        وتُسلّم 147,363 تِكّة و613 تمرّر تسعة رموز. لا مرجع مفقود — بل ساعةٌ
        وصلت متأخّرة. القراءة الآن من `clock` مباشرة بلا طابور.
        **حدود الطزاجة لم تُمَسّ حرفًا** (`max_age`/`fallback_age` كما هي)."""
        if not f.get("valid") or f.get("timestamp") is None:return False
        return 0.0<=clock.now()-f["timestamp"]<=age
    def jump_ok(self,source,s,p):
        key=source+"|"+s
        old=self._last_prices.get(key)
        self._last_prices[key]=p
        return not(old is not None and self._max_jump>0 and abs(p-old)>self._max_jump)
    async def _on_primary(self,p):
        if not self._running or not isinstance(p,dict):return
        s=text(p.get("symbol"));
        if not s or not self.allowed(s):return
        bid=num(p.get("bid"))
        ask=num(p.get("ask"))
        price=num(p.get("price"))
        if price is None and bid is not None and ask is not None:price=(bid+ask)/2
        ts=source_stamp(p)
        f=self.feed(s)[PRIMARY]
        reason=""
        if price is None or price<=0:reason="BAD_PRICE"
        elif bid is None or ask is None or bid<=0 or ask<=0:reason="BAD_BID_ASK"
        elif ask<bid:reason="CROSSED_MARKET"
        elif ask-bid>self._max_spread:reason="WIDE_SPREAD"
        elif not self.jump_ok(PRIMARY,s,price):reason="TICK_JUMP"
        elif ts is None:reason="MISSING_SOURCE_TIMESTAMP"
        elif f.get("timestamp") is not None and ts<=f["timestamp"]:return
        self._sources.setdefault(s,{})[text(p.get("provider"),"?").upper()]={
            "valid":not reason,"reason":reason,"timestamp":ts,"price":price}
        self._seen+=1
        f.update({"valid":not reason,"reason":reason,"timestamp":ts,"price":price,"bid":bid,"ask":ask,"spread":ask-bid if bid is not None and ask is not None else None})
        if reason:self._rejected+=1
        await self._publish(s)
    async def _on_fallback(self,p):
        if not self._running or not isinstance(p,dict):return
        s=text(p.get("symbol"));
        if not s or not self.allowed(s):return
        price=num(p.get("value")) or num(p.get("price"))
        ts=source_stamp(p)
        f=self.feed(s)[FALLBACK]
        reason=""
        if price is None or price<=0:reason="BAD_PRICE"
        elif not self.jump_ok(FALLBACK,s,price):reason="TICK_JUMP"
        elif ts is None:reason="MISSING_SOURCE_TIMESTAMP"
        elif f.get("timestamp") is not None and ts<=f["timestamp"]:return
        self._seen+=1
        f.update({"valid":not reason,"reason":reason,"timestamp":ts,"price":price,"provider":text(p.get("provider"),"fallback")})
        if reason:self._rejected+=1
        await self._publish(s)
    async def _on_pulse(self,p):
        if not self._running or not isinstance(p,dict):return
        now=num(p.get("official_time"))
        if now is None:return
        self._now=now
        for s in list(self._feeds):await self._publish(s)
    def ages(self,s):
        """عتبتا الطزاجة لهذا الرمز — والمؤشّر المرجعيّ ليس سعر تنفيذ.

        حكم المالك ٢٠٢٦-٠٩-١٠: «^TNX/^VIX مؤشّرات مرجعيّة، مو صالح لا
        تداول» و«رموز تداول ٧». وكان الاثنان يُقاسان بمسطرة التنفيذ
        (٥ث/٣٠ث) وهما يصلان من مصدرٍ دوريّ بطيء: ٦٢٠ ينشر كل ٣٠ ثانية
        بالضبط، فالعتبة تساوي الدورة ويبيت المؤشّر في اللحظة التي
        يُنتظر فيها التالي. مقيس ٢٠٢٦-٠٩-١٠: `^TNX,^VIX` في قائمة «لا
        مرجع» بينما ٦٢٠ حيّ (`published` يتقدّم ٣ كل ٧٥ ثانية).

        ورموز التداول لا تُمَسّ عتبتاها حرفًا: سعرٌ يُبنى عليه أمرٌ يبقى
        محكومًا بخمس ثوانٍ أساسيًّا وثلاثين احتياطيًّا.
        """
        if self._trading and s not in self._trading:
            return self._reference_age,self._reference_age
        return self._max_age,self._fallback_age

    def candidate(self,s):
        f=self.feed(s)
        primary_age,fallback_age=self.ages(s)
        p=self.fresh(f[PRIMARY],primary_age)
        q=self.fresh(f[FALLBACK],fallback_age)
        candidate=PRIMARY if p else FALLBACK if q else None
        current=f.get("selected",{}).get("provider")
        if candidate and current and candidate!=current and f["selected"].get("at") is not None and clock.now()-f["selected"]["at"]<self._dwell:
            candidate=current
        if candidate!=current:f["selected"]={"provider":candidate,"at":clock.now()}
        return candidate,p,q
    async def _publish(self,s):
        if self._context is None:return
        provider,p,q=self.candidate(s)
        f=self.feed(s)
        selected=f.get(provider,{}) if provider else {}
        state="HEALTHY" if provider==PRIMARY else "FALLBACK" if provider==FALLBACK else "STALE" if f[PRIMARY].get("timestamp") or f[FALLBACK].get("timestamp") else "INVALID"
        ts=selected.get("timestamp")
        age=clock.now()-ts if ts is not None else None
        out={"symbol":s,"state":state,"selected_provider":provider,"selected_price":selected.get("price"),"source_timestamp":ts,"data_age_s":age,"primary":dict(f[PRIMARY]),"fallback":dict(f[FALLBACK]),"warnings":[]}
        self._states[s]=out
        await self._context.publish(EVENT_OUT,out)
        self._published+=1
    def state(self,s):return self._states.get(s)
    def source_ready(self,s,src):
        """أيغطّي هذا المصدرُ وحدَه هذا الرمزَ الآن؟ بعتبة الرمز نفسها."""
        f=(self._sources.get(s) or {}).get(src)
        return bool(f) and self.fresh(f,self.ages(s)[0])
    def why(self,s):
        """سببُ غياب المرجع لرمزٍ بعينه — بالاسم لا بالغياب.

        الرسالة كانت تقول «لا مرجع للتداول: BTCUSD,GBPUSD,US30,USTEC»
        وتسكت عن السبب، فيُقرأ الغياب كانقطاع تغذية. وقياس ٢٠٢٦-٠٩-١٦
        نفى ذلك: الأربعة غائبة بينما ٦٢٢ تُسلّم و٦٢٣ تُصدر بلا فقد
        (`malformed=0`، `received == emitted`). فالسبب هنا حكمٌ من هذه
        الذرّة لا صمتٌ من المصدر — ويجب أن يُنطق باسمه.

        يُوضع في **الرسالة** لا في `details`: الأخيرة تُقصّ عند حدود
        النواة فلا تبلغ لوحةً ولا API.
        """
        x=self._states.get(s) or {}
        pr=x.get("primary") or {}
        fb=x.get("fallback") or {}
        if pr.get("reason"):return pr["reason"]
        ts=pr.get("timestamp")
        if ts is None:
            return "لا أوّليّ قطّ" if fb.get("timestamp") is None else "احتياطيّ فقط"
        age=clock.now()-ts
        if age<0.0:return "ساعة %+.0fث"%age
        # ٢٠٢٦-٠٩-١٦: الرقم كان عاريًا («بائت ٣١ث») فيُقرأ حكمًا على الرمز،
        # والسؤال الحقيقيّ **مقابل ماذا**. المقيس لحظتها: الرموز السبعة كلّها
        # بائتة بأعمار ١٤ إلى ٣٧ ثانية، والعتبة خمس — بينما المغذّي نفسه
        # يُقرّ أنّه يسلّم بعمر ٨٫٤٨/١٢٫٤٥/٢٢٫٦٤ ثانية. فالعتبة والواقع
        # لا يلتقيان، ولا يُعرف ذلك من رقمٍ بلا مقياسه.
        limit,_=self.ages(s)
        return "بائت %.0fث/%.0fث"%(age,limit)
    async def health_check(self):
        if not self._running:return HealthStatus(state=HealthState.UNHEALTHY,message="NOT_STARTED")
        usable={s for s,x in self._states.items() if x.get("state") in ("HEALTHY","FALLBACK")}
        # ٢٠٢٦-٠٩-١٠ (حكم المالك «رموز تداول ٧»): الرقم كان مخلوطًا —
        # `usable=6/11` تجمع سبعة رموز تداول بأربعة مؤشّرات مرجعيّة، فلا
        # يُعرف أيُّ نصفٍ هو الذي يمنع الأمر. الرمز الذي يُبنى عليه أمرٌ
        # يُعدّ وحده، والمؤشّر يُعلَن غيابه ولا يُخلط بمسطرة التنفيذ.
        trading={s for s in self._states if not self._trading or s in self._trading}
        refs=set(self._states)-trading
        trade_missing=sorted(trading-usable)
        ref_missing=sorted(refs-usable)
        good=len(usable)
        d={"symbols":len(self._feeds),"seen":self._seen,"rejected":self._rejected,
           "published":self._published,"usable":good,
           "trading_missing":trade_missing,"reference_missing":ref_missing,
           "by_source":{s:{k:{"valid":v.get("valid"),"reason":v.get("reason")}
                           for k,v in d2.items()} for s,d2 in self._sources.items()}}
        if not self._states:return HealthStatus(state=HealthState.DEGRADED,message="NO_REFERENCE_DATA",details=d)
        if not good:return HealthStatus(state=HealthState.DEGRADED,message="NO_USABLE_REFERENCE | symbols=%d"%len(self._states),details=d)
        message="تداول=%d/%d"%(len(trading&usable),len(trading))
        if refs:message+=" · مرجعيّة=%d/%d"%(len(refs&usable),len(refs))
        # تغطية كلّ مصدرٍ وحده — الرقم الذي يقول هل يكفي أحدهما.
        # ولا يُعلَن مصدرٌ لم يصل منه شيءٌ قطّ: «صفر من سبعة» عن مصدرٍ
        # غائبٍ أصلًا خبرٌ كاذب، و«صفر» عن مصدرٍ كان يصل ثمّ سقط خبرٌ
        # صادق — والفرق بينهما هو كلُّ الفائدة.
        seen_src={k for d2 in self._sources.values() for k in d2}
        names={"MT5":"وحده MT5","CTRADER":"وحده سي‑تريدر"}
        for src in ("MT5","CTRADER"):
            if trading and src in seen_src:
                message+=" · %s=%d/%d"%(names[src],
                    sum(1 for s in trading if self.source_ready(s,src)),len(trading))
        if trade_missing:message+=" | لا مرجع للتداول: %s"%",".join(
            "%s(%s)"%(s,self.why(s)) for s in trade_missing)
        if ref_missing:message+=" | مؤشّرات غائبة: %s"%",".join(ref_missing)
        return HealthStatus(state=HealthState.HEALTHY,message=message,details=d)
