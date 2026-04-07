#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""检查 PC 端榜单 URL"""
import asyncio
import sys
import io
import re
import json
sys.path.insert(0, '..')

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import httpx

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9",
    "Referer": "https://www.qidian.com/",
}

async def check_pc_page(category):
    """检查 PC 端页面"""
    url = f"https://www.qidian.com/rank/{category}/"

    async with httpx.AsyncClient(headers=HEADERS, timeout=15.0, follow_redirects=True) as client:
        resp = await client.get(url)
        html = resp.text

    print(f"\n=== PC: {category} ===")
    print(f"URL: {url}")
    print(f"Status: {resp.status_code}")
    print(f"HTML length: {len(html)}")

    # 检查页面是否被 WAF 拦截
    if 'probe.js' in html or 'buid' in html:
        print("  WAF blocked (probe.js)")
        return

    # 检查是否有数据
    if 'pageData' in html or 'records' in html:
        # 查找 JSON 数据
        match = re.search(r'window\.__INITIAL_STATE__\s*=\s*({.+?})\s*;', html, re.DOTALL)
        if not match:
            match = re.search(r'<script[^>]*type=["\']application/json["\'][^>]*>([^<]+)</script>', html, re.DOTALL)

        if match:
            try:
                data = json.loads(match.group(1))
                # 尝试找到 records
                for key in ['pageData', 'data', 'records']:
                    if key in str(data)[:500]:
                        break

                # 直接搜索 records
                records_match = re.search(r'"records"\s*:\s*\[', html)
                if records_match:
                    print(f"  'records' array found in HTML")
                    idx = records_match.start()
                    print(f"  Context: {html[idx:idx+200]}")
            except:
                pass

    # 检查页面标题
    title_match = re.search(r'<title>([^<]+)</title>', html)
    if title_match:
        print(f"  Title: {title_match.group(1)}")

async def main():
    categories = ['hot', 'collect', 'weekclick', 'vipcollect', 'recom']

    for cat in categories:
        await check_pc_page(cat)
        await asyncio.sleep(0.5)

if __name__ == '__main__':
    asyncio.run(main())