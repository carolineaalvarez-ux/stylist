from __future__ import annotations
from datetime import datetime
from typing import Optional
from uuid import UUID
from pydantic import BaseModel

from .product import ProductOut


class AlertOut(BaseModel):
    id: UUID
    product: ProductOut
    alert_type: str
    previous_price: Optional[float]
    current_price: Optional[float]
    message: Optional[str]
    is_read: bool
    created_at: datetime

    model_config = {"from_attributes": True}
