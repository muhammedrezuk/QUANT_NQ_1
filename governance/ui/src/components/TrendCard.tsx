// بطاقة استمرار الاتّجاه (414) — قطعٌ مشتركة بين «القرار» و«الاستراتيجيات» و«الرئيسيّة» و«غرفة النظام» و«شو صاير».
//
// ٢٠٢٦-١٠-٠٨ (فكّ الأقسام عن القرار، ختم المالك «NQ»): أُرشفت ٣٦ ذرّة — مدراء الأقسام وسلسلة القرار
// 450-466 و581 — فصار القرار من ذرّةٍ واحدة. والأقسام تعطيها حقائق خامًا بلا وزنٍ ولا ثقة.
//
// المصدران، كلٌّ من كود ناشره لا من تخمين:
//   • `strategy.card.state` لكلّ شمعة 5 د (`atoms/قسم 400-449/414_بطاقة_استمرار_الاتجاه/atom.py:226-250`
//     والحقول من `shared/card_trend.py:96-160`) — يصل اللوحة على البثّ نفسه، مفتاحه الرمز.
//   • رسالة صحّة 414 (`atom.py:351-369`): «شموع_5د=… · بطاقات_مفتوحة=… · عدّ الحالات · حقائق: …».
//     `details` لا تصل اللوحة (النواة تحذفها)، فتُقرأ الرسالة نفسها.
// ⛔ اللوحة لا تحسب جهةً ولا وقفًا ولا هدفًا: تعرض ما قرّرته البطاقة، والغائب يُقال غائبًا.
import type { CSSProperties } from 'react'
import { useMemo } from 'react'
import { useStore } from '../core/store'
import { CARD_STATUS_HINT, CARD_STATUS_TONE, cardStatusAr, ownerWindowAr, type CardTone } from '../core/arabic'
import { decimalsOfAll, priceText } from '../core/price'

export const CARD_ATOM = 414

/** حقيقة اتّجاه (151) أو مدى (153) كما خزّنتها البطاقة لحظة تقييمها. */
export interface CardFact {
  close?: number; ema_slow_value?: number; atr?: number
  at?: number; source?: string; age_s?: number | null
}
export interface CardFacts {
  '151_trend_1h'?: CardFact; '151_trend_4h'?: CardFact
  '153_atr_5m'?: CardFact; '153_atr_1d'?: CardFact
  '201_ladder_age_s'?: number | null
  '412_window'?: { window?: string | null; window_at?: number | null; seen?: number; source?: string } | null
  '411_news_windows'?: number
  '151_peers'?: Record<string, Record<string, CardFact | null> | null>
}
export interface TrendCard {
  status?: string; side?: string; symbol?: string; card_id?: string
  at?: number; period_start?: number; timeframe?: string; close?: number
  entry?: number; stop?: number; target?: number; rr?: number; risk?: number
  window?: string | null; direction?: number; peers?: Record<string, number>
  facts?: CardFacts; missing?: string; trigger_level?: number; late_s?: number
  pullback?: number; broken_level?: number; reach?: number | null
  atr_5m?: number; atr_1d?: number
  // ٢٠٢٦-١٠-٠٨: النسبة الأساسيّة الصادقة للنافذة على السنتين — للعلم لا للمنع (بطاقة مفتوحة وحدها).
  base_rate_text?: string | null
}

const EMPTY: Record<string, TrendCard> = {}

/** آخر بطاقة لكلّ رمز — كما وصلت. */
export function useCards(): Record<string, TrendCard> {
  const cards = useStore((s) => s.symbolStreams['strategy.card.state']) as Record<string, TrendCard> | undefined
  return cards ?? EMPTY
}

export interface CardHealth {
  loaded: boolean
  running: boolean
  healthState: string
  candles: number | null
  opened: number | null
  tally: Array<[string, number]>
  facts: Array<{ key: string; label: string; have: number; of: number }>
}

// أسماء الحقائق كما تكتبها 414 في رسالتها (`atom.py:360`) — والشدّة اختياريّة في المطابقة.
const FACT_LABEL: Record<string, string> = {
  'اتجاه': 'الاتّجاه — ساعة وأربع ساعات للناسداك والسوقين المرتبطين',
  'مدى': 'المدى — ٥ دقائق واليوم',
  'سلم': 'سلّم المستويات',
  'وقت': 'نافذة الوقت',
}

