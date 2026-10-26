// القرار (855) — من ذرّةٍ واحدة: بطاقة استمرار الاتّجاه (414).
//
// ٢٠٢٦-١٠-٠٨ (فكّ الأقسام عن القرار، ختم المالك «NQ»): أُرشفت سلسلة القرار القديمة كلّها
// (451 تجميع · 452 تقييم · 453 درجة · 455/456/457 أهليّة · 458 حسم · 454 حواجز · 460-463 فلاتر ·
// 466 موافقة · 450 السجلّ الموحّد) ومعها لوحاتها هنا: بطاقة الثماني، جدول الحواجز، الأهليّات
// الثلاث، رحلة القرار، وعيارات DECISION_*. لم يعد لأيٍّ منها ناشر، فبقاؤها فراغٌ أبديّ.
//
// المسار الآن: 414 تقرّر عند إغلاق كل شمعة 5 د ⟵ `decision.approved.state` ⟵ 467 مرسل القرار
// ⟵ `decision.gate.passed` ⟵ 555 طالب أمر الدخول ⟵ `execution.order.requested` ⟵ حرّاس التنفيذ.
// كل رقم هنا من حدث حقيقيّ أو من رسالة صحّة 414 — لا حساب بالواجهة، والغائب «ما وصل».
import { useEffect, useMemo, useState } from 'react'
import { useStore } from '../core/store'
import { arabicVisible, ownerWindowAr } from '../core/arabic'
import { SectionAtomsHealth, SectionConfigTable } from '../components/SectionAtoms'
import {
  CardHealthStrip, CardStatusPill, cardHint, cardPrice, cardTime, rrText, sideAr, useCardHealth, useCards,
  type CardFact, type TrendCard,
} from '../components/TrendCard'
import TiltEngine from './TiltEngine'

type Rec = Record<string, unknown>

// تبقى لسجلّ 707: اتجاه القرار كما خزّنه — والمجهول «غير معروف» لا خام.
const SIG: Record<string, { t: string; a: string; c: string }> = {
  buy: { t: 'شراء', a: '▲', c: 'green' }, sell: { t: 'بيع', a: '▼', c: 'red' },
  wait: { t: 'انتظار', a: '⏸', c: 'grey' }, none: { t: 'لا قرار', a: '·', c: 'grey' },
}
const sigOf = (s?: unknown) => SIG[String(s ?? '').toLowerCase()] ?? { t: 'غير معروف', a: '·', c: 'grey' }

const num = (n: unknown, dp = 2): string =>
  typeof n === 'number' && Number.isFinite(n)
    ? n.toLocaleString('ar-EG-u-nu-latn', { maximumFractionDigits: dp, minimumFractionDigits: dp })
    : '—'
const timeText = (v: unknown): string => {
  const n = typeof v === 'number' ? v : undefined
  if (!n) return 'لم يصل'
  const ms = n > 10_000_000_000 ? n : n * 1000
  return new Date(ms).toLocaleString('ar-EG-u-nu-latn', { hour: '2-digit', minute: '2-digit', second: '2-digit' })
}
const ageText = (s?: number | null): string => {
  if (typeof s !== 'number' || !Number.isFinite(s)) return '—'
  if (s < 90) return `${Math.round(s)} ث`
  if (s < 5400) return `${Math.round(s / 60)} د`
  return `${num(s / 3600, 1)} س`
}
const fmtAny = (v: unknown): string => {
  if (v == null) return '—'
  if (typeof v === 'number') return num(v)
  if (typeof v === 'boolean') return v ? 'نعم' : 'لا'
  const s = String(v)
  return SIG[s] ? SIG[s].t : arabicVisible(s)
}

const DIRECTION_AR = (d?: unknown): [string, string] =>
  d === 1 ? ['صاعد ▲', 'green'] : d === -1 ? ['هابط ▼', 'red'] : d === 0 ? ['بلا اتّجاه', 'grey'] : ['ما وصل', 'grey']

