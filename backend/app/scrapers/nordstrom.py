"""
Nordstrom scraper — uses Playwright to navigate search results pages
and intercepts XHR product data, with DOM extraction as fallback.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import AsyncIterator, Optional
from urllib.parse import quote

from .base import BaseScraper, RawProduct
from ..config import settings

logger = logging.getLogger(__name__)

# Search queries targeting Deep Winter fabric preferences
NORDSTROM_QUERIES = [
    "silk dress women",
    "silk blouse women",
    "linen dress women",
    "silk skirt women",
    "linen pants women",
    "silk pants women",
    "structured cotton blouse women",
]


class NordstromScraper(BaseScraper):
    source = "nordstrom"

    def __init__(self, max_products: int = settings.max_products_per_run):
        super().__init__()
        self.max_products = max_products

    async def scrape(self) -> AsyncIterator[RawProduct]:
        page = await self._new_page()
        count = 0
        captured_products: list[dict] = []

        async def on_response(response):
            try:
                url = response.url
                ct = response.headers.get("content-type", "")
                if response.status == 200 and "json" in ct and (
                    "/api/search" in url
                    or "/sr?" in url
                    or "nordstrom.com/api" in url
                ):
                    data = await response.json()
                    products = (
                        data.get("products")
                        or data.get("results")
                        or data.get("items")
                        or []
                    )
                    if products:
                        captured_products.extend(products)
                        logger.info(
                            "Nordstrom intercepted %d products from %s",
                            len(products), url
                        )
            except Exception as exc:
                logger.debug("Nordstrom response parse error: %s", exc)

        page.on("response", on_response)

        for query in NORDSTROM_QUERIES:
            if count >= self.max_products:
                break

            captured_products.clear()
            url = f"https://www.nordstrom.com/sr?origin=keywordsearch&keyword={quote(query)}"
            logger.info("Nordstrom navigating: %s", url)

            try:
                await page.goto(url, wait_until="networkidle", timeout=60_000)
                await asyncio.sleep(3)
            except Exception as exc:
                logger.warning("Nordstrom navigation failed for '%s': %s", query, exc)
                continue

            # If XHR interception didn't capture anything, fall back to DOM
            items = captured_products if captured_products else await self._extract_from_dom(page)

            if not items:
                logger.warning("Nordstrom: no products found for query '%s'", query)
                continue

            for item in items:
                if count >= self.max_products:
                    break
                product = self._parse_listing(item)
                if product:
                    yield product
                    count += 1

            await self._delay()

        await page.close()

    async def _extract_from_dom(self, page) -> list[dict]:
        """Extract product data directly from the rendered Nordstrom DOM."""
        try:
            # Wait for product tiles to appear
            await page.wait_for_selector(
                '[data-element-id="product-results"], [class*="product-module"], article',
                timeout=15_000
            )

            products = await page.evaluate("""() => {
                const results = [];

                // Try multiple selector strategies Nordstrom uses
                const selectors = [
                    '[data-element-id="product-module"]',
                    '[class*="productModule"]',
                    'article[class*="product"]',
                    '[data-testid*="product"]',
                ];

                let tiles = [];
                for (const sel of selectors) {
                    tiles = document.querySelectorAll(sel);
                    if (tiles.length > 0) break;
                }

                tiles.forEach(tile => {
                    try {
                        const link = tile.querySelector('a[href*="/s/"]') || tile.querySelector('a');
                        const img = tile.querySelector('img');
                        const nameEl = tile.querySelector('[class*="title"], [class*="name"], [data-element-id*="title"]');
                        const brandEl = tile.querySelector('[class*="brand"], [data-element-id*="brand"]');
                        const priceEl = tile.querySelector('[class*="price"], [data-element-id*="price"]');

                        const href = link?.href || '';
                        const name = nameEl?.textContent?.trim() || link?.getAttribute('aria-label') || '';
                        const brand = brandEl?.textContent?.trim() || '';
                        const priceText = priceEl?.textContent?.trim() || '';
                        const imageUrl = img?.src || img?.getAttribute('data-src') || '';

                        // Extract product ID from URL
                        const idMatch = href.match(/\\/s\\/[^/]+\\/(\\d+)/);
                        const productId = idMatch ? idMatch[1] : href.split('/').pop();

                        if (name && href) {
                            results.push({
                                id: productId,
                                name,
                                brand,
                                priceText,
                                url: href,
                                imageUrl,
                            });
                        }
                    } catch (e) {}
                });

                return results;
            }""")

            logger.info("Nordstrom DOM extraction found %d products", len(products))
            return products
        except Exception as exc:
            logger.warning("Nordstrom DOM extraction failed: %s", exc)
            return []

    def _parse_listing(self, item: dict) -> Optional[RawProduct]:
        try:
            # Handle both API JSON and DOM-extracted dicts
            product_id = str(
                item.get("styleId")
                or item.get("productId")
                or item.get("id")
                or ""
            )
            if not product_id:
                return None

            name = (
                item.get("productTitle")
                or item.get("name")
                or ""
            ).strip()
            if not name:
                return None

            brand_name = (
                item.get("brandName")
                or item.get("brand", {}).get("name", "") if isinstance(item.get("brand"), dict) else item.get("brand", "")
                or ""
            ).strip()

            price = self._extract_price(item)
            if price is None or not (settings.price_min <= price <= settings.price_max):
                return None

            color_name = (
                item.get("colorDefaultName")
                or (item.get("color", {}).get("name", "") if isinstance(item.get("color"), dict) else "")
                or item.get("colorName", "")
                or ""
            )

            image_url = (
                item.get("imageUrl")
                or (item.get("media", {}).get("main", {}).get("src", "") if isinstance(item.get("media"), dict) else "")
                or item.get("heroImage", "")
                or ""
            )

            url = item.get("url") or item.get("productUrl") or f"https://www.nordstrom.com/s/product/{product_id}"
            if url and not url.startswith("http"):
                url = f"https://www.nordstrom.com{url}"

            return RawProduct(
                source="nordstrom",
                external_id=product_id,
                name=name,
                brand=brand_name,
                url=url,
                price=price,
                currency="USD",
                color_name=color_name,
                image_url=image_url,
                description="",
                fabric_raw="",
            )
        except Exception as exc:
            logger.debug("Nordstrom parse error: %s", exc)
            return None

    def _extract_price(self, item: dict) -> Optional[float]:
        # Handle DOM-extracted priceText like "$245.00" or "$120 – $245"
        price_text = item.get("priceText", "")
        if price_text:
            nums = re.findall(r'[\d,]+\.?\d*', price_text.replace(",", ""))
            if nums:
                try:
                    return float(nums[0])
                except ValueError:
                    pass

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
            content = await page.content()
            product.fabric_raw = self._extract_fabric(content)
            product.description = self._extract_description(content)

            if not product.fabric_raw:
                # Try clicking the Details accordion
                try:
                    btn = await page.query_selector('[data-test="accordion-details"], [aria-label*="details" i]')
                    if btn:
                        await btn.click()
                        await page.wait_for_timeout(1500)
                        product.fabric_raw = self._extract_fabric(await page.content())
                except Exception:
                    pass
        except Exception as exc:
            logger.debug("Nordstrom enrich failed for %s: %s", product.external_id, exc)
        finally:
            await page.close()
        return product

    def _extract_fabric(self, html: str) -> str:
        ld_match = re.search(r'<script type="application/ld\+json">(.*?)</script>', html, re.S)
        if ld_match:
            try:
                ld = json.loads(ld_match.group(1))
                if isinstance(ld, list):
                    ld = ld[0]
                desc = ld.get("description", "")
                m = re.search(r'(\d{1,3}%\s*\w[\w\s,/]+(?:,?\s*\d{1,3}%\s*\w[\w\s,/]+)*)', desc)
                if m:
                    return m.group(1).strip()
            except Exception:
                pass

        for pattern in [
            r'<li[^>]*>\s*(?:Fabric|Material|Composition|Content)[:\s]*([^<]{5,150})</li>',
            r'(?:Fabric|Material|Composition|Content)[:\s]+([^\n<.;]{5,150})',
        ]:
            m = re.search(pattern, html, re.I)
            if m:
                return m.group(1).strip()
        return ""

    def _extract_description(self, html: str) -> str:
        m = re.search(r'<meta name="description" content="([^"]{10,500})"', html, re.I)
        if m:
            return m.group(1).strip()
        return ""
