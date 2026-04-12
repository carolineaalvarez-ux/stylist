from pydantic_settings import BaseSettings
from typing import List
import json


class Settings(BaseSettings):
    # Database
    database_url: str = "postgresql+asyncpg://stylist:stylist@localhost:5432/stylist"
    database_url_sync: str = "postgresql://stylist:stylist@localhost:5432/stylist"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # API Keys
    google_vision_api_key: str = ""
    anthropic_api_key: str = ""

    # App
    app_env: str = "development"
    secret_key: str = "change-me-in-production"
    cors_origins: List[str] = ["http://localhost:5173", "http://localhost:3000"]

    # Scraping
    scrape_delay_min: float = 1.5   # seconds between requests
    scrape_delay_max: float = 4.0
    max_products_per_run: int = 200

    # Color matching
    color_match_threshold: int = 70   # minimum score to surface an item
    delta_e_good: float = 15.0        # ΔE < 15 → strong match
    delta_e_ok: float = 25.0          # ΔE < 25 → acceptable

    # Deep Winter color palette (hex)
    deep_winter_palette: List[str] = [
        "#000000",  # Black
        "#FFFFFF",  # Bright White
        "#006B3C",  # Emerald
        "#4169E1",  # Royal Blue
        "#CC0000",  # True Red
        "#800020",  # Burgundy
        "#580F41",  # Deep Plum
        "#FF0090",  # Fuchsia
        "#0047AB",  # Cobalt
        "#36454F",  # Charcoal
        "#000080",  # Navy
        "#008080",  # Teal
        "#3C1F1F",  # Mahogany
    ]

    # Colors to exclude (described by name — used in NLP fabric/color parser)
    excluded_color_keywords: List[str] = [
        "camel", "tan", "beige", "ivory", "cream",
        "mustard", "warm yellow",
        "peach", "coral", "orange",
        "terracotta",
        "warm olive",
    ]

    # Fabric preferences
    preferred_fabrics: List[str] = ["silk", "linen", "cotton"]
    excluded_fabrics: List[str] = ["polyester", "acrylic"]

    # Price range
    price_min: float = 100.0
    price_max: float = 400.0

    # Priority brands
    priority_brands: List[str] = [
        "sézane", "sezane", "equipment", "rouje", "zimmermann",
        "doen", "maje", "vince", "theory", "toteme",
        "alemais", "cara cara", "ba&sh", "bash",
    ]

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
