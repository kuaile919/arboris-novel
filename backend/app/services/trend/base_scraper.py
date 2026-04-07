# AIMETA P=爬虫基类_定义统一抓取接口|R=排行榜抓取接口抽象|NR=不含具体爬虫实现|E=BaseScraper|X=internal|A=抽象基类|D=abc|S=net|RD=./README.ai
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional, Union

logger = logging.getLogger(__name__)


@dataclass
class ScrapedBook:
    """爬取到的单本书籍信息。"""

    rank: int
    title: str
    author: str = ""
    genre: str = ""
    word_count: str = ""
    description: str = ""
    tags: str = ""
    heat_score: int = 0
    cover_url: str = ""
    book_url: str = ""


@dataclass
class ScrapedRanking:
    """一次完整抓取的结果。"""

    platform: str
    category: str
    books: list[ScrapedBook] = field(default_factory=list)
    raw_html: str = ""
    raw_json: Optional[dict] = None


# 分类映射值类型: str(显示名) 或 tuple(显示名, url_slug)
CategoryValue = Union[str, tuple[str, str]]


class BaseScraper(ABC):
    """网文平台爬虫基类，定义统一抓取接口。"""

    platform: str = ""
    display_name: str = ""
    base_url: str = ""
    supported_categories: dict[str, CategoryValue] = {}

    @abstractmethod
    async def fetch_ranking(self, category: str = "hot", limit: int = 50) -> ScrapedRanking:
        """抓取指定分类的排行榜。

        Args:
            category: 榜单分类标识
            limit: 最大条目数

        Returns:
            ScrapedRanking 包含书籍列表
        """

    async def fetch_genres(self) -> list[str]:
        """获取平台题材分类列表（可选实现）。"""
        return []

    def get_category_name(self, category: str) -> str:
        """获取分类的显示名称。"""
        val = self.supported_categories.get(category, category)
        return val[0] if isinstance(val, tuple) else val

    def get_category_slug(self, category: str) -> str:
        """获取分类的 URL slug（仅 tuple 格式有效）。"""
        val = self.supported_categories.get(category)
        if isinstance(val, tuple):
            return val[1]
        return category

    def get_supported_categories(self) -> dict[str, str]:
        """返回该平台支持的分类列表 {key: 显示名}。"""
        result = {}
        for key, val in self.supported_categories.items():
            result[key] = val[0] if isinstance(val, tuple) else val
        return result

    def get_platform_meta(self) -> dict:
        """返回平台额外元数据，默认无附加信息。"""
        return {}