// الأسواق المرتبطة كما تسمّيها البطاقة (`shared/card_trend.py:45`) — الرمز علمٌ يبقى كما هو.
const PEER_AR: Record<string, string> = { US500: 'الإس آند بي', US30: 'الداو' }
// ما تسمّيه البطاقة ناقصًا مع `FACT_MISSING` (`shared/card_trend.py:115,125`).
const MISSING_AR: Record<string, string> = { peers: 'اتّجاه الأسواق المرتبطة', atr_1d: 'مدى اليوم' }
// أسباب حجب مرسل القرار 467 (`atoms/قسم 450-499/467_إرسال_القرار/atom.py:27-31`).
const GATE_REASON_AR: Record<string, string> = {
  NOT_APPROVED: 'الموافقة غير معتمدة', SIDE_UNKNOWN: 'الجهة غير معروفة',
  NO_DECISION_IDENTITY: 'بلا معرّف قرار', NOT_STARTED: 'لم تُشغَّل', NO_INPUT_YET: 'لم يصلها مدخل بعد',
}

// ——— ١ — رأس الصفحة: البطاقة وصحّتها ———
function CardHeader() {
  const h = useCardHealth()
  return (
    <div className="scard" style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, flexWrap: 'wrap' }}>
        <b style={{ fontSize: 15.5 }}>القرار — بطاقة استمرار الاتّجاه بعد الارتداد</b>
        <span className="num dim" style={{ fontSize: 11.5 }}>#414</span>
        <span className={`pill ${!h.loaded ? 'grey' : !h.running ? 'red' : h.healthState === 'healthy' ? 'green' : 'amber'}`}
          style={{ marginInlineStart: 'auto' }}>
          {!h.loaded ? 'غير محمّلة' : !h.running ? 'واقفة' : h.healthState === 'healthy' ? 'تعمل' : 'تعمل — لم تقرأ شمعة بعد'}
        </span>
      </div>
      <div className="ss dim" style={{ marginTop: 0, lineHeight: 1.8 }}>
        ذرّةٌ واحدة تقرّر الآن: عند إغلاق كلّ شمعة ٥ دقائق تقرأ الحقائق الخام (الاتّجاه · المدى · سلّم المستويات ·
        نافذة الوقت · الخبر · الأسواق المرتبطة) وتكتب بطاقة — إمّا صفقة بجهتها ودخولها ووقفها وهدفها، وإمّا سببًا
        واحدًا لعدم الدخول. الأقسام ما عاد لها وزن ولا ثقة ولا موصولة بالقرار.
      </div>
      <CardHealthStrip />
    </div>
  )
}

// ——— ٢ — مصادر الحقائق التي بُنيت عليها البطاقة ———
function trendValue(f?: CardFact | null): string {
  if (!f || typeof f.close !== 'number') return 'غائبة'
  return `إغلاق ${num(f.close)} · متوسّط ٢٠: ${num(f.ema_slow_value)}`
}
function atrValue(f?: CardFact | null): string {
  if (!f || typeof f.atr !== 'number') return 'غائبة'
  return `متوسّط المدى الحقيقيّ ${num(f.atr)}`
}

