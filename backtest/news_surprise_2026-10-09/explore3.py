# -*- coding: utf-8 -*-
"""استكشاف ٣: رموز تقويم ميتاتريدر الأمريكيّة (للأيّام والتوقيت) + طلبٌ تجريبيّ واحد من ناسداك لتاريخٍ قديم."""
import gzip
import json
import sqlite3
import sys
import time
import urllib.request
from datetime import datetime, timezone

sys.stdout.reconfigure(encoding="utf-8")
CAL = "file:C:/Users/NQ/AppData/Roaming/MetaQuotes/Terminal/Common/Files/nq_calendar_history.db?mode=ro"
cal = sqlite3.connect(CAL, uri=True, timeout=5)
codes = ["consumer-price-index-mm", "consumer-price-index-ex-food-energy-mm", "nonfarm-payrolls", "unemployment-rate",
         "initial-jobless-claims", "retail-sales-mm", "producer-price-index-mm", "producer-price-index-ex-food-energy-mm",
         "gross-domestic-product-qq", "core-pce-price-index-mm", "ism-manufacturing-pmi", "ism-non-manufacturing-pmi",
         "fed-interest-rate-decision"]
like = cal.execute("select distinct event_code, importance from calendar_history where country_code='US' and "
                   "(event_code like '%ism%' or event_code like '%retail%' or event_code like '%pce%' or event_code like '%gross-dom%')").fetchall()
print("like:", like)
for c in codes:
    r = cal.execute("select count(*), min(time_server), max(time_server), max(importance) from calendar_history where country_code='US' and event_code=?", (c,)).fetchone()
    f = lambda t: datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%d %H:%M") if t else None
    print("%-45s n=%-4s %s .. %s imp=%s" % (c, r[0], f(r[1]), f(r[2]), r[3]))
# طلبٌ تجريبيّ: يوم الوظائف 2019-06-07 ⟸ نطلب 2019-06-08
url = "https://api.nasdaq.com/api/calendar/economicevents?date=2019-06-08"
req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"})
with urllib.request.urlopen(req, timeout=20) as resp:
    raw = resp.read()
if raw[:2] == b"\x1f\x8b":
    raw = gzip.decompress(raw)
js = json.loads(raw.decode("utf-8"))
rows = (js.get("data") or {}).get("rows") or []
print("keys top:", list(js.keys()), "data keys:", list((js.get("data") or {}).keys()))
print("n rows:", len(rows))
for r in rows:
    if "United States" in str(r.get("country")):
        print(json.dumps(r, ensure_ascii=False))
