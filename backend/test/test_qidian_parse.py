#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""测试起点移动端解析"""
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

    # 测试不同的正则模式
    patterns = [
        (r'window\.__INITIAL_STATE__\s*=\s*({.+?})\s*;', "__INITIAL_STATE__"),
        (r'window\.__INITIAL__\s*=\s*({.+?})\s*;', "__INITIAL__"),
    ]

    for pattern, name in patterns:
        match = re.search(pattern, html, re.DOTALL)
        if match:
            print(f"\nFound {name}!")
            json_str = match.group(1)
            print(f"JSON length: {len(json_str)}")

            try:
                data = json.loads(json_str)
                print(f"JSON parsed successfully!")

                # 遍历查找 records
                pageContext = data.get("pageContext", {})
                pageProps = pageContext.get("pageProps", {})
                pageData = pageProps.get("pageData", {})
                records = pageData.get("records", [])

                print(f"records count: {len(records)}")

                if records:
                    first = records[0]
                    print(f"\nFirst record keys: {list(first.keys())}")
                    print(f"First record: {json.dumps(first, ensure_ascii=False)[:300]}")

            except json.JSONDecodeError as e:
                print(f"JSON parse error: {e}")
                print(f"First 200 chars: {json_str[:200]}")
        else:
            print(f"\n{name} not found")

if __name__ == '__main__':
    asyncio.run(main())