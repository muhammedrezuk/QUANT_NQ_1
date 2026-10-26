# -*- coding: utf-8 -*-
"""Builds shared/news_colors.json -- our own reference of the USD news colors (owner seal "NQ", 2026-10-17: "the red news of
the year are known -- write them; the difference is only in MetaTrader").

Colors are ForexFactory's (red = HIGH, orange = MEDIUM, yellow = LOW): for every ForexFactory title the bridge has stored,
the latest color seen. MetaTrader names the same events in Arabic and grades them differently (crude oil HIGH, the Fed
statement MEDIUM) -- so each MetaTrader event code is mapped by hand to its ForexFactory title, and every Arabic name that
code carries gets that color. Every MetaTrader code it grades HIGH is mapped, so none of them keeps MetaTrader's grade.
Two events not seen in the stored ForexFactory month are added from the known calendar and marked as such.
Read-only on the bridge databases; run again whenever the ForexFactory store has grown.
"""
from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "shared" / "news_colors.json"
BRIDGE = Path(os.path.expandvars(r"%APPDATA%\MetaQuotes\Terminal\Common\Files\nq_brain.db"))
HISTORY = Path(os.path.expandvars(r"%APPDATA%\MetaQuotes\Terminal\Common\Files\nq_calendar_history.db"))
COLOR = {"HIGH": "red", "MEDIUM": "orange", "LOW": "yellow", "NONE": "none"}

#: MetaTrader event code -> ForexFactory title (the color comes from ForexFactory).
MT5_TO_FF = {
    "nonfarm-payrolls": "Non-Farm Employment Change",
    "unemployment-rate": "Unemployment Rate",
    "average-hourly-earnings-mm": "Average Hourly Earnings m/m",
    "consumer-price-index-mm": "CPI m/m",
    "consumer-price-index-yy": "CPI y/y",
    "consumer-price-index-ex-food-energy-mm": "Core CPI m/m",
    "consumer-price-index-ex-food-energy-yy": "Core CPI y/y",
    "producer-price-index-mm": "PPI m/m",
    "producer-price-index-ex-food-energy-mm": "Core PPI m/m",
    "core-pce-price-index-mm": "Core PCE Price Index m/m",
    "retail-sales-mm": "Retail Sales m/m",
    "retail-sales-ex-autos-mm": "Core Retail Sales m/m",
    "gross-domestic-product-qq": "Final GDP q/q",
    "fed-interest-rate-decision": "Federal Funds Rate",
    "fomc-meeting-statement": "FOMC Statement",
    "fomc-economic-projections": "FOMC Economic Projections",
    "fomc-press-conference": "FOMC Press Conference",
    "fomc-minutes": "FOMC Meeting Minutes",
    "fed-chair-powell-speech": "Fed Chairman Warsh Speaks",
    "fed-chair-yellen-speech": "Fed Chairman Warsh Speaks",
    "fed-chair-powell-testimony": "Fed Chair Testifies",
    "fed-chair-yellen-testimony": "Fed Chair Testifies",
    "adp-nonfarm-employment-change": "ADP Non-Farm Employment Change",
    "consumer-confidence-index": "CB Consumer Confidence",
    "ism-manufacturing-pmi": "ISM Manufacturing PMI",
    "ism-non-manufacturing-pmi": "ISM Services PMI",
    "jolts-job-openings": "JOLTS Job Openings",
    "philadelphia-fed-manufacturing-index": "Philly Fed Manufacturing Index",
    "michigan-consumer-sentiment": "Prelim UoM Consumer Sentiment",
    "michigan-inflation-expectations": "Prelim UoM Inflation Expectations",
    "initial-jobless-claims": "Unemployment Claims",
    "gross-domestic-product-price-index": "Final GDP Price Index q/q",
    "fomc-member-kashkari-speech": "FOMC Member Kashkari Speaks",
    # MetaTrader HIGH, ForexFactory yellow:
    "10-year-note-auction": "10-y Bond Auction",
    "30-year-bond-auction": "30-y Bond Auction",
    "chicago-pmi": "Chicago PMI",
    "durable-goods-orders": "Durable Goods Orders m/m",
    "eia-crude-oil-stocks-change": "Crude Oil Inventories",
    "existing-home-sales": "Existing Home Sales",
    "new-home-sales": "New Home Sales",
    "markit-manufacturing-pmi": "Flash Manufacturing PMI",
    "markit-services-pmi": "Flash Services PMI",
    "ism-prices-paid": "ISM Manufacturing Prices",
}
#: MetaTrader HIGH codes ForexFactory does not carry as an event of its own -- yellow (the parent event carries the color).
MT5_YELLOW = ("consumer-price-index", "consumer-price-index-ex-food-energy-nsa-mm", "core-pce-price-index-yy",
              "gdp-sales-qq", "ism-non-manufacturing-prices")
