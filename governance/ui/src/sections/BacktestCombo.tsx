// منشئ التوليفة — أداة الباك تست الاحترافيّة (ورقة الخطوات ١٧/١٠، الخطوة 6؛ ختم المالك «NQ»).
// قوله: «أيّ توليفة بدّي ياها بقدر أختبرها أنا بيدي … أغيّر أهداف واقتصاص وستوب … مع أخبار … سريعة، وتقرير كامل واضح بالعربي».
// الحقائق من مخزن الحقائق (ذرّات الأقسام الحقيقيّة شُغّلت على شموع الفترة مرّةً)، والمحرّك `backtest/combo_engine.py`.
import { useEffect, useMemo, useState } from 'react'

interface Field { key: string; label: string; kind: 'num' | 'word'; vocab: string[]; frames: string[] }
interface AtomInfo { id: string; name: string; frames: string[]; fields: Field[] }
interface Store { symbol: string; folder: string; from: string; to: string; minutes?: number; atoms: AtomInfo[]; path?: string; kind?: string; ticks?: string }
interface Trig { atom: string; frame: string; key: string; value: string; side_key: string; buy: string; sell: string }
interface ComboCatalog { ok: boolean; error?: string; stores: Store[]; defaults: Spec; frames: string[]; symbols: string[]; building: { name: string; symbol: string; progress: string }[] }
interface Cond { atom: string; frame: string; key: string; op: string; value: unknown; max_age_min?: number; role?: string }
interface Spec {
  symbol: string; from: string; to: string; decision_frame: string
  direction: { source: 'random' | 'fact' | 'signal' | 'role'; atom?: string; frame?: string; key?: string; role?: string }
  conditions: Cond[]
  stop: { method: 'structure' | 'fixed' | 'atr'; band: [number, number]; pips: number; atr_frame: string; atr_mult: number; pad: number }
  targets: { r: number; close_pct: number }[]
  breakeven_after: number; trail_after: number; trail_to_r: number; risk_pct: number; cost_pips: number
  scale_with_price: boolean; wait_min: number; max_per_day: number; day_counted?: number
  session: { use_red_lines: boolean; first_minutes: number }
  news: { on: boolean; colors: string[]; before_min: number; after_min: number; close_open: boolean; currencies: string[] }
  time_enough: boolean; reference_random: boolean; name: string
  store?: string
  entry?: { within_min?: number; triggers?: Trig[]; levels?: LevelCfg; majority?: boolean }
}
interface LevelCfg { source?: 'session'; scenario?: string; candle: string; kinds?: string[]; entry_on?: string; tolerance_pips?: number; touches?: number }

const SYMBOL_AR: Record<string, string> = {
  XAUUSD: 'الذهب', BTCUSD: 'البتكوين', USTEC: 'الناسداك', US30: 'داو جونز', US500: 'إس آند بي', EURUSD: 'يورو/دولار', GBPUSD: 'جنيه/دولار',
}
const WORD_AR: Record<string, string> = {
  rising: 'صاعد', falling: 'هابط', none: 'لا شيء', up: 'صاعد', down: 'هابط', sideways: 'عرضيّ', bullish: 'صاعد', bearish: 'هابط',
  buy: 'شراء', sell: 'بيع', ok: 'سليم', insufficient_data: 'بيانات ناقصة', normal: 'عاديّ', high: 'مرتفع', low: 'منخفض',
  uptrend: 'اتّجاه صاعد', downtrend: 'اتّجاه هابط', range: 'مدى', transition: 'انتقال', early: 'مبكّر', established: 'راسخ',
  extended: 'ممتدّ', neutral: 'محايد', higher_highs_higher_lows: 'قمم وقيعان أعلى', lower_highs_lower_lows: 'قمم وقيعان أدنى',
  mixed: 'مختلط', with_primary: 'مع الأساسيّ', against_primary: 'ضدّ الأساسيّ', undetermined: 'غير محدّد', above_fast: 'فوق السريع',
  below_fast: 'تحت السريع', at_fast: 'عند السريع', emerging: 'ناشئ', weakening: 'يضعف', strong: 'قويّ', weak: 'ضعيف',
  moderate: 'متوسّط', true: 'نعم', false: 'لا', close_below_last_swing_low: 'إغلاق تحت آخر قاع',
  close_above_last_swing_high: 'إغلاق فوق آخر قمّة', higher: 'أعلى', lower: 'أدنى', equal: 'مساوٍ', good: 'جيّدة', stale: 'قديمة',
  above: 'فوق', below: 'تحت', gap_up: 'فجوة صاعدة', gap_down: 'فجوة هابطة', fvg_bullish: 'فجوة قيمة صاعدة', fvg_bearish: 'فجوة قيمة هابطة',
  buy_side: 'سيولة الشراء (القمم)', sell_side: 'سيولة البيع (القيعان)', sweep: 'كنس', bos: 'كسر هيكل', choch: 'تغيّر طبع', shift: 'تحوّل',
  trending: 'متّجه', mean_reverting: 'يرجع إلى المتوسّط', random_walk: 'عشوائيّ', flat: 'مسطّح', stable: 'مستقرّ', accelerating: 'يتسارع',
  decelerating: 'يتباطأ', steady: 'ثابت', fast: 'سريع', slow: 'بطيء', engulfing: 'ابتلاع', inside: 'داخليّة', outside: 'خارجيّة', doji: 'دوجي',
  marubozu: 'ماروبوزو', filled: 'امتلأت', contracting: 'ينقبض', expanding: 'يتّسع',
}
const wordAr = (w: string) => WORD_AR[w] ?? w
const FRAME_AR: Record<string, string> = { '1m': 'الدقيقة', '5m': 'الخمس دقائق', '15m': 'الربع ساعة', '30m': 'النصف ساعة', '1h': 'الساعة', '4h': 'الأربع ساعات', '1d': 'اليوم' }
const frameAr = (f: string) => FRAME_AR[f] ?? f
const SECTION_ORDER = ['التحليل', 'البنية', 'السيولة', 'المؤشّرات', 'النماذج', 'المعرفة', 'الاستراتيجيّات والبطاقات', 'السياق والمستويات والأخبار']
function sectionOf(id: string) {
  const n = Number(id)
  if (!Number.isFinite(n)) return 'السياق والمستويات والأخبار'
  return n < 150 ? 'المعرفة' : n < 200 ? 'التحليل' : n < 250 ? 'البنية' : n < 300 ? 'السيولة' : n < 350 ? 'المؤشّرات' : n < 400 ? 'النماذج' : 'الاستراتيجيّات والبطاقات'
}
const OPS_NUM: [string, string][] = [['same_way', 'إشارته في جهة الصفقة'], ['>', 'أكبر من'], ['>=', 'أكبر أو يساوي'], ['<', 'أصغر من'], ['<=', 'أصغر أو يساوي'], ['==', 'يساوي'], ['!=', 'لا يساوي'], ['between', 'بين']]
const OPS_WORD: [string, string][] = [['==', 'يساوي'], ['!=', 'لا يساوي'], ['in', 'واحدة من'], ['same_way', 'في جهة الصفقة نفسها']]
// ٩/١١ (المالك «أغلبيّة»، وختمه): الشرط بدورٍ يصوّت في دوره، والدور يمرّ بأكثر من نصف ذرّاته التي لها قراءة، والأدوار كلّها معًا
const ROLES = ['الوقت', 'الجهة', 'حالة السوق', 'المكان', 'لحظة الدخول', 'الوقف والهدف']
const COLORS_AR: [string, string][] = [['red', 'أحمر'], ['orange', 'برتقاليّ'], ['yellow', 'أصفر']]
const chip = (on: boolean) => ({
  fontSize: 12, padding: '3px 10px', borderRadius: 8, cursor: 'pointer', fontFamily: 'inherit', whiteSpace: 'nowrap' as const,
  background: on ? 'var(--accent)' : 'transparent', color: on ? '#06121c' : 'var(--dim)', border: `1px solid ${on ? 'var(--accent)' : 'var(--glassb)'}`,
})
const field = { margin: 0, padding: '4px 7px' }
const lbl = { fontSize: 12, display: 'flex', alignItems: 'center', gap: 6 } as const
const box = { display: 'flex', flexWrap: 'wrap' as const, gap: 10, alignItems: 'center' }

function NumIn({ v, set, w = 64, step = 1 }: { v: number; set: (x: number) => void; w?: number; step?: number }) {
  return <input className="cfginput num" type="number" step={step} style={{ ...field, width: w }} value={Number.isFinite(v) ? v : ''} onChange={(e) => set(Number(e.target.value))} />
}

