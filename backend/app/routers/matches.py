"""Endpoints for curated matches surfaced to the dashboard."""
from __future__ import annotations

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func, desc
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models import Match
from ..schemas import MatchOut, MatchListOut

router = APIRouter(prefix="/matches", tags=["matches"])


@router.get("/", response_model=MatchListOut)
async def list_matches(
    page: int = Query(1, ge=1),
    page_size: int = Query(24, ge=1, le=100),
    min_score: int = Query(70, ge=0, le=100),
    brand: Optional[str] = None,
    color: Optional[str] = None,
    fabric: Optional[str] = None,
    price_min: Optional[float] = None,
    price_max: Optional[float] = None,
    is_new: Optional[bool] = None,
    db: AsyncSession = Depends(get_db),
):
    query = (
        select(Match)
        .where(Match.overall_score >= min_score)
        .order_by(desc(Match.matched_at))
    )

    if is_new is not None:
        query = query.where(Match.is_new == is_new)

    # Join-based filters on the related Product
    from ..models import Product
    query = query.join(Product, Match.product_id == Product.id)

    if brand:
        query = query.where(Product.brand.ilike(f"%{brand}%"))
    if price_min is not None:
        query = query.where(Product.price >= price_min)
    if price_max is not None:
        query = query.where(Product.price <= price_max)
    if color:
        query = query.where(Product.color_name.ilike(f"%{color}%"))

    # Count
    count_q = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_q)).scalar_one()

    # Paginate
    offset = (page - 1) * page_size
    rows = (await db.execute(query.offset(offset).limit(page_size))).scalars().all()

    return MatchListOut(items=rows, total=total, page=page, page_size=page_size)


@router.get("/{match_id}", response_model=MatchOut)
async def get_match(match_id: UUID, db: AsyncSession = Depends(get_db)):
    result = await db.get(Match, match_id)
    if not result:
        raise HTTPException(404, "Match not found")
    return result


@router.patch("/{match_id}/read")
async def mark_match_read(match_id: UUID, db: AsyncSession = Depends(get_db)):
    match = await db.get(Match, match_id)
    if not match:
        raise HTTPException(404, "Match not found")
    match.is_new = False
    await db.commit()
    return {"status": "ok"}
