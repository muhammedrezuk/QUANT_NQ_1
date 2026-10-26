// «سياق اليوم» — خطّة المالك ١٠-١٧، المرحلة 3، الخطوة 22 (ختم «NQ»): «ويكتب على الموقع: اليوم عطلة، ويكتب كلّ المكتوب
// بهالرسالة، ويشرح سبب العطلة، ويحدّد كم باقي على العطلة القادمة، وشو العطلة السابقة، وكم باقي على إغلاق التداول وإغلاق السوق».
// ١٧/١٠ مساءً (المالك بصورة الصفحة: «بنيتها خام … لا موديل ولا ألوان وترتيب … بدّي ضلّ دقايق لأعرف أرتّبها بعقلي»): أُعيد تصميمها
// لتُقرأ بنظرة: شريط «الآن» بعدّاداته · خطّ الجلسات على 24 ساعة · بطاقات الأصول بألوان حالها · الأخبار · سلّم مستويات الناسداك ·
// السنين الماضية أعمدةً · أداء الاستراتيجيّات بأسمائها العربيّة. تعرض ما يصل فقط — لا تحسب شيئًا من عندها:
//   123 knowledge.context.state · 109 market_data.calendar.state · 124 knowledge.levels.state · 119 knowledge.seasonal.state
//   469 knowledge.accountability.state — وكلّ الساعات بساعة تركيا كما ينشرها الجهاز.
import { useState } from 'react'
import { useStore } from '../core/store'

/* eslint-disable @typescript-eslint/no-explicit-any */
type Any = any

