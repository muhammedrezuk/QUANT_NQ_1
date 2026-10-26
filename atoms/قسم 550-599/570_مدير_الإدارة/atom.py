from __future__ import annotations
import uuid
from typing import Any
from core.contracts.atom import AtomBase, AtomContext, HealthState, HealthStatus
from shared.broker_refusals import retryable as refusal_retryable

ATOM_VERSION = "3.4.0"
EVENT_INTENT="execution.manage.intent"
EVENT_VANISH="platform.position.vanished"
EVENT_OUT="execution.manage.command"
EVENT_WRITTEN="execution.manage.written"
EVENT_FAILED="execution.command.failed"
EVENT_ACK="execution.command.ack"
EVENT_PULSE="SYS_SECOND"
ACTIONS=("MODIFY_SL","CLOSE_PARTIAL","CLOSE")
BUY="BUY"
SELL="SELL"
MAX_RETRY_ATTEMPTS=3
#: 🔴 ٢٠٢٦-٠٩-١٩ (أمر المالك) — «إغلاق ماركت · ما بصير يتعذّر · يتنفّذ
#: إغلاق على أيّ سعر».
#:
#: فأمرُ الإغلاق لا يُسقَط بعد ثلاث محاولات كما يُسقَط تعديلُ وقف. والفرق
#: بينهما فرقُ ما يُفقد: تعديلُ وقفٍ ضائع يُعاد في المرحلة التالية، وإغلاقٌ
#: ضائع **يترك المال في السوق** — الجزءُ لا يُقبض وتمضي الصفقة إلى وقفها.
#:
#: والمهلُ تتضاعف (`2^attempt`) فتبلغ العشرون محاولةً نحو ساعة، ثمّ يُعلَن
#: الإسقاط ولا يُبتلع. ولا تُترك بلا حدّ: طابورٌ لا ينتهي يغرق الجسر،
#: والصفقةُ التي لا تُغلق في ساعةٍ لن تُغلق بإلحاح.
MAX_RETRY_CLOSE=20
_CLOSING=("CLOSE_PARTIAL","CLOSE")
# ٢٠٢٦-١٠-٠٢ (ختم المالك «صلح كامل nq»): الإعادة لا تقع إلّا على فشلٍ ثبت أنّه
# لم يُنفَّذ فيه شيء. صارت الإعادة حيّةً (معرّفٌ جديد لكلّ محاولة، انظر `_send`)،
# فإعادةُ ما قد نُفّذ تكرارُ أمرٍ على مالٍ حيّ — `RETCODE_10012` (مهلة) رُدّت
# أربع مرّات في ٠٩-٠٦ ونُفّذت كلّها، و`UNKNOWN_AFTER_CRASH` مجهول المصير.
# فالمقبول للإعادة نوعان لا ثالث لهما:
#   ١· ردُّ الجسر المؤكَّد العابر — قائمته الواحدة في `shared/broker_refusals.py`
#      (`STALE_*` · `NO_POSITION` · `BROKER_DISCONNECTED` · 10004 · 10018 · 10029 …).
#   ٢· رفضُ ٥٧٥ قبل أن يكتب صفًّا للمحاولة، وهو عابرٌ بطبعه: لا صفّ في الجسر
#      فلا شيء يُنفَّذ مرّتين.
# و`DUPLICATE_REQUEST_ID` ليس منهما: معناه أنّ المحاولة نفسها في الجسر فعلًا.
_UNWRITTEN_TRANSIENT=("OFFICIAL_TIME_UNAVAILABLE","POSITION_OWNERSHIP_MISMATCH",
                      "database is locked","database table is locked")

def may_retry(reason:Any)->bool:
    text=str(reason or "").strip()
    return refusal_retryable(text) or text in _UNWRITTEN_TRANSIENT

def number(v:Any)->float|None:
    try:r=float(v)
    except (TypeError,ValueError):return None
    return r if r==r else None

