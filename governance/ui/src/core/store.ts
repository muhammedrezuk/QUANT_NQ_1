// طبقة البيانات (١٤ §٤/§٦): آخر قيمة لكل تدفّق، في الذاكرة فقط.
// الحوكمة مو مصدر الحقيقة — بلا تخزين؛ تموت وتعود تقرأ من جديد (١٤ §١٠).
import { create } from 'zustand'
import type { Color } from './i18n'

export interface AtomRec {
  id: number
  name: string
  name_ar?: string
  label_ar?: string
  color?: Color
  version?: string
  critical?: boolean
  state: string
  health: { state: string; message?: string } | null
  restart_count: number
  last_error: string | null
}

// ٢٠٢٦-٠٩-٠٨ (بلاغ المالك: «اش هاد عم يكذب انا مالي مشغل منصة وسيط»):
// وصولُ الحدث ليس دليل حياة. المقيس يومها وميتاتريدر متوقّف منذ ساعات:
// 740,580 تِكّة متراكمة في `ticks_v2`، فظلّ 618 يستهلكها وينشر 417
// رسالة/ثانية ثمانيًا وأربعين دقيقة — وكل شارة تقيس التدفّق كانت خضراء،
// والفارق الحقيقي `BTCUSD` 78,796.65 على الجسر مقابل 78,435.4 على سي‑تريدر.
//
// ولا يُسأل 618 عن ذلك: طوابعه من `MqlTick.time_msc` بوقت **خادم الوسيط**
// (مقيس على +3 ساعات)، فلا يملك مقياس عمر — إنّما أثر آخر نشر، وهو يعمى عن
// الطابور. المقياس الصادق عند **619**: `updated_at` يكتبه الإكسبرت بـ
// `TimeGMT()`، فـ`official − updated_at` عمرٌ حقيقيّ. ولذلك وحدها كانت 619
// تعلن `ACCOUNT_STATE_STALE` طوال الوقت ولا تسمعها اللوحة.
//
// الحالة تُقرأ من `health.state` — الحقل الصريح لا نصّ الرسالة (تحذير بوّابة
// ٥٥٢ أعلاه قائم). فكل شارة تدفّق تُخضَع لحكم الذرّة التي تملك المقياس.
//
// ٢٠٢٦-٠٩-٠٩: و`degraded` ليست موتًا. 622 يعلنها متى نام رمز خارج جلسته
// ويسمّيه، والتصميم مقصود ومقيس (`622/atom.py:469` — أربعة مؤشّرات ومعدن
// سكتت عند استراحتها اليوميّة وثلاثة تنبض تحت الثانية). فترجمتُها «بائت»
// كانت كذبًا بالاتجاه المعاكس: أعلنَت الموت وسوقُ اليورو مشتعل.
// ثلاث حالات لا اثنتان: حيّ · جزئيّ (نائم مسمّى) · بائت (`unhealthy`).
export const atomStale = (a?: AtomRec): boolean =>
  !!a && !!a.health && a.health.state === 'unhealthy'

export const atomPartial = (a?: AtomRec): boolean =>
  !!a && !!a.health && a.health.state === 'degraded'

export interface AnalyzerContribution {
  analyzer_id?: string
  signal?: string
  direction?: number
  score?: number
  confidence?: number            // 0..100
  strength?: number
  ratio?: number
  current_depth?: number         // 0..100، عمق الأدلة الحالي
  required_depth?: number        // 0..100، عمق الأدلة المطلوب
  confidence_threshold?: number  // 0..100، عيار الثقة المستقل
  threshold?: number
  weight?: number                // لا يُطبَّق إلا بعد الجاهزية
  weight_applied?: number
  analysis_state?: string
  state?: string
  ready?: boolean
  included?: boolean
  source_timestamp?: number
  timestamp?: number
  sequence?: number
}

// إقفال 150 مرحلة ٢/٣ (أمر المالك 2026-08-23): الروم المتدفّق ولوحة المحلّلين.
// ⛔ الواجهة تنقل ما وصل فقط؛ الغائب مجهول معلن، لا صفر ولا حساب.
export interface RoomSectionRow {
  section_id: string
  state?: string
  direction?: number | null
  strength?: number | null
  confidence?: number | null
  readiness_pct?: number | null
  weight?: number | null
  current_depth?: number | null
  required_depth?: number | null
  timeframe?: string
  period_start?: unknown
  age_s?: number
}

