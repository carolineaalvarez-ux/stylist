"""
ASOS scraper — targets women's new-arrivals and sale sections,
filtered to the Deep Winter price range ($100–$400).

ASOS exposes a JSON API used by its own SPA; we use that rather than
parsing raw HTML, which makes the scraper far more reliable.
"""
from __future__ import annotations

import json
import logging
import re
from typing import AsyncIterator, Optional
from urllib.parse import urlencode

from .base import BaseScraper, RawProduct
from ..config import settings

logger = logging.getLogger(__name__)

# ASOS category IDs for women's clothing
ASOS_CATEGORY_IDS = [
    "4169",   # Dresses
    "2623",   # Tops
    "6461",   # Blouses & shirts
    "2638",   # Trousers & leggings
    "2641",   # Skirts
    "2637",   # Coats & jackets
    "2631",   # Jumpers & cardigans
]

ASOS_API_BASE = "https://www.asos.com/api/product/search/v2/categories/{category_id}"


class AsosScraper(BaseScraper):
    source = "asos"

    def __init__(self, max_products: int = settings.max_products_per_run):
        super().__init__()
        self.max_products = max_products

    async def scrape(self) -> AsyncIterator[RawProduct]:
        page = await self._new_page()
        count = 0

        for category_id in ASOS_CATEGORY_IDS:
            if count >= self.max_products:
                break

            offset = 0
            page_size = 48

            while count < self.max_products:
                params = {
                    "channel": "com-en",
                    "country": "US",
                    "currency": "USD",
                    "lang": "en-US",
                    "limit": page_size,
                    "offset": offset,
                    "rowlength": 4,
                    "store": "US",
                    "priceTo": int(settings.price_max),
                    "priceFrom": int(settings.price_min),
                    "q": "",
                }
                url = ASOS_API_BASE.format(category_id=category_id) + "?" + urlencode(params)

                try:
                    response = await page.goto(url, wait_until="domcontentloaded", timeout=30_000)
                    if not response or response.status != 200:
                        logger.warning("ASOS API returned %s for category %s", response and response.status, category_id)
                        break

                    body = await response.body()
                    data = json.loads(body)
                except Exception as exc:
                    logger.error("ASOS fetch error category=%s offset=%s: %s", category_id, offset, exc)
                    break

                products = data.get("products", [])
                if not products:
                    break

                for item in products:
                    product = self._parse_listing(item)
                    if product:
                        yield product
                        count += 1
                        if count >= self.max_products:
                            break

                if len(products) < page_size:
                    break

                offset += page_size
                await self._delay()

        await page.close()

        # Second pass: enrich top candidates with full product detail pages
        # (fabric content lives on the detail page, not listing API)

    def _parse_listing(self, item: dict) -> Optional[RawProduct]:
        try:
            product_id = str(item["id"])
            name = item.get("name", "").strip()
            brand_name = item.get("brandName", "ASOS").strip()

            price_data = item.get("price", {})
            current = price_data.get("current", {})
            price_value = current.get("value") or current.get("text", "0")
            try:
                price = float(str(price_value).replace("$", "").replace(",", ""))
            except ValueError:
                return None

            if not (settings.price_min <= price <= settings.price_max):
                return None

            # Colour
            colour = item.get("colour", "")

            # Image
            images = item.get("imageUrl") or ""
            if isinstance(images, list):
                images = images[0] if images else ""
            image_url = f"https://images.asos-media.com/products/{images}" if images and not images.startswith("http") else images

            url = f"https://www.asos.com/us/{self._slugify(name)}/prd/{product_id}"

            return RawProduct(
                source="asos",
                external_id=product_id,
                name=name,
                brand=brand_name,
                url=url,
                price=price,
                currency="USD",
                color_name=colour,
                image_url=image_url,
                description="",
                fabric_raw="",  # enriched in detail scrape
            )
        except Exception as exc:
            logger.debug("Failed to parse ASOS listing item: %s", exc)
            return None

    async def enrich_product(self, product: RawProduct) -> RawProduct:
        """Fetch the product detail page to extract fabric content."""
        page = await self._new_page()
        try:
            await page.goto(product.url, wait_until="domcontentloaded", timeout=30_000)

            # ASOS renders product info in a JSON script tag
            content = await page.content()
            fabric_raw = self._extract_fabric_from_html(content)
            description = self._extract_description_from_html(content)

            product.fabric_raw = fabric_raw
            product.description = description
        except Exception as exc:
            logger.debug("ASOS enrich failed for %s: %s", product.external_id, exc)
        finally:
            await page.close()
        return product

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _extract_fabric_from_html(self, html: str) -> str:
        """
        Pull fabric/composition data out of the ASOS product page HTML.
        ASOS puts it in a <li> under a "Fabric" or "Composition" heading,
        and also in the __NEXT_DATA__ JSON blob.
        """
        # Try __NEXT_DATA__ JSON blob first (most reliable)
        json_match = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', html, re.S)
        if json_match:
            try:
                data = json.loads(json_match.group(1))
                # Navigate the deeply nested structure
                page_props = data.get("props", {}).get("pageProps", {})
                product_data = page_props.get("product", {}) or page_props.get("data", {}).get("product", {})
                about = product_data.get("variants", [{}])
                for variant in about:
                    fabric = variant.get("fabric", "") or variant.get("composition", "")
                    if fabric:
                        return fabric.strip()
                # Try productDescription field
                desc = product_data.get("description", "") or str(product_data)
                fabric_match = re.search(
                    r'(?:composition|fabric|material|content)[:\s]+([^<\n.]{5,120})',
                    desc, re.I
                )
                if fabric_match:
                    return fabric_match.group(1).strip()
            except Exception:
                pass

        # Fallback: parse raw HTML
        patterns = [
            r'<li[^>]*>\s*(?:Fabric|Composition|Material|Content)[:\s]*([^<]{5,120})</li>',
            r'(?:Fabric|Composition|Material|Content)[:\s]+([^\n<]{5,120})',
        ]
        for pattern in patterns:
            m = re.search(pattern, html, re.I)
            if m:
                return m.group(1).strip()

        return ""

    def _extract_description_from_html(self, html: str) -> str:
        # Try meta description first
        m = re.search(r'<meta name="description" content="([^"]{10,500})"', html, re.I)
        if m:
            return m.group(1).strip()

        # Try og:description
        m = re.search(r'<meta property="og:description" content="([^"]{10,500})"', html, re.I)
        if m:
            return m.group(1).strip()

        return ""

    @staticmethod
    def _slugify(text: str) -> str:
        return re.sub(r'[^a-z0-9]+', '-', text.lower()).strip('-')
