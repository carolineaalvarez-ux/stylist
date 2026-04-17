"""Manual scraper trigger endpoint."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..scheduler.jobs import run_scrape_pipeline

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/scraper", tags=["scraper"])

# Simple in-memory state — good enough for a single-process setup
_scrape_state: dict = {"status": "idle", "last_run": None, "last_source": None}


async def _tracked_pipeline(source: Optional[str]):
    _scrape_state["status"] = "running"
    _scrape_state["last_source"] = source or "all"
    try:
        await run_scrape_pipeline(source=source)
        _scrape_state["status"] = "idle"
    except Exception as exc:
        logger.error("Scrape pipeline failed: %s", exc)
        _scrape_state["status"] = "error"
    finally:
        _scrape_state["last_run"] = datetime.now(timezone.utc).isoformat()


@router.post("/run")
async def trigger_scrape(
    background_tasks: BackgroundTasks,
    source: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    if _scrape_state["status"] == "running":
        return {"status": "already_running", "message": "A scrape is already in progress."}

    background_tasks.add_task(_tracked_pipeline, source=source)
    return {
        "status": "started",
        "message": f"Scrape pipeline started for source={'all' if not source else source}",
    }


@router.get("/status")
async def scrape_status():
    return _scrape_state
