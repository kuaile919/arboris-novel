#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""使用 Playwright 渲染 PUA 字符到 Canvas 并提取"""
import sys
import io
sys.path.insert(0, '..')

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

def main():
    from playwright.sync_api import sync_playwright
    import json

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        # 加载页面
        page.goto("https://fanqienovel.com/rank", wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(5000)

        # 获取页面上实际显示的书名
        script = """
        () => {
            // 找到排行榜中的书名
            const books = document.querySelectorAll('.book-title, .title, [class*="title"]');
            const results = [];
            books.forEach((book, i) => {
                if (i < 5) {
                    results.push({
                        text: book.textContent.trim(),
                        html: book.innerHTML
                    });
                }
            });
            return results;
        }
        """
        results = page.evaluate(script)
        print("页面上的书名:")
        for r in results:
            print(f"  text: {r['text']}")
            print(f"  html: {r['html'][:100]}...")
            print()

        # 获取 computed font-family
        font_script = """
        () => {
            const el = document.querySelector('[class*="title"], [class*="book"]');
            if (el) {
                const style = window.getComputedStyle(el);
                return {
                    fontFamily: style.fontFamily,
                    fontSize: style.fontSize,
                    fontWeight: style.fontWeight
                };
            }
            return null;
        }
        """
        font_info = page.evaluate(font_script)
        print(f"字体信息: {font_info}")

        browser.close()

if __name__ == '__main__':
    main()