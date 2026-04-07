#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""检查响应头和压缩编码"""
import asyncio
import sys
import io
import zlib
sys.path.insert(0, '..')

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import httpx

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) "
        "Version/16.6 Mobile/15E148 Safari/604.1"
    ),
    "Accept-Encoding": "gzip, deflate, br",  # 请求压缩
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9",
    "Referer": "https://m.qidian.com/",
}

async def main():
    url = "https://m.qidian.com/rank/hotsales/"

    async with httpx.AsyncClient(headers=HEADERS, timeout=15.0, follow_redirects=True) as client:
        resp = await client.get(url)

    print("=== Response Headers ===")
    for k, v in resp.headers.items():
        if k.lower() in ['content-type', 'content-encoding', 'content-length', 'transfer-encoding']:
            print(f"  {k}: {v}")

    print(f"\nResponse encoding: {resp.encoding}")
    print(f"Content length after decoding: {len(resp.text)}")

    # 检查 text 是否包含乱码
    text = resp.text
    bad_char_count = sum(1 for c in text if ord(c) > 0xfffd)
    print(f"Characters outside BMP: {bad_char_count}")

    # 查找 script 中的数据
    import re
    scripts = re.findall(r'<script[^>]*>([^<]+)</script>', text)
    for i, s in enumerate(scripts):
        if 'bName' in s:
            print(f"\nScript {i} has bName:")
            # 尝试用 GBK 重新解读这个脚本内容
            try:
                # 先找到 JSON 字符串
                match = re.search(r'({"pageContext".+?"records".+?})\s*$', s, re.DOTALL)
                if match:
                    json_str = match.group(1)
                    # 尝试用不同编码解读
                    json_bytes = json_str.encode('utf-8')
                    print(f"JSON as UTF-8 bytes[:100]: {json_bytes[:100]}")

                    # 检查是否有高位字节
                    high_bytes = [b for b in json_bytes if b > 127]
                    if high_bytes:
                        print(f"Contains {len(high_bytes)} high bytes")
            except Exception as e:
                print(f"Error: {e}")

if __name__ == '__main__':
    asyncio.run(main())