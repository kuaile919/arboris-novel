#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""检查起点实际返回多少条数据"""
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

async def main():
    url = "https://m.qidian.com/rank/hotsales/"

    async with httpx.AsyncClient(headers=M_HEADERS, timeout=15.0, follow_redirects=True) as client:
        resp = await client.get(url)
        html = resp.text

    print(f"HTML length: {len(html)}")

    # 直接用正则提取 JSON
    script_pattern = r'<script[^>]*type=["\']application/json["\'][^>]*>([^<]+)</script>'
    match = re.search(script_pattern, html, re.DOTALL)
    if match:
        json_str = match.group(1)
        try:
            data = json.loads(json_str)
            records = data.get("pageContext", {}).get("pageProps", {}).get("pageData", {}).get("records", [])
            print(f"\nTotal records in pageData.records: {len(records)}")

            # 检查是否还有更多分页数据
            pageData = data.get("pageContext", {}).get("pageProps", {}).get("pageData", {})
            total = pageData.get("total", 0)
            isLast = pageData.get("isLast", 1)
            print(f"total: {total}, isLast: {isLast}")

            if records:
                print(f"\nFirst 3 records:")
                for i, rec in enumerate(records[:3]):
                    print(f"  {i+1}. rankNum={rec.get('rankNum')}, bName={rec.get('bName')}")

                print(f"\nLast 3 records:")
                for i, rec in enumerate(records[-3:]):
                    print(f"  {len(records)-2+i}. rankNum={rec.get('rankNum')}, bName={rec.get('bName')}")

        except json.JSONDecodeError as e:
            print(f"JSON parse error: {e}")

if __name__ == '__main__':
    asyncio.run(main())