const EXCHANGE_AR: Record<string, string> = {
  SYDNEY: 'سيدني', TOKYO: 'طوكيو', SHANGHAI: 'شنغهاي', HONG_KONG: 'هونغ كونغ', SINGAPORE: 'سنغافورة',
  FRANKFURT: 'فرانكفورت', LONDON: 'لندن', NEW_YORK: 'نيويورك', TORONTO: 'تورونتو', ZURICH: 'زيورخ', GENERAL: 'النافذة العامّة',
}
const SYMBOL_AR: Record<string, string> = {
  USTEC: 'الناسداك', US30: 'الداو جونز', US500: 'الإس آند بي', XAUUSD: 'الذهب', BTCUSD: 'البتكوين',
  EURUSD: 'اليورو/الدولار', GBPUSD: 'الجنيه/الدولار',
}
const HOLIDAY_AR: Record<string, string> = {
  'new-years-day': 'رأس السنة', 'birthday-of-martin-luther-king': 'ميلاد مارتن لوثر كينغ', 'washingtons-birthday': 'يوم الرؤساء',
  'good-friday': 'الجمعة العظيمة', 'memorial-day': 'يوم الذكرى', 'juneteenth-national-independence-day': 'يوم التحرير (جونتينث)',
  'independence-day': 'عيد الاستقلال الأمريكيّ', 'labor-day': 'عيد العمّال', 'columbus-day': 'يوم كولومبوس (البنوك)',
  'veterans-day': 'يوم المحاربين القدامى (البنوك)', 'thanksgiving-day': 'عيد الشكر', 'christmas-day': 'عيد الميلاد',
  'early-close': 'إغلاق مبكّر (نصف يوم)',
}
const NEWS_AR: [RegExp, string][] = [
  [/^Federal Funds Rate/, 'قرار سعر الفائدة الأمريكيّ'], [/^FOMC Statement/, 'بيان اللجنة الفيدراليّة'],
  [/^FOMC Economic Projections/, 'توقّعات اللجنة الاقتصاديّة'], [/^FOMC Press Conference/, 'المؤتمر الصحفيّ للّجنة'],
  [/^FOMC Meeting Minutes/, 'محضر اللجنة الفيدراليّة'], [/^Fed Chair.*Speaks/, 'خطاب رئيس الاحتياطيّ'],
  [/^Fed Chair.*Testif/, 'شهادة رئيس الاحتياطيّ'], [/^Non-Farm Employment Change/, 'الوظائف غير الزراعيّة'],
  [/^Unemployment Rate/, 'معدّل البطالة'], [/^Average Hourly Earnings/, 'متوسّط الأجر بالساعة'],
  [/^Core CPI m\/m/, 'التضخّم الأساسيّ الشهريّ'], [/^Core CPI y\/y/, 'التضخّم الأساسيّ السنويّ'], [/^CPI m\/m/, 'التضخّم الشهريّ'],
  [/^CPI y\/y/, 'التضخّم السنويّ'], [/^Core PCE/, 'نفقات الاستهلاك الأساسيّة'], [/^Core PPI/, 'أسعار المنتجين الأساسيّة'],
  [/^PPI/, 'أسعار المنتجين'], [/^Core Retail Sales/, 'مبيعات التجزئة الأساسيّة'], [/^Retail Sales/, 'مبيعات التجزئة'],
  [/^Advance GDP/, 'الناتج المحلّيّ الأوّليّ'], [/^Prelim GDP/, 'الناتج المحلّيّ التمهيديّ'], [/^Final GDP/, 'الناتج المحلّيّ النهائيّ'],
]
const LEVEL_AR: Record<string, string> = {
  yesterday_high: 'أعلى الأمس', yesterday_low: 'أدنى الأمس', yesterday_close: 'إغلاق الأمس',
  premarket_high: 'أعلى ما قبل الافتتاح', premarket_low: 'أدنى ما قبل الافتتاح',
  overnight_high: 'أعلى الليل', overnight_low: 'أدنى الليل', open: 'سعر الافتتاح',
  first15_high: 'أعلى أوّل ربع ساعة', first15_low: 'أدنى أوّل ربع ساعة',
  week_high: 'أعلى الأسبوع', week_low: 'أدنى الأسبوع', prev_week_high: 'أعلى الأسبوع الماضي', prev_week_low: 'أدنى الأسبوع الماضي',
  month_high: 'أعلى الشهر', month_low: 'أدنى الشهر', prev_month_high: 'أعلى الشهر الماضي', prev_month_low: 'أدنى الشهر الماضي',
}
const STRATEGY_AR: Record<string, string> = {
  '404': 'الاتّجاه', '405': 'الانعكاس', '406': 'الاختراق', '407': 'الارتداد', '408': 'الزخم', '409': 'المدى', '410': 'السيولة',
  '414': 'بطاقة استمرار الاتّجاه',
}
const WEEKDAY_AR = ['الإثنين', 'الثلاثاء', 'الأربعاء', 'الخميس', 'الجمعة', 'السبت', 'الأحد']
const GREEN = 'var(--green)', AMBER = 'var(--amber)', DIM = 'var(--dim)', ACCENT = 'var(--accent)', LINE = 'var(--line)'
const RED = '#e5534b'

const n = (v: number | null | undefined, d = 1) => (v == null || Number.isNaN(v) ? '—' : v.toLocaleString('ar-EG-u-nu-latn', { maximumFractionDigits: d }))
const newsAr = (t: string) => NEWS_AR.find(([re]) => re.test(t))?.[1] ?? t
function span(seconds: number | null | undefined): string {
  if (seconds == null) return '—'
  const s = Math.max(0, Math.round(seconds))
  const d = Math.floor(s / 86400), h = Math.floor((s % 86400) / 3600), m = Math.floor((s % 3600) / 60)
  if (d > 0) return `${d} يوم ${h} ساعة`
  if (h > 0) return `${h} ساعة ${m} دقيقة`
  return `${m} دقيقة`
}
const minutes = (hhmm?: string) => { const [h, m] = String(hhmm ?? '0:0').split(':').map(Number); return (h || 0) * 60 + (m || 0) }
const LTR = ({ children }: { children: React.ReactNode }) => <span dir="ltr" style={{ unicodeBidi: 'isolate' }}>{children}</span>

