from datetime import date, datetime, timezone
from app.domain.policy import (
    calculate_trip_fare,
    calculate_daily_incentive,
    calculate_cancellation_penalty,
    to_ist_date,
    is_within_dispute_window,
)


def test_completed_trip_fare_under_2km():
    # <= 2 km base fare is 25
    assert calculate_trip_fare(distance_km=1.0, surge_multiplier=1.0) == 25
    assert calculate_trip_fare(distance_km=2.0, surge_multiplier=1.0) == 25


def test_completed_trip_fare_with_surge_and_rounding():
    # 6.0 km with 1.5 surge: (25 + 4*6) * 1.5 = 49 * 1.5 = 73.5 -> 74
    assert calculate_trip_fare(distance_km=6.0, surge_multiplier=1.5) == 74

    # 10.0 km with 1.2 surge: (25 + 8*6) * 1.2 = 73 * 1.2 = 87.6 -> 88
    assert calculate_trip_fare(distance_km=10.0, surge_multiplier=1.2) == 88

    # 7.4 km with 1.0 surge: 25 + 5.4*6 = 25 + 32.4 = 57.4 -> 57
    assert calculate_trip_fare(distance_km=7.4, surge_multiplier=1.0) == 57


def test_daily_incentive_rule():
    # ₹150 for 12 or more completed trips
    assert calculate_daily_incentive(0) == 0
    assert calculate_daily_incentive(10) == 0
    assert calculate_daily_incentive(11) == 0
    assert calculate_daily_incentive(12) == 150
    assert calculate_daily_incentive(20) == 150


def test_cancellation_penalties():
    # ₹10 penalty for rider cancel, ₹0 for customer cancel
    assert calculate_cancellation_penalty("cancelled_by_rider") == -10
    assert calculate_cancellation_penalty("cancelled_by_customer") == 0
    assert calculate_cancellation_penalty("completed") == 0


def test_ist_calendar_day_conversion():
    # 2026-09-12 02:30:00 UTC is 08:00:00 IST (same day)
    utc_morning = datetime(2026, 9, 12, 2, 30, tzinfo=timezone.utc)
    assert to_ist_date(utc_morning) == date(2026, 9, 12)

    # 2026-09-12 18:31:00 UTC is 00:01:00 IST on 2026-09-13
    utc_night = datetime(2026, 9, 12, 18, 31, tzinfo=timezone.utc)
    assert to_ist_date(utc_night) == date(2026, 9, 13)


def test_7_day_dispute_window():
    today = date(2026, 9, 23)
    assert is_within_dispute_window(date(2026, 9, 23), today) is True
    assert is_within_dispute_window(date(2026, 9, 16), today) is True  # 7 days
    assert is_within_dispute_window(date(2026, 9, 15), today) is False  # 8 days (expired)
    assert is_within_dispute_window(date(2026, 9, 13), today) is False  # 10 days (expired)
