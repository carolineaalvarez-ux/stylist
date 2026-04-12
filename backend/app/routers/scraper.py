"""Manual scraper trigger endpoint (for testing / on-demand runs)."""
from __future__ import annotations

import asyncio
import logging
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..scheduler.jobs import run_scrape_pipeline

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/scraper", tags=["scraper"])


@router.post("/run")
async def trigger_scrape(
    background_tasks: BackgroundTasks,
    source: Optional[str] = None,   # "asos" | "nordstrom" | None for both
    db: AsyncSession = Depends(get_db),
):
    """
    Manually trigger the scraping pipeline.
    Runs in the background and returns immediately.
    """
    background_tasks.add_task(run_scrape_pipeline, source=source)
    return {
        "status": "started",
        "message": f"Scrape pipeline started for source={'all' if not source else source}",
    }


@router.get("/status")
async def scrape_status():
    """Basic health check for the scraper (extend with Redis state later)."""
    return {"status": "idle", "last_run": None}
