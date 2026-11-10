// «شو صاير» — الصفحة الوحيدة المكتوبة للمالك بصفته تاجرًا.
//
// ٢٠٢٦-٠٩-١٦ — حكمه: «ظبّط لوحات، ما عم افهم شي منهم».
//
// ونظرتُ بعينه فوجدتُه محقًّا: «الرئيسيّة» تعرض ثلاثة أشرطة مكتوب عليها
// «الاتجاه ٧٫٧٪ · الثقة ٥٢٫١٪ · الجاهزيّة ٦٠٫٨٪»، و«غرفة النظام» تعرض
// «الاتجاه 100.00 / 20.00 · القوّة 24.00 / 10.00». هذه أرقامٌ **لمن يعرف
// العتبات**؛ والتاجر لا يقرأ «24.00 / 20.00» — يقرأ «مرّ» أو «ما مرّ».
//
// فهذه الصفحة تجيب خمسة أسئلة بلغته، بهذا الترتيب لا غيره:
//   ١. هل عم نتداول؟ وإن لا — ليش، ومين بيفكّها؟
//   ٢. فلوسي: الرصيد · الربح المفتوح · كم صفقة
//   ٣. صفقاتي المفتوحة: رمز · شراء ولّا بيع · ربحان ولّا خسران بالدولار
//   ٤. النظام شو شايف بكل رمز: شراء · بيع · مستني — والسبب بكلمة
//   ٥. في شي لازم أنتبهله؟
//
// ⛔ وقواعد مكتوبة على نفسي في هذه الصفحة:
//   • لا رقم ذرّة ولا اسم حدث ولا مصطلح تقنيّ.
//   • لا نسبة مئويّة بلا معنى — إمّا تُترجَم لحكم أو تُحذف.
//   • كل رقم ماليّ يُسمّى مصدره (حكم ٠٩-١٠ بعد كذبة «الربح المفتوح 0.00»).
//   • الغائب يُقال «ما وصل» — لا صفر ولا تخمين.
import { useEffect, useState } from 'react'
import { useStore } from '../core/store'
import { readGate } from '../core/gate'
import { priceText, decimalsOfAll } from '../core/price'
import { arabicHealth, ownerWindowAr } from '../core/arabic'
import { AssetBudgetsCard } from '../components/AssetBudgets'
import { cardHint, cardPrice, cardTime, rrText, useCards } from '../components/TrendCard'

interface Account { balance?: number; equity?: number; free_margin?: number }
interface Pos {
  ticket?: number; symbol?: string; side?: string; volume?: number
  entry_price?: number; current_price?: number
  profit?: number | null; swap?: number | null; commission?: number | null
}
interface Positions { positions?: Pos[]; open_count?: number; owner_open_count?: number }
// ٢٠٢٦-١٠-٢٦ (قانون صفقات المالك، ختم «NQ»: «صفقات انا بفتحها مالها علاقة بل منظومة ابدا … بل نسبة لا خسارة وربح يسجل على
// انه خسار وربح مالك على لوحة»): أرقام المنظومة من ناشريها بعد فصل صفقات المالك عندهم — الصفقات المفتوحة من حاسب الصفقات
// المفتوحة، والربح المفتوح من حاسب الربح والخسارة — و«ربح المالك وخسارته» بطاقةٌ وحدها من الحاسب نفسه. لا تمييزَ هنا.
interface OwnerPnl {
  label?: string; open_count?: number; floating_pnl?: number; realized_today?: number | null
  net_today?: number | null; since?: number | null; positions?: Pos[]
}
interface PnlState { floating_pnl?: number; owner?: OwnerPnl }
interface RealizedRow { events: number; profit: number; commission: number; swap: number; fee: number; net: number }
interface RealizedTotals { available?: boolean; accounts: Record<string, RealizedRow> }

