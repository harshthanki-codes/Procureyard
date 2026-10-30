from datetime import datetime, timezone
import uuid
from typing import Any, Dict, List, Optional
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.models import OpsPendingItem
from app.services.payswift import payswift_client


class OpsService:
    @staticmethod
    async def create_pending_item(
        session: AsyncSession,
        rider_id: str,
        item_type: str,  # "approval" or "escalation"
        reason: str,
        amount: Optional[int] = None,
    ) -> OpsPendingItem:
        """Create an approval or escalation item in the ops queue."""
        item_id = f"ops_{uuid.uuid4().hex[:8]}"
        item = OpsPendingItem(
            id=item_id,
            rider_id=rider_id,
            item_type=item_type,
            amount=amount if item_type == "approval" else None,
            reason=reason,
            status="pending",
            created_at=datetime.now(timezone.utc),
        )
        session.add(item)
        await session.commit()
        await session.refresh(item)
        return item

    @staticmethod
    async def get_pending_items(session: AsyncSession) -> List[Dict[str, Any]]:
        """
        Return JSON list of items waiting for ops conforming strictly to SUBMISSION.md:
        [{ "id": "...", "rider_id": "...", "type": "approval"|"escalation", "amount": 120|null, "reason": "...", "created_at": "<ISO>" }]
        """
        stmt = (
            select(OpsPendingItem)
            .where(OpsPendingItem.status == "pending")
            .order_by(OpsPendingItem.created_at.asc())
        )
        res = await session.execute(stmt)
        items = res.scalars().all()

        results = []
        for it in items:
            results.append(
                {
                    "id": it.id,
                    "rider_id": it.rider_id,
                    "type": it.item_type,
                    "amount": it.amount,
                    "reason": it.reason,
                    "created_at": it.created_at.isoformat(),
                }
            )
        return results

    @staticmethod
    async def process_ops_decision(
        session: AsyncSession,
        item_id: str,
        decision: str,  # "approved" or "rejected"
    ) -> Dict[str, Any]:
        """Human ops approves or rejects an item. If approved and type==approval, disburse via PaySwift."""
        stmt = select(OpsPendingItem).where(OpsPendingItem.id == item_id)
        res = await session.execute(stmt)
        item = res.scalar_one_or_none()
        if not item:
            return {"error": "Item not found"}

        item.status = decision
        disbursed = False
        payout_info = None

        if decision == "approved" and item.item_type == "approval" and item.amount:
            # Trigger payout via PaySwift
            idempotency_key = f"ops-appr-{item.id}"
            payout_info = await payswift_client.create_payout(
                rider_id=item.rider_id,
                amount=item.amount,
                reference=f"Ops Approved: {item.reason[:50]}",
                idempotency_key=idempotency_key,
            )
            disbursed = True

        await session.commit()
        return {
            "status": "success",
            "item_id": item.id,
            "decision": decision,
            "disbursed": disbursed,
            "payout_info": payout_info,
        }
