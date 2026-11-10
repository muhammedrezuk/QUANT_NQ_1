// المختبر — لماذا يفشل محلّلٌ أو قسم، على تِكّات سي‑تريدر الحقيقيّة والنظام كاملًا.
// ٢٠٢٦-١٠-٠٦ (ختم المالك «… المختبر … مثلها nq»): ترك ملفّات شموع الكريبتو القديمة إلى محرّك الاختبار
// الكامل؛ الجهاز يشغّل الجولة في الخلفيّة (وضع «مختبر»: آخر حالةٍ وسببها لكلّ حدث)، وعتبات المختبر
// المحفوظة تدخل الجولة نفسها. العزل صار عرضًا: النظام كلّه يعمل دائمًا، وتختار القسم أو المحلّل لتقرأه.
import { useCallback, useEffect, useMemo, useState } from 'react'
import { AtomConfigForm } from './Settings'

interface SectionSpec { id: string; ar: string; atoms: number[]; why: string; names?: Record<string, string> }
interface Analyst { id: number; key: string; ar: string }
interface LabCatalog { ok: boolean; sections?: Record<string, SectionSpec>; analysts?: Analyst[] }
interface Window { from?: string | null; to?: string | null }
interface FullCatalog { ok: boolean; windows?: { recorded?: Window | null; ctrader?: Record<string, Window> }; symbols?: string[] }
interface RunRow {
  name: string; status: string; mode?: string; started_at?: number; from?: number; to?: number
  symbols?: string[]; progress?: string; error_tail?: string
  brief?: { 'أحداث_متعثّرة'?: number }
}
interface LabRow { count: number; states: Record<string, number>; healthy_pct: number; reason: string; last: Record<string, unknown> }
interface Report { ok: boolean; error?: string; name?: string; summary?: Record<string, unknown>; lab?: Record<string, LabRow> }

const SYMBOL_AR: Record<string, string> = {
  XAUUSD: 'الذهب', BTCUSD: 'البتكوين', USTEC: 'الناسداك', US30: 'داو جونز', US500: 'إس آند بي',
  EURUSD: 'يورو/دولار', GBPUSD: 'جنيه/دولار',
}
const PREFIX: Record<string, string[]> = {
  analysis: ['analysis.'], structure: ['structure.'], liquidity: ['liquidity.'], statistics: ['stats.'],
  stats: ['stats.'], probability: ['probability.'], strategy: ['strategy.'], decision: ['decision.'],
  risk: ['risk.'], news: ['market.news', 'news.', 'market.calendar', 'market_data.calendar'],
}
const STATUS_AR: Record<string, string> = { running: 'يعمل', done: 'انتهت', failed: 'فشلت', stopped: 'أُوقفت' }
const num = (n?: number | null, d = 0) =>
  n == null || !Number.isFinite(n) ? '—' : n.toLocaleString('ar-EG-u-nu-latn', { maximumFractionDigits: d })
