# -*- coding: utf-8 -*-
"""الاختبار التاريخيّ الكامل — النظام كلّه على تِكّات سي‑تريدر حقيقيّة.

ختم المالك ٢٠٢٦-١٠-٠٥: «هلق بدك تفتح صفقة يكون كل اقسام مشتركين فيها … كل اوزان والاعتمادات
ونوافذ بدها تعديل لهيك عمد شي اسمه باك تست تختبر تداول و كل سستم على بيانات تاريخية لي عم
تسحبها فيك تختبر هنيك فيك تغير كل اعتماديات … nq». وقراره في سؤال البيانات: «الاثنان» —
التِكّات المسجّلة الآن، وطلب التِكّات التاريخيّة من سي‑تريدر للمدد الأطول.

يبني على ما ختمه المالك ٢٠٢٦-٠٩-٠٢ («ختم مصدر المختبر والباك تست»): تحميل الذرّات الحقيقيّة
بعقد الـBootloader (`backtest/runner.py`) على ناقلٍ متزامن. ويضيف:

١· **تِكّات سي‑تريدر حقيقيّة لكلّ الرموز بترتيبها الزمنيّ الحقيقيّ** — قاعدة التِكّات المسجّلة
   (`market_data`، قراءة فقط). لا تِكّة تُخترع (ختم ٠٩-٠٢)، ولا إعادة برمزٍ واحد (درس
   «الإعادة برمزٍ واحد عمياء» ٠٩-١٩: التداخل الحقيقيّ شرطٌ لا حجم).
٢· **عزلٌ كامل**: مجلّد تشغيلٍ خاصّ، ونسخةٌ من عيارات المالك المعتمدة الحيّة (التعديل على النسخة
   وحدها)، وجسرُ إكسبرت معزول. وذرّةٌ في إعدادها مسارٌ مطلق خارج مجلّد التشغيل **لا تُحمَّل**
   وتُسمّى في التقرير — فلا يُمسّ ملفٌّ حيّ ولا حساب ولا شبكة.
٣· **ساعةٌ تسير مع البيانات**: الساعة الرسميّة و`time.time` على زمن التِكّة، وجودة الساعة
   متزامنة (552 يرفض بلا ذلك). نبضات 806 (ثانية/٥د/١٥د/ساعة/يوم) بزمن البيانات.
٤· **محاكي إكسبرت بعقد `mt5/QUANT_NQ.mq5` حرفيًّا**: يقرأ أوامر 601 من الجسر المعزول، وينفّذ
   OPEN/CLOSE/CLOSE_PARTIAL/MODIFY_SL/MODIFY_TP على سعر التِكّة (الشراء على العرض والبيع على
   الطلب)، ويغلق بالوقف والهدف على أوّل تِكّةٍ تعبرهما، ويكتب `trade_events_v2` و`positions_v2`
   و`account_v2` كما يكتبها الإكسبرت (توقيت الخادم = غرينتش + ٣ ساعات، مقيس). والعمولة مقيسة من
   سجلّ الحساب: 3.50$ للّوت لكلّ اتّجاه على الذهب والعملات، وصفر على البتكوين والمؤشّرات.
   ثمّ تقرؤه ذرّات النظام الحقيقيّة 609/611/619/618 كما تقرأ الإكسبرت الحيّ.
٥· **تقرير**: الصفقات والربح والسحب، ومشاركة كلّ قسمٍ في كلّ قرار وعند كلّ أمر دخول.

حدود معلنة (لا تُخفى):
· عرض ميتاتريدر يُستعار من تِكّة سي‑تريدر نفسها (الوسيط واحد).
· لا دفتر عمقٍ تاريخيّ ⟸ ذرّات العمق (261–264) صامتة كما ستكون.
· `time.monotonic` يبقى حقيقيًّا: مؤقّتاتٌ رتيبة داخل بعض الذرّات تنضغط مع سرعة الإعادة.
· ذرّات الشبكة والمراجع الخارجيّة (108–111، 608، 616، 620–626، 630) خارج الإعادة.

التشغيل:  vendor\\python\\runtime\\python.exe -m backtest.full_replay --from 2026-10-02T06:10 --to 2026-10-02T07:10
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import json
import os
import sqlite3
import sys
import time
import uuid
from collections import Counter, defaultdict, deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

LIVE_RUNTIME = ROOT / "forex_runtime"
LIVE_TICKS_DB = LIVE_RUNTIME / "var" / "store" / "market_data.db"
LIVE_SETTINGS_DB = LIVE_RUNTIME / "var" / "store" / "analysis_settings.db"
LIVE_BRIDGE_DB = Path(os.environ.get("APPDATA", "")) / "MetaQuotes" / "Terminal" / "Common" / "Files" / "nq_brain.db"
RUNS_DIR = LIVE_RUNTIME / "var" / "backtest_runs"

ACCOUNT_ID = "52992818"            # الهويّة كما في التِكّات المسجّلة — عيارات المالك لكلّ (حساب، وسيط، رمز)
BROKER = "Raw Trading Ltd"
SERVER_OFFSET_S = 10800            # مقيس: open_time − written_at = 10800 في سجلّ الإكسبرت
COMMISSION_PER_LOT_SIDE = {"XAUUSD": -3.5, "EURUSD": -3.5, "GBPUSD": -3.5}   # مقيس؛ غيرها صفر
TICKET_BASE = 9_000_000_000
LEVERAGE = 5000                    # الحساب الحيّ (account_v2)
SYMBOLS = ("XAUUSD", "BTCUSD", "USTEC", "US30", "US500", "EURUSD", "GBPUSD")
PULSES = (("SYS_SECOND", 1), ("SYS_5MIN", 300), ("SYS_15MIN", 900), ("SYS_HOUR", 3600), ("SYS_DAY", 86400))

ATOM_RANGES = ((100, 599), (650, 699))
BRIDGE_ATOMS = (601, 609, 611, 616, 618, 619)
EXTRA_ATOMS = (613, 708, 830)         # 613 موزّع التغذية من قسم 600 — باب التِّكّة الحيّ
# 708 سجلّ الرموز (قسم 700): مجيبُ «ترجمة الرمز» لبوّابة 527 — بدونه سقط كلّ أمر دخول في الإعادة
# `SYMBOL_RESOLUTION_TIMEOUT` (مقيس ٢٠٢٦-١٠-٠٦: 9 من 9). بلا مسار قرصٍ في إعداده.
# الشبكة والمراجع الخارجيّة والتغذية الحيّة. ٢٠٢٦-١٠-٠٦: 613/112/616/109 عادت — قِيس على البتكوين
# أنّ مرشّح القرار 454 حجب 17,962 من 17,962 بثلاثة أسبابٍ كلّها بيئةٌ أبعدتُها: التقويم مجهول
# (616 يقرأ جدول الإكسبرت لا الشبكة، و109 يبنيه)، وجودة السوق مجهولة (115 يقرأ `market.tick` من
# 613)، والتغذية «لم تُرَ» (116 لا يعدّها حيّة إلّا من `feed.ctrader.raw`). فالتِّكّة تدخل من بابها الحيّ.
DENY = frozenset({108, 110, 111, 608, 620, 621, 622, 623, 624, 625, 626, 630})
BRIDGE_TABLES_COPIED = ("calendar", "calendar_ff", "news")      # التقويم والأخبار الحقيقيّة لجسر الأخبار
SECTION_FAMILIES = ("analysis", "structure", "liquidity", "stats", "probability", "strategy")
# ٢٠٢٦-١٠-٠٩: 411 · 412 · 414 · 465 — سلسلة القرار منذ ١٠-٠٧ (البطاقة 414 وحدها تقرّر)؛ كانت القائمة على الأرشيف.
DECISION_CHAIN = (201, 411, 412, 414, 465, 404, 405, 406, 409, 410, 413,
                  450, 451, 452, 453, 454, 455, 456, 457, 458, 460, 461, 462, 463, 464, 466, 467, 468,
                  512, 513, 516, 518, 551, 552, 555, 601)


# ─────────────────────────────────────────────────────────── التهيئة المعزولة ──

CALIB_FIELDS = ("required_depth", "confidence_threshold", "strength_threshold", "stale_after_s",
                "direction_neutral_band", "weight")


def parse_calib(item: str) -> tuple[str, str, str, str, float]:
    """«SYMBOL:ANALYZER:PATH:field=value» — `*` لكلّ رمز/مسار. على نسخة العيارات وحدها."""
    head, value = item.split("=", 1)
    symbol, analyzer, path, field = head.split(":")
    if field not in CALIB_FIELDS:
        raise ValueError("حقل عيار غير معروف: %s (المسموح: %s)" % (field, ", ".join(CALIB_FIELDS)))
    return symbol.upper(), analyzer, path, field, float(value)


def prepare_run_dir(run_dir: Path, overrides: dict[str, float],
                    calibs: list[tuple[str, str, str, str, float]] | None = None) -> dict[str, str]:
    """مجلّد التشغيل: نسخة العيارات المعتمدة، وجسرٌ بمخطّط الإكسبرت ومواصفاته. يُرجع متغيّرات البيئة."""
    store = run_dir / "var" / "store"
    store.mkdir(parents=True, exist_ok=True)
    (run_dir / "bridge").mkdir(parents=True, exist_ok=True)
    settings = store / "analysis_settings.db"
    src = sqlite3.connect("file:%s?mode=ro" % LIVE_SETTINGS_DB, uri=True)
    dst = sqlite3.connect(str(settings))
    src.backup(dst)
    src.close()
    applied = []
    for name, value in overrides.items():
        cur = dst.execute("UPDATE parameters SET value=?, status='APPROVED', source='BACKTEST', "
                          "approved_by='backtest' WHERE name=?", (float(value), name))
        applied.append((name, value, cur.rowcount))
    for symbol, analyzer, path, field, value in calibs or ():
        cur = dst.execute(
            "UPDATE analysis_settings SET %s=?, updated_by='backtest' WHERE (?='*' OR symbol=?) "
            "AND analyzer_id=? AND (?='*' OR path=?)" % field,
            (value, symbol, symbol, analyzer, path, path))
        applied.append(("%s:%s:%s:%s" % (symbol, analyzer, path, field), value, cur.rowcount))
    dst.commit()
    dst.close()
    bridge = run_dir / "bridge" / "nq_brain.db"
    live = sqlite3.connect("file:%s?mode=ro" % LIVE_BRIDGE_DB, uri=True)
    schema = [r[0] for r in live.execute(
        "SELECT sql FROM sqlite_master WHERE sql IS NOT NULL AND name NOT LIKE 'sqlite_%' "
        "ORDER BY type='index'")]
    specs = live.execute("SELECT * FROM symbol_specs_v2 WHERE account_id=?", (ACCOUNT_ID,)).fetchall()
    spec_cols = [d[0] for d in live.execute("SELECT * FROM symbol_specs_v2 LIMIT 0").description]
    copied = {}
    for table in BRIDGE_TABLES_COPIED:
        try:
            cols = [d[0] for d in live.execute("SELECT * FROM %s LIMIT 0" % table).description]
            copied[table] = (cols, live.execute("SELECT * FROM %s" % table).fetchall())
        except sqlite3.Error:
            continue
    live.close()
    out = sqlite3.connect(str(bridge))
    out.execute("PRAGMA journal_mode=WAL")
    for sql in schema:
        out.execute(sql.replace("CREATE TABLE ", "CREATE TABLE IF NOT EXISTS ", 1)
                    .replace("CREATE INDEX ", "CREATE INDEX IF NOT EXISTS ", 1)
                    if "IF NOT EXISTS" not in sql else sql)
    out.executemany("INSERT OR REPLACE INTO symbol_specs_v2 (%s) VALUES (%s)"
                    % (",".join(spec_cols), ",".join("?" * len(spec_cols))), specs)
    for table, (cols, rows) in copied.items():
        out.executemany("INSERT OR REPLACE INTO %s (%s) VALUES (%s)"
                        % (table, ",".join(cols), ",".join("?" * len(cols))), rows)
    out.commit()
    out.close()
    (run_dir / "overrides_applied.json").write_text(
        json.dumps(applied, ensure_ascii=False, indent=1), encoding="utf-8")
    return {
        "QUANT_RUNTIME_ROOT": str(run_dir), "QUANT_CORE_STATE_ROOT": str(run_dir / "var"),
        "QUANT_ANALYSIS_SETTINGS_DB": str(settings), "QUANT_GOV_MARKET": "forex",
        "QUANT_REPLAY_CLOCK": "1", "QUANT_REPLAY_NO_WARM": "1", "NQ_BRIDGE_DB": str(bridge),
    }


class ReplayTime:
    """الزمن الرسميّ و`time.time` على زمن البيانات؛ وجودة الساعة متزامنة."""

    def __init__(self) -> None:
        self.now = 0.0
        self._saved: list[tuple[Any, str, Any]] = []

    def install(self) -> None:
        import clock.clock as clock_module
        target = clock_module._CLOCK
        real_monotonic = time.monotonic
        mono0, data0 = real_monotonic(), self.now
        last = [mono0]

        def monotonic() -> float:
            # ٢٠٢٦-١٠-٠٦: مهلُ الذرّات بـ`time.monotonic` (طلبٌ في الطريق 90ث عند 555، عمر الحجم والإعداد
            # 30ث، حجوزات 516/518) كانت بساعة الجدار والإعادة أسرع منها نحو عشرين مرّة — فطلبٌ واحد يحجب
            # الرمز نصف ساعةٍ من زمن البيانات (مقيس على `warm-btc3`: `REQUEST_IN_FLIGHT`×280 بعد أمرٍ واحد).
            # الآن تمشي بزمن البيانات، ولا تتأخّر عن الجدار أبدًا فلا تتعطّل مهل الحلقة نفسها، ولا ترجع.
            value = max(last[0], real_monotonic(), mono0 + (self.now - data0))
            last[0] = value
            return value
        for obj, name, value in ((target, "now", lambda: self.now),
                                 (target, "quality", lambda: clock_module.SYNCED),
                                 (time, "time", lambda: self.now),
                                 (time, "monotonic", monotonic)):
            self._saved.append((obj, name, getattr(obj, name)))
            setattr(obj, name, value)

    def restore(self) -> None:
        for obj, name, value in reversed(self._saved):
            setattr(obj, name, value)
        self._saved.clear()


def _replay_speedups(run_dir: Path) -> dict[str, Any]:
    """تسريعان للإعادة وحدها، لا يغيّران قرارًا — مقيسان بالملمح ٢٠٢٦-١٠-٠٦ على 4000 تِكّة (226ث):

    ١· `sqlite3` بلا انتظار القرص على قواعد مجلّد التشغيل (`synchronous=OFF`): commit/close/execute
       كانت ≈52ث (23%) — قواعدُ تُرمى بعد التشغيل لا تحتاج متانةً عند انقطاع التيّار. وما يُفتح
       للقراءة وحدها (`mode=ro`، تِكّات الحيّ ومخزن سي‑تريدر) لا يُمسّ.
    ٢· سجلّ العيارات ثابتٌ طوال التشغيل (نسخته في مجلّد التشغيل، وعياراتها مطبَّقة قبل الإقلاع): مساره
       وبصمة حداثته يُحسبان مرّة. كانت `_registry_path`/بصمة البيئة/`stat` ≈40ث (15%) لـ1.2 مليون نداء.
    """
    import shared.parameter_registry as registry
    real_connect = sqlite3.connect
    root = str(run_dir.resolve()).lower()

    def connect(database: Any, *args: Any, **kwargs: Any) -> sqlite3.Connection:
        conn = real_connect(database, *args, **kwargs)
        target = str(database)
        if "mode=ro" not in target:
            try:
                resolved = str(Path(target).resolve()).lower() if not target.startswith("file:") else ""
            except (OSError, ValueError):
                resolved = ""
            if resolved.startswith(root):
                try:
                    conn.execute("PRAGMA synchronous=OFF")
                except sqlite3.Error:
                    pass
        return conn
    sqlite3.connect = connect
    path = registry._registry_path()
    mtime = registry._registry_mtime()
    registry._registry_path = lambda: path
    registry._registry_mtime = lambda: mtime
    return {"settings_db": path}


def _live_path(value: Any, run_dir: Path) -> bool:
    """قيمة إعدادٍ تشير إلى ملفٍّ خارج مجلّد التشغيل."""
    if not isinstance(value, str):
        return False
    text = value.strip()
    if "%APPDATA%" in text.upper():
        return True
    if not (len(text) > 2 and (os.path.isabs(text) or text[1:3] in (":\\", ":/"))):
        return False
    try:
        Path(text).resolve().relative_to(run_dir.resolve())
        return False
    except ValueError:
        return True


def _walk_values(config: Any):
    if isinstance(config, dict):
        for value in config.values():
            yield from _walk_values(value)
    elif isinstance(config, list):
        for value in config:
            yield from _walk_values(value)
    else:
        yield config


# ─────────────────────────────────────────────────────────── محاكي الإكسبرت ──

class PaperBroker:
    """عقد `mt5/QUANT_NQ.mq5` على جسرٍ معزول — الأوامر من 601، والنتائج لـ609/611/619."""

    def __init__(self, bridge_path: Path, balance: float) -> None:
        self.db = sqlite3.connect(str(bridge_path))
        self.db.execute("PRAGMA journal_mode=WAL")
        self.balance = balance
        self.start_balance = balance
        self.trade_from = 0.0
        self.quotes: dict[str, tuple[float, float]] = {}
        self.positions: dict[int, dict[str, Any]] = {}
        self.closed: list[dict[str, Any]] = []
        self.rejected: Counter = Counter()
        self.next_ticket = TICKET_BASE
        self.equity_curve: list[tuple[float, float]] = []
        self.specs = {row[0]: {"contract": row[1] or 1.0, "margin": row[2]}
                      for row in self.db.execute(
                          "SELECT symbol, contract_size, margin_initial FROM symbol_specs_v2")}

    # ── أدوات ──
    def _contract(self, symbol: str) -> float:
        return float(self.specs.get(symbol, {}).get("contract") or 1.0)

    def _commission(self, symbol: str, volume: float) -> float:
        return round(COMMISSION_PER_LOT_SIDE.get(symbol, 0.0) * volume, 2)

    def _profit(self, pos: dict[str, Any], exit_price: float, volume: float) -> float:
        sign = 1.0 if pos["side"] == "BUY" else -1.0
        return round((exit_price - pos["entry"]) * sign * volume * self._contract(pos["symbol"]), 2)

    def _event(self, kind: str, ticket: int | None, symbol: str, side: str, volume: float,
               entry: float | None, exit_price: float | None, open_utc: float | None,
               close_utc: float | None, reason: str | None, request_id: str | None, now: float,
               profit: float | None = None, commission: float | None = None) -> None:
        broker = (lambda t: None if t is None else float(int(t + SERVER_OFFSET_S)))
        self.db.execute(
            "INSERT INTO trade_events_v2 (account_id,event_type,ticket,symbol,side,volume,entry_price,"
            "exit_price,open_time,close_time,reason,request_id,profit,commission,swap,fee,written_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (ACCOUNT_ID, kind, ticket, symbol, side, volume, entry, exit_price, broker(open_utc),
             broker(close_utc), reason or None, request_id or None, profit,
             commission, 0.0 if commission is not None else None,
             0.0 if commission is not None else None, int(now)))

    def _close(self, ticket: int, volume: float, price: float, reason: str, now: float) -> None:
        pos = self.positions[ticket]
        volume = min(volume, pos["volume"])
        profit = self._profit(pos, price, volume)
        commission = self._commission(pos["symbol"], volume)
        self.balance += profit + commission
        remaining = round(pos["volume"] - volume, 8)
        kind = "PARTIAL" if remaining > 1e-9 else "CLOSED"
        self._event(kind, ticket, pos["symbol"], pos["side"], volume, pos["entry"], price,
                    pos["opened"], now, reason, "", now, profit, commission)
        self.closed.append({"ticket": ticket, "symbol": pos["symbol"], "side": pos["side"],
                            "volume": volume, "entry": pos["entry"], "exit": price,
                            "opened_utc": pos["opened"], "closed_utc": now, "reason": reason,
                            "profit": profit, "commission": commission,
                            "entry_commission": pos["entry_commission"] if kind == "CLOSED" else 0.0,
                            "request_id": pos["request_id"], "kind": kind})
        if kind == "CLOSED":
            del self.positions[ticket]
        else:
            pos["volume"] = remaining

    # ── التِكّة: الوقف والهدف على أوّل تِكّةٍ تعبرهما ──
    def on_tick(self, symbol: str, bid: float, ask: float, now: float) -> None:
        self.quotes[symbol] = (bid, ask)
        for ticket in [t for t, p in self.positions.items() if p["symbol"] == symbol]:
            pos = self.positions[ticket]
            price = bid if pos["side"] == "BUY" else ask
            buy = pos["side"] == "BUY"
            sl, tp = pos["sl"], pos["tp"]
            if sl and ((buy and price <= sl) or (not buy and price >= sl)):
                self._close(ticket, pos["volume"], price, "SL", now)
            elif tp and ((buy and price >= tp) or (not buy and price <= tp)):
                self._close(ticket, pos["volume"], price, "TP", now)

    # ── الأوامر ──
    def process_commands(self, now: float) -> int:
        rows = self.db.execute(
            "SELECT id, request_id, action, symbol, side, volume, stop_loss, take_profit, ticket "
            "FROM commands WHERE status='PENDING' ORDER BY id").fetchall()
        for cid, request_id, action, symbol, side, volume, sl, tp, ticket in rows:
            ok, result, out_ticket = self._execute(action, symbol, side, volume or 0.0, sl, tp,
                                                   ticket, request_id, now)
            self.db.execute("UPDATE commands SET status=?, result=?, ticket=?, taken_at=?, done_at=? "
                            "WHERE id=?", ("DONE" if ok else "FAILED", result, out_ticket, now, now, cid))
            if not ok:
                self.rejected[result] += 1
        if rows:
            self.db.commit()
        return len(rows)

    def _execute(self, action: str, symbol: str, side: str, volume: float, sl: Any, tp: Any,
                 ticket: Any, request_id: str, now: float) -> tuple[bool, str, Any]:
        quote = self.quotes.get(symbol)
        if quote is None:
            return False, "NO_QUOTE", None
        bid, ask = quote
        if action == "OPEN" and now < self.trade_from:
            # شريحةٌ متوازية: ما قبل بدايتها إحماءٌ للتحليل فقط — لا صفقة تُحسب على شريحتين.
            return False, "WARMUP", None
        if action == "OPEN":
            if volume <= 0:
                return False, "NO_VOLUME", None
            if side not in ("BUY", "SELL"):
                return False, "BAD_SIDE", None
            if not sl or float(sl) <= 0:
                self._event("REJECTED", None, symbol, side, volume, None, None, None, None,
                            "NO_STOP", request_id, now)
                return False, "NO_STOP", None
            fill = ask if side == "BUY" else bid
            self.next_ticket += 1
            commission = self._commission(symbol, volume)
            self.balance += commission
            self.positions[self.next_ticket] = {
                "symbol": symbol, "side": side, "volume": volume, "entry": fill,
                "sl": float(sl or 0.0), "tp": float(tp or 0.0), "opened": now,
                "request_id": request_id, "entry_commission": commission}
            self._event("OPENED", self.next_ticket, symbol, side, volume, fill, None, now, None, "",
                        request_id, now, None, commission)
            return True, "OK", self.next_ticket
        pos_ticket = int(ticket) if ticket else next(
            (t for t, p in self.positions.items() if p["symbol"] == symbol), None)
        if pos_ticket not in self.positions:
            return False, "NO_POSITION", None
        pos = self.positions[pos_ticket]
        price = bid if pos["side"] == "BUY" else ask
        if action == "CLOSE":
            self._close(pos_ticket, pos["volume"], price, "SYSTEM", now)
            return True, "OK", pos_ticket
        if action == "CLOSE_PARTIAL":
            if volume <= 0:
                return False, "NO_VOLUME", None
            self._close(pos_ticket, volume, price, "SYSTEM", now)
            return True, "OK", pos_ticket
        if action in ("MODIFY_SL", "MODIFY_TP"):
            if action == "MODIFY_SL":
                pos["sl"] = float(sl or 0.0)
            else:
                pos["tp"] = float(tp or 0.0)
            return True, "OK", pos_ticket
        return False, "ACTION_NOT_SIMULATED", None

    def close_all(self, now: float, reason: str) -> int:
        """نهاية التشغيل: المفتوح يُغلق على آخر سعرٍ معلوم ويُعلَّم سببه — فلا ربحٌ عائم بلا حساب."""
        tickets = list(self.positions)
        for ticket in tickets:
            pos = self.positions[ticket]
            bid, ask = self.quotes.get(pos["symbol"], (pos["entry"], pos["entry"]))
            self._close(ticket, pos["volume"], bid if pos["side"] == "BUY" else ask, reason, now)
        if tickets:
            self.db.commit()
        return len(tickets)

    # ── الصورة: المراكز والحساب كما يكتبها الإكسبرت ──
    def floating(self) -> float:
        total = 0.0
        for pos in self.positions.values():
            bid, ask = self.quotes.get(pos["symbol"], (pos["entry"], pos["entry"]))
            total += self._profit(pos, bid if pos["side"] == "BUY" else ask, pos["volume"])
        return total

    def snapshot(self, now: float) -> None:
        self.db.execute("DELETE FROM positions_v2 WHERE account_id=?", (ACCOUNT_ID,))
        margin = 0.0
        for ticket, pos in self.positions.items():
            bid, ask = self.quotes.get(pos["symbol"], (pos["entry"], pos["entry"]))
            current = bid if pos["side"] == "BUY" else ask
            margin += pos["volume"] * self._contract(pos["symbol"]) * current / LEVERAGE
            self.db.execute(
                "INSERT INTO positions_v2 (account_id,ticket,symbol,side,volume,entry_price,current_price,"
                "stop_loss,take_profit,profit,swap,commission,magic,comment,opened_at,updated_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (ACCOUNT_ID, ticket, pos["symbol"], pos["side"], pos["volume"], pos["entry"], current,
                 pos["sl"], pos["tp"], self._profit(pos, current, pos["volume"]), 0.0,
                 pos["entry_commission"], 20260801, "NQ", pos["opened"] + SERVER_OFFSET_S, now))
        equity = self.balance + self.floating()
        self.db.execute(
            "INSERT OR REPLACE INTO account_v2 (account_id,balance,equity,margin,free_margin,margin_level,"
            "currency,leverage,open_count,updated_at,connected,trade_allowed,expert_allowed,bridge_beat,"
            "broker,account_server,margin_mode,expert_id,expert_version,project_build_id) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (ACCOUNT_ID, round(self.balance, 2), round(equity, 2), round(margin, 2),
             round(equity - margin, 2), (equity / margin * 100.0) if margin > 0 else 0.0, "USD",
             LEVERAGE, len(self.positions), now, 1, 1, 1, now, BROKER, "BACKTEST", 2,
             "QUANT_NQ", "backtest", "BACKTEST"))
        self.db.commit()
        self.equity_curve.append((now, equity))

    def mt5_tick(self, symbol: str, bid: float, ask: float, now: float) -> dict[str, Any]:
        """عرض ميتاتريدر للبوّابة 552 — مستعارٌ من التِكّة نفسها (الوسيط واحد)."""
        return {"provider": "MT5", "account_id": ACCOUNT_ID, "broker": BROKER, "symbol": symbol,
                "bid": bid, "ask": ask, "price": (bid + ask) / 2.0, "volume": 0.0,
                "broker_timestamp": now + SERVER_OFFSET_S, "broker_timestamp_raw": now + SERVER_OFFSET_S,
                "broker_clock_offset_s": SERVER_OFFSET_S, "clock_offset_s": SERVER_OFFSET_S,
                "exchange_timestamp": now, "received_at": now, "timestamp": now,
                "timestamp_source": "broker", "clock_domain": "utc", "clock_valid": True}


# ─────────────────────────────────────────────────────────── وضع المختبر ──
# ٢٠٢٦-١٠-٠٦ (ختم المالك «… المختبر … nq»): صفحة المختبر تركت ملفّات شموع الكريبتو القديمة إلى هذا
# المحرّك؛ وسؤالها «ليش هذا المحلّل/القسم عم يفشل» يُجاب من آخر حمولةٍ لكلّ حدثٍ وتوزيع حالاته.

LAB_SKIP = ("SYS_", "feed.", "market.tick", "market.broker_tick", "market_data.price_received",
            "market_data.depth", "kernel.", "time.", "storage.", "core.")
LAB_FIELDS = ("state", "status", "analysis_state", "ready", "signal", "direction", "strength", "confidence",
              "current_depth", "required_depth", "readiness_pct", "missing_reason", "not_ready_reason",
              "blocking_units", "reason", "warnings", "symbol", "timeframe", "atom_id", "id")


def lab_record(lab: dict[str, dict[str, Any]], name: str, payload: dict[str, Any]) -> None:
    row = lab.setdefault(name, {"count": 0, "states": Counter(), "last": {}, "reason": ""})
    row["count"] += 1
    unified = payload.get("unified") if isinstance(payload.get("unified"), dict) else {}
    state = str(unified.get("state") or payload.get("state") or payload.get("analysis_state")
                or payload.get("status") or "—")
    row["states"][state] += 1
    last = {k: payload.get(k) for k in LAB_FIELDS if k in payload}
    if unified:
        last["unified"] = {k: unified.get(k) for k in ("state", "direction", "strength", "weight",
                                                        "weight_effect", "current_depth", "required_depth",
                                                        "not_ready_reason", "unknown_fields") if k in unified}
    row["last"] = last
    reason = (payload.get("missing_reason") or payload.get("not_ready_reason") or unified.get("not_ready_reason")
              or payload.get("reason") or "")
    if not reason and isinstance(payload.get("warnings"), list) and payload["warnings"]:
        reason = str(payload["warnings"][0])
    if reason:
        row["reason"] = str(reason)[:200]


def lab_report(lab: dict[str, dict[str, Any]]) -> dict[str, Any]:
    out = {}
    for name, row in sorted(lab.items()):
        states = dict(row["states"].most_common())
        healthy = sum(v for k, v in states.items() if str(k).upper() in ("READY", "OK", "TRUE"))
        out[name] = {"count": row["count"], "states": states, "healthy_pct": round(healthy / row["count"] * 100, 1),
                     "reason": row["reason"], "last": row["last"]}
    return out


# ─────────────────────────────────────────────────────────── الناقل ──

class AsyncReplayBus:
    """ناقلٌ غير متزامن على حلقةٍ واحدة — النشر المتداخل `await` لا حلقةٌ جديدة.

    مقيس ٢٠٢٦-١٠-٠٥ بالملمح على 150 تِكّة: `SyncEventBus` يفتح لكلّ نشرٍ من داخل معالِج خيطًا
    وحلقةً جديدة (`asyncio.run` في `ThreadPoolExecutor`)، وكلّ حلقةٍ على ويندوز زوجُ مقابس:
    250 ثانية من 265 في `connect/bind`. هنا العمق أوّلًا كما في ناقل النواة، وكلّ مستمعٍ يأخذ
    نسخته من الحمولة.
    """

    def __init__(self) -> None:
        self._handlers: dict[str, list] = defaultdict(list)
        self._all: list = []
        self._errors: list[dict[str, str]] = []
        self.dispatches = 0
        # ٢٠٢٦-١٠-٠٦ — إعادة آخر حالةٍ للمشترك المتأخّر، كناقل النواة حرفًا (`core/event_bus.py`
        # `_last_event` + `subscribe`، والتصنيف `_is_replayable` نفسه مستوردًا). كان غيابها يُسقط ما يُنشر
        # عند الإقلاع قبل اشتراك مستهلكه: قائمة 468 تُنشر في `start` قبل أن يشترك 552 (مقيس على
        # `warm-btc4`: 3 أوامر مبنيّة ماتت `SYMBOL_NOT_ALLOWED` والقائمة تقول BTCUSD).
        from core.event_bus import _is_replayable
        self._replayable = _is_replayable
        self._last: dict[str, Any] = {}
        self._late: list[tuple[str, Any, Any]] = []
        self._queue: deque = deque()
        self._draining = False

    def subscribe(self, name: str, handler) -> None:
        self._handlers[name].append(handler)
        if name in self._last:
            self._late.append((name, handler, self._last[name]))

    async def flush_late(self) -> int:
        """تسليم ما فات المشتركين المتأخّرين — يُنادى بعد التحميل وقبل كلّ نشر."""
        count = 0
        while self._late:
            name, handler, payload = self._late.pop(0)
            await self._call(name, handler, dict(payload) if isinstance(payload, dict) else payload)
            count += 1
        return count

    def subscribe_all(self, handler) -> None:
        self._all.append(handler)

    async def _call(self, name: str, handler, *args) -> None:
        try:
            result = handler(*args)
            if asyncio.iscoroutine(result) or isinstance(result, asyncio.Future):
                await result
            self.dispatches += 1
        except Exception as exc:  # noqa: BLE001 — يُعدّ ويُسمّى، كناقل النواة
            self._errors.append({"event": name, "handler": getattr(handler, "__qualname__", str(handler)),
                                 "error": "%s: %s" % (type(exc).__name__, exc)})

    async def publish(self, name: str, payload: Any) -> None:
        """بترتيب الوصول لا بالعمق أوّلًا — ٢٠٢٦-١٠-٠٦.

        ناقل النواة صناديقُ لكلّ مشترك تُفرَّغ بترتيب الإيداع؛ والعمق أوّلًا هنا كان يُكمل سلسلةً
        كاملة قبل أن يصل الحدث نفسه لمشتركه التالي: `execution.order.resolved` ⟵ 516 ⟵ 551 ⟵ 552
        تمّت كلّها قبل أن يراه 526، فمات كلّ أمرٍ `MARGIN_VERDICT_MISSING` (مقيس على `warm-btc5`: 9 من
        9). الآن يُودَع الحدث في طابورٍ واحد ويُسلَّم لكلّ مشتركيه قبل ما نشروه هم. والنشر الأعلى
        (لا المتداخل) يفرّغ الطابور كلّه قبل أن يعود — فما بعد `await publish` يرى أثره كاملًا كما كان.
        """
        if self._late:
            await self.flush_late()
        if self._replayable(name):
            self._last[name] = dict(payload) if isinstance(payload, dict) else payload
        self._queue.append((name, payload))
        if self._draining:
            return
        self._draining = True
        try:
            while self._queue:
                event, body = self._queue.popleft()
                for handler in list(self._handlers.get(event, ())):
                    await self._call(event, handler, dict(body) if isinstance(body, dict) else body)
                for handler in self._all:
                    await self._call(event, handler, event, body)
        finally:
            self._draining = False

    def report(self) -> dict[str, Any]:
        return {"total_dispatches": self.dispatches, "total_errors": len(self._errors)}


def _context(atom_id: int, config: dict[str, Any], bus: AsyncReplayBus) -> Any:
    from backtest.sync_event_bus import create_logger
    from core.contracts.atom import AtomContext
    return AtomContext(atom_id=atom_id, config=config, logger=create_logger(),
                       publish=bus.publish, subscribe=bus.subscribe, subscribe_all=bus.subscribe_all)


# ─────────────────────────────────────────────────────────── التشغيل ──

class FullReplay:
    def __init__(self, run_dir: Path, *, balance: float,
                 atom_config: dict[int, dict[str, Any]] | None = None) -> None:
        self.run_dir = run_dir
        self.time = ReplayTime()
        self.broker = PaperBroker(run_dir / "bridge" / "nq_brain.db", balance)
        self.atom_config = atom_config or {}
        self.atoms: dict[int, Any] = {}
        self.blocked: dict[int, str] = {}
        self.failed: dict[int, str] = {}
        self.section_state: dict[tuple[str, str], str] = {}
        self.participation = Counter()
        self.evaluations = 0
        self.entry_participation: list[dict[str, Any]] = []
        self.event_counts = Counter()
        self.pulse_bucket: dict[str, int] = {}
        self.chain_health: dict[int, str] = {}
        self.lab: dict[str, dict[str, Any]] | None = None     # وضع المختبر: آخر حالةٍ وسببها لكلّ حدث
        # تسخين المحلّلين: شموعٌ مغلقة قبل البداية من مخزن سي‑تريدر (`shared/ladder_seed.history_candles`)
        self.warm: list[tuple[float, int, dict[str, Any]]] = []
        self.warmed = 0
        self.late_delivered = 0
        self.request_origin: dict[str, dict[str, Any]] = {}
        self.order_rejections: Counter = Counter()
        self.order_rejection_samples: list[dict[str, Any]] = []
        self.bus = AsyncReplayBus()
        self.loop = asyncio.new_event_loop()

    def load(self) -> None:
        """كلّ ذرّةٍ تُهيَّأ وتُبدأ على حلقةٍ تُغلق بعدها: مهامّها الخلفيّة (استطلاع الجسر كلّ
        ١٠م.ث، نبضات 601) لا تعمل على ساعة الجدار — الإيقاع كلّه من زمن البيانات (`_pump_bridge`)."""
        from backtest.runner import _entrypoint_class, _load_atom_class, discover_atoms
        from shared.runtime_paths import manifest_config_rebase
        wanted = []
        for info in discover_atoms(ROOT / "atoms"):
            aid = info["id"]
            in_range = any(lo <= aid <= hi for lo, hi in ATOM_RANGES)
            if (in_range or aid in BRIDGE_ATOMS or aid in EXTRA_ATOMS) and aid not in DENY:
                wanted.append(info)
        bridge = str(self.run_dir / "bridge" / "nq_brain.db")
        for info in wanted:
            aid = info["id"]
            config = manifest_config_rebase(dict(info["manifest"].get("config") or {}), code_root=ROOT)
            if aid in BRIDGE_ATOMS or "db_path" in config and _live_path(config.get("db_path"), self.run_dir) \
                    and "nq_brain" in str(config.get("db_path")):
                config["db_path"] = bridge
            if aid == 601:
                config["cursor_db"] = str(self.run_dir / "var" / "store" / "bridge_cursor.db")
            config.update(self.atom_config.get(aid, {}))
            live = [v for v in _walk_values(config) if _live_path(v, self.run_dir)]
            if live:
                self.blocked[aid] = str(live[0])
                continue
            cls = _load_atom_class(info["dir"], "fr_atom_%d" % aid, _entrypoint_class(info["manifest"]))
            if cls is None:
                self.failed[aid] = "LOAD"
                continue
            boot = asyncio.new_event_loop()
            try:
                atom = cls()
                boot.run_until_complete(atom.initialize(_context(aid, config, self.bus)))
                boot.run_until_complete(atom.start())
                self.atoms[aid] = atom
            except Exception as exc:  # noqa: BLE001 — يُسمّى في التقرير ولا يُبتلع
                self.failed[aid] = "%s: %s" % (type(exc).__name__, str(exc)[:160])
            finally:
                for task in asyncio.all_tasks(boot):
                    task.cancel()
                boot.close()
        self._watch()

    def _watch(self) -> None:
        lab = self.lab

        def on_any(name: str, payload: Any) -> None:
            self.event_counts[name] += 1
            if lab is not None and isinstance(payload, dict) and not name.startswith(LAB_SKIP):
                lab_record(lab, name, payload)
        self.bus.subscribe_all(on_any)
        for family in SECTION_FAMILIES:
            def on_card(payload: Any, _family=family) -> None:
                if isinstance(payload, dict):
                    unified = payload.get("unified") or {}
                    self.section_state[(_family, str(payload.get("symbol") or "").upper())] = str(
                        unified.get("state") or payload.get("state") or "")
            self.bus.subscribe("%s.section.live" % family, on_card)

        def on_evaluated(payload: Any) -> None:
            if not isinstance(payload, dict):
                return
            rows = payload.get("evidence") or payload.get("rows") or []
            weighed = {str(r.get("source", "")).split(":")[0].split("-")[0]
                       for r in rows if isinstance(r, dict) and (r.get("weight_effect") or 0) > 0}
            self.evaluations += 1
            for fam in weighed:
                self.participation[fam] += 1
        self.bus.subscribe("decision.evaluated.state", on_evaluated)

        def on_entry(payload: Any) -> None:
            if not isinstance(payload, dict):
                return
            symbol = str(payload.get("symbol") or "").upper()
            setup = str(payload.get("setup_id") or "")
            if payload.get("request_id"):
                self.request_origin[str(payload["request_id"])] = {
                    "strategy": setup.split(":", 1)[0] if setup else "", "setup_id": setup,
                    "stop": payload.get("stop_loss"), "target": payload.get("take_profit")}
            self.entry_participation.append({
                "time": self.time.now, "symbol": symbol, "side": payload.get("side"),
                "sections": {fam: self.section_state.get((fam, symbol), "") for fam in SECTION_FAMILIES}})
        self.bus.subscribe("execution.order.requested", on_entry)

        # ٢٠٢٦-١٠-٠٦: أمرٌ طُلب ثمّ رُفض داخل النظام (قبل الإكسبرت) — مَن رفضه وبأيّ سبب، لا عددٌ وحده.
        def on_rejected(payload: Any) -> None:
            if not isinstance(payload, dict):
                return
            who = (payload.get("rejected_by") or payload.get("source_atom") or payload.get("atom_id")
                   or payload.get("source") or payload.get("gate") or "?")
            why = (payload.get("reason") or payload.get("rejection_reason") or payload.get("code")
                   or payload.get("error") or "?")
            self.order_rejections["%s · %s" % (str(who)[:40], str(why)[:120])] += 1
            if len(self.order_rejection_samples) < 3:
                self.order_rejection_samples.append({k: (v if isinstance(v, (int, float, bool)) or v is None
                                                         else str(v)[:160]) for k, v in payload.items()})
        self.bus.subscribe("execution.order.rejected", on_rejected)

    async def _pulses(self, now: float) -> bool:
        fired = False
        for name, seconds in PULSES:
            bucket = int(now // seconds)
            if self.pulse_bucket.get(name) == bucket:
                continue
            self.pulse_bucket[name] = bucket
            await self.bus.publish(name, {
                "count": bucket, "official_time": now, "monotonic_time": time.monotonic(),
                "time_source": "NTP", "clock_quality": "SYNCED", "sync_age_s": 0.0, "offset_s": 0.0,
                "bucket_start": float(bucket * seconds), "pulse_id": "%s|%d" % (name, bucket * seconds),
                "missed_intervals": 0})
            fired = fired or name == "SYS_SECOND"
        return fired

    async def _settle(self) -> None:
        """مهامٌّ أطلقتها المعالِجات (كتابة 601 في الجسر عبر خيط) تكتمل قبل أن يقرأ الإكسبرت."""
        current = asyncio.current_task()
        # ٢٠٢٦-١٠-٠٩ (قيادة المالك «NQ»): مهلة 414 لحقائق الحدّ (`_expire_later`، 30 ث بالساعة الحقيقيّة) ليست عملًا
        # يُنتظر — حيًّا تجري التِّكّات أثناءها فتصل الحقائق وتُطلقها. انتظارُها هنا (حتّى 2 ث في كلّ ثانية بيانات)
        # كان يجمّد الإعادة عند أوّل شمعة زنادٍ محجوزة (مقيس: 2026-09-22 13:58 غرينتش، صفر معالج دقائق).
        pending = [t for t in asyncio.all_tasks() if t is not current and not t.done()
                   and getattr(t.get_coro(), "__qualname__", "") != "Atom._expire_later"]
        if pending:
            await asyncio.wait(pending, timeout=2.0)

    async def _pump_bridge(self, now: float) -> None:
        await self._settle()
        self.broker.process_commands(now)
        self.broker.snapshot(now)
        # `_read_once` نفسه الذي تناديه حلقاتها الحيّة — هنا بإيقاع زمن البيانات (619 `read_now`
        # غلافٌ متزامن لا يعمل داخل حلقةٍ دائرة).
        for aid, method in ((619, "_read_once"), (609, "_read_once"), (611, "_read_once")):
            atom = self.atoms.get(aid)
            fn = getattr(atom, method, None) if atom is not None else None
            if fn is None:
                continue
            try:
                out = fn()
                if asyncio.iscoroutine(out):
                    await out
            except Exception as exc:  # noqa: BLE001
                self.failed.setdefault(aid, "PUMP %s: %s" % (type(exc).__name__, str(exc)[:120]))
        await self._settle()

    async def _specs(self) -> None:
        atom = self.atoms.get(618)
        if atom is not None and hasattr(atom, "_refresh_specs"):
            await atom._refresh_specs()

    async def _warm_up(self, first_tick: dict[str, Any]) -> None:
        """قبل أوّل تِكّة: شموع الأطر الخمسة المغلقة قبل البداية على `market_data.candle_closed`.

        الحيّ يبدأ ومحلّلوه ممتلئون (لقطاتهم وشهورٌ من الشموع)، والإعادة كانت تبدأ فارغة: بطاقة 166
        البطيئة بلا فريم ساعةٍ حيّ، فيُرفض كلّ إعدادٍ بنيويّ «إذن الساعة مجهول» (مقيس: 405/406/410 كلّها
        `STRUCTURE_GATE_UNKNOWN` على صفقة البتكوين الرابحة). الساعة تمشي مع كلّ شمعة إلى لحظة إغلاقها،
        وأوامرُ تولد هنا (إن وُلدت) تسقط عند أوّل ضخٍّ للجسر بلا سعر (`NO_QUOTE`) — لا تُنفَّذ.
        """
        ident, _ = feed_events(first_tick)
        for closed_at, _seconds, candle in self.warm:
            self.time.now = closed_at
            await self.bus.publish("market_data.candle_closed", {
                **candle, "account_id": ident["account_id"], "broker": ident["broker"]})
            self.warmed += 1
        await self._settle()

    async def _run(self, ticks, max_ticks: int, progress_every: int) -> int:
        count = 0
        started = time.perf_counter()
        self.late_delivered = await self.bus.flush_late()
        for tick in ticks:
            # الساعة لا ترجع: الدمج يُخرج أحدث تِكّة الشريحة متأخّرةً بأقلّ من عرضها عن تِكّات رموزٍ أخرى.
            now = max(float(tick["timestamp"]), self.time.now if count else 0.0)
            if count == 0 and self.warm:
                await self._warm_up(tick)
            self.time.now = now
            if count == 0:
                await self._pulses(now)
                await self._pump_bridge(now)
                await self._specs()
            # الباب الحيّ: الخام لكاشف الانقطاع (116)، وتِكّة 623 لموزّع التغذية (613) ⟵ المصدّق (112)
            # ⟵ `market.tick.validated`؛ وجودة السوق (115) من `market.tick` نفسه.
            raw, ctick = feed_events(tick)
            await self.bus.publish("feed.ctrader.raw", raw)
            await self.bus.publish("feed.ctrader.tick", ctick)
            await self.bus.publish("feed.mt5.tick", self.broker.mt5_tick(
                tick["symbol"], tick["bid"], tick["ask"], now))
            self.broker.on_tick(tick["symbol"], tick["bid"], tick["ask"], now)
            if await self._pulses(now):
                await self._pump_bridge(now)
            count += 1
            if progress_every and count % progress_every == 0:
                rate = count / max(1e-9, time.perf_counter() - started)
                print("   … %d تِكّة · %s · %.0f تِكّة/ث · صفقات مغلقة %d · مفتوحة %d · رصيد %.2f" % (
                    count, _utc(now), rate, len(self.broker.closed), len(self.broker.positions),
                    self.broker.balance), flush=True)
            if max_ticks and count >= max_ticks:
                break
        await self._settle()
        self.broker.close_all(self.time.now, "END_OF_RUN")
        # صحّة سلسلة القرار عند النهاية — أين تتوقّف الصفقة إن لم تصدر (حجبٌ وأسبابه بلسان كلّ ذرّة).
        for aid in DECISION_CHAIN:
            atom = self.atoms.get(aid)
            if atom is None or not hasattr(atom, "health_check"):
                continue
            try:
                health = await atom.health_check()
                self.chain_health[aid] = str(getattr(health, "message", health))[:400]
            except Exception as exc:  # noqa: BLE001
                self.chain_health[aid] = "%s: %s" % (type(exc).__name__, exc)
        return count

    def run(self, ticks, *, max_ticks: int = 0, progress_every: int = 2000) -> int:
        """الساعة مُركَّبة قبل التحميل (`main`): ذرّةٌ تختم بدايتها بساعة الجدار ثمّ تقارن بزمن
        البيانات تحسب أعمارًا سالبة."""
        asyncio.set_event_loop(self.loop)
        return self.loop.run_until_complete(self._run(ticks, max_ticks, progress_every))


# ─────────────────────────────────────────────────────────── البيانات ──

def feed_events(tick: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """من التِّكّة المسجّلة إلى ما تنشره 622 (الخام) و623 (تِكّة سي‑تريدر) بحقولهما — بلا قيمة مخترعة.

    الحقول التي لا تحملها التِّكّة المسجّلة (فجوات التسلسل والدفتر) تُعلَن بقيمها الصادقة في الإعادة:
    لا فجوة ولا دفتر فارغ، لأنّ التِّكّة المسجّلة نفسها اجتازت 112 حيًّا.
    """
    stamp = float(tick["timestamp"])
    common = {"provider": "CTRADER", "account_id": tick.get("account_id") or ACCOUNT_ID,
              "broker": tick.get("broker") or BROKER, "build": "backtest", "symbol": tick["symbol"],
              "timestamp": stamp, "received_at": float(tick.get("received_at") or stamp),
              "sequence": tick.get("sequence") or tick.get("tick_id"), "sequence_gap": False,
              "out_of_order": False, "fabric_gap": False}
    ctick = {**common, "bid": tick["bid"], "ask": tick["ask"],
             "price": (tick["bid"] + tick["ask"]) / 2.0,
             "exchange_timestamp": float(tick.get("exchange_timestamp") or stamp),
             "tick_id": tick.get("tick_id"), "top_changed": True, "book_empty": False}
    return common, ctick

def recorded_ticks(start: float, end: float, symbols: tuple[str, ...]):
    """تِكّات سي‑تريدر المسجّلة (ناتج 112 كما خزّنه 701) — قراءة فقط، بترتيبها الزمنيّ عبر الرموز."""
    db = sqlite3.connect("file:%s?mode=ro" % LIVE_TICKS_DB, uri=True)
    marks = ",".join("?" * len(symbols))
    cursor = db.execute(
        "SELECT id, payload_json FROM market_data WHERE occurred_at >= ? AND occurred_at < ? "
        "AND symbol IN (%s) AND provider='CTRADER' ORDER BY occurred_at, id" % marks,
        (start, end, *symbols))
    while True:
        rows = cursor.fetchmany(5000)
        if not rows:
            break
        for row_id, raw in rows:
            try:
                tick = json.loads(raw)
            except (TypeError, ValueError):
                continue
            bid, ask = tick.get("bid"), tick.get("ask")
            if not isinstance(bid, (int, float)) or not isinstance(ask, (int, float)) or ask <= bid:
                continue
            tick["tick_id"] = tick["sequence"] = "replay-%d" % row_id
            tick["source_row_id"] = row_id
            yield tick
    db.close()


CTRADER_HISTORY_DB = LIVE_RUNTIME / "var" / "history" / "ctrader_history.db"


def write_ladder_seed(run_dir: Path, symbols: tuple[str, ...], start: float,
                      bars: dict[str, int] | None = None) -> dict[str, dict[str, int]]:
    """بذرة سلّم المستويات (201) من شموع سي‑تريدر المجلوبة — مغلقةٌ قبل `start` وحدها (لا نظرة للمستقبل).

    الحيّ يبذر سلّمه من ملفّ `structure_ladder_seed.json` في جذر التشغيل؛ والإعادة بلا بذرة لا تجد
    وقفًا ولا هدفًا بنيويًّا فلا تفتح صفقة. ٢٠٢٦-١٠-٠٦: البناء من `shared/ladder_seed` — المنطق
    نفسه الذي يبذر الحيَّ (`tools/بناء_بذرة_السلم.py`)، فلا يختلف سلّم الاختبار عن سلّم الحيّ.
    """
    from shared.ladder_seed import build_seed, write_seed
    seed, counts = build_seed(CTRADER_HISTORY_DB, symbols, start, bars=bars,
                              label="اختبار تاريخيّ قبل %s" % _utc(start))
    write_seed(run_dir / "var" / "telemetry" / "structure_ladder_seed.json", seed)
    return counts


def ctrader_ticks(start: float, end: float, symbols: tuple[str, ...]):
    """تِكّات سي‑تريدر التاريخيّة (أداة الجلب: عرضٌ وطلب منفصلان) — تُدمج في أسعارٍ بترتيب الزمن.

    كلّ تغيّرٍ في العرض أو الطلب سعرٌ جديد بآخر الطرف الآخر، كما تصل التغذية الحيّة (622 ⟵ 623).
    ولا يُنشر سعرٌ قبل أن يُعرف الطرفان. والرموز تتداخل بزمنها الحقيقيّ (`heapq.merge`).
    """
    import heapq
    db = sqlite3.connect("file:%s?mode=ro" % CTRADER_HISTORY_DB, uri=True)

    def stream(symbol: str):
        cursor = db.execute("SELECT ts_ms, side, price FROM ticks_history WHERE symbol=? AND ts_ms>=? "
                            "AND ts_ms<? ORDER BY ts_ms, side", (symbol, int(start * 1000), int(end * 1000)))
        bid = ask = None
        seq = 0
        while True:
            rows = cursor.fetchmany(5000)
            if not rows:
                break
            for ts_ms, side, price in rows:
                if side == 1:
                    bid = price
                else:
                    ask = price
                if bid is None or ask is None or ask <= bid:
                    continue
                seq += 1
                stamp = ts_ms / 1000.0
                yield (stamp, symbol, seq, {
                    "account_id": ACCOUNT_ID, "broker": BROKER, "provider": "CTRADER", "symbol": symbol,
                    "bid": bid, "ask": ask, "price": (bid + ask) / 2.0, "timestamp": stamp,
                    "exchange_timestamp": stamp, "received_at": stamp,
                    "tick_id": "hist-%s-%d" % (symbol, seq), "sequence": "hist-%s-%d" % (symbol, seq)})

    for _stamp, _symbol, _seq, tick in heapq.merge(*(stream(s) for s in symbols)):
        yield tick
    db.close()


# ─────────────────────────────────────────────────────────── التقرير ──

def _utc(ts: float | None) -> str:
    return "—" if ts is None else datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def summarize(replay: FullReplay, ticks: int, wall_s: float, args: argparse.Namespace) -> dict[str, Any]:
    broker = replay.broker
    trades = [c for c in broker.closed]
    net = sum(c["profit"] + c["commission"] + c["entry_commission"] for c in trades)
    wins = [c for c in trades if c["kind"] == "CLOSED" and c["profit"] > 0]
    closed_full = [c for c in trades if c["kind"] == "CLOSED"]
    gross_win = sum(c["profit"] for c in trades if c["profit"] > 0)
    gross_loss = -sum(c["profit"] for c in trades if c["profit"] < 0)
    peak, max_dd = broker.start_balance, 0.0
    for _ts, equity in broker.equity_curve:
        peak = max(peak, equity)
        max_dd = max(max_dd, peak - equity)
    per_symbol = defaultdict(lambda: {"صفقات": 0, "صافي": 0.0})
    for c in trades:
        row = per_symbol[c["symbol"]]
        row["صفقات"] += 1 if c["kind"] == "CLOSED" else 0
        row["صافي"] = round(row["صافي"] + c["profit"] + c["commission"] + c["entry_commission"], 2)
    per_strategy = defaultdict(lambda: {"صفقات": 0, "رابحة": 0, "صافي": 0.0})
    for c in trades:
        name = replay.request_origin.get(str(c.get("request_id") or ""), {}).get("strategy") or "?"
        row = per_strategy["%s %s" % (name, c["symbol"])]
        row["صفقات"] += 1 if c["kind"] == "CLOSED" else 0
        row["رابحة"] += 1 if c["kind"] == "CLOSED" and c["profit"] > 0 else 0
        row["صافي"] = round(row["صافي"] + c["profit"] + c["commission"] + c["entry_commission"], 2)
    entries = replay.entry_participation
    all_ready = sum(1 for e in entries if all(v == "READY" for v in e["sections"].values()))
    return {
        "الفترة": [_utc(args.start), _utc(args.end)], "الرموز": list(args.symbols),
        "تِكّات": ticks, "زمن_التشغيل_ث": round(wall_s, 1),
        "ذرّات_محمّلة": len(replay.atoms), "ذرّات_محجوبة_لمسار_حيّ": replay.blocked,
        "ذرّات_فشلت": replay.failed,
        "شموع_التسخين": replay.warmed,
        "حالات_أُعيدت_لمتأخّرين_عند_البدء": replay.late_delivered,
        "رفض_الأوامر_داخل_النظام": dict(replay.order_rejections.most_common(20)),
        "عيّنات_رفض_الأوامر": replay.order_rejection_samples,
        "الرصيد": {"بداية": broker.start_balance, "نهاية": round(broker.balance, 2),
                   "صافي": round(net, 2), "أقصى_سحب": round(max_dd, 2)},
        "صفقات_مغلقة": len(closed_full), "إغلاقات_جزئيّة": len(trades) - len(closed_full),
        "نسبة_الربح": round(len(wins) / len(closed_full) * 100.0, 1) if closed_full else None,
        "معامل_الربح": round(gross_win / gross_loss, 3) if gross_loss > 0 else None,
        "مفتوحة_في_النهاية": len(broker.positions), "أوامر_مرفوضة_عند_الإكسبرت": dict(broker.rejected),
        "لكلّ_رمز": dict(per_symbol), "لكلّ_استراتيجيّة": dict(per_strategy),
        "مشاركة_الأقسام_في_التقييم": {
            "تقييمات": replay.evaluations,
            **{fam: replay.participation.get(fam, 0) for fam in ("150", "200", "250", "300", "350", "400")}},
        "أوامر_دخول": len(entries), "أوامر_دخول_كلّ_الأقسام_جاهزة": all_ready,
        "أخطاء_الناقل": replay.bus.report().get("total_errors"),
        "أكثر_أخطاء_الناقل": Counter("%s|%s" % (e["handler"].split(".")[0], e["error"][:80])
                                    for e in replay.bus._errors).most_common(12),
        "صحّة_سلسلة_القرار": {str(k): v for k, v in replay.chain_health.items()},
        "أحداث_مفتاحيّة": {k: replay.event_counts.get(k, 0) for k in (
            "market_data.candle_closed", "structure.levels.state", "strategy.setup.proposed",
            "decision.evaluated.state", "decision.gate.passed",
            "execution.order.requested", "trading.final_decision", "execution.order.rejected",
            "platform.trade_event", "market.outcome.realized")},
    }


def write_report(replay: FullReplay, summary: dict[str, Any]) -> None:
    run_dir = replay.run_dir
    (run_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
    with (run_dir / "trades.csv").open("w", newline="", encoding="utf-8-sig") as fh:
        fields = ["ticket", "kind", "symbol", "side", "volume", "entry", "exit", "opened_utc", "closed_utc",
                  "reason", "profit", "commission", "entry_commission", "request_id",
                  "strategy", "setup_id", "stop", "target"]
        writer = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in replay.broker.closed:
            # ٢٠٢٦-١٠-٠٦: الاستراتيجيّة التي فتحت الصفقة (من طلب 555 بمعرّفه) — ليُعرف أيّها يربح.
            origin = replay.request_origin.get(str(row.get("request_id") or ""), {})
            writer.writerow({**row, **origin, "opened_utc": _utc(row["opened_utc"]),
                             "closed_utc": _utc(row["closed_utc"])})
    (run_dir / "entries.json").write_text(json.dumps(replay.entry_participation, ensure_ascii=False, indent=1),
                                          encoding="utf-8")


def coalesce(ticks, window_ms: int):
    """أحدث تِكّةٍ حقيقيّة لكلّ رمز في كلّ شريحةٍ زمنيّة — كما يستبدل محرّك النواة المعلَّقَ بالأحدث.

    لا تِكّة تُخترع: كلّ ما يخرج تِكّةٌ مسجّلة بسعرها وزمنها، وإنّما يُسقط ما سبقها في شريحتها.
    وأثرُ الإسقاط على القرار يُقاس بمقارنة تشغيلٍ كامل بتشغيلٍ مدموج على النافذة نفسها قبل أن يُعتمد.
    """
    pending: dict[str, dict[str, Any]] = {}
    bucket: dict[str, int] = {}
    for tick in ticks:
        symbol = tick["symbol"]
        slot = int(float(tick["timestamp"]) * 1000) // window_ms
        if symbol in pending and bucket[symbol] != slot:
            yield pending[symbol]
        pending[symbol], bucket[symbol] = tick, slot
    yield from sorted(pending.values(), key=lambda t: float(t["timestamp"]))


def run_parallel(args: argparse.Namespace, argv: list[str]) -> int:
    """شرائح زمنيّة متوازية: لكلّ شريحةٍ عمليّةٌ بإحماءٍ قبلها لا تُحسب فيه صفقات، ثمّ تُجمع النتائج.

    الحدّ المعلن: الرصيد لا ينتقل بين الشرائح (كلٌّ يبدأ بالرصيد نفسه) — وتحجيم المالك بمخاطرةٍ ثابتة
    بالدولار (100$) لا يتبع الرصيد، فالأثر محصور في حدود الهامش. والمفتوح عند نهاية الشريحة يُغلق على
    آخر سعر بسبب `END_OF_RUN`.
    """
    import subprocess
    run_id = "%s-%s" % (datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S"), args.name or "parallel")
    parent = Path(args.out) if args.out else RUNS_DIR / run_id
    parent.mkdir(parents=True, exist_ok=True)
    span = (args.end - args.start) / args.workers
    passthrough = []
    skip = {"--from", "--to", "--workers", "--name", "--parent", "--trade-from", "--out"}
    items = list(argv)
    i = 0
    while i < len(items):
        key = items[i].split("=", 1)[0]
        has_inline = "=" in items[i]
        if key in skip:
            i += 1 if has_inline else 2
            continue
        passthrough.append(items[i])
        i += 1
    procs = []
    for k in range(args.workers):
        trade_from = args.start + k * span
        trade_to = args.end if k == args.workers - 1 else trade_from + span
        warm = max(args.start - args.warmup_hours * 3600 if k == 0 else 0.0,
                   trade_from - args.warmup_hours * 3600)
        name = "chunk%02d" % k
        cmd = [sys.executable, "-m", "backtest.full_replay", "--from", repr(warm), "--to", repr(trade_to),
               "--trade-from", repr(trade_from), "--parent", str(parent), "--name", name, *passthrough]
        log = (parent / ("%s.log" % name)).open("w", encoding="utf-8")
        procs.append((name, subprocess.Popen(cmd, cwd=str(ROOT), stdout=log, stderr=subprocess.STDOUT,
                                             env={**os.environ, "PYTHONIOENCODING": "utf-8"}), log))
    print("شرائح متوازية: %d في %s" % (len(procs), parent), flush=True)
    started = time.perf_counter()
    for name, proc, log in procs:
        proc.wait()
        log.close()
        print("   ✓ %s انتهت (%.0fث) رمز الخروج %s" % (name, time.perf_counter() - started, proc.returncode),
              flush=True)
    combined = merge_chunks(parent, [name for name, _p, _l in procs], args, time.perf_counter() - started)
    (parent / "summary.json").write_text(json.dumps(combined, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(combined, ensure_ascii=False, indent=1))
    return 0


def merge_chunks(parent: Path, names: list[str], args: argparse.Namespace, wall_s: float) -> dict[str, Any]:
    rows, ticks, entries, all_ready = [], 0, 0, 0
    participation, evaluations = Counter(), 0
    rejected, failed = Counter(), {}
    for name in names:
        folder = parent / name
        try:
            part = json.loads((folder / "summary.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            failed[name] = "NO_SUMMARY"
            continue
        ticks += part.get("تِكّات", 0)
        entries += part.get("أوامر_دخول", 0)
        all_ready += part.get("أوامر_دخول_كلّ_الأقسام_جاهزة", 0)
        share = part.get("مشاركة_الأقسام_في_التقييم", {})
        evaluations += share.get("تقييمات", 0)
        for fam in ("150", "200", "250", "300", "350", "400"):
            participation[fam] += share.get(fam, 0)
        rejected.update(part.get("أوامر_مرفوضة_عند_الإكسبرت", {}))
        if part.get("ذرّات_فشلت"):
            failed[name] = part["ذرّات_فشلت"]
        with (folder / "trades.csv").open(encoding="utf-8-sig") as fh:
            rows.extend(csv.DictReader(fh))
    with (parent / "trades.csv").open("w", newline="", encoding="utf-8-sig") as fh:
        if rows:
            writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(sorted(rows, key=lambda r: r["closed_utc"]))
    num = lambda r, k: float(r.get(k) or 0.0)  # noqa: E731
    closed = [r for r in rows if r["kind"] == "CLOSED"]
    net = sum(num(r, "profit") + num(r, "commission") + num(r, "entry_commission") for r in rows)
    gross_win = sum(num(r, "profit") for r in rows if num(r, "profit") > 0)
    gross_loss = -sum(num(r, "profit") for r in rows if num(r, "profit") < 0)
    equity, peak, max_dd = 0.0, 0.0, 0.0
    for r in sorted(rows, key=lambda r: r["closed_utc"]):
        equity += num(r, "profit") + num(r, "commission") + num(r, "entry_commission")
        peak = max(peak, equity)
        max_dd = max(max_dd, peak - equity)
    per_symbol: dict[str, dict[str, float]] = defaultdict(lambda: {"صفقات": 0, "صافي": 0.0})
    for r in rows:
        per_symbol[r["symbol"]]["صفقات"] += 1 if r["kind"] == "CLOSED" else 0
        per_symbol[r["symbol"]]["صافي"] = round(per_symbol[r["symbol"]]["صافي"] + num(r, "profit")
                                                + num(r, "commission") + num(r, "entry_commission"), 2)
    per_strategy: dict[str, dict[str, float]] = defaultdict(lambda: {"صفقات": 0, "رابحة": 0, "صافي": 0.0})
    for r in rows:
        row = per_strategy["%s %s" % (r.get("strategy") or "?", r["symbol"])]
        row["صفقات"] += 1 if r["kind"] == "CLOSED" else 0
        row["رابحة"] += 1 if r["kind"] == "CLOSED" and num(r, "profit") > 0 else 0
        row["صافي"] = round(row["صافي"] + num(r, "profit") + num(r, "commission") + num(r, "entry_commission"), 2)
    return {
        "لكلّ_استراتيجيّة": dict(per_strategy),
        "الفترة": [_utc(args.start), _utc(args.end)], "الرموز": list(args.symbols), "شرائح": len(names),
        "تِكّات": ticks, "زمن_التشغيل_ث": round(wall_s, 1), "دمج_م.ث": args.coalesce_ms,
        "صافي": round(net, 2), "أقصى_سحب_على_الإغلاقات": round(max_dd, 2),
        "صفقات_مغلقة": len(closed), "إغلاقات_جزئيّة": len(rows) - len(closed),
        "نسبة_الربح": round(sum(1 for r in closed if num(r, "profit") > 0) / len(closed) * 100, 1) if closed else None,
        "معامل_الربح": round(gross_win / gross_loss, 3) if gross_loss > 0 else None,
        "لكلّ_رمز": dict(per_symbol), "أوامر_مرفوضة_عند_الإكسبرت": dict(rejected),
        "مشاركة_الأقسام_في_التقييم": {"تقييمات": evaluations, **dict(participation)},
        "أوامر_دخول": entries, "أوامر_دخول_كلّ_الأقسام_جاهزة": all_ready, "شرائح_بمشاكل": failed,
    }


def _parse_time(text: str) -> float:
    try:
        return float(text)
    except ValueError:
        return datetime.fromisoformat(text).replace(tzinfo=timezone.utc).timestamp()


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description="الاختبار التاريخيّ الكامل على تِكّات سي‑تريدر الحقيقيّة")
    ap.add_argument("--from", dest="start", required=True, help="بداية (ISO بتوقيت غرينتش أو ثوانٍ)")
    ap.add_argument("--to", dest="end", required=True)
    ap.add_argument("--symbols", default=",".join(SYMBOLS))
    ap.add_argument("--balance", type=float, default=10000.0)
    ap.add_argument("--set", action="append", default=[], help="NAME=VALUE على نسخة العيارات وحدها")
    ap.add_argument("--atom", action="append", default=[], help="ID:key=value على إعداد ذرّة في الذاكرة")
    ap.add_argument("--calib", action="append", default=[],
                    help="SYMBOL:ANALYZER:PATH:field=value على عيارات المحلّلين في النسخة (* للكلّ)")
    ap.add_argument("--source", choices=("recorded", "ctrader"), default="recorded",
                    help="recorded: تِكّات النظام المسجّلة · ctrader: تِكّات سي‑تريدر التاريخيّة المجلوبة")
    ap.add_argument("--max-ticks", type=int, default=0)
    ap.add_argument("--name", default="")
    ap.add_argument("--coalesce-ms", type=int, default=0,
                    help="أحدث تِكّةٍ حقيقيّة لكلّ رمز في كلّ شريحة بهذا العرض (0 = كلّ التِّكّات)")
    ap.add_argument("--workers", type=int, default=1, help="شرائح زمنيّة متوازية، كلٌّ في عمليّة")
    ap.add_argument("--warmup-hours", type=float, default=3.0, help="إحماء التحليل قبل كلّ شريحة (بلا صفقات)")
    ap.add_argument("--no-seed", action="store_true", help="بلا بذرة سلّم المستويات من شموع سي‑تريدر")
    ap.add_argument("--seed-bars", default="",
                    help="عمق البذرة لكلّ فريم، مثل 15m=139,1h=35,4h=10,1d=2 (البذرة الحيّة القديمة) — الافتراض العميقة")
    ap.add_argument("--asset-budget", type=float, default=2000.0,
                    help="ميزانيّة خسارة كلّ أصل في دفتر 518 (الحيّ يضبطها المالك بزرّه؛ افتراض 518 صفر يردّ كلّ أمر)")
    ap.add_argument("--warm-bars", type=int, default=300,
                    help="تسخين المحلّلين: شموع كلّ إطار (5د·15د·ساعة·4س·يوم) قبل البداية من مخزن سي‑تريدر (0 = بلا)")
    ap.add_argument("--lab", action="store_true", help="وضع المختبر: آخر حالةٍ وسببها لكلّ حدث في التقرير")
    ap.add_argument("--lab-overrides", action="store_true", help="عتبات المختبر المحفوظة على إعداد الذرّات")
    ap.add_argument("--trade-from", type=float, default=0.0, help=argparse.SUPPRESS)
    ap.add_argument("--parent", default="", help=argparse.SUPPRESS)
    ap.add_argument("--out", default="", help="مجلّد التشغيل صراحةً (صفحة اللوحة تحدّده لتجده)")
    args = ap.parse_args(argv)
    args.start, args.end = _parse_time(args.start), _parse_time(args.end)
    args.symbols = tuple(s.strip().upper() for s in args.symbols.split(",") if s.strip())
    if args.workers > 1:
        return run_parallel(args, argv or sys.argv[1:])
    overrides = {k: float(v) for k, v in (item.split("=", 1) for item in args.set)}
    atom_config: dict[int, dict[str, Any]] = defaultdict(dict)
    for item in args.atom:
        head, value = item.split("=", 1)
        aid, key = head.split(":", 1)
        try:
            parsed: Any = json.loads(value)
        except ValueError:
            parsed = value
        atom_config[int(aid)][key] = parsed
    # ٢٠٢٦-١٠-٠٦ — ما يضبطه المالك بأزراره في الحيّ، وغيابُه في الإعادة يردّ كلّ أمر (مقيس على `warm-btc3`:
    # 516 `RISK_BUDGET_EXCEEDED` لأنّ ميزانيّة 518 الافتراضيّة صفر): ميزانيّة كلّ أصل، ورموز التشغيل مفعّلة
    # في بوّابة الأصول 468. وما يُمرَّر صراحةً بـ`--atom` يغلب.
    atom_config[518].setdefault("default_risk_budget", args.asset_budget)
    atom_config[468].setdefault("allowed_symbols", list(args.symbols))

    run_id = "%s-%s" % (datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S"), args.name or uuid.uuid4().hex[:6])
    run_dir = (Path(args.parent) / args.name) if args.parent else Path(args.out) if args.out else RUNS_DIR / run_id
    os.environ.update(prepare_run_dir(run_dir, overrides, [parse_calib(c) for c in args.calib]))
    os.chdir(run_dir)                               # أيّ مسارٍ نسبيّ بقي يقع داخل مجلّد التشغيل
    print("مجلّد التشغيل: %s" % run_dir)
    speed = _replay_speedups(run_dir)
    if not str(speed["settings_db"]).lower().startswith(str(run_dir.resolve()).lower()):
        print("⚠️ سجلّ العيارات خارج مجلّد التشغيل: %s" % speed["settings_db"], flush=True)
    if not args.no_seed and CTRADER_HISTORY_DB.exists():
        bars = None
        if args.seed_bars:
            from shared.ladder_seed import SEED_BARS
            bars = {**SEED_BARS, **{k.strip(): int(v) for k, v in
                                    (item.split("=", 1) for item in args.seed_bars.split(",") if "=" in item)}}
        print("بذرة السلّم: %s" % json.dumps(write_ladder_seed(run_dir, args.symbols, args.start, bars),
                                           ensure_ascii=False), flush=True)
    if args.lab_overrides:
        # عتبات صفحة المختبر (`var/lab/overrides`) — تحت ما يُمرَّر صراحةً في الأمر نفسه.
        from backtest.lab_sandbox import overlays_for
        for aid, overlay in overlays_for().items():
            atom_config[int(aid)] = {**overlay, **atom_config.get(int(aid), {})}
    replay = FullReplay(run_dir, balance=args.balance, atom_config=dict(atom_config))
    if args.lab:
        replay.lab = {}
    if args.warm_bars > 0 and CTRADER_HISTORY_DB.exists():
        from shared.ladder_seed import history_candles
        replay.warm = history_candles(CTRADER_HISTORY_DB, args.symbols, args.start, args.warm_bars)
        print("شموع التسخين: %d" % len(replay.warm), flush=True)
    replay.broker.trade_from = args.trade_from or args.start
    # صفّ الحساب في الجسر قبل الإقلاع — كما يكون الإكسبرت حيًّا قبل النواة؛ 601 يتعرّف الحساب منه
    # عند التهيئة («CURRENT_ACCOUNTS_UNAVAILABLE_OR_BLOCKED» حين كُتب بعدها).
    replay.broker.snapshot(args.start)
    replay.time.now = args.start
    replay.time.install()
    try:
        t0 = time.perf_counter()
        replay.load()
        print("ذرّات محمّلة %d · محجوبة لمسارٍ حيّ %d · فشلت %d (%.1fث)" % (
            len(replay.atoms), len(replay.blocked), len(replay.failed), time.perf_counter() - t0), flush=True)
        t1 = time.perf_counter()
        source = (ctrader_ticks if args.source == "ctrader" else recorded_ticks)(
            args.start, args.end, args.symbols)
        if args.coalesce_ms > 0:
            source = coalesce(source, args.coalesce_ms)
        ticks = replay.run(source, max_ticks=args.max_ticks)
        wall = time.perf_counter() - t1
    finally:
        replay.time.restore()
    summary = summarize(replay, ticks, wall, args)
    write_report(replay, summary)
    if replay.lab is not None:
        (run_dir / "lab.json").write_text(json.dumps(lab_report(replay.lab), ensure_ascii=False, indent=1,
                                                     default=str), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