function FactPicker({ store, atom, frame, keyName, onChange, kinds }: {
  store?: Store; atom?: string; frame?: string; keyName?: string; kinds?: ('num' | 'word')[]
  onChange: (x: { atom: string; frame: string; key: string; field?: Field }) => void
}) {
  const a = store?.atoms.find((x) => x.id === atom)
  const fields = (a?.fields ?? []).filter((f) => (!frame || f.frames.includes(frame)) && (!kinds || kinds.includes(f.kind)))
  return (
    <>
      <select className="cfginput" style={field} value={atom ?? ''} onChange={(e) => {
        const na = store?.atoms.find((x) => x.id === e.target.value)
        onChange({ atom: e.target.value, frame: na?.frames.includes(frame ?? '') ? frame ?? '' : na?.frames[0] ?? '', key: '' })
      }}>
        <option value="">— الذرّة —</option>
        {SECTION_ORDER.map((sec) => {
          const atoms = (store?.atoms ?? []).filter((x) => sectionOf(x.id) === sec)
          return atoms.length ? <optgroup key={sec} label={sec}>{atoms.map((x) => <option key={x.id} value={x.id}>{x.id} {x.name}</option>)}</optgroup> : null
        })}
      </select>
      <select className="cfginput" style={field} value={frame ?? ''} onChange={(e) => onChange({ atom: atom ?? '', frame: e.target.value, key: keyName ?? '' })}>
        {(a?.frames ?? []).map((f) => <option key={f} value={f}>{frameAr(f)}</option>)}
      </select>
      <select className="cfginput" style={{ ...field, maxWidth: 280 }} value={keyName ?? ''} onChange={(e) => onChange({ atom: atom ?? '', frame: frame ?? '', key: e.target.value, field: fields.find((f) => f.key === e.target.value) })}>
        <option value="">— الحقيقة —</option>
        {fields.map((f) => <option key={f.key} value={f.key}>{f.label}</option>)}
      </select>
    </>
  )
}

const num = (n?: unknown, d = 2) => (typeof n === 'number' && Number.isFinite(n) ? n.toLocaleString('ar-EG-u-nu-latn', { maximumFractionDigits: d }) : n == null ? '—' : String(n))
const cell = { padding: '5px 8px' }

// ١/١١ (المالك «nq»: «ليش تبني زر … صفحة باك تست لازم تكون كاملة كل ما بدي اختبر شي يكون موجود»): منشئٌ واحد لكلّ قياس. الأزواج × السنوات ×
// التجارب، والإعدادات المحفوظة مكان الأزرار، وما ينقص خانةٌ تُضاف هنا مرّةً واحدة.
interface Experiment { label: string; spec: Partial<Spec> }
interface Setting { name: string; symbols: string[]; years: string[][]; experiments: Experiment[] }
interface StoreRow { symbol: string; year: string; atoms: number; want: number; ready: boolean; cut?: boolean; failed?: Record<string, string>; progress?: string }
interface StoresState { ok: boolean; stores: StoreRow[]; want: number; queue: { alive?: boolean; running?: string[]; done?: string[]; failed?: string[]; total?: number; memory_gb?: number } }
interface DayLook { ok: boolean; error?: string; levels: { known: string; kind: string; price: number }[]; signals: { at: string; side: string; price: number; level: number | string }[] }
const YEARS = ['2022', '2023', '2024']
const yearSpan = (y: string) => [`${y}-01-01`, `${Number(y) + 1}-01-01`]
const SCENARIOS: [string, string][] = [['retest', 'كسر ثمّ رجوع'], ['break', 'كسر وثبات'], ['false', 'كسر كاذب']]
const ENTRY_ON: [string, string][] = [['pullback', 'بإغلاق أوّل شمعة رجوع'], ['confirm', 'بإغلاق الشمعة التالية في جهة الكسر']]
const CANDLES: [string, string][] = [['M1', 'الدقيقة'], ['M5', 'الخمس دقائق']]
const MAP_KINDS: [string, string][] = [['y_high', 'أعلى الأمس'], ['y_low', 'أدنى الأمس'], ['y_close', 'إغلاق الأمس'], ['n_high', 'أعلى الليل'], ['n_low', 'أدنى الليل'], ['w_high', 'أعلى الأسبوع الماضي'], ['w_low', 'أدنى الأسبوع الماضي'], ['round', 'رقم مستدير'], ['round_strong', 'رقم مستدير قويّ']]

function StoresTable({ state, symbols, onComplete, busy }: { state: StoresState | null; symbols: Record<string, string>; onComplete: () => void; busy: boolean }) {
  if (!state?.ok) return <div className="dim" style={{ fontSize: 12 }}>حال المخازن غير معروف</div>
  const syms = [...new Set(state.stores.map((r) => r.symbol))]
  const years = [...new Set(state.stores.map((r) => r.year))]
  const q = state.queue
  const missing = state.stores.filter((r) => !r.ready).length
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
      <table className="tbl" style={{ fontSize: 12.5, borderCollapse: 'collapse' }}>
        <thead><tr className="dim"><th style={{ padding: '3px 10px' }}>الزوج</th>{years.map((y) => <th key={y} style={{ padding: '3px 10px' }}>{y}</th>)}</tr></thead>
        <tbody>{syms.map((s) => (
          <tr key={s} style={{ borderTop: '1px solid var(--line)' }}>
            <td style={{ padding: '3px 10px' }}>{symbols[s] ?? s}</td>
            {years.map((y) => {
              const r = state.stores.find((x) => x.symbol === s && x.year === y)
              const building = q.running?.includes(`${s} ${y}`)
              return <td key={y} className={r?.ready ? 'num green' : 'num amber'} style={{ padding: '3px 10px' }}>{r?.ready ? `جاهز ${r.atoms} ذرّة` : building ? 'يُبنى' : r?.cut ? `مقطوع ${r.atoms} ذرّة` : r?.atoms ? `ناقص ${r.atoms} من ${r.want}` : 'لا مخزن'}</td>
            })}
          </tr>
        ))}</tbody>
      </table>
      <div style={box}>
        <button className="btn" disabled={busy || q.alive || missing === 0} onClick={onComplete}>{missing === 0 ? 'كلّ المخازن جاهزة' : `أكمل الناقص (${missing})`}</button>
        {q.alive ? <span className="dim num" style={{ fontSize: 12 }}>الطابور يعمل · انتهى {q.done?.length ?? 0} من {q.total ?? 0}{q.running?.length ? '' : ' · ينتظر ذاكرة حرّة'} · الذاكرة المتاحة {q.memory_gb ?? '—'} غيغا{q.failed?.length ? ` · لم يكتمل: ${q.failed.join('، ')}` : ''}</span> : null}
      </div>
    </div>
  )
}

