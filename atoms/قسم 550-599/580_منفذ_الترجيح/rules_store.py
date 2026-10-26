from __future__ import annotations

import json
import sqlite3
from typing import Any

from ruling_math import RESTORE_JOURNAL, ID_ENGINE, _valid_points, EIGHT_FIELDS

# Campaign 450-901 batch B: rules loading and journal management extracted
# verbatim from the original atom -- same behavior, smaller atom.

#: بصمةُ هذا الملفّ، تُعرَض في `health.message` لـ٥٨٠. غرضُها سؤالٌ واحد:
#: هل يُعيد التحميلُ الحارّ استيرادَ **الملفّات الشقيقة** أم `atom.py` وحده؟
#: ٢٠٢٦-٠٩-٢٢ — أصلحتُ استعلامًا هنا، ثمّ أعاد التحميلُ الحارّ ٥٨٠ إلى
#: `1.5.0`، وبقي الزمنُ المقيس ‎4,978‎ م.ث وهو كلفةُ المسار **القديم**
#: (‎4.03‎ ث للترتيب + ‎0.53‎ للمسح)، بينما المصلَح ‎0.53‎ وحدها. فإن ظهرت
#: هذه البصمة بعد إعادة تحميلٍ لا يُغيّر هذا الملفّ، فالشقيق يُحدَّث؛ وإن
#: بقيت القديمة فهو لا يُحدَّث — وذلك يخصّ لوحَ النواة لا ذرّتي.
STORE_REV = "2026-09-23-skip-scan"

def _load_rules(atom) -> None:
    try:
        connection = atom._connect()
        try:
            rows = connection.execute(
                "SELECT field, side, points_json, enabled, version,"
                " updated_at, updated_by FROM tilt_rules"
                " ORDER BY field, side").fetchall()
        finally:
            connection.close()
    except sqlite3.Error as exc:
        atom._db_error = "RULES_LOAD_FAILED:%s" % exc
        return
    for row in rows:
        try:
            decoded = json.loads(str(row["points_json"]))
        except ValueError:
            decoded = None
        points = _valid_points(decoded) if isinstance(decoded, list) else None
        if points is None:
            # Corrupt points come back as None -- never an invented curve
            # (same law as the governance read endpoint).
            atom._corrupt_rules += 1
        atom._rules[(str(row["field"]), str(row["side"]))] = {
            "field": str(row["field"]), "side": str(row["side"]),
            "points": points, "enabled": bool(row["enabled"]),
            "version": int(row["version"]),
            "updated_at": float(row["updated_at"]),
            "updated_by": str(row["updated_by"])}
    atom._restored_rules = len(rows)