const card = { background: 'var(--glass)', border: '1px solid var(--glassb)', borderRadius: 12, padding: '12px 14px' } as const
const title = { fontSize: 13, fontWeight: 700, marginBottom: 8 } as const
const pill = (bg: string, fg = '#06121c') => ({ background: bg, color: fg, borderRadius: 999, padding: '2px 10px', fontSize: 12, fontWeight: 700, whiteSpace: 'nowrap' as const })

function Tile({ label, value, note, color }: { label: string; value: string; note?: string; color?: string }) {
  return (
    <div style={{ ...card, minWidth: 150, flex: 1 }}>
      <div style={{ fontSize: 12, color: DIM }}>{label}</div>
      <div className="num" style={{ fontSize: 20, fontWeight: 800, color: color ?? 'inherit', marginTop: 2 }}>{value}</div>
      {note ? <div style={{ fontSize: 11.5, color: DIM, marginTop: 2 }}>{note}</div> : null}
    </div>
  )
}

function NowStrip({ c, cal }: { c: Any; cal: Any }) {
  const t = c.time, h = c.holidays ?? {}
  const holiday = h.today_holiday
  const next = (cal?.next_blocking ?? [])[0]
  const clock = String(t.owner_time ?? '').split(' ')[1]?.slice(0, 5) ?? ''
  return (
    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 10 }}>
      <div style={{ ...card, minWidth: 260, display: 'flex', flexDirection: 'column', gap: 6 }}>
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 10 }}>
          <span className="num" style={{ fontSize: 34, fontWeight: 800 }}><LTR>{clock}</LTR></span>
          <span style={{ fontSize: 15 }}>{WEEKDAY_AR[t.weekday] ?? ''} <span className="num">{String(t.owner_time ?? '').split(' ')[0]}</span></span>
        </div>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, fontSize: 12 }}>
          <span style={pill('var(--glassb)', 'inherit')}>الربع {t.quarter}</span>
          <span style={pill('var(--glassb)', 'inherit')}>النصف {t.half}</span>
          <span style={pill('var(--glassb)', 'inherit')}>الشهر {t.month}</span>
          <span style={pill('var(--glassb)', 'inherit')}>الأسبوع {t.week_of_month} من {t.weeks_in_month}</span>
        </div>
        <div style={{ fontSize: 12, color: DIM }}>
          أوّل أسبوع {t.first_week_full ? 'كامل' : 'ناقص'} · آخر أسبوع {t.last_week_full ? 'كامل' : 'ناقص'} · باقي {t.days_left_in_month} يوم في الشهر
        </div>
        <div>{holiday ? <span style={pill(AMBER)}>عطلة: {HOLIDAY_AR[holiday] ?? holiday} — لا تداول</span>
          // ٢٠٢٦-١٠-٢٦ (فحص المشروع، ختم «nq اصلح»): كان «البتكوين وحده يتداول» — والقانون 23 (٢٣/١٠): لا تداول لأيّ رمز في السبت والأحد.
          : t.weekday >= 5 ? <span style={pill(AMBER)}>عطلة نهاية الأسبوع — لا تداول لأيّ رمز، ومعه البتكوين</span>
          : <span style={pill(GREEN)}>يوم تداول</span>}</div>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, alignItems: 'center', fontSize: 12 }}>
          <span style={{ color: DIM }}>يتداول الآن:</span>
          {(c.schedule ?? []).filter((r: Any) => r.open).length === 0 ? <span style={{ color: DIM }}>لا أصل مفتوح</span>
            : (c.schedule ?? []).filter((r: Any) => r.open).map((r: Any) => <span key={r.symbol} style={pill('#2ea043', '#fff')}>{SYMBOL_AR[r.symbol] ?? r.symbol}</span>)}
        </div>
      </div>
      <Tile label="إغلاق السوق اليوميّ" value={span(t.seconds_to_daily_close)} />
      <Tile label="إغلاق الأسبوع" value={span(t.seconds_to_week_end)} />
      <Tile label="الخبر الحاجب القادم" value={next ? span(next.seconds_until) : 'لا خبر'} note={next ? newsAr(next.title) : 'لا خبر حاجب معروف'} color={next && next.seconds_until < 3600 ? RED : undefined} />
      <Tile label="العطلة القادمة" value={h.next_holiday ? `${n(h.next_holiday.days_left, 0)} يوم` : '—'} note={h.next_holiday ? `${HOLIDAY_AR[h.next_holiday.name] ?? h.next_holiday.name} · ${h.next_holiday.date}` : ''} />
      <Tile label="العطلة السابقة" value={h.previous_holiday ? `قبل ${n(h.previous_holiday.days_ago, 0)} يوم` : '—'} note={h.previous_holiday ? `${HOLIDAY_AR[h.previous_holiday.name] ?? h.previous_holiday.name} · ${h.previous_holiday.date}` : ''} />
      <Tile label="نهاية الشهر · الربع · السنة" value={span(t.seconds_to_month_end)} note={`الربع ${span(t.seconds_to_quarter_end)} · السنة ${span(t.seconds_to_year_end)}`} />
    </div>
  )
}

