from __future__ import annotations
import time
from typing import Any
from core.contracts.atom import AtomBase, AtomContext, HealthState, HealthStatus
from shared.financial_truth import FinancialTruth, bind_truth

ATOM_VERSION="1.5.0"
# ٢٠٢٦-٠٩-١٨ — الحجز يُحرَّر بحدثٍ يحمل `request_id` بعينه (حكمُ ٥١٦ أو
# رفضٌ أو صفقة). وأمرٌ مات مع إقلاعٍ لا يصله حدثٌ أبدًا، فحجزُه خالد:
# المقيس ٢٥ حجزًا = ‎304.79$‎ من هامش حسابٍ رصيدُه ‎8,367.75$‎، وكلّ
# إقلاعٍ يضيف ولا يطرح. فيُعطى الحجز عمرًا. والقيمة مشتقّة لا مخترَعة:
# دورةُ طلبِ ٥٥٥ دقيقتان، والحسم يتمّ في ثوانٍ — فخمس عشرة دقيقة
# سبعُ دوراتِ طلبٍ كاملة، أوسعُ بكثير من أيّ حسمٍ حيّ.
HOLD_TTL_DEFAULT=900.0
EVENT_ORDER="execution.order.resolved"
EVENT_ACCOUNT="platform.account.state"
EVENT_SPECS="market.symbol_specs"
EVENT_OUT="risk.margin.validation.completed"
EVENT_VERDICT="risk.validation.completed"
EVENT_REJECTED="execution.order.rejected"
EVENT_CMD_FAILED="execution.command.failed"
EVENT_TRADE="platform.trade_event"
EVENT_SHORTAGE="financial.truth.shortage"
OPEN="OPEN"

