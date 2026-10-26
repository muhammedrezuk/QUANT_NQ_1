// التنفيذ (863) — عيلة 550: بوّابة الأوامر · أسباب الحجب · الإدارة الذكية · النتائج.
// بند 15 شقّ 2 (دفتر 97): «من نفس المكان أقدر أشيل المنع بمجرّد ضغطة» — زرّا فتح/إقفال
// البوّابة هون، بنفس مسار «تحكّم» (بوّابة الأوامر 901 بتأكيد مزدوج — لا مسار جديد).
// بند 14: رسم سلسلة الذرّات نزل لطبقة مطويّة تُفتح عند الطلب — الجواب البسيط أوّلًا.
// بند ١٨ (ورقة ٩٩) — التسع بوابات الموحّدة: حُصرت من الكود فعليًّا (لا من الورق):
// كل ذرّة تملك سلطة نعم/لا حقيقية على المسار قرار→أمر→منصّة.
//   قرار:  414 بطاقة استمرار الاتّجاه ← 467 مرسل القرار
//   أمر:   527 حلّ الرمز ← 526 الهامش ← 551 البناء ← 525 شرعية الستوب ← 552 البوّابة
//   كتابة: 601 كاتب الجسر · إدارة: 575 مرسل الإدارة
// لكل بطاقة: آخر رفض من أحداثها الحقيقية + زرّ فتح/إقفال حيث يدعمه الكود (552/575 عبر 901 حصراً).
// ٢٠٢٦-١٠-٠٨ (فكّ الأقسام عن القرار، ختم المالك «NQ»): 454 فلتر القرار و466 موافقته و581 محرّك الهدف أُرشفت — حلّت محلّهما 414 و467، ورُفعت لوحة 581.
import { useState } from 'react'
import { useStore } from '../core/store'
import { arabicVisible, arabicHealth, cardStatusAr } from '../core/arabic'
import { confirmedCommand } from '../core/commands'
import { SectionConfigTable } from '../components/SectionAtoms'
import { useCards } from '../components/TrendCard'
import CardJourney from './CardJourney'

const num = (n?: number | null, dp = 2) =>
  n == null ? '—' : n.toLocaleString('ar-EG-u-nu-latn', { maximumFractionDigits: dp })

const time = (ts: number) => new Date(ts).toLocaleTimeString('ar-EG-u-nu-latn', { hour12: false })

const SIDE: Record<string, [string, string]> = { BUY: ['شراء', 'var(--green)'], SELL: ['بيع', 'var(--red)'] }

const KIND: Record<string, [string, string]> = {
  built: ['انبنى', 'var(--dim)'],
  skipped: ['ما بُني — توقّف قبل البوّابة', 'var(--amber)'],
  final: ['انبعت للمنصّة', 'var(--green)'],
  rejected: ['مرفوض بالبوّابة', 'var(--red)'],
}

// كل أسباب رفض 552 الحقيقيّة — من order_validation.py و_on_built نفسها
// (atom.py) لا افتراض. «disabled»/«halted» هنّ بالضبط سبب «البوّابة مقفولة».
const REJECT: Record<string, string> = {
  // order_validation.py — فحص شكل الأمر قبل أي قرار بوّابة
  BAD_ACTION: 'نوع أمر غير معروف',
  NO_SYMBOL: 'بلا رمز',
  BAD_SIDE: 'اتجاه غلط',
  BAD_VOLUME: 'حجم غلط',
  NO_TICKET: 'أمر تعديل/إغلاق بلا تذكرة صفقة',
  BAD_PRICE: 'سعر غلط',
  NO_STOP: 'بلا وقف خسارة',
  NO_TARGET: 'بلا هدف',
  BUY_LEVELS: 'مستويات الشراء غلط (الوقف لازم تحت السعر والهدف فوقه)',
  SELL_LEVELS: 'مستويات البيع غلط (الهدف لازم تحت السعر والوقف فوقه)',
  NO_BUDGET: 'مركز دائم بلا ميزانيّة مخاطرة موجبة',
  PERPETUAL_NO_TP: 'مركز دائم ومعه هدف — ممنوع، المركز الدائم ما بينسكر بهدف',
  // atom.py (552 نفسها) — قرار البوّابة بعد صحّة الشكل
  disabled: 'البوّابة مقفولة — قرارك إنت',
  halted: 'إيقاف طارئ فعّال',
  MISSING_ACCOUNT_BROKER_OR_SYMBOL: 'هويّة الحساب أو الوسيط أو الرمز ناقصة',
  MISSING_MAGIC: 'رقم تعريف الأمر (magic) مفقود',
  SYMBOL_NOT_ALLOWED: 'الرمز غير مسموح بقائمة الأصول',
  SPREAD_TOO_WIDE: 'الفرق السعريّ أوسع من الحدّ',
  CLOCK_NOT_SYNCED: 'ساعة النظام غير متزامنة',
  RECONCILIATION_NOT_MATCHED: 'مراكز المنصّة ما تطابقت مع سجلّنا بعد',
  REFERENCE_NOT_USABLE: 'السعر المرجعي غير صالح للاستعمال',
  EXPOSURE_STATE_NOT_USABLE: 'حالة التعرّض غير جاهزة لفتح مركز جديد',
}

