"""٥١٦ — أسباب القاطع: ترتيبُ أسباب الإيقاف ومجموعتُها، وسببُ ردّ الأمر، والشارةُ التي تعلنها.

٢٠٢٦-١٠-٠٢ (ختم المالك «صلح كامل nq»): نُقلت **حرفيًّا** من `atom.py` لأنّ 5.10.0 (مجموعة الأسباب
والإيقاف الشامل) رفعه إلى ٤٢٤ سطرًا فعليًّا فوق حدّ الأربع مئة (المادة ٩ ملف ٤) — صفر تغيير في
السلوك، الموضعُ وحده. `_reject_reason` و`health_check` كانتا طريقتين في `Atom`: `self` صار الذرّةَ
معاملًا أوّل (`atom`)، وبقي في `atom.py` تفويضٌ بالاسمين القديمين؛ وكلّ اسمٍ آخر هنا يستورده
`atom.py` باسمه كما كان، فلا يفترق تعريفان لاسمٍ واحد.

لا تنشر هذه الوحدة حدثًا ولا تلمس قرصًا: `set_reasons` تكتب في الدفتر المُمرَّر إليها وحده،
و`reject_reason` تقرأ الدفتر بـ`atom.book` (التي تُنشئه إن غاب، كما كانت).
"""
from __future__ import annotations

import math
from typing import Any

from core.contracts.atom import HealthState, HealthStatus
from shared.financial_scope import text

RISK_EPSILON=1e-9
# ٢٠٢٦-١٠-٠٢ (ختم المالك «صلح كامل nq»): شدّة الأسباب — أوّلُ المجموعة بهذا الترتيب هو `reason` المعلَن:
# يدُ المالك، ثمّ تعطّل المخزن، ثمّ حدود الخسارة، ثمّ العدّ، وآخرُها التعرّض الذي يزول آليًّا. والسبب
# غير المعروف يُرتَّب بعد أسباب المالك مباشرة. والإيقاف الشامل يُحفظ تحت مستهلكٍ مستقلّ في المخزن نفسه.
REASON_RANK=("KILL_SWITCH","OWNER_COMMAND","RISK_LEDGER_UNAVAILABLE","RISK_DAILY_LIMIT","EQUITY_DRAWDOWN_LIMIT","SESSION_LOSS_LIMIT","MAX_CONSECUTIVE_LOSSES","PROFIT_GIVEBACK","DAILY_PROFIT_TARGET","MAX_SESSION_TRADES","MAX_EXPOSURE")
SYSTEM_SCOPE="SYSTEM"


def number(v:Any)->float|None:
    if isinstance(v,bool):return None
    try:r=float(v)
    except (TypeError,ValueError):return None
    return r if math.isfinite(r) else None

def reason_rank(r):return (REASON_RANK.index(r) if r in REASON_RANK else 1.5,r)

def held_reasons(b):
    """أسباب الدفتر الممسوكة — الدفتر القديم بسببٍ واحد يُحوَّل، والتالف يبقى موقوفًا."""
    raw=b.get("reasons")
    if isinstance(raw,(list,tuple,set)):out={text(x) for x in raw if text(x)}
    elif isinstance(raw,str):out={text(raw)} if text(raw) else set()
    else:out={"RISK_HALT"} if raw else set()
    if b.get("kill") and not out:out={text(b.get("reason")) or "RISK_HALT"}
    return out

def set_reasons(b,reasons):
    """`kill` و`reason` (الأشدّ) يُشتقّان من المجموعة — لا يُكتبان بمعزلٍ عنها."""
    rs=sorted({text(r) for r in reasons if text(r)},key=reason_rank)
    b.update({"reasons":rs,"kill":bool(rs),"reason":rs[0] if rs else ""})
    return b

def opens_new(p):return str(p.get("action") or "OPEN").upper()=="OPEN"


