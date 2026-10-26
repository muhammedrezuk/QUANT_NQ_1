import { getApiKey } from './auth'
// طبقة النقل (١٤ §٣): اتصال واحد ببثّ النواة (WS) + عميل قراءة (REST عبر خادم الحوكمة).
// إعادة اتصال تلقائية عند الانقطاع؛ لا CORS (الـREST يمرّ بخادم الحوكمة، نفس الأصل).

// المرشِد على أصل الصفحة (يعمل عن بُعد ومعاينة Arena). المسار المباشر :8010
// للجهاز المحلّي فقط — هناك المتصفّح يصل للنواة. عن بُعد، :8010 على اسم الصفحة
// لا يصل أبدًا وكان يترك اللوحة في حالة تجميد سوداء.
const _secure = window.location.protocol === 'https:'
const _host = window.location.host || '127.0.0.1:8090'
const _hostname = window.location.hostname || '127.0.0.1'
const RELAY_WS = `${_secure ? 'wss' : 'ws'}://${_host}/gov/ws/core`

// ٢٠٢٦-٠٩-٠٩ (أمر المالك «ما ضلّ شي اسمه قسم كريبتو»): كان المنفذ يتبع سوقًا
// مختارًا بكوكي (فوركس 8010 · كريبتو 8020). السوق واحد الآن، فالنواة منفذ واحد
// ولا كوكي يُقرأ ولا منفذ ثانٍ يُخمَّن.
const CORE_PORT = 8010
// ٢٠٢٦-٠٩-٠٩ (ختم NQ) — عطل «⛔ النواة مقطوعة» وكل شيء سليم:
// النواة تستمع على `127.0.0.1` وحده (IPv4)، و`localhost` يُحلّ إلى `::1` أوّلًا
// عند المتصفّح. فمن يفتح اللوحة على `http://localhost:8090` تُحمَّل صفحته
// (المتصفّح يسقط لـIPv4 في HTTP) بينما **مقبس البثّ** يقصد `::1` ويفشل —
// فتُعلَن النواة مقطوعة وهي حيّة. مقيسًا: `[::1]:8010` يرفض الاتصال.
// العنوان هنا صريح بالرقم، فلا يُترك للمحلّل أن يختار عائلة العنوان.
const CORE_HOST = '127.0.0.1'
const _coreWs = (): string =>
  `${_secure ? 'wss' : 'ws'}://${CORE_HOST}:${CORE_PORT}/ws/events`

// ٢٠٢٦-٠٩-٠٩ (ختم NQ): كل رسالة بثّ تحمل `stream_sequence`، وحين يمتلئ طابور
// النواة (`maxsize=500`) تُسقَط أقدم رسالة وتُعلَن الحالية بـ`dropped_total`
// و`stream_gap: true` (`core/api/app.py:59-72`). **واللوحة كانت تتجاهل
// الثلاثة**: النواة تقول «أسقطتُ أحداثًا» والمالك يظنّ أنّه يرى كل شيء —
// وهو أخطر أنواع الصمت لأنّ الشاشة تبقى خضراء وكاملة المظهر.
type WsCommon = { stream_sequence?: number; dropped_total?: number; stream_gap?: boolean }
export type WsMsg =
  | ({ type: 'snapshot'; atoms: unknown[]; metrics: unknown } & WsCommon)
  | ({ type: 'event'; name: string; payload: unknown } & WsCommon)

/** يفتح اتصالًا واحدًا ببثّ النواة. عن بُعد: المرشِد فقط. محلّيًا: النواة مباشرة. */
export function connectWs(
  onMsg: (m: WsMsg) => void,
  onStatus: (open: boolean) => void,
): () => void {
  let ws: WebSocket | null = null
  let stopped = false
  let reconnectTimer: number | undefined
  let downTimer: number | undefined
  const localHost = _hostname === '127.0.0.1' || _hostname === 'localhost' || _hostname === '::1'
  // ٢٠٢٦-٠٩-٠٩ (ختم NQ): المسار المباشر للنواة أسرع، لكنّه يعتمد على منفذ ثانٍ
  // مفتوح. إن أخفق مرّتين متتاليتين نسقط تلقائيًّا إلى مرسى الحوكمة (نفس أصل
  // الصفحة ونفس منفذها) بدل إعلان «النواة مقطوعة» وهي حيّة. أوّل اتّصال ناجح
  // مباشرةً يصفّر العدّاد، فلا نبقى على المرسى بعد زوال السبب.
  let directFails = 0
  const DIRECT_FAIL_LIMIT = 2

  // لا نعلن الانقطاع من أول إغلاق عابر: ننتظر 10 ثوانٍ. هذا يمنع وميض
  // الشاشة عند إعادة تشغيل النواة أو عند تبدّل الشبكة للحظات.
  const markDownDebounced = () => {
    if (downTimer !== undefined) return
    downTimer = window.setTimeout(() => { if (!stopped && ws?.readyState !== WebSocket.OPEN) onStatus(false) }, 10000)
  }
  const markUp = () => {
    if (downTimer !== undefined) { window.clearTimeout(downTimer); downTimer = undefined }
    onStatus(true)
  }

  const open = () => {
    if (stopped) return
    const direct = localHost && directFails < DIRECT_FAIL_LIMIT
    let next: WebSocket
    try {
      const key = getApiKey()
      const encoded = key ? btoa(unescape(encodeURIComponent(key))).replace(/=+$/g, '').replace(/\+/g, '-').replace(/\//g, '_') : ''
      const url = direct ? _coreWs() : RELAY_WS
      next = encoded ? new WebSocket(url, ['quant-nq', `quant-nq-key.${encoded}`]) : new WebSocket(url)
    } catch {
      if (direct) directFails++
      markDownDebounced()
      reconnectTimer = window.setTimeout(open, 2500)
      return
    }
    ws = next
    ws.onopen = () => { if (direct) directFails = 0; markUp() }
    ws.onmessage = (e) => {
      try { onMsg(JSON.parse(e.data as string) as WsMsg) } catch { /* رسالة غير صالحة تُتجاهل */ }
    }
    ws.onclose = () => {
      if (direct) directFails++
      markDownDebounced()
      if (!stopped) reconnectTimer = window.setTimeout(open, 2500)
    }
    ws.onerror = () => { try { ws?.close() } catch { /* تجاهل */ } }
  }
  open()
  return () => {
    stopped = true
    if (reconnectTimer !== undefined) window.clearTimeout(reconnectTimer)
    if (downTimer !== undefined) window.clearTimeout(downTimer)
    try { ws?.close() } catch { /* تجاهل */ }
  }
}

/** قراءة عبر خادم الحوكمة (يقرأ النواة ويترجم للعربي). */
export async function govGet<T>(path: string): Promise<T> {
  const r = await fetch(path)
  if (!r.ok) throw new Error(String(r.status))
  return (await r.json()) as T
}

/** كتابة/أمر عبر بوّابة الحوكمة (تمرّر لخُطّاف النواة). */
export function govPost(path: string): Promise<Response> {
  return fetch(path, { method: 'POST' })
}
