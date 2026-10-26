// ميزانيّة الأصول — ٢٠٢٦-١٠-٠٥ (ختم المالك «NQ وأبنيها»).
//
// حكمه قبلها بدقائق: «ما في شي بقول أصول إذا مجمّدة أو كم باقي من ميزانيّتها،
// إنت عم تشوف وأنا لا». وكان محقًّا مقيسًا: البتكوين والناسداك مجمّدان والذهب
// نفدت ميزانيّته، وبوّابة الأوامر ردّت ٨٨٨ أمرًا من ٨٩٤ لهذا السبب وحده — ولا
// شاشة تقوله. أقرب ما وُجد بطاقةٌ مدفونة أسفل «التنفيذ» تقول «مجمَّدة» بلا سبب
// ولا رقم، وتكتب الحالة الطبيعيّة بالإنكليزيّة.
//
// المصدر حدثان يصلان اللوحة أصلًا ويُعادان لكلّ شاشة تُفتح متأخّرة (اسماهما
// ينتهيان بـ`.state`):
//   risk.asset_ledger.state  ← 518 — الميزانيّة والخسارة و`u` والمتبقّي
//                              (`518/atom.py:464-483` · `ledger_support.py:202-220`)
//   asset.portfolio.state    ← 519 — حالة الأصل وإيقاف المالك (`519/atom.py:273-328`)
//
// ⛔ والحكم «ممنوع الفتح» لا يُخترع هنا: هو مرآة `asset_state_gate` في 552
// (`order_gates.py:112-137`) حرفًا — الحالة FROZEN/PAUSED أو إيقاف المالك، أو
// `breached` أو `u ≥ 1`. فما تقوله البطاقة هو ما تفعله البوّابة. والعتبتان
// 0.95 و1 من 518 نفسه (`ledger_support.py:220`)، لا أرقام جديدة.
import { useMemo } from 'react'
import { useStore } from '../core/store'

interface LedgerRow {
  account_id?: string; broker?: string; symbol?: string
  risk_budget?: number | null; budgeted?: boolean
  realized_drawdown?: number | null; realized_costs?: number | null
  effective_exposure?: number | null; loss_exposure?: number | null
  u?: number | null; remaining_risk?: number | null
  warning?: boolean; breached?: boolean; open_legs?: number | null
}
interface LedgerState { ledgers?: LedgerRow[] }
interface PortfolioRow {
  account_id?: string; broker?: string; symbol?: string
  state?: string; paused?: boolean; u?: number | null
  warning?: boolean; breached?: boolean
}
interface PortfolioState { portfolios?: PortfolioRow[]; halted_accounts?: string[] }

export type AssetTone = 'green' | 'amber' | 'red' | 'grey'

export interface AssetBudgetRow {
  key: string
  account: string
  symbol: string
  name: string
  budget: number | null
  lossRealized: number | null
  lossOpen: number | null
  costs: number | null
  used: number | null
  remaining: number | null
  /** الميزانيّة التي تحت `u` منها 0.95 — دونها يبقى الأصل مجمّدًا بعد رفعها. */
  needBudget: number | null
  paused: boolean
  blocked: boolean
  verdict: string
  tone: AssetTone
  why: string
}

// أسماء الأصول بالعربيّة. والرمز يبقى تحت الاسم لأنّ باقي اللوحة تكتبه به.
export const ASSET_AR: Record<string, string> = {
  BTCUSD: 'البتكوين', USTEC: 'الناسداك', XAUUSD: 'الذهب',
  US30: 'داو جونز', US500: 'إس آند بي 500',
  EURUSD: 'اليورو', GBPUSD: 'الإسترليني', AUDUSD: 'الأسترالي', DXY_U6: 'مؤشّر الدولار',
}
export const assetAr = (symbol: string) => ASSET_AR[symbol] ?? symbol

