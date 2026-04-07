#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import re

with open('qidian_mobile_debug.html', 'r', encoding='utf-8') as f:
    html = f.read()

print(f"HTML length: {len(html)}")

# 检查是否有特殊编码
if 'window.__INITIAL' in html:
    print('window.__INITIAL found')
else:
    print('window.__INITIAL NOT found')

# 查找 pageData
if 'pageData' in html:
    print('pageData found')
    idx = html.find('pageData')
    print(f'Context: ...{html[idx-50:idx+150]}...')
else:
    print('pageData NOT found')

# 检查 records
if 'records' in html:
    print('records found')
    idx = html.find('"records"')
    print(f'Context: ...{html[idx-50:idx+150]}...')
else:
    print('records NOT found')

# 查找 script 标签
script_pattern = r'<script[^>]*>([^<]+)</script>'
scripts = re.findall(script_pattern, html)
print(f'\nFound {len(scripts)} script tags')

for i, s in enumerate(scripts):
    if 'bName' in s or 'records' in s:
        print(f'\nScript {i} has data:')
        print(s[:500])