from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field


TraceType = Literal["message_in", "tool_call", "decision", "reply", "error"]


class TraceStepSchema(BaseModel):
    at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    type: TraceType
    name: str
    input: Optional[Any] = None
    output: Optional[Any] = None


class AuditLogger:
    """In-memory or persistent helper to log traces conforming strictly to SUBMISSION.md."""

    @staticmethod
    def create_step(
        step_type: TraceType,
        name: str,
        input_data: Optional[Any] = None,
        output_data: Optional[Any] = None,
        timestamp: Optional[datetime] = None,
    ) -> TraceStepSchema:
        ts = (timestamp or datetime.now(timezone.utc)).isoformat()
        return TraceStepSchema(
            at=ts,
            type=step_type,
            name=name,
            input=input_data,
            output=output_data,
        )
