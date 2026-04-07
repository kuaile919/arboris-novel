#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""探索移动端正确的榜单 URL"""
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

async def check_url(url, name):
    """检查 URL 是否有效"""
    async with httpx.AsyncClient(headers=M_HEADERS, timeout=15.0, follow_redirects=True) as client:
        resp = await client.get(url)

    status = resp.status_code
    has_data = False
    record_count = 0

    if status == 200:
        html = resp.text
        # 检查是否有 JSON 数据
        match = re.search(r'<script[^>]*type=["\']application/json["\'][^>]*>([^<]+)</script>', html, re.DOTALL)
        if match:
            try:
                data = json.loads(match.group(1))
                records = data.get("pageContext", {}).get("pageProps", {}).get("pageData", {}).get("records", [])
                record_count = len(records)
                has_data = record_count > 0
            except:
                pass

    print(f"{name}: {url} -> {status}, records={record_count}")
    return has_data, status

async def main():
    print("=== Testing different URL patterns ===\n")

    # 测试不同的 URL 格式
    urls_to_test = [
        # 标准格式
        ("m.qidian.com/rank/hotsales/", "畅销榜"),
        ("m.qidian.com/rank/collect/", "收藏榜-标准"),
        ("m.qidian.com/rank/yuepiao/", "月票榜"),

        # 可能的替代格式
        ("m.qidian.com/rank/collect/1/", "收藏榜-带页码"),
        ("m.qidian.com/rank/weekclick/", "周点击榜"),
        ("m.qidian.com/rank/vipcollect/", "VIP收藏榜"),
        ("m.qidian.com/rank/recom/", "推荐榜"),

        # 尝试不同的路径
        ("m.qidian.com/rank/?cat=collect", "收藏榜-Query"),
        ("m.qidian.com/rank/?type=weekclick", "周点击-Query"),
    ]

    results = []
    for path, name in urls_to_test:
        url = f"https://{path}"
        has_data, status = await check_url(url, name)
        results.append((name, status, has_data))
        await asyncio.sleep(0.3)

    print("\n=== Summary ===")
    working = [(n, s) for n, s, d in results if d]
    not_found = [(n, s) for n, s, d in results if not d and s == 404]
    blocked = [(n, s) for n, s, d in results if not d and s == 202]

    if working:
        print("Working:")
        for n, s in working:
            print(f"  {n}")

    if not_found:
        print("\n404 Not Found:")
        for n, s in not_found:
            print(f"  {n}")

if __name__ == '__main__':
    asyncio.run(main())