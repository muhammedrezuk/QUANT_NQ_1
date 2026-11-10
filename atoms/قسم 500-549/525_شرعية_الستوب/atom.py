from __future__ import annotations
import math
import time
from typing import Any
from core.contracts.atom import AtomBase, AtomContext, HealthState, HealthStatus
from shared import execution_costs


def _rejection(payload: dict, reason: str) -> dict:
    """حقل الرفض كما يقرؤه مخزن القرارات ٧٠٧.

    ٢٠٢٦-٠٩-١٦ — مقيس: **٤٬٤٠٥ صفّ `ORDER_REJECTED` وكلّها
    `rejection_reason = NULL`**، منها ٣٬٠٨٤ لبتكوين. و٧٠٧ يقرأ السبب من
    `payload["rejection"]["reason"]` (سطر ٦٦٦) لا من الجذر — فالعمود
    المخصّص للسبب يبقى فارغًا بينما السبب بجانبه في عمود `reason`.
    نفس عائلة `decision_side`/`side` التي كلّفت عشرة قرارات في ٠٩-٠٩.

    والشكل منسوخ من ناشره الأصليّ ٤٦٦ (سطر ١٤٤) لا مخترَعًا. إضافة خالصة:
    ما كان يُنشر يبقى كما هو، ويُضاف هذا بجانبه.
    """
    return {"reason": reason, "stage": "STOP_LEGALITY", "value": None,
            "threshold": None, "time": time.time(),
            "decision_id": payload.get("decision_id")}


ATOM_VERSION = "2.5.0"
# أرضية ضجيج وقف التنفيذ — مقيسة لا مقدَّرة: زمن العبور 410→581 قِيس
# 0.3–0.83s، وتوزيع الحركة المعاكسة على 257 إعدادًا من 60 ألف تِكّة
# أعطى P95=10.69 وP99=16.57 عند صفّ الثانية. 0.000225 ≈ 18$ على 80,000.
#: ⛔ لم يعد مستعمَلًا — أُبدل بحدٍّ مشتقٍّ لكلّ رمز
#: (`shared/execution_costs.py`). يبقى مكتوبًا ليُعرف ما كان.
EXECUTION_NOISE_FRAC = 0.000225
EVENT_BUILT = "execution.order.built"
EVENT_SPECS = "market.symbol_specs"
EVENT_LEGAL = "execution.order.legal"
EVENT_REJECTED = "execution.order.rejected"
OPEN = "OPEN"
BUY = "BUY"
SELL = "SELL"
EPS = 1e-12
DEFAULT_STEP = 0.01


def num(v: Any) -> float | None:
    try: r = float(v)
    except (TypeError, ValueError): return None
    return r if r == r else None


