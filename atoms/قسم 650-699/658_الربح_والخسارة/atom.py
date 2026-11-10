from __future__ import annotations
import time
from core.contracts.atom import AtomBase, AtomContext, HealthState, HealthStatus
# ٢٠٢٦-١٠-٢٦ (قانون صفقات المالك، ختم «NQ»): «صفقات انا بفتحها مالها علاقة بل منظومة ابدا ولا بصير يقيس عليها ولا يسجلها
# ولا يحسبها … بل نسبة لا خسارة وربح يسجل على انه خسار وربح مالك على لوحة وبل منطومة NQ».
# · `floating_pnl` و`net_pnl` للمنظومة وحدها: مراكز المالك تُفصل بالتمييز الواحد في `shared/owner_trades.py` (كانت تُجمع معها).
#   و`realized_pnl` كان للمنظومة وحدها من قبل (نتائج ٥٦٣، والخبير لا يكتب إغلاقًا إلّا لسحرها).
# · وحقلٌ منفصل `owner` باسم «ربح المالك وخسارته»: عائم مراكزه وعددها، ومحقَّقه اليوم من الرصيد نفسه —
#   (الرصيد الآن − رصيد أوّل اليوم) − صافي صفقات المنظومة منذه بعمولتها وتبييتها ورسومها (`platform.trade_event`، وكلّها
#   للمنظومة من مصدرها). فما تحرّك به الرصيد ولم تحرّكه المنظومة فهو للمالك، ومعه أيّ إيداعٍ أو سحب.
#   والمحقَّق يبدأ من أوّل رصيدٍ تراه الذرّة في يومها (`since`) — فإن بدأت وسط اليوم قالت «منذ». ويُحفظ لكلّ يومٍ مضى.
#   ولا يدخل رقمٌ منه شيئًا من أرقام المنظومة.
from shared import owner_trades
from shared.account_limits import turkey_day
ATOM_VERSION="1.3.1"
FAIL_CLOSED="RESTORE_FAILED_FAIL_CLOSED"
EVENT_ACCOUNT="platform.account.state"
EVENT_POSITIONS="platform.positions.state"
EVENT_TRADE="market.outcome.realized"
EVENT_SYSTEM_DEAL="platform.trade_event"
EVENT_OUT="portfolio.pnl.state"
OWNER_LABEL="ربح المالك وخسارته"
#: أيّامٌ مضت يُحفظ محقَّق المالك فيها — حدّ ذاكرةٍ لا قيمة تداول.
OWNER_HISTORY_DAYS=31
#: نافذة إزالة تكرار أحداث الصفقات — حدّ ذاكرة؛ صفقات المنظومة بضعٌ في اليوم.
SEEN_MAX=4096
DEAL_COSTS=("commission","swap","fee")
#: أعمدة صفّ صفقةٍ محفوظ في اللقطة، بترتيبها.
DEAL_ROW=("key","net","applied","day")
OWNER_FIELDS=("ticket","symbol","side","volume","entry_price","current_price","profit","swap","stop_loss","take_profit")
def num(v):
 try:r=float(v)
 except (TypeError,ValueError):return 0.0
 return r if r==r else 0.0
def known(v):
 try:r=float(v)
 except (TypeError,ValueError):return None
 return r if r==r else None