function SessionsTimeline({ c }: { c: Any }) {
  const ex = c?.sessions?.exchanges ?? []
  const nowMin = minutes(String(c.time?.owner_time ?? '').split(' ')[1])
  const W = 1000, rowH = 22, padL = 120, H = ex.length * rowH + 26
  const x = (m: number) => padL + (m / 1440) * (W - padL - 10)
  const overlaps = c?.sessions?.overlaps ?? []
  return (
    <div style={card}>
      <div style={title}>الجلسات على مدار اليوم — بساعة تركيا <span style={{ color: DIM, fontWeight: 400, fontSize: 12 }}>(الأخضر مفتوحة الآن · الخطّ الأحمر الساعة الآن)</span></div>
      <svg viewBox={`0 0 ${W} ${H}`} style={{ width: '100%', direction: 'ltr' }}>
        {[0, 3, 6, 9, 12, 15, 18, 21, 24].map((hr) => (
          <g key={hr}>
            <line x1={x(hr * 60)} x2={x(hr * 60)} y1={0} y2={H - 18} stroke={LINE} />
            <text x={x(hr * 60)} y={H - 4} fontSize={11} fill="currentColor" opacity={0.6} textAnchor="middle">{String(hr).padStart(2, '0')}:00</text>
          </g>
        ))}
        {ex.map((r: Any, i: number) => {
          const a = minutes(r.open_owner), b = minutes(r.close_owner)
          const segs = b > a ? [[a, b]] : [[a, 1440], [0, b]]
          const y = i * rowH + 4
          return (
            <g key={r.name}>
              <text x={padL - 8} y={y + 13} fontSize={12} fill="currentColor" textAnchor="end">{EXCHANGE_AR[r.name] ?? r.name}</text>
              {segs.map(([s, e], k) => <rect key={k} x={x(s)} y={y} width={Math.max(2, x(e) - x(s))} height={rowH - 8} rx={4}
                fill={r.open ? '#2ea043' : '#57606a'} opacity={r.open ? 0.9 : 0.55} />)}
            </g>
          )
        })}
        <line x1={x(nowMin)} x2={x(nowMin)} y1={0} y2={H - 18} stroke={RED} strokeWidth={2} />
      </svg>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginTop: 6, fontSize: 12.5 }}>
        {overlaps.length === 0 ? <span style={{ color: DIM }}>لا جلستان متّصلتان الآن</span> : overlaps.map((o: Any, i: number) => (
          <span key={i} style={pill(ACCENT)}>🔗 {EXCHANGE_AR[o.a] ?? o.a} + {EXCHANGE_AR[o.b] ?? o.b} حتّى <LTR>{o.until_owner}</LTR> (باقي {span(o.seconds_left)})</span>
        ))}
        {c?.sessions?.next_open ? <span style={{ color: DIM }}>التالية افتتاحًا: {EXCHANGE_AR[c.sessions.next_open] ?? c.sessions.next_open} بعد {span(c.sessions.seconds_to_next_open)}</span> : null}
      </div>
    </div>
  )
}