/** يقرأ رسالة صحّة 414 — لا حساب، فكّ النصّ كما كتبته الذرّة. */
export function parseCardHealth(message: string): Omit<CardHealth, 'loaded' | 'running' | 'healthState'> {
  const n = (re: RegExp): number | null => {
    const m = re.exec(message)
    return m ? Number(m[1]) : null
  }
  const tally: Array<[string, number]> = []
  for (const m of message.matchAll(/(?:^|\s)([A-Z][A-Z_]+)=(\d+)/g)) tally.push([m[1], Number(m[2])])
  tally.sort((a, b) => b[1] - a[1])
  const facts: CardHealth['facts'] = []
  for (const m of message.matchAll(/(اتّ?جاه|مدى|سلّ?م|وقت)=(\d+)\/(\d+)/g)) {
    const key = m[1].replace(/ّ/g, '')
    facts.push({ key, label: FACT_LABEL[key] ?? key, have: Number(m[2]), of: Number(m[3]) })
  }
  return {
    candles: n(/شموع_5د=(\d+)/),
    opened: n(/بطاقات_مفتوحة=(\d+)/),
    tally, facts,
  }
}

export function useCardHealth(): CardHealth {
  const atom = useStore((s) => s.atoms[CARD_ATOM])
  return useMemo(() => {
    const message = atom?.health?.message ?? ''
    return {
      loaded: atom != null,
      running: atom?.state === 'running',
      healthState: atom?.health?.state ?? '',
      ...parseCardHealth(message),
    }
  }, [atom])
}

export const SIDE_AR: Record<string, [string, CardTone]> = {
  buy: ['شراء', 'green'], sell: ['بيع', 'red'],
}
export const sideAr = (side?: unknown): [string, CardTone] =>
  SIDE_AR[String(side ?? '').toLowerCase()] ?? ['—', 'grey']

export const cardTone = (status?: unknown): CardTone => CARD_STATUS_TONE[String(status ?? '')] ?? 'grey'
export const cardHint = (status?: unknown): string => CARD_STATUS_HINT[String(status ?? '')] ?? ''

/** وقت إغلاق شمعة البطاقة (`at` بالثواني) بساعة الجهاز. */
export function cardTime(card?: TrendCard): string {
  const at = card?.at
  if (typeof at !== 'number' || !Number.isFinite(at)) return '—'
  return new Date(at * 1000).toLocaleTimeString('ar-EG-u-nu-latn', { hour: '2-digit', minute: '2-digit', hour12: false })
}

/** دقّة واحدة لأسعار البطاقة كلّها — من أسعار السوق فيها (الدخول والهدف)، فالوقف المحسوب لا يجرّ ذيلًا عشريًّا. */
export function cardPrice(card: TrendCard, v: unknown): string {
  const refs = [card.entry, card.target, card.close]
  // بلا سعر سوقٍ مرجعيّ في البطاقة تُشتقّ الدقّة من القيمة نفسها — لا تُقصّ إلى صفر خانات.
  return priceText(v, refs.some((x) => typeof x === 'number') ? decimalsOfAll(...refs) : undefined)
}

export const rrText = (rr?: number): string =>
  typeof rr === 'number' && Number.isFinite(rr)
    ? `١ : ${rr.toLocaleString('ar-EG-u-nu-latn', { maximumFractionDigits: 2, minimumFractionDigits: 2 })}`
    : '—'

export function CardStatusPill({ status, style }: { status?: string; style?: CSSProperties }) {
  return (
    <span className={`pill ${cardTone(status)}`} style={style} title={cardHint(status) || undefined}>
      {cardStatusAr(status)}
    </span>
  )
}

const factTone = (have: number, of: number): CardTone => (of > 0 && have >= of ? 'green' : have === 0 ? 'red' : 'amber')

