#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""检查番茄页面编码和初始状态"""
import asyncio
import sys
import re
import io
sys.path.insert(0, '..')

# Fix Windows stdout encoding
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import httpx

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Referer": "https://fanqienovel.com/",
}

async def main():
    url = "https://fanqienovel.com/rank"
    print(f"Fetching: {url}")

    async with httpx.AsyncClient(headers=HEADERS, timeout=15.0, follow_redirects=True) as client:
        resp = await client.get(url)
        print(f"Status: {resp.status_code}")
        print(f"Encoding from headers: {resp.encoding}")
        print(f"Content-Type: {resp.headers.get('content-type', '')}")

        html = resp.text
        print(f"HTML length: {len(html)}")

        # 查找 INITIAL_STATE
        patterns = [
            r'window\.__INITIAL_STATE__\s*=\s*({.+?});\s*</script>',
            r'window\.__INITIAL_STATE__\s*=\s*({.+?});',
        ]
        match = None
        for pattern in patterns:
            match = re.search(pattern, html, re.DOTALL)
            if match:
                print(f"\nFound INITIAL_STATE with pattern: {pattern[:50]}...")
                state_str = match.group(1)
                print(f"State string length: {len(state_str)}")

                # 检查是否是有效JSON
                import json
                try:
                    data = json.loads(state_str)
                    print("JSON parsed successfully!")

                    # 打印rank节点的keys
                    rank_data = data.get("rank", {})
                    print(f"rank keys: {list(rank_data.keys()) if isinstance(rank_data, dict) else 'not a dict'}")

                    book_list = rank_data.get("book_list", [])
                    print(f"book_list length: {len(book_list)}")

                    if book_list:
                        print("\nFirst book raw data:")
                        first = book_list[0]
                        for k, v in first.items():
                            v_str = str(v)[:100]
                            print(f"  {k}: {v_str}")
                except json.JSONDecodeError as e:
                    print(f"JSON parse error: {e}")
                    print(f"First 200 chars of state: {state_str[:200]}")
                break
        else:
            print("INITIAL_STATE not found!")
            # 保存部分HTML用于调试
            with open('fanqie_debug.html', 'w', encoding='utf-8') as f:
                f.write(html[:10000])
            print("Saved first 10000 chars to fanqie_debug.html")

if __name__ == '__main__':
    asyncio.run(main())