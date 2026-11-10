"""Stage 1, step 2 of the owner's plan (seal "NQ", 2026-10-17): the hand-written summer/winter rules of the market clock
(on which the candle builder 103 and the cTrader feed 622 stand) must equal the time-zone database for New York and London,
hour by hour from 2014 to 2030 -- otherwise nothing may be switched without showing the owner the difference."""
import pathlib
import sys
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from shared import market_clock as mc  # noqa: E402

START = int(datetime(2014, 1, 1, tzinfo=timezone.utc).timestamp())
END = int(datetime(2031, 1, 1, tzinfo=timezone.utc).timestamp())
HOUR = 3600


def test_new_york_and_london_hand_rules_equal_the_zone_database_every_hour_2014_2030():
    zones = {mc.CITY_NEW_YORK: ZoneInfo("America/New_York"), mc.CITY_LONDON: ZoneInfo("Europe/London")}
    mismatches = []
    for city, zone in zones.items():
        for t in range(START, END, HOUR):
            hand = mc.OFFSET_FNS[city](float(t))
            real = datetime.fromtimestamp(t, zone).utcoffset().total_seconds() / HOUR
            if hand != real:
                mismatches.append((city, datetime.fromtimestamp(t, timezone.utc).isoformat(), hand, real))
    assert mismatches == [], mismatches[:10]


def test_broker_clock_is_new_york_plus_seven_every_hour_2014_2030():
    ny = ZoneInfo("America/New_York")
    bad = [t for t in range(START, END, HOUR)
           if mc.broker_day_offset_s(float(t)) != datetime.fromtimestamp(t, ny).utcoffset().total_seconds() + 7 * HOUR]
    assert bad == [], bad[:5]
