from sqlalchemy import Column, String, Float, Boolean, DateTime, Text, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import uuid
import enum
from sqlalchemy import Enum

from ..database import Base


class AlertType(str, enum.Enum):
    price_drop = "price_drop"
    restock = "restock"
    new_match = "new_match"


class Alert(Base):
    __tablename__ = "alerts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    product_id = Column(UUID(as_uuid=True), ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True)
    alert_type = Column(Enum(AlertType), nullable=False)

    previous_price = Column(Float)
    current_price = Column(Float)
    message = Column(Text)
    is_read = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    product = relationship("Product", lazy="joined")
