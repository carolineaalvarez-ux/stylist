from sqlalchemy import Column, String, DateTime, Text, ForeignKey, Boolean
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import uuid
import enum
from sqlalchemy import Enum

from ..database import Base


class FeedbackAction(str, enum.Enum):
    accepted = "accepted"     # added to wishlist
    rejected = "rejected"     # dismissed
    saved = "saved"           # saved for later


class UserFeedback(Base):
    __tablename__ = "user_feedback"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    match_id = Column(UUID(as_uuid=True), ForeignKey("matches.id", ondelete="CASCADE"), nullable=False, index=True)
    action = Column(Enum(FeedbackAction), nullable=False)
    note = Column(Text)                              # optional user note
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    match = relationship("Match", lazy="joined")