function FactsTable({ card }: { card: TrendCard }) {
  const f = card.facts
  if (!f) {
    return <div className="ss dim">هذه البطاقة بلا مصادر حقائق — تُكتب حين تُقيَّم الشمعة كاملةً، لا حين تُرفض لتأخّرها.</div>
  }
  const peerRows = Object.entries(f['151_peers'] ?? {}).flatMap(([peer, frames]) =>
    (['1h', '4h'] as const).map((frame) => ({
      key: `peer-${peer}-${frame}`,
      name: `${peer} (${PEER_AR[peer] ?? peer}) — ${frame === '1h' ? 'الساعة' : 'الأربع ساعات'}`,
      src: 'الاتّجاه 151', value: trendValue(frames?.[frame]), age: null as number | null,
      ok: typeof frames?.[frame]?.close === 'number',
    })))
  const win = f['412_window']
  const rows = [
    { key: 't1h', name: 'اتّجاه الساعة', src: 'الاتّجاه 151', value: trendValue(f['151_trend_1h']), age: f['151_trend_1h']?.age_s ?? null, ok: typeof f['151_trend_1h']?.close === 'number' },
    { key: 't4h', name: 'اتّجاه الأربع ساعات', src: 'الاتّجاه 151', value: trendValue(f['151_trend_4h']), age: f['151_trend_4h']?.age_s ?? null, ok: typeof f['151_trend_4h']?.close === 'number' },
    { key: 'a5m', name: 'مدى ٥ دقائق', src: 'التذبذب 153', value: atrValue(f['153_atr_5m']), age: f['153_atr_5m']?.age_s ?? null, ok: typeof f['153_atr_5m']?.atr === 'number' },
    { key: 'a1d', name: 'مدى اليوم', src: 'التذبذب 153', value: atrValue(f['153_atr_1d']), age: f['153_atr_1d']?.age_s ?? null, ok: typeof f['153_atr_1d']?.atr === 'number' },
    { key: 'lad', name: 'سلّم المستويات', src: 'القمم والقيعان 201', value: f['201_ladder_age_s'] == null ? 'غائب' : 'حاضر', age: f['201_ladder_age_s'] ?? null, ok: f['201_ladder_age_s'] != null },
    { key: 'win', name: 'نافذة المالك', src: 'الجلسة 412', value: win ? ownerWindowAr(win.window) : 'ما وصلت', age: null, ok: !!win },
    { key: 'news', name: 'نوافذ منع الخبر المسجّلة', src: 'الأخبار 411', value: typeof f['411_news_windows'] === 'number' ? `${f['411_news_windows']} نافذة` : '—', age: null, ok: typeof f['411_news_windows'] === 'number' },
    ...peerRows,
  ]
  return (
    <div style={{ overflowX: 'auto' }}>
      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12.5 }}>
        <thead><tr className="dim" style={{ textAlign: 'right' }}>
          <th style={{ padding: 5 }}>الحقيقة</th><th style={{ padding: 5 }}>مصدرها</th>
          <th style={{ padding: 5 }}>قيمتها لحظة البطاقة</th><th style={{ padding: 5 }}>عمرها عندئذٍ</th>
        </tr></thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.key} style={{ borderBottom: '1px solid var(--glassb)' }}>
              <td style={{ padding: 5, fontWeight: 600 }}>{r.name}</td>
              <td style={{ padding: 5 }} className="dim">{r.src}</td>
              <td style={{ padding: 5, color: r.ok ? undefined : 'var(--amber)' }} className="num">{r.value}</td>
              <td style={{ padding: 5 }} className="num dim">{ageText(r.age)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

// ——— ٣ — ما بعد الموافقة: 414 ⟵ 467 ⟵ 555 (مطابَقة بمعرّف القرار = معرّف البطاقة) ———
function ApprovalJourney({ symbol }: { symbol: string }) {
  const approved = useStore((s) => s.symbolStreams['decision.approved.state']?.[symbol]) as Rec | undefined
  const passed = useStore((s) => s.symbolStreams['decision.gate.passed']?.[symbol]) as Rec | undefined
  const blocked = useStore((s) => s.symbolStreams['decision.gate.blocked']?.[symbol]) as Rec | undefined
  const recorded = useStore((s) => s.symbolStreams['decision.gate.recorded']?.[symbol]) as Rec | undefined
  const ordered = useStore((s) => s.symbolStreams['execution.order.requested']?.[symbol]) as Rec | undefined

  if (!approved) {
    return <div className="ss dim">ما وصلت موافقة لهذا الرمز منذ فتح الشاشة — الموافقة تصدر فقط حين تكون البطاقة «مفتوحة».</div>
  }
  const id = String(approved.decision_id ?? '')
  const mine = (p?: Rec) => (p && String(p.decision_id ?? '') === id ? p : undefined)
  const gPass = mine(passed)
  const gBlock = mine(blocked)
  const gRec = mine(recorded)
  const order = mine(ordered)
  const [sideTxt, sideTone] = sideAr(approved.decision_side)
  const card = (approved.card ?? {}) as TrendCard
  const step = (label: string, text: string, tone: string) => (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
      <span className="dim" style={{ fontSize: 11.5 }}>{label}</span>
      <span className={`pill ${tone}`} style={{ fontSize: 12 }}>{text}</span>
    </span>
  )
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, alignItems: 'center' }}>
        {step('البطاقة (414)', `وافقت — ${sideTxt}`, sideTone)}
        <span className="dim">←</span>
        {step('مرسل القرار (467)',
          gPass ? 'مرّت ✓' : gBlock ? `حُجبت — ${GATE_REASON_AR[String(gBlock.reject_reason ?? '')] ?? arabicVisible(gBlock.reject_reason, 'سبب غير مترجَم')}` : gRec ? 'سُجّلت انتظارًا' : 'لم يصل حكمه',
          gPass ? 'green' : gBlock ? 'red' : gRec ? 'amber' : 'grey')}
        <span className="dim">←</span>
        {step('طالب أمر الدخول (555)',
          order ? `طلب أمرًا — حجم ${num(order.volume as number, 2)}` : 'لم يطلب أمرًا لها',
          order ? 'green' : 'grey')}
      </div>
      <div className="ss dim" style={{ marginTop: 0 }}>
        بطاقة الشمعة {cardTime(card)} · وقف الإرسال {cardPrice(card, approved.invalidation_price)} · هدفه {cardPrice(card, approved.target_price)}
        {order ? <> · وقف الأمر {cardPrice(card, order.stop_loss)} · هدفه {cardPrice(card, order.take_profit)}</> : null}
        {gPass?.gated_at ? <> · وقت البوّابة {timeText(gPass.gated_at)}</> : null}
      </div>
      {!order ? (
        <div className="ss dim" style={{ marginTop: 0 }}>
          إن لم يطلب طالب الأمر أمرًا، فسببه في صفحة «التنفيذ» (رسالة ٥٥٥ وقُمع رحلة البطاقة) — هذا السجلّ يمتلئ من البثّ الحيّ وحده.
        </div>
      ) : null}
    </div>
  )
}