const num = (v: unknown): number | null =>
  typeof v === 'number' && Number.isFinite(v) ? v : null
export const usd = (n: number | null | undefined) =>
  n == null ? '—' : `$${n.toLocaleString('ar-EG-u-nu-latn', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`

// مرآة 552: `_FROZEN_STATES` و`_BUDGET_SPENT_U` (`order_gates.py:97-99`).
const FROZEN_STATES = new Set(['FROZEN', 'PAUSED'])
const SPENT_U = 1.0
// عتبة التحذير والخروج من التجميد في 518/519 (`ledger_support.py:220` · `519/atom.py:41,229`).
const WARN_U = 0.95

// الممنوع أوّلًا، ثمّ القريب من النفاد، ثمّ المسموح، وما بلا ميزانيّة أو حالة آخرًا.
const RANK: Record<AssetTone, number> = { red: 0, amber: 1, green: 2, grey: 3 }

/** صفوف الأصول مدموجةً من الدفتر والمحفظة — الممنوع أوّلًا، ثمّ الأكثر استهلاكًا. */
export function useAssetBudgets() {
  const ledger = useStore((s) => s.streams['risk.asset_ledger.state']) as LedgerState | undefined
  const portfolio = useStore((s) => s.streams['asset.portfolio.state']) as PortfolioState | undefined
  return useMemo(() => {
    const ports = new Map<string, PortfolioRow>()
    for (const p of portfolio?.portfolios ?? []) {
      if (p?.account_id && p?.symbol) ports.set(`${p.account_id}::${p.symbol}`, p)
    }
    const halted = new Set((portfolio?.halted_accounts ?? []).map(String))
    const rows: AssetBudgetRow[] = []
    for (const l of ledger?.ledgers ?? []) {
      if (!l?.account_id || !l?.symbol) continue
      const key = `${l.account_id}::${l.symbol}`
      const p = ports.get(key)
      const budget = num(l.risk_budget)
      const lossRealized = num(l.realized_drawdown)
      const lossOpen = num(l.effective_exposure) ?? num(l.loss_exposure)
      const used = num(p?.u) ?? num(l.u)
      const remaining = num(l.remaining_risk)
      const worst = Math.max(lossRealized ?? 0, lossOpen ?? 0)
      const needBudget = worst > 0 ? Math.ceil((worst / WARN_U) * 100) / 100 : null
      const paused = p?.paused === true
      const state = String(p?.state ?? '')
      const spent = p?.breached === true || l.breached === true || (used ?? 0) >= SPENT_U
      const near = !spent && (p?.warning === true || l.warning === true || (used ?? 0) >= WARN_U)
      const name = assetAr(l.symbol)
      let verdict: string; let tone: AssetTone; let why: string
      if (!p) {
        verdict = 'ما وصلت حالته'; tone = 'grey'
        why = 'ما وصلت حالة هالأصل لهالشاشة — وبوّابة الأوامر بترفض فتح أيّ أصل ما وصلتها حالته.'
      } else if (halted.has(String(l.account_id))) {
        verdict = 'الحساب موقوف'; tone = 'red'
        why = 'الحساب كلّه موقوف (إيقاف طارئ أو حارس) — فما في فتح على ولا أصل فيه.'
      } else if (paused) {
        verdict = 'موقوف بأمرك'; tone = 'red'
        why = 'أوقفته إنت بزرّ «إيقاف مؤقّت» أو «جمّد الزيادات» — ما بيرجع إلا بزرّ «متابعة».'
      } else if (spent) {
        verdict = 'ممنوع الفتح — نفدت ميزانيّته'; tone = 'red'
        why = `خسر ${usd(worst)} من ميزانيّة ${usd(budget)}. بيرجع مسموح إذا صفّرت دفتر خسارته، `
          + `أو رفعت ميزانيّته لأكثر من ${usd(needBudget)}.`
      } else if (FROZEN_STATES.has(state)) {
        // 519 لا يفكّ التجميد ما دامت الخسارة فوق عتبة التحذير (`519/atom.py:223-231`):
        // رفعُ الميزانيّة إلى ما فوق الخسارة بقليل لا يكفي.
        verdict = 'ممنوع الفتح — مجمّد'; tone = 'red'
        why = `خسارته ${usd(worst)} بعدها قريبة من ميزانيّته ${usd(budget)}، والتجميد ما بينفكّ إلا لمّا تنزل `
          + `تحت 95% منها. بيرجع إذا صفّرت دفتره أو رفعت ميزانيّته لأكثر من ${usd(needBudget)}.`
      } else if (near) {
        verdict = 'قارب النفاد'; tone = 'amber'
        why = `باقي ${usd(remaining)} — إذا وصلت الخسارة ${usd(budget)} بيتجمّد ويمنع الفتح.`
      } else if (budget == null || budget <= 0) {
        verdict = 'بلا ميزانيّة'; tone = 'grey'
        why = 'ما إله ميزانيّة بدفتر الخسارة.'
      } else {
        verdict = 'مسموح'; tone = 'green'
        why = `باقي ${usd(remaining)} من ميزانيّة ${usd(budget)}.`
      }
      rows.push({
        key, account: String(l.account_id), symbol: l.symbol, name, budget,
        lossRealized, lossOpen, costs: num(l.realized_costs), used, remaining, needBudget,
        paused, blocked: tone === 'red', verdict, tone, why,
      })
    }
    rows.sort((a, b) => RANK[a.tone] - RANK[b.tone] || (b.used ?? 0) - (a.used ?? 0)
      || a.symbol.localeCompare(b.symbol))
    const blocked = rows.filter((r) => r.blocked)
    const open = rows.filter((r) => r.tone === 'green' || r.tone === 'amber')
    const accounts = new Set(rows.map((r) => r.account))
    return { rows, blocked, open, multiAccount: accounts.size > 1, received: ledger != null }
  }, [ledger, portfolio])
}

