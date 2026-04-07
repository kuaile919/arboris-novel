# AIMETA P=趋势数据仓库_排行榜CRUD|R=排行榜数据存取|NR=不含业务逻辑|E=TrendRepository|X=internal|A=仓库类|D=sqlalchemy|S=db|RD=./README.ai
from datetime import datetime, timedelta
from typing import Any, Optional

from sqlalchemy import JSON, delete, desc, select, func
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.trend import TrendSnapshot, RankingBook, TrendReport
from .base import BaseRepository


class TrendSnapshotRepository(BaseRepository[TrendSnapshot]):
    """排行榜快照数据访问。"""

    model = TrendSnapshot

    async def get_latest_snapshot(
        self, platform: str, category: str, max_age_hours: int = 6
    ) -> Optional[TrendSnapshot]:
        """获取平台+分类的最新快照，可指定最大年龄。"""
        cutoff = datetime.utcnow() - timedelta(hours=max_age_hours)
        stmt = (
            select(TrendSnapshot)
            .where(
                TrendSnapshot.platform == platform,
                TrendSnapshot.category == category,
                TrendSnapshot.snapshot_date >= cutoff,
            )
            .order_by(desc(TrendSnapshot.snapshot_date))
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def get_latest_snapshot_any_age(
        self, platform: str, category: str
    ) -> Optional[TrendSnapshot]:
        """获取平台+分类的最新快照，不限年龄（降级用）。"""
        stmt = (
            select(TrendSnapshot)
            .where(
                TrendSnapshot.platform == platform,
                TrendSnapshot.category == category,
            )
            .order_by(desc(TrendSnapshot.snapshot_date))
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def delete_by_platform(self, platform: str) -> int:
        """删除指定平台的所有快照，返回删除数量。"""
        stmt = delete(TrendSnapshot).where(TrendSnapshot.platform == platform)
        result = await self.session.execute(stmt)
        return result.rowcount

    async def get_snapshot_ids_by_platform(self, platform: str) -> list[int]:
        """获取指定平台的所有快照ID。"""
        stmt = select(TrendSnapshot.id).where(TrendSnapshot.platform == platform)
        result = await self.session.execute(stmt)
        return [row[0] for row in result.all()]


class RankingBookRepository(BaseRepository[RankingBook]):
    """排行书籍数据访问。"""

    model = RankingBook

    async def get_books_by_snapshot(self, snapshot_id: int) -> list[RankingBook]:
        """获取指定快照的所有书籍。"""
        stmt = (
            select(RankingBook)
            .where(RankingBook.snapshot_id == snapshot_id)
            .order_by(RankingBook.rank)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_genre_distribution(self, snapshot_id: int) -> dict[str, int]:
        """统计指定快照的题材分布。"""
        stmt = (
            select(RankingBook.genre, func.count(RankingBook.id))
            .where(RankingBook.snapshot_id == snapshot_id)
            .group_by(RankingBook.genre)
            .order_by(desc(func.count(RankingBook.id)))
        )
        result = await self.session.execute(stmt)
        return {row[0]: row[1] for row in result.all()}

    async def delete_by_snapshot_ids(self, snapshot_ids: list[int]) -> int:
        """删除指定快照ID的所有书籍，返回删除数量。"""
        if not snapshot_ids:
            return 0
        stmt = delete(RankingBook).where(RankingBook.snapshot_id.in_(snapshot_ids))
        result = await self.session.execute(stmt)
        return result.rowcount


class TrendReportRepository(BaseRepository[TrendReport]):
    """趋势报告数据访问。"""

    model = TrendReport

    async def get_latest_report(self, platform: str, category: str = "all") -> Optional[TrendReport]:
        """获取平台指定分类的最新趋势报告。"""
        stmt = (
            select(TrendReport)
            .where(
                TrendReport.platform == platform,
                TrendReport.category == category,
            )
            .order_by(desc(TrendReport.report_date))
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def get_latest_report_any_category(self, platform: str) -> Optional[TrendReport]:
        """获取平台任意分类下最新的一份趋势报告。"""
        stmt = (
            select(TrendReport)
            .where(TrendReport.platform == platform)
            .order_by(desc(TrendReport.report_date))
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def get_all_platforms_latest(self, category: str = "all") -> list[TrendReport]:
        """获取所有平台指定分类的最新报告。"""
        stmt = select(TrendReport).distinct(TrendReport.platform).order_by(
            TrendReport.platform, desc(TrendReport.report_date)
        )
        if category:
            stmt = stmt.where(TrendReport.category == category)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def delete_by_platform(self, platform: str) -> int:
        """删除指定平台的所有报告，返回删除数量。"""
        stmt = delete(TrendReport).where(TrendReport.platform == platform)
        result = await self.session.execute(stmt)
        return result.rowcount
