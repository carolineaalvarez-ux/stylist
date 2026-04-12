"""Read-only product endpoints."""
from __future__ import annotations

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models import Product
from ..schemas import ProductOut, ProductListOut

router = APIRouter(prefix="/products", tags=["products"])


@router.get("/", response_model=ProductListOut)
async def list_products(
    page: int = Query(1, ge=1),
    page_size: int = Query(48, ge=1, le=100),
    source: Optional[str] = None,
    brand: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    query = select(Product).order_by(Product.scraped_at.desc())
    if source:
        query = query.where(Product.source == source)
    if brand:
        query = query.where(Product.brand.ilike(f"%{brand}%"))

    count_q = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_q)).scalar_one()

    offset = (page - 1) * page_size
    rows = (await db.execute(query.offset(offset).limit(page_size))).scalars().all()
    return ProductListOut(items=rows, total=total, page=page, page_size=page_size)


@router.get("/{product_id}", response_model=ProductOut)
async def get_product(product_id: UUID, db: AsyncSession = Depends(get_db)):
    product = await db.get(Product, product_id)
    if not product:
        raise HTTPException(404, "Product not found")
    return product
