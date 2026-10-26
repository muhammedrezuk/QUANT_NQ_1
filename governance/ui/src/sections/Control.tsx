// تحكّم — كل مفتاح في النظام في شاشة واحدة.
// حكم المالك 2026-08-16: «كل شي بنعمله زر، اعمله زر وحطّه فيها».
// وقاعدته الأقدم: حرّاس بلا مفاتيح = فشل · يد المالك قبل عينه.
// لا يوجد شراء ولا بيع مباشر هنا — كل أمر يمرّ من بوّابة 901 بتأكيد مزدوج.
import { useEffect, useState } from 'react'
import { useStore } from '../core/store'
import { arabicHealth } from '../core/arabic'
// ٢٠٢٦-١٠-٠٢ (ختم المالك «صلح كامل nq»): الأزرار الثلاثة للإيقاف كانت ترسل `{}`
// فيرميه 516 ولا يقف شيء. الحمولة الآن نطاق النظام كلّه، من مكانٍ واحد.
import { HALT_PAYLOAD, stopAtom, CRITICAL_ATOMS } from '../core/commands'
import { readGate } from '../core/gate'
import { AssetBudgetsCard, useAssetBudgets, usd, type AssetBudgetRow } from '../components/AssetBudgets'
import { AccountLimitsCard, pairPcts, useAccountLimits, type LimitsActions, type LimitsSettings } from '../components/AccountLimits'

type Danger = 'halt' | 'kill_switch_reset' | 'activate_asset' | 'deactivate_asset'
  | 'asset_control' | 'execution_gate' | 'adaptation_switch' | 'account_limits'

// ٢٠٢٦-١٠-٠٥ (ختم المالك «NQ وأبنيها»): `note` جملةٌ عربيّة فوق نصّ الخادم في نافذة التأكيد —
// نصّ الخادم يكتب الأمر برمزه (`RESET_LEDGER`)، والمالك يوافق على ما يقرؤه.
async function send(action: Danger, payload: Record<string, unknown>, note?: string):
  Promise<{ ok: boolean; message?: string; error?: string }> {
  const first = await fetch('/gov/command', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ action, payload }),
  })
  const one = await first.json() as { token?: string; summary?: string; ttl_s?: number; error?: string }
  if (!first.ok || !one.token) return { ok: false, error: one.error ?? 'تعذّر طلب التأكيد' }
  if (!window.confirm(`${note ? `${note}\n\n` : ''}⚠️ ${one.summary ?? 'أمر خطر'}؟\nالتأكيد صالح ${one.ttl_s ?? 60} ثانية`))
    return { ok: false, error: 'أُلغي' }
  const second = await fetch('/gov/command', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ action, confirm: one.token, payload }),
  })
  const two = await second.json() as { message?: string; error?: string }
  return second.ok ? { ok: true, message: two.message } : { ok: false, error: two.error ?? 'رفضت البوابة الأمر' }
}

// الذرّات التي يُسمح بإيقافها وتشغيلها من هنا — سلسلة التنفيذ والإدارة وحدها.
// لا نعرض 212 زرًّا: إيقاف ذرّة تحليل لا يوقف تداولًا، وإيقاف ذرّة نواة يقتل النظام.
// ٢٠٢٦-١٠-٠٨ (ختم المالك «NQ» — فكّ الأقسام عن القرار): أزرار 451 · 453 · 458 · 466 · 581 أُزيلت — ذرّاتها
// أُرشفت، فكانت أزرارًا ميّتة («متوقّف» أبدًا). القرار الآن من البطاقة 414، وطلب الدخول من 555.
const ATOMS: [number, string, string][] = [
  [414, 'بطاقة استمرار الاتّجاه', 'قرار'], [467, 'إرسال القرار', 'قرار'],
  [555, 'طالب أمر الدخول', 'قرار'], [468, 'التحكّم بالأصول', 'قرار'],
  [516, 'قاطع الأمان', 'مخاطر'], [518, 'دفتر مخاطر الأصل', 'مخاطر'],
  [513, 'تحجيم المركز', 'مخاطر'], [525, 'سعر الوقف الصلب', 'مخاطر'],
  [512, 'الوقف الهيكليّ', 'مخاطر'], [506, 'حدود الجلسة', 'مخاطر'],
  // ٢٠٢٦-٠٩-١٨: زرّا ٥٧٦ «المحرّك الدائم» و٥٧٨ «منفّذ التحوّط» حُذفا — أُرشفت
  // الذرّتان بأمر المالك (`25b0cbb`)، فكان الزرّان يطلبان تشغيل ما لا وجود له،
  // ومصباحاهما أحمر أبدًا. طلبُ الأمر صار من ٥٥٥ و٥٨١، والأصلُ من ٤٦٨.
  [523, 'محرّك العيار', 'وضع'],
  [583, 'لقطة التنفيذ', 'وضع'],
  [527, 'بوّابة الرموز', 'تنفيذ'],
  [526, 'حارس الهامش', 'تنفيذ'], [525, 'شرعيّة الستوب', 'تنفيذ'],
  [551, 'باني الأمر', 'تنفيذ'], [552, 'بوّابة الأوامر', 'تنفيذ'],
  [563, 'تأكيد التنفيذ', 'تنفيذ'], [601, 'كاتب الجسر', 'تنفيذ'],
  [570, 'منسّق الإدارة', 'إدارة'], [572, 'التعادل', 'إدارة'],
  [574, 'الإغلاق الجزئيّ', 'إدارة'],   // ٢٣/١٠: 573 التتبّع نُقلت إلى الأرشيف بأمر المالك
  [575, 'مرسل الإدارة', 'إدارة'], [577, 'صيانة الستوب', 'إدارة'],
  [579, 'منفّذ التخريج', 'إدارة'], [580, 'منفّذ الترجيح', 'إدارة'],
  [609, 'مزامنة المراكز', 'جسر'], [611, 'قارئ الصفقات', 'جسر'],
  [618, 'جسر ميتاتريدر 5', 'جسر'], [619, 'حالة الحساب', 'جسر'],
  [622, 'تغذية سي‑تريدر', 'تحليل'],
]

const GROUPS = ['تحليل', 'قرار', 'مخاطر', 'وضع', 'تنفيذ', 'إدارة', 'جسر']

