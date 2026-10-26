// اللوحة الجديدة — البناء من الصفر حول أربعة أسئلة (أمر المالك ٢٠٢٦-٠٨-٢٣)
// القواعد الـ21 من ورقة إعادة البناء + رؤية المالك المسجّلة حرفيًا.
// ⛔ الواجهة لا تحسب رقمًا واحدًا — كل معروض وصل بالحدث.
// ٢٠٢٦-٠٨-٢٩ (ختم NQ): أنماط هذه اللوحة (`dl-*`) كانت في `styles-dashboard.css`
// **بلا استيراد من أي ملف** — فلم تدخل حزمة البناء إطلاقًا، فظهر التبويب نصًّا
// خامًا بلا ألوان ولا تقطيع (مقيس: صفر ذكر لـ`dl-` في built/assets/*.css).
// يُستورَد هنا بنفس نمط `CryptoDashboard.tsx` مع `crypto-dashboard.css`.
import '../styles-dashboard.css'
import { useEffect, useMemo, useRef, useState } from 'react'
import { useStore } from '../core/store'
import { readGate } from '../core/gate'
import { dangerCommand } from '../core/commands'
import { CardBar, cardHint, useCardHealth, useCards } from '../components/TrendCard'
import { useTwinAccounts } from '../components/AccountsBar'
import { isWaitingMessage } from '../core/i18n'
// ٢٠٢٦-٠٩-٠٩ (ختم NQ): رسائل صحّة الذرّات كانت تُعرض خامًا بالإنكليزيّة هنا
// (`PENDING_OR_ORPHANED_RESOLUTION` · `CLOCK_HEARTBEAT_STALE` · `UNTRUSTED`…)
// على لوحة مواصفتها عربيّة كاملة. المترجم كان موجودًا وغير موصول بهذه الشاشة.
import { arabicHealth, cardStatusAr } from '../core/arabic'

// ═══════════════════════════════════════════════════════════
// الأدوات المشتركة
// ═══════════════════════════════════════════════════════════

type Color4 = 'green' | 'amber' | 'red' | 'grey'
const C: Record<Color4, string> = {
  green: 'var(--dl-green)',
  amber: 'var(--dl-amber)',
  red: 'var(--dl-red)',
  grey: 'var(--dl-grey)',
}

// ═══════════════════════════════════════════════════════════
// ١ — هل أنا بأمان؟ (الشريط العلوي)
// ═══════════════════════════════════════════════════════════

interface SafetyStatus {
  color: Color4
  label: string
  detail: string
}

function useSafety(): SafetyStatus {
  const risk = useStore((s) => s.risk)
  const gate = useStore((s) => s.gate)
  const a552 = useStore((s) => s.atoms[552])
  const execution = useStore((s) => s.execution)
  const conn = useStore((s) => s.conn)

  return useMemo(() => {
    if (conn !== 'live') return { color: 'red', label: 'انقطع الاتصال', detail: 'النواة غير متصلة أو لا يصل بثّها' }
    // ٢٠٢٦-٠٩-٠٩ (ختم NQ): كان الشرط `risk?.halted || execution?.halted` —
    // وكلا الحقلين غير موجود في أي حمولة (مقيسًا على البثّ الحيّ)، فالغرفة ما
    // كانت تعلن «متوقف» ولو كان الإيقاف فعّالًا. `halted` الحقيقيّ ينشره ٥٥٢
    // بـ`execution.gate.state`، وقاطع الأمان من ٥١٦ بعد تسطيح حمولة ٥٠٠.
    // ٢٠٢٦-١٠-٢٦ (فحص المشروع، ختم «nq اصلح»): الغائب كان «البوّابة مقفلة»، وإيقاف الحارس لحسابٍ يُجمع مع الإيقاف العامّ.
    // القراءة الآن مشتركة مع «شو صاير» (`core/gate.ts`): الغائب «غير مقروء»، والحارس حارسٌ لا عطل.
    const g = readGate(gate, a552)
    if (g.ownerHalt || risk?.kill_switch_state === true) {
      return { color: 'red', label: 'متوقف', detail: 'التداول موقوف' }
    }
    if (g.guardHalt) return { color: 'red', label: 'موقوف بحارس', detail: 'حارسٌ أوقف الحساب لحاله — ليس عطلًا ولا أمرًا منك' }
    if (!g.known) return { color: 'grey', label: 'غير مقروء', detail: 'ما وصلت حال بوّابة التنفيذ لهالشاشة — لا تُقرأ مقفلةً ولا مفتوحة' }
    if (!g.open) return { color: 'amber', label: 'البوّابة مقفلة', detail: 'التداول غير مسموح حتى يثبت فتح البوّابة' }
    return { color: 'green', label: 'آمن — التداول مسموح', detail: 'كل الحرّاس سليمون' }
  }, [risk, gate, a552, execution, conn])
}

