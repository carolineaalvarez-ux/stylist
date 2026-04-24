"""
Test the Apify Nordstrom scraper integration.

    docker compose exec backend python debug_nordstrom.py
"""
import asyncio
import json
import os
import httpx

APIFY_ACTOR_ID = "trudax~actor-nordstrom-scraper"
APIFY_URL = f"https://api.apify.com/v2/acts/{APIFY_ACTOR_ID}/run-sync-get-dataset-items"


async def main():
    token = os.environ.get("APIFY_API_TOKEN", "")
    if not token:
        # Try reading from .env file directly
        env_path = "/app/.env"
        if os.path.exists(env_path):
            for line in open(env_path):
                if line.startswith("APIFY_API_TOKEN="):
                    token = line.strip().split("=", 1)[1]

    if not token:
        print("ERROR: APIFY_API_TOKEN not set in environment or .env file")
        return

    print(f"Token found: {token[:12]}...")
    print("Calling Apify Nordstrom scraper for 'silk blouse women' (maxItems=3)...")

    async with httpx.AsyncClient(timeout=120.0) as client:
        try:
            resp = await client.post(
                APIFY_URL,
                params={"token": token},
                json={"search": "silk blouse women", "country": "United States", "maxItems": 3},
            )
            print(f"HTTP status: {resp.status_code}")

            if resp.status_code != 200:
                print(f"Error response: {resp.text[:500]}")
                return

            data = resp.json()
            items = data if isinstance(data, list) else data.get("items", [])
            print(f"Items returned: {len(items)}")

            for i, item in enumerate(items[:3]):
                print(f"\n--- Item {i+1} ---")
                print(f"Keys: {list(item.keys())}")
                print(f"Name:  {item.get('title') or item.get('name') or item.get('productName')}")
                print(f"Brand: {item.get('brand') or item.get('brandName')}")
                print(f"Price: {item.get('price') or item.get('salePrice') or item.get('regularPrice')}")
                print(f"Color: {item.get('color') or item.get('colorName')}")
                print(f"URL:   {(item.get('url') or '')[:80]}")

        except Exception as exc:
            print(f"Error: {exc}")


asyncio.run(main())
