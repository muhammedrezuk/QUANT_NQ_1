"""خادم الحوكمة — الباك-إند (البنية التحتية · القطعة ٢).

طبقة ٢ · عملية منفصلة تمامًا عن النواة المختومة (لا تستوردها ولا تلمسها — العزل، ١٤ §٠).
تقرأ النواة عبر HTTP المحلي (:8010) قراءةً فقط، تُثري كل ذرة باسمها العربي (من اسم مجلّدها)
وحالتها المترجَمة (طبقة الترجمة، ١٤ §٩)، وتقدّم واجهة React المبنيّة (dist) + منافذ القراءة
والتحكّم لطبقة النقل بالواجهة. لا تخزّن شيئًا (الحوكمة مو مصدر الحقيقة، ١٤ §١٠). لو ماتت:
النواة والتداول يكملان.

تشغيل (ويندوز/PowerShell، في الواجهة):
    cd C:\\Users\\NQ\\QUANT_NQ; $env:PYTHONUTF8=1; .\\venv\\Scripts\\python.exe governance\\server.py
ثم المتصفّح على http://127.0.0.1:8090  (النواة لازم تكون شغّالة: .\\venv\\Scripts\\python.exe scripts\\run_core.py)
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import secrets
import socket
import subprocess
import sys
import time
import tempfile
import threading
import functools
from datetime import datetime
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import sqlite3
from pathlib import Path
from urllib.parse import parse_qs, urlparse

try:
    import yaml
    from jsonschema import Draft202012Validator
except Exception:  # pragma: no cover
    yaml = None
    Draft202012Validator = None

ROOT = Path(__file__).resolve().parent
# One governance process is started per market. The market is selected by the
# wrapper, while the browser sees the same UI and the same /gov API shape.
MARKET = str(os.environ.get("QUANT_GOV_MARKET", "forex")).strip().lower()

# ٢٠٢٦-٠٩-٠٣ (فحص جذور المسارات): كان الجذر يُحسب يدويًّا بـ`ROOT.parent/<runtime>`
# بلا تحقّق، فتقرأ اللوحة مجلّدًا بلا `var` وتعلن `available=false` على قاعدة موجودة
# بينما المحرّك يكتب في ملفّ آخر. المصدر الوحيد الآن `shared/runtime_paths.py`
# (يُستورد بعد إضافة جذر المشروع إلى sys.path أدناه)، ويُلقي خطأً صريحًا بدل
# الرجوع الصامت إلى `PROJECT_ROOT/var`.
def _resolve_runtime_var(*parts: str) -> Path:
    import sys as _sys
    _cand = str(ROOT.parent)
    if _cand not in _sys.path:
        _sys.path.insert(0, _cand)
    from shared.runtime_paths import runtime_var
    return runtime_var(*parts, code_root=ROOT.parent, market=MARKET)


def _resolve_runtime_root() -> Path:
    import sys as _sys
    _cand = str(ROOT.parent)
    if _cand not in _sys.path:
        _sys.path.insert(0, _cand)
    from shared.runtime_paths import runtime_root
    return runtime_root(code_root=ROOT.parent, market=MARKET)


def _resolve_settings_db() -> Path:
    import sys as _sys
    _cand = str(ROOT.parent)
    if _cand not in _sys.path:
        _sys.path.insert(0, _cand)
    from shared.runtime_paths import settings_db_path
    return settings_db_path(code_root=ROOT.parent, market=MARKET)
# سوق واحد — الفوركس (حكم المالك 2026-09-07، ونُفِّذ مسح قسم الكريبتو
# 2026-09-09 بأمره «امسح»). لا فرع ثانٍ ولا منافذ 8020/8091 ولا atoms_crypto.
if MARKET != "forex":
    raise RuntimeError("QUANT_GOV_MARKET must be forex — سوق واحد بحكم المالك")
CORE = os.environ.get("QUANT_GOV_CORE", "http://127.0.0.1:8010")
PORT = int(os.environ.get("QUANT_GOV_PORT", "8090"))
ATOMS_DIR = ROOT.parent / "atoms"
DIST = ROOT / "ui" / "built"                          # واجهة React المبنيّة (تُقدَّم أوفلاين)
RUNTIME_ROOT = _resolve_runtime_root()           # <runtime> — مقياس المالك
DATA_ROOT = _resolve_runtime_var()               # <runtime>/var — لا حساب يدويّ
MARKET_DB = _resolve_runtime_var("store", "market_data.db")   # تكّات مخزّنة → شموع
COMMANDS_DB = _resolve_runtime_var("governance", "commands.db")  # جسر بوّابة الأوامر
# بند ٤: مسار سجلّ المعايرة = عقد ParameterRegistry نفسه (بما فيه
# QUANT_ANALYSIS_SETTINGS_DB) — لا اشتقاق يدويّ ولا تكرار لمنطق الجذر هنا.
ANALYSIS_SETTINGS_DB = _resolve_settings_db()
TILT_RULES_DB = _resolve_runtime_var("store", "tilt_rules.db")
DECISIONS_DB = _resolve_runtime_var("store", "decisions.db")
CARDS_DB = _resolve_runtime_var("store", "trade_cards.db")   # دفتر البطاقات (٤٦٥)
# إصلاح ف-1 (ورقة ٤٠ · ديفرق ورقة ٣٩ بند ٤): للفوركس، صفحتا الأخبار والصفقات
# تقرآن nq_brain.db حيث يكتب الـEA فعليًّا (مجلّد MetaTrader المشترك) — لا
# bridge.db المعزولة الفارغة غير الموجودة أصلًا (كانت تجعل /gov/news يكذب:
# available:false رغم وصول مئات الأخبار — مقاس بورقة ٣٨ بند ٤).
_news_raw = os.environ.get("NQ_NEWS_DB") or str(
    Path(os.environ.get("APPDATA", "")) / "MetaQuotes" / "Terminal"
    / "Common" / "Files" / "nq_brain.db")
TRADE_DB = Path(_news_raw)
# على لينكس مسار ويندوز C:\... يصير اسم ملف بجذر المشروع — نرفضه.
# ويندوز يبقى على مسار الـEA (لا يُنكر).
if os.name != "nt" and (
    not TRADE_DB.is_absolute() or _news_raw.startswith("C:") or "AppData" in TRADE_DB.name
):
    TRADE_DB = _resolve_runtime_var("nq_brain.db")
LOGS_DIR = _resolve_runtime_var("logs")

# جذر المشروع على المسار: الخادم يُشغَّل ملفًّا داخل governance فلا يرى حزم
# الجذر (shared/…) بدون هذا. كان يُزرع داخل الدوال عند الحاجة؛ صار هنا لأنّ
# مصدري الحقيقة أدناه يُستوردان مرّة عند الإقلاع.
if str(ROOT.parent) not in sys.path:
    sys.path.insert(0, str(ROOT.parent))
# توحيد المصدر (بند ٢٢ حزمة أ — أ٧): أوزان المحلّلين الافتراضية ومعرّفات
# الأقسام من عقد التحليل الحي نفسه — كانت هنا خريطة يدوية قديمة (trend 15،
# momentum 10…) تخالف حكم التساوي المختوم ٢٠٢٦-٠٨-٢٠ (100/15 لكل محلّل).
from shared.live_analysis import DEFAULT_WEIGHTS as _ANALYSIS_DEFAULT_WEIGHTS
from shared.live_analysis import SECTION_IDS as _SECTION_IDS
# أسماء المُعامِلات المعلنة (سجلّ المُعامِلات §٥٢) — للتحقّق قبل بوّابة ٩٠١.
from shared.parameter_registry import DECLARED as _DECLARED_PARAMETERS


_IMPACT_RANK = {"NONE": 0, "LOW": 1, "MEDIUM": 2, "HIGH": 3}


def calendar_rows(currency: str, min_impact: str) -> list:
    """أحداث اليوم من تقويم ميتاتريدر عبر جسر التداول — قراءة فقط.

    المصدر نفسه الذي يقرأه بوت الأخبار: جدول `calendar` الذي يكتبه الإكسبرت
    (`WriteCalendar`)، وفيه العنوان بالعربي والعملة والأهمية والمتوقّع والسابق
    والفعلي. لا مفتاح API ولا مصدر خارجي.
    """
    if not TRADE_DB.is_file():
        return []
    floor = _IMPACT_RANK.get(str(min_impact or "").upper(), 0)
    now = time.time()
    start = now - (now % 86400)                      # منتصف ليل بتوقيت UTC
    try:
        con = sqlite3.connect(f"file:{TRADE_DB}?mode=ro", uri=True, timeout=3)
        con.row_factory = sqlite3.Row
        rows = con.execute(
            "SELECT id,title,country,currency,impact_level,scheduled_at,"
            "actual,forecast,previous FROM calendar "
            "WHERE scheduled_at >= ? AND scheduled_at < ? ORDER BY scheduled_at ASC",
            (start, start + 86400)).fetchall()
        con.close()
    except Exception:
        return []
    out = []
    for r in rows:
        cur = str(r["currency"] or "").upper()
        if currency and currency != "ALL" and cur != currency:
            continue
        if _IMPACT_RANK.get(str(r["impact_level"] or "").upper(), 0) < floor:
            continue
        out.append({
            "id": str(r["id"]), "title": str(r["title"] or ""),
            "country": str(r["country"] or ""), "currency": cur,
            "impact": str(r["impact_level"] or "").upper(),
            # الطابع يصل ناقصًا ثانيةً أحيانًا (15:29:59) — التقريب لأقرب دقيقة
            "epoch": round(float(r["scheduled_at"] or 0) / 60.0) * 60,
            "actual": str(r["actual"] or ""), "forecast": str(r["forecast"] or ""),
            "previous": str(r["previous"] or "")})
    return out


NEWS_AR_CACHE = _resolve_runtime_var("governance", "news_ar.json")
_news_ar: dict | None = None
_NEWS_AR_BUDGET = 5          # كم عنوانًا جديدًا يُترجَم في الطلب الواحد


def _news_ar_map() -> dict:
    """ذاكرة الترجمة على القرص — العنوان يُترجَم مرّة واحدة بالعمر."""
    global _news_ar
    if _news_ar is None:
        try:
            _news_ar = json.loads(NEWS_AR_CACHE.read_text(encoding="utf-8"))
        except Exception:
            _news_ar = {}
    return _news_ar


def _news_ar_save() -> None:
    try:
        NEWS_AR_CACHE.parent.mkdir(parents=True, exist_ok=True)
        NEWS_AR_CACHE.write_text(json.dumps(_news_ar_map(), ensure_ascii=False),
                                 encoding="utf-8")
    except OSError:
        pass


_tr_lock = threading.Lock()
_tr_busy = False
_tr_warned = False       # يُعلَن غياب مكتبة الترجمة مرّة واحدة لا كل طلب


def _has_arabic(text: str) -> bool:
    """هل في النصّ حرف عربيّ؟ — شرط قبول أي ترجمة قبل تخزينها للعمر."""
    return any("؀" <= ch <= "ۿ" or "ﭐ" <= ch <= "﻿"
               for ch in text)


def _translate_worker(missing: list) -> None:
    """يترجم بالخلفية ويملأ الذاكرة — لا يحبس أي طلب.

    القياس الذي فرض هذا: الترجمة نداء شبكة (~ثانية للعنوان)، وترجمة خمسة
    داخل الطلب كانت تُجمّد اللوحة خمس ثوانٍ لكل تحديث.
    """
    global _tr_busy, _tr_warned
    try:
        from deep_translator import GoogleTranslator
    except Exception as exc:
        # ٢٠٢٦-٠٨-٣١ (ختم NQ): كان `except Exception: return` صامتًا تمامًا.
        # `deep_translator` لم تكن منصَّبة ولا مذكورة في `requirements.txt`،
        # فبقيت كل العناوين إنكليزيّة بلا أيّ أثر في أيّ سجلّ — والمالك لا
        # يقرأ الإنكليزيّة. حارس بلا مفتاح. يُعلَن مرّة واحدة ولا يُغرق السجلّ.
        if not _tr_warned:
            _tr_warned = True
            print("[حوكمة] ⚠️ ترجمة العناوين معطّلة — %s: %s. "
                  "نصّب: venv\\Scripts\\python.exe -m pip install deep-translator"
                  % (type(exc).__name__, exc), flush=True)
        with _tr_lock:
            _tr_busy = False
        return
    cache, changed = _news_ar_map(), False
    for src in missing[:_NEWS_AR_BUDGET]:
        try:
            out = GoogleTranslator(source="auto", target="ar").translate(src[:4500])
        except Exception:
            continue
        # ٢٠٢٦-٠٨-٣١ (ختم NQ): الشرط القديم كان «غير فارغ ويختلف عن الأصل»،
        # فمرّت صفحة خطأ من الخدمة نصُّها «Error 500 (Server Error)!!1…» وخُزّنت
        # كترجمة دائمة (الذاكرة تُخزّن مرّة للعمر) — قناع لا قاموس. الترجمة إلى
        # العربيّة يجب أن تحمل حرفًا عربيًّا واحدًا على الأقلّ؛ وما لا يحمله
        # يُرفض ولا يُخزَّن، فتُعاد محاولته لاحقًا.
        if out and out.strip() and out.strip() != src.strip() and _has_arabic(out):
            cache[src] = out.strip()
            changed = True
    if changed:
        _news_ar_save()
    with _tr_lock:
        _tr_busy = False


def translate_headlines(rows: list) -> list:
    """يضيف `headline_ar` من الذاكرة فورًا، ويطلق ترجمة الناقص بالخلفية.

    الردّ لا ينتظر الشبكة أبدًا: ما تُرجم يظهر الآن، وما لم يُترجم بعد يبقى
    بعنوانه الأصلي ويظهر مترجَمًا بالتحديث التالي (كل ٣٠ ثانية).
    وإن غابت المكتبة أو سقطت الشبكة يبقى الأصل كما هو — لا ترجمة مخترعة.
    """
    global _tr_busy
    cache = _news_ar_map()
    missing = []
    for r in rows:
        src = r.get("headline") or ""
        r["headline_ar"] = cache.get(src, "")
        if src and not r["headline_ar"]:
            missing.append(src)
    if missing:
        with _tr_lock:
            start = not _tr_busy
            if start:
                _tr_busy = True
        if start:
            threading.Thread(target=_translate_worker, args=(missing,), daemon=True).start()
    return rows


def news_rows(limit: int) -> list:
    """آخر الأخبار من جسر التداول — قراءة فقط."""
    if not TRADE_DB.is_file():
        return []
    try:
        con = sqlite3.connect(f"file:{TRADE_DB}?mode=ro", uri=True, timeout=3)
        con.row_factory = sqlite3.Row
        cols = {row[1] for row in con.execute("PRAGMA table_info(news)")}
        # العمودان مضافان حديثًا — نطلبهما فقط إن وُجدا كي لا يسقط المنفذ
        # على قاعدة قديمة (الغياب يُعلَن غيابًا، لا يُسقِط الصفحة).
        extra = "".join(f",{c}" for c in ("summary", "relevance") if c in cols)
        rows = con.execute(
            "SELECT id,headline,link,source,sentiment_score,impact_level,"
            f"published_at,written_at{extra} FROM news "
            "ORDER BY published_at DESC LIMIT ?", (limit,)).fetchall()
        con.close()
    except Exception:
        return []
    out = []
    for r in rows:
        keys = r.keys()
        out.append({"id": r["id"], "headline": str(r["headline"] or ""),
                    "link": str(r["link"] or ""), "source": str(r["source"] or ""),
                    "sentiment": r["sentiment_score"], "impact": r["impact_level"],
                    "published_at": r["published_at"],
                    "summary": str(r["summary"] or "") if "summary" in keys else "",
                    "relevance": str(r["relevance"] or "") if "relevance" in keys else ""})
    return out


def trade_history(symbol: str, limit: int) -> list:
    """تاريخ الصفقات المعزول بالحساب من جسر التداول الإصدار الثاني — قراءة فقط."""
    if not TRADE_DB.is_file():
        return []
    try:
        con = sqlite3.connect(f"file:{TRADE_DB}?mode=ro", uri=True, timeout=3)
        con.row_factory = sqlite3.Row
        q = ("SELECT account_id,event_type,ticket,symbol,side,volume,entry_price, "
             "exit_price,open_time,close_time,reason,profit,commission,swap,fee "
             "FROM trade_events_v2 ")
        args: tuple = ()
        if symbol:
            q += "WHERE symbol = ? "
            args = (symbol,)
        q += "ORDER BY id DESC LIMIT ?"
        rows = [dict(r) for r in con.execute(q, args + (limit,))]
        con.close()
        return rows
    except Exception:
        return []


def realized_totals(db_path: Path | None = None) -> dict:
    """المحقَّق الكلّيّ لكلّ حساب من سجلّ صفقات الجسر — الربح ومعه العمولة والتبييت والرسوم. قراءة فقط.

    ٢٠٢٦-١٠-٢٦ (فحص المشروع، ختم «nq اصلح»): «المحقَّق الكلّي» في «شو صاير» كان من 658، وهي تجمع `profit` وحده —
    فعرض −10,159.25 والوسيط نفسه يقول: ربح −10,134.56 · عمولة −852.49 · تبييت −60.30، أي خسارةٌ أكبر بنحو 913$.
    العمولة تُكتب على صفّ الفتح أيضًا (الوسيط يأخذها عند الدخول)، فتُجمع من كلّ الصفوف، لا من الإغلاق وحده.
    القاعدة الغائبة أو غير المقروءة تُعلن غيابًا (`available=false`) — لا صفر.
    """
    path = Path(db_path) if db_path is not None else TRADE_DB
    if not path.is_file():
        return {"available": False, "accounts": {}}
    try:
        con = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=3)
        try:
            rows = con.execute(
                "SELECT account_id, COUNT(*), COALESCE(SUM(profit),0), COALESCE(SUM(commission),0), "
                "COALESCE(SUM(swap),0), COALESCE(SUM(fee),0) FROM trade_events_v2 GROUP BY account_id").fetchall()
        finally:
            con.close()
    except Exception:  # noqa: BLE001 — قاعدةٌ مقفلة أو جدولٌ غائب: غيابٌ يُعلن
        return {"available": False, "accounts": {}}
    accounts = {}
    for account, count, profit, commission, swap, fee in rows:
        accounts[str(account)] = {"events": int(count), "profit": round(float(profit), 2),
                                  "commission": round(float(commission), 2), "swap": round(float(swap), 2),
                                  "fee": round(float(fee), 2),
                                  "net": round(float(profit) + float(commission) + float(swap) + float(fee), 2)}
    return {"available": True, "accounts": accounts}

# ── بوّابة الأوامر الخطرة (١٤ §٨ · ورقة ١٦): تأكيد بخطوتين، ثم كتابة بالجسر ──
_DANGER_COMMANDS = {
    "halt": "إيقاف طارئ شامل — كل إرسال الأوامر للمنصّة يتوقّف فورًا",
    "kill_switch_reset": "تصفير قاطع الأمان — يرفع الإيقاف وترجع البوّابات تشتغل",
    # ٢٠٢٦-١٠-٢٦ (فحص المشروع، ختم «nq اصلح»): كان «سيطلب شراءً وبيعًا محايدين» — نصّ المحرّك الدائم المؤرشف، ويصف تحوّطًا
    # يمنعه القانون 13. والحيّ: 901 تنشر `perpetual.asset.activate` ولا يسمعه إلّا 468 (القائمة المسموحة) و518 (الميزانيّة).
    "activate_asset": "تفعيل أصل — يُضاف إلى القائمة المسموحة لهذا الحساب وتُوضع ميزانيّة مخاطرته. لا يُفتح بهذا الأمر شراءٌ ولا بيع",
    # ٢٠٢٦-١٠-٠٢ (ختم المالك «صلح كامل nq»): كان النصّ يَعِد بمسح «مفعّل» في 576 المؤرشفة؛
    # الآن 901 v2.9.0 تنشر معه أمرَ أصلٍ PAUSE فتُخرجه 468 من القائمة المسموحة ويجمّده 519.
    "deactivate_asset": "إلغاء تفعيل أصل — يُخرجه من القائمة المسموحة لهذا الحساب ويجمّد نطاقه — العودة بزرّ «متابعة»",
    "execution_gate": "فتح أو إيقاف بوّابة التنفيذ — الأمر الصالح يصل المنصّة أو يُرفض",
    "asset_control": "تحكم في حالة أصل واحد عبر بوابة الأوامر — بلا شراء ولا بيع مباشر",
    "analysis_setting": "تعديل إعداد محلل مستقل لهذا الحساب والأصل — العمق والعيار والوزن فقط",
    "decision_setting": "تعديل عيار قرار محكوم (عتبة الحياد، المشاركة، الأوزان…) — قيمة دقيقة من سجلّ المُعامِلات المعتمد",
    "parameter_approve": "اعتماد مُعامِل معلن من سجلّ المُعامِلات — القيمة تصير رسمية بمصدر مالك ونسخة جديدة (حكم ق١: الأولية العادلة تبقى سارية حتى هذا الاعتماد)",
    "tilt_rule": "قاعدة ترجيح لمحرّك 580 (ق١٠ §١٨–٢١) — منحنى نقاط (عتبة ← مقدار) لحقل واحد من مخرجات القرار؛ المحرّك يطبّقها بمخزنه بعد تنفيذ بوّابة ٩٠١",
    "adaptation_switch": "مفتاح التكيّف (860) — ON يعيد التكيّف بعد إيقافه وOFF يوقفه؛ كان طريقًا باتّجاه واحد بلا ناشر (ختم nq ٢٠٢٦-٠٨-٢٥)",
    # ٢٠٢٦-١٠-٢٣ (ختم المالك «NQ» على القوانين 7–10): حدود الحساب بيد المالك — 509 يطبّقها ويردّ الخطأ بنفسه.
    "account_limits": "حدود الحساب — الرصيد الابتدائيّ ونسب الأزواج والحدّ اليوميّ الشامل والتراجع الكلّيّ، أو إعادة التداول بعد التراجع الكلّيّ",
    # ٢٠٢٦-١٠-٢٦ (فحص المشروع، ختم «nq اصلح»): زرّ «وقّف» كان يوقف أيّ ذرّة بنقرة، ومنها حدود الحساب والخطوط الحمراء.
    # الإيقاف بيد النواة وحدها، ولا أمر له في 901؛ فالختم هنا بالخطوتين نفسيهما، ثمّ يوقفها الخادم ويكتبها في سجلّ الأوامر.
    "atom_stop": "إيقاف ذرّةٍ حرجة — يسقط ما تحرسه حتّى تُشغَّل بيدك من جديد",
}
# الذرّات التي لا تُوقف إلّا بختم المالك، وما يسقط بإيقافها — لملخّص التأكيد بخطوتين.
CRITICAL_ATOMS: dict[int, tuple[str, str]] = {
    509: ("حدود الحساب", "تسقط حدود كلّ زوج والحدّ اليوميّ الشامل والتراجع الكلّيّ، فلا يُغلق المفتوح عند بلوغها (القوانين 8–10)"),
    516: ("قاطع الأمان", "يسقط الحارس الثاني لخسارة اليوم وعدد الصفقات والخسائر المتتالية"),
    552: ("مدقّق الأمر", "لا يُدقَّق أمرٌ فلا يصل الوسيط أمرٌ جديد، والوقف مع كلّ أمرٍ يُفحص هنا"),
    555: ("طالب أمر الدخول", "لا يُطلب دخولٌ جديد، وحرّاس الدخول كلّها فيه: الخبر والوقت والانتظار والحدود"),
    565: ("الخطوط الحمراء", "لا يُغلق المفتوح عند الخطّ الأحمر ولا عند نهاية نافذة أصله (القانونان 19 و20)"),
    601: ("كاتب الجسر", "لا يُكتب للوسيط أمرٌ، ومنها أوامر الإغلاق عند الحدود والخطّ الأحمر"),
    618: ("جسر ميتاتريدر 5", "لا يصل سعرٌ ولا حسابٌ ولا مراكز، فتعمى الحرّاس كلّها"),
    901: ("بوّابة الأوامر", "لا يصل أمرٌ منك إلى المنظومة، ومنه الإيقاف الطارئ"),
}
# الحقول الستّة القابلة للترجيح بالعربي (مفردات ق١٠ §٣) — لملخّص التأكيد بخطوتين.
# state وweight ليسا هنا عمدًا: حاجز وعامل مساهمة، لا سلّما نقاط.
_TILT_FIELD_AR = {
    "direction": "القيمة الاتجاهية",
    "strength": "القوة",
    "confidence": "الثقة",
    "current_depth": "العمق الحالي",
    "required_depth": "العمق المطلوب",
    "ratio": "النسبة",
}
_TILT_SIDE_AR = {"up": "صعودًا", "down": "هبوطًا", "abs": "بالقيمة المطلقة"}
_TILT_MAX_POINTS = 12


def _tilt_points_valid(points) -> bool:
    """نقاط منحنى الترجيح: حتى 12 زوجًا [عتبة، مقدار] أرقامًا منتهية (لا bool)
    وعتباتها تصاعدية تمامًا. القائمة الفارغة شرعية (مسح منحنى). نفس تحقّق
    بوّابة ٩٠١ حرفيًّا — الخادم حاجز أول لا بديل عن حاجز الذرة."""
    if not isinstance(points, list) or len(points) > _TILT_MAX_POINTS:
        return False
    thresholds = []
    for point in points:
        if not isinstance(point, list) or len(point) != 2:
            return False
        for number in point:
            if isinstance(number, bool) or not isinstance(number, (int, float)):
                return False
            if number != number or number in (float("inf"), float("-inf")):
                return False
        thresholds.append(float(point[0]))
    return all(b > a for a, b in zip(thresholds, thresholds[1:]))
# أسماء المُعامِلات الستّة المعلنة بالعربي — لملخّص التأكيد بخطوتين فقط
_PARAMETER_AR = {
    "MOVEMENT_FLOOR": "أرضية الحركة",
    "ABNORMALITY_GAIN": "كسب الشذوذ",
    "INTEGRITY_BLEND": "مزيج التماسك",
    "CONFIDENCE_BLEND": "مزيج الثقة",
    "DEPTH_BLEND": "مزيج العمق",
    "STALE_AFTER_S": "مهلة النضارة (ثوانٍ)",
}
_CONFIRM_TTL_S = 60.0
_CMD_SCHEMA = (
    "CREATE TABLE IF NOT EXISTS commands ("
    "id INTEGER PRIMARY KEY AUTOINCREMENT, "
    "action TEXT NOT NULL, "
    "operator TEXT NOT NULL, "
    "requested_at REAL NOT NULL, "
    "status TEXT NOT NULL DEFAULT 'PENDING', "
    "executed_at REAL, payload_json TEXT)")
_pending_confirms: dict[str, tuple[str, str, str, float]] = {}  # token -> (action,payload,operator,time)
_CONFIRM_LOCK = threading.Lock()
_CONFIG_LOCK = threading.Lock()
_MAX_BODY_BYTES = 1_048_576
GOV_API_KEY = os.environ.get("QUANT_GOV_API_KEY", "").strip()
# ٢٠٢٦-١٠-٠٢ (ختم المالك «صلح كامل nq»): أسماء الحلقة المحلّيّة ومنفذ اللوحة العلنيّ
# (المحور الموحّد يمرّر `Origin` اللوحة 8090 إلى هذا الخادم على 8092).
_LOOPBACK_NAMES = ("127.0.0.1", "localhost")
_PANEL_PORT = 8090


# ── النسخة الاحتياطية الموحّدة (ورقة ٠٩ مكوّن ٧): لقطة النظام كله بزر — نقطة رجوع ──
# تلقط: الذرات + النواة + الإعدادات + الحوكمة + الورق + السكربتات. تستثني بيانات السوق
# الضخمة (var ~445MB — تُعاد من مصادرها) و venv/node_modules (تُعاد بالتثبيت).
BACKUPS_DIR = _resolve_runtime_var("backups")
_SNAPSHOT_KEEP = 10  # سياسة احتفاظ اللقطات اليدوية: آخر ١٠ (نسخ الذرة 800 لها سياستها keep_last_n=7)
_BACKUP_LOCK = threading.Lock()

def _backup_locked(fn):
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        with _BACKUP_LOCK: return fn(*args, **kwargs)
    return wrapper
# ── 2026-08-16: قُلبت القائمة من «تضمين» إلى «استثناء» ──────────────────────────
# كانت قائمة تضمين مكتوبة بأسماء سبعة مجلّدات، فسقط منها بصمت: `transport`
# (حزمة تستوردها 608 و620) و`runtime` (الخزنة ومفتاح الجهاز) و`scripts` و`tests`
# و`tools` و`docs` و`سياق` -- بينما التعليق أعلاه يَعِد بـ«الورق والسكربتات».
#
# والثمن مقيس: مدقّق خارجيّ استخرج لقطة وحاول إقلاعها، فسقطت 608 و620 بـ
# `No module named 'transport'` وأعلن الإقلاع `success=True` رغم استبعادهما.
# **لقطة لا تُقلع ليست نقطة استرجاع.**
#
# قائمة التضمين تفشل صامتة مع كل مجلّد جديد؛ قائمة الاستثناء تفشل **مرئيّة**:
# الجديد يدخل تلقائيًّا، وما يُستثنى مكتوب باسمه وسببه أدناه.
_BACKUP_SKIP_TOP = {
    "venv":           "بيئة بايثون — تُعاد بـ requirements.txt",
    "var":            "بيانات السوق والمخازن (~500MB) — تنشأ على جهاز التشغيل",
    "backups":        "لا نضع اللقطات داخل اللقطات",
    # ٢٠٢٦-٠٨-٢٩ (ختم NQ) — عطل مقيس حيًّا: مجلّدا التشغيل كلاهما **روابط
    # Junction راجعة لجذر المشروع** (atoms · core · governance …) ولا يحويان
    # ملفًّا أصليًّا واحدًا، وتحتهما `var/backups` حيث تُكتب اللقطة نفسها.
    # فمسحهما كان (أ) ينسخ كل شيء مرّتين عبر الروابط، و(ب) **يقرأ ملفّ اللقطة
    # وهو يكبر** ⇒ نموّ لا نهائي: بلغ 7.72 غيغابايت في خمس دقائق قبل الإيقاف
    # (وسابقةٌ موثّقة عند الشريك بلغت 188 غيغابايت).
    "forex_runtime":  "روابط للجذر + var — لا أصل فيها، وتحتها مجلّد اللقطة",
    ".git":           "تاريخ المستودع",
    "__pycache__":    "ملفّات مترجَمة",
    ".pytest_cache":  "ذاكرة اختبارات مؤقّتة",
    ".ruff_cache":    "ذاكرة فحص مؤقّتة",
}
_BACKUP_EXCLUDE_PARTS = {"node_modules", "__pycache__", ".git", "dist",
                         ".pytest_cache", ".ruff_cache"}
_BACKUP_SENSITIVE_NAMES = {".env", "secrets.enc", "device.key", "credentials.json"}
# ما لا تكون اللقطة لقطةً بدونه. يُتحقَّق منه **بعد** الكتابة بقراءة الأرشيف نفسه،
# لا بالثقة بحلقة النسخ -- لأنّ العطل السابق كان بالضبط «نسخنا ولم نتحقّق».
_BACKUP_MUST_CONTAIN = (
    "pyproject.toml", "requirements.txt",
    "core/__init__.py", "core/CORE.lock", "core/contracts/atom.py",
    "transport/__init__.py", "security/__init__.py",
    "governance/server.py", "governance/scripts/run_core.py",
    "scripts/run_core.py", "mt5/QUANT_NQ.mq5",
)
_RESTORE_GUIDE = """\
# كيف أرجّع المشروع من هاللقطة (خطوة خطوة)

