from __future__ import annotations
import time
from typing import Any
from core.contracts.atom import AtomBase,AtomContext,HealthState,HealthStatus

ATOM_VERSION="2.1.0"
EVENT_RISK="risk.account.state"
EVENT_EXPOSURE="risk.exposure.state"
EVENT_PROFIT="risk.profit_limits.state"
EVENT_SESSION="risk.session_limits.state"
EVENT_OUT="risk.unified.state"
BUCKETS=("risk","exposure","profit","session")
# ٥١٦ و٥٠٨ يبثّان الحقيقة كل بضع ثوانٍ (مقيس ٢٠٢٦-٠٩-٠٩: حدث في كل أربعين
# ثانية على الأقلّ).  صمتٌ أطول من هذا يعني أنّ المجمِّع يعرض ماضيًا، فيقولها
# بدل أن يبقى أخضر فوق بيانات ميتة.  والعتبة أوسع من المقيس ٢٢ ضعفًا كي لا
# تزرع إنذارًا كاذبًا في هدأة السوق.
STALE_AFTER_S=900.0
class Atom(AtomBase):
    def __init__(self):self._context=None;self._running=False;self._risk={};self._exposure={};self._profit={};self._session={};self._seen=0;self._emitted=0;self._last_seen_mono=None
    async def initialize(self,c):
        self._context=c
        for event,name in ((EVENT_RISK,"risk"),(EVENT_EXPOSURE,"exposure"),(EVENT_PROFIT,"profit"),(EVENT_SESSION,"session")):c.subscribe(event,self._handler(name))
    async def start(self):self._running=True
    async def stop(self):self._running=False
    async def shutdown(self):await self.stop()
    def _handler(self,name):
        # يُمسَك **اسم** الوعاء لا الوعاء نفسه: الإمساك بالكائن كان يقطع الوصلة
        # عند أي إعادة إسناد لاحقة، فتذهب كل حمولة حيّة إلى قاموس يتيم.
        attribute="_"+name
        async def handler(p):
            if not self._running or not isinstance(p,dict):return
            account=str(p.get("account_id") or "")
            if not account:return
            getattr(self,attribute)[account]=dict(p)
            self._seen+=1;self._last_seen_mono=time.monotonic()
            await self._publish()
        return handler
    async def _publish(self):
        if self._context is None:return
        accounts=sorted(set(self._risk)|set(self._exposure)|set(self._profit)|set(self._session));rows={a:{"risk":self._risk.get(a),"exposure":self._exposure.get(a),"profit_limits":self._profit.get(a),"session_limits":self._session.get(a),"status":(self._risk.get(a) or {}).get("status","UNKNOWN")} for a in accounts};await self._context.publish(EVENT_OUT,{"id":"risk_manager","role":"READ_ONLY_AGGREGATOR","authority":"516","accounts":rows,"count":len(rows)});self._emitted+=1
    async def snapshot(self):return {"version":ATOM_VERSION,"risk":self._risk,"exposure":self._exposure,"profit":self._profit,"session":self._session}
    async def restore(self,state):
        if not isinstance(state,dict):raise ValueError("INVALID_RISK_AGGREGATOR_STATE")
        loaded={}
        for name in BUCKETS:
            value=state.get(name,{})
            if not isinstance(value,dict):raise ValueError("INVALID_RISK_AGGREGATOR_STATE")
            loaded[name]={str(k):dict(v) for k,v in value.items() if isinstance(v,dict)}
        # تعديل في مكانه لا استبدال: الاستبدال بـ`setattr` كان يبدّل الكائن الذي
        # يمسكه المشترِك، فيبقى ٥٠٠ يعرض لقطة الإقلاع أبدًا.  مقيس ٢٠٢٦-٠٩-٠٩:
        # ٤٫٩ يوم من العمى — `open_trade_count=0` والواقع 1، وفارق ٨٢٨ دولارًا
        # في `equity` — وشارته خضراء طوالها.
        for name in BUCKETS:
            bucket=getattr(self,"_"+name);bucket.clear();bucket.update(loaded[name])
    async def health_check(self):
        if not self._running:return HealthStatus(state=HealthState.UNHEALTHY,message="NOT_STARTED")
        idle=None if self._last_seen_mono is None else time.monotonic()-self._last_seen_mono
        d={"risk_accounts":len(self._risk),"seen":self._seen,"emitted":self._emitted,"authority":"516","idle_s":None if idle is None else round(idle,1)}
        if not self._risk:return HealthStatus(state=HealthState.DEGRADED,message="RISK_AUTHORITY_STATE_UNKNOWN",details=d)
        # حالة مستعادة بلا بثّ حيّ ليست حياة: هذه هي الحال التي كذبت ٤٫٩ يوم.
        if idle is None:return HealthStatus(state=HealthState.DEGRADED,message="RISK_STATE_RESTORED_AWAITING_LIVE_516",details=d)
        if idle>STALE_AFTER_S:return HealthStatus(state=HealthState.DEGRADED,message="RISK_STATE_STALE | idle_s=%d"%int(idle),details=d)
        return HealthStatus(state=HealthState.HEALTHY,message="aggregating_516_accounts=%d idle_s=%d"%(len(self._risk),int(idle)),details=d)