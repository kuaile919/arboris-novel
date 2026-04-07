# AIMETA P=手动导入处理器_解析用户粘贴的排行榜文本|R=手动数据导入|NR=不含爬虫逻辑|E=ManualImportHandler|X=internal|A=处理器|D=re|S=none|RD=./README.ai
from __future__ import annotations

import json
import logging
import re
from typing import Optional

from .base_scraper import ScrapedBook, ScrapedRanking

logger = logging.getLogger(__name__)


class ManualImportHandler:
    """处理用户手动导入的排行榜数据。"""

    async def parse_text(self, text: str, platform: str, category: str = "manual") -> ScrapedRanking:
        """解析用户粘贴的排行榜文本。

        支持的格式：
        1. 每行一条: "排名. 书名 作者" 或 "排名. 书名 - 作者"
        2. JSON 数组: [{"title": "...", "author": "..."}]
        3. 自由文本: 用 LLM 提取
        """
        text = text.strip()
        if not text:
            return ScrapedRanking(platform=platform, category=category)

        # 尝试 JSON 解析
        books = self._try_parse_json(text)
        if books:
            return ScrapedRanking(platform=platform, category=category, books=books)

        # 尝试结构化文本解析
        books = self._try_parse_structured(text)
        if books:
            return ScrapedRanking(platform=platform, category=category, books=books)

        # 自由文本，按行分割尝试
        books = self._try_parse_lines(text)
        return ScrapedRanking(platform=platform, category=category, books=books)

    def _try_parse_json(self, text: str) -> list[ScrapedBook]:
        """尝试解析 JSON 格式。"""
        try:
            data = json.loads(text)
            if not isinstance(data, list):
                return []

            books = []
            for idx, item in enumerate(data, start=1):
                if not isinstance(item, dict):
                    continue
                book = ScrapedBook(
                    rank=idx,
                    title=item.get("title", item.get("name", item.get("书名", ""))),
                    author=item.get("author", item.get("作者", "")),
                    genre=item.get("genre", item.get("题材", item.get("分类", ""))),
                    word_count=str(item.get("word_count", item.get("字数", ""))),
                    description=item.get("description", item.get("简介", "")),
                    tags=item.get("tags", ""),
                    heat_score=item.get("heat_score", item.get("热度", 0)),
                )
                if book.title:
                    books.append(book)
            return books
        except (json.JSONDecodeError, TypeError):
            return []

    def _try_parse_structured(self, text: str) -> list[ScrapedBook]:
        """尝试解析结构化文本（排名. 书名 作者）。"""
        books = []
        # 匹配 "1. 书名 作者" 或 "1、书名 作者" 或 "1 书名 作者"
        pattern = re.compile(
            r"(\d+)\s*[.、\s]\s*(.+?)(?:\s{2,}|\t|[-|—]+)\s*(.+?)(?:\s{2,}|\t|[-|—]+)?\s*(.*?)(?:\n|$)"
        )
        matches = pattern.findall(text)

        for rank_str, title, author, extra in matches:
            try:
                book = ScrapedBook(
                    rank=int(rank_str),
                    title=title.strip(),
                    author=author.strip(),
                    genre=extra.strip() if extra else "",
                )
                if book.title:
                    books.append(book)
            except ValueError:
                continue

        return books

    def _try_parse_lines(self, text: str) -> list[ScrapedBook]:
        """按行分割，尝试提取书名和作者。"""
        books = []
        lines = [line.strip() for line in text.split("\n") if line.strip()]

        for idx, line in enumerate(lines, start=1):
            # 去掉序号前缀
            cleaned = re.sub(r"^\d+\s*[.、)\s]\s*", "", line)
            if not cleaned:
                continue

            # 尝试分离书名和作者
            parts = re.split(r"\s{2,}|\t", cleaned)
            title = parts[0].strip() if parts else cleaned
            author = parts[1].strip() if len(parts) > 1 else ""
            genre = parts[2].strip() if len(parts) > 2 else ""

            if title and len(title) > 1:
                books.append(ScrapedBook(
                    rank=idx,
                    title=title,
                    author=author,
                    genre=genre,
                ))

        return books