هاللقطة فيها **عقل المشروع كامل**: الذرات · النواة المختومة · الإعدادات · الحوكمة
(بما فيها كود الواجهة) · ورق السياق · السكربتات · الإكسبرت · ملفات الجذر (بما فيها
`governance\\launchers\\Control_Room.bat` و`governance\\setup\\requirements.txt` والمفاتيح).

**المستثنى (وليش):**
- `venv` بيئة بايثون — تُعاد بالتثبيت.
- `var` بيانات السوق والمخازن — تنشأ على جهاز التشغيل، ولا تُحشر في لقطة المشروع.

**خطوات الاسترجاع على جهاز ويندوز:**
1. فكّ ضغط هالملف بمجلد جديد (مثلًا `C:\\Users\\NQ\\QUANT_NQ`).
2. شغّل `governance\\launchers\\Repair_Tests.bat` لتجهيز بيئة بايثون.
3. شغّل `governance\\launchers\\Check_Project.bat`.
4. شغّل `governance\\launchers\\Control_Room.bat` — الواجهة المبنية موجودة داخل الحزمة ولا تحتاج بناءً خارجيًا.

**تحقّق:** شغّل فحوصات الحوكمة والملفات والأحداث قبل تشغيل الأصل.
**تنبيه:** اللقطة قد تحتوي ملفات مفاتيحك — خلّيها بجهازك، لا تنقلها لحدا."""


@_backup_locked
def make_backup() -> tuple[int, dict]:
    import zipfile
    try:
        BACKUPS_DIR.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        path = BACKUPS_DIR / f"snapshot_{stamp}.zip"
        fd, tmp_name = tempfile.mkstemp(dir=BACKUPS_DIR, prefix=".snapshot.", suffix=".tmp")
        os.close(fd); tmp_path = Path(tmp_name)
        root = ROOT.parent
        count = 0
        with zipfile.ZipFile(tmp_path, "w", zipfile.ZIP_DEFLATED) as z:
            # ملفات جذر المشروع (غرفة القيادة.bat · requirements · المفاتيح…) — بدونها ما يرجع كامل
            for f in root.iterdir():
                if (f.is_file() and f.name != "اقرأني — كيف أرجّع المشروع من هالملف.md"
                        and f.name not in _BACKUP_SENSITIVE_NAMES
                        and not f.name.startswith(("secrets.enc.", "device.key."))
                        and f.suffix.lower() not in (".db", ".log", ".key", ".enc")):
                    z.write(f, f.name); count += 1
            # كل مجلّدات الجذر إلّا المستثناة باسمها — فالمجلّد الجديد يدخل تلقائيًّا
            per_top: dict[str, int] = {}
            for base in sorted(root.iterdir()):
                if not base.is_dir() or base.name in _BACKUP_SKIP_TOP:
                    continue
                taken = 0
                for f in base.rglob("*"):
                    if not f.is_file():
                        continue
                    if any(part in _BACKUP_EXCLUDE_PARTS for part in f.parts):
                        continue
                    if f.name in _BACKUP_SENSITIVE_NAMES or f.name.startswith("secrets.enc.") or f.name.startswith("device.key."):
                        continue
                    z.write(f, f.relative_to(root))
                    taken += 1
                count += taken
                per_top[base.name] = taken
            # وصفة الاسترجاع جوّا اللقطة نفسها — الملف يشرح حاله
            z.writestr("اقرأني — كيف أرجّع المشروع من هالملف.md", _RESTORE_GUIDE)

        # ── التحقّق: نقرأ الأرشيف المكتوب ونسأله، ولا نثق بحلقة النسخ ──────────
        with zipfile.ZipFile(tmp_path) as z:
            inside = {n.replace("\\", "/") for n in z.namelist()}
            bad = z.testzip()
        missing = [m for m in _BACKUP_MUST_CONTAIN if m not in inside]
        if bad or missing:
            tmp_path.unlink(missing_ok=True)  # لقطة ناقصة أسوأ من لا لقطة
            reason = (f"أرشيف تالف عند {bad}" if bad
                      else "ناقصها ملفّات لا تقوم اللقطة بدونها: " + " · ".join(missing))
            return 500, {"ok": False, "verified": False, "missing": missing,
                         "message": f"❌ اللقطة رُفضت وحُذفت — {reason}"}

        # `r+b` لا `rb`: على ويندوز `os.fsync` تنادي `_commit()` وهي ترفض مقبضًا
        # بلا نيّة كتابة، فتُلقي [Errno 9] Bad file descriptor — بينما لينكس يقبله،
        # فالعطل لا يظهر إلّا هنا. وثمنه مقيس 2026-08-18: كل لقطة يدويّة كانت تموت
        # **بعد** كتابة الأرشيف والتحقّق منه، عند خطوة المتانة الأخيرة، ثمّ يحذفه
        # مسار الخطأ — فلا نقطة رجوع ولا أثر يدلّ على السبب.
        # حارسه: governance/checks/check_snapshot_button_contract.py
        with tmp_path.open("r+b") as handle: os.fsync(handle.fileno())
        os.replace(tmp_path, path)
        size_mb = round(path.stat().st_size / 1048576, 1)
        # سياسة الاحتفاظ (نفس مبدأ الذرة 800): آخر ١٠ لقطات يدوية تبقى، الأقدم يروح.
        # نمسّ snapshot_*.zip تبعنا فقط — نسخ الذرة 800 (backup_*.tar.gz) ما ننقّيها.
        snaps = sorted(BACKUPS_DIR.glob("snapshot_*.zip"))
        removed = 0
        for old in snaps[:-_SNAPSHOT_KEEP]:
            try:
                old.unlink()
                removed += 1
            except OSError:
                pass
        extra = f" (وانشالت {removed} لقطة أقدم — منحتفظ بآخر {_SNAPSHOT_KEEP})" if removed else ""
        tops = " · ".join(f"{k}:{v}" for k, v in sorted(per_top.items(), key=lambda kv: -kv[1]))
        return 200, {"ok": True, "path": str(path), "files": count, "size_mb": size_mb,
                     "verified": True, "per_top": per_top,
                     "skipped": {k: v for k, v in _BACKUP_SKIP_TOP.items()},
                     "message": (f"✅ لقطة مُتحقَّقة: {count} ملف ({size_mb}MB) "
                                 f"→ var\\backups\\{path.name}{extra}\n{tops}")}
    except Exception as e:
        try:
            if "tmp_path" in locals(): tmp_path.unlink(missing_ok=True)
        except OSError: pass
        return 500, {"ok": False, "message": str(e)}


def unified_log() -> dict:
    """السجل الموحّد الكامل بزر واحد (ورقة ٠٩ مكوّن ٢): جورنال النواة + الصفقات +
    أوامر البوّابة بخط زمني واحد، وأخطاء الذرات المعلّقة جنبهن — بلا فتح عشرين ملف."""
    items: list[dict] = []
    st, body = core_request("/api/journal?n=200")
    if st == 200:
        try:
            for e in json.loads(body):
                items.append({"ts": e.get("ts"), "src": "core",
                              "atom_id": e.get("atom_id"), "kind": e.get("action")})
        except Exception:
            pass
    for r in trade_history("", 120):
        if r.get("open_time"):
            items.append({"ts": r["open_time"], "src": "trade", "kind": "OPENED",
                          "symbol": r.get("symbol"), "side": r.get("side"),
                          "volume": r.get("volume"), "price": r.get("entry_price"),
                          "ticket": r.get("ticket")})
        if r.get("close_time"):
            items.append({"ts": r["close_time"], "src": "trade", "kind": "CLOSED",
                          "symbol": r.get("symbol"), "side": r.get("side"),
                          "volume": r.get("volume"), "price": r.get("exit_price"),
                          "ticket": r.get("ticket")})
    try:
        if COMMANDS_DB.is_file():
            con = sqlite3.connect(f"file:{COMMANDS_DB}?mode=ro", uri=True, timeout=3)
            con.row_factory = sqlite3.Row
            for r in con.execute("SELECT action, operator, requested_at, status "
                                 "FROM commands ORDER BY id DESC LIMIT 50"):
                items.append({"ts": r["requested_at"], "src": "gate",
                              "kind": r["action"], "status": r["status"],
                              "operator": r["operator"]})
            con.close()
    except Exception:
        pass
    errors: list[dict] = []
    st, body = core_request("/api/atoms")
    if st == 200:
        try:
            names = arabic_names()
            for a in json.loads(body):
                if a.get("last_error"):
                    errors.append({"atom_id": a["id"],
                                   "name_ar": names.get(a["id"], str(a["id"])),
                                   "error": str(a["last_error"])[:200]})
        except Exception:
            pass
    items = [i for i in items if isinstance(i.get("ts"), (int, float))]
    items.sort(key=lambda i: i["ts"], reverse=True)
    return {"items": items[:400], "errors": errors}


def day_logs(tail_n: int) -> dict:
    """سجلّا اليوم النصّيان — أخطاء (ذرة 719) وصفقات (ذرة 720) من var/logs.
    قراءة فقط: آخر tail_n سطرًا من ملفّ اليوم + العدد الكامل. ملفّ غائب ليس
    عطلًا — معناه ما انكتب شيء اليوم بعد (قاعدة الصدق)."""
    day = datetime.now().strftime("%Y%m%d")

    def read_one(prefix: str) -> dict:
        path = LOGS_DIR / f"{prefix}-{day}.log"
        info: dict = {"file": f"var\\logs\\{path.name}", "exists": False,
                      "count_today": 0, "lines": []}
        if not path.is_file():
            return info
        try:
            data = path.read_bytes()
        except OSError as exc:
            info["error"] = str(exc)
            return info
        truncated = len(data) > 4_194_304  # نقرأ آخر 4MB فقط لو تضخّم الملف
        if truncated:
            data = data[-4_194_304:]
        lines = data.decode("utf-8", "replace").splitlines()
        if truncated and lines:
            lines = lines[1:]  # أول سطر بعد القصّ قد يكون مبتورًا
        if lines and lines[0].startswith("—"):
            lines = lines[1:]  # سطر ترويسة الملف لا يُعدّ حدثًا
        info.update({"exists": True, "count_today": len(lines),
                     "truncated": truncated, "lines": lines[-tail_n:]})
        return info

    return {"date": day, "errors": read_one("errors"), "trades": read_one("trades")}


# ── قسم السكربتات: أدوات فحص حقيقية تُشغَّل بضغطة زر (قراءة/فحص فقط — لا تغيير) ──
# كل أداة: (سكربت المشروع الفعلي، مهلة بالثواني). تعمل ببايثون البيئة نفسها.
TOOLS: dict[str, tuple[list[str], int]] = {
    "seal": (["governance/scripts/freeze_core.py", "verify"], 90),
    "validator": (["governance/scripts/validate_atoms.py"], 240),
    "tests": (["governance/scripts/test_atoms.py"], 900),
    "governance": (["governance/checks/check_governance.py"], 90),
    "files": (["governance/checks/check_files.py"], 90),
    "events": (["governance/checks/check_events.py"], 90),
    "boot": (["governance/checks/check_boot.py"], 90),
    # ٢٠٢٦-٠٩-٢٢ — سقطت المنصّة بسطرٍ نحويٍّ مكسور في النواة، ولم يظهر في أيّ
    # سجلّ: الموتُ عند الاستيراد قبل تهيئة المسجّل، فلا سطرَ يُكتب. ولم يكن
    # للمالك زرٌّ يسأل «هل كلُّ ملفٍّ يُقرأ أصلًا؟» — فكان الكشفُ مسحًا يدويًّا
    # بـ`py_compile`، وهو **يكتب بايتكود** فكسر أختام أقسامٍ مجمّدة.
    # هذا الحارس يترجم في الذاكرة: صفرُ بايتٍ على القرص (مقيسٌ قبل وبعد).
    "syntax": (["governance/checks/check_syntax.py"], 90),
    "project": (["governance/checks/check_project.py"], 180),
    "safety": (["governance/checks/check_execution_safety.py"], 90),
    "security": (["governance/scripts/check_security.py"], 90),
    # ٢٠٢٦-٠٩-٠٤ (ختم NQ): حارس عربيّة اللوحة. أُضيف بعد أن كشف المالك بعينه
    # ثلاثين بطاقة بأسمائها الإنكليزيّة الخام على شاشته — ولم يكشفها فحص.
    # دستوره: «عربيّ ١٠٠٪ في كل ما يُعرض للمالك»، وحكمه: «ما بدي ولا شي
    # انكليزي او خام». عينُ المالك ليست جهاز إنذار: عيارٌ يُضاف غدًا بلا اسم
    # عربيّ كان سيمرّ صامتًا. مُثبَت أنّه يعضّ: حُذف اسمٌ واحد فأعطى FAIL ورمز 1.
    "arabic_ui": (["governance/checks/check_arabic_ui.py"], 60),
    # ٢٠٢٦-٠٩-١٦ (ختم NQ — «بدي شغل نظيف، لا لوحات ٠ كذب») — حارسان جديدان،
    # ولهما زرّان من أوّل يوم: حارسٌ بلا مفتاح فشلٌ بحكمه المسجَّل، وقد قِيس
    # اليوم أنّ `arabic_ui` نفسه عاش بلا بطاقة.
    #
    # الأوّل يقارن كل حقل تقرؤه اللوحة بمفاتيح حمولة ناشره الفعليّة (قراءة
    # `atom.py` بـ`ast`). يكشف النوع الذي كلّفنا `kill_switch_state` و
    # `floating_pnl`: حقلٌ يُقرأ من حدثٍ لا يحويه فيبقى صفرًا أو «سليمًا»
    # أبدًا — ويمرّ من `tsc` ومن كل الاختبارات سليمًا.
    "dashboard_fields": (["governance/checks/check_dashboard_fields.py"], 90),
    # والثاني يقارن أزرار هذا القاموس ببطاقات «فحوصات الحوكمة»: لا زرّ يشير
    # إلى ملفّ محذوف (وقع فعلًا مع `check_ctrader.py`)، ولا حارس بلا مفتاح.
    "dashboard_buttons": (["governance/checks/check_dashboard_buttons.py"], 60),
    # ٢٠٢٦-٠٩-١٦ — حارس العربيّة كان يفحص أسماء العيارات وحدها، ورسائل صحّة
    # الذرّات (وهي التي تملأ «التنفيذ» و«التحليل») بلا حارس. قِيس: ١٨٢ حقلًا
    # و٢٨ قيمة بلا ترجمة، تُعرض كلّها «حقل تقني=قيمة تقنية».
    "health_arabic": (["governance/checks/check_health_arabic.py"], 90),
    # أمر المالك 2026-08-13: «إذا الهم شغلة لازم من طبقة حوكمة نتحكم فيهم مو من
    # جذر مشروع». هذه الستّة كانت ملفّات .bat بالجذر فقط — صارت أزرارًا باللوحة.
    "bridge": (["governance/scripts/check_bridge.py"], 90),
    "ctrader": (["governance/scripts/check_ctrader.py"], 90),
    "gate": (["governance/scripts/check_execution_gate.py"], 90),
    "health": (["governance/scripts/check_health.py"], 90),
    "versions": (["governance/checks/check_versions.py"], 120),
    # ٢٠٢٦-١٠-٠٧ (ختم المالك «NQ»): رُفع زرّ «hedge» — حارسه يحرس ذرّةً أُرشفت مع فكّ الأقسام عن القرار.
    # ٢٠٢٦-٠٩-٢٣ (ختم nq «ارشف على سطح مكتب»): رُفعت `hedge_chain` و`stop` و`reqid`
    # — حرّاسها تحرس ٥٧٨ و«٥٢٥ سعر الستوب الصلب» المؤرشفتين، فكانت تسقط عند
    # الاستيراد. ملفّاتها في `Desktop\أرشيف QUANT_NQ\حرّاس منظومة التحوّط — 2026-09-23`.
    # ٢٠٢٦-١٠-٠٧ (ختم المالك «NQ»): رُفع زرّ «weights» — حارسه يحرس ذرّةً أُرشفت مع فكّ الأقسام عن القرار.
    # ٢٠٢٦-١٠-٠٧ (ختم المالك «NQ»): رُفع زرّ «contract405» — حارسه يحرس ذرّةً أُرشفت مع فكّ الأقسام عن القرار.
    # ٢٠٢٦-١٠-٠٧ (ختم المالك «NQ»): رُفع زرّ «contract409» — حارسه يحرس ذرّةً أُرشفت مع فكّ الأقسام عن القرار.
    # ٢٠٢٦-١٠-٠٧ (ختم المالك «NQ»): رُفع زرّ «conviction» — حارسه يحرس ذرّةً أُرشفت مع فكّ الأقسام عن القرار.
    # ٢٠٢٦-١٠-٠٧ (ختم المالك «NQ»): رُفع زرّ «contract166» — حارسه يحرس ذرّةً أُرشفت مع فكّ الأقسام عن القرار.
    # ٢٠٢٦-١٠-٠٧ (ختم المالك «NQ»): رُفع زرّ «budget» — حارسه يحرس ذرّةً أُرشفت مع فكّ الأقسام عن القرار.
    # ٢٠٢٦-١٠-٠٧ (ختم المالك «NQ»): رُفع زرّ «dispatch» — حارسه يحرس ذرّةً أُرشفت مع فكّ الأقسام عن القرار.
    "specs": (["governance/checks/check_specs_contract.py"], 180),
    "shutdown": (["governance/checks/check_shutdown_contract.py"], 240),
    # ٢٠٢٦-١٠-٠٧ (ختم المالك «NQ»): رُفع زرّ «protection» — حارسه يحرس ذرّةً أُرشفت مع فكّ الأقسام عن القرار.
    # ٢٠٢٦-١٠-٠٧ (ختم المالك «NQ»): رُفع زرّ «held» — حارسه يحرس ذرّةً أُرشفت مع فكّ الأقسام عن القرار.
    "limits": (["governance/checks/check_limits_state_contract.py"], 300),
    "hotreload": (["governance/checks/check_hot_reload_state_contract.py"], 180),
    "deltavis": (["governance/checks/check_delta_visibility_contract.py"], 180),
    "alignment": (["governance/checks/check_reference_alignment_contract.py"], 180),
    "switches": (["governance/checks/check_switch_safety_contract.py"], 120),
    "stoppath": (["governance/checks/check_stop_path_contract.py"], 180),
    # ٢٠٢٦-١٠-٠٧ (ختم المالك «NQ»): رُفع زرّ «decimals» — حارسه يحرس ذرّةً أُرشفت مع فكّ الأقسام عن القرار.
    "telegram": (["governance/checks/check_telegram.py"], 90),
    "storagecap": (["governance/checks/check_storage_cap_contract.py"], 180),
    "snapbutton": (["governance/checks/check_snapshot_button_contract.py"], 300),
    # ═══ فحوصات قسم أسمر (الكريبتو) — أمر المالك ٢٠٢٦-٠٨-٢٩ ═══
    # كل الفحوص فوقها فوركسيّة العقود؛ قسم الكريبتو كان بلا فحص خاصّ به.
    # هذه الخمسة تقيس ما يخصّه وحده: تغذيته · سلسلته · عزله · بشريّة تنفيذه ·
    # ومطابقته لملفّ أحمد. كلّها قراءة فقط على النظام الحيّ.
    # ٢٠٢٦-٠٩-٠٩ (أمر المالك «ما ضلّ شي اسمه قسم كريبتو»): خمسة فحوص كريبتو
    # (التغذية · السلسلة · العزل · بشريّة التنفيذ · مطابقة شجرة أحمد) رُفعت من
    # جدول الأدوات، وبطاقاتها رُفعت من اللوحة، وملفّاتها أُرشفت لسطح المكتب.
}


def run_tool(name: str) -> tuple[int, dict]:
    tool = TOOLS.get(name)
    if tool is None:
        return 404, {"error": "أداة غير معروفة"}
    args, timeout_s = tool
    env = dict(os.environ)
    env["PYTHONUTF8"] = "1"
    env.pop("NQ_BRIDGE_DB", None)  # درس 601/609: المتغيّر الملوّث يكذّب اختبارات الجسر
    try:
        r = subprocess.run(
            [sys.executable] + args, cwd=str(ROOT.parent), env=env,
            capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=timeout_s)
        out = (r.stdout or "") + (("\n" + r.stderr) if r.stderr else "")
        return 200, {"ok": r.returncode == 0, "code": r.returncode,
                     "output": out[-6000:]}
    except subprocess.TimeoutExpired:
        return 200, {"ok": False, "code": -1,
                     "output": "انتهت المهلة (%d ثانية) قبل ما تخلص الأداة" % timeout_s}
    except Exception as e:
        return 500, {"ok": False, "code": -1, "output": str(e)}


# ── خزنة الأسرار من اللوحة (أمر المالك): «مو من أكواد — لازم من قسم أمان» ──
REMOTE_FLAG = _resolve_runtime_var("governance", "remote_on.txt")


def vault_request(body: dict, client_ip: str) -> tuple[int, dict]:
    """عمليّة خزنة واحدة. **لا تُرجع قيمة سرّ أبدًا — أسماء فقط.**

    حاجزان قبل أي شيء:
      ١) **عبارة المرور لا تسافر خارج الجهاز.** لو الخادم مفتوح للشبكة
         (`remote_on.txt`) أو جاء الطلب من غير الحلقة المحليّة ⇒ يُرفض.
         مفتاح كلّ أسرار النظام لا يُرسل عبر واي‑فاي ولا نفق ولا موبايل.
      ٢) القراءة والكتابة كلاهما عبر `vault_ops` — لا تشفير هنا.
    """
    if REMOTE_FLAG.is_file():
        return 403, {"error": "إدارة الخزنة متوقّفة والتحكّم عن بعد مفتوح — "
                              "احذف var\\governance\\remote_on.txt وافتحها من الجهاز نفسه."}
    if client_ip not in ("127.0.0.1", "::1", "localhost"):
        return 403, {"error": "إدارة الخزنة من جهاز النظام وحده."}
    # الخادم يُشغَّل كملفّ داخل `governance`، فجذر المشروع ليس على المسار
    # وتفشل `from governance import …`. نضيفه هنا لا عالميًّا: أثر محصور.
    if str(ROOT.parent) not in sys.path:
        sys.path.insert(0, str(ROOT.parent))
    try:
        from governance import vault_ops as vops
    except Exception as e:  # noqa: BLE001
        return 500, {"error": "طبقة الأمان غير متاحة: %s" % type(e).__name__}

    op = str(body.get("op", ""))
    passphrase = str(body.get("passphrase", ""))
    key = str(body.get("key", ""))

    if op == "status":
        return 200, {"ok": True, "status": vops.status(), "audit": vops.audit_tail(20),
                     "windows_bound": vops.windows_bound()}
    if op == "archive":
        # ٢٠٢٦-١٠-٢٦ (فحص المشروع، ختم «nq اصلح»): كانت الإزاحة بنقرتين بلا عبارة — فيقلع تلغرام بلا مفتاحه وتغذية
        # الأسعار بلا كلمة مرورها. صارت تطلب العبارة، وتفتح الخزنة بها قبل أن تنقلها.
        if not passphrase:
            return 400, {"ok": False, "message": "اكتب عبارة المرور أوّلًا — الخزنة لا تُزاح بلا عبارتها."}
        ok, msg = vops.archive(passphrase, source="panel")
        return (200 if ok else 400), {"ok": ok, "message": msg}
    if op == "bind_windows":
        ok, msg = vops.bind_windows(passphrase, source="panel")
        return (200 if ok else 400), {"ok": ok, "message": msg}
    if op == "init":
        ok, msg = vops.init(passphrase, source="panel")
        return (200 if ok else 400), {"ok": ok, "message": msg}
    if op == "list":
        ok, msg, keys = vops.list_keys(passphrase, source="panel")
        return (200 if ok else 400), {"ok": ok, "message": msg, "keys": keys}
    if op == "set":
        ok, msg = vops.set_secret(passphrase, key, str(body.get("value", "")),
                                  source="panel")
        return (200 if ok else 400), {"ok": ok, "message": msg}
    if op == "remove":
        ok, msg = vops.remove_secret(passphrase, key, source="panel")
        return (200 if ok else 400), {"ok": ok, "message": msg}
    if op == "rotate":
        ok, msg = vops.rotate(passphrase, str(body.get("new_passphrase", "")),
                              source="panel")
        return (200 if ok else 400), {"ok": ok, "message": msg}
    return 400, {"error": "عمليّة غير معروفة"}


# ══════════════════════════════════════════════════════════════════════
# /gov/ws/core — مرشِد WebSocket من اللوحة إلى النواة المختومة (8010)
#
# لماذا: اللوحة كانت تفتح وصلة مباشرة على 8010 — فتفشل فورًا إن كانت
# للنواة مفتاح (المفتاح عندها في المتصفح فقط) أو إن كان 8010 مقفولًا على
# الجهاز (الوصول البعيد يمرّ بـ 8090 وحده). المرشِد ينقل نفس الأصل:
# المفتاح يبقى في بيئة الخادم، والوصلة تعمل محليًّا وعن بُعد على حدٍ سواء.
# نقل فقط — قراءة وكتابة بحجم البثّ، ولا حكم هنا.
# ══════════════════════════════════════════════════════════════════════

_WS_MAGIC = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"


def _ws_accept(key: str) -> str:
    return base64.b64encode(
        hashlib.sha1((key + _WS_MAGIC).encode("ascii")).digest()
    ).decode("ascii")


def _ws_recv_exact(sock: socket.socket, n: int) -> bytes:
    buf = b""
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            raise ConnectionError("ws-closed")
        buf += chunk
    return buf


def _ws_read_frame(sock: socket.socket) -> tuple[int, bytes]:
    b1, b2 = _ws_recv_exact(sock, 2)
    opcode = b1 & 0x0F
    masked = b2 & 0x80
    ln = b2 & 0x7F
    if ln == 126:
        ln = int.from_bytes(_ws_recv_exact(sock, 2), "big")
    elif ln == 127:
        ln = int.from_bytes(_ws_recv_exact(sock, 8), "big")
    mask = _ws_recv_exact(sock, 4) if masked else b""
    payload = _ws_recv_exact(sock, ln) if ln else b""
    if masked:
        payload = bytes(c ^ mask[i % 4] for i, c in enumerate(payload))
    return opcode, payload


def _ws_send_frame(sock: socket.socket, opcode: int, payload: bytes = b"",
                   mask: bool = False) -> None:
    b0 = 0x80 | opcode
    n = len(payload)
    mask_bit = 0x80 if mask else 0
    if n < 126:
        header = bytes([b0 | mask_bit, n])
    elif n < 1 << 16:
        header = bytes([b0 | mask_bit, 126]) + n.to_bytes(2, "big")
    else:
        header = bytes([b0 | mask_bit, 127]) + n.to_bytes(8, "big")
    if mask:
        m = os.urandom(4)
        payload = bytes(c ^ m[i % 4] for i, c in enumerate(payload))
        header += m
    sock.sendall(header + payload)


def alerts_state() -> dict:
    """حالة ذرة 831 «المُنذِر» — **قراءةً وحدها** (القاعدة: الحوكمة تقرأ لا تكتب).

    المُنذِر هو صاحب القلم: يكتب `system_alerts.json` عند كل تغيير (كتابة
    ذريّة: ملف مؤقت ثم استبدال). نحن نقرأ المسار من مانيفست الذرة نفسها —
    فلا يُكسَّر شيء إن عدّل المالك الإعداد — ونعيد ما هو هناك حرفيًّا.
    غياب الملف حالة طبيعية (الذرّة ما بدأت أو ما سجلّ إخفاقًا بعد).
    """
    # مرسى الحالة، لا جذر المشروع: من جذر الـmirror أبو governance = الجذر، فصار
    # المسار يُحال إلى <root>/var/alerts ويُنبت شجرة var/ في المستودع.
    try:
        from runtime_paths import core_state_root as _csr
        project_root = _csr()
    except Exception:  # noqa: BLE001 — بلا جسور: نقرأ من الـmirror نفسه
        project_root = ROOT
    rel = "alerts/system_alerts.json"
    if not (project_root / rel).is_file() and (project_root / "var" / rel).is_file():
        rel = f"var/{rel}"
    # المانيفست في شجرة الذرّات لا في مرسى الحالة: أبو governance هو جذر الشجرة
    tree_root = Path(__file__).resolve().parent.parent
    manifest = next((tree_root / "atoms").glob("831_*/manifest.yaml"), None)
    if manifest is not None:
        try:
            doc = yaml.safe_load(manifest.read_text(encoding="utf-8"))
            rel = str(((doc or {}).get("config") or {}).get("state_file") or rel)
        except Exception:  # noqa: BLE001 — مانيفست فاسد: نرجع للافتراضي
            pass
    path = (project_root / rel).resolve()
    base = {"path": str(path)}
    if not path.is_file():
        return {**base, "file_missing": True, "total": 0, "alerts": {},
                "updated_at": None}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return {**base, "file_missing": False, "read_error": type(exc).__name__,
                "total": 0, "alerts": {}, "updated_at": None}
    alerts = data.get("alerts") if isinstance(data, dict) else None
    total = data.get("total") if isinstance(data, dict) else 0
    try:
        total = int(total)
    except (TypeError, ValueError):
        total = 0
    return {**base, "file_missing": False,
            "atom_version": data.get("atom_version") if isinstance(data, dict) else None,
            "total": total,
            "alerts": alerts if isinstance(alerts, dict) else {},
            "updated_at": data.get("updated_at") if isinstance(data, dict) else None}


def telegram_status() -> dict:
    """حالة منصّة تلغرام (٦١٠) للّوحة — **بلا توكن ولا أي سرّ.**

    ليست ذرّة (دستور الذرة يمنع الشبكة والحلقة الخلفيّة داخل الذرّة)، فلا يصل
    خبرها عبر ناقل الأحداث. فتسألها اللوحة هنا مباشرة: أمفعّلة؟ أمقترنة؟ أتعمل؟
    """
    out = {"running": False, "paired": False, "token": False, "reason": "",
           "beat_age": None}
    # الحياة من نبض تكتبه المنصّة كل دورة، لا من محاولة اتصال بمنفذ القفل:
    # المنفذ ممسوك ولا يُردّ عليه أبدًا، فطابوره يمتلئ ويبدو الحيّ ميّتًا.
    try:
        b = json.loads(_resolve_runtime_var("governance", "telegram_beat.json")
                       .read_text(encoding="utf-8"))
        age = time.time() - float(b.get("at") or 0)
        out["beat_age"] = round(age, 1)
        out["running"] = age < 90          # دورة الاستطلاع ٢٥ث + تهدئة محتملة
    except Exception:  # noqa: BLE001
        pass
    try:
        conf = json.loads(_resolve_runtime_var("governance", "telegram.json")
                          .read_text(encoding="utf-8"))
        out["paired"] = bool(int(conf.get("owner_chat_id") or 0))
    except Exception:  # noqa: BLE001
        pass
    try:
        if str(ROOT.parent) not in sys.path:
            sys.path.insert(0, str(ROOT.parent))
        from governance.telegram import token_from_vault
        token, why = token_from_vault()
        out["token"] = bool(token)
        out["reason"] = "" if token else why
        del token
    except Exception as e:  # noqa: BLE001
        out["reason"] = "تعذّر سؤال الخزنة (%s)" % type(e).__name__
    return out


OPERATORS = {"dashboard": "اللوحة", "telegram": "تلغرام",   # مصادر الأمر المعروفة
             "launcher": "زرّ التشغيل"}                     # ٢٠٢٦-١٠-٢٦: زرّ «تفعيل البتكوين» صار يمرّ بالختم


def queue_command(action: str, payload: dict | None = None,
                  operator: str = "dashboard") -> tuple[int, dict]:
    """يكتب الأمر المؤكَّد بجسر الأوامر — 901 تنشره في النبضة الجاية.

    `operator` يقول **من أين** جاء الأمر. كان مثبَّتًا على "dashboard" دائمًا،
    فكان السجلّ يقول «اللوحة» عن أمر أرسله المالك من موبايله — سجلّ يكذب
    على صاحبه. والقيمة محصورة بالمعروف، فلا يكتب أحد اسمًا يخترعه.
    """
    if operator not in OPERATORS:
        operator = "dashboard"
    try:
        COMMANDS_DB.parent.mkdir(parents=True, exist_ok=True)
        con = sqlite3.connect(str(COMMANDS_DB), timeout=3)
        con.execute("PRAGMA journal_mode=WAL")
        con.execute(_CMD_SCHEMA)
        columns = {str(row[1]) for row in con.execute("PRAGMA table_info(commands)")}
        if "payload_json" not in columns:
            con.execute("ALTER TABLE commands ADD COLUMN payload_json TEXT")
        body = json.dumps(payload or {}, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        con.execute(
            "INSERT INTO commands (action, operator, requested_at, payload_json) VALUES (?, ?, ?, ?)",
            (action, operator, time.time(), body))
        con.commit()
        con.close()
        return 200, {"stage": "queued",
                     "message": "انكتب الأمر — بوّابة الأوامر (٩٠١) تنفّذه خلال ثانية"}
    except Exception as e:
        return 500, {"error": str(e)}


def sealed_atom_stop(atom_id: int, operator: str = "dashboard") -> tuple[int, dict]:
    """إيقاف ذرّةٍ حرجة بعد ختم المالك بخطوتين — ٢٠٢٦-١٠-٢٦ (فحص المشروع، ختم «nq اصلح»).

    901 لا تملك أمرًا يوقف ذرّة، والإيقاف بيد النواة وحدها؛ فينفّذه الخادم بعد التأكيد، ويكتبه في سجلّ الأوامر نفسه
    بحالٍ منتهية (`DONE` أو `REJECTED`) لا تعيد 901 قراءتها — فيُرى في «السجلّ» بجانب أوامر البوّابة، ولا يُنفَّذ مرّتين.
    """
    if operator not in OPERATORS:
        operator = "dashboard"
    status, body = core_request(f"/api/atoms/{atom_id}/stop", method="POST")
    done = status == 200
    try:
        COMMANDS_DB.parent.mkdir(parents=True, exist_ok=True)
        con = sqlite3.connect(str(COMMANDS_DB), timeout=3)
        con.execute("PRAGMA journal_mode=WAL")
        con.execute(_CMD_SCHEMA)
        columns = {str(row[1]) for row in con.execute("PRAGMA table_info(commands)")}
        if "payload_json" not in columns:
            con.execute("ALTER TABLE commands ADD COLUMN payload_json TEXT")
        record = json.dumps({"atom_id": atom_id, "core_status": status, "by": "governance"},
                            ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        now = time.time()
        con.execute(
            "INSERT INTO commands (action, operator, requested_at, status, executed_at, payload_json) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            ("atom_stop", operator, now, "DONE" if done else "REJECTED", now, record))
        con.commit()
        con.close()
    except Exception:  # noqa: BLE001 — فشل السجلّ لا يُخفي نتيجة الإيقاف، ويُقال
        name = CRITICAL_ATOMS.get(atom_id, ("", ""))[0]
        return (200 if done else status), {
            "stage": "done" if done else "refused",
            "message": ("أُوقفت الذرّة %d «%s» بختمك — وتعذّرت كتابتها في سجلّ الأوامر" % (atom_id, name)) if done
            else "رفضت النواة الإيقاف، وتعذّرت كتابته في سجلّ الأوامر"}
    name = CRITICAL_ATOMS.get(atom_id, ("", ""))[0]
    if done:
        return 200, {"stage": "done", "message": "أُوقفت الذرّة %d «%s» بختمك، وكُتب الإيقاف في سجلّ الأوامر — "
                                                 "ولا تعود إلّا بزرّ «شغّل»" % (atom_id, name)}
    try:
        detail = json.loads(body).get("detail") or {}
        why = detail.get("message") if isinstance(detail, dict) else str(detail)
    except Exception:  # noqa: BLE001
        why = ""
    return status, {"error": "رفضت النواة إيقاف الذرّة %d%s" % (atom_id, (" — " + why) if why else "")}


def candles(symbol: str, tf: int, limit: int) -> list:
    """شموع OHLC حقيقية بأي فريم — مبنيّة من التكّات المخزّنة (قراءة فقط، لا تلمس النواة)."""
    if not symbol or not MARKET_DB.is_file():
        return []
    try:
        con = sqlite3.connect(f"file:{MARKET_DB}?mode=ro", uri=True, timeout=3)
        cur = con.cursor()
        top = cur.execute("SELECT MAX(occurred_at) FROM market_data WHERE symbol=?", (symbol,)).fetchone()
        if not top or top[0] is None:
            con.close()
            return []
        since = top[0] - limit * tf
        buckets: dict[int, list] = {}
        for ts, bid, ask in cur.execute(
            "SELECT occurred_at, bid, ask FROM market_data WHERE symbol=? AND occurred_at>=? ORDER BY occurred_at",
            (symbol, since),
        ):
            mid = (bid + ask) / 2.0
            b = int(ts // tf) * tf
            c = buckets.get(b)
            if c is None:
                buckets[b] = [mid, mid, mid, mid]  # open · high · low · close
            else:
                if mid > c[1]:
                    c[1] = mid
                if mid < c[2]:
                    c[2] = mid
                c[3] = mid
        con.close()
        out = [{"time": b, "open": v[0], "high": v[1], "low": v[2], "close": v[3]}
               for b, v in sorted(buckets.items())]
        return out[-limit:]
    except Exception:
        return []


# تبويب الشارت = تنفيذ ميتاتريدر عبر الإكسبرت، لا تحليل ولا مخزن 701 المختلط.
# العدد الافتراضي يطابق InpWarmupBars في mt5/QUANT_NQ.mq5 (آخر مثال مختوم).
_EA_WARMUP_BARS = 200
_EA_TICK_CAP = 20000


def _trade_table_names(con: sqlite3.Connection) -> set[str]:
    return {str(row[0]) for row in con.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}


def _ohlc_bar(time_s: int, open_: float, high: float, low: float, close: float) -> dict | None:
    if time_s <= 0 or not (open_ > 0 and high > 0 and low > 0 and close > 0):
        return None
    return {"time": time_s, "open": open_, "high": high, "low": low, "close": close}


def _ea_copyrates(con: sqlite3.Connection, symbol: str, period_seconds: int, limit: int) -> list:
    rows = con.execute(
        "SELECT period_start, open, high, low, close FROM candles_history "
        "WHERE symbol=? AND period_seconds=? ORDER BY period_start ASC",
        (symbol, period_seconds)).fetchall()
    out: list[dict] = []
    last_t = None
    for row in rows:
        bar = _ohlc_bar(int(float(row["period_start"] or 0)),
                        float(row["open"] or 0), float(row["high"] or 0),
                        float(row["low"] or 0), float(row["close"] or 0))
        if bar is None:
            continue
        if last_t is not None and bar["time"] <= last_t:
            out[-1] = bar
        else:
            out.append(bar)
        last_t = bar["time"]
    return out[-limit:]


def _agg_ohlc(bars: list, tf: int, limit: int) -> list:
    buckets: dict[int, list] = {}
    order: list[int] = []
    for bar in bars:
        t = int(bar["time"] // tf) * tf
        cur = buckets.get(t)
        if cur is None:
            buckets[t] = [bar["open"], bar["high"], bar["low"], bar["close"]]
            order.append(t)
        else:
            if bar["high"] > cur[1]:
                cur[1] = bar["high"]
            if bar["low"] < cur[2]:
                cur[2] = bar["low"]
            cur[3] = bar["close"]
    return [_ohlc_bar(t, *buckets[t]) for t in order if _ohlc_bar(t, *buckets[t])][-limit:]


def _ea_ticks_ohlc(con: sqlite3.Connection, symbol: str, tf: int, limit: int) -> list:
    cap = min(_EA_TICK_CAP, max(400, limit * 80))
    rows = con.execute(
        "SELECT tick_ms, bid, ask FROM ticks_v2 WHERE symbol=? ORDER BY id DESC LIMIT ?",
        (symbol, cap)).fetchall()
    buckets: dict[int, list] = {}
    order: list[int] = []
    for row in reversed(rows):
        ms = int(row["tick_ms"] or 0)
        bid = float(row["bid"] or 0)
        ask = float(row["ask"] or 0)
        if ms <= 0 or bid <= 0 or ask < bid:
            continue
        # tick_ms كما كتبه الإكسبرت (ملّي ثانية وسيط) — بلا تحويل منطقة زمنية.
        t = int((ms / 1000.0) // tf) * tf
        mid = (bid + ask) / 2.0
        cur = buckets.get(t)
        if cur is None:
            buckets[t] = [mid, mid, mid, mid]
            order.append(t)
        else:
            if mid > cur[1]:
                cur[1] = mid
            if mid < cur[2]:
                cur[2] = mid
            cur[3] = mid
    return [_ohlc_bar(t, *buckets[t]) for t in order if _ohlc_bar(t, *buckets[t])][-limit:]


def exec_chart(symbol: str, tf: int, limit: int) -> dict:
    """شموع تبويب الشارت من قاعدة الإكسبرت (nq_brain) — مزامنة ميتاتريدر لا التحليل.

    CopyRates → candles_history بنفس فريم المنصّة. إن غاب الفريم تُجمَّع شموع
    أصغر كتبها الإكسبرت. تحت الدقيقة: تِكّات ticks_v2. لا market_data ولا cTrader.
    انقطاع النواة لا يمسح الجدول: الإكسبرت يكتب القاعدة وحده.
    """
    tf = max(1, int(tf))
    limit = min(2000, max(1, int(limit)))
    out: dict = {
        "symbol": symbol, "tf": tf, "limit": limit,
        "warmup_bars": _EA_WARMUP_BARS, "source": "none",
        "ea_db": bool(MARKET == "forex" and TRADE_DB.is_file()),
        "candles": [], "symbols": [], "count": 0, "last_tick": None,
    }
    if MARKET != "forex" or not TRADE_DB.is_file():
        return out
    try:
        con = sqlite3.connect(f"file:{TRADE_DB}?mode=ro", uri=True, timeout=3)
        con.row_factory = sqlite3.Row
        tables = _trade_table_names(con)
        names: list[str] = []
        seen: set[str] = set()
        for table, sql in (
            ("symbol_specs_v2", "SELECT DISTINCT symbol FROM symbol_specs_v2 "
                                "WHERE symbol IS NOT NULL AND symbol<>''"),
            ("candles_history", "SELECT DISTINCT symbol FROM candles_history "
                                "WHERE symbol IS NOT NULL AND symbol<>''"),
        ):
            if table not in tables:
                continue
            for row in con.execute(sql):
                name = str(row[0] or "")
                if name and name not in seen:
                    seen.add(name)
                    names.append(name)
        out["symbols"] = names
        if not symbol:
            con.close()
            return out

        candles: list = []
        source = "none"
        if "candles_history" in tables:
            candles = _ea_copyrates(con, symbol, tf, limit)
            if candles:
                source = "ea_copyrates"
            else:
                periods = [int(row[0]) for row in con.execute(
                    "SELECT DISTINCT period_seconds FROM candles_history WHERE symbol=?",
                    (symbol,)) if row[0]]
                bases = sorted((p for p in periods if tf % p == 0 and p < tf), reverse=True)
                for base in bases:
                    src = _ea_copyrates(con, symbol, base,
                                        min(2000, limit * max(1, tf // base)))
                    if src:
                        candles = _agg_ohlc(src, tf, limit)
                        source = "ea_agg"
                        break
        if not candles and "ticks_v2" in tables:
            candles = _ea_ticks_ohlc(con, symbol, tf, limit)
            if candles:
                source = "ea_ticks"
        last_tick = None
        if "ticks_v2" in tables:
            row = con.execute(
                "SELECT bid, ask, tick_ms FROM ticks_v2 WHERE symbol=? "
                "ORDER BY id DESC LIMIT 1", (symbol,)).fetchone()
            if row is not None:
                bid = float(row["bid"] or 0)
                ask = float(row["ask"] or 0)
                if bid > 0 and ask >= bid:
                    last_tick = {"bid": bid, "ask": ask,
                                 "tick_ms": int(row["tick_ms"] or 0)}
        con.close()
        out["candles"] = candles
        out["source"] = source
        out["count"] = len(candles)
        out["last_tick"] = last_tick
        return out
    except Exception:
        return out

# ── طبقة الترجمة: حالة خام → معنى عربي (دالة نقية · ١٤ §٩) ──────────────────────
_STATE_AR = {
    "running": "شغّالة", "stopped": "واقفة", "failed": "فيها خلل",
    "starting": "عم تشتغل", "stopping": "عم توقف", "unloaded": "مسحوبة",
}
_HEALTH_AR = {"healthy": "سليمة", "degraded": "متعثّرة", "unhealthy": "فيها خلل"}
# منافذ القراءة الخام المسموح تمريرها من النواة (بلا كتابة)
_READ_PROXY = {
    "/gov/health": "/api/health",
    "/gov/metrics": "/api/metrics",
    # ٢٠٢٦-٠٩-٠٩ (ختم NQ): صفحة «عدّادات النواة» كانت تقرأ `/api/metrics` وحده،
    # وهو لا يُخرج إلّا عدّادًا واحدًا لكل ذرّة (`lifecycle.start.success=1`)
    # جامدًا منذ الإقلاع — فوصفها يعد بعدّادات نشر وتسليم لا وجود لها فيه.
    # وعدّادات الناقل الحقيقيّة موجودة بالنواة منذ ٢٠٢٦-٠٨-٣١ على
    # `/api/bus-stats` (نُشر · سُلّم · بلا مشترك · أُسقط · مضغوط · تجاوز…)
    # ولم يكن للوحة طريق إليها. هذا التمرير قراءة محضة، بلا منطق ولا كتابة.
    "/gov/bus-stats": "/api/bus-stats",
    # ٢٠٢٦-٠٩-١٠ (ختم NQ): حالة النقل — `worker_count` و`partitioned`
    # و`cold_worker` و`ownership` (أيّ عامل يملك أيّ حساب|رمز) ونِسَب التسليم
    # المشترَك. موجودة بالنواة ولم يكن للوحة طريق إليها، فكان المالك يقرأ
    # «الناقل» بلا أن يعرف من يحمل ماذا. تمرير قراءة محض.
    "/gov/transport-stats": "/api/transport-stats",
    "/gov/journal": "/api/journal",
    "/gov/boot-report": "/api/boot-report",
}


def _iter_atom_manifests() -> list:
    """مانيفستات الذرات بالشكلين معاً: الشجرة المسطّحة (atoms_crypto/2007_…)
    والشجرة المقسّمة أقساماً (atoms/قسم 000-049/003_…/manifest.yaml).
    إصلاح الملعب 2026-08-27: المسح الضحّل بمستوى واحد كان يرى الأقسامَ
    ملفّاتٍ بلا مانيفست فتفرغ خريطة الأسماء ولوحة الشبكة بأكملها."""
    out: list = []
    if not ATOMS_DIR.is_dir():
        return out
    for pattern in ("*/manifest.yaml", "*/*/manifest.yaml"):
        for mf in sorted(ATOMS_DIR.glob(pattern)):
            if mf not in out:
                out.append(mf)
    return out



def arabic_names() -> dict[int, str]:
    """اسم عربي لكل ذرة، مُشتقّ من اسم مجلّدها (لا خريطة يدوية · ١٤ §٩)."""
    out: dict[int, str] = {}
    for manifest in _iter_atom_manifests():
        folder = manifest.parent
        # utf-8-sig: علامة BOM براس الملف (يكتبها Set-Content بويندوز) كانت
        # تُسقط سطر id الأول فتختفي الذرة من الرسم كله — مقيس 2026-08-19.
        text = manifest.read_text(encoding="utf-8-sig")
        m = re.search(r"^\s*id:\s*(\d+)", text, re.M)
        arabic = re.search(r"^\s*name_ar:\s*[\"']?(.+?)[\"']?\s*$", text, re.M)
        if m:
            out[int(m.group(1))] = arabic.group(1).strip() if arabic else re.sub(r"^\d+[_\s]*", "", folder.name).replace("_", " ").strip()
    return out


def _events_block(text: str, key: str) -> list[str]:
    """أسماء الأحداث تحت publishes:/subscribes: — بالصيغتين: القائمة العمودية
    (- بند) وصيغة السطر الواحد `key: [a, b]` (كلتاهما YAML صالح — تجاهل
    الثانية كان يُظهر وصلات «مكسورة» كذبًا، مقيس على منظّف البيانات 113)."""
    out, inblock = [], False
    for ln in text.splitlines():
        flow = re.match(rf"^{key}:\s*\[(.*)\]\s*$", ln)
        if flow:
            return [item.strip().strip("'\"")
                    for item in flow.group(1).split(",") if item.strip().strip("'\"")]
        if re.match(rf"^{key}:\s*$", ln):
            inblock = True
            continue
        if inblock:
            m = re.match(r'^\s*-\s*["\']?([\w.]+)["\']?\s*$', ln)
            if m:
                out.append(m.group(1))
            elif re.match(r"^\S", ln):     # مفتاح جديد بالمستوى الأعلى → نهاية الكتلة
                break
    return out


def system_graph() -> dict:
    """شبكة النظام الحقيقية: عُقَد=الذرات · وصلات=مين ينشر حدثًا يسمعه غيره (من المانيفستات)."""
    names = arabic_names()
    nodes: list[dict] = []
    pubs: dict[str, list[int]] = {}
    subs: dict[str, list[int]] = {}
    for mf in _iter_atom_manifests():
            text = mf.read_text(encoding="utf-8-sig")
            m = re.search(r"^\s*id:\s*(\d+)", text, re.M)
            if not m:
                continue
            aid = int(m.group(1))
            nodes.append({"id": aid, "name": names.get(aid, str(aid))})
            for ev in _events_block(text, "publishes"):
                pubs.setdefault(ev, []).append(aid)
            for ev in _events_block(text, "subscribes"):
                subs.setdefault(ev, []).append(aid)
    edges, seen = [], set()
    for ev, publishers in pubs.items():
        for s in subs.get(ev, []):
            for p in publishers:
                if p != s and (p, s, ev) not in seen:
                    seen.add((p, s, ev))
                    edges.append({"source": p, "target": s, "topic": ev})
    # ٢٠٢٦-٠٨-٢٩ كان هنا مسحٌ لشجرة السوق الآخر (atoms_crypto) لتمييز الأحداث
    # التي ينشرها ذاك وحده، فلا تظهر «وصلات مكسورة» كذبًا. ٢٠٢٦-٠٩-٠٩ (أمر
    # المالك «امسح»): لم يبقَ سوق آخر ولا شجرة ثانية — فلا ناشر أجنبيّ بتعريفه.
    # المفتاحان يبقيان في الردّ فارغَين لأنّ اللوحة تقرؤهما (عقد الواجهة).
    foreign_pubs: list[str] = []

    # pubs/subs خام كمان — محلل الصمت الحي بالتشخيص يصنّف بها الذرات الساكتة والوصلات المكسورة
    return {"nodes": nodes, "edges": edges, "pubs": pubs, "subs": subs,
            "foreign_pubs": foreign_pubs, "foreign_market": None}


# ── جوع الذرّات: هل تتقدّم فعلًا، أم تمثال أخضر؟ ─────────────────────────────
# «سليمة» في عقد النواة تعني «لم أنهَر»، لا «أنا أشتغل». وفحص الجوع داخل الذرّات
# يسأل «هل رأيتُ شيئًا يومًا؟» لا «هل وصلني شيء مؤخّرًا؟» — فذرّة أطعمها إحماءٌ
# مرّةً واحدة عند الإقلاع تعبر العتبة إلى الأبد ولا تستطيع أن تجوع بعدها أبدًا.
# قِيس 2026-08-21: بعد توقّف باني الشموع بقيت 71 ذرّة متجمّدة عند العدد 200
# بالضبط — رقم الإحماء — وكلّها تعلن «سليمة» خضراء. متحفٌ يبتسم.
#
# فالقياس هنا لا يسأل الذرّة عن حالها: يراقب الأرقام التي تنشرها عن نفسها.
# ما لم يتحرّك رقم، لم يحصل شغل. والحوكمة لا تلمس الذرّات ولا النواة (١٤ §٠).
#
# والحكم لا يصدر إلّا بعددٍ تعلنه الذرّة في مانيفستها (max_idle_s) — قانون
# «لا اختراع مدد»: الحوكمة تقيس المدّة الصادقة وتعرضها، والحدّ يضعه المالك.
_HUNGER_LOCK = threading.Lock()
_HUNGER: dict[int, tuple[str, float]] = {}          # id -> (بصمة الأرقام · لحظة آخر تقدّم)
_NUM_RE = re.compile(r"-?\d+(?:\.\d+)?")
_LIMITS_CACHE: tuple[float, dict[int, float]] = (0.0, {})


def _progress_print(atom: dict) -> str:
    """بصمة كل رقم تنشره الذرّة عن نفسها؛ تغيّرها = تقدّم حقيقي لا ادّعاء."""
    health = atom.get("health") or {}
    parts = [str(atom.get("state", "")), str(health.get("state", "")),
             " ".join(_NUM_RE.findall(str(health.get("message", "")))),
             str(atom.get("restart_count", ""))]
    details = health.get("details")
    if isinstance(details, (dict, list)):
        try:
            parts.append(" ".join(_NUM_RE.findall(
                json.dumps(details, sort_keys=True, default=str))))
        except Exception:                                   # تفاصيل غير قابلة للتسلسل
            parts.append("?")
    return "|".join(parts)


def _reports_numbers(atom: dict) -> bool:
    """هل تنشر الذرّة رقمًا واحدًا عن شغلها أصلًا؟

    مقيس 2026-08-21: خمس عشرة ذرّة من 212 تقول كلمة مجرّدة بلا رقم واحد
    (`ACTIVE` · `NO_VOLUME_YET` · `reconciliation_live` …). هذه لا تُقاس، فلا
    تُتّهم: ساكنٌ لا نملك ما نقيسه فيه ليس مُدانًا، بل **خارج القياس**. واتّهامه
    كذبًا هو نفس مرض التمثال الأخضر مقلوبًا.
    """
    health = atom.get("health") or {}
    blob = str(health.get("message", ""))
    details = health.get("details")
    if isinstance(details, (dict, list)):
        try:
            blob += " " + json.dumps(details, sort_keys=True, default=str)
        except Exception:
            return False
    return bool(_NUM_RE.search(blob))


def idle_limits() -> dict[int, float]:
    """حدّ السكون المعلَن لكل ذرّة (max_idle_s بمانيفستها) — بلا افتراضي.
    ذرّة لم تعلن حدَّها تُقاس مدّتها وتُعرض، ولا يصدر عليها حكم."""
    global _LIMITS_CACHE
    stamped, cached = _LIMITS_CACHE
    now = time.time()
    if cached and now - stamped < 10.0:
        return cached
    out: dict[int, float] = {}
    for mf in _iter_atom_manifests():
            # utf-8-sig لنفس سبب arabic_names: BOM بويندوز كان يُسقط سطر id.
            text = mf.read_text(encoding="utf-8-sig")
            ident = re.search(r"^\s*id:\s*(\d+)", text, re.M)
            limit = re.search(r"^\s*max_idle_s:\s*([0-9]+(?:\.[0-9]+)?)\s*$", text, re.M)
            if ident and limit:
                out[int(ident.group(1))] = float(limit.group(1))
    _LIMITS_CACHE = (now, out)
    return out


def hunger_of(atom: dict, now: float, limit: float | None) -> dict:
    """كم ثانية والذرّة ساكنة أمام أعيننا، والحكم إن كانت أعلنت حدَّها.

    المدّة مقيسة من لحظة أوّل رصد لا من إقلاع النظام: الحوكمة لا تدّعي علمًا
    بما لم تشهده، فتمثالٌ قديم يبدأ عندها من الصفر ثمّ يفضح نفسه بنفسه.
    """
    stamp = _progress_print(atom)
    with _HUNGER_LOCK:
        seen = _HUNGER.get(atom.get("id"))
        if seen is None or seen[0] != stamp:
            _HUNGER[atom.get("id")] = (stamp, now)
            since = now
        else:
            since = seen[1]
    idle = max(0.0, now - since)
    measurable = _reports_numbers(atom)
    hungry = bool(measurable and limit and limit > 0
                  and atom.get("state") == "running" and idle > limit)
    return {"idle_s": round(idle, 1), "limit_s": limit, "hungry": hungry,
            "declared": limit is not None, "measurable": measurable}


def label(atom: dict) -> tuple[str, str]:
    """(نصّ الحالة بالعربي · اللون) — كل نتيجة مشتقّة من الحقيقة الخام."""
    state = atom.get("state", "")
    health = (atom.get("health") or {}).get("state", "")
    if state == "running":
        if health in ("degraded", "unhealthy"):
            return _HEALTH_AR.get(health, "متعثّرة"), "amber"
        # التمثال الأخضر: تقول «سليمة» وأرقامها لم تتحرّك فوق حدّها المعلَن.
        if (atom.get("hunger") or {}).get("hungry"):
            return "جائعة", "amber"
        return "سليمة", "green"
    if state == "failed":
        return "فيها خلل", "red"
    if state == "stopped":
        return "واقفة", "grey"
    return _STATE_AR.get(state, state or "؟"), "amber"


def _manifest_path(atom_id: int):
    for mf in _iter_atom_manifests():
            m = re.search(r"^\s*id:\s*(\d+)", mf.read_text(encoding="utf-8-sig"), re.M)
            if m and int(m.group(1)) == atom_id:
                return mf
    return None


def atom_config(atom_id: int):
    """إعدادات الذرة المعلَنة: المفتاح · القيمة · النوع · الحدّ (من config + config_schema)."""
    mf = _manifest_path(atom_id)
    if not mf or yaml is None:
        return None
    data = yaml.safe_load(mf.read_text(encoding="utf-8-sig")) or {}
    cfg = data.get("config") or {}
    props = (data.get("config_schema") or {}).get("properties") or {}
    settings = []
    for key, val in cfg.items():
        p = props.get(key, {})
        # ٢٠٢٦-١٠-٢٦: المقفل يُعلَن مع سببه، فتعرضه الواجهة للقراءة ولا تعرض له خانةً تُكتب ثمّ تُرفض.
        reason = _panel_lock(atom_id, key)
        settings.append({"key": key, "value": val, "type": p.get("type", "string"),
                         "min": p.get("minimum"), "max": p.get("maximum"),
                         "locked": reason is not None, "lock_reason": reason or ""})
    return {"id": atom_id, "settings": settings}


def _to_bool(value: object) -> bool | None:
    """حكم المالك ٢٠٢٦-٠٨-١٤ (البند ٢٢، المرحلة أ): مفتاح الأمان لا يُفتح إلّا
    بقيمة منطقيّة صريحة. لا `bool(string)` أبدًا — المقيس أنّ «لا» و«nope»
    و«None» كانت تُخزَّن نصًّا فتُقرأ `True` **فتفتح بوّابة السوق**.
    و«0»/«1»/«yes»/«no»/«on»/«off» غير مقبولة بأمره الصريح: «لا أضيف هذا
    السلوك من عندي». يرجع None حين لا يكون المُدخَل منطقيًّا ⇒ رفض."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        text = value.strip().lower()
        if text == "true":
            return True
        if text == "false":
            return False
    return None


