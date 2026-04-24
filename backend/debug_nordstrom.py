"""
Run this inside the backend container to see what Nordstrom actually returns:

    docker compose exec backend python debug_nordstrom.py
"""
import asyncio
from playwright.async_api import async_playwright

URL = "https://www.nordstrom.com/sr?origin=keywordsearch&keyword=silk+blouse+women"


async def main():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 900},
            locale="en-US",
        )
        page = await context.new_page()

        json_responses = []

        async def on_response(response):
            ct = response.headers.get("content-type", "")
            if "json" in ct:
                try:
                    body = await response.json()
                    json_responses.append((response.url, body))
                    print(f"[XHR JSON] {response.url[:120]}")
                except Exception:
                    pass

        page.on("response", on_response)

        print(f"Navigating to: {URL}")
        await page.goto(URL, wait_until="networkidle", timeout=45_000)
        await page.wait_for_timeout(2_000)

        title = await page.title()
        html = await page.content()

        print(f"\nPage title: {title}")
        print(f"HTML length: {len(html)} chars")
        print(f"\n--- First 1000 chars of HTML ---")
        print(html[:1000])
        print(f"\n--- JSON responses captured: {len(json_responses)} ---")
        for url, body in json_responses[:3]:
            keys = list(body.keys()) if isinstance(body, dict) else type(body).__name__
            print(f"  {url[:100]}  →  keys: {keys}")

        await browser.close()


asyncio.run(main())
