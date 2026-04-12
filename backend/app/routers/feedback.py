"""User accept/reject/save feedback on matches."""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models import Match, UserFeedback
from ..models.user_feedback import FeedbackAction
from ..schemas import FeedbackIn, FeedbackOut

router = APIRouter(prefix="/feedback", tags=["feedback"])

VALID_ACTIONS = {a.value for a in FeedbackAction}


@router.post("/{match_id}", response_model=FeedbackOut, status_code=201)
async def submit_feedback(
    match_id: UUID,
    body: FeedbackIn,
    db: AsyncSession = Depends(get_db),
):
    if body.action not in VALID_ACTIONS:
        raise HTTPException(400, f"action must be one of: {', '.join(VALID_ACTIONS)}")

    match = await db.get(Match, match_id)
    if not match:
        raise HTTPException(404, "Match not found")

    feedback = UserFeedback(
        match_id=match_id,
        action=body.action,
        note=body.note,
    )
    db.add(feedback)

    # Mark as read when user acts on it
    match.is_new = False

    await db.commit()
    await db.refresh(feedback)
    return feedback


@router.get("/wishlist", response_model=list[FeedbackOut])
async def get_wishlist(db: AsyncSession = Depends(get_db)):
    """Return all accepted/saved items."""
    query = select(UserFeedback).where(
        UserFeedback.action.in_(["accepted", "saved"])
    ).order_by(UserFeedback.created_at.desc())
    rows = (await db.execute(query)).scalars().all()
    return rows