export function ComboBuilder({ onStarted }: { onStarted: () => void }) {
  const [cat, setCat] = useState<ComboCatalog | null>(null)
  const [spec, setSpec] = useState<Spec | null>(null)
  const [note, setNote] = useState<{ ok: boolean; text: string } | null>(null)
  const [busy, setBusy] = useState(false)
  const [buildAtoms, setBuildAtoms] = useState('')
  const [buildTicks, setBuildTicks] = useState(false)
  const [symbols, setSymbols] = useState<string[]>(['USTEC'])
  const [yearsOn, setYearsOn] = useState<string[]>(['2022', '2023'])
  const [custom, setCustom] = useState(false)
  const [experiments, setExperiments] = useState<Experiment[]>([])
  const [expLabel, setExpLabel] = useState('')
  const [pairRules, setPairRules] = useState(true)
  const [settings, setSettings] = useState<{ seeds: Setting[]; saved: Setting[] }>({ seeds: [], saved: [] })
  const [saveName, setSaveName] = useState('')
  const [stores, setStores] = useState<StoresState | null>(null)
  const [day, setDay] = useState('2026-10-26')
  const [look, setLook] = useState<DayLook | null>(null)
  const load = () => {
    fetch('/gov/backtest/full/combo/catalog', { cache: 'no-store' })
      .then((r) => r.json() as Promise<ComboCatalog>)
      .then((c) => { setCat(c); setSpec((cur) => cur ?? JSON.parse(JSON.stringify(c.defaults)) as Spec) })
      .catch(() => setCat({ ok: false, error: 'خادم اللوحة لا يجيب', stores: [], defaults: {} as Spec, frames: [], symbols: [], building: [] }))
    fetch('/gov/backtest/full/stores', { cache: 'no-store' }).then((r) => r.json() as Promise<StoresState>).then(setStores).catch(() => setStores(null))
  }
  const loadSettings = () => fetch('/gov/backtest/full/settings', { cache: 'no-store' }).then((r) => r.json() as Promise<{ seeds: Setting[]; saved: Setting[] }>).then((s) => setSettings({ seeds: s.seeds ?? [], saved: s.saved ?? [] })).catch(() => undefined)
  useEffect(() => { void load(); void loadSettings(); const t = window.setInterval(() => void load(), 15000); return () => window.clearInterval(t) }, [])
  // الذرّات في القوائم من أغنى مخزنٍ للزوج الأوّل: كلّ ما بُني يظهر، والخطّة تختار لكلّ زوجٍ وسنة مخزنًا فيه ما طُلب.
  const store = useMemo(() => {
    const own = (cat?.stores ?? []).filter((s) => s.symbol === symbols[0])
    const pool = own.length ? own : cat?.stores ?? []
    return [...pool].sort((a, b) => b.atoms.length - a.atoms.length)[0]
  }, [cat, symbols])
  if (!cat || !spec) return <div className="scard dim">يُحمَّل الفهرس…</div>
  const up = (patch: Partial<Spec>) => setSpec({ ...spec, ...patch })
  const post = async (path: string, body: unknown, ok: string): Promise<Record<string, unknown> | null> => {
    setBusy(true); setNote(null)
    try {
      const r = await fetch(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
      const j = await r.json() as { ok: boolean; error?: string }
      setNote(j.ok ? { ok: true, text: ok } : { ok: false, text: j.error ?? 'تعذّر' })
      onStarted(); void load()
      setBusy(false)
      return j as Record<string, unknown>
    } catch { setNote({ ok: false, text: 'خطأ اتّصال بخادم اللوحة' }) }
    setBusy(false)
    return null
  }
  const setCond = (i: number, c: Partial<Cond>) => up({ conditions: spec.conditions.map((x, j) => (j === i ? { ...x, ...c } : x)) })
  const fieldOf = (c: { atom?: string; key?: string }) => store?.atoms.find((a) => a.id === c.atom)?.fields.find((f) => f.key === c.key)
  const periods = custom ? [[spec.from, spec.to]] : YEARS.filter((y) => yearsOn.includes(y)).map(yearSpan)
  const current = (): Partial<Spec> => { const { store: _s, name: _n, symbol: _y, from: _f, to: _t, ...rest } = spec; return JSON.parse(JSON.stringify(rest)) as Partial<Spec> }
  const open = (s: Setting) => {
    setSymbols(s.symbols); setExperiments(s.experiments); setCustom(false)
    setYearsOn(s.years.map((y) => y[0].slice(0, 4)))
    const first = s.experiments[0]?.spec ?? {}
    const merged = JSON.parse(JSON.stringify(cat.defaults)) as Spec
    setSpec({ ...merged, ...first, stop: { ...merged.stop, ...(first.stop ?? {}) }, name: '' } as Spec)
    setExpLabel(''); setNote({ ok: true, text: `فُتح: ${s.name}` })
  }
  const lv = spec.entry?.levels
  const entrySource = lv?.source === 'session' ? 'session' : lv ? 'map' : spec.entry?.triggers?.length ? 'atom' : 'none'
  const setLevels = (patch: Partial<LevelCfg>) => up({ entry: { within_min: spec.entry?.within_min ?? 15, levels: { ...(lv ?? { candle: 'M1' }), ...patch } } })
  const triggers = spec.entry?.triggers ?? []
  const start = async () => {
    const list = experiments.length ? experiments : [{ label: expLabel || spec.name || 'التجربة', spec: current() }]
    const j = await post('/gov/backtest/full/plan/start', { name: spec.name, symbols, years: periods, experiments: list, pair_rules: pairRules }, 'بدأ على الجهاز — التقدّم والنتيجة في قائمة التشغيلات تحت')
    const missing = (j?.missing as string[] | undefined) ?? []
    if (j?.ok && missing.length) setNote({ ok: false, text: `بدأ، ولا مخزن فيه ما طُلب لهذه فلن تُقاس: ${missing.join('، ')}` })
  }

  return (
    <div className="scard" style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      <div style={box}>
        <span className="st" style={{ fontSize: 12 }}>إعداد محفوظ</span>
        <select className="cfginput" style={{ ...field, maxWidth: 380 }} value="" onChange={(e) => { const all = [...settings.seeds, ...settings.saved]; const s = all.find((x) => x.name === e.target.value); if (s) open(s) }}>
          <option value="">— افتح إعدادًا —</option>
          {settings.seeds.map((s) => <option key={s.name} value={s.name}>{s.name}</option>)}
          {settings.saved.map((s) => <option key={s.name} value={s.name}>{s.name} (حفظتَه)</option>)}
        </select>
        <input className="cfginput" style={{ ...field, width: 180 }} placeholder="اسم للحفظ" value={saveName} onChange={(e) => setSaveName(e.target.value)} />
        <button className="btn" disabled={busy || !saveName.trim()} onClick={() => void post('/gov/backtest/full/settings', { name: saveName.trim(), symbols, years: periods, experiments: experiments.length ? experiments : [{ label: saveName.trim(), spec: current() }] }, 'حُفظ').then(() => { setSaveName(''); void loadSettings() })}>احفظ</button>
      </div>

      <div style={box}>
        <span className="st" style={{ fontSize: 12 }}>الأزواج</span>
        {cat.symbols.map((s) => <button key={s} style={chip(symbols.includes(s))} onClick={() => setSymbols(symbols.includes(s) ? symbols.filter((x) => x !== s) : [...symbols, s])}>{SYMBOL_AR[s] ?? s}</button>)}
        <span className="st" style={{ fontSize: 12, marginInlineStart: 12 }}>السنوات</span>
        {YEARS.map((y) => <button key={y} className="num" style={chip(!custom && yearsOn.includes(y))} onClick={() => { setCustom(false); setYearsOn(yearsOn.includes(y) ? yearsOn.filter((x) => x !== y) : [...yearsOn, y]) }}>{y}</button>)}
        <button style={chip(custom)} onClick={() => setCustom(!custom)}>فترة بيدي</button>
        {custom ? <>
          <label className="dim" style={lbl}>من <input className="cfginput" type="date" style={field} value={spec.from} onChange={(e) => up({ from: e.target.value })} /></label>
          <label className="dim" style={lbl}>إلى <input className="cfginput" type="date" style={field} value={spec.to} onChange={(e) => up({ to: e.target.value })} /></label>
        </> : null}
      </div>

      <div style={box}>
        <span className="st" style={{ fontSize: 12 }}>لحظة القرار</span>
        <select className="cfginput" style={field} value={spec.decision_frame} onChange={(e) => up({ decision_frame: e.target.value, direction: e.target.value !== 'signal' && spec.direction.source === 'signal' ? { source: 'random' } : spec.direction })}>
          <option value="signal">لحظة الإشارة نفسها</option>
          {cat.frames.map((f) => <option key={f} value={f}>كلّ إغلاق {frameAr(f)}</option>)}
        </select>
        <span className="st" style={{ fontSize: 12, marginInlineStart: 12 }}>الجهة</span>
        <button style={chip(spec.direction.source === 'random')} onClick={() => up({ direction: { source: 'random' } })}>عشوائيّة</button>
        <button style={chip(spec.direction.source === 'fact')} onClick={() => up({ direction: { source: 'fact', atom: '209', frame: '15m', key: 'readings.four_hours.trend' } })}>من ذرّة</button>
        <button style={chip(spec.direction.source === 'signal')} onClick={() => up({ direction: { source: 'signal' }, decision_frame: 'signal' })}>الجهتان: الإشارة تعطي الجهة</button>
        <button style={chip(spec.direction.source === 'role')} onClick={() => up({ direction: { source: 'role', role: 'الجهة' } })}>بأغلبيّة دور الجهة</button>
        {spec.direction.source === 'role' ? <span className="dim" style={{ fontSize: 12 }}>شروط دور «الجهة» كلّها «في جهة الصفقة»، والجهة ما قاله أكثر من نصفها</span> : null}
        {spec.direction.source === 'fact' ? (
          <FactPicker store={store} atom={spec.direction.atom} frame={spec.direction.frame} keyName={spec.direction.key}
            onChange={(x) => up({ direction: { source: 'fact', atom: x.atom, frame: x.frame, key: x.key } })} />
        ) : null}
        {spec.direction.source === 'fact' && spec.decision_frame === 'signal' ? <span className="dim" style={{ fontSize: 12 }}>إشارةٌ عكس هذه الجهة لا تُؤخذ</span> : null}
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
        <div style={box}>
          <span className="st" style={{ fontSize: 12 }}>الشروط</span>
          <span className="dim" style={{ fontSize: 12 }}>بلا دور: كلّها معًا · بدور: أغلبيّة ذرّات الدور التي لها قراءة، والأدوار كلّها معًا</span>
          <button className="btn" onClick={() => up({ conditions: [...spec.conditions, { atom: '', frame: '15m', key: '', op: '>', value: 0 }] })}>أضف شرطًا</button>
        </div>
        {spec.conditions.map((c, i) => {
          const f = fieldOf(c)
          const ops = f?.kind === 'word' ? OPS_WORD : OPS_NUM
          return (
            <div key={i} style={box}>
              <FactPicker store={store} atom={c.atom} frame={c.frame} keyName={c.key}
                onChange={(x) => setCond(i, { atom: x.atom, frame: x.frame, key: x.key, op: x.field?.kind === 'word' ? '==' : c.op === 'same_way' ? '>' : c.op, value: x.field?.kind === 'word' ? x.field.vocab[0] ?? '' : c.value })} />
              <select className="cfginput" style={field} value={c.op} onChange={(e) => setCond(i, { op: e.target.value, value: e.target.value === 'between' ? [0, 1] : e.target.value === 'in' ? [] : c.op === 'in' ? f?.vocab[0] ?? '' : c.value })}>
                {ops.map(([v, t]) => <option key={v} value={v}>{t}</option>)}
              </select>
              {c.op === 'same_way' ? null : c.op === 'in' ? (
                (f?.vocab ?? []).map((w) => { const on = ((c.value as string[]) ?? []).includes(w); return <button key={w} style={chip(on)} onClick={() => setCond(i, { value: on ? (c.value as string[]).filter((x) => x !== w) : [...((c.value as string[]) ?? []), w] })}>{wordAr(w)}</button> })
              ) : f?.kind === 'word' ? (
                <select className="cfginput" style={field} value={String(c.value ?? '')} onChange={(e) => setCond(i, { value: e.target.value })}>
                  {f.vocab.map((w) => <option key={w} value={w}>{wordAr(w)}</option>)}
                </select>
              ) : c.op === 'between' ? (
                <>
                  <NumIn v={Number((c.value as number[])?.[0])} set={(x) => setCond(i, { value: [x, (c.value as number[])?.[1] ?? 0] })} step={0.01} />
                  <span className="dim">و</span>
                  <NumIn v={Number((c.value as number[])?.[1])} set={(x) => setCond(i, { value: [(c.value as number[])?.[0] ?? 0, x] })} step={0.01} />
                </>
              ) : <NumIn v={Number(c.value)} set={(x) => setCond(i, { value: x })} step={0.01} w={80} />}
              <label className="dim" style={lbl}>عمرها حتّى (دقيقة، ٠ = بلا حدّ) <NumIn v={c.max_age_min ?? 0} set={(x) => setCond(i, { max_age_min: x })} w={56} /></label>
              <label className="dim" style={lbl}>الدور <select className="cfginput" style={field} value={c.role ?? ''} onChange={(e) => setCond(i, { role: e.target.value || undefined })}>
                <option value="">بلا دور</option>
                {ROLES.map((r) => <option key={r} value={r}>{r}</option>)}
              </select></label>
              <button className="btn" style={{ padding: '1px 8px' }} onClick={() => up({ conditions: spec.conditions.filter((_, j) => j !== i) })}>احذف الشرط</button>
            </div>
          )
        })}
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
        <div style={box}>
          <span className="st" style={{ fontSize: 12 }}>إشارة الدخول</span>
          <button style={chip(entrySource === 'none')} onClick={() => up({ entry: undefined })}>بلا إشارة</button>
          <button style={chip(entrySource === 'session')} onClick={() => up({ entry: { within_min: 15, levels: { source: 'session', candle: 'M1', tolerance_pips: 6, touches: 3, entry_on: 'pullback' } } })}>مستوى الجلسة</button>
          <button style={chip(entrySource === 'map')} onClick={() => up({ entry: { within_min: 15, levels: { scenario: 'retest', candle: 'M1', entry_on: 'pullback' } } })}>مستويات المتداول</button>
          <button style={chip(entrySource === 'atom')} onClick={() => up({ entry: { within_min: spec.entry?.within_min ?? 15, triggers: [...triggers, { atom: '', frame: '1m', key: 'signal', value: '', side_key: '', buy: '', sell: '' }] } })}>إشارة ذرّة</button>
          {entrySource !== 'none' && spec.decision_frame !== 'signal' ? <label className="dim" style={lbl}>ينتظرها حتّى (دقيقة) <NumIn v={spec.entry?.within_min ?? 15} set={(x) => up({ entry: { ...spec.entry!, within_min: x } })} w={56} /></label> : null}
          {entrySource === 'none' ? <span className="dim" style={{ fontSize: 12 }}>الدخول بإغلاق لحظة القرار</span> : null}
          {entrySource === 'atom' ? <button style={chip(!!spec.entry?.majority)} onClick={() => up({ entry: { ...spec.entry!, majority: !spec.entry?.majority } })}>دور «لحظة الدخول»: أغلبيّة ذرّات الدقيقة</button> : null}
        </div>
        {entrySource === 'session' ? (
          <div style={box}>
            <label className="dim" style={lbl}>لمسات <NumIn v={lv?.touches ?? 3} set={(x) => setLevels({ touches: x })} w={44} /></label>
            <label className="dim" style={lbl}>ضمن (نقطة) <NumIn v={lv?.tolerance_pips ?? 6} set={(x) => setLevels({ tolerance_pips: x })} step={0.1} w={56} /></label>
          </div>
        ) : null}
        {entrySource === 'map' ? (
          <div style={box}>
            {SCENARIOS.map(([k, t]) => <button key={k} style={chip((lv?.scenario ?? 'break') === k)} onClick={() => setLevels({ scenario: k })}>{t}</button>)}
            {MAP_KINDS.map(([k, t]) => { const on = !lv?.kinds || lv.kinds.includes(k); return <button key={k} style={chip(on)} onClick={() => { const all = lv?.kinds ?? MAP_KINDS.map((x) => x[0]); setLevels({ kinds: on ? all.filter((x) => x !== k) : [...all, k] }) }}>{t}</button> })}
          </div>
        ) : null}
        {entrySource === 'session' || entrySource === 'map' ? (
          <div style={box}>
            <span className="dim" style={{ fontSize: 12 }}>الشمعة</span>
            {CANDLES.map(([k, t]) => <button key={k} style={chip((lv?.candle ?? 'M1') === k)} onClick={() => setLevels({ candle: k })}>{t}</button>)}
            {entrySource === 'session' || lv?.scenario === 'retest' ? <>
              <span className="dim" style={{ fontSize: 12, marginInlineStart: 12 }}>الدخول</span>
              {ENTRY_ON.map(([k, t]) => <button key={k} style={chip((lv?.entry_on ?? 'pullback') === k)} onClick={() => setLevels({ entry_on: k })}>{t}</button>)}
            </> : null}
            <span className="dim" style={{ fontSize: 12, marginInlineStart: 12 }}>إشارات يوم</span>
            <input className="cfginput" type="date" style={field} value={day} onChange={(e) => setDay(e.target.value)} />
            <button className="btn" disabled={busy} onClick={() => { setLook(null); void fetch('/gov/backtest/full/plan/day', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ symbol: symbols[0], day, entry: spec.entry }) }).then((r) => r.json() as Promise<DayLook>).then(setLook).catch(() => setNote({ ok: false, text: 'خطأ اتّصال بخادم اللوحة' })) }}>اعرض</button>
          </div>
        ) : null}
        {look && !look.ok ? <span className="amber" style={{ fontSize: 12 }}>{look.error}</span> : null}
        {look?.ok ? (
          <div style={{ display: 'flex', gap: 24, flexWrap: 'wrap', fontSize: 12.5 }}>
            <div><div className="st">الإشارات ({look.signals.length}) <span className="dim" style={{ fontSize: 11 }}>— ساعة تركيا، وقبل الخطوط الحمراء والجهة</span></div>
              <table className="tbl" style={{ borderCollapse: 'collapse' }}><thead><tr className="dim">{['الشمعة', 'الجهة', 'الدخول', 'المستوى'].map((h) => <th key={h} style={cell}>{h}</th>)}</tr></thead>
                <tbody>{look.signals.map((s, i) => <tr key={i} style={{ borderTop: '1px solid var(--line)' }}><td className="num" style={cell}>{s.at}</td><td style={cell}>{s.side}</td><td className="num" style={cell}>{s.price}</td><td className="num" style={cell}>{s.level}</td></tr>)}</tbody></table>
            </div>
            {look.levels.length ? <div><div className="st">مستويات الجلسة ({look.levels.length})</div>
              <table className="tbl" style={{ borderCollapse: 'collapse' }}><thead><tr className="dim">{['عُرف', 'النوع', 'السعر'].map((h) => <th key={h} style={cell}>{h}</th>)}</tr></thead>
                <tbody>{look.levels.map((x, i) => <tr key={i} style={{ borderTop: '1px solid var(--line)' }}><td className="num" style={cell}>{x.known}</td><td style={cell}>{x.kind}</td><td className="num" style={cell}>{x.price}</td></tr>)}</tbody></table>
            </div> : null}
          </div>
        ) : null}
        {triggers.map((g, i) => {
          const setTrig = (patch: Partial<Trig>) => up({ entry: { ...spec.entry!, triggers: triggers.map((x, j) => (j === i ? { ...x, ...patch } : x)) } })
          const ev = fieldOf({ atom: g.atom, key: g.key })
          const words = (store?.atoms.find((a) => a.id === g.atom)?.fields ?? []).filter((f) => f.kind === 'word' && f.frames.includes(g.frame))
          const side = words.find((f) => f.key === g.side_key)
          return (
            <div key={i} style={box}>
              <FactPicker store={store} atom={g.atom} frame={g.frame} keyName={g.key} kinds={['word']}
                onChange={(x) => setTrig({ atom: x.atom, frame: x.frame, key: x.key, value: x.field?.vocab.find((w) => w !== 'none') ?? '' })} />
              <span className="dim" style={{ fontSize: 12 }}>=</span>
              <select className="cfginput" style={field} value={g.value} onChange={(e) => setTrig({ value: e.target.value })}>
                {(ev?.vocab ?? []).map((w) => <option key={w} value={w}>{wordAr(w)}</option>)}
              </select>
              <span className="dim" style={{ fontSize: 12 }}>وجهته من</span>
              <select className="cfginput" style={field} value={g.side_key} onChange={(e) => { const f = words.find((x) => x.key === e.target.value); setTrig({ side_key: e.target.value, buy: f?.vocab[0] ?? '', sell: f?.vocab[1] ?? '' }) }}>
                <option value="">— حقل الجهة —</option>
                {words.map((f) => <option key={f.key} value={f.key}>{f.label}</option>)}
              </select>
              <label className="dim" style={lbl}>للشراء <select className="cfginput" style={field} value={g.buy} onChange={(e) => setTrig({ buy: e.target.value })}>{(side?.vocab ?? []).map((w) => <option key={w} value={w}>{wordAr(w)}</option>)}</select></label>
              <label className="dim" style={lbl}>للبيع <select className="cfginput" style={field} value={g.sell} onChange={(e) => setTrig({ sell: e.target.value })}>{(side?.vocab ?? []).map((w) => <option key={w} value={w}>{wordAr(w)}</option>)}</select></label>
              <button className="btn" style={{ padding: '1px 8px' }} onClick={() => up({ entry: { ...spec.entry!, triggers: triggers.filter((_, j) => j !== i) } })}>احذف الإشارة</button>
            </div>
          )
        })}
      </div>

      <div style={box}>
        <span className="st" style={{ fontSize: 12 }}>الوقف</span>
        {([['structure', 'خلف آخر قاع/قمّة (المنظومة)'], ['fixed', 'ثابت بالبِب'], ['atr', 'مضاعف متوسّط المدى']] as const).map(([m, t]) => (
          <button key={m} style={chip(spec.stop.method === m)} onClick={() => up({ stop: { ...spec.stop, method: m } })}>{t}</button>
        ))}
        {spec.stop.method === 'structure' ? <>
          <label className="dim" style={lbl}>أدنى <NumIn v={spec.stop.band[0]} set={(x) => up({ stop: { ...spec.stop, band: [x, spec.stop.band[1]] } })} /></label>
          <label className="dim" style={lbl}>أقصى <NumIn v={spec.stop.band[1]} set={(x) => up({ stop: { ...spec.stop, band: [spec.stop.band[0], x] } })} /></label>
          <label className="dim" style={lbl}>هامش <NumIn v={spec.stop.pad} set={(x) => up({ stop: { ...spec.stop, pad: x } })} step={0.1} /></label>
        </> : spec.stop.method === 'fixed' ? (
          <label className="dim" style={lbl}>بِب <NumIn v={spec.stop.pips} set={(x) => up({ stop: { ...spec.stop, pips: x } })} /></label>
        ) : <>
          <select className="cfginput" style={field} value={spec.stop.atr_frame} onChange={(e) => up({ stop: { ...spec.stop, atr_frame: e.target.value } })}>{cat.frames.map((f) => <option key={f} value={f}>{frameAr(f)}</option>)}</select>
          <label className="dim" style={lbl}>× <NumIn v={spec.stop.atr_mult} set={(x) => up({ stop: { ...spec.stop, atr_mult: x } })} step={0.1} /></label>
        </>}
        <label className="dim" style={lbl}><input type="checkbox" checked={pairRules} onChange={(e) => setPairRules(e.target.checked)} /> حدود الوقف وهامشه وكلفته لكلّ زوج من جدول المنظومة</label>
      </div>

      <div style={box}>
        <span className="st" style={{ fontSize: 12 }}>الأهداف والاقتصاص</span>
        {spec.targets.map((t, i) => (
          <span key={i} style={{ display: 'inline-flex', gap: 4, alignItems: 'center', fontSize: 12 }}>
            <span className="dim">هدف {i + 1}:</span>
            <NumIn v={t.r} set={(x) => up({ targets: spec.targets.map((y, j) => (j === i ? { ...y, r: x } : y)) })} step={0.1} w={52} />
            <span className="dim">× يُغلق</span>
            <NumIn v={t.close_pct} set={(x) => up({ targets: spec.targets.map((y, j) => (j === i ? { ...y, close_pct: x } : y)) })} w={56} />
            <span className="dim">٪</span>
            <button className="btn" style={{ padding: '0 6px' }} onClick={() => up({ targets: spec.targets.filter((_, j) => j !== i) })}>×</button>
          </span>
        ))}
        {spec.targets.length < 5 ? <button className="btn" onClick={() => up({ targets: [...spec.targets, { r: (spec.targets[spec.targets.length - 1]?.r ?? 0) + 1, close_pct: 0 }] })}>أضف هدفًا</button> : null}
        <label className="dim" style={lbl}>التعادل بعد الهدف <NumIn v={spec.breakeven_after} set={(x) => up({ breakeven_after: x })} w={44} /></label>
        <label className="dim" style={lbl}>الوقف إلى <NumIn v={spec.trail_to_r} set={(x) => up({ trail_to_r: x })} step={0.1} w={52} />× بعد الهدف <NumIn v={spec.trail_after} set={(x) => up({ trail_after: x })} w={44} /></label>
      </div>

      <div style={box}>
        <span className="st" style={{ fontSize: 12 }}>القوانين</span>
        <label className="dim" style={lbl}>مخاطرة ٪ <NumIn v={spec.risk_pct} set={(x) => up({ risk_pct: x })} step={0.1} w={56} /></label>
        <label className="dim" style={lbl}>كلفة بِب <NumIn v={spec.cost_pips} set={(x) => up({ cost_pips: x })} step={0.1} w={56} /></label>
        <label className="dim" style={lbl}><input type="checkbox" checked={spec.scale_with_price} onChange={(e) => up({ scale_with_price: e.target.checked })} /> الوقف والكلفة بنسبة السعر</label>
        <label className="dim" style={lbl}>انتظار بعد الصفقة (دقيقة) <NumIn v={spec.wait_min} set={(x) => up({ wait_min: x })} w={52} /></label>
        <label className="dim" style={lbl}>أقصى صفقات اليوم (٠ = بلا) <NumIn v={spec.max_per_day} set={(x) => up({ max_per_day: x })} w={44} /></label>
        <label className="dim" style={lbl} title="قانون المالك ١٠/١١: المحسوبة وقفٌ كامل أو الأهداف كلّها، والتأمين لا يُحسب">يُغلق اليوم بعد صفقات محسوبة (٠ = بلا القانون) <NumIn v={spec.day_counted ?? 2} set={(x) => up({ day_counted: x })} w={44} /></label>
        <label className="dim" style={lbl}><input type="checkbox" checked={spec.session.use_red_lines} onChange={(e) => up({ session: { ...spec.session, use_red_lines: e.target.checked } })} /> نافذة الأصل وخطوطه الحمراء</label>
        <label className="dim" style={lbl}>أوّل دقائق ممنوعة <NumIn v={spec.session.first_minutes} set={(x) => up({ session: { ...spec.session, first_minutes: x } })} w={44} /></label>
        <label className="dim" style={lbl}><input type="checkbox" checked={spec.time_enough} onChange={(e) => up({ time_enough: e.target.checked })} /> القانون 21: لا صفقة جديدة في الساعة الأخيرة</label>
      </div>

      <div style={box}>
        <span className="st" style={{ fontSize: 12 }}>الأخبار</span>
        <label className="dim" style={lbl}><input type="checkbox" checked={spec.news.on} onChange={(e) => up({ news: { ...spec.news, on: e.target.checked } })} /> مرشّح الأخبار</label>
        {COLORS_AR.map(([c, t]) => (
          <button key={c} style={chip(spec.news.colors.includes(c))} onClick={() => up({ news: { ...spec.news, colors: spec.news.colors.includes(c) ? spec.news.colors.filter((x) => x !== c) : [...spec.news.colors, c] } })}>{t}</button>
        ))}
        <label className="dim" style={lbl}>قبل (دقيقة) <NumIn v={spec.news.before_min} set={(x) => up({ news: { ...spec.news, before_min: x } })} w={44} /></label>
        <label className="dim" style={lbl}>بعد <NumIn v={spec.news.after_min} set={(x) => up({ news: { ...spec.news, after_min: x } })} w={44} /></label>
        <label className="dim" style={lbl}><input type="checkbox" checked={spec.news.close_open} onChange={(e) => up({ news: { ...spec.news, close_open: e.target.checked } })} /> يُغلق المفتوح قبل الخبر</label>
        <span className="dim" style={{ fontSize: 12 }}>العملات: عملات الأصل والدولار</span>
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
        <div style={box}>
          <span className="st" style={{ fontSize: 12 }}>المقارنة</span>
          <input className="cfginput" style={{ ...field, width: 220 }} placeholder="اسم هذه التجربة" value={expLabel} onChange={(e) => setExpLabel(e.target.value)} />
          <button className="btn" disabled={!expLabel.trim()} onClick={() => { setExperiments([...experiments.filter((x) => x.label !== expLabel.trim()), { label: expLabel.trim(), spec: current() }]); setExpLabel('') }}>أضفها إلى المقارنة</button>
          <label className="dim" style={lbl}><input type="checkbox" checked={spec.reference_random} onChange={(e) => up({ reference_random: e.target.checked })} /> ومعها الجهة العشوائيّة</label>
        </div>
        {experiments.map((x) => (
          <div key={x.label} style={box}>
            <button style={chip(false)} onClick={() => { const merged = JSON.parse(JSON.stringify(cat.defaults)) as Spec; setSpec({ ...merged, ...x.spec, stop: { ...merged.stop, ...(x.spec.stop ?? {}) }, from: spec.from, to: spec.to, name: spec.name } as Spec); setExpLabel(x.label) }}>{x.label}</button>
            <button className="btn" style={{ padding: '0 6px' }} onClick={() => setExperiments(experiments.filter((y) => y.label !== x.label))}>×</button>
          </div>
        ))}
      </div>

      <div style={box}>
        <label className="dim" style={lbl}>اسم القياس (فارغ = يُكتب وحده) <input className="cfginput" style={{ ...field, width: 320 }} value={spec.name} onChange={(e) => up({ name: e.target.value })} /></label>
        <button className="btn start" disabled={busy || !symbols.length || !periods.length} onClick={() => void start()}>شغّل</button>
        <span className="dim num" style={{ fontSize: 12 }}>{symbols.length} × {periods.length} × {experiments.length || 1} = {symbols.length * periods.length * (experiments.length || 1)} تشغيل</span>
        {note ? <span style={{ fontSize: 13, color: note.ok ? 'var(--green)' : 'var(--amber)' }}>{note.text}</span> : null}
      </div>

      <details open={stores ? stores.stores.some((r) => !r.ready) : false}>
        <summary className="st" style={{ fontSize: 12, cursor: 'pointer' }}>مخازن الذرّات</summary>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginTop: 8 }}>
          <StoresTable state={stores} symbols={SYMBOL_AR} busy={busy} onComplete={() => void post('/gov/backtest/full/stores/complete', {}, 'بدأ إكمال المخازن على الجهاز، والناسداك أوّلًا')} />
          <div style={box}>
            <span className="dim" style={{ fontSize: 12 }}>مخزن بيدي: {SYMBOL_AR[symbols[0]] ?? symbols[0]} {periods[0]?.[0]} إلى {periods[0]?.[1]}</span>
            <label className="dim" style={lbl}>ذرّات بعينها <input className="cfginput" style={{ ...field, width: 150 }} placeholder="كلّها" value={buildAtoms} onChange={(e) => setBuildAtoms(e.target.value)} /></label>
            <label className="dim" style={lbl}><input type="checkbox" checked={buildTicks} onChange={(e) => setBuildTicks(e.target.checked)} /> تِكّات حقيقيّة</label>
            <button className="btn" disabled={busy || cat.building.length > 0 || !periods.length} onClick={() => void post('/gov/backtest/full/combo/build', { symbol: symbols[0], from: periods[0][0], to: periods[0][1], warm_days: 60, atoms: buildAtoms, real_ticks: buildTicks }, 'بدأ بناء المخزن على الجهاز')}>ابنِ مخزنًا</button>
            {cat.building.map((b) => <span key={b.name} className="dim num" style={{ fontSize: 11 }}>يُبنى {SYMBOL_AR[b.symbol] ?? b.symbol}: {b.progress}</span>)}
          </div>
        </div>
      </details>
    </div>
  )
}

