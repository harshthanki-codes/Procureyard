import asyncio
import pytest
from app.db.session import init_db, AsyncSessionLocal
from app.db.seeder import seed_data_if_empty


@pytest.fixture(scope="session")
def anyio_backend():
    return "asyncio"


@pytest.fixture(scope="session", autouse=True)
def setup_database_tables():
    """Ensure database schema is created and seeded once per test session."""
    async def _init():
        await init_db()
        async with AsyncSessionLocal() as session:
            await seed_data_if_empty(session)

    asyncio.run(_init())
