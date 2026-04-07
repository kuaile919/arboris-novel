# AIMETA P=定时任务_自动刷新排行榜数据|R=定时任务调度|NR=不含业务逻辑|E=ScheduledTasks|X=internal|A=任务类|D=apscheduler|S=db|RD=./README.ai
from __future__ import annotations

import logging
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from .scraping_service import TrendScrapingService

logger = logging.getLogger(__name__)

# 定时任务配置
SCHEDULED_REFRESH_HOUR = 2  # 每天凌晨 2 点
SCHEDULED_REFRESH_MINUTE = 0


class TrendScheduledTasks:
    """趋势数据定时任务。

    每天自动刷新排行榜数据，保持数据新鲜度。
    """

    def __init__(self, session: AsyncSession):
        self.session = session
        self.scraping_service = TrendScrapingService(session)

    async def refresh_all_rankings(self) -> dict[str, int]:
        """刷新所有平台所有分类的排行榜。

        通常在凌晨执行，避免影响日间使用。
        """
        logger.info("开始执行定时刷新任务: %s", datetime.now().isoformat())

        results = {}
        platforms = self.scraping_service.get_supported_platforms()

        for platform in platforms:
            platform_id = platform["id"]
            categories = platform.get("categories", {})

            for cat_key in categories.keys():
                try:
                    books = await self.scraping_service.refresh(platform_id, cat_key)
                    results[f"{platform_id}:{cat_key}"] = len(books)
                    logger.info("定时刷新成功 %s:%s: %d 本", platform_id, cat_key, len(books))
                except Exception as e:
                    logger.error("定时刷新失败 %s:%s: %s", platform_id, cat_key, e)
                    results[f"{platform_id}:{cat_key}"] = -1

        success_count = sum(1 for v in results.values() if v > 0)
        fail_count = sum(1 for v in results.values() if v == -1)
        logger.info(
            "定时刷新任务完成: 成功 %d, 失败 %d",
            success_count, fail_count
        )

        return results

    async def refresh_platform(self, platform_id: str) -> dict[str, int]:
        """刷新指定平台的所有分类。"""
        logger.info("开始刷新平台: %s", platform_id)

        results = {}
        platforms = self.scraping_service.get_supported_platforms()

        platform = next((p for p in platforms if p["id"] == platform_id), None)
        if not platform:
            logger.warning("未知的平台: %s", platform_id)
            return results

        categories = platform.get("categories", {})
        for cat_key in categories.keys():
            try:
                books = await self.scraping_service.refresh(platform_id, cat_key)
                results[cat_key] = len(books)
            except Exception as e:
                logger.error("刷新失败 %s:%s: %s", platform_id, cat_key, e)
                results[cat_key] = -1

        return results


# 全局调度器实例
_scheduler = None


def init_scheduler(session_factory) -> "AsyncScheduler | None":
    """初始化 APScheduler 定时任务调度器。

    Args:
        session_factory: 异步 session 工厂函数

    Returns:
        配置好的调度器实例，如果 apscheduler 未安装则返回 None
    """
    global _scheduler

    try:
        from apscheduler.schedulers.asyncio import AsyncIOScheduler
        from apscheduler.triggers.cron import CronTrigger
    except ImportError:
        logger.warning("APScheduler 未安装，跳过定时任务初始化")
        return None

    if _scheduler is not None:
        return _scheduler

    async def scheduled_job():
        """定时执行的刷新任务。"""
        async with session_factory() as session:
            tasks = TrendScheduledTasks(session)
            await tasks.refresh_all_rankings()

    _scheduler = AsyncIOScheduler()

    # 每天凌晨 2:00 执行
    _scheduler.add_job(
        scheduled_job,
        trigger=CronTrigger(hour=SCHEDULED_REFRESH_HOUR, minute=SCHEDULED_REFRESH_MINUTE),
        id="trend_refresh_all",
        name="刷新所有排行榜数据",
        replace_existing=True,
    )

    logger.info(
        "定时任务已配置: 每天 %02d:%02d 自动刷新排行榜",
        SCHEDULED_REFRESH_HOUR, SCHEDULED_REFRESH_MINUTE
    )

    return _scheduler


def start_scheduler():
    """启动调度器。"""
    global _scheduler
    if _scheduler:
        _scheduler.start()
        logger.info("定时任务调度器已启动")


def shutdown_scheduler():
    """关闭调度器。"""
    global _scheduler
    if _scheduler:
        _scheduler.shutdown()
        logger.info("定时任务调度器已关闭")