// قياسات لا تُفتح فيها صفقات: اختيارٌ واحد وزرٌّ واحد مكان ثمانية أزرار.
const OTHER_MEASURES: { name: string; path: string; body: Record<string, unknown>; text: string }[] = [
  { name: 'اتّجاه الفريمات: الأدوات مقابل الشموع', path: 'direction/start', body: {}, text: 'الناسداك، 2022 و2023، الأطر التسعة. الفريم صاعد بعد ثلاث شموع صاعدة متتالية، ويبقى حتّى ثلاث هابطة. والأدوات تقول صاعد أو هابط فقط، وكم تطابق الشموع. بلا صفقات.' },
  { name: 'اضبط الاتّجاه على الماضي', path: 'direction/start', body: { fit: true }, text: 'أعدادٌ كثيرة على 2022 و2023 ويُختار الأعلى. على الماضي، وقد لا يصدق في المستقبل.' },
  { name: 'عاير الاتّجاه على موجات الماضي', path: 'direction/start', body: { describe: true }, text: 'الشارت بعد انتهائه مقسومٌ موجات كما تراها العين، وكم من 100 شمعة قال الجهاز موجتها بما كان يعرفه يومها.' },
  { name: 'امتحن الاتّجاه على 2024', path: 'direction/start', body: { exam: true }, text: 'الإعدادات المختارة على 2022 و2023 تُطبَّق كما هي على 2024 التي لم يرها.' },
  { name: 'علّم الاتّجاه وامتحنه', path: 'direction/start', body: { learn: true }, text: 'يتعلّم من شارت 2022 و2023 كاملًا كيف تُقرأ الحركة، ثمّ يُمتحن على 2024.' },
  { name: 'علّم بكلّ الأقسام والأدوات', path: 'direction/start', body: { learn: true, rich: true, sections: true }, text: 'مثله، ومعه حقائق الأقسام والأسواق المرتبطة والأخبار والمستويات.' },
  { name: 'الكواشف الثلاثة لتغيّر اتّجاه الجلسة', path: 'detectors/start', body: { symbol: 'USTEC' }, text: 'داخل جلسة نيويورك، أيّ الثلاثة يعرف تغيّر اتّجاه الجلسة أبكر وأصحّ: داو الأربع ساعات، أو ترتيب المتوسّطات على الربع ساعة، أو ردّ السعر عند مستويات الخريطة.' },
  { name: 'البحث عن استراتيجيّة رابحة', path: 'strategy/start', body: { symbol: 'USTEC' }, text: 'لكلّ إغلاق خمس دقائق ولكلّ جهة: كم كان الصافي بوقف البنية والأثلاث؟ والتلميذ يتعلّم الجواب، ويُمتحن على 2022 و2023.' },
]