const money = (n?: number | null) =>
  n == null ? '—' : n.toLocaleString('ar-EG-u-nu-latn', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
const signed = (n: number) => `${n >= 0 ? '+' : '−'}${money(Math.abs(n))}`

// الكلمة الحاسمة — حكم المالك ٢٠٢٦-٠٩-١٠: «لش مايل؟ لا. شراء أو بيع».
const SIDE_AR: Record<string, [string, string]> = {
  buy: ['شراء', 'green'],
  sell: ['بيع', 'red'],
  wait: ['مستني', 'amber'],
  none: ['مستني', 'amber'],
}

// ٢٠٢٦-١٠-٠٨ (فكّ الأقسام عن القرار، ختم المالك «NQ»): «رأي النظام» كان من حلّ التعارض (458) وقد أُرشف؛ صار من بطاقة الاتّجاه — وأسبابها بلغة التاجر في `core/arabic.ts`.

// ٢٠٢٦-٠٩-١٦ (صورة المالك على شاشته الكاملة + «ظبّطهم»): كان كل رقم في صفّ
// عريض بـ`space-between`، فعلى ١٩٠٠ بكسل يقف الاسم في طرف والرقم في الطرف
// الآخر — **العين تسافر بينهما**، والرقم الماليّ بحجم النصّ العاديّ. صار كل
// رقم بلاطةً: الاسم صغير فوق، والرقم كبير تحته ملاصقًا له.
function Stat({ k, v, c, t }: { k: string; v: string; c?: string; t?: string }) {
  return (
    <div className="scard" title={t} style={{ padding: '10px 14px' }}>
      <div className="st dim" style={{ fontSize: 12.5 }}>{k}</div>
      <div className="num" style={{ fontSize: 26, fontWeight: 700, color: c, lineHeight: 1.35 }}>{v}</div>
    </div>
  )
}

export default function Now({ onGo }: { onGo?: (id: string) => void }) {
  const conn = useStore((s) => s.conn)
  const acc = useStore((s) => s.streams['platform.account.state']) as Account | undefined
  // صفقات المنظومة وحدها — صفقات المالك مفصولةٌ عند ناشرها (لا من صورة المراكز الخام التي تحمل الاثنين).
  const posState = useStore((s) => s.streams['portfolio.open_positions.state']) as Positions | undefined
  const pnlState = useStore((s) => s.streams['portfolio.pnl.state']) as PnlState | undefined
  const owner = pnlState?.owner
  const cards = useCards()
  const risk = useStore((s) => s.risk)
  const gate = useStore((s) => s.gate) as
    | { status?: string; halted?: boolean; enabled?: boolean; halted_accounts?: Record<string, string> }
    | null
  const market = useStore((s) => s.market)
  // يُقرأ مبكّرًا: بلاطاتُ «يومك» تحتاج سقفَ الصفقات اليوميّ من رسالة ٥١٦.
  const atoms = useStore((s) => s.atoms)

  const list = posState?.positions ?? []
  // الربح المفتوح من ناشره، وإلّا مجموعًا من الصفقات، وإلّا «ما وصل».
  const sum = list.length
    ? list.reduce((a, p) => a + (p.profit ?? 0) + (p.swap ?? 0) + (p.commission ?? 0), 0)
    : null
  const pnl = typeof pnlState?.floating_pnl === 'number' ? pnlState.floating_pnl : sum
  const pnlFrom = typeof pnlState?.floating_pnl === 'number'
    ? 'من حاسب الربح والخسارة' : pnl != null ? 'مجموع أرباح الصفقات + السواب والعمولة' : 'ما وصل رقم'

  // ٢٠٢٦-٠٩-١٦ — بقي ثلث الشاشة أسود فارغًا في صورة المالك. والفراغ ليس
  // كذبًا، لكنّ المكان يستحقّ ما يهمّ التاجر فعلًا: **يومه**. وكلّه مقيس من
  // `risk.unified.state → accounts[<رقم>]` الحيّ، لا محسوبٌ هنا:
  //   risk.daily_trade_count · profit_limits.daily_profit · wins · losses
  //   session_limits.session · max_session_trades   و realized_pnl من 658.
  // ⚠️ ولا يُقرأ من جذر `risk`: الحقول تسكن `accounts` (كذبة ٠٩-٠٩ نفسها).
  const acctRisk = (() => {
    const accounts = (risk as unknown as { accounts?: Record<string, Record<string, unknown>> })?.accounts
    const first = accounts ? Object.values(accounts)[0] : null
    return (first ?? null) as null | {
      risk?: { daily_trade_count?: number }
      profit_limits?: { daily_profit?: number; wins?: number; losses?: number }
      session_limits?: { session?: string; max_session_trades?: number; session_trades?: number }
    }
  })()
  const dayProfit = acctRisk?.profit_limits?.daily_profit
  const wins = acctRisk?.profit_limits?.wins
  const losses = acctRisk?.profit_limits?.losses
  // 🔴 ٢٠٢٦-٠٩-٢٣ (حكم المالك: «في كثير أرقام تكذب على أول تبويب») — كانت
  // البلاطة تكتب «صفقات اليوم 17 من 60»، **والبسط والمقام من ساعتين
  // مختلفتين**:
  //
  //   17  ⟸ 500 `risk.daily_trade_count`        عدّادٌ **يوميّ**
  //   60  ⟸ 506 `session_limits.max_session_trades`  سقفُ **جلسة**
  //   و506 نفسه يقول `session_trades = 0` في اللحظة ذاتها
  //
  // فالنسبة كانت تُقرأ «قاربتَ السقف» وهي لا تعني شيئًا: عددٌ من تقويمٍ
  // ومقامٌ من تقويمٍ آخر. وتلميحُ البلاطة كان يقول «السقف المسموح
  // **للجلسة**» — أي أنّ الكود يعرف الفرق ويخلطهما مع ذلك.
  //
  // وهذا بعينه سببُ تناقضٍ ثانٍ على البطاقة: «رابحة/خاسرة ٠/٠» و«ربح
  // اليوم ‎$0.00‎» صحيحان (٥٠٧ يصفّرهما مع دوران اليوم، سطر ١٦١-١٦٣)،
  // فيقرؤهما المالك مع «١٧ صفقة» فيرى كذبًا — وهو خلطُ ساعاتٍ لا كذب رقم.
  //
  // فصار كلُّ عددٍ مع مقامه من **ناشره نفسه**:
  //   الجلسة : 506 `session_trades` / `max_session_trades`
  //   اليوم  : 500 `daily_trade_count`، وسقفُه من رسالة ٥١٦ نفسها
  //            (`صفقات=17/200`) — لأنّ الحدث لا يحمل سقفًا يوميًّا
  //            (فحصتُ مفاتيح الحمولة كلَّها: لا `max_daily_trades`).
  const dayTrades = acctRisk?.risk?.daily_trade_count
  const sessTrades = acctRisk?.session_limits?.session_trades
  const capSession = acctRisk?.session_limits?.max_session_trades
  const capDaily = (() => {
    const m = /(?:^|\s)صفقات=(\d+)\/(\d+)/.exec(atoms[516]?.health?.message ?? '')
    return m ? Number(m[2]) : null
  })()
  // ٢٠٢٦-١٠-٢٦ (فحص المشروع، ختم «nq اصلح»): كان من 658 (`realized_pnl`)، وهي تجمع ربح الصفقة وحده — فعرض −10,159.25
  // والوسيط نفسه يقول: ربح −10,134.56 · عمولة −852.49 · تبييت −60.30، أي خسارةٌ أكبر بنحو 913$. صار من سجلّ صفقات الجسر
  // نفسه (ما كتبه الوسيط) مع العمولة والتبييت والرسوم، عبر `/gov/realized` — قراءة فقط، كلّ دقيقة. والغائب «ما وصل».
  const [realizedAll, setRealizedAll] = useState<RealizedTotals | null>(null)
  useEffect(() => {
    let alive = true
    const pull = () => {
      fetch('/gov/realized')
        .then((r) => r.json() as Promise<RealizedTotals>)
        .then((d) => { if (alive) setRealizedAll(d) })
        .catch(() => { if (alive) setRealizedAll(null) })
    }
    pull()
    const timer = window.setInterval(pull, 60000)
    return () => { alive = false; window.clearInterval(timer) }
  }, [])
  const accountId = String((acc as { account_id?: string | number } | undefined)?.account_id ?? '')
  const realizedRows = realizedAll?.available ? realizedAll.accounts : {}
  const realizedRow = (accountId && realizedRows[accountId])
    || (Object.keys(realizedRows).length === 1 ? Object.values(realizedRows)[0] : undefined)
  const realized = realizedRow?.net

  // ٢٠٢٦-٠٩-١٨ (أمر المالك عبر جلسة ٤٥٠-٥٩٩، ختم `NQ`): **٥٥٥ هي التي تطلب
  // كلّ أمر دخول** — وكان لها **صفر ذكر في اللوحة كلّها** (فحصتُه: صفر تطابق
  // في `core/` و`sections/` و`components/`). ويوم توقّف التداول اثنتي عشرة
  // ساعة كان السبب فيها، ولا شاشة تعرضه.
  //
  // ⚠️ وقِستُ قبل العرض: `halted` يسكن `details` في `555/atom.py:health_check`،
  // و**النواة تحذف `details`** — فهو لا يصل اللوحة أصلًا مهما فعلتُ هنا.
  // المتاح في `message` هو: `seen · emitted · blocked · … last=<السبب>`.
  // فأعرض ما يصل، وأُعلن ما لا يصل غيابًا — ولا أخترع «سليم» من صمت.
  const a555 = useStore((s) => s.atoms[555])
  const msg555 = a555?.health?.message ?? ''
  // ٢٠٢٦-٠٩-١٨ بعد الظهر — نقلته جلسة ٤٥٠-٥٩٩ إلى صدر الرسالة (`b7c7ac4`)
  // ردًّا على هذا القياس، فصار `halted` يصل اللوحة. يُقرأ من نصّ الرسالة نفسه
  // لأنّ الذرّة تكتبه بادئةً: `"🔴 موقوف — لا أمر يخرج · " + …`.
  const halted555 = msg555.includes('🔴 موقوف')
  const lastReason555 = /(?:^|\s)last=(\S+)/.exec(msg555)?.[1] ?? ''
  const emitted555 = Number(/(?:^|\s)emitted=(\d+)/.exec(msg555)?.[1] ?? NaN)
  const seen555 = Number(/(?:^|\s)seen=(\d+)/.exec(msg555)?.[1] ?? NaN)

  // ٢٠٢٦-٠٩-١٨ (أمر المالك عبر جلسة ٤٥٠-٥٩٩، ختم `NQ`): رقمان يجب أن يراهما
  // مع كل أمر — نسبةُ الهدف إلى الوقف، والمالُ المعرَّض بالدولار. وقد سألتُ
  // عن ناشرهما قبل عرضهما، فنُشرا في `trading.final_decision` من مدقّق الأمر
  // ٥٥٢ (`atom.py:495-506`) — يُحسبان **حيث تُقاس البوّابة نفسها**، أي على
  // الأرقام التي تصل الوسيط حرفيًّا بعد أن يوسّع ٥٢٥ الوقف.
  //
  // ⚠️ ولا يُقرأ `reward_risk` بدلهما: ذاك **عيارٌ** ينشره ٥٥١ وقيمتُه واحدة
  // لكل أمر (٣٫٠)، لا نسبةُ هذا الأمر. وعرضُه مكانَها هو بعينه ما جعل اللوحة
  // تقول «٣٫٠» بينما ٩٢ صفقة من ١٩٦ خرجت دون ١:٣.
  //
  // ⚠️ وهذان **حدثان لا حالة**: `execOrders` سجلٌّ يمتلئ من البثّ الحيّ وحده،
  // فالشاشة المفتوحة للتوّ لا ترى ما سبقها. يُقال ذلك صراحةً ولا يُقرأ الفراغ
  // «ما في أوامر».
  const orders = useStore((s) => s.execOrders)
  const lastOut = orders.find((o) => o.kind === 'final')
  const lastNo = orders.find((o) => o.kind === 'rejected')

  // ٢٠٢٦-٠٩-١٨ — مقيسٌ على المنصّة الحيّة: الحكم الكبير كتب «🟢 شغّال — الأمر
  // بيوصل للمنصّة» بينما **صفر أمر وصل الوسيط منذ الإقلاع**. والسلسلة حيّة:
  //
  //   551 built=5 · 525 legal=0 rejected=5 دون_الأرضيّة=5 XAUUSD BUY 0.15300<2.00000
  //   552 READY_AWAITING_FIRST_LEGAL_ORDER finalized=0 · 601 written=0
  //
  // وعلّةُ الكذب أنّ الحكم كان يتوقّف عند **منتصف** السلسلة (٥٥٥): رآها تُصدر
  // ٦٧٣ طلبًا فحكم بالخضرة — والأوامر تموت بعدها بذرّتين. فالحكم يُؤخذ من
  // **آخر** السلسلة: ما كُتب للمنصّة فعلًا، لا ما طُلب.
  //
  // الصيغ مقروءة من `health_check` كلٍّ منها لا مخمَّنة:
  //   551/atom.py:1036  "built=%d skipped=%d …"
  //   525/atom.py:256   "legal=%d rejected=%d دون_الأرضيّة=%d %s | …"
  //   shared/order_validator_state.py:177,194  "finalized=%d rejected=%d …"
  //   601/atom.py:638   "bridge writable, written=%d"
  const chainMsg = (id: number) => atoms[id]?.health?.message ?? ''
  const chainNum = (id: number, key: string): number | null => {
    const m = new RegExp(`(?:^|[\\s|])${key}=(\\d+)`).exec(chainMsg(id))
    return m ? Number(m[1]) : null
  }
  const built551 = chainNum(551, 'built')
  const legal584 = chainNum(525, 'legal')
  const floorRej584 = chainNum(525, 'دون_الأرضيّة')
  const lastFloor584 = /دون_الأرضيّة=\d+\s+([^|]+)/.exec(chainMsg(525))?.[1]?.trim() ?? ''
  const finalized552 = chainNum(552, 'finalized')
  const written601 = chainNum(601, 'written')
  // تمييز العدد بالعربيّة: «٥ أوامر» لا «٥ أمر». والرقم يبقى لاتينيًّا
  // بمواصفة اللوحة، والمعدود وحده هو الذي يُطابق.
  const countAr = (n: number, one: string, two: string, few: string, many: string) =>
    `${n} ${n === 1 ? one : n === 2 ? two : n <= 10 ? few : many}`
  const ordersAr = (n: number) => countAr(n, 'أمر واحد', 'أمرين', 'أوامر', 'أمرًا')

  const kill = risk?.kill_switch_state === true
  // 🔴 ٢٠٢٦-٠٩-٢٢ — كانت `PARTIAL_HALT` تُجمَع مع `HALTED` في حكمٍ واحد يقول
  // «⛔ إيقاف طارئ فعّال · كل الأوامر مقفولة **بأمرك** · رفعه بيدك». وقِستُه
  // على الحيّ فكانت **ثلاث كذبات في جملة**:
  //
  //   لقطة ٥٥٢ (٢١:٠٣): enabled=true · global_halted=false
  //                     halted_accounts={"52992818":"SESSION_LOSS_LIMIT"}
  //   ولقطة ٥٠٦:        session_loss_pct=10.2506  والعيار 10%
  //
  // فالبوّابة **مفتوحة**، ولا إيقافَ عامًّا، والمالك **لم يأمر بشيء** —
  // حارسُ حدود الجلسة أوقف الحساب لبلوغ خسارته عيارَ المالك. وعقد ٥٥٢ يفرّق
  // بينهما بيده (`atom.py:183`):
  //
  //   HALTED        ⟸ global_halted     (إيقافٌ عامّ — أمرُ المالك)
  //   PARTIAL_HALT  ⟸ halted_accounts   (حسابٌ أوقفه حارس، والسبب معه)
  //
  // وكذبةُ «بأمرك» أسوأ من الحمرة نفسها: تجعل المالك يبحث عن أمرٍ لم يصدره،
  // وتُقرأ عطبًا يُصلَح بينما هي **حارسٌ يعمل**. وبلاغُ قسم ٥٠٠-٥٩٩ نصًّا:
  // «الفرق بينهما عند المالك هو الفرق بين عطبٍ يُصلَح وحارسٍ يعمل».
  // ٢٠٢٦-١٠-٢٦ (فحص المشروع، ختم «nq اصلح»): هذه القراءة نُقلت إلى `core/gate.ts` كما هي، لتقرأ بها «تحكّم» والرئيسيّة
  // وغرفة النظام أيضًا — وزادت مصدرًا ثانيًا: رسالة صحّة 552 نفسها، فمنذ ٢٠٢٦-١٠-٠٢ تبدأ بما يمنع، وتُستطلع كلّ أربع ثوانٍ.
  const gateRead = readGate(gate, atoms[552])
  const ownerHalt = gateRead.ownerHalt
  const guardHalts = gateRead.guardAccounts
  const guardHalt = gateRead.guardHalt
  // 🔴 ٢٠٢٦-٠٩-٢٣ — `!open` كان يعني شيئين: «البوّابة مقفولة» و«ما وصلتني
  // حالتها». وقِستُهما فافترقا: لقطة ٥٥٢ (١١:٤٢، والوقت ١١:٤٥) تقول
  // `enabled=True · global_halted=False · halted_accounts={}` — أي **مفتوحة**،
  // والشاشة تكتب «🔒 بوّابة التنفيذ مقفولة — فتحها بيدك».
  //
  // والعلّةُ أنّ `execution.gate.state` **حدثُ حدوثٍ لا حالة**: ينشره ٥٥٢ في
  // `start()` (`atom.py:147`) وعند أمر بوّابةٍ أو إيقافٍ أو تصفير — فشاشةٌ
  // تُفتح بعد الإقلاع لا تراه أبدًا. فالغياب كان يُقرأ إقفالًا، وهو صنفي
  // الثالث بعينه: صمتٌ يُقرأ خبرًا.
  //
  // ولا بديلَ أشتقّ منه: `enabled` لا يسكن رسالة صحّة ٥٥٢، و`details` تُحذف
  // عند الحدّ. فالغياب يُعلَن غيابًا ويُقال للمالك أين يقرؤه بيده.
  const gateKnown = gateRead.known
  const open = gateRead.open

  const verdict: { text: string; tone: string; why: string; todo: string; where?: string } =
    conn !== 'live'
      ? { text: '⛔ اللوحة مقطوعة عن النظام', tone: 'red',
          why: 'ما في قراءة حيّة — ما بقدر قلّك شي عن وضعك الآن.',
          todo: 'شغّل «غرفة القيادة» من جديد.' }
      : kill
        ? { text: '⛔ التداول موقوف', tone: 'red',
            // ٢٠٢٦-٠٩-١٨: كان يُعرَض خامًا (`RISK_DAILY_LIMIT`) — وهو أهمّ
            // سطر على الصفحة وقت الإيقاف: جواب «ليش ما عم نتداول».
            why: risk?.kill_switch_reason
              ? arabicHealth(String(risk.kill_switch_reason))
              : 'قاطع الأمان مرفوع.',
            todo: 'التصفير بيدك من صفحة «المخاطر».', where: 'risk' }
        : ownerHalt
          ? { text: '⛔ إيقاف طارئ فعّال', tone: 'red',
              why: 'كل الأوامر مقفولة بأمرك — إيقاف عامّ على كل الحسابات.',
              todo: 'رفعه بيدك من صفحة «تحكّم».', where: 'control' }
        : guardHalt
          ? { text: '⛔ موقوف بحارس — مش عطل', tone: 'red',
              why: (guardHalts.length
                ? guardHalts.map(([acct, reason]) =>
                  `الحساب ${acct}: ${reason ? arabicHealth(String(reason)) : 'سببه في سجلّ الحارس، لا في رسالة البوّابة'}`).join(' · ')
                : 'حساب موقوف بحارس ولا سببَ معلَنًا معه')
                + '. البوّابة مفتوحة وما في إيقاف منّك — حارس أوقف الحساب لحاله.',
              todo: 'هاد حارس عم يشتغل مش خلل. التصفير من «تحكّم» ← «صفّر قاطع الأمان»، '
                + 'وحالات الجلسة تتسحب وحدها لمّا يزول سببها (تبدّل الجلسة أو دوران اليوم).',
              where: 'control' }
          : !gateKnown
            ? { text: '⚠️ ما وصلتني حالة بوّابة التنفيذ', tone: 'amber',
                why: 'البوّابة بتعلن حالتها وقت الإقلاع وكل ما تتغيّر — فشاشة انفتحت بعد '
                  + 'الإقلاع ما بتشوفها. يعني ما بعرف هي مفتوحة ولا مقفولة، وما بخترع جواب.',
                todo: 'اكبس «🔄 تحديث» فوق، أو اقرأها بعينك من «التنفيذ» — بطاقة بوّابة الأوامر.',
                where: 'execution' }
          : !open
            ? { text: '🔒 بيحلّل بس ما بيفتح صفقات', tone: 'amber',
                why: gateRead.from === 'atom'
                  ? 'مدقّق الأمر (بوّابة التنفيذ) ما عم يشتغل — ما في أمر بيتدقّق، فما في أمر بيوصل الوسيط.'
                  : 'بوّابة التنفيذ مقفولة — النظام بيدرس السوق وما بيرسل أمر.',
                todo: 'فتحها بيدك من «تحكّم» أو «التنفيذ».', where: 'control' }
            // ٥٥٥ آخرُ حلقةٍ قبل الأمر: البوّابة مفتوحة ولا شيء يخرج إن كانت
            // غائبةً أو ساكتة. وكتابة «شغّال» حينها كذب.
            // ٥٥٥ موقوفة: هذا بعينه ما أوقف التداول اثنتي عشرة ساعة يوم
            // ٢٠٢٦-٠٩-١٨ بقفلٍ يتيم — والبوّابة مفتوحة طوال الوقت.
            : halted555
              ? { text: '⛔ طالب الأمر موقوف — ما في أمر بيخرج', tone: 'red',
                  why: 'بوّابة التنفيذ مفتوحة، بس الذرّة اللي بتطلب الأوامر (٥٥٥) '
                    + 'موقوفة عندها — فالتحليل بيمشي وما بيطلع ولا أمر.',
                  todo: 'ارفع الإيقاف من «تحكّم» — وإذا ما ارتفع، القفل عالق وبدّه إقلاع.',
                  where: 'control' }
            : !a555
              ? { text: '⚠️ ناقص — طالب الأمر مش محمّل', tone: 'amber',
                  why: 'الذرّة اللي بتطلب كل أمر دخول (٥٥٥) مش موجودة بالنواة، '
                    + 'فما في أمر رح يخرج مهما كان التحليل.',
                  todo: 'شوف «التشخيص» — إقلاع ناقص.', where: 'diag' }
              : Number.isFinite(emitted555) && emitted555 === 0 && seen555 > 0
                ? { text: '⚠️ بيوصلها قرارات وما بتطلع أوامر', tone: 'amber',
                    why: `وصل طالبَ الأمر ${seen555} قرارًا وما طلع ولا أمر`
                      + (lastReason555 ? ` — آخر سبب: ${arabicHealth(lastReason555)}` : '.'),
                    todo: 'السبب فوق هو الحاجب — اقرأه قبل أي تعديل.', where: 'execution' }
                // ــ آخر السلسلة: الحكم من الوسيط لا من منتصف الطريق ــ
                // ٢٠٢٦-٠٩-١٩ — بلا هذا الفرع يخضرّ الحكم والسلسلة واقفة:
                // حرّاسُ ما بعد ٥٥٥ كلُّهم «بانتظار أوّل أمر»، وانتظارُ مَن لم
                // يصله شيء ليس سلامة.
                //
                // 🔴 وكنتُ كتبتُ هنا «الوصلة بين طالب الأمر وبانيه مقطوعة» —
                // **إنذارٌ كاذب، ونقضه قسمُ ٥٥٠ بالدليل خلال دقائق**: سجلّ
                // الصفقات يحمل عشرات `STOP_BELOW_FLOOR` بين ٢٣:٤٠ و٢٣:٥٨،
                // وينشرها ٥٢٥ وهو **خلف** ٥٥١ في السلسلة — فلو كانت مقطوعة
                // لما وُجد رفضٌ من آخرها.
                //
                // وعلّةُ غلطي أنّ **الصفر في ذرّةٍ حيّة له معنيان**: «لم يصلها
                // شيء» و«أُعيد بناؤها للتوّ» — فحفظُ `atom.py` تحميلٌ حارّ
                // يُصفّر العدّادات، وقد عُدِّلت ذرّاتٌ كثيرة تلك الليلة. ولا
                // يفرّق بينهما عدّادٌ وحده. فالحكم ينقل الرقم والسبب المعلَن،
                // **ويُعلن قيد العدّاد**، ولا يدّعي سببًا لا يملك دليله.
                : (emitted555 ?? 0) > 0 && built551 === 0
                  ? { text: '⛔ ما في أمر عم ينبني', tone: 'red',
                      why: `طالب الأمر (٥٥٥) طلع ${countAr(emitted555 ?? 0, 'طلب واحد', 'طلبين', 'طلبات', 'طلبًا')} وما انبنى ولا أمر`
                        + (lastReason555 ? ` — وآخر سبب حجب عنده: ${arabicHealth(lastReason555)}.` : '.')
                        + ' وعدّادات الذرّات بتتصفّر مع كل تحديث حيّ، فالصفر معناه «من وقت آخر تحديث» مش «من الإقلاع».',
                      todo: 'السبب فوق هو الحاجب — اقرأه قبل أي تعديل.',
                      where: 'execution' }
                : legal584 === 0 && (floorRej584 ?? 0) > 0
                  ? { text: '⛔ الأوامر بتنبنى وبتنرفض عند حارس الوقف', tone: 'red',
                      why: `انرفض ${ordersAr(floorRej584 ?? 0)} لأنّ الوقف أقرب من الأرضيّة المسموحة للرمز`
                        + (lastFloor584 ? ` — آخرها: ${lastFloor584} (المسافة قبل السهم، والأرضيّة بعده).` : '.')
                        + ' ولا أمر وصل المنصّة.',
                      todo: 'إمّا الأرضيّة أعلى من حركة الرمز، وإمّا الوقف بينحسب أضيق من اللازم — الرقمان فوق.',
                      where: 'execution' }
                  : built551 != null && built551 > 0 && finalized552 === 0
                    ? { text: '⛔ الأمر بينبنى وما بيعدّي البوّابة النهائيّة', tone: 'red',
                        why: `انبنى ${ordersAr(built551)} وما عدّى ولا واحد من مدقّق الأمر (٥٥٢)`
                          + (/(?:^|[\s|])last=(\S+)/.exec(chainMsg(552))?.[1]
                            ? ` — آخر سبب: ${arabicHealth(/(?:^|[\s|])last=(\S+)/.exec(chainMsg(552))![1])}` : '.'),
                        // ٢٠٢٦-١٠-٠٥ (ختم المالك «NQ وأبنيها»): ردُّ ميزانيّة الأصل علاجه بيد المالك
                        // في «تحكّم» — كان الزرّ يرسله إلى «التنفيذ» حيث لا زرّ يفكّه.
                        ...(/(?:^|[\s|])last=(ASSET_FROZEN|ASSET_BUDGET_EXHAUSTED)\b/.test(chainMsg(552))
                          ? { todo: 'آخر رفض كان لأصل نفدت ميزانيّته — شوف «ميزانيّة الأصول» تحت، '
                              + 'والتصفير أو رفع الميزانيّة من «تحكّم».', where: 'control' }
                          : { todo: 'السبب فوق هو الحاجب — اقرأه قبل أي تعديل.', where: 'execution' }) }
                    : finalized552 != null && finalized552 > 0 && written601 === 0
                      ? { text: '⛔ الأمر بيعدّي البوّابة وما بينكتب للمنصّة', tone: 'red',
                          why: `عدّى ${ordersAr(finalized552)} البوّابة النهائيّة وما انكتب ولا واحد بجسر ميتاتريدر (٦٠١).`,
                          todo: 'العلّة بالجسر مش بالقرار — شوف «التنفيذ».', where: 'execution' }
                      : { text: '🟢 شغّال — الأمر بيوصل للمنصّة', tone: 'green',
                          why: written601 != null && written601 > 0
                            ? `البوّابة مفتوحة، وانكتب ${ordersAr(written601)} للمنصّة.`
                            : 'البوّابة مفتوحة وما في إيقاف — وما مرق أمر بعد.',
                          todo: '' }

  const rows = Object.values(cards)
    .filter((c) => c?.symbol)
    .sort((a, b) => String(a.symbol).localeCompare(String(b.symbol)))

  return (
    <div className="section" style={{ display: 'flex', flexDirection: 'column', gap: 14, overflow: 'auto' }}>

      {/* ١ — الحكم الكبير: أوّل شيء تقع عليه العين، وبكلمتين. */}
      <div
        className="scard"
        style={{
          borderInlineStart: `5px solid var(--${verdict.tone})`,
          background: verdict.tone === 'red' ? 'color-mix(in srgb, var(--red) 8%, transparent)' : undefined,
          display: 'flex', alignItems: 'center', gap: 18, flexWrap: 'wrap', padding: '12px 16px',
        }}
      >
        <div className={`sv ${verdict.tone}`} style={{ fontSize: 24, fontWeight: 700, flex: 'none' }}>
          {verdict.text}
        </div>
        <div className="ss" style={{ fontSize: 13.5, lineHeight: 1.8, flex: 1, minWidth: 220 }}>
          {verdict.why}
          {verdict.todo ? <> · <b>{verdict.todo}</b></> : null}
        </div>
        {verdict.where && onGo ? (
          <button className="btn" style={{ flex: 'none' }} onClick={() => onGo(verdict.where as string)}>
            روح لهناك
          </button>
        ) : null}
      </div>

      {/* ٢ — فلوسك: أربع بلاطات، الرقم فيها هو البطل لا الاسم. */}
      <div>
        <div className="st" style={{ fontWeight: 700, fontSize: 15, marginBottom: 6 }}>فلوسك</div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(210px, 1fr))', gap: 10 }}>
          <Stat k="الرصيد" v={acc?.balance != null ? `$${money(acc.balance)}` : 'ما وصل'}
            t="من حالة الحساب على منصّة التنفيذ" />
          <Stat k="قيمة الحساب الآن" v={acc?.equity != null ? `$${money(acc.equity)}` : 'ما وصل'}
            t="الرصيد + ربح الصفقات المفتوحة" />
          <Stat
            k="ربح الصفقات المفتوحة"
            v={pnl == null ? 'ما وصل' : `$${signed(pnl)}`}
            c={pnl == null ? 'var(--dim)' : pnl >= 0 ? 'var(--green)' : 'var(--red)'}
            t={pnlFrom}
          />
          <Stat k="صفقات مفتوحة" v={posState ? String(posState.open_count ?? list.length) : 'ما وصل'}
            t="صفقات المنظومة وحدها — صفقاتك اليدويّة في بطاقتها تحت" />
        </div>
      </div>

      {/* ٢أ — ٢٠٢٦-١٠-٢٦ (قانون صفقات المالك، ختم «NQ»): ربح المالك وخسارته وحده، ولا يدخل رقمًا من أرقام المنظومة. */}
      <div>
        <div className="st" style={{ fontWeight: 700, fontSize: 15, marginBottom: 6 }}>{owner?.label ?? 'ربح المالك وخسارته'}</div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(210px, 1fr))', gap: 10 }}>
          <Stat
            k="ربح صفقاتك المفتوحة"
            v={owner?.floating_pnl == null ? 'ما وصل' : `$${signed(owner.floating_pnl)}`}
            c={owner?.floating_pnl == null ? 'var(--dim)' : owner.floating_pnl >= 0 ? 'var(--green)' : 'var(--red)'}
            t="صفقاتك اليدويّة المفتوحة الآن: ربحها مع التبييت — من حاسب الربح والخسارة"
          />
          <Stat
            k="محقَّقك اليوم"
            v={owner?.realized_today == null ? 'ما وصل' : `$${signed(owner.realized_today)}`}
            c={owner?.realized_today == null ? 'var(--dim)' : owner.realized_today >= 0 ? 'var(--green)' : 'var(--red)'}
            t={'ما تحرّك به الرصيد اليوم ولم تحرّكه صفقات المنظومة — ومعه أيّ إيداعٍ أو سحب.'
              + (owner?.since ? ` منذ ${new Date(owner.since * 1000).toLocaleTimeString('ar-EG-u-nu-latn', { hour: '2-digit', minute: '2-digit', hour12: false })}.` : '')}
          />
          <Stat k="صفقاتك المفتوحة" v={owner?.open_count == null ? 'ما وصل' : String(owner.open_count)}
            t="صفقاتك اليدويّة وحدها — لا تُعدّ في المنظومة" />
        </div>
        {owner?.positions && owner.positions.length > 0 ? (
          <div className="scard" style={{ marginTop: 8, overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13.5 }}>
              <tbody>
                {owner.positions.map((p, i) => {
                  const net = (p.profit ?? 0) + (p.swap ?? 0)
                  const side = SIDE_AR[String(p.side ?? '').toLowerCase()] ?? [String(p.side ?? '—'), 'dim']
                  return (
                    <tr key={p.ticket ?? i} style={{ borderTop: i ? '1px solid var(--glassb)' : undefined }}>
                      <td style={{ padding: '6px 8px' }}><b>{p.symbol ?? '—'}</b></td>
                      <td style={{ padding: '6px 8px', color: `var(--${side[1]})`, fontWeight: 700 }}>{side[0]}</td>
                      <td className="num" style={{ padding: '6px 8px' }}>{p.volume ?? '—'}</td>
                      <td className="num" style={{ padding: '6px 8px', fontWeight: 700, color: net >= 0 ? 'var(--green)' : 'var(--red)' }}>
                        {p.profit == null ? 'ما وصل' : `$${signed(net)}`}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        ) : null}
      </div>

      {/* ٢ب — يومك: الرقم الذي يسأل عنه التاجر أوّل ما يفتح. */}
      <div>
        <div className="st" style={{ fontWeight: 700, fontSize: 15, marginBottom: 6 }}>
          يومك{acctRisk?.session_limits?.session ? ` · جلسة ${acctRisk.session_limits.session === 'new_york' ? 'نيويورك' : acctRisk.session_limits.session === 'london' ? 'لندن' : acctRisk.session_limits.session}` : ''}
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(210px, 1fr))', gap: 10 }}>
          <Stat
            k="ربح/خسارة اليوم"
            v={typeof dayProfit === 'number' ? `$${signed(dayProfit)}` : 'ما وصل'}
            c={typeof dayProfit !== 'number' ? 'var(--dim)' : dayProfit >= 0 ? 'var(--green)' : 'var(--red)'}
            t={'محقَّق اليوم من حارس حدود الربح (٥٠٧) — لا يشمل الصفقات المفتوحة، '
              + 'ويتصفّر مع دوران اليوم. فإن كان صفرًا ومعه صفقات، فصفقاتُها قبل الدوران.'}
          />
          <Stat
            k="رابحة / خاسرة"
            // تناقضُ ساعتين يُعلَن ولا يُبتلع: ٥٠٧ يصفّر `wins`/`losses` مع
            // دوران اليوم (`atom.py:161-163`)، و٥٠٠ يحمل `daily_trade_count`
            // لا يُصفَّر معه. فصفرٌ رابحٌ وخاسرٌ مع سبعةَ عشرَ صفقةً ليس كذبَ
            // رقمٍ بل **اختلافُ نافذتين**، والمالك يقرؤه كذبًا إن لم يُقَل.
            v={wins == null && losses == null
              ? 'ما وصل'
              : `${wins ?? 0} / ${losses ?? 0}`
                + ((wins ?? 0) + (losses ?? 0) === 0 && (dayTrades ?? 0) > 0 ? ' ⚠' : '')}
            c={wins != null && losses != null ? (wins > losses ? 'var(--green)' : wins < losses ? 'var(--red)' : undefined) : 'var(--dim)'}
            t={(wins ?? 0) + (losses ?? 0) === 0 && (dayTrades ?? 0) > 0
              ? `صفر رابحة وصفر خاسرة مع ${dayTrades} صفقة اليوم — العدّادان من نافذتين: `
                + 'هدول من حارس حدود الربح (٥٠٧) ويتصفّروا مع دوران اليوم، وعدد الصفقات '
                + 'من مدير المخاطر (٥٠٠) وما يتصفّر معهم. يعني صفقات اليوم انسكرت قبل الدوران.'
              : 'عدد الصفقات الرابحة مقابل الخاسرة — من حارس حدود الربح (٥٠٧)، ويتصفّر مع دوران اليوم.'}
          />
          <Stat
            k="صفقات الجلسة"
            v={sessTrades == null
              ? 'ما وصل'
              : capSession ? `${sessTrades} من ${capSession}` : String(sessTrades)}
            t={'عدد صفقات الجلسة الجارية وسقفها — الاثنان من حارس حدود الجلسة (٥٠٦) نفسه. '
              + 'وهذا السقف هو اللي وقّف الحساب سابقًا، فالنسبة هون بتعني شي.'}
          />
          <Stat
            k="صفقات اليوم"
            v={dayTrades == null
              ? 'ما وصل'
              : capDaily ? `${dayTrades} من ${capDaily}` : String(dayTrades)}
            t={capDaily
              ? `العدد من مدير المخاطر (٥٠٠) والسقف اليوميّ ${capDaily} من قاطع الأمان (٥١٦) — عدّاد يوميّ وسقف يوميّ.`
              : 'عدد صفقات اليوم من مدير المخاطر (٥٠٠). ولا سقف يوميّ في الحدث، فما بنخترع مقامًا.'}
          />
          <Stat
            k="المحقَّق الكلّي"
            v={typeof realized === 'number' ? `$${signed(realized)}` : 'ما وصل'}
            c={typeof realized !== 'number' ? 'var(--dim)' : realized >= 0 ? 'var(--green)' : 'var(--red)'}
            t={realizedRow
              ? `صافي كلّ ما أُغلق على هذا الحساب كما كتبه الوسيط: ربح الصفقات $${signed(realizedRow.profit)} · `
                + `العمولة $${signed(realizedRow.commission)} · التبييت $${signed(realizedRow.swap)}`
                + (realizedRow.fee ? ` · الرسوم $${signed(realizedRow.fee)}` : '')
                + ` — من سجلّ صفقات الجسر (${realizedRow.events} حدثًا).`
              : 'ما وصل سجلّ صفقات الجسر لهالشاشة — فما في رقم، ولا بنخترعه.'}
          />
        </div>
      </div>

      {/* ٢ج — ٢٠٢٦-١٠-٠٥ (ختم المالك «NQ وأبنيها»): «ما في شي بقول أصول إذا مجمّدة أو كم
          باقي من ميزانيّتها». كلّ أصل بسطر: مسموح أو ممنوع، وكم خسر، وكم باقي. والأزرار
          في «تحكّم» وحدها — هالصفحة للقراءة. */}
      <AssetBudgetsCard onGo={onGo} />

      {/* ٣ و٤ جنبًا إلى جنب على الشاشة العريضة — كانت كلٌّ في صفٍّ كامل فبقي
          ثلث الشاشة أسود فارغًا (ظاهرٌ في صورة المالك)، ومع ذلك كان النصّ
          مزدحمًا في طرفٍ واحد. وتحت ١١٠٠ بكسل يعودان فوق بعض تلقائيًّا. */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(430px, 1fr))', gap: 14, alignItems: 'start' }}>

      {/* ٣ — صفقاتك. الأهمّ عند التاجر: كم ربحان أو خسران بالدولار. */}
      <div className="scard">
        <div className="st" style={{ fontWeight: 700, fontSize: 15 }}>صفقات المنظومة المفتوحة</div>
        {!posState ? (
          <div className="ss dim">ما وصلت صورة المراكز بعد.</div>
        ) : list.length === 0 ? (
          <div className="ss dim">ما في ولا صفقة مفتوحة الآن.</div>
        ) : (
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13.5, marginTop: 6 }}>
              <thead><tr className="dim" style={{ textAlign: 'start' }}>
                <th style={{ padding: '5px 8px', textAlign: 'start' }}>الرمز</th>
                <th style={{ padding: '5px 8px', textAlign: 'start' }}>شو عامل</th>
                <th style={{ padding: '5px 8px', textAlign: 'start' }}>الحجم</th>
                <th style={{ padding: '5px 8px', textAlign: 'start' }}>سعر الدخول</th>
                <th style={{ padding: '5px 8px', textAlign: 'start' }}>السعر الآن</th>
                <th style={{ padding: '5px 8px', textAlign: 'start' }}>ربحان / خسران</th>
              </tr></thead>
              <tbody>
                {list.map((p, i) => {
                  const net = (p.profit ?? 0) + (p.swap ?? 0) + (p.commission ?? 0)
                  const dp = decimalsOfAll(p.entry_price, p.current_price)
                  const side = SIDE_AR[String(p.side ?? '').toLowerCase()] ?? [String(p.side ?? '—'), 'dim']
                  return (
                    <tr key={p.ticket ?? i} style={{ borderTop: '1px solid var(--glassb)' }}>
                      <td style={{ padding: '6px 8px' }}><b>{p.symbol ?? '—'}</b></td>
                      <td style={{ padding: '6px 8px', color: `var(--${side[1]})`, fontWeight: 700 }}>{side[0]}</td>
                      <td className="num" style={{ padding: '6px 8px' }}>{p.volume ?? '—'}</td>
                      <td className="num" style={{ padding: '6px 8px' }}>{priceText(p.entry_price, dp)}</td>
                      <td className="num" style={{ padding: '6px 8px' }}>{priceText(p.current_price, dp)}</td>
                      <td className="num" style={{ padding: '6px 8px', fontWeight: 700, color: net >= 0 ? 'var(--green)' : 'var(--red)' }}>
                        {p.profit == null ? 'ما وصل' : `$${signed(net)}`}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* ٤ — رأي النظام بكل رمز: كلمة واحدة وسبب واحد. لا نسب ولا عتبات. */}
      <div className="scard">
        <div className="st" style={{ fontWeight: 700, fontSize: 15 }}>النظام شو شايف بالسوق الآن</div>
        {rows.length === 0 ? (
          <div className="ss dim">ما وصل قرار لأيّ رمز من وقت ما فتحت الشاشة — القرار بيتجدّد مع إغلاق كل شمعة ٥ دقائق.</div>
        ) : (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(190px, 1fr))', gap: 8, marginTop: 8 }}>
            {rows.map((c) => {
              // «مفتوحة» وحدها فرصةٌ انبعتت؛ كل حالة تانية «مستني» وسببها بجملة.
              const go = c.status === 'OPEN'
              const side = go ? (SIDE_AR[String(c.side ?? '').toLowerCase()] ?? ['—', 'dim']) : SIDE_AR.wait
              const bid = market[String(c.symbol)]?.bid
              return (
                <div key={c.symbol} style={{ border: '1px solid var(--glassb)', borderRadius: 10, padding: '8px 10px' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', gap: 8 }}>
                    <b style={{ fontSize: 14 }}>{c.symbol}</b>
                    <b style={{ color: `var(--${side[1]})`, fontSize: 15 }}>{side[0]}</b>
                  </div>
                  <div className="ss dim" style={{ marginTop: 3, lineHeight: 1.7 }}>
                    {bid != null ? <>السعر {priceText(bid)}<br /></> : null}
                    {go
                      ? <>دخول {cardPrice(c, c.entry)} · وقف {cardPrice(c, c.stop)} · هدف {cardPrice(c, c.target)} ({rrText(c.rr)})<br /></>
                      : null}
                    {cardHint(c.status) || 'ما ذكر سببًا'}
                    <br />آخر قرار مع شمعة {cardTime(c)} · {ownerWindowAr(c.window)}
                  </div>
                </div>
              )
            })}
          </div>
        )}
        <div className="ss dim" style={{ marginTop: 8, fontSize: 11.5 }}>
          «مستني» يعني النظام درس الرمز وقرّر ما يدخل الآن — مو إنّه واقف أو معطّل. والقرار من بطاقة واحدة
          بتشتغل على الرموز المحدّدة بإعدادها بس.
        </div>
      </div>

      {/* ٥ — آخر أمر خرج وآخر أمر انرفض: الرقمان اللي بيحكموا على الصفقة. */}
      <div className="scard">
        <div className="st" style={{ fontWeight: 700, fontSize: 15 }}>آخر أمر خرج · وآخر أمر انرفض</div>

        {lastOut == null ? (
          <div className="ss dim" style={{ marginTop: 6, lineHeight: 1.8 }}>
            ما مرق أمر من وقت ما فتحت هالشاشة. هاد سجلّ بيمتلئ لحظة بلحظة —
            مو تاريخ، فالفراغ هون ما بيعني إنّو ما في أوامر قبل.
          </div>
        ) : (
          <>
            <div style={{ display: 'flex', gap: 10, alignItems: 'baseline', flexWrap: 'wrap', marginTop: 6 }}>
              <b style={{ fontSize: 15 }}>{lastOut.symbol ?? '—'}</b>
              {(() => {
                const s = SIDE_AR[String(lastOut.side ?? '').toLowerCase()] ?? [String(lastOut.side ?? '—'), 'dim']
                return <b style={{ color: `var(--${s[1]})`, fontSize: 15 }}>{s[0]}</b>
              })()}
              <span className="ss dim">الحجم {lastOut.volume ?? '—'}</span>
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 8, marginTop: 8 }}>
              {/* ٢٠٢٦-٠٩-١٨ — الغياب كان ذا معنيين: حارسٌ مطفأ، أو أسعارٌ
                  ناقصة. سألتُ قسم ٥٥٠ فصار العيار يعبر مع كلّ أمر
                  (`552/atom.py:515`)، فصار الفرق مقروءًا — والحارس المطفأ
                  حالٌ **أحمر**، لا صمت. */}
              {(() => {
                const r = lastOut.reward_risk_ratio
                const min = lastOut.reward_risk_min
                const off = min === 0
                return (
                  <Stat
                    k="الهدف مقابل الوقف"
                    v={off ? '⛔ ما في حارس'
                      : typeof r === 'number' ? `١ : ${r.toFixed(2)}` : 'ما انحسب'}
                    c={off ? 'red' : typeof r === 'number' ? 'green' : 'amber'}
                    t={off
                      ? 'حارس النسبة مطفي (عياره صفر) — يعني أيّ أمر بيمرق مهما كان هدفه قريب من وقفه. هاد مش نقص قراءة، هاد بوّابة مفتوحة.'
                      : typeof r === 'number'
                        ? `محسوبة على أرقام الأمر النهائيّة عند آخر بوّابة قبل الوسيط (٥٥٢) — بعد ما يوسّع حارس الشرعيّة (٥٢٥) الوقف.${typeof min === 'number' ? ` والمطلوب ${min} فما تحته ما بيمرق.` : ''}`
                        : 'الحارس شغّال بس الأسعار (مرجع/وقف/هدف) ناقصة بهالأمر، فما انحسبت النسبة.'}
                  />
                )
              })()}
              <Stat
                k="المال المعرَّض"
                v={typeof lastOut.risk_dollars === 'number' ? `$${money(lastOut.risk_dollars)}` : 'ما انحسب'}
                c={typeof lastOut.risk_dollars === 'number' ? 'ink' : 'dim'}
                t={typeof lastOut.risk_dollars === 'number'
                  ? 'الحجم × مسافة الوقف × قيمة الوحدة من مواصفات الرمز — يعني كم بتخسر بالضبط إذا ضرب الوقف.'
                  : 'ما وصل الحقل: مواصفات الرمز أو مسافة الوقف ناقصة.'}
              />
              {typeof lastOut.risk_budget === 'number' ? (() => {
                // المدى المسموح نسبةٌ من الميزانيّة ينشرها ٥٥٢ مع الأمر
                // (`atom.py:516`) — فيُعرض بالدولار لا بالكسر.
                const b = lastOut.risk_budget as number
                const bounds = lastOut.risk_budget_bounds
                const range = Array.isArray(bounds) && bounds.length === 2
                  ? `المسموح من $${money(b * bounds[0])} إلى $${money(b * bounds[1])} — وبرّا المدى بينرفض الأمر.`
                  : 'السقف اللي منقيس عليه المال المعرَّض — الأمر برّاته بينرفض.'
                return <Stat k="ميزانيّة الرمز" v={`$${money(b)}`} c="dim" t={range} />
              })() : null}
            </div>
          </>
        )}

        {/* آخر رفض — جواب «ليش ما صار في صفقة» بسبب واحد ورقمه. */}
        <div style={{ marginTop: 10, borderTop: '1px solid var(--glassb)', paddingTop: 8 }}>
          {lastNo == null ? (
            <div className="ss dim">ولا أمر انرفض من وقت ما فتحت الشاشة.</div>
          ) : (
            <div className="ss" style={{ lineHeight: 1.9 }}>
              <b style={{ color: 'var(--red)' }}>✗ انرفض {lastNo.symbol ?? ''}</b>
              {' — '}
              <span title={lastNo.reason ?? undefined}>{arabicHealth(String(lastNo.reason ?? ''))}</span>
              {(() => {
                // الرقم والعتبة من `rejection` (الأحدث) وإلّا `barrier` — لا من
                // الجذر: ٥٥٢ لا تنشرهما هناك إطلاقًا.
                const b = lastNo.rejection ?? lastNo.barrier
                return typeof b?.value === 'number' && typeof b?.threshold === 'number' ? (
                  <span className="num dim">
                    {' · طلع '}<b>{b.value}</b>{' والمطلوب '}<b>{b.threshold}</b>
                  </span>
                ) : null
              })()}
            </div>
          )}
        </div>
      </div>

      </div>

      <div className="ss dim" style={{ textAlign: 'center', fontSize: 11.5, lineHeight: 1.8 }}>
        هالصفحة فيها اللي بيهمّك كتاجر. باقي التبويبات للتفاصيل التقنيّة —
        ما بدّك ياها إلا إذا بدّك تفحص شي بعينه.
      </div>
    </div>
  )
}
