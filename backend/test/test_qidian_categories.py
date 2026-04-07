#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""测试起点各分类的数据"""
import asyncio
import sys
import io
import re
import json
sys.path.insert(0, '..')

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

from app.services.trend.qidian_scraper import QidianScraper

async def main():
    scraper = QidianScraper()

    # 测试各分类
    categories = [
        ('hot', '畅销榜'),
        ('monthly', '月票榜'),
        ('readindex', '阅读指数榜'),
        ('collect', '收藏榜'),
        ('vipcollect', 'VIP收藏榜'),
        ('newauthor', '新人新书榜'),
        ('signnewbook', '签约新书榜'),
        ('recommend', '推荐榜'),
        ('week', '周点击榜'),
    ]

    print("=== Testing Qidian Categories ===\n")

    for cat_id, cat_name in categories:
        print(f"Testing {cat_name} ({cat_id})...")

        # 检查支持的分类
        if cat_id not in scraper.supported_categories:
            print(f"  NOT supported by scraper")
            continue

        display_name, api_cat, m_slug = scraper.supported_categories[cat_id]
        print(f"  API cat: {api_cat}, Mobile slug: {m_slug}")

        # 测试移动端
        url = f"https://m.qidian.com/rank/{m_slug}/"
        print(f"  URL: {url}")

        import httpx
        M_HEADERS = {
            "User-Agent": (
                "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) "
                "AppleWebKit/605.1.15 (KHTML, like Gecko) "
                "Version/16.6 Mobile/15E148 Safari/604.1"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Referer": "https://m.qidian.com/",
        }

        try:
            async with httpx.AsyncClient(headers=M_HEADERS, timeout=15.0, follow_redirects=True) as client:
                resp = await client.get(url)
                html = resp.text

            # 提取数据
            script_pattern = r'<script[^>]*type=["\']application/json["\'][^>]*>([^<]+)</script>'
            match = re.search(script_pattern, html, re.DOTALL)
            if match:
                data = json.loads(match.group(1))
                records = data.get("pageContext", {}).get("pageProps", {}).get("pageData", {}).get("records", [])
                total = data.get("pageContext", {}).get("pageProps", {}).get("pageData", {}).get("total", 0)
                print(f"  Records: {len(records)}, Total: {total}")

                if records:
                    first = records[0]
                    print(f"    First: {first.get('bName')} by {first.get('bAuth')}")
            else:
                print(f"  No JSON data found!")
                # 检查页面标题
                if '畅销榜' in html:
                    print(f"    Page contains '畅销榜'")
                if '月票' in html:
                    print(f"    Page contains '月票'")

        except Exception as e:
            print(f"  Error: {e}")

        print()

if __name__ == '__main__':
    asyncio.run(main())