export function OtherMeasures({ onStarted }: { onStarted: () => void }) {
  const [pick, setPick] = useState(0)
  const [busy, setBusy] = useState(false)
  const [note, setNote] = useState<{ ok: boolean; text: string } | null>(null)
  const m = OTHER_MEASURES[pick]
  return (
    <div className="scard" style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
      <div style={box}>
        <select className="cfginput" style={{ ...field, maxWidth: 380 }} value={pick} onChange={(e) => { setPick(Number(e.target.value)); setNote(null) }}>
          {OTHER_MEASURES.map((x, i) => <option key={x.name} value={i}>{x.name}</option>)}
        </select>
        <button className="btn start" disabled={busy} onClick={() => {
          setBusy(true); setNote(null)
          fetch(`/gov/backtest/full/${m.path}`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(m.body) })
            .then((r) => r.json() as Promise<{ ok: boolean; error?: string }>)
            .then((j) => { setNote(j.ok ? { ok: true, text: 'بدأ على الجهاز — النتيجة في قائمة التشغيلات تحت' } : { ok: false, text: j.error ?? 'تعذّر الإطلاق' }); onStarted() })
            .catch(() => setNote({ ok: false, text: 'خطأ اتّصال بخادم اللوحة' }))
            .finally(() => setBusy(false))
        }}>شغّل</button>
        {note ? <span style={{ fontSize: 13, color: note.ok ? 'var(--green)' : 'var(--amber)' }}>{note.text}</span> : null}
      </div>
      <div className="ss dim" style={{ fontSize: 12.5, lineHeight: 1.9 }}>{m.text}</div>
    </div>
  )
}

