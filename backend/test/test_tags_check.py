#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""检查抓取数据中的 tags 字段"""
import asyncio
import sys
import io
import json
sys.path.insert(0, '..')

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

from app.services.trend.qidian_scraper import QidianScraper
from app.services.trend.fanqie_scraper import FanqieScraper

async def main():
    # 测试起点
    print("=== QidianScraper ===\n")
    qidian = QidianScraper()
    result = await qidian.fetch_ranking('hot', 5)
    for book in result.books[:5]:
        print(f"Title: {book.title}")
        print(f"  Genre: {book.genre}")
        print(f"  Tags: {book.tags}")
        print()

    # 测试番茄
    print("=== FanqieScraper ===\n")
    fanqie = FanqieScraper()
    result2 = await fanqie.fetch_ranking('hot', 5)
    for book in result2.books[:5]:
        print(f"Title: {book.title}")
        print(f"  Genre: {book.genre}")
        print(f"  Tags: {book.tags}")
        print()

if __name__ == '__main__':
    asyncio.run(main())