function UsageBar({ used, tone }: { used: number | null; tone: AssetTone }) {
  const pct = used == null ? 0 : Math.max(0, Math.min(1, used)) * 100
  return (
    <div style={{ height: 7, borderRadius: 4, background: 'var(--glassb)', overflow: 'hidden', minWidth: 90 }}>
      <div style={{ width: `${pct}%`, height: '100%', background: `var(--${tone === 'grey' ? 'dim' : tone})` }} />
    </div>
  )
}

export interface AssetActions {
  busy: boolean
  reset: (row: AssetBudgetRow) => void
  budget: (row: AssetBudgetRow) => void
  resume: (row: AssetBudgetRow) => void
}

/** البطاقة كاملة: جدول بسطر لكلّ أصل، وأزرار كلّ أصل بجانبه حين تُمرَّر `actions`. */
export function AssetBudgetsCard({ actions, onGo }: { actions?: AssetActions; onGo?: (id: string) => void }) {
  const { rows, blocked, multiAccount, received } = useAssetBudgets()
  const th = { padding: '5px 8px', textAlign: 'start' as const, fontWeight: 500 }
  const td = { padding: '7px 8px', verticalAlign: 'top' as const }
  return (
    <div className="scard" style={{ borderColor: blocked.length ? '#5a2020' : undefined }}>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, flexWrap: 'wrap' }}>
        <div className="st" style={{ fontWeight: 700, fontSize: 15 }}>💼 ميزانيّة الأصول</div>
        {blocked.length ? (
          <b style={{ color: 'var(--red)', fontSize: 13.5 }}>
            ممنوع الفتح على {blocked.length === 1 ? 'أصل واحد' : blocked.length === 2 ? 'أصلين' : `${blocked.length} أصول`}:
            {' '}{blocked.map((r) => r.name).join(' · ')}
          </b>
        ) : rows.length ? (
          <span style={{ color: 'var(--green)', fontSize: 13.5 }}>كلّ الأصول مسموحة</span>
        ) : null}
        {onGo && blocked.length ? (
          <button className="btn" style={{ marginInlineStart: 'auto' }} onClick={() => onGo('control')}>
            روح لهناك
          </button>
        ) : null}
      </div>
      <div className="ss dim" style={{ marginTop: 4, lineHeight: 1.8 }}>
        لكلّ أصل ميزانيّة خسارة. لمّا تخلص، بوّابة الأوامر بتمنع فتح صفقة جديدة عليه — وما بتمسّ
        إدارة صفقة مفتوحة ولا إغلاقها. الخسارة هون محقّقة قبل العمولة من آخر تصفير لدفتره.
      </div>
      {!received ? (
        <div className="ss dim" style={{ marginTop: 8 }}>ما وصل دفتر الخسارة لهالشاشة بعد — اكبس «🔄 تحديث» فوق.</div>
      ) : rows.length === 0 ? (
        <div className="ss dim" style={{ marginTop: 8 }}>دفتر الخسارة وصل وما فيه ولا أصل.</div>
      ) : (
        <div style={{ overflowX: 'auto', marginTop: 8 }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13.5 }}>
            <thead><tr className="dim">
              <th style={th}>الأصل</th>
              <th style={th}>الحالة</th>
              <th style={th}>الخسارة</th>
              <th style={th}>الميزانيّة</th>
              <th style={th}>الباقي</th>
              <th style={{ ...th, minWidth: 100 }}>المصروف منها</th>
              {actions ? <th style={th}></th> : null}
            </tr></thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.key} style={{ borderTop: '1px solid var(--glassb)' }}>
                  <td style={td}>
                    <b>{r.name}</b>
                    <div className="dim" style={{ fontSize: 11 }}>{r.symbol}{multiAccount ? ` · ${r.account}` : ''}</div>
                  </td>
                  <td style={{ ...td, maxWidth: 320 }}>
                    <span className={`pill ${r.tone}`}>{r.verdict}</span>
                    <div className="ss dim" style={{ marginTop: 3, lineHeight: 1.7 }}>{r.why}</div>
                  </td>
                  <td className="num" style={td}
                    title={r.costs != null && r.costs > 0 ? `وفوقها عمولة وسواب: ${usd(r.costs)}` : undefined}>
                    <b style={{ color: (r.lossRealized ?? 0) > 0 ? 'var(--red)' : undefined }}>{usd(r.lossRealized)}</b>
                    {(r.lossOpen ?? 0) > 0 ? (
                      <div className="dim" style={{ fontSize: 11 }}>ومفتوحة الآن {usd(r.lossOpen)}</div>
                    ) : null}
                  </td>
                  <td className="num" style={td}>{usd(r.budget)}</td>
                  <td className="num" style={td}><b>{usd(r.remaining)}</b></td>
                  <td style={{ ...td, verticalAlign: 'middle' }}><UsageBar used={r.used} tone={r.tone} /></td>
                  {actions ? (
                    <td style={{ ...td, whiteSpace: 'nowrap' }}>
                      {r.paused ? (
                        <button className="btn" disabled={actions.busy} onClick={() => actions.resume(r)}>▶️ متابعة</button>
                      ) : null}{' '}
                      <button className="btn" disabled={actions.busy || !((r.lossRealized ?? 0) > 0)}
                        title={(r.lossRealized ?? 0) > 0 ? 'يمحو الخسارة المحقّقة لهالأصل ويبدأ دفتر جديد' : 'ما في خسارة محقّقة لتنصفّر'}
                        onClick={() => actions.reset(r)}>🧾 صفّر الدفتر</button>{' '}
                      <button className="btn" disabled={actions.busy} onClick={() => actions.budget(r)}>💵 الميزانيّة</button>
                    </td>
                  ) : null}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
