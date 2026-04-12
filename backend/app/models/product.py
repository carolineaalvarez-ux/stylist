from sqlalchemy import Column, String, Float, Boolean, DateTime, Text, Integer, JSON, Enum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
import uuid
import enum

from ..database import Base


class ScraperSource(str, enum.Enum):
    asos = "asos"
    nordstrom = "nordstrom"


class Product(Base):
    __tablename__ = "products"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source = Column(Enum(ScraperSource), nullable=False, index=True)
    external_id = Column(String(128), nullable=False, index=True)  # retailer's product ID

    # Core product info
    name = Column(String(512), nullable=False)
    brand = Column(String(256), index=True)
    url = Column(Text, nullable=False)
    image_url = Column(Text)
    price = Column(Float, nullable=False)
    currency = Column(String(8), default="USD")

    # Color
    color_name = Column(String(256))               # as listed by retailer
    dominant_colors = Column(JSON)                 # list of {hex, percentage} from Vision API
    color_match_score = Column(Integer)            # 0–100
    closest_palette_color = Column(String(16))    # hex of best match

    # Fabric
    fabric_raw = Column(Text)                      # raw description from retailer
    fabric_parsed = Column(JSON)                   # [{fiber, percentage}]
    fabric_score = Column(Integer)                 # 0–100
    has_excluded_fabric = Column(Boolean, default=False)

    # Metadata
    description = Column(Text)
    available_sizes = Column(JSON)
    in_stock = Column(Boolean, default=True)
    is_priority_brand = Column(Boolean, default=False)

    # Timestamps
    first_seen_at = Column(DateTime(timezone=True), server_default=func.now())
    last_seen_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    scraped_at = Column(DateTime(timezone=True), server_default=func.now())
