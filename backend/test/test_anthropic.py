#!/usr/bin/env python3
"""测试 Anthropic API 连接"""

import asyncio
import os
import sys

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv()

async def test_anthropic():
    from anthropic import AsyncAnthropic

    api_key = os.getenv("ZHIPU_API_KEY")
    base_url = os.getenv("ZHIPU_BASE_URL")
    model = os.getenv("ZHIPU_MODEL_NAME", "glm-5")

    print(f"API Key: {api_key[:20]}...")
    print(f"Base URL: {base_url}")
    print(f"Model: {model}")
    print("-" * 40)

    client = AsyncAnthropic(api_key=api_key, base_url=base_url)

    try:
        print("发送测试请求...")
        response = await client.messages.create(
            model=model,
            max_tokens=100,
            messages=[
                {"role": "user", "content": "请用一句话介绍你自己"}
            ]
        )
        print(f"响应: {response.content[0].text}")
        print(f"停止原因: {response.stop_reason}")
        print("\n测试成功!")
        return True
    except Exception as e:
        print(f"错误: {type(e).__name__}: {e}")
        return False

if __name__ == "__main__":
    success = asyncio.run(test_anthropic())
    sys.exit(0 if success else 1)