// أسباب توقّف 551 (باني الأمر) الخمسة — لا يصل حتى إلى البوّابة أصلًا
const SKIP_REASON: Record<string, string> = {
  UPSTREAM_REJECTED: 'مرفوض من فوق — ما اعتُمد القرار',
  BAD_SYMBOL_OR_SIDE: 'رمز أو جهة غير صالحة',
  NO_SIZE_YET: 'ما وصل تحجيم للّوت بعد',
  INCOMPLETE_SIZE_DATA: 'بيانات التحجيم ناقصة (سعر/حجم/وقف)',
  INVALID_RISK_DISTANCE: 'مسافة المخاطرة غير صالحة (الوقف بالجهة الغلط)',
}

// ── بند ١٨: قواميس أسباب كل بوّابة — من كود ذرّتها نفسه، لا افتراض ──
// ٢٠٢٦-١٠-٠٨ (فكّ الأقسام عن القرار، ختم المالك «NQ»): قاموسا حواجز 454 وموافقة 466 حُذفا مع أرشفتهما؛ وأسباب 414 من `core/arabic.ts`.

// 467 مرسل القرار (`atoms/قسم 450-499/467_إرسال_القرار/atom.py:27-31`)
const DISPATCH_REASON: Record<string, string> = {
  NOT_APPROVED: 'الموافقة غير معتمدة',
  SIDE_UNKNOWN: 'جهة القرار غير معروفة',
  NO_DECISION_IDENTITY: 'بلا معرّف قرار',
}

// 527 بوّابة الرموز (stage=SYMBOL_RESOLUTION)
const SYMBOL_REASON: Record<string, string> = {
  SYMBOL_RESOLUTION_TIMEOUT: 'مهلة حلّ الرمز انتهت بلا جواب',
  MISSING_REQUEST_ID: 'بلا معرّف طلب',
  DUPLICATE_REQUEST_ID: 'معرّف الطلب مكرّر',
  MISSING_ACCOUNT_OR_SYMBOL: 'الحساب أو الرمز ناقص',
  SYMBOL_UNRESOLVED: 'الرمز ما انحلّ لهويّة وسيط حقيقية',
}

// 526 حارس الهامش (حكم risk.validation.completed)
const MARGIN_REASON: Record<string, string> = {
  MISSING_OR_DUPLICATE_REQUEST_ID: 'معرّف الطلب مفقود أو مكرّر',
  ACCOUNT_MARGIN_DATA_MISSING: 'بيانات هامش الحساب مفقودة',
  ACCOUNT_STATE_STALE: 'بيانات الحساب متقادمة',
  FREE_MARGIN_MISSING: 'الهامش الحرّ غير معروف',
  MARGIN_PER_VOLUME_MISSING: 'هامش اللوت غير معروف من الوسيط',
  INSUFFICIENT_FREE_MARGIN: 'الهامش الحرّ ما بيكفي للأمر',
  MANAGEMENT_NO_NEW_MARGIN: 'أمر إدارة — ما بيحتاج هامش جديد (مسموح)',
}

// 525 شرعيّة الستوب (stage=STOP_LEGALITY) — يكمّل قاموس 552 بأسبابه الخاصة
const STOP_REASON: Record<string, string> = {
  BAD_ACCOUNT_SYMBOL_OR_SIDE: 'الحساب أو الرمز أو الجهة ناقصة',
  NO_SYMBOL_SPECS: 'مواصفات الرمز ما وصلت من الوسيط بعد',
  INCOMPLETE_ORDER: 'الأمر ناقص (سعر/حجم/وقف)',
  VOLUME_BELOW_MINIMUM: 'الحجم تحت أدنى حدّ الوسيط',
  VOLUME_ABOVE_MAXIMUM: 'الحجم فوق أقصى حدّ الوسيط',
  BUY_LEVELS: 'مستويات الشراء غلط (الوقف لازم تحت السعر)',
  SELL_LEVELS: 'مستويات البيع غلط (الوقف لازم فوق السعر)',
  STOP_LEGALITY_VOLUME_TOO_SMALL: 'بعد تصحيح مسافة الوقف صار الحجم أصغر من المسموح',
}

// 601 كاتب جسر الدماغ (platform.brain_signal.write_failed / halted)
const WRITE_REASON: Record<string, string> = {
  ACCOUNT_ID_MISMATCH: 'رقم الحساب لا يطابق حساب الجسر',
  MISSING_ACCOUNT_ID: 'رقم الحساب مفقود',
  SYMBOL_UNRESOLVED: 'رمز الوسيط غير محلول',
  MISSING_REQUEST_ID_OR_BAD_ACTION: 'معرّف الطلب مفقود أو نوع الفعل غلط',
  MISSING_OR_FOREIGN_MAGIC: 'الرقم التعريفي (magic) مفقود أو غريب',
  CURRENT_ACCOUNTS_UNAVAILABLE_OR_BLOCKED: 'حسابات الجسر الحالية غير متاحة أو محجوبة',
  BRIDGE_ACCOUNT_ID_MISMATCH_OR_BLOCKED: 'حساب الجسر لا يطابق أو محجوب',
}

