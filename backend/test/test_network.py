#!/usr/bin/env python3
"""测试网络连接"""
import asyncio
import httpx

async def test_url(url, name):
    """测试单个URL"""
    print(f"\n测试 {name}: {url}")
    try:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            resp = await client.get(url, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            })
            print(f"  状态: {resp.status_code}")
            print(f"  成功!")
            return True
    except Exception as e:
        print(f"  失败: {type(e).__name__}: {e}")
        return False

async def main():
    urls = [
        ("https://www.baidu.com", "百度"),
        ("https://www.qidian.com", "起点"),
        ("https://fanqienovel.com", "番茄"),
    ]

    results = []
    for url, name in urls:
        success = await test_url(url, name)
        results.append((name, success))

    print("\n" + "="*40)
    print("测试结果:")
    for name, success in results:
        status = "通过" if success else "失败"
        print(f"  {name}: {status}")

if __name__ == "__main__":
    asyncio.run(main())
