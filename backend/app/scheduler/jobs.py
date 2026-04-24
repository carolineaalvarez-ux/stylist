"""
APScheduler daily job: scrape → analyze → persist → alert.

Schedule: runs every day at 06:00 UTC.

Scoring system (total 0–100, from shopping_rules.md):
  Color  : 0–40  (tier-based: tier1 solid=40, tier1 print=35,
                               tier2 solid=30, tier2 print=25,
                               tier3=15, hard_avoid=0 → auto-reject)
  Fabric : 0–30  (silk 19mm+=30, silk any=25, linen/cotton=20,
                   silk blend=15, cotton blend=10, polyester=0 → auto-reject)
  Style  : 0–20  (brand tier1=20, tier2=15, unknown=10, avoid=5)
  Florida: 0–10  (silk/linen=10, cotton=8, blend=6, heavy=0)

Thresholds:
  80–100 → recommend immediately
  60–79  → recommend with notes
  40–59  → flag for client review
  0–39   → reject (not surfaced unless auto_rejected flag is stored for analysis)
"""
from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..analysis.claude_analyzer import ClaudeAnalyzer
from ..analysis.color_matcher import ColorMatcher
from ..analysis.fabric_parser import FabricParser, FabricParseResult
from ..config import settings
from ..database import AsyncSessionLocal
from ..models import Alert, Match, Product
from ..models.alert import AlertType
from ..models.product import ScraperSource
from ..scrapers.asos import AsosScraper
from ..scrapers.nordstrom import NordstromScraper

logger = logging.getLogger(__name__)


async def run_scrape_pipeline(source: Optional[str] = None):
    """
    Full scrape → analyze → store pipeline.
    Called by APScheduler daily and by the manual trigger endpoint.
    """
    logger.info("Starting scrape pipeline (source=%s)", source or "all")

    fabric_parser = FabricParser()
    color_matcher = ColorMatcher()
    claude = ClaudeAnalyzer()

    scrapers = []
    if source in (None, "asos"):
        scrapers.append(AsosScraper())
    if source in (None, "nordstrom"):
        scrapers.append(NordstromScraper())

    async with AsyncSessionLocal() as db:
        for scraper_cls in scrapers:
            async with scraper_cls as scraper:
                async for raw in scraper.scrape():
                    try:
                        await _process_product(
                            raw=raw,
                            db=db,
                            scraper=scraper,
                            fabric_parser=fabric_parser,
                            color_matcher=color_matcher,
                            claude=claude,
                        )
                        await db.commit()
                    except Exception as exc:
                        logger.error("Error processing %s/%s: %s", raw.source, raw.external_id, exc)
                        await db.rollback()

    logger.info("Scrape pipeline complete")


