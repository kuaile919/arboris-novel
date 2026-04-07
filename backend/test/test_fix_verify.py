#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""验证修复后的爬虫"""
import asyncio
import sys
import io
import json
sys.path.insert(0, '..')

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

from app.services.trend.qidian_scraper import QidianScraper
from app.services.trend.fanqie_scraper import FanqieScraper

async def main():
    print("=== Testing QidianScraper ===\n")

    scraper = QidianScraper()
    result = await scraper.fetch_ranking('hot', 5)

    print(f"Platform: {result.platform}")
    print(f"Category: {result.category}")
    print(f"Books count: {len(result.books)}")

    if result.books:
        print("\nFirst 5 books:")
        for i, book in enumerate(result.books[:5], 1):
            data = {
                'rank': book.rank,
                'title': book.title,
                'author': book.author,
                'genre': book.genre,
                'word_count': book.word_count,
                'desc_preview': (book.description or '')[:50]
            }
            print(f"\n  {i}. {json.dumps(data, ensure_ascii=False)}")
    else:
        print("\nNo books fetched!")

    print("\n\n=== Testing FanqieScraper ===\n")

    scraper2 = FanqieScraper()
    result2 = await scraper2.fetch_ranking('hot', 5)

    print(f"Platform: {result2.platform}")
    print(f"Category: {result2.category}")
    print(f"Books count: {len(result2.books)}")

    if result2.books:
        print("\nFirst 5 books:")
        for i, book in enumerate(result2.books[:5], 1):
            data = {
                'rank': book.rank,
                'title': book.title,
                'author': book.author,
                'genre': book.genre,
                'word_count': book.word_count,
                'desc_preview': (book.description or '')[:50]
            }
            print(f"\n  {i}. {json.dumps(data, ensure_ascii=False)}")

if __name__ == '__main__':
    asyncio.run(main())