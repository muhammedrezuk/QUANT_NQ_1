# -*- coding: utf-8 -*-
"""قانون الأيّام (ختم المالك «nq» ٢٠٢٦-١٠-١٧): 15 يومًا في السنة لا تداول فيها لأيّ رمز — عطل البورصة والبنوك الأمريكيّة والإغلاق المبكّر."""
import pathlib
import sys
from datetime import datetime, timezone

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from shared import market_clock as mc  # noqa: E402


def at(day: str, hour_utc: int = 15) -> float:
    return datetime.fromisoformat(day).replace(hour=hour_utc, tzinfo=timezone.utc).timestamp()


def test_market_and_bank_holidays_and_half_days():
    assert mc.no_trade_day(at("2026-11-26")) == mc.THANKSGIVING          # عيد الشكر
    assert mc.no_trade_day(at("2026-11-27")) == mc.EARLY_CLOSE           # الجمعة بعده (نصف يوم)
    assert mc.no_trade_day(at("2026-12-24")) == mc.EARLY_CLOSE           # ليلة الميلاد
    assert mc.no_trade_day(at("2026-12-25")) == "christmas-day"
    assert mc.no_trade_day(at("2026-10-12")) == mc.COLUMBUS              # البنوك وحدها
    assert mc.no_trade_day(at("2026-11-11")) == mc.VETERANS
    assert mc.no_trade_day(at("2026-07-03")) == "independence-day"       # 4 تمّوز سبتٌ ⟸ الجمعة عطلة
    assert mc.no_trade_day(at("2027-07-02")) is None                    # يوم عملٍ عاديّ
    assert mc.no_trade_day(at("2027-07-05")) == "independence-day"       # 4 تمّوز 2027 أحد ⟸ الاثنين


def test_ordinary_days_trade():
    for d in ("2026-10-16", "2026-10-19", "2026-11-25", "2026-12-23"):
        assert mc.no_trade_day(at(d)) is None, d


def test_the_evening_before_belongs_to_the_holiday():
    # يوم الوسيط يبدأ مع افتتاح 18:00 نيويورك ⟸ مساء الأربعاء بعد الافتتاح من يوم الخميس (عيد الشكر).
    wed_after_open = datetime(2026, 11, 25, 23, 30, tzinfo=timezone.utc).timestamp()   # 18:30 نيويورك شتاءً
    assert mc.no_trade_day(wed_after_open) == mc.THANKSGIVING
    count = sum(1 for m in range(1, 13) for d in range(1, 29) if mc.no_trade_day(at("2026-%02d-%02d" % (m, d))))
    assert count >= 13, count
