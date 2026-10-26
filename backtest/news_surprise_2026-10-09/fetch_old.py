# -*- coding: utf-8 -*-
"""جلب تقويم ناسداك للفترة الأقدم (2014-01 ⟶ 2024-10-07) إلى قاعدة قياسٍ منفصلة في هذا المجلّد — للقياس وحده.

لا يُكتب شيءٌ في قاعدة الجسر ولا في المشروع. طلبٌ واحد كلّ 1.1 ث على الأكثر.
الأيّام المطلوبة: أيّام الأحداث الأمريكيّة المستهدفة في تقويم ميتاتريدر (قراءة فقط) — لا كلّ أيّام العمل.
الفخّان (من QUANT_NQ_NEWS/app/nasdaq_calendar.py، منسوخٌ منطقهما هنا):
  (١) الحقل gmt = غرينتش + إزاحة نيويورك لحظة الطلب ⟸ غرينتش = المعروض − إزاحة نيويورك الآن.
  (٢) date=D يُرجع أحداث D−1 ⟸ يوم الحدث E يُطلب بـ E+1.
يُستأنف من حيث توقّف (الأيّام المجلوبة تُتخطّى).
"""
import gzip
import html
import json
import os
import re
import sqlite3
import sys
import time
import urllib.request
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "news_old.db")
CAL = "file:C:/Users/NQ/AppData/Roaming/MetaQuotes/Terminal/Common/Files/nq_calendar_history.db?mode=ro"
NY = ZoneInfo("America/New_York")
CAL_OFFSET_S = 3 * 3600
FIRST, LAST = date(2014, 1, 1), date(2024, 10, 7)       # الجسر يبدأ 2024-10-08
CODES = ("consumer-price-index-mm", "consumer-price-index-ex-food-energy-mm", "nonfarm-payrolls", "unemployment-rate",
         "initial-jobless-claims", "retail-sales-mm", "producer-price-index-mm", "producer-price-index-ex-food-energy-mm",
         "gross-domestic-product-qq", "core-pce-price-index-mm", "ism-manufacturing-pmi", "ism-non-manufacturing-pmi",
         "fed-interest-rate-decision")
URL = "https://api.nasdaq.com/api/calendar/economicevents?date=%s"
HEAD = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
GAP_S = 1.1
HHMM = re.compile(r"^(\d{1,2}):(\d{2})$")


def clean(v):
    if v is None:
        return ""
    return " ".join(html.unescape(str(v)).replace("\xa0", " ").split())


def ny_offset_s(at):
    return int(datetime.fromtimestamp(at, NY).utcoffset().total_seconds())


def event_days():
    cal = sqlite3.connect(CAL, uri=True, timeout=5)
    days = set()
    q = "select time_server from calendar_history where country_code='US' and event_code in (%s)" % ",".join("?" * len(CODES))
    for (ts,) in cal.execute(q, CODES):
        d = datetime.fromtimestamp(ts - CAL_OFFSET_S, NY).date()
        if FIRST <= d <= LAST:
            days.add(d)
    return sorted(days)


def main():
    con = sqlite3.connect(OUT)
    con.execute("create table if not exists fetched (event_date text primary key, request_date text, fetched_at real, "
                "n_all integer, n_us integer, ok integer)")
    con.execute("create table if not exists econ (id text primary key, event_date text, time_et text, scheduled_at real, "
                "shown text, event_name text, actual text, consensus text, previous text, fetched_at real)")
    con.commit()
    done = {r[0] for r in con.execute("select event_date from fetched where ok=1")}
    days = [d for d in event_days() if d.isoformat() not in done]
    print("أيّام مطلوبة: %d (مجلوبة سابقًا %d)" % (len(days), len(done)), flush=True)
    last = 0.0
    fails = 0
    t0 = time.time()
    for i, e in enumerate(days):
        wait = last + GAP_S - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        last = time.monotonic()
        req_d = e + timedelta(days=1)
        try:
            req = urllib.request.Request(URL % req_d.isoformat(), headers=HEAD)
            with urllib.request.urlopen(req, timeout=20) as resp:
                raw = resp.read()
            if raw[:2] == b"\x1f\x8b":
                raw = gzip.decompress(raw)
            js = json.loads(raw.decode("utf-8"))
            rows = ((js.get("data") or {}).get("rows")) or []
        except Exception as exc:  # noqa: BLE001
            fails += 1
            print("فشل %s: %s" % (e, str(exc)[:120]), flush=True)
            if fails >= 8:
                print("ثمانية إخفاقات متتالية — توقّف", flush=True)
                break
            time.sleep(5)
            continue
        fails = 0
        fetched_at = time.time()
        shown_off = ny_offset_s(fetched_at)
        us = [r for r in rows if isinstance(r, dict) and clean(r.get("country")) == "United States"]
        seen = {}
        out = []
        for r in us:
            name = clean(r.get("eventName"))
            if not name:
                continue
            shown = clean(r.get("gmt"))
            m = HHMM.match(shown)
            at, day, clock = None, e.isoformat(), shown
            if m and int(m.group(1)) < 24 and int(m.group(2)) < 60:
                wall = datetime(e.year, e.month, e.day, int(m.group(1)), int(m.group(2)), tzinfo=timezone.utc)
                at = wall.timestamp() - shown_off
                loc = datetime.fromtimestamp(at, NY)
                day, clock = loc.date().isoformat(), loc.strftime("%H:%M")
            base = "%s|%s|%s" % (day, clock, name)
            k = seen.get(base, 0) + 1
            seen[base] = k
            key = base if k == 1 else "%s#%d" % (base, k)
            out.append((key, day, clock, at, shown, name, clean(r.get("actual")), clean(r.get("consensus")),
                        clean(r.get("previous")), fetched_at))
        con.execute("begin")
        con.executemany("insert or replace into econ values (?,?,?,?,?,?,?,?,?,?)", out)
        con.execute("insert or replace into fetched values (?,?,?,?,?,?)",
                    (e.isoformat(), req_d.isoformat(), fetched_at, len(rows), len(us), 1 if rows else 0))
        con.commit()
        if i % 50 == 0:
            print("%d/%d %s · صفوف %d (أمريكيّة %d) · %.0f ث" % (i, len(days), e, len(rows), len(us), time.time() - t0), flush=True)
    print("انتهى: %.0f ث" % (time.time() - t0), flush=True)


if __name__ == "__main__":
    main()
