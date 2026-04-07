#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""检查所有可能的榜单 URL"""
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

# 测试所有可能的 URL
URL_PATTERNS = [
    # 标准榜单
    "hotsales", "yuepiao", "readindex", "newsign", "signnewbook",
    # 尝试各种变体
    "weekclick", "weekVIP", "vipcollect", "vip", "recom",
    "collect", "favor", "favorite", "subscribe",
    "newbook", "new", "sign",
    "month", "monthly", "yuepiao",
    "total", "all",
    # 可能的路径格式
    "rank/hotsales", "rank/yuepiao",
    # 变体拼写
    "recommand", "rec",
    # 各种排行榜
    "vote", "voteRank",
    # 尝试带参数的
    "?cat=hotsales",
]

async def test_url(url, name):
    async with httpx.AsyncClient(headers=M_HEADERS, timeout=10.0, follow_redirects=True) as client:
        resp = await client.get(url)

    if resp.status_code == 200:
        html = resp.text
        # 检查是否有数据
        match = re.search(r'<script[^>]*type=["\']application/json["\'][^>]*>([^<]+)</script>', html, re.DOTALL)
        if match:
            try:
                data = json.loads(match.group(1))
                records = data.get("pageContext", {}).get("pageProps", {}).get("pageData", {}).get("records", [])
                total = data.get("pageContext", {}).get("pageProps", {}).get("pageData", {}).get("total", 0)
                if records:
                    return f"✅ {len(records)} records, total={total}"
                else:
                    return f"⚠️ 0 records"
            except:
                return f"⚠️ JSON parse error"
        return f"⚠️ No JSON data"
    elif resp.status_code == 404:
        return f"❌ 404"
    else:
        return f"⚠️ {resp.status_code}"

async def main():
    base_url = "https://m.qidian.com/rank/"

    print("=== Testing Qidian Mobile Rank URLs ===\n")

    results = []
    for pattern in URL_PATTERNS:
        url = f"{base_url}{pattern}/"
        result = await test_url(url, pattern)
        results.append((pattern, result))
        print(f"{pattern}: {result}")
        await asyncio.sleep(0.2)

    print("\n=== Working URLs ===")
    for pattern, result in results:
        if result.startswith("✅"):
            print(f"  {pattern}: {result}")

if __name__ == '__main__':
    asyncio.run(main())