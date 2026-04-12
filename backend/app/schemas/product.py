from __future__ import annotations
from datetime import datetime
from typing import Optional, List
from uuid import UUID
from pydantic import BaseModel


class ProductOut(BaseModel):
    id: UUID
    source: str
    external_id: str
    name: str
    brand: Optional[str]
    url: str
    image_url: Optional[str]
    price: float
    currency: str
    color_name: Optional[str]
    dominant_colors: Optional[list]
    color_match_score: Optional[int]
    closest_palette_color: Optional[str]
    fabric_raw: Optional[str]
    fabric_parsed: Optional[list]
    fabric_score: Optional[int]
    has_excluded_fabric: bool
    description: Optional[str]
    available_sizes: Optional[list]
    in_stock: bool
    is_priority_brand: bool
    first_seen_at: datetime
    last_seen_at: datetime

    model_config = {"from_attributes": True}


class ProductListOut(BaseModel):
    items: List[ProductOut]
    total: int
    page: int
    page_size: int
