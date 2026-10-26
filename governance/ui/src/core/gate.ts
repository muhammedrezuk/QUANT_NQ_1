// حال بوّابة التنفيذ (552) — قراءةٌ واحدة لكلّ الصفحات.
//
// ٢٠٢٦-١٠-٢٦ (فحص المشروع، وختم المالك «nq اصلح»): «تحكّم» كتبت «مسار التداول: متوقّف» والبوّابة أنهت ثلاثة أوامر في اليوم
// نفسه، و«الرئيسية» قالت «مقفولة بقرارك» و«غرفة النظام» «مقفلة» عن الحال نفسها. والعلّة واحدة: `execution.gate.state` حدثُ
// حدوثٍ لا حالة — ينشره 552 عند الإقلاع وعند كلّ تغيّر — فالنافذة التي تُفتح بعده لا تراه، وكانت تقرأ غيابه إقفالًا.
// «شو صاير» أصلحت ذلك وحدها (٢٠٢٦-٠٩-٢٣): الغياب غيابٌ لا إقفال، وإيقاف الحارس لحسابٍ غير إيقاف المالك العامّ.
// وهذا الملفّ يحمل الطريقة نفسها لكلّ الصفحات، ويزيد مصدرًا ثانيًا مقروءًا: رسالة صحّة 552 نفسها، وهي تُستطلع كلّ أربع ثوانٍ.
// فمنذ ٢٠٢٦-١٠-٠٢ تبدأ الرسالة بما يمنع («🔴 البوّابة مقفلة (enabled=false)» · «🔴 موقوفة لكلّ الحسابات» ·
// «🔴 موقوفة للحسابات […]»، من `shared/order_validator_state.py`)، وبلا بادئةٍ تكون البوّابة مفتوحة.
// ولا يُقرأ شكلٌ لا نعرفه: رسالةٌ ليست من الشكلين المعروفين تبقى «غير مقروء».
import type { AtomRec, GateState } from './store'

export interface GateRead {
  known: boolean                       // هل وصلت حالٌ نعرفها؟ وإلّا فالجواب «غير مقروء»، لا «متوقّف»
  open: boolean                        // البوّابة مفتوحة ولا إيقاف عامّ
  ownerHalt: boolean                   // إيقافٌ عامّ بأمر المالك
  guardHalt: boolean                   // حسابٌ أوقفه حارس — ليس عطلًا ولا أمرًا من المالك
  guardAccounts: [string, string][]    // الحساب وسببه، إن عُرف السبب
  from: 'event' | 'health' | 'atom' | null
}

const UNKNOWN: GateRead = { known: false, open: false, ownerHalt: false, guardHalt: false, guardAccounts: [], from: null }

export function readGate(gate: GateState | null | undefined, a552: AtomRec | undefined): GateRead {
  if (gate != null && gate.status != null) {
    const ownerHalt = gate.halted === true || gate.status === 'HALTED'
    const guardAccounts = Object.entries(gate.halted_accounts ?? {})
    const guardHalt = !ownerHalt && (guardAccounts.length > 0 || gate.status === 'PARTIAL_HALT')
    return { known: true, open: gate.status === 'LIVE', ownerHalt, guardHalt, guardAccounts, from: 'event' }
  }
  if (!a552) return UNKNOWN
  // مدقّق الأمر نفسه لا يعمل: لا أمر يُدقَّق فلا أمر يصل الوسيط — حالٌ معروفة، لا مجهولة.
  if (a552.state !== 'running') return { ...UNKNOWN, known: true, from: 'atom' }
  const msg = a552.health?.message ?? ''
  if (!/(?:^|[\s|])finalized=\d+|READY_AWAITING_FIRST_LEGAL_ORDER/.test(msg)) return UNKNOWN
  const closed = msg.includes('enabled=false')
  const ownerHalt = msg.includes('موقوفة لكلّ الحسابات')
  const listed = /موقوفة للحسابات \[([^\]]*)\]/.exec(msg)
  const guardAccounts: [string, string][] = !ownerHalt && listed
    ? listed[1].split(',').map((a) => a.trim()).filter(Boolean).map((a) => [a, ''] as [string, string])
    : []
  const guardHalt = !ownerHalt && listed != null
  return { known: true, open: !closed && !ownerHalt && !guardHalt, ownerHalt, guardHalt, guardAccounts, from: 'health' }
}