// بند 18 (دفتر 97): كل مجموعة تُشرح بجملة واحدة — شو مسؤوليّتها بالضبط
const GROUP_DESC: Record<string, string> = {
  'تحليل': 'مصدر أسعار التحليل من سي‑تريدر. بيانات فقط — لا يفتح صفقة ولا يكتب للمنصّة.',
  'قرار': 'البطاقة تقرأ الحقائق الخام وتقرّر وحدها بدخولها ووقفها وهدفها؛ والإرسال وطالب الدخول ينقلان قرارها إلى الحرّاس.',
  'مخاطر': 'تحرس رأس المال: قاطع الأمان، حدود الخسارة، حجم اللوت، وأسعار الوقف.',
  'وضع': 'تحسب المركز الدائم المستهدَف لكل أصل والفرق بينه وبين الواقع.',
  'تنفيذ': 'تحوّل القرار الموافَق لأمر حقيقي وتفحصه وتبعثه للمنصّة عبر البوّابة.',
  'إدارة': 'تعدّل الصفقات المفتوحة: تعادل، تتبّع وقف، وجني ربح جزئي — لا تفتح صفقة.',
  'جسر': 'الوصل مع منصّة ميتاتريدر 5: أسعار، حساب، مراكز، وكتابة الأوامر.',
}

type AtomRow = { id: number; state?: string; version?: string; health?: { state?: string; message?: string } }
// ٢٠٢٦-١٠-٢٦ (فحص المشروع، ختم المالك «nq اصلح»): كانت الحال ثلاثًا، فالغائب يُكتب «متوقّف» — والمقيس 15:15: «مسار التداول:
// متوقّف» على ثلاثة أزرار وبوّابة الأوامر أنهت ثلاثة أوامر في اليوم نفسه. صار الغائب حالًا رابعة: «غير مقروء».
type TradingStatus = 'stopped' | 'waiting' | 'open' | 'unknown'

// مؤشّر حيّ ملاصق لكل زر: اللون يصف حالة المسار الذي يتحكّم به الزر الآن.
function TradingLed({ status, text }: { status: TradingStatus; text: string }) {
  const color = status === 'open' ? '#2ecc71' : status === 'waiting' ? '#f1c40f' : status === 'unknown' ? '#8a8f98' : '#e74c3c'
  const label = status === 'open' ? 'مفتوح' : status === 'waiting' ? 'مفتوح — ينتظر' : status === 'unknown' ? 'غير مقروء' : 'متوقّف'
  return (
    <span title={text} style={{ display: 'inline-flex', alignItems: 'center', gap: 5, marginInlineEnd: 7, fontSize: 11.5, color, whiteSpace: 'nowrap' }}>
      <span aria-label={label} style={{ width: 9, height: 9, borderRadius: '50%', background: color, boxShadow: `0 0 6px ${color}`, display: 'inline-block' }} />
      {text}
    </span>
  )
}