// 575 مرسل الإدارة (execution.command.failed)
const MANAGE_FAIL_REASON: Record<string, string> = {
  MANAGEMENT_GATE_DISABLED: 'مرسل الإدارة مقفول — التعديل ما انبعت',
}

const MANAGE_ACTION: Record<string, string> = {
  MODIFY_SL: 'تعديل الوقف',
  CLOSE_PARTIAL: 'إغلاق جزئي',
  CLOSE: 'إغلاق',
}

const MANAGE_REASON: Record<string, string> = {
  breakeven: 'نقل الوقف للتعادل',
  trailing: 'تتبّع الوقف مع البنية',
  partial_take: 'جني ربح جزئي',
  // ٢٠٢٦-١٠-٠٥ (ختم المالك «nq اعتمدناها»): أسباب ٥٧٤ كما يرسلها — ومعها سببا الإدارة على
  // مستويات التحليل (الوقف على المستوى الأوّل، وتتبّع قمم/قيعان الربع ساعة).
  partial_take_last_lot: 'خروج كامل عند الهدف',
  BREAKEVEN_AT_FIRST_TARGET: 'الوقف للتعادل بعد أوّل هدف',
  STOP_LOCKED_AT_TARGET_1: 'الوقف على الهدف الأوّل',
  STOP_LOCKED_AT_LEVEL_1: 'الوقف على المستوى الأوّل من التحليل',
  STOP_TRAIL_STRUCTURE_15M: 'الوقف يتبع بنية الربع ساعة',
}

const MANAGE_STAGE: Record<string, [string, string]> = {
  intent: ['نيّة', 'var(--dim)'],
  command: ['أمر', 'var(--amber)'],
  written: ['انكتب للجسر', 'var(--green)'],
}

const OUTCOME_TYPE: Record<string, string> = {
  CLOSED: 'إغلاق كامل',
  PARTIAL: 'إغلاق جزئي',
}

// سلسلة فتح الصفقة + سلسلة الإدارة — بترتيب مرور الأمر (المعرّف = رقم الذرة الحقيقي)
// ٢٠٢٦-١٠-٠٨ (فكّ الأقسام عن القرار، ختم المالك «NQ»): رأس السلسلة صار البطاقة 414، و555 طالب أمر الدخول بعد 467.
const OPEN_CHAIN: [number, string][] = [
  [414, 'بطاقة الاتّجاه'], [467, 'مرسل القرار'], [555, 'طالب أمر الدخول'],
  [516, 'قاطع الأمان'], [512, 'الوقف الهيكلي'], [513, 'حجم اللوت'],
  [551, 'باني الأمر'], [552, 'المدقق (البوّابة)'], [601, 'كاتب الجسر'],
]
const MANAGE_CHAIN: [number, string][] = [
  [572, 'التعادل'], [574, 'الإغلاق الجزئي'],
  [570, 'مدير الإدارة'], [575, 'مرسل الإدارة'],
]

const HEALTH_COLOR: Record<string, string> = { healthy: 'green', degraded: 'amber', unhealthy: 'red' }

// ── بند ١٨: تعريف التسع بوابات — بترتيب مرور القرار/الأمر الحقيقي ──
interface GateDef {
  id: number
  name: string
  family: string
  role: string
  switchGate?: '552' | '575' // مفتاح 901 موجود بالكود لهاتين حصرًا (execution_gate)
}

const GATES: GateDef[] = [
  { id: 414, name: 'بطاقة استمرار الاتّجاه', family: 'قرار',
    role: 'تقرأ الحقائق الخام عند إغلاق كل شمعة ٥ دقائق وتقرّر: صفقة بجهتها ووقفها وهدفها، أو سببًا واحدًا لعدم الدخول.' },
  { id: 467, name: 'مرسل القرار', family: 'قرار',
    role: 'يمرّر موافقة البطاقة مرّةً واحدة إلى طالب أمر الدخول — الناقص الهويّة أو غير المعتمد يُحجب.' },
  { id: 527, name: 'بوّابة الرموز', family: 'أمر',
    role: 'يحلّ رمز الأمر لهويّة وسيط حقيقية قبل كل شيء — المجهول يُرفض.' },
  { id: 526, name: 'حارس الهامش', family: 'أمر',
    role: 'يفحص الهامش الحرّ ويحجزه قبل تمرير الأمر — هامش ما بيكفي = رفض.' },
  { id: 551, name: 'باني الأمر', family: 'أمر',
    role: 'يبني الأمر من القرار المعتمد والتحجيم — الناقص لا يُبنى أصلًا.' },
  { id: 525, name: 'شرعيّة الستوب', family: 'أمر',
    role: 'يفحص شرعية الوقف/الهدف ومسافات الوسيط — يصحّح ما يقبل التصحيح ويرفض الباقي.' },
  { id: 552, name: 'مدقّق الأمر (البوّابة)', family: 'أمر', switchGate: '552',
    role: 'البوّابة النهائية: أمر صالح + بوّابة مفتوحة = قرار نهائي ينبعت للجسر.' },
  { id: 601, name: 'كاتب جسر الدماغ', family: 'كتابة',
    role: 'يكتب القرار النهائي لجسر المنصّة — هوية الحساب والرمز والمعرّف لازم كاملة.' },
  { id: 575, name: 'مرسل الإدارة', family: 'إدارة', switchGate: '575',
    role: 'يبعت تعديلات الصفقات المفتوحة (تعادل·تتبّع·جني جزئي) — لا يفتح صفقة أبدًا.' },
]