# ٢٠٢٦-١٠-٠٢ (ختم المالك «صلح كامل nq»): الهامش بمعادلة ميتاتريدر لكلّ وضعِ حسابٍ للرمز.
#
# كان: `margin_initial` يُضرب في الحجم مباشرةً، وإن كان صفرًا فـ`الحجم×العقد×السعر÷رافعة الحساب`.
# والجسر الحيّ (`symbol_specs_v2`) يقول: المؤشّرات والبتكوين `calc_mode=2` (CFD) و`margin_initial=0`،
# فقُسمت على رافعة الحساب 1:5000 وهي لا تدخل معادلة CFD أصلًا ⟸ USTEC 31.2 لوت قُدّرت 189$
# والوسيط طلب 4,725$؛ واليورو والذهب `calc_mode=0` (FOREX) و`margin_initial` = 100000 و100 —
# وهو عند ميتاتريدر **بديلُ حجم العقد** يُقسم على الرافعة، لا مبلغٌ بالدولار ⟸ اليورو 0.01 لوت
# قُدّر 1000$ فرُدّ دائمًا، والذهب نصفَ هامشه. المقيس: 48 أمرًا بلغت الوسيط فردّها `RETCODE_10019`.
#
# المعادلات (وثائق ميتاتريدر `ENUM_SYMBOL_CALC_MODE`؛ والأرقام كما في وحدة MetaTrader5 المضمّنة
# `vendor/python/runtime/Lib/site-packages/MetaTrader5/__init__.py:130-143`)، للّوت الواحد:
#   0 FOREX              ContractSize ÷ Leverage × Rate          (بعملة الهامش)
#   5 FOREX_NO_LEVERAGE  ContractSize × Rate                     (بعملة الهامش)
#   1 FUTURES            InitialMargin × Rate
#   2 CFD                ContractSize × MarketPrice × Rate        (بلا رافعة الحساب)
#   3 CFDINDEX           ContractSize × MarketPrice × TickValue ÷ TickSize × Rate
#   4 CFDLEVERAGE        ContractSize × MarketPrice ÷ Leverage × Rate
# وفي FOREX/FOREX_NO_LEVERAGE: `margin_initial` إن كان موجبًا يحلّ محلّ ContractSize (هكذا يُقرأ
# عند الوسيط: 100000 لليورو و100 للذهب = حجم العقد نفسه). وأوضاع البورصة (32 فما فوق) لا تُحسب
# هنا فتُرفض باسمها. والفحص على الهامش **الابتدائيّ** — `margin_maintenance` صفرٌ لكلّ الرموز في
# الجسر ولا يدخل فحص الدخول.
CALC_FOREX=0
CALC_FUTURES=1
CALC_CFD=2
CALC_CFDINDEX=3
CALC_CFDLEVERAGE=4
CALC_FOREX_NO_LEVERAGE=5
# Rate معدّلُ الهامش الابتدائيّ للرمز عند الوسيط (`SymbolInfoMarginRate`)، والإكسبرت لا يكتبه.
# فهو هنا **مقيسٌ لا مخترَع**: الهامشُ الذي حجزه الوسيط فعلًا ÷ المعادلة بمعدّل 1، كلّما كانت
# المراكز المفتوحة كلّها على رمزٍ واحد — من سجلّ المحفظة `forex_runtime/var/store/portfolio.db`
# (هامش 655 مع مراكز 659، 09-05 ⟶ 10-02، وسيط IC Markets «Raw Trading Ltd»، حساب 52992818):
#   USTEC 0.005 (261 عيّنة) · US30 0.005 (244) · US500 0.005 (80) · BTCUSD 0.002 (1,473)
#   XAUUSD 2.5 (1,441) · EURUSD 1.0 (264)
# الوسيط يرفع المعدّل عشرةَ أضعاف قرب إغلاق الجمعة وافتتاح الأحد (ذهب 25 وبتكوين 0.017 في عيّنات
# قليلة) — وذاك الطور لا يُرى قبل الأمر، فيردّه الوسيط حينها. ورمزٌ بلا قياس (GBPUSD لم يُتداول
# قطّ) أو وسيطٌ آخر ⟸ `MARGIN_RATE_UNKNOWN`: لا يُعار معدّل رمزٍ لرمز. والرقم الذي يُقدَّم على كلّ
# هذا رقمُ الوسيط نفسه للّوت (`margin_per_volume`) متى كتبه الإكسبرت.
MARGIN_RATE_MEASURED={
    ("Raw Trading Ltd","USTEC"):0.005,("Raw Trading Ltd","US30"):0.005,
    ("Raw Trading Ltd","US500"):0.005,("Raw Trading Ltd","BTCUSD"):0.002,
    ("Raw Trading Ltd","XAUUSD"):2.5,("Raw Trading Ltd","EURUSD"):1.0}

def num(v:Any)->float|None:
    try:r=float(v)
    except (TypeError,ValueError):return None
    return r if r==r else None

def key(a,s):return str(a or "")+"\x1f"+str(s or "")