// ═══════════════════════════════════════════════════════════
// ٢ — شريط القرار: بطاقة استمرار الاتّجاه (414)
// ٢٠٢٦-١٠-٠٨ (فكّ الأقسام عن القرار، ختم المالك «NQ»): «الروم الحيّ» من 451 أُرشف؛ الشريط صار `CardBar` المشترك.
// ═══════════════════════════════════════════════════════════

// ═══════════════════════════════════════════════════════════
// ٣ — لماذا لست في صفقة؟ (الموانع)
// ═══════════════════════════════════════════════════════════

interface Blocker {
  id: string
  label: string
  value: string
  threshold: string
  color: Color4
}

// حواجز النظام على مستوى السلسلة — تُقرأ من صحّة الذرات (REST، ما تحتاج WS):
// تغذية واقعة أو تحجيم مقطوع ما بيقدر يوصل «كل الموانع راحلة»
const BARRIER_ATOMS: Array<{ id: number; label: string }> = [
  { id: 613, label: 'تغذية السوق' },
  { id: 622, label: 'تغذية cTrader (FIX)' },
  { id: 618, label: 'تغذية جسر المنصة' },
  { id: 619, label: 'حالة الحساب' },
  { id: 513, label: 'التحجيم' },
  { id: 708, label: 'سجلّ الرموز' },
  { id: 552, label: 'بوّابة التنفيذ' },
]

function useBlockers(): Blocker[] {
  const cards = useCards()
  const risk = useStore((s) => s.risk)
  const atoms = useStore((s) => s.atoms)

  return useMemo(() => {
    const blockers: Blocker[] = []
    // حواجز النظام من صحّة الذرات (تتقدّم على أي شي — تغذية/تحجيم/بوّابة)
    for (const b of BARRIER_ATOMS) {
      const a = atoms[b.id]
      if (!a?.health) continue
      const hs = (a.health.state ?? '').toLowerCase()
      const msg = a.health.message ?? ''
      // الفحص على الرمز الخام، والمعروض عربيّ (ختم NQ ٢٠٢٦-٠٩-٠٩)
      const msgAr = msg ? arabicHealth(msg) : ''
      if (hs === 'unhealthy' || hs === 'error') {
        blockers.push({ id: `bar-${b.id}`, label: b.label, value: msgAr.slice(0, 60) || 'معطوب', threshold: `الذرّة ${b.id}`, color: 'red' })
      } else if (hs === 'degraded' && !isWaitingMessage(msg)) {
        blockers.push({ id: `bar-${b.id}`, label: b.label, value: msgAr.slice(0, 60) || 'متعثّر', threshold: `الذرّة ${b.id}`, color: 'amber' })
      }
    }
    // من البطاقة — آخر بطاقة لكلّ رمز: «مفتوحة» لا تمنع، وغيرها سببُ عدم الدخول بجملة.
    // ٢٠٢٦-١٠-٠٨ (فكّ الأقسام عن القرار، ختم المالك «NQ»): كانت من أقسام «الروم» (451) غير الجاهزة، وقد أُرشف.
    for (const c of Object.values(cards)) {
      if (!c?.symbol || c.status === 'OPEN') continue
      blockers.push({
        id: `card-${c.symbol}`, label: `${c.symbol} · بطاقة الاتّجاه`,
        value: cardStatusAr(c.status), threshold: cardHint(c.status) || '—',
        color: c.status === 'ACCOUNT_UNKNOWN' ? 'red' : 'grey',
      })
    }
    // من المخاطر — قاطع الأمان (٥١٦) بعد تسطيح حمولة ٥٠٠ المجمِّعة؛ الحقل
    // `risk.halted` الذي كان هنا لا وجود له في أي حمولة (مقيسًا ٢٠٢٦-٠٩-٠٩).
    if (risk?.kill_switch_state === true) {
      blockers.push({
        id: 'halt', label: 'قاطع الأمان', value: 'موقوف',
        // ٢٠٢٦-٠٩-١٨: السبب كان يُعرَض خامًا هنا أيضًا — ثلاث شاشات بالعطب نفسه.
        threshold: risk.kill_switch_reason
          ? arabicHealth(String(risk.kill_switch_reason)) : 'بقرار المالك',
        color: 'red',
      })
    }
    return blockers.slice(0, 10)
  }, [cards, risk, atoms])
}