function Assets({ c }: { c: Any }) {
  const rows = c?.schedule ?? []
  return (
    <div style={card}>
      <div style={title}>الأصول اليوم — كلّ أصلٍ مع بورصته</div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(190px, 1fr))', gap: 8 }}>
        {rows.map((r: Any) => {
          // ٢٥/١٠ (القانون 21): الساعة الأخيرة — لا صفقة جديدة، والمفتوح يكمل حتّى الإغلاق
          const state = !r.open ? ['مغلقة', '#57606a', `تفتح بعد ${span(r.seconds_to_open)}`] : r.first_minutes
            ? ['أوّل ربع ساعة', AMBER, 'لا دخول الآن'] : r.last_hour
            ? ['الساعة الأخيرة', AMBER, `لا صفقة جديدة · المفتوح يُغلق بعد ${span(r.seconds_to_close)}`]
            : ['مفتوحة', '#2ea043', `الخطّ الأحمر بعد ${span(r.seconds_to_close)}`]
          return (
            <div key={r.symbol} style={{ border: `1px solid ${state[1]}`, borderRadius: 10, padding: '8px 10px' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <span style={{ fontWeight: 700 }}>{SYMBOL_AR[r.symbol] ?? r.symbol}</span>
                <span style={pill(state[1], '#fff')}>{state[0]}</span>
              </div>
              <div style={{ fontSize: 12, color: DIM, marginTop: 4 }}>{EXCHANGE_AR[r.session] ?? r.session} · من {r.open_owner} إلى {r.close_owner}{r.no_new_owner ? ` · لا جديد بعد ${r.no_new_owner}` : ''}</div>
              <div style={{ fontSize: 12.5, marginTop: 2 }}>{state[2]}</div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

function News({ cal }: { cal: Any }) {
  const rows = cal?.next_blocking ?? []
  return (
    <div style={card}>
      <div style={title}>الأخبار الحاجبة القادمة <span style={{ color: DIM, fontWeight: 400, fontSize: 12 }}>(لا دخول 15 دقيقة قبلها وبعدها على أصول عملتها — والدولار على كلّ الرموز — ويُغلق المفتوح)</span></div>
      {cal?.in_event_window ? <div style={{ ...pill(RED, '#fff'), display: 'inline-block', marginBottom: 6 }}>الآن داخل نافذة خبر</div> : null}
      {rows.length === 0 ? <div style={{ color: DIM }}>لا خبر حاجب معروف</div> : rows.map((e: Any, i: number) => (
        <div key={i} style={{ display: 'flex', justifyContent: 'space-between', borderTop: i ? `1px solid ${LINE}` : 'none', padding: '6px 0' }}>
          <span>{newsAr(e.title)}</span>
          <span className="num" style={{ fontWeight: 700, color: e.seconds_until < 3600 ? RED : 'inherit' }}>بعد {span(e.seconds_until)}</span>
        </div>
      ))}
    </div>
  )
}

function Ladder({ levels, openNow }: { levels: Record<string, Any> | undefined; openNow: string[] }) {
  const all = ['USTEC', 'US500', 'US30', 'XAUUSD', 'BTCUSD', 'EURUSD', 'GBPUSD'].filter((s) => levels?.[s]?.available)
  const symbols = [...all.filter((s) => openNow.includes(s)), ...all.filter((s) => !openNow.includes(s))]
  const [sym, setSym] = useState(symbols[0] ?? 'USTEC')
  const lv = levels?.[symbols.includes(sym) ? sym : symbols[0]]
  if (!lv) return <div style={card}><div style={title}>المستويات</div><div style={{ color: DIM }}>تصل مع أوّل إغلاق ربع ساعةٍ حيّ</div></div>
  const mv = lv.movement_pips ?? {}, gap = lv.gap
  const above = (lv.nearest_above ?? []).slice().reverse(), below = lv.nearest_below ?? []
  const row = (m: Any, color: string) => (
    <div key={m.name} style={{ display: 'flex', justifyContent: 'space-between', padding: '4px 8px', borderInlineStart: `3px solid ${color}`, margin: '3px 0' }}>
      <span>{LEVEL_AR[m.name] ?? m.name}</span>
      <span className="num"><b>{n(m.price, 2)}</b> <span style={{ color }}>({n(m.pips_from_last)} بِب)</span></span>
    </div>
  )
  return (
    <div style={card}>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, alignItems: 'center', marginBottom: 8 }}>
        <span style={title}>سلّم المستويات</span>
        {symbols.map((s) => <button key={s} onClick={() => setSym(s)} style={{ ...pill(s === lv.symbol ? ACCENT : 'transparent', s === lv.symbol ? '#06121c' : 'inherit'), border: `1px solid ${openNow.includes(s) ? '#2ea043' : 'var(--glassb)'}`, cursor: 'pointer', fontFamily: 'inherit' }}>{SYMBOL_AR[s] ?? s}{openNow.includes(s) ? ' ●' : ''}</button>)}
      </div>
      {above.map((m: Any) => row(m, RED))}
      <div style={{ textAlign: 'center', margin: '6px 0', fontWeight: 800 }}><span style={pill(ACCENT)}>السعر الآن {n(lv.last, 2)}</span></div>
      {below.map((m: Any) => row(m, '#2ea043'))}
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginTop: 10 }}>
        <Tile label="الفجوة" value={gap ? `${n(gap.pips)} بِب` : '—'} note={gap ? `${gap.opened === 'above_yesterday_close' ? 'افتتح فوق إغلاق الأمس' : gap.opened === 'below_yesterday_close' ? 'افتتح تحته' : 'افتتح عنده'} · ${gap.filled ? 'امتلأت' : 'لم تمتلئ'}` : ''} />
        <Tile label="مدى اليوم" value={`${n(mv.today)} بِب`} note={`الأمس ${n(mv.yesterday)}`} />
        <Tile label="الأسبوع · الشهر" value={`${n(mv.week)} · ${n(mv.month)}`} note="بِب" />
      </div>
    </div>
  )
}

function Seasons({ se }: { se: Any }) {
  const by = se?.facts?.by_year
  if (!by) return null
  const bars = (unit: 'month' | 'quarter', head: string) => {
    const years = Object.keys(by[unit] ?? {}).sort().reverse()
    const max = Math.max(1, ...years.map((y) => Math.abs(by[unit][y].change_pct ?? 0)))
    return (
      <div style={{ flex: 1, minWidth: 260 }}>
        <div style={{ fontSize: 12.5, color: DIM, marginBottom: 4 }}>{head}</div>
        {years.map((y) => {
          const r = by[unit][y], v = r.change_pct ?? 0
          return (
            <div key={y} style={{ display: 'grid', gridTemplateColumns: '78px 1fr 70px', alignItems: 'center', gap: 6, margin: '2px 0', fontSize: 12 }}>
              <span className="num">{y}{r.complete ? '' : ' (الآن)'}</span>
              <div dir="ltr" style={{ position: 'relative', height: 12, background: 'var(--glassb)', borderRadius: 6 }}>
                <div style={{ position: 'absolute', left: '50%', top: 0, bottom: 0, width: 1, background: LINE }} />
                <div style={{ position: 'absolute', height: 12, borderRadius: 6, background: v >= 0 ? '#2ea043' : RED,
                  left: `${v >= 0 ? 50 : 50 - (Math.abs(v) / max) * 50}%`, width: `${(Math.abs(v) / max) * 50}%` }} />
              </div>
              <span className="num" style={{ color: v >= 0 ? '#2ea043' : RED, fontWeight: 700 }}>{v >= 0 ? '+' : ''}{n(v, 2)}٪</span>
            </div>
          )
        })}
      </div>
    )
  }
  return (
    <div style={card}>
      <div style={title}>الناسداك في الوقت نفسه من السنين الماضية <span style={{ color: DIM, fontWeight: 400, fontSize: 12 }}>(التغيّر من الافتتاح إلى الإغلاق)</span></div>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 20 }}>
        {bars('month', `الشهر ${by.month_number}`)}
        {bars('quarter', `الربع ${by.quarter_number}`)}
      </div>
    </div>
  )
}

function Performance({ acc }: { acc: Any }) {
  const per = acc?.facts?.by_strategy_period
  if (!per) return null
  const names = Object.keys(per).filter((k) => k !== 'date_zone' && k !== 'today')
  const money = (v?: number) => <span className="num" style={{ color: (v ?? 0) > 0 ? '#2ea043' : (v ?? 0) < 0 ? RED : DIM, fontWeight: 700 }}>{n(v, 2)}$</span>
  return (
    <div style={card}>
      <div style={title}>أداء الاستراتيجيّات <span style={{ color: DIM, fontWeight: 400, fontSize: 12 }}>(بتاريخ تركيا · بين القوسين عدد الصفقات)</span></div>
      {names.length === 0 ? <div style={{ color: DIM }}>لا صفقة مغلقة بعد</div> : (
        <table style={{ width: '100%', fontSize: 12.5, borderCollapse: 'collapse' }}>
          <thead><tr style={{ color: DIM, textAlign: 'right' }}><th style={{ padding: 4 }}>الاستراتيجيّة</th><th>اليوم</th><th>الأسبوع</th><th>آخر الأشهر</th></tr></thead>
          <tbody>{names.map((s) => {
            const p = per[s], id = s.split(':').pop() ?? s
            return (
              <tr key={s} style={{ borderTop: `1px solid ${LINE}` }}>
                <td style={{ padding: 4, fontWeight: 700 }}>{STRATEGY_AR[id] ?? s} <span style={{ color: DIM, fontWeight: 400 }}>({id})</span></td>
                <td>{money(p.today?.total_usd)} <span style={{ color: DIM }}>({p.today?.n ?? 0})</span></td>
                <td>{money(p.this_week?.total_usd)} <span style={{ color: DIM }}>({p.this_week?.n ?? 0})</span></td>
                <td>{Object.entries(p.by_month ?? {}).slice(-3).map(([m, v]: [string, Any]) => <span key={m} style={{ marginInlineEnd: 10 }}><span className="num" style={{ color: DIM }}>{m}</span> {money(v.total_usd)}</span>)}</td>
              </tr>
            )
          })}</tbody>
        </table>
      )}
    </div>
  )
}

export default function DayContext() {
  const streams = useStore((s) => s.streams) as Record<string, Any>
  const levels = useStore((s) => s.symbolStreams['knowledge.levels.state']) as Record<string, Any> | undefined
  const c = streams['knowledge.context.state']
  const cal = streams['market_data.calendar.state']
  const se = streams['knowledge.seasonal.state']
  const acc = streams['knowledge.accountability.state']
  if (!c) return <div className="section"><div className="ss">لم يصل سياق اليوم بعد — يصل كلّ دقيقة بعد إقلاع الجهاز.</div></div>
  if (c.available === false) return <div className="section"><div className="ss">قاعدة المناطق الزمنيّة غائبة عن النواة — لا سياق.</div></div>
  return (
    <div className="section" style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
      <NowStrip c={c} cal={cal} />
      <SessionsTimeline c={c} />
      <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 2fr) minmax(0, 1fr)', gap: 10 }}>
        <Assets c={c} />
        <News cal={cal} />
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1fr) minmax(0, 1fr)', gap: 10 }}>
        <Ladder levels={levels} openNow={(c.schedule ?? []).filter((r: Any) => r.open).map((r: Any) => r.symbol)} />
        <Seasons se={se} />
      </div>
      <Performance acc={acc} />
    </div>
  )
}
