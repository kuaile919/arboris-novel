#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""检查数据库中的关键词"""
import asyncio
import sys
import io
sys.path.insert(0, '..')

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

from app.services.trend.analysis_service import TrendAnalysisService
from app.db.session import AsyncSessionLocal

async def check():
    async with AsyncSessionLocal() as session:
        service = TrendAnalysisService(session)

        # 检查关键词
        keywords = await service.get_hot_keywords('qidian', 'hot')
        print(f'Qidian hot keywords: {keywords[:10]}')

        keywords2 = await service.get_hot_keywords('fanqie', 'hot')
        print(f'Fanqie hot keywords: {keywords2[:10]}')

        # 检查报告
        report = await service.get_trend_report('qidian')
        print(f'\nQidian report hot_keywords: {report.get("hot_keywords", [])[:10]}')

        report2 = await service.get_trend_report('fanqie')
        print(f'Fanqie report hot_keywords: {report2.get("hot_keywords", [])[:10]}')

if __name__ == '__main__':
    asyncio.run(check())