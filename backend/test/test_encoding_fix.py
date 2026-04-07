#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""测试编码问题"""
import asyncio
import sys
import io
sys.path.insert(0, '..')

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import httpx

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

    print(f"Status: {resp.status_code}")
    print(f"Content-Type: {resp.headers.get('content-type', '')}")
    print(f"Encoding from headers: {resp.encoding}")

    # 尝试不同的编码
    content_bytes = resp.content
    print(f"Content length (bytes): {len(content_bytes)}")

    # 尝试 UTF-8
    try:
        content_utf8 = content_bytes.decode('utf-8')
        print(f"\nUTF-8 decode: OK, length={len(content_utf8)}")
        if '�' in content_utf8 or '\ufffd' in content_utf8:
            print("UTF-8 contains replacement characters - might be wrong encoding")
    except Exception as e:
        print(f"UTF-8 decode failed: {e}")

    # 尝试 GBK
    try:
        content_gbk = content_bytes.decode('gbk')
        print(f"\nGBK decode: OK, length={len(content_gbk)}")
        if '捞尸人' in content_gbk:
            print("GBK contains correct Chinese characters!")
            # 搜索 bName
            idx = content_gbk.find('"bName"')
            print(f"bName context: {content_gbk[idx:idx+100]}")
    except Exception as e:
        print(f"GBK decode failed: {e}")

    # 保存原始 bytes
    with open('qidian_raw.bin', 'wb') as f:
        f.write(content_bytes)
    print("\nSaved raw bytes to qidian_raw.bin")

if __name__ == '__main__':
    asyncio.run(main())