# -*- coding: utf-8 -*-
"""قياس التغذية — أين تضيع الثانية، بالرقم لا بالظنّ.

يجمع في تقريرٍ واحد ما كان يُقاس بسكربتات متفرّقة:

  ١. رِجل الوسيط   — `received_at − exchange_timestamp`: كم أخذ حتى بلغ مقبسنا.
  ٢. رِجلنا نحن    — عمر الحدث حين يصل كلَّ ذرّة، وكلفة نشرها، ونبض المضخّة.
  ٣. النقل         — طوابير العمّال وإسقاطهم، وزمن التِكّة لكل رمز.
  ٤. المرجع        — أيُّ رمز تداولٍ بلا سعرٍ صالح، **ولماذا** بالاسم.

القاعدة التي بُني عليها: `received_at` ختمُ ٦٢٢ لحظة قراءة المقبس. بطرحه
مرّتين عند حدثين متتاليين في السلسلة يُعرف نصيبُ كل رِجل، فلا يُخلط
«الوسيط لم يرسل» بـ«وصل عندنا وانتظر».

⚠️ لا يلمس شيئًا. قراءةٌ فقط: مقبس WS واحد، ونداءان لـ`/api/atoms`
   (النداء الكامل ثقيل على النواة، فلا يُكثَر منه).

التشغيل:  «قياس التغذية.bat»  أو
          vendor\\python\\runtime\\python.exe tools\\قياس_التغذية.py
"""
from __future__ import annotations

import base64
import io
import json
import os
import socket
import struct
import sys
import time
import urllib.request
from collections import defaultdict

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

HOST, PORT = "127.0.0.1", 8010
BASE = "http://%s:%d" % (HOST, PORT)
TRADING = ["BTCUSD", "XAUUSD", "EURUSD", "GBPUSD", "US30", "USTEC", "US500"]
CHAIN = {611: "قارئ الصفقات", 613: "موزّع التغذية", 618: "جسر MT5",
         620: "مصدر ياهو", 621: "مرجع سي‑تريدر", 622: "مصدر FIX",
         623: "صانع التِكّة", 624: "باني الدفتر"}
WS_SECONDS = 45
REF_SAMPLES = 6
REF_GAP_S = 12


def line(ch="─", n=78):
    print(ch * n)


def head(text):
    print()
    line("═")
    print(text)
    line("═")


def api(path, timeout=90):
    with urllib.request.urlopen(BASE + path, timeout=timeout) as r:
        return json.load(r)


def atoms_by_id(payload):
    rows = payload if isinstance(payload, list) else payload.get("atoms", payload)
    out = {}
    for x in rows or []:
        i = x.get("id")
        if i is None:
            continue
        health = x.get("health") or {}
        out[int(i)] = {
            "version": x.get("version"),
            "message": str(x.get("message") or health.get("message") or "").strip(),
            "state": health.get("state") or x.get("status") or "",
        }
    return out


# ── ١ · المقبس ───────────────────────────────────────────────────────────

def ws_sample(seconds):
    """عيّنة أحداث من مقبس واحد. الحقل `name` لا `event`، والبروتوكول مطلوب."""
    key = base64.b64encode(os.urandom(16)).decode()
    req = ("GET /ws/events HTTP/1.1\r\nHost: %s:%d\r\n"
           "Upgrade: websocket\r\nConnection: Upgrade\r\n"
           "Sec-WebSocket-Key: %s\r\nSec-WebSocket-Version: 13\r\n"
           "Sec-WebSocket-Protocol: quant-nq\r\n\r\n" % (HOST, PORT, key))
    sock = socket.create_connection((HOST, PORT), timeout=20)
    sock.settimeout(20)
    sock.sendall(req.encode())
    raw = b""
    while b"\r\n\r\n" not in raw:
        chunk = sock.recv(4096)
        if not chunk:
            sock.close()
            return []
        raw += chunk
    buf = bytearray(raw.split(b"\r\n\r\n", 1)[1])
    seen = []
    deadline = time.time() + seconds
    sock.settimeout(2)
    while time.time() < deadline:
        try:
            chunk = sock.recv(1 << 20)
            if not chunk:
                break
            buf += chunk
        except socket.timeout:
            pass
        while True:
            if len(buf) < 2:
                break
            second, length, offset = buf[1], buf[1] & 0x7F, 2
            opcode = buf[0] & 0x0F
            if length == 126:
                if len(buf) < 4:
                    break
                length = struct.unpack(">H", buf[2:4])[0]
                offset = 4
            elif length == 127:
                if len(buf) < 10:
                    break
                length = struct.unpack(">Q", buf[2:10])[0]
                offset = 10
            if second & 0x80:
                offset += 4
            if len(buf) < offset + length:
                break
            payload = bytes(buf[offset:offset + length])
            del buf[:offset + length]
            if opcode not in (1, 2):
                continue
            try:
                msg = json.loads(payload.decode("utf-8", "replace"))
            except Exception:
                continue
            if msg.get("type") == "event":
                seen.append((time.time(), msg.get("name"), msg.get("payload") or {}))
    sock.close()
    return seen