function WhyNotPanel() {
  const blockers = useBlockers()
  const cards = useCards()
  const hasCards = Object.keys(cards).length > 0
  // «جاهز» ما ينقال إلا إذا وصلت بطاقة ومافي مانع — وإلا نعلن الانتظار
  const allReady = blockers.length === 0 && hasCards
  return (
    <div className="dl-panel dl-wide">
      <div className="dl-panel-title">لماذا لست في صفقة؟</div>
      {allReady ? (
        <div className="dl-all-clear" style={{ color: C.green }}>
          كل الموانع راحلة — آخر بطاقة مفتوحة وانبعتت للتنفيذ
        </div>
      ) : blockers.length === 0 ? (
        <div className="dl-all-clear dim">
          بانتظار أوّل بطاقة — تُكتب مع إغلاق كل شمعة ٥ دقائق
        </div>
      ) : (
        <div className="dl-blockers dl-tile-list">
          {blockers.map((b) => (
            <div key={b.id} className="dl-blocker" data-color={b.color}>
              <span className="dl-blocker-name">{b.label}</span>
              <span className="dl-blocker-val">{b.value}</span>
              <span className="dl-blocker-th dim">{b.threshold}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

// ═══════════════════════════════════════════════════════════
// ٣-ب — حقائق البطاقة وتفعيل الأصل
// ═══════════════════════════════════════════════════════════
// ٢٠٢٦-١٠-٠٨ (فكّ الأقسام عن القرار، ختم المالك «NQ»): أرقام القوّة/الثقة/الاتّجاه/العمق مقابل عتباتها كانت
// من أهليّة 455/456 — وقد أُرشفتا مع مقياس الوزن والثقة كلّه. ما يقابلها في المسار الجديد: هل الحقائق
// التي تبني عليها البطاقة حاضرة (الاتّجاه · المدى · سلّم المستويات · نافذة الوقت). وصفّ الأصل باقٍ كما هو.

function GateNumbersPanel() {
  const atoms = useStore((s) => s.atoms)
  const health = useCardHealth()

  // ٢٠٢٦-٠٩-١٨ — أُرشفت ٥٧٦ و٥٧٨ بأمر المالك (`25b0cbb`)، فحُذف صفّا «زوج
  // التحوّط» و«تفعيل الأصل (576)». وبقاؤهما كان **يقلب الغياب حجبًا**: الصفّ
  // يقرأ صحّة ذرّةٍ لا وجود لها فيخرج أصفر أبدًا ولا يخضرّ مهما فُعِّل الأصل.
  // والتفعيل الساري تحكمه بوّابة الأصول ٤٦٨ وحدها — وهي التي تفصل التِكّة.
  const a468 = atoms[468]
  const m468 = a468?.health?.message ?? ''
  // رسالة ٤٦٨: `allowed=N [أسماء] · <حساب>=N [أسماء] seen=N blocked=N`
  // (`atoms/قسم 450-499/468_التحكم_بالأصول/atom.py:219-230`) — أو
  // `EMPTY_WHITELIST_BLOCKS_ALL` حين لا أصل مسموح البتّة.
  const allowedCount = (() => {
    if (!m468) return null
    if (m468.includes('EMPTY_WHITELIST_BLOCKS_ALL')) return 0
    const perAccount = Array.from(m468.matchAll(/\b\d+=(\d+)\s*\[/g)).map((x) => Number(x[1]))
    if (perAccount.length) return Math.max(...perAccount)
    const m = /\ballowed=(\d+)\b/.exec(m468)
    return m ? Number(m[1]) : null
  })()

  return (
    <div className="dl-panel dl-wide">
      <div className="dl-panel-title">حقائق البطاقة وتفعيل الأصل</div>

      {/* ١ — حقائق البطاقة الحاضرة الآن (من رسالة صحّة 414) — حلّت محلّ عتبات الأهليّة 455/456 المؤرشفة */}
      {!health.loaded ? (
        <div className="dl-all-clear dim">بطاقة استمرار الاتّجاه غير محمّلة — لا حقائق تُعرض</div>
      ) : health.facts.length === 0 ? (
        <div className="dl-all-clear dim">ما أعلنت البطاقة حقائقها بعد</div>
      ) : (
        <div className="dl-blockers dl-tile-list" style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(232px, 1fr))' }}>
          {health.facts.map((f) => (
            <div key={f.key} className="dl-blocker" data-color={f.of > 0 && f.have >= f.of ? 'green' : f.have === 0 ? 'red' : 'amber'}>
              <span className="dl-blocker-name">{f.label}</span>
              <span className="dl-blocker-val num">{f.have} من {f.of}</span>
              <span className="dl-blocker-th dim">{f.have >= f.of ? 'حاضرة كلّها' : f.have === 0 ? 'غائبة — لا دخول على نقص' : 'ناقصة'}</span>
            </div>
          ))}
        </div>
      )}

      {/* ٢ — تفعيل الأصل: مَن يمرّ من بوّابة الأصول الآن */}
      <div className="dl-blockers" style={{ marginTop: 8 }}>
        <div className="dl-blocker"
          data-color={allowedCount == null ? 'grey' : allowedCount === 0 ? 'red' : 'green'}>
          <span className="dl-blocker-name">تفعيل الأصل (468)</span>
          <span className="dl-blocker-val">
            {allowedCount == null
              ? 'ما وصلت صحّة بوّابة الأصول بعد'
              : allowedCount === 0
                ? '✗ ما في أصل مفعَّل — كل تِكّة تُفصل قبل التحليل'
                : `✓ ${allowedCount} أصل مفعَّل`}
          </span>
          <span className="dl-blocker-th dim" title={m468 || undefined}>
            {m468 ? arabicHealth(m468) : '—'}
          </span>
        </div>
      </div>
    </div>
  )
}

// ═══════════════════════════════════════════════════════════
// ٤ — ما المعطوب؟
// ═══════════════════════════════════════════════════════════

interface SickAtom {
  id: number
  name: string
  state: string
  message: string
  color: Color4
}

function useSickAtoms(): { sick: SickAtom[]; waiting: SickAtom[] } {
  const atoms = useStore((s) => s.atoms)
  // لا حكمَ على ذرّةٍ بلا صحّة قبل أن تصل قراءةُ `/gov/atoms` الكاملة —
  // وإلّا قِيل «لم تُبلّغ قطّ» عن ذرّةٍ صحّتُها في الطريق. (وقعتُ فيها.)
  const snapshotAt = useStore((s) => s.snapshotAt)
  return useMemo(() => {
    const sick: SickAtom[] = []
    const waiting: SickAtom[] = []
    for (const a of Object.values(atoms)) {
      const hs = (a.health?.state ?? '').toLowerCase()
      const msg = a.health?.message ?? ''
      // النواة ترسل الحالة حروفًا صغيرة ('unhealthy') — مقارنة كبيرة ما تطابق أبدًا
      // فبتطلع «كل الذرّات سليمة» و10 مو سليمة (الكذبة المقيسة 2026-08-24)
      // ٢٠٢٦-٠٩-٠٩ (ختم NQ): الفرز يبقى على الرمز الخام (`isWaitingMessage`
      // تقرؤه)، والمخزَّن للعرض عربيّ — كانت البطاقة تكتب `UNTRUSTED` و
      // `NO_VOLUME_IN_CANDLES` و`checked=… alerts=…` كما تصل من النواة.
      const msgAr = msg ? arabicHealth(msg) : ''
      if (hs === 'unhealthy' || hs === 'error') {
        sick.push({ id: a.id, name: a.name_ar || a.name, state: a.state, message: msgAr, color: 'red' })
      } else if (hs === 'degraded' && !isWaitingMessage(msg)) {
        waiting.push({ id: a.id, name: a.name_ar || a.name, state: a.state, message: msgAr, color: 'amber' })
      } else if (a.state === 'running' && a.health == null && snapshotAt > 0) {
        // 🔴 ٢٠٢٦-٠٩-٢٣ — مقيسٌ على الحيّ: الذرّة ٧ «سلامة الملفّات» تخرج من
        // النواة بـ`health: null` — **لم تُبلّغ صحّتها قطّ** — ومع ذلك تحمل
        // `label_ar: "سليمة"` و`color: "green"`. وكان هذا الفرز يقرأ
        // `health?.state ?? ''` فلا يطابق شيئًا، **فتسقط من القائمتين
        // صامتةً** ويبقى الأخضر وحده. غيابٌ يُقرأ سلامة.
        //
        // وأثمنُ ما فيه أنّها **حارسُ تغيُّر الملفّات بلا إذن**: صمتُها
        // يُقرأ «لا اختراق» وهو «لا خبر». وقد اشتكت بحقٍّ من ختم النواة
        // قبل ساعات ثمّ هدأت — فسكوتُها الآن لا يُعرف معناه.
        //
        // فيُعلَن غيابُ البلاغ كما هو، ولا يُسمّى مرضًا: أصفر لا أحمر.
        waiting.push({
          id: a.id, name: a.name_ar || a.name, state: a.state,
          message: 'ما بلّغت صحّتها إطلاقًا — شغّالة وساكتة، فما بعرف هي سليمة ولا لأ',
          color: 'amber',
        })
      }
    }
    sick.sort((x, y) => x.id - y.id)
    waiting.sort((x, y) => x.id - y.id)
    return { sick: sick.slice(0, 12), waiting: waiting.slice(0, 12) }
  }, [atoms])
}

const GUARD_CHAIN: Array<{ id: number; label: string; purpose: string }> = [
  { id: 527, label: 'حلّ الرمز', purpose: 'الرمز معروف عند الوسيط' },
  { id: 526, label: 'حارس الهامش', purpose: 'الهامش والاحتياطي معروفان' },
  { id: 551, label: 'باني الأمر', purpose: 'الأمر مكتمل الهوية والسعر' },
  { id: 525, label: 'شرعية الوقف', purpose: 'الوقف والهدف صالحان' },
  { id: 552, label: 'مدقّق الأمر', purpose: 'القرار النهائي قبل الجسر' },
  { id: 601, label: 'كاتب الجسر', purpose: 'الحساب والرقم السحري ومنع التكرار' },
  { id: 901, label: 'بوابة الأوامر', purpose: 'أمر المالك وحالة الإيقاف' },
]

function GuardChainPanel() {
  const atoms = useStore((s) => s.atoms)
  const risk = useStore((s) => s.risk)
  const gate = useStore((s) => s.gate)
  // ٢٠٢٦-٠٩-٠٩ (ختم NQ): الإيقاف الفعّال من مصادره الحقيقيّة — `halted` و`status`
  // من بوّابة ٥٥٢، وقاطع الأمان من ٥١٦. الحقل `risk.halted` الذي كان يُقرأ هنا
  // غير موجود بأيّ حمولة على الناقل (مقيسًا)، فالسطر كان يطمئن أبدًا.
  const g = readGate(gate, atoms[552])
  const haltActive = g.ownerHalt || g.guardHalt || risk?.kill_switch_state === true
  return (
    <div className="dl-panel dl-guard-chain">
      <div className="dl-panel-title">سلسلة فتح الصفقة — لا تخمين</div>
      <div className="dl-guard-note">كل سطر يبيّن حالة الحارس. «لم تصل» ليست نجاحًا ولا فشلًا.</div>
      <div className="dl-guard-list">
        {GUARD_CHAIN.map((g) => {
          const a = atoms[g.id]
          const state = (a?.health?.state ?? '').toLowerCase()
          const healthy = state === 'healthy'
          const bad = state === 'unhealthy' || state === 'error'
          const color: Color4 = healthy ? 'green' : bad ? 'red' : state === 'degraded' ? 'amber' : 'grey'
          const gMsg = a?.health?.message ? arabicHealth(a.health.message) : ''
          const status = healthy ? 'جاهز' : bad ? 'يمنع — ' + (gMsg || 'فشل') : state === 'degraded' ? 'تحذير — ' + (gMsg || 'متعثّر') : 'لم تصل حالته بعد'
          return (
            <div key={g.id} className="dl-guard-row" data-color={color}>
              <span className="dl-guard-light" />
              <b className="dl-guard-id">{g.id}</b>
              <span className="dl-guard-name">{g.label}</span>
              <span className="dl-guard-purpose">{g.purpose}</span>
              <span className="dl-guard-status">{status}</span>
            </div>
          )
        })}
      </div>
      <div className="dl-guard-summary" data-color={haltActive ? 'red' : 'grey'}>
        {haltActive ? 'يوجد إيقاف فعّال — فتح الصفقة ممنوع' : 'الحكم النهائي يُؤخذ من السلسلة نفسها، وليس من لون اللوحة فقط'}
      </div>
    </div>
  )
}

function WhatBrokenPanel() {
  const { sick, waiting } = useSickAtoms()
  // ٢٠٢٦-٠٩-١٨ — مقيسة على الشاشة الحيّة والنواة مطفأة: كانت البطاقة تكتب
  // **«كل الذرّات سليمة — لا شيء معطوب»** بينما لا ذرّة واحدة محمّلة، ورأسُ
  // الشاشة نفسه يقول «انقطع الاتصال». والسبب أنّ الحكم مبنيّ على **خلوّ
  // قائمتي المرضى والمنتظرين**، وهما تخلوان حين لا يصل شيء أصلًا.
  // فالصفر يُفرَّق: صفرٌ من فحصٍ غير صفرٍ من صمت.
  const total = useStore((s) => Object.keys(s.atoms).length)
  const conn = useStore((s) => s.conn)
  const blind = total === 0 || conn !== 'live'
  return (
    <div className="dl-panel">
      <div className="dl-panel-title">ما المعطوب؟</div>
      {blind ? (
        <div className="dl-all-clear" style={{ color: C.amber }}>
          {total === 0
            ? 'ما وصلت ولا ذرّة — ما بقدر قول سليم ولا معطوب'
            : `الاتّصال مقطوع — آخر قراءة كانت لـ${total} ذرّة، وما بعدها مجهول`}
        </div>
      ) : sick.length === 0 && waiting.length === 0 ? (
        <div className="dl-all-clear" style={{ color: C.green }}>
          كل الذرّات سليمة — لا شيء معطوب <span className="dim">({total} ذرّة مفحوصة)</span>
        </div>
      ) : (
        <>
          {sick.length > 0 && (
            <>
              <div className="dl-sub-title" style={{ color: C.red }}>معطوب ({sick.length})</div>
              <div className="dl-sick-list">
                {sick.map((a) => (
                  <div key={a.id} className="dl-sick-item" data-color="red">
                    <span className="dl-sick-id">{a.id}</span>
                    <span className="dl-sick-name">{a.name}</span>
                    <span className="dl-sick-msg">{a.message.slice(0, 60)}</span>
                  </div>
                ))}
              </div>
            </>
          )}
          {waiting.length > 0 && (
            <>
              <div className="dl-sub-title" style={{ color: C.amber }}>ينتظر مدخله ({waiting.length}) — ليس معطوبًا</div>
              <div className="dl-sick-list">
                {waiting.slice(0, 6).map((a) => (
                  <div key={a.id} className="dl-sick-item" data-color="amber">
                    <span className="dl-sick-id">{a.id}</span>
                    <span className="dl-sick-name">{a.name}</span>
                    <span className="dl-sick-msg">{a.message.slice(0, 60)}</span>
                  </div>
                ))}
              </div>
            </>
          )}
        </>
      )}
    </div>
  )
}

// ═══════════════════════════════════════════════════════════
// ٥ — ماذا فعل النظام؟ (الخط الزمني)
// ═══════════════════════════════════════════════════════════

const ACT_AR: Record<string, string> = {
  'execution.order.built': 'بني أمر',
  'execution.order.requested': 'طُلب أمر',
  'execution.order.rejected': 'رُفض أمر',
  'trading.final_decision': 'قرار نهائي',
  'decision.gate.passed': 'عبَر البوّابة',
  'decision.gate.blocked': 'حُجب عند البوّابة',
  'perpetual.entry.rejected': 'رُفض تفعيل',
  'execution.command.ack': 'وصل تأكيد',
  'execution.command.failed': 'فشل أمر',
}

function TimelinePanel() {
  const execOrders = useStore((s) => s.execOrders)
  const events = useStore((s) => s.events)
  return (
    <div className="dl-panel">
      <div className="dl-panel-title">ماذا فعل النظام؟</div>
      {execOrders.length === 0 && events.length === 0 ? (
        <div className="dl-all-clear dim">لم ينفّذ النظام أي إجراء بعد — بانتظار أول قرار</div>
      ) : (
        <div className="dl-timeline">
          {execOrders.slice(0, 10).map((o, i) => {
            const act = ACT_AR[o.kind ?? ''] ?? o.kind ?? 'إجراء'
            const color: Color4 = o.kind === 'rejected' ? 'red' : o.kind === 'skipped' ? 'amber' : 'green'
            return (
              <div key={i} className="dl-tl-item" data-color={color}>
                <span className="dl-tl-dot" />
                <span className="dl-tl-act">{act}</span>
                <span className="dl-tl-sym">{typeof (o as { symbol?: unknown }).symbol === 'string' ? (o as { symbol: string }).symbol : ''}</span>
                <span className="dl-tl-time dim">
                  {o.ts ? new Date(o.ts).toLocaleTimeString('ar', { hour12: false }) : '—'}
                </span>
              </div>
            )
          })}
          {events.filter((e) => ACT_AR[e.name]).slice(0, 5).map((e, i) => (
            <div key={`e${i}`} className="dl-tl-item" data-color="grey">
              <span className="dl-tl-dot" />
              <span className="dl-tl-act">{ACT_AR[e.name]}</span>
              <span className="dl-tl-detail dim">{e.detail?.slice(0, 50)}</span>
              <span className="dl-tl-time dim">
                {e.ts ? new Date(e.ts).toLocaleTimeString('ar', { hour12: false }) : '—'}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

// ٢٠٢٦-١٠-٠٨ (فكّ الأقسام عن القرار، ختم المالك «NQ»): لوحة «المحلّلون» حُذفت — ناشرها مدير التحليل (150) أُرشف، فلا تصل أبدًا.

// ═══════════════════════════════════════════════════════════
// الشريط السفلي (الاتصال + الإنذار المبكر)
// ═══════════════════════════════════════════════════════════

const EARLY_AR: Record<string, string> = {
  'tools.device_resources.state': 'موارد الجهاز',
  'telemetry.carrier.state': 'ناقل التلمترية',
  'time.clock.quality.state': 'جودة الساعة',
}

function EarlyWarningBar() {
  const streams = useStore((s) => s.streams)
  const flows = useStore((s) => s.flows)
  const conn = useStore((s) => s.conn)
  return (
    <div className="dl-early-bar">
      {Object.entries(EARLY_AR).map(([event, ar]) => {
        const arrived = flows[event] != null
        const payload = streams[event] as Record<string, unknown> | undefined
        const status = arrived
          ? (typeof payload?.status === 'string' ? payload.status : 'وصل')
          : 'لم يصل بعد'
        const color: Color4 = arrived
          ? status.includes('OK') || status === 'وصل' ? 'green'
          : status.includes('DEGRADED') || status.includes('STALE') ? 'amber' : 'grey'
          : 'grey'
        return (
          <span key={event} className="dl-early-chip" data-color={color}>
            <span className="dl-early-dot" />
            {ar}
            <b className="dl-early-status">{status}</b>
          </span>
        )
      })}
      <span className="dl-conn" title={conn === 'live' ? 'الاتصال حيّ' : conn === 'connecting' ? 'جارٍ الاتصال' : 'الاتصال مقطوع'}>
        {conn === 'live' ? '🟢' : conn === 'connecting' ? '🟡' : '🔴'}
      </span>
    </div>
  )
}

// ═══════════════════════════════════════════════════════════
// التخطيط الرئيسي
// ═══════════════════════════════════════════════════════════

export default function NewDashboard() {
  const safety = useSafety()
  const market = useStore((s) => s.market)
  const accts = useTwinAccounts()
  // النبضة تعيد الرسم كل ثانية (الأعمار الحيّة)؛ القيمة نفسها لا تُقرأ هنا.
  const [, setNow] = useState(Date.now())

  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(id)
  }, [])

  // اختصار الطوارئ — من أي شاشة
  const emergencyRef = useRef<HTMLButtonElement>(null)
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && e.ctrlKey) {
        e.preventDefault()
        emergencyRef.current?.click()
      }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [])

  const tickSymbols = Object.entries(market).slice(0, 3)

  return (
    <div className="dl-root">
      {/* ═══ ١ — هل أنا بأمان؟ ═══ */}
      <header className="dl-safety-bar" data-color={safety.color}>
        <span className="dl-safety-label">{safety.label}</span>
        <span className="dl-safety-detail">{safety.detail}</span>
        <div className="dl-prices">
          <span className="dl-price" title="سي-تريدر — بيانات فقط">
            تحليل <b className="num">{accts.analysisId ?? '—'}</b>
          </span>
          <span className="dl-price" title="ميتاتريدر 5 — عليه الصفقة">
            تنفيذ <b className="num">{accts.execId ?? '—'}</b>
          </span>
          {tickSymbols.map(([sym, t]) => (
            <span key={sym} className="dl-price">
              {sym} <b className="num">{t.bid?.toFixed(1)}</b>
            </span>
          ))}
        </div>
        <button
          ref={emergencyRef}
          className="dl-emergency"
          onClick={async () => {
            if (!window.confirm('⚠️ إيقاف طارئ — إيقاف الدخول الجديد فقط؟')) return
            const result = await dangerCommand('halt')
            window.alert(result.message || (result.ok ? 'تم إرسال الإيقاف الطارئ' : 'تعذّر إرسال الإيقاف الطارئ'))
          }}
        >
          إيقاف طارئ
        </button>
      </header>

      {/* ═══ ٢ — شريط القرار: بطاقة استمرار الاتّجاه ═══ */}
      <CardBar />

      {/* ═══ ٣ — الأقسام الأربعة ═══ */}
      <main className="dl-main">
        <WhyNotPanel />
        <GateNumbersPanel />
        <GuardChainPanel />
        <WhatBrokenPanel />
        <TimelinePanel />
      </main>

      {/* ═══ الشريط السفلي ═══ */}
      <EarlyWarningBar />
    </div>
  )
}
