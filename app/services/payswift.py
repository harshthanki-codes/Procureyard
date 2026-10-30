import asyncio
from datetime import date, datetime, timezone
import logging
import random
from typing import Any, Dict, List, Optional
import httpx
from app.core.config import settings
from app.domain.policy import to_ist_date

logger = logging.getLogger(__name__)


class PaySwiftException(Exception):
    def __init__(self, message: str, status_code: Optional[int] = None, payload: Optional[Any] = None):
        super().__init__(message)
        self.status_code = status_code
        self.payload = payload


class PaySwiftClient:
    """
    Resilient PaySwift sandbox API client with automatic retries,
    exponential backoff with jitter, and strict idempotency.
    """

    def __init__(self, base_url: Optional[str] = None, timeout: float = 8.0, max_retries: int = 3):
        self.base_url = (base_url or settings.PAYSWIFT_BASE_URL).rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries

    async def check_health(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                res = await client.get(f"{self.base_url}/health")
                return res.status_code == 200
        except Exception:
            return False

    async def list_payouts(self, rider_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Fetch list of payouts from PaySwift ledger, optionally filtered by rider_id."""
        url = f"{self.base_url}/v1/payouts"
        params = {"rider_id": rider_id} if rider_id else {}

        for attempt in range(self.max_retries):
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    resp = await client.get(url, params=params)
                    if resp.status_code == 200:
                        data = resp.json()
                        return data.get("data", [])
                    elif resp.status_code in (429, 500, 502, 503, 504):
                        await self._sleep_backoff(attempt)
                        continue
                    else:
                        raise PaySwiftException(f"PaySwift GET returned {resp.status_code}: {resp.text}", resp.status_code)
            except (httpx.RequestError, httpx.TimeoutException) as exc:
                if attempt == self.max_retries - 1:
                    raise PaySwiftException(f"PaySwift GET failed after {self.max_retries} attempts: {exc}")
                await self._sleep_backoff(attempt)
        return []

    async def count_payouts_on_date(self, rider_id: str, target_date_ist: date) -> int:
        """Counts how many payouts the rider has already received on a given calendar day (IST)."""
        payouts = await self.list_payouts(rider_id=rider_id)
        count = 0
        for p in payouts:
            created_at_str = p.get("created_at") or p.get("at")
            if created_at_str:
                try:
                    if created_at_str.endswith("Z"):
                        created_at_str = created_at_str[:-1] + "+00:00"
                    dt = datetime.fromisoformat(created_at_str)
                    if to_ist_date(dt) == target_date_ist:
                        count += 1
                except Exception:
                    pass
        return count

    async def create_payout(
        self,
        rider_id: str,
        amount: int,
        reference: str,
        idempotency_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Disburse payout to rider via PaySwift.
        Includes Idempotency-Key and retries with jitter to handle chaos testing.
        """
        if amount < 1 or amount > 10000:
            raise PaySwiftException(f"Invalid amount {amount}. Must be whole rupees between 1 and 10000.", 400)

        url = f"{self.base_url}/v1/payouts"
        clean_reference = reference.encode("ascii", "ignore").decode("ascii").strip() or "Dispute Payout"
        payload = {
            "rider_id": rider_id,
            "amount": int(amount),
            "reference": clean_reference,
        }
        headers = {"Content-Type": "application/json"}
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key

        last_error = None
        for attempt in range(self.max_retries):
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    resp = await client.post(url, json=payload, headers=headers)
                    if resp.status_code in (200, 201):
                        return resp.json()
                    elif resp.status_code == 409:
                        # Idempotency collision or already processed
                        return resp.json()
                    elif resp.status_code in (429, 500, 502, 503, 504):
                        last_error = f"Status {resp.status_code}: {resp.text}"
                        await self._sleep_backoff(attempt)
                        continue
                    else:
                        raise PaySwiftException(
                            f"PaySwift POST rejected ({resp.status_code}): {resp.text}",
                            resp.status_code,
                            resp.json() if resp.headers.get("content-type") == "application/json" else None,
                        )
            except (httpx.RequestError, httpx.TimeoutException) as exc:
                last_error = str(exc)
                if attempt == self.max_retries - 1:
                    raise PaySwiftException(f"PaySwift POST failed after {self.max_retries} attempts: {last_error}")
                await self._sleep_backoff(attempt)

        raise PaySwiftException(f"PaySwift payout failed: {last_error}")

    async def _sleep_backoff(self, attempt: int) -> None:
        """Exponential backoff with full jitter."""
        base_delay = 0.3 * (2**attempt)
        jitter = random.uniform(0.1, 0.4)
        await asyncio.sleep(base_delay + jitter)


payswift_client = PaySwiftClient()