def _atomic_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".config.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text); fh.flush(); os.fsync(fh.fileno())
        os.replace(tmp, path)
        if hasattr(os, "O_DIRECTORY"):
            try:
                directory_fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
                try: os.fsync(directory_fd)
                finally: os.close(directory_fd)
            except OSError: pass
    except BaseException:
        Path(tmp).unlink(missing_ok=True); raise


def _typed_setting(value: object, schema: dict) -> object:
    kind = schema.get("type")
    if kind == "boolean":
        parsed = _to_bool(value)
        if parsed is None: raise ValueError("expected boolean")
        return parsed
    if kind == "integer":
        if isinstance(value, bool): raise ValueError("expected integer")
        return int(value)
    if kind == "number":
        if isinstance(value, bool): raise ValueError("expected number")
        result = float(value)
        if result != result or result in (float("inf"), float("-inf")): raise ValueError("finite number required")
        return int(result) if result.is_integer() else result
    if kind in ("array", "object") and isinstance(value, str):
        value = json.loads(value)
    if kind == "array" and not isinstance(value, list): raise ValueError("expected array")
    if kind == "object" and not isinstance(value, dict): raise ValueError("expected object")
    if kind == "string" and not isinstance(value, str): return str(value)
    return value


def _yaml_scalar(value: object) -> str | None:
    """قيمةٌ بسيطة بسطرٍ واحد كما تُكتب في YAML — أو None إن لم تكن بسيطة."""
    if value is None or isinstance(value, (bool, int, float, str)):
        text = json.dumps(value, ensure_ascii=False)
        return None if "\n" in text else text
    return None


