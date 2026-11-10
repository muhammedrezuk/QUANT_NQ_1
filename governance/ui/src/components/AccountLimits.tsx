// حدود الحساب — ٢٠٢٦-١٠-٢٣ (ختم المالك «NQ» على القوانين 7–10 من ورقة «خطوط حمراء»).
//
// قوله: «من لوحة التحكّم هنيك، مو تبني لوحة جديدة» — فهذه بطاقةٌ في رأس صفحة «التحكّم»، وسطر كلّ زوجٍ في «ميزانيّة الأصول».
// المصدر حدثٌ واحد يُعاد لكلّ شاشة تُفتح متأخّرة: `risk.account_limits.state` من حدود الحساب 509 — الإعدادات، ومخاطرة صفقة كلّ
// رمز، ولكلّ حساب أرقام ميتاتريدر (الرصيد والحقوق مع المفتوح) وخسارة اليوم والحدّان والمنعان. والحكم لا يُخترع هنا: هو ما
// تمنع به بوّابة الدخول 555 (`shared/account_limits.entry_block`).
import { useStore } from '../core/store'
import { assetAr, usd } from './AssetBudgets'

export interface LimitsSettings {
  initial_balance: number; pair_risk_pct: number; pair_daily_pct: number; daily_pct: number; total_pct: number
  pairs?: Record<string, { risk_pct?: number; daily_pct?: number }>
}
interface AccountView {
  known?: boolean; balance?: number | null; equity?: number | null; day_base?: number | null; day_loss?: number | null
  daily_limit?: number; floor?: number; daily_blocked?: boolean; total_blocked?: boolean; blocked_pairs?: string[]
  pair_loss?: Record<string, number>; pair_limit?: Record<string, number>
  // ٢٦/١٠ (فحص المشروع، ختم «nq اصلح»): 509 صارت تقول لماذا لا تعرف أرقام الحساب، وكم عمرها.
  why?: 'TRUTH_STALE' | 'TRUTH_MISSING' | string; truth_age_s?: number | null
  // ٢٦/١٠ (جواب المالك «NQ»: «تراجع يومي 5 % انا بسجل 4 الكم و1 الي»): الحدود على المنظومة وحدها — رصيدها وحقوقها.
  system_balance?: number | null; system_equity?: number | null
}
export interface LimitsState {
  settings?: LimitsSettings; trade_risk?: Record<string, number>
  accounts?: Record<string, AccountView>; applied?: { result?: string; reason?: string }
}

export const useAccountLimits = () =>
  useStore((s) => s.streams['risk.account_limits.state']) as LimitsState | undefined

/** (مخاطرة الصفقة ٪ · حدّ الزوج اليوميّ ٪) لهذا الزوج — رقمه إن كتبه المالك، وإلّا رقم كلّ الأزواج. */
export function pairPcts(state: LimitsState | undefined, symbol: string): [number | null, number | null] {
  const s = state?.settings
  if (!s) return [null, null]
  const row = s.pairs?.[symbol.toUpperCase()] ?? {}
  return [row.risk_pct ?? s.pair_risk_pct, row.daily_pct ?? s.pair_daily_pct]
}

const pct = (n: number | null | undefined) => (n == null ? '—' : `${n}٪`)

export interface LimitsActions {
  busy: boolean
  edit: (settings: LimitsSettings) => void
  release: (account: string) => void
}

const APPLIED_AR: Record<string, string> = { APPLIED: 'طُبّقت أرقامك', RELEASED: 'أُعيد التداول بيدك', REFUSED: 'رُفض آخر تعديل' }