export interface DecisionRoom {
  account_id?: string | null
  broker?: string | null
  symbol: string
  direction?: number | null
  strength?: number | null
  confidence?: number | null
  confidence_defined?: boolean
  readiness_pct?: number | null
  signal?: string
  sections_present?: string[]
  sections_missing?: string[]
  sections?: RoomSectionRow[]
}

export interface AnalystRow {
  id: string
  present: boolean
  mode?: string
  timeframe?: string
  period_start?: unknown
  sequence?: number | null
  direction?: number | null
  strength?: number | null
  confidence?: number | null
  weight?: number | null
  ready?: boolean
  state?: string
  deliveries?: number
  delivered_at?: number | null
  age_s?: number | null
  next_expected_at?: number | null
}

export interface AnalystsPanel {
  account_id?: string | null
  broker?: string | null
  symbol: string
  expected?: number
  present?: number
  missing?: string[]
  analysts?: AnalystRow[]
}

// بند أ١١ — بطاقة مسار (سريع من التكّات / بطيء من الشموع) من ١٦٦ v2.3.1:
// العقد الثماني + unknown_fields. ⛔ القيمة 0.0 مع ورود اسمها في unknown_fields
// = مجهول، وتُعرض «مجهول» لا صفرًا. اللوحة تنقل ما وصل ولا تحسب شيئًا.
export interface PathCard {
  path?: string                  // "fast" | "slow"
  source?: string                // "ticks" | "candles"
  account_id?: string | null
  broker?: string | null
  symbol?: string
  timeframe?: string
  cycle_id?: string
  quality?: string
  warnings?: string[]
  direction?: number             // ±100
  strength?: number
  confidence?: number            // 0..100
  current_depth?: number         // 0..100
  required_depth?: number        // 0..100
  weight?: number                // وزن المسار المعلَن
  ratio?: number
  state?: string                 // READY | ANALYZING | NOT_READY | STALE
  unknown_fields?: string[]
  sequence?: number
  source_timestamp?: number
  timestamp?: number
  active_weight?: number
  available_weight?: number
  missing_weight?: number
  contributors?: Record<string, AnalyzerContribution>
}

// جسم القسم من ١٦٦ (analysis.raw.completed بحقل timeframe="section"):
// الثماني المدموجة (section_contract) + البطاقتان كاملتين أو null للغائب.
export interface SectionFusionState {
  account_id?: string | null
  broker?: string | null
  symbol: string
  status?: string
  signal?: string | null
  ready?: boolean
  warnings?: string[]            // منها "missing_path"
  section_contract?: PathCard
  paths?: { fast?: PathCard | null; slow?: PathCard | null }
  path_weights?: { fast?: number; slow?: number }
  path_missing_weight?: number
  contributors?: Record<string, AnalyzerContribution>
  timestamp?: number
  source_timestamp?: number
  metadata?: { present_paths?: string[]; merge?: string }
}

export interface AnalysisState {
  account_id?: string
  symbol: string
  status: string
  analysis_state?: string
  ready?: boolean
  signal?: string | null
  direction?: number | null
  score?: number | null           // -100..+100
  confidence: number              // 0..100
  strength?: number
  ratio?: number
  current_depth?: number
  quality: string
  agreement: number               // 0..1
  active_weight?: number
  available_weight?: number
  missing_weight?: number
  timestamp?: number
  source_timestamp?: number
  warnings?: string[]
  contributors?: Record<string, AnalyzerContribution>
  metadata?: { expected?: number; present?: number; complete?: boolean; valid?: number; weight_normalization?: string }
}

// ٢٠٢٦-٠٩-٠٩ (ختم NQ): النوع كان ناقصًا ثلاثة حقول ينشرها ٢١٠ فعلًا
// (`atom.py` السطور ١٤٨-١٥٠): عمق الجاهزيّة الحاليّ والمطلوب واكتمالها.
// الصفحة تقرؤها منذ زمن — المفقود كان الإعلان عنها هنا وحده.
export interface StructureState {
  symbol: string
  status: string
  signal: string
  score: number
  confidence: number
  quality: string
  current_depth?: number
  required_depth?: number
  complete?: boolean
  structure: {
    trend: string; phase: string; swing: string; swing_price: number | null
    external_high: number | null; external_low: number | null; internal: string
    last_shift: { type: string | null; direction: string | null }
  }
  metadata?: { timeframe?: string; present?: number; expected?: number }
}