interface PlanRun { 'الزوج': string; 'السنة': string; 'التجربة': string; 'بلا_مخزن'?: string[]; 'الأقسام'?: Record<string, string[]>; 'التوليفة'?: { 'أيّام_القانون'?: Record<string, number>; 'الإحصاء': Record<string, number>; 'الأشهر': Record<string, number | string>[]; 'الحساب_الافتراضيّ': { account_falls: number }; 'وقف_أوّل_5_دقائق': number }; 'مرجع: جهة عشوائيّة'?: { 'الإحصاء': Record<string, number> } }

export function PlanReport({ summary, texts, folder }: { summary: Record<string, unknown>; texts?: Record<string, string>; folder?: string }) {
  const [open, setOpen] = useState('')
  const rows = Object.entries((summary['التجارب'] ?? {}) as Record<string, PlanRun>)
  const balance = Number(summary['رأس_المال'] ?? 9000)
  const dip = (low: number) => (low >= 0 ? 'ربح مباشرة' : `${num(low, 1)}٪ (${num(balance * low / 100, 0)}$)`)
  const pct = (v?: number) => (v == null ? '—' : <span className={`num ${v >= 0 ? 'green' : 'amber'}`} style={{ fontWeight: 700 }}>{v >= 0 ? '+' : ''}{num(v, 1)}٪</span>)
  const heads = ['الزوج', 'السنة', 'التجربة', 'صفقات', 'هدف أوّل', 'هدف ثانٍ', 'هدف ثالث', 'وقف', 'كم نزل قبل الربح', 'الصافي', 'العشوائيّ', 'سقوط الحساب', 'وقف في أوّل 5 دقائق']
  return (
    <div className="scard" style={{ overflowX: 'auto' }}>
      <div className="st" style={{ fontWeight: 700, fontSize: 15 }}>{String(summary['الاسم'] ?? '')}</div>
      <div className="ss dim num" style={{ fontSize: 11 }}>{folder} · {String(summary['الزمن'] ?? '')} · بلا حكم</div>
      {[...new Map(rows.filter(([, r]) => r['الأقسام']).map(([, r]) => [r['التجربة'], r['الأقسام']!])).entries()].map(([label, secs]) => (
        <div key={label} className="ss" style={{ fontSize: 12, marginTop: 6 }}>
          <span className="st">ما دخل «{label}» من كلّ قسم:</span>{' '}
          {Object.entries(secs).map(([s, a]) => `${s} ${a.length}`).join(' · ')} · المجموع {Object.values(secs).reduce((n, a) => n + a.length, 0)}
        </div>
      ))}
      <table className="tbl" style={{ width: '100%', fontSize: 12.5, borderCollapse: 'collapse', marginTop: 8 }}>
        <thead><tr className="dim">{heads.map((h) => <th key={h} style={cell}>{h}</th>)}</tr></thead>
        <tbody>{rows.map(([k, r]) => {
          const s = r['التوليفة']?.['الإحصاء']
          if (!s) return <tr key={k} style={{ borderTop: '1px solid var(--line)' }}><td style={cell}>{SYMBOL_AR[r['الزوج']] ?? r['الزوج']}</td><td className="num" style={cell}>{r['السنة']}</td><td style={cell}>{r['التجربة']}</td><td className="amber" colSpan={10} style={cell}>لم يُقس: لا مخزن فيه {(r['بلا_مخزن'] ?? []).join(' و') || 'ما طُلب'}</td></tr>
          return [
            <tr key={k} style={{ borderTop: '1px solid var(--line)', cursor: 'pointer', background: open === k ? 'var(--glass)' : undefined }} onClick={() => setOpen(open === k ? '' : k)}>
              <td style={cell}>{SYMBOL_AR[r['الزوج']] ?? r['الزوج']}</td><td className="num" style={cell}>{r['السنة']}</td><td style={cell}>{r['التجربة']}</td>
              <td className="num" style={cell}>{s['صفقات']}</td><td className="num" style={cell}>{s['بلغ_الهدف_1'] ?? 0}</td><td className="num" style={cell}>{s['بلغ_الهدف_2'] ?? 0}</td><td className="num" style={cell}>{s['بلغ_الهدف_3'] ?? 0}</td>
              <td className="num" style={cell}>{s['وقف_قبل_أيّ_هدف']}</td><td className="num" style={cell}>{dip(s['أعمق_نزول_تحت_البداية_٪'])}</td><td style={cell}>{pct(s['صافي_٪'])}</td>
              <td style={cell}>{pct(r['مرجع: جهة عشوائيّة']?.['الإحصاء']['صافي_٪'])}</td><td className="num" style={cell}>{r['التوليفة']?.['الحساب_الافتراضيّ'].account_falls}</td><td className="num" style={cell}>{r['التوليفة']?.['وقف_أوّل_5_دقائق']}</td>
            </tr>,
            open === k ? <tr key={`${k}-m`}><td colSpan={13} style={{ padding: 8 }}>
              <table className="tbl" style={{ fontSize: 12, borderCollapse: 'collapse' }}>
                <thead><tr className="dim">{['الشهر', 'صفقات', 'هدف أوّل', 'هدف ثانٍ', 'هدف ثالث', 'وقف', 'الصافي'].map((h) => <th key={h} style={cell}>{h}</th>)}</tr></thead>
                <tbody>{(r['التوليفة']?.['الأشهر'] ?? []).map((m) => <tr key={String(m['الشهر'])} style={{ borderTop: '1px solid var(--line)' }}><td className="num" style={cell}>{m['الشهر']}</td><td className="num" style={cell}>{m['صفقات']}</td><td className="num" style={cell}>{m['هدف_1'] ?? 0}</td><td className="num" style={cell}>{m['هدف_2'] ?? 0}</td><td className="num" style={cell}>{m['هدف_3'] ?? 0}</td><td className="num" style={cell}>{m['وقف']}</td><td style={cell}>{pct(Number(m['عائد_٪']))}</td></tr>)}</tbody>
              </table>
            </td></tr> : null,
          ]
        })}</tbody>
      </table>
      <div className="ss dim" style={{ marginTop: 6 }}>اضغط سطرًا لترى أشهره.</div>
      {rows.some(([, r]) => r['التوليفة']?.['أيّام_القانون']) ? <>
        <div className="st" style={{ marginTop: 10 }}>قانون اليوم: كيف انتهى كلّ يوم <span className="dim" style={{ fontSize: 11 }}>— المحسوبة وقفٌ كامل أو الأهداف كلّها، والتأمين لا يُحسب</span></div>
        <table className="tbl" style={{ fontSize: 12.5, borderCollapse: 'collapse', marginTop: 4 }}>
          <thead><tr className="dim">{['الزوج', 'السنة', 'التجربة', 'أيّام التداول', 'وقفان', 'الأهداف مرّتين', 'وقف وأهداف', 'لم يكتمل', 'بلا صفقة'].map((h) => <th key={h} style={cell}>{h}</th>)}</tr></thead>
          <tbody>{rows.filter(([, r]) => r['التوليفة']?.['أيّام_القانون']).map(([k, r]) => { const d = r['التوليفة']!['أيّام_القانون']!; return (
            <tr key={k} style={{ borderTop: '1px solid var(--line)' }}><td style={cell}>{SYMBOL_AR[r['الزوج']] ?? r['الزوج']}</td><td className="num" style={cell}>{r['السنة']}</td><td style={cell}>{r['التجربة']}</td>
              {['أيّام_التداول', 'وقفان', 'الأهداف_مرّتين', 'وقف_وأهداف', 'لم_يكتمل', 'بلا_صفقة'].map((x) => <td key={x} className="num" style={cell}>{d[x] ?? 0}</td>)}</tr>) })}</tbody>
        </table>
      </> : null}
      <details style={{ marginTop: 8 }}><summary className="st" style={{ cursor: 'pointer' }}>ملفّ النتيجة كاملًا</summary><pre style={{ whiteSpace: 'pre-wrap', fontSize: 12, marginTop: 6 }}>{texts?.['النتيجة.md'] ?? ''}</pre></details>
      <details style={{ marginTop: 4 }}><summary className="st" style={{ cursor: 'pointer' }}>ملفّ الاختبار</summary><pre className="dim" style={{ whiteSpace: 'pre-wrap', fontSize: 11, marginTop: 6 }}>{texts?.['الاختبار.md'] ?? ''}</pre></details>
    </div>
  )
}

