// الإعدادات★ (٨٦٧) — تعديل حيّ لإعداد الذرة (كتابة). نموذج عربي مولّد من إعدادات الذرة
// المعلَنة (لا JSON) · يتحقّق بالباك-إند · يكتب سطريًّا · يرفع النسخة ويتأكّد من إعادة التحميل.
// النموذج نفسه (AtomConfigForm) تستعمله نافذة الذرة كمان (زر «تعديل» — طلب المالك).
// وفوقه بطاقة «عيارات القرار» (أمر المالك ٢٠٢٦-٠٨-١٩): العتبات عيارها بإيد المالك من
// اللوحة، كل رقم قابل للتغيير بدقّة 100.00 — قراءة من /gov/decision/settings، تعديل حصرًا
// عبر بوّابة الأوامر (تأكيد بخطوتين action=decision_setting)، وتحديث حي من decision.settings.state.
import { useEffect, useMemo, useState } from 'react'
import { useStore } from '../core/store'
import { useMarket } from '../core/market'
import { settingLabel } from '../core/settingLabels'
import { confirmedCommand, confirmedCommandMany } from '../core/commands'
import { LockedValue, lockedShown } from '../components/SectionAtoms'
import { SECTIONS } from '../core/sections'
import {
  COLOR_VARS, loadColors, saveColor, resetColors, type ColorsMap,
  loadZoom, saveZoom, ZOOM_MIN, ZOOM_MAX,
  getTabOrder, saveTabOrder, resetTabOrder, TAB_ORDER_EVENT,
} from '../core/appearance'

interface Setting {
  key: string; value: unknown; type: string; min: number | null; max: number | null
  live_value?: unknown; overridden?: boolean
  locked?: boolean; lock_reason?: string
}

export function AtomConfigForm({ atomId, sandbox = false }: { atomId: number; sandbox?: boolean }) {
  const atoms = useStore((s) => s.atoms)
  // ٢٠٢٦-١٠-٢٦ (فحص المشروع، ختم «nq اصلح»): أرقام الخطوط الحمراء والقسم 600 مقفلة — تُعرض للقراءة ولا تُرسل، وأرقام 509
  // الخمسة من حالها الحيّة (الرصيد الابتدائيّ 9,000 الذي كتبه المالك، لا 10,000 البيان). التفصيل في `SectionAtoms.tsx`.
  const liveLimits = (useStore((s) => s.streams['risk.account_limits.state']) as
    { settings?: Record<string, unknown> } | undefined)?.settings
  const [settings, setSettings] = useState<Setting[] | null>(null)
  const [vals, setVals] = useState<Record<string, string>>({})
  const [msg, setMsg] = useState('')
  const [busy, setBusy] = useState(false)
  const cfgPath = sandbox ? `/gov/lab/config/${atomId}` : `/gov/atoms/${atomId}/config`

  const load = () => {
    setMsg(''); setSettings(null)
    fetch(cfgPath)
      .then((r) => r.json())
      .then((d: { settings?: Setting[]; error?: string }) => {
        const s = d.settings ?? []
        setSettings(s)
        const v: Record<string, string> = {}
        for (const x of s) v[x.key] = x.type === 'array' || x.type === 'object' ? JSON.stringify(x.value) : String(x.value)
        setVals(v)
        if (d.error) setMsg(d.error)
      })
      .catch(() => setSettings([]))
  }

  useEffect(() => { load() }, [atomId, sandbox]) // eslint-disable-line react-hooks/exhaustive-deps

  async function save() {
    if (!settings) return
    const name = atoms[atomId]?.name_ar ?? `#${atomId}`
    if (!sandbox && !window.confirm(`تعديل إعدادات «${name}» وإعادة تحميلها حيًّا؟`)) return
    setBusy(true); setMsg('')
    const updates: Record<string, unknown> = {}
    try {
      for (const setting of settings) {
        if (!sandbox && setting.locked) continue
        const raw = vals[setting.key]
        updates[setting.key] = setting.type === 'array' || setting.type === 'object' ? JSON.parse(raw) : raw
      }
      const r = await fetch(cfgPath, {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(updates),
      })
      const j = (await r.json()) as { message?: string; error?: string; ok?: boolean }
      setMsg(j.message ?? j.error ?? (r.ok ? 'تمّ' : 'ما تمّ'))
      if (sandbox && r.ok) load()
    } catch {
      setMsg('خطأ اتصال')
    }
    setBusy(false)
  }

  async function resetSandbox() {
    if (!sandbox) return
    setBusy(true); setMsg('')
    try {
      const r = await fetch(`/gov/lab/config/${atomId}/reset`, { method: 'POST' })
      const j = (await r.json()) as { message?: string }
      setMsg(j.message ?? 'رجعت للأصل')
      load()
    } catch {
      setMsg('خطأ اتصال')
    }
    setBusy(false)
  }

  if (settings == null) return <div className="dim">جارِ جلب الإعدادات…</div>
  if (settings.length === 0) return <div className="empty">هالذرة ما عندها إعدادات قابلة للتعديل.</div>
  return (
    <>
      <div className="cards">
        {settings.map((s) => (
          <div className="scard" key={s.key}>
            <div className="st">{settingLabel(s.key)}</div>
            {!sandbox && s.locked ? (
              <>
                <LockedValue text={lockedShown(atomId, s, liveLimits)} reason={s.lock_reason} />
                <div className="ss dim" style={{ lineHeight: 1.7 }}>{s.lock_reason}</div>
              </>
            ) : s.type === 'boolean' ? (
              // البند ٢٢ (المرحلة أ): مفتاح الأمان يُعرَض مفتاحًا حقيقيًّا،
              // وحالته من القيمة المنطقيّة نفسها لا من «هل النصّ غير فارغ» —
              // كتابة «لا» بالمربّع القديم كانت تُقرأ True فتفتح البوّابة.
              <label className="cfgswitch">
                <input
                  type="checkbox"
                  checked={vals[s.key] === 'true'}
                  onChange={(e) => setVals((v) => ({ ...v, [s.key]: e.target.checked ? 'true' : 'false' }))}
                />
                <span className={vals[s.key] === 'true' ? 'on' : 'off'}>
                  {vals[s.key] === 'true' ? 'مفتوح' : 'مقفل'}
                </span>
              </label>
            ) : (
              <input
                className="cfginput num"
                value={vals[s.key] ?? ''}
                inputMode="decimal"
                onChange={(e) => setVals((v) => ({ ...v, [s.key]: e.target.value }))}
              />
            )}
            <div className="ss">
              {s.min != null ? `أدنى ${s.min}` : ''}{s.min != null && s.max != null ? ' · ' : ''}{s.max != null ? `أقصى ${s.max}` : ''}
              {sandbox && s.overridden ? ' · مختبر (الحي مختلف)' : ''}
            </div>
          </div>
        ))}
      </div>
      <div style={{ display: 'flex', gap: 12, alignItems: 'center', marginTop: 10, flexWrap: 'wrap' }}>
        <button className="btn start" disabled={busy || (!sandbox && settings.every((s) => s.locked))} onClick={save}>
          {sandbox ? 'حفظ للمختبر فقط' : settings.every((s) => s.locked) ? 'كلّها مقفلة 🔒' : 'حفظ وتطبيق حيّ'}
        </button>
        {sandbox ? (
          <button className="btn" disabled={busy} onClick={() => void resetSandbox()}>
            ارجع لأصل التداول
          </button>
        ) : null}
        {msg ? <span className="dim">{msg}</span> : null}
      </div>
    </>
  )
}