def _patch_manifest_text(text: str, new_version: str, changes: dict) -> str | None:
    """يعدّل سطر الإصدار وأسطر القيم المتغيّرة وحدها، ويترك كلّ تعليقٍ مكانه.

    ٢٠٢٦-٠٩-٢٤ (ختم Nq صلح): كان الحفظ يعيد كتابة المانيفست كلّه بـ
    `yaml.safe_dump` فتضيع كلّ التعليقات — ومنها أسباب أحكام المالك. مقيس
    ٢٠٢٦-٠٩-٢٤ ٠٠:٠٣: فقد ٥٠٦ شروح حكمَي ٠٩-٠٦ و٠٩-١٨، وفقد ٥١٣ شرح «١٠٠$
    ثابتة» و«عمولة ٧$». يرجع None حين لا يُضمن التعديل السطريّ، فيعود
    المستدعي إلى الكتابة القديمة — لا أسوأ ممّا كان.
    """
    lines = text.splitlines(keepends=True)
    ending = "\r\n" if lines and lines[0].endswith("\r\n") else "\n"
    version_rows = [i for i, row in enumerate(lines) if re.match(r"^version:\s*\S", row)]
    config_rows = [i for i, row in enumerate(lines) if re.match(r"^config:\s*(#.*)?$", row.rstrip("\r\n"))]
    if len(version_rows) != 1 or len(config_rows) != 1:
        return None
    lines[version_rows[0]] = f'version: "{new_version}"{ending}'
    start = config_rows[0] + 1
    end = next((i for i in range(start, len(lines))
                if lines[i].strip() and not lines[i][0].isspace()
                and not lines[i].lstrip().startswith("#")), len(lines))
    indent = next((len(row) - len(row.lstrip(" ")) for row in lines[start:end]
                   if row.strip() and not row.lstrip().startswith("#")), 0)
    if indent <= 0:
        return None
    for key, value in changes.items():
        scalar = _yaml_scalar(value)
        if scalar is None:
            return None
        pattern = re.compile(r"^( {%d})(%s)(\s*:\s*)([^#\r\n]*?)(\s+#[^\r\n]*)?(\r?\n)?$"
                             % (indent, re.escape(str(key))))
        hits = [i for i in range(start, end) if pattern.match(lines[i])]
        if len(hits) != 1:
            return None
        match = pattern.match(lines[hits[0]])
        old_value = match.group(4).strip()
        if not old_value or old_value[0] in "|>":
            return None
        lines[hits[0]] = (match.group(1) + match.group(2) + ": " + scalar
                          + (match.group(5) or "") + (match.group(6) or ending))
    return "".join(lines)


