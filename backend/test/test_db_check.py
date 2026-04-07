#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import asyncio
import sys
import io
sys.path.insert(0, '..')

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

from app.db.session import AsyncSessionLocal
from app.repositories.trend_repository import TrendSnapshotRepository, RankingBookRepository

async def check():
    async with AsyncSessionLocal() as session:
        snapshot_repo = TrendSnapshotRepository(session)
        book_repo = RankingBookRepository(session)

        # 检查番茄
        snapshot = await snapshot_repo.get_latest_snapshot_any_age('fanqie', 'hot')
        if snapshot:
            print(f'Fanqie hot snapshot: id={snapshot.id}')
            books = await book_repo.get_books_by_snapshot(snapshot.id)
            print(f'Books count: {len(books)}')
            if books:
                for i, b in enumerate(books[:3]):
                    print(f'  {i+1}. tags={repr(b.tags)}, genre={repr(b.genre)}, is_enriched={b.is_enriched}')
        else:
            print('No fanqie hot snapshot found')

        print()

        # 检查起点
        snapshot2 = await snapshot_repo.get_latest_snapshot_any_age('qidian', 'hot')
        if snapshot2:
            print(f'Qidian hot snapshot: id={snapshot2.id}')
            books2 = await book_repo.get_books_by_snapshot(snapshot2.id)
            print(f'Books count: {len(books2)}')
            if books2:
                for i, b in enumerate(books2[:3]):
                    print(f'  {i+1}. tags={repr(b.tags)}, genre={repr(b.genre)}, is_enriched={b.is_enriched}')
        else:
            print('No qidian hot snapshot found')

if __name__ == '__main__':
    asyncio.run(check())