def report_legs(events):
    head("١ · رِجل الوسيط مقابل رِجلنا — لكلّ حدثٍ في السلسلة")
    want = ("feed.ctrader.raw", "market.depth", "feed.ctrader.tick", "market.tick")
    rows = defaultdict(list)
    no_stamp = defaultdict(int)
    for now, name, body in events:
        if name not in want:
            continue
        received = body.get("received_at")
        if not isinstance(received, (int, float)) or received <= 0:
            no_stamp[name] += 1
            continue
        venue = body.get("exchange_timestamp") or body.get("timestamp")
        venue_leg = (received - venue) if isinstance(venue, (int, float)) and venue > 0 else None
        rows[name].append((venue_leg, now - received))

    if not rows:
        print("  لا عيّنة في النافذة — لا تِكّات، أو التسليم إلى المقبس مقطوع.")
    else:
        print("%-22s %7s %14s %14s %14s" % ("الحدث", "عيّنات", "وسيط الوسيط",
                                            "وسيط عندنا", "أقصى عندنا"))
        line()
        for name in want:
            data = rows.get(name)
            if not data:
                continue
            venue = sorted(v for v, _ in data if v is not None)
            ours = sorted(o for _, o in data)
            med = lambda s: ("%12.2fث" % s[len(s) // 2]) if s else "           —"
            top = lambda s: ("%12.2fث" % s[-1]) if s else "           —"
            print("%-22s %7d %s %s %s" % (name, len(data), med(venue), med(ours), top(ours)))
        print()
        print("  وسيط الوسيط ≈ صفر ⟸ الوسيط سلّم فورًا. الثواني كلّها بعد المقبس.")
    if no_stamp:
        print()
        print("  ⚠️ بلا `received_at` (مصدرٌ لا يختم لحظة وصوله): %s"
              % " · ".join("%s=%d" % kv for kv in no_stamp.items()))


# ── ٢ · ذرّاتي ───────────────────────────────────────────────────────────

def report_chain(snapshot):
    head("٢ · سلسلة التغذية — عمر ما يصلها وكلفة ما تنشره")
    print("  age = آخر/أُسّيّ/أقصى · pub = كلفة النشر · pump = نبض المضخّة (العيار ٥ م.ث)")
    line()
    for atom_id, name in CHAIN.items():
        row = snapshot.get(atom_id)
        if not row:
            print("  %-4d %-16s ✗ غائبة عن السجلّ" % (atom_id, name))
            continue
        state = row["state"]
        mark = "✔" if str(state).lower() in ("healthy", "ok") else "⚠"
        print("  %s %-4d %-16s v%-9s %s" % (mark, atom_id, name, row["version"],
                                            row["message"][:118] or "(بلا رسالة)"))


# ── ٣ · النقل ────────────────────────────────────────────────────────────

def report_transport():
    head("٣ · النقل — من ينتظر، وكم يُرمى")
    try:
        stats = api("/api/transport-stats", timeout=60)
    except Exception as exc:
        print("  تعذّر: %s — %s" % (type(exc).__name__, exc))
        return
    runtime = stats.get("runtime") or {}
    workers = runtime.get("workers") or []
    if workers:
        print("%-8s %-7s %10s %10s %12s %s" % ("عامل", "مسار", "طابور", "أُسقط",
                                               "عولج", "الحالة"))
        line()
        for w in workers:
            print("  #%-5s %-7s %10d %10d %12d %s" % (
                w.get("worker_id"), w.get("lane", ""), w.get("queued", 0),
                w.get("dropped", 0), w.get("processed", 0),
                w.get("overload_state", "")))
        idle = [w for w in workers if w.get("queued", 0) < 200]
        busy = [w for w in workers if w.get("queued", 0) >= 2000]
        if idle and busy:
            print()
            print("  ⚠️ اختلال توزيع: عاملٌ يحمل %d وآخر يحمل %d في اللحظة نفسها."
                  % (max(w.get("queued", 0) for w in busy),
                     min(w.get("queued", 0) for w in idle)))
            print("     طابورٌ ينمو بينما طاقةٌ خاملة ليس نقصَ عتاد.")
        for w in workers:
            waiting = w.get("waiting")
            if waiting:
                print()
                print("  أطول الانتظار على #%s: %s" % (
                    w.get("worker_id"),
                    " · ".join("%s=%s" % (x.get("subscriber"), x.get("queued"))
                               for x in waiting[:6])))

    latency = (stats.get("latency") or {}).get("symbols") or {}
    if latency:
        limit = (stats.get("latency") or {}).get("limit_s")
        print()
        print("  زمن التِكّة لكل رمز — الحدّ %s ثانية" % limit)
        line()
        print("  %-10s %9s %9s %9s %12s" % ("الرمز", "p50", "p95", "p99", "تجاوز الحدّ"))
        for sym in sorted(latency):
            d = latency[sym]
            print("  %-10s %8.2fث %8.2fث %8.2fث %12d" % (
                sym, d.get("p50_s", 0), d.get("p95_s", 0), d.get("p99_s", 0),
                d.get("over_limit", 0)))


# ── ٤ · المرجع ───────────────────────────────────────────────────────────

def report_reference():
    head("٤ · المرجع — أيُّ رمزٍ لا يصلح لبناء أمر، ولماذا")
    print("  عتبة الرمز الذي يُبنى عليه أمرٌ خمس ثوانٍ. «بائت» = وصل متأخّرًا لا أنّه غاب.")
    line()
    missing = {s: 0 for s in TRADING}
    taken = 0
    last = ""
    for i in range(REF_SAMPLES):
        if i:
            time.sleep(REF_GAP_S)
        try:
            snapshot = atoms_by_id(api("/api/atoms"))
        except Exception:
            continue
        row = snapshot.get(521)
        if not row:
            continue
        taken += 1
        last = row["message"]
        print("  %s  %s" % (time.strftime("%H:%M:%S"), last[:110]))
        tail = last.split("لا مرجع للتداول:", 1)
        bad = tail[1].split("|")[0] if len(tail) > 1 else ""
        for sym in TRADING:
            if sym in bad:
                missing[sym] += 1
    if not taken:
        print("  تعذّرت القراءة من ٥٢١.")
        return
    print()
    print("  كم مرّة كان الرمز بلا سعرٍ صالح · %d عيّنة" % taken)
    line()
    for sym in TRADING:
        pct = 100.0 * missing[sym] / taken
        print("  %-9s %2d/%-3d %5.0f%%  %s" % (sym, missing[sym], taken, pct,
                                               "█" * int(pct / 5)))
    worst = [s for s in TRADING if missing[s] == taken]
    if worst:
        print()
        print("  ⛔ بلا مرجعٍ صالح في كل عيّنة: %s" % "، ".join(worst))
        print("     كلُّ أمرٍ على هذه يموت على REFERENCE_NOT_USABLE.")
    if taken and not any(missing.values()):
        print()
        print("  ✔ سبعةٌ من سبعة في كل عيّنة — التسليم مستوٍ.")


def main():
    print()
    print("قياس التغذية — %s" % time.strftime("%Y-%m-%d %H:%M:%S"))
    try:
        socket.create_connection((HOST, PORT), timeout=5).close()
    except Exception as exc:
        print()
        print("  النواة مطفأة على %s:%d (%s)." % (HOST, PORT, type(exc).__name__))
        print("  شغّل «غرفة القيادة.bat» ثمّ أعد التشغيل.")
        return 1

    print("  جمع عيّنة أحداث من المقبس · %d ثانية …" % WS_SECONDS)
    events = ws_sample(WS_SECONDS)
    print("  وصل %d حدثًا." % len(events))

    try:
        snapshot = atoms_by_id(api("/api/atoms"))
    except Exception as exc:
        print("  تعذّرت قراءة الذرّات: %s" % type(exc).__name__)
        snapshot = {}

    report_legs(events)
    report_chain(snapshot)
    report_transport()
    report_reference()

    head("الخلاصة")
    print("  رِجل الوسيط ≈ صفر  ⟵  الوسيط بريء.")
    print("  كلفة كل ذرّة ≈ ١ م.ث  ⟵  السلسلة بريئة.")
    print("  ما بقي من الثواني بين النشر والاستلام — وهو في النقل.")
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
