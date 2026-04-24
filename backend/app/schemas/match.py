from __future__ import annotations
from datetime import datetime
from typing import Optional, List
from uuid import UUID
from pydantic import BaseModel

from .product import ProductOut


class MatchOut(BaseModel):
    id: UUID
    product: ProductOut
    color_score: int
    fabric_score: int
    style_score: Optional[int]
    florida_score: Optional[int]
    overall_score: int
    is_borderline_color: bool
    auto_rejected: bool
    auto_reject_reason: Optional[str]
    claude_style_analysis: Optional[str]
    claude_color_reasoning: Optional[str]
    claude_flags: Optional[list]
    is_new: bool
    matched_at: datetime

    model_config = {"from_attributes": True}


class MatchListOut(BaseModel):
    items: List[MatchOut]
    total: int
    page: int
    page_size: int
