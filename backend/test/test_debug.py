#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""临时测试脚本"""
import asyncio
import sys
import json
import io
sys.path.insert(0, '..')

# Fix Windows stdout encoding for Chinese
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

from app.services.trend.fanqie_scraper import FanqieScraper
from app.services.trend.qidian_scraper import QidianScraper

async def test_fanqie():
    print("=== Testing FanqieScraper ===")
    scraper = FanqieScraper()
    result = await scraper.fetch_ranking('hot', 3)
    print('Platform:', result.platform)
    print('Books count:', len(result.books))
    for b in result.books[:3]:
        data = {
            'rank': b.rank,
            'title': b.title,
            'author': b.author,
            'genre': b.genre,
            'desc_len': len(b.description) if b.description else 0,
            'heat_score': b.heat_score,
            'word_count': b.word_count,
            'book_url': b.book_url[:50] if b.book_url else ''
        }
        print(json.dumps(data, ensure_ascii=False))
    print()

async def test_qidian():
    print("=== Testing QidianScraper ===")
    scraper = QidianScraper()

    # Test each strategy
    strategies = [
        ('API', lambda: scraper._fetch_via_api('hotsales', 3)),
        ('PC', lambda: scraper._fetch_via_pc('hot', 3)),
    ]

    for name, fn in strategies:
        print(f'Testing {name}...')
        try:
            books = await fn()
            print(f'  Result: {len(books)} books')
            for b in books[:2]:
                print(f'    - {b.title[:30]} by {b.author[:10]}')
        except Exception as e:
            print(f'  Error: {type(e).__name__}: {e}')
    print()

async def main():
    await test_fanqie()
    await test_qidian()

if __name__ == '__main__':
    asyncio.run(main())