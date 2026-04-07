#!/usr/bin/env python3
"""调试网文平台爬虫"""
import asyncio
import sys
import logging

logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

sys.path.insert(0, '/backend')

import httpx
from app.services.trend.qidian_scraper import QidianScraper

async def debug_qidian():
    """调试起点爬虫"""
    print("Testing Qidian API endpoint...")

    # Test 1: Try the API endpoint directly
    api_url = "https://www.qidian.com/ajax/book/category?gender=male&pageNum=1&pageSize=20"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/json",
        "Referer": "https://www.qidian.com/rank/hotsales/",
    }

    try:
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            print(f"Fetching: {api_url}")
            resp = await client.get(api_url, headers=headers)
            print(f"Status: {resp.status_code}")
            print(f"Content-Type: {resp.headers.get('content-type', 'unknown')}")
            print(f"Response length: {len(resp.text)}")

            if resp.status_code == 200:
                try:
                    data = resp.json()
                    print(f"JSON keys: {list(data.keys())[:5]}")
                    if 'data' in data:
                        print(f"Data type: {type(data['data'])}")
                except Exception as e:
                    print(f"Failed to parse JSON: {e}")
                    print(f"First 500 chars: {resp.text[:500]}")
    except Exception as e:
        print(f"Request failed: {e}")

    print("\n" + "="*60 + "\n")

    # Test 2: Try the scraper
    print("Testing QidianScraper...")
    scraper = QidianScraper()
    try:
        result = await scraper.fetch_ranking(category="hot", limit=5)
        print(f"Platform: {result.platform}")
        print(f"Category: {result.category}")
        print(f"Books count: {len(result.books)}")
        if result.books:
            for b in result.books[:2]:
                print(f"  - {b.title} by {b.author}")
    except Exception as e:
        print(f"Scraper error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(debug_qidian())
