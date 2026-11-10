// بوّابة الأوامر (١٤ §٨): كل كتابة/أمر تمرّ من مكان واحد، بدرجة صلاحية وتأكيد،
// ثم تنادي خادم الحوكمة الذي يمرّرها لخُطّاف النواة ويُسجّلها بجورنال النواة.
// الدرجات: قراءة (بلا تأكيد) · كتابة (تأكيد) · أوامر خطرة (تأكيد صريح + تمييز).
import { govPost } from './transport'

export type Tier = 'read' | 'write' | 'danger'

export interface Command {
  tier: Tier
  label: string // بالعربي — نصّ التأكيد
  run: () => Promise<Response>
}

export interface CommandResult { ok: boolean; message?: string }

export async function execute(cmd: Command): Promise<CommandResult> {
  if (cmd.tier !== 'read') {
    const prefix = cmd.tier === 'danger' ? '⚠️ أمر خطر — ' : ''
    if (!window.confirm(prefix + cmd.label + '؟')) return { ok: false, message: 'أُلغي' }
  }
  try {
    const r = await cmd.run()
    if (!r.ok) {
      const j = (await r.json().catch(() => ({}))) as { message?: string; detail?: { message?: string }; error?: string }
      return { ok: false, message: j.message ?? j.detail?.message ?? j.error ?? String(r.status) }
    }
    return { ok: true }
  } catch (e) {
    return { ok: false, message: 'خطأ اتصال: ' + String(e) }
  }
}