def margin_per_lot(spec:dict,price:float|None,leverage:float|None,account_currency:str,rate:float|None)->tuple[float|None,str]:
    """هامشُ لوتٍ واحد بعملة الحساب بمعادلة ميتاتريدر، أو (None، السبب). لا يُكمَل مدخلٌ غائب."""
    mode=num(spec.get("calc_mode"))
    if mode not in (CALC_FOREX,CALC_FUTURES,CALC_CFD,CALC_CFDINDEX,CALC_CFDLEVERAGE,CALC_FOREX_NO_LEVERAGE):
        return None,"MARGIN_CALC_MODE_UNSUPPORTED"
    if rate is None or rate<=0:return None,"MARGIN_RATE_UNKNOWN"
    cs=num(spec.get("contract_size"));initial=num(spec.get("margin_initial"))
    margin_ccy=str(spec.get("currency_margin") or "");profit_ccy=str(spec.get("currency_profit") or "")
    ccy=str(account_currency or "")
    if mode in (CALC_FOREX,CALC_FOREX_NO_LEVERAGE,CALC_FUTURES):
        if mode==CALC_FUTURES:
            if initial is None or initial<=0:return None,"MARGIN_PER_VOLUME_MISSING"
            raw=initial*rate
        else:
            size=initial if initial is not None and initial>0 else cs
            if size is None or size<=0:return None,"MARGIN_PER_VOLUME_MISSING"
            if mode==CALC_FOREX:
                if leverage is None or leverage<=0:return None,"MARGIN_PER_VOLUME_MISSING"
                raw=size/leverage*rate
            else:raw=size*rate
        # بعملة الهامش ⟸ عملة الحساب: كما هي إن تطابقتا، وبسعر الرمز إن كانت عملةُ ربحه عملةَ الحساب.
        if ccy and margin_ccy==ccy:return raw,""
        if ccy and profit_ccy==ccy and price is not None and price>0:return raw*price,""
        return None,"MARGIN_PER_VOLUME_MISSING"
    if price is None or price<=0 or cs is None or cs<=0:return None,"MARGIN_PER_VOLUME_MISSING"
    raw=cs*price*rate
    if mode==CALC_CFDINDEX:
        tv=num(spec.get("tick_value"));ts=num(spec.get("tick_size"))
        if tv is None or ts is None or tv<=0 or ts<=0:return None,"MARGIN_PER_VOLUME_MISSING"
        raw=raw*tv/ts
    elif mode==CALC_CFDLEVERAGE:
        if leverage is None or leverage<=0:return None,"MARGIN_PER_VOLUME_MISSING"
        raw=raw/leverage
    # السعر بعملة الربح، فالناتج بها.
    if ccy and profit_ccy==ccy:return raw,""
    return None,"MARGIN_PER_VOLUME_MISSING"