const when = (epoch?: number) => (epoch ? new Date(epoch * 1000).toLocaleString('ar-EG-u-nu-latn',
  { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit', timeZone: 'UTC' }) : '—')
const chip = (on: boolean) => ({
  fontSize: 12, padding: '3px 10px', borderRadius: 8, cursor: 'pointer', fontFamily: 'inherit',
  whiteSpace: 'nowrap' as const, background: on ? 'var(--accent)' : 'transparent',
  color: on ? '#06121c' : 'var(--dim)', border: `1px solid ${on ? 'var(--accent)' : 'var(--glassb)'}`,
})
const field = { margin: 0, padding: '4px 7px' }
const lbl = { fontSize: 12, display: 'flex', alignItems: 'center', gap: 6 } as const

export default function Lab() {
  const [labCat, setLabCat] = useState<LabCatalog | null>(null)
  const [fullCat, setFullCat] = useState<FullCatalog | null>(null)
  const [source, setSource] = useState<'ctrader' | 'recorded'>('ctrader')
  const [symbols, setSymbols] = useState<string[]>(['XAUUSD'])
  const [from, setFrom] = useState('')
  const [to, setTo] = useState('')
  const [warmup, setWarmup] = useState(1)
  const [section, setSection] = useState('full')
  const [analyst, setAnalyst] = useState<string>('')
  const [runs, setRuns] = useState<RunRow[]>([])
  const [report, setReport] = useState<Report | null>(null)
  const [openEvent, setOpenEvent] = useState<string | null>(null)
  const [note, setNote] = useState<{ ok: boolean; text: string } | null>(null)
  const [busy, setBusy] = useState(false)
  const [cfgAtom, setCfgAtom] = useState<number | ''>('')
  const [cmp, setCmp] = useState<string | null>(null)

  useEffect(() => {
    fetch('/gov/lab/catalog', { cache: 'no-store' }).then((r) => r.json() as Promise<LabCatalog>)
      .then(setLabCat).catch(() => setLabCat({ ok: false }))
    fetch('/gov/backtest/full/catalog', { cache: 'no-store' }).then((r) => r.json() as Promise<FullCatalog>)
      .then((c) => {
        setFullCat(c)
        const w = c.windows?.ctrader?.XAUUSD
        if (w?.to) {
          const end = new Date(w.to + 'Z')
          setTo(end.toISOString().slice(0, 16))
          setFrom(new Date(end.getTime() - 2 * 3600 * 1000).toISOString().slice(0, 16))
        }
      }).catch(() => setFullCat({ ok: false }))
  }, [])

  const loadRuns = useCallback(() => {
    fetch('/gov/backtest/full/runs', { cache: 'no-store' })
      .then((r) => r.json() as Promise<{ runs?: RunRow[] }>)
      .then((j) => setRuns((j.runs ?? []).filter((r) => r.mode === 'lab')))
      .catch(() => undefined)
  }, [])
  useEffect(() => { loadRuns(); const t = window.setInterval(loadRuns, 5000); return () => window.clearInterval(t) }, [loadRuns])

  const open = (name: string) => {
    setOpenEvent(null)
    fetch(`/gov/backtest/full/run/${name}`, { cache: 'no-store' }).then((r) => r.json() as Promise<Report>)
      .then(setReport).catch(() => setReport({ ok: false, error: 'تعذّر قراءة الجولة' }))
  }

  const run = async () => {
    setBusy(true); setNote(null)
    try {
      const r = await fetch('/gov/backtest/full/start', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ mode: 'lab', lab_overrides: true, source, symbols, from, to, workers: 1,
          warmup_hours: warmup }),
      })
      const j = await r.json() as { ok: boolean; error?: string }
      setNote(j.ok ? { ok: true, text: 'بدأت الجولة على الجهاز بعتبات المختبر — النتيجة في الجولات تحت' } : { ok: false, text: j.error ?? 'تعذّر الإطلاق' })
      loadRuns()
    } catch { setNote({ ok: false, text: 'خطأ اتّصال بخادم اللوحة' }) }
    setBusy(false)
  }
  const stop = async (name: string) => {
    await fetch('/gov/backtest/full/stop', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ name }) })
    loadRuns()
  }
  const resetLab = async () => {
    const j = await (await fetch('/gov/lab/reset-overrides', { method: 'POST' })).json() as { ok?: boolean; message?: string }
    setNote({ ok: !!j.ok, text: j.message ?? 'رجعت عتبات المختبر للأصل' })
  }
  const compare = () => {
    const done = runs.filter((r) => r.status === 'done' && r.brief)
    if (done.length < 2) { setCmp('تحتاج جولتين منتهيتين'); return }
    const [after, before] = done
    setCmp(`الأحداث المتعثّرة: ${num(before.brief?.['أحداث_متعثّرة'])} ← ${num(after.brief?.['أحداث_متعثّرة'])}`)
  }

  const sections = useMemo(() => Object.values(labCat?.sections ?? {}), [labCat])
  const names = useMemo(() => {
    const out: Record<number, string> = {}
    for (const s of sections) for (const [k, v] of Object.entries(s.names ?? {})) out[Number(k)] = v
    return out
  }, [sections])
  const visible = useMemo(() => {
    const lab = report?.lab ?? {}
    return Object.entries(lab).filter(([event]) => {
      if (analyst) return event === `analysis.${analyst}.state`
      if (section === 'full') return true
      return (PREFIX[section] ?? []).some((p) => event.startsWith(p))
    }).sort((a, b) => a[1].healthy_pct - b[1].healthy_pct)
  }, [report, section, analyst])
  const failing = visible.filter(([, v]) => v.healthy_pct < 50)
  const openRow = openEvent ? report?.lab?.[openEvent] : undefined
  const currentAtoms = section === 'full' ? sections.flatMap((s) => s.atoms) : labCat?.sections?.[section]?.atoms ?? []

  return (
    <div className="section" style={{ display: 'flex', flexDirection: 'column', gap: 10, minHeight: 0 }}>
      <div className="scard">
        <div className="st" style={{ fontWeight: 700, fontSize: 16 }}>المختبر — معزول عن التداول</div>
        <div className="ss dim" style={{ marginTop: 4 }}>
          النظام كاملًا على تِكّات سي‑تريدر الحقيقيّة، بعتبات المختبر المحفوظة أدناه. الجولة تقول لكلّ حدثٍ
          كم مرّة كان جاهزًا وآخر سببٍ لعدم جاهزيّته. العتبة هنا بنسخة المختبر وحدها — التداول لا يُمسّ.
          الصفقات والربح في صفحة «باك تست».
        </div>
      </div>

      <div className="scard" style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, alignItems: 'center' }}>
          <span className="st" style={{ fontSize: 12 }}>البيانات</span>
          <button style={chip(source === 'ctrader')} onClick={() => setSource('ctrader')}>تِكّات سي‑تريدر التاريخيّة</button>
          <button style={chip(source === 'recorded')} onClick={() => setSource('recorded')}>تِكّات النظام المسجّلة</button>
          <span className="st" style={{ fontSize: 12, marginInlineStart: 10 }}>الرموز</span>
          {(fullCat?.symbols ?? Object.keys(SYMBOL_AR)).map((sym) => (
            <button key={sym} style={chip(symbols.includes(sym))}
              onClick={() => setSymbols((cur) => cur.includes(sym) ? cur.filter((x) => x !== sym) : [...cur, sym])}>{SYMBOL_AR[sym] ?? sym}</button>
          ))}
        </div>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 12, alignItems: 'center' }}>
          <label className="dim" style={lbl}>من (غرينتش)<input className="cfginput" type="datetime-local" style={field} value={from} onChange={(e) => setFrom(e.target.value)} /></label>
          <label className="dim" style={lbl}>إلى<input className="cfginput" type="datetime-local" style={field} value={to} onChange={(e) => setTo(e.target.value)} /></label>
          <label className="dim" style={lbl}>إحماء (ساعة)<input className="cfginput num" type="number" min={0} step={0.5} style={{ ...field, width: 60 }} value={warmup} onChange={(e) => setWarmup(Number(e.target.value))} /></label>
          <span className="dim" style={{ fontSize: 11 }}>جولة المختبر قصيرة: ساعتان من البيانات تكفي لقراءة الأسباب</span>
        </div>
      </div>

      <div className="scard" style={{ display: 'flex', flexWrap: 'wrap', gap: 8, alignItems: 'center' }}>
        <span className="st" style={{ fontSize: 12 }}>اقرأ</span>
        <button style={chip(section === 'full' && !analyst)} onClick={() => { setSection('full'); setAnalyst('') }}>النظام كاملًا</button>
        {sections.map((s) => (
          <button key={s.id} style={chip(section === s.id && !analyst)} title={s.why} onClick={() => { setSection(s.id); setAnalyst('') }}>{s.ar}</button>
        ))}
      </div>
      {section === 'analysis' ? (
        <div className="scard" style={{ display: 'flex', flexWrap: 'wrap', gap: 8, alignItems: 'center' }}>
          <span className="st" style={{ fontSize: 12 }}>محلّل منفرد</span>
          {(labCat?.analysts ?? []).map((a) => (
            <button key={a.id} style={chip(analyst === a.key)} onClick={() => setAnalyst(analyst === a.key ? '' : a.key)}>{a.ar}</button>
          ))}
        </div>
      ) : null}

      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, alignItems: 'center' }}>
        <button className="btn start" disabled={busy || !symbols.length || !from || !to} onClick={() => void run()}>شغّل المختبر على الجهاز</button>
        <button className="btn" onClick={compare}>قارن آخر جولتين</button>
        <button className="btn" onClick={() => void resetLab()}>ارجع عتبات المختبر للأصل</button>
        {note ? <span style={{ fontSize: 13, color: note.ok ? 'var(--green)' : 'var(--amber)' }}>{note.text}</span> : null}
        {cmp ? <span style={{ fontSize: 13 }}>{cmp}</span> : null}
      </div>

      <div className="scard">
        <div className="st">الجولات</div>
        {runs.length === 0 ? <div className="ss dim" style={{ marginTop: 4 }}>لا جولة بعد.</div> : null}
        <div style={{ display: 'grid', gap: 6, marginTop: 6 }}>
          {runs.map((r) => (
            <div key={r.name} style={{ display: 'flex', flexWrap: 'wrap', gap: 10, alignItems: 'center', fontSize: 12.5, borderTop: '1px solid var(--line)', paddingTop: 6 }}>
              <span className={r.status === 'done' ? 'green' : r.status === 'running' ? '' : 'amber'}>{STATUS_AR[r.status] ?? r.status}</span>
              <span className="num">{when(r.from)} ← {when(r.to)}</span>
              <span>{(r.symbols ?? []).map((x) => SYMBOL_AR[x] ?? x).join('، ')}</span>
              {r.brief?.['أحداث_متعثّرة'] != null ? <span>أحداث متعثّرة <span className="num amber">{num(r.brief['أحداث_متعثّرة'])}</span></span> : null}
              {r.status === 'running' && r.progress ? <span className="dim num" style={{ fontSize: 11 }}>{r.progress}</span> : null}
              {r.status === 'done' ? <button className="btn" style={{ padding: '1px 10px' }} onClick={() => open(r.name)}>اقرأ</button> : null}
              {r.status === 'running' ? <button className="btn" style={{ padding: '1px 10px' }} onClick={() => void stop(r.name)}>أوقف</button> : null}
              {r.status === 'failed' && r.error_tail ? <pre className="dim" style={{ margin: 0, fontSize: 11, whiteSpace: 'pre-wrap', width: '100%' }}>{r.error_tail}</pre> : null}
            </div>
          ))}
        </div>
      </div>

      {report && !report.ok ? <div className="scard" style={{ color: 'var(--amber)' }}>{report.error}</div> : null}
      {report?.ok ? (
        <>
          <div className="cards" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))' }}>
            <div className="scard"><div className="st">أحداث مقروءة</div><div className="sv num">{num(visible.length)}</div><div className="ss">في ما اخترت</div></div>
            <div className="scard"><div className="st">متعثّرة (جاهزة أقلّ من النصف)</div><div className={`sv num ${failing.length ? 'amber' : 'green'}`}>{num(failing.length)}</div></div>
            <div className="scard"><div className="st">تِكّات الجولة</div><div className="sv num">{num(report.summary?.['تِكّات'] as number)}</div></div>
          </div>
          <div className="scard" style={{ overflow: 'hidden', padding: 0 }}>
            <div style={{ padding: '10px 14px', borderBottom: '1px solid var(--glassb)' }}>
              <div className="st">الأحداث — الأضعف جاهزيّةً أوّلًا</div>
              <div className="ss dim">اضغط صفًّا لترى آخر حمولةٍ نشرها.</div>
            </div>
            <div style={{ overflowX: 'auto', maxHeight: 420 }}>
              <table className="tbl" style={{ width: '100%', fontSize: 12, borderCollapse: 'collapse' }}>
                <thead><tr className="dim" style={{ textAlign: 'right' }}>
                  {['الحدث (اسمه في الكود)', 'مرّات', 'جاهز٪', 'الحالات', 'آخر سبب'].map((h) => <th key={h} style={{ padding: '5px 10px' }}>{h}</th>)}
                </tr></thead>
                <tbody>
                  {visible.map(([event, v]) => (
                    <tr key={event} style={{ borderTop: '1px solid var(--line)', cursor: 'pointer' }} onClick={() => setOpenEvent(openEvent === event ? null : event)}>
                      <td style={{ padding: '5px 10px', fontFamily: 'ui-monospace, monospace', direction: 'ltr', textAlign: 'left' }}>{event}</td>
                      <td className="num" style={{ padding: '5px 10px' }}>{num(v.count)}</td>
                      <td className={`num ${v.healthy_pct < 50 ? 'amber' : 'green'}`} style={{ padding: '5px 10px' }}>{num(v.healthy_pct, 1)}</td>
                      <td className="num dim" style={{ padding: '5px 10px', direction: 'ltr' }}>{Object.entries(v.states).map(([k, c]) => `${k}:${c}`).join(' ')}</td>
                      <td style={{ padding: '5px 10px', color: 'var(--amber)', direction: 'ltr', textAlign: 'left' }}>{v.reason}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
          {openRow ? (
            <div className="scard">
              <div className="st">آخر حمولة</div>
              <pre style={{ margin: '8px 0 0', fontSize: 12, direction: 'ltr', textAlign: 'left', whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>{JSON.stringify(openRow.last, null, 2)}</pre>
            </div>
          ) : null}
        </>
      ) : null}

      <div className="scard">
        <div className="st">تعديل عتبات ذرّة — نسخة المختبر</div>
        <div className="ss dim" style={{ marginBottom: 8 }}>
          الحفظ يكتب نسخة المختبر وحدها، وتدخل الجولة التالية هنا. التداول الحيّ لا يتغيّر.
        </div>
        <select className="cfginput" style={{ minWidth: 260 }} value={cfgAtom === '' ? '' : String(cfgAtom)}
          onChange={(e) => setCfgAtom(e.target.value === '' ? '' : Number(e.target.value))}>
          <option value="">اختر ذرّة للمعايرة…</option>
          {currentAtoms.map((id) => <option key={id} value={id}>{id} · {names[id] ?? id}</option>)}
        </select>
        {cfgAtom !== '' ? <div style={{ marginTop: 10 }}><AtomConfigForm atomId={cfgAtom} sandbox /></div> : null}
      </div>
    </div>
  )
}
