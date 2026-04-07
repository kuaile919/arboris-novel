# AIMETA P=趋势数据模型_排行榜快照和书籍|R=排行榜存储_趋势分析|NR=不含业务逻辑|E=TrendSnapshot_RankingBook_TrendReport|X=internal|A=ORM模型|D=sqlalchemy|S=none|RD=./README.ai
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.dialects.mysql import LONGTEXT
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db.base import Base

LONG_TEXT_TYPE = Text().with_variant(LONGTEXT, "mysql")


class TrendSnapshot(Base):
    """排行榜数据快照，每次抓取后存储一份。"""

    __tablename__ = "trend_snapshots"
    __table_args__ = (
        Index("ix_trend_snapshots_platform_category_date", "platform", "category", "snapshot_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    platform: Mapped[str] = mapped_column(String(32), nullable=False, comment="平台标识: qidian/fanqie")
    category: Mapped[str] = mapped_column(String(32), nullable=False, comment="榜单分类: hot/monthly/weekly")
    snapshot_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    raw_data: Mapped[Optional[dict]] = mapped_column(JSON, comment="原始抓取数据")
    data_source: Mapped[str] = mapped_column(String(32), nullable=False, default="scraping", comment="数据来源: api/scraping/manual/cache")
    data_quality_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0, comment="数据质量评分 0-1")
    fetch_duration_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="抓取耗时毫秒")
    error_message: Mapped[Optional[str]] = mapped_column(String(512), comment="错误信息")
    books: Mapped[list["RankingBook"]] = relationship(
        back_populates="snapshot", cascade="all, delete-orphan", order_by="RankingBook.rank"
    )


class RankingBook(Base):
    """排行书籍条目。"""

    __tablename__ = "ranking_books"
    __table_args__ = (
        Index("ix_ranking_books_snapshot_id_rank", "snapshot_id", "rank"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    snapshot_id: Mapped[int] = mapped_column(ForeignKey("trend_snapshots.id", ondelete="CASCADE"), nullable=False)
    rank: Mapped[int] = mapped_column(Integer, nullable=False, comment="排名")
    title: Mapped[str] = mapped_column(String(255), nullable=False, comment="书名")
    author: Mapped[str] = mapped_column(String(128), nullable=False, default="", comment="作者")
    genre: Mapped[str] = mapped_column(String(64), nullable=False, default="", comment="题材分类")
    word_count: Mapped[str] = mapped_column(String(32), nullable=False, default="", comment="字数")
    description: Mapped[Optional[str]] = mapped_column(LONG_TEXT_TYPE, comment="简介")
    tags: Mapped[Optional[str]] = mapped_column(String(512), comment="逗号分隔标签")
    heat_score: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="热度值")
    cover_url: Mapped[Optional[str]] = mapped_column(String(512), comment="封面URL")
    book_url: Mapped[Optional[str]] = mapped_column(String(512), comment="书籍详情页URL")
    is_enriched: Mapped[bool] = mapped_column(default=False, comment="是否经过LLM补全")
    original_data: Mapped[Optional[dict]] = mapped_column(JSON, comment="原始数据备份")

    snapshot: Mapped["TrendSnapshot"] = relationship(back_populates="books")


class TrendReport(Base):
    """趋势分析报告，由 LLM 生成。"""

    __tablename__ = "trend_reports"
    __table_args__ = (
        Index("ix_trend_reports_platform_category_date", "platform", "category", "report_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    platform: Mapped[str] = mapped_column(String(32), nullable=False, comment="平台标识")
    category: Mapped[str] = mapped_column(String(64), nullable=False, default="all", comment="榜单分类")
    report_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    genre_distribution: Mapped[Optional[dict]] = mapped_column(JSON, comment="题材分布统计")
    hot_keywords: Mapped[Optional[list]] = mapped_column(JSON, comment="热门关键词列表")
    trend_summary: Mapped[Optional[str]] = mapped_column(LONG_TEXT_TYPE, comment="LLM分析摘要")
    ai_full_report: Mapped[Optional[str]] = mapped_column(LONG_TEXT_TYPE, comment="LLM完整报告")
    hot_elements: Mapped[Optional[list]] = mapped_column(JSON, comment="热门元素列表")
    reader_preferences: Mapped[Optional[dict]] = mapped_column(JSON, comment="读者偏好")
    opportunities: Mapped[Optional[list]] = mapped_column(JSON, comment="创作机会")
    creation_suggestions: Mapped[Optional[list]] = mapped_column(JSON, comment="创作建议列表")
