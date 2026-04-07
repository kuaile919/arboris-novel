#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""检查起点移动端页面结构"""
import asyncio
import sys
import io
import re
sys.path.insert(0, '..')

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import httpx
from bs4 import BeautifulSoup

HEADERS = {
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

    async with httpx.AsyncClient(headers=HEADERS, timeout=15.0, follow_redirects=True) as client:
        resp = await client.get(url)
        html = resp.text

    print(f"HTML length: {len(html)}")

    soup = BeautifulSoup(html, "lxml")

    # 检查页面标题
    title = soup.find('title')
    print(f"Title: {title.get_text() if title else 'None'}")

    # 查找所有书籍相关链接
    book_links = soup.select('a[href*="/book/"]')
    print(f"\nBook links found: {len(book_links)}")

    # 查找包含书籍数据的 script 标签
    scripts = soup.find_all('script')
    print(f"\nScript tags: {len(scripts)}")

    for i, script in enumerate(scripts):
        text = script.string or ""
        if len(text) > 50 and ('book' in text.lower() or 'rank' in text.lower()):
            print(f"\nScript {i} (len={len(text)}):")
            print(text[:500])

    # 查找 JSON 数据
    json_patterns = [
        r'window\.__INITIAL_STATE__\s*=\s*({.+?})\s*;',
        r'var\s+\w+\s*=\s*({.+?})\s*;',
    ]

    for pattern in json_patterns:
        match = re.search(pattern, html, re.DOTALL)
        if match:
            print(f"\nFound JSON with pattern: {pattern[:30]}...")
            print(f"JSON length: {len(match.group(1))}")
            print(f"First 300 chars: {match.group(1)[:300]}")

    # 保存完整HTML用于调试
    with open('qidian_mobile_debug.html', 'w', encoding='utf-8') as f:
        f.write(html)
    print("\nSaved full HTML to qidian_mobile_debug.html")

if __name__ == '__main__':
    asyncio.run(main())