// ٢٠٢٦-٠٩-٠٩ (ختم NQ): خمسة حقول ينشرها ٢٦٠ فعلًا (`atom.py` ٢٤٠-٢٤٥) ولم
// تكن معلَنة هنا: الضغط وجودة السيولة وعمق الجاهزيّة الحاليّ والمطلوب واكتمالها.
export interface LiquidityState {
  symbol: string
  status: string
  signal: string
  confidence: number
  quality: string
  current_depth?: number
  required_depth?: number
  complete?: boolean
  liquidity_pressure?: number
  liquidity_quality?: number
  liquidity: {
    pool: string
    buyside_level: number | null; sellside_level: number | null
    sweep: { signal: string; direction: string | null; price: number | null }
    fvg: { signal: string; gap_top: number | null; gap_bottom: number | null }
  }
  metadata?: { timeframe?: string; present?: number; expected?: number }
}

// ٢٠٢٦-٠٩-٠٩: لوحة وحدات السيولة (٢٥٠ `liquidity.units.state`) — كانت تُنشر
// منذ ٢٦-٠٨ وما قرأها أحد. فيها صفّان: `units` وحدات الدورة، و`book_units`
// عائلة الدفتر (٢٦١/٢٦٢/٢٦٣/٢٦٤) المرصودة خارج الدورة — تنشر بإيقاع الدفتر
// بلا cycle_id فلا تدخل present/expected ولا نتائج الدورة.
export interface LiquidityUnitRow {
  id: string
  present?: boolean
  observed?: boolean
  excluded?: boolean
  reason?: string
  direction?: number | null
  strength?: number | null
  confidence?: number | null
  weight?: number | null
  ready?: boolean
  state?: string
  // الحقول غير المحسوبة تُنشر بصفر ويسمّيها العقد هنا (section_contract §١١).
  // عرض صفرها كأنّه قياس = كذب صامت — فتُعرض «مجهول».
  unknown_fields?: string[]
  // ٢٠٢٦-٠٩-١٦: بأيّ إيقاع وصلت الوحدة — "candle" بلّغت داخل دورتها،
  // "book" ضُمّت إليها بالحداثة لأنّ مصدرها تدفّق بلا رقم دورة.
  paced_by?: string
  status?: string
  signal?: string | null
  provider?: string | null
  method?: string | null
  levels?: number | null
  warnings?: string[]
  deliveries?: number
  age_s?: number | null
}
export interface LiquidityUnitsState {
  symbol: string
  timeframe?: string | null
  present?: number
  expected?: number
  missing?: string[]
  excluded_units?: string[]
  units?: LiquidityUnitRow[]
  book_units?: LiquidityUnitRow[]
  book_ids?: string[]
  book_reason?: string
  // من `liquidity.cycle.collected` (٢٥٠ v1.8.0): مَن ضُمّ للدورة بالحداثة،
  // ومَن كانت لقطته أقدم من مهلة الدورة فتُرك مسمّى بدل أن يُرقَّع بها.
  book_units_admitted?: string[]
  book_stale_units?: string[]
  book_max_age_s?: number
}

export interface StatsUnit { id?: string; signal?: string; status?: string; metadata?: { value?: number; count?: number } }
export interface StatsState {
  symbol: string
  timeframe?: string
  results: Record<string, StatsUnit>
}

export interface ProbUnit { signal?: string; status?: string; quality?: string; confidence?: number; metadata?: { probability?: number; value?: number; direction?: string; band?: string } }
export interface ProbabilityState { symbol: string; results: Record<string, ProbUnit> }

// ٢٠٢٦-١٠-٠٨ (فكّ الأقسام عن القرار، ختم المالك «NQ»): نوعا دورتَي الاستراتيجيّات (400) والقرار (450) حُذفا مع أرشفة ناشريهما.
// ٢٠٢٦-٠٩-٠٩ (ختم NQ) — الحقول الخمسة الأولى كانت تُقرأ من جذر الحمولة، و٥٠٠
// صار مجمِّعًا لكل حساب: القيم الحقيقيّة داخل `accounts[<رقم>].risk`. فالجذر
// كان `undefined` دائمًا، أي **قاطع الأمان لا يظهر مفعَّلًا أبدًا** والخسارة
// اليوميّة والخسائر المتتالية صفرٌ أبديّ. القياس الحيّ أثبت ذلك، و`engine.ts`
// يسطّح الحمولة الآن قبل الحفظ. `accounts` تبقى كما وصلت للقارئ المفصّل.
export interface AccountRisk {
  account_id?: string; broker?: string; status?: string
  daily_loss_pct?: number; consecutive_losses?: number; daily_trade_count?: number
  open_trade_count?: number; kill_switch_state?: boolean; kill_switch_reason?: string
  account_status?: string; system_status?: string; reason?: string
}
export interface RiskState {
  daily_loss_pct?: number; consecutive_losses?: number; daily_trade_count?: number
  kill_switch_state?: boolean; kill_switch_reason?: string
  id?: string; role?: string; authority?: string; count?: number
  accounts?: Record<string, { risk?: AccountRisk; status?: string }>
}

