from collections import defaultdict
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Dict, List, Optional
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Trip, PayoutLine
from app.domain.policy import (
    calculate_trip_fare,
    calculate_daily_incentive,
    calculate_cancellation_penalty,
    to_ist_date,
    is_within_dispute_window,
)


class DiscrepancyItem(BaseModel):
    item_type: str  # "trip_fare", "daily_incentive", "cancellation_penalty", "missing_trip"
    date_str: str
    trip_id: Optional[str] = None
    expected_amount: int
    actual_amount: int
    underpaid_amount: int
    explanation: str


class DiscrepancyReport(BaseModel):
    rider_id: str
    total_underpaid: int
    items: List[DiscrepancyItem]
    days_evaluated: List[str]


async def evaluate_rider_discrepancies(
    session: AsyncSession,
    rider_id: str,
    target_date: Optional[date] = None,
    target_trip_id: Optional[str] = None,
    target_trip_ids: Optional[List[str]] = None,
    reference_date: Optional[date] = None,
) -> DiscrepancyReport:
    """
    Deterministically computes payout discrepancies between QuickDrop policy and actual payout lines.
    Zero LLM hallucination - backed purely by policy formulas and database records.
    """
    if reference_date is None:
        reference_date = datetime.now(timezone.utc).date()

    if target_trip_id and not target_trip_ids:
        target_trip_ids = [target_trip_id]

    # 1. Fetch Trips for rider
    trip_query = select(Trip).where(Trip.rider_id == rider_id)
    if target_trip_ids:
        trip_query = trip_query.where(Trip.trip_id.in_(target_trip_ids))
    trip_res = await session.execute(trip_query)
    trips = trip_res.scalars().all()

    # Filter trips within 7-day window if target_date not explicitly set
    evaluated_trips: List[Trip] = []
    for t in trips:
        t_date = to_ist_date(t.started_at)
        if target_date and t_date != target_date:
            continue
        if target_trip_ids or target_date or is_within_dispute_window(t_date, reference_date):
            evaluated_trips.append(t)

    # 2. Fetch Payout Lines for rider
    payout_query = select(PayoutLine).where(PayoutLine.rider_id == rider_id)
    if target_date:
        payout_query = payout_query.where(PayoutLine.payout_date == target_date)
    payout_res = await session.execute(payout_query)
    payout_lines = payout_res.scalars().all()

    # Map payout lines by trip_id and by date
    payouts_by_trip: Dict[str, List[PayoutLine]] = defaultdict(list)
    payouts_by_date: Dict[date, List[PayoutLine]] = defaultdict(list)
    for p in payout_lines:
        if p.trip_id:
            payouts_by_trip[p.trip_id].append(p)
        payouts_by_date[p.payout_date].append(p)

    discrepancy_items: List[DiscrepancyItem] = []
    trips_by_date: Dict[date, List[Trip]] = defaultdict(list)
    for t in evaluated_trips:
        trips_by_date[to_ist_date(t.started_at)].append(t)

    # 3. Check each trip
    for t in evaluated_trips:
        t_date = to_ist_date(t.started_at)
        p_lines = payouts_by_trip.get(t.trip_id, [])

        if t.status == "completed":
            expected_fare = calculate_trip_fare(t.distance_km, t.surge_multiplier)
            actual_trip_paid = sum(p.amount for p in p_lines if p.line_type == "trip")

            if len(p_lines) == 0:
                # Missing trip entirely from payout lines
                discrepancy_items.append(
                    DiscrepancyItem(
                        item_type="missing_trip",
                        date_str=t_date.isoformat(),
                        trip_id=t.trip_id,
                        expected_amount=expected_fare,
                        actual_amount=0,
                        underpaid_amount=expected_fare,
                        explanation=f"Trip {t.trip_id} on {t_date.strftime('%d %b')} was completed but missing from payout. Amount due: ₹{expected_fare}.",
                    )
                )
            elif expected_fare > actual_trip_paid:
                diff = expected_fare - actual_trip_paid
                surge_str = f" with {t.surge_multiplier}x surge" if t.surge_multiplier > 1.0 else ""
                discrepancy_items.append(
                    DiscrepancyItem(
                        item_type="trip_fare",
                        date_str=t_date.isoformat(),
                        trip_id=t.trip_id,
                        expected_amount=expected_fare,
                        actual_amount=actual_trip_paid,
                        underpaid_amount=diff,
                        explanation=f"Trip {t.trip_id} on {t_date.strftime('%d %b')}{surge_str}: ₹{expected_fare} banta tha, ₹{actual_trip_paid} mila. Farak ₹{diff}.",
                    )
                )

    # 4. Check Daily Incentives and Cancellation Penalties per date (only when evaluating ledger/day, not specific trips)
    all_dates: set[date] = set()
    if target_trip_ids:
        all_dates = {to_ist_date(t.started_at) for t in evaluated_trips}
    else:
        all_dates = set(trips_by_date.keys()).union(set(payouts_by_date.keys()))
        if target_date:
            all_dates = {target_date}
        else:
            all_dates = {d for d in all_dates if is_within_dispute_window(d, reference_date)}

        for d in sorted(all_dates):
            d_trips = trips_by_date.get(d, [])
            d_payouts = payouts_by_date.get(d, [])

            # A. Daily Incentive: 12 or more completed trips
            completed_count = sum(1 for t in d_trips if t.status == "completed")
            expected_incentive = calculate_daily_incentive(completed_count)
            actual_incentive = sum(p.amount for p in d_payouts if p.line_type == "daily_incentive")

            if expected_incentive > actual_incentive:
                diff = expected_incentive - actual_incentive
                discrepancy_items.append(
                    DiscrepancyItem(
                        item_type="daily_incentive",
                        date_str=d.isoformat(),
                        trip_id=None,
                        expected_amount=expected_incentive,
                        actual_amount=actual_incentive,
                        underpaid_amount=diff,
                        explanation=f"{d.strftime('%d %b')} ko {completed_count} trips complete hue. Incentive ₹{expected_incentive} banta tha par nahi mila. Farak ₹{diff}.",
                    )
                )

            # B. Cancellation Penalties: Check for duplicate penalty deductions
            rider_cancelled_trips = [t for t in d_trips if t.status == "cancelled_by_rider"]
            penalty_payouts = [p for p in d_payouts if p.line_type == "cancellation_penalty"]

            # If more penalties deducted than rider-cancelled trips
            if len(penalty_payouts) > len(rider_cancelled_trips):
                # Duplicate penalty deducted
                extra_penalties = len(penalty_payouts) - len(rider_cancelled_trips)
                refund_due = extra_penalties * 10
                discrepancy_items.append(
                    DiscrepancyItem(
                        item_type="cancellation_penalty",
                        date_str=d.isoformat(),
                        trip_id=penalty_payouts[0].trip_id if penalty_payouts else None,
                        expected_amount=len(rider_cancelled_trips) * -10,
                        actual_amount=sum(p.amount for p in penalty_payouts),
                        underpaid_amount=refund_due,
                        explanation=f"{d.strftime('%d %b')} ko cancellation penalty extra kata (do baar kata). ₹{refund_due} wapas bante hain.",
                    )
                )

    total_diff = sum(item.underpaid_amount for item in discrepancy_items)
    return DiscrepancyReport(
        rider_id=rider_id,
        total_underpaid=total_diff,
        items=discrepancy_items,
        days_evaluated=[d.isoformat() for d in sorted(all_dates)],
    )