// ——— ٤ — بطاقة الرمز كاملة ———
function CardDetail({ card }: { card: TrendCard }) {
  const [open, setOpen] = useState(false)
  const [sideTxt, sideTone] = sideAr(card.side)
  const [dirTxt, dirTone] = DIRECTION_AR(card.direction)
  const hasLevels = typeof card.entry === 'number'
  const cell = (label: string, value: string, color?: string) => (
    <div className="scard" style={{ padding: '8px 12px' }}>
      <div className="st dim" style={{ fontSize: 12 }}>{label}</div>
      <div className="num" style={{ fontSize: 18, fontWeight: 700, color }}>{value}</div>
    </div>
  )
  return (
    <div className="scard" style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
        <b style={{ fontSize: 17 }}>{card.symbol ?? '—'}</b>
        <CardStatusPill status={card.status} style={{ fontSize: 13 }} />
        {card.side ? <span className={`pill ${sideTone}`} style={{ fontSize: 13 }}>{sideTxt}</span> : null}
        <span className="dim num" style={{ marginInlineStart: 'auto', fontSize: 12 }}>
          شمعة ٥ دقائق أُغلقت {cardTime(card)}
        </span>
      </div>
      {cardHint(card.status) ? <div className="ss" style={{ marginTop: 0 }}>{cardHint(card.status)}</div> : null}

      {/* تفصيل الحالة نفسها — ما تقوله البطاقة عن سببها، بلا زيادة */}
      {card.status === 'NO_TRIGGER' && typeof card.trigger_level === 'number' ? (
        <div className="ss" style={{ marginTop: 0 }}>المستوى اللي لازم تكسره الشمعة: <b className="num">{cardPrice(card, card.trigger_level)}</b> — وأغلقت على <b className="num">{cardPrice(card, card.close)}</b></div>
      ) : null}
      {card.status === 'FACT_MISSING' ? (
        <div className="ss" style={{ marginTop: 0, color: 'var(--amber)' }}>
          الناقص: {card.missing ? (MISSING_AR[card.missing] ?? arabicVisible(card.missing, 'حقيقة غير مسمّاة')) : 'الشمعة السابقة أو مدى ٥ دقائق أو سلّم المستويات'}
        </div>
      ) : null}
      {card.status === 'CANDLE_LATE' && typeof card.late_s === 'number' ? (
        <div className="ss" style={{ marginTop: 0, color: 'var(--amber)' }}>تأخّرت الشمعة <b className="num">{num(card.late_s, 1)}</b> ثانية عن إغلاقها.</div>
      ) : null}

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(130px, 1fr))', gap: 8 }}>
        {cell('الجهة', card.side ? sideTxt : '—', card.side ? `var(--${sideTone})` : 'var(--dim)')}
        {cell('الدخول', hasLevels ? cardPrice(card, card.entry) : '—')}
        {cell('الوقف', hasLevels ? cardPrice(card, card.stop) : '—', hasLevels ? 'var(--red)' : 'var(--dim)')}
        {cell('الهدف', typeof card.target === 'number' ? cardPrice(card, card.target) : '—', typeof card.target === 'number' ? 'var(--green)' : 'var(--dim)')}
        {cell('الهدف مقابل الوقف', rrText(card.rr))}
        {cell('النافذة', ownerWindowAr(card.window), card.window ? undefined : 'var(--dim)')}
      </div>
      {!hasLevels ? (
        <div className="ss dim" style={{ marginTop: 0 }}>الدخول والوقف تُحسب فقط حين تبلغ البطاقة بنية الارتداد والزناد؛ والهدف والنسبة حين تكون «مفتوحة».</div>
      ) : null}
      {card.base_rate_text ? (
        <div className="ss" style={{ marginTop: 0 }}>📊 {card.base_rate_text} — للعلم، لا يمنع ولا يسمح.</div>
      ) : null}

      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '4px 16px', fontSize: 13, alignItems: 'baseline' }}>
        <span><span className="dim">اتّجاه الناسداك (ساعة وأربع ساعات معًا)</span> <b style={{ color: `var(--${dirTone})` }}>{dirTxt}</b></span>
        <span><span className="dim">الأسواق المرتبطة</span>{' '}
          {card.peers && Object.keys(card.peers).length
            ? Object.entries(card.peers).map(([peer, d], i) => {
                const [t, c] = DIRECTION_AR(d)
                return <span key={peer}>{i ? ' · ' : ''}<b className="num">{peer}</b> <span className="dim">({PEER_AR[peer] ?? peer})</span> <b style={{ color: `var(--${c})` }}>{t}</b></span>
              })
            : <span className="dim">ما قُرئت بهالبطاقة — تُقرأ بعد النافذة والخبر والاتّجاه</span>}
        </span>
        {typeof card.risk === 'number' ? <span><span className="dim">مسافة الوقف</span> <b className="num">{cardPrice(card, card.risk)}</b></span> : null}
        {typeof card.pullback === 'number' ? <span><span className="dim">طرف الارتداد</span> <b className="num">{cardPrice(card, card.pullback)}</b></span> : null}
        {typeof card.broken_level === 'number' ? <span><span className="dim">المستوى المكسور</span> <b className="num">{cardPrice(card, card.broken_level)}</b></span> : null}
        {typeof card.reach === 'number' ? <span><span className="dim">أقصى مسافة للهدف (من مدى اليوم)</span> <b className="num">{cardPrice(card, card.reach)}</b></span> : null}
      </div>

      <div style={{ borderTop: '1px solid var(--glassb)', paddingTop: 8 }}>
        <div className="st" style={{ marginBottom: 6 }}>بعد الموافقة — هل وصلت التنفيذ؟</div>
        <ApprovalJourney symbol={String(card.symbol ?? '')} />
      </div>

      <div>
        <button className="btn" style={{ fontSize: 12 }} onClick={() => setOpen((v) => !v)}>
          {open ? '▴ خبّي مصادر الحقائق' : '▾ مصادر الحقائق — من أيّ ذرّة جاءت كلّ معلومة وكم كان عمرها'}
        </button>
        {open ? <div style={{ marginTop: 8 }}><FactsTable card={card} /></div> : null}
      </div>
      <div className="ss dim" style={{ fontSize: 11, marginTop: 0 }} title={card.card_id ?? undefined}>
        معرّف البطاقة {card.card_id ?? '—'} — وهو نفسه معرّف القرار في البوّابة والأمر والسجلّ.
      </div>
    </div>
  )
}

