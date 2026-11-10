from __future__ import annotations

import asyncio
import copy
import math
import time
from pathlib import Path
from typing import Any
from clock import PulseGuard
from core.contracts.atom import AtomBase, AtomContext, HealthState, HealthStatus
from shared.financial_truth import EVENT_SHORTAGE, FinancialTruth, bind_truth
from shared.financial_scope import text
from shared.durable_execution_journal import Journal
# ٢٠٢٦-١٠-٢٦ (قانون صفقات المالك، ختم «NQ»: «صفقات انا بفتحها مالها علاقة بل منظومة ابدا … ولا يحسبها»): عدد المراكز المفتوحة
# في القاطع (`open_trade_count` وحدّه `max_open_trades`) كان يعدّ مراكز المالك اليدويّة مع مراكز المنظومة. صار يعدّ مراكز
# المنظومة وحدها، بالتمييز الواحد في `shared/owner_trades.py`. وأحداث الصفقات (الخسارة اليوميّة والمتتاليات وصفقات اليوم)
# نظيفةٌ من مصدرها: الخبير لا يكتب إغلاقًا إلّا لسحر المنظومة.
# وجواب المالك بختمه «NQ»: «تراجع يومي 5 % انا بسجل 4 الكم و1 الي» — فالحدّ اليوميّ 4٪ هنا من ربح المنظومة وخسارتها
# وحدهما. كانت نسبة الخسارة تُقسم على حقوق الحساب كلّه (`loss_pct` من ٥١٧، مقامه `equity`)، فيتحرّك المقام بعائم
# صفقات المالك وربحها. صارت على الرصيد الابتدائيّ الذي يكتبه المالك بيده (القانون 7: «كلّ النسب تُحسب على رصيدٍ ابتدائيّ»)
# كما يقرؤه ٥٠٩ في حالته؛ وقبل أن تصل حالته تبقى نسبة ٥١٧ كما كانت.
from shared import owner_trades
EVENT_LIMITS="risk.account_limits.state"
# ٢٠٢٦-١٠-٠٢ (ختم المالك «صلح كامل nq»): بعد 5.10.0 تجاوز الملفّ حدّ ٤٠٠ سطرٍ فعليّ (م٩/ملف٤)، فنُقلت أسباب القاطع
# حرفيًّا إلى breaker_reasons.py — صفر تغيير في السلوك: ترتيبها ومجموعتها (`REASON_RANK` · `reason_rank` ·
# `held_reasons` · `set_reasons`)، وقارئا الحمولة (`number` · `opens_new`)، وسبب ردّ الأمر (`_reject_reason`
# ومعه `RISK_EPSILON`)، والشارة (`health_check` ومعها `SYSTEM_SCOPE`). الأسماء تُستورد هنا كما كانت، والطريقتان
# بقيتا في `Atom` تفويضًا بأسمائهما.
from breaker_reasons import REASON_RANK, RISK_EPSILON, SYSTEM_SCOPE, held_reasons, number, opens_new, reason_rank, set_reasons
import breaker_reasons