// بوّابة التنفيذ (٥٥٢ — execution.gate.state): حالة حقيقيّة تُنشَر عند كل تغيير،
// لا تُشتقّ من رسالة صحّة الذرّة (كانت `health.message` تبدأ بـ`LIVE` افتراضًا
// لم يعد كود ٥٥٢ الحالي ينتجه إطلاقًا — راجع سياق/٩٠).
export interface GateState {
  enabled?: boolean
  halted?: boolean
  halted_accounts?: Record<string, string>
  status?: 'LIVE' | 'STOPPED' | 'HALTED' | 'PARTIAL_HALT' | string
  seen?: number
}

// التنفيذ (عيلة ٥٥٠) — عرض فقط: الحالة الموحّدة من ٥٥٠ + سجلّات دوّارة للأوامر/الإدارة/النتائج
export interface ExecutionState {
  counts?: Record<string, number>
  halted?: boolean
  last_order?: { stage?: string; symbol?: string; side?: string; volume?: number | null; stop_loss?: number | null; take_profit?: number | null } | null
  last_outcome?: { symbol?: string; profit?: number | null } | null
  reject_reasons?: Record<string, number>  // من ٥٥٢ execution.order.rejected — لماذا رُفض كل أمر
  skip_reasons?: Record<string, number>    // من ٥٥١ execution.order.skipped — لماذا ما بُني الأمر أصلًا
}
export interface ExecOrderRec {
  kind: 'built' | 'final' | 'rejected' | 'skipped'
  symbol?: string; side?: string; volume?: number
  reference_price?: number; stop_loss?: number; take_profit?: number
  // ٢٠٢٦-٠٩-١٨: `gate` حُذف — لا ناشر له على أيٍّ من روافد هذا السجلّ الأربعة
  // (الكلمة تظهر في ٥٥٢ مرّةً واحدة `payload.get("gate")` وهي **قراءةُ أمرِ
  // بوّابةٍ وارد** لا نشرًا)، ولا شاشة تعرضه. حقلٌ بلا ناشرٍ ولا قارئ.
  reward_risk?: number; reason?: string
  // ٢٠٢٦-٠٩-١٨ — الرقمان النهائيّان، ينشرهما مدقّق الأمر ٥٥٢ مع
  // `trading.final_decision` حيث تُقاس البوّابة نفسها
  // (`atoms/قسم 550-599/552_مدقق_الأمر/atom.py:500-506`). وهما شرطيّان:
  // إن تعذّر حسابُهما لا يُوضع المفتاح أصلًا — فالغياب غياب، لا صفر.
  //
  // ⚠️ وفرقُهما عن `reward_risk` أعلاه فرقُ نيّةٍ عن واقع: ذاك **عيارٌ**
  // ينشره ٥٥١ (`atom.py:926`) وقيمتُه واحدة لكل أمر، وهذا **مقيسٌ من
  // أسعار الأمر نفسه بعد أن وسّع ٥٢٥ الوقفَ**. عرضُ الأوّل مكان الثاني
  // هو بعينه ما جعل ٩٢ صفقة من ١٩٦ تخرج دون ١:٣ واللوحة تقول ٣٫٠.
  reward_risk_ratio?: number   // |الهدف − المرجع| ÷ |المرجع − الوقف|
  risk_dollars?: number        // الحجم × مسافة الوقف × قيمة الوحدة
  risk_budget?: number         // ميزانيّة الرمز التي يُقاس عليها المعرَّض
  // ٢٠٢٦-٠٩-١٨ (`15c5699`) — العياران يعبران مع كلّ أمر، وينشران **بلا شرط**
  // (`552/atom.py:515-516`). وسببُهما أنّ غياب `reward_risk_ratio` كان ذا
  // معنيين لا يُفرَّق بينهما: حارسٌ مطفأ بعياره، أو أسعارٌ ناقصة في هذا الأمر.
  // فصار `reward_risk_min === 0` يعني **بوّابةً مفتوحة وكلَّ نسبةٍ تمرّ** —
  // وهذا حالٌ أحمر لا صمت.
  reward_risk_min?: number          // صفر = لا حارس للنسبة
  risk_budget_bounds?: [number, number]  // [الأرضيّة، السقف] كنسبةٍ من الميزانيّة
  // حمولة الرفض من `execution.order.rejected` — كانت تُقرأ بـcast في
  // `Execution.tsx`، فصارت معلَنةً هنا لتُقرأ مرّةً واحدةً بأمان.
  //
  // ⚠️ الرقم والعتبة **ليسا في الجذر**: ينشرهما ٥٥٢ داخل `rejection` و`barrier`
  // معًا (`atoms/قسم 550-599/552_مدقق_الأمر/atom.py:321-340`). وقراءتهما من
  // الجذر تُخرج `undefined` أبدًا — أي بطاقةً تقول «انرفض» بلا رقمٍ إلى الأبد،
  // وهي بعينها الكذبة التي كُتب حارس الحقول لأجلها. `barrier` أقدم ويحتفظ به
  // قارئوه (٥٥٢ و٥٨٠)، و`rejection` أُضيف ٢٠٢٦-٠٩-١٦ على شكل ٤٦٦ — يُقرأ
  // الأحدث أوّلًا والأقدم احتياطًا.
  stage?: string
  rejection?: { reason?: string; stage?: string; value?: number; threshold?: number }
  barrier?: { name?: string; reason?: string; value?: number; threshold?: number }
  ts: number
}
export interface ExecManageRec {
  stage: 'intent' | 'command' | 'written'
  action?: string; ticket?: number | string; symbol?: string; side?: string
  stop_loss?: number; volume?: number; reason?: string; r_multiple?: number
  ts: number
}
export interface ExecOutcomeRec {
  symbol?: string; side?: string; profit?: number; volume?: number
  entry_price?: number; exit_price?: number; event_type?: string; reason?: string
  ticket?: number | string
  ts: number
}

