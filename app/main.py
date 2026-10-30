from contextlib import asynccontextmanager
import logging
import os
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes import router
from app.core.config import settings
from app.db.seeder import seed_data_if_empty
from app.db.session import init_db, AsyncSessionLocal

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("quickdrop.app")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Initialize DB tables and seed CSV data
    logger.info("Initializing database tables...")
    await init_db()
    logger.info("Checking and seeding CSV dataset...")
    async with AsyncSessionLocal() as session:
        await seed_data_if_empty(session)
    logger.info("QuickDrop Dispute Desk ready on port %d", settings.PORT)
    yield
    logger.info("Shutting down QuickDrop Dispute Desk.")


app = FastAPI(
    title=settings.APP_NAME,
    version="1.0.0",
    description="Production-grade Rider Payout Dispute Desk Agent and Reconciliation Engine",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include core routes (health, messages, trace, ops)
app.include_router(router)

# Serve the Ops Portal & WhatsApp Simulator at root
static_dir = Path(__file__).resolve().parent / "static"
index_html_path = static_dir / "index.html"


@app.get("/", response_class=HTMLResponse)
async def serve_dashboard():
    if index_html_path.exists():
        with open(index_html_path, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    return HTMLResponse("<h1>QuickDrop Ops Dispute Desk is Running.</h1>")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=settings.PORT, reload=settings.DEBUG)
