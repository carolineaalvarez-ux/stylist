"""
Nordstrom scraper — uses the Apify Nordstrom Scraper Actor
(trudax~actor-nordstrom-scraper) instead of direct Playwright scraping.

Nordstrom runs Akamai Bot Manager which blocks all headless browsers from
cloud/datacenter IPs. Apify runs on residential proxies and handles this.

Requires APIFY_API_TOKEN in .env.
"""
from __future__ import annotations

import logging
from typing import AsyncIterator, Optional

import httpx

from .base import RawProduct
from ..config import settings

logger = logging.getLogger(__name__)

APIFY_ACTOR_ID = "trudax~actor-nordstrom-scraper"
APIFY_RUN_SYNC_URL = (
    f"https://api.apify.com/v2/acts/{APIFY_ACTOR_ID}"
    f"/run-sync-get-dataset-items"
)

NORDSTROM_QUERIES = [
    "silk blouse women",
    "linen dress women",
    "silk dress women",
    "structured cotton top women",
    "silk skirt women",
    "linen pants women",
    "silk pants women",
]


class NordstromScraper:
    source = "nordstrom"

    def __init__(self, max_products: int = settings.max_products_per_run):
        self.max_products = max_products
        self._client: Optional[httpx.AsyncClient] = None

    async def __aenter__(self):
        self._client = httpx.AsyncClient(timeout=300.0)  # Apify runs can take a few minutes
        return self

    async def __aexit__(self, *_):
        if self._client:
            await self._client.aclose()

    async def scrape(self) -> AsyncIterator[RawProduct]:
        if not settings.apify_api_token:
            logger.error("APIFY_API_TOKEN not set — Nordstrom scraping skipped")
            return

        count = 0
        per_query = max(10, self.max_products // len(NORDSTROM_QUERIES))

        for query in NORDSTROM_QUERIES:
            if count >= self.max_products:
                break

            items = await self._fetch_query(query, per_query)
            logger.info("Nordstrom/Apify: query='%s' returned %d items", query, len(items))

            for item in items:
                product = self._parse_item(item)
                if product:
                    yield product
                    count += 1
                    if count >= self.max_products:
                        break

    async def _fetch_query(self, query: str, max_items: int) -> list[dict]:
        payload = {
            "search": query,
            "country": "United States",
            "maxItems": max_items,
        }
        try:
            resp = await self._client.post(
                APIFY_RUN_SYNC_URL,
                params={"token": settings.apify_api_token},
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()
            # Apify returns a list of items directly from run-sync-get-dataset-items
            if isinstance(data, list):
                return data
            # Some responses wrap in an "items" key
            if isinstance(data, dict):
                return data.get("items", [])
            return []
        except httpx.HTTPStatusError as exc:
            logger.error(
                "Apify HTTP error for query='%s': %s %s",
                query, exc.response.status_code, exc.response.text[:200],
            )
        except Exception as exc:
            logger.error("Apify error for query='%s': %s", query, exc)
        return []

    def _parse_item(self, item: dict) -> Optional[RawProduct]:
        try:
            # Apify Nordstrom scraper field names
            product_id = str(
                item.get("id") or item.get("styleId") or item.get("productId") or ""
            )
            if not product_id:
                return None

            name = (
                item.get("title") or item.get("name") or item.get("productName") or ""
            ).strip()
            if not name:
                return None

            brand = (
                item.get("brand") or item.get("brandName") or ""
            ).strip()

            price = self._extract_price(item)
            if price is None or not (settings.price_min <= price <= settings.price_max):
                return None

            url = item.get("url") or item.get("productUrl") or ""
            if url and not url.startswith("http"):
                url = f"https://www.nordstrom.com{url}"
            if not url:
                return None

            color = (
                item.get("color") or item.get("colorName") or
                item.get("colorDefaultName") or ""
            )

            image_url = (
                item.get("image") or item.get("imageUrl") or
                item.get("thumbnailUrl") or ""
            )

            description = item.get("description") or ""
            fabric_raw = item.get("fabric") or item.get("material") or item.get("composition") or ""

            return RawProduct(
                source="nordstrom",
                external_id=product_id,
                name=name,
                brand=brand,
                url=url,
                price=price,
                currency="USD",
                color_name=color,
                image_url=image_url,
                description=description,
                fabric_raw=fabric_raw,
            )
        except Exception as exc:
            logger.debug("Failed to parse Apify item: %s | keys: %s", exc, list(item.keys()))
            return None

    def _extract_price(self, item: dict) -> Optional[float]:
        for key in ("price", "salePrice", "regularPrice", "currentPrice", "originalPrice"):
            val = item.get(key)
            if isinstance(val, (int, float)) and val > 0:
                return float(val)
            if isinstance(val, str):
                try:
                    return float(val.replace("$", "").replace(",", ""))
                except ValueError:
                    continue
            if isinstance(val, dict):
                for sub in ("min", "max", "amount", "value"):
                    v = val.get(sub)
                    if isinstance(v, (int, float)) and v > 0:
                        return float(v)
        return None

    async def enrich_product(self, product: RawProduct) -> RawProduct:
        # Apify already returns fabric/description in the main payload — nothing to enrich
        return product