// ——— ٥ — سجل مخزن دورة حياة التنفيذ (707) — قراءة REST مباشرة، لا بثّ ———
interface DecisionRow {
  id: number; stage?: string; request_id?: string; account_id?: string; symbol?: string
  direction?: string; approved?: number | null; reason?: string; confidence?: number
  strategy_id?: string; model_id?: string; volume?: number; stop_loss?: number
  take_profit?: number; decided_at?: number; decision_id?: string; gate_request_id?: string
  // ٢٠٢٦-٠٩-٠٩ (ختم NQ): `reason` تصنيف طبقة لا سبب — ٦٧٬٩٧٧ صفًّا بمرحلة
  // `APPROVED` كلّها `BLOCKED_UPSTREAM` (قياس جلسة القرار على القاعدة نفسها).
  // السبب الفعليّ من `payload_json`: `rejection.reason` وتفصيله `barriers[]`.
  rejection_reason?: string | null; barrier_reasons?: string[]
}
interface DecisionsPayload { available: boolean; decisions: DecisionRow[]; has_link_columns: boolean }

// أسباب حجبٍ مكتوبة في صفوف السجلّ القديمة (حواجز 454 قبل أرشفته) — تبقى لتُقرأ تلك الصفوف عربيّةً.
const BARRIER_REASON_AR: Record<string, string> = {
  DECISION_SIDE_UNKNOWN: 'الجانب غير معروف', DECISION_SIDE_WAIT: 'الجانب انتظار — لا اتجاه للتنفيذ',
  SCORE_UNKNOWN: 'الدرجة غير معروفة', SCORE_BELOW_MIN: 'الدرجة تحت العتبة الدنيا',
  FILTER_VERDICT_MISSING: 'حكم الفلتر غائب', FILTER_VERDICT_STALE: 'حكم الفلتر متقادم',
  FILTER_CYCLE_MISMATCH: 'حكم الفلتر من دورة مختلفة', FILTER_FAILED: 'الفلتر رفض',
  CALENDAR_UNKNOWN: 'التقويم الاقتصادي مجهول', CALENDAR_EVENT_WINDOW: 'داخل نافذة حدث اقتصادي',
  NEWS_WINDOW_BLOCK: 'داخل نافذة خبر مؤثّر', MARKET_QUALITY_UNKNOWN: 'جودة السوق مجهولة',
  MARKET_QUALITY_INVALID: 'جودة السوق ساقطة', FEED_NOT_ACTIVE: 'التغذية غير نشطة',
}
// مراحل السجلّ كما يكتبها 707 — والمجهول يُقال مجهولًا لا خامًا.
const STAGE_AR: Record<string, string> = {
  APPROVED: 'موافقة', DISPATCH: 'إرسال', ORDER_REQUESTED: 'طلب أمر', ORDER_BUILT: 'بناء أمر',
  ORDER_REJECTED: 'رفض أمر', DECISION_FINALIZED: 'قرار نهائيّ', QUEUED_TO_BRIDGE: 'انكتب للجسر',
  BRIDGE_WRITE_FAILED: 'فشل الكتابة للجسر', BROKER_ACKNOWLEDGED: 'أقرّه الوسيط',
  BROKER_COMMAND_FAILED: 'فشل أمر الوسيط', FILLED_OPEN: 'امتلأ وفتح', FILLED_PARTIAL: 'امتلأ جزئيًّا',
  FILLED_CLOSED: 'أُغلق',
}
const LEDGER_REASON_AR: Record<string, string> = {
  TP: 'ضرب الهدف', SL: 'ضرب الوقف', POSITION_OWNERSHIP_MISMATCH: 'ملكيّة المركز لا تطابق',
  BLOCKED_UPSTREAM: 'محجوب من فوق', ...BARRIER_REASON_AR,
}