export type Conn = 'connecting' | 'live' | 'down'

interface StoreState {
  atoms: Record<number, AtomRec>
  metrics: unknown
  streams: Record<string, unknown> // آخر قيمة لكل حدث أعمال (باسمه الكامل)
  // حزمة ج (ختم 22): آخر حمولة لكل (اسم حدث × رمز) — لأحداث سلسلة القرار/التنفيذ/تفعيل
  // الأصل التي `streams` لا تكفيها لأنها عامّة (رمز واحد يدهس رمزًا آخر). المفتاح
  // الخارجي اسم الحدث الكامل، الداخلي الرمز — بلا حساب، نقل ما وصل فقط.
  symbolStreams: Record<string, Record<string, unknown>>
  // عدّاد «رفض بلا أصل» (perpetual.entry.rejected بسبب NO_PARENT_AUTHORITY) لكل رمز — ج٥
  assetRejectCounts: Record<string, number>
  market: Record<string, { bid: number; ask: number; ts: number }> // أسعار حسب الرمز
  // ٢٠٢٦-٠٨-٣١ (ختم NQ): سعر الوسيط (ميتاتريدر) منفصل تمامًا عن سعر المرجع.
  // `market` أعلاه هو المرجع (سي‑تريدر) الذي يقود التحليل؛ وهذا سعر التنفيذ
  // الفعليّ بسبريده — للعرض على الشارت واللوحة فقط، لا يدخل حكمًا ولا تحليلًا.
  brokerMarket: Record<string, { bid: number; ask: number; spread: number; provider: string; ts: number }>
  // §١٨ — بطاقة القسم كما بناها section_contract؛ المفتاح حساب::وسيط::أصل::قسم
  sectionCards: Record<string, Record<string, unknown>>
  // بند أ١١ — جسم قسم التحليل المدموج من ١٦٦ (timeframe="section")؛ المفتاح حساب::رمز
  sectionFusion: Record<string, SectionFusionState>
  room: Record<string, DecisionRoom>
  analystsPanels: Record<string, AnalystsPanel>
  analysis: Record<string, AnalysisState> // آخر تحليل مُجمَّع حسب الرمز (من ١٦٦ دمج التحليل)
  structure: Record<string, StructureState> // آخر بنية حسب الرمز (من ٢١٠ ناشر البنية)
  liquidity: Record<string, LiquidityState> // آخر سيولة حسب الرمز (من ٢٦٠ ناشر السيولة)
  liquidityUnits: Record<string, LiquidityUnitsState> // لوحة وحدات السيولة (من ٢٥٠ مدير السيولة)
  stats: Record<string, StatsState> // آخر إحصاء مُجمَّع حسب الرمز (من ٣٠٠ مدير الإحصاء)
  probability: Record<string, ProbabilityState> // آخر احتمالات حسب الرمز (من ٣٥٠ مدير الاحتمالات)
  risk: RiskState | null // حالة المخاطر الموحّدة العالمية (من ٥٠٠ مدير المخاطر)
  gate: GateState | null // حالة بوّابة التنفيذ الحقيقيّة (من ٥٥٢ — execution.gate.state)
  execution: ExecutionState | null // حالة التنفيذ الموحّدة (من ٥٥٠ مدير التنفيذ — execution.unified.state)
  execOrders: ExecOrderRec[]   // سجلّ دوّار: أوامر (انبنى/مقفول/نهائي/مرفوض) — أحدث أولًا
  execManage: ExecManageRec[]  // سجلّ دوّار: الإدارة الذكية (نيّة/أمر/انكتب للجسر)
  execOutcomes: ExecOutcomeRec[] // سجلّ دوّار: نتائج محقَّقة (من ٥٦٣ تأكيد التنفيذ)
  // أحداث مهمّة (سجل دوّار للمراقبة). `detail` من حمولة الحدث (رمز · جهة · سبب)،
  // و`n` يدمج التكرار المتتالي المتطابق بعدّاد بدل رشق أسطر متطابقة (بند 17 بدفتر 97).
  events: Array<{ id: number; name: string; detail?: string; ts: number; n: number }>
  flows: Record<string, number>    // آخر وقت (performance.now) انطلق فيه كل حدث — لتدفّق الشبكة
  flowStats: Record<string, { n: number; first: number; last: number }> // نبض كل تيار — لإنذار الصمت
  conn: Conn
  lastMsgAt: number                // performance.now() لآخر رسالة (للطزاجة)
  // ٢٠٢٦-٠٩-٠٩ (ختم NQ): صحّة البثّ نفسه — النواة تعلن الفقد ولم يكن يُقرأ.
  // `missed` تُحسب من قفزات `stream_sequence` (تكشف الفقد حتى لو ضاعت رسالة
  // الإعلان نفسها)، و`droppedTotal` رقم النواة المعلن، و`gaps` عدد مرّات
  // الإعلان. صفرٌ هنا معناه «لم يُفقد شيء»، و`seq=0` معناه «لم تصل رسالة بعد».
  streamSeq: number
  streamMissed: number
  streamDropped: number
  streamGaps: number
  // ما أسقطته **اللوحة نفسها** حين امتلأ طابورها — لا النواة. يُفصل عن
  // `streamDropped` عمدًا: فقدٌ عند النواة عطبٌ في النظام، وفقدٌ هنا عطبٌ في
  // الشاشة. خلطهما يوجّه البحث إلى المكان الخطأ.
  clientDropped: number
  // ٢٠٢٦-٠٩-١٦ — أرقام الذرّات المستبعَدة من الإقلاع، من `/gov/boot-report`.
  // ليست في `atoms` لأنّ النواة لم تُحمّلها، فكانت **غائبة عن اللوحة كلّها**:
  // لا خضراء ولا حمراء. وقائمة القسم تعدّ المحمَّل وحده فتبدو مكتملة — غيابٌ
  // يُقرأ اكتمالًا. تُحفظ هنا ليعلنها كل قسمٍ يخصّه رقمٌ منها.
  excluded: number[]
  namesAr: Record<number, string>
  selectedId: number | null        // الذرة المفتوحة تفاصيلها (من الشبكة أو القائمة)
  /** لحظةُ وصول آخر قراءةٍ كاملة من `/gov/atoms` — صفرٌ يعني «لم تصل بعد». */
  snapshotAt: number
  setSnapshot: (atoms: AtomRec[], metrics?: unknown) => void
  resetLive: () => void
  setEvent: (name: string, payload: unknown) => void
  setSymbolStream: (event: string, symbol: string, payload: unknown) => void
  bumpAssetReject: (symbol: string) => void
  setConn: (c: Conn) => void
  setNames: (n: Record<number, string>) => void
  markMsg: () => void
  /** يسجّل صحّة البثّ من ترويسة الرسالة: التسلسل · المُسقَط المعلن · راية الفجوة. */
  markStream: (seq?: number, dropped?: number, gap?: boolean) => void
  /** يسجّل رسائل أسقطها طابور اللوحة نفسه — تُعلَن ولا تُبتلع. */
  markClientDrop: (n: number) => void
  setExcluded: (ids: number[]) => void
  select: (id: number | null) => void
  setMarketTick: (symbol: string, bid: number, ask: number, ts: number) => void
  setBrokerTick: (symbol: string, bid: number, ask: number, spread: number, provider: string, ts: number) => void
  setSectionCard: (key: string, card: Record<string, unknown>) => void
  setSectionFusion: (key: string, body: SectionFusionState) => void
  setRoom: (key: string, room: DecisionRoom) => void
  setAnalysts: (key: string, panel: AnalystsPanel) => void
  setAnalysis: (symbol: string, s: AnalysisState) => void
  setStructure: (symbol: string, s: StructureState) => void
  setLiquidity: (symbol: string, s: LiquidityState) => void
  setLiquidityUnits: (symbol: string, s: LiquidityUnitsState) => void
  setStats: (symbol: string, s: StatsState) => void
  setProbability: (symbol: string, s: ProbabilityState) => void
  setRisk: (s: RiskState) => void
  setGate: (s: GateState) => void
  setExecution: (s: ExecutionState) => void
  pushExecOrder: (r: ExecOrderRec) => void
  pushExecManage: (r: ExecManageRec) => void
  pushExecOutcome: (r: ExecOutcomeRec) => void
  pushEvent: (name: string, detail?: string) => void
  bumpFlows: (names: string[]) => void
}

