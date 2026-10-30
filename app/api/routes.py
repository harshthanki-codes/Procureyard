from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.engine import AgentEngine
from app.db.models import TraceRecord, Rider, MessageRecord, OpsPendingItem
from app.db.session import get_db
from sqlalchemy import select, delete
from app.services.ops import OpsService
from app.services.payswift import payswift_client

router = APIRouter()


class IncomingMessageRequest(BaseModel):
    message_id: str
    rider_id: str
    text: str
    received_at: str


class IncomingMessageResponse(BaseModel):
    reply: str


class OpsDecisionRequest(BaseModel):
    item_id: str
    decision: str  # "approved" or "rejected"


@router.get("/health")
async def health_check() -> Dict[str, str]:
    """Health check endpoint answering 200 when ready."""
    return {"status": "ok"}


@router.post("/messages", response_model=IncomingMessageResponse)
async def handle_message(
    payload: IncomingMessageRequest,
    session: AsyncSession = Depends(get_db),
) -> IncomingMessageResponse:
    """
    Vendor webhook for rider messages.
    Returns {"reply": "..."} to be forwarded back to WhatsApp.
    """
    engine = AgentEngine(session)
    reply_text = await engine.process_incoming_message(
        message_id=payload.message_id,
        rider_id=payload.rider_id,
        text=payload.text,
        received_at_str=payload.received_at,
    )
    return IncomingMessageResponse(reply=reply_text)


@router.get("/trace/{rider_id}")
async def get_rider_trace(
    rider_id: str,
    session: AsyncSession = Depends(get_db),
) -> List[Dict[str, Any]]:
    """
    GET /trace/{rider_id}
    Returns a JSON list of steps in order:
    [
      {"at": "<ISO time>", "type": "message_in", "name": "<name>", "input": {...}, "output": null},
      {"at": "<ISO time>", "type": "tool_call",  "name": "<your tool>", "input": {...}, "output": {...}},
      {"at": "<ISO time>", "type": "decision",   "name": "<what was decided>", "input": {...}, "output": {...}},
      {"at": "<ISO time>", "type": "reply",      "name": "<name>", "input": null, "output": "<text>"}
    ]
    """
    stmt = (
        select(TraceRecord)
        .where(TraceRecord.rider_id == rider_id)
        .order_by(TraceRecord.at.asc(), TraceRecord.id.asc())
    )
    res = await session.execute(stmt)
    records = res.scalars().all()

    trace_list = []
    for r in records:
        trace_list.append(
            {
                "at": r.at.isoformat() if r.at.tzinfo else r.at.replace(tzinfo=timezone.utc).isoformat(),
                "type": r.step_type,
                "name": r.name,
                "input": r.input_json,
                "output": r.output_json,
            }
        )
    return trace_list


@router.get("/ops/pending")
async def get_ops_pending(
    session: AsyncSession = Depends(get_db),
) -> List[Dict[str, Any]]:
    """
    GET /ops/pending
    Returns a JSON list of items waiting for ops:
    [
      {"id": "<id>", "rider_id": "<rider>", "type": "approval", "amount": 120, "reason": "...", "created_at": "<ISO time>"},
      {"id": "<id>", "rider_id": "<rider>", "type": "escalation", "amount": null, "reason": "...", "created_at": "<ISO time>"}
    ]
    """
    return await OpsService.get_pending_items(session)


@router.post("/ops/decision")
async def ops_decision(
    payload: OpsDecisionRequest,
    session: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Action endpoint for ops executives to approve or reject items."""
    return await OpsService.process_ops_decision(
        session=session,
        item_id=payload.item_id,
        decision=payload.decision,
    )


@router.post("/ops/reset")
async def reset_ops_state(session: AsyncSession = Depends(get_db)) -> Dict[str, str]:
    """Reset test state (traces, messages, ops pending) for fresh evaluation per data/README.md."""
    await session.execute(delete(TraceRecord))
    await session.execute(delete(MessageRecord))
    await session.execute(delete(OpsPendingItem))
    await session.commit()
    return {"status": "reset_success"}


@router.get("/api/riders")
async def list_riders(session: AsyncSession = Depends(get_db)) -> List[Dict[str, Any]]:
    """List riders for UI simulator dropdown."""
    stmt = select(Rider).order_by(Rider.rider_id.asc())
    res = await session.execute(stmt)
    riders = res.scalars().all()
    return [{"rider_id": r.rider_id, "name": r.name, "city": r.city} for r in riders]


@router.get("/api/payswift/ledger")
async def get_payswift_ledger() -> List[Dict[str, Any]]:
    """Fetch live PaySwift ledger for the dashboard."""
    try:
        return await payswift_client.list_payouts()
    except Exception as e:
        return [{"error": str(e)}]
