from sqlalchemy import Column, Float, Boolean, DateTime, Text, Integer, ForeignKey, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import uuid

from ..database import Base


class Match(Base):
    """
    Items that passed the color + fabric filter and are surfaced to the user.
    """
    __tablename__ = "matches"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    product_id = Column(UUID(as_uuid=True), ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True)

    # Scoring
    color_score = Column(Integer, nullable=False)          # 0–100 from Delta-E
    fabric_score = Column(Integer, nullable=False)         # 0–100
    overall_score = Column(Integer, nullable=False)        # weighted composite
    is_borderline_color = Column(Boolean, default=False)   # ΔE in gray zone

    # Claude analysis
    claude_style_analysis = Column(Text)       # "Why this works for Deep Winter…"
    claude_color_reasoning = Column(Text)      # color-specific explanation
    claude_flags = Column(JSON)                # list of flag strings

    # State
    is_new = Column(Boolean, default=True)
    matched_at = Column(DateTime(timezone=True), server_default=func.now())

    product = relationship("Product", lazy="joined")
