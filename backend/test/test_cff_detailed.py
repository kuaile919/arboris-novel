#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""深入分析 CFF 字体"""
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

    # 获取 CFF 数据
    cff = font['CFF ']

    # 尝试访问 CFF 字体对象
    print("CFF 属性:")
    for attr in dir(cff):
        if not attr.startswith('_'):
            print(f"  {attr}")

    # 获取字符映射
    best_cmap = font['cmap'].getBestCmap()

    # PUA 范围
    pua_chars = [(cp, gid) for cp, gid in best_cmap.items() if 0xE000 <= cp <= 0xF8FF]
    print(f"\n共有 {len(pua_chars)} 个 PUA 字符映射")

    # 检查这些 PUA 对应的 glyph ID
    # glyph ID 是以字符串形式存储的，如 "gid58344"
    sample_pua = [(0xE3E8, 'gid58344'), (0xE49C, None), (0xE500, None)]
    print("\n样本 PUA 字符:")
    for pua, expected_gid in sample_pua:
        if pua in best_cmap:
            gid = best_cmap[pua]
            print(f"  U+{pua:04X} -> {gid}")

    # 看看 glyph ID 如何编码
    # 在 fonttools 中，gid 通常是数字，不是字符串
    # 但这里显示为 "gid58344" 说明它被存储为了字符串

    # 让我检查 GlyphOrder
    glyph_order = font.getGlyphOrder()
    print(f"\nGlyphOrder 长度: {len(glyph_order)}")
    print(f"GlyphOrder[0-10]: {glyph_order[:10]}")

    # 找到 gid58344 在 GlyphOrder 中的位置
    gid_name = 'gid58344'
    if gid_name in glyph_order:
        gid_index = glyph_order.index(gid_name)
        print(f"\n'{gid_name}' 在 GlyphOrder 中的索引: {gid_index}")

    # 另一个角度：CFF 字体的 CharStrings 映射
    # 每个 glyph 都有一个 CharString，其中包含绘制指令
    if hasattr(cff, 'CharStrings'):
        char_strings = cff.CharStrings
        print(f"\nCharStrings 条目数: {len(char_strings)}")
        # 看看能否找到 gid58344
        if 'gid58344' in char_strings.keys():
            print("  找到 gid58344")

    font.close()

if __name__ == '__main__':
    main()