def _load_journal_tail(atom) -> None:
    """S39: the last recorded tilt per symbol, rebuilt from the journal.
    Only what the journal really holds is restored -- fields absent from
    it stay absent, declared through restore_source."""
    try:
        connection = atom._connect()
        try:
            # 🔴 ٢٠٢٦-٠٩-٢٣ — وهذا ما بقي بعد إصلاح الترتيب، فصار هو الكلفة
            # كلَّها. `DISTINCT symbol` تُجيب الخطّة
            # `SCAN ... USING COVERING INDEX` — مسحُ ‎6,122,272‎ مدخلًا في
            # الفهرس كلِّه لاستخراج **خمسة** أسماء، لأنّ SQLite لا يقفز في
            # الفهرس من تلقاء نفسه.
            #
            # المقيس على قرصٍ بارد (وهو حالُ الإقلاع):
            #   DISTINCT المجرّد   12.411 ث   ← وهو بعينه ‎11,042‎ م.ث الحيّة
            #   القفز على الفهرس    0.003 ث
            # ودافئًا ‎0.555‎ ث مقابل ‎0.000‎ — فالفرقُ ليس ذاكرةً بل خطّة.
            #
            # والقفزُ أدناه يجعل كلَّ خطوةٍ **بحثًا** لا مسحًا
            # (`SEARCH ... (symbol>?)`): عددُ الخطوات = عدد الرموز + ١.
            # والنتيجة **متطابقة** تمامًا — لا عيّنة ولا سقف ولا تقدير،
            # فلا يسقط رمزٌ صامتٌ منذ أسابيع (EURUSD آخرُ كتابةٍ له ٠٩-٠٩).
            symbols = [str(row[0]) for row in connection.execute(
                "WITH RECURSIVE s(x) AS ("
                " SELECT MIN(symbol) FROM tilt_state_journal"
                " UNION ALL"
                " SELECT (SELECT MIN(symbol) FROM tilt_state_journal"
                "         WHERE symbol > s.x) FROM s WHERE s.x IS NOT NULL)"
                " SELECT x FROM s WHERE x IS NOT NULL")]
            for symbol in symbols:
                # 🔴 ٢٠٢٦-٠٩-٢٢ — هنا كانت ثلاثون ثانيةً من إقلاع النواة.
                #
                # كان `ORDER BY rowid DESC` وهو **لا يستعمل الفهرس القائم**
                # `ix_tilt_journal_symbol(symbol, changed_at)`؛ فتُجيب الخطّة
                # `USE TEMP B-TREE FOR ORDER BY` — أي تُسحب كلُّ صفوف الرمز من
                # جدولٍ فيه ‎6,058,648‎ صفًّا (‎657‎ م.ب) إلى شجرةٍ مؤقّتة
                # لتُرتَّب، ثمّ يُؤخذ صفٌّ واحد.
                #
                # المقيس على القرص نفسه (عمليّة ساكنة، ذاكرةٌ دافئة):
                #   القائم   `rowid DESC`       = 4.290 ث للرموز الخمسة
                #   المقترَح `changed_at DESC`  = 0.000 ث — بحثٌ في الفهرس
                # وباردًا في الإقلاع بلغ نصيبُ ٥٨٠ ‎19.96‎ ثمّ ‎28.57‎ ثمّ ‎30.97‎
                # ث في ستّ إقلاعاتٍ متتالية — ينمو مع نموّ الجدول.
                #
                # والنتيجة **واحدة**: `changed_at` يلي `symbol` في مفتاح
                # الفهرس، و`rowid` ذيلُه الضمنيّ، فالمسحُ تنازليًّا يعطي أحدثَ
                # `changed_at` ثمّ أكبرَ `rowid` عند التساوي — وهو بعينه ما
                # كان `rowid DESC` يعطيه. تحقّقتُ صفًّا صفًّا على الرموز
                # الخمسة (BTCUSD · EURUSD · US30 · USTEC · XAUUSD): متطابق.
                head = connection.execute(
                    "SELECT rowid, decision_id, changed_at, total"
                    " FROM tilt_state_journal WHERE symbol=?"
                    " ORDER BY changed_at DESC, rowid DESC LIMIT 1",
                    (symbol,)).fetchone()
                if head is None:
                    continue
                rows = connection.execute(
                    "SELECT field, value, tilt FROM tilt_state_journal"
                    " WHERE symbol=? AND decision_id=? AND changed_at=?"
                    " ORDER BY rowid", (symbol, head["decision_id"],
                                        head["changed_at"])).fetchall()
                contributions = {
                    str(row["field"]): {"value": row["value"],
                                        "tilt": float(row["tilt"])}
                    for row in rows}
                atom._last_tilt[symbol] = {
                    "id": ID_ENGINE, "symbol": symbol,
                    "decision_id": str(head["decision_id"]),
                    "contributions": contributions,
                    "total_capped": float(head["total"]),
                    "tilt_max_total": atom._tilt_max_total,
                    "source_timestamp": float(head["changed_at"]),
                    "restored": True, "restore_source": RESTORE_JOURNAL}
        finally:
            connection.close()
    except sqlite3.Error as exc:
        atom._db_error = "JOURNAL_LOAD_FAILED:%s" % exc
        return
    atom._restored_symbols = len(atom._last_tilt)

def _journal(atom, symbol: str, decision_id: str,
             contributions: dict[str, dict[str, Any]], total: float,
             changed_at: float) -> None:
    try:
        connection = atom._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            for field in EIGHT_FIELDS:
                entry = contributions.get(field) or {}
                connection.execute(
                    "INSERT INTO tilt_state_journal"
                    "(symbol, decision_id, field, value, tilt, total,"
                    " changed_at) VALUES(?,?,?,?,?,?,?)",
                    (symbol, decision_id, field, entry.get("value"),
                     float(entry.get("tilt") or 0.0), total, changed_at))
            connection.execute("COMMIT")
        finally:
            connection.close()
    except sqlite3.Error as exc:
        atom._db_error = "JOURNAL_WRITE_FAILED:%s" % exc
        return
    atom._db_error = ""
    atom._journal_writes += 1
