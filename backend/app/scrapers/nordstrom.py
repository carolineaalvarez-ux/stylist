"""
Nordstrom scraper — uses Nordstrom's internal GraphQL/REST API
that powers their website, plus BeautifulSoup for detail pages.
"""
from __future__ import annotations

import json
import logging
import re
from typing import AsyncIterator, Optional
from urllib.parse import quote

from .base import BaseScraper, RawProduct
from ..config import settings

logger = logging.getLogger(__name__)

# Nordstrom search endpoint used by their SPA
NORDSTROM_SEARCH_API = "https://www.nordstrom.com/api/search"

# Category keywords aligned to Deep Winter style preferences
NORDSTROM_QUERIES = [
    "silk blouse women",
    "linen dress women",
    "silk dress women",
    "structured cotton top women",
    "silk skirt women",
    "linen pants women",
    "silk pants women",
]

NORDSTROM_DEPT = "Women"


class NordstromScraper(BaseScraper):
    source = "nordstrom"

    def __init__(self, max_products: int = settings.max_products_per_run):
        super().__init__()
        self.max_products = max_products

    async def scrape(self) -> AsyncIterator[RawProduct]:
        page = await self._new_page()
        count = 0

        for query in NORDSTROM_QUERIES:
            if count >= self.max_products:
                break

            offset = 0
            page_size = 48

            while count < self.max_products:
                # Nordstrom uses a JSON API at /api/search
                params = (
                    f"?query={quote(query)}"
                    f"&offset={offset}"
                    f"&pageSize={page_size}"
                    f"&department={NORDSTROM_DEPT}"
                    f"&priceMin={int(settings.price_min)}"
                    f"&priceMax={int(settings.price_max)}"
                    f"&country=US"
                    f"&currency=USD"
                    f"&lang=en-US"
                )
                url = NORDSTROM_SEARCH_API + params

                try:
                    response = await page.goto(url, wait_until="domcontentloaded", timeout=30_000)
                    if not response or response.status != 200:
                        logger.warning("Nordstrom API %s for query '%s'", response and response.status, query)
                        break

                    body = await response.body()
                    data = json.loads(body)
                except Exception as exc:
                    logger.error("Nordstrom fetch error query=%s offset=%s: %s", query, offset, exc)
                    break

                items = (
                    data.get("products")
                    or data.get("results")
                    or data.get("items")
                    or []
                )
                if not items:
                    break

                for item in items:
                    product = self._parse_listing(item)
                    if product:
                        yield product
                        count += 1
                        if count >= self.max_products:
                            break

                if len(items) < page_size:
                    break

                offset += page_size
                await self._delay()

        await page.close()

    def _parse_listing(self, item: dict) -> Optional[RawProduct]:
        try:
            # Nordstrom API uses styleId or productId
            product_id = str(item.get("styleId") or item.get("productId") or item.get("id", ""))
            if not product_id:
                return None

            name = (item.get("productTitle") or item.get("name") or "").strip()
            brand_name = (
                item.get("brandName")
                or item.get("brand", {}).get("name", "")
                or ""
            ).strip()

            # Price — Nordstrom nests it differently across API versions
            price = self._extract_price(item)
            if price is None or not (settings.price_min <= price <= settings.price_max):
                return None

            color_name = (
                item.get("colorDefaultName")
                or item.get("color", {}).get("name", "")
                or item.get("colorName", "")
                or ""
            )

            # Image
            media = item.get("media", {})
            image_url = (
                media.get("main", {}).get("src", "")
                or item.get("imageUrl", "")
                or item.get("heroImage", "")
                or ""
            )

            # URL
            slug = item.get("productUrl") or item.get("url") or f"/s/product/{product_id}"
            if not slug.startswith("http"):
                slug = f"https://www.nordstrom.com{slug}"

            return RawProduct(
                source="nordstrom",
                external_id=product_id,
                name=name,
                brand=brand_name,
                url=slug,
                price=price,
                currency="USD",
                color_name=color_name,
                image_url=image_url,
                description="",
                fabric_raw="",
            )
        except Exception as exc:
            logger.debug("Failed to parse Nordstrom listing: %s", exc)
            return None

    def _extract_price(self, item: dict) -> Optional[float]:
        """Handle Nordstrom's varied price structures."""
        for key in ("currentMaxPrice", "currentMinPrice", "regularPrice", "salePrice", "price"):
            val = item.get(key)
            if isinstance(val, (int, float)):
                return float(val)
            if isinstance(val, dict):
                for sub in ("min", "max", "amount", "value"):
                    if isinstance(val.get(sub), (int, float)):
                        return float(val[sub])
            if isinstance(val, str):
                try:
                    return float(val.replace("$", "").replace(",", ""))
                except ValueError:
                    continue
        return None

    async def enrich_product(self, product: RawProduct) -> RawProduct:
        """Fetch the Nordstrom detail page for fabric info."""
        page = await self._new_page()
        try:
            await page.goto(product.url, wait_until="networkidle", timeout=45_000)

            # Nordstrom renders product details as JSON-LD + hidden elements
            content = await page.content()
            product.fabric_raw = self._extract_fabric(content)
            product.description = self._extract_description(content)

            # Also try clicking the "Details" tab if it exists
            try:
                details_btn = await page.query_selector('[data-test="accordion-details"]')
                if details_btn:
                    await details_btn.click()
                    await page.wait_for_timeout(1000)
                    content2 = await page.content()
                    fabric2 = self._extract_fabric(content2)
                    if fabric2:
                        product.fabric_raw = fabric2
            except Exception:
                pass

        except Exception as exc:
            logger.debug("Nordstrom enrich failed for %s: %s", product.external_id, exc)
        finally:
            await page.close()
        return product

    # ------------------------------------------------------------------
    # Parsing helpers
    # ------------------------------------------------------------------

    def _extract_fabric(self, html: str) -> str:
        # JSON-LD first
        ld_match = re.search(r'<script type="application/ld\+json">(.*?)</script>', html, re.S)
        if ld_match:
            try:
                ld = json.loads(ld_match.group(1))
                if isinstance(ld, list):
                    ld = ld[0]
                description = ld.get("description", "")
                fabric = self._fabric_from_text(description)
                if fabric:
                    return fabric
            except Exception:
                pass

        # Nordstrom puts fabric in a detail list
        patterns = [
            r'<li[^>]*>\s*(?:Fabric|Material|Composition|Content)[:\s]*([^<]{5,150})</li>',
            r'(?:Fabric|Material|Composition|Content)[:\s]+([^\n<.;]{5,150})',
        ]
        for pattern in patterns:
            m = re.search(pattern, html, re.I)
            if m:
                return m.group(1).strip()
        return ""

    def _extract_description(self, html: str) -> str:
        m = re.search(r'<meta name="description" content="([^"]{10,500})"', html, re.I)
        if m:
            return m.group(1).strip()
        return ""

    @staticmethod
    def _fabric_from_text(text: str) -> str:
        m = re.search(r'(\d{1,3}%\s*\w[\w\s,/]+(?:\d{1,3}%\s*\w[\w\s,/]+)*)', text)
        if m:
            return m.group(1).strip()
        return ""