export const useStore = create<StoreState>((set) => ({
  atoms: {},
  snapshotAt: 0,
  metrics: null,
  streams: {},
  symbolStreams: {},
  assetRejectCounts: {},
  market: {},
  brokerMarket: {},
  sectionCards: {},
  sectionFusion: {},
  room: {},
  analystsPanels: {},
  analysis: {},
  structure: {},
  liquidity: {},
  liquidityUnits: {},
  stats: {},
  probability: {},
  risk: null,
  gate: null,
  execution: null,
  execOrders: [],
  execManage: [],
  execOutcomes: [],
  events: [],
  flows: {},
  flowStats: {},
  conn: 'connecting',
  lastMsgAt: 0,
  streamSeq: 0,
  streamMissed: 0,
  streamDropped: 0,
  streamGaps: 0,
  clientDropped: 0,
  excluded: [],
  namesAr: {},
  selectedId: null,
  setSnapshot: (atoms, metrics) =>
    set((s) => {
      const map: Record<number, AtomRec> = {}
      for (const a of atoms) map[a.id] = a
      // ٢٠٢٦-٠٩-٢٣ — `snapshotAt`: لحظةُ وصول قراءةِ `/gov/atoms` الكاملة.
      // وبدونها لا يجوز الحكم على ذرّةٍ بلا صحّة: قبل أوّل لقطةٍ يكون البثّ
      // الحيّ قد أنشأ مدخلاتٍ بلا صحّةٍ بعد، فيُقرأ **«لم تُبلّغ قطّ»** وهو
      // «لم تصل بعد». وقعتُ فيها بنفسي: اثنتا عشرةَ ذرّةً أُعلنت ساكتةً في
      // النافذة الأولى بعد التحميل — وهي نفسُ الكذبة التي أُصلحها.
      return { atoms: map, metrics: metrics ?? s.metrics, snapshotAt: Date.now() }
    }),
  resetLive: () => set({
    atoms: {}, metrics: null, streams: {}, symbolStreams: {}, assetRejectCounts: {},
    market: {}, brokerMarket: {}, sectionCards: {}, sectionFusion: {}, room: {}, analystsPanels: {},
    analysis: {}, structure: {}, liquidity: {}, liquidityUnits: {}, stats: {}, probability: {},
    risk: null, gate: null, execution: null,
    execOrders: [], execManage: [], execOutcomes: [], events: [], flows: {},
    flowStats: {}, conn: 'connecting', lastMsgAt: 0,
  streamSeq: 0, streamMissed: 0, streamDropped: 0, streamGaps: 0, clientDropped: 0,
  }),
  setEvent: (name, payload) => set((s) => ({ streams: { ...s.streams, [name]: payload } })),

  setSymbolStream: (event, symbol, payload) => set((s) => ({
    symbolStreams: { ...s.symbolStreams, [event]: { ...(s.symbolStreams[event] ?? {}), [symbol]: payload } },
  })),
  bumpAssetReject: (symbol) => set((s) => ({
    assetRejectCounts: { ...s.assetRejectCounts, [symbol]: (s.assetRejectCounts[symbol] ?? 0) + 1 },
  })),
  setConn: (conn) => set({ conn }),
  setNames: (namesAr) => set({ namesAr }),
  markMsg: () => set({ lastMsgAt: performance.now() }),
  markStream: (seq, dropped, gap) => set((s) => {
    // قفزة بالتسلسل تكشف الفقد حتى لو ضاعت رسالة الإعلان نفسها. أوّل رسالة
    // (seq السابق = 0) تُلتقط كنقطة بداية لا كفقد، وكذلك تراجع التسلسل بعد
    // إقلاع النواة من جديد — لا نخترع فقدًا من إعادة تشغيل.
    const prev = s.streamSeq
    const missed = (seq != null && prev > 0 && seq > prev + 1) ? seq - prev - 1 : 0
    return {
      streamSeq: seq ?? prev,
      streamMissed: s.streamMissed + missed,
      streamDropped: typeof dropped === 'number' ? dropped : s.streamDropped,
      streamGaps: s.streamGaps + (gap === true ? 1 : 0),
    }
  }),
  markClientDrop: (n) => set((s) => (n > 0 ? { clientDropped: s.clientDropped + n } : s)),
  setExcluded: (excluded) => set({ excluded }),
  select: (selectedId) => set({ selectedId }),
  setMarketTick: (symbol, bid, ask, ts) => set((s) => ({ market: { ...s.market, [symbol]: { bid, ask, ts } } })),
  setBrokerTick: (symbol, bid, ask, spread, provider, ts) =>
    set((s) => ({ brokerMarket: { ...s.brokerMarket, [symbol]: { bid, ask, spread, provider, ts } } })),
  setSectionCard: (key, card) => set((s) => ({ sectionCards: { ...s.sectionCards, [key]: card } })),
  setSectionFusion: (key, body) => set((s) => ({ sectionFusion: { ...s.sectionFusion, [key]: body } })),
  setRoom: (key, room) => set((s) => ({ room: { ...s.room, [key]: room } })),
  setAnalysts: (key, panel) => set((s) => ({ analystsPanels: { ...s.analystsPanels, [key]: panel } })),
  setAnalysis: (symbol, a) => set((s) => ({ analysis: { ...s.analysis, [symbol]: a } })),
  setStructure: (symbol, a) => set((s) => ({ structure: { ...s.structure, [symbol]: a } })),
  setLiquidity: (symbol, a) => set((s) => ({ liquidity: { ...s.liquidity, [symbol]: a } })),
  setLiquidityUnits: (symbol, a) => set((s) => ({ liquidityUnits: { ...s.liquidityUnits, [symbol]: a } })),
  setStats: (symbol, a) => set((s) => ({ stats: { ...s.stats, [symbol]: a } })),
  setProbability: (symbol, a) => set((s) => ({ probability: { ...s.probability, [symbol]: a } })),
  setRisk: (a) => set({ risk: a }),
  setGate: (a) => set({ gate: a }),
  setExecution: (a) => set({ execution: a }),
  pushExecOrder: (r) => set((s) => ({ execOrders: [r, ...s.execOrders].slice(0, 40) })),
  pushExecManage: (r) => set((s) => ({ execManage: [r, ...s.execManage].slice(0, 40) })),
  pushExecOutcome: (r) => set((s) => ({ execOutcomes: [r, ...s.execOutcomes].slice(0, 40) })),
  pushEvent: (name, detail) => set((s) => {
    const head = s.events[0]
    // نفس الحدث بنفس التفصيل يتكرّر مباشرة ⇒ عدّاد على السطر نفسه، لا سطر جديد
    if (head && head.name === name && (head.detail ?? '') === (detail ?? '')) {
      return { events: [{ ...head, ts: Date.now(), n: head.n + 1 }, ...s.events.slice(1)] }
    }
    const e = { id: (head?.id ?? 0) + 1, name, detail, ts: Date.now(), n: 1 }
    const arr = [e, ...s.events]
    return { events: arr.length > 60 ? arr.slice(0, 60) : arr }
  }),
  bumpFlows: (names) => set((s) => {
    if (!names.length) return {} as Partial<StoreState>
    const t = performance.now()
    const f = { ...s.flows }
    const fs = { ...s.flowStats }
    for (const n of names) {
      f[n] = t
      const cur = fs[n]
      fs[n] = cur ? { n: cur.n + 1, first: cur.first, last: t } : { n: 1, first: t, last: t }
    }
    return { flows: f, flowStats: fs }
  }),
}))
