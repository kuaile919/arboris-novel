# AIMETA P=采集调度服务_统一管理爬虫和缓存|R=采集调度_缓存管理_并发控制|NR=不含爬虫实现|E=TrendScrapingService|X=internal|A=服务类|D=cachetools|S=db,net|RD=./README.ai
from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timedelta
from typing import Optional

from cachetools import TTLCache
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from ...models.trend import TrendSnapshot, RankingBook
from ...repositories.trend_repository import TrendSnapshotRepository, RankingBookRepository
from .base_scraper import ScrapedRanking, ScrapedBook
from .qidian_scraper import QidianScraper
from .fanqie_scraper import FanqieScraper
from .font_decoder import is_likely_encrypted
from .manual_import import ManualImportHandler
from .data_enrichment import DataEnrichmentService

logger = logging.getLogger(__name__)

# TTL 内存缓存: key = "platform:category", value = (timestamp, data)
# 最大 100 条缓存，1小时过期
_memory_cache = TTLCache(maxsize=100, ttl=3600)
CACHE_TTL_HOURS = 6

# 平台级并发锁: 防止同时刷新同一平台
_platform_locks: dict[str, asyncio.Lock] = {}

# 失败计数器（用于熔断）
_failure_counts: dict[str, int] = {}
_failure_threshold = 10
_circuit_breaker_until: dict[str, float] = {}