class Atom(AtomBase):
    def __init__(self) -> None:
        self._context=None
        self._running=False
        self._specs={}
        self._buffer=0.0
        self._reward=2.0
        self._seen=0
        self._legal=0
        self._rejected=0
        self._spec_from_order=0
        self._hard_floor_points=0.0
        self._symbol_floor={}
        self._floor_rejected=0
        self._last_floor=""
        # 📢 ٢٠٢٦-٠٩-١٩ — الحدّ الفعليّ المطبَّق لكل رمز، يُعلَن في الشارة.
        #
        # سنده مقيس: الأمر الوحيد الذي خرج اليوم (BTCUSD SELL) حمل وقفًا
        # 1.88 ورُفض دون 19.41 — لأنّ المنبع لا يعرف الرقم. والشارة كانت
        # تُعلن أرضيّات المالك الثلاث وحدها، والبتكوين ليس فيها: حدُّه
        # **مشتقٌّ** من تكلفة عبوره لا منصوصٌ عليه، فبقي غير منظور.
        #
        # ولا يُنسخ الجدول إلى ذرّات التحليل: رقمٌ واحد في مكانين ينحرف،
        # وحين ينحرف تصير حقيقتان وإحداهما تكذب صامتة. فيُعلَن من موضع
        # إنفاذه وحده — هنا — ويُقرأ.
        self._effective_floor={}

    async def initialize(self, context: AtomContext) -> None:
        self._context=context
        cfg=context.config
        self._buffer=float(cfg.get("stop_buffer",0.0))
        self._reward=float(cfg.get("reward_risk",2.0))
        self._hard_floor_points=float(cfg.get("hard_floor_points",0.0))
        raw=cfg.get("stop_floor_by_symbol") or {}
        self._symbol_floor={str(k).strip().upper():float(v)
                            for k,v in raw.items() if num(v) is not None and float(v)>0.0}
        context.subscribe(EVENT_BUILT,self._on_built)
        context.subscribe(EVENT_SPECS,self._on_specs)
    async def start(self): self._running=True
    async def stop(self): self._running=False
    async def shutdown(self): await self.stop()

    async def _on_specs(self,payload):
        if not self._running or not isinstance(payload,dict): return
        for row in payload.get("symbols",[]) if isinstance(payload.get("symbols"),list) else []:
            if isinstance(row,dict) and row.get("symbol"):
                account = str(row.get("account_id") or payload.get("account_id") or "")
                if account: self._specs[account + "\x1f" + str(row["symbol"])] = dict(row)

    # 🔴 ٢٠٢٦-٠٩-٢٣ (ختم `nq`) — إزالة منظومة الهيدج. كان الشكلان أدناه
    # استثناءين: ساقُ الزوج المحايد تعبر بلا وقفٍ ولا هدف، والرِّجل الدائمة
    # بلا هدف. ومنتِجاهما (٥٧٦/٥٧٨) في الأرشيف، فبقيا بابين بلا صاحب.
    # صار الشكلُ سببَ رفضٍ مسمّى، وكلُّ فتحٍ يُحاكَم بالوقف والهدف معًا.
    def _neutral(self,o):
        return str(o.get("action") or OPEN).upper()==OPEN and str(o.get("protection_mode") or "").upper()=="NEUTRAL_HEDGE"

    def _perpetual(self,o):
        return (str(o.get("action") or OPEN).upper()==OPEN
                and (str(o.get("protection_mode") or "").upper()=="PERPETUAL_BUDGET"
                     or str(o.get("origin") or "")=="perpetual-delta"))

    @staticmethod
    def _payload_spec(payload,symbol):
        """المواصفة المرافقة للأمر نفسه — ٥٥١ يمرّرها في `symbol_spec`.

        خريطة `_specs` تُملأ من دورة ٦١٨ كل ٣٠٠ ثانية وتُمسح مع كل إعادة
        تحميل ساخنة، فتبقى الذرّة عمياء حتى الدورة التالية.  مقيس ٢٠٢٦-٠٩-١٠:
        `legal=0 rejected=19` ثمّ قفز `legal` إلى ١١ في الدقيقة التي وصلت
        فيها الدورة — والأمر المرفوض كان يحمل `symbol_spec` كاملًا في يده
        طوال الوقت (contract_size · tick_size · point · stops_level ·
        freeze_level · volume_min/max/step).  ٣٤٧ رفضًا بـ`NO_SYMBOL_SPECS`
        فوق مواصفةٍ حاضرة.

        الخريطة تبقى المصدر الأوّل لأنّها قد تكون أحدث؛ وهذه شبكة الأمان.
        ولا تُقبل مواصفة رمزٍ آخر: المطابقة بالاسم شرط.
        """
        spec=payload.get("symbol_spec")
        if not isinstance(spec,dict): return None
        if str(spec.get("symbol") or "")!=symbol: return None
        return spec

    def _round_volume(self, volume, spec):
        step=num(spec.get("volume_step")) or DEFAULT_STEP
        minimum=num(spec.get("volume_min")) or step
        maximum=num(spec.get("volume_max"))
        value=math.floor(max(0.0,volume)/step+EPS)*step
        if value + EPS < minimum: return 0.0
        return min(maximum,value) if maximum else value

    async def _on_built(self,payload):
        if not self._running or self._context is None or not isinstance(payload,dict): return
        self._seen+=1
        action=str(payload.get("action") or OPEN).upper()
        if action != OPEN:
            self._legal+=1
            await self._context.publish(EVENT_LEGAL,dict(payload))
            return
        neutral=self._neutral(payload)
        perpetual=self._perpetual(payload)
        account=str(payload.get("account_id") or "")
        symbol=str(payload.get("symbol") or "")
        side=str(payload.get("side") or "").upper()
        ref=num(payload.get("reference_price"))
        sl=num(payload.get("stop_loss"))
        tp=num(payload.get("take_profit"))
        volume=num(payload.get("volume"))
        spec=self._specs.get(account+"\x1f"+symbol)
        if spec is None:
            spec=self._payload_spec(payload,symbol)
            if spec is not None: self._spec_from_order+=1
        reason=""
        if neutral: reason="NEUTRAL_HEDGE_REMOVED"
        elif perpetual: reason="PERPETUAL_REMOVED"
        elif not account or not symbol or side not in (BUY,SELL): reason="BAD_ACCOUNT_SYMBOL_OR_SIDE"
        elif spec is None: reason="NO_SYMBOL_SPECS"
        elif ref is None or ref<=0 or volume is None or volume<=0: reason="INCOMPLETE_ORDER"
        if not reason:
            rounded=self._round_volume(volume,spec)
            if rounded<=0: reason="VOLUME_BELOW_MINIMUM"
            elif num(spec.get("volume_max")) is not None and rounded>num(spec.get("volume_max")): reason="VOLUME_ABOVE_MAXIMUM"
            else: volume=rounded
        if reason:
            self._rejected+=1
            await self._context.publish(EVENT_REJECTED,{**payload,"reason":reason,"stage":"STOP_LEGALITY","rejection":_rejection(payload,reason)})
            return
        if sl is None or sl<=0: reason="INCOMPLETE_ORDER"
        elif tp is None or tp<=0: reason="INCOMPLETE_ORDER"
        elif side==BUY and not sl<ref<tp: reason="BUY_LEVELS"
        elif side==SELL and not tp<ref<sl: reason="SELL_LEVELS"
        if reason:
            self._rejected+=1
            await self._context.publish(EVENT_REJECTED,{**payload,"reason":reason,"stage":"STOP_LEGALITY","rejection":_rejection(payload,reason)})
            return
        point=num(spec.get("point")) or num(spec.get("tick_size")) or 0.0
        stops=num(spec.get("stops_level")) or 0.0
        freeze=num(spec.get("freeze_level")) or 0.0
        # 🔴 ٢٠٢٦-٠٩-١٩ (أمر المالك) — «ولا أرضيّة لأيّ زوج، احذفها».
        #
        # يُحذف كلُّ حدٍّ أدنى **من عندنا**: أرضيّاتُه المنصوصة لكلّ رمز
        # (`stop_floor_by_symbol`)، وتكلفةُ العبور المقيسة
        # (`execution_costs.minimum_stop_distance`)، و`hard_floor_points`،
        # والوسادة. وينقض هذا أمرَه السابق ٢٠٢٦-٠٩-١٨ «لا وقف دون تكلفة
        # عبور رمزه المقيسة» — وهو حقُّه، وأحدثُ كلمتيه تعلو.
        #
        # ويبقى حدُّ الوسيط وحده (`stops_level`/`freeze_level`)، ولا يبقى
        # لأنّي أراه صوابًا بل لأنّه **ليس أرضيّةً منّا**: هو شرط قبولٍ عند
        # المنصّة، ووقفٌ دونه يردّه الوسيط نفسه فتضيع الصفقة عنده بدل أن
        # تُردّ عندي بسببٍ معلن. فحذفُه لا يُمرّر وقفًا أضيق، بل ينقل الردَّ
        # إلى حيث لا نراه.
        minimum_distance=max(stops,freeze)*point
        # ٢٠٢٦-٠٩-٠٧ (قرار المالك المعماريّ): حدّ الوسيط يمنع رفض المنصّة
        # ولا يقول شيئًا عن ضجيج السوق. الإبطال التحليليّ (≈4.5$) يعبّر عن
        # صلاحية الفكرة، ووقف التنفيذ يجب أن يتحمّل زمن العبور المقيس
        # (0.3–0.83s) وحركته المعاكسة — P99 ≈ 16.6$ عند صفّ الثانية.
        # فالتوسيع هنا وحده: الفكرة تعبر كما نطق بها مالكها، والحماية
        # تُبنى في طبقة التنفيذ. الرقم رقم اختبار حتى يُقاس P99 مباشرةً
        # على عيّنة العبور نفسها لا على صفّ الثانية.
        # ⚖️ ٢٠٢٦-٠٩-١٨ — حكم المالك: «مو الإكسبرت عم يزوّدك؟ بدك تخرج عن
        # الأصول». وكان الحدّ هنا `abs(ref) * 0.000225` — نسبةً عمياء واحدة
        # على السوق كلّه. ونسبةٌ واحدة من السعر ليست شيئًا واحدًا: تعطي
        # **3.4 أضعاف** سبريد البتكوين و**8.1 أضعاف** سبريد الذهب.
        #
        # الآن يُشتقّ لكلّ رمزٍ من سجلّ تنفيذه: السبريد من التِكّة، وانزلاق
        # الدخول والخروج عند المئين الثمانين من `decisions.db`. وللبتكوين
        # مثالًا: 5.00 + 11.54 + 6.74 = 18.27$ — وقفٌ أضيق منها يُضرَب
        # بتكلفة عبوره وحدها قبل أن يتحرّك السوق.
        #
        # ولا مضاعفَ فوق ذلك ولا «نقطة»: المضاعف رقمٌ من الرأس، والنقطة لا
        # مرجع لها — ميتاتريدر نفسه يعرض «قيمة النقطة: 0» لهذا الرمز.
        # ⛔ حُذف بأمر المالك ٢٠٢٦-٠٩-١٩ — كان هنا:
        #     minimum_distance = max(minimum_distance,
        #         execution_costs.minimum_stop_distance(symbol, ref, spread))
        # يبقى مكتوبًا ليُعرف ما كان، ولا يُنفَّذ. والدالّة باقيةٌ في
        # `shared/execution_costs.py` لمن يقيس بها، فالقياس غير الإنفاذ.
        # 🔴 ٢٠٢٦-٠٩-١٨ (ختم NQ) — أرضيّةُ كل رمزٍ بأمر المالك، بوحدة السعر:
        #
        #   «دهب ما في أقلّ من 2 دولار على حركة ستوب — دهب عنيف. وأيّ ستوب
        #    فوق 2 دولار تُفتح صفقة بلوتها الصحيح، وإذا خسرت تخسر 100
        #    دولار رسميّ.»
        #   «ناسداك: أيّ صفقة أقلّ من 15 دولار من حركة ناسداك تُرفض.»
        #   «يورو: أيّ صفقة أقلّ من 5 بيب تُرفض.»
        #
        # ورقمٌ واحدٌ بالنقاط لا يصلح لهذا: `hard_floor_points` كانت 200
        # تُضرب في `point`، و`point` هي `0.01` لخمسة رموز و`0.00001` لليورو
        # — فالرقم نفسه يعطي 220$ للّوت على الذهب و2.20$ على البتكوين،
        # واختلافُ أثره بين اليورو والبتكوين **سبعةٌ وستّون ضعفًا**. فصارت
        # الأرضيّة لكل رمزٍ بوحدة سعره، وتُصفَّر النقاط العمياء.
        # ⛔ وأرضيّةُ الرمز المنصوصة حُذفت معها — كان هنا:
        #     floor = self._symbol_floor.get(symbol)
        #     if floor: minimum_distance = max(minimum_distance, floor)
        # والجدول ما زال يُقرأ من المانيفست ويُعلَن في الشارة **بوصفه
        # معطَّلًا**، لا ليُنفَّذ: رقمٌ يُحذف بلا إعلانٍ يعود بعد أسبوع.
        # الرقم الحاكم الآن حدُّ الوسيط وحده — يُحفظ ليُقرأ من الشارة.
        name=str(symbol or "").strip().upper()
        if name:
            self._effective_floor[name]=minimum_distance
        requested_distance=abs(ref-sl)
        out=dict(payload)
        out["volume"]=volume
        # والوقف **لا يُوسَّع**: حكم المالك ٢٠٢٦-٠٩-١٨ «وقف لا يوسّع بهل
        # همجيّة · هي مصاري مو لعب» و«المرفوضة تُرفض ولا تُعدَّل». التوسيع
        # كان يمدّ الوقف ويقصّ الحجم ويترك الهدف، فتنقلب النسبة بعد أن
        # أجازها كلُّ حارسٍ فوق: مقيسًا على التذكرة 1943171698، بنى ٥٥١
        # وقف 0.36 وهدف 2.56 (1:7.1) فخرج وقف 2.20 وهدف 2.08 (1:0.945).
        if point>0 and requested_distance<minimum_distance-EPS:
            self._rejected+=1
            self._floor_rejected+=1
            self._last_floor="%s %s %.5f<%.5f" % (
                symbol,side,requested_distance,minimum_distance)
            if self._floor_rejected<=5:
                self._context.logger.warning(
                    "525 STOP_BELOW_FLOOR %s %s: مسافة الوقف %.5f دون "
                    "أرضيّة الرمز %.5f — يُرفض ولا يُوسَّع",
                    symbol,side,requested_distance,minimum_distance)
            await self._context.publish(EVENT_REJECTED,{**payload,"reason":"STOP_BELOW_FLOOR","stage":"STOP_LEGALITY","min_stop_distance":minimum_distance,"requested_distance":requested_distance,"rejection":_rejection(payload,"STOP_BELOW_FLOOR")})
            return
        out.update({"min_stop_distance":minimum_distance,"freeze_level":spec.get("freeze_level"),"stop_buffer":self._buffer})
        self._legal+=1
        await self._context.publish(EVENT_LEGAL,out)

    async def health_check(self):
        if not self._running:return HealthStatus(state=HealthState.UNHEALTHY,message="NOT_STARTED")
        # ٢٠٢٦-٠٩-١٨ — `details` تحذفها النواة، فما لا يسكن `message` لا يصل
        # اللوحة. وعدّادا الأرضيّة كانا مخفيّين: الحارس يرفض ولا يقول لماذا.
        d={"seen":self._seen,"legal":self._legal,"rejected":self._rejected,
           "specs":len(self._specs),"spec_from_order":self._spec_from_order,
           "floor_rejected":self._floor_rejected,"last_floor":self._last_floor,
           "symbol_floor":dict(self._symbol_floor),"stop_buffer":self._buffer,
           "reward_risk":self._reward,
           "effective_floor":dict(self._effective_floor)}
        floors=" ".join("%s=%g"%(s,v) for s,v in sorted(self._symbol_floor.items()))
        applied=" ".join("%s=%.5g"%(s,v)
                         for s,v in sorted(self._effective_floor.items()))
        if not self._seen:
            return HealthStatus(state=HealthState.HEALTHY,
                                message="READY_AWAITING_FIRST_ORDER_STOP_CHECK | legal=0 rejected=0 | أرضيّات: %s"%(floors or "—"),details=d)
        return HealthStatus(state=HealthState.HEALTHY,message="legal=%d rejected=%d دون_حدّ_الوسيط=%d %s | specs=%d from_order=%d | ⛔ الأرضيّات محذوفة بأمر المالك ٢٠٢٦-٠٩-١٩ (كانت: %s · وتكلفة العبور المقيسة) | الحدّ المطبَّق = حدّ الوسيط وحده: %s"%(self._legal,self._rejected,self._floor_rejected,self._last_floor or "-",len(self._specs),self._spec_from_order,floors or "—",applied or "—"),details=d)
