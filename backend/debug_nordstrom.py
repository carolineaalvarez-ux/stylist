"""
Run inside the backend container:
    docker compose exec backend python debug_nordstrom.py
"""
import asyncio
import json
import re
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
        await page.wait_for_timeout(3_000)

        title = await page.title()
        html = await page.content()

        print(f"\nPage title: {title}")
        print(f"HTML length: {len(html)} chars")
        print(f"JSON responses captured: {len(json_responses)}")

        # --- Search for product data patterns ---
        print("\n--- Searching for product data in HTML ---")

        # 1. Look for any <script> tags containing JSON with product-like keys
        script_jsons = re.findall(r'<script[^>]*>\s*(\{[^<]{200,})\s*</script>', html, re.S)
        print(f"Large JSON script blocks found: {len(script_jsons)}")
        for i, blob in enumerate(script_jsons[:5]):
            try:
                data = json.loads(blob)
                keys = list(data.keys())[:8]
                print(f"  [{i}] top-level keys: {keys}")
                # Check if it has product-looking content
                blob_lower = blob[:500].lower()
                if any(k in blob_lower for k in ("styleid", "productid", "brandname", "pricecurrencycode")):
                    print(f"      *** LOOKS LIKE PRODUCT DATA ***")
                    print(f"      First 300 chars: {blob[:300]}")
            except Exception:
                pass

        # 2. Look for window.* assignments with JSON
        window_vars = re.findall(r'window\.(\w+)\s*=\s*(\{.*?\});', html, re.S)
        print(f"\nwindow.* assignments found: {len(window_vars)}")
        for name, val in window_vars[:5]:
            print(f"  window.{name} = (first 100 chars) {val[:100]}")

        # 3. Search for inline JSON-LD
        jsonld = re.findall(r'<script type="application/ld\+json">(.*?)</script>', html, re.S)
        print(f"\nJSON-LD blocks: {len(jsonld)}")
        for i, blob in enumerate(jsonld[:3]):
            try:
                data = json.loads(blob)
                t = data.get("@type", "unknown") if isinstance(data, dict) else type(data).__name__
                print(f"  [{i}] @type={t}, keys={list(data.keys())[:6] if isinstance(data, dict) else 'list'}")
            except Exception as e:
                print(f"  [{i}] parse error: {e}")

        # 4. Search HTML for product card patterns
        article_count = html.count('<article')
        li_product = html.count('product-card') + html.count('product-item') + html.count('productCard')
        print(f"\n<article> tags in HTML: {article_count}")
        print(f"'product-card/item/Card' occurrences: {li_product}")

        # 5. Look for price patterns
        prices = re.findall(r'\$\d{2,3}\.\d{2}', html)
        print(f"Price patterns ($XX.XX) found: {len(prices)}")
        if prices:
            print(f"  Sample: {prices[:5]}")

        # 6. Look for brand names we know
        for brand in ["Equipment", "Theory", "Vince", "Toteme", "Sezane"]:
            if brand.lower() in html.lower():
                print(f"  Brand '{brand}' found in HTML")

        # 7. Dump a snippet around first product-like content
        for pattern in ["styleId", "productId", "brandName", "product-card"]:
            idx = html.find(pattern)
            if idx != -1:
                print(f"\nFound '{pattern}' at position {idx}. Surrounding 400 chars:")
                print(html[max(0, idx-50):idx+350])
                break

        await browser.close()


asyncio.run(main())
