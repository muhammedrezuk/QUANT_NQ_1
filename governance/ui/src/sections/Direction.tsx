// الاتّجاه بنظرة واحدة — ختم المالك «NQ» ٢٠٢٦-١٠-٢٢: «بهمّني أعرف بأيّ وقت نحن بأيّ اتّجاه بدون ما أفتح شارت … بدّي أشوف كلّ
// الفريمات على كلّ زوج صاعد أو هابط بنظرة وحدة» · «ثلاث شموع متتالية».
//
// المصدر الوحيد: `structure.direction.state` من الذرّة 211 (`atoms/قسم 200-249/211_اتجاه_الفريمات/atom.py`)، مفتاحه الرمز.
// ⛔ اللوحة لا تحسب اتّجاهًا: تعرض ما نشرته الذرّة، والغائب يُقال غائبًا.
import { useStore } from '../core/store'

const SYMBOLS = ['USTEC', 'US500', 'US30', 'XAUUSD', 'BTCUSD', 'EURUSD', 'GBPUSD']
const SYMBOL_AR: Record<string, string> = {
  USTEC: 'الناسداك', US500: 'إس آند بي', US30: 'داو جونز', XAUUSD: 'الذهب', BTCUSD: 'البتكوين',
  EURUSD: 'يورو/دولار', GBPUSD: 'جنيه/دولار',
}
const FRAMES: [string, string][] = [
  ['1m', 'الدقيقة'], ['5m', '5 دقائق'], ['15m', 'ربع ساعة'], ['30m', 'نصف ساعة'], ['1h', 'الساعة'],
  ['4h', '4 ساعات'], ['1d', 'اليوم'], ['1w', 'الأسبوع'], ['1mo', 'الشهر'],
]
const FRAME_S: Record<string, number> = { '1m': 60, '5m': 300, '15m': 900, '30m': 1800, '1h': 3600, '4h': 14400, '1d': 86400 }

interface FrameState { trend?: 'up' | 'down' | null; since_bars?: number; since?: number | null; bars?: number }
interface DirectionState { symbol?: string; period_start?: number; timeframe?: string; run?: number; frames?: Record<string, FrameState> }

const turkey = (sec?: number | null): string => {
  if (!sec) return '—'
  return new Intl.DateTimeFormat('ar', {
    timeZone: 'Europe/Istanbul', day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit',
    hour12: false, numberingSystem: 'latn',
  }).format(new Date(sec * 1000))
}

function Cell({ f }: { f?: FrameState }) {
  const up = f?.trend === 'up'
  const down = f?.trend === 'down'
  const tone = up ? 'var(--green)' : down ? 'var(--red)' : 'var(--grey)'
  return (
    <td style={{ textAlign: 'center', padding: '8px 6px', borderTop: '1px solid var(--line)', background: up ? '#34d39922' : down ? '#fb718522' : 'transparent' }}>
      <div style={{ color: tone, fontWeight: 700, fontSize: 15 }}>{up ? 'صاعد' : down ? 'هابط' : '—'}</div>
      <div className="dim num" style={{ fontSize: 11 }}>{up || down ? `منذ ${f?.since_bars ?? 0} شمعة` : (f?.bars ? 'ينتظر ثلاثًا متتالية' : 'لا شموع بعد')}</div>
    </td>
  )
}

export default function Direction() {
  const states = (useStore((s) => s.symbolStreams['structure.direction.state']) ?? {}) as Record<string, DirectionState>
  const any = SYMBOLS.some((s) => states[s])
  return (
    <div className="section" style={{ display: 'flex', flexDirection: 'column', gap: 10, minHeight: 0 }}>
      <div className="scard">
        <div className="st" style={{ fontWeight: 700, fontSize: 16 }}>الاتّجاه — كلّ الفريمات على كلّ زوج</div>
        <div className="ss dim" style={{ marginTop: 4, lineHeight: 1.8 }}>
          قاعدتك: الفريم يصير صاعدًا بعد ثلاث شموع صاعدة متتالية (قمّة أعلى وقاع أعلى)، ويبقى صاعدًا حتّى تأتي ثلاث هابطة متتالية.
          لا عرضيّ. هذه أداة اتّجاه لا صفقات. الوقت بساعة تركيا.
        </div>
      </div>
      {!any ? (
        <div className="scard" style={{ color: 'var(--amber)' }}>
          لا قراءة بعد: الذرّة 211 تنشر مع أوّل شمعةٍ تُغلق لكلّ زوج. إن طال الانتظار فالمنظومة مطفأة أو السوق مغلق.
        </div>
      ) : null}
      <div className="scard" style={{ overflowX: 'auto' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
          <thead>
            <tr>
              <th style={{ textAlign: 'right', padding: 6 }}>الزوج</th>
              {FRAMES.map(([k, ar]) => <th key={k} style={{ padding: 6, fontWeight: 600 }}>{ar}</th>)}
              <th style={{ padding: 6, fontWeight: 600 }}>صاعد من 9</th>
            </tr>
          </thead>
          <tbody>
            {SYMBOLS.map((sym) => {
              const st = states[sym]
              const frames = st?.frames ?? {}
              const ups = FRAMES.filter(([k]) => frames[k]?.trend === 'up').length
              const downs = FRAMES.filter(([k]) => frames[k]?.trend === 'down').length
              const closedAt = st?.period_start != null ? st.period_start + (FRAME_S[st.timeframe ?? ''] ?? 0) : null
              return (
                <tr key={sym}>
                  <td style={{ padding: '8px 6px', borderTop: '1px solid var(--line)', whiteSpace: 'nowrap' }}>
                    <div style={{ fontWeight: 700 }}>{SYMBOL_AR[sym] ?? sym}</div>
                    <div className="dim num" style={{ fontSize: 11 }}>آخر تحديث {turkey(closedAt)}</div>
                  </td>
                  {FRAMES.map(([k]) => <Cell key={k} f={frames[k]} />)}
                  <td className="num" style={{ textAlign: 'center', borderTop: '1px solid var(--line)', fontWeight: 700 }}>
                    {st ? <span><span style={{ color: 'var(--green)' }}>{ups}</span> · <span style={{ color: 'var(--red)' }}>{downs}</span></span> : '—'}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}
