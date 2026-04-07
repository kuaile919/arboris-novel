# AIMETA P=趋势API_排行榜查询和趋势分析|R=排行榜展示_趋势报告_数据刷新|NR=不含爬虫实现|E=route:GET_/api/trends/*|X=http|A=趋势查询|D=fastapi|S=db,net|RD=./README.ai
"""市场风向 API - 网文平台排行榜和趋势分析"""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.dependencies import get_current_user
from ...db.session import get_session
from ...models.user import User
from ...services.trend.scraping_service import TrendScrapingService
from ...services.trend.analysis_service import TrendAnalysisService
from ...repositories.trend_repository import (
    RankingBookRepository,
    TrendReportRepository,
    TrendSnapshotRepository,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/trends", tags=["Trends"])


# ==================== 请求/响应模型 ====================

ALLOWED_PLATFORMS = {"qidian", "fanqie"}


class ManualImportRequest(BaseModel):
    """手动导入请求。"""
    platform: str = Field(..., max_length=32, description="平台标识")
    category: str = Field("manual", max_length=32, description="榜单分类")
    text: str = Field(..., max_length=100000, description="导入文本内容")
    format: str = Field("auto", max_length=16, description="格式: auto | json | text")


class RefreshResponse(BaseModel):
    """刷新响应。"""
    status: str
    message: str
    count: int = 0


class SuggestionRequest(BaseModel):
    """创作建议请求。"""
    context: str = ""


# ==================== 端点 ====================

@router.get("/platforms")
async def list_platforms(
    session: AsyncSession = Depends(get_session),
    _user: User = Depends(get_current_user),
):
    """获取所有支持的平台列表。"""
    service = TrendScrapingService(session)
    return {"platforms": service.get_supported_platforms()}


@router.get("/{platform}/ranking")
async def get_ranking(
    platform: str,
    category: str = Query("hot", description="榜单分类"),
    limit: int = Query(50, ge=1, le=200, description="返回条数"),
    force_refresh: bool = Query(False, description="强制刷新"),
    session: AsyncSession = Depends(get_session),
    _user: User = Depends(get_current_user),
):
    """获取指定平台的排行榜数据。"""
    service = TrendScrapingService(session)

    if platform not in service.scrapers:
        raise HTTPException(status_code=400, detail=f"不支持的平台: {platform}")

    books = await service.get_ranking(platform, category, limit, force_refresh)
    await session.commit()

    return {
        "platform": platform,
        "category": category,
        "count": len(books),
        "books": books,
    }


@router.get("/{platform}/genres")
async def get_genre_distribution(
    platform: str,
    category: str = Query("hot", description="榜单分类"),
    session: AsyncSession = Depends(get_session),
    _user: User = Depends(get_current_user),
):
    """获取题材分布统计。"""
    service = TrendAnalysisService(session)
    result = await service.get_genre_distribution(platform, category)
    await session.commit()
    return result


@router.get("/{platform}/report")
async def get_trend_report(
    platform: str,
    category: str = Query("all", description="榜单分类，all 表示平台总览"),
    force_regenerate: bool = Query(False, description="强制重新生成"),
    session: AsyncSession = Depends(get_session),
    _user: User = Depends(get_current_user),
):
    """获取 AI 趋势分析报告。"""
    service = TrendAnalysisService(session)
    report = await service.get_trend_report(platform, category, force_regenerate)
    await session.commit()
    return report


@router.post("/{platform}/refresh")
async def refresh_ranking(
    platform: str,
    category: str = Query("hot", description="榜单分类"),
    session: AsyncSession = Depends(get_session),
    _user: User = Depends(get_current_user),
):
    """手动触发排行榜数据刷新。"""
    service = TrendScrapingService(session)

    if platform not in service.scrapers:
        raise HTTPException(status_code=400, detail=f"不支持的平台: {platform}")

    books = await service.refresh(platform, category)
    await session.commit()

    return RefreshResponse(
        status="success",
        message=f"刷新成功: {platform}/{category}",
        count=len(books),
    )


@router.post("/refresh-all")
async def refresh_all(
    session: AsyncSession = Depends(get_session),
    _user: User = Depends(get_current_user),
):
    """刷新所有平台数据。"""
    service = TrendScrapingService(session)
    results = await service.refresh_all()
    await session.commit()
    return {"status": "success", "results": results}


@router.post("/import")
async def import_manual_data(
    request: ManualImportRequest,
    session: AsyncSession = Depends(get_session),
    _user: User = Depends(get_current_user),
):
    """手动导入排行榜数据。"""
    service = TrendScrapingService(session)

    if request.platform not in ALLOWED_PLATFORMS:
        raise HTTPException(status_code=400, detail=f"不支持的平台: {request.platform}")

    books = await service.import_manual_data(
        text=request.text,
        platform=request.platform,
        category=request.category,
    )
    await session.commit()

    return {
        "status": "success",
        "platform": request.platform,
        "category": request.category,
        "count": len(books),
        "books": books,
    }


@router.get("/suggestion")
async def get_creation_suggestion(
    context: str = Query("", max_length=1000, description="用户创作上下文"),
    session: AsyncSession = Depends(get_session),
    _user: User = Depends(get_current_user),
):
    """获取基于市场风向的创作建议（灵感模式用）。"""
    service = TrendAnalysisService(session)
    suggestion = await service.get_creation_suggestion(context)
    await session.commit()
    return {"suggestion": suggestion}


@router.delete("/{platform}")
async def delete_platform_data(
    platform: str,
    session: AsyncSession = Depends(get_session),
    _user: User = Depends(get_current_user),
):
    """删除指定平台的所有趋势数据（快照、排行榜、报告）。"""
    if platform not in ALLOWED_PLATFORMS:
        raise HTTPException(status_code=400, detail=f"不支持的平台: {platform}")

    snapshot_repo = TrendSnapshotRepository(session)
    book_repo = RankingBookRepository(session)
    report_repo = TrendReportRepository(session)

    # 先获取该平台所有快照ID，删除关联的书籍
    snapshot_ids = await snapshot_repo.get_snapshot_ids_by_platform(platform)
    deleted_books = await book_repo.delete_by_snapshot_ids(snapshot_ids)

    # 删除快照
    deleted_snapshots = await snapshot_repo.delete_by_platform(platform)

    # 删除报告
    deleted_reports = await report_repo.delete_by_platform(platform)

    await session.commit()

    return {
        "status": "success",
        "platform": platform,
        "deleted": {
            "snapshots": deleted_snapshots,
            "books": deleted_books,
            "reports": deleted_reports,
        },
    }