async def _process_product(
    raw,
    db: AsyncSession,
    scraper,
    fabric_parser: FabricParser,
    color_matcher: ColorMatcher,
    claude: ClaudeAnalyzer,
):
    # ------------------------------------------------------------------
    # 1. Upsert product record
    # ------------------------------------------------------------------
    existing = (
        await db.execute(
            select(Product).where(
                Product.source == raw.source,
                Product.external_id == raw.external_id,
            )
        )
    ).scalar_one_or_none()

    is_new_product = existing is None

    if existing:
        product = existing
        old_price = product.price
        product.price = raw.price
        product.in_stock = True
        product.last_seen_at = None   # triggers server_default onupdate
    else:
        product = Product(
            source=raw.source,
            external_id=raw.external_id,
            name=raw.name,
            brand=raw.brand,
            url=raw.url,
            image_url=raw.image_url,
            price=raw.price,
            currency=raw.currency,
            color_name=raw.color_name,
            description=raw.description,
            fabric_raw=raw.fabric_raw,
            is_priority_brand=_is_priority_brand(raw.brand),
        )
        db.add(product)
        old_price = None

    # ------------------------------------------------------------------
    # 2. Enrich with detail page (fabric) if missing
    # ------------------------------------------------------------------
    if not product.fabric_raw:
        enriched = await scraper.enrich_product(raw)
        product.fabric_raw = enriched.fabric_raw
        product.description = enriched.description or product.description

    # ------------------------------------------------------------------
    # 3. Fabric parsing + auto-reject check
    # ------------------------------------------------------------------
    fabric_result = fabric_parser.parse(product.fabric_raw or "")
    product.fabric_parsed = [
        {"fiber": f.fiber, "percentage": f.percentage} for f in fabric_result.fibers
    ]
    product.fabric_score = fabric_result.score
    product.has_excluded_fabric = fabric_result.has_excluded

    fabric_auto_reject, fabric_reject_reason = _check_fabric_auto_reject(fabric_result, product.fabric_raw or "")
    if fabric_auto_reject:
        logger.debug("Skipping %s — fabric auto-reject: %s", product.name, fabric_reject_reason)
        return

    # ------------------------------------------------------------------
    # 4. Color matching + tier classification
    # ------------------------------------------------------------------
    if product.image_url:
        color_result = await color_matcher.analyze_image(
            product.image_url, color_name=product.color_name or ""
        )
    elif product.color_name:
        hex_color = _color_name_to_hex(product.color_name)
        if hex_color:
            color_result = color_matcher.analyze_hex(hex_color, color_name=product.color_name)
        else:
            logger.debug("Skipping %s — no image and unrecognised color '%s'", product.name, product.color_name)
            return
    else:
        return

    product.dominant_colors = color_result.dominant_colors
    product.color_match_score = color_result.score
    product.closest_palette_color = color_result.closest_palette_hex
    product.color_tier = color_result.color_tier

    # ------------------------------------------------------------------
    # 5. Compute 4-component score
    # ------------------------------------------------------------------
    is_print = _detect_print(product.name, product.description or "")
    color_auto_reject = color_result.color_tier == "hard_avoid"

    color_pts = _compute_color_points(color_result.color_tier, is_print)
    fabric_pts = _compute_fabric_points(fabric_result)
    style_pts = _compute_style_points(product.brand or "")
    florida_pts = _compute_florida_points(fabric_result, product.color_name or "")
    overall = color_pts + fabric_pts + style_pts + florida_pts

    auto_rejected = color_auto_reject
    auto_reject_reason: Optional[str] = None
    if color_auto_reject:
        auto_reject_reason = (
            f"Hard-avoid color: '{product.color_name or 'unknown'}' "
            f"(tier={color_result.color_tier}, score={color_result.score})"
        )

    # Skip creating a match for auto-rejected or very low scoring items
    if auto_rejected or overall < settings.score_flag_review:
        logger.debug(
            "Skipping match for %s — overall=%d auto_rejected=%s",
            product.name, overall, auto_rejected,
        )
        return

    is_borderline = settings.delta_e_good <= color_result.delta_e_best <= settings.delta_e_ok

    # ------------------------------------------------------------------
    # 6. Create/update Match record
    # ------------------------------------------------------------------
    existing_match = (
        await db.execute(select(Match).where(Match.product_id == product.id))
    ).scalar_one_or_none()

    if existing_match:
        match = existing_match
        match.color_score = color_pts
        match.fabric_score = fabric_pts
        match.style_score = style_pts
        match.florida_score = florida_pts
        match.overall_score = overall
        match.is_borderline_color = is_borderline
        match.auto_rejected = auto_rejected
        match.auto_reject_reason = auto_reject_reason
    else:
        match = Match(
            product_id=product.id,
            color_score=color_pts,
            fabric_score=fabric_pts,
            style_score=style_pts,
            florida_score=florida_pts,
            overall_score=overall,
            is_borderline_color=is_borderline,
            auto_rejected=auto_rejected,
            auto_reject_reason=auto_reject_reason,
            is_new=True,
        )
        db.add(match)

    # ------------------------------------------------------------------
    # 7. Claude analysis
    # ------------------------------------------------------------------
    claude_result = await claude.analyze_product(
        name=product.name,
        brand=product.brand or "",
        color_name=product.color_name or "",
        color_tier=color_result.color_tier,
        fabric_raw=product.fabric_raw or "",
        description=product.description or "",
        color_score=color_pts,
        fabric_score=fabric_pts,
        style_score=style_pts,
        florida_score=florida_pts,
        overall_score=overall,
        closest_palette_color=color_result.closest_palette_name,
        delta_e=color_result.delta_e_best,
        is_borderline=is_borderline,
    )
    if claude_result:
        match.claude_style_analysis = claude_result.style_fit
        match.claude_color_reasoning = claude_result.color_reasoning
        match.claude_flags = claude_result.flags

    # ------------------------------------------------------------------
    # 8. Price drop alert
    # ------------------------------------------------------------------
    if old_price and raw.price < old_price * 0.95:
        alert = Alert(
            product_id=product.id,
            alert_type=AlertType.price_drop,
            previous_price=old_price,
            current_price=raw.price,
            message=(
                f"{product.name} dropped from ${old_price:.0f} to ${raw.price:.0f} "
                f"({100*(old_price - raw.price)/old_price:.0f}% off)"
            ),
        )
        db.add(alert)

    logger.info(
        "Processed %s '%s' — color=%d/%d fabric=%d style=%d florida=%d overall=%d",
        product.source, product.name,
        color_pts, 40, fabric_pts, style_pts, florida_pts, overall,
    )


