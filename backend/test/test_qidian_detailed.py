#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""详细检查起点连接问题"""
import asyncio
import sys
import io
sys.path.insert(0, '..')

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import httpx

# 测试不同端点
URLS = [
    ("PC API", "https://www.qidian.com/ajax/rank/hotsales?page=1", "https://www.qidian.com/"),
    ("Mobile", "https://m.qidian.com/rank/hotsales/", "https://m.qidian.com/"),
    ("PC Page", "https://www.qidian.com/rank/hot/", "https://www.qidian.com/"),
]

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

async def test_url(name, url, referer):
    """测试单个URL"""
    print(f"\n--- Testing {name} ---")
    print(f"URL: {url}")

    headers = HEADERS.copy()
    headers["Referer"] = referer

    try:
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            resp = await client.get(url, headers=headers)
            print(f"Status: {resp.status_code}")
            print(f"Encoding: {resp.encoding}")
            print(f"Content-Type: {resp.headers.get('content-type', '')}")

            content = resp.text
            print(f"Content length: {len(content)}")

            # 检查是否是重定向到其他页面
            if resp.headers.get('location'):
                print(f"Redirect to: {resp.headers.get('location')}")

            # 检查内容样本
            if len(content) < 500:
                print(f"Content: {content[:200]}")
            else:
                print(f"First 200 chars: {content[:200]}")

            return True
    except httpx.ConnectError as e:
        print(f"ConnectError: {e}")
        # 检查是否是代理问题
        return False
    except httpx.TimeoutException as e:
        print(f"Timeout: {e}")
        return False
    except Exception as e:
        print(f"Error: {type(e).__name__}: {e}")
        return False

async def main():
    print("Testing Qidian connections...")

    results = []
    for name, url, referer in URLS:
        success = await test_url(name, url, referer)
        results.append((name, success))
        await asyncio.sleep(1)  # 避免请求太快

    print("\n" + "="*50)
    print("Results:")
    for name, success in results:
        status = "OK" if success else "FAILED"
        print(f"  {name}: {status}")

if __name__ == '__main__':
    asyncio.run(main())