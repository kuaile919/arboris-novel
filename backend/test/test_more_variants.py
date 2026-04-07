#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import asyncio
import httpx
import io
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

M_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'zh-CN,zh;q=0.9',
    'Referer': 'https://m.qidian.com/',
}

async def test(url):
    async with httpx.AsyncClient(headers=M_HEADERS, timeout=10.0, follow_redirects=True) as client:
        resp = await client.get(url)
    return resp.status_code

async def main():
    # 尝试收藏/VIP相关的变体
    slugs = [
        'vip', 'vipbook', 'viprank', 'vipbook',
        'fav', 'favor', 'favorite',
        'subscribe', 'sub',
        'bookcase', 'bookself',
        'store', 'storebook',
        'collectbook', 'collections',
        'rankList', 'ranklist',
        'allRank', 'allrank',
    ]
    base = 'https://m.qidian.com/rank/'

    for s in slugs:
        status = await test(base + s + '/')
        print(f'{s}: {status}')
        await asyncio.sleep(0.2)

asyncio.run(main())