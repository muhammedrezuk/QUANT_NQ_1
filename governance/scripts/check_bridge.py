#!/usr/bin/env python3
"""قراءة فقط: فحص جسر MT5 قبل التشغيل.
لا ينشئ أمرًا ولا يفتح صفقة ولا يغيّر أي جدول.
"""
from __future__ import annotations

import os
import sqlite3

DEFAULT_DB = os.path.join(os.environ.get("APPDATA", r"C:\Users\NQ\AppData\Roaming"), "MetaQuotes", "Terminal", "Common", "Files", "nq_brain.db")
BLOCKED_ACCOUNT_IDS = set()
# ٢٠٢٦-٠٩-٢٣ (ختم nq): الجسر صار جداول `_v2` بعمود الحساب (الإكسبرت v3.x)، و٦١٨/
# ٦١٩ ترفضان القديمة (`LEGACY_MARKET_TABLE_FORBIDDEN`). وكان هذا الفحص يقرأ
# `account` القديم — **صفر صفوف** — فيعلن «هوية الحساب غير موجودة» والحساب في
# `account_v2` حيّ (52992818 · Raw Trading Ltd · ICMarketsSC-Demo). يُقرأ ما يقرؤه النظام.
TABLES = ("account_v2", "ticks_v2", "symbol_specs_v2", "candles_history", "positions_v2",
          "trade_events_v2", "commands")


def main() -> int:
    path = os.environ.get("NQ_BRIDGE_DB", "").strip() or DEFAULT_DB
    print("فحص جسر MT5 — قراءة فقط")
    print(f"الملف: {path}")
    try:
        con = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=5)
    except sqlite3.Error as exc:
        print(f"❌ لا أستطيع قراءة ملف الجسر: {exc}")
        return 2
    try:
        names = {row[0] for row in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        print("الجداول:")
        for table in TABLES:
            if table not in names:
                print(f"  ❌ {table}")
                continue
            try: count = con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            except sqlite3.Error: count = "؟"
            print(f"  ✅ {table}: {count}")
        if "account_v2" not in names: return 2
        rows = con.execute("SELECT account_id, broker, account_server, connected, trade_allowed, "
                           "expert_allowed FROM account_v2 ORDER BY updated_at DESC").fetchall()
        if len(rows) > 1:
            print(f"⚠ في الجسر {len(rows)} حسابات — يُعرض أحدثها تحديثًا.")
        row = rows[0] if rows else None
        if not row or not row[0]:
            print("❌ هوية الحساب غير موجودة — النظام سيبقى مقفولًا.")
            return 3
        account_id = str(row[0])
        print(f"الحساب المتصل: {account_id}")
        print(f"الوسيط/الخادم: {row[1] or '—'} / {row[2] or '—'}")
        print(f"متصل/تداول/إكسبرت: {bool(row[3])} / {bool(row[4])} / {bool(row[5])}")
        if account_id in BLOCKED_ACCOUNT_IDS:
            print("🛑 هذا الحساب موجود في قائمة المنع — توقف.")
            return 4
        if not bool(row[3]) or not bool(row[4]) or not bool(row[5]):
            print("⚠ الاتصال أو التداول الآلي غير مفعّل.")
            return 5
        print("✅ الحساب الحالي مقروء والجسر متصل. 601 سيستخدمه تلقائيًا، ويتوقف إذا تغيّر.")
        return 0
    finally:
        con.close()


if __name__ == "__main__":
    raise SystemExit(main())