class Atom(AtomBase):
    def __init__(self):
        self._context=None
        self._running=False
        self._accounts={}
        self._specs={}
        self._reserved={}
        self._holds={}
        self._buffer=.10
        self._hold_ttl=HOLD_TTL_DEFAULT
        self._truth=FinancialTruth("526")
        self._seen=0
        self._approved=0
        self._rejected=0
        self._released=0
        self._expired=0
        self._last_reason=""
    async def initialize(self,context):
        self._context=context
        cfg=context.config
        self._buffer=float(cfg.get("margin_buffer_pct",.10))
        self._hold_ttl=float(cfg.get("hold_ttl_s",HOLD_TTL_DEFAULT))
        context.subscribe(EVENT_ORDER,self._on_order)
        context.subscribe(EVENT_ACCOUNT,self._on_account)
        context.subscribe(EVENT_SPECS,self._on_specs)
        bind_truth(self,context,self._truth,("equity","free_margin"))
        context.subscribe(EVENT_VERDICT,self._on_downstream)
        context.subscribe(EVENT_REJECTED,self._on_downstream)
        context.subscribe(EVENT_CMD_FAILED,self._on_downstream)
        context.subscribe(EVENT_TRADE,self._on_trade)
    async def start(self):self._running=True
    async def stop(self):self._running=False
    async def shutdown(self):await self.stop()
    async def _on_account(self,p):
        if not self._running or not isinstance(p,dict) or not p.get("account_id"):return
        account_id=str(p["account_id"])
        self._accounts[account_id]={"leverage":num(p.get("leverage")),"stale":bool(p.get("stale")),"age_s":num(p.get("age_s")),"broker":str(p.get("broker") or ""),"currency":str(p.get("currency") or "")}
        self._reserved[account_id]=sum(h[1] for h in self._holds.values() if h[0]==account_id)
    async def _on_specs(self,p):
        if not self._running or not isinstance(p,dict):return
        for row in p.get("symbols",[]) if isinstance(p.get("symbols"),list) else []:
            if isinstance(row,dict) and row.get("symbol"):self._specs[key(row.get("account_id") or p.get("account_id"), row["symbol"])] = dict(row)
    def _required(self,o,account):
        """(الهامش المطلوب، تقديرٌ أم رقمُ الوسيط، أساس الحساب أو سبب الغياب)."""
        s=o.get("symbol_spec") if isinstance(o.get("symbol_spec"),dict) else self._specs.get(key(o.get("account_id"), o.get("symbol")),{})
        v=num(o.get("volume"))
        price=num(o.get("reference_price"))
        if v is None or v<=0:return None,False,"MARGIN_PER_VOLUME_MISSING"
        # ٢٠٢٦-١٠-٠٢ (ختم المالك «صلح كامل nq»): رقمُ الوسيط للّوت أوّلًا؛ و`margin_initial` لم يعد
        # «مبلغًا للّوت» — هو مدخلٌ في معادلة الوضع (`margin_per_lot`).
        direct=num(s.get("margin_per_volume"))
        if direct is not None and direct>0:return v*direct,False,"BROKER_PER_VOLUME"
        lev=num(account.get("leverage"))
        if s.get("calc_mode") is None:
            # مواصفةٌ بلا `calc_mode` (إكسبرت أقدم من 3.14): يبقى التقدير القديم كما كان، معلَنًا
            # باسمه في الحكم. والرموز السبعة الحيّة كلّها تحمل `calc_mode` فلا تمرّ من هنا.
            cs=num(s.get("contract_size"))
            if price is None or price<=0 or cs is None or cs<=0 or lev is None or lev<=0:return None,True,"MARGIN_PER_VOLUME_MISSING"
            return v*cs*price/lev,True,"LEGACY_ACCOUNT_LEVERAGE"
        rate=MARGIN_RATE_MEASURED.get((str(account.get("broker") or ""),str(o.get("symbol") or "")))
        per_lot,why=margin_per_lot(s,price,lev,str(account.get("currency") or ""),rate)
        if per_lot is None:return None,True,why
        return v*per_lot,True,"CALC_MODE_%d*%g"%(int(num(s.get("calc_mode"))),rate)
    def _expire_holds(self):
        """حجزٌ بلا قرارٍ بعد عمره = أمرٌ مات. يُحرَّر هامشُه."""
        now=time.time()
        dead=[rid for rid,h in self._holds.items() if now-float(h[2])>self._hold_ttl]
        for rid in dead:
            account_id,amount=self._holds.pop(rid)[:2]
            self._reserved[account_id]=max(0.0,self._reserved.get(account_id,0.0)-amount)
            self._expired+=1
        if dead and self._context is not None:
            self._context.logger.warning(
                "526 حُرّر %d حجزًا تجاوز عمره %.0f ثانية — أوامرُ لا قرار لها",
                len(dead),self._hold_ttl)
    async def _on_order(self,p):
        if not self._running or self._context is None or not isinstance(p,dict):return
        self._expire_holds()
        self._seen+=1
        action=str(p.get("action") or OPEN).upper()
        account_id=str(p.get("account_id") or "")
        account=self._accounts.get(account_id)
        reason=""
        required=None
        estimated=False
        basis=""
        rid=str(p.get("request_id") or "")
        if action==OPEN and (not rid or rid in self._holds):approved=False;reason="MISSING_OR_DUPLICATE_REQUEST_ID"
        elif action!=OPEN:approved=True;reason="MANAGEMENT_NO_NEW_MARGIN"
        elif account is None:approved=False;reason="ACCOUNT_MARGIN_DATA_MISSING"
        elif account.get("stale"):approved=False;reason="ACCOUNT_STATE_STALE"
        elif not self._truth.has(account_id,"free_margin"):
            approved=False
            reason="FREE_MARGIN_MISSING"
            await self._context.publish(EVENT_SHORTAGE,self._truth.shortage_body(
                account_id,"free_margin",broker=account.get("broker",""),detail="526 margin gate"))
        else:
            required,estimated,basis=self._required(p,account)
            if required is None:approved=False;reason=basis
            else:
                reserved=self._reserved.get(account_id,0.0)
                free_margin=self._truth.get(account_id,"free_margin")
                available=free_margin-reserved
                need=required*(1.0+self._buffer)
                approved=available>=need
                reason="" if approved else "INSUFFICIENT_FREE_MARGIN"
                if approved:
                    self._reserved[account_id]=reserved+required
                    self._holds[rid]=(account_id,required,time.time())
        if approved:self._approved+=1
        else:
            self._rejected+=1
            self._last_reason=reason
        await self._context.publish(EVENT_OUT,{**p,"approved":approved,"reason":reason,"required_margin":required,"margin_estimated":estimated,"margin_basis":basis if required is not None else "","free_margin":self._truth.get(account_id,"free_margin"),"equity":self._truth.get(account_id,"equity"),"financial_truth_owner":"656","reserved_margin":self._reserved.get(account_id,0.0),"account_age_s":account.get("age_s") if account else None,"account_stale":bool(account.get("stale")) if account else None})
    def _release(self,rid):
        hold=self._holds.pop(str(rid or ""),None)
        if hold is None:return
        account_id,amount=hold[0],hold[1]
        self._reserved[account_id]=max(0.0,self._reserved.get(account_id,0.0)-amount)
        self._released+=1
    async def _on_downstream(self,p):
        if not self._running or not isinstance(p,dict):return
        if p.get("approved") is False or "approved" not in p:self._release(p.get("request_id"))
    async def _on_trade(self,p):
        if not self._running or not isinstance(p,dict):return
        if str(p.get("event_type") or "").upper() in ("OPENED","REJECTED"):self._release(p.get("request_id"))
    async def snapshot(self):
        return {"version":ATOM_VERSION,
                "holds":{rid:[h[0],h[1],h[2]] for rid,h in self._holds.items()},
                "reserved":dict(self._reserved),"accounts":sorted(self._accounts),
                "seen":self._seen,"approved":self._approved,"rejected":self._rejected,
                "released":self._released,"expired":self._expired,
                "last_reason":self._last_reason,"hold_ttl_s":self._hold_ttl}
    async def restore(self,state):
        rows=state.get("holds") if isinstance(state,dict) else None
        if not isinstance(rows,dict):
            raise ValueError("INVALID_MARGIN_HOLDS")
        # الطابع مكتوبٌ منذ v1.4.0؛ حجزٌ قديمٌ بلا طابع يُعدّ حاضرَ اللحظة
        # فيأخذ عمره كاملًا مرّةً واحدة ثمّ ينتهي — لا يُسقَط بلا وزن.
        now=time.time()
        self._holds={}
        for rid,value in rows.items():
            if isinstance(rid,str) and isinstance(value,list) and len(value)>=2 and num(value[1]) is not None and num(value[1])>=0:
                stamp=num(value[2]) if len(value)>2 else None
                self._holds[rid]=(str(value[0]),float(value[1]),stamp if stamp is not None else now)
        self._reserved={}
        for h in self._holds.values():self._reserved[h[0]]=self._reserved.get(h[0],0.0)+h[1]
        self._expire_holds()
    async def health_check(self):
        if not self._running:return HealthStatus(state=HealthState.UNHEALTHY,message="NOT_STARTED")
        d={"seen":self._seen,"approved":self._approved,"rejected":self._rejected,"released":self._released,"expired":self._expired,"held":len(self._holds),"accounts":len(self._accounts),"specs":len(self._specs),"last_reason":self._last_reason}
        if not self._seen:
            return HealthStatus(state=HealthState.HEALTHY,
                                message="READY_AWAITING_FIRST_ORDER_MARGIN_CHECK | approved=0 rejected=0 released=0",details=d)
        # ٢٠٢٦-٠٩-١٨ (ختم NQ): وسادةُ الهامش وعمرُ الحجز معلَنان.
        # ٢٠٢٦-١٠-٠٢ (ختم المالك «صلح كامل nq»): ومعدّلات الهامش المقيسة عيارٌ يُعلَن كذلك.
        return HealthStatus(state=HealthState.HEALTHY,message="approved=%d rejected=%d released=%d expired=%d held=%d سبب=%s | عيار: وسادة=%g%% عمر_الحجز=%gث معدّل_هامش_مقيس=%d رمزًا"%(self._approved,self._rejected,self._released,self._expired,len(self._holds),self._last_reason or "-",self._buffer*100.0,self._hold_ttl,len(MARGIN_RATE_MEASURED)),details=d)
