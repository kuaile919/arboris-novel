#!/usr/bin/env python3
"""测试各种可能的 endpoints"""
import asyncio
import httpx

async def test_url(method, url, headers=None, name=""):
    """测试单个URL"""
    print(f"\n测试 [{method.upper()}] {name or url}")
    try:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            if method == "get":
                resp = await client.get(url, headers=headers or {})
            else:
                resp = await client.post(url, headers=headers or {})
            print(f"  状态: {resp.status_code}")
            if resp.status_code == 200:
                content_type = resp.headers.get('content-type', '')
                print(f"  类型: {content_type}")
                print(f"  长度: {len(resp.text)}")
                if 'json' in content_type:
                    try:
                        data = resp.json()
                        print(f"  JSON keys: {list(data.keys())[:5]}")
                    except:
                        pass
                else:
                    print(f"  内容片段: {resp.text[:300]}")
            return resp.status_code == 200
    except Exception as e:
        print(f"  错误: {type(e).__name__}: {str(e)[:100]}")
        return False

async def main():
    # 起点测试
    print("=" * 60)
    print("起点测试")
    print("=" * 60)

    qidian_urls = [
        ("get", "https://www.qidian.com/rank/hotsales/", None, "PC热销榜"),
        ("get", "https://m.qidian.com/rank/hotsales", None, "移动端热销"),
        ("get", "https://www.qidian.com/ajax/book/category?gender=male&pageNum=1&pageSize=20", {"Accept": "application/json"}, "API"),
    ]

    for method, url, headers, name in qidian_urls:
        await test_url(method, url, headers, name)

    # 番茄测试
    print("\n" + "=" * 60)
    print("番茄测试")
    print("=" * 60)

    fanqie_urls = [
        ("get", "https://fanqienovel.com/", None, "首页"),
        ("get", "https://fanqienovel.com/rank", None, "排行榜"),
        ("get", "https://api.fanqienovel.com", None, "API根"),
        ("get", "https://fanqie.qq.com/", None, "番茄QQ"),
    ]

    for method, url, headers, name in fanqie_urls:
        await test_url(method, url, headers, name)

if __name__ == "__main__":
    asyncio.run(main())
