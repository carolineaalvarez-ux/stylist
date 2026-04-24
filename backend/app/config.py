from pydantic_settings import BaseSettings
from typing import List


class Settings(BaseSettings):
    # Database
    database_url: str = "postgresql+asyncpg://stylist:stylist@localhost:5432/stylist"
    database_url_sync: str = "postgresql://stylist:stylist@localhost:5432/stylist"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # API Keys
    google_vision_api_key: str = ""
    anthropic_api_key: str = ""
    apify_api_token: str = ""

    # App
    app_env: str = "development"
    secret_key: str = "change-me-in-production"
    cors_origins: List[str] = ["http://localhost:5173", "http://localhost:3000"]

    # Scraping
    scrape_delay_min: float = 1.5
    scrape_delay_max: float = 4.0
    max_products_per_run: int = 200

    # Color matching
    color_match_threshold: int = 60   # minimum raw Delta-E score to proceed
    delta_e_good: float = 15.0        # ΔE < 15 → strong match
    delta_e_ok: float = 25.0          # ΔE < 25 → acceptable

    # --------------------------------------------------------------------------
    # Tier 1 — Always works (40 color pts solid, 35 pts print)
    # --------------------------------------------------------------------------
    tier1_palette: List[str] = [
        "#000000",  # True Black
        "#FFFFFF",  # Bright White
        "#006B3C",  # Emerald
        "#CC0000",  # True Red (blue-based)
        "#4169E1",  # Royal Blue
        "#800020",  # Burgundy
        "#000080",  # Deep Navy
    ]

    # --------------------------------------------------------------------------
    # Tier 2 — Strong options (30 pts solid, 25 pts print)
    # --------------------------------------------------------------------------
    tier2_palette: List[str] = [
        "#580F41",  # Deep Plum
        "#FF0090",  # Fuchsia
        "#0047AB",  # Cobalt Blue
        "#008080",  # Teal
        "#36454F",  # Cool Charcoal
        "#3C1F1F",  # Mahogany
        "#FFB6C1",  # Icy Pink
        "#301934",  # Deep Purple
    ]

    # Combined palette for Delta-E matching
    deep_winter_palette: List[str] = [
        "#000000", "#FFFFFF", "#006B3C", "#CC0000", "#4169E1",
        "#800020", "#000080", "#580F41", "#FF0090", "#0047AB",
        "#36454F", "#008080", "#3C1F1F", "#FFB6C1", "#301934",
    ]

    # --------------------------------------------------------------------------
    # Hard-avoid color keywords → auto-reject (0 pts, item removed from results)
    # Source: client_profile.json hard_avoid + shopping_rules.md
    # --------------------------------------------------------------------------
    hard_avoid_keywords: List[str] = [
        "camel", "tan", "beige", "ivory", "cream", "ecru",
        "mustard", "warm yellow", "golden yellow",
        "peach", "coral", "orange",
        "terracotta", "rust", "cognac", "caramel",
        "sand", "wheat", "toffee", "honey",
        "warm brown", "golden brown", "caramel brown",
        "warm olive", "warm floral", "sunset",
    ]

    # Tier 3 borderline keywords (proceed with caution, 15 pts)
    tier3_keywords: List[str] = [
        "espresso", "mocha", "chocolate", "mahogany",
        "cool grey", "cool gray", "cool olive", "icy",
    ]

    # --------------------------------------------------------------------------
    # Fabric auto-reject triggers
    # --------------------------------------------------------------------------
    auto_reject_fabrics: List[str] = ["polyester", "acrylic"]
    preferred_fabrics: List[str] = ["silk", "linen", "cotton"]
    excluded_fabrics: List[str] = ["polyester", "acrylic"]

    # Fake-silk red-flag phrases (from shopping_rules.md)
    fake_silk_phrases: List[str] = [
        "silky smooth", "silky feel", "silky finish",
        "satin finish", "wrinkle-resistant",
    ]

    # Print detection keywords
    print_keywords: List[str] = [
        "floral", "print", "printed", "stripe", "striped",
        "pattern", "patterned", "check", "plaid", "abstract",
        "geometric", "paisley", "leopard", "animal", "polka dot",
    ]

    # --------------------------------------------------------------------------
    # Budget ranges (USD)  — from client_profile.json
    # --------------------------------------------------------------------------
    budget_tops_min: float = 100.0
    budget_tops_max: float = 300.0
    budget_dresses_min: float = 150.0
    budget_dresses_max: float = 400.0
    budget_bottoms_min: float = 150.0
    budget_bottoms_max: float = 400.0
    budget_blazers_min: float = 200.0
    budget_blazers_max: float = 400.0
    budget_swimwear_min: float = 80.0
    budget_swimwear_max: float = 200.0

    # Backwards-compat alias used by existing filtering logic
    price_min: float = 80.0
    price_max: float = 400.0

    # --------------------------------------------------------------------------
    # Brand tiers — from client_profile.json brands section
    # Style score: tier1=20, tier2=15, unknown=10, avoid=5
    # --------------------------------------------------------------------------
    brand_tier1: List[str] = [
        # Existing client favorites
        "sézane", "sezane", "maje", "zimmermann", "doen",
        "petite mendigote", "rag & bone", "cinq à sept",
        # Workwear specific (highest priority)
        "equipment", "vince", "toteme", "theory",
        "veronica beard", "frame", "scanlan theodore", "cami nyc",
    ]

    brand_tier2: List[str] = [
        # French / European approved
        "rouje", "musier paris", "ba&sh", "bash", "soeur paris",
        "sessùn", "sessun", "isabel marant étoile", "isabel marant etoile",
        # Independent unique
        "alemais", "cara cara", "faithfull the brand", "fanm mon",
        "rhode", "significant other",
        # Investment
        "ulla johnson", "staud", "brock collection", "paloma wool",
        "westman atelier",
    ]

    brand_avoid: List[str] = ["reformation"]

    # Combined list used by existing _is_priority_brand helper
    priority_brands: List[str] = [
        "sézane", "sezane", "equipment", "rouje", "zimmermann",
        "doen", "maje", "vince", "theory", "toteme",
        "alemais", "cara cara", "ba&sh", "bash",
        "veronica beard", "frame", "faithfull the brand",
        "petite mendigote", "rag & bone", "cinq à sept",
        "musier paris", "soeur paris", "sessùn", "sessun",
        "isabel marant étoile", "fanm mon", "rhode",
        "significant other", "ulla johnson", "staud",
        "brock collection", "paloma wool", "cami nyc",
        "scanlan theodore",
    ]

    # --------------------------------------------------------------------------
    # Scoring thresholds (from shopping_rules.md)
    # --------------------------------------------------------------------------
    score_recommend_high: int = 80    # 80-100: recommend immediately
    score_recommend_notes: int = 60   # 60-79: recommend with notes
    score_flag_review: int = 40       # 40-59: flag for client review
    # 0-39: reject

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