# ---------------------------------------------------------------------------
# Scoring functions — each returns points in its own range
# ---------------------------------------------------------------------------

def _compute_color_points(color_tier: str, is_print: bool) -> int:
    """
    Color component: 0–40 points.

    Tier 1 solid=40, Tier 1 print=35
    Tier 2 solid=30, Tier 2 print=25
    Tier 3=15
    hard_avoid=0 (items auto-rejected before reaching this)
    unknown=10
    """
    if color_tier == "tier1":
        return 35 if is_print else 40
    if color_tier == "tier2":
        return 25 if is_print else 30
    if color_tier == "tier3":
        return 15
    if color_tier == "hard_avoid":
        return 0
    return 10  # unknown


def _compute_fabric_points(fabric_result: FabricParseResult) -> int:
    """
    Fabric component: 0–30 points.

    100% silk 19mm+: 30 (we can't detect momme from fabric text reliably,
                          so we give full credit for any 100% silk and flag for review)
    100% silk any:   25
    Linen ≥95%:      20
    Cotton ≥95%:     20
    Silk blend (silk ≥50%): 15
    Cotton blend:    10
    All others:       5
    Excluded:         0 (should have been caught by auto-reject, but guard here too)
    """
    if fabric_result.has_excluded:
        return 0

    fibers = {f.fiber: f.percentage for f in fabric_result.fibers}
    silk_pct = fibers.get("silk", 0.0)
    linen_pct = fibers.get("linen", 0.0)
    cotton_pct = fibers.get("cotton", 0.0)

    if silk_pct >= 95:
        return 30
    if silk_pct >= 70:
        return 25
    if linen_pct >= 95 or cotton_pct >= 95:
        return 20
    if silk_pct >= 50:
        return 15
    if cotton_pct >= 50 or linen_pct >= 50:
        return 10
    if fabric_result.has_preferred:
        return 8
    # Unknown composition — give benefit of the doubt but flag
    return 5


def _compute_style_points(brand: str) -> int:
    """
    Style component: 0–20 points based on brand DNA match.

    Tier 1 brands (existing favorites + workwear specialists): 20
    Tier 2 brands (approved new discoveries):                  15
    Avoid list:                                                  5
    Unknown brand from approved retailers:                      10
    """
    if not brand:
        return 10
    b = brand.lower().strip()
    for t1 in settings.brand_tier1:
        if t1 in b or b in t1:
            return 20
    for t2 in settings.brand_tier2:
        if t2 in b or b in t2:
            return 15
    for avoid in settings.brand_avoid:
        if avoid in b or b in avoid:
            return 5
    return 10


def _compute_florida_points(fabric_result: FabricParseResult, color_name: str) -> int:
    """
    Florida suitability: 0–10 points.

    Silk or linen (breathable, elevated): 10
    Cotton (breathable):                    8
    Blend with preferred fiber:             6
    Unknown / mixed:                        4
    Heavy / excluded fabric:                0
    """
    if fabric_result.has_excluded:
        return 0

    fibers = {f.fiber: f.percentage for f in fabric_result.fibers}
    silk_pct = fibers.get("silk", 0.0)
    linen_pct = fibers.get("linen", 0.0)
    cotton_pct = fibers.get("cotton", 0.0)

    if silk_pct >= 70 or linen_pct >= 70:
        return 10
    if cotton_pct >= 70:
        return 8
    if silk_pct + linen_pct + cotton_pct >= 50:
        return 6
    if fabric_result.has_preferred:
        return 4
    return 2