_ATOM_VERSION_LINE = re.compile(r'^ATOM_VERSION\s*=\s*"([^"]+)"', re.M)

# ٢٠٢٦-١٠-٠٢ (ختم المالك «صلح كامل nq»): طريقان لمفتاحٍ واحد. جدول الإعدادات في
# اللوحة كان يكتب مفتاح بوّابة التنفيذ وحدود القاطع واتّصال تغذية FIX بتأكيد متصفّح
# وحده — بلا خطوتَي التأكيد ولا بوّابة 901 ولا سجلّ أوامر — بينما الكود يصرّح أنّ
# التعديل «حصرًا عبر /gov/command». ومخطّط 622 يقبل أيّ مضيف و`use_tls: false`، فطلبٌ
# واحد كان يرسل كلمة مرور FIX الحيّة إلى خادمٍ غريب. هذه المفاتيح لا تُغيَّر من هنا.
_GATE_BY_COMMAND = ("مفتاح بوّابة التنفيذ لا يُكتب من جدول الإعدادات — يُفتح ويُغلق من زرّ "
                    "«بوّابة التنفيذ» وحده (تأكيد بخطوتين ثمّ بوّابة الأوامر 901).")
_PANEL_PROTECTED_KEYS: dict[int, tuple[frozenset[str], str]] = {
    552: (frozenset({"enabled"}), _GATE_BY_COMMAND),
    # 575 بوّابةٌ ثانية يحملها أمر «بوّابة التنفيذ» نفسه (gate = 575 أو both).
    575: (frozenset({"enabled"}), _GATE_BY_COMMAND),
    # كلّ حدود القاطع، ومعها عمر الحجز ومسار دفتره (تبديل المسار = تصفير الدفتر).
    516: (frozenset({"max_daily_loss_pct", "max_consecutive_losses", "max_daily_trades",
                     "max_open_trades", "max_reserved_risk_pct", "reservation_ttl_s",
                     "consumer_db_path"}),
          "حدود قاطع الأمان (516) لا تُعدَّل من جدول الإعدادات — تُعدَّل في ملفّ "
          "المانيفست بيد المالك."),
    # الوجهة والتشفير وهويّة الجلسة واعتمادها.
    622: (frozenset({"host", "port", "use_tls", "sender_comp_id", "target_comp_id", "sub_id",
                     "username", "identity_account_id", "password_secret_key"}),
          "اتّصال تغذية الأسعار (622) — المضيف والمنفذ والتشفير وهويّة الجلسة واعتمادها — لا "
          "يُعدَّل من اللوحة؛ يُعدَّل في ملفّ المانيفست بيد المالك."),
}

# ٢٠٢٦-١٠-٢٦ (فحص المشروع، ختم المالك «nq اصلح»): الجدول كان يكتب أرقام ورقة الخطوط الحمراء ويعيد تحميل الذرّة حيًّا بنافذة
# «موافق» واحدة — الرصيد الابتدائيّ ونسب المخاطرة والحدود اليوميّة والكلّيّة (509)، ونافذة الخبر (109)، والإغلاق الجزئيّ
# والتعادل (574 و572)، وأدنى مضاعف الهدف (555 و552) — بلا بوّابة الأوامر ولا سجلّها، ولا حارس للقسم 600 المجمّد.
# وفي 509 خاصّةً كان المكتوب لا يصل: الترقية الحارّة تستعيد أرقام المالك المحفوظة بعد الإقلاع، والخادم يقول «تمّ».
# فهذه لا تُكتب من الجدول أبدًا. أرقام 509 طريقها المختوم قائم (أمر `account_limits` من بطاقة «حدود الحساب»)؛
# والباقي لا أمر له في 901 بعد، فيبقى على ختم المالك في ملفّ البيان. والرقم السحريّ يحدّد أيّ المراكز للمنظومة:
# تغييره في 509 أو 565 يُخرج مراكزها من نظر الحارس الذي يُغلقها عند الحدّ وعند الخطّ الأحمر.
_RED_LINE_BY_CARD = ("رقمٌ من الخطوط الحمراء، فلا يُكتب من جدول الإعدادات. يتغيّر عبر بطاقة «حدود الحساب» المختومة في "
                     "صفحة «تحكّم»: ملخّصٌ ثمّ تأكيد ثمّ بوّابة الأوامر 901، و509 تطبّقه وتردّ الخطأ بنفسها.")
_RED_LINE_NO_COMMAND = ("رقمٌ يحرس قانونًا من ورقة الخطوط الحمراء، فلا يُكتب من جدول الإعدادات. يتغيّر بختم المالك عبر "
                        "عامل، في ملفّ بيان الذرّة — ولا أمر له في بوّابة الأوامر 901 بعد.")
_RED_LINE_KEYS: dict[int, tuple[tuple[frozenset[str], str], ...]] = {
    509: ((frozenset({"initial_balance", "pair_risk_pct", "pair_daily_pct", "daily_pct", "total_pct"}),
           _RED_LINE_BY_CARD),
          (frozenset({"magic"}), _RED_LINE_NO_COMMAND)),
    # نافذة الخبر قبله (alert_before_seconds) وبعده (keep_past_seconds)، وما يحجب، وحارس الأفق.
    109: ((frozenset({"alert_before_seconds", "keep_past_seconds", "blocking_currencies", "blocking_min_impact",
                      "blocking_titles", "require_forward_horizon"}), _RED_LINE_NO_COMMAND),),
    # أدنى مضاعف الهدف، ومدى خسارة الوقف من الميزانيّة (القانون 2)، وحارسا الأصل والتعرّض قبل الإرسال.
    552: ((frozenset({"min_reward_risk", "risk_floor_frac", "risk_cap_frac", "asset_freeze_gate",
                      "pre_trade_exposure_cap"}), _RED_LINE_NO_COMMAND),),
    555: ((frozenset({"min_reward_multiple"}), _RED_LINE_NO_COMMAND),),
    565: ((frozenset({"magic"}), _RED_LINE_NO_COMMAND),),
    572: ((frozenset({"breakeven_at_r"}), _RED_LINE_NO_COMMAND),),
    574: ((frozenset({"partial_at_r", "partial_fraction"}), _RED_LINE_NO_COMMAND),),
}
_FROZEN_SECTIONS: tuple[tuple[int, int, str], ...] = (
    (600, 649, "القسم 600 مجمّد بأمر المالك، فلا يُكتب إعدادٌ لذرّاته من اللوحة. يتغيّر بختم المالك عبر عامل، "
               "بعد فكّ التجميد."),
)


def _panel_lock(atom_id: int, key: str) -> str | None:
    """سبب منع كتابة هذا المفتاح من جدول الإعدادات، أو `None` إن كان يُكتب من هنا."""
    for low, high, reason in _FROZEN_SECTIONS:
        if low <= atom_id <= high:
            return reason
    protected = _PANEL_PROTECTED_KEYS.get(atom_id)
    if protected is not None and key in protected[0]:
        return protected[1]
    for keys, reason in _RED_LINE_KEYS.get(atom_id, ()):
        if key in keys:
            return reason
    return None


def write_atom_config(atom_id: int, updates: dict) -> tuple[int, dict]:
    mf = _manifest_path(atom_id)
    if not mf or yaml is None or Draft202012Validator is None:
        return 404, {"ok": False, "message": "الذرة غير موجودة أو التحقق غير متاح"}
    if not isinstance(updates, dict) or not updates:
        return 400, {"ok": False, "message": "لا يوجد تعديل صالح"}
    with _CONFIG_LOCK:
        try:
            original_text = mf.read_text(encoding="utf-8-sig")
            data = yaml.safe_load(original_text) or {}
            cfg = data.get("config")
            schema = data.get("config_schema") or {}
            props = schema.get("properties") or {}
            if not isinstance(cfg, dict): raise ValueError("config is not an object")
            clean = {}
            for key, value in updates.items():
                if key not in cfg or key not in props: raise ValueError(f"إعداد غير معروف: {key}")
                clean[key] = _typed_setting(value, props[key])
            merged = dict(cfg); merged.update(clean)
            errors = sorted(Draft202012Validator(schema).iter_errors(merged), key=lambda e: list(e.path))
            if errors: raise ValueError("؛ ".join(f"{'.'.join(map(str,e.path)) or '(root)'}: {e.message}" for e in errors))
            changed = {k: v for k, v in clean.items() if cfg.get(k) != v}
            if not changed:
                return 200, {"ok": True, "changed": False, "message": "لا يوجد تغيير"}
            # ٢٠٢٦-١٠-٠٢ (ختم المالك «صلح كامل nq»): المفاتيح المحميّة تُرفض هنا قبل
            # أيّ كتابة — والمرفوض هو تغييرها وحده (الواجهة ترسل كلّ مفاتيح الذرّة
            # مع كلّ حفظ، فقيمةٌ لم تتغيّر لا تُسقط حفظ جيرانها).
            # ٢٠٢٦-١٠-٢٦: ومعها أرقام الخطوط الحمراء والقسم المجمّد (`_panel_lock`).
            refused = next((r for r in (_panel_lock(atom_id, k) for k in sorted(changed)) if r), None)
            if refused:
                return 403, {"ok": False, "changed": False, "message": refused}
            parts = str(data.get("version") or "").split(".")
            if len(parts) != 3 or not all(x.isdigit() for x in parts): raise ValueError("invalid manifest version")
            new_version = f"{parts[0]}.{parts[1]}.{int(parts[2])+1}"
            # ٢٠٢٦-١٠-٠٢ (ختم المالك «صلح كامل nq»): كان `re.sub` ثمّ «لم يتغيّر النصّ ⇒
            # ATOM_VERSION not found» — فالذرّات الثماني المقسومة (كودها أعلى من
            # مانيفستها برقعة) تسقط بخطأٍ كاذب: الثابت موجود وقيمته هي الإصدار الجديد
            # أصلًا. الآن: يُرفض حين يغيب الثابت فعلًا وحده؛ والكود الذي بلغ الإصدار
            # الجديد (أو تجاوزه) لا يُعاد كتابته ولا يُنزَّل — يُكتب المانيفست وحده.
            code = mf.parent / "atom.py"; old_code = code.read_text(encoding="utf-8") if code.is_file() else None
            current = _ATOM_VERSION_LINE.search(old_code) if old_code is not None else None
            if old_code is not None and current is None:
                raise ValueError("ثابت إصدار الكود غير موجود في ملفّ الذرّة — لا يُرفع إصدار المانيفست وحده")
            code_parts = current.group(1).split(".") if current else []
            if (len(code_parts) == 3 and all(x.isdigit() for x in code_parts)
                    and tuple(map(int, code_parts)) > tuple(map(int, new_version.split(".")))):
                new_version = current.group(1)
            data["version"] = new_version; data["config"] = merged
            # التعليقات تبقى: تعديلٌ سطريّ يُقبل فقط إن أعاد قراءةً مطابقةً تمامًا
            # لما كانت الكتابة الكاملة ستكتبه؛ وإلّا فالطريق القديم كما هو.
            manifest_text = _patch_manifest_text(original_text, new_version, changed)
            if manifest_text is not None:
                try:
                    if yaml.safe_load(manifest_text) != data:
                        manifest_text = None
                except yaml.YAMLError:
                    manifest_text = None
            if manifest_text is None:
                manifest_text = yaml.safe_dump(data, allow_unicode=True, sort_keys=False)
            code_written = False
            if current is not None and current.group(1) != new_version:
                fixed, count = _ATOM_VERSION_LINE.subn(f'ATOM_VERSION = "{new_version}"', old_code, count=1)
                if count != 1:
                    raise ValueError("ثابت إصدار الكود غير موجود في ملفّ الذرّة — لا يُرفع إصدار المانيفست وحده")
                _atomic_text(code, fixed); code_written = True
            try: _atomic_text(mf, manifest_text)
            except BaseException:
                if code_written: _atomic_text(code, old_code)
                raise
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            return 400, {"ok": False, "message": str(exc)}
        except OSError as exc:
            return 500, {"ok": False, "message": type(exc).__name__}
    try:
        with (mf.parent / "التاريخ.md").open("a", encoding="utf-8") as fh:
            # القديم والجديد معًا — «أي حركة بدها تسجيل»، والاسم وحده لا يقول ما تغيّر.
            moves = "، ".join(f"{key}: كان {cfg.get(key)} صار {changed[key]}" for key in sorted(changed))
            fh.write(f"\n- {time.strftime('%Y-%m-%d %H:%M')} v{new_version}: panel config {sorted(changed)} ({moves})\n")
    except OSError: pass
    core_request("/api/rescan", method="POST")
    for _ in range(8):
        time.sleep(1); status, body = core_request("/api/atoms")
        if status != 200: continue
        try:
            if any(a.get("id") == atom_id and str(a.get("version")) == new_version for a in json.loads(body)):
                return 200, {"ok": True, "changed": True, "version": new_version, "message": "تم التعديل وإعادة التحميل"}
        except (ValueError, TypeError): continue
    return 200, {"ok": False, "changed": True, "version": new_version, "message": "حُفظ التعديل ولم تتأكد إعادة التحميل"}

def parameters_rows(db_path: Path | None = None) -> dict:
    """كل صفوف جدول المُعامِلات المحكوم — قراءة فقط (mode=ro: لا إنشاء ولا كتابة).

    الاعتماد لا يمرّ من هنا أبدًا: مساره الوحيد `/gov/command`
    action=`parameter_approve` (تأكيد بخطوتين) ثم بوّابة الأوامر ٩٠١ هي
    التي تكتب بالسجلّ. `approvable` = الاسم من
    `shared.parameter_registry.DECLARED` (الستّة التحليلية)؛ عيارات القرار
    في نفس الجدول لها طريقها `decision_setting` ولا تُعتمد من هنا.
    قاعدة أو جدول غائب يُعلَن غيابًا (`available=false`) — لا يُخترع صفّ.
    """
    path = Path(db_path) if db_path is not None else ANALYSIS_SETTINGS_DB
    if not path.is_file():
        return {"available": False, "parameters": []}
    try:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=3)
        conn.row_factory = sqlite3.Row
        rows = [dict(row) for row in conn.execute(
            "SELECT name,scope,value,source,status,version,effective_from,"
            "approved_by,approved_at,governs,declared_at FROM parameters "
            "ORDER BY name, scope")]
        conn.close()
    except (OSError, sqlite3.Error):
        return {"available": False, "parameters": []}
    # ٢٠٢٦-١٠-٠٩ (ختم المالك «NQ» — إلغاء مفاتيح السرعة إلى الأرشيف): صفٌّ لا اسم له في الكود — لا مُعامِلًا
    # معلنًا (`DECLARED`) ولا عيارًا (`DIALS`) — بياناتٌ بلا قارئ: يبقى في الجدول ولا يُعرض في اللوحة.
    # (يومها: المفاتيح الأربعة وتفعيل شخصيّة الأفق، بقيمها المعتمدة.)
    try:
        from shared.decision_dials import DIALS as _dials
        known = set(_DECLARED_PARAMETERS) | set(_dials)
        rows = [row for row in rows if row["name"] in known]
    except Exception:  # noqa: BLE001 — تعذّر قراءة العيارات لا يُخفي المعلن: يُعرض كلّ صفّ كما كان
        pass
    for row in rows:
        row["approvable"] = row["name"] in _DECLARED_PARAMETERS
    return {"available": True, "parameters": rows}


