"""
Nordstrom scraper — navigates the Nordstrom search results page and
captures the product API responses the SPA fires, rather than calling
an internal endpoint directly (which returns no results or HTML).

Flow:
1. Navigate to https://www.nordstrom.com/sr?origin=keywordsearch&keyword=…
2. Register a response listener that captures any JSON response whose URL
   contains known Nordstrom search API path fragments
3. Wait for the page to finish loading (networkidle)
4. Parse products from captured API response, or fall back to extracting
   the embedded __NEXT_DATA__ / window state from the page HTML
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

NORDSTROM_SEARCH_URL = "https://www.nordstrom.com/sr"

# API path fragments that appear in Nordstrom's internal XHR requests
_API_FRAGMENTS = (
    "/api/search",
    "/api/2/search",
    "searchProducts",
    "nordstrom.com/sr",
    "api/products",
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


class NordstromScraper(BaseScraper):
    source = "nordstrom"

    def __init__(self, max_products: int = settings.max_products_per_run):
        super().__init__()
        self.max_products = max_products

    async def scrape(self) -> AsyncIterator[RawProduct]:
        count = 0

        for query in NORDSTROM_QUERIES:
            if count >= self.max_products:
                break

            offset = 0
            page_size = 48

            while count < self.max_products:
                items = await self._fetch_search_page(query, offset, page_size)

                if not items:
                    logger.warning(
                        "Nordstrom: no items for query='%s' offset=%d — stopping this query",
                        query, offset,
                    )
                    break

                for item in items:
                    product = self._parse_listing(item)
                    if product:
                        yield product
                        count += 1
                        if count >= self.max_products:
                            break

                if len(items) < page_size:
                    break  # last page

                offset += page_size
                await self._delay()

    # ------------------------------------------------------------------
    # Page navigation + response capture
    # ------------------------------------------------------------------

    async def _fetch_search_page(
        self, query: str, offset: int, page_size: int
    ) -> list[dict]:
        """
        Navigate to Nordstrom's search results page and return raw product dicts.

        Tries two strategies in order:
        1. Capture the XHR API response the SPA fires while loading
        2. Extract the embedded __NEXT_DATA__ JSON from the page HTML
        """
        page = await self._new_page()
        captured: list[dict] = []

        async def _on_response(response) -> None:
            url = response.url
            ct = response.headers.get("content-type", "")
            if "json" not in ct:
                return
            if not any(frag in url for frag in _API_FRAGMENTS):
                return
            try:
                data = await response.json()
                items = _extract_items_from_payload(data)
                if items:
                    captured.extend(items)
                    logger.debug(
                        "Nordstrom: captured %d items from XHR %s", len(items), url
                    )
            except Exception as exc:
                logger.debug("Nordstrom: could not parse XHR response from %s: %s", url, exc)

        page.on("response", _on_response)

        url = (
            f"{NORDSTROM_SEARCH_URL}"
            f"?origin=keywordsearch"
            f"&keyword={quote(query)}"
            f"&offset={offset}"
            f"&pageSize={page_size}"
            f"&priceCurrencyCode=USD"
        )

        try:
            await page.goto(url, wait_until="networkidle", timeout=45_000)
            # Brief extra wait in case the SPA fires requests after networkidle
            await page.wait_for_timeout(2_000)
        except Exception as exc:
            logger.error("Nordstrom navigation error query='%s': %s", query, exc)
            await page.close()
            return []

        # Strategy 1: captured XHR responses
        if captured:
            await page.close()
            return captured

        # Strategy 2: __NEXT_DATA__ embedded JSON
        logger.debug(
            "Nordstrom: no XHR capture for query='%s', trying __NEXT_DATA__", query
        )
        items = await self._extract_next_data(page)
        await page.close()

        if not items:
            logger.warning(
                "Nordstrom: both XHR and __NEXT_DATA__ extraction failed for query='%s'",
                query,
            )
        return items

    async def _extract_next_data(self, page) -> list[dict]:
        """Extract products from Next.js embedded page data."""
        try:
            html = await page.content()

            # __NEXT_DATA__ is a JSON blob inside a <script> tag
            m = re.search(
                r'<script id="__NEXT_DATA__"[^>]*>\s*(\{.*?\})\s*</script>',
                html,
                re.S,
            )
            if not m:
                # Some Nordstrom pages use window.__INITIAL_STATE__
                m = re.search(
                    r'window\.__INITIAL_STATE__\s*=\s*(\{.*?\});\s*(?:window|</script)',
                    html,
                    re.S,
                )
            if not m:
                return []

            data = json.loads(m.group(1))
            items = _extract_items_from_payload(data)
            logger.debug("Nordstrom __NEXT_DATA__: found %d items", len(items))
            return items

        except Exception as exc:
            logger.debug("Nordstrom __NEXT_DATA__ parse error: %s", exc)
            return []

    # ------------------------------------------------------------------
    # Listing parser
    # ------------------------------------------------------------------

    def _parse_listing(self, item: dict) -> Optional[RawProduct]:
        try:
            product_id = str(
                item.get("styleId")
                or item.get("productId")
                or item.get("id")
                or item.get("styleNumber")
                or ""
            )
            if not product_id:
                return None

            name = (
                item.get("productTitle")
                or item.get("name")
                or item.get("title")
                or ""
            ).strip()
            if not name:
                return None

            brand_name = (
                item.get("brandName")
                or (item.get("brand") or {}).get("name", "")
                or item.get("brandTitle", "")
                or ""
            ).strip()

            price = self._extract_price(item)
            if price is None or not (settings.price_min <= price <= settings.price_max):
                return None

            color_name = (
                item.get("colorDefaultName")
                or (item.get("color") or {}).get("name", "")
                or item.get("colorName", "")
                or ""
            )

            # Image
            media = item.get("media") or {}
            hero = item.get("colorDefaultImageUrl") or ""
            image_url = (
                (media.get("main") or {}).get("src", "")
                or (media.get("hero") or {}).get("src", "")
                or hero
                or item.get("imageUrl", "")
                or item.get("heroImage", "")
                or ""
            )

            # Product URL
            slug = (
                item.get("productUrl")
                or item.get("url")
                or item.get("pdpUrl")
                or f"/s/product/{product_id}"
            )
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
            logger.debug("Failed to parse Nordstrom listing: %s | item keys: %s", exc, list(item.keys()))
            return None

    def _extract_price(self, item: dict) -> Optional[float]:
        for key in (
            "currentMaxPrice", "currentMinPrice", "regularPrice",
            "salePrice", "price", "priceRange",
        ):
            val = item.get(key)
            if isinstance(val, (int, float)):
                return float(val)
            if isinstance(val, dict):
                for sub in ("min", "max", "amount", "value", "regular", "sale"):
                    v = val.get(sub)
                    if isinstance(v, (int, float)):
                        return float(v)
                    if isinstance(v, dict):
                        inner = v.get("amount") or v.get("value")
                        if isinstance(inner, (int, float)):
                            return float(inner)
            if isinstance(val, str):
                try:
                    return float(val.replace("$", "").replace(",", ""))
                except ValueError:
                    continue
        return None

    async def enrich_product(self, product: RawProduct) -> RawProduct:
        """Fetch the Nordstrom detail page to extract fabric composition."""
        page = await self._new_page()
        try:
            await page.goto(product.url, wait_until="networkidle", timeout=45_000)

            content = await page.content()
            product.fabric_raw = self._extract_fabric(content)
            product.description = self._extract_description(content)

            # Nordstrom puts fabric in an accordion — try clicking it open
            if not product.fabric_raw:
                for selector in (
                    '[data-test="accordion-details"]',
                    '[aria-label="Details"]',
                    'button:has-text("Details")',
                    'button:has-text("Fabric & Care")',
                ):
                    try:
                        btn = await page.query_selector(selector)
                        if btn:
                            await btn.click()
                            await page.wait_for_timeout(1_000)
                            content2 = await page.content()
                            fabric2 = self._extract_fabric(content2)
                            if fabric2:
                                product.fabric_raw = fabric2
                                break
                    except Exception:
                        continue

        except Exception as exc:
            logger.debug("Nordstrom enrich failed for %s: %s", product.external_id, exc)
        finally:
            await page.close()
        return product

    # ------------------------------------------------------------------
    # HTML parsing helpers
    # ------------------------------------------------------------------

    def _extract_fabric(self, html: str) -> str:
        # JSON-LD first
        ld_match = re.search(
            r'<script type="application/ld\+json">(.*?)</script>', html, re.S
        )
        if ld_match:
            try:
                ld = json.loads(ld_match.group(1))
                if isinstance(ld, list):
                    ld = ld[0]
                fabric = self._fabric_from_text(ld.get("description", ""))
                if fabric:
                    return fabric
            except Exception:
                pass

        patterns = [
            r'<li[^>]*>\s*(?:Fabric|Material|Composition|Content)[:\s]*([^<]{5,150})</li>',
            r'(?:Fabric|Material|Composition|Content)[:\s]+([^\n<.;]{5,150})',
            r'(\d{1,3}%\s*\w[\w\s,/]+(?:,\s*\d{1,3}%\s*\w[\w\s,/]+)*)',
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
        return m.group(1).strip() if m else ""


# ---------------------------------------------------------------------------
# Payload extraction — handles multiple Nordstrom API response shapes
# ---------------------------------------------------------------------------

def _extract_items_from_payload(data: dict) -> list[dict]:
    """
    Nordstrom's internal API has varied shapes across versions. Try all known
    paths and return the first non-empty list of product dicts found.
    """
    if not isinstance(data, dict):
        return []

    candidates = [
        # Direct top-level keys
        data.get("products"),
        data.get("results"),
        data.get("items"),
        # Nested under search key
        (data.get("search") or {}).get("products"),
        (data.get("search") or {}).get("results"),
        # pageProps from __NEXT_DATA__
        (data.get("props") or {}).get("pageProps", {}).get("products"),
        (data.get("props") or {}).get("pageProps", {}).get("searchResults", {}).get("products"),
        # dehydratedState path (react-query)
        _pluck_react_query(data, "products"),
    ]

    for candidate in candidates:
        if isinstance(candidate, list) and candidate:
            logger.debug(
                "Nordstrom payload: found %d products via known path", len(candidate)
            )
            return candidate

    # Last resort: walk top-level values for a non-empty list of dicts
    # that look like products (have a price or productId)
    for val in data.values():
        if isinstance(val, list) and val and isinstance(val[0], dict):
            if any(
                k in val[0]
                for k in ("styleId", "productId", "productTitle", "brandName", "price")
            ):
                logger.debug(
                    "Nordstrom payload: found %d products via dict-walk", len(val)
                )
                return val

    return []


def _pluck_react_query(data: dict, key: str) -> Optional[list]:
    """Walk react-query dehydratedState to find a list stored under a query key."""
    try:
        queries = (
            (data.get("dehydratedState") or {})
            .get("queries", [])
        )
        for q in queries:
            state_data = (q.get("state") or {}).get("data", {})
            if isinstance(state_data, dict):
                result = state_data.get(key)
                if isinstance(result, list) and result:
                    return result
    except Exception:
        pass
    return None
