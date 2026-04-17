"""
ASOS scraper — uses Playwright to browse category pages and intercepts
the product search API responses the browser makes naturally.
This avoids bot detection since the browser handles cookies/headers.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import AsyncIterator, Optional

from .base import BaseScraper, RawProduct
from ..config import settings

logger = logging.getLogger(__name__)

# ASOS women's category pages with price filter baked in
ASOS_CATEGORY_URLS = [
    f"https://www.asos.com/us/women/dresses/cat/?cid=8799&currentpricerange={int(settings.price_min)}-{int(settings.price_max)}",
    f"https://www.asos.com/us/women/tops/cat/?cid=4169&currentpricerange={int(settings.price_min)}-{int(settings.price_max)}",
    f"https://www.asos.com/us/women/blouses-and-shirts/cat/?cid=6461&currentpricerange={int(settings.price_min)}-{int(settings.price_max)}",
    f"https://www.asos.com/us/women/trousers/cat/?cid=2638&currentpricerange={int(settings.price_min)}-{int(settings.price_max)}",
    f"https://www.asos.com/us/women/skirts/cat/?cid=2641&currentpricerange={int(settings.price_min)}-{int(settings.price_max)}",
    f"https://www.asos.com/us/women/coats-and-jackets/cat/?cid=2637&currentpricerange={int(settings.price_min)}-{int(settings.price_max)}",
]


class AsosScraper(BaseScraper):
    source = "asos"

    def __init__(self, max_products: int = settings.max_products_per_run):
        super().__init__()
        self.max_products = max_products

    async def scrape(self) -> AsyncIterator[RawProduct]:
        page = await self._new_page()
        count = 0
        captured_products: list[dict] = []

        # Intercept API responses the browser makes when loading pages
        async def on_response(response):
            try:
                if (
                    "/api/product/search/v2/" in response.url
                    and response.status == 200
                ):
                    data = await response.json()
                    products = data.get("products", [])
                    captured_products.extend(products)
                    logger.info("ASOS intercepted %d products from %s", len(products), response.url)
            except Exception as exc:
                logger.debug("ASOS response parse error: %s", exc)

        page.on("response", on_response)

        for category_url in ASOS_CATEGORY_URLS:
            if count >= self.max_products:
                break

            captured_products.clear()
            logger.info("ASOS navigating to %s", category_url)

            try:
                await page.goto(category_url, wait_until="networkidle", timeout=60_000)
                # Give extra time for lazy-loaded API responses
                await asyncio.sleep(3)
            except Exception as exc:
                logger.warning("ASOS navigation failed for %s: %s", category_url, exc)
                continue

            if not captured_products:
                # Fallback: try extracting from __NEXT_DATA__ JSON blob
                captured_products.extend(await self._extract_next_data(page))

            if not captured_products:
                logger.warning("ASOS: no products captured for %s", category_url)
                continue

            for item in captured_products:
                if count >= self.max_products:
                    break
                product = self._parse_listing(item)
                if product:
                    yield product
                    count += 1

            await self._delay()

        await page.close()

    async def _extract_next_data(self, page) -> list[dict]:
        """Fallback: extract products from Next.js __NEXT_DATA__ script tag."""
        try:
            next_data_str = await page.evaluate(
                "() => document.getElementById('__NEXT_DATA__')?.textContent || ''"
            )
            if not next_data_str:
                return []
            data = json.loads(next_data_str)
            # Navigate the Next.js page props to find products
            page_props = data.get("props", {}).get("pageProps", {})
            products = (
                page_props.get("products")
                or page_props.get("initialProducts")
                or []
            )
            if not products:
                # Try deeper nesting
                redux_state = page_props.get("reduxState", {})
                listing = redux_state.get("listing", {})
                products = listing.get("products", [])
            logger.info("ASOS __NEXT_DATA__ fallback found %d products", len(products))
            return products
        except Exception as exc:
            logger.debug("ASOS __NEXT_DATA__ extraction failed: %s", exc)
            return []

    def _parse_listing(self, item: dict) -> Optional[RawProduct]:
        try:
            product_id = str(item.get("id", ""))
            if not product_id:
                return None

            name = item.get("name", "").strip()
            if not name:
                return None

            brand_name = item.get("brandName", "ASOS").strip()

            # Price
            price_data = item.get("price", {})
            current = price_data.get("current", {})
            price_value = current.get("value") or current.get("text", "0")
            try:
                price = float(str(price_value).replace("$", "").replace(",", ""))
            except (ValueError, TypeError):
                return None

            if not (settings.price_min <= price <= settings.price_max):
                return None

            colour = item.get("colour", "")

            # Image
            image_url = item.get("imageUrl", "")
            if isinstance(image_url, list):
                image_url = image_url[0] if image_url else ""
            if image_url and not image_url.startswith("http"):
                image_url = f"https://images.asos-media.com/products/{image_url}"

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
                fabric_raw="",
            )
        except Exception as exc:
            logger.debug("ASOS parse error: %s", exc)
            return None

    async def enrich_product(self, product: RawProduct) -> RawProduct:
        """Fetch the product detail page to extract fabric content."""
        page = await self._new_page()
        try:
            await page.goto(product.url, wait_until="domcontentloaded", timeout=30_000)
            content = await page.content()
            product.fabric_raw = self._extract_fabric_from_html(content)
            product.description = self._extract_description_from_html(content)
        except Exception as exc:
            logger.debug("ASOS enrich failed for %s: %s", product.external_id, exc)
        finally:
            await page.close()
        return product

    def _extract_fabric_from_html(self, html: str) -> str:
        json_match = re.search(
            r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>',
            html, re.S
        )
        if json_match:
            try:
                data = json.loads(json_match.group(1))
                page_props = data.get("props", {}).get("pageProps", {})
                product_data = page_props.get("product", {})
                for variant in product_data.get("variants", []):
                    fabric = variant.get("fabric", "") or variant.get("composition", "")
                    if fabric:
                        return fabric.strip()
                desc = str(product_data.get("description", ""))
                m = re.search(
                    r'(?:composition|fabric|material|content)[:\s]+([^<\n.]{5,120})',
                    desc, re.I
                )
                if m:
                    return m.group(1).strip()
            except Exception:
                pass

        for pattern in [
            r'<li[^>]*>\s*(?:Fabric|Composition|Material|Content)[:\s]*([^<]{5,120})</li>',
            r'(?:Fabric|Composition|Material|Content)[:\s]+([^\n<]{5,120})',
        ]:
            m = re.search(pattern, html, re.I)
            if m:
                return m.group(1).strip()
        return ""

    def _extract_description_from_html(self, html: str) -> str:
        m = re.search(r'<meta name="description" content="([^"]{10,500})"', html, re.I)
        if m:
            return m.group(1).strip()
        return ""

    @staticmethod
    def _slugify(text: str) -> str:
        return re.sub(r'[^a-z0-9]+', '-', text.lower()).strip('-')
