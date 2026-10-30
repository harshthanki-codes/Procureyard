import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app


@pytest.mark.anyio
async def test_health_endpoint():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}


@pytest.mark.anyio
async def test_ops_pending_and_reset():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        reset_resp = await client.post("/ops/reset")
        assert reset_resp.status_code == 200

        pending_resp = await client.get("/ops/pending")
        assert pending_resp.status_code == 200
        assert isinstance(pending_resp.json(), list)


@pytest.mark.anyio
async def test_trace_endpoint():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/trace/R001")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)
