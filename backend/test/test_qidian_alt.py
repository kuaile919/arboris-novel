#!/usr/bin/env python3
"""测试起点网站 - 尝试不同方法"""
import asyncio
import httpx

async def test_with_client(name, client_config, url="https://www.qidian.com"):
    """使用不同配置测试"""
    print(f"\n测试: {name}")
    try:
        async with httpx.AsyncClient(**client_config) as client:
            resp = await client.get(url)
            print(f"  成功! 状态: {resp.status_code}")
            print(f"  内容长度: {len(resp.text)}")
            return True
    except Exception as e:
        print(f"  失败: {type(e).__name__}: {str(e)[:100]}")
        return False

async def main():
    configs = [
        ("默认配置", {"timeout": 10.0, "follow_redirects": True}),
        ("禁用HTTP/2", {"timeout": 10.0, "follow_redirects": True, "http2": False}),
        ("仅IPv4", {"timeout": 10.0, "follow_redirects": True, "transport": httpx.AsyncHTTPTransport(local_address="0.0.0.0")}),
        ("不验证SSL", {"timeout": 10.0, "follow_redirects": True, "verify": False}),
    ]

    print("测试不同配置访问起点...")
    for name, config in configs:
        await test_with_client(name, config)

    # 测试移动端
    print("\n测试移动端 m.qidian.com...")
    mobile_headers = {
        "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15",
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": "zh-CN,zh;q=0.9",
    }
    try:
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            resp = await client.get("https://m.qidian.com", headers=mobile_headers)
            print(f"  成功! 状态: {resp.status_code}")
            print(f"  内容前200字符: {resp.text[:200]}")
    except Exception as e:
        print(f"  失败: {type(e).__name__}: {str(e)[:100]}")

if __name__ == "__main__":
    asyncio.run(main())