interface ComboResult { 'الإحصاء': Record<string, unknown>; 'الأشهر': Record<string, unknown>[]; 'الساعات': Record<string, { 'صفقات': number; 'صافي_٪': number }>; 'الأيّام': Record<string, { 'صفقات': number; 'صافي_٪': number }>; 'منحنى_الرصيد': [string, number][] }

function Curve({ series }: { series: [string, [string, number][]][] }) {
  const all = series.flatMap(([, p]) => p.map((x) => x[1]))
  if (!all.length) return null
  const lo = Math.min(0, ...all), hi = Math.max(0, ...all), W = 900, H = 180
  const colors = ['var(--accent)', 'var(--dim)']
  return (
    <svg viewBox={`0 0 ${W} ${H}`} style={{ width: '100%', height: 180, direction: 'ltr' }}>
      <line x1={0} x2={W} y1={H - ((0 - lo) / (hi - lo || 1)) * H} y2={H - ((0 - lo) / (hi - lo || 1)) * H} stroke="var(--line)" />
      {series.map(([name, p], k) => (
        <polyline key={name} fill="none" stroke={colors[k % 2]} strokeWidth={k ? 1 : 2}
          points={p.map((x, i) => `${(i / Math.max(1, p.length - 1)) * W},${H - ((x[1] - lo) / (hi - lo || 1)) * H}`).join(' ')} />
      ))}
    </svg>
  )
}

export function ComboReport({ summary, trades, texts, folder }: { summary: Record<string, unknown>; trades: Record<string, string>[]; texts?: Record<string, string>; folder?: string }) {
  const res = (summary['النتائج'] ?? {}) as Record<string, ComboResult>
  const groups = Object.keys(res)
  const [g, setG] = useState(groups[0] ?? '')
  const [month, setMonth] = useState('')
  const [show, setShow] = useState('')
  const r = res[g]
  const statKeys = Object.keys(res[groups[0]]?.['الإحصاء'] ?? {}).filter((k) => typeof res[groups[0]]['الإحصاء'][k] !== 'object')
  const list = trades.filter((t) => t['المجموعة'] === g && (!month || t.day?.startsWith(month)))
  return (
    <>
      <div className="scard">
        <div className="st" style={{ fontWeight: 700, fontSize: 15 }}>{String(summary['الاسم'] ?? '')}</div>
        <div className="ss dim num" style={{ fontSize: 11, direction: 'ltr', textAlign: 'right' }}>{folder}</div>
        <div className="ss dim">{num(summary['ثوانٍ'] as number, 1)} ثانية · لحظات القرار {num(summary['لحظات_القرار'] as number, 0)} · بقيت بعد الشروط {num(summary['مرشّحة_بعد_الشروط'] as number, 0)}</div>
        <div style={{ display: 'flex', gap: 8, marginTop: 6 }}>
          {['الاختبار.md', 'النتيجة.md'].map((n) => <button key={n} style={chip(show === n)} onClick={() => setShow(show === n ? '' : n)}>{n === 'الاختبار.md' ? 'ملفّ الاختبار' : 'ملفّ النتيجة'}</button>)}
        </div>
        {show && texts?.[show] ? <pre style={{ whiteSpace: 'pre-wrap', fontSize: 12, marginTop: 6 }}>{texts[show]}</pre> : null}
      </div>
      <OwnerTables summary={summary} />
      <details className="scard"><summary className="st" style={{ cursor: 'pointer' }}>كلّ بنود الإحصاء</summary>
      <div style={{ overflowX: 'auto' }}>
        <div className="st">الإحصاء</div>
        <table className="tbl" style={{ width: '100%', fontSize: 12.5, borderCollapse: 'collapse', marginTop: 6 }}>
          <thead><tr className="dim"><th style={cell}>البند</th>{groups.map((x) => <th key={x} style={cell}>{x}</th>)}</tr></thead>
          <tbody>{statKeys.map((k) => (
            <tr key={k} style={{ borderTop: '1px solid var(--line)' }}><td style={cell}>{k.replace(/_/g, ' ')}</td>
              {groups.map((x) => <td key={x} className="num" style={cell}>{num(res[x]['الإحصاء'][k] as number)}</td>)}</tr>
          ))}</tbody>
        </table>
      </div>
      </details>
      <div className="scard">
        <div className="st">منحنى الرصيد ٪ <span className="dim" style={{ fontSize: 11 }}>— الخطّ العريض التوليفة، والرفيع المرجع</span></div>
        <Curve series={groups.map((x) => [x, res[x]['منحنى_الرصيد']])} />
      </div>
      <div className="scard" style={{ overflowX: 'auto' }}>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
          <span className="st">الأشهر</span>
          {groups.map((x) => <button key={x} style={chip(g === x)} onClick={() => setG(x)}>{x}</button>)}
        </div>
        <table className="tbl" style={{ width: '100%', fontSize: 12.5, borderCollapse: 'collapse', marginTop: 6 }}>
          <thead><tr className="dim">{Object.keys(r?.['الأشهر']?.[0] ?? {}).map((k) => <th key={k} style={cell}>{k.replace(/_/g, ' ')}</th>)}</tr></thead>
          <tbody>{(r?.['الأشهر'] ?? []).map((m) => (
            <tr key={String(m['الشهر'])} style={{ borderTop: '1px solid var(--line)', cursor: 'pointer', background: month === m['الشهر'] ? 'var(--glass)' : undefined }} onClick={() => setMonth(month === m['الشهر'] ? '' : String(m['الشهر']))}>
              {Object.entries(m).map(([k, v]) => <td key={k} className="num" style={cell}>{Array.isArray(v) ? v.map((w) => num(w as number)).join(' · ') : num(v as number)}</td>)}
            </tr>
          ))}</tbody>
        </table>
        <div className="ss dim">اضغط شهرًا لترى صفقاته تحت.</div>
      </div>
      <div className="scard" style={{ display: 'flex', gap: 30, flexWrap: 'wrap', fontSize: 12.5 }}>
        <div><div className="st">الأيّام</div>{Object.entries(r?.['الأيّام'] ?? {}).map(([d, v]) => <div key={d}>{d}: <span className="num">{v['صفقات']} صفقة · {num(v['صافي_٪'])}٪</span></div>)}</div>
        <div><div className="st">الساعات (ساعة تركيا)</div>{Object.entries(r?.['الساعات'] ?? {}).map(([h, v]) => <div key={h} className="num">{h}:00 — {v['صفقات']} صفقة · {num(v['صافي_٪'])}٪</div>)}</div>
      </div>
      <div className="scard" style={{ overflow: 'hidden', padding: 0 }}>
        <div style={{ padding: '10px 14px' }}><div className="st">الصفقات — {g}{month ? ` — ${month}` : ''} ({list.length})</div></div>
        <div style={{ overflowX: 'auto', maxHeight: 420 }}>
          <table className="tbl" style={{ width: '100%', fontSize: 12.5, borderCollapse: 'collapse' }}>
            <thead><tr className="dim">{['فُتحت (تركيا)', 'الجهة', 'الدخول', 'الوقف', 'المخاطرة بِب', 'بلغ', 'الخروج', 'المدّة د', 'أقصى ربح R', 'أقصى ضدّ R', 'النتيجة ٪'].map((h) => <th key={h} style={cell}>{h}</th>)}</tr></thead>
            <tbody>{list.map((t, i) => (
              <tr key={i} style={{ borderTop: '1px solid var(--line)' }}>
                <td className="num" style={cell}>{t.opened}</td><td style={cell}>{t.side}</td><td className="num" style={cell}>{t.entry}</td>
                <td className="num" style={cell}>{t.stop}</td><td className="num" style={cell}>{t.risk_pips}</td>
                <td style={cell}>{Number(t.reached) ? `الهدف ${t.reached}` : '—'}</td><td style={cell}>{t.exit}</td>
                <td className="num" style={cell}>{t.minutes}</td><td className="num" style={cell}>{t.mfe_r}</td><td className="num" style={cell}>{t.mae_r}</td>
                <td className={`num ${Number(t.pct) >= 0 ? 'green' : 'amber'}`} style={cell}>{t.pct}</td>
              </tr>
            ))}</tbody>
          </table>
        </div>
      </div>
    </>
  )
}