def tilt_rules_rows(db_path: Path | None = None) -> dict:
    """قواعد محرّك الترجيح (580) من مخزنه — قراءة فقط (mode=ro: لا إنشاء ولا كتابة).

    التعديل لا يمرّ من هنا أبدًا: مساره الوحيد `/gov/command` action=`tilt_rule`
    (تأكيد بخطوتين) ثم بوّابة الأوامر ٩٠١ تنشر `tilt.rule.command` والمحرّك 580
    — المالك الوحيد للمخزن — يطبّق وينشر الحالة. الملف قد لا يوجد قبل أول
    تشغيل للمحرّك: الغائب/غير المقروء يُعلَن غيابًا (`available=false`) —
    لا يُخترع صفّ ولا منحنى. `points_json` الفاسد يُعلَن `points=null` لا [].
    """
    path = Path(db_path) if db_path is not None else TILT_RULES_DB
    if not path.is_file():
        return {"available": False, "rules": []}
    try:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=3)
        conn.row_factory = sqlite3.Row
        rows = [dict(row) for row in conn.execute(
            "SELECT field,side,points_json,enabled,version,updated_at,updated_by "
            "FROM tilt_rules ORDER BY field, side")]
        conn.close()
    except (OSError, sqlite3.Error):
        return {"available": False, "rules": []}
    out = []
    for row in rows:
        try:
            points = json.loads(str(row["points_json"] or "[]"))
            if not isinstance(points, list):
                points = None
        except (TypeError, ValueError):
            points = None
        out.append({"field": row["field"], "side": row["side"], "points": points,
                    "enabled": bool(row["enabled"]), "version": row["version"],
                    "updated_at": row["updated_at"], "updated_by": row["updated_by"]})
    return {"available": True, "rules": out}


def decisions_rows(limit: int, symbol: str = "", db_path: Path | None = None) -> dict:
    """آخر صفوف مخزن دورة حياة التنفيذ (٧٠٧) — قراءة فقط (mode=ro: لا إنشاء ولا كتابة).

    حزمة ج (ج٢.٥، ختم ٢٢): عمودا الربط `decision_id`/`gate_request_id` أُضيفا
    بهجرة ت١ (707 v4.1.0) عبر `ALTER TABLE ADD COLUMN` على قاعدة حيّة قديمة —
    `PRAGMA table_info` يتحقّق من وجودهما فعليًّا وقت القراءة بدل افتراضهما؛
    قاعدة لم تُهاجَر بعد تُعلن `has_link_columns=false` ولا نصطنع عمودًا غائبًا.
    """
    path = Path(db_path) if db_path is not None else DECISIONS_DB
    if not path.is_file():
        return {"available": False, "decisions": [], "has_link_columns": False}
    try:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=3)
        conn.row_factory = sqlite3.Row
        cols = {str(r["name"]) for r in conn.execute("PRAGMA table_info(decisions)")}
        has_link = "decision_id" in cols and "gate_request_id" in cols
        select_cols = ["id", "stage", "request_id", "account_id", "symbol", "direction",
                       "approved", "reason", "confidence", "strategy_id", "model_id",
                       "volume", "stop_loss", "take_profit", "decided_at"]
        if has_link:
            select_cols += ["decision_id", "gate_request_id"]
        # ٢٠٢٦-٠٩-٠٩ (ختم NQ) — عمود `reason` **تصنيف طبقة لا سبب**:
        # قياس جلسة القرار (450-499) على هذه القاعدة نفسها: ٦٧٬٩٧٧ صفًّا بمرحلة
        # `APPROVED` كلّها `BLOCKED_UPSTREAM` — رقمٌ ثابت يبدو سببًا وليس سببًا.
        # والسبب الفعليّ محفوظ في `payload_json`: `rejection.reason` (وتفصيله
        # في `barriers[]`)، ومقيسٌ عليه: `DECISION_SIDE_WAIT` ٩٠٫٣٪ ·
        # `FILTER_FAILED` · `FILTER_VERDICT_STALE` · `MARKET_QUALITY_INVALID`.
        # نستخرجه هنا في حقلين جديدين ولا نلمس `reason` — فمن يقرأ القديم لا
        # ينكسر، ومن يعرض للمالك يجد الحقيقة. الحمولة كاملة لا تُصدَّر (ثقيلة).
        if "payload_json" in cols:
            select_cols.append("payload_json")
        q = "SELECT %s FROM decisions " % ",".join(select_cols)
        args: tuple = ()
        if symbol:
            q += "WHERE symbol = ? "
            args = (symbol,)
        q += "ORDER BY id DESC LIMIT ?"
        rows = []
        for record in conn.execute(q, args + (limit,)):
            row = dict(record)
            raw = row.pop("payload_json", None)
            row["rejection_reason"] = None
            row["barrier_reasons"] = []
            if raw:
                try:
                    payload = json.loads(raw)
                except (ValueError, TypeError):
                    payload = None
                if isinstance(payload, dict):
                    rejection = payload.get("rejection")
                    if isinstance(rejection, dict) and rejection.get("reason"):
                        row["rejection_reason"] = str(rejection["reason"])
                    barriers = payload.get("barriers")
                    if isinstance(barriers, list):
                        row["barrier_reasons"] = [
                            str(b.get("reason")) for b in barriers
                            if isinstance(b, dict) and b.get("reason")
                        ][:6]
            rows.append(row)
        conn.close()
    except (OSError, sqlite3.Error):
        return {"available": False, "decisions": [], "has_link_columns": False}
    return {"available": True, "decisions": rows, "has_link_columns": has_link}


# ─────────────────── رحلة البطاقة: من ٤٦٥ إلى ٥٥٥ إلى الجسر ───────────────────
# ترتيب المحطّات مأخوذ من عقود الأحداث لا من الذاكرة: ٥٥٥ ينشر
# `execution.order.requested` ← ٥٥١ `execution.order.built` ← ٥٨٤
# `execution.order.legal` ← ٥٥٢ `trading.final_decision` ← ٦٠١ يكتب الجسر ←
# ٦١١ `platform.trade_event` ← ٥٦٣ `market.outcome.realized` ← ٤٦٥ يُغلق البطاقة.
#
# ⚠️ **المعروض عربيّ، والخام في تلميح الفأرة وحده** — قاعدة المالك: «ما بدّي
# أشوف ولا شي أجنبيّ» على اللوحة. فالعمود الثالث وصفٌ عربيّ، والرابع اسمُ الحدث
# الخام لا يُعرض إلّا في `title`. (حُكم ٢٠٢٦-٠٩-١٩: «ق انكليزي ندق لا مترجم».)
CARD_CHAIN: tuple[tuple[str, str, str, str], ...] = (
    ("ORDER_REQUESTED", "٥٥٥ طالب أمر الدخول", "بيطلب يفتح مركز",
     "execution.order.requested"),
    ("ORDER_BUILT", "٥٥١ باني الأمر", "بيركّب الأمر بسعره وحجمه",
     "execution.order.built"),
    ("ORDER_REJECTED", "٥٨٤/٥٥٢ — رُدّ", "شرعيّة الوقف أو تدقيق الأمر ردّته",
     "execution.order.rejected"),
    ("DECISION_FINALIZED", "٥٥٢ مدقّق الأمر", "مرّره — صار قرارًا نهائيًّا",
     "trading.final_decision"),
    ("QUEUED_TO_BRIDGE", "٦٠١ كاتب الجسر", "انكتب بقاعدة الجسر",
     "platform.brain_signal.written"),
    ("BRIDGE_WRITE_FAILED", "٦٠١ — فشل الجسر", "ما وصل القاعدة",
     "platform.brain_signal.write_failed"),
    ("BROKER_ACKNOWLEDGED", "ميتاتريدر", "الوسيط أقرّ الأمر",
     "platform.trade_event"),
    ("FILLED_OPEN", "٦١١ ← ٥٦٣", "امتلأ وفتح المركز",
     "market.outcome.realized"),
    ("FILLED_PARTIAL", "تعبئة جزئيّة", "امتلأ جزءٌ منه", ""),
    ("FILLED_CLOSED", "أُغلق المركز", "سكّر المركز", ""),
)


def card_journey_state(days: int = 3, db_path: Path | None = None,
                       cards_path: Path | None = None) -> dict:
    """قُمع رحلة الأمر وأزمنة قفزاتها + بناء آخر بطاقة — قراءة فقط (mode=ro).

    ⚠️ **المفتاح `request_id` لا `decision_id`.** أوّل قياسٍ ربط المحطّات
    بـ`decision_id` فخرجت **صفر** رحلةٍ كاملة: المحطّات بعد البناء تحمل
    `request_id` بصيغة `555-<بصمة>` يختمها ٥٥٥ نفسه، ومحطّاتُ الوسيط تحمل
    مفتاحًا آخر (`manage-…`). الرقم الصفر كان عيبَ ربطٍ لا غيابَ رحلات.

    ⚠️ **وساعتان لا ساعة:** `recorded_at` هنا ساعةُ المنصّة. و`opened_at` في
    مخزن الصفقات ساعةُ الوسيط وتسبقها ثلاث ساعات — لا يُطرح أحدهما من الآخر.
    """
    out: dict = {"available": False, "days": days, "chain": [
        {"stage": k, "label": lab, "what": what, "event": ev}
        for k, lab, what, ev in CARD_CHAIN]}
    path = Path(db_path) if db_path is not None else DECISIONS_DB
    if not path.is_file():
        return out
    cut = time.time() - days * 86400.0
    trips: dict[str, list] = {}
    try:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=5)
        conn.row_factory = sqlite3.Row
        for record in conn.execute(
                "SELECT stage, request_id, symbol, recorded_at, reason FROM decisions "
                "WHERE recorded_at > ? AND request_id LIKE '555-%' ORDER BY recorded_at",
                (cut,)):
            trips.setdefault(str(record["request_id"]), []).append(record)
        conn.close()
    except (OSError, sqlite3.Error):
        return out

    order = {k: i for i, (k, _, _, _) in enumerate(CARD_CHAIN)}
    reached = {k: 0 for k, _, _, _ in CARD_CHAIN}
    hops: dict[tuple[str, str], list[float]] = {}
    for events in trips.values():
        first: dict[str, float] = {}
        for record in events:
            first.setdefault(str(record["stage"]), float(record["recorded_at"]))
        for stage in first:
            if stage in reached:
                reached[stage] += 1
        seq = sorted((s for s in first if s in order), key=lambda s: order[s])
        for a, b in zip(seq, seq[1:]):
            hops.setdefault((a, b), []).append(first[b] - first[a])

    top = reached.get("ORDER_REQUESTED", 0) or 1
    out["funnel"] = [{"stage": k, "label": lab, "what": what, "event": ev,
                      "n": reached[k],
                      "pct": round(100.0 * reached[k] / top, 2)}
                     for k, lab, what, ev in CARD_CHAIN]
    out["hops"] = sorted(
        ({"from": a, "to": b, "median": round(sorted(v)[len(v) // 2], 3),
          "min": round(min(v), 3), "max": round(max(v), 3), "n": len(v)}
         for (a, b), v in hops.items()), key=lambda h: -h["n"])[:10]
    out["requests"] = len(trips)

    # آخر رحلةٍ بلغت الجسر ثمّ امتلأت — بالثانية وكسرها
    complete = [(k, v) for k, v in trips.items()
                if any(x["stage"] == "QUEUED_TO_BRIDGE" for x in v)
                and any(str(x["stage"]).startswith("FILLED") for x in v)]
    complete.sort(key=lambda kv: kv[1][-1]["recorded_at"])
    if complete:
        key, events = complete[-1]
        seen: set = set()
        steps = []
        for record in events:
            if record["stage"] in seen:
                continue
            seen.add(record["stage"])
            steps.append(record)
        # طابعان متساويان يقعان في محطّتين متتاليتين: يكسر التعادلَ ترتيبُ
        # السلسلة لا ترتيبُ الورود، وإلّا ظهر ٥٥٢ قبل ٥٥١.
        steps.sort(key=lambda r: (round(float(r["recorded_at"]), 3),
                                  order.get(str(r["stage"]), 99)))
        t0 = float(steps[0]["recorded_at"])
        out["last_trip"] = {
            "request_id": key, "symbol": steps[0]["symbol"],
            "span": round(float(steps[-1]["recorded_at"]) - t0, 3),
            "steps": [{"stage": r["stage"], "at": float(r["recorded_at"]),
                       "offset": round(float(r["recorded_at"]) - t0, 3),
                       "reason": r["reason"] or ""} for r in steps]}

    out.update(card_build_state(cards_path))
    out["available"] = True
    return out


def card_build_state(cards_path: Path | None = None) -> dict:
    """بناءُ آخر بطاقةٍ حقلًا حقلًا باسم من كتبه — من `card_writes` (٤٦٥)."""
    path = Path(cards_path) if cards_path is not None else CARDS_DB
    if not path.is_file():
        return {"cards_available": False}
    try:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=5)
        conn.row_factory = sqlite3.Row
        card = conn.execute("SELECT * FROM cards WHERE ticket IS NOT NULL "
                            "ORDER BY card_no DESC LIMIT 1").fetchone()
        if card is None:
            card = conn.execute(
                "SELECT * FROM cards ORDER BY card_no DESC LIMIT 1").fetchone()
        if card is None:
            conn.close()
            return {"cards_available": False}
        writes = [dict(r) for r in conn.execute(
            "SELECT author, field, value_json, first_at, hits FROM card_writes "
            "WHERE card_no=? ORDER BY first_at, author", (card["card_no"],))]
        states = [{"state": r["state"], "n": r["n"]} for r in conn.execute(
            "SELECT state, COUNT(*) n FROM cards GROUP BY state ORDER BY n DESC")]
        authors = [{"author": r["author"], "writes": r["n"], "cards": r["c"]}
                   for r in conn.execute(
                       "SELECT author, COUNT(*) n, COUNT(DISTINCT card_no) c "
                       "FROM card_writes GROUP BY author ORDER BY n DESC")]
        total = conn.execute("SELECT COUNT(*) FROM cards").fetchone()[0]
        conn.close()
    except (OSError, sqlite3.Error):
        return {"cards_available": False}
    row = dict(card)
    return {"cards_available": True, "cards_total": total, "card_states": states,
            "card_authors": authors,
            "card": {k: row.get(k) for k in
                     ("card_no", "symbol", "side", "state", "ticket", "entry",
                      "stop", "target", "rr", "outcome", "profit")},
            "card_filled": sum(1 for v in row.values() if v not in (None, "")),
            "card_columns": len(row), "card_writes": writes}


def parameters_audit_rows(limit: int, db_path: Path | None = None) -> dict:
    """آخر صفوف سجلّ تدقيق المُعامِلات (`parameters_audit`) — قراءة فقط.

    حزمة ج (ج٤ — نمط المطلوبة/الفعالة/الحالة): الجدول موجود بمخزن المُعامِلات
    نفسه (`shared/parameter_registry.py`) ويسجّل كل اعتماد (قديم/جديد/من/متى).
    سجلّ عيارات القرار (`decision_dials`) لا جدول تدقيق له بالكود — فلا يُعرض
    له سجل تغييرات (غياب مُعلَن، لا اختراع).
    """
    path = Path(db_path) if db_path is not None else ANALYSIS_SETTINGS_DB
    if not path.is_file():
        return {"available": False, "audit": []}
    try:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=3)
        conn.row_factory = sqlite3.Row
        rows = [dict(row) for row in conn.execute(
            "SELECT audit_id,name,scope,old_json,new_json,version,changed_at,"
            "changed_by,command_id FROM parameters_audit "
            "ORDER BY audit_id DESC LIMIT ?", (limit,))]
        conn.close()
    except (OSError, sqlite3.Error):
        return {"available": False, "audit": []}
    return {"available": True, "audit": rows}


#: افتراضات العتبات — تُقرأ من المحرّك نفسه، لا تُنسخ هنا فتتقادم بصمت.
try:
    if str(ROOT.parent) not in sys.path:
        sys.path.insert(0, str(ROOT.parent))
    from shared.live_analysis import DIAL_DEFAULTS as _ANALYSIS_DIAL_DEFAULTS
    from shared.live_analysis import TUNABLE_SETTINGS as _ANALYSIS_TUNABLE_TUPLE
except Exception:  # noqa: BLE001 - الخادم يقرأ ولا يسقط لغياب وحدة
    _ANALYSIS_DIAL_DEFAULTS = {"required_depth": 60.0, "confidence_threshold": 60.0}
    _ANALYSIS_TUNABLE_TUPLE = ("required_depth", "confidence_threshold", "weight")
#: العيارات المسموح ضبطها من اللوحة — مصدرها المحرّك وحده.
_ANALYSIS_TUNABLE = frozenset(_ANALYSIS_TUNABLE_TUPLE)


def _analysis_defaults() -> dict:
    """صفّ افتراضات المحللات — نسخة مستقلّة لكل مسار، فلا يشتركان بمرجع.

    ⛔ الصفّ يحمل **كل** العتبات النافذة بالمحرّك. نقصه كان يجعل اللوحة تقرأ
       الحقل الغائب صفرًا فتعرض «مهلة الطزاجة 0» بدل 5 — ولو حفظ المالك،
       كتب صفرًا لم يقصده. الغياب هنا كذبٌ صامت، لا اختصار.
    """
    return {key: {**_ANALYSIS_DIAL_DEFAULTS, "weight": weight, "revision": 0}
            for key, weight in _ANALYSIS_DEFAULT_WEIGHTS.items()}


def analysis_settings(account_id: str, symbol: str, broker: str = "") -> dict:
    """قراءة إعدادات المحللات الدائمة؛ اللوحة تضبطها ولا تستنتج قرارًا.

    ⛔ §٣٠ — مفتاح المعايرة صار `account+broker+symbol+analyzer`. قراءةٌ
       بلا وسيط تُرجع صفوف وسطاء متعدّدين فيغلب آخرها — أي يعود خلط
       الوسطاء من باب اللوحة. لذلك: الوسيط يدخل الاستعلام حين يُطلب،
       وحين لا يُطلب تُعلَن الوسطاء الموجودة في `brokers` بدل اختيار
       واحد صامتًا.

    ⛔ ختم المالك ٢٠٢٦-٠٨-٢١ — بُعد المسار: المخزن يحمل عمود `path`
       (`fast` للتِكّات · `slow` للشموع)، وإعدادات المسارين مستقلّة بحكم
       ورقة المالك (§٢٦: «تغيير إعداد في السريع لا يغيّر إعداد البطيء»).
       والقراءة بلا تفريق كانت تدمج الصفّين فيغلب آخرهما — أي يضيع نصف
       المعايرة من باب اللوحة. فصارت مفصولة في `settings_by_path`،
       و`settings` تبقى صفّ المسار السريع حفاظًا على القارئ القديم.
    """
    by_path = {"fast": _analysis_defaults(), "slow": _analysis_defaults()}
    account_id, symbol = account_id.strip(), symbol.strip().upper()
    broker = broker.strip()
    brokers: list[str] = []
    if not account_id or not symbol or not ANALYSIS_SETTINGS_DB.is_file():
        return {"account_id": account_id, "broker": broker, "symbol": symbol,
                "settings": by_path["fast"], "settings_by_path": by_path,
                "brokers": brokers}
    try:
        conn = sqlite3.connect(f"file:{ANALYSIS_SETTINGS_DB}?mode=ro", uri=True, timeout=3)
        conn.row_factory = sqlite3.Row
        columns = {row[1] for row in conn.execute(
            "PRAGMA table_info(analysis_settings)")}
        # مخزن قديم بلا عمود مسار: صفّه الوحيد سريعٌ بحكم الافتراض القديم.
        path_column = "path" if "path" in columns else "'fast' AS path"
        # وعتبةٌ غائبة عن مخزن لم يهاجر بعد تُقرأ بافتراض المحرّك نفسه، لا
        # بصفرٍ ولا بإسقاط الاستعلام كلّه.
        dial_columns = ",".join(
            name if name in columns else f"{value} AS {name}"
            for name, value in _ANALYSIS_DIAL_DEFAULTS.items())
        select = (f"SELECT analyzer_id,{dial_columns},"
                  f"weight,revision,updated_at,updated_by,{path_column} "
                  "FROM analysis_settings ")
        if "broker" in columns:
            brokers = [str(row[0]) for row in conn.execute(
                "SELECT DISTINCT broker FROM analysis_settings "
                "WHERE account_id=? AND symbol=? ORDER BY broker",
                (account_id, symbol))]
            if not broker and len(brokers) == 1:
                broker = brokers[0]
            if broker:
                rows = conn.execute(
                    select + "WHERE account_id=? AND broker=? AND symbol=?",
                    (account_id, broker, symbol)).fetchall()
            else:
                # وسطاء متعدّدون بلا تحديد ⇒ لا يُختار أحدهم صامتًا.
                rows = []
        else:
            rows = conn.execute(select + "WHERE account_id=? AND symbol=?",
                                (account_id, symbol)).fetchall()
        conn.close()
        for row in rows:
            analyzer_id = str(row["analyzer_id"])
            path = str(row["path"] or "fast").strip().lower()
            if path in by_path and analyzer_id in by_path[path]:
                by_path[path][analyzer_id] = {
                    key: row[key] for key in row.keys()
                    if key not in ("analyzer_id", "path")}
    except (OSError, sqlite3.Error):
        pass
    return {"account_id": account_id, "broker": broker, "symbol": symbol,
            "settings": by_path["fast"], "settings_by_path": by_path,
            "brokers": brokers}


def core_request(path: str, method: str = "GET", body: bytes | None = None) -> tuple[int, bytes]:
    try:
        headers = {}
        core_key = os.environ.get("QUANT_CORE_API_KEY") or os.environ.get("QUANT_GOV_API_KEY")
        if core_key: headers["X-API-Key"] = core_key
        if body is not None: headers["Content-Type"] = "application/json"
        req = urllib.request.Request(
            CORE + path, method=method,
            data=(body if body is not None else (b"" if method == "POST" else None)),
            headers=headers,
        )
        with urllib.request.urlopen(req, timeout=8) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()
    except Exception as e:                            # النواة مطفية أو غير جاهزة
        return 503, json.dumps({"error": str(e)}, ensure_ascii=False).encode("utf-8")


