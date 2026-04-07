#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""检查 CFF strings 和其他可能的字符信息"""
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
    cff_data = cff.cff
    td = cff_data['SourceHanSansSCNormal']

    # 检查 strings
    print(f"strings 属性: {type(td.strings)}")
    if hasattr(td, 'strings') and td.strings:
        strings = td.strings
        print(f"  数量: {len(strings)}")

        # 检查是否有实际的字符字符串
        for i in range(min(50, len(strings))):
            try:
                s = strings[i]
                if isinstance(s, bytes):
                    print(f"  [{i}]: bytes({len(s)}): {s[:50]}")
                elif isinstance(s, str):
                    print(f"  [{i}]: str({len(s)}): {repr(s[:50])}")
                else:
                    print(f"  [{i}]: {type(s)}: {s}")
            except Exception as e:
                print(f"  [{i}]: error: {e}")
    else:
        print("  没有 strings 或为空")

    # 检查 numGlyphs
    if hasattr(td, 'numGlyphs'):
        print(f"\nnumGlyphs: {td.numGlyphs}")

    # 检查 rawDict
    if hasattr(td, 'rawDict'):
        print(f"\nrawDict: {td.rawDict}")

    # 尝试直接渲染 glyph 看能否获取信息
    # 检查 CFF CharStrings
    if hasattr(cff, 'CharStrings'):
        cs = cff.CharStrings
        print(f"\nCharStrings: {len(cs)} entries")
        # 看看能不能获取 gid58344 的 CharString
        if 'gid58344' in cs.keys():
            charstring = cs['gid58344']
            print(f"  gid58344 CharString 长度: {len(charstring.program) if hasattr(charstring, 'program') else 'unknown'}")

    font.close()

if __name__ == '__main__':
    main()