#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""检查空数据页面的实际内容"""
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

async def check_page(slug, name):
    url = f"https://m.qidian.com/rank/{slug}/"

    async with httpx.AsyncClient(headers=M_HEADERS, timeout=15.0, follow_redirects=True) as client:
        resp = await client.get(url)
        html = resp.text

    print(f"\n=== {name} ({slug}) ===")
    print(f"URL: {url}")
    print(f"Status: {resp.status_code}")
    print(f"HTML length: {len(html)}")

    # 检查是否有 JSON 数据
    script_pattern = r'<script[^>]*type=["\']application/json["\'][^>]*>([^<]+)</script>'
    match = re.search(script_pattern, html, re.DOTALL)
    if match:
        try:
            data = json.loads(match.group(1))
            pageData = data.get("pageContext", {}).get("pageProps", {}).get("pageData", {})
            records = pageData.get("records", [])
            total = pageData.get("total", 0)
            print(f"JSON found: records={len(records)}, total={total}")

            # 检查数据结构
            if records:
                print(f"  First record: {records[0].get('bName', 'N/A')}")
            else:
                # 看看 pageData 里有什么
                print(f"  pageData keys: {list(pageData.keys())}")
                for k, v in pageData.items():
                    if v:
                        print(f"    {k}: {str(v)[:100]}")
        except Exception as e:
            print(f"JSON parse error: {e}")
    else:
        print("No JSON found!")
        # 检查是否有其他数据结构
        if 'pageContext' in html:
            print("  'pageContext' found in HTML")
        if 'records' in html:
            print("  'records' found in HTML")

        # 保存部分内容用于调试
        with open(f'qidian_{slug}_debug.html', 'w', encoding='utf-8') as f:
            f.write(html[:5000])
        print(f"  Saved first 5000 chars to qidian_{slug}_debug.html")

async def main():
    # 先测试有数据的，再测试没数据的
    await check_page("hotsales", "畅销榜(hot)")
    await check_page("collect", "收藏榜(collect)")
    await check_page("weekclick", "周点击榜(week)")

if __name__ == '__main__':
    asyncio.run(main())