export default function Control() {
  const term = useStore((s) => s.streams['platform.terminal_state']) as { account_id?: string } | undefined
  const acct = useStore((s) => s.streams['platform.account.state']) as { account_id?: string } | undefined
  // حالة البوّابة الحقيقيّة من حدث 552 نفسه (execution.gate.state) — لا من رسالة
  // الصحّة: startsWith('LIVE') كان النمط الشبح المثبَت خطؤه بورقة 90-31.
  const gate = useStore((s) => s.gate)
  // ٢٠٢٦-١٠-٢٦: الحدث وحده كان المصدر، وهو يُنشر عند الإقلاع والتغيّر فقط. القراءة المشتركة مع «شو صاير» والرئيسيّة
  // وغرفة النظام: الحدث أوّلًا، ثمّ رسالة صحّة 552 نفسها، وإلّا «غير مقروء» (`core/gate.ts`).
  const a552 = useStore((s) => s.atoms[552])
  const gateRead = readGate(gate, a552)
  const risk = useStore((s) => s.risk)
  const [account, setAccount] = useState('')
  const [symbol, setSymbol] = useState('BTCUSD')
  const [budget, setBudget] = useState('100')
  const [dial, setDial] = useState('50')
  const [message, setMessage] = useState('')
  const [busy, setBusy] = useState(false)
  const [atoms, setAtoms] = useState<Record<number, AtomRow>>({})

  useEffect(() => {
    const found = term?.account_id || acct?.account_id || ''
    if (found && !account) setAccount(String(found))
  }, [term?.account_id, acct?.account_id, account])

  // حالة الذرّات حيّة — الزرّ يجب أن يعرف ما يوقفه قبل أن يوقفه.
  useEffect(() => {
    let alive = true
    const pull = async () => {
      try {
        const body = await (await fetch('/gov/atoms')).json() as { atoms?: AtomRow[] } | AtomRow[]
        if (!alive) return
        // الحوكمة ترجع {connected, atoms}، مع دعم القائمة القديمة فقط للتوافق.
        const rows = Array.isArray(body) ? body : (body.atoms ?? [])
        const map: Record<number, AtomRow> = {}
        for (const r of rows) map[r.id] = r
        setAtoms(map)
      } catch { /* اللوحة لا تكذب: تعذّر القراءة يترك الحالة كما هي */ }
    }
    void pull()
    const t = setInterval(() => void pull(), 4000)
    return () => { alive = false; clearInterval(t) }
  }, [])

  const run = async (action: Danger, payload: Record<string, unknown>, ok: string, note?: string) => {
    setBusy(true); setMessage('')
    const result = await send(action, payload, note)
    setMessage(result.ok ? `🟢 ${result.message ?? ok}` : `🛑 ${result.error ?? 'فشل الأمر'}`)
    setBusy(false)
  }

  const asset = (command: string, extra: Record<string, unknown> = {}) =>
    run('asset_control',
      { account_id: account.trim(), symbol: symbol.trim().toUpperCase(), command, ...extra },
      'وصل الأمر إلى بوّابة 901')

  // ٢٠٢٦-١٠-٠٥ (ختم المالك «NQ وأبنيها»): أزرار كلّ أصل في بطاقة «ميزانيّة الأصول» —
  // الحساب والرمز من سطر الأصل نفسه، فلا يُكتب اسمٌ بيدٍ ولا يُضرب أصلٌ غير المقصود.
  // والأوامر نفسها التي تحت في بطاقة «الأصل»: `RESET_LEDGER` · `SET_BUDGET` · `RESUME`.
  const budgets = useAssetBudgets()
  const assetActions = {
    busy,
    reset: (r: AssetBudgetRow) => void run('asset_control',
      { account_id: r.account, symbol: r.symbol, command: 'RESET_LEDGER' },
      `صُفّر دفتر خسارة ${r.name}`,
      `🧾 تصفير دفتر خسارة ${r.name}: تنمحي خسارته المحقّقة ${usd(r.lossRealized)} `
        + `وبيبدأ دفتر جديد بنفس ميزانيّته ${usd(r.budget)}.`),
    budget: (r: AssetBudgetRow) => {
      const typed = window.prompt(
        `ميزانيّة ${r.name} الآن ${usd(r.budget)}، وخسارته ${usd(r.lossRealized)}.`
          + (r.blocked && r.needBudget != null ? `\nليرجع مسموح لازم تكون أكثر من ${usd(r.needBudget)}.` : '')
          + '\n\nاكتب الميزانيّة الجديدة بالدولار:',
        r.budget != null ? String(r.budget) : '')
      if (typed == null) return
      const value = Number(typed.replace(/[,\s$]/g, ''))
      if (!(value > 0)) { setMessage('🛑 الميزانيّة لازم تكون رقم أكبر من صفر'); return }
      const short = r.blocked && r.needBudget != null && value <= r.needBudget
      void run('asset_control',
        { account_id: r.account, symbol: r.symbol, command: 'SET_BUDGET', risk_budget: value },
        `انضبطت ميزانيّة ${r.name}`,
        `💵 ميزانيّة ${r.name}: من ${usd(r.budget)} إلى ${usd(value)}.`
          + (short ? `\n⚠️ هالرقم ما بيكفي — لازم أكثر من ${usd(r.needBudget)}، فبيضلّ ممنوع الفتح.` : ''))
    },
    resume: (r: AssetBudgetRow) => void run('asset_control',
      { account_id: r.account, symbol: r.symbol, command: 'RESUME' },
      `رجع ${r.name} للعمل`, `▶️ متابعة ${r.name} بعد إيقافك له.`),
    pairLimits: (r: AssetBudgetRow) => pairLimits(r),
  }

  // ٢٠٢٦-١٠-٢٣ (ختم المالك «NQ» على القوانين 7–10): حدود الحساب بيدك — الرصيد الابتدائيّ والحدّان ونسبتا كلّ زوج، وزرّ
  // إعادة التداول بعد التراجع الكلّيّ. كلّ أمرٍ يمرّ ببوّابة 901 بتأكيدٍ بخطوتين، و509 تردّ القيمة الخاطئة وتبقي القديمة.
  const askNumber = (label: string, current: number | null | undefined): number | null | undefined => {
    const typed = window.prompt(`${label}\nالآن: ${current ?? '—'}\n\nاكتب الرقم الجديد (أو اتركه كما هو):`, current != null ? String(current) : '')
    if (typed == null) return undefined
    const value = Number(typed.replace(/[,\s$٪%]/g, ''))
    return value > 0 ? value : null
  }
  const limitsActions: LimitsActions = {
    busy,
    edit: (s: LimitsSettings) => {
      const fields: [keyof LimitsSettings, string][] = [
        ['initial_balance', 'الرصيد الابتدائيّ بالدولار'], ['daily_pct', 'الحدّ اليوميّ الشامل ٪'],
        ['total_pct', 'التراجع الكلّيّ ٪'], ['pair_risk_pct', 'مخاطرة الصفقة لكلّ زوج ٪ (ما لم يُكتب لزوجٍ رقمه)'],
        ['pair_daily_pct', 'حدّ كلّ زوج اليوميّ ٪ (ما لم يُكتب لزوجٍ رقمه)']]
      const settings: Record<string, number> = {}
      for (const [key, label] of fields) {
        const value = askNumber(label, s[key] as number)
        if (value === undefined) return
        if (value === null) { setMessage(`🛑 ${label}: لازم رقم أكبر من صفر`); return }
        if (value !== s[key]) settings[key] = value
      }
      if (!Object.keys(settings).length) { setMessage('ما تغيّر رقم'); return }
      void run('account_limits', { command: 'SET', settings }, 'وصلت أرقامك إلى حدود الحساب')
    },
    release: (account: string) => void run('account_limits', { command: 'RELEASE_TOTAL', account_id: account },
      'أُعيد التداول', '🔓 إعادة التداول بعد التراجع الكلّيّ. إن بقيت الحقوق تحت الحدّ يقف التداول ثانيةً — عدّل الرصيد الابتدائيّ أوّلًا إن لزم.'),
  }
  const limitsState = useAccountLimits()
  const pairLimits = (r: AssetBudgetRow) => {
    const [risk, daily] = pairPcts(limitsState, r.symbol)
    const newRisk = askNumber(`مخاطرة الصفقة على ${r.name} ٪ من الرصيد الابتدائيّ`, risk)
    if (newRisk === undefined) return
    const newDaily = askNumber(`حدّ ${r.name} اليوميّ ٪ من الرصيد الابتدائيّ`, daily)
    if (newDaily === undefined) return
    if (newRisk === null || newDaily === null) { setMessage('🛑 النسبة لازم تكون رقم أكبر من صفر'); return }
    void run('account_limits', { command: 'SET', settings: { pairs: { [r.symbol]: { risk_pct: newRisk, daily_pct: newDaily } } } },
      `انضبطت نسبتا ${r.name}`)
  }

  // خانة «الميزانيّة بالدولار» كانت تبدأ بـ100 لكلّ أصل — وميزانيّة البتكوين 1,000 وغيره 740.
  // فضغطُ «اضبط الميزانيّة» بلا تعديل كان يخفض الميزانيّة عشرة أضعاف. تُملأ الآن بميزانيّة
  // الأصل المكتوب من دفتره، وتبقى 100 لأصلٍ لا دفتر له بعد (تفعيلٌ أوّل).
  const typedSymbol = symbol.trim().toUpperCase()
  const currentBudget = budgets.rows.find((r) => r.symbol === typedSymbol
    && (!account.trim() || r.account === account.trim()))?.budget ?? null
  useEffect(() => {
    if (currentBudget != null) setBudget(String(currentBudget))
  }, [typedSymbol, currentBudget])

  const atomPower = async (id: number, on: boolean) => {
    // ٢٠٢٦-١٠-٢٦ (فحص المشروع، ختم «nq اصلح»): الإيقاف كان بنافذة «موافق» واحدة لكلّ الثلاثين، ومنها قاطع الأمان وبوّابة
    // الأوامر وجسر ميتاتريدر. الحرجة صارت بالختم: ملخّصٌ يقول ما يسقط، ثمّ تأكيد — والخادم يرفض طريقها القديم.
    if (!on) {
      const name = ATOMS.find(([atomId]) => atomId === id)?.[1] ?? String(id)
      setBusy(true); setMessage('')
      const r = await stopAtom(id, name)
      setMessage(r.ok ? `🟢 الذرّة ${id} أُوقفت${r.message ? ` — ${r.message}` : ''}`
        : r.message === 'أُلغي' ? 'أُلغي — لم تُوقف' : `🛑 لم تُوقف الذرّة ${id}: ${r.message ?? ''}`)
      setBusy(false)
      return
    }
    if (!window.confirm(`تشغيل الذرّة ${id}؟`)) return
    setBusy(true); setMessage('')
    try {
      const r = await fetch(`/gov/atoms/${id}/start`, { method: 'POST' })
      setMessage(r.ok ? `🟢 الذرّة ${id} شُغّلت` : `🛑 فشل على الذرّة ${id}`)
    } catch (e) { setMessage(`🛑 ${String(e)}`) }
    setBusy(false)
  }

  // ——— بند 18 (دفتر 97): مسارات موجَّهة فوق الأزرار الخام، لا بدلًا عنها ———
  // كل خطوة خطرة تمرّ بتأكيدها المعتاد (يد المالك قبل عينه) — المسار يرتّب، ما يتجاوز.
  const startAtomStep = async (id: number, nm: string): Promise<string> => {
    if (!window.confirm(`تشغيل «${nm}» (${id})؟ — خطوة من المسار`)) return `تخطّيت «${nm}»`
    try {
      const r = await fetch(`/gov/atoms/${id}/start`, { method: 'POST' })
      return r.ok ? `▶️ «${nm}» اشتغلت` : `🛑 «${nm}»: فشل التشغيل`
    } catch (e) { return `🛑 «${nm}»: ${String(e)}` }
  }

  const pathOpenTrading = async () => {
    setBusy(true)
    const steps: string[] = []
    const push = (s: string) => { steps.push(s); setMessage(steps.join('  ·  ')) }
    const killActive = risk?.kill_switch_state === true || msgOf(516).includes('KILL_SWITCH_ACTIVE')
    if (killActive) {
      const r = await send('kill_switch_reset', {})
      push(r.ok ? '♻️ صُفّر قاطع الأمان' : `🛑 توقّف المسار عند القاطع: ${r.error ?? ''}`)
      if (!r.ok) { setBusy(false); return }
    } else push('قاطع الأمان سليم ✓')
    for (const [id, nm] of [[618, 'جسر ميتاتريدر 5'], [601, 'كاتب الجسر']] as [number, string][]) {
      if (atoms[id] && atoms[id].state !== 'running') push(await startAtomStep(id, nm))
      else push(`«${nm}» شغّال ✓`)
    }
    if (!(gateRead.known && gateRead.open)) {
      const r = await send('execution_gate', { gate: 'both', enabled: true })
      push(r.ok ? '🚪 فُتحت البوّابتان (552 + 575)' : `🛑 توقّف المسار عند البوّابة: ${r.error ?? ''}`)
      if (!r.ok) { setBusy(false); return }
    } else push('البوّابة مفتوحة ✓')
    const connectedAccount = term?.account_id || acct?.account_id
    if (!connectedAccount) {
      push('🔴 توقّف المسار: لا يوجد حساب تنفيذ مؤكّد خلف 601 — الكاتب وحده لا يختار حسابًا')
    } else if (assetAllowed === 0) {
      push('⚠️ باقي خطوة بإيدك: فعّل الأصل من بطاقة «الأصل» تحت — بدها ميزانيّة وما منخترعها عنّك')
    } else push(`تمّ — البوّابات مفتوحة للحساب المتصل ${connectedAccount}`)
    setBusy(false)
  }

  const pathStopAll = async () => {
    setBusy(true)
    const steps: string[] = []
    const push = (s: string) => { steps.push(s); setMessage(steps.join('  ·  ')) }
    const h = await send('halt', HALT_PAYLOAD)
    push(h.ok ? '🛑 أُعلن الإيقاف الطارئ' : `🛑 فشل الإيقاف الطارئ: ${h.error ?? ''}`)
    const g = await send('execution_gate', { gate: 'both', enabled: false })
    push(g.ok ? '🚪 أُقفلت البوّابتان (552 + 575)' : `⚠️ البوّابتان: ${g.error ?? ''}`)
    setBusy(false)
  }

  const pill = (id: number) => {
    const row = atoms[id]
    if (!row) return <span className="pill unk">—</span>
    if (row.state !== 'running') return <span className="pill dead">متوقّفة</span>
    const h = row.health?.state
    if (h === 'healthy') return <span className="pill ok">سليمة</span>
    if (h === 'degraded') return <span className="pill warn">تنتظر</span>
    return <span className="pill unk">—</span>
  }

  // ٢٠٢٦-١٠-٢٦: ذرّةٌ لم تصل حالها بعد «غير مقروء»، لا «متوقّف» — والمتوقّفة فعلًا تبقى متوقّفة.
  const atomStatus = (id: number): TradingStatus => {
    const row = atoms[id]
    if (!row) return 'unknown'
    if (row.state !== 'running') return 'stopped'
    if (row.health?.state === 'healthy') return 'open'
    return 'waiting'
  }
  const gateStatus = (): TradingStatus => {
    // ٢٠٢٦-٠٩-٠٩ (ختم NQ): `risk.halted` حقلٌ لا وجود له بأي حمولة — بديله
    // `halted` الذي ينشره ٥٥٢ نفسه بـ`execution.gate.state`.
    // ٢٠٢٦-١٠-٢٦: والقاطع يُقرأ من رسالة 516 أيضًا، كما في قائمة الموانع تحت — حدث المخاطر يُنشر عند الحدوث وحده.
    if (risk?.kill_switch_state === true || msgOf(516).includes('KILL_SWITCH_ACTIVE')) return 'stopped'
    if (!gateRead.known) return 'unknown'
    return gateRead.open ? 'open' : 'stopped'
  }
  const tradingStatus = (): TradingStatus => {
    // 601 كاتب الجسر لا ينشئ حسابًا ولا يختاره. لا نعلن المسار مفتوحًا
    // ما لم يصل account_id حيّ من المنصّة نفسها.
    const connectedAccount = term?.account_id || acct?.account_id
    const legs = [gateStatus(), atomStatus(601), atomStatus(618)]
    if (legs.includes('stopped')) return 'stopped'
    // ٢٠٢٦-١٠-٢٦: حسابٌ لم يصل أو حلقةٌ لم تُقرأ = «غير مقروء» — لا «متوقّف» يدفع إلى «افتح التداول» على منظومةٍ مفتوحة.
    if (!connectedAccount || legs.includes('unknown')) return 'unknown'
    // ٢٠٢٦-١٠-٠٨ (فكّ الأقسام عن القرار، ختم المالك «NQ»): 451/453/458/466 أُرشفت — المسار الحيّ 414 ⟵ 467 ⟵ 555.
    if ([414, 467, 555, 468, 516, 552, 575].some((id) => atomStatus(id) === 'waiting')) return 'waiting'
    return 'open'
  }
  const statusText = (status: TradingStatus, subject = 'مسار التداول') =>
    status === 'open' ? `${subject}: مفتوح` : status === 'waiting' ? `${subject}: مفتوح — ينتظر`
      : status === 'unknown' ? `${subject}: غير مقروء` : `${subject}: متوقّف`

  const needAsset = busy || !account.trim() || !symbol.trim()

  // 90-16: «شو مانع التداول الآن» بجملة واحدة بدل التفتيش.
  // كل سطر مقروء من صحّة الذرّة نفسها — لا استنتاج ولا ذاكرة في اللوحة.
  // القاعدة: ما لا نستطيع قراءته يُعرض «غير معروف»، لا «تمام».
  const msgOf = (id: number) => atoms[id]?.health?.message ?? ''
  const isRunning = (id: number) => atoms[id]?.state === 'running'

  // ٢٠٢٦-٠٩-١٨ — «الأصل مفعَّل؟» كان يُقرأ من `active=0` في رسالة ٥٧٦، وقد
  // أُرشفت (`25b0cbb`). فصار يُقرأ من بوّابة الأصول ٤٦٨ — وهي التي تفصل
  // التِكّة فعلًا، لا التي تعلن نيّة. شكل رسالتها مقروءٌ من ناشرها:
  // `allowed=N [أسماء] · <حساب>=N [أسماء] seen=N blocked=N`، أو
  // `EMPTY_WHITELIST_BLOCKS_ALL` حين لا أصل مسموح
  // (`atoms/قسم 450-499/468_التحكم_بالأصول/atom.py:196-230`).
  // والقائمة **لكل حساب** ترجَّح على العامّة لأنّها هي التي تحكم من يمرّ.
  // الغياب يبقى غيابًا: `null` لا صفر.
  const assetAllowed = ((): number | null => {
    const m = msgOf(468)
    if (!m) return null
    if (m.includes('EMPTY_WHITELIST_BLOCKS_ALL')) return 0
    const perAccount = Array.from(m.matchAll(/\b\d+=(\d+)\s*\[/g)).map((x) => Number(x[1]))
    if (perAccount.length) return Math.max(...perAccount)
    const g = /\ballowed=(\d+)\b/.exec(m)
    return g ? Number(g[1]) : null
  })()
  const blockers: [string, boolean | null, string][] = [
    ['قاطع الأمان مفتوح — كل الإرسال متوقّف',
      msgOf(516) ? msgOf(516).includes('KILL_SWITCH_ACTIVE') : null,
      'اضغط «صفّر قاطع الأمان» فوق'],
    ['بوّابة الأوامر مقفولة — الأمر يُرفض ولا يصل المنصّة',
      gateRead.known ? !gateRead.open : null,
      gateRead.guardHalt ? 'حارسٌ أوقف الحساب، لا عطل — «صفّر قاطع الأمان» فوق، وحالات الجلسة تُسحب وحدها حين يزول سببها'
        : 'اضغط «افتح بوّابة الأوامر»'],
    ['مرسل الإدارة موقوف — الصفقة المفتوحة بلا تعادل ولا تتبّع',
      msgOf(575) ? msgOf(575).includes('DISABLED') : null,
      'اضغط «شغّل مرسل الإدارة»'],
    ['ما في أصل مفعَّل — بوّابة الأصول بتفصل كل تِكّة قبل التحليل',
      assetAllowed == null ? null : assetAllowed === 0,
      'اضغط «فعّل الأصل» تحت — بدها حساب ورمز وميزانيّة'],
    ['جسر ميتاتريدر 5 لا يعمل — لا سعر ولا حساب',
      atoms[618] ? !isRunning(618) : null, 'شغّل الذرّة 618'],
    ['كاتب الجسر لا يعمل — الأمر لا يُكتب للمنصّة',
      atoms[601] ? !isRunning(601) : null, 'شغّل الذرّة 601'],
    ['قياس الانزلاق غير قابل للاستعمال',
      msgOf(563) ? msgOf(563).includes('NO_REQUESTED_PRICE') : null,
      'الوصل بين الطلب والتنفيذ انكسر — لا تُرقّع، ارجع للجذر'],
    // ٢٠٢٦-١٠-٠٥ (ختم المالك «NQ وأبنيها»): كانت هذه البطاقة تقول «🟢 لا شيء يمنع التداول»
    // وبوّابة الأوامر تردّ ٨٨٨ أمرًا من ٨٩٤ لأصولٍ نفدت ميزانيّاتها. المنع الكامل هنا مانع؛
    // والجزئيّ يُعلَن تحت بسطرٍ كهرمانيّ — باقي الأصول تتداول فعلًا.
    ['ولا أصل مسموح الفتح عليه — كلّها ممنوعة',
      budgets.rows.length ? budgets.blocked.length > 0 && budgets.open.length === 0 : null,
      'السبب لكلّ أصل وأزراره في بطاقة «ميزانيّة الأصول» تحت مباشرة'],
  ]
  const active = blockers.filter(([, on]) => on === true)
  const unknown = blockers.filter(([, on]) => on === null)

  return (
    <div>
      {/* ٢٠٢٦-٠٩-١٨ («صارت كم حال من تكرار»): بطاقتا الحساب كانتا تتكرّران على
          خمس صفحات، ورقماهما معروضان أصلًا في **ترويسة كل صفحة** (`AccountsBar`).
          بقيتا حيث الحساب هو الموضوع — «المحافظ» و«السوق والاتصال» — ورُفعتا من
          هنا ومن «التحليل» و«التنفيذ»: الترويسة تكفي فيها. لا معلومة فُقدت. */}
      <div className="scard" style={{
        marginTop: 14,
        borderColor: active.length ? '#5a2020' : unknown.length ? '#4a4420' : '#1e5a2e',
      }}>
        <div className="st" style={{ color: active.length ? '#ff8080' : unknown.length ? '#f1c40f' : '#2ecc71' }}>
          {active.length
            ? `🔴 التداول متوقّف — ${active.length} مانع`
            : unknown.length
              ? '🟡 لا مانع معروف — وبعض الحالات غير مقروءة'
              : '🟢 لا شيء يمنع التداول'}
        </div>
        {active.map(([why, , how]) => (
          <div key={why} style={{ borderRight: '3px solid #e74c3c', paddingRight: 12, margin: '10px 0' }}>
            <b>{why}</b><br /><span className="ss dim">{how}</span>
          </div>
        ))}
        {unknown.length ? (
          <div className="ss dim" style={{ marginTop: 8 }}>
            غير مقروء الآن: {unknown.map(([why]) => why.split('—')[0].trim()).join(' · ')}
            <br />اللوحة لا تقول «تمام» عن حالة لم تصلها.
          </div>
        ) : null}
        {!active.length && !unknown.length ? (
          <div className="ss dim">القاطع مغلق · البوّابتان مفتوحتان · الأصل مفعَّل · الجسر يعمل.
            وهذا لا يعني أنّ صفقةً ستُفتح — يعني أنّ لا شيء يمنعها.</div>
        ) : null}
        {budgets.blocked.length && budgets.open.length ? (
          <div style={{ borderRight: '3px solid #f1c40f', paddingRight: 12, margin: '10px 0' }}>
            <b>ممنوع الفتح على: {budgets.blocked.map((r) => r.name).join(' · ')}</b>
            <br /><span className="ss dim">والباقي مسموح. السبب لكلّ أصل وأزراره في «ميزانيّة الأصول» تحت مباشرة.</span>
          </div>
        ) : null}
      </div>
      <div style={{ marginTop: 14 }}>
        <AccountLimitsCard actions={limitsActions} />
      </div>
      <div style={{ marginTop: 14 }}>
        <AssetBudgetsCard actions={assetActions} />
      </div>
      {/* بند 18 (دفتر 97) — «الخريطة»: ثلاث مسارات جاهزة فوق الأزرار الخام.
          كل مسار يضغط تسلسل الأزرار الصحيح بترتيبه، وكل خطوة خطرة بتأكيدها. */}
      <div className="scard" style={{ marginTop: 14, borderColor: 'var(--accent)' }}>
        <div className="st" style={{ color: 'var(--ink)' }}>🗺️ مسارات جاهزة — بدل ما تدوّر بين المفاتيح</div>
        <div className="ss dim">المسار بينفّذ الخطوات الصحيحة بترتيبها الصحيح، ويسألك تأكيدًا عند كل خطوة خطرة. الأزرار الدقيقة كلّها باقية تحت لمن بدّه يمسك التفاصيل.</div>
        <div style={{ display: 'flex', gap: 10, marginTop: 10, flexWrap: 'wrap' }}>
          <button className="btn" disabled={busy} onClick={() => void pathOpenTrading()}
            title="قاطع الأمان ← ذرّتا الجسر ← البوّابتان — وبيقلّك إذا باقي خطوة بإيدك"><TradingLed status={tradingStatus()} text={statusText(tradingStatus())} />▶️ افتح التداول (خطوة خطوة)</button>
          <button className="btn" disabled={busy} onClick={() => void pathStopAll()}
            title="إيقاف طارئ + إقفال البوّابتين"><TradingLed status={tradingStatus()} text={statusText(tradingStatus())} />🛑 أوقف كل شيء</button>
          <button className="btn" disabled={busy} onClick={() => void run('halt', HALT_PAYLOAD, 'أُعلن الإيقاف الطارئ')}
            title="الإيقاف الطارئ وحده — بلا لمس البوّابات"><TradingLed status={tradingStatus()} text={statusText(tradingStatus())} />⛔ مسار الطوارئ فقط</button>
        </div>
      </div>

      <div className="scard" style={{ marginTop: 14, borderColor: '#5a2020' }}>
        <div className="st" style={{ color: '#ff8080' }}>🛑 الطوارئ</div>
        {/* ٢٠٢٦-٠٩-٠٦: كان مكتوبًا «والتصفير لا يُرفع تلقائيًّا أبدًا — بيدك
            وحدها». صار كذبًا بعد أمر المالك «لازم يصير أوتوماتيك»: خرقُ عدّ
            صفقات الجلسة يسحبه 506 من تلقاء نفسه حين يزول، و516 يفكّ المفتاح
            **إن طابق السبب** وحده. ما عداه يبقى بيد المالك. الورق يتبع الكود. */}
        <div className="ss dim">الإيقاف الطارئ يوقف كل إرسال فورًا ويعلو على كل زرّ آخر في هذه الشاشة.
          والتصفير بيدك وحدها — إلا مفتاحًا رفعه خرقُ عدّ صفقات الجلسة، فهذا
          يُسحب تلقائيًّا حين يزول سببه (تبدّل الجلسة أو دوران اليوم أو إقلاع
          بحدٍّ جديد)، وحدَّ الخسارة اليوميّة، فيُسحب وحده مع دوران اليوم (حكمك ١٨/٠٩).
          أمّا ما رُفع لمتتاليات أو بأمرك، فلا يفكّه إلا هذا الزرّ.</div>
        <div style={{ display: 'flex', gap: 10, marginTop: 10, flexWrap: 'wrap' }}>
          <button className="btn" disabled={busy}
            onClick={() => void run('halt', HALT_PAYLOAD, 'أُعلن الإيقاف الطارئ')}><TradingLed status={tradingStatus()} text={statusText(tradingStatus())} />🛑 إيقاف طارئ شامل</button>
          <button className="btn" disabled={busy}
            onClick={() => void run('kill_switch_reset', {}, 'صُفّر قاطع الأمان')}><TradingLed status={atomStatus(516)} text={statusText(atomStatus(516), 'قاطع الأمان')} />♻️ صفّر قاطع الأمان</button>
        </div>
      </div>

      {/* ٢٠٢٦-٠٩-٠٦ (جرد اللوحات بأمر المالك): المسار كامل من طرفيه —
          901 يترجم `adaptation_switch` إلى `adaptation.kill_switch.command`
          و860 مشترك فيه — ولا زرّ في اللوحة كلّها يرسله. حارس بلا مفتاح،
          وهو حكم المالك المسجَّل: «حرّاس بلا مفاتيح = فشل». العقد الذي
          يتحقّق منه 901: `action` إمّا ON أو OFF، لا شيء غيرهما. */}
      <div className="scard" style={{ marginTop: 14 }}>
        <div className="st" style={{ color: 'var(--ink)' }}>🧬 مفتاح التكيّف (860)</div>
        <div className="ss dim">التكيّف يعدّل النظام على الانحراف والتأخير. إيقافه يجمّد ذلك
          فيبقى النظام على معايرته الحالية — ولا يمسّ صفقة مفتوحة ولا يفتح صفقة.
          <br />كان بابًا باتّجاه واحد: يُوقَف ولا ناشر يعيده إلا إقلاع (ختم NQ ٢٠٢٦-٠٨-٢٥).</div>
        <div style={{ display: 'flex', gap: 10, marginTop: 10, flexWrap: 'wrap' }}>
          <button className="btn" disabled={busy}
            onClick={() => void run('adaptation_switch', { action: 'ON' }, 'أُعيد التكيّف')}><TradingLed status={atomStatus(860)} text={statusText(atomStatus(860), 'مفتاح التكيّف')} />▶️ أعِد التكيّف</button>
          <button className="btn" disabled={busy}
            onClick={() => void run('adaptation_switch', { action: 'OFF' }, 'أُوقف التكيّف')}><TradingLed status={atomStatus(860)} text={statusText(atomStatus(860), 'مفتاح التكيّف')} />⏹️ أوقف التكيّف</button>
        </div>
      </div>

      <div className="scard" style={{ marginTop: 14 }}>
        <div className="st" style={{ color: 'var(--ink)' }}>🚪 بوّابتا التنفيذ</div>
        <div className="ss dim"><b>بوّابة الأوامر (552)</b> تقرّر إن كان الأمر الصالح يصل المنصّة فعلًا ·
          <b> مرسل الإدارة (575)</b> يحمل التعديلات على صفقة مفتوحة ولا يفتح صفقة أبدًا.
          <br />فتح البوّابة لا يرفع إيقافًا طارئًا أمرت به.</div>
        <div style={{ display: 'flex', gap: 10, marginTop: 10, flexWrap: 'wrap' }}>
          <button className="btn" disabled={busy} onClick={() => void run('execution_gate', { gate: '552', enabled: true }, 'فُتحت بوّابة الأوامر')}><TradingLed status={gateStatus()} text={statusText(gateStatus(), 'بوّابة الأوامر')} />▶️ افتح بوّابة الأوامر</button>
          <button className="btn" disabled={busy} onClick={() => void run('execution_gate', { gate: '552', enabled: false }, 'أُوقفت بوّابة الأوامر')}><TradingLed status={gateStatus()} text={statusText(gateStatus(), 'بوّابة الأوامر')} />⏹️ أوقف بوّابة الأوامر</button>
          <button className="btn" disabled={busy} onClick={() => void run('execution_gate', { gate: '575', enabled: true }, 'شُغّل مرسل الإدارة')}><TradingLed status={atomStatus(575)} text={statusText(atomStatus(575), 'مرسل الإدارة')} />▶️ شغّل مرسل الإدارة</button>
          <button className="btn" disabled={busy} onClick={() => void run('execution_gate', { gate: '575', enabled: false }, 'أُوقف مرسل الإدارة')}><TradingLed status={atomStatus(575)} text={statusText(atomStatus(575), 'مرسل الإدارة')} />⏹️ أوقف مرسل الإدارة</button>
          <button className="btn" disabled={busy} onClick={() => void run('execution_gate', { gate: 'both', enabled: true }, 'فُتح الاثنان')}><TradingLed status={gateStatus()} text={statusText(gateStatus(), 'بوّابتا التنفيذ')} />▶️ افتح الاثنين</button>
          <button className="btn" disabled={busy} onClick={() => void run('execution_gate', { gate: 'both', enabled: false }, 'أُوقف الاثنان')}><TradingLed status={gateStatus()} text={statusText(gateStatus(), 'بوّابتا التنفيذ')} />🛑 أوقف الاثنين</button>
        </div>
      </div>

      <div className="scard" style={{ marginTop: 14 }}>
        <div className="st" style={{ color: 'var(--ink)' }}>🎯 الأصل</div>
        <div className="cards" style={{ marginTop: 10 }}>
          <label className="scard"><span className="ss">حساب التنفيذ (ميتاتريدر 5)</span>
            <input className="cfginput num" value={account} onChange={(e) => setAccount(e.target.value)} placeholder="يُقرأ تلقائيًا" /></label>
          <label className="scard"><span className="ss">الأصل</span>
            <input className="cfginput" value={symbol} onChange={(e) => setSymbol(e.target.value)} /></label>
          <label className="scard"><span className="ss">الميزانية بالدولار</span>
            <input className="cfginput num" value={budget} onChange={(e) => setBudget(e.target.value)} inputMode="decimal" /></label>
          <label className="scard"><span className="ss">العيار (0–100)</span>
            <input className="cfginput num" value={dial} onChange={(e) => setDial(e.target.value)} inputMode="decimal" /></label>
        </div>
        {/* ٢٠٢٦-١٠-٠٨ (فكّ الأقسام عن القرار، ختم المالك «NQ»): «أقصى مراكز للرمز» أُزيل — مستلمه حارس المراكز 463 أُرشف،
            فكان الأمر يصل بوّابة الأوامر ولا يسمعه أحد. «مركزٌ واحد للرمز» صار في البطاقة 414 وطالب الدخول 555. */}
        <div className="ss dim" style={{ marginTop: 6 }}>
          مركزٌ واحد للرمز: البطاقة لا تفتح وفي الرمز مركزٌ مفتوح، وطالب الدخول لا يضيف على مركزٍ قائم.
        </div>
        <div style={{ display: 'flex', gap: 10, marginTop: 10, flexWrap: 'wrap' }}>
          <button className="btn" disabled={needAsset || !(Number(budget) > 0)}
            onClick={() => void run('activate_asset', { account_id: account.trim(), symbol: symbol.trim().toUpperCase(), budget: Number(budget) }, 'وصل أمر التفعيل — يُضاف الأصل إلى القائمة المسموحة وتُوضع ميزانيّته')}><TradingLed status={atomStatus(468)} text={statusText(atomStatus(468), 'بوّابة الأصول')} />▶️ فعّل الأصل</button>
          <button className="btn" disabled={needAsset}
            onClick={() => void run('deactivate_asset', { account_id: account.trim(), symbol: symbol.trim().toUpperCase() }, 'أُلغي التفعيل')}><TradingLed status={atomStatus(468)} text={statusText(atomStatus(468), 'بوّابة الأصول')} />⏹️ ألغِ التفعيل</button>
          <button className="btn" disabled={needAsset} onClick={() => void asset('PAUSE')}><TradingLed status={atomStatus(468)} text={statusText(atomStatus(468), 'بوّابة الأصول')} />⏸️ إيقاف مؤقت</button>
          <button className="btn" disabled={needAsset} onClick={() => void asset('RESUME')}><TradingLed status={atomStatus(468)} text={statusText(atomStatus(468), 'بوّابة الأصول')} />▶️ متابعة</button>
          <button className="btn" disabled={needAsset} onClick={() => void asset('FREEZE')}><TradingLed status={atomStatus(468)} text={statusText(atomStatus(468), 'بوّابة الأصول')} />🧊 جمّد الزيادات</button>
          <button className="btn" disabled={needAsset} onClick={() => void asset('UNFREEZE')}><TradingLed status={atomStatus(468)} text={statusText(atomStatus(468), 'بوّابة الأصول')} />🔥 ارفع التجميد</button>
          <button className="btn" disabled={needAsset} onClick={() => void asset('FORCE_RECONCILE')}><TradingLed status={atomStatus(468)} text={statusText(atomStatus(468), 'بوّابة الأصول')} />🔄 مطابقة فوريّة</button>
          <button className="btn" disabled={needAsset || !(Number(dial) >= 0)} onClick={() => void asset('CALIBRATE', { dial: Number(dial) })}><TradingLed status={atomStatus(468)} text={statusText(atomStatus(468), 'بوّابة الأصول')} />🎚️ اضبط العيار</button>
          <button className="btn" disabled={needAsset || !(Number(budget) > 0)} onClick={() => void asset('SET_BUDGET', { risk_budget: Number(budget) })}><TradingLed status={atomStatus(468)} text={statusText(atomStatus(468), 'بوّابة الأصول')} />💵 اضبط الميزانية</button>
          {/* ٢٠٢٦-٠٩-٢٣ (ختم nq): أمرك ٢٠٢٦-٠٩-١٠ «صفّر الخسارة ورجّعه للعمل» — مستلِمه ٥١٨ */}
          <button className="btn" disabled={needAsset} onClick={() => void asset('RESET_LEDGER')}><TradingLed status={atomStatus(518)} text={statusText(atomStatus(518), 'دفتر مخاطر الأصل')} />🧾 صفّر دفتر الخسارة</button>
        </div>
      </div>

      {GROUPS.map((group) => (
        <div className="scard" style={{ marginTop: 14 }} key={group}>
          <div className="st" style={{ color: 'var(--ink)' }}>⚙️ ذرّات — {group}</div>
          {/* بند 18/3 — جملة واحدة تشرح مسؤوليّة المجموعة */}
          <div className="ss dim">{GROUP_DESC[group]}</div>
          <table style={{ width: '100%', borderCollapse: 'collapse', marginTop: 8 }}>
            <tbody>
              {ATOMS.filter(([, , g]) => g === group).map(([id, name]) => (
                <tr key={id} style={{ borderBottom: '1px solid var(--line)' }}>
                  <td style={{ padding: '6px 8px', fontFamily: 'ui-monospace,monospace', width: 60 }}>{id}</td>
                  <td style={{ padding: '6px 8px' }}>{name}</td>
                  <td style={{ padding: '6px 8px', width: 90 }}>{pill(id)}</td>
                  <td className="ss dim" style={{ padding: '6px 8px' }}>
                    {arabicHealth(atoms[id]?.health?.message)}</td>
                  <td style={{ padding: '6px 8px', width: 200, textAlign: 'left' }}>
                    <button className="btn" disabled={busy} onClick={() => void atomPower(id, true)}><TradingLed status={atomStatus(id)} text={statusText(atomStatus(id), name)} />▶️ شغّل</button>{' '}
                    <button className="btn" disabled={busy} onClick={() => void atomPower(id, false)}
                      title={CRITICAL_ATOMS.has(id) ? 'ذرّةٌ حرجة — إيقافها بختمك: ملخّصٌ يقول ما يسقط، ثمّ تأكيد' : undefined}><TradingLed status={atomStatus(id)} text={statusText(atomStatus(id), name)} />⏹️ أوقف{CRITICAL_ATOMS.has(id) ? ' (بختمك)' : ''}</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ))}

      {message ? (
        <div className="scard" style={{ marginTop: 14, position: 'sticky', bottom: 10 }}>
          <b>{message}</b>
        </div>
      ) : null}
    </div>
  )
}

