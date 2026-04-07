#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""查找并下载混淆字体"""
import sys
import io
sys.path.insert(0, '..')

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

def main():
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        # 拦截所有 CSS 和字体请求
        css_urls = set()
        font_urls = set()

        def handle_response(response):
            url = response.url
            content_type = response.headers.get('content-type', '')
            if 'css' in content_type or url.endswith('.css'):
                css_urls.add(url)
            if any(ext in url for ext in ['.woff2', '.woff', '.ttf', '.otf']):
                font_urls.add(url)

        page.on("response", handle_response)

        page.goto("https://fanqienovel.com/rank", wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(5000)

        print(f"CSS URLs ({len(css_urls)}):")
        for url in list(css_urls)[:5]:
            print(f"  {url}")

        print(f"\nFont URLs ({len(font_urls)}):")
        for url in font_urls:
            print(f"  {url}")

        # 查找包含 font-DNMrHsV173Pd4pgy 的 CSS
        font_face_script = """
        () => {
            // 查找所有样式表
            const styleSheets = document.styleSheets;
            const results = [];

            for (let i = 0; i < styleSheets.length; i++) {
                try {
                    const sheet = styleSheets[i];
                    const rules = sheet.cssRules || sheet.rules;
                    if (!rules) continue;

                    for (let j = 0; j < rules.length; j++) {
                        const rule = rules[j];
                        if (rule.type === CSSRule.FONT_FACE_RULE) {
                            const style = rule.style;
                            const fontFamily = style.getPropertyValue('font-family');
                            const src = style.getPropertyValue('src');
                            if (fontFamily.includes('DNMrHsV173Pd4pgy')) {
                                results.push({
                                    fontFamily: fontFamily,
                                    src: src
                                });
                            }
                        }
                    }
                } catch (e) {
                    // 跨域样式表可能无法访问
                }
            }
            return results;
        }
        """
        font_faces = page.evaluate(font_face_script)
        print(f"\n找到的混淆字体 ({len(font_faces)}):")
        for ff in font_faces:
            print(f"  font-family: {ff['fontFamily']}")
            print(f"  src: {ff['src'][:200]}...")

        browser.close()

if __name__ == '__main__':
    main()