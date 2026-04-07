#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""测试起点 PC API"""
import asyncio
import sys
import io
import json
sys.path.insert(0, '..')

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import httpx

# 尝试 PC API
API_URLS = {
    "hotsales": "https://www.qidian.com/ajax/rank/hotsales?page=1",
    "yuepiao": "https://www.qidian.com/ajax/rank/yuepiao?page=1",
    "readindex": "https://www.qidian.com/ajax/rank/readindex?page=1",
    "collect": "https://www.qidian.com/ajax/rank/collect?page=1",
    "weekclick": "https://www.qidian.com/ajax/rank/weekclick?page=1",
    "vipcollect": "https://www.qidian.com/ajax/rank/vipcollect?page=1",
    "recom": "https://www.qidian.com/ajax/rank/recom?page=1",
}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "X-Requested-With": "XMLHttpRequest",
    "Referer": "https://www.qidian.com/",
}

async def test_api():
    print("=== Testing Qidian PC API ===\n")

    for cat, url in API_URLS.items():
        print(f"Testing {cat}...")
        try:
            async with httpx.AsyncClient(headers=HEADERS, timeout=15.0, follow_redirects=True) as client:
                resp = await client.get(url)

            print(f"  Status: {resp.status_code}")

            if resp.status_code == 200:
                content_type = resp.headers.get('content-type', '')
                if 'json' in content_type:
                    try:
                        data = resp.json()
                        records = data.get("data", {}).get("records", [])
                        print(f"  Records: {len(records)}")
                        if records:
                            first = records[0]
                            print(f"    First: {first.get('bName', 'N/A')}")
                    except Exception as e:
                        print(f"  JSON error: {e}")
                        # 保存响应
                        with open(f'api_{cat}_response.txt', 'w', encoding='utf-8') as f:
                            f.write(resp.text[:500])
                else:
                    print(f"  Not JSON: {content_type}")
                    print(f"  Content: {resp.text[:200]}")
            else:
                print(f"  Content: {resp.text[:200]}")

        except Exception as e:
            print(f"  Error: {e}")

        print()

asyncio.run(test_api())