"""
APScheduler daily job: scrape → analyze → persist → alert.

Schedule: runs every day at 06:00 UTC.
"""
from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..analysis.claude_analyzer import ClaudeAnalyzer
from ..analysis.color_matcher import ColorMatcher
from ..analysis.fabric_parser import FabricParser
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
        product.last_seen_at = None  # triggers server_default onupdate
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
    # 3. Fabric parsing
    # ------------------------------------------------------------------
    fabric_result = fabric_parser.parse(product.fabric_raw or "")
    product.fabric_parsed = [
        {"fiber": f.fiber, "percentage": f.percentage} for f in fabric_result.fibers
    ]
    product.fabric_score = fabric_result.score
    product.has_excluded_fabric = fabric_result.has_excluded

    # Hard exclude: skip if fabric is disqualifying
    if fabric_result.has_excluded:
        logger.debug("Skipping %s — excluded fabric: %s", product.name, fabric_result.exclusion_reason)
        return

    # ------------------------------------------------------------------
    # 4. Color matching
    # ------------------------------------------------------------------
    if product.image_url:
        color_result = await color_matcher.analyze_image(product.image_url)
    elif product.color_name:
        # Use Vision API hex if available, else skip
        color_result = color_matcher.analyze_hex("#000000")  # placeholder
        color_result.score = 0  # will be overridden by Claude analysis
    else:
        return

    product.dominant_colors = color_result.dominant_colors
    product.color_match_score = color_result.score
    product.closest_palette_color = color_result.closest_palette_hex

    # Skip if color score too low
    if color_result.score < settings.color_match_threshold:
        logger.debug(
            "Skipping %s — color score %d < threshold %d",
            product.name, color_result.score, settings.color_match_threshold
        )
        return

    # ------------------------------------------------------------------
    # 5. Create/update Match record
    # ------------------------------------------------------------------
    is_borderline = settings.delta_e_good <= color_result.delta_e_best <= settings.delta_e_ok
    overall_score = _compute_overall_score(color_result.score, fabric_result.score, product.is_priority_brand)

    existing_match = (
        await db.execute(select(Match).where(Match.product_id == product.id))
    ).scalar_one_or_none()

    if existing_match:
        match = existing_match
        match.color_score = color_result.score
        match.fabric_score = fabric_result.score
        match.overall_score = overall_score
        match.is_borderline_color = is_borderline
    else:
        match = Match(
            product_id=product.id,
            color_score=color_result.score,
            fabric_score=fabric_result.score,
            overall_score=overall_score,
            is_borderline_color=is_borderline,
            is_new=True,
        )
        db.add(match)

    # ------------------------------------------------------------------
    # 6. Claude analysis (async, non-blocking)
    # ------------------------------------------------------------------
    claude_result = await claude.analyze_product(
        name=product.name,
        brand=product.brand or "",
        color_name=product.color_name or "",
        fabric_raw=product.fabric_raw or "",
        description=product.description or "",
        color_score=color_result.score,
        closest_palette_color=color_result.closest_palette_name,
        delta_e=color_result.delta_e_best,
        is_borderline=is_borderline,
    )
    if claude_result:
        match.claude_style_analysis = claude_result.style_fit
        match.claude_color_reasoning = claude_result.color_reasoning
        match.claude_flags = claude_result.flags

    # ------------------------------------------------------------------
    # 7. Price drop alert
    # ------------------------------------------------------------------
    if old_price and raw.price < old_price * 0.95:  # ≥5% drop
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
        "Processed %s '%s' — color=%d fabric=%d overall=%d",
        product.source, product.name, color_result.score, fabric_result.score, overall_score
    )


def _compute_overall_score(color_score: int, fabric_score: int, is_priority: bool) -> int:
    """Weighted composite: 60% color, 30% fabric, 10% brand priority."""
    score = color_score * 0.60 + fabric_score * 0.30
    if is_priority:
        score += 10
    return min(100, round(score))


def _is_priority_brand(brand: str) -> bool:
    if not brand:
        return False
    return brand.lower() in settings.priority_brands
