#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""测试字体文件分析"""
import sys
import io
sys.path.insert(0, '..')

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

def main():
    from playwright.sync_api import sync_playwright

    font_data = {}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        def handle_response(response):
            url = response.url
            if any(ext in url for ext in ['.woff2', '.woff', '.ttf', '.otf']):
                try:
                    font_data[url] = response.body()
                    print(f"拦截到字体文件: {url}")
                    print(f"  大小: {len(font_data[url])} bytes")
                except Exception as e:
                    print(f"字体拦截失败: {e}")

        page.on("response", handle_response)

        page.goto("https://fanqienovel.com/rank", wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(5000)

        browser.close()

    print(f"\n共拦截到 {len(font_data)} 个字体文件")

    # 尝试解析字体
    try:
        from fontTools.ttLib import TTFont
        from io import BytesIO
    except ImportError:
        print("fonttools 未安装")
        return

    for url, data in font_data.items():
        try:
            font = TTFont(BytesIO(data))
            print(f"\n分析字体: {url}")

            # 打印所有表
            print(f"  字体表: {list(font.keys())}")

            # 尝试访问 cmap 表
            try:
                cmap_table = font['cmap']
                print(f"  cmap 表存在")

                if hasattr(cmap_table, 'tables'):
                    for table in cmap_table.tables:
                        print(f"    format: {table.format}")
                        if hasattr(table, 'cmap'):
                            pua_mappings = {}
                            for codepoint, glyph_name in table.cmap.items():
                                if 0xE000 <= codepoint <= 0xF8FF:
                                    pua_mappings[codepoint] = glyph_name
                            print(f"    PUA 字符数量: {len(pua_mappings)}")
                            if pua_mappings:
                                for i, (cp, gn) in enumerate(list(pua_mappings.items())[:10]):
                                    print(f"      U+{cp:04X} -> {gn}")
            except Exception as e:
                print(f"  cmap 访问失败: {e}")

            # 检查 post 表
            try:
                post_table = font['post']
                print(f"  post 表存在, 格式: {post_table.format}")
                if hasattr(post_table, 'glyphOrder'):
                    glyph_order = post_table.glyphOrder
                    print(f"    glyphOrder 前20个: {glyph_order[:20]}")
            except Exception as e:
                print(f"  post 访问失败: {e}")

            # 检查 name 表
            try:
                name_table = font['name']
                print(f"  name 表存在:")
                for record in name_table.names:
                    if record.nameID in [1, 4, 5, 6] and record.platformID == 3:  # Windows names
                        try:
                            print(f"    nameID {record.nameID}: {record.toUnicode()}")
                        except:
                            pass
            except Exception as e:
                print(f"  name 访问失败: {e}")

            # 检查 CFF 表
            try:
                cff_table = font['CFF ']
                print(f"  CFF 表存在")
                # 获取 CFF 字体的主字体
                if hasattr(cff_table, 'cff'):
                    cff = cff_table.cff
                    for font_name in cff.keys():
                        top_dict = cff[font_name]
                        print(f"    字体: {font_name}")
                        if hasattr(top_dict, 'charset'):
                            charset = top_dict.charset
                            print(f"    charset 总数: {len(charset)}")

                        # 获取 GlyphOrder
                        glyph_order = font.getGlyphOrder()
                        print(f"    GlyphOrder 总数: {len(glyph_order)}")
                        print(f"    GlyphOrder 前10个: {glyph_order[:10]}")

                        # 从 cmap 获取正确的 glyph ID
                        if hasattr(font, 'cmap'):
                            best_cmap = font['cmap'].getBestCmap()
                            if best_cmap:
                                # 找几个 PUA 字符看看
                                for pua in [0xE3E8, 0xE49C, 0xE500]:
                                    if pua in best_cmap:
                                        gid = best_cmap[pua]
                                        print(f"    U+{pua:04X} -> glyph ID {gid}")
                                        # 通过 GlyphOrder 找 glyph 名称
                                        if gid < len(glyph_order):
                                            gname = glyph_order[gid]
                                            print(f"      -> glyph name: {gname}")
                                            # 在 charset 中找这个 glyph 的索引
                                            if hasattr(top_dict, 'charset') and gid < len(top_dict.charset):
                                                charset_gid = top_dict.charset[gid]
                                                print(f"      -> charset[{gid}] = {charset_gid}")
            except Exception as e:
                print(f"  CFF 访问失败: {e}")
                import traceback
                traceback.print_exc()
                print("  cmap 表存在")
                for table in font['cmap'].tables:
                    if hasattr(table, 'cmap'):
                        pua_mappings = {}
                        for codepoint, glyph_name in table.cmap.items():
                            if 0xE000 <= codepoint <= 0xF8FF:
                                pua_mappings[codepoint] = glyph_name

                        print(f"  PUA 字符数量: {len(pua_mappings)}")
                        if pua_mappings:
                            print("  前10个 PUA 映射:")
                            for i, (cp, gn) in enumerate(list(pua_mappings.items())[:10]):
                                print(f"    U+{cp:04X} -> {gn}")
            else:
                print("  无 cmap 表")

            # 检查 name 表
            if hasattr(font, 'name'):
                print("  name 表存在:")
                for record in font['name'].names:
                    if record.nameID in [1, 4, 5, 6]:  # font family, full name, version, postscript name
                        try:
                            print(f"    nameID {record.nameID}: {record.toUnicode()}")
                        except:
                            pass

        except Exception as e:
            print(f"  解析失败: {e}")
            import traceback
            traceback.print_exc()

if __name__ == '__main__':
    main()