#: Not seen in the stored ForexFactory month; red in the known calendar (marked "known", to confirm when seen).
KNOWN = {"Advance GDP q/q": "red", "Prelim GDP q/q": "red", "Fed Chair Testifies": "red"}


def main() -> None:
    ff: dict[str, tuple[float, str]] = {}
    b = sqlite3.connect("file:%s?mode=ro" % BRIDGE, uri=True)
    for title, impact, at in b.execute("SELECT title, impact_level, scheduled_at FROM calendar_ff WHERE currency='USD'"):
        color = COLOR.get(str(impact or "").upper())
        if color and (title not in ff or at > ff[title][0]):
            ff[title] = (float(at), color)
    b.close()
    colors = {title: color for title, (_, color) in ff.items()}
    origin = {title: "forexfactory" for title in colors}
    for title, color in KNOWN.items():
        if title not in colors:
            colors[title], origin[title] = color, "known"
    names: dict[str, list[str]] = {}
    h = sqlite3.connect("file:%s?mode=ro" % HISTORY, uri=True)
    for code, name in h.execute("SELECT DISTINCT event_code, event_name FROM calendar_history WHERE currency='USD'"):
        if name:
            names.setdefault(str(code), []).append(" ".join(str(name).split()))
    high = {str(c) for (c,) in h.execute("SELECT DISTINCT event_code FROM calendar_history WHERE currency='USD' AND importance=3")}
    none_codes = {str(c) for (c,) in h.execute(
        "SELECT DISTINCT event_code FROM calendar_history WHERE currency='USD' AND importance=0")}
    h.close()
    by_name: dict[str, str] = dict(colors)
    rank = {"none": 0, "yellow": 1, "orange": 2, "red": 3}
    mt5 = {}
    for code, title in MT5_TO_FF.items():
        color = colors.get(title)
        if color is None:
            continue
        mt5[code] = {"ff_title": title, "color": color}
        for ar in names.get(code, []):
            if rank[color] > rank.get(by_name.get(ar, "none"), 0):   # one Arabic name, two codes: the stronger color
                by_name[ar] = color
    for code in MT5_YELLOW:
        mt5.setdefault(code, {"ff_title": None, "color": "yellow"})
        for ar in names.get(code, []):
            by_name.setdefault(ar, "yellow")
    for code in none_codes - set(mt5):   # MetaTrader holidays (importance 0) -- no color, like ForexFactory's "Bank Holiday"
        mt5[code] = {"ff_title": None, "color": "none"}
        for ar in names.get(code, []):
            by_name.setdefault(ar, "none")
    unmapped_high = sorted(high - set(mt5))
    out = {"built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "source": "ForexFactory colors (latest seen) + MetaTrader codes mapped by hand",
           "currency": "USD", "ff_titles": len(ff), "known_added": [t for t in KNOWN if origin.get(t) == "known"],
           "mt5_codes_mapped": len(mt5), "mt5_high_unmapped": unmapped_high,
           "red": sorted(t for t, c in colors.items() if c == "red"),
           "by_name": dict(sorted(by_name.items())), "mt5_codes": dict(sorted(mt5.items()))}
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print("ff", len(ff), "names", len(by_name), "mt5", len(mt5), "high unmapped", unmapped_high, "red", len(out["red"]))


if __name__ == "__main__":
    main()
