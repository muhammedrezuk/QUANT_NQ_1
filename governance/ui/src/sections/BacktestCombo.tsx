// منشئ التوليفة — أداة الباك تست الاحترافيّة (ورقة الخطوات ١٧/١٠، الخطوة 6؛ ختم المالك «NQ»).
// قوله: «أيّ توليفة بدّي ياها بقدر أختبرها أنا بيدي … أغيّر أهداف واقتصاص وستوب … مع أخبار … سريعة، وتقرير كامل واضح بالعربي».
// الحقائق من مخزن الحقائق (ذرّات الأقسام الحقيقيّة شُغّلت على شموع الفترة مرّةً)، والمحرّك `backtest/combo_engine.py`.
import { useEffect, useMemo, useState } from 'react'

interface Field { key: string; label: string; kind: 'num' | 'word'; vocab: string[]; frames: string[] }
interface AtomInfo { id: string; name: string; frames: string[]; fields: Field[] }
interface Store { symbol: string; folder: string; from: string; to: string; minutes?: number; atoms: AtomInfo[]; path?: string; kind?: string; ticks?: string }
interface Trig { atom: string; frame: string; key: string; value: string; side_key: string; buy: string; sell: string }
interface ComboCatalog { ok: boolean; error?: string; stores: Store[]; defaults: Spec; frames: string[]; symbols: string[]; building: { name: string; symbol: string; progress: string }[] }
interface Cond { atom: string; frame: string; key: string; op: string; value: unknown; max_age_min?: number }
interface Spec {
  symbol: string; from: string; to: string; decision_frame: string
  direction: { source: 'random' | 'fact'; atom?: string; frame?: string; key?: string }
  conditions: Cond[]
  stop: { method: 'structure' | 'fixed' | 'atr'; band: [number, number]; pips: number; atr_frame: string; atr_mult: number; pad: number }
  targets: { r: number; close_pct: number }[]
  breakeven_after: number; trail_after: number; trail_to_r: number; risk_pct: number; cost_pips: number
  scale_with_price: boolean; wait_min: number; max_per_day: number
  session: { use_red_lines: boolean; first_minutes: number }
  news: { on: boolean; colors: string[]; before_min: number; after_min: number; close_open: boolean; currencies: string[] }
  time_enough: boolean; reference_random: boolean; name: string
  store?: string
  entry?: { within_min: number; triggers: Trig[] }
}

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
const OPS_NUM: [string, string][] = [['same_way', 'إشارته في جهة الصفقة'], ['>', 'أكبر من'], ['>=', 'أكبر أو يساوي'], ['<', 'أصغر من'], ['<=', 'أصغر أو يساوي'], ['==', 'يساوي'], ['!=', 'لا يساوي'], ['between', 'بين']]
const OPS_WORD: [string, string][] = [['==', 'يساوي'], ['!=', 'لا يساوي'], ['same_way', 'في جهة الصفقة نفسها']]
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
        {(store?.atoms ?? []).map((x) => <option key={x.id} value={x.id}>{x.id} {x.name}</option>)}
      </select>
      <select className="cfginput" style={field} value={frame ?? ''} onChange={(e) => onChange({ atom: atom ?? '', frame: e.target.value, key: keyName ?? '' })}>
        {(a?.frames ?? []).map((f) => <option key={f} value={f}>{f}</option>)}
      </select>
      <select className="cfginput" style={{ ...field, maxWidth: 280 }} value={keyName ?? ''} onChange={(e) => onChange({ atom: atom ?? '', frame: frame ?? '', key: e.target.value, field: fields.find((f) => f.key === e.target.value) })}>
        <option value="">— الحقيقة —</option>
        {fields.map((f) => <option key={f.key} value={f.key}>{f.label} ({f.key})</option>)}
      </select>
    </>
  )
}