export function AccountLimitsCard({ actions }: { actions?: LimitsActions }) {
  const state = useAccountLimits()
  const s = state?.settings
  const accounts = Object.entries(state?.accounts ?? {})
  const stopped = accounts.some(([, v]) => v.total_blocked || v.daily_blocked)
  const initial = s?.initial_balance ?? null
  const money = (p: number | undefined) => (initial == null || p == null ? null : (initial * p) / 100)
  return (
    <div className="scard" style={{ borderColor: stopped ? '#5a2020' : undefined }}>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, flexWrap: 'wrap' }}>
        <div className="st" style={{ fontWeight: 700, fontSize: 15 }}>🛡️ حدود الحساب</div>
        {actions && s ? (
          <button className="btn" style={{ marginInlineStart: 'auto' }} disabled={actions.busy}
            onClick={() => actions.edit(s)}>✏️ عدّل الأرقام</button>
        ) : null}
      </div>
      {!s ? (
        <div className="ss dim" style={{ marginTop: 8 }}>
          ما وصلت حالة حدود الحساب لهالشاشة بعد — وبوّابة الدخول بترفض كلّ دخول لحتّى توصل.
        </div>
      ) : (
        <>
          <div className="ss" style={{ marginTop: 6, lineHeight: 2 }}>
            الرصيد الابتدائيّ <b className="num">{usd(initial)}</b>
            {' · '}الحدّ اليوميّ الشامل <b>{pct(s.daily_pct)}</b> ({usd(money(s.daily_pct))})
            {' · '}التراجع الكلّيّ <b>{pct(s.total_pct)}</b> (يقف التداول عند {usd(initial == null ? null : initial - (money(s.total_pct) ?? 0))})
            {' · '}مخاطرة الصفقة لكلّ زوج <b>{pct(s.pair_risk_pct)}</b> ({usd(money(s.pair_risk_pct))})
            {' · '}حدّ كلّ زوج اليوميّ <b>{pct(s.pair_daily_pct)}</b> ({usd(money(s.pair_daily_pct))})
          </div>
          <div className="ss dim" style={{ lineHeight: 1.8 }}>
            كلّ النسب من الرصيد الابتدائيّ اللي بتكتبه بإيدك — ثابتة، مو تراكميّة. والأرقام من ميتاتريدر: الرصيد والحقوق مع المفتوح، متل ما
            بتحسبها الجهة المموِّلة. خسارة اليوم من الأعلى بين رصيد إغلاق الأمس وحقوق بداية اليوم، واليوم بيبلّش 00:00 بساعتك.
            ونسب كلّ زوج وحده بسطره تحت في «ميزانيّة الأصول».
          </div>
          {state?.applied?.result ? (
            <div className="ss" style={{ marginTop: 4 }}>
              {APPLIED_AR[state.applied.result] ?? state.applied.result}
              {state.applied.reason ? ` — قيمة غير مقبولة (${state.applied.reason}) وبقيت الأرقام القديمة` : ''}
            </div>
          ) : null}
          {accounts.length === 0 ? (
            <div className="ss dim" style={{ marginTop: 8 }}>ما وصلت أرقام الحساب من ميتاتريدر بعد — لا دخول بلا معرفة.</div>
          ) : accounts.map(([account, v]) => {
            const tone = !v.known ? 'grey' : v.total_blocked || v.daily_blocked ? 'red' : (v.blocked_pairs ?? []).length ? 'amber' : 'green'
            const verdict = !v.known
              ? (v.why === 'TRUTH_STALE'
                ? `أرقام الحساب قديمة${v.truth_age_s != null ? ` — آخرها قبل ${Math.round(v.truth_age_s)} ثانية` : ''} — لا دخول`
                : v.why === 'TRUTH_MISSING' ? 'أرقام الحساب لم تصل من ميتاتريدر — لا دخول'
                  : 'أرقام الحساب غير معروفة — لا دخول')
              : v.total_blocked ? 'التداول واقف — بلغ التراجع الكلّيّ، وما بيرجع إلا بإيدك'
                : v.daily_blocked ? 'واقف حتّى 00:00 — بلغت خسارة المنظومة الحدّ اليوميّ، وانسكّر كلّ مفتوحها'
                  : (v.blocked_pairs ?? []).length ? `ممنوع لليوم: ${(v.blocked_pairs ?? []).map(assetAr).join(' · ')} — بلغ حدّه اليوميّ`
                    : 'ضمن الحدود'
            return (
              <div key={account} style={{ borderTop: '1px solid var(--glassb)', marginTop: 8, paddingTop: 8 }}>
                <div style={{ display: 'flex', gap: 10, alignItems: 'baseline', flexWrap: 'wrap' }}>
                  <span className={`pill ${tone}`}>{verdict}</span>
                  <span className="dim num" style={{ fontSize: 11 }}>{account}</span>
                  {actions && v.total_blocked ? (
                    <button className="btn" style={{ marginInlineStart: 'auto' }} disabled={actions.busy}
                      onClick={() => actions.release(account)}>🔓 أعِد التداول</button>
                  ) : null}
                </div>
                <div className="ss num" style={{ marginTop: 4, lineHeight: 2 }}>
                  رصيد الحساب {usd(v.balance)} · حقوقه مع المفتوح {usd(v.equity)}
                  {' · '}حقوق المنظومة <b>{usd(v.system_equity)}</b>
                  {' · '}خسارة المنظومة اليوم <b style={{ color: (v.day_loss ?? 0) > 0 ? 'var(--red)' : undefined }}>{usd(v.day_loss)}</b> من {usd(v.daily_limit)}
                  {' · '}حدّ التراجع الكلّيّ {usd(v.floor)}
                </div>
                <div className="ss dim" style={{ fontSize: 11 }}>
                  الحدود على المنظومة وحدها — صفقاتك اليدويّة خارجها، وحصّتك من حدّ الجهة اليوميّ بيدك.
                </div>
              </div>
            )
          })}
        </>
      )}
    </div>
  )
}