// ١٧/١٠ (المالك: «هدول جداول بدّي أشوفها بعد كلّ اختبار، بدها تتولّد بالنتيجة، ما بدّي أسألك عنها»): الخلاصة · الأهداف والوقف ·
// كيف انتهت الصفقات · المال — في أعلى كلّ تقرير (والأشهر تحتها).
function OwnerTables({ summary }: { summary: Record<string, unknown> }) {
  const res = (summary['النتائج'] ?? {}) as Record<string, { 'الإحصاء': Record<string, any> }>
  const groups = Object.keys(res)
  const combo = res['التوليفة']?.['الإحصاء'] ?? {}
  const ref = res['مرجع: جهة عشوائيّة']?.['الإحصاء']
  const balance = Number(summary['رأس_المال'] ?? 10000)
  const nT = Object.keys(combo).filter((k) => k.startsWith('بلغ_الهدف_')).length
  const pct = (v: number) => <span className={`num ${v >= 0 ? 'green' : 'amber'}`} style={{ fontWeight: 700 }}>{v >= 0 ? '+' : ''}{num(v, 1)}٪</span>
  const usd = (v: number) => <span className={`num ${v >= 0 ? 'green' : 'amber'}`}>{v >= 0 ? '+' : ''}{num(v * balance / 100, 0)}$</span>
  const th = (h: string[]) => <thead><tr className="dim">{h.map((x) => <th key={x} style={cell}>{x}</th>)}</tr></thead>
  const ends = Object.entries((combo['النهايات'] ?? {}) as Record<string, { 'صفقات': number; 'متوسّط_R': number }>).sort((a, b) => b[1]['صفقات'] - a[1]['صفقات'])
  return (
    <>
      <div className="scard" style={{ overflowX: 'auto' }}>
        <div className="st">١. الخلاصة</div>
        <table className="tbl" style={{ width: '100%', fontSize: 12.5, borderCollapse: 'collapse' }}>
          {th(['', 'صفقات', 'رابحة من 100', 'الصافي', 'معامل الربح', 'أكبر تراجع', 'أعمق نزول تحت البداية'])}
          <tbody>{groups.map((g) => { const s = res[g]['الإحصاء']; return (
            <tr key={g} style={{ borderTop: '1px solid var(--line)' }}><td style={cell}>{g}</td><td className="num" style={cell}>{s['صفقات']}</td>
              <td className="num" style={cell}>{num(s['نسبة_الربح'], 1)}</td><td style={cell}>{pct(s['صافي_٪'])}</td>
              <td className="num" style={cell}>{num(s['معامل_الربح'])}</td><td className="num" style={cell}>{num(s['أكبر_تراجع_٪'], 0)}٪</td>
              <td style={cell}>{pct(s['أعمق_نزول_تحت_البداية_٪'])}</td></tr>) })}</tbody>
        </table>
      </div>
      <div className="scard" style={{ overflowX: 'auto' }}>
        <div className="st">٢. الأهداف والوقف <span className="dim" style={{ fontSize: 11 }}>— متداخلة: من بلغ الثاني بلغ الأوّل قبله</span></div>
        <table className="tbl" style={{ width: '100%', fontSize: 12.5, borderCollapse: 'collapse' }}>
          {th(['', 'صفقات', ...Array.from({ length: nT }, (_, i) => `بلغت الهدف ${i + 1}`), 'ضربت الوقف قبل أيّ هدف'])}
          <tbody>{groups.map((g) => { const s = res[g]['الإحصاء']; return (
            <tr key={g} style={{ borderTop: '1px solid var(--line)' }}><td style={cell}>{g}</td><td className="num" style={cell}>{s['صفقات']}</td>
              {Array.from({ length: nT }, (_, i) => <td key={i} className="num green" style={cell}>{s[`بلغ_الهدف_${i + 1}`]}</td>)}
              <td className="num amber" style={cell}>{s['وقف_قبل_أيّ_هدف']}</td></tr>) })}</tbody>
        </table>
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1fr) minmax(0, 1fr)', gap: 10 }}>
        <div className="scard" style={{ overflowX: 'auto' }}>
          <div className="st">٣. كيف انتهت صفقات التوليفة</div>
          <table className="tbl" style={{ width: '100%', fontSize: 12.5, borderCollapse: 'collapse' }}>
            {th(['النهاية', 'صفقات', 'ربح الصفقة في المتوسّط'])}
            <tbody>{ends.map(([k, v]) => (
              <tr key={k} style={{ borderTop: '1px solid var(--line)' }}><td style={cell}>{k}</td><td className="num" style={cell}>{v['صفقات']}</td>
                <td className={`num ${v['متوسّط_R'] >= 0 ? 'green' : 'amber'}`} style={cell}>{v['متوسّط_R'] >= 0 ? '+' : ''}{num(v['متوسّط_R'])} من المخاطرة</td></tr>
            ))}</tbody>
          </table>
        </div>
        <div className="scard" style={{ overflowX: 'auto' }}>
          <div className="st">٥. المال <span className="dim" style={{ fontSize: 11 }}>— على حساب {num(balance, 0)}$</span></div>
          <table className="tbl" style={{ width: '100%', fontSize: 12.5, borderCollapse: 'collapse' }}>
            {th(['', 'النسبة', 'بالدولار'])}
            <tbody>
              <tr><td style={cell}>مجموع الصفقات الرابحة</td><td style={cell}>{pct(combo['إجماليّ_الربح_٪'] ?? 0)}</td><td style={cell}>{usd(combo['إجماليّ_الربح_٪'] ?? 0)}</td></tr>
              <tr style={{ borderTop: '1px solid var(--line)' }}><td style={cell}>مجموع الصفقات الخاسرة</td><td style={cell}>{pct(combo['إجماليّ_الخسارة_٪'] ?? 0)}</td><td style={cell}>{usd(combo['إجماليّ_الخسارة_٪'] ?? 0)}</td></tr>
              <tr style={{ borderTop: '1px solid var(--line)', fontWeight: 800 }}><td style={cell}>الصافي آخر الفترة</td><td style={cell}>{pct(combo['صافي_٪'] ?? 0)}</td><td style={cell}>{usd(combo['صافي_٪'] ?? 0)}</td></tr>
              {ref ? <tr style={{ borderTop: '1px solid var(--line)' }}><td style={cell} className="dim">الجهة العشوائيّة بالقوانين نفسها</td><td style={cell}>{pct(ref['صافي_٪'])}</td><td style={cell}>{usd(ref['صافي_٪'])}</td></tr> : null}
            </tbody>
          </table>
        </div>
      </div>
    </>
  )
}
