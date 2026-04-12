"""Price drop and restock alert endpoints."""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models import Alert
from ..schemas import AlertOut

router = APIRouter(prefix="/alerts", tags=["alerts"])


@router.get("/", response_model=list[AlertOut])
async def list_alerts(
    unread_only: bool = False,
    db: AsyncSession = Depends(get_db),
):
    query = select(Alert).order_by(desc(Alert.created_at))
    if unread_only:
        query = query.where(Alert.is_read == False)
    rows = (await db.execute(query)).scalars().all()
    return rows


@router.patch("/{alert_id}/read")
async def mark_alert_read(alert_id: UUID, db: AsyncSession = Depends(get_db)):
    alert = await db.get(Alert, alert_id)
    if not alert:
        raise HTTPException(404, "Alert not found")
    alert.is_read = True
    await db.commit()
    return {"status": "ok"}


@router.patch("/read-all")
async def mark_all_read(db: AsyncSession = Depends(get_db)):
    from sqlalchemy import update
    await db.execute(update(Alert).where(Alert.is_read == False).values(is_read=True))
    await db.commit()
    return {"status": "ok"}
