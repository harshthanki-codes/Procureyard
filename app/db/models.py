from datetime import date, datetime, timezone
from typing import Any, Optional
from sqlalchemy import (
    Column,
    Date,
    DateTime,
    Float,
    Integer,
    String,
    Text,
    JSON,
    Index,
)
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class Rider(Base):
    __tablename__ = "riders"

    rider_id = Column(String(50), primary_key=True)
    name = Column(String(100), nullable=False)
    city = Column(String(100), nullable=False)
    joined_on = Column(Date, nullable=False)


class Trip(Base):
    __tablename__ = "trips"

    trip_id = Column(String(50), primary_key=True)
    rider_id = Column(String(50), nullable=False, index=True)
    started_at = Column(DateTime(timezone=True), nullable=False, index=True)
    status = Column(String(50), nullable=False)  # completed, cancelled_by_rider, cancelled_by_customer
    distance_km = Column(Float, nullable=False)
    surge_multiplier = Column(Float, default=1.0, nullable=False)


class PayoutLine(Base):
    __tablename__ = "payout_lines"

    line_id = Column(String(50), primary_key=True)
    payout_date = Column(Date, nullable=False, index=True)
    rider_id = Column(String(50), nullable=False, index=True)
    line_type = Column(String(50), nullable=False)  # trip, daily_incentive, cancellation_penalty
    trip_id = Column(String(50), nullable=True, index=True)
    amount = Column(Integer, nullable=False)


class MessageRecord(Base):
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    message_id = Column(String(100), unique=True, index=True, nullable=False)
    rider_id = Column(String(50), nullable=False, index=True)
    sender = Column(String(20), nullable=False)  # rider, agent
    text = Column(Text, nullable=False)
    received_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)


class TraceRecord(Base):
    __tablename__ = "trace_records"

    id = Column(Integer, primary_key=True, autoincrement=True)
    rider_id = Column(String(50), nullable=False, index=True)
    at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    step_type = Column(String(30), nullable=False)  # message_in, tool_call, decision, reply, error
    name = Column(String(100), nullable=False)
    input_json = Column(JSON, nullable=True)
    output_json = Column(JSON, nullable=True)


class OpsPendingItem(Base):
    __tablename__ = "ops_pending"

    id = Column(String(60), primary_key=True)
    rider_id = Column(String(50), nullable=False, index=True)
    item_type = Column(String(30), nullable=False)  # approval, escalation
    amount = Column(Integer, nullable=True)  # rupees for approvals, null for escalations
    reason = Column(Text, nullable=False)
    status = Column(String(20), default="pending", nullable=False)  # pending, approved, rejected
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
