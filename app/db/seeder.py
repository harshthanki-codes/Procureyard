import csv
from datetime import datetime, date
import os
from pathlib import Path
from typing import Optional
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.models import Rider, Trip, PayoutLine


def normalize_rider_id(rid: str) -> str:
    """Normalize rider IDs such as R7 -> R007, r19 -> R019."""
    r = rid.strip()
    if r.lower().startswith("r"):
        num_part = r[1:]
        if num_part.isdigit():
            return f"R{int(num_part):03d}"
    return r.upper()


async def seed_data_if_empty(session: AsyncSession, data_dir: Optional[str] = None) -> None:
    """Seed base CSV data into PostgreSQL / SQLite if tables are empty."""
    if data_dir is None:
        base_dir = Path(__file__).resolve().parent.parent.parent
        data_dir = str(base_dir / "data")

    # 1. Check if Riders exist
    count_res = await session.execute(select(func.count(Rider.rider_id)))
    riders_count = count_res.scalar_one_or_none() or 0
    if riders_count == 0:
        riders_file = os.path.join(data_dir, "riders.csv")
        if os.path.exists(riders_file):
            riders_to_add = []
            for row in csv.DictReader(open(riders_file, mode="r", encoding="utf-8")):
                riders_to_add.append(
                    Rider(
                        rider_id=normalize_rider_id(row["rider_id"]),
                        name=row["name"].strip(),
                        city=row["city"].strip(),
                        joined_on=date.fromisoformat(row["joined_on"].strip()),
                    )
                )
            session.add_all(riders_to_add)

    # 2. Check if Trips exist
    count_res = await session.execute(select(func.count(Trip.trip_id)))
    trips_count = count_res.scalar_one_or_none() or 0
    if trips_count == 0:
        trips_file = os.path.join(data_dir, "trips.csv")
        if os.path.exists(trips_file):
            trips_to_add = []
            seen_trip_ids = set()
            for row in csv.DictReader(open(trips_file, mode="r", encoding="utf-8")):
                tid = row["trip_id"].strip()
                if tid in seen_trip_ids:
                    continue
                seen_trip_ids.add(tid)
                started_str = row["started_at"].strip()
                if started_str.endswith("Z"):
                    started_str = started_str[:-1] + "+00:00"
                started_dt = datetime.fromisoformat(started_str)

                # Clean GPS meter anomaly (e.g. 5000.0 m -> 5.0 km)
                raw_dist = float(row["distance_km"])
                clean_dist = raw_dist / 1000.0 if raw_dist > 100.0 else raw_dist

                trips_to_add.append(
                    Trip(
                        trip_id=tid,
                        rider_id=normalize_rider_id(row["rider_id"]),
                        started_at=started_dt,
                        status=row["status"].strip(),
                        distance_km=clean_dist,
                        surge_multiplier=float(row.get("surge_multiplier", 1.0) or 1.0),
                    )
                )
            session.add_all(trips_to_add)

    # 3. Check if PayoutLines exist
    count_res = await session.execute(select(func.count(PayoutLine.line_id)))
    payout_count = count_res.scalar_one_or_none() or 0
    if payout_count == 0:
        payout_file = os.path.join(data_dir, "payout_lines.csv")
        if os.path.exists(payout_file):
            payouts_to_add = []
            for row in csv.DictReader(open(payout_file, mode="r", encoding="utf-8")):
                trip_id_val = row.get("trip_id", "").strip() or None
                payouts_to_add.append(
                    PayoutLine(
                        line_id=row["line_id"].strip(),
                        payout_date=date.fromisoformat(row["payout_date"].strip()),
                        rider_id=normalize_rider_id(row["rider_id"]),
                        line_type=row["line_type"].strip(),
                        trip_id=trip_id_val,
                        amount=int(row["amount"]),
                    )
                )
            session.add_all(payouts_to_add)

    await session.commit()
