#!/usr/bin/env python3
"""طلب تفعيل أصل واحد — بختم المالك بخطوتين عبر خادم الحوكمة، ثمّ بوّابة الأوامر 901.

هذا السكربت لا يكتب أوامر ميتاتريدر، ولا يحسب لوتًا أو وقفًا، ولا يفتح شراءً ولا بيعًا:
التفعيل يضيف الأصل إلى القائمة المسموحة للحساب (468) ويضع ميزانيّته (518).

٢٠٢٦-١٠-٢٦ (فحص المشروع، ختم المالك «nq اصلح»): كان يكتب الأمر مباشرةً في قاعدة الأوامر، بلا ملخّصٍ ولا تأكيد —
متجاوزًا الختم بخطوتين الذي تمرّ به كلّ الأوامر الخطرة. صار يطلبه من خادم الحوكمة كما تطلبه اللوحة:
ملخّصٌ يُعرض، ثمّ رقمٌ يكتبه المالك بيده للتأكيد، ثمّ يكتبه الخادم لبوّابة الأوامر. وبلا خادمٍ يجيب لا يُكتب شيء.
"""
from __future__ import annotations

import argparse
import json
import os
import secrets
import sqlite3
import urllib.error
import urllib.request

DEFAULT_BRIDGE = os.path.join(os.environ.get("APPDATA", r"C:\Users\NQ\AppData\Roaming"), "MetaQuotes", "Terminal", "Common", "Files", "nq_brain.db")
KNOWN_REAL_ACCOUNT = ""
GOV_URL = "http://127.0.0.1:%s/gov/command" % os.environ.get("QUANT_GOV_PORT", "8090")
OPERATOR = "launcher"


def gov_command(body: dict) -> tuple[int, dict]:
    """طلبٌ واحد لخادم الحوكمة — يُرجع الحال والجواب، ولا يرمي."""
    request = urllib.request.Request(GOV_URL, data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
                                     method="POST", headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return response.status, json.loads(response.read() or b"{}")
    except urllib.error.HTTPError as exc:
        try:
            return exc.code, json.loads(exc.read() or b"{}")
        except ValueError:
            return exc.code, {}
    except (OSError, ValueError) as exc:
        return 0, {"error": str(exc)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("symbol", nargs="?", default="BTCUSD")
    ap.add_argument("budget", nargs="?", type=float, default=100.0)
    args = ap.parse_args()
    bridge = os.environ.get("NQ_BRIDGE_DB", "").strip() or DEFAULT_BRIDGE

    try:
        con = sqlite3.connect(f"file:{bridge}?mode=ro", uri=True, timeout=5)
        con.row_factory = sqlite3.Row
    except sqlite3.Error as exc:
        print(f"❌ لا أستطيع قراءة جسر MT5: {exc}")
        return 2
    try:
        # ٢٠٢٦-٠٩-٠٥: الإكسبرت يكتب الهوية في account_v2؛ جدول account القديم
        # بقي فارغًا (مقيس: 0 صف مقابل 1) فكانت الأداة تردّ «لا توجد هوية حساب»
        # وتوقف كل تفعيل أصل قبل أن يبدأ. نقرأ الحيّ أولًا ونُبقي القديم احتياطًا.
        account = con.execute(
            "SELECT account_id, broker, account_server, connected, trade_allowed, expert_allowed "
            "FROM account_v2 ORDER BY updated_at DESC LIMIT 1").fetchone()
        if account is None or not account["account_id"]:
            account = con.execute(
                "SELECT account_id, broker, account_server, connected, trade_allowed, expert_allowed "
                "FROM account WHERE id=1").fetchone()
        if account is None or not account["account_id"]:
            print("❌ لا توجد هوية حساب في الجسر.")
            return 3
        account_id = str(account["account_id"])
        print(f"الحساب: {account_id} · {account['broker'] or '—'} · {account['account_server'] or '—'}")
        if account_id == KNOWN_REAL_ACCOUNT:
            print("🛑 هذا الحساب الحقيقي المعروف — توقّف.")
            return 4
        if not bool(account["connected"]):
            print("⚠ MT5 غير متصل.")
            return 5
        if not bool(account["trade_allowed"]) or not bool(account["expert_allowed"]):
            print("⚠ التداول الآلي مقفول في MT5.")
            return 6
    finally:
        con.close()

    if not args.symbol or args.budget <= 0:
        print("اكتب رمزًا وميزانية موجبة.")
        return 7
    payload = {"account_id": account_id, "symbol": args.symbol.upper(), "budget": float(args.budget)}
    status, first = gov_command({"action": "activate_asset", "payload": payload, "operator": OPERATOR})
    if status == 0:
        print("❌ لا يُكتب الأمر: خادم الحوكمة لا يجيب — الأمر لا يمرّ إلّا بالختم، والختم في الخادم.")
        return 8
    if status != 200 or not first.get("token"):
        print("❌ رفض الخادم الطلب: %s" % (first.get("error") or status))
        return 9
    print("")
    print("⚠️ أمر خطر — " + str(first.get("summary") or "تفعيل أصل"))
    code = "%04d" % secrets.randbelow(10000)
    typed = input("للتأكيد اكتب الرقم %s ثمّ اضغط الإدخال، أو اتركه فارغًا للإلغاء (صالح %s ثانية): "
                  % (code, first.get("ttl_s", 60))).strip()
    if typed != code:
        print("أُلغي — لم يُكتب شيء.")
        return 10
    status, second = gov_command({"action": "activate_asset", "payload": payload, "operator": OPERATOR,
                                  "confirm": first["token"]})
    if status != 200:
        print("❌ لم يُكتب الأمر: %s" % (second.get("error") or status))
        return 11
    print("✅ " + str(second.get("message") or "انكتب الأمر لبوّابة الأوامر 901"))
    print(f"   {payload['symbol']} · ميزانيّة المخاطرة ${payload['budget']:.2f} · الحساب {account_id}")
    print("التفعيل يضيف الأصل إلى القائمة المسموحة ويضع ميزانيّته، ولا يفتح صفقة. ويحتاج النواة شغّالة.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