// ——— عيارات القرار (سجلّ المُعامِلات المحكوم — القيمة المعتمدة تعلو المانيفست) ———
/** ٢٠٢٦-٠٩-٠٤ (ختم NQ): يُبقي العربيّة وعلامات الترقيم و**الأرقام اللاتينيّة**
 *  (دستور المالك يطلبها: `60.0` لا `٦٠٫٠`)، ويحذف الرموز الإنكليزيّة الخام —
 *  مفاتيح الإعداد وأسماء الأحداث ورموز الإصدارات. إن لم يبقَ شرحٌ عربيّ يُقال
 *  «بلا شرح» صراحةً؛ الفراغ الصامت كذبةٌ صغيرة، والخام مخالفة للدستور. */
const arabicOnly = (text: unknown): string =>
  String(text ?? '')
    .replace(/[A-Za-z][A-Za-z0-9_.]*/g, ' ')
    .replace(/\s{2,}/g, ' ')
    .replace(/^[\s—·:،-]+|[\s—·:،-]+$/g, '')
    .trim() || 'بلا شرح'

// Dial/DialRow/useDecisionDials مُصدَّرة عمدًا (بند ١٨ بورقة ٩٩): بطاقات البوابات
// بصفحة «التنفيذ» تعيد استعمال نفس المكوّن — لا نسخة ثانية منه.

export interface Dial {
  name: string; atom: string; key: string; value: number
  status: string; source: string; version: number
  display: 'percent' | 'raw' | 'integer'
  bounds: [number, number]
  where: string
}

// التسميات العربية بترتيب العرض المعتمد — والأرقام تبقى غربية (عرف اللوحة)
const DIAL_AR: Record<string, string> = {
  // ٢٠٢٦-١٠-٠٩ (ختم المالك «NQ» — إلغاء مفاتيح السرعة إلى الأرشيف): المفاتيح الأربعة (الرئيسي · السرعة ·
  // الأفق · الحدود) وتفعيل شخصيّة الأفق خرجت من الكود ومن اللوحة — النوافذ والعتبات أرقامها المكتوبة.
  RISK_DIAL: 'عيار المخاطرة — بوابة الزيادة (100 = مثل اليوم · 0 = لا إضافة)',
  // عيارا وزن المسارين وعمقيهما — مستوى القسم لا مستوى المحلّل (اجوبة §٢٢).
  // كانا يظهران بأسمائهما الإنكليزية الخام لأنّ القاموس لم يعرفهما.
  ANALYSIS_FAST_WEIGHT: 'وزن المسار السريع · تِكّات',
  ANALYSIS_SLOW_WEIGHT: 'وزن المسار البطيء · شموع',
  ANALYSIS_FAST_REQUIRED_DEPTH: 'العمق المطلوب — السريع',
  ANALYSIS_SLOW_REQUIRED_DEPTH: 'العمق المطلوب — البطيء',
  DECISION_NEUTRAL_BAND: 'عتبة الحياد',
  DECISION_CONFLICT_RATIO: 'نسبة التعارض',
  DECISION_MIN_PARTICIPATION: 'المشاركة الدنيا',
  DECISION_DIRECTIONAL_WEIGHT: 'وزن الاستراتيجيات الاتجاهية',
  DECISION_CONTEXT_WEIGHT: 'وزن الأدلة السياقية',
  DECISION_MIN_CONFIDENCE: 'الثقة الدنيا للدليل',
  DECISION_LOW_QUALITY_FACTOR: 'خصم الجودة المنخفضة',
  DECISION_MIN_SCORE: 'الدرجة الدنيا للبوابة',
  DECISION_FILTER_TTL_S: 'مهلة نضارة الفلاتر (ثوانٍ)',
  DECISION_MAX_PER_SYMBOL: 'أقصى مراكز للرمز الواحد',
}

// مقياس العرض: النسب تُعرض ×100 بعشريتين مع «%»، الخام بعشريتين، الصحيح بلا كسور
const shownValue = (d: Dial): string =>
  d.display === 'percent' ? (d.value * 100).toFixed(2)
    : d.display === 'integer' ? String(Math.round(d.value))
      : d.value.toFixed(2)

