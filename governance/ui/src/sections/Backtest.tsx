// الاختبار التاريخيّ — النظام كاملًا على تِكّات سي‑تريدر الحقيقيّة.
// ٢٠٢٦-١٠-٠٦ (ختم المالك «ابنيها كامل بهل صفحة nq» ثمّ «شيل منها كل شي اله علاقة بالقسم كريبتو
// القديم nq»): الجهاز يشغّل الاختبار عمليّةً خلفيّة، والصفحة تطلقه وتعرض تقدّمه ونتيجته. خرج منها
// الدفتر الورقيّ السريع على ملفّات شموع البتكوين الجاهزة (القسم القديم) — الملفّات باقية مكانها.
import { useCallback, useEffect, useMemo, useState } from 'react'
import { ComboBuilder, ComboReport } from './BacktestCombo'

interface Window { from?: string | null; to?: string | null }
interface Catalog {
  ok: boolean
  error?: string
  windows?: { recorded?: Window | null; ctrader?: Record<string, Window> }
  symbols?: string[]
  parameters?: { name: string; value: number }[]
  atom_knobs?: string[]
  analyzers?: string[]
  calib_fields?: string[]
  max_workers?: number
  year?: { label: string; from: string; to: string; symbol: string }
}
interface RunRow {
  name: string
  mode?: string
  status: 'running' | 'done' | 'failed' | 'stopped'
  started_at?: number
  ended_at?: number
  from?: number
  to?: number
  symbols?: string[]
  source?: string
  workers?: number
  progress?: string
  brief?: { 'صافي'?: number; 'صفقات'?: number; 'نسبة_الربح'?: number | null; 'عوائد'?: Record<string, number>; 'الاسم'?: string }
  error_tail?: string
  /** ٢٠٢٦-١٠-٠٦: تجارب العيار المستمرّ (`backtest/calibration_loop.py`) — سببها مكتوب معها. */
  note?: string
}
type Summary = Record<string, unknown>
interface Report { ok: boolean; error?: string; name?: string; texts?: Record<string, string>; folder?: string; summary?: Summary; trades?: Record<string, string>[]; entries?: { time: number; symbol: string; side?: string; sections: Record<string, string> }[] }
interface CalibRow { symbol: string; analyzer: string; path: string; field: string; value: string }

const SYMBOL_AR: Record<string, string> = {
  XAUUSD: 'الذهب', BTCUSD: 'البتكوين', USTEC: 'الناسداك', US30: 'داو جونز', US500: 'إس آند بي',
  EURUSD: 'يورو/دولار', GBPUSD: 'جنيه/دولار',
}
// ٢٠٢٦-١٠-٠٩ (ختم المالك «NQ» — إلغاء مفاتيح السرعة إلى الأرشيف): خرجت أسماء المفاتيح الأربعة وتفعيل شخصيّة
// الأفق — فهرس الخادم (`backtest/full_panel.catalog`) لا يعرض صفًّا بلا قارئ في الكود.
const PARAM_AR: Record<string, string> = {
  ABNORMALITY_GAIN: 'ربح الشذوذ في القوّة', ANALYSIS_FAST_REQUIRED_DEPTH: 'عمق المسار السريع المطلوب',
  ANALYSIS_FAST_WEIGHT: 'وزن المسار السريع', ANALYSIS_SLOW_REQUIRED_DEPTH: 'عمق المسار البطيء المطلوب',
  ANALYSIS_SLOW_WEIGHT: 'وزن المسار البطيء', CONFIDENCE_BLEND: 'مزج الثقة',
  DECISION_BUY_MIN_DIRECTION: 'أدنى اتّجاه للشراء', DECISION_CONFLICT_RATIO: 'نسبة التعارض',
  DECISION_CONTEXT_WEIGHT: 'وزن الأقسام (السياق) في الدرجة', DECISION_DIRECTIONAL_WEIGHT: 'وزن الأصوات الاتّجاهيّة',
  DECISION_ELIGIBILITY_MIN_CONFIDENCE: 'أدنى ثقة للأهليّة', DECISION_FILTER_TTL_S: 'صلاحيّة المرشّحات (ثانية)',
  DECISION_LIVE_STALE_AFTER_S: 'قِدم الدمج الحيّ (ثانية)', DECISION_LOW_QUALITY_FACTOR: 'معامل الجودة الرديئة',
  DECISION_MAX_PER_SYMBOL: 'أقصى مراكز لكلّ رمز', DECISION_MIN_CONFIDENCE: 'أدنى ثقة للقرار',
  DECISION_MIN_CURRENT_DEPTH: 'أدنى عمق للقرار', DECISION_MIN_PARTICIPATION: 'أدنى مشاركة للقرار',
  DECISION_MIN_SCORE: 'أدنى درجة', DECISION_MIN_STRENGTH: 'أدنى قوّة', DECISION_NEUTRAL_BAND: 'نطاق الحياد',
  DECISION_SELL_MIN_DIRECTION: 'أدنى اتّجاه للبيع', DEPTH_BLEND: 'مزج العمق',
  INTEGRITY_BLEND: 'مزج السلامة',
  MOVEMENT_FLOOR: 'أرضيّة الحركة', NEWS_HIGH_WINDOW_AFTER_MIN: 'نافذة الخبر العالي بعده (دقيقة)',
  NEWS_HIGH_WINDOW_BEFORE_MIN: 'نافذة الخبر العالي قبله (دقيقة)', NEWS_LIGHT_WINDOW_MIN: 'نافذة الخبر الخفيف (دقيقة)',
  NEWS_MEDIUM_WINDOW_MIN: 'نافذة الخبر المتوسّط (دقيقة)', RISK_DIAL: 'مفتاح المخاطرة',
  STALE_AFTER_S: 'أفق القِدم (ثانية)',
}
const KNOB_AR: Record<string, string> = {
  prob_depth: 'عمق الاحتمالات المطلوب', prob_confidence: 'عتبة ثقة الاحتمالات',
  strat_active: 'أقلّ وزنٍ نشط للاستراتيجيّات معًا', strat_depth: 'عمق الاستراتيجيّات المطلوب',
  strat_confidence: 'عتبة ثقة الاستراتيجيّات',
}
const ANALYZER_AR: Record<string, string> = {
  trend: 'الاتّجاه', momentum: 'الزخم', volatility: 'التذبذب', volume: 'الحجم', spread: 'السبريد',
  candle: 'الشموع', gap: 'الفجوات', session: 'الجلسات', time: 'أثر الوقت', correlation: 'الارتباط',
  relative_strength: 'القوّة النسبيّة', velocity: 'السرعة', acceleration: 'التسارع',
  volume_quality: 'جودة الحجم', noise: 'الضوضاء',
}
const FIELD_AR: Record<string, string> = {
  required_depth: 'العمق المطلوب', confidence_threshold: 'عتبة الثقة', strength_threshold: 'عتبة القوّة',
  stale_after_s: 'القِدم (ثانية)', direction_neutral_band: 'نطاق الحياد', weight: 'الوزن',
}
const SECTION_AR: Record<string, string> = {
  '150': 'التحليل', '200': 'البنية', '250': 'السيولة', '300': 'الإحصاء', '350': 'الاحتمالات', '400': 'الاستراتيجيّات',
  analysis: 'التحليل', structure: 'البنية', liquidity: 'السيولة', stats: 'الإحصاء', probability: 'الاحتمالات', strategy: 'الاستراتيجيّات',
}
const REASON_AR: Record<string, string> = {
  SL: 'وقف', TP: 'هدف', SYSTEM: 'إدارة النظام', END_OF_RUN: 'نهاية الاختبار', MANUAL: 'يدويّ',
}
const STATUS_AR: Record<string, string> = { running: 'يعمل', done: 'انتهى', failed: 'فشل', stopped: 'أُوقف' }
const EVENT_AR: Record<string, string> = {
  'market_data.candle_closed': 'شموع أُغلقت', 'structure.levels.state': 'سلّم مستويات نُشر',
  'strategy.setup.proposed': 'إعدادات استراتيجيّة', 'decision.evaluated.state': 'قرارات قُيّمت',
  'decision.gate.passed': 'قرارات عبرت البوّابة', 'execution.order.requested': 'طلبات دخول',
  'trading.final_decision': 'أوامر نهائيّة', 'execution.order.rejected': 'أوامر رُدّت',
  'platform.trade_event': 'أحداث صفقات', 'market.outcome.realized': 'نتائج محقّقة',
}

