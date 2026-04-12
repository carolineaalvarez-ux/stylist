from __future__ import annotations
from datetime import datetime
from typing import Optional
from uuid import UUID
from pydantic import BaseModel


class FeedbackIn(BaseModel):
    action: str   # "accepted" | "rejected" | "saved"
    note: Optional[str] = None


class FeedbackOut(BaseModel):
    id: UUID
    match_id: UUID
    action: str
    note: Optional[str]
    created_at: datetime

    model_config = {"from_attributes": True}
