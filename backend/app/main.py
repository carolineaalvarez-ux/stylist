"""FastAPI application entry point."""
from __future__ import annotations

import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .database import create_tables
from .routers import (
    alerts_router,
    feedback_router,
    matches_router,
    products_router,
    scraper_router,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Starting up Stylist API…")
    await create_tables()

    # Schedule daily scrape at 06:00 UTC
    from .scheduler.jobs import run_scrape_pipeline
    scheduler.add_job(
        run_scrape_pipeline,
        CronTrigger(hour=6, minute=0, timezone="UTC"),
        id="daily_scrape",
        replace_existing=True,
    )
    scheduler.start()
    logger.info("APScheduler started — daily scrape at 06:00 UTC")

    yield

    # Shutdown
    scheduler.shutdown(wait=False)
    logger.info("Stylist API shut down")


app = FastAPI(
    title="Stylist — Deep Winter Shopping Agent",
    description="Finds clothing matching your Deep Winter color palette.",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(matches_router, prefix="/api/v1")
app.include_router(products_router, prefix="/api/v1")
app.include_router(feedback_router, prefix="/api/v1")
app.include_router(alerts_router, prefix="/api/v1")
app.include_router(scraper_router, prefix="/api/v1")


@app.get("/health")
async def health():
    return {"status": "ok", "version": "1.0.0"}