export function DialRow({ dial }: { dial: Dial }) {
  const [draft, setDraft] = useState(() => shownValue(dial))
  const [busy, setBusy] = useState(false)
  const [note, setNote] = useState<{ ok: boolean; text: string } | null>(null)
  // كل قيمة/نسخة جديدة تصل من النواة تعيد ضبط المسودّة على الواقع
  useEffect(() => { setDraft(shownValue(dial)) }, [dial.value, dial.version, dial.status]) // eslint-disable-line react-hooks/exhaustive-deps

  const integer = dial.display === 'integer'
  const lo = dial.display === 'percent' ? dial.bounds[0] * 100 : dial.bounds[0]
  const hi = dial.display === 'percent' ? dial.bounds[1] * 100 : dial.bounds[1]
  const fmtBound = (b: number) => (integer ? String(Math.round(b)) : b.toFixed(2))

  const save = async () => {
    const n = Number(draft)
    if (draft.trim() === '' || !Number.isFinite(n)) { setNote({ ok: false, text: 'أدخل رقمًا صالحًا' }); return }
    if (n < lo || n > hi) { setNote({ ok: false, text: `القيمة خارج الحدود — من ${fmtBound(lo)} إلى ${fmtBound(hi)}` }); return }
    // دقّة عشريتين على مقياس العرض، ثم التحويل لمقياس التخزين (كسور 0-1 للنسب)
    const stored = integer ? Math.round(n)
      : dial.display === 'percent' ? Math.round(n * 100) / 10000
        : Math.round(n * 100) / 100
    setBusy(true); setNote(null)
    // بند ٥ (٢٠٢٦-٠٩-٠٣): «حفظ» يكتب القيمة في سجلّ المُعامِلات ويبقيها
    // UNAPPROVED — لا تُطبَّق. الاعتماد زرٌّ منفصل يمرّر confirm:true.
    const r = await confirmedCommand('decision_setting', { name: dial.name, value: stored, confirm: false })
    setBusy(false)
    setNote(r.ok
      ? { ok: true, text: 'حُفظت القيمة كمسودة (غير معتمدة) — «اعتماد» بالزرّ المجاور يجعلها سارية' }
      : { ok: false, text: r.message ?? 'تعذّر الإرسال' })
  }

  const approve = async () => {
    const n = Number(draft)
    if (draft.trim() === '' || !Number.isFinite(n)) { setNote({ ok: false, text: 'أدخل رقمًا صالحًا' }); return }
    const storedA = integer ? Math.round(n)
      : dial.display === 'percent' ? Math.round(n * 100) / 10000
        : Math.round(n * 100) / 100
    if (storedA < dial.bounds[0] || storedA > dial.bounds[1]) {
      setNote({ ok: false, text: `القيمة خارج الحدود — من ${fmtBound(lo)} إلى ${fmtBound(hi)}` }); return
    }
    setBusy(true); setNote(null)
    const r = await confirmedCommand('decision_setting', { name: dial.name, value: storedA, confirm: true })
    setBusy(false)
    setNote(r.ok
      ? { ok: true, text: r.message ?? 'اعتماد المالك مُرسَل — تُطبّقه الذرّة وتصل هنا لحظة نشْرها' }
      : { ok: false, text: r.message ?? 'تعذّر الإرسال' })
  }

  const approved = dial.status === 'APPROVED'
  return (
    <div className="scard">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', gap: 8, flexWrap: 'wrap' }}>
        {/* بحثٌ موحَّد: `DIAL_AR` ثمّ `PARAM_AR` — عيارٌ غائب عن الأولى كان يسقط
          على اسمه الخام (`DECISION_LIVE_STALE_AFTER_S` · `NEWS_*`). */}
      <div className="st" style={{ fontWeight: 700 }} title={dial.name}>{paramAr(dial.name)}</div>
        <span className={`pill ${approved ? 'green' : 'grey'}`}>
          {approved ? `معتمد ✓ v${dial.version}` : 'غير معتمد — قيمة المانيفست'}
        </span>
      </div>
      {/* حزمة ج (ج٤): نمط المطلوبة/الفعالة/الحالة — الفعّالة هي القيمة الجارية،
          والمطلوبة تساويها إن كانت معتمدة (أمر المالك هو ما يعمل به النظام)،
          وتبقى «لا طلب مسجَّل» قبل أول اعتماد — لا اختراع قيمة مطلوبة غير موجودة. */}
      <div className="ss dim" style={{ marginTop: 4 }}>الفعّالة (ما يعمل به النظام الآن)</div>
      <div className={`sv num${approved ? ' green' : ''}`}>{shownValue(dial)}{dial.display === 'percent' ? '%' : ''}</div>
      <div className="ss dim" style={{ marginTop: 2 }}>
        المطلوبة (آخر أمر مالك): {approved ? <b className="num">{shownValue(dial)}{dial.display === 'percent' ? '%' : ''}</b> : 'لا طلب مسجَّل بعد — قيمة المانيفست الأولية سارية'}
      </div>
      <input className="cfginput num" type="number" inputMode="decimal"
        min={lo} max={hi} step={integer ? 1 : 0.01} value={draft}
        onChange={(e) => setDraft(e.target.value)} />
      <div style={{ display: 'flex', gap: 10, alignItems: 'center', marginTop: 8, flexWrap: 'wrap' }}>
        <button className="btn" disabled={busy} onClick={save}>{busy ? 'جارٍ الإرسال…' : 'حفظ'}</button>
        {/* بند ٥: الحفظ كتابة، والاعتماد قرار — زرّان منفصلان بخطوتين لكلٍّ منهما */}
        <button className="btn" disabled={busy} onClick={approve}
          title="اعتماد المالك وحده ما يجعل القيمة سارية — الحفظ وحده مسودة">
          {approved && dial.status === 'APPROVED' ? 'اعتماد من جديد' : 'اعتماد ✓'}
        </button>
        <span className="ss num" style={{ marginTop: 0 }}>أدنى {fmtBound(lo)} · أقصى {fmtBound(hi)}</span>
      </div>
      {note ? <div style={{ fontSize: 12.5, marginTop: 5, color: note.ok ? 'var(--green)' : 'var(--amber)' }}>{note.text}</div> : null}
      {/* ٢٠٢٦-٠٩-٠٤ (ختم NQ): كان `where` يُعرض خامًا، وهو يبدأ باسم الذرّة
          العربيّ ثم مفتاح الإعداد الإنكليزيّ ثم الشرح — فيظهر `analysis_speed`
          و`fast_required_depth` وأمثالها على شاشة مالكٍ لا يقرأ الإنكليزيّة.
          بحكمه: «ما بدي ولا شي انكليزي او خام». يُنزَع المفتاح من المعروض
          ويبقى كاملًا في تلميح الفأرة — الشرح العربيّ وحده على الشاشة. */}
      <div className="ss dim" title={`${dial.name} · ${dial.where}`}
        style={{ marginTop: 6, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{arabicOnly(dial.where)}</div>
    </div>
  )
}

/** يجلب العيارات المحكومة ويعيد الجلب مع كل نشرة اعتماد حيّة — مشترك بين
 *  بطاقة «عيارات القرار» هنا وبطاقات البوابات بصفحة «التنفيذ» (بند ١٨). */
export function useDecisionDials(onlyNames?: string[], excludeNames: string[] = []): { dials: Dial[] | null; err: string } {
  const [dials, setDials] = useState<Dial[] | null>(null)
  const [err, setErr] = useState('')
  // الحدث الحي decision.settings.state يصل عبر المحرّك إلى streams تلقائيًّا؛
  // كل نشرة (لحظة تطبيق الذرّة اعتماد المالك) تعيد الجلب من سجلّ المُعامِلات.
  const live = useStore((s) => s.streams['decision.settings.state'])
  // مفاتيح ثابتة حتى لا يعيد المكوّن جلب السجل في كل إعادة رسم بسبب مصفوفة جديدة.
  const onlyKey = onlyNames?.join('|') ?? ''
  const excludeKey = excludeNames.join('|')

  useEffect(() => {
    const controller = new AbortController()
    fetch('/gov/decision/settings', { signal: controller.signal })
      .then((r) => r.json())
      .then((d: { dials?: Dial[] }) => {
        const order = Object.keys(DIAL_AR)
        const filtered = (d.dials ?? []).filter((dial) =>
          (!onlyNames || onlyNames.includes(dial.name)) && !excludeNames.includes(dial.name))
        setDials(filtered.slice().sort((a, b) => order.indexOf(a.name) - order.indexOf(b.name)))
        setErr('')
      })
      .catch(() => setErr('تعذّر جلب العيارات — تأكّد أن خادم الحوكمة شغّال'))
    return () => controller.abort()
  }, [live, onlyKey, excludeKey])

  return { dials, err }
}

export function DecisionDialsCard({ excludeNames = [], onlyNames }: {
  excludeNames?: string[]; onlyNames?: string[]
}) {
  const { dials, err } = useDecisionDials(onlyNames, excludeNames)

  // ٢٠٢٦-٠٩-٠٤ (ختم NQ): توأم زرّ «اعتماد الكل» في بطاقة المُعامِلات، لأنّ
  // العيارات مسارها `decision_setting` لا `parameter_approve`، فزرّ تلك البطاقة
  // لا يمسّها. مقيس بعد أوّل كبسة: اعتُمد ٢٧ من ٣٦، وبقيت تسعة — كلّها عيارات —
  // فبقيت **١٠٢ بطاقة قسم** كلّها `provisional=True` بسبب `UNAPPROVED_PARAMETER`
  // وحده، و`weight_effect=0.0` في كلٍّ منها، فبقي `active_weight=0.0` مع أنّ
  // المتاح 233.33، وأعماقها كلّها فوق المطلوب (‏82.3/64.8 · 89.6/60 · 91.8/60).
  // تسعةٌ غير معتمدة تحجب مئةً واثنتين مقيسة.
  //
  // القيمة المرسَلة هي المخزَّنة كما هي (`d.value`) — لا رقم يُخترع ولا يُقرَّب،
  // وكل عيار يمرّ بخطوتَي البوّابة نفسِهما؛ التأكيد وحده صار واحدًا.
  const [bulkBusy, setBulkBusy] = useState(false)
  const [bulkMsg, setBulkMsg] = useState('')
  const pendingDials = (dials ?? []).filter((d) => d.status !== 'APPROVED')
  const approveAllDials = async () => {
    if (!pendingDials.length) return
    setBulkBusy(true); setBulkMsg('')
    const r = await confirmedCommandMany(
      // ٢٠٢٦-١٠-٢٦: كلّ أمرٍ يحمل اسمه العربيّ وقيمته كما تُعرض، فيُرى في التأكيد واحدًا واحدًا.
      pendingDials.map((d) => ({
        action: 'decision_setting',
        payload: { name: d.name, value: d.value, confirm: true },
        label: `${DIAL_AR[d.name] ?? 'عيار بلا اسم'}: ${shownValue(d)}${d.display === 'percent' ? '٪' : ''}`,
      })),
      `اعتماد ${pendingDials.length} عيارًا بقيمها المعروضة الآن`,
    )
    setBulkBusy(false)
    setBulkMsg(r.ok
      ? `اعتُمد ${r.done} عيارًا — تظهر «معتمد ✓» لحظة تنفيذ بوّابة الأوامر`
      : `نجح ${r.done} · تعذّر ${r.failed.length}${r.failed.length ? ' — ' + r.failed.slice(0, 3).map((f) => f.message).join(' · ') : ''}`)
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
      <div className="scard">
        <div className="st" style={{ fontWeight: 700 }}>
          عيارات القرار
          {dials ? <span className="ss dim" style={{ fontWeight: 400 }}>
            {'  · معتمدة: '}{dials.filter((d) => d.status === 'APPROVED').length}{' من '}{dials.length}
          </span> : null}
        </div>
        <div className="ss dim">
          عتبات سلسلة القرار المحكومة — كل رقم قابل للتغيير بدقّة 100.00، والتعديل يمرّ ببوّابة الأوامر بتأكيد.
          المعتمد يعلو قيمة المانيفست حيًّا بلا إعادة تشغيل؛ وغير المعتمد تبقى قيمة المانيفست هي السارية.
        </div>
        {dials ? (
          <div style={{ marginTop: 8, display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
            <button className="btn" disabled={bulkBusy || pendingDials.length === 0} onClick={approveAllDials}
              title="كل عيار يمرّ ببوّابة الأوامر (٩٠١) بقيمته المعروضة — التأكيد وحده صار واحدًا">
              {bulkBusy ? 'جارٍ الاعتماد…'
                : pendingDials.length === 0 ? 'كلّها معتمدة ✓'
                  : `اعتماد الكل (${pendingDials.length}) ✓`}
            </button>
            <span className="ss dim">
              كبسة واحدة · تأكيد واحد · لا قيمة تتغيّر ولا حارس يُرفع
            </span>
          </div>
        ) : null}
        {bulkMsg ? <div style={{ marginTop: 6, fontSize: 13 }}>{bulkMsg}</div> : null}
        {err ? <div style={{ marginTop: 6, fontSize: 13, color: 'var(--amber)' }}>{err}</div> : null}
      </div>
      {dials == null
        ? <div className="dim">جارِ جلب العيارات…</div>
        : dials.length === 0
          ? <div className="empty">ما وصل أي عيار — سجلّ المُعامِلات فاضي.</div>
          : <div className="cards" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(250px, 1fr))' }}>
              {dials.map((d) => <DialRow key={d.name} dial={d} />)}
            </div>}
      {/* ٢٠٢٦-١٠-٠٩ (ختم المالك «NQ» — إلغاء مفاتيح السرعة إلى الأرشيف): بطاقتا «سرعة التحليل لكل أصل»
          و«شخصيّة الأفق المولّدة» خرجتا مع مفاتيحهما — لا قارئ لهما في الكود. */}
    </div>
  )
}

// كل ما يخص قسم التحليل يُدار من قسم التحليل نفسه، لا من الإعدادات العامة.
export const ANALYSIS_DIAL_NAMES = [
  'ANALYSIS_FAST_WEIGHT', 'ANALYSIS_SLOW_WEIGHT',
  'ANALYSIS_FAST_REQUIRED_DEPTH', 'ANALYSIS_SLOW_REQUIRED_DEPTH',
]

// ٢٠٢٦-١٠-٠٨ (فكّ الأقسام عن القرار، ختم المالك «NQ»): قائمتا عيارات القرار (451-463) والمخاطرة (581) حُذفتا — ذرّاتها أُرشفت وما عاد لهما بطاقة تعرضهما.

export function AnalysisSettingsCard() {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
      <DecisionDialsCard onlyNames={ANALYSIS_DIAL_NAMES} />
      <DeclaredParametersCard />
    </div>
  )
}

// ——— المُعامِلات المعلنة (بند ٢٢ حزمة أ — أ٧، حكم ق١) ———
// الستّة التحليلية التي تحكم بوّابة READY ولم يكن لها أي طريق اعتماد. نفس نمط
// DialRow حرفيًّا: قراءة من /gov/parameters (قراءة فقط mode=ro)، الاعتماد حصرًا
// عبر بوّابة الأوامر (تأكيد بخطوتين action=parameter_approve → ٩٠١ تكتب بالسجلّ)،
// وتحديث حيّ من parameter.approved.state لحظة تنفيذ البوّابة.

export interface GovParameter {
  name: string; scope: string; value: number; source: string; status: string
  version: number; approved_by: string; approved_at: number
  governs: string; declared_at: string; approvable: boolean
}

// التسميات العربية بترتيب العرض — والأرقام تبقى غربية (عرف اللوحة)
// ٢٠٢٦-٠٩-٠٤ (ختم NQ): كانت هذه الخريطة تغطّي الستّة القابلة للاعتماد وحدها،
// لأنّ البطاقة كانت تعرضها وحدها. ولمّا صارت تعرض الستّ والثلاثين كلّها ظهرت
// ثلاثون بطاقة باسمها الخام الإنكليزيّ على شاشة مالكٍ **لا يقرأ الإنكليزيّة** —
// خرقٌ لدستوره: «عربيّ ١٠٠٪ في كل ما يُعرض للمالك». بحكمه: «ما بدي ولا شي
// انكليزي او خام». فالخريطة الآن تغطّي الستّ والثلاثين، وتسقط على `DIAL_AR`
// لعيارات القرار المسمّاة هناك، والاسم الخام ينتقل إلى تلميح الفأرة فيبقى
// للتتبّع بلا أن يُعرض. النقص يُكشف بفحص `check_arabic_ui` لا بالعين.
const PARAM_AR: Record<string, string> = {
  MOVEMENT_FLOOR: 'أرضية الحركة',
  ABNORMALITY_GAIN: 'كسب الشذوذ',
  INTEGRITY_BLEND: 'مزيج التماسك',
  CONFIDENCE_BLEND: 'مزيج الثقة',
  DEPTH_BLEND: 'مزيج العمق',
  STALE_AFTER_S: 'مهلة النضارة (ثوانٍ)',
  // عتبات سلسلة القرار
  DECISION_MIN_STRENGTH: 'أدنى قوّة للإشارة',
  DECISION_ELIGIBILITY_MIN_CONFIDENCE: 'أدنى ثقة للأهليّة',
  DECISION_MIN_CURRENT_DEPTH: 'أدنى عمق حاليّ',
  DECISION_BUY_MIN_DIRECTION: 'أدنى اتّجاه للشراء',
  DECISION_SELL_MIN_DIRECTION: 'أدنى اتّجاه للبيع',
  DECISION_LIVE_STALE_AFTER_S: 'مهلة بيات التِكّة (ثوانٍ)',
  // نوافذ الأخبار — بالدقائق
  NEWS_HIGH_WINDOW_BEFORE_MIN: 'نافذة الخبر القويّ — قبله (دقائق)',
  NEWS_HIGH_WINDOW_AFTER_MIN: 'نافذة الخبر القويّ — بعده (دقائق)',
  NEWS_MEDIUM_WINDOW_MIN: 'نافذة الخبر المتوسّط (دقائق)',
  NEWS_LIGHT_WINDOW_MIN: 'نافذة الخبر الخفيف (دقائق)',
}

/** الاسم المعروض: العربيّ أوّلًا، ثمّ اسم عيار القرار، ولا يُعرض خام أبدًا. */
const paramAr = (name: string): string =>
  PARAM_AR[name] ?? DIAL_AR[name] ?? name

/** اسم الذرّة المسؤولة بالعربيّ من `declared_at` — رقمها واسمها، بلا مسار
 *  ولا اسم حدث إنكليزيّ. وإن لم يوجد عربيّ يُقال «غير معلَن» لا يُعرض الخام. */
const atomAr = (declared: unknown): string => {
  const raw = String(declared ?? '')
  const m = /(\d{3,4})_([؀-ۿ][؀-ۿ_\s]*)/.exec(raw)
  if (m) return `${m[1]} · ${m[2].replace(/_/g, ' ').trim()}`
  const ar = raw.match(/[؀-ۿ][؀-ۿ\s_]*/g)
  const joined = ar ? ar.join(' ').replace(/_/g, ' ').trim() : ''
  return joined || 'غير معلَن'
}

// دقّة عشريتين — إلا القيم الصغرى (أرضية الحركة 0.000001): تدويرها لعشريتين
// كان سيعرض 0.00 ويكذب على المالك، فتُعرض وتُرسل كما هي.
const paramShown = (v: number): string =>
  v !== 0 && Math.abs(v) < 0.01 ? String(v) : v.toFixed(2)

// حزمة ج (ج٤): سجلّ تدقيق المُعامِلات — جدول `parameters_audit` موجود فعلًا بمخزن
// المعايرة (shared/parameter_registry.py)، يُقرأ عبر منفذ جديد `/gov/parameters/audit`
// (يحتاج إعادة تشغيل الخادم مثل بقية المنافذ الجديدة). عيارات القرار (decision_dials)
// ليس لها جدول تدقيق بالكود — فلا سجل تغييرات يُعرض لها (غياب مُعلَن، لا اختراع).
interface ParamAuditRow {
  audit_id: number; name: string; scope: string; old_json: string; new_json: string
  version: number; changed_at: number; changed_by: string; command_id: string
}
function useParametersAudit(): { rows: ParamAuditRow[] | null; err: string } {
  const [rows, setRows] = useState<ParamAuditRow[] | null>(null)
  const [err, setErr] = useState('')
  const live = useStore((s) => s.streams['parameter.approved.state'])
  useEffect(() => {
    const controller = new AbortController()
    fetch('/gov/parameters/audit?limit=200', { signal: controller.signal })
      .then((r) => r.json())
      .then((d: { available?: boolean; audit?: ParamAuditRow[] }) => {
        if (d.available === false) { setRows([]); setErr('منفذ /gov/parameters/audit غير حيّ بعد — يحتاج إعادة تشغيل الخادم'); return }
        setRows(d.audit ?? []); setErr('')
      })
      .catch(() => setErr('تعذّر جلب سجلّ التدقيق'))
    return () => controller.abort()
  }, [live])
  return { rows, err }
}

function auditValue(json: string): string {
  try {
    const v = (JSON.parse(json) as { value?: unknown }).value
    return typeof v === 'number' ? v.toLocaleString('ar-EG-u-nu-latn', { maximumFractionDigits: 6 }) : String(v ?? '—')
  } catch { return '—' }
}

export function ParameterRow({ param, audit, auditErr }: { param: GovParameter; audit: ParamAuditRow[] | null; auditErr: string }) {
  const [draft, setDraft] = useState(() => paramShown(param.value))
  const [busy, setBusy] = useState(false)
  const [note, setNote] = useState<{ ok: boolean; text: string } | null>(null)
  const [showAudit, setShowAudit] = useState(false)
  const myAudit = (audit ?? []).filter((r) => r.name === param.name)
  // كل قيمة/نسخة جديدة تصل من السجلّ تعيد ضبط المسودّة على الواقع
  useEffect(() => { setDraft(paramShown(param.value)) }, [param.value, param.version, param.status]) // eslint-disable-line react-hooks/exhaustive-deps

  const save = async () => {
    const n = Number(draft)
    if (draft.trim() === '' || !Number.isFinite(n)) { setNote({ ok: false, text: 'أدخل رقمًا صالحًا' }); return }
    const stored = n !== 0 && Math.abs(n) < 0.01 ? n : Math.round(n * 100) / 100
    setBusy(true); setNote(null)
    const r = await confirmedCommand('parameter_approve', { name: param.name, value: stored })
    setBusy(false)
    setNote(r.ok
      ? { ok: true, text: r.message ?? 'أُرسل — الاعتماد يظهر هنا لحظة ما تنفّذه بوّابة الأوامر (٩٠١)' }
      : { ok: false, text: r.message ?? 'تعذّر الإرسال' })
  }

  const approved = param.status === 'APPROVED'
  return (
    <div className="scard">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', gap: 8, flexWrap: 'wrap' }}>
        <div className="st" style={{ fontWeight: 700 }} title={param.name}>{paramAr(param.name)}</div>
        <span className={`pill ${approved ? 'green' : 'grey'}`}>
          {approved ? `معتمد ✓ v${param.version}` : 'غير معتمد — القيمة الأولية العادلة سارية'}
        </span>
      </div>
      {/* حزمة ج (ج٤): الفعّالة/المطلوبة/الحالة صراحة — لا اختراع قيمة مطلوبة قبل أول اعتماد */}
      <div className="ss dim" style={{ marginTop: 4 }}>الفعّالة (ما يعمل به النظام الآن)</div>
      <div className={`sv num${approved ? ' green' : ''}`}>{paramShown(param.value)}</div>
      <div className="ss dim" style={{ marginTop: 2 }}>
        المطلوبة (آخر أمر مالك): {approved ? <b className="num">{paramShown(param.value)}</b> : 'لا طلب مسجَّل بعد — القيمة الأولية العادلة سارية'}
      </div>
      <input className="cfginput num" type="number" inputMode="decimal" step={0.01}
        value={draft} disabled={!param.approvable} onChange={(e) => setDraft(e.target.value)} />
      <div style={{ display: 'flex', gap: 10, alignItems: 'center', marginTop: 8, flexWrap: 'wrap' }}>
        {/* ٢٠٢٦-٠٩-٠٤ (ختم NQ): الصفحة صارت تعرض الستّ والثلاثين كلّها. وما ليس قابلًا
            للاعتماد يُعرض للقراءة بزرّ معطَّل — لا مخفيًّا ولا بزرٍّ يفشل عند الخادم. */}
        <button className="btn" disabled={busy || !param.approvable} onClick={save}>
          {busy ? 'جارٍ الإرسال…' : param.approvable ? 'اعتماد' : 'للقراءة فقط'}
        </button>
      </div>
      {param.approvable ? null : (
        <div className="ss dim" style={{ marginTop: 4 }}>
          لا يُعتمد من هنا — يُضبط من بطاقة «عيارات القرار» أو من مانيفست ذرّته.
        </div>
      )}
      {note ? <div style={{ fontSize: 12.5, marginTop: 5, color: note.ok ? 'var(--green)' : 'var(--amber)' }}>{note.text}</div> : null}
      {/* ٢٠٢٦-٠٩-٠٤ (ختم NQ): كان هذا السطر يعرض `governs` و`declared_at` خامَين —
          أسماء أحداثٍ ومسارات إنكليزيّة على شاشة مالكٍ لا يقرأ الإنكليزيّة.
          المعروض الآن اسم الذرّة العربيّ وحده؛ والخام كلّه في تلميح الفأرة،
          فالتتبّع محفوظ ولا حرف أجنبيّ على الشاشة. */}
      <div className="ss dim"
        title={`${param.name} · يحكم: ${param.governs} · المصدر بالكود: ${param.declared_at}`}
        style={{ marginTop: 6, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
        الذرّة المسؤولة: {atomAr(param.declared_at)}
      </div>
      {/* سجل تغييرات — جدول parameters_audit موجود بالكود فعلًا؛ لا زرّ رجوع
          لأن لا آلية رجوع فعلية بالكود (901/parameter_registry لا يملكان استرجاعًا) —
          الرجوع لقيمة سابقة يحتاج اعتمادًا يدويًّا جديدًا بنفس القيمة القديمة. */}
      {auditErr ? <div className="ss dim" style={{ marginTop: 6 }}>{auditErr}</div> : myAudit.length ? (
        <div style={{ marginTop: 6 }}>
          <button className="btn" style={{ fontSize: 11.5 }} onClick={() => setShowAudit(!showAudit)}>
            {showAudit ? '▴ خبّي سجل التغييرات' : `▾ سجل التغييرات (${myAudit.length})`}
          </button>
          {showAudit ? (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 3, marginTop: 6, fontSize: 11.5 }}>
              {myAudit.map((a) => (
                <div key={a.audit_id} className="dim">
                  {new Date(a.changed_at * 1000).toLocaleString('ar-EG-u-nu-latn', { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
                  {' — '}{auditValue(a.old_json)} ← <b className="num" style={{ color: 'var(--ink)' }}>{auditValue(a.new_json)}</b>
                  {' '}(v{a.version} · {a.changed_by || 'غير معروف'})
                </div>
              ))}
            </div>
          ) : null}
        </div>
      ) : <div className="ss dim" style={{ marginTop: 6 }}>لا سجل تغييرات بعد لهذا المُعامِل — لا زرّ رجوع (لا آلية رجوع فعلية بالكود).</div>}
    </div>
  )
}

export function DeclaredParametersCard() {
  const [params, setParams] = useState<GovParameter[] | null>(null)
  const [err, setErr] = useState('')
  // الحدث الحي parameter.approved.state يصل عبر المحرّك إلى streams تلقائيًّا؛
  // كل نشرة (لحظة تطبيق ٩٠١ اعتماد المالك) تعيد الجلب من السجلّ.
  const live = useStore((s) => s.streams['parameter.approved.state'])

  useEffect(() => {
    const controller = new AbortController()
    fetch('/gov/parameters', { signal: controller.signal })
      .then((r) => r.json())
      .then((d: { available?: boolean; parameters?: GovParameter[] }) => {
        const order = Object.keys(PARAM_AR)
        // ٢٠٢٦-٠٩-٠٤ (ختم NQ): كان الفلتر يُبقي المُعامِلات القابلة للاعتماد وحدها — ستًّا
        // من ستٍّ وثلاثين — فيفتح المالك الصفحة ولا يرى ثلاثين قيمة يعمل بها نظامه.
        // بحكمه: «انا اعمى ما عم شوف شي قدام عيني». الآن تُعرض كلّها؛ وغير القابل
        // للاعتماد يظهر للقراءة بزرّ معطَّل وسببٍ مكتوب (انظر ParameterRow).
        // الترتيب: المعروف بـPARAM_AR أوّلًا بترتيبه، ثم الباقي أبجديًّا بلا إخفاء.
        const rank = (n: string): number => { const i = order.indexOf(n); return i === -1 ? order.length : i }
        // ٢٠٢٦-١٠-٠٩ (ختم المالك «NQ» — إلغاء مفاتيح السرعة إلى الأرشيف): صفٌّ لا اسم عربيّ له في الخريطتين
        // صفٌّ بلا قارئ في الكود (فحص `check_arabic_ui` يُلزم كلّ معلنٍ وعيارٍ باسم) — كصفوف المفاتيح المؤرشفة؛
        // لا يُعرض، والخادم يُسقطه كذلك بعد إقلاعه التالي.
        setParams((d.parameters ?? []).filter((p) => p.name in PARAM_AR || p.name in DIAL_AR)
          .sort((a, b) => rank(a.name) - rank(b.name) || a.name.localeCompare(b.name)))
        setErr(d.available === false ? 'سجلّ المُعامِلات غير متاح بعد — يتكوّن مع أول تشغيل للنواة' : '')
      })
      .catch(() => setErr('تعذّر جلب المُعامِلات — تأكّد أن خادم الحوكمة شغّال'))
    return () => controller.abort()
  }, [live])
  const { rows: auditRows, err: auditErr } = useParametersAudit()

  // ٢٠٢٦-٠٩-٠٤ (ختم NQ — «بدي افتح تداول من زر واحد كبسة 1 بس»):
  // الاعتماد كان ٣٦ كبسة، كلٌّ بتأكيدين — فبقيت ٣٦/٣٦ غير معتمدة، وبقيت كل
  // بطاقات العقد provisional، فبقي `active_weight = 0.0` مع أنّ المتاح 233.33،
  // فما بلغ قسمٌ READY قطّ، ولا أهّل ٤٥٥ مرّة واحدة في ١٤٢٤ محاولة.
  //
  // الكبسة الواحدة هنا لا تلفّ على شيء: كل مُعامِل يمرّ بخطوتَي بوّابة الأوامر
  // (٩٠١) نفسِهما عبر `confirmedCommandMany` — الفرق أنّ المالك يؤكّد الدفعة
  // مرّة بدل ستٍّ وثلاثين. ولا تُعتمد إلّا القيمة المعروضة أصلًا: لا رقم جديد
  // يُخترع هنا، ولا يُمَسّ حارس.
  const [bulkBusy, setBulkBusy] = useState(false)
  const [bulkMsg, setBulkMsg] = useState('')
  const pending = (params ?? []).filter((p) => p.approvable && p.status !== 'APPROVED')
  const approveAll = async () => {
    if (!pending.length) return
    setBulkBusy(true); setBulkMsg('')
    const r = await confirmedCommandMany(
      pending.map((p) => ({ action: 'parameter_approve', payload: { name: p.name, value: p.value },
        label: `${PARAM_AR[p.name] ?? DIAL_AR[p.name] ?? 'مُعامِل بلا اسم'}: ${p.value}` })),
      `اعتماد ${pending.length} مُعامِلًا بقيمها المعروضة الآن`,
    )
    setBulkBusy(false)
    setBulkMsg(r.ok
      ? `اعتُمد ${r.done} مُعامِلًا — تظهر «معتمد ✓» لحظة تنفيذ بوّابة الأوامر`
      : `نجح ${r.done} · تعذّر ${r.failed.length}${r.failed.length ? ' — ' + r.failed.slice(0, 3).map((f) => f.message).join(' · ') : ''}`)
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
      <div className="scard">
        <div className="st" style={{ fontWeight: 700 }}>
          المُعامِلات المعلنة{params ? ` — ${params.length} بطاقة` : ''}
          {params ? <span className="ss dim" style={{ fontWeight: 400 }}>
            {'  · قابلة للاعتماد: '}{params.filter((p) => p.approvable).length}
            {' · معتمدة: '}{params.filter((p) => p.status === 'APPROVED').length}
          </span> : null}
        </div>
        {params ? (
          <div style={{ marginTop: 8, display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
            <button className="btn" disabled={bulkBusy || pending.length === 0} onClick={approveAll}
              title="كل مُعامِل يمرّ ببوّابة الأوامر (٩٠١) كما هو — التأكيد وحده صار واحدًا بدل ستٍّ وثلاثين">
              {bulkBusy ? 'جارٍ الاعتماد…'
                : pending.length === 0 ? 'كلّها معتمدة ✓'
                  : `اعتماد الكل (${pending.length}) ✓`}
            </button>
            <span className="ss dim">
              كبسة واحدة · تأكيد واحد · لا قيمة تتغيّر ولا حارس يُرفع
            </span>
          </div>
        ) : null}
        {bulkMsg ? <div style={{ marginTop: 6, fontSize: 13 }}>{bulkMsg}</div> : null}
        <div className="ss dim">
          كل مُعامِل معلن بالسجلّ — لا المعتمَد وحده. القيمة الأولية العادلة سارية غير رسمية حتى
          يعتمدها المالك (حكم ق١)، وبقاء أي واحدة غير معتمدة يبقي كل بطاقات العقد provisional.
          الاعتماد يمرّ ببوّابة الأوامر بتأكيد بخطوتين. وما ليس قابلًا للاعتماد من هنا يظهر
          <b> للقراءة فقط</b> بزرٍّ معطَّل — معروضًا لا مخفيًّا، كي تُرى القيمة التي يعمل بها النظام.
        </div>
        {err ? <div style={{ marginTop: 6, fontSize: 13, color: 'var(--amber)' }}>{err}</div> : null}
      </div>
      {params == null
        ? <div className="dim">جارِ جلب المُعامِلات…</div>
        : params.length === 0
          ? <div className="empty">ما وصل أي مُعامِل معلن — سجلّ المُعامِلات فاضي.</div>
          : <div className="cards" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(250px, 1fr))' }}>
              {params.map((p) => <ParameterRow key={p.name} param={p} audit={auditRows} auditErr={auditErr} />)}
            </div>}
    </div>
  )
}

// ——— بند ١٥ (ورقة ٩٩) — لوحة «تخصيص الشكل»: أزرار بإيد المالك مو طلبات ———
// (أ) لوح ألوان حرّ يضبط متغيّرات CSS فورًا · (ب) تكبير عام · (ج) ترتيب التبويبات.
// كلّه localStorage — بلا أي مكتبة خارجية جديدة.

/** القيمة الحالية للمتغيّر: المخصَّص المحفوظ، وإلا قيمة الإطلالة الحالية (إن كانت hex). */
function currentHex(id: string, colors: ColorsMap): string {
  if (colors[id]) return colors[id]
  if (id === 'glass') return '#ffffff'
  const raw = getComputedStyle(document.documentElement).getPropertyValue(id).trim()
  return /^#[0-9a-fA-F]{6}$/.test(raw) ? raw : '#888888'
}

function AppearancePanel() {
  const [colors, setColors] = useState<ColorsMap>(() => loadColors())
  const [zoom, setZoomState] = useState<number>(() => loadZoom())
  const [order, setOrder] = useState<string[]>(() => getTabOrder(SECTIONS.map((s) => s[0])))

  // لو غيّر الترتيبَ طرفٌ آخر (تبويب ثانٍ مفتوح) — انعكس هون كمان
  useEffect(() => {
    const sync = () => setOrder(getTabOrder(SECTIONS.map((s) => s[0])))
    window.addEventListener(TAB_ORDER_EVENT, sync)
    return () => window.removeEventListener(TAB_ORDER_EVENT, sync)
  }, [])

  const labelOf = (id: string) => SECTIONS.find((s) => s[0] === id)?.[1] ?? id

  const move = (idx: number, dir: -1 | 1) => {
    const next = order.slice()
    const j = idx + dir
    if (j < 0 || j >= next.length) return
    // «الذرات» هو التبويب الخامس الثابت، ولا يُسمح بسحبه أو تبديل مكانه.
    if (next[idx] === 'atoms' || next[j] === 'atoms') return
    ;[next[idx], next[j]] = [next[j], next[idx]]
    setOrder(next)
    saveTabOrder(next) // يُطبَّق على شريط الملاحة فورًا (App يستمع للحدث)
  }

  const customized = Object.keys(colors).length > 0

  return (
    <div className="scard">
      <div className="st" style={{ fontWeight: 700 }}>🎨 تخصيص الشكل</div>
      <div className="ss dim">
        كل شي هون بإيدك وبيتطبّق فورًا وبيتحفظ على هالجهاز — ما بتحتاج تطلب من حدا.
        الألوان الحرّة تعلو كل الإطلالات الجاهزة؛ زر «رجوع للون الأساسي» يمسح كل تعديلاتك ويرجّع ألوان الفوركس الأصلية فورًا.
      </div>

      {/* (أ) لوح الألوان الحرّ */}
      <div style={{ marginTop: 12 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
          <div style={{ fontWeight: 700, fontSize: 14 }}>لوح الألوان — اختر اللون يلي بدّك ياه</div>
          <span className={customized ? 'settings-mode custom' : 'settings-mode base'}>
            {customized ? '● وضع مخصّص' : '● الوضع الأساسي'}
          </span>
          <button className="btn" style={{ fontSize: 12 }} disabled={!customized}
            onClick={() => { resetColors(); setColors({}) }}>🎨 رجوع للون الأساسي</button>
        </div>
        <div className="cards" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(190px, 1fr))', marginTop: 8 }}>
          {COLOR_VARS.map((def) => (
            <label key={def.id} className="scard" style={{ display: 'flex', alignItems: 'center', gap: 10, cursor: 'pointer' }}
              title={def.hint ?? ''}>
              <input type="color" value={currentHex(def.id, colors)}
                style={{ width: 42, height: 32, border: 'none', background: 'none', padding: 0, cursor: 'pointer' }}
                onChange={(e) => setColors(saveColor(def.id, e.target.value))} />
              <span style={{ display: 'grid', gap: 2 }}>
                <span style={{ fontSize: 13.5 }}>{def.label}</span>
                {colors[def.id] ? <span className="num dim" style={{ fontSize: 11 }}>{colors[def.id]} — مخصَّص</span>
                  : <span className="dim" style={{ fontSize: 11 }}>من الإطلالة</span>}
              </span>
            </label>
          ))}
        </div>
      </div>

      {/* (ب) التكبير العام */}
      <div style={{ marginTop: 14 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
          <div style={{ fontWeight: 700, fontSize: 14 }}>🔍 تكبير عام</div>
          <input type="range" min={ZOOM_MIN} max={ZOOM_MAX} step={1} value={zoom}
            style={{ flex: 1, minWidth: 180, maxWidth: 380 }}
            onChange={(e) => { const v = Number(e.target.value); setZoomState(v); saveZoom(v) }} />
          <span className="num" style={{ fontWeight: 700, minWidth: 48 }}>{zoom}%</span>
          <button className="btn" style={{ fontSize: 12 }} disabled={zoom === 100}
            onClick={() => { setZoomState(100); saveZoom(100) }}>↩️ 100%</button>
        </div>
        <div className="ss dim">يضبط حجم الخطّ الأساس وتكبير كل الأقسام — عدا صفحة «الشبكة» تبقى بدقّتها الأصلية.</div>
      </div>

      {/* (ج) ترتيب التبويبات */}
      <div style={{ marginTop: 14 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
          <div style={{ fontWeight: 700, fontSize: 14 }}>🧭 ترتيب التبويبات</div>
          <span className="ss dim" style={{ marginTop: 0 }}>فوق/تحت — والشريط فوق بيترتّب لحظيًّا</span>
          <button className="btn" style={{ fontSize: 12 }}
            onClick={() => { resetTabOrder(); setOrder(getTabOrder(SECTIONS.map((s) => s[0]))) }}>↩️ الترتيب الافتراضي</button>
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(230px, 1fr))', gap: 6, marginTop: 8 }}>
          {order.map((id, idx) => (
            <div key={id} style={{ display: 'flex', alignItems: 'center', gap: 8, border: '1px solid var(--glassb)', borderRadius: 9, padding: '5px 9px', background: 'var(--glass)' }}>
              <span className="num dim" style={{ fontSize: 11, minWidth: 20 }}>{idx + 1}</span>
              <span style={{ fontSize: 13.5, flex: 1 }}>{labelOf(id)}</span>
              <button className="btn" style={{ fontSize: 11, padding: '2px 8px' }} disabled={idx === 0}
                onClick={() => move(idx, -1)} title="فوق">▲</button>
              <button className="btn" style={{ fontSize: 11, padding: '2px 8px' }} disabled={idx === order.length - 1}
                onClick={() => move(idx, 1)} title="تحت">▼</button>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

export default function Settings() {
  const atoms = useStore((s) => s.atoms)
  const [id, setId] = useState<number | ''>('')
  const options = useMemo(() => Object.values(atoms).sort((a, b) => a.id - b.id), [atoms])
  // أمر المالك ٢٠٢٦-٠٨-٢٩: «شيل هدول من الإعدادات».
  // «عيارات القرار» و«سرعة التحليل لكل أصل» و«المُعامِلات المعلنة» ثلاثتها
  // سجلّات فوركسيّة (shared/decision_dials.py كلّه ذرّات فوركس، و/gov/parameters
  // يردّ available=false على الكريبتو) — فكانت تظهر بقسم أسمر بطاقاتٍ فارغة
  // بنصوص فوركس. تُخفى هنا بحسب السوق، ولا يتغيّر شيء بالفوركس.
  const market = useMarket()
  const governedDials = market === 'forex'

  return (
    <div className={`section settings-page${governedDials ? ' settings-forex' : ''}`} style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
      {governedDials ? (
        <div className="settings-hero">
          <div className="settings-hero-mark">⚙️</div>
          <div>
            <div className="st" style={{ fontSize: 17, fontWeight: 700 }}>إعدادات الفوركس</div>
            <div className="ss dim">تخصيص الشكل والإعدادات العامة — كل قسم يحتفظ بمفاتيحه الخاصة.</div>
          </div>
          <div className="settings-legend"><span><i className="settings-dot green" /> حيّ</span><span><i className="settings-dot amber" /> يحتاج انتباه</span><span><i className="settings-dot red" /> خطر</span></div>
        </div>
      ) : null}
      {/* ٢٠٢٦-٠٩-٠٤ (ختم NQ): صفحة الإعدادات كانت تعرض البقايا وحدها — تستثني عيارات
          التحليل والقرار والمخاطر لأنّها معروضة في صفحات أخرى، و«المُعامِلات المعلَنة»
          الستّ والثلاثين كانت داخل AnalysisSettingsCard الذي يُستدعى في صفحة «التحليل»
          وحدها (Analysis.tsx:890) ولا يُستدعى هنا إطلاقًا. فالمالك يفتح «الإعدادات»
          ولا يرى بطاقاته. بحكمه: «بدي اشوف كل شي على لوحاتي وانا بنص تداول».
          الآن: المعامِلات المعلَنة + عيارات التحليل، ثم كل العيارات الباقية بلا استثناء
          سوى ما عُرض للتوّ — صفحة واحدة تجمع الجميع بلا تكرار. */}
      {governedDials ? <AnalysisSettingsCard /> : null}
      {governedDials ? <DecisionDialsCard excludeNames={ANALYSIS_DIAL_NAMES} /> : null}
      {/* بند ١٥ — لوحة تخصيص الشكل: مبنيّة حول بطاقة «عيارات القرار» لا فوقها */}
      <AppearancePanel />
      <select className="search" value={id} onChange={(e) => setId(e.target.value === '' ? '' : Number(e.target.value))}>
        <option value="">اختر ذرة لتعديل إعداداتها…</option>
        {options.map((a) => <option key={a.id} value={a.id}>{a.name_ar} #{a.id}</option>)}
      </select>
      {id !== '' ? <AtomConfigForm atomId={id} /> : null}
    </div>
  )
}