class Atom(AtomBase):
 def __init__(self):
  self._context=None;self._running=False;self._accounts={};self._floating={};self._realized={};self._seen=set();self._updates=0;self._restore_error=""
  self._owner_open={}
  self._owner_day={}
  self._owner_history={}
  self._deals={}
 async def initialize(self,c):
  self._context=c;c.subscribe(EVENT_ACCOUNT,self._on_account);c.subscribe(EVENT_POSITIONS,self._on_positions);c.subscribe(EVENT_TRADE,self._on_trade)
  c.subscribe(EVENT_SYSTEM_DEAL,self._on_system_deal)
 async def start(self):self._running=True
 async def stop(self):self._running=False
 async def shutdown(self):await self.stop()
 async def _on_account(self,p):
  if self._running and isinstance(p,dict) and p.get("account_id"):
   a=str(p["account_id"]);self._accounts[a]=p
   self._owner_balance(a,p)
   await self._publish(a)
 def _owner_balance(self,a,p):
  """محقَّق المالك اليوم من الرصيد — يومٌ جديد يحفظ ما قبله ويبدأ من رصيده الأوّل."""
  balance=known(p.get("balance"))
  if balance is None or p.get("stale") is True:return
  stamp=known(p.get("measured_at")) or time.time()
  day=turkey_day(stamp);book=self._owner_day.get(a)
  if book is None or book.get("day")!=day:
   if book is not None and book.get("realized") is not None:
    history=self._owner_history.setdefault(a,{});history[str(book["day"])]={"realized":book["realized"],"since":book.get("since")}
    for old in sorted(history,key=int)[:-OWNER_HISTORY_DAYS]:del history[old]
   book={"day":day,"anchor_balance":balance,"since":stamp,"system":0.0};self._owner_day[a]=book
  book["balance"]=balance;book["realized"]=round(balance-book["anchor_balance"]-book["system"],2)
 async def _on_system_deal(self,p):
  """صافي صفقة المنظومة بتكاليفها — يُطرح من حركة الرصيد، فلا يُنسب إلى المالك."""
  if not self._running or not isinstance(p,dict) or owner_trades.is_owner(p):return
  a=str(p.get("account_id") or "");key=str(p.get("source_row_id") or p.get("event_id") or "")
  if not a or not key:return
  net=num(p.get("profit"))+sum(num(p.get(f)) for f in DEAL_COSTS)
  book=self._owner_day.get(a);stamp=known(p.get("timestamp"))
  # ٢٠٢٦-١٠-٢٦ (نقض): الصفّ يُعاد نشره بتكاليفه — يُطرح فرقه، لا يُسقط فتصير تكاليف المنظومة على المالك.
  prev=self._deals.pop(a+"|"+key,None)
  if prev is not None:
   applied=prev["applied"] and book is not None and book["day"]==prev["day"]
   if applied:book["system"]=book["system"]+net-prev["net"]
  else:
   applied=book is not None and not (stamp is not None and (turkey_day(stamp)!=book["day"] or stamp<book["since"]))
   if applied:book["system"]=book["system"]+net
  self._deals[a+"|"+key]={"net":net,"applied":applied,"day":book["day"] if book is not None else None}
  while len(self._deals)>SEEN_MAX:self._deals.pop(next(iter(self._deals)))
  if not applied:return
  if book.get("balance") is not None:book["realized"]=round(book["balance"]-book["anchor_balance"]-book["system"],2)
  await self._publish(a)
 async def _on_positions(self,p):
  if not self._running or not isinstance(p,dict):return
  by={};owners={}
  for row in p.get("positions",[]) if isinstance(p.get("positions"),list) else []:
   if not isinstance(row,dict):continue
   a=str(row.get("account_id") or p.get("account_id") or "")
   if owner_trades.is_owner(row):owners.setdefault(a,[]).append({k:row.get(k) for k in OWNER_FIELDS});by.setdefault(a,0.0)
   else:by[a]=by.get(a,0)+num(row.get("profit"))
  # ٢٠٢٦-١٠-٢٦: حساب الصورة يُحسب ولو بلا مركز — صورة ٦٠٩ «كاملة» لكلّ حساب، وبعد الإقلاع لا حساب معروفٌ بعد.
  if p.get("account_id"):by.setdefault(str(p.get("account_id")),0.0)
  affected=set(by)
  if p.get("complete") is True:
   affected.update(self._floating)
   for a in set(self._floating)-set(by):by[a]=0.0
  elif p.get("account_id") and not by:
   a=str(p.get("account_id"))
   by[a]=0.0
   affected.add(a)
  self._floating.update(by)
  for a in affected:
   mine=owners.get(a,[]);self._owner_open[a]={"open_count":len(mine),"floating_pnl":round(sum(num(r.get("profit"))+num(r.get("swap")) for r in mine),2),"positions":mine}
  for a in affected:await self._publish(a)
 async def _on_trade(self,p):
  if not self._running or not isinstance(p,dict):return
  event=str(p.get("event_id") or p.get("source_row_id") or "")
  if event and event in self._seen:return
  if event:self._seen.add(event)
  a=str(p.get("account_id") or "")
  self._realized[a]=self._realized.get(a,0)+num(p.get("profit"))
  await self._publish(a)
 def _owner(self,a):
  # ٢٠٢٦-١٠-٢٦ (نقض): قبل أوّل صورة مراكزٍ للحساب «ما وصل»، لا صفر.
  opened=self._owner_open.get(a,{"open_count":None,"floating_pnl":None,"positions":[]});book=self._owner_day.get(a) or {}
  realized=book.get("realized");floating=opened["floating_pnl"]
  return {"label":OWNER_LABEL,"open_count":opened["open_count"],"floating_pnl":floating,"positions":opened["positions"],
          "realized_today":realized,"since":book.get("since"),"day":book.get("day"),
          "net_today":round(realized+floating,2) if realized is not None and floating is not None else None,
          "history":dict(self._owner_history.get(a,{}))}
 async def _publish(self,a):
  if self._context is None or not a:return
  acc=self._accounts.get(a,{})
  floating=self._floating.get(a,0.0)
  realized=self._realized.get(a,0.0)
  self._updates+=1
  await self._context.publish(EVENT_OUT,{"component":"pnl","event_name":EVENT_OUT,"account_id":a,"floating_pnl":floating,"realized_pnl":realized,"net_pnl":floating+realized,"equity":acc.get("equity"),"measured_at":acc.get("measured_at"),"owner":self._owner(a)})
 async def snapshot(self):
  return {"version":ATOM_VERSION,"realized":{str(k):float(v) for k,v in self._realized.items()},
          "owner_day":{a:dict(b) for a,b in self._owner_day.items()},"owner_history":{a:dict(h) for a,h in self._owner_history.items()},
          "deals":[[k,d["net"],d["applied"],d["day"]] for k,d in self._deals.items()]}
 async def restore(self,state):
  r=state.get("realized") if isinstance(state,dict) else None
  if not isinstance(r,dict) or not all(isinstance(k,str) and isinstance(v,(int,float)) for k,v in r.items()):
   self._realized={}
   self._restore_error=FAIL_CLOSED
   raise ValueError(FAIL_CLOSED)
  self._realized={k:float(v) for k,v in r.items()}
  self._restore_error=""
  # ٢٠٢٦-١٠-٢٦: سجلّ المالك يعبر الإقلاع؛ والناقص أو الفاسد منه يبدأ من أوّل رصيد — لا يُسقط ربح المنظومة المحفوظ.
  days=state.get("owner_day")
  if isinstance(days,dict):
   for a,b in days.items():
    if isinstance(b,dict) and all(known(b.get(k)) is not None for k in ("day","anchor_balance","since","system")):
     self._owner_day[str(a)]={"day":int(b["day"]),"anchor_balance":float(b["anchor_balance"]),"since":float(b["since"]),"system":float(b["system"]),
                              "balance":known(b.get("balance")),"realized":known(b.get("realized"))}
  history=state.get("owner_history")
  if isinstance(history,dict):
   for a,h in history.items():
    if isinstance(h,dict):self._owner_history[str(a)]={str(d):dict(v) for d,v in h.items() if str(d).isdigit() and isinstance(v,dict)}
  deals=state.get("deals")
  if isinstance(deals,list):
   for row in deals[-SEEN_MAX:]:
    if isinstance(row,list) and len(row)==len(DEAL_ROW) and known(row[1]) is not None:
     self._deals[str(row[0])]={"net":float(row[1]),"applied":bool(row[2]),"day":int(row[3]) if known(row[3]) is not None else None}
 async def health_check(self):
  if not self._running:return HealthStatus(state=HealthState.UNHEALTHY,message="NOT_STARTED")
  if self._restore_error:return HealthStatus(state=HealthState.DEGRADED,message=self._restore_error,details={"restore_error":self._restore_error})
  return HealthStatus(state=HealthState.HEALTHY if self._updates else HealthState.DEGRADED,message="pnl_updates=%d"%self._updates)
