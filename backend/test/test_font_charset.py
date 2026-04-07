#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""分析 CFF 字体的 charset"""
import sys
import io
sys.path.insert(0, '..')

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

def main():
    from fontTools.ttLib import TTFont
    from io import BytesIO
    import urllib.request

    # 下载字体文件
    font_url = "https://lf6-awef.bytetos.com/obj/awesome-font/c/dc027189e0ba4cd.woff2"
    print(f"下载字体: {font_url}")
    response = urllib.request.urlopen(font_url, timeout=30)
    font_data = response.read()
    print(f"字体大小: {len(font_data)} bytes")

    font = TTFont(BytesIO(font_data))
    print(f"字体表: {list(font.keys())}")

    # 检查 cmap
    cmap_table = font['cmap']
    print(f"\nCmap tables:")
    for table in cmap_table.tables:
        print(f"  platformID: {table.platformID}, encodingID: {table.platEncID}, format: {table.format}")

    # 获取 best cmap
    best_cmap = cmap_table.getBestCmap()
    if best_cmap:
        print(f"\nBestCmap 共有 {len(best_cmap)} 个映射")

        # 找几个 PUA 看它们映射到什么
        print("\nPUA 字符映射示例:")
        for i, (cp, gid) in enumerate(sorted(best_cmap.items())):
            if 0xE000 <= cp <= 0xF8FF and i < 10:
                print(f"  U+{cp:04X} (dec {cp}) -> glyph ID {gid}")

    # 检查 CFF 字体的结构
    print("\n检查 CFF 字体结构:")
    cff = font['CFF ']
    print(f"  CFF 类型: {type(cff)}")

    # 获取 TopDict
    if hasattr(cff, 'TopDict'):
        td = cff.TopDict
        print(f"  TopDict: {td}")
        if hasattr(td, 'charset'):
            charset = td.charset
            print(f"  charset 条目数: {len(charset)}")
            for i in range(min(10, len(charset))):
                print(f"    [{i}]: {charset[i]}")

    # 检查 post 表
    if hasattr(font, 'post'):
        post = font['post']
        print(f"\npost 表:")
        print(f"  format: {post.format}")
        if hasattr(post, 'glyphOrder'):
            go = post.glyphOrder
            print(f"  glyphOrder 长度: {len(go)}")
            print(f"  前10个: {go[:10]}")

    font.close()

if __name__ == '__main__':
    main()