export function ComboBuilder({ onStarted }: { onStarted: () => void }) {
  const [cat, setCat] = useState<ComboCatalog | null>(null)
  const [spec, setSpec] = useState<Spec | null>(null)
  const [note, setNote] = useState<{ ok: boolean; text: string } | null>(null)
  const [busy, setBusy] = useState(false)
  const [buildAtoms, setBuildAtoms] = useState('')
  const [buildTicks, setBuildTicks] = useState(false)
  const load = () => fetch('/gov/backtest/full/combo/catalog', { cache: 'no-store' })
    .then((r) => r.json() as Promise<ComboCatalog>)
    .then((c) => { setCat(c); setSpec((cur) => cur ?? JSON.parse(JSON.stringify(c.defaults)) as Spec) })
    .catch(() => setCat({ ok: false, error: 'خادم اللوحة لا يجيب', stores: [], defaults: {} as Spec, frames: [], symbols: [], building: [] }))
  useEffect(() => { void load(); const t = window.setInterval(() => void load(), 15000); return () => window.clearInterval(t) }, [])
  // ١٩/١٠: لفترةٍ واحدة قد يكون أكثر من مخزن (كامل · سريع · البنية · التِّكّ الحقيقيّ) — يختار المالك منها.
  const matches = useMemo(() => (cat?.stores ?? []).filter((s) => spec && s.symbol === spec.symbol && s.from === spec.from && s.to === spec.to), [cat, spec])
  const store = matches.find((s) => s.path === spec?.store) ?? matches[0]
  if (!cat || !spec) return <div className="scard dim">يُحمَّل الفهرس…</div>
  const up = (patch: Partial<Spec>) => setSpec({ ...spec, ...patch })
  const post = async (path: string, body: unknown, ok: string) => {
    setBusy(true); setNote(null)
    try {
      const r = await fetch(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
      const j = await r.json() as { ok: boolean; error?: string }
      setNote(j.ok ? { ok: true, text: ok } : { ok: false, text: j.error ?? 'تعذّر' })
      onStarted(); void load()
    } catch { setNote({ ok: false, text: 'خطأ اتّصال بخادم اللوحة' }) }
    setBusy(false)
  }
  const setCond = (i: number, c: Partial<Cond>) => up({ conditions: spec.conditions.map((x, j) => (j === i ? { ...x, ...c } : x)) })
  const fieldOf = (c: { atom?: string; key?: string }) => store?.atoms.find((a) => a.id === c.atom)?.fields.find((f) => f.key === c.key)

  return (
    <div className="scard" style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      <div className="st">منشئ التوليفة — اختر البيانات والجهة والشروط وإدارة الصفقة، ثمّ شغّل</div>

      <div style={box}>
        <span className="st" style={{ fontSize: 12 }}>البيانات</span>
        <select className="cfginput" style={field} value={spec.symbol} onChange={(e) => up({ symbol: e.target.value })}>
          {cat.symbols.map((s) => <option key={s} value={s}>{SYMBOL_AR[s] ?? s}</option>)}
        </select>
        <label className="dim" style={lbl}>من <input className="cfginput" type="date" style={field} value={spec.from} onChange={(e) => up({ from: e.target.value })} /></label>
        <label className="dim" style={lbl}>إلى <input className="cfginput" type="date" style={field} value={spec.to} onChange={(e) => up({ to: e.target.value })} /></label>
        <span className="dim" style={{ fontSize: 12 }}>شموع الدقيقة المحفوظة + حقائق الذرّات الحقيقيّة</span>
        {store ? (
          <>
            <select className="cfginput" style={field} value={store.path ?? ''} onChange={(e) => up({ store: e.target.value })}>
              {matches.map((s) => <option key={s.path} value={s.path}>مخزن {s.kind} · {s.atoms.length} ذرّة · تِكّات {s.ticks}</option>)}
            </select>
          </>
        ) : <span className="amber" style={{ fontSize: 12 }}>لا مخزن حقائق لهذه الفترة</span>}
        <label className="dim" style={lbl}>ذرّات بعينها <input className="cfginput" style={{ ...field, width: 150 }} placeholder="كلّها" value={buildAtoms} onChange={(e) => setBuildAtoms(e.target.value)} /></label>
        <label className="dim" style={lbl}><input type="checkbox" checked={buildTicks} onChange={(e) => setBuildTicks(e.target.checked)} /> تِكّات حقيقيّة</label>
        <button className="btn" disabled={busy || cat.building.length > 0} onClick={() => void post('/gov/backtest/full/combo/build', { symbol: spec.symbol, from: spec.from, to: spec.to, warm_days: 60, atoms: buildAtoms, real_ticks: buildTicks }, 'بدأ بناء المخزن على الجهاز')}>ابنِ مخزنًا</button>
        {cat.building.map((b) => <span key={b.name} className="dim num" style={{ fontSize: 11 }}>يُبنى {SYMBOL_AR[b.symbol] ?? b.symbol}: {b.progress}</span>)}
      </div>

      <div style={box}>
        <span className="st" style={{ fontSize: 12 }}>لحظة القرار</span>
        <span className="dim" style={{ fontSize: 12 }}>كلّ إغلاق</span>
        <select className="cfginput" style={field} value={spec.decision_frame} onChange={(e) => up({ decision_frame: e.target.value })}>
          {cat.frames.map((f) => <option key={f} value={f}>{f}</option>)}
        </select>
        <span className="st" style={{ fontSize: 12, marginInlineStart: 12 }}>الجهة</span>
        <button style={chip(spec.direction.source === 'random')} onClick={() => up({ direction: { source: 'random' } })}>عشوائيّة</button>
        <button style={chip(spec.direction.source === 'fact')} onClick={() => up({ direction: { source: 'fact', atom: '209', frame: '15m', key: 'readings.four_hours.trend' } })}>من حقيقة</button>
        {spec.direction.source === 'fact' ? (
          <FactPicker store={store} atom={spec.direction.atom} frame={spec.direction.frame} keyName={spec.direction.key}
            onChange={(x) => up({ direction: { source: 'fact', atom: x.atom, frame: x.frame, key: x.key } })} />
        ) : null}
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
        <div style={box}>
          <span className="st" style={{ fontSize: 12 }}>الشروط (كلّها معًا)</span>
          <button className="btn" onClick={() => up({ conditions: [...spec.conditions, { atom: '', frame: '15m', key: '', op: '>', value: 0 }] })}>أضف شرطًا</button>
        </div>
        {spec.conditions.map((c, i) => {
          const f = fieldOf(c)
          const ops = f?.kind === 'word' ? OPS_WORD : OPS_NUM
          return (
            <div key={i} style={box}>
              <FactPicker store={store} atom={c.atom} frame={c.frame} keyName={c.key}
                onChange={(x) => setCond(i, { atom: x.atom, frame: x.frame, key: x.key, op: x.field?.kind === 'word' ? '==' : c.op === 'same_way' ? '>' : c.op, value: x.field?.kind === 'word' ? x.field.vocab[0] ?? '' : c.value })} />
              <select className="cfginput" style={field} value={c.op} onChange={(e) => setCond(i, { op: e.target.value, value: e.target.value === 'between' ? [0, 1] : c.value })}>
                {ops.map(([v, t]) => <option key={v} value={v}>{t}</option>)}
              </select>
              {c.op === 'same_way' ? null : f?.kind === 'word' ? (
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
              <button className="btn" style={{ padding: '1px 8px' }} onClick={() => up({ conditions: spec.conditions.filter((_, j) => j !== i) })}>احذف الشرط</button>
            </div>
          )
        })}
      </div>

      {/* ١٩/١٠ (المالك: «كمّل على دخول بتِكّات حقيقيّة»): رأس الحربة — بعد لحظة القرار يُنتظر أوّل حدثٍ في جهة الصفقة، والدخول بإغلاق دقيقته. */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
        <div style={box}>
          <span className="st" style={{ fontSize: 12 }}>إشارة الدخول (رأس الحربة)</span>
          <button className="btn" onClick={() => up({ entry: { within_min: spec.entry?.within_min ?? 15, triggers: [...(spec.entry?.triggers ?? []), { atom: '', frame: '1m', key: 'signal', value: '', side_key: '', buy: '', sell: '' }] } })}>أضف إشارة</button>
          {spec.entry?.triggers.length ? <label className="dim" style={lbl}>ينتظرها حتّى (دقيقة) <NumIn v={spec.entry.within_min} set={(x) => up({ entry: { ...spec.entry!, within_min: x } })} w={56} /></label>
            : <span className="dim" style={{ fontSize: 12 }}>بلا إشارة: الدخول بإغلاق لحظة القرار</span>}
        </div>
        {(spec.entry?.triggers ?? []).map((g, i) => {
          const setTrig = (patch: Partial<Trig>) => up({ entry: { ...spec.entry!, triggers: spec.entry!.triggers.map((x, j) => (j === i ? { ...x, ...patch } : x)) } })
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
              <button className="btn" style={{ padding: '1px 8px' }} onClick={() => up({ entry: { ...spec.entry!, triggers: spec.entry!.triggers.filter((_, j) => j !== i) } })}>احذف الإشارة</button>
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
          <select className="cfginput" style={field} value={spec.stop.atr_frame} onChange={(e) => up({ stop: { ...spec.stop, atr_frame: e.target.value } })}>{cat.frames.map((f) => <option key={f}>{f}</option>)}</select>
          <label className="dim" style={lbl}>× <NumIn v={spec.stop.atr_mult} set={(x) => up({ stop: { ...spec.stop, atr_mult: x } })} step={0.1} /></label>
        </>}
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
        <span className="st" style={{ fontSize: 12 }}>المخاطرة والوقت</span>
        <label className="dim" style={lbl}>مخاطرة ٪ <NumIn v={spec.risk_pct} set={(x) => up({ risk_pct: x })} step={0.1} w={56} /></label>
        <label className="dim" style={lbl}>كلفة بِب <NumIn v={spec.cost_pips} set={(x) => up({ cost_pips: x })} step={0.1} w={56} /></label>
        <label className="dim" style={lbl}><input type="checkbox" checked={spec.scale_with_price} onChange={(e) => up({ scale_with_price: e.target.checked })} /> الوقف والكلفة بنسبة السعر</label>
        <label className="dim" style={lbl}>انتظار بعد الصفقة (دقيقة) <NumIn v={spec.wait_min} set={(x) => up({ wait_min: x })} w={52} /></label>
        <label className="dim" style={lbl}>أقصى صفقات اليوم (٠ = بلا) <NumIn v={spec.max_per_day} set={(x) => up({ max_per_day: x })} w={44} /></label>
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
        <label className="dim" style={lbl}>العملات <input className="cfginput" style={{ ...field, width: 110 }} value={spec.news.currencies.join(',')} onChange={(e) => up({ news: { ...spec.news, currencies: e.target.value.split(',').map((x) => x.trim().toUpperCase()).filter(Boolean) } })} /></label>
        <label className="dim" style={lbl}>قبل (دقيقة) <NumIn v={spec.news.before_min} set={(x) => up({ news: { ...spec.news, before_min: x } })} w={44} /></label>
        <label className="dim" style={lbl}>بعد <NumIn v={spec.news.after_min} set={(x) => up({ news: { ...spec.news, after_min: x } })} w={44} /></label>
        <label className="dim" style={lbl}><input type="checkbox" checked={spec.news.close_open} onChange={(e) => up({ news: { ...spec.news, close_open: e.target.checked } })} /> يُغلق المفتوح قبل الخبر</label>
      </div>

      <div style={box}>
        <label className="dim" style={lbl}><input type="checkbox" checked={spec.reference_random} onChange={(e) => up({ reference_random: e.target.checked })} /> مرجع بجهةٍ عشوائيّة</label>
        <label className="dim" style={lbl}>اسم الاختبار (فارغ = يُكتب وحده) <input className="cfginput" style={{ ...field, width: 320 }} value={spec.name} onChange={(e) => up({ name: e.target.value })} /></label>
        <button className="btn start" disabled={busy || !store} onClick={() => void post('/gov/backtest/full/combo/start', { spec: { ...spec, store: store?.path } }, 'بدأ على الجهاز — النتيجة في قائمة التشغيلات، وفي مجلّد «اختبارات الباك تست» بتاريخ اليوم')}>شغّل التوليفة</button>
        {note ? <span style={{ fontSize: 13, color: note.ok ? 'var(--green)' : 'var(--amber)' }}>{note.text}</span> : null}
      </div>
    </div>
  )
}

interface ComboResult { 'الإحصاء': Record<string, unknown>; 'الأشهر': Record<string, unknown>[]; 'الساعات': Record<string, { 'صفقات': number; 'صافي_٪': number }>; 'الأيّام': Record<string, { 'صفقات': number; 'صافي_٪': number }>; 'منحنى_الرصيد': [string, number][] }
const num = (n?: unknown, d = 2) => (typeof n === 'number' && Number.isFinite(n) ? n.toLocaleString('ar-EG-u-nu-latn', { maximumFractionDigits: d }) : n == null ? '—' : String(n))
const cell = { padding: '5px 8px' }

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