ATOM_VERSION="5.12.0"
# ٢٠٢٦-١٠-٠٢ (ختم المالك «صلح كامل nq»): v5.10.0 — **القاطع يمسك مجموعة أسباب، والإيقاف بلا حساب
# يوقف الكلّ.** كان الدفتر يحمل سببًا واحدًا: ما دام `MAX_EXPOSURE` ممسوكًا يضيع أيّ خرقٍ آخر صامتًا،
# ثمّ يفكّ 508 قفله آليًّا فيعود التداول فوق حدٍّ مخروق. وكان طلب الإيقاف بلا `account_id` (زرّ
# «الإيقاف الطارئ الشامل» في اللوحة وتلغرام) يُرمى. الآن `reasons` لكلّ دفتر: الإيقاف يضيف سببه،
# والإفراج الموسوم يسحب سببه وحده، وزرّ المالك يمسح الكلّ؛ والإيقاف الشامل علمٌ دائم يوقف كلّ دفترٍ
# معروف وكلّ حسابٍ يظهر بعده حتى زرّ المالك بلا حساب. Doc note #14.
# v5.9.3 (٢٠٢٦-٠٩-٢٤، ختم المالك «Nq»): **للحجز عمر.** كان الحجز لا يُفكّ إلّا
# بـ`execution.order.rejected` أو `platform.trade_event` بالهويّة نفسها، فالأمر
# الذي يموت بطريقٍ آخر (ردٌّ بلا هويّة · انتهاء عمره عند الإكسبرت بعد ثانيتين ·
# إقلاعٌ في منتصفه) يبقى حجزه إلى الأبد، ويُحفظ في اللقطة ويُستعاد. مقيس بعد إقلاع
# 14:22: 13 حجزًا عالقًا، منها 7 على XAUUSD = 700$ من ميزانيّة 740$، فردّ هذا
# الحارس الطلبات الأربعة كلّها `RISK_BUDGET_EXCEEDED`. الآن: حجزٌ لم يُفكّ خلال
# `reservation_ttl_s` (المانيفست) يُفكّ آليًّا، ويُسجَّل، ويُعدّ في الشارة.
# v5.2.0 (2026-08-25): the owner's reset button reaches the switch. The
# direction law is asymmetric on purpose: a HALT without identity never
# widens; an EXPLICIT owner release without identity frees every latched
# book -- restoring normal operation is the safe direction. Doc note #9.
# ٢٠٢٦-١٠-٠٢ (ختم المالك «صلح كامل nq»): نُقض نصفُ الإيقاف من هذا القانون: الإيقاف بلا هويّة صار
# شاملًا (العقد المشترك — الاتّجاه الآمن)، والإفراج بلا هويّة كما هو. Doc note #14.
FINANCIAL_SCOPE_PARTS=3
EVENT_VALIDATE="risk.margin.validation.completed"
EVENT_LOSS="risk.loss_reported"
EVENT_DAY="SYS_MARKET_DAY"  # 2026-10-17 (owner seal): the funder's day starts 00:00 Turkey (806), not UTC midnight
EVENT_CLOCK="SYS_SECOND"
EVENT_RELEASE_REQUEST="risk.release.requested"
EVENT_RESET="risk.kill_switch.reset_requested"
EVENT_POSITIONS="platform.positions.state"
EVENT_ACCOUNT="platform.account.state"
EVENT_TERMINAL="platform.terminal_state"
EVENT_LEDGER="risk.asset_ledger.state"
EVENT_REJECTED="execution.order.rejected"
EVENT_TRADE="platform.trade_event"
EVENT_VALIDATED="risk.validation.completed"
EVENT_HALT="emergency.halt"
EVENT_HALT_REQUEST="risk.halt.requested"
EVENT_STATE="risk.account.state"
EVENT_AUDIT="risk.audit.state"
# ٢٠٢٦-١٠-٠٢ (ختم المالك «صلح كامل nq»): والإيقاف الشامل يُحفظ تحت مستهلكٍ مستقلّ في المخزن نفسه — مفتاحه `SYSTEM_SCOPE`،
# وشرح `REASON_RANK` معه، في breaker_reasons.py.
SYSTEM_CONSUMER="516:system"


def _rebased_config(raw_cfg: dict) -> dict:
    """Resolve manifest paths against the runtime root. See doc note #1."""
    here = Path(__file__).resolve()
    code_root = None
    for parent in here.parents:
        if (parent / "shared" / "runtime_paths.py").is_file():
            code_root = parent
            break
    if code_root is None:
        return raw_cfg
    # ٢٠٢٦-٠٩-٢٣ — رُفع حقنُ `sys.path` من هنا: وزنٌ ميّت لا حماية.
    # `scripts/run_forex.py:9-11` ثمّ `governance/scripts/run_core.py:19-22`
    # يضعان جذرَ المشروع في رأس المسار عند كلّ إقلاع، وهو بعينه
    # `code_root` أدناه — فالشرطُ لا يتحقّق أبدًا. ونصُّ النواة صريح
    # (`core/bootloader.py:252`): لا حاجة لأن تحقن الذرّة المسارَ بنفسها.
    try:
        from shared.runtime_paths import manifest_config_rebase
        return manifest_config_rebase(raw_cfg, code_root=code_root)
    except Exception:  # noqa: BLE001 -- never block boot on a path issue
        return raw_cfg


