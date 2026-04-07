#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""测试 Brotli 压缩内容的实际编码"""
import asyncio
import sys
import io
import brotli
sys.path.insert(0, '..')

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import httpx

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) "
        "Version/16.6 Mobile/15E148 Safari/604.1"
    ),
    "Accept-Encoding": "gzip, deflate, br",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9",
    "Referer": "https://m.qidian.com/",
}

async def main():
    url = "https://m.qidian.com/rank/hotsales/"

    # 不自动解码，直接获取原始内容
    async with httpx.AsyncClient(
        headers=HEADERS,
        timeout=15.0,
        follow_redirects=True,
        cookies=httpx.Cookies()
    ) as client:
        # 设置不自动解压缩
        resp = await client.get(url)
        raw_content = resp.content

    print(f"Raw content length: {len(raw_content)}")
    print(f"First 100 bytes: {raw_content[:100]}")

    # 尝试 Brotli 解压
    try:
        decompressed = brotli.decompress(raw_content)
        print(f"\nBrotli decompressed length: {len(decompressed)}")

        # 尝试 UTF-8 解码
        try:
            text_utf8 = decompressed.decode('utf-8')
            print(f"UTF-8 decode: OK, length={len(text_utf8)}")
            # 检查是否包含中文
            if '捞尸人' in text_utf8:
                print("UTF-8 contains correct Chinese!")
            else:
                # 查找包含 bName 的位置
                idx = text_utf8.find('"bName"')
                if idx >= 0:
                    print(f"bName context (UTF-8): {text_utf8[idx:idx+50]}")
        except UnicodeDecodeError as e:
            print(f"UTF-8 decode failed: {e}")

        # 尝试 GBK 解码
        try:
            text_gbk = decompressed.decode('gbk')
            print(f"\nGBK decode: OK, length={len(text_gbk)}")
            if '捞尸人' in text_gbk:
                print("GBK contains correct Chinese!")
                idx = text_gbk.find('"bName"')
                if idx >= 0:
                    print(f"bName context (GBK): {text_gbk[idx:idx+50]}")
        except UnicodeDecodeError as e:
            print(f"GBK decode failed: {e}")

    except Exception as e:
        print(f"Brotli decompress failed: {e}")

if __name__ == '__main__':
    asyncio.run(main())