class Handler(BaseHTTPRequestHandler):
    # HTTP/1.1: عملاء WebSocket الصارمة ترفض 101 على خط حالة HTTP/1.0
    # (مُقاس 2026-08-24). كل مسارات الرد تمرّ بـ _send ومعها Content-Length،
    # فـ keep-alive آمن. مرسِل WebSocket يرفع close_connection صراحةً.
    protocol_version = "HTTP/1.1"

    def _authorized(self) -> bool:
        if not REMOTE_FLAG.is_file(): return True
        origin = self.headers.get("Origin")
        host = self.headers.get("Host", "")
        if origin:
            parsed = urlparse(origin)
            if not parsed.netloc or parsed.netloc.lower() != host.lower(): return False
        supplied = self.headers.get("X-API-Key", "")
        return bool(GOV_API_KEY) and secrets.compare_digest(supplied, GOV_API_KEY)

    def _guard(self) -> bool:
        if self._authorized():
            return True
        self._json(401, {"error": "unauthorized"})
        return False

    # ٢٠٢٦-١٠-٠٢ (ختم المالك «صلح كامل nq»): في الوضع المحلّيّ كان `_authorized`
    # يُرجع صحيحًا لكلّ طلب، والخادم يقرأ الجسم JSON أيًّا كان نوعه — فصفحةٌ
    # غريبة يفتحها المالك تكتب إعداد أيّ ذرّة، وتوقف ذرّة، وتزيح الخزنة، بطلب
    # «بسيط» بلا فحص CORS (مقيس: `Host: attacker.example` أُجيب بـ200). الآن كلّ
    # طلبٍ مغيِّر (POST) وكلّ ترقية WebSocket: `Host` لا بدّ أن يكون عنوان هذا
    # الخادم الحلقيّ (دفاع إعادة ربط DNS)، و`Origin` إن وُجد لا بدّ أن يكون أصل
    # اللوحة. وما بلا `Origin` (urllib: تلغرام والمحور والحرّاس) يمرّ كما كان.
    # الوضع البعيد (`remote_on.txt`) يبقى على حارسه: مفتاحٌ إلزاميّ ومطابقة الأصل.
    def _cross_site_refusal(self) -> str | None:
        if REMOTE_FLAG.is_file():
            return None
        host = (self.headers.get("Host") or "").strip().lower()
        if host not in {f"{name}:{PORT}" for name in _LOOPBACK_NAMES}:
            return "طلبٌ مرفوض: المضيف ليس عنوان اللوحة المحلّيّ (حماية من إعادة ربط DNS)."
        origin = self.headers.get("Origin")
        if origin is not None:
            allowed = {f"http://{name}:{port}" for name in _LOOPBACK_NAMES
                       for port in {PORT, _PANEL_PORT}}
            if origin.strip().lower() not in allowed:
                return "طلبٌ مرفوض: جاء من صفحةٍ غير لوحة القيادة — لا يُغيَّر شيءٌ من موقعٍ آخر."
        return None

    def _refuse_cross_site(self) -> bool:
        reason = self._cross_site_refusal()
        if reason is None:
            return False
        self._json(403, {"ok": False, "error": reason, "message": reason})
        # جسم الطلب المرفوض لم يُقرأ: يُغلق الاتّصال كي لا يُقرأ طلبًا تاليًا.
        self.close_connection = True
        return True

    def _send(self, status: int, body: bytes, ctype: str, no_store: bool = False) -> None:
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        if no_store:
            self.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, status: int, obj) -> None:
        self._send(status, json.dumps(obj, ensure_ascii=False).encode("utf-8"),
                   "application/json; charset=utf-8", no_store=True)

    # ── /gov/ws/core: مرشِد WebSocket نحو النواة (8010) ──
    def _ws_relay_core(self) -> None:
        key = self.headers.get("Sec-WebSocket-Key", "")
        if not key:
            self._json(400, {"error": "not-a-websocket"})
            return
        upstream_host, upstream_port = "127.0.0.1", 8010
        try:
            parts = urlparse(CORE)
            upstream_host = parts.hostname or "127.0.0.1"
            upstream_port = parts.port or 8010
        except ValueError:
            pass
        # ١) مصافحة عميل مع النواة — المفتاح من بيئة الخادم لا من المتصفح
        try:
            up = socket.create_connection((upstream_host, upstream_port), timeout=5)
        except OSError as exc:
            self._json(502, {"error": f"core-unreachable: {exc.__class__.__name__}"})
            return
        core_key = os.environ.get("QUANT_CORE_API_KEY") or os.environ.get("QUANT_GOV_API_KEY")
        req = (
            "GET /ws/events HTTP/1.1\r\n"
            f"Host: {upstream_host}:{upstream_port}\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {base64.b64encode(os.urandom(16)).decode('ascii')}\r\n"
            "Sec-WebSocket-Version: 13\r\n"
            "Sec-WebSocket-Protocol: quant-nq\r\n"
        )
        if core_key:
            req += f"X-API-Key: {core_key}\r\n"
        req += "\r\n"
        try:
            up.settimeout(5)
            up.sendall(req.encode("ascii"))
            resp = b""
            while b"\r\n\r\n" not in resp:
                chunk = up.recv(4096)
                if not chunk:
                    raise ConnectionError("core-closed-handshake")
                resp += chunk
            if b" 101 " not in resp.split(b"\r\n", 1)[0]:
                raise ConnectionError("core-refused-upgrade")
        except (OSError, ConnectionError) as exc:
            up.close()
            self._json(502, {"error": f"core-relay-failed: {exc}"})
            return
        # ٢) مصافحة مع المتصفح
        try:
            self.send_response(101, "Switching Protocols")
            self.send_header("Upgrade", "websocket")
            self.send_header("Connection", "Upgrade")
            self.send_header("Sec-WebSocket-Accept", _ws_accept(key))
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
        except OSError:
            up.close()
            return
        # ٣) ضخّ ثنائي الاتجاه — خيط لكل اتجاه (النموذج: طلب/ردّ، نقل فقط)
        up.settimeout(None)
        self.connection.settimeout(None)
        stop = threading.Event()

        def pump(src: socket.socket, dst: socket.socket, mask_out: bool) -> None:
            while not stop.is_set():
                try:
                    opcode, payload = _ws_read_frame(src)
                except (OSError, ConnectionError):
                    break
                if opcode == 0x8:  # close
                    stop.set()
                    try:
                        _ws_send_frame(dst, 0x8, payload[:2], mask=mask_out)
                    except OSError:
                        pass
                    break
                if opcode == 0x9:  # ping → pong (لكل رجلٍ حارس حياته)
                    try:
                        _ws_send_frame(dst, 0xA, payload, mask=mask_out)
                    except OSError:
                        break
                    continue
                if opcode in (0x0, 0x1, 0x2):  # continuation/text/binary
                    try:
                        _ws_send_frame(dst, opcode, payload, mask=mask_out)
                    except OSError:
                        break

        # المتصفح يرسل مموّهًا دائمًا؛ نحو النواة نعيده مموّهًا (عقد العميل)
        t1 = threading.Thread(target=pump, args=(self.connection, up, True), daemon=True)
        t2 = threading.Thread(target=pump, args=(up, self.connection, False), daemon=True)
        t1.start()
        t2.start()
        t1.join()
        t2.join()
        try:
            up.close()
        except OSError:
            pass
        self.close_connection = True

    # ── قراءة ──
    def do_GET(self) -> None:  # noqa: N802
        p = self.path.split("?", 1)[0]
        if (p.startswith("/gov/") or p.startswith("/api/")) and not self._guard(): return

        if p == "/gov/market":
            # ٢٠٢٦-٠٩-٠٩ (أمر المالك «ما ضلّ شي اسمه قسم كريبتو»): كان الردّ
            # يحمل `alternate_port` و`alternate_label` — أي منفذ سوق ثانٍ
            # واسمه. المنفذان 8091/8020 مغلقان مقيسًا، واللوحة لم تعد تقرأ
            # الحقلين. السوق واحد، فلا بديل يُعلَن.
            self._json(200, {
                "market": MARKET,
                "label": "فوركس" if MARKET == "forex" else "كريبتو",
                "core": CORE,
                "governance_port": PORT,
            })
            return

        if p == "/gov/universe/overrides":
            path = _resolve_runtime_var("universe_overrides.json")
            try:
                payload = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
            except (OSError, ValueError):
                payload = {}
            self._json(200, {"market": MARKET, "overrides": payload})
            return

        if p == "/gov/names":
            self._json(200, arabic_names())
            return

        if p == "/gov/graph":
            self._json(200, system_graph())
            return

        if p == "/gov/telegram":
            self._json(200, telegram_status())
            return

        if p == "/gov/alerts":
            # قراءة حالة المُنذِر (831) — اللوحة وتلغرام يقرآن من هنا
            self._json(200, alerts_state())
            return

        if p == "/gov/ws/core":
            # مرشِد بثّ النواة — نفس الأصل، والمفتاح بيد الخادم.
            # ٢٠٢٦-١٠-٠٢ (ختم المالك «صلح كامل nq»): ترقية WebSocket تحمل `Origin`
            # دائمًا من المتصفّح، فتُفحص كالطلب المغيِّر — البثّ فيه الحساب والمراكز.
            if self._refuse_cross_site(): return
            self._ws_relay_core()
            return

        if p == "/gov/version":
            # اسم ملف جافاسكربت المبني (يتغيّر مع كل بناء) → الواجهة تكتشفه وتعيد التحميل لحالها
            v = "?"
            try:
                for f in (DIST / "assets").glob("index-*.js"):
                    v = f.name
                    break
            except Exception:
                pass
            self._json(200, {"v": v})
            return

        if p == "/gov/analysis/settings":
            q = parse_qs(urlparse(self.path).query)
            account_id = (q.get("account_id") or [""])[0]
            symbol = (q.get("symbol") or [""])[0]
            broker = (q.get("broker") or [""])[0]
            self._json(200, analysis_settings(account_id, symbol, broker))
            return

        if p == "/gov/decision/settings":
            # عيارات القرار المحكومة — من سجلّ المُعامِلات نفسه (قيمة دقيقة +
            # مصدر واعتماد ونسخة)، مع بيانات العرض (نسبة/خام/صحيح وحدوده)
            # لتعرضها اللوحة بدقّة عشريتين. التعديل حصراً عبر /gov/command
            # action=decision_setting (تأكيد بخطوتين ثم بوّابة ٩٠١).
            #
            # ٢٠٢٦-٠٨-٢٩ (ختم NQ): `shared/decision_dials.py` عيارات **فوركس
            # حصرًا** (ذرّاتها 150·166·411·452-458·463·581) — وهو ملفّ مشترك
            # فكان يُخدَم للكريبتو أيضًا، فتظهر ٣١ عيار فوركس في إعدادات قسم
            # أسمر. أمر المالك: «ما بدّي شي فوركسي بقسم كريبتو».
            # الكريبتو لا سجلّ عيارات محكومة له بعد ⇒ تُعاد قائمة فارغة
            # **بسبب مُعلَن**، لا قائمة سوق آخر.
            if MARKET != "forex":
                self._json(200, {"dials": [],
                                 "reason": "لا عيارات قرار محكومة لهذا السوق — "
                                           "سجلّ العيارات الحاليّ خاصّ بالفوركس"})
                return
            try:
                if str(ROOT.parent) not in sys.path:
                    sys.path.insert(0, str(ROOT.parent))
                from shared.decision_dials import DIALS as _dials, declare as _declare
                registry = _declare()
                rows = {row["name"]: row for row in registry.all()}
                out = []
                for name, spec in _dials.items():
                    if spec.get("retired"):
                        continue  # ٢٠٢٦-١٠-٠٧: عيارٌ مالكه مؤرشف مع فكّ الأقسام عن القرار — لا يُعرض
                    row = rows.get(name) or {}
                    out.append({
                        "name": name, "atom": spec["atom"], "key": spec["key"],
                        "value": float(row.get("value", spec["value"])),
                        "status": row.get("status", "UNAPPROVED"),
                        "source": row.get("source", "UNSET"),
                        "version": int(row.get("version", 0) or 0),
                        "display": spec["display"],
                        "bounds": list(spec["bounds"]),
                        "where": spec["where"]})
                self._json(200, {"dials": out})
            except Exception as exc:
                self._json(500, {"error": str(exc)})
            return

        if p == "/gov/realized":
            # ٢٠٢٦-١٠-٢٦: المحقَّق الكلّيّ مع العمولة والتبييت من سجلّ الوسيط — قراءة فقط.
            self._json(200, realized_totals())
            return

        if p == "/gov/parameters":
            # لوحة حقيقة سجلّ المُعامِلات — قراءة فقط؛ الاعتماد عبر
            # /gov/command action=parameter_approve حصرًا (يد المالك).
            self._json(200, parameters_rows())
            return

        if p == "/gov/tilt/rules":
            # قواعد محرّك الترجيح (580) — قراءة فقط من مخزنه؛ التعديل عبر
            # /gov/command action=tilt_rule حصرًا (تأكيد بخطوتين ثم بوّابة ٩٠١).
            self._json(200, tilt_rules_rows())
            return

        if p == "/gov/calendar":
            q = parse_qs(urlparse(self.path).query)
            cur = (q.get("currency") or ["USD"])[0].upper()
            imp = (q.get("impact") or ["MEDIUM"])[0].upper()
            self._json(200, {"currency": cur, "impact": imp,
                             "available": TRADE_DB.is_file(),
                             "events": calendar_rows(cur, imp)})
            return

        if p == "/gov/news":
            q = parse_qs(urlparse(self.path).query)
            try:
                limit = min(100, max(1, int((q.get("limit") or ["30"])[0])))
            except ValueError:
                limit = 30
            self._json(200, {"available": TRADE_DB.is_file(),
                             "news": translate_headlines(news_rows(limit))})
            return

        if p == "/gov/trades":
            q = parse_qs(urlparse(self.path).query)
            sym = (q.get("symbol") or [""])[0]
            try:
                limit = min(200, max(1, int((q.get("limit") or ["60"])[0])))
            except ValueError:
                limit = 60
            self._json(200, {"symbol": sym, "trades": trade_history(sym, limit)})
            return

        if p == "/gov/decisions":
            # حزمة ج (ج٢.٥): سجلّ مخزن ٧٠٧ — قراءة فقط. منفذ جديد؛ لا يصير حيًّا
            # إلا بإعادة تشغيل الخادم (governance/server.py لا يُحمَّل حيًّا).
            q = parse_qs(urlparse(self.path).query)
            sym = (q.get("symbol") or [""])[0]
            try:
                limit = min(200, max(1, int((q.get("limit") or ["30"])[0])))
            except ValueError:
                limit = 30
            self._json(200, decisions_rows(limit, sym))
            return

        if p == "/gov/card/journey":
            # رحلة البطاقة: قُمع ٥٥٥→الجسر وأزمنته + بناء آخر بطاقة. قراءة فقط.
            # منفذ جديد؛ لا يصير حيًّا إلا بإعادة تشغيل الخادم (server.py لا
            # يُحمَّل حيًّا) — كما هو حال /gov/decisions أعلاه.
            q = parse_qs(urlparse(self.path).query)
            try:
                days = min(30, max(1, int((q.get("days") or ["3"])[0])))
            except ValueError:
                days = 3
            self._json(200, card_journey_state(days))
            return

        if p == "/gov/parameters/audit":
            # حزمة ج (ج٤): سجلّ تدقيق المُعامِلات — قراءة فقط. منفذ جديد؛ يحتاج
            # إعادة تشغيل الخادم مثل /gov/decisions أعلاه.
            q = parse_qs(urlparse(self.path).query)
            try:
                limit = min(500, max(1, int((q.get("limit") or ["100"])[0])))
            except ValueError:
                limit = 100
            self._json(200, parameters_audit_rows(limit))
            return

        if p == "/gov/candles":
            q = parse_qs(urlparse(self.path).query)
            sym = (q.get("symbol") or [""])[0]
            try:
                tf = max(1, int((q.get("tf") or ["60"])[0]))
                limit = min(2000, max(10, int((q.get("limit") or ["400"])[0])))
            except ValueError:
                tf, limit = 60, 400
            # ٢٠٢٦-٠٩-٠٩ (ختم NQ): هذا المسار كان **يقطع الاتّصال** بلا ردّ ولا
            # سطر بسجلّ الأخطاء — أي عطل صامت تمامًا. (`candles()` تنجح معزولةً،
            # فالسبب في العمليّة الحيّة وحدها ولم يُمسك بعد.) لا قارئ له باللوحة
            # اليوم — الشارت يقرأ `/gov/exec-candles` — لكن العطل الصامت أسوأ من
            # العطل المُعلَن: صار يردّ 500 بالسبب بدل أن يُغلق المقبس.
            try:
                rows = candles(sym, tf, limit)
            except Exception as exc:  # noqa: BLE001 — الغرض إعلان أي عطل لا ابتلاعه
                self._json(500, {"error": "candles_failed",
                                 "message": "%s: %s" % (type(exc).__name__, exc),
                                 "symbol": sym, "tf": tf, "limit": limit})
                return
            self._json(200, {"symbol": sym, "tf": tf, "candles": rows})
            return

        if p == "/gov/exec-candles":
            # تبويب الشارت — شموع الإكسبرت / CopyRates ميتاتريدر، لا تحليل.
            q = parse_qs(urlparse(self.path).query)
            sym = (q.get("symbol") or [""])[0]
            try:
                tf = max(1, int((q.get("tf") or ["60"])[0]))
                limit = min(2000, max(1, int((q.get("limit") or [str(_EA_WARMUP_BARS)])[0])))
            except ValueError:
                tf, limit = 60, _EA_WARMUP_BARS
            self._json(200, exec_chart(sym, tf, limit))
            return

        cm = re.fullmatch(r"/gov/atoms/(\d+)/config", p)
        if cm:
            cfg = atom_config(int(cm.group(1)))
            self._json(200 if cfg is not None else 404, cfg if cfg is not None else {"error": "not found"})
            return

        if p == "/gov/atoms":
            status, body = core_request("/api/atoms")
            if status != 200:
                self._json(503, {"connected": False})
                return
            names, atoms = arabic_names(), json.loads(body)
            limits, seen_at = idle_limits(), time.time()
            for a in atoms:
                a["name_ar"] = names.get(a["id"], a.get("name", str(a["id"])))
                # الجوع يُحسب قبل الشارة: الشارة تقرؤه ولا تسبقه.
                a["hunger"] = hunger_of(a, seen_at, limits.get(a["id"]))
                a["label_ar"], a["color"] = label(a)
            self._json(200, {"connected": True, "atoms": atoms})
            return

        if p == "/gov/unified-log":
            self._json(200, unified_log())
            return

        if p == "/gov/day-logs":
            q = parse_qs(urlparse(self.path).query)
            try:
                n = min(1000, max(10, int((q.get("n") or ["250"])[0])))
            except ValueError:
                n = 250
            self._json(200, day_logs(n))
            return

        if p.startswith("/gov/lab"):
            # مختبر المعايرة — ذرّات حقيقية على بيانات تاريخية (أمر المالك).
            try:
                from backtest.atom_lab import handle_lab as _handle_lab
            except Exception as exc:  # noqa: BLE001
                self._json(500, {"ok": False, "error": "مختبر غير متاح: %s" % type(exc).__name__})
                return
            self._json(200, _handle_lab("GET", p, None))
            return

        if p.startswith("/gov/backtest"):
            try:
                from backtest.trade_replay import handle_backtest as _handle_bt
            except Exception as exc:  # noqa: BLE001
                self._json(500, {"ok": False, "error": "باك تست غير متاح: %s" % type(exc).__name__})
                return
            self._json(200, _handle_bt("GET", p, None))
            return

        if p == "/gov/backups":
            # جرد النسخ الحقيقي من القرص: الآلية (ذرة 800) واليدوية (اللقطات)
            def scan(pattern: str) -> dict:
                try:
                    files = sorted(BACKUPS_DIR.glob(pattern), key=lambda f: f.stat().st_mtime)
                    if not files:
                        return {"count": 0}
                    last = files[-1]
                    return {"count": len(files), "last_name": last.name,
                            "last_ts": last.stat().st_mtime,
                            "last_mb": round(last.stat().st_size / 1048576, 1)}
                except OSError:
                    return {"count": 0}
            self._json(200, {"auto": scan("backup_*.tar.gz"), "manual": scan("snapshot_*.zip")})
            return

        if p in _READ_PROXY:
            status, body = core_request(_READ_PROXY[p] + (self.path[len(p):] or ""))
            self._send(status, body, "application/json; charset=utf-8", no_store=True)
            return

        self._serve_static(p)

    # ── تحكّم (بوّابة الأوامر — تمرير لخُطّاف النواة، ١٤ §٨) ──
    def do_POST(self) -> None:  # noqa: N802
        if not self._guard() or self._refuse_cross_site(): return
        try: declared_length = int(self.headers.get("Content-Length", "0"))
        except (TypeError, ValueError): self._json(400, {"error": "bad content length"}); return
        if declared_length < 0 or declared_length > _MAX_BODY_BYTES:
            self._json(413, {"error": "request body too large"}); return
        cm = re.fullmatch(r"/gov/atoms/(\d+)/config", self.path)
        if cm:
            length = declared_length
            raw = self.rfile.read(length) if length > 0 else b"{}"
            try:
                updates = json.loads(raw)
            except Exception:
                self._json(400, {"ok": False, "message": "JSON غير صالح"}); return
            if not isinstance(updates, dict):
                self._json(400, {"ok": False, "message": "الحمولة يجب أن تكون object"}); return
            status, obj = write_atom_config(int(cm.group(1)), updates)
            self._json(status, obj)
            return

        m = re.fullmatch(r"/gov/atoms/(\d+)/(stop|start)", self.path)
        if m:
            # ٢٠٢٦-١٠-٢٦ (فحص المشروع، ختم «nq اصلح»): الذرّة الحرجة لا تُوقف بنقرة — طريقها `/gov/command` بأمر
            # `atom_stop`: ملخّصٌ ثمّ تأكيد. والتشغيل يبقى بلا ختم: يعيد حارسًا ولا يُسقطه.
            if m.group(2) == "stop" and int(m.group(1)) in CRITICAL_ATOMS:
                reason = ("إيقاف «%s» (%s) يحتاج ختمك: ملخّصٌ ثمّ تأكيد — %s"
                          % (CRITICAL_ATOMS[int(m.group(1))][0], m.group(1), CRITICAL_ATOMS[int(m.group(1))][1]))
                self._json(403, {"ok": False, "sealed": True, "error": reason, "message": reason})
                return
            status, body = core_request(f"/api/atoms/{m.group(1)}/{m.group(2)}", method="POST")
            self._send(status, body, "application/json; charset=utf-8", no_store=True)
            return

        tm = re.fullmatch(r"/gov/tool/(\w+)", self.path)
        if tm:
            status, obj = run_tool(tm.group(1))
            self._json(status, obj)
            return

        if self.path == "/gov/vault":
            # إدارة الخزنة من قسم الأمان باللوحة (أمر المالك): إنشاء · إضافة ·
            # حذف · أسماء. المنطق كلّه في vault_ops — هنا حواجز ونقل فقط.
            length = declared_length
            try:
                body_obj = json.loads(self.rfile.read(length) if length > 0 else b"{}")
            except Exception:
                body_obj = {}
            self._json(*vault_request(body_obj, self.client_address[0]))
            return

        if self.path == "/gov/backup":
            status, obj = make_backup()
            self._json(status, obj)
            return

        if self.path == "/gov/rescan":
            status, body = core_request("/api/rescan", method="POST")
            self._send(status, body, "application/json; charset=utf-8", no_store=True)
            return

        if self.path == "/gov/universe/scan":
            body = json.dumps({"name": "crypto.universe.scan.requested", "payload": {"force": True}}, ensure_ascii=False).encode("utf-8")
            status, response = core_request("/api/events", method="POST", body=body)
            self._send(status, response, "application/json; charset=utf-8", no_store=True)
            return

        if self.path == "/gov/universe/override":
            raw = self.rfile.read(declared_length) if declared_length > 0 else b"{}"
            try:
                request = json.loads(raw)
            except (TypeError, ValueError):
                self._json(400, {"ok": False, "error": "JSON غير صالح"})
                return
            symbol = str(request.get("symbol") or "").strip().upper()
            decision = str(request.get("decision") or "").strip().upper()
            if not re.fullmatch(r"[A-Z0-9]+_[A-Z0-9]+", symbol) or decision not in {"ALLOW", "DENY", "NEUTRAL"}:
                self._json(400, {"ok": False, "error": "رمز futures صحيح وقرار ALLOW/DENY/NEUTRAL مطلوب"})
                return
            event = {
                "name": "crypto.universe.override.command",
                "payload": {
                    "symbol": symbol,
                    "decision": decision,
                    "scope": str(request.get("scope") or "BOTH").upper(),
                    "reason": str(request.get("reason") or "dashboard"),
                    "operator": str(request.get("operator") or "dashboard"),
                    "command_id": secrets.token_hex(12),
                },
            }
            status, response = core_request("/api/events", method="POST", body=json.dumps(event, ensure_ascii=False).encode("utf-8"))
            self._send(status, response, "application/json; charset=utf-8", no_store=True)
            return

        if self.path == "/gov/command":
            # أمر المالك الخطِر — خطوتان: طلب → ملخّص/رمز → تأكيد → 901.
            length = declared_length
            raw = self.rfile.read(length) if length > 0 else b"{}"
            try:
                body_obj = json.loads(raw)
            except Exception:
                body_obj = {}
            action = str(body_obj.get("action", ""))
            token = str(body_obj.get("confirm", ""))
            operator = str(body_obj.get("operator", "dashboard"))   # من أين جاء الأمر
            payload = body_obj.get("payload") if isinstance(body_obj.get("payload"), dict) else {}
            payload_json = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            now = time.time()
            with _CONFIRM_LOCK:
                for t in [t for t, (_, _, _, ts) in list(_pending_confirms.items())
                          if now - ts > _CONFIRM_TTL_S]:
                    _pending_confirms.pop(t, None)
            if action not in _DANGER_COMMANDS:
                self._json(400, {"error": "أمر غير معروف"})
                return
            if not token:
                if action == "activate_asset":
                    account_id = str(payload.get("account_id") or "").strip()
                    symbol = str(payload.get("symbol") or "").strip()
                    try:
                        budget = float(payload.get("budget"))
                    except (TypeError, ValueError):
                        budget = 0.0
                    if not account_id or not symbol or budget <= 0:
                        self._json(400, {"error": "لازم رقم الحساب والرمز وميزانية موجبة"})
                        return
                if action == "execution_gate":
                    # حكم المالك ٢٠٢٦-٠٨-١٦: مفتاح البوّابة على اللوحة.
                    # `enabled` لا بدّ أن يكون منطقيًّا صريحًا — القيمة الناقصة
                    # أو المشوّهة لا تُقرأ «افتح» أبدًا.
                    if str(payload.get("gate") or "") not in ("552", "575", "both") \
                            or not isinstance(payload.get("enabled"), bool):
                        self._json(400, {"error": "لازم تحديد البوّابة وحالة صحيحة"})
                        return
                if action == "deactivate_asset":
                    # حكم المالك ٢٠٢٦-٠٨-١٥: الإطفاء لا يطلب رقمًا أبدًا.
                    if (not str(payload.get("account_id") or "").strip()
                            or not str(payload.get("symbol") or "").strip()):
                        self._json(400, {"error": "لازم رقم الحساب والرمز"})
                        return
                if action == "analysis_setting":
                    account_id = str(payload.get("account_id") or "").strip()
                    symbol = str(payload.get("symbol") or "").strip()
                    analyzer_id = str(payload.get("analyzer_id") or "").strip()
                    settings = payload.get("settings")
                    # §١٢ — الأقسام تُعاير كما تُعاير المحلّلات: المعرّف إمّا
                    # محلّل من الخمسة عشر أو قسم من SECTION_IDS (فُكّ الحظر
                    # الذي كان يحصر المعايرة بالمحلّلين — بند ٢٢/أ٧).
                    # ⛔ قائمة العيارات تُقرأ من المحرّك، لا تُنسخ هنا: نسخةٌ
                    #    محفورة كانت ترفض العتبات الثلاث المختومة (٢٠٢٦-٠٨-٢١)
                    #    قبل أن تصل البوّابة أصلًا — رفضٌ من حارسٍ ثالث لا
                    #    يعرف أحدٌ أنّه يحرس.
                    table = payload.get("weights")
                    if isinstance(table, dict) and table:
                        # جدول أوزان معسكر كامل بأمر واحد — الخمسة عشر
                        # مجتمعين ومجموعهم 100، وإلّا رُفض قبل البوّابة.
                        valid = bool(account_id and symbol
                                     and set(table) == set(_ANALYSIS_DEFAULT_WEIGHTS))
                        if valid:
                            try:
                                values = [float(v) for v in table.values()]
                                valid = (all(0 <= v <= 100 for v in values)
                                         and abs(sum(values) - 100.0) <= 0.01)
                            except (TypeError, ValueError):
                                valid = False
                    else:
                        valid = bool(account_id and symbol
                                     and (analyzer_id in _ANALYSIS_DEFAULT_WEIGHTS
                                          or analyzer_id in _SECTION_IDS)
                                     and isinstance(settings, dict) and settings
                                     and not (set(settings) - _ANALYSIS_TUNABLE))
                        if valid:
                            try:
                                valid = all(0 <= float(value) <= 100 for value in settings.values())
                            except (TypeError, ValueError):
                                valid = False
                    if not valid:
                        self._json(400, {"error": "لازم الحساب والأصل والمحلل أو القسم وقيم بين صفر ومئة"})
                        return
                if action == "parameter_approve":
                    parameter_name = str(payload.get("name") or "").strip()
                    try:
                        parameter_value = float(payload.get("value"))
                    except (TypeError, ValueError):
                        parameter_value = float("nan")
                    if (parameter_name not in _DECLARED_PARAMETERS
                            or parameter_value != parameter_value
                            or parameter_value in (float("inf"), float("-inf"))):
                        self._json(400, {"error": "لازم اسم مُعامِل معلن من السجلّ وقيمة رقمية"})
                        return
                if action == "tilt_rule":
                    # ث٣ (ق١٠ §١٨–٢١): حقل من الستّة القابلة للترجيح حصرًا
                    # (state وweight مرفوضان — حاجز وعامل لا سلّمان)، جهة
                    # من الثلاث، نقاط [عتبة، مقدار] تصاعدية، وتفعيل صريح.
                    if (str(payload.get("field") or "") not in _TILT_FIELD_AR
                            or str(payload.get("side") or "") not in _TILT_SIDE_AR
                            or not isinstance(payload.get("enabled"), bool)
                            or not _tilt_points_valid(payload.get("points"))
                            or set(payload) - {"field", "side", "points", "enabled"}):
                        self._json(400, {"error": "لازم حقل من الستّة القابلة للترجيح وجهة صحيحة "
                                                  "ونقاط [عتبة، مقدار] رقمية مرتبة تصاعديًّا (حتى 12) وحالة تفعيل صريحة"})
                        return
                if action == "asset_control":
                    account_id = str(payload.get("account_id") or "").strip()
                    symbol = str(payload.get("symbol") or "").strip()
                    command = str(payload.get("command") or "").upper()
                    # ٢٠٢٦-٠٩-٢٣ (ختم nq): `RESET_LEDGER` — أمر المالك ٢٠٢٦-٠٩-١٠ بتصفير
                    # دفتر خسارة الأصل (٥١٨) كان بلا زرّ. يمرّ بالتأكيد بخطوتين.
                    allowed = {"PAUSE", "RESUME", "FREEZE", "UNFREEZE", "CALIBRATE", "FORCE_RECONCILE", "SET_BUDGET", "SET_MAX_PER_SYMBOL", "RESET_LEDGER"}
                    if not account_id or not symbol or command not in allowed:
                        self._json(400, {"error": "لازم الحساب والرمز وأمر أصل صحيح"})
                        return
                    if command == "CALIBRATE":
                        try: dial = float(payload.get("dial"))
                        except (TypeError, ValueError): dial = float("nan")
                        if not (dial == dial):
                            self._json(400, {"error": "أدخل عيارًا رقميًا"})
                            return
                    if command == "SET_BUDGET":
                        try: budget = float(payload.get("risk_budget"))
                        except (TypeError, ValueError): budget = 0.0
                        if budget <= 0:
                            self._json(400, {"error": "أدخل ميزانية موجبة"})
                            return
                    if command == "SET_MAX_PER_SYMBOL":
                        # حكم المالك ٢٠٢٦-٠٨-١٦: رقم مخاطرة على اللوحة لا في ملفّ.
                        try: limit = int(float(payload.get("max_per_symbol")))
                        except (TypeError, ValueError): limit = 0
                        if limit < 1:
                            self._json(400, {"error": "أدخل حدًّا لا يقلّ عن ١"})
                            return
                if action == "account_limits":
                    command = str(payload.get("command") or "").upper()
                    if command not in ("SET", "RELEASE_TOTAL") or (command == "SET" and not isinstance(payload.get("settings"), dict)):
                        self._json(400, {"error": "لازم أمر حدود صحيح: تعديل الأرقام أو إعادة التداول"})
                        return
                if action == "atom_stop":
                    raw_id = payload.get("atom_id")
                    stop_id = raw_id if isinstance(raw_id, int) and not isinstance(raw_id, bool) else -1
                    if stop_id not in CRITICAL_ATOMS or set(payload) - {"atom_id"}:
                        self._json(400, {"error": "الختم لإيقاف ذرّةٍ حرجة وحدها — وغير الحرجة تُوقف بزرّها"})
                        return
                t = secrets.token_hex(8)
                with _CONFIRM_LOCK:
                    _pending_confirms[t] = (action, payload_json, operator, now)
                summary = _DANGER_COMMANDS[action]
                if action == "activate_asset":
                    summary += f"\nالحساب: {payload.get('account_id')} · الأصل: {payload.get('symbol')} · ميزانية المخاطرة: ${payload.get('budget')}"
                if action == "execution_gate":
                    state = "فتح" if payload.get("enabled") else "إيقاف"
                    summary += f"\nالبوّابة: {payload.get('gate')} · الحالة المطلوبة: {state}"
                if action == "deactivate_asset":
                    summary += f"\nالحساب: {payload.get('account_id')} · الأصل: {payload.get('symbol')}"
                if action == "asset_control":
                    summary += f"\nالحساب: {payload.get('account_id')} · الأصل: {payload.get('symbol')} · الأمر: {payload.get('command')}"
                    if str(payload.get("command") or "").upper() == "RESET_LEDGER":
                        summary += ("\n⚠️ يمحو الخسارة المحقّقة لهذا الأصل من دفتر ٥١٨ ويبدأ دفترًا جديدًا"
                                    " — فيرفع التجميد الذي سبّبته. المحوُ يُسجَّل ولا يُرجَع.")
                if action == "parameter_approve":
                    summary += ("\nالمُعامِل: %s (%s) · القيمة المعتمدة: %s"
                                % (_PARAMETER_AR.get(str(payload.get("name")), "غير معروف"),
                                   payload.get("name"), payload.get("value")))
                if action == "account_limits":
                    if str(payload.get("command") or "").upper() == "RELEASE_TOTAL":
                        summary += "\nإعادة التداول بعد التراجع الكلّيّ — وإن بقيت الحقوق تحت الحدّ يقف ثانيةً"
                    else:
                        names = {"initial_balance": "الرصيد الابتدائيّ", "pair_risk_pct": "مخاطرة الصفقة لكلّ زوج ٪", "pair_daily_pct": "حدّ كلّ زوج اليوميّ ٪",
                                 "daily_pct": "الحدّ اليوميّ الشامل ٪", "total_pct": "التراجع الكلّيّ ٪"}
                        settings = payload.get("settings") or {}
                        parts = [f"{names.get(k, k)}: {v}" for k, v in settings.items() if k != "pairs"]
                        for sym, row in (settings.get("pairs") or {}).items():
                            parts.append(f"{sym}: مخاطرة الصفقة {row.get('risk_pct', '—')}٪ · حدّ اليوم {row.get('daily_pct', '—')}٪")
                        summary += "\n" + " · ".join(parts)
                if action == "atom_stop":
                    name, falls = CRITICAL_ATOMS[payload["atom_id"]]
                    summary += f"\nالذرّة: {payload['atom_id']} «{name}» — {falls}.\nلا تعود إلّا بزرّ «شغّل»."
                if action == "decision_setting":
                    # ٢٠٢٦-١٠-٢٦: كان الملخّص الجملة العامّة وحدها، فدفعة «اعتماد الكلّ» تعرض الجملة نفسها لكلّ عيار.
                    # والاسم العربيّ للعيار تضعه الواجهة بجانبه (رمزه الإنكليزيّ لا يُعرض على المالك).
                    summary += f"\nالقيمة المطلوبة: {payload.get('value')}"
                if action == "tilt_rule":
                    tilt_points = payload.get("points") or []
                    summary += ("\nالحقل: %s · الجهة: %s · عدد النقاط: %d · القاعدة: %s"
                                % (_TILT_FIELD_AR.get(str(payload.get("field")), "غير معروف"),
                                   _TILT_SIDE_AR.get(str(payload.get("side")), "غير معروف"),
                                   len(tilt_points),
                                   "مفعّلة" if payload.get("enabled") else "معطّلة"))
                    if len(tilt_points) == 0:
                        summary += " (بلا نقاط — مسح المنحنى)"
                if action == "analysis_setting":
                    analyzer_names = {"trend": "الاتجاه", "momentum": "الزخم", "volatility": "التذبذب",
                        "volume": "الحجم", "spread": "السبريد", "candle": "الشموع", "gap": "الفجوات",
                        "session": "الجلسات", "time": "أثر الوقت", "velocity": "السرعة",
                        "acceleration": "التسارع", "volume_quality": "جودة الحجم", "noise": "الضوضاء",
                        "correlation": "الارتباط", "relative_strength": "القوة النسبية",
                        "150": "قسم التحليل", "200": "قسم البنية", "250": "قسم السيولة",
                        "300": "قسم الإحصاء", "350": "قسم الاحتمالات", "400": "قسم الاستراتيجيات"}
                    # نصّ التأكيد يسمّي كل عيار بالعربي — عيارٌ بلا اسم يظهر
                    # إنكليزيًّا خامًا في اللحظة التي يوافق فيها المالك.
                    setting_names = {"required_depth": "العمق المطلوب",
                                     "confidence_threshold": "عيار الثقة",
                                     "strength_threshold": "عتبة القوّة",
                                     "stale_after_s": "مهلة الطزاجة (ثانية)",
                                     "direction_neutral_band": "المنطقة الحيادية",
                                     "weight": "الوزن"}
                    values = " · ".join(f"{setting_names.get(key, key)}: {value}"
                                        for key, value in (payload.get("settings") or {}).items())
                    path_names = {"fast": "سريع · تِكّات", "slow": "بطيء · شموع"}
                    path_text = path_names.get(str(payload.get("path") or "fast"), "سريع · تِكّات")
                    summary += (f"\nالحساب: {payload.get('account_id')} · الأصل: {payload.get('symbol')}"
                                f" · المحلل: {analyzer_names.get(str(payload.get('analyzer_id')), 'غير معروف')}"
                                f" · المسار: {path_text} · {values}")
                self._json(200, {"stage": "confirm", "token": t,
                                 "summary": summary,
                                 "ttl_s": int(_CONFIRM_TTL_S)})
                return
            with _CONFIRM_LOCK:
                pend = _pending_confirms.pop(token, None)
            if (pend is None or pend[0] != action or pend[1] != payload_json or pend[2] != operator):
                self._json(409, {"error": "التأكيد غير صالح أو تغيّرت بيانات الأصل — أعد الأمر"})
                return
            if action == "atom_stop":
                status, obj = sealed_atom_stop(int(payload["atom_id"]), operator)
                self._json(status, obj)
                return
            status, obj = queue_command(action, payload, operator)
            self._json(status, obj)
            return

        lab_path = self.path.split("?", 1)[0]
        if lab_path.startswith("/gov/backtest"):
            raw = self.rfile.read(declared_length) if declared_length > 0 else b"{}"
            try:
                body_obj = json.loads(raw) if raw else {}
            except Exception:
                self._json(400, {"ok": False, "error": "JSON غير صالح"})
                return
            if not isinstance(body_obj, dict):
                self._json(400, {"ok": False, "error": "الحمولة يجب أن تكون object"})
                return
            try:
                from backtest.trade_replay import handle_backtest as _handle_bt
            except Exception as exc:  # noqa: BLE001
                self._json(500, {"ok": False, "error": "باك تست غير متاح: %s" % type(exc).__name__})
                return
            obj = _handle_bt("POST", lab_path, body_obj)
            self._json(200 if obj.get("ok") else 400, obj)
            return

        if lab_path.startswith("/gov/lab"):
            raw = self.rfile.read(declared_length) if declared_length > 0 else b"{}"
            try:
                body_obj = json.loads(raw) if raw else {}
            except Exception:
                self._json(400, {"ok": False, "error": "JSON غير صالح"})
                return
            if not isinstance(body_obj, dict):
                self._json(400, {"ok": False, "error": "الحمولة يجب أن تكون object"})
                return
            try:
                from backtest.atom_lab import handle_lab as _handle_lab
            except Exception as exc:  # noqa: BLE001
                self._json(500, {"ok": False, "error": "مختبر غير متاح: %s" % type(exc).__name__})
                return
            obj = _handle_lab("POST", lab_path, body_obj)
            self._json(200 if obj.get("ok") else 400, obj)
            return

        self._send(404, b"not found", "text/plain; charset=utf-8")

    # ── تقديم واجهة React المبنيّة (SPA) ──
    def _serve_static(self, p: str) -> None:
        rel = "index.html" if p in ("/", "/index.html") else p.lstrip("/")
        f = (DIST / rel).resolve()
        if not f.is_relative_to(DIST.resolve()) or not f.is_file():
            # SPA fallback: أي مسار غير موجود → index.html (لو الواجهة مبنيّة)
            f = DIST / "index.html"
        if not f.is_file():
            self._send(200, "الواجهة المبنية غير موجودة داخل governance/ui/built".encode("utf-8"),
                       "text/plain; charset=utf-8")
            return
        ctypes = {".html": "text/html", ".js": "text/javascript", ".css": "text/css",
                  ".svg": "image/svg+xml", ".json": "application/json", ".woff2": "font/woff2"}
        # index.html بلا تخزين (يشير دائمًا لأحدث كود) · الأصول المُجزّأة تُخزَّن (ثابتة الاسم)
        self._send(200, f.read_bytes(),
                   ctypes.get(f.suffix, "application/octet-stream") + "; charset=utf-8",
                   no_store=(f.name == "index.html"))

    def log_message(self, *_a) -> None:               # صمت — لا ضجيج بالترمنال
        pass


