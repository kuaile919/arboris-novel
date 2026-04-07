#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""检查文件实际字节"""
with open('qidian_mobile_debug.html', 'rb') as f:
    raw = f.read()

print(f"File size: {len(raw)} bytes")

# 查找 bName 的位置
bName_idx = raw.find(b'"bName"')
if bName_idx >= 0:
    print(f"\nbName found at position {bName_idx}")
    # 显示周围的字节
    context = raw[bName_idx-20:bName_idx+100]
    print(f"Context bytes: {context}")
    print(f"Context as hex: {context.hex()}")

    # bName 后面跟着的值
    value_idx = raw.find(b'"', bName_idx + 6)
    if value_idx >= 0:
        value = raw[value_idx+1:value_idx+20]
        print(f"Value bytes: {value}")
        print(f"Value as hex: {value.hex()}")

        # 尝试不同解码
        for enc in ['utf-8', 'gbk', 'gb2312']:
            try:
                decoded = value.decode(enc)
                print(f"As {enc}: {decoded}")
            except:
                print(f"As {enc}: FAILED")

# 检查是否存在 UTF-8  BOM 或其他标记
if raw.startswith(b'\xef\xbb\xbf'):
    print("\nFile starts with UTF-8 BOM")
else:
    print(f"\nFile starts with: {raw[:20].hex()}")

# 检查 0xaf 字节位置（之前 GBK 解码失败的位置）
af_count = raw.count(b'\xaf')
print(f"\n0xAF byte count: {af_count}")
if af_count > 0:
    af_idx = raw.find(b'\xaf')
    print(f"First 0xAF context: {raw[af_idx-10:af_idx+10].hex()}")