/** عدّادات البطاقة وحقائقها الحاضرة — من رسالة صحّتها. */
export function CardHealthStrip({ compact = false }: { compact?: boolean }) {
  const h = useCardHealth()
  if (!h.loaded) {
    return <div className="ss dim">بطاقة استمرار الاتّجاه غير محمّلة بالنواة الآن — لا عدّاد يُقرأ.</div>
  }
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '4px 14px', fontSize: compact ? 12 : 13, alignItems: 'baseline' }}>
        <span><span className="dim">شموع ٥ دقائق منذ الإقلاع</span> <b className="num">{h.candles ?? '—'}</b></span>
        <span><span className="dim">بطاقات فُتحت (تراكميّ)</span> <b className="num">{h.opened ?? '—'}</b></span>
        {!h.running ? <span className="pill red" style={{ fontSize: 11 }}>الذرّة واقفة</span> : null}
      </div>
      {h.tally.length ? (
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 5, alignItems: 'center' }}>
          <span className="dim" style={{ fontSize: compact ? 11.5 : 12 }}>عدّ الحالات (تراكميّ):</span>
          {h.tally.map(([status, n]) => (
            <span key={status} className={`pill ${cardTone(status)}`} style={{ fontSize: 11.5 }} title={cardHint(status) || undefined}>
              {cardStatusAr(status)} <b className="num">{n}</b>
            </span>
          ))}
        </div>
      ) : <div className="ss dim">ما في حالة معدودة بعد.</div>}
      {h.facts.length ? (
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 5, alignItems: 'center' }}>
          <span className="dim" style={{ fontSize: compact ? 11.5 : 12 }}>الحقائق الحاضرة الآن:</span>
          {h.facts.map((f) => (
            <span key={f.key} className={`pill ${factTone(f.have, f.of)}`} style={{ fontSize: 11.5 }} title={f.label}>
              {f.label.split(' — ')[0]} <b className="num">{f.have} من {f.of}</b>
            </span>
          ))}
        </div>
      ) : null}
    </div>
  )
}

/** سطر بطاقة واحدة مختصر — للشرائط العلويّة وصفحة الاستراتيجيات. */
export function CardLine({ card }: { card: TrendCard }) {
  const [sideTxt, sideTone] = sideAr(card.side)
  const hasLevels = typeof card.entry === 'number'
  return (
    <div style={{ display: 'flex', flexWrap: 'wrap', gap: '4px 12px', alignItems: 'baseline', fontSize: 12.5 }}>
      <b style={{ fontSize: 14 }}>{card.symbol ?? '—'}</b>
      <CardStatusPill status={card.status} style={{ fontSize: 12 }} />
      {card.side ? <b style={{ color: `var(--${sideTone})` }}>{sideTxt}</b> : null}
      {hasLevels ? (
        <span className="num">
          <span className="dim">دخول</span> {cardPrice(card, card.entry)}
          {' · '}<span className="dim">وقف</span> <span style={{ color: 'var(--red)' }}>{cardPrice(card, card.stop)}</span>
          {typeof card.target === 'number' ? <>{' · '}<span className="dim">هدف</span> <span style={{ color: 'var(--green)' }}>{cardPrice(card, card.target)}</span></> : null}
          {typeof card.rr === 'number' ? <>{' · '}{rrText(card.rr)}</> : null}
        </span>
      ) : null}
      <span className="dim">النافذة {ownerWindowAr(card.window)}</span>
      <span className="dim num" style={{ marginInlineStart: 'auto' }}>شمعة {cardTime(card)}</span>
      {cardHint(card.status) ? <div className="ss dim" style={{ flexBasis: '100%', marginTop: 0 }}>{cardHint(card.status)}</div> : null}
    </div>
  )
}

/** الشريط العلويّ لـ«الرئيسيّة» و«غرفة النظام» — حلّ محلّ «الروم» بعد أرشفة 451. */
export function CardBar() {
  const cards = useCards()
  const list = Object.values(cards).filter((c) => c?.symbol).sort((a, b) => String(a.symbol).localeCompare(String(b.symbol)))
  return (
    <div className="card" style={{ padding: '9px 14px', marginBottom: 8, display: 'grid', gap: 6 }}>
      <div style={{ display: 'flex', gap: 10, alignItems: 'baseline', flexWrap: 'wrap' }}>
        <span style={{ fontSize: 13.5, fontWeight: 800 }}>القرار — بطاقة استمرار الاتّجاه</span>
        <span className="dim" style={{ fontSize: 11.5 }}>تُقيَّم مع إغلاق كل شمعة ٥ دقائق · الأقسام تعطيها حقائق خامًا</span>
      </div>
      {list.length === 0
        ? <div className="ss dim" style={{ marginTop: 0 }}>ما وصلت بطاقة لأيّ رمز منذ فتح الشاشة — أوّل بطاقة مع إغلاق الشمعة الجاية.</div>
        : list.map((c) => <CardLine key={c.symbol} card={c} />)}
      <CardHealthStrip compact />
    </div>
  )
}