def reject_reason(atom,a,p):
    b=atom.book(a)
    # critical 5: storage failure = reject every order (fail-closed)
    if atom._storage_error:return "RISK_LEDGER_UNAVAILABLE"
    if b["kill"] or atom._global_reasons:return "KILL_SWITCH"
    if b["account_status"]!="HEALTHY":return "ACCOUNT_STATE_UNKNOWN"
    if b["system_status"]!="HEALTHY":return "SYSTEM_STATE_UNKNOWN"
    if b["daily_trade_count"]>=atom._max_daily_trades:return "MAX_DAILY_TRADES"
    if b["open_trade_count"]>=atom._max_open_trades:return "MAX_OPEN_TRADES"
    if opens_new(p):
        broker=text(p.get("broker")) or b.get("broker","")
        symbol=text(p.get("symbol"))
        amount=number(p.get("risk_budget"))
        if not broker or not symbol:return "MISSING_FINANCIAL_SCOPE"
        if amount is None or amount<=0:return "RISK_BUDGET_UNKNOWN"
        scope=(a,broker,symbol)
        ledger=atom._ledger.get(scope)
        if ledger is None:return "RISK_LEDGER_UNKNOWN"
        if ledger["used"]+atom._reserved(scope)+amount>ledger["budget"]+RISK_EPSILON:return "RISK_BUDGET_EXCEEDED"
        equity=number(b.get("equity"))
        if equity and atom._reserved(scope)+amount>equity*atom._max_reserved_risk_pct/100.:return "ACCOUNT_RESERVATION_LIMIT"
    return ""


async def health_check(atom):
    if not atom._running:return HealthStatus(state=HealthState.UNHEALTHY,message="NOT_STARTED")
    killed=[a for a,b in atom._books.items() if b.get("kill")]
    unknown=[a for a,b in atom._books.items() if b.get("account_status")!="HEALTHY" or b.get("system_status")!="HEALTHY"];_p=lambda f:max((b.get(f) or 0) for b in atom._books.values()) if atom._books else 0  # أسوأ دفتر: قفلٌ واحد يوقف الكلّ
    d={"accounts":len(atom._books),"killed":killed,"unknown":unknown,"reservations":len(atom._reservations),"validations":atom._validations,"rejections":atom._rejections,"identity_rejections":atom._identity_rejections,"incomplete_ignored":atom._incomplete_ignored,"duplicates":atom._duplicates,"storage_error":atom._storage_error,"system_halt":sorted(atom._global_reasons,key=reason_rank)}
    dials="يوم=%.2f/%g%% متتالية=%d/%d صفقات=%d/%d مراكز=%d/%d محجوز=%g%%"%(_p("daily_loss_pct"),atom._max_daily_loss_pct,_p("consecutive_losses"),atom._max_consecutive_losses,_p("daily_trade_count"),atom._max_daily_trades,_p("open_trade_count"),atom._max_open_trades,atom._max_reserved_risk_pct)  # حيّ/عيار — Doc note #12 و#13
    if atom._storage_error:return HealthStatus(state=HealthState.UNHEALTHY,message="DURABLE_CONSUMER_UNAVAILABLE | "+dials,details=d)
    if killed or atom._global_reasons:return HealthStatus(state=HealthState.DEGRADED,message="KILL_SWITCH_ACTIVE %s | %s"%(" ".join(([SYSTEM_SCOPE+":"+"+".join(sorted(atom._global_reasons,key=reason_rank))] if atom._global_reasons else [])+["%s:%s"%(a,"+".join(atom.book(a).get("reasons") or [atom.book(a).get("reason") or "-"])) for a in killed[:3]]),dials),details=d)
    if not atom._books or unknown:return HealthStatus(state=HealthState.DEGRADED,message="RISK_STATE_UNKNOWN | "+dials,details=d)
    # details is stripped by the core; everything that matters rides here. #7
    return HealthStatus(state=HealthState.HEALTHY,message="accounts=%d validations=%d rejected=%d last=%s | مكرَّر=%d هويّة=%d ناقص=%d حجوزات=%d%s | %s"%(len(atom._books),atom._validations,atom._rejections,atom._last_reject_reason or "-",atom._duplicates,atom._identity_rejections,atom._incomplete_ignored,len(atom._reservations),(" فُكّ_آليًّا=%d"%atom._reservations_expired if atom._reservations_expired else ""),dials),details=d)