class TrendScrapingService:
    """统一采集调度服务，管理爬虫调用和数据缓存。

    特性:
    1. TTL 缓存替代无限增长字典
    2. 平台级并发锁，防止重复抓取
    3. 数据自动补全
    4. 熔断机制，连续失败自动暂停
    """

    def __init__(self, session: AsyncSession):
        self.session = session
        self.snapshot_repo = TrendSnapshotRepository(session)
        self.book_repo = RankingBookRepository(session)
        self.enrichment_service = DataEnrichmentService(session)
        self.scrapers = {
            "qidian": QidianScraper(),
            "fanqie": FanqieScraper(),
        }
        self.manual_handler = ManualImportHandler()

    def get_supported_platforms(self) -> list[dict]:
        """返回所有支持的平台信息。"""
        platforms = []
        for key, scraper in self.scrapers.items():
            platform_info = {
                "id": scraper.platform,
                "name": scraper.display_name,
                "categories": scraper.get_supported_categories(),
            }
            meta = scraper.get_platform_meta()
            if meta:
                platform_info["meta"] = meta
            platforms.append(platform_info)
        return platforms

    async def get_ranking(
        self,
        platform: str,
        category: str = "hot",
        limit: int = 50,
        force_refresh: bool = False,
    ) -> list[dict]:
        """获取排行榜数据，优先缓存。

        Returns:
            书籍字典列表
        """
        cache_key = f"{platform}:{category}"

        # 检查熔断器
        if self._is_circuit_breaker_open(platform):
            logger.warning("平台 %s 熔断器开启，跳过抓取", platform)
            # 尝试从数据库加载
            db_books = await self._load_from_db_any_age(platform, category)
            return db_books[:limit] if db_books else []

        # 1. 检查内存缓存
        if not force_refresh and cache_key in _memory_cache:
            cached_data = _memory_cache[cache_key]
            if self._ranking_has_obfuscated_text(platform, cached_data):
                logger.warning("缓存命中但包含异常字符，忽略并重新抓取: %s", cache_key)
                _memory_cache.pop(cache_key, None)
            else:
                logger.debug("内存缓存命中: %s", cache_key)
                return cached_data[:limit]

        # 2. 检查数据库缓存（6小时内）
        if not force_refresh:
            db_books = await self._load_from_db(platform, category)
            if db_books:
                _memory_cache[cache_key] = db_books
                return db_books[:limit]

        # 3. 降级：不限年龄的数据库缓存
        if not force_refresh:
            db_books = await self._load_from_db_any_age(platform, category)
            if db_books:
                logger.info("使用降级数据库缓存: %s", cache_key)
                return db_books[:limit]

        # 4. 实时抓取（带并发锁）
        books = await self._scrape_with_lock(platform, category, limit)
        if books:
            _memory_cache[cache_key] = books
            # 重置失败计数
            _failure_counts[platform] = 0
            return books[:limit]

        return []

    async def refresh(self, platform: str, category: str = "hot") -> list[dict]:
        """强制刷新排行榜数据。"""
        return await self.get_ranking(platform, category, force_refresh=True)

    async def refresh_all(self) -> dict[str, int]:
        """刷新所有平台所有分类的数据。"""
        results = {}
        for platform_key, scraper in self.scrapers.items():
            for cat_key in scraper.get_supported_categories():
                try:
                    books = await self.get_ranking(platform_key, cat_key, force_refresh=True)
                    results[f"{platform_key}:{cat_key}"] = len(books)
                except Exception as e:
                    logger.error("刷新 %s:%s 失败: %s", platform_key, cat_key, e)
                    results[f"{platform_key}:{cat_key}"] = -1
        return results

    async def import_manual_data(
        self, text: str, platform: str, category: str = "manual"
    ) -> list[dict]:
        """手动导入排行榜数据。"""
        ranking = await self.manual_handler.parse_text(text, platform, category)

        # 数据补全（手动导入的数据通常缺少题材）
        if ranking.books:
            ranking.books = await self.enrichment_service.enrich_books(ranking.books)

        await self._save_ranking(ranking, data_source="manual")
        books = [self._scraped_book_to_dict(b) for b in ranking.books]
        cache_key = f"{platform}:{category}"
        _memory_cache[cache_key] = books
        return books

    # ==================== 私有方法 ====================

    def _is_circuit_breaker_open(self, platform: str) -> bool:
        """检查熔断器是否开启。"""
        until = _circuit_breaker_until.get(platform, 0)
        if time.time() < until:
            return True
        return False

    def _record_failure(self, platform: str):
        """记录失败，检查是否触发熔断。"""
        _failure_counts[platform] = _failure_counts.get(platform, 0) + 1
        if _failure_counts[platform] >= _failure_threshold:
            # 触发熔断，暂停1小时
            _circuit_breaker_until[platform] = time.time() + 3600
            logger.error("平台 %s 连续失败 %d 次，熔断器开启1小时", platform, _failure_counts[platform])

    async def _scrape_with_lock(self, platform: str, category: str, limit: int) -> list[dict]:
        """使用并发锁执行抓取。"""
        lock = _platform_locks.setdefault(platform, asyncio.Lock())

        async with lock:
            try:
                start_time = time.time()
                books = await self._scrape_and_save(platform, category, limit)
                duration_ms = int((time.time() - start_time) * 1000)

                if books:
                    logger.info("抓取成功 %s/%s: %d 本, 耗时 %dms", platform, category, len(books), duration_ms)
                else:
                    self._record_failure(platform)

                return books
            except Exception as e:
                self._record_failure(platform)
                logger.error("抓取异常 %s/%s: %s", platform, category, e)
                return []

    async def _load_from_db(self, platform: str, category: str) -> list[dict]:
        """从数据库加载 6 小时内的快照。"""
        snapshot = await self.snapshot_repo.get_latest_snapshot(platform, category, max_age_hours=CACHE_TTL_HOURS)
        if not snapshot:
            return []
        books = await self.book_repo.get_books_by_snapshot(snapshot.id)
        if self._ranking_has_obfuscated_text(platform, books):
            logger.warning(
                "数据库快照存在异常字符，忽略缓存: %s/%s#%s",
                platform,
                category,
                snapshot.id,
            )
            return []
        return [self._book_to_dict(b) for b in books]

    async def _load_from_db_any_age(self, platform: str, category: str) -> list[dict]:
        """从数据库加载最新快照（不限年龄）。"""
        snapshot = await self.snapshot_repo.get_latest_snapshot_any_age(platform, category)
        if not snapshot:
            return []
        books = await self.book_repo.get_books_by_snapshot(snapshot.id)
        if self._ranking_has_obfuscated_text(platform, books):
            logger.warning(
                "降级数据库快照存在异常字符，忽略缓存: %s/%s#%s",
                platform,
                category,
                snapshot.id,
            )
            return []
        return [self._book_to_dict(b) for b in books]

    async def _scrape_and_save(
        self, platform: str, category: str, limit: int
    ) -> list[dict]:
        """执行抓取并保存。"""
        scraper = self.scrapers.get(platform)
        if not scraper:
            logger.warning("不支持的平台: %s", platform)
            return []

        start_time = time.time()
        ranking = await scraper.fetch_ranking(category, limit)
        fetch_duration_ms = int((time.time() - start_time) * 1000)

        if not ranking.books:
            return []

        # 数据补全（填充缺失的题材和标签）
        ranking.books = await self.enrichment_service.enrich_books(ranking.books)

        # 计算数据质量分数
        quality_score = self._calculate_quality_score(ranking.books)

        await self._save_ranking(ranking, data_source="scraping", quality_score=quality_score, fetch_duration_ms=fetch_duration_ms)
        return [self._scraped_book_to_dict(b) for b in ranking.books]

    def _ranking_has_obfuscated_text(
        self,
        platform: str,
        books: list[RankingBook] | list[dict],
    ) -> bool:
        """检测番茄缓存中是否仍残留反爬字符或方块字。"""
        if platform != "fanqie" or not books:
            return False

        return any(self._book_has_obfuscated_text(book) for book in books)

    @staticmethod
    def _book_has_obfuscated_text(book: RankingBook | dict) -> bool:
        """检查单本书的标题/作者/简介是否包含异常字符。"""
        if isinstance(book, dict):
            fields = (
                book.get("title", ""),
                book.get("author", ""),
                book.get("description", ""),
            )
        else:
            fields = (book.title, book.author, book.description or "")

        return any(
            TrendScrapingService._text_has_obfuscated_chars(value)
            for value in fields
        )

    @staticmethod
    def _text_has_obfuscated_chars(text: Optional[str]) -> bool:
        """识别番茄私有码点或已经降级成方块的脏文本。"""
        if not text:
            return False

        return any(char == "\u25A1" or is_likely_encrypted(char) for char in text)

    def _calculate_quality_score(self, books: list[ScrapedBook]) -> float:
        """计算数据质量分数。"""
        if not books:
            return 0.0

        total_score = 0.0
        for book in books:
            score = 0.0
            # 有题材 +0.3
            if book.genre:
                score += 0.3
            # 有标签 +0.2
            if book.tags:
                score += 0.2
            # 有描述 +0.2
            if book.description and len(book.description) > 10:
                score += 0.2
            # 有作者 +0.2
            if book.author:
                score += 0.2
            # 有字数 +0.1
            if book.word_count:
                score += 0.1
            total_score += score

        return round(total_score / len(books), 2)

    async def _save_ranking(
        self,
        ranking: ScrapedRanking,
        data_source: str = "scraping",
        quality_score: float = 0.0,
        fetch_duration_ms: int = 0,
    ) -> None:
        """将抓取结果保存到数据库。"""
        snapshot = TrendSnapshot(
            platform=ranking.platform,
            category=ranking.category,
            raw_data={
                "total_books": len(ranking.books),
                "fetch_duration_ms": fetch_duration_ms,
            },
            data_source=data_source,
            data_quality_score=quality_score,
            fetch_duration_ms=fetch_duration_ms,
        )
        self.session.add(snapshot)
        await self.session.flush()

        for scraped in ranking.books:
            book = RankingBook(
                snapshot_id=snapshot.id,
                rank=scraped.rank,
                title=scraped.title,
                author=scraped.author,
                genre=scraped.genre,
                word_count=scraped.word_count,
                description=scraped.description,
                tags=scraped.tags,
                heat_score=scraped.heat_score,
                cover_url=scraped.cover_url,
                book_url=scraped.book_url,
                is_enriched=bool(scraped.genre or scraped.tags),  # 只要有补全数据即标记
            )
            self.session.add(book)

        await self.session.flush()
        logger.info(
            "保存排行榜快照: %s/%s, %d本书籍, 质量分数 %.2f",
            ranking.platform, ranking.category, len(ranking.books), quality_score,
        )

    @staticmethod
    def _book_to_dict(book: RankingBook) -> dict:
        """ORM 模型转字典。"""
        return {
            "rank": book.rank,
            "title": book.title,
            "author": book.author,
            "genre": book.genre,
            "word_count": book.word_count,
            "description": book.description or "",
            "tags": book.tags or "",
            "heat_score": book.heat_score,
            "cover_url": book.cover_url or "",
            "book_url": book.book_url or "",
            "is_enriched": book.is_enriched,
        }

    @staticmethod
    def _scraped_book_to_dict(book: ScrapedBook) -> dict:
        """ScrapedBook 转字典。"""
        return {
            "rank": book.rank,
            "title": book.title,
            "author": book.author,
            "genre": book.genre,
            "word_count": book.word_count,
            "description": book.description,
            "tags": book.tags,
            "heat_score": book.heat_score,
            "cover_url": book.cover_url,
            "book_url": book.book_url,
        }
