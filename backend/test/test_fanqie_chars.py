#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""测试番茄爬虫返回的字符"""
import asyncio
import sys
import io
sys.path.insert(0, '..')

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

from app.services.trend.fanqie_scraper import FanqieScraper

async def main():
    scraper = FanqieScraper()
    result = await scraper.fetch_ranking('hot', 3)
    for book in result.books:
        print(f'标题: {repr(book.title)}')
        for char in book.title:
            print(f'  char: {char!r} -> U+{ord(char):04X}')
        print(f'  描述: {repr(book.description[:80] if book.description else "")}...')
        print()

if __name__ == '__main__':
    asyncio.run(main())