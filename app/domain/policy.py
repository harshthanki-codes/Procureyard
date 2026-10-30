from datetime import date, datetime, timezone, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

# IST is UTC+05:30 (Indian Standard Time)
IST = timezone(timedelta(hours=5, minutes=30))


def to_ist_date(dt: datetime) -> date:
    """Convert a datetime (naive UTC or aware) to IST calendar date."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(IST).date()


def calculate_trip_fare(distance_km: float, surge_multiplier: float = 1.0) -> int:
    """
    Every completed trip pays ₹25 base + ₹6 for each km after the first 2 km.
    If the trip had a surge multiplier, it applies to the whole trip fare (base + distance).
    Round each trip to the nearest rupee, 0.5 rounds up.
    """
    base = Decimal("25.0")
    dist = Decimal(str(distance_km))
    extra_km = max(Decimal("0.0"), dist - Decimal("2.0"))
    dist_fare = extra_km * Decimal("6.0")
    surge = Decimal(str(surge_multiplier))
    total = (base + dist_fare) * surge
    return int(total.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def calculate_daily_incentive(completed_trips_count: int) -> int:
    """Daily incentive of ₹150 for 12 or more trips in a day."""
    if completed_trips_count >= 12:
        return 150
    return 0


def calculate_cancellation_penalty(status: str) -> int:
    """
    ₹10 penalty for every trip the rider cancels.
    Customer cancellations earn nothing and have no penalty.
    """
    if status == "cancelled_by_rider":
        return -10
    return 0


def is_within_dispute_window(trip_or_dispute_date: date, reference_date: date, max_days: int = 7) -> bool:
    """We only look at disputes for the last 7 days."""
    diff = (reference_date - trip_or_dispute_date).days
    return 0 <= diff <= max_days
