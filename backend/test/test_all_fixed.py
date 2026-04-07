#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""测试所有分类"""
import asyncio
import sys
import io
import json
sys.path.insert(0, '..')

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

from app.services.trend.qidian_scraper import QidianScraper

async def main():
    scraper = QidianScraper()

    print("=== 测试 QidianScraper 所有分类 ===\n")

    # 获取所有支持的分类
    categories = scraper.get_supported_categories()
    print(f"支持的分类数量: {len(categories)}\n")

    for cat_id, cat_name in categories.items():
        result = await scraper.fetch_ranking(cat_id, 3)
        count = len(result.books)
        status = f"✅ {count}条" if count > 0 else "❌ 0条"
        first = result.books[0].title if result.books else "-"
        print(f"{cat_name:30s} [{cat_id:15s}]: {status}, 首本: {first}")

asyncio.run(main())