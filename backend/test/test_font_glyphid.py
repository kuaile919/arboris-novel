#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""找出 glyph ID 对应的实际字符"""
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

    # 获取 CFF 主字体
    cff_data = cff.cff
    print(f"CFF fonts: {list(cff_data.keys())}")

    for font_name in cff_data.keys():
        td = cff_data[font_name]
        print(f"\n字体: {font_name}")
        print(f"  TopDict 属性: {[a for a in dir(td) if not a.startswith('_')]}")

        # charset 映射 glyph ID 到 SID (String ID)
        if hasattr(td, 'charset'):
            charset = td.charset
            print(f"  charset 长度: {len(charset)}")

            # charset[0] = .notdef, charset[1] = SID for glyph 1, etc.
            # SID 映射到实际的字符串（在 CFF 的 String INDEX 中）

            # 获取 Strings
            if hasattr(td, 'Strings'):
                strings = td.Strings
                print(f"  Strings 长度: {len(strings)}")

                # 打印前几个字符串
                for i in range(min(20, len(strings))):
                    try:
                        s = strings[i]
                        print(f"    [{i}]: {repr(s)}")
                    except:
                        pass

            # 找到 gid58344 对应的索引
            glyph_order = font.getGlyphOrder()
            if 'gid58344' in glyph_order:
                gid_index = glyph_order.index('gid58344')
                print(f"\n  gid58344 的 glyph 索引: {gid_index}")

                # charset[gid_index] 应该给出 SID
                if gid_index < len(charset):
                    sid = charset[gid_index]
                    print(f"  charset[{gid_index}] (SID): {sid}")

                    # SID 映射到字符串
                    if hasattr(td, 'Strings') and sid < len(td.Strings):
                        char_string = td.Strings[sid]
                        print(f"  对应字符串: {repr(char_string)}")

                        # 尝试解析为 Unicode
                        if len(char_string) == 1:
                            print(f"  作为 Unicode 字符: {char_string} (U+{ord(char_string):04X})")
                        elif len(char_string) > 1:
                            # 可能是多字符字符串
                            print(f"  字符串长度: {len(char_string)}")

    font.close()

if __name__ == '__main__':
    main()