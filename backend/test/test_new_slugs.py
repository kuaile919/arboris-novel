#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""检查可用的替代榜单"""
import asyncio
import sys
import io
import re
import json
sys.path.insert(0, '..')

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

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

SLUGS_TO_CHECK = [
    ("sign", "签约相关"),
    ("rec", "推荐相关"),
    ("newbook", "新书相关"),
    ("signnewbook", "签约新书(原URL)"),
    ("newsign", "新人签约(原URL)"),
]

async def check_slug(slug, name):
    url = f"https://m.qidian.com/rank/{slug}/"
    async with httpx.AsyncClient(headers=M_HEADERS, timeout=10.0, follow_redirects=True) as client:
        resp = await client.get(url)

    if resp.status_code == 200:
        html = resp.text
        match = re.search(r'<script[^>]*type=["\']application/json["\'][^>]*>([^<]+)</script>', html, re.DOTALL)
        if match:
            try:
                data = json.loads(match.group(1))
                records = data.get("pageContext", {}).get("pageProps", {}).get("pageData", {}).get("records", [])
                total = data.get("pageContext", {}).get("pageProps", {}).get("pageData", {}).get("total", 0)
                if records:
                    first = records[0]
                    return {
                        "status": "✅",
                        "count": len(records),
                        "total": total,
                        "first_title": first.get("bName", "N/A"),
                        "first_author": first.get("bAuth", "N/A"),
                        "genre": first.get("cat", "N/A"),
                    }
                return {"status": "⚠️", "count": 0}
            except Exception as e:
                return {"status": "❌", "error": str(e)}
    return {"status": "❌", "code": resp.status_code}

async def main():
    print("=== 替代榜单检查 ===\n")

    for slug, name in SLUGS_TO_CHECK:
        print(f"Testing {name} ({slug})...")
        result = await check_slug(slug, name)
        print(f"  Status: {result.get('status')}")
        if result.get('status') == '✅':
            print(f"  Records: {result.get('count')}, Total: {result.get('total')}")
            print(f"  First: {result.get('first_title')} by {result.get('first_author')} [{result.get('genre')}]")
        elif result.get('error'):
            print(f"  Error: {result.get('error')}")
        elif result.get('code'):
            print(f"  HTTP: {result.get('code')}")
        print()

if __name__ == '__main__':
    asyncio.run(main())