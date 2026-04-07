#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""最终验证 - 重新获取并解析"""
import asyncio
import sys
import io
import re
import json
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
        html = resp.text

    print(f"HTML length: {len(html)}")

    # 直接搜索 bName 来验证
    if '捞尸人' in html:
        print("UTF-8 Chinese '捞尸人' found in HTML!")
    else:
        print("'捞尸人' NOT found")

    # 搜索 \u8D9E\u65E0\u5883 这样的转义序列
    if '\\u' in html:
        print("Contains \\u escape sequences")

    # 尝试直接用正则提取 JSON
    # 查找 {"pageContext":...} 模式
    pattern = r'\{"pageContext":(.+?)\}\s*;?\s*$'
    match = re.search(pattern, html, re.DOTALL)
    if match:
        print(f"\nFound pageContext JSON, length: {len(match.group(0))}")
        json_str = match.group(0)
        # 尝试解析
        try:
            # 可能需要补全大括号
            full_json = '{"pageContext":' + match.group(1)
            # 检查是否以 } 结尾
            if not full_json.rstrip().endswith('}'):
                full_json += '}'
            data = json.loads(full_json)
            print("JSON parsed!")

            records = data.get("pageContext", {}).get("pageProps", {}).get("pageData", {}).get("records", [])
            print(f"Records count: {len(records)}")

            if records:
                first = records[0]
                print(f"\nFirst book:")
                print(f"  title: {first.get('bName')}")
                print(f"  author: {first.get('bAuth')}")
                print(f"  genre: {first.get('cat')}")
                print(f"  word_count: {first.get('cnt')}")
                print(f"  desc: {first.get('desc', '')[:50]}")
        except json.JSONDecodeError as e:
            print(f"JSON parse failed: {e}")
    else:
        print("pageContext JSON not found")
        # 尝试更宽泛的搜索
        if 'pageContext' in html:
            print("pageContext keyword found")
            idx = html.find('pageContext')
            print(f"Context: {html[idx:idx+200]}")

if __name__ == '__main__':
    asyncio.run(main())