const FAMILY_COLOR: Record<string, string> = { 'قرار': 'green', 'أمر': 'amber', 'كتابة': 'red', 'إدارة': 'grey' }

function GatesBoard() {
  const atoms = useStore((s) => s.atoms)
  const gate = useStore((s) => s.gate)
  const orders = useStore((s) => s.execOrders)
  // اشتراكات دقيقة — كل بوّابة تُقرأ من حدثها الحقيقي هي نفسها، لا استنتاج
  const cards = useCards()
  const gatePassed = useStore((s) => s.streams['decision.gate.passed']) as
    { symbol?: string } | undefined
  const gateBlocked = useStore((s) => s.streams['decision.gate.blocked']) as
    { symbol?: string; reject_reason?: string } | undefined
  const verdict = useStore((s) => s.streams['risk.validation.completed']) as
    { approved?: boolean; reason?: string } | undefined
  const writeFail = useStore((s) => s.streams['platform.brain_signal.write_failed']) as
    { reason?: string } | undefined
  const writeHalted = useStore((s) => s.streams['platform.brain_signal.halted']) as
    { reason?: string } | undefined
  const manageFail = useStore((s) => s.streams['execution.command.failed']) as
    { reason?: string } | undefined
  const [busy, setBusy] = useState<string>('')
  const [notes, setNotes] = useState<Record<number, string>>({})

  // نفس أمر «تحكّم» حرفيًّا: execution_gate عبر بوّابة الأوامر 901 بتأكيد مزدوج
  const setGateEnabled = async (def: GateDef, enabled: boolean) => {
    if (!def.switchGate) return
    setBusy(def.switchGate)
    const r = await confirmedCommand('execution_gate', { gate: def.switchGate, enabled })
    setNotes((n) => ({ ...n, [def.id]: r.ok ? `🟢 ${r.message ?? (enabled ? 'فُتحت' : 'أُقفلت')}` : `🛑 ${r.message ?? 'ما تمّ'}` }))
    setBusy('')
  }

  // آخر رفض من execution.order.rejected — التمييز بحقل stage الذي تضعه الذرّة نفسها:
  // 525 تكتب STOP_LEGALITY و586 تكتب SYMBOL_RESOLUTION و552 لا تكتب stage إطلاقًا.
  const lastReject = (stage: string | null): { reason?: string; symbol?: string } | undefined =>
    orders.find((o) => o.kind === 'rejected'
      && ((o as unknown as { stage?: string }).stage ?? null) === stage) as { reason?: string; symbol?: string } | undefined
  const lastSkip = orders.find((o) => o.kind === 'skipped')

  // حالة/آخر منع لكل بوّابة — من حدثها؛ وإلا من صحّة ذرّتها (بلا اختراع)
  const info = (def: GateDef): { status: string; color: string; refusal?: string } => {
    const a = atoms[def.id]
    const base = a == null
      ? { status: 'مو محمّلة بالنواة', color: 'grey' }
      : a.state !== 'running'
        ? { status: 'واقفة', color: 'red' }
        : { status: arabicHealth(a.health?.message) || 'شغّالة', color: HEALTH_COLOR[a.health?.state ?? ''] ?? 'grey' }
    switch (def.id) {
      case 414: {
        // آخر بطاقة لكلّ رمز — «مفتوحة» تعني صفقةً انبعتت، وغيرها سببُ عدم الدخول.
        const list = Object.values(cards).filter((c) => c?.symbol)
        const open = list.filter((c) => c.status === 'OPEN')
        const closed = list.filter((c) => c.status !== 'OPEN')
        if (open.length) return { ...base, status: `فتحت بطاقة ✓ — ${open.map((c) => c.symbol).join(' · ')}`, color: 'green' }
        return closed.length
          ? { ...base, refusal: closed.map((c) => `${cardStatusAr(c.status)} — ${c.symbol}`).join(' · ') }
          : base
      }
      case 467: {
        const st = gatePassed
          ? { ...base, status: `مرّرت موافقة ✓${gatePassed.symbol ? ` — ${gatePassed.symbol}` : ''}`, color: 'green' }
          : base
        return gateBlocked?.reject_reason
          ? { ...st, refusal: `${DISPATCH_REASON[gateBlocked.reject_reason] ?? arabicVisible(gateBlocked.reject_reason, 'سبب غير معروف')}${gateBlocked.symbol ? ` — ${gateBlocked.symbol}` : ''}` }
          : st
      }
      case 527: {
        const r = lastReject('SYMBOL_RESOLUTION')
        return r?.reason ? { ...base, refusal: `${SYMBOL_REASON[r.reason] ?? arabicVisible(r.reason, 'سبب غير معروف')}${r.symbol ? ` — ${r.symbol}` : ''}` } : base
      }
      case 526: {
        if (verdict?.approved === false && verdict.reason) {
          return { ...base, refusal: MARGIN_REASON[verdict.reason] ?? arabicVisible(verdict.reason, 'سبب غير مترجَم') }
        }
        if (verdict?.approved === true) return { ...base, status: 'وافق على آخر فحص هامش ✓', color: 'green' }
        return base
      }
      case 551: {
        return lastSkip?.reason
          ? { ...base, refusal: `${SKIP_REASON[lastSkip.reason] ?? arabicVisible(lastSkip.reason, 'سبب غير مترجَم')}${lastSkip.symbol ? ` — ${lastSkip.symbol}` : ''}` }
          : base
      }
      case 525: {
        const r = lastReject('STOP_LEGALITY')
        return r?.reason ? { ...base, refusal: `${STOP_REASON[r.reason] ?? arabicVisible(r.reason, 'سبب غير مترجَم')}${r.symbol ? ` — ${r.symbol}` : ''}` } : base
      }
      case 552: {
        const halted = gate?.status === 'HALTED' || gate?.status === 'PARTIAL_HALT'
        const open = gate?.status === 'LIVE'
        const r = lastReject(null)
        const refusal = r?.reason ? `${REJECT[r.reason] ?? arabicVisible(r.reason, 'سبب غير مترجَم')}${r.symbol ? ` — ${r.symbol}` : ''}` : undefined
        if (halted) return { status: '🛑 إيقاف طارئ — الأوامر بتضلّ مقفولة', color: 'red', refusal }
        if (open) return { status: '⚠️ مفتوحة — الأمر الصالح بينبعت للمنصّة فعليًّا', color: 'red', refusal }
        if (gate) return { status: '🔒 مقفولة — كل أمر بيُرفض جوّاها، ولا صفقة بتنفتح', color: 'green', refusal }
        return { ...base, refusal }
      }
      case 601: {
        if (writeHalted) return { ...base, refusal: 'موقوف بالطوارئ — ما بيكتب شي للجسر' }
        if (writeFail?.reason) return { ...base, refusal: WRITE_REASON[writeFail.reason] ?? arabicVisible(writeFail.reason, 'سبب غير مترجَم') }
        return base
      }
      case 575: {
        const disabled = (a?.health?.message ?? '').includes('DISABLED')
        const refusal = manageFail?.reason
          ? MANAGE_FAIL_REASON[manageFail.reason] ?? arabicVisible(manageFail.reason, 'سبب غير مترجَم')
          : undefined
        if (a && disabled) return { status: '🔒 مقفول — التعديلات ما بتنبعت', color: 'amber', refusal }
        if (a && a.state === 'running') return { status: 'شغّال — يبعت تعديلات الصفقات المفتوحة', color: 'green', refusal }
        return { ...base, refusal }
      }
      default: return base
    }
  }

  // مفتاح الفتح/الإقفال: حالة 552 من حدث بوّابتها، و575 من صحّة ذرّته (DISABLED)
  const isOpen = (def: GateDef): boolean | null => {
    if (def.switchGate === '552') return gate ? gate.status === 'LIVE' : null
    if (def.switchGate === '575') {
      const a = atoms[575]
      if (!a) return null
      return a.state === 'running' && !(a.health?.message ?? '').includes('DISABLED')
    }
    return null
  }

  return (
    <div className="scard" style={{ padding: 0, overflow: 'hidden' }}>
      <div style={{ padding: '11px 14px', borderBottom: '1px solid var(--glassb)' }}>
        <div className="st" style={{ fontWeight: 700 }}>🚧 بوابات القرار والتنفيذ التسع — بترتيب مرور الأمر</div>
        <div className="ss dim">
          كل بطاقة تقول سبب آخر منع من أحداث بوّابتها الحقيقية. المفاتيح موجودة حيث يدعمها الكود (552 و575 عبر بوّابة الأوامر 901
          بتأكيد مزدوج). أوّل بوّابتين قرار: البطاقة 414 تقرّر، ومرسل القرار 467 يمرّر — وتفصيل البطاقة كاملًا بصفحة «القرار».
        </div>
      </div>
      <div className="cards" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(290px, 1fr))', padding: 10 }}>
        {GATES.map((def, i) => {
          const st = info(def)
          const open = isOpen(def)
          return (
            <div className="scard" key={def.id} style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
              <div style={{ display: 'flex', alignItems: 'baseline', gap: 8, flexWrap: 'wrap' }}>
                <span className="num dim" style={{ fontSize: 11 }}>{i + 1}</span>
                <b style={{ fontSize: 14.5 }}>{def.name}</b>
                <span className="num dim" style={{ fontSize: 11 }}>#{def.id}</span>
                <span className={`pill ${FAMILY_COLOR[def.family]}`} style={{ fontSize: 11, marginInlineStart: 'auto' }}>{def.family}</span>
              </div>
              <div className="ss dim" style={{ marginTop: 0 }}>{def.role}</div>
              <div style={{ fontSize: 13.5, color: `var(--${st.color})`, fontWeight: 600 }}>{st.status}</div>
              {st.refusal ? (
                <div style={{ fontSize: 13, color: 'var(--red)' }}>آخر منع: {st.refusal}</div>
              ) : (
                <div className="ss dim" style={{ marginTop: 0 }}>ما في منع مسجَّل من أحداثها بهالجلسة</div>
              )}
              {def.switchGate ? (
                <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap', marginTop: 2 }}>
                  {open === true
                    ? <button className="btn" disabled={busy === def.switchGate} onClick={() => void setGateEnabled(def, false)}>⏹️ سكّرها</button>
                    : <button className="btn" disabled={busy === def.switchGate} onClick={() => void setGateEnabled(def, true)}>▶️ افتحها{def.id === 552 ? ' — بيصير الأمر الصالح ينبعت فعليًّا' : ''}</button>}
                  {notes[def.id] ? <span style={{ fontSize: 12.5 }}>{notes[def.id]}</span> : null}
                </div>
              ) : null}
            </div>
          )
        })}
      </div>
      <div className="ss dim" style={{ padding: '0 14px 10px' }}>
        الحصر من الكود لا من الورق: هدول التسع وحدهنّ يملكن سلطة نعم/لا على مسار قرار→أمر→منصّة.
        باقي المحطّات (تحجيم 513 · وقف هيكلي 512 · قاطع أمان 516) تُغذّي ولا تبوّب — وقاطع الأمان له بطاقته بقسم «المخاطر».
      </div>
    </div>
  )
}

