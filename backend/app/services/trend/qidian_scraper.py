# AIMETA P=起点爬虫_抓取起点排行榜|R=起点中文网数据抓取|NR=不含其他平台逻辑|E=QidianScraper|X=internal|A=爬虫类|D=httpx,beautifulsoup|S=net|RD=./README.ai
from __future__ import annotations

import logging
import re
from typing import Optional

import httpx
from bs4 import BeautifulSoup

from .base_scraper import BaseScraper, ScrapedBook, ScrapedRanking

logger = logging.getLogger(__name__)

# 起点新版 Web API（推荐，稳定）
QIDIAN_API_URL = "https://www.qidian.com/ajax/rank/{category}?page=1"

# 起点移动端页面（备用）
QIDIAN_M_RANK_URL = "https://m.qidian.com/rank/{category}/"

# 分类映射: key → (显示名, API category, 移动端 slug)
# 注意: 部分分类在移动端 m.qidian.com 不支持 (返回404)，已用可用分类替代
QIDIAN_CATEGORIES = {
    "hot": ("畅销榜", "hotsales", "hotsales"),
    "monthly": ("月票榜", "yuepiao", "yuepiao"),
    "readindex": ("阅读指数榜", "readindex", "readindex"),
    "newauthor": ("签约新书榜", "sign", "sign"),        # 原 newsign 移动端404，用 sign 替代
    "signnewbook": ("新书榜", "newbook", "newbook"),    # 原 signnewbook 移动端404，用 newbook 替代
    "recommend": ("推荐榜", "rec", "rec"),              # 原 recom 移动端404，用 rec 替代
    # 以下分类移动端返回404，已移除
    # "collect": ("收藏榜", "collect", "collect"),        # 移动端404
    # "vipcollect": ("VIP收藏榜", "vipcollect", "vipcollect"),  # 移动端404
    # "week": ("周点击榜", "weekclick", "weekclick"),    # 移动端404
}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "X-Requested-With": "XMLHttpRequest",
    "Referer": "https://www.qidian.com/",
}

M_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) "
        "Version/16.6 Mobile/15E148 Safari/604.1"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9",
    "Referer": "https://m.qidian.com/",
}