const num = (n?: number | null, d = 2) =>
  n == null || !Number.isFinite(n) ? '—' : n.toLocaleString('ar-EG-u-nu-latn', { maximumFractionDigits: d })
const when = (epoch?: number) => {
  if (!epoch) return '—'
  return new Date(epoch * 1000).toLocaleString('ar-EG-u-nu-latn', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit', timeZone: 'UTC' })
}
const chip = (on: boolean) => ({
  fontSize: 12, padding: '3px 10px', borderRadius: 8, cursor: 'pointer', fontFamily: 'inherit',
  whiteSpace: 'nowrap' as const, background: on ? 'var(--accent)' : 'transparent',
  color: on ? '#06121c' : 'var(--dim)', border: `1px solid ${on ? 'var(--accent)' : 'var(--glassb)'}`,
})
const field = { margin: 0, padding: '4px 7px' }
const lbl = { fontSize: 12, display: 'flex', alignItems: 'center', gap: 6 } as const
const toInput = (iso?: string | null) => (iso ? iso.slice(0, 16) : '')

export default function Backtest() {
  const [catalog, setCatalog] = useState<Catalog | null>(null)
  const [source, setSource] = useState<'ctrader' | 'recorded' | 'year' | 'combo' | 'direction' | 'strategy' | 'levels' | 'detectors' | 'system'>('ctrader')
  const [symbols, setSymbols] = useState<string[]>(['XAUUSD', 'BTCUSD', 'USTEC'])
  const [from, setFrom] = useState('')
  const [to, setTo] = useState('')
  const [balance, setBalance] = useState(10000)
  const [workers, setWorkers] = useState(4)
  const [warmup, setWarmup] = useState(1.5)
  const [coalesce, setCoalesce] = useState(0)
  const [knobs, setKnobs] = useState<Record<string, string>>({})
  const [params, setParams] = useState<Record<string, string>>({})
  const [showParams, setShowParams] = useState(false)
  const [calibs, setCalibs] = useState<CalibRow[]>([])
  const [draft, setDraft] = useState<CalibRow>({ symbol: '*', analyzer: 'trend', path: '*', field: 'required_depth', value: '' })
  const [runs, setRuns] = useState<RunRow[]>([])
  const [note, setNote] = useState<{ ok: boolean; text: string } | null>(null)
  const [busy, setBusy] = useState(false)
  const [report, setReport] = useState<Report | null>(null)
  const [showTech, setShowTech] = useState(false)

  useEffect(() => {
    fetch('/gov/backtest/full/catalog', { cache: 'no-store' })
      .then((r) => r.json() as Promise<Catalog>)
      .then((c) => {
        setCatalog(c)
        const w = c.windows?.ctrader?.XAUUSD
        if (w?.to) {
          const end = new Date(w.to + 'Z')
          const start = new Date(end.getTime() - 24 * 3600 * 1000)
          setTo(toInput(end.toISOString()))
          setFrom(toInput(start.toISOString()))
        }
      })
      .catch(() => setCatalog({ ok: false, error: 'خادم اللوحة لا يجيب' }))
  }, [])

  const loadRuns = useCallback(() => {
    fetch('/gov/backtest/full/runs', { cache: 'no-store' })
      .then((r) => r.json() as Promise<{ ok: boolean; runs?: RunRow[] }>)
      .then((j) => setRuns((j.runs ?? []).filter((r) => r.mode !== 'lab')))
      .catch(() => undefined)
  }, [])
  useEffect(() => {
    loadRuns()
    const t = window.setInterval(loadRuns, 5000)
    return () => window.clearInterval(t)
  }, [loadRuns])

  const open = useCallback((name: string) => {
    fetch(`/gov/backtest/full/run/${name}`, { cache: 'no-store' })
      .then((r) => r.json() as Promise<Report>)
      .then((j) => setReport(j))
      .catch(() => setReport({ ok: false, error: 'تعذّر قراءة التقرير' }))
  }, [])

  const start = async () => {
    setBusy(true); setNote(null)
    try {
      const r = await fetch('/gov/backtest/full/start', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(source === 'year' ? { source } : {
          source, symbols, from: from || undefined, to: to || undefined, balance, workers,
          warmup_hours: warmup, coalesce_s: coalesce, knobs, parameters: params,
          calibs: calibs.map((c) => ({ ...c, value: Number(c.value) })),
        }),
      })
      const j = await r.json() as { ok: boolean; error?: string; name?: string }
      setNote(j.ok ? { ok: true, text: 'بدأ على الجهاز — التقدّم في قائمة التشغيلات تحت' } : { ok: false, text: j.error ?? 'تعذّر الإطلاق' })
      loadRuns()
    } catch {
      setNote({ ok: false, text: 'خطأ اتّصال بخادم اللوحة' })
    }
    setBusy(false)
  }
  const stop = async (name: string) => {
    await fetch('/gov/backtest/full/stop', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ name }) })
    loadRuns()
  }

  const windowText = useMemo(() => {
    if (source === 'year' || source === 'combo' || source === 'direction' || source === 'strategy' || source === 'levels' || source === 'detectors' || source === 'system') return ''
    if (source === 'recorded') {
      const w = catalog?.windows?.recorded
      return w ? `${w.from ?? '—'} ← ${w.to ?? '—'}` : 'غير متاحة'
    }
    return symbols.map((s) => {
      const w = catalog?.windows?.ctrader?.[s]
      return `${SYMBOL_AR[s] ?? s}: ${w ? `${w.from} ← ${w.to}` : 'لا تِكّات'}`
    }).join(' · ')
  }, [catalog, source, symbols])

  const s = report?.summary ?? {}
  const balanceBox = (s['الرصيد'] ?? {}) as Record<string, number>
  const net = (s['صافي'] as number | undefined) ?? balanceBox['صافي']
  const dd = (s['أقصى_سحب_على_الإغلاقات'] as number | undefined) ?? balanceBox['أقصى_سحب']
  const share = (s['مشاركة_الأقسام_في_التقييم'] ?? {}) as Record<string, number>
  const perSymbol = (s['لكلّ_رمز'] ?? {}) as Record<string, { 'صفقات': number; 'صافي': number }>
  const events = (s['أحداث_مفتاحيّة'] ?? {}) as Record<string, number>
  const health = (s['صحّة_سلسلة_القرار'] ?? {}) as Record<string, string>
  const trades = report?.trades ?? []
  const entries = report?.entries ?? []

  return (
    <div className="section" style={{ display: 'flex', flexDirection: 'column', gap: 10, minHeight: 0 }}>
      <div className="scard">
        <div className="st" style={{ fontWeight: 700, fontSize: 16 }}>اختبار تاريخيّ — النظام كاملًا على تِكّات سي‑تريدر</div>
        <div className="ss dim" style={{ marginTop: 4 }}>
          كلّ وحدات النظام (١٧٨) على تِكّات حقيقيّة بترتيبها الزمنيّ، وبنسخةٍ من عياراتك المعتمدة. التنفيذ عند
          محاكي الإكسبرت بعقده نفسه: وقف وأهداف وإغلاق جزئيّ وعمولة مقيسة — بلا حساب حقيقيّ ولا شبكة.
          ما تغيّره هنا يجري على النسخة وحدها. الجهاز يشغّله في الخلفيّة؛ لا تحتاج أن تبقى على الصفحة.
        </div>
      </div>

      <div className="scard" style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, alignItems: 'center' }}>
          <span className="st" style={{ fontSize: 12 }}>البيانات</span>
          <button style={chip(source === 'ctrader')} onClick={() => setSource('ctrader')}>تِكّات سي‑تريدر التاريخيّة</button>
          <button style={chip(source === 'recorded')} onClick={() => setSource('recorded')}>تِكّات النظام المسجّلة</button>
          <button style={chip(source === 'combo')} onClick={() => setSource('combo')}>منشئ التوليفة — أيّ ذرّات وشروط وإدارة صفقة</button>
          <button style={chip(source === 'direction')} onClick={() => setSource('direction')}>اتّجاه الفريمات — صاعد أو هابط</button>
          <button style={chip(source === 'strategy')} onClick={() => setSource('strategy')}>البحث عن استراتيجيّة رابحة — بناء الصفقة</button>
          <button style={chip(source === 'levels')} onClick={() => setSource('levels')}>مستويات المتداول — السيناريوهان داخل التوليفة</button>
          <button style={chip(source === 'detectors')} onClick={() => setSource('detectors')}>اتّجاه الجلسة — الكواشف الثلاثة</button>
          <button style={chip(source === 'system')} onClick={() => setSource('system')}>المنظومة كما هي — الأزواج السبعة</button>
          <span className="dim num" style={{ fontSize: 11 }}>{windowText}</span>
        </div>
        {source === 'year' ? (
          <div className="ss" style={{ fontSize: 12.5, lineHeight: 1.9 }}>
            <div>سنة 2023 كاملة على الناسداك، وكلّ ما قبلها للتحضير. الاتّجاه من قراءات داو الثلاث المعتمدة، كلٌّ وحدها، ومعها الصفقات نفسها بجهةٍ عشوائيّة مرجعًا.</div>
            <div className="dim">قوانينك المختومة: جلسة نيويورك وحدها (16:45–23:00 بساعتك) · لا دخول ±6 دقائق حول خبر الدولار الأحمر · ربع ساعة انتظار بعد كلّ صفقة · الوقت الكافي للهدف الثالث · وقف المنظومة الحيّ · ثلاثة أهداف بالأثلاث · مخاطرة 1٪ للصفقة.</div>
          </div>
        ) : null}
        <div style={{ display: source === 'year' || source === 'combo' || source === 'direction' || source === 'strategy' || source === 'levels' || source === 'detectors' || source === 'system' ? 'none' : 'flex', flexWrap: 'wrap', gap: 8, alignItems: 'center' }}>
          <span className="st" style={{ fontSize: 12 }}>الرموز</span>
          {(catalog?.symbols ?? Object.keys(SYMBOL_AR)).map((sym) => (
            <button key={sym} style={chip(symbols.includes(sym))}
              onClick={() => setSymbols((cur) => cur.includes(sym) ? cur.filter((x) => x !== sym) : [...cur, sym])}>
              {SYMBOL_AR[sym] ?? sym}
            </button>
          ))}
        </div>
        <div style={{ display: source === 'year' || source === 'combo' || source === 'direction' || source === 'strategy' || source === 'levels' || source === 'detectors' || source === 'system' ? 'none' : 'flex', flexWrap: 'wrap', gap: 12, alignItems: 'center' }}>
          <label className="dim" style={lbl}>من (غرينتش)
            <input className="cfginput" type="datetime-local" style={field} value={from} onChange={(e) => setFrom(e.target.value)} />
          </label>
          <label className="dim" style={lbl}>إلى
            <input className="cfginput" type="datetime-local" style={field} value={to} onChange={(e) => setTo(e.target.value)} />
          </label>
          <label className="dim" style={lbl}>رأس مال
            <input className="cfginput num" type="number" min={100} step={100} style={{ ...field, width: 90 }} value={balance} onChange={(e) => setBalance(Number(e.target.value))} />
          </label>
          <label className="dim" style={lbl}>شرائح متوازية
            <input className="cfginput num" type="number" min={1} max={catalog?.max_workers ?? 6} style={{ ...field, width: 56 }} value={workers} onChange={(e) => setWorkers(Number(e.target.value))} />
          </label>
          <label className="dim" style={lbl}>إحماء (ساعة)
            <input className="cfginput num" type="number" min={0} step={0.5} style={{ ...field, width: 60 }} value={warmup} onChange={(e) => setWarmup(Number(e.target.value))} />
          </label>
          <label className="dim" style={lbl}>دمج التِّكّات (ثانية، ٠ = كلّها)
            <input className="cfginput num" type="number" min={0} step={1} style={{ ...field, width: 56 }} value={coalesce} onChange={(e) => setCoalesce(Number(e.target.value))} />
          </label>
        </div>
      </div>

      {source === 'combo' ? <ComboBuilder onStarted={loadRuns} /> : null}

      {source === 'direction' ? (
        <div className="scard" style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          <div className="ss" style={{ fontSize: 12.5, lineHeight: 1.9 }}>
            <div>قاعدتك: «شموع صاعدة وشموع هابطة». الشمعة الصاعدة قمّتها وقاعها أعلى من التي قبلها، والهابطة أدنى. يصير الفريم صاعدًا بعد عددٍ من الشموع الصاعدة المتتالية، ويبقى صاعدًا حتّى يأتي العدد نفسه هابطًا. لا عرضيّ أبدًا.</div>
            <div className="dim">الناسداك · سنتان: 2022 هابطة و2023 صاعدة · الأطر التسعة من الدقيقة إلى الشهر · ثلاث شموع متتالية. ومعها الأدوات تقول صاعد أو هابط فقط — المتوسّطات 5 و10 و50، والسعر مع متوسّط 50، وداو، وداو والمتوسّطات معًا — كم تطابق الشموع، ومتى تنقلب قبلها أو بعدها. بلا صفقات.</div>
          </div>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, alignItems: 'center' }}>
            <button className="btn start" disabled={busy} onClick={() => {
              setBusy(true); setNote(null)
              fetch('/gov/backtest/full/direction/start', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' })
                .then((r) => r.json() as Promise<{ ok: boolean; error?: string }>)
                .then((j) => { setNote(j.ok ? { ok: true, text: 'بدأ على الجهاز — النتيجة في قائمة التشغيلات تحت' } : { ok: false, text: j.error ?? 'تعذّر الإطلاق' }); loadRuns() })
                .catch(() => setNote({ ok: false, text: 'خطأ اتّصال بخادم اللوحة' }))
                .finally(() => setBusy(false))
            }}>قِس الاتّجاه على الجهاز</button>
            <button className="btn" disabled={busy} title="أعدادٌ كثيرة على 2022 و2023 ويُختار الأعلى — على الماضي، وقد لا يصدق في المستقبل" onClick={() => {
              setBusy(true); setNote(null)
              fetch('/gov/backtest/full/direction/start', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ fit: true }) })
                .then((r) => r.json() as Promise<{ ok: boolean; error?: string }>)
                .then((j) => { setNote(j.ok ? { ok: true, text: 'بدأ الضبط على الجهاز — النتيجة في قائمة التشغيلات تحت' } : { ok: false, text: j.error ?? 'تعذّر الإطلاق' }); loadRuns() })
                .catch(() => setNote({ ok: false, text: 'خطأ اتّصال بخادم اللوحة' }))
                .finally(() => setBusy(false))
            }}>اضبط الاتّجاه على الماضي</button>
            <button className="btn" disabled={busy} title="الشارت بعد انتهائه مقسومٌ موجات كما تراها العين، وكم من 100 شمعة قال الجهاز موجتها بما كان يعرفه يومها" onClick={() => {
              setBusy(true); setNote(null)
              fetch('/gov/backtest/full/direction/start', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ describe: true }) })
                .then((r) => r.json() as Promise<{ ok: boolean; error?: string }>)
                .then((j) => { setNote(j.ok ? { ok: true, text: 'بدأت المعايرة على الجهاز — النتيجة في قائمة التشغيلات تحت' } : { ok: false, text: j.error ?? 'تعذّر الإطلاق' }); loadRuns() })
                .catch(() => setNote({ ok: false, text: 'خطأ اتّصال بخادم اللوحة' }))
                .finally(() => setBusy(false))
            }}>عاير الاتّجاه على موجات الماضي</button>
            <button className="btn" disabled={busy} title="الإعدادات المختارة على 2022 و2023 تُطبَّق كما هي على 2024 التي لم يرها" onClick={() => {
              setBusy(true); setNote(null)
              fetch('/gov/backtest/full/direction/start', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ exam: true }) })
                .then((r) => r.json() as Promise<{ ok: boolean; error?: string }>)
                .then((j) => { setNote(j.ok ? { ok: true, text: 'بدأ الامتحان على الجهاز — النتيجة في قائمة التشغيلات تحت' } : { ok: false, text: j.error ?? 'تعذّر الإطلاق' }); loadRuns() })
                .catch(() => setNote({ ok: false, text: 'خطأ اتّصال بخادم اللوحة' }))
                .finally(() => setBusy(false))
            }}>امتحن الاتّجاه على 2024</button>
            <button className="btn" disabled={busy} title="يتعلّم من شارت 2022 و2023 كاملًا كيف تُقرأ الحركة، ثمّ يُمتحن على 2024 كأنّها سوقٌ حقيقيّ" onClick={() => {
              setBusy(true); setNote(null)
              fetch('/gov/backtest/full/direction/start', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ learn: true }) })
                .then((r) => r.json() as Promise<{ ok: boolean; error?: string }>)
                .then((j) => { setNote(j.ok ? { ok: true, text: 'بدأ التعليم على الجهاز — النتيجة في قائمة التشغيلات تحت' } : { ok: false, text: j.error ?? 'تعذّر الإطلاق' }); loadRuns() })
                .catch(() => setNote({ ok: false, text: 'خطأ اتّصال بخادم اللوحة' }))
                .finally(() => setBusy(false))
            }}>علّم الاتّجاه وامتحنه</button>
            <button className="btn" disabled={busy} title="مثله، ومعه حقائق الأقسام الخمسة والأسواق المرتبطة والأخبار والمستويات — يبني الجهاز المخازن الناقصة أوّلًا (ساعات)" onClick={() => {
              setBusy(true); setNote(null)
              fetch('/gov/backtest/full/direction/start', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ learn: true, rich: true, sections: true }) })
                .then((r) => r.json() as Promise<{ ok: boolean; error?: string }>)
                .then((j) => { setNote(j.ok ? { ok: true, text: 'بدأ التعليم بكلّ الأقسام على الجهاز — يبني المخازن أوّلًا، والنتيجة في قائمة التشغيلات' } : { ok: false, text: j.error ?? 'تعذّر الإطلاق' }); loadRuns() })
                .catch(() => setNote({ ok: false, text: 'خطأ اتّصال بخادم اللوحة' }))
                .finally(() => setBusy(false))
            }}>علّم بكلّ الأقسام والأدوات</button>
            {note ? <span style={{ fontSize: 13, color: note.ok ? 'var(--green)' : 'var(--amber)' }}>{note.text}</span> : null}
          </div>
        </div>
      ) : null}

      {source === 'strategy' ? (
        <div className="scard" style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          <div className="ss" style={{ fontSize: 12.5, lineHeight: 1.9 }}>
            <div>الربح من بناء الصفقة لا من معرفة الاتّجاه. لكلّ إغلاق خمس دقائق ولكلّ جهة: لو دخلنا الآن بوقف البنية (20 إلى 45 بِب للناسداك) وثلاثة أهداف بالأثلاث، فكم كان الصافي بوحدة المخاطرة بعد الكلفة؟ والجواب بالخطوط الحمراء كلّها.</div>
            <div className="dim">التلميذ يتعلّم هذا الجواب من 147 معلومة من الأدوات، ويتداول فقط حين يتوقّع ربحًا فوق الكلفة بهامش، ثمّ ينتظر ساعة وربع بعد كلّ صفقة. الامتحان على سنتين: 2022 الهابطة بعد أن يتعلّم على 2018 إلى 2021، و2023 الصاعدة بعد أن يتعلّم على 2018 إلى 2022. والتقرير لكلّ سنة وكلّ شهر بشكلك، ومعه الصفقات نفسها بجهةٍ عشوائيّة، وكم مرّة كان الحساب سيسقط.</div>
          </div>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, alignItems: 'center' }}>
            <button className="btn start" disabled={busy} onClick={() => {
              setBusy(true); setNote(null)
              fetch('/gov/backtest/full/strategy/start', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ symbol: 'USTEC' }) })
                .then((r) => r.json() as Promise<{ ok: boolean; error?: string }>)
                .then((j) => { setNote(j.ok ? { ok: true, text: 'بدأ البحث على الجهاز — التقدّم والنتيجة في قائمة التشغيلات تحت' } : { ok: false, text: j.error ?? 'تعذّر الإطلاق' }); loadRuns() })
                .catch(() => setNote({ ok: false, text: 'خطأ اتّصال بخادم اللوحة' }))
                .finally(() => setBusy(false))
            }}>ابحث على الناسداك</button>
            {note ? <span style={{ fontSize: 13, color: note.ok ? 'var(--green)' : 'var(--amber)' }}>{note.text}</span> : null}
          </div>
        </div>
      ) : null}

      {source === 'levels' ? (
        <div className="scard" style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          <div className="ss" style={{ fontSize: 12.5, lineHeight: 1.9 }}>
            <div>لا استراتيجيّة جديدة: التوليفة الحيّة كما هي (داو الأربع ساعات ومتوسّطات الربع ساعة، ووقف البنية 20 إلى 45، والأثلاث، وكلّ الخطوط الحمراء)، ومعها رأس حربةٍ واحد عند مستويات المتداول: أعلى الأمس وأدناه وإغلاقه، وأعلى الليل وأدناه، وأعلى الأسبوع الماضي وأدناه، وأقرب رقمين مستديرين — تُثبَّت عند افتتاح النافذة من الماضي وحده.</div>
            <div className="dim">السيناريو الأوّل كسرٌ وثبات، والثاني كسرٌ كاذب، كلٌّ في جهة التوليفة وحدها، على شمعة الخمس دقائق ثمّ الدقيقة. والهدف الأخير عند المستوى التالي، قبله لا عليه، ولا صفقة إن كان أقلّ من ثلاثة أضعاف بعد الكلفة، وبجانبه الهدف الثابت ثلاثة أضعاف. بجانبها التوليفة بلا رأس حربة، والجهة العشوائيّة، ومرّات سقوط الحساب، وكم وقفًا ضُرب في أوّل 5 دقائق، وكم صفقةً أخذت كلّ جلسة. على 2022 و2023.</div>
          </div>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, alignItems: 'center' }}>
            <button className="btn start" disabled={busy} onClick={() => {
              setBusy(true); setNote(null)
              fetch('/gov/backtest/full/levels/start', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ symbol: 'USTEC' }) })
                .then((r) => r.json() as Promise<{ ok: boolean; error?: string }>)
                .then((j) => { setNote(j.ok ? { ok: true, text: 'بدأ القياس على الجهاز — التقدّم والنتيجة في قائمة التشغيلات تحت' } : { ok: false, text: j.error ?? 'تعذّر الإطلاق' }); loadRuns() })
                .catch(() => setNote({ ok: false, text: 'خطأ اتّصال بخادم اللوحة' }))
                .finally(() => setBusy(false))
            }}>قِس المستويات على الناسداك</button>
            <button className="btn" disabled={busy} title="الهدف عند المستوى التالي من خريطة المتداول وحدها: الأمس والليل والأسبوع الماضي والرقمان المستديران — التجارب الأربع وبجانبها التوليفة بلا رأس حربة" onClick={() => {
              setBusy(true); setNote(null)
              fetch('/gov/backtest/full/levels/start', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ symbol: 'USTEC', target: 'map' }) })
                .then((r) => r.json() as Promise<{ ok: boolean; error?: string }>)
                .then((j) => { setNote(j.ok ? { ok: true, text: 'بدأ القياس بهدف الخريطة على الجهاز — النتيجة في قائمة التشغيلات تحت' } : { ok: false, text: j.error ?? 'تعذّر الإطلاق' }); loadRuns() })
                .catch(() => setNote({ ok: false, text: 'خطأ اتّصال بخادم اللوحة' }))
                .finally(() => setBusy(false))
            }}>قِس بهدف خريطة المتداول</button>
            <button className="btn" disabled={busy} title="للمعرفة: التوليفة الحيّة كما هي بلا القانون 21 وحده (لا صفقة جديدة في الساعة الأخيرة منذ ٢٥/١٠)، وبجانبها هي نفسها به — والقانون باقٍ خطًّا أحمر في الحيّ" onClick={() => {
              setBusy(true); setNote(null)
              fetch('/gov/backtest/full/levels/start', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ symbol: 'USTEC', target: 'notime' }) })
                .then((r) => r.json() as Promise<{ ok: boolean; error?: string }>)
                .then((j) => { setNote(j.ok ? { ok: true, text: 'بدأ قياس المعرفة على الجهاز — النتيجة في قائمة التشغيلات تحت' } : { ok: false, text: j.error ?? 'تعذّر الإطلاق' }); loadRuns() })
                .catch(() => setNote({ ok: false, text: 'خطأ اتّصال بخادم اللوحة' }))
                .finally(() => setBusy(false))
            }}>قِس التوليفة بلا القانون 21</button>
            {note ? <span style={{ fontSize: 13, color: note.ok ? 'var(--green)' : 'var(--amber)' }}>{note.text}</span> : null}
          </div>
        </div>
      ) : null}

      {source === 'system' ? (
        <div className="scard" style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          <div className="ss" style={{ fontSize: 12.5, lineHeight: 1.9 }}>
            <div>المنظومة كما هي في الشيفرة الآن: التوليفة الحيّة على أزواجها السبعة (الناسداك والداو والإس آند بي والذهب والبتكوين واليورو والجنيه)، بالقانونين الجديدين: لا صفقة جديدة في الساعة الأخيرة، ونافذة الذهب والبتكوين حتّى 23:00 بساعتك. وكلّ قانونٍ آخر كما هو، وحدود الحساب كما حفظتها.</div>
            <div className="dim">لكلّ زوجٍ وسنةٍ وشهرٍ بشكلك، ومعه الجهة العشوائيّة، وسقوط الحساب، وما أغلقته نهاية النافذة، وكم صفقةً أخذت كلّ جلسة، والحساب الافتراضيّ للأزواج السبعة معًا، والناسداك بجانب قياسَي ليلة 23–24/10. على 2022 و2023. يبني الجهاز المخازن الناقصة أوّلًا (نحو نصف ساعة). للمعرفة، بلا حكم.</div>
          </div>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, alignItems: 'center' }}>
            <button className="btn start" disabled={busy} onClick={() => {
              setBusy(true); setNote(null)
              fetch('/gov/backtest/full/system/start', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' })
                .then((r) => r.json() as Promise<{ ok: boolean; error?: string }>)
                .then((j) => { setNote(j.ok ? { ok: true, text: 'بدأ قياس المنظومة على الجهاز — التقدّم والنتيجة في قائمة التشغيلات تحت' } : { ok: false, text: j.error ?? 'تعذّر الإطلاق' }); loadRuns() })
                .catch(() => setNote({ ok: false, text: 'خطأ اتّصال بخادم اللوحة' }))
                .finally(() => setBusy(false))
            }}>قِس المنظومة على الأزواج السبعة</button>
            {note ? <span style={{ fontSize: 13, color: note.ok ? 'var(--green)' : 'var(--amber)' }}>{note.text}</span> : null}
          </div>
        </div>
      ) : null}

      {source === 'detectors' ? (
        <div className="scard" style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          <div className="ss" style={{ fontSize: 12.5, lineHeight: 1.9 }}>
            <div>قياسُ اتّجاهٍ لا صفقات: داخل جلسة نيويورك، أيّ الثلاثة يعرف تغيّر اتّجاه الجلسة أبكر وأصحّ؟ (أ) داو الأربع ساعات · (ب) ترتيب المتوسّطات 5 و10 و50 على الربع ساعة · (ج) ردّ السعر عند مستويات خريطة المتداول بشمعة الخمس دقائق.</div>
            <div className="dim">يبدأ كلٌّ من اتّجاه الافتتاح (داو والمتوسّطات على السوق كاملًا). ولكلّ كاشف: هل سار السعر في الجهة الجديدة بعد ساعة وحتّى الإغلاق، والسوق نفسه مرجعًا · كم نقطةً بعد القمّة أو القاع قالها · كم إشارةً في الجلسة وكم رجع منها خلال نصف ساعة. الناسداك على 2022 و2023، ومعها جلسة 23/10 مثالًا.</div>
          </div>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, alignItems: 'center' }}>
            <button className="btn start" disabled={busy} onClick={() => {
              setBusy(true); setNote(null)
              fetch('/gov/backtest/full/detectors/start', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ symbol: 'USTEC' }) })
                .then((r) => r.json() as Promise<{ ok: boolean; error?: string }>)
                .then((j) => { setNote(j.ok ? { ok: true, text: 'بدأ قياس الكواشف على الجهاز — النتيجة في قائمة التشغيلات تحت' } : { ok: false, text: j.error ?? 'تعذّر الإطلاق' }); loadRuns() })
                .catch(() => setNote({ ok: false, text: 'خطأ اتّصال بخادم اللوحة' }))
                .finally(() => setBusy(false))
            }}>قِس الكواشف الثلاثة على الناسداك</button>
            {note ? <span style={{ fontSize: 13, color: note.ok ? 'var(--green)' : 'var(--amber)' }}>{note.text}</span> : null}
          </div>
        </div>
      ) : null}

      <div className="scard" style={{ display: source === 'year' || source === 'combo' || source === 'direction' || source === 'strategy' || source === 'levels' || source === 'detectors' || source === 'system' ? 'none' : 'flex', flexDirection: 'column', gap: 8 }}>
        <div className="st">مفاتيح التجربة <span className="dim" style={{ fontSize: 11 }}>— الخانة الفارغة = قيمتك المعتمدة الحيّة</span></div>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 12 }}>
          {(catalog?.atom_knobs ?? Object.keys(KNOB_AR)).map((k) => (
            <label key={k} className="dim" style={lbl}>{KNOB_AR[k] ?? k}
              <input className="cfginput num" type="number" style={{ ...field, width: 64 }} value={knobs[k] ?? ''}
                onChange={(e) => setKnobs((cur) => ({ ...cur, [k]: e.target.value }))} />
            </label>
          ))}
        </div>
        <button style={{ ...chip(showParams), alignSelf: 'flex-start' }} onClick={() => setShowParams((v) => !v)}>
          المعاملات المعتمدة ({num(catalog?.parameters?.length ?? 0, 0)}) {showParams ? '▲' : '▼'}
        </button>
        {showParams ? (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(260px, 1fr))', gap: 6 }}>
            {(catalog?.parameters ?? []).map((p) => (
              <label key={p.name} className="dim" style={{ ...lbl, justifyContent: 'space-between' }}>
                <span>{PARAM_AR[p.name] ?? 'معامل'} <span className="num">({num(p.value, 4)})</span></span>
                <input className="cfginput num" type="number" style={{ ...field, width: 80 }} value={params[p.name] ?? ''}
                  onChange={(e) => setParams((cur) => ({ ...cur, [p.name]: e.target.value }))} />
              </label>
            ))}
          </div>
        ) : null}
        <div className="st" style={{ fontSize: 12, marginTop: 4 }}>عيارات المحلّلين</div>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, alignItems: 'center' }}>
          <select className="cfginput" style={field} value={draft.symbol} onChange={(e) => setDraft({ ...draft, symbol: e.target.value })}>
            <option value="*">كلّ الرموز</option>
            {Object.keys(SYMBOL_AR).map((x) => <option key={x} value={x}>{SYMBOL_AR[x]}</option>)}
          </select>
          <select className="cfginput" style={field} value={draft.analyzer} onChange={(e) => setDraft({ ...draft, analyzer: e.target.value })}>
            {(catalog?.analyzers ?? Object.keys(ANALYZER_AR)).map((a) => <option key={a} value={a}>{ANALYZER_AR[a] ?? a}</option>)}
          </select>
          <select className="cfginput" style={field} value={draft.path} onChange={(e) => setDraft({ ...draft, path: e.target.value })}>
            <option value="*">المساران</option><option value="fast">السريع</option><option value="slow">البطيء</option>
          </select>
          <select className="cfginput" style={field} value={draft.field} onChange={(e) => setDraft({ ...draft, field: e.target.value })}>
            {(catalog?.calib_fields ?? Object.keys(FIELD_AR)).map((f) => <option key={f} value={f}>{FIELD_AR[f] ?? f}</option>)}
          </select>
          <input className="cfginput num" type="number" placeholder="القيمة" style={{ ...field, width: 72 }} value={draft.value} onChange={(e) => setDraft({ ...draft, value: e.target.value })} />
          <button className="btn" disabled={draft.value === ''} onClick={() => { setCalibs((c) => [...c, draft]); setDraft({ ...draft, value: '' }) }}>أضف</button>
        </div>
        {calibs.map((c, i) => (
          <div key={i} style={{ fontSize: 12.5, display: 'flex', gap: 8, alignItems: 'center' }}>
            <span>{c.symbol === '*' ? 'كلّ الرموز' : SYMBOL_AR[c.symbol]} · {ANALYZER_AR[c.analyzer]} · {c.path === '*' ? 'المساران' : c.path === 'fast' ? 'السريع' : 'البطيء'} · {FIELD_AR[c.field]} = <span className="num">{c.value}</span></span>
            <button className="btn" style={{ padding: '1px 8px' }} onClick={() => setCalibs((cur) => cur.filter((_, j) => j !== i))}>احذف من القائمة</button>
          </div>
        ))}
      </div>

      <div style={{ display: source === 'combo' || source === 'direction' || source === 'strategy' || source === 'levels' || source === 'detectors' || source === 'system' ? 'none' : 'flex', flexWrap: 'wrap', gap: 8, alignItems: 'center' }}>
        <button className="btn start" disabled={busy || (source !== 'year' && (!symbols.length || !from || !to))} onClick={() => void start()}>شغّل الاختبار على الجهاز</button>
        {note ? <span style={{ fontSize: 13, color: note.ok ? 'var(--green)' : 'var(--amber)' }}>{note.text}</span> : null}
        {catalog && !catalog.ok ? <span style={{ fontSize: 13, color: 'var(--amber)' }}>{catalog.error ?? 'الفهرس غير متاح'}</span> : null}
      </div>

      <div className="scard">
        <div className="st">التشغيلات</div>
        {runs.length === 0 ? <div className="ss dim" style={{ marginTop: 4 }}>لا تشغيل بعد.</div> : null}
        <div style={{ display: 'grid', gap: 6, marginTop: 6 }}>
          {runs.map((r) => (
            <div key={r.name} style={{ display: 'flex', flexWrap: 'wrap', gap: 10, alignItems: 'center', fontSize: 12.5, borderTop: '1px solid var(--line)', paddingTop: 6 }}>
              <span className={r.status === 'done' ? 'green' : r.status === 'running' ? '' : 'amber'}>{STATUS_AR[r.status] ?? r.status}</span>
              {r.mode === 'calibration' ? <span className="dim" title={r.note ?? ''}>🔁 عيار تلقائيّ{r.note ? ` — ${r.note}` : ''}</span> : null}
              <span className="num dim">بدأ {when(r.started_at)}</span>
              <span className="num">{when(r.from)} ← {when(r.to)}</span>
              <span>{(r.symbols ?? []).map((x) => SYMBOL_AR[x] ?? x).join('، ')}</span>
              <span className="dim">{r.mode === 'system' ? 'المنظومة كما هي — الأزواج السبعة' : r.mode === 'detectors' ? `الكواشف الثلاثة لتغيّر اتّجاه الجلسة${r.brief?.['الاسم'] ? ` — ${r.brief['الاسم']}` : ''}` : r.mode === 'levels' ? `مستويات المتداول والسيناريوهان${r.brief?.['الاسم'] ? ` — ${r.brief['الاسم']}` : ''}` : r.mode === 'strategy' ? `البحث عن استراتيجيّة رابحة${r.brief?.['الاسم'] ? ` — ${r.brief['الاسم']}` : ''}` : r.mode === 'direction' ? 'اتّجاه الفريمات' : r.mode === 'combo' ?`توليفة${r.brief?.['الاسم'] ? ` — ${r.brief['الاسم']}` : ''}` : r.mode === 'store' ? 'بناء مخزن الحقائق' : r.mode === 'year' ? 'سنة القياس 2023 — شموع الدقيقة' : `${r.source === 'ctrader' ? 'تِكّات تاريخيّة' : 'تِكّات مسجّلة'} · شرائح ${num(r.workers, 0)}`}</span>
              {r.mode !== 'detectors' && r.mode !== 'system' && r.brief?.['عوائد'] ? (
                <span className="num">صفقات {num(r.brief['صفقات'], 0)} · {Object.entries(r.brief['عوائد']).filter(([k]) => !k.includes('عشوائيّة')).map(([k, v]) => (
                  <span key={k}>{k} <span className={v >= 0 ? 'green' : 'amber'}>{num(v)}٪</span> · </span>
                ))}</span>
              ) : r.mode !== 'detectors' && r.mode !== 'system' && r.brief ? <span className="num">صفقات {num(r.brief['صفقات'], 0)} · صافي <span className={(r.brief['صافي'] ?? 0) >= 0 ? 'green' : 'amber'}>{num(r.brief['صافي'])}</span></span> : null}
              {r.status === 'running' && r.progress ? <span className="dim num" style={{ fontSize: 11 }}>{r.progress}</span> : null}
              {r.status === 'done' ? <button className="btn" style={{ padding: '1px 10px' }} onClick={() => open(r.name)}>اعرض</button> : null}
              {r.status === 'running' ? <button className="btn" style={{ padding: '1px 10px' }} onClick={() => void stop(r.name)}>أوقف</button> : null}
              {r.status === 'failed' && r.error_tail ? <pre style={{ margin: 0, fontSize: 11, whiteSpace: 'pre-wrap', width: '100%' }} className="dim">{r.error_tail}</pre> : null}
            </div>
          ))}
        </div>
      </div>

      {report && !report.ok ? <div className="scard" style={{ color: 'var(--amber)' }}>{report.error}</div> : null}
      {report?.ok && s['kind'] === 'year' ? <YearReport summary={s as unknown as YearSummary} trades={trades} /> : null}
      {report?.ok && s['kind'] === 'combo' ? <ComboReport summary={s} trades={trades} texts={report.texts} folder={report.folder} /> : null}
      {report?.ok && s['kind'] === 'direction' ? (
        <div className="scard">
          <div className="st">اتّجاه الفريمات {report.folder ? <span className="dim num" style={{ fontSize: 11 }}>— {report.folder}</span> : null}</div>
          <pre style={{ whiteSpace: 'pre-wrap', fontSize: 12, marginTop: 6 }}>{report.texts?.['النتيجة.md'] ?? ''}</pre>
          <pre className="dim" style={{ whiteSpace: 'pre-wrap', fontSize: 11, marginTop: 6 }}>{report.texts?.['الاختبار.md'] ?? ''}</pre>
        </div>
      ) : null}
      {report?.ok && (s['kind'] === 'strategy' || s['kind'] === 'levels' || s['kind'] === 'detectors' || s['kind'] === 'system') ? (
        <div className="scard">
          <div className="st">{s['kind'] === 'system' ? 'المنظومة كما هي — الأزواج السبعة' : s['kind'] === 'detectors' ? 'الكواشف الثلاثة لتغيّر اتّجاه الجلسة' : s['kind'] === 'levels' ? 'مستويات المتداول والسيناريوهان' : 'البحث عن استراتيجيّة رابحة'} {report.folder ? <span className="dim num" style={{ fontSize: 11 }}>— {report.folder}</span> : null}</div>
          <pre style={{ whiteSpace: 'pre-wrap', fontSize: 12, marginTop: 6 }}>{report.texts?.['النتيجة.md'] ?? ''}</pre>
          <pre className="dim" style={{ whiteSpace: 'pre-wrap', fontSize: 11, marginTop: 6 }}>{report.texts?.['الاختبار.md'] ?? ''}</pre>
        </div>
      ) : null}
      {report?.ok && s['kind'] !== 'year' && s['kind'] !== 'combo' && s['kind'] !== 'direction' && s['kind'] !== 'strategy' && s['kind'] !== 'levels' && s['kind'] !== 'detectors' && s['kind'] !== 'system' ? (
        <>
          <div className="cards" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))' }}>
            <div className="scard"><div className="st">الصافي بعد العمولة</div><div className={`sv num ${(net ?? 0) >= 0 ? 'green' : 'amber'}`}>{num(net)}</div><div className="ss">أقصى سحب {num(dd)}</div></div>
            <div className="scard"><div className="st">صفقات مغلقة</div><div className="sv num">{num(s['صفقات_مغلقة'] as number, 0)}</div><div className="ss">إغلاقات جزئيّة {num(s['إغلاقات_جزئيّة'] as number, 0)}</div></div>
            <div className="scard"><div className="st">نسبة الربح</div><div className="sv num">{s['نسبة_الربح'] == null ? '—' : `${num(s['نسبة_الربح'] as number, 1)}٪`}</div><div className="ss">معامل الربح {num(s['معامل_الربح'] as number, 2)}</div></div>
            <div className="scard"><div className="st">تِكّات</div><div className="sv num">{num(s['تِكّات'] as number, 0)}</div><div className="ss">{num(s['زمن_التشغيل_ث'] as number, 0)} ثانية تشغيل</div></div>
            <div className="scard"><div className="st">أوامر دخول</div><div className="sv num">{num(s['أوامر_دخول'] as number, 0)}</div><div className="ss">كلّ الأقسام جاهزة عند {num(s['أوامر_دخول_كلّ_الأقسام_جاهزة'] as number, 0)}</div></div>
          </div>

          <div className="scard">
            <div className="st">مشاركة الأقسام في تقييم القرار</div>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 14, marginTop: 6, fontSize: 13 }}>
              {['150', '200', '250', '300', '350', '400'].map((k) => {
                const total = share['تقييمات'] || 0
                const v = share[k] || 0
                return <span key={k}>{SECTION_AR[k]}: <span className="num">{total ? num(v / total * 100, 1) : '—'}٪</span></span>
              })}
              <span className="dim">من {num(share['تقييمات'], 0)} تقييم</span>
            </div>
          </div>

          {Object.keys(perSymbol).length ? (
            <div className="scard">
              <div className="st">لكلّ رمز</div>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 16, marginTop: 6, fontSize: 13 }}>
                {Object.entries(perSymbol).map(([sym, v]) => (
                  <span key={sym}>{SYMBOL_AR[sym] ?? sym}: صفقات <span className="num">{num(v['صفقات'], 0)}</span> · صافي <span className={`num ${v['صافي'] >= 0 ? 'green' : 'amber'}`}>{num(v['صافي'])}</span></span>
                ))}
              </div>
            </div>
          ) : null}

          <div className="scard">
            <div className="st">مسار القرار</div>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 14, marginTop: 6, fontSize: 12.5 }}>
              {Object.entries(events).map(([k, v]) => <span key={k}>{EVENT_AR[k] ?? k}: <span className="num">{num(v, 0)}</span></span>)}
            </div>
          </div>

          {trades.length ? (
            <div className="scard" style={{ overflow: 'hidden', padding: 0 }}>
              <div style={{ padding: '10px 14px', borderBottom: '1px solid var(--glassb)' }}><div className="st">الصفقات ({num(trades.length, 0)} حدث خروج)</div></div>
              <div style={{ overflowX: 'auto', maxHeight: 360 }}>
                <table className="tbl" style={{ width: '100%', fontSize: 12.5, borderCollapse: 'collapse' }}>
                  <thead><tr className="dim" style={{ textAlign: 'right' }}>
                    {['التذكرة', 'الرمز', 'الجهة', 'الحجم', 'دخول', 'خروج', 'النوع', 'السبب', 'الربح', 'العمولة', 'فُتحت', 'أُغلقت'].map((h) => <th key={h} style={{ padding: '6px 8px' }}>{h}</th>)}
                  </tr></thead>
                  <tbody>
                    {trades.map((t, i) => {
                      const pnl = Number(t.profit || 0)
                      return (
                        <tr key={i} style={{ borderTop: '1px solid var(--line)' }}>
                          <td className="num" style={{ padding: '5px 8px' }}>{t.ticket}</td>
                          <td style={{ padding: '5px 8px' }}>{SYMBOL_AR[t.symbol] ?? t.symbol}</td>
                          <td style={{ padding: '5px 8px' }}>{t.side === 'BUY' ? 'شراء' : 'بيع'}</td>
                          <td className="num" style={{ padding: '5px 8px' }}>{t.volume}</td>
                          <td className="num" style={{ padding: '5px 8px' }}>{num(Number(t.entry), 2)}</td>
                          <td className="num" style={{ padding: '5px 8px' }}>{num(Number(t.exit), 2)}</td>
                          <td style={{ padding: '5px 8px' }}>{t.kind === 'PARTIAL' ? 'جزئيّ' : 'كامل'}</td>
                          <td style={{ padding: '5px 8px' }}>{REASON_AR[t.reason] ?? t.reason}</td>
                          <td className={`num ${pnl >= 0 ? 'green' : 'amber'}`} style={{ padding: '5px 8px' }}>{num(pnl)}</td>
                          <td className="num" style={{ padding: '5px 8px' }}>{num(Number(t.commission || 0) + Number(t.entry_commission || 0))}</td>
                          <td className="num dim" style={{ padding: '5px 8px' }}>{t.opened_utc}</td>
                          <td className="num dim" style={{ padding: '5px 8px' }}>{t.closed_utc}</td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          ) : <div className="scard"><div className="st">لا صفقة في هذا التشغيل</div><div className="ss dim">مسار القرار أعلاه يقول أين توقّفت القرارات.</div></div>}

          {entries.length ? (
            <div className="scard">
              <div className="st">أوامر الدخول ومشاركة الأقسام لحظتها</div>
              <div style={{ display: 'grid', gap: 4, marginTop: 6, fontSize: 12 }}>
                {entries.slice(-30).map((e, i) => (
                  <div key={i}>
                    <span className="num dim">{when(e.time)}</span> · {SYMBOL_AR[e.symbol] ?? e.symbol} · {e.side === 'BUY' ? 'شراء' : e.side === 'SELL' ? 'بيع' : '—'} ·{' '}
                    {Object.entries(e.sections).map(([k, v]) => <span key={k} className={v === 'READY' ? 'green' : 'amber'} style={{ marginInlineEnd: 8 }}>{SECTION_AR[k] ?? k} {v === 'READY' ? '✓' : '✗'}</span>)}
                  </div>
                ))}
              </div>
            </div>
          ) : null}

          <button style={{ ...chip(showTech), alignSelf: 'flex-start' }} onClick={() => setShowTech((v) => !v)}>
            تفاصيل سلسلة القرار (بلغة الكود) {showTech ? '▲' : '▼'}
          </button>
          {showTech ? (
            <div className="scard">
              <pre style={{ margin: 0, fontSize: 11, direction: 'ltr', textAlign: 'left', whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>
                {Object.entries(health).map(([k, v]) => `${k} | ${v}`).join('\n')}
              </pre>
            </div>
          ) : null}
        </>
      ) : null}
    </div>
  )
}

// ٢٠٢٦-١٠-١٧ (ختم المالك «NQ»): تقرير «سنة القياس» بشكله — «كلّ شهر: كم صفقة، كم هدف أوّل وثاني وثالث، كم عائد، والأسابيع
// … كم خسر بالبداية، كم تراجع، كم أصاب، وكلّ صفقات الشهر كاملة».
interface YearStats {
  'صفقات': number; 'هدف_أوّل': number; 'هدف_ثانٍ': number; 'هدف_ثالث': number; 'وقف': number; 'إصابة': number
  'عائد': number; 'أعمق_نزول_تحت_البداية': number; 'أكبر_تراجع': number
}
interface YearMonth extends YearStats { 'الشهر': number; 'الأسابيع': number[] }
interface YearReading { 'القراءة': string; 'الاسم': string; 'السنة': YearStats; 'الأشهر': YearMonth[] }
interface YearSummary { kind: 'year'; 'السنة': string; 'القراءات': YearReading[] }
const EXIT_AR: Record<string, string> = {
  stop: 'وقف', stop_after_t1: 'وقف بعد الهدف الأوّل', stop_after_t2: 'وقف بعد الهدف الثاني', t3: 'الهدف الثالث',
  session_end: 'إغلاق الجلسة', news: 'خبر أحمر',
}
const cell = { padding: '5px 8px' }
const pct = (v?: number | null) => <span className={`num ${(v ?? 0) >= 0 ? 'green' : 'amber'}`}>{num(v)}٪</span>

function YearReport({ summary, trades }: { summary: YearSummary; trades: Record<string, string>[] }) {
  const readings = summary['القراءات'] ?? []
  const [pick, setPick] = useState(readings.find((r) => !r['القراءة'].includes('__'))?.['القراءة'] ?? readings[0]?.['القراءة'] ?? '')
  const [month, setMonth] = useState(1)
  const chosen = readings.find((r) => r['القراءة'] === pick)
  const list = trades.filter((t) => t.variant === pick && Number(t.day?.slice(5, 7)) === month)
  return (
    <>
      <div className="scard" style={{ overflowX: 'auto' }}>
        <div className="st">السنة كلّها — {summary['السنة']}</div>
        <table className="tbl" style={{ width: '100%', fontSize: 12.5, borderCollapse: 'collapse', marginTop: 6 }}>
          <thead><tr className="dim" style={{ textAlign: 'right' }}>
            {['الاتّجاه', 'صفقات', 'هدف أوّل', 'ثانٍ', 'ثالث', 'وقف', 'إصابة', 'عائد السنة', 'أعمق نزولٍ تحت البداية', 'أكبر تراجع'].map((h) => <th key={h} style={cell}>{h}</th>)}
          </tr></thead>
          <tbody>
            {readings.map((r) => {
              const y = r['السنة']
              return (
                <tr key={r['القراءة']} style={{ borderTop: '1px solid var(--line)' }} className={r['القراءة'].includes('__') ? 'dim' : ''}>
                  <td style={cell}>{r['الاسم']}</td>
                  <td className="num" style={cell}>{num(y['صفقات'], 0)}</td>
                  <td className="num" style={cell}>{num(y['هدف_أوّل'], 0)}</td>
                  <td className="num" style={cell}>{num(y['هدف_ثانٍ'], 0)}</td>
                  <td className="num" style={cell}>{num(y['هدف_ثالث'], 0)}</td>
                  <td className="num" style={cell}>{num(y['وقف'], 0)}</td>
                  <td className="num" style={cell}>{num(y['إصابة'], 1)}٪</td>
                  <td style={cell}>{pct(y['عائد'])}</td>
                  <td style={cell}>{pct(y['أعمق_نزول_تحت_البداية'])}</td>
                  <td className="num amber" style={cell}>{num(y['أكبر_تراجع'])}٪</td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>

      <div className="scard" style={{ overflowX: 'auto' }}>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, alignItems: 'center' }}>
          <span className="st">الأشهر</span>
          {readings.map((r) => <button key={r['القراءة']} style={chip(pick === r['القراءة'])} onClick={() => setPick(r['القراءة'])}>{r['الاسم']}</button>)}
        </div>
        <table className="tbl" style={{ width: '100%', fontSize: 12.5, borderCollapse: 'collapse', marginTop: 6 }}>
          <thead><tr className="dim" style={{ textAlign: 'right' }}>
            {['الشهر', 'صفقات', 'هدف أوّل', 'ثانٍ', 'ثالث', 'وقف', 'إصابة', 'عائد الشهر', 'الأسابيع: ربح أو خسارة'].map((h) => <th key={h} style={cell}>{h}</th>)}
          </tr></thead>
          <tbody>
            {(chosen?.['الأشهر'] ?? []).map((m) => (
              <tr key={m['الشهر']} style={{ borderTop: '1px solid var(--line)', cursor: 'pointer', background: month === m['الشهر'] ? 'var(--glass)' : undefined }} onClick={() => setMonth(m['الشهر'])}>
                <td className="num" style={cell}>{m['الشهر']}</td>
                <td className="num" style={cell}>{num(m['صفقات'], 0)}</td>
                <td className="num" style={cell}>{num(m['هدف_أوّل'], 0)}</td>
                <td className="num" style={cell}>{num(m['هدف_ثانٍ'], 0)}</td>
                <td className="num" style={cell}>{num(m['هدف_ثالث'], 0)}</td>
                <td className="num" style={cell}>{num(m['وقف'], 0)}</td>
                <td className="num" style={cell}>{num(m['إصابة'], 1)}٪</td>
                <td style={cell}>{pct(m['عائد'])}</td>
                <td style={cell}>{m['الأسابيع'].length ? m['الأسابيع'].map((w, i) => <span key={i}>{i ? ' · ' : ''}{pct(w)}</span>) : '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <div className="ss dim" style={{ marginTop: 4 }}>اضغط شهرًا لترى كلّ صفقاته تحت.</div>
      </div>

      <div className="scard" style={{ overflow: 'hidden', padding: 0 }}>
        <div style={{ padding: '10px 14px', borderBottom: '1px solid var(--glassb)' }}>
          <div className="st">صفقات الشهر {month} — {chosen?.['الاسم'] ?? ''} ({num(list.length, 0)})</div>
        </div>
        <div style={{ overflowX: 'auto', maxHeight: 420 }}>
          <table className="tbl" style={{ width: '100%', fontSize: 12.5, borderCollapse: 'collapse' }}>
            <thead><tr className="dim" style={{ textAlign: 'right' }}>
              {['اليوم', 'ساعة نيويورك', 'الجهة', 'الدخول', 'الوقف', 'المخاطرة (بِب)', 'بلغ', 'الخروج', 'النتيجة'].map((h) => <th key={h} style={cell}>{h}</th>)}
            </tr></thead>
            <tbody>
              {list.map((t, i) => (
                <tr key={i} style={{ borderTop: '1px solid var(--line)' }}>
                  <td className="num" style={cell}>{t.day}</td>
                  <td className="num" style={cell}>{t.time_ny}</td>
                  <td style={cell}>{t.side === 'buy' ? 'شراء' : 'بيع'}</td>
                  <td className="num" style={cell}>{num(Number(t.entry), 2)}</td>
                  <td className="num" style={cell}>{num(Number(t.stop), 2)}</td>
                  <td className="num" style={cell}>{num(Number(t.risk_pips), 1)}</td>
                  <td className="num" style={cell}>{Number(t.reached) ? `الهدف ${t.reached}` : '—'}</td>
                  <td style={cell}>{EXIT_AR[t.exit] ?? t.exit}</td>
                  <td style={cell}>{pct(Number(t.pct))}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </>
  )
}