// ٢٠٢٦-١٠-٠٨ (فكّ الأقسام عن القرار، ختم المالك «NQ»): لوحة «المركز والهدف الدائم» حُذفت — ناشرها الوحيد 581 أُرشف، فكانت تقول «لم يصل» أبدًا.

function Chain({ title, ids }: { title: string; ids: [number, string][] }) {
  const atoms = useStore((s) => s.atoms)
  return (
    <div className="scard">
      <div className="st">{title}</div>
      <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 6, marginTop: 8 }}>
        {ids.map(([id, label], i) => {
          const a = atoms[id]
          const color = a ? (HEALTH_COLOR[a.health?.state ?? ''] ?? 'grey') : 'grey'
          return (
            <span key={id} style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              {i > 0 ? <span className="dim">←</span> : null}
              <span className={`pill ${color}`} title={a ? ('حالة متاحة في التشخيص') : 'الذرة مو محمّلة بالنواة'}>
                {label}
              </span>
            </span>
          )
        })}
      </div>
      <div className="ss dim">أخضر = شغّالة · كهرماني = مستنّية مدخل (طبيعي قبل أول أمر) · رمادي = مو محمّلة</div>
    </div>
  )
}

export default function Execution() {
  const execution = useStore((s) => s.execution)
  const orders = useStore((s) => s.execOrders)
  const manage = useStore((s) => s.execManage)
  const outcomes = useStore((s) => s.execOutcomes)
  const [showChains, setShowChains] = useState(false)

  const c = execution?.counts ?? {}

  return (
    <div className="section" style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
      {/* ٢٠٢٦-٠٩-١٨: رُفعت — رقما الحساب في ترويسة كل صفحة (`AccountsBar`)،
          وبقيتا في «المحافظ» و«السوق والاتصال» حيث الحساب هو الموضوع. */}
      <div className="ss dim">هالقسم يشتغل على حساب التنفيذ (ميتاتريدر). حساب التحليل فوق ما بينكتب عليه أمر.</div>

      {/* رحلة البطاقة — سؤال المالك ٢٠٢٦-٠٩-١٩: «كيف عم تنبنى وإيمتى بتمرق على ٥٥٥
          للجسر للمخازن». وُضعت هنا لا بتبويب جديد: حكمه ٢٠٢٦-٠٩-١٨ «خفّف»، والموضوع
          هو موضوع هالصفحة نفسها. المصدر /gov/card/journey — قراءة فقط.
          ⚠️ وُضعت أوّلًا بعد أن حطّيتها تحت البوّابات والأهداف فما لقاها: «ما شفتها
          وين حطيت البطاقة». الخلاصة قبل التفصيل — والقُمع هو خلاصة هالصفحة كلّها. */}
      <CardJourney />

      {/* بند ١٨ (ورقة ٩٩): بطاقة موحّدة لكل بوّابة — السبب + المفتاح + العيار بمكانها.
          بطاقة 552 المفردة القديمة صارت وحدة من تسع بنفس مسار 901 حرفيًّا. */}
      <GatesBoard />

      <div className="cards">
        <div className="scard"><div className="st">أوامر انبنت</div><div className="sv num">{c.built ?? 0}</div></div>
        <div className="scard"><div className="st">ما بُنيت (551 توقّف)</div><div className="sv num">{c.order_skipped ?? 0}</div></div>
        <div className="scard"><div className="st">مرفوضة بالبوّابة (552)</div><div className="sv num">{c.rejected ?? 0}</div></div>
        <div className="scard"><div className="st">قرار نهائي (بينبعت للجسر)</div><div className={`sv num ${(c.decision_finalized ?? 0) > 0 ? 'red' : ''}`}>{c.decision_finalized ?? 0}</div></div>
        <div className="scard"><div className="st">أوامر إدارة</div><div className="sv num">{c.manage_commands ?? 0}</div></div>
        <div className="scard"><div className="st">انكتبت للجسر</div><div className="sv num">{c.manage_queued ?? 0}</div></div>
        <div className="scard"><div className="st">نتائج محقَّقة</div><div className="sv num">{c.outcomes ?? 0}</div></div>
      </div>

      {(() => {
        const rejectR = execution?.reject_reasons ?? {}
        const skipR = execution?.skip_reasons ?? {}
        const rows = [
          ...Object.entries(rejectR).map(([reason, n]) => ({ reason, n, label: REJECT[reason] ?? arabicVisible(reason, 'سبب غير مترجَم'), src: 'البوّابة 552' })),
          ...Object.entries(skipR).map(([reason, n]) => ({ reason, n, label: SKIP_REASON[reason] ?? arabicVisible(reason, 'سبب غير مترجَم'), src: 'باني الأمر 551' })),
        ].sort((a, b) => b.n - a.n)
        if (rows.length === 0) return null
        return (
          <div className="scard">
            <div className="st">ليش ما وصلت الأوامر؟ — تجميع كل الأسباب من بداية التشغيل</div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 4, marginTop: 8 }}>
              {rows.map((r) => (
                <div key={r.src + r.reason} style={{ display: 'flex', gap: 10, alignItems: 'baseline', fontSize: 13 }}>
                  <span className="num" style={{ fontWeight: 700, minWidth: 28, textAlign: 'end' }}>{r.n}</span>
                  <span>{r.label}</span>
                  <span className="dim" style={{ fontSize: 11, marginInlineStart: 'auto' }}>{r.src}</span>
                </div>
              ))}
            </div>
          </div>
        )
      })()}

      {/* بند 14 (دفتر 97): الرسم التقنيّ لا يُدفن الجواب البسيط — طبقة مطويّة تُفتح عند الطلب */}
      <div>
        <button className="btn" style={{ fontSize: 12.5 }} onClick={() => setShowChains(!showChains)}>
          {showChains ? '▴ خبّي التفصيل التقني' : '▾ التفصيل التقني — سلسلة الذرّات (للفحص عند الحاجة، مو لازم لفهم الحالة)'}
        </button>
        {showChains ? (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10, marginTop: 10 }}>
            <Chain title="سلسلة فتح الصفقة (بترتيب مرور الأمر)" ids={OPEN_CHAIN} />
            <Chain title="سلسلة الإدارة الذكية (تعادل · تتبّع · جني جزئي)" ids={MANAGE_CHAIN} />
          </div>
        ) : null}
      </div>

      <div className="scard">
        <div className="st">آخر الأوامر (أحدث أولًا — وقت الوصول للوحة)</div>
        {orders.length === 0 ? (
          <div className="empty">ما مرق ولا أمر بعد — أوّل ما القرار يبعت طلب، بتشوفه هون لحظيًّا.</div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6, marginTop: 8 }}>
            {orders.map((o, i) => {
              const [sideTxt, sideColor] = SIDE[o.side ?? ''] ?? [o.side ?? '—', 'var(--dim)']
              const [kindTxt, kindColor] = KIND[o.kind]
              return (
                <div key={`${o.ts}-${i}`} style={{ display: 'flex', flexWrap: 'wrap', gap: 12, alignItems: 'baseline', borderBottom: '1px solid var(--glassb)', paddingBottom: 6 }}>
                  <span className="num dim" style={{ fontSize: 12 }}>{time(o.ts)}</span>
                  <span style={{ fontWeight: 700 }}>{o.symbol ?? '—'}</span>
                  <span style={{ color: sideColor, fontWeight: 700 }}>{sideTxt}</span>
                  {o.kind === 'rejected' ? (
                    <span style={{ color: 'var(--red)' }}>{REJECT[o.reason ?? ''] ?? arabicVisible(o.reason, 'سبب غير مترجَم')}</span>
                  ) : o.kind === 'skipped' ? (
                    <span style={{ color: 'var(--amber)' }}>{SKIP_REASON[o.reason ?? ''] ?? arabicVisible(o.reason, 'سبب غير مترجَم')}</span>
                  ) : (
                    <>
                      <span className="num">الحجم {num(o.volume)}</span>
                      <span className="num dim">السعر {num(o.reference_price, 6)}</span>
                      <span className="num" style={{ color: 'var(--red)' }}>وقف {num(o.stop_loss, 6)}</span>
                      <span className="num" style={{ color: 'var(--green)' }}>هدف {num(o.take_profit, 6)}</span>
                      {/* ٢٠٢٦-٠٩-١٨ — كان يُكتب «ر:م ٣٫٠» لكلّ أمر، وهو
                          **عيار ٥٥١ الثابت** (`atom.py:926`) لا نسبةُ هذا
                          الأمر. فيقرؤه المالك نسبةً محقّقة وهي نيّةٌ قبل أن
                          يوسّع ٥٢٥ الوقف. النسبة الحقيقيّة ينشرها ٥٥٢ على
                          الأرقام النهائيّة، فتُقدَّم — ويبقى العيار مسمّى
                          باسمه حين تغيب. */}
                      {o.reward_risk_min === 0 ? (
                        <span className="num" style={{ fontWeight: 700, color: 'var(--red)' }}
                          title="حارس النسبة مطفي بعياره (552) — أيّ نسبة بتمرق، حتى لو الهدف أقرب من الوقف">
                          ⛔ ما في حارس نسبة
                        </span>
                      ) : o.reward_risk_ratio != null ? (
                        <span className="num" style={{ fontWeight: 700 }}
                          title="نسبة الهدف إلى الوقف مقيسةً على أرقام هذا الأمر عند آخر بوّابة قبل الوسيط (552)">
                          ١:{num(o.reward_risk_ratio, 2)}
                        </span>
                      ) : o.reward_risk != null ? (
                        <span className="num dim"
                          title="عيار باني الأمر (551) — الحدّ المطلوب لكل الأوامر، مش نسبة هذا الأمر">
                          الحدّ {num(o.reward_risk, 1)}
                        </span>
                      ) : null}
                      {o.risk_dollars != null ? (
                        <span className="num dim"
                          title="المال المعرَّض لو ضرب الوقف — الحجم × مسافة الوقف × قيمة الوحدة (552)">
                          معرَّض ${num(o.risk_dollars, 2)}
                        </span>
                      ) : null}
                    </>
                  )}
                  <span style={{ color: kindColor, marginInlineStart: 'auto' }}>{kindTxt}</span>
                </div>
              )
            })}
          </div>
        )}
      </div>

      <div className="scard">
        <div className="st">الإدارة الذكية للصفقات المفتوحة (أحدث أولًا)</div>
        {manage.length === 0 ? (
          <div className="empty">ما في إدارة بعد — بتشتغل بس لمّا يكون في مركز مفتوح بالمنصّة.</div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6, marginTop: 8 }}>
            {manage.map((m, i) => {
              const [stageTxt, stageColor] = MANAGE_STAGE[m.stage]
              return (
                <div key={`${m.ts}-${i}`} style={{ display: 'flex', flexWrap: 'wrap', gap: 12, alignItems: 'baseline', borderBottom: '1px solid var(--glassb)', paddingBottom: 6 }}>
                  <span className="num dim" style={{ fontSize: 12 }}>{time(m.ts)}</span>
                  <span style={{ fontWeight: 700 }}>{m.symbol || '—'}</span>
                  <span>{MANAGE_ACTION[m.action ?? ''] ?? arabicVisible(m.action, 'إجراء غير مترجَم')}</span>
                  {m.reason ? <span className="dim">({MANAGE_REASON[m.reason] ?? arabicVisible(m.reason, 'سبب غير مترجَم')})</span> : null}
                  {m.stop_loss != null ? <span className="num">وقف جديد {num(m.stop_loss, 6)}</span> : null}
                  {m.volume != null ? <span className="num">حجم {num(m.volume)}</span> : null}
                  {m.ticket != null ? <span className="num dim">تذكرة {m.ticket}</span> : null}
                  <span style={{ color: stageColor, marginInlineStart: 'auto' }}>{stageTxt}</span>
                </div>
              )
            })}
          </div>
        )}
      </div>

      <div className="scard">
        <div className="st">النتائج المحقَّقة (من تأكيد التنفيذ 563)</div>
        {outcomes.length === 0 ? (
          <div className="empty">ما في نتيجة بعد — أوّل إغلاق (كامل أو جزئي) بيظهر هون بربحه أو خسارته.</div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6, marginTop: 8 }}>
            {outcomes.map((o, i) => {
              const [sideTxt, sideColor] = SIDE[o.side ?? ''] ?? [o.side ?? '—', 'var(--dim)']
              const win = (o.profit ?? 0) >= 0
              return (
                <div key={`${o.ts}-${i}`} style={{ display: 'flex', flexWrap: 'wrap', gap: 12, alignItems: 'baseline', borderBottom: '1px solid var(--glassb)', paddingBottom: 6 }}>
                  <span className="num dim" style={{ fontSize: 12 }}>{time(o.ts)}</span>
                  <span style={{ fontWeight: 700 }}>{o.symbol ?? '—'}</span>
                  <span style={{ color: sideColor }}>{sideTxt}</span>
                  <span className="dim">{OUTCOME_TYPE[o.event_type ?? ''] ?? arabicVisible(o.event_type, 'نتيجة غير مترجَمة')}</span>
                  <span className="num dim">دخول {num(o.entry_price, 6)} → خروج {num(o.exit_price, 6)}</span>
                  <span className="num" style={{ color: win ? 'var(--green)' : 'var(--red)', fontWeight: 700, marginInlineStart: 'auto' }}>
                    {win ? '+' : ''}{num(o.profit)}
                  </span>
                </div>
              )
            })}
          </div>
        )}
      </div>

      <div className="ss dim">
        كل شي بهالقسم من بثّ النواة الحيّ — الأصل الخام: أحداث «execution.*» و«trading.final_decision» (بتشوفها بقسم المراقبة).
        اللوحة ما بتخزّن: السجلّات دوّارة (آخر 40) وبتصفّر مع إعادة الفتح — التاريخ الكامل عند مصدره.
      </div>

      <SectionConfigTable from={550} to={600} title="معاملات ذرّات التنفيذ (550-599) — ضبط جماعي" />
    </div>
  )
}
