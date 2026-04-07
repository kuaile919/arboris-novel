#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import sys
import io
sys.path.insert(0, '..')

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

from app.services.trend.scraping_service import TrendScrapingService
from app.db.session import AsyncSessionLocal

async def main():
    async with AsyncSessionLocal() as session:
        service = TrendScrapingService(session)
        platforms = service.get_supported_platforms()

    print("=== 返回的 platforms 数据 ===\n")
    for p in platforms:
        print(f"平台: {p['id']} - {p['name']}")
        print(f"  分类: {p['categories']}")
        print()

if __name__ == '__main__':
    import asyncio
    asyncio.run(main())