class QidianScraper(BaseScraper):
    """起点中文网排行榜爬虫（轻量级 HTTP 版）。

    使用官方 Web API 或移动版网页解析，无需浏览器渲染。
    三级策略：
    1. 优先使用新版 Web API
    2. 降级到移动端网页解析
    3. 最终降级到 PC 端网页
    """

    platform = "qidian"
    display_name = "起点中文网"
    base_url = "https://www.qidian.com"
    supported_categories = QIDIAN_CATEGORIES

    async def fetch_ranking(self, category: str = "hot", limit: int = 50) -> ScrapedRanking:
        """抓取起点排行榜，使用多级策略。"""
        cat_config = self.supported_categories.get(category)
        if not cat_config:
            logger.warning("起点不支持的分类: %s", category)
            return ScrapedRanking(platform=self.platform, category=category, books=[])

        display_name, api_cat, m_slug = cat_config
        books: list[ScrapedBook] = []

        # 策略 1: 尝试 Web API
        try:
            books = await self._fetch_via_api(api_cat, limit)
            if books:
                logger.info("起点 %s 榜 API 抓取成功，共 %d 条", category, len(books))
        except Exception as e:
            logger.debug("起点 API 抓取失败: %s", e)

        # 策略 2: 尝试移动端网页
        if not books:
            try:
                books = await self._fetch_via_mobile(m_slug, limit)
                if books:
                    logger.info("起点 %s 榜移动端抓取成功，共 %d 条", category, len(books))
            except Exception as e:
                logger.debug("起点移动端抓取失败: %s", e)

        # 策略 3: 尝试 PC 端网页
        if not books:
            try:
                books = await self._fetch_via_pc(category, limit)
                if books:
                    logger.info("起点 %s 榜 PC 端抓取成功，共 %d 条", category, len(books))
            except Exception as e:
                logger.debug("起点 PC 端抓取失败: %s", e)

        if not books:
            logger.warning("起点 %s 榜所有抓取策略均失败", category)

        return ScrapedRanking(
            platform=self.platform,
            category=category,
            books=books[:limit],
        )

    async def _fetch_via_api(self, api_cat: str, limit: int) -> list[ScrapedBook]:
        """使用起点新版 Web API 获取数据。"""
        url = QIDIAN_API_URL.format(category=api_cat)

        async with httpx.AsyncClient(headers=HEADERS, timeout=15.0, follow_redirects=True) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            data = resp.json()

        # 解析 API 响应
        books: list[ScrapedBook] = []
        records = data.get("data", {}).get("records", []) if isinstance(data, dict) else []

        for idx, item in enumerate(records[:limit], start=1):
            try:
                book = ScrapedBook(
                    rank=idx,
                    title=item.get("bName", "").strip(),
                    author=item.get("bAuth", "").strip(),
                    genre=item.get("cName", "").strip() or item.get("catName", "").strip(),
                    word_count=self._format_word_count(item.get("cnt", 0)),
                    description=item.get("desc", "").strip()[:200],
                    tags=item.get("tag", "").strip(),
                    heat_score=item.get("rankCnt", 0),
                    book_url=f"https://book.qidian.com/info/{item.get('bid', '')}/" if item.get('bid') else "",
                    cover_url=item.get("imgUrl", "").replace("150", "300") if item.get("imgUrl") else "",
                )
                if book.title:
                    books.append(book)
            except Exception as e:
                logger.debug("API 数据解析失败: %s", e)

        return books

    async def _fetch_via_mobile(self, slug: str, limit: int) -> list[ScrapedBook]:
        """使用移动端网页解析获取数据。"""
        url = QIDIAN_M_RANK_URL.format(category=slug)

        async with httpx.AsyncClient(headers=M_HEADERS, timeout=15.0, follow_redirects=True) as client:
            resp = await client.get(url)

            # 处理 404 等错误状态码
            if resp.status_code == 404:
                logger.warning("移动端榜单不存在: %s (404)", url)
                return []
            if resp.status_code >= 400:
                logger.warning("移动端请求失败: %s (%d)", url, resp.status_code)
                return []

            html = resp.text

        return self._parse_mobile_html(html, limit)

    def _parse_mobile_html(self, html: str, limit: int) -> list[ScrapedBook]:
        """解析起点移动端 HTML。

        优先尝试从 window.__INITIAL_STATE__ 提取 JSON 数据，
        兜底使用 BeautifulSoup 解析 DOM。
        """
        books: list[ScrapedBook] = []

        # 策略 1: 尝试从 window.__INITIAL_STATE__ 提取 JSON 数据
        books = self._parse_mobile_json(html, limit)
        if books:
            return books

        # 策略 2: 兜底使用 BeautifulSoup 解析
        soup = BeautifulSoup(html, "lxml")

        # 新版移动端的几种可能结构
        selectors = [
            ".book-list li",  # 通用列表
            ".rank-list .book-item",  # 排行榜专用
            ".books-list .book",  # 其他变体
            "a[href*='/book/']",  # 兜底：所有书籍链接
        ]

        items = []
        for selector in selectors:
            items = soup.select(selector)
            if items:
                break

        for idx, item in enumerate(items[:limit], start=1):
            try:
                book = self._extract_book_from_mobile_item(item, idx)
                if book and book.title:
                    books.append(book)
            except Exception as e:
                logger.debug("移动端解析第 %d 条失败: %s", idx, e)

        return books

    def _parse_mobile_json(self, html: str, limit: int) -> list[ScrapedBook]:
        """从 JSON 数据中提取书籍列表。

        支持两种格式：
        1. window.__INITIAL_STATE__ = {...};
        2. <script type="application/json"> {...} </script>
        """
        import json

        json_str = None

        # 模式 1: window.__INITIAL_STATE__ = {...};
        patterns_var = [
            r'window\.__INITIAL_STATE__\s*=\s*(\{.+?\}\s*);',
            r'window\.__INITIAL__\s*=\s*(\{.+?\}\s*);',
        ]

        for pattern in patterns_var:
            match = re.search(pattern, html, re.DOTALL)
            if match:
                json_str = match.group(1)
                break

        # 模式 2: <script type="application/json"> {...} </script>
        if not json_str:
            script_pattern = r'<script[^>]*type=["\']application/json["\'][^>]*>([^<]+)</script>'
            match = re.search(script_pattern, html, re.DOTALL)
            if match:
                json_str = match.group(1)

        if not json_str:
            return []

        try:
            data = json.loads(json_str)
        except json.JSONDecodeError as e:
            logger.debug("移动端 JSON 解析失败: %s", e)
            return []

        # 提取 records 数组: pageContext.pageProps.pageData.records
        try:
            records = data.get("pageContext", {}) \
                .get("pageProps", {}) \
                .get("pageData", {}) \
                .get("records", [])
        except Exception:
            return []

        if not records:
            return []

        books: list[ScrapedBook] = []
        for idx, item in enumerate(records[:limit], start=1):
            try:
                book = ScrapedBook(
                    rank=item.get("rankNum", idx),
                    title=item.get("bName", "").strip(),
                    author=item.get("bAuth", "").strip(),
                    genre=item.get("cat", "").strip(),
                    word_count=self._format_word_count(item.get("cnt", "")),
                    description=item.get("desc", "").strip()[:200],
                    tags=item.get("subCat", "").strip(),
                    heat_score=item.get("heat", 0),
                    book_url=f"https://book.qidian.com/info/{item.get('bid', '')}/" if item.get('bid') else "",
                    cover_url="",
                )
                if book.title:
                    books.append(book)
            except Exception as e:
                logger.debug("移动端 JSON 书籍解析失败: %s", e)

        if books:
            logger.debug("移动端 JSON 解析成功，获取 %d 本书", len(books))
            return books

        return []

    def _extract_book_from_mobile_item(self, item, rank: int) -> Optional[ScrapedBook]:
        """从移动端列表项中提取书籍信息。"""
        # 尝试多种可能的选择器
        title_sel = [
            "h2", ".book-title", ".title", "h3", "h4",
            "span.title", ".name"
        ]
        author_sel = [
            ".author", ".book-author", "[class*='author']",
            ".sub-title", ".meta"
        ]
        desc_sel = [
            ".description", ".book-desc", ".desc", ".intro",
            "p[class*='desc']", ".summary"
        ]

        # 提取标题
        title = ""
        for sel in title_sel:
            el = item.select_one(sel)
            if el:
                title = el.get_text(strip=True)
                break

        # 如果没有找到标题，尝试从链接的文本获取
        if not title:
            link = item if item.name == "a" else item.select_one("a")
            if link:
                title = link.get_text(strip=True)

        if not title or len(title) < 2:
            return None

        # 提取作者
        author = ""
        for sel in author_sel:
            el = item.select_one(sel)
            if el:
                text = el.get_text(strip=True)
                # 清理作者名（通常包含 "作者：" 或 "·" 分隔）
                author = re.split(r'[·|]', text)[0].replace("作者：", "").strip()
                break

        # 提取描述
        description = ""
        for sel in desc_sel:
            el = item.select_one(sel)
            if el:
                description = el.get_text(strip=True)[:200]
                break

        # 提取链接
        book_url = ""
        link = item if item.name == "a" else item.select_one("a[href]")
        if link and link.get("href"):
            href = link["href"]
            book_url = href if href.startswith("http") else f"https:{href}" if href.startswith("//") else f"https://m.qidian.com{href}"

        # 尝试提取题材（从链接或样式类）
        genre = ""
        genre_el = item.select_one(".tag, .category, .genre, [class*='cat']")
        if genre_el:
            genre = genre_el.get_text(strip=True)

        return ScrapedBook(
            rank=rank,
            title=title,
            author=author,
            genre=genre,
            description=description,
            book_url=book_url,
        )

    async def _fetch_via_pc(self, category: str, limit: int) -> list[ScrapedBook]:
        """使用 PC 端网页解析获取数据。"""
        url = f"https://www.qidian.com/rank/{category}/"

        async with httpx.AsyncClient(headers=HEADERS, timeout=15.0, follow_redirects=True) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            html = resp.text

        return self._parse_pc_html(html, limit)

    def _parse_pc_html(self, html: str, limit: int) -> list[ScrapedBook]:
        """解析起点 PC 端 HTML。"""
        soup = BeautifulSoup(html, "lxml")
        books: list[ScrapedBook] = []

        # PC 端可能的书籍列表选择器
        selectors = [
            ".book-img-text ul li",  # 标准排行
            ".rank-list li",  # 其他排行
            ".books-list .book-item",  # 通用列表
        ]

        items = []
        for selector in selectors:
            items = soup.select(selector)
            if items:
                break

        for idx, item in enumerate(items[:limit], start=1):
            try:
                title_el = (
                    item.select_one(".book-mid-info h2 a")
                    or item.select_one("h2 a")
                    or item.select_one(".book-info h3 a")
                )
                title = title_el.get_text(strip=True) if title_el else ""

                author_el = (
                    item.select_one(".book-mid-info .author a.name")
                    or item.select_one(".author a")
                    or item.select_one("[class*='author'] a")
                )
                author = author_el.get_text(strip=True) if author_el else ""

                desc_el = item.select_one(".book-mid-info .intro") or item.select_one(".intro") or item.select_one(".desc")
                description = desc_el.get_text(strip=True)[:200] if desc_el else ""

                genre_el = item.select_one("a[href*='cat']") or item.select_one(".tag") or item.select_one(".category")
                genre = genre_el.get_text(strip=True) if genre_el else ""

                link = ""
                if title_el and title_el.get("href"):
                    href = title_el["href"]
                    link = href if href.startswith("http") else f"{self.base_url}{href}"

                if title:
                    books.append(ScrapedBook(
                        rank=idx,
                        title=title,
                        author=author,
                        genre=genre,
                        description=description,
                        book_url=link,
                    ))
            except Exception as e:
                logger.debug("PC 端解析第 %d 条失败: %s", idx, e)

        return books

    def _format_word_count(self, count: int | str) -> str:
        """格式化字数显示。"""
        try:
            num = int(count)
            if num >= 10000:
                return f"{num / 10000:.1f}万"
            return str(num)
        except (ValueError, TypeError):
            return str(count) if count else ""