class Atom(AtomBase):
    def __init__(self):self._context=None;self._running=False;self._state={};self._pending={};self._seen=0;self._commands=0;self._dropped=0;self._counter=0;self._close_abandoned=0;self._last_abandoned="";self._now=0.;self._failed=0;self._magic=20260801;self._retries=0
    async def initialize(self,c):
        self._context=c
        self._magic=int(c.config.get("magic",20260801))
        c.subscribe(EVENT_INTENT,self._on_intent)
        c.subscribe(EVENT_VANISH,self._on_vanish)
        c.subscribe(EVENT_WRITTEN,self._on_written)
        c.subscribe(EVENT_FAILED,self._on_failed)
        c.subscribe(EVENT_ACK,self._on_ack)
        c.subscribe(EVENT_PULSE,self._on_pulse)
    async def start(self):self._running=True
    async def stop(self):self._running=False
    async def shutdown(self):await self.stop()
    async def _on_vanish(self,p):
        if not self._running or not isinstance(p,dict):return
        ticket=str(p.get("ticket") or "")
        account=str(p.get("account_id") or "")
        key=account+"|"+ticket
        self._state.pop(key,None)
        for rid,row in list(self._pending.items()):
            if row["key"]==key:self._pending.pop(rid,None)
    def _st(self,key,side):return self._state.setdefault(key,{"side":side,"best_sl":None,"partials":0,"closed":False})
    def _find(self,rid):
        # ٢٠٢٦-١٠-٠٢ (ختم المالك «صلح كامل nq»): الردّ يحمل معرّف المحاولة
        # (`<rid>-aN`)، والصفّ محفوظٌ بمعرّفه الأصل — فيُردّ إليه من أيّ محاولة.
        row=self._pending.get(rid)
        if row is not None:return rid,row
        for root,row in self._pending.items():
            if rid in row["attempt_ids"]:return root,row
        return rid,None
    async def _send(self,rid,row):
        if self._context is None:return
        row["attempts"]+=1
        # ٢٠٢٦-١٠-٠٢ (ختم المالك «صلح كامل nq»): كلُّ محاولةٍ بمعرّفٍ جديد.
        # كانت الإعادة بالمعرّف نفسه، و٥٧٥ يردّ كلَّ معرّفٍ في جدول الجسر
        # الدائم مهما كانت حالته `DUPLICATE_REQUEST_ID` — فلم تبلغ إعادةٌ واحدة
        # الوسيط. مقيس: US500 تذكرة 1977026413، الجزء الأوّل 2.8 لوت ختمه الإكسبرت
        # `STALE_2s` (09-30 17:47:36 UTC) ثمّ ردّ ٥٧٥ إعادته مكرّرةً بمهلٍ
        # 4·9·19·31·64… حتى ضُرب الوقف كاملًا (18:33:44) بـ−94.35$.
        # فالمحاولة الأولى بالمعرّف الأصل كما كانت، وكلّ إعادةٍ `<rid>-aN` (نمط
        # ٥٧٩ القائم `-a%d`)، والأصل يُحمل في `parent_request_id` أثرًا. وحارس
        # ٥٧٥ يبقى قاطعًا كما هو: يردّ المحاولةَ الواحدة إن تكرّرت حقًّا.
        attempt_id=rid if row["attempts"]==1 else "%s-a%d"%(rid,row["attempts"])
        row["attempt_id"]=attempt_id
        row["attempt_ids"].append(attempt_id)
        row["last_at"]=self._now
        row["status"]="EMITTED"
        self._commands+=1
        if row["attempts"]>1:self._retries+=1
        await self._context.publish(EVENT_OUT,dict(row["command"],request_id=attempt_id,parent_request_id=rid,attempt=row["attempts"]))
    def _abandon(self,rid,row,why):
        self._pending.pop(rid,None);self._dropped+=1
        if row["action"] in _CLOSING:
            self._close_abandoned+=1
            self._last_abandoned="%s %s بعد %d محاولة (%s)"%(row["command"].get("symbol"),row["action"],row["attempts"],why)
            if self._context is not None:
                self._context.logger.error(
                    "570 🔴 أمرُ إغلاقٍ سقط بعد %d محاولة (%s): %s تذكرة=%s "
                    "— المال باقٍ في السوق",row["attempts"],why,
                    row["command"].get("symbol"),row["command"].get("ticket"))
    async def _on_intent(self,p):
        if not self._running or self._context is None or not isinstance(p,dict):return
        self._seen+=1
        ticket=p.get("ticket")
        action=str(p.get("action") or "")
        side=str(p.get("side") or "")
        account=str(p.get("account_id") or "")
        if ticket in (None,"",0) or not account or side not in (BUY,SELL) or action not in ACTIONS:self._dropped+=1;return
        key=account+"|"+str(ticket)
        st=self._st(key,side)
        if st["closed"]:self._dropped+=1;return
        signature=(key,action)
        if any(row["signature"]==signature for row in self._pending.values()):return
        command={"account_id":account,"magic":self._magic,"ticket":ticket,"symbol":str(p.get("symbol") or ""),"side":side,"action":action,"reason":str(p.get("reason") or "")}
        if action=="MODIFY_SL":
            value=number(p.get("stop_loss"))
            best=st["best_sl"]
            if value is None or value<=0 or (best is not None and not ((side==BUY and value>best) or (side==SELL and value<best))):self._dropped+=1;return
            command["stop_loss"]=value
        elif action=="CLOSE_PARTIAL":
            # 🔴 ٢٠٢٦-٠٩-١٩ (شكوى المالك «هدف ثاني ما سكّر جزء منه»)
            #
            # كان الشرط `or st["partialed"]` — عَلَمٌ يصير `True` بعد أوّل
            # إغلاقٍ جزئيٍّ مُقَرّ، فيُسقط كلَّ إغلاقٍ جزئيٍّ بعده **بصمت**
            # (`_dropped`). أي أنّ الذرّة تسمح بجزءٍ واحدٍ لكلّ صفقة.
            #
            # وخطّة المالك فيها **جزآن**: ثلثٌ عند الهدف الأوّل، ونصفُ
            # الباقي عند الثاني. فالمرحلة الثانية كانت تموت هنا قبل أن
            # تبلغ الجسر — ومقيسٌ على التذكرة 1945036903:
            #
            #   18:41:09  إغلاق 0.33  ✔  ثمّ 18:41:58 تعديلُ وقفٍ ✔
            #   والإغلاق الثاني لم يخرج أصلًا: `570 commands_emitted=3`
            #   — أمرَا وقفٍ وإغلاقٌ واحد، لا اثنان.
            #
            # فيظهر الأثرُ مربكًا: الوقف يتحرّك إلى مرحلته الثانية والجزء
            # لا يُغلق، فيبدو كأنّ الوسيط ردّ أمرًا — ولم يصله أمرٌ قطّ.
            #
            # ولا يُترك البابُ بلا حارس: `signature` أعلاه يمنع أمرين
            # معلّقين بالفعل نفسه على الصفقة نفسها، و٥٧٤ يحكم المراحل ولا
            # يعيد مرحلةً بلغها. وهذه الذرّة ناقلٌ لا حاكم، فلا تحبس
            # خطّةً ليست لها.
            value=number(p.get("volume"))
            if value is None or value<=0:self._dropped+=1;return
            command["volume"]=value
        # 🔴 ٢٠٢٦-٠٩-١٩ — لاحقةٌ تعود إلى الخلف تقتل الإغلاق الجزئيّ.
        #
        # كان `self._counter` يبدأ من صفرٍ مع كلّ إعادة بناءٍ للذرّة، وجدول
        # `commands` الذي يفحص التكرار **دائم**. فبعد إعادة بناءٍ تُولَّد
        # لواحقُ سبق استعمالها ويردّها الوسيط `DUPLICATE_REQUEST_ID` —
        # وليس ردًّا خاطئًا منه: الحارس يعمل صوابًا على معرّفٍ كرّرناه.
        #
        # ومقيسٌ على التذكرة 1945019317 (أوّل صفقة اليوم، لوت 1 على بتكوين):
        #   18:04:00  إغلاق 0.33  ✔ بالمعرّف ‎-2‎      ⟵ الهدف الأوّل نجح
        #   18:05:55  إغلاق 0.22  ✗ بالمعرّف ‎-1‎      ⟵ الثاني، واللاحقة رجعت
        #   18:05:58 · 18:06:03 · 18:16:10 · 18:16:12 · 18:16:17  ✗ كلُّها
        # فبقي المركز على ‎0.67‎ لوت ولم يُغلق نصفُه عند الهدف الثاني — وهو
        # نصُّ خطّة المالك: «انتقل ستوب من تأمين إلى هدف أوّل وأُغلق جزء».
        #
        # والعلّةُ نفسها أُصلحت في ٥٧٥ باستئنافٍ من `MAX(id)` ولم تُصلَح هنا،
        # و**هنا يُبنى المعرّف** — فإصلاحُ الجار لم يكن يُستعمل أصلًا.
        # [[twin-gates-fix-one-forget-the-other]]
        #
        # والدواءُ تفرّدٌ بنيويّ لا ساعة. جرّبتُ الساعةَ ثلاث مرّات وأسقطها
        # القياسُ ثلاثًا: عدّادٌ أساسُه الثانية (تقاطع بعد ثلاثة أوامر)،
        # ثمّ `max` بينه وبين الميلي‑ثانية (دفعةُ ٢٠٠٠ أمرٍ تسبق الساعة
        # بثانيتين فترجع)، ثمّ حِقبةٌ بالميلي مع عدّادٍ داخلها (إعادةُ بناءٍ
        # في الميلي‑ثانية نفسها تُعيد الحِقبة نفسها والعدّاد من واحد).
        # وكلُّ ترقيعٍ زمنيٍّ يؤخّر التصادم ولا يمنعه.
        #
        # و`uuid4` نمطٌ قائمٌ في المشروع لهذا الغرض بعينه — ٥٥٥ يبني
        # معرّفه به (`555-<hex12>`) — فأتّبعه ولا أخترع. والتفرّد مضمونٌ
        # بلا حالةٍ تُحفظ ولا قاعدةٍ تُقرأ ولا ساعةٍ يُوثق بها.
        #
        # ٢٠٢٦-١٠-٠٢ (ختم المالك «صلح كامل nq»): كان هنا «والإعادةُ تبقى
        # بالمعرّف نفسه» — وهي التي قتلت الإعادة (٥٧٥ يردّها مكرّرة). المعرّف
        # الأصل يُبنى مرّةً هنا ويُخزَّن في `_pending`، وكلُّ إعادةٍ تأخذ لاحقة
        # محاولتها في `_send`؛ فحارس التكرار يبقى قاطعًا على المحاولة الواحدة.
        self._counter+=1
        rid=str(p.get("request_id") or "manage-%s-%s-%s"%(account,ticket,uuid.uuid4().hex[:12]))
        row={"key":key,"signature":signature,"action":action,"side":side,"command":command,"attempts":0,"last_at":0.,"status":"NEW","attempt_id":"","attempt_ids":[]}
        self._pending[rid]=row
        await self._send(rid,row)
    async def _on_written(self,p):
        if not self._running or not isinstance(p,dict):return
        rid=str(p.get("request_id") or "")
        root,row=self._find(rid)
        if row is not None and rid==row["attempt_id"]:row["status"]="QUEUED_TO_BRIDGE"
    async def _on_ack(self,p):
        if not self._running or not isinstance(p,dict):return
        rid=str(p.get("request_id") or p.get("command_id") or "")
        # ٢٠٢٦-١٠-٠٢: تأكيدُ أيّ محاولةٍ من محاولات الأمر يُتمّه — التنفيذ وقع.
        root,row=self._find(rid)
        if row is None:return
        self._pending.pop(root,None)
        st=self._st(row["key"],row["side"])
        action=row["action"]
        if action=="MODIFY_SL":st["best_sl"]=row["command"]["stop_loss"]
        elif action=="CLOSE_PARTIAL":st["partials"]=st.get("partials",0)+1
        elif action=="CLOSE":st["closed"]=True
    async def _on_failed(self,p):
        if not self._running or not isinstance(p,dict):return
        rid=str(p.get("request_id") or "")
        root,row=self._find(rid)
        if row is None:return
        # ٢٠٢٦-١٠-٠٢ (ختم المالك «صلح كامل nq»): لا إعادة والمحاولة الجارية
        # في الجسر بعد. الفشل يُقبل من المحاولة الجارية وحدها وهي خارجة
        # (`EMITTED`/`QUEUED_TO_BRIDGE`)، وناشراه اثنان لا ثالث لهما: ٦٠١ ولا ينشر
        # إلّا صفًّا خُتم (`done_at` قائم ⟸ لا `PENDING` ولا `TAKEN`)، و٥٧٥ ولا ينشره
        # إلّا حين لم يكتب للمحاولة صفًّا. وفشلُ محاولةٍ سابقة يصل متأخّرًا لا يُطلق
        # إعادةً فوق محاولةٍ لاحقة ما زالت في الطريق.
        if rid!=row["attempt_id"] or row["status"] not in ("EMITTED","QUEUED_TO_BRIDGE"):return
        self._failed+=1
        reason=str(p.get("reason") or "")
        if not may_retry(reason):
            self._abandon(root,row,"لا يُعاد: %s"%(reason or "بلا سبب"))
            return
        row["status"]="RETRY"
    async def _on_pulse(self,p):
        if not self._running or not isinstance(p,dict):return
        try:self._now=float(p.get("official_time"))
        except (TypeError,ValueError):return
        for rid,row in list(self._pending.items()):
            # حدُّ المحاولات بحسب ما يُفقد: الإغلاق لا يُسقَط كما يُسقَط الوقف.
            cap=MAX_RETRY_CLOSE if row["action"] in _CLOSING else MAX_RETRY_ATTEMPTS
            # والمهلة تتضاعف ولا تتجاوز خمس دقائق، وإلّا بلغت أيّامًا عند
            # المحاولة العشرين (`2^20` ثانية = اثنا عشر يومًا).
            wait=min(2**row["attempts"],300)
            if row["status"]=="RETRY" and row["attempts"]<cap and self._now-row["last_at"]>=wait:await self._send(rid,row)
            elif row["status"]=="RETRY" and row["attempts"]>=cap:self._abandon(rid,row,"نفد الحدّ")
    async def health_check(self):
        if not self._running:return HealthStatus(state=HealthState.UNHEALTHY,message="NOT_STARTED")
        d={"tracked":len(self._state),"pending":len(self._pending),"seen":self._seen,"commands_emitted":self._commands,"failed":self._failed,"dropped":self._dropped,
           "retries":self._retries,"close_abandoned":self._close_abandoned,"last_abandoned":self._last_abandoned,
           "partials_per_ticket":{k:v.get("partials",0) for k,v in self._state.items() if v.get("partials")}}
        # ٢٠٢٦-٠٩-١٩ — كانت الشارة تحمل عدّادين، و`dropped` و`failed` في
        # `details` التي تحذفها النواة. فالإغلاق الجزئيّ الثاني كان يُسقط
        # هنا بصمتٍ تامّ ولا يظهر في شاشة: يتحرّك الوقف ولا يُغلق الجزء،
        # فيُظنّ الردُّ من الوسيط وهو لم يصله أمرٌ قطّ.
        parts=" ".join("%s×%d"%(k.split("|")[-1],v.get("partials",0))
                       for k,v in sorted(self._state.items()) if v.get("partials"))
        # ٢٠٢٦-١٠-٠٢: عدّاد الإعادات في الشارة — دليلُ نفاذ الإصلاح حيًّا.
        line="أُصدر=%d معلّق=%d%s%s%s%s"%(
            self._commands,len(self._pending),
            " ⚠ فشل=%d"%self._failed if self._failed else "",
            " ↻ أُعيد=%d"%self._retries if self._retries else "",
            " 🔴 أُسقط=%d"%self._dropped if self._dropped else "",
            " | أجزاء مُقَرّة: %s"%parts if parts else "")
        if any(r["status"]=="RETRY" for r in self._pending.values()):
            return HealthStatus(state=HealthState.DEGRADED,message=line,details=d)
        if not self._seen:
            return HealthStatus(state=HealthState.HEALTHY,
                                message="READY_AWAITING_FIRST_MANAGE_INTENT | "+line,details=d)
        return HealthStatus(state=HealthState.HEALTHY,message=line,details=d)