// الأوامر الخطرة عبر بوّابة الأوامر (٩٠١) — خطوتان مع الخادم:
// طلب → رمز تأكيد + ملخّص عربي → تأكيد المالك → تُكتب بالجسر → الذرة تنشر الحدث خلال ≤ ثانية
export async function confirmedCommand(action: string, payload: Record<string, unknown> = {}, operator = 'لوحة التحكم'): Promise<CommandResult> {
  const post = (body: object) =>
    fetch('/gov/command', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
  try {
    const r1 = await post({ action, payload, operator })
    const j1 = (await r1.json()) as { token?: string; summary?: string; ttl_s?: number; error?: string }
    if (!r1.ok || !j1.token) return { ok: false, message: j1.error ?? String(r1.status) }
    if (!window.confirm(`⚠️ أمر خطر — ${j1.summary ?? action}؟\n(التأكيد صالح ${j1.ttl_s ?? 60} ثانية)`)) {
      return { ok: false, message: 'أُلغي' }
    }
    const r2 = await post({ action, payload, operator, confirm: j1.token })
    const j2 = (await r2.json()) as { message?: string; error?: string }
    if (!r2.ok) return { ok: false, message: j2.error ?? String(r2.status) }
    return { ok: true, message: j2.message }
  } catch (e) {
    return { ok: false, message: 'خطأ اتصال: ' + String(e) }
  }
}

// ٢٠٢٦-١٠-٠٢ (ختم المالك «صلح كامل nq»): الإيقاف كان يُرسل بحمولة `{}` فيرميه
// 516 («بلا حساب») ولا يقف شيء. العقد المشترك: إيقافٌ بلا حساب = كلّ الحسابات،
// والنطاق يُكتب صريحًا. التأكيد بخطوتين كما هو.
export const HALT_PAYLOAD: Record<string, unknown> = { scope: 'SYSTEM' }

export const dangerCommand = (action: 'halt' | 'kill_switch_reset'): Promise<CommandResult> =>
  confirmedCommand(action, action === 'halt' ? HALT_PAYLOAD : {})

// دفعة أوامر (بند 2ب بدفتر 97 — «حفظ إعدادات الكل» و«اعتماد الكل»): كبسة واحدة، وكل أمر يمرّ بخطوتي الخادم نفسهما.
// ٢٠٢٦-١٠-٢٦ (فحص المشروع، ختم المالك «nq اصلح»): كان التأكيد جملة الدفعة وحدها («اعتماد ٣٦ عيارًا»)، ثمّ يُستعمل رمز
// كلّ أمرٍ آليًّا بلا أن يُرى ملخّصه — فالمالك يوافق على عددٍ لا على أوامر. الآن: تُطلب الخطوة الأولى لكلّ أمر أوّلًا،
// ويُعرض ملخّص كلّ واحدٍ منها (مع اسمه بالعربيّ إن أرسلته الصفحة) قبل أيّ إرسال، صفحةً صفحة لعشرة أوامر. وإلغاء أيّ
// صفحة يلغي الدفعة كلّها: لا يُرسل شيء. وإن انتهت مهلة رمزٍ أثناء القراءة، يُطلب رمزه من جديد ويُرسل فقط إن طابق ملخّصُه
// الجديد ما رآه المالك حرفًا حرفًا.
const BATCH_PAGE = 10

/** ملخّص الخادم بلا سطره الأوّل (جملة الأمر العامّة، تُعرض مرّة) وبلا رموز المفاتيح اللاتينيّة الخام. */
const summaryDetail = (summary: string): string =>
  summary.split('\n').slice(1).join(' · ')
    .replace(/\(\s*[A-Za-z][A-Za-z0-9_.]*\s*\)/g, '')
    .replace(/\s{2,}/g, ' ').trim()

export async function confirmedCommandMany(
  items: Array<{ action: string; payload: Record<string, unknown>; label?: string }>,
  batchLabel: string,
  operator = 'لوحة التحكم',
): Promise<{ ok: boolean; done: number; failed: Array<{ index: number; message: string }> }> {
  if (!items.length) return { ok: true, done: 0, failed: [] }
  const post = (body: object) =>
    fetch('/gov/command', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
  const askToken = async (i: number): Promise<{ token?: string; summary?: string; error?: string }> => {
    const { action, payload } = items[i]
    try {
      const r1 = await post({ action, payload, operator })
      const j1 = (await r1.json()) as { token?: string; summary?: string; error?: string }
      return r1.ok && j1.token ? j1 : { error: j1.error ?? String(r1.status) }
    } catch (e) {
      return { error: 'خطأ اتصال: ' + String(e) }
    }
  }
  const failed: Array<{ index: number; message: string }> = []
  const ready: Array<{ index: number; token: string; summary: string }> = []
  for (let i = 0; i < items.length; i++) {
    const one = await askToken(i)
    if (one.token) ready.push({ index: i, token: one.token, summary: one.summary ?? items[i].action })
    else failed.push({ index: i, message: one.error ?? 'تعذّر طلب التأكيد' })
  }
  if (!ready.length) return { ok: false, done: 0, failed }
  const pages = Math.ceil(ready.length / BATCH_PAGE)
  for (let p = 0; p < pages; p++) {
    const slice = ready.slice(p * BATCH_PAGE, (p + 1) * BATCH_PAGE)
    const head = slice[0].summary.split('\n')[0]
    const lines = slice.map((r, k) => {
      const label = items[r.index].label
      const detail = summaryDetail(r.summary)
      return `${p * BATCH_PAGE + k + 1}. ${[label, detail].filter(Boolean).join(' — ') || head}`
    })
    const text = `⚠️ ${batchLabel}؟`
      + `\n${ready.length} أمرًا — كلّ أمرٍ يمرّ ببوّابة الأوامر${pages > 1 ? ` · الصفحة ${p + 1} من ${pages}، وإلغاء أيّ صفحة يلغي الدفعة كلّها` : ''}`
      + (failed.length ? `\nورُدّ ${failed.length} أمرًا قبل التأكيد فلن يُرسل` : '')
      + `\n${head}\n\n${lines.join('\n')}`
    if (!window.confirm(text)) return { ok: false, done: 0, failed: [{ index: -1, message: 'أُلغي' }] }
  }
  let done = 0
  for (const r of ready) {
    const { action, payload } = items[r.index]
    try {
      let r2 = await post({ action, payload, operator, confirm: r.token })
      if (r2.status === 409) {
        // انتهت مهلة الرمز وهو يقرأ: رمزٌ جديد للأمر نفسه، ولا يُرسل إلّا إن طابق ملخّصه ما رآه.
        const again = await askToken(r.index)
        if (!again.token || again.summary !== r.summary) {
          failed.push({ index: r.index, message: again.error ?? 'تغيّر ملخّص الأمر بعد تأكيدك — لم يُرسل' })
          continue
        }
        r2 = await post({ action, payload, operator, confirm: again.token })
      }
      const j2 = (await r2.json()) as { error?: string }
      if (!r2.ok) { failed.push({ index: r.index, message: j2.error ?? String(r2.status) }); continue }
      done++
    } catch (e) {
      failed.push({ index: r.index, message: 'خطأ اتصال: ' + String(e) })
    }
  }
  failed.sort((a, b) => a.index - b.index)
  return { ok: failed.length === 0, done, failed }
}

// أوامر جاهزة (تستعملها الشاشات لاحقًا) — إيقاف = خطر، تشغيل = كتابة
export const atomStop = (id: number, name: string): Command => ({
  tier: 'danger',
  label: `إيقاف الذرة «${name}» (#${id})`,
  run: () => govPost(`/gov/atoms/${id}/stop`),
})

// ٢٠٢٦-١٠-٢٦ (فحص المشروع، ختم المالك «nq اصلح»): زرّ «وقّف» كان يوقف أيّ ذرّة بنافذة «موافق» واحدة — ومنها حدود الحساب
// والخطوط الحمراء، فتسقط الحدود والإغلاق عند الخطّ. هذه الثماني لا تُوقف إلّا بالختم: ملخّصٌ من الخادم يقول ما يسقط، ثمّ
// تأكيد. والخادم يرفض إيقافها بالطريق القديم أيضًا، فهذه القائمة للعرض والتوجيه لا الحارسَ الوحيد.
export const CRITICAL_ATOMS = new Set([509, 516, 552, 555, 565, 601, 618, 901])

export function stopAtom(id: number, name: string): Promise<CommandResult> {
  return CRITICAL_ATOMS.has(id) ? confirmedCommand('atom_stop', { atom_id: id }) : execute(atomStop(id, name))
}
export const atomStart = (id: number, name: string): Command => ({
  tier: 'write',
  label: `تشغيل الذرة «${name}» (#${id})`,
  run: () => govPost(`/gov/atoms/${id}/start`),
})