function DecisionsLedger() {
  const [data, setData] = useState<DecisionsPayload | null>(null)
  const [err, setErr] = useState('')
  useEffect(() => {
    const c = new AbortController()
    fetch('/gov/decisions?limit=30', { signal: c.signal })
      .then((r) => r.json() as Promise<DecisionsPayload>)
      .then(setData)
      .catch(() => setErr('تعذّر جلب سجلّ 707 — تأكّد أن المنفذ /gov/decisions حيّ (منفذ جديد يحتاج إعادة تشغيل خادم الحوكمة)'))
    return () => c.abort()
  }, [])

  return (
    <div className="scard" style={{ padding: 0, overflow: 'hidden' }}>
      <div style={{ padding: '9px 12px', borderBottom: '1px solid var(--glassb)' }}>
        <div className="st">سجل مخزن دورة حياة التنفيذ (707)</div>
        <div className="ss dim">آخر القرارات والأوامر كما كتبها 707 — قراءة فقط. عمودا الربط (معرّف القرار/طلب البوابة) يظهران فقط إذا أثبتتهما القاعدة الحيّة فعليًّا.</div>
      </div>
      {err ? <div className="ss" style={{ padding: '9px 12px', color: 'var(--amber)' }}>{err}</div> : null}
      {!data ? <div className="ss dim" style={{ padding: '9px 12px' }}>جارٍ الجلب…</div>
        : !data.available ? <div className="empty">قاعدة 707 غير متاحة من الخادم الآن (المسار غائب، أو المنفذ الجديد /gov/decisions لم يُحمَّل حيًّا بعد — يحتاج إعادة تشغيل).</div>
        : data.decisions.length === 0 ? <div className="empty">القاعدة فاضية — صفر صفّ حتى الآن.</div>
          : (
            <div style={{ overflowX: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12.5 }}>
                <thead><tr className="dim" style={{ textAlign: 'right', whiteSpace: 'nowrap' }}>
                  <th style={{ padding: 6 }}>الوقت</th><th style={{ padding: 6 }}>الرمز</th><th style={{ padding: 6 }}>المرحلة</th>
                  <th style={{ padding: 6 }}>الاتجاه</th><th style={{ padding: 6 }}>معتمد</th><th style={{ padding: 6 }}>السبب</th>
                  <th style={{ padding: 6 }}>الحجم</th>
                  {data.has_link_columns ? <><th style={{ padding: 6 }}>معرّف القرار</th><th style={{ padding: 6 }}>معرّف طلب البوابة</th></> : null}
                </tr></thead>
                <tbody>
                  {data.decisions.map((d) => (
                    <tr key={d.id} style={{ borderBottom: '1px solid var(--glassb)' }}>
                      <td style={{ padding: 6, whiteSpace: 'nowrap' }} className="dim">{timeText(d.decided_at)}</td>
                      <td style={{ padding: 6, fontWeight: 600 }}>{d.symbol ?? '—'}</td>
                      <td style={{ padding: 6 }} title={d.stage}>{d.stage ? (STAGE_AR[d.stage] ?? arabicVisible(d.stage, 'مرحلة غير مترجمة')) : '—'}</td>
                      <td style={{ padding: 6 }}>{d.direction ? sigOf(d.direction).t : '—'}</td>
                      <td style={{ padding: 6 }}>{d.approved == null ? '—' : d.approved ? <span className="green">نعم</span> : <span className="red">لا</span>}</td>
                      {/* السبب الفعليّ أوّلًا؛ وتصنيف الطبقة خافتًا تحته مسمًّى بما هو. */}
                      <td style={{ padding: 6 }} title={d.rejection_reason ?? d.reason ?? undefined}>
                        {d.rejection_reason
                          ? <>
                              <span>{LEDGER_REASON_AR[d.rejection_reason] ?? arabicVisible(d.rejection_reason, 'سبب غير مترجم')}</span>
                              {d.reason && d.reason !== d.rejection_reason
                                ? <div className="dim" style={{ fontSize: 10.5 }}>تصنيف الطبقة: {LEDGER_REASON_AR[d.reason] ?? arabicVisible(d.reason, 'غير مترجم')}</div>
                                : null}
                              {d.barrier_reasons && d.barrier_reasons.length > 1
                                ? <div className="dim" style={{ fontSize: 10 }}>
                                    حواجز أخرى: {d.barrier_reasons.filter((b) => b !== d.rejection_reason)
                                      .map((b) => LEDGER_REASON_AR[b] ?? arabicVisible(b, 'غير مترجم')).join(' · ')}
                                  </div>
                                : null}
                            </>
                          : d.reason ? (LEDGER_REASON_AR[d.reason] ?? arabicVisible(d.reason, 'سبب غير مترجم')) : '—'}
                      </td>
                      <td style={{ padding: 6 }} className="num">{fmtAny(d.volume)}</td>
                      {data.has_link_columns ? (<>
                        <td style={{ padding: 6, fontSize: 11 }} className="dim">{d.decision_id ?? '—'}</td>
                        <td style={{ padding: 6, fontSize: 11 }} className="dim">{d.gate_request_id ?? '—'}</td>
                      </>) : null}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
    </div>
  )
}

// ——— الصفحة ———
// ذرّات المسار الجديد: الخبر 411 · الجلسة 412 · البطاقة 414 · دفتر البطاقات 465 · مرسل القرار 467 · طالب الأمر 555.
const PATH_ATOMS = [411, 412, 414, 465, 467, 555]

export default function Decision() {
  const cards = useCards()
  const list = useMemo(
    () => Object.values(cards).filter((c) => c?.symbol).sort((a, b) => String(a.symbol).localeCompare(String(b.symbol))),
    [cards])

  return (
    <div className="section chartsec" style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
      <CardHeader />
      {list.length === 0 ? (
        <div className="empty">
          ما وصلت بطاقة لأيّ رمز منذ فتح الشاشة — البطاقة تُكتب مع إغلاق كل شمعة ٥ دقائق، وأوّلها تظهر هنا لحظة صدورها.
          العدّادات فوق من رسالة صحّة البطاقة نفسها.
        </div>
      ) : list.map((c) => <CardDetail key={c.symbol} card={c} />)}

      <SectionAtomsHealth ids={PATH_ATOMS} title="ذرّات مسار القرار — حالتها الحيّة الآن"
        note="الخبر والجلسة يغذّيان البطاقة · البطاقة تقرّر · دفتر البطاقات يسجّل · مرسل القرار يمرّر · طالب الأمر يطلب الدخول." />
      <DecisionsLedger />
      <TiltEngine />
      <SectionConfigTable from={450} to={500} title="معاملات ذرّات قسم القرار الحيّة (450-499) — الطزاجة 464 · دفتر البطاقات 465 · مرسل القرار 467 · الأصول 468" />
    </div>
  )
}