def _check_fabric_auto_reject(fabric_result: FabricParseResult, raw_text: str) -> tuple[bool, str]:
    """Return (should_reject, reason) for fabric-based auto-reject triggers."""
    if fabric_result.has_excluded:
        return True, fabric_result.exclusion_reason

    # Detect "satin" without confirmed silk (fake silk red flag)
    import re as _re
    raw_lower = raw_text.lower()
    if _re.search(r'\bsatin\b', raw_lower) and "silk" not in raw_lower:
        return True, "Listed as 'satin' without confirmed silk content"

    # Detect fake-silk phrases
    for phrase in settings.fake_silk_phrases:
        if phrase in raw_lower and "silk" not in raw_lower:
            return True, f"Fake-silk indicator: '{phrase}' without actual silk content"

    return False, ""


def _detect_print(name: str, description: str) -> bool:
    """Return True if the product appears to be a print rather than a solid."""
    text = (name + " " + description).lower()
    return any(kw in text for kw in settings.print_keywords)


def _is_priority_brand(brand: str) -> bool:
    if not brand:
        return False
    return brand.lower() in settings.priority_brands


# ---------------------------------------------------------------------------
# Color name → hex lookup for products without images
# ---------------------------------------------------------------------------
_COLOR_NAME_HEX: dict[str, str] = {
    # Tier 1 — always works
    "black": "#000000",
    "white": "#FFFFFF",
    "bright white": "#FFFFFF",
    "true white": "#FFFFFF",
    "navy": "#000080",
    "navy blue": "#000080",
    "deep navy": "#000080",
    "emerald": "#006B3C",
    "emerald green": "#006B3C",
    "green": "#006B3C",
    "red": "#CC0000",
    "true red": "#CC0000",
    "crimson": "#CC0000",
    "ruby": "#CC0000",
    "burgundy": "#800020",
    "wine": "#800020",
    "bordeaux": "#800020",
    "wine red": "#800020",
    "blue": "#4169E1",
    "royal blue": "#4169E1",
    "cornflower blue": "#4169E1",
    "periwinkle": "#4169E1",
    # Tier 2 — strong options
    "plum": "#580F41",
    "deep plum": "#580F41",
    "purple": "#580F41",
    "fuchsia": "#FF0090",
    "magenta": "#FF0090",
    "hot pink": "#FF0090",
    "cobalt": "#0047AB",
    "cobalt blue": "#0047AB",
    "teal": "#008080",
    "charcoal": "#36454F",
    "charcoal grey": "#36454F",
    "grey": "#36454F",
    "gray": "#36454F",
    "dark grey": "#36454F",
    "mahogany": "#3C1F1F",
    "chocolate": "#3C1F1F",
    "icy pink": "#FFB6C1",
    "blush": "#FFB6C1",
    "pink": "#FFB6C1",
    "deep purple": "#301934",
    # Warm tones — kept so they score low and trigger hard_avoid classification
    "camel": "#C19A6B",
    "tan": "#D2B48C",
    "beige": "#F5F5DC",
    "ivory": "#FFFFF0",
    "cream": "#FFFDD0",
    "off white": "#FAF0E6",
    "ecru": "#FAF0E6",
    "mustard": "#FFDB58",
    "yellow": "#FFD700",
    "golden yellow": "#FFD700",
    "warm yellow": "#FFD700",
    "orange": "#FFA500",
    "coral": "#FF6B6B",
    "peach": "#FFCBA4",
    "terracotta": "#CB6B4E",
    "rust": "#B7410E",
    "cognac": "#9A463D",
    "caramel": "#C68642",
    "warm brown": "#A0522D",
    "golden brown": "#A0522D",
}


def _color_name_to_hex(color_name: str) -> str:
    """Return best-guess hex for a color name string, or empty string if unknown."""
    key = color_name.strip().lower()
    if key in _COLOR_NAME_HEX:
        return _COLOR_NAME_HEX[key]
    for name, hex_val in _COLOR_NAME_HEX.items():
        if name in key or key in name:
            return hex_val
    return ""
