#!/usr/bin/env python3
"""يولّد نسختين آمتين للترجمة في MetaEditor من mt5/QUANT_NQ.mq5 (الأصل لا يُمَسّ).
   ١) QUANT_NQ.utf16.mq5  : نفس الرموز حرفيًّا — UTF-16LE + BOM + CRLF (المرسوم لدى MetaEditor)
   ٢) QUANT_NQ.ascii.mq5  : ASCII صرفة — التعليقات تُعرَّب نقلرةً، والنصوص تُترجم بجدول مضمون
"""
from pathlib import Path
import re, sys

SRC = Path("sys/../mnt").parent  # placeholder, replaced below
ROOT = Path("/home/user/QUANT_NQ")
SRC = ROOT / "mt5" / "QUANT_NQ.mq5"

TRANS = {
    "??? ? الجسر ???": "--- BRIDGE ---", "??? ? الرموز ???": "--- SYMBOLS ---",
    "??? ? الهوية ???": "--- IDENTITY ---", "??? ? التغذية ???": "--- FEED ---",
    "??? ? العمق (DOM) ???": "--- DEPTH (DOM) ---", "??? ? الشاشة ???": "--- SCREEN ---",
    "??? ? الأمان ???": "--- SAFETY ---",
    "—": "-", "": "", " – ": " - ", "«": '"', "»": '"', "…": "...",
    "لا شيء": "none", "التداول مطفأ": "TRADING DISABLED", "الإكسبرت ممنوع": "EA DISABLED",
    "? [DEPTH] تعذّر الاشتراك بعمق %s (قد لا يوفّره الوسيط)":
        "[DEPTH] cannot subscribe depth %s (broker may not provide it)",
    "حي": "LIVE", "بايثون": "PYTHON", "الحساب": "ACCOUNT", "العمق": "DEPTH", "مطفأ": "OFF",
    "محمد رزوق": "Mohammad Rzouk",
    "QUANT_NQ — الإكسبرت الواحد الشامل (v3.12 · شموع CopyRates لكل فريم الشارت)":
        "QUANT_NQ - all-in-one EA (v3.12, CopyRates candles for every chart timeframe)",
    "??? ? الجسر ???": "--- BRIDGE ---", "??? ? الرموز ???": "--- SYMBOLS ---",
    "??? ? الهوية ???": "--- IDENTITY ---", "??? ? التغذية ???": "--- FEED ---",
    "??? ? العمق (DOM) ???": "--- DEPTH (DOM) ---", "??? ? الشاشة ???": "--- SCREEN ---",
    "??? ? الأمان ???": "--- SAFETY ---",
    "%.1f ث": "%.1f s", "%d ث": "%d s", "%d د": "%d m", "%d س": "%d h",
    "شراء": "BUY", "بيع": "SELL", "فتح": "OPEN", "إغلاق": "CLOSE", "إغلاق جزئي": "PARTIAL",
    "تعديل الوقف": "MODIFY SL", "تعديل الهدف": "MODIFY TP", "أمر معلَّق": "PENDING",
    "حذف معلَّق": "DEL PENDING", "تم": "DONE", "بلا حجم": "NO SIZE", "جهة فاسدة": "BAD SIDE",
    "معطيات فاسدة": "BAD DATA", "بلا وقف خسارة": "NO STOP", "بلا سعر": "NO PRICE",
    "لا مركز": "NO POSITION", "بلا تأكيد صفقة": "NO DEAL ACK",
}

def to_ascii(text: str) -> tuple[str, int]:
    """يبدّل داخل النصوص الحرفية فقط بجدول TRANS، وما لا يُعرف يُنقلَر بحروف آمنة."""
    n = 0
    def lit_repl(m):
        nonlocal n
        body = m.group(1)
        if all(ord(c) < 128 for c in body):
            return m.group(0)
        n += 1
        new = body
        for k, v in TRANS.items():
            new = new.replace(k, v)
        new = re.sub(r"[^\x20-\x7e]", "", new)          # ما تبقّى (غالبًا تشكيل/أقواس)
        new = re.sub(r"\s{2,}", " ", new).strip()
        return '"' + new + '"'
    out_lines = []
    for line in text.split("\n"):
        code, sep, comment = line.partition("//")
        code = re.sub(r'"((?:[^"\\]|\\.)*)"', lit_repl, code)
        if comment:
            c = re.sub(r"[^\x20-\x7e]", "", comment)
            c = re.sub(r"[ ]{2,}", " ", c)
            code = code + sep + c.rstrip()
        out_lines.append(code)
    return "\n".join(out_lines), n

def main() -> int:
    src = SRC.read_text(encoding="utf-8")
    lf = src.replace("\r\n", "\n")
    # ١) UTF-16LE + BOM + CRLF
    u16 = ROOT / "mt5" / "QUANT_NQ.utf16.mq5"
    u16.write_bytes(b"\xff\xfe" + lf.replace("\n", "\r\n").encode("utf-16-le"))
    # ٢) ASCII صرفة + CRLF
    body, touched = to_ascii(lf)
    left = sum(1 for c in body if ord(c) > 127)
    if left:
        print(f"🛑 بقي {left} حرفًا غير-ASCII — أوقفتُ التوليد"); return 1
    head = ("// ASCII-safe build of QUANT_NQ.mq5 (Arabic comments transliterated, labels translated).\n"
            "// Source of truth stays mt5/QUANT_NQ.mq5. If MetaEditor still fails, compile THIS file.\n")
    asc = ROOT / "mt5" / "QUANT_NQ.ascii.mq5"
    asc.write_bytes((head + body).replace("\r\n", "\n").replace("\n", "\r\n").encode("ascii"))
    # تقرير السلامة
    def sig(t):
        code = "\n".join(l.split("//")[0] for l in t.split("\n"))
        return dict(lines=t.count("\n") + 1, braces=code.count("{") - code.count("}"),
                    paren=code.count("(") - code.count(")"),
                    funcs=len(re.findall(r'^\s*(?:void|int|bool|double|string|ulong|datetime|long)\s+\w+\s*\(', code, re.M)),
                    calls=len(re.findall(r'[A-Za-z_]\w*\s*\(', re.sub(r'"[^"]*"|//.*', "", code))))
    s0, s1 = sig(lf), sig(body)
    print("النسخة 1:", u16.name, len(u16.read_bytes()), "ب · BOM+يفتح UTF-16:",
          u16.read_bytes()[:2] == b"\xff\xfe" and u16.read_bytes().decode("utf-16")[:2] == "/*")
    print("النسخة 2:", asc.name, len(asc.read_bytes()), "ب · نصوص مُبدَّلة:", touched)
    print("توقيع الأصل:", s0); print("توقيع ASCII:", s1)
    ok = (s0["braces"] == s1["braces"] == 0 and s0["paren"] == s1["paren"] == 0
          and s0["funcs"] == s1["funcs"] and s0["calls"] == s1["calls"])
    print("البنية محفوظة (أقواس/دوال/استدعاءات):", "✓" if ok else "🛑")
    return 0 if ok else 2

sys.exit(main())
