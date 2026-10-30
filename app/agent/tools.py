from datetime import date, datetime, timezone
import re
from typing import Any, Dict, List, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import AuditLogger
from app.core.config import settings
from app.db.models import TraceRecord, Trip, PayoutLine
from app.domain.discrepancy import evaluate_rider_discrepancies, DiscrepancyReport
from app.domain.policy import to_ist_date
from app.services.ops import OpsService
from app.services.payswift import payswift_client


def parse_date_reference(text: str, ref_date: Optional[date] = None, reference_year_month: str = "2026-09") -> Optional[date]:
    """Parse dates like '20', '20th', '20 wala', '20 tarikh', 'Sep 19', '19th', '17', 'kal', 'yesterday'."""
    from datetime import timedelta
    text_lower = text.lower()

    if ref_date and ("kal" in text_lower or "yesterday" in text_lower):
        return ref_date - timedelta(days=1)

    # Direct match for day numbers like '20 tarikh', '20 wala', '20 ko', 'Sep 19', '19th'
    patterns = [
        r"\b(?:sep|september)?\s*([0-2]?[0-9]|3[01])\s*(?:th|st|nd|rd)?\s*(?:tarikh|ko|wala|wali|pe|date|orders|order)?\b",
        r"\border\s+t[0-9]+\s+on\s+([0-2]?[0-9]|3[01])\b",
        r"\b([0-2]?[0-9]|3[01])\s*(?:sept|sep|september)\b",
    ]
    for pat in patterns:
        m = re.search(pat, text_lower)
        if m and m.group(1):
            day_num = int(m.group(1))
            if 1 <= day_num <= 31:
                day_str = str(day_num).zfill(2)
                try:
                    return date.fromisoformat(f"{reference_year_month}-{day_str}")
                except Exception:
                    pass
    return None


def parse_trip_ids(text: str) -> List[str]:
    """Extract order/trip IDs like T926334, T604546, T795007."""
    return re.findall(r"\b[tT][0-9]{5,7}\b", text)


async def execute_payout_or_queue(
    session: AsyncSession,
    rider_id: str,
    discrepancy_amount: int,
    reason: str,
    trace_steps: List[TraceRecord],
) -> Dict[str, Any]:
    """
    Core Financial Guardrail:
    - If amount <= 200 AND rider has not received auto-payout today:
      Executes payout via PaySwift and logs 'decision' and 'tool_call'.
    - If amount > 200 OR rider already received auto-payout today:
      Queues for Ops Approval.
    """
    # Check auto-payouts executed in current system state for this rider
    from sqlalchemy import func
    trace_stmt = select(func.count(TraceRecord.id)).where(
        TraceRecord.rider_id == rider_id,
        TraceRecord.step_type == "tool_call",
        TraceRecord.name == "payswift_create_payout"
    )
    t_res = await session.execute(trace_stmt)
    payouts_today = t_res.scalar_one_or_none() or 0

    # Log tool call attempt
    tool_input = {"rider_id": rider_id, "amount": discrepancy_amount, "reason": reason}

    if discrepancy_amount <= settings.AUTO_PAY_MAX_AMOUNT and payouts_today < settings.MAX_AUTO_PAYS_PER_RIDER_PER_DAY:
        # Eligible for auto-pay
        try:
            idempotency_key = f"qd-auto-{rider_id}-{datetime.now().strftime('%Y%m%d%H%M%S')}-{discrepancy_amount}"
            payout_res = await payswift_client.create_payout(
                rider_id=rider_id,
                amount=discrepancy_amount,
                reference=reason[:60],
                idempotency_key=idempotency_key,
            )
            tool_output = {"status": "disbursed", "amount": discrepancy_amount, "payout_res": payout_res}
            decision_output = {"action": "auto_payout", "amount": discrepancy_amount, "channel": "PaySwift"}

            # Trace steps
            trace_steps.append(
                TraceRecord(
                    rider_id=rider_id,
                    step_type="tool_call",
                    name="payswift_create_payout",
                    input_json=tool_input,
                    output_json=tool_output,
                    at=datetime.now(timezone.utc),
                )
            )
            trace_steps.append(
                TraceRecord(
                    rider_id=rider_id,
                    step_type="decision",
                    name="auto_pay_decision",
                    input_json={"rule": "amount <= 200 and payouts_today == 0", "amount": discrepancy_amount},
                    output_json=decision_output,
                    at=datetime.now(timezone.utc),
                )
            )

            return {"action": "paid", "amount": discrepancy_amount}
        except Exception as e:
            # Fallback to ops queue on payment failure
            ops_item = await OpsService.create_pending_item(
                session=session,
                rider_id=rider_id,
                item_type="approval",
                amount=discrepancy_amount,
                reason=f"Payment gateway error: {e}. Original: {reason}",
            )
            return {"action": "queued_for_approval", "amount": discrepancy_amount, "ops_id": ops_item.id}
    else:
        # Exceeds limit or second payout today -> Send to Ops Approval
        approval_reason = (
            f"Exceeds ₹{settings.AUTO_PAY_MAX_AMOUNT} auto-pay limit (Amount: ₹{discrepancy_amount}). {reason}"
            if discrepancy_amount > settings.AUTO_PAY_MAX_AMOUNT
            else f"Already received an auto-payment today (Daily limit 1). {reason}"
        )
        ops_item = await OpsService.create_pending_item(
            session=session,
            rider_id=rider_id,
            item_type="approval",
            amount=discrepancy_amount,
            reason=approval_reason,
        )
        decision_output = {"action": "queued_ops_approval", "amount": discrepancy_amount, "ops_id": ops_item.id}

        trace_steps.append(
            TraceRecord(
                rider_id=rider_id,
                step_type="decision",
                name="ops_approval_queue_decision",
                input_json={"rule": "amount > 200 or already_paid_today", "amount": discrepancy_amount},
                output_json=decision_output,
                at=datetime.now(timezone.utc),
            )
        )
        return {"action": "queued_for_approval", "amount": discrepancy_amount, "ops_id": ops_item.id}