class Atom(AtomBase):
    def __init__(self):
        self._context=None
        self._running=False
        self._max_daily_loss_pct=5.
        self._max_consecutive_losses=3
        self._max_daily_trades=20
        self._max_open_trades=5
        self._max_reserved_risk_pct=100.
        self._books={}
        self._ledger={}
        self._reservations={}
        self._reservation_ttl_s=None;self._reservation_born={};self._reservations_expired=0
        self._official_time=None
        self._seen=0
        self._validations=0
        self._rejections=0
        self._last_reject_reason=""
        self._identity_rejections=0
        self._incomplete_ignored=0
        self._processed_result_ids=set()
        self._journal=None;self._aligned=False
        self._storage_error=""
        self._duplicates=0
        self._day_guard=PulseGuard(EVENT_DAY)
        self._truth=FinancialTruth('516')
        self._locks={}
        self._global_reasons=set();self._unannounced=set()
    def book(self,a):
        b=self._books.get(a)
        if b is None:
            b=self._books[a]={"broker":"","daily_loss_pct":0.,"consecutive_losses":0,"daily_trade_count":0,"open_trade_count":0,"kill":False,"reason":"","reasons":[],"account_status":"UNKNOWN","system_status":"UNKNOWN","equity":None}
            # ٢٠٢٦-١٠-٠٢ (ختم المالك «صلح كامل nq»): حسابٌ يظهر تحت إيقافٍ شامل يولد موقوفًا، ويُعلَن لتابعيه عند أوّل نشر.
            if self._global_reasons:
                set_reasons(b,self._global_reasons)
                if self._running:self._unannounced.add(a)
        return b
    def _lock(self,a):return self._locks.setdefault(a,asyncio.Lock())
    def _load_durable(self):
        # ٢٠٢٦-١٠-٠٢ (ختم المالك «صلح كامل nq»): الإيقاف الشامل أوّلًا (فيولد كلّ دفترٍ مستعاد تحته)، ثمّ الدفاتر.
        g=self._journal.consumer_states(SYSTEM_CONSUMER).get(SYSTEM_SCOPE)
        if g is not None:self._global_reasons=held_reasons(g) if isinstance(g,dict) else {"RISK_HALT"}
        for account,state in self._journal.consumer_states("516").items():self.book(account).update(state)
    def _normalize(self):
        for b in self._books.values():set_reasons(b,held_reasons(b)|self._global_reasons)
    def _halt_body(self,a,b,origin):return {"account_id":a,"broker":b.get("broker"),"reason":b.get("reason") or "RISK_HALT","reasons":list(b.get("reasons") or []),"origin":origin,"daily_loss_pct":round(float(b.get("daily_loss_pct") or 0.),4),"consecutive_losses":b.get("consecutive_losses")}
    async def initialize(self,c):
        self._context=c
        cfg=_rebased_config(c.config)
        self._max_daily_loss_pct=float(cfg["max_daily_loss_pct"])
        self._max_consecutive_losses=int(cfg["max_consecutive_losses"])
        self._max_daily_trades=int(cfg["max_daily_trades"])
        self._max_open_trades=int(cfg["max_open_trades"])
        self._max_reserved_risk_pct=float(cfg.get("max_reserved_risk_pct",100.0))
        ttl=number(cfg.get("reservation_ttl_s"));self._reservation_ttl_s=ttl if ttl is not None and ttl>0 else None
        self._journal=Journal(str(cfg.get("consumer_db_path") or "var/store/risk_guard_consumer_516.db"))
        try:
            self._journal.ensure()
            self._load_durable()
        except Exception as exc:self._storage_error=type(exc).__name__
        self._normalize()
        for event,handler in ((EVENT_VALIDATE,self._on_validate),(EVENT_LOSS,self._on_loss),(EVENT_DAY,self._on_day),(EVENT_CLOCK,self._on_clock),(EVENT_RELEASE_REQUEST,self._on_reset),(EVENT_HALT_REQUEST,self._on_halt_request),(EVENT_POSITIONS,self._on_positions),(EVENT_ACCOUNT,self._on_account),(EVENT_TERMINAL,self._on_terminal),(EVENT_LEDGER,self._on_ledger),(EVENT_REJECTED,self._release),(EVENT_TRADE,self._release)):c.subscribe(event,handler)
        bind_truth(self,c,self._truth,("equity",),after=self._on_equity)
        c.subscribe(EVENT_LIMITS,self._on_limits)
    async def _on_limits(self,p):
        """الرصيد الابتدائيّ الذي كتبه المالك — مقام نسبة الخسارة اليوميّة (٢٠٢٦-١٠-٢٦)."""
        settings=p.get("settings") if isinstance(p,dict) else None
        initial=number(settings.get("initial_balance")) if isinstance(settings,dict) else None
        if initial is not None and initial>0:self._initial_balance=initial
    def _loss_pct(self,p):
        """خسارة الصفقة نسبةً من الرصيد الابتدائيّ؛ وقبل أن يصل نسبةُ ٥١٧ كما هي."""
        pnl=number(p.get("pnl"));initial=getattr(self,"_initial_balance",None)
        if pnl is not None and initial:return -(pnl/initial)*100.0
        return number(p.get("loss_pct"))
    async def start(self):self._running=True;await self._flush_outbox()
    async def stop(self):self._running=False
    async def shutdown(self):await self.stop()
    async def _flush_outbox(self):
        if self._context is None or self._journal is None or self._storage_error:return
        try:
            for output_id,event_name,payload in await asyncio.to_thread(self._journal.pending_outputs):
                await self._context.publish(event_name,payload)
                await asyncio.to_thread(self._journal.mark_emitted,output_id)
        except Exception as exc:self._storage_error=type(exc).__name__
    async def _on_clock(self,p):
        if self._running and isinstance(p,dict):
            stamp=number(p.get("official_time"))
            if stamp is not None:self._official_time=stamp
            await self._expire_reservations()
            if not getattr(self,"_aligned",False) and self._books and self._context is not None:
                self._aligned=True;self._context.logger.warning("516 محاذاة الإقلاع — حالة القفل تُعلَن لـ%d حساب",len(self._books))  # Doc note #10
                for a in list(self._books):
                    b=self.book(a);k=bool(b.get("kill"));self._unannounced.discard(a)
                    await self._context.publish(EVENT_HALT if k else EVENT_RESET,{"account_id":a,"broker":b.get("broker"),"reason":(b.get("reason") or "RISK_HALT") if k else "BOOT_ALIGN","reasons":list(b.get("reasons") or []),"origin":"516:boot_align","daily_loss_pct":round(b["daily_loss_pct"],4),"consecutive_losses":b["consecutive_losses"]})
            await self._announce()
    def _financial_state(self,a):
        b=self.book(a)
        return {key:(list(b.get(key) or []) if key=="reasons" else b[key]) for key in ("daily_loss_pct","consecutive_losses","daily_trade_count","kill","reason","reasons")}
    async def _persist_financial_state(self,a,event_id):
        if self._journal is None or self._storage_error:return
        try:await asyncio.to_thread(self._journal.save_consumer_state,"516",a,self._financial_state(a),event_id)
        except Exception as exc:self._storage_error=type(exc).__name__
    async def _persist_global(self,event_id):
        if self._journal is None or self._storage_error:return
        try:await asyncio.to_thread(self._journal.save_consumer_state,SYSTEM_CONSUMER,SYSTEM_SCOPE,{"reasons":sorted(self._global_reasons,key=reason_rank)},event_id)
        except Exception as exc:self._storage_error=type(exc).__name__
    async def _announce(self):
        # ٢٠٢٦-١٠-٠٢ (ختم المالك «صلح كامل nq»): الحساب الذي وُلد تحت الإيقاف الشامل يُعلَن لـ552/555/575/601.
        while self._unannounced and self._context is not None:
            a=self._unannounced.pop();b=self.book(a)
            if not b["kill"]:continue
            self._context.logger.error("516 KILL SWITCH حساب=%s سبب=%s — حسابٌ جديد تحت الإيقاف الشامل",a,b["reason"])
            await self._context.publish(EVENT_HALT,self._halt_body(a,b,"516:system_halt"))
    async def _changed(self,a,reason,before):
        b=self.book(a)
        await self._publish_state(a,reason)
        if self._context is not None and before!=b:
            await self._context.publish(EVENT_AUDIT,{"account_id":a,"broker":b.get("broker"),"reason":reason,"previous":before,"current":copy.deepcopy(b),"timestamp":self._official_time})
    async def _publish_state(self,a,reason=""):
        if self._context is None:return
        await self._announce()
        b=self.book(a)
        reserved=sum(float(x["amount"]) for x in self._reservations.values() if x["account_id"]==a)
        await self._context.publish(EVENT_STATE,{"account_id":a,"broker":b.get("broker"),"status":"HALTED" if b["kill"] else "READY" if b["account_status"]==b["system_status"]=="HEALTHY" else "UNKNOWN","daily_loss_pct":b["daily_loss_pct"],"consecutive_losses":b["consecutive_losses"],"daily_trade_count":b["daily_trade_count"],"open_trade_count":b["open_trade_count"],"reserved_risk":reserved,"kill_switch_state":b["kill"],"kill_switch_reason":b["reason"],"kill_switch_reasons":list(b.get("reasons") or []),"system_halt":sorted(self._global_reasons,key=reason_rank),"account_status":b["account_status"],"system_status":b["system_status"],"reason":reason,"timestamp":self._official_time})
    async def _on_account(self,p):
        if not self._running or not isinstance(p,dict):return
        a=text(p.get("account_id"))
        broker=text(p.get("broker"))
        if not a or not broker:self._identity_rejections+=1;return
        equity=self._truth.get(a,"equity")
        before=copy.deepcopy(self.book(a))
        b=self.book(a)
        b["broker"]=broker
        b["equity"]=equity if equity and equity>0 else None
        b["account_status"]="UNKNOWN" if p.get("stale") is True or b["equity"] is None else "HEALTHY"
        await self._changed(a,"ACCOUNT_STATE",before)
        if b["equity"] is None and self._context is not None:
            await self._context.publish(EVENT_SHORTAGE,self._truth.shortage_body(a,"equity",broker=broker,detail="516 safety breaker"))
    async def _on_equity(self,a):
        if not self._running or not a:return
        equity=self._truth.get(a,"equity")
        before=copy.deepcopy(self.book(a))
        b=self.book(a)
        b["equity"]=equity if equity and equity>0 else None
        if b["broker"]:b["account_status"]="HEALTHY" if b["equity"] is not None else "UNKNOWN"
        await self._changed(a,"ACCOUNT_EQUITY",before)
    async def _on_terminal(self,p):
        if not self._running or not isinstance(p,dict):return
        a=text(p.get("account_id"))
        if not a:self._identity_rejections+=1;return
        before=copy.deepcopy(self.book(a))
        known=all(k in p for k in ("connected","trade_allowed","expert_allowed"))
        healthy=known and all(bool(p.get(k)) for k in ("connected","trade_allowed","expert_allowed"))
        self.book(a)["system_status"]="HEALTHY" if healthy else "DEGRADED" if known else "UNKNOWN"
        await self._changed(a,"SYSTEM_STATE",before)
    async def _on_ledger(self,p):
        if not self._running or not isinstance(p,dict):return
        for row in p.get("ledgers",[]) if isinstance(p.get("ledgers"),list) else []:
            if not isinstance(row,dict):continue
            a=text(row.get("account_id"))
            broker=text(row.get("broker")) or self.book(a).get("broker","") if a else ""
            symbol=text(row.get("symbol"))
            budget=number(row.get("risk_budget",row.get("R")))
            used=number(row.get("loss_exposure"))
            if a and broker and symbol and budget is not None and budget>=0:self._ledger[(a,broker,symbol)]={"budget":budget,"used":max(0.,used or 0.)}
    def _reserved(self,scope):return sum(float(x["amount"]) for x in self._reservations.values() if x["scope"]==scope)
    # ٢٠٢٦-١٠-٠٢ (ختم المالك «صلح كامل nq»): جسدها في breaker_reasons.py حرفيًّا — تفويضٌ بالاسم.
    def _reject_reason(self,a,p):return breaker_reasons.reject_reason(self,a,p)
    async def _on_validate(self,p):
        if not self._running or self._context is None or not isinstance(p,dict):return
        self._seen+=1
        self._validations+=1
        a=text(p.get("account_id"))
        out=dict(p)
        if not a:reason="MISSING_ACCOUNT_ID";approved=False;self._identity_rejections+=1
        elif p.get("approved") is False:reason=text(p.get("reason")) or "UPSTREAM_REJECTED";approved=False
        else:reason=self._reject_reason(a,p);approved=not reason
        if not approved:self._rejections+=1;self._last_reject_reason=reason or "UNKNOWN"
        elif opens_new(p):
            request=text(p.get("request_id"))
            b=self.book(a)
            broker=text(p.get("broker")) or b.get("broker","")
            amount=number(p.get("risk_budget"))
            symbol=text(p.get("symbol"))
            if request and amount is not None:self._reservations[(a,request)]={"account_id":a,"scope":(a,broker,symbol),"amount":amount};self._reservation_born[(a,request)]=time.monotonic()
        out.update({"request_id":text(p.get("request_id")),"account_id":a or None,"broker":text(p.get("broker")) or (self.book(a).get("broker","") if a else ""),"symbol":text(p.get("symbol")),"side":text(p.get("side")),"approved":approved,"reason":reason,"kill_switch_state":self.book(a)["kill"] if a else None})
        await self._context.publish(EVENT_VALIDATED,out)
        if a:await self._publish_state(a,"VALIDATION_"+("APPROVED" if approved else "REJECTED"))
    async def _on_loss(self,p):
        if not self._running or not isinstance(p,dict):return
        event_id=text(p.get("event_id"))
        a=text(p.get("account_id"))
        if not event_id or not a:self._identity_rejections+=1;return
        # critical 5: never stop on storage error -- keep counting in memory
        completeness=text(p.get("completeness") or ("COMPLETE" if p.get("costs_complete") is True else "UNKNOWN")).upper()
        loss=self._loss_pct(p)
        b=self.book(a)
        initial=self._financial_state(a)
        glob=set(self._global_reasons)
        def reduce(state):
            outputs=[]
            if loss is None:return state,outputs
            if completeness!="COMPLETE":
                state["incomplete_costs"]=int(state.get("incomplete_costs",0))+1
            state["daily_loss_pct"]=float(state.get("daily_loss_pct",0.))+loss
            state["consecutive_losses"]=int(state.get("consecutive_losses",0))+1 if p.get("is_loss") is True else 0
            state["daily_trade_count"]=int(state.get("daily_trade_count",0))+1
            # ٢٠٢٦-١٠-٠٢ (ختم المالك «صلح كامل nq»): كان سببٌ واحد (اليوميّ يحجب المتتاليات) و`if reason and not
            # state.get("kill")` فيضيع الخرق تحت `MAX_EXPOSURE`. الآن كلّ حدٍّ مخروق يُضاف دائمًا، ويُعلَن الإيقاف إن
            # فُتح الآن أو صار سببٌ جديد أشدَّ الممسوك. الحدّان نفساهما لم يُمسّا.
            breached={r for r,hit in (("RISK_DAILY_LIMIT",state["daily_loss_pct"]>=self._max_daily_loss_pct),("MAX_CONSECUTIVE_LOSSES",state["consecutive_losses"]>=self._max_consecutive_losses)) if hit}
            held=held_reasons(state)|glob;prev=min(held,key=reason_rank) if held else ""
            set_reasons(state,held|breached)
            if breached and state["reason"]!=prev:
                outputs.append(("risk-halt:"+event_id,EVENT_HALT,self._halt_body(a,dict(state,broker=b.get("broker")),"516")))
            return state,outputs
        async with self._lock(a):
            fresh=True
            if self._journal is not None and not self._storage_error:
                try:
                    fresh,state=await asyncio.to_thread(self._journal.reduce_consumer_event,event_id,a,"TRADE_RESULT",event_id,p,"516",a,initial,reduce)
                except Exception as exc:
                    # critical 5: storage failure -- in-memory counting + fail-closed
                    self._storage_error=type(exc).__name__
                    _,state=reduce(dict(initial))
                    set_reasons(state,held_reasons(state)|{"RISK_LEDGER_UNAVAILABLE"})
            else:
                # critical 5: no journal or prior error -- in-memory + fail-closed
                _,state=reduce(dict(initial))
                if self._storage_error:set_reasons(state,held_reasons(state)|{"RISK_LEDGER_UNAVAILABLE"})
            before=copy.deepcopy(b)
            b.update(state)
            set_reasons(b,held_reasons(b)|glob)
        if not fresh:self._duplicates+=1;return
        self._processed_result_ids.add(event_id)
        if loss is None:self._incomplete_ignored+=1;await self._publish_state(a,"LOSS_UNKNOWN_IGNORED");return
        await self._flush_outbox()
        # Second trip path (daily loss / streak) bypasses _trip. See doc note #2.
        bk=self.book(a)
        if set(bk["reasons"])-set(initial["reasons"]):
            self._context.logger.error(
                ("516 KILL SWITCH" if not initial.get("kill") else "516 سبب إيقاف إضافيّ")+
                " حساب=%s سبب=%s خسارة_يومية=%.4f%% متتاليات=%s "
                "صفقات_اليوم=%s أسباب=%s — التداول متوقّف حتى إعادة تعيين صريحة",
                a,bk.get("reason"),bk.get("daily_loss_pct",0.0),
                bk.get("consecutive_losses"),bk.get("daily_trade_count"),"+".join(bk["reasons"]))
        await self._changed(a,"COMPLETE_TRADE_RESULT" if completeness=="COMPLETE" else "TRADE_RESULT_COSTS_INCOMPLETE",before)
    async def _trip(self,a,reason,origin="516"):
        if not a or self._context is None:return
        async with self._lock(a):
            b=self.book(a);held=held_reasons(b)
            # ٢٠٢٦-١٠-٠٢ (ختم المالك «صلح كامل nq»): كان `if b["kill"]:return` فيضيع كلّ سببٍ ثانٍ صامتًا. الآن
            # يُضاف، ويُعلَن الإيقاف إن فُتح المفتاح الآن أو صار السبب الجديد أشدَّ الممسوك (لا إعلانَ مكرَّرًا غير ذلك).
            if reason in held:return
            before=copy.deepcopy(b);prev=b["reason"] if held else ""
            set_reasons(b,held|{reason})
            await self._persist_financial_state(a,"administrative-halt:"+reason)
        # The guard speaks when it cuts. See doc note #3.
        self._context.logger.error(
            ("516 KILL SWITCH" if not held else "516 سبب إيقاف إضافيّ")+
            " حساب=%s سبب=%s مصدر=%s خسارة_يومية=%.4f%% "
            "متتاليات=%s أسباب=%s — التداول متوقّف حتى إعادة تعيين صريحة",
            a,reason,origin,b["daily_loss_pct"],b["consecutive_losses"],"+".join(b["reasons"]))
        if b["reason"]!=prev:self._unannounced.discard(a);await self._context.publish(EVENT_HALT,self._halt_body(a,b,origin))
        await self._changed(a,"HARD_STOP" if not held else "HALT_REASON_ADDED",before)
    async def _on_halt_request(self,p):
        if not self._running or not isinstance(p,dict):return
        a=text(p.get("account_id"));reason=text(p.get("reason")) or "KILL_SWITCH";origin=text(p.get("origin")) or "516"
        # ٢٠٢٦-١٠-٠٢ (ختم المالك «صلح كامل nq»): كان الطلب بلا حساب يُرمى (`_identity_rejections`) — وهو بعينه زرّ
        # «الإيقاف الطارئ الشامل». العقد المشترك: بلا حساب أو `scope=SYSTEM` = إيقافٌ لكلّ دفترٍ معروف ولكلّ حسابٍ
        # يظهر بعده؛ علمٌ دائم يعبر الإقلاع (المخزن واللقطة) حتى زرّ المالك بلا حساب.
        if a and text(p.get("scope")).upper()!=SYSTEM_SCOPE:await self._trip(a,reason,origin);return
        async with self._lock(SYSTEM_CONSUMER):
            self._global_reasons.add(reason)
            await self._persist_global("system-halt:"+str(p.get("command_id") or p.get("request_id") or self._official_time or ""))
        if self._context is not None:self._context.logger.error("516 KILL SWITCH شامل سبب=%s مصدر=%s حسابات=%d — كلّ حسابٍ متوقّف، والجديد يولد متوقّفًا حتى زرّ المالك",reason,origin,len(self._books))
        for x in list(self._books):await self._trip(x,reason,origin)
    async def _on_day(self,p):
        if not self._running or not self._day_guard.accept(p):return
        for a,b in list(self._books.items()):
            async with self._lock(a):
                before=copy.deepcopy(b)
                b["daily_loss_pct"]=0.
                b["daily_trade_count"]=0
                await self._persist_financial_state(a,"day-reset:"+str(p.get("pulse_id") or p.get("bucket_start") or ""))
            await self._changed(a,"DAY_ROLL_COUNTER_RESET",before)
        # 2026-09-18 owner ruling: a daily limit does not outlive its day.
        # Reuses the tagged auto-rearm. Doc note #8.
        # ٢٠٢٦-١٠-٠٢ (ختم المالك «صلح كامل nq»): يُسحب `RISK_DAILY_LIMIT` وحده من مجموعة كلّ دفتر؛ والمتتاليات
        # وأمرُ المالك والإيقاف الشامل وكلّ سببٍ آخر تبقى — حكم ٠٩-١٨ للحدّ اليوميّ وحده. Doc note #14.
        await self._on_reset({"auto_rearm":True,"reason":"RISK_DAILY_LIMIT",
                              "origin":"516:day_roll"})
    async def _on_reset(self,p):
        if not self._running or not isinstance(p,dict):return
        a=text(p.get("account_id"));auto=p.get("auto_rearm") is True;system=text(p.get("scope")).upper()==SYSTEM_SCOPE
        # ٢٠٢٦-١٠-٠٢ (ختم المالك «صلح كامل nq»): زرّ المالك بلا حساب (أو `scope=SYSTEM`) يفكّ الإيقاف الشامل أيضًا —
        # وهو ما ترسله اللوحة وتلغرام (`{}`). والإفراج الآليّ الموسوم لا يمسّه أبدًا.
        if not auto and (system or not a) and self._global_reasons:
            async with self._lock(SYSTEM_CONSUMER):
                self._global_reasons.clear()
                await self._persist_global("owner-release:"+str(p.get("command_id") or p.get("request_id") or self._official_time or ""))
            self._context.logger.warning("516 فُكّ الإيقاف الشامل — زرّ المالك")
        # Owner's master button (no account) unlocks every book, not only the
        # ones killed here: followers hold halts this book dropped. Note #11.
        targets=[a] if a and not system else ([x for x in list(self._books) if self.book(x).get("kill")] if auto else list(self._books))
        if not targets:return
        # Tagged auto-rearm releases ONLY its own reason; an untagged
        # release is the owner's button, unconditional. Doc note #4.
        scoped=text(p.get("reason")) if auto else ""
        for account in targets:
            async with self._lock(account):
                b=self.book(account);held=held_reasons(b);before=copy.deepcopy(b)
                # ٢٠٢٦-١٠-٠٢ (ختم المالك «صلح كامل nq»): الموسوم يسحب سببه من المجموعة وحده ولا يسحب سببَ إيقافٍ
                # شامل، ويبقى المفتاح مرفوعًا ما بقي سبب؛ وزرّ المالك يمسح الكلّ (ويبقى الشامل إن لم يُفكّ).
                if scoped and (scoped not in held or scoped in self._global_reasons):
                    # Warn only on a real mismatch. See doc note #5.
                    if b.get("kill"):
                        self._context.logger.warning(
                            "516 إفراج آليّ مرفوض حساب=%s وارد=%s ممسوك=%r — "
                            "المفتاح مرفوع لسبب آخر",account,scoped,"+".join(b["reasons"]))
                    continue
                if scoped:set_reasons(b,held-{scoped})
                else:
                    b.update({"kill":False,"reason":"","reasons":[]})
                    set_reasons(b,self._global_reasons)
                    # Owner button clears the counters that raised the latch. Note #6.
                    b["consecutive_losses"]=0
                    b["daily_loss_pct"]=0.0
                await self._persist_financial_state(account,("auto-rearm:"+scoped) if scoped else ("owner-release:"+str(p.get("request_id") or self._official_time or "")))
            if b["kill"]:
                self._context.logger.warning("516 سُحب سبب حساب=%s سبب=%s — المفتاح باقٍ مرفوعًا بـ%s",account,scoped or "OWNER_RELEASE","+".join(b["reasons"]))
                await self._changed(account,"REASON_RELEASED_STILL_HALTED",before);continue
            self._context.logger.warning(
                "516 فُكّ المفتاح حساب=%s نوع=%s سبب=%s — التداول مستأنف",
                account,"آليّ" if scoped else "زرّ المالك",scoped or "+".join(sorted(held,key=reason_rank)) or "-")
            await self._changed(account,"AUTO_REARM" if scoped else "EXPLICIT_OWNER_RELEASE",before)
            if self._context is not None:await self._context.publish(EVENT_RESET,{"account_id":account,"broker":b.get("broker"),"reason":("AUTO_REARM:"+scoped) if scoped else "OWNER_RELEASE","origin":"516"})
    async def _on_positions(self,p):
        if not self._running or not isinstance(p,dict):return
        rows=p.get("positions")
        if isinstance(rows,list):
            counts={}
            for row in rows:
                if isinstance(row,dict):
                    a=text(row.get("account_id") or p.get("account_id"))
                    # الحساب يُرى بمراكز المالك أيضًا (صفرٌ معروف لا قيمةٌ قديمة)، والعدّ للمنظومة وحدها.
                    if a:counts[a]=counts.get(a,0)+(0 if owner_trades.is_owner(row) else 1)
            if p.get("complete") is True:
                for a in self._books:counts.setdefault(a,0)
            for a,count in counts.items():
                before=copy.deepcopy(self.book(a))
                self.book(a)["open_trade_count"]=count
                await self._changed(a,"BROKER_POSITION_SNAPSHOT",before)
    async def _release(self,p):
        if not self._running or not isinstance(p,dict):return
        a=text(p.get("account_id"))
        request=text(p.get("request_id"))
        self._reservation_born.pop((a,request),None)
        if a and request and self._reservations.pop((a,request),None) is not None:await self._publish_state(a,"RESERVATION_RELEASED")
    async def _expire_reservations(self):
        """يفكّ الحجز الذي تجاوز عمره `reservation_ttl_s` — والمستعادُ يبدأ عمرَه من الإقلاع."""
        if not self._reservations or not self._reservation_ttl_s:return
        now=time.monotonic()
        stale=[k for k in list(self._reservations) if now-self._reservation_born.setdefault(k,now)>self._reservation_ttl_s]
        for key in stale:
            gone=self._reservations.pop(key,None);self._reservation_born.pop(key,None)
            if gone is None:continue
            self._reservations_expired+=1
            if self._context is not None:
                self._context.logger.warning("516 حجزٌ عالق فُكّ آليًّا حساب=%s طلب=%s نطاق=%s مبلغ=%s بعد %.0fث",key[0],key[1],"/".join(str(x) for x in gone["scope"]),gone["amount"],self._reservation_ttl_s)
            await self._publish_state(key[0],"RESERVATION_EXPIRED")
    async def snapshot(self):
        return {"version":ATOM_VERSION,"books":copy.deepcopy(self._books),"ledger":[{"scope":list(k),**v} for k,v in self._ledger.items()],"reservations":[{"account_id":a,"request_id":r,"scope":list(v["scope"]),"amount":v["amount"]} for (a,r),v in self._reservations.items()],"official_time":self._official_time,"global_halt":sorted(self._global_reasons,key=reason_rank),"processed_result_ids":sorted(self._processed_result_ids),"day_guard":self._day_guard.snapshot(),"seen":self._seen,"approved":self._validations,"rejected":self._rejections,"last_reject":self._last_reject_reason}
    async def restore(self,state):
        if not isinstance(state,dict) or not isinstance(state.get("books"),dict):raise ValueError("INVALID_KILL_SWITCH_STATE")
        self._books={str(a):dict(b) for a,b in state["books"].items() if isinstance(b,dict)}
        self._ledger={tuple(x["scope"]):{"budget":float(x["budget"]),"used":float(x["used"])} for x in state.get("ledger",[]) if isinstance(x,dict) and isinstance(x.get("scope"),list) and len(x["scope"])==FINANCIAL_SCOPE_PARTS}
        self._reservations={(text(x.get("account_id")),text(x.get("request_id"))):{"account_id":text(x.get("account_id")),"scope":tuple(x["scope"]),"amount":float(x["amount"])} for x in state.get("reservations",[]) if isinstance(x,dict) and isinstance(x.get("scope"),list) and len(x["scope"])==FINANCIAL_SCOPE_PARTS}
        self._reservation_born={k:time.monotonic() for k in self._reservations}  # المستعادُ يبدأ عمرَه من الآن
        self._official_time=number(state.get("official_time"))
        self._processed_result_ids={str(x) for x in state.get("processed_result_ids",[])}
        # ٢٠٢٦-١٠-٠٢ (ختم المالك «صلح كامل nq»): الإيقاف الشامل يعبر الإقلاع، والمخزن الدائم يغلب اللقطة كالدفاتر؛
        # واللقطة القديمة بسببٍ واحد تُحوَّل إلى مجموعة، والتالف يبقى موقوفًا (`_normalize`).
        self._global_reasons=held_reasons({"reasons":state.get("global_halt")})
        if self._journal is not None and not self._storage_error:
            try:self._load_durable()
            except Exception as exc:self._storage_error=type(exc).__name__
        self._normalize()
        # 2026-10-17: an old SYS_DAY guard would raise on restore (name mismatch) -- skipped, fresh guard, no reset at boot.
        guard=state.get("day_guard")
        if isinstance(guard,dict) and guard.get("event_name")==EVENT_DAY:self._day_guard.restore(guard)
    # ٢٠٢٦-١٠-٠٢ (ختم المالك «صلح كامل nq»): جسد الشارة في breaker_reasons.py حرفيًّا — تفويضٌ بالاسم.
    async def health_check(self):return await breaker_reasons.health_check(self)