def main() -> None:
    # التحكم عن بعد (ورقة ١٧): وجود var/governance/remote_on.txt = افتح للشبكة (خلف Tailscale)
    remote = REMOTE_FLAG.is_file()
    if remote and not GOV_API_KEY:
        # المرحلة ١٦ — حماية API: STARTUP = FAIL (ليس مجرد warning)
        raise RuntimeError(
            "SECURITY_VIOLATION: remote governance (host != 127.0.0.1) "
            "requires QUANT_GOV_API_KEY. "
            "Startup BLOCKED — set the environment variable or remove "
            f"{REMOTE_FLAG} to bind localhost only."
        )
    bind = "0.0.0.0" if remote else "127.0.0.1"
    srv = ThreadingHTTPServer((bind, PORT), Handler)
    print("=" * 54)
    print("  غرفة القيادة — الباك-إند (طبقة الحوكمة)")
    print(f"  يقرا النواة:   {CORE}")
    print(f"  افتح المتصفّح:  http://127.0.0.1:{PORT}")
    if remote:
        print("  🌐 التحكم عن بعد مُفعَّل — اللوحة مفتوحة للشبكة (خلّيها خلف Tailscale)")
    print("  (أوقفه: Ctrl+C)")
    print("=" * 54)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        srv.shutdown()


if __name__ == "__main__":
    main()
