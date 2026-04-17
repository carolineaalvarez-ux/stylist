"""Base scraper class with shared Playwright plumbing."""
from __future__ import annotations

import asyncio
import logging
import random
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import AsyncIterator, Optional

from playwright.async_api import async_playwright, Browser, BrowserContext, Page

from ..config import settings

logger = logging.getLogger(__name__)


@dataclass
class RawProduct:
    source: str
    external_id: str
    name: str
    url: str
    price: float
    currency: str = "USD"
    brand: str = ""
    color_name: str = ""
    image_url: str = ""
    description: str = ""
    fabric_raw: str = ""
    available_sizes: list = field(default_factory=list)


class BaseScraper(ABC):
    source: str = ""

    def __init__(self):
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None

    # ------------------------------------------------------------------
    # Playwright lifecycle
    # ------------------------------------------------------------------

    async def __aenter__(self):
        self._pw = await async_playwright().start()
        self._browser = await self._pw.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )
        self._context = await self._browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 900},
            locale="en-US",
        )
        return self

    async def __aexit__(self, *_):
        if self._context:
            await self._context.close()
        if self._browser:
            await self._browser.close()
        await self._pw.stop()

    async def _new_page(self) -> Page:
        assert self._context, "Call __aenter__ first"
        page = await self._context.new_page()
        # Block only fonts — allow images so pages render normally (helps avoid bot detection)
        await page.route(
            "**/*.{woff,woff2,ttf,otf}",
            lambda route: route.abort(),
        )
        return page

    async def _delay(self):
        """Polite random delay between requests."""
        await asyncio.sleep(
            random.uniform(settings.scrape_delay_min, settings.scrape_delay_max)
        )

    # ------------------------------------------------------------------
    # Subclass interface
    # ------------------------------------------------------------------

    @abstractmethod
    async def scrape(self) -> AsyncIterator[RawProduct]:
        """Yield RawProduct instances."""
        ...
