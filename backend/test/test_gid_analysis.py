#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""分析 gidXXXXX 数字和 PUA codepoint 的关系"""
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
    response = urllib.request.urlopen(font_url, timeout=30)
    font_data = response.read()

    font = TTFont(BytesIO(font_data))

    # 获取 best cmap
    best_cmap = font['cmap'].getBestCmap()

    # 获取 GlyphOrder
    glyph_order = font.getGlyphOrder()

    print("分析 gid 和 PUA codepoint 的关系:")
    print("=" * 60)

    for pua_cp in sorted(best_cmap.keys()):
        if 0xE000 <= pua_cp <= 0xF8FF:
            gid = best_cmap[pua_cp]  # e.g., 'gid58344'

            # 提取 gid 中的数字
            if gid.startswith('gid'):
                gid_num = int(gid[3:])  # e.g., 58344

                # 检查关系
                print(f"\nPUA U+{pua_cp:04X} (dec {pua_cp}) -> gid{gid_num}")
                print(f"  PUA hex: 0x{pua_cp:04X} = {pua_cp}")
                print(f"  gid 数字: {gid_num}")

                if pua_cp == gid_num:
                    print(f"  结论: PUA codepoint == gid 数字 (直接映射)")
                else:
                    diff = abs(pua_cp - gid_num)
                    print(f"  差值: {diff}")

    # 检查 GlyphOrder 中的 gid 是否和索引有关系
    print("\n" + "=" * 60)
    print("检查 GlyphOrder 索引和 gid 数字的关系:")
    for i in range(min(10, len(glyph_order))):
        name = glyph_order[i]
        if name.startswith('gid'):
            gid_num = int(name[3:])
            print(f"  GlyphOrder[{i}] = {name}, gid数字 = {gid_num}, 差值 = {abs(i - gid_num)}")

    font.close()

if __name__ == '__main__':
    main()