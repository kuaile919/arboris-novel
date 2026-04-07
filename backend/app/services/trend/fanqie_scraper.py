# AIMETA P=番茄爬虫_抓取番茄小说排行榜|R=番茄小说数据抓取|NR=不含其他平台逻辑|E=FanqieScraper|X=internal|A=爬虫类|D=httpx|S=net|RD=./README.ai
"""番茄小说排行榜爬虫 - 纯 httpx 实现。

采集策略（三级降级）：
1. 排行榜页面 __INITIAL_STATE__ + 字体反爬解码（主策略）
2. 排行 API 分页加载更多数据（补充策略）
3. 若字体解码失败，保留加密原文（降级展示）

核心流程：
  获取排行页 HTML → 提取初始数据 + 自定义字体 URL
  → 下载自定义字体 → FanqieFontDecoder 对比参考字体建立映射
  → 用映射替换加密字符 → 返回可读排行榜数据
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Optional

import httpx

from .base_scraper import BaseScraper, ScrapedBook, ScrapedRanking
from .font_decoder import FanqieFontDecoder, is_likely_encrypted

logger = logging.getLogger(__name__)

# 排行榜页面
FANQIE_RANK_URL = "https://fanqienovel.com/rank"

# 排行榜 API（用于分页加载更多数据）
FANQIE_RANK_API = "https://fanqienovel.com/api/rank/category/list"

# 番茄官网当前公开的主榜单配置：
# /rank/{gender}_{rank_type}_{category_id}
# gender: 0=女频, 1=男频
# rank_type: 1=新书榜, 2=阅读榜
FANQIE_MAIN_RANKINGS = {
    "female_read": ("女频阅读榜", "0_2_1139"),
    "female_new": ("女频新书榜", "0_1_1139"),
    "male_read": ("男频阅读榜", "1_2_1141"),
    "male_new": ("男频新书榜", "1_1_1141"),
}

FANQIE_MAIN_RANKING_PARAMS = {
    "female_read": (0, 2, "1139"),
    "female_new": (0, 1, "1139"),
    "male_read": (1, 2, "1141"),
    "male_new": (1, 1, "1141"),
}

FANQIE_GENDER_TABS = {
    "male": "男频排行榜",
    "female": "女频排行榜",
}

FANQIE_RANKING_TYPES = {
    "read": "阅读榜",
    "new": "新书榜",
}

LEGACY_CATEGORY_ALIASES = {
    "hot": "female_read",
    "new": "female_new",
}

STRUCTURED_CATEGORY_PATTERN = re.compile(
    r"^(?P<gender>male|female):(?P<category_id>\d+):(?P<rank_kind>read|new)$"
)
RANK_PAGE_SLUG_PATTERN = re.compile(
    r"^(?P<gender>[01])_(?P<rank_type>[12])_(?P<category_id>\d+)$"
)

# 男频分类 ID -> 名称
MALE_CATEGORIES_ID_TO_NAME = {
    "1141": "西方奇幻",
    "1140": "东方仙侠",
    "8": "科幻末世",
    "261": "都市日常",
    "124": "都市修真",
    "1014": "都市高武",
    "273": "历史古代",
    "27": "战神赘婿",
    "263": "都市种田",
    "258": "传统玄幻",
    "272": "历史脑洞",
    "539": "悬疑脑洞",
    "262": "都市脑洞",
    "257": "玄幻脑洞",
    "751": "悬疑灵异",
    "504": "抗战谍战",
    "746": "游戏体育",
    "718": "动漫衍生",
    "1016": "男频衍生",
}

# 女频分类 ID -> 名称
FEMALE_CATEGORIES_ID_TO_NAME = {
    "1139": "古风世情",
    "8": "科幻末世",
    "746": "游戏体育",
    "1015": "女频衍生",
    "248": "玄幻言情",
    "23": "种田",
    "79": "年代",
    "267": "现言脑洞",
    "246": "宫斗宅斗",
    "539": "悬疑脑洞",
    "253": "古言脑洞",
    "24": "快穿",
    "749": "青春甜宠",
    "745": "星光璀璨",
    "747": "女频悬疑",
    "750": "职场婚恋",
    "748": "豪门总裁",
    "1017": "民国言情",
}

FANQIE_CATEGORY_GROUPS = {
    "male": MALE_CATEGORIES_ID_TO_NAME,
    "female": FEMALE_CATEGORIES_ID_TO_NAME,
}

# 前端展示用的分类映射：仅保留番茄官网当前真实可见的几种主榜单
FANQIE_CATEGORIES = FANQIE_MAIN_RANKINGS

# 判断分类属于男频还是女频（用于 API 调用）
MALE_CATEGORY_IDS = set(MALE_CATEGORIES_ID_TO_NAME.keys())
FEMALE_CATEGORY_IDS = set(FEMALE_CATEGORIES_ID_TO_NAME.keys())

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Referer": "https://fanqienovel.com/",
}

API_HEADERS = {
    **HEADERS,
    "Accept": "application/json, text/plain, */*",
    "X-Requested-With": "XMLHttpRequest",
}


class FanqieScraper(BaseScraper):
    """番茄小说排行榜爬虫（纯 HTTP 实现，无 Playwright 依赖）。

    三级采集策略：
    1. 页面 __INITIAL_STATE__ + 字体反爬解码
    2. 排行 API 分页加载
    3. 降级：保留加密原文（□ 替换未知字符）
    """

    platform = "fanqie"
    display_name = "番茄小说"
    base_url = "https://fanqienovel.com"
    supported_categories = FANQIE_CATEGORIES

    def __init__(self):
        self._font_decoder = FanqieFontDecoder()
        self._category_id_to_name: dict[str, dict[str, str]] = {
            "female": FEMALE_CATEGORIES_ID_TO_NAME.copy(),
            "male": MALE_CATEGORIES_ID_TO_NAME.copy(),
        }
        self._detail_cache: dict[str, Optional[dict[str, str]]] = {}
        self._font_decoded = False

    async def fetch_ranking(
        self, category: str = "female_read", limit: int = 50
    ) -> ScrapedRanking:
        """抓取番茄排行榜。"""
        books: list[ScrapedBook] = []

        # 主策略：从排行页面获取数据 + 字体解码
        try:
            books = await self._fetch_from_page(category, limit)
            if books:
                logger.info(
                    "番茄 %s 榜页面抓取成功，共 %d 条", category, len(books)
                )
        except Exception as e:
            logger.warning("番茄 %s 榜页面抓取失败: %s", category, e)

        return ScrapedRanking(
            platform=self.platform,
            category=category,
            books=books[:limit],
        )

    def get_platform_meta(self) -> dict:
        """返回番茄首页式分类导航元数据。"""
        return {
            "gender_tabs": FANQIE_GENDER_TABS,
            "category_groups": FANQIE_CATEGORY_GROUPS,
            "ranking_types": FANQIE_RANKING_TYPES,
        }

    def get_category_name(self, category: str) -> str:
        """补充结构化 category key 的显示名。"""
        normalized_category = self._normalize_category(category)

        val = self.supported_categories.get(normalized_category)
        if isinstance(val, tuple):
            return val[0]
        if isinstance(val, str):
            return val

        structured = self._parse_structured_category(normalized_category)
        if structured:
            gender_key, _gender, rank_type, category_id = structured
            category_name = self._category_id_to_name.get(gender_key, {}).get(category_id, category_id)
            rank_name = "阅读榜" if rank_type == 2 else "新书榜"
            return f"{category_name}·{rank_name}"

        slug = self._parse_rank_page_slug(normalized_category)
        if slug:
            gender_key = "male" if slug[0] == 1 else "female"
            category_name = self._category_id_to_name.get(gender_key, {}).get(slug[2], slug[2])
            rank_name = "阅读榜" if slug[1] == 2 else "新书榜"
            return f"{category_name}·{rank_name}"

        return super().get_category_name(category)

    # ------------------------------------------------------------------
    # 核心采集
    # ------------------------------------------------------------------

    async def _fetch_from_page(
        self, category: str, limit: int
    ) -> list[ScrapedBook]:
        """从排行榜页面获取数据，并尝试通过 API 补充更多数据。"""
        rank_page_url = self._build_rank_page_url(category)
        async with httpx.AsyncClient(
            headers=HEADERS, timeout=20.0, follow_redirects=True
        ) as client:
            # Step 1: 获取排行页面 HTML
            resp = await client.get(rank_page_url)
            resp.raise_for_status()
            html = resp.text

            # Step 2: 提取 __INITIAL_STATE__
            data = self._extract_initial_state(html)
            if not data:
                logger.warning("未找到 __INITIAL_STATE__")
                return []

            # Step 3: 提取自定义字体 URL 并解码
            await self._decode_font(client, data)

            # Step 4: 更新分类映射
            self._update_category_map(data.get("rank", {}))

            # Step 5: 获取初始书籍列表
            rank_data = data.get("rank", {})
            book_list: list[dict] = rank_data.get("book_list", [])

            # Step 6: 如果初始数据不足，通过 API 获取更多
            if len(book_list) < limit:
                api_books = await self._fetch_more_from_api(
                    client, category, limit - len(book_list)
                )
                seen_ids = {b.get("bookId") for b in book_list}
                for b in api_books:
                    if b.get("bookId") not in seen_ids:
                        book_list.append(b)
                        seen_ids.add(b.get("bookId"))

            # Step 7: 解码加密文本
            self._decode_book_list(book_list)

            # Step 8: If obfuscated text remains, refill it from plaintext book pages.
            await self._enrich_books_from_detail_pages(client, book_list, limit)

            return self._parse_books(book_list, limit)

    async def _fetch_more_from_api(
        self,
        client: httpx.AsyncClient,
        category: str,
        needed: int,
    ) -> list[dict]:
        """通过排行 API 分页加载更多数据。"""
        gender, rank_type, category_id = self._category_to_params(category)

        all_books: list[dict] = []
        offset = 0
        count = 20

        while len(all_books) < needed:
            try:
                params: dict = {
                    "gender": gender,
                    "rank_type": rank_type,
                    "offset": offset,
                    "count": count,
                }
                if category_id:
                    params["category_id"] = category_id

                resp = await client.get(
                    FANQIE_RANK_API,
                    params=params,
                    headers=API_HEADERS,
                )
                resp.raise_for_status()
                result = resp.json()

                book_list = result.get("data", {}).get("book_list", [])
                if not book_list:
                    break

                all_books.extend(book_list)
                offset += count

                if len(book_list) < count:
                    break
            except Exception as e:
                logger.debug("排行 API 调用失败 (offset=%d): %s", offset, e)
                break

        if all_books:
            logger.debug("API 获取了 %d 本额外数据", len(all_books))
        return all_books

    # ------------------------------------------------------------------
    # 字体反爬解码
    # ------------------------------------------------------------------

    async def _decode_font(
        self, client: httpx.AsyncClient, data: dict
    ) -> None:
        """提取自定义字体 URL，下载字体并建立映射。"""
        font_url = self._extract_font_url(data)
        if not font_url:
            logger.debug("未找到自定义字体 URL")
            return

        try:
            # 在后台准备参考字体（首次会下载 ~24MB）
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(
                None, self._font_decoder.ensure_reference_font
            )

            # 下载自定义字体
            resp = await client.get(font_url, timeout=30.0)
            if resp.status_code != 200:
                logger.warning("字体下载失败: HTTP %d", resp.status_code)
                return

            # 建立映射（在执行器中运行以避免阻塞事件循环）
            mapping = await loop.run_in_executor(
                None, self._font_decoder.build_mapping, resp.content
            )

            if mapping:
                self._font_decoded = True
                logger.info("字体映射建立成功: %d 个字符", len(mapping))
            else:
                logger.info("字体映射建立失败，将回退到详情页明文补全")

        except Exception as e:
            logger.info("字体解码过程失败，将回退到详情页明文补全: %s", e)

    def _decode_book_list(self, book_list: list[dict]) -> None:
        """对书籍列表中的加密文本进行解码。"""
        if not self._font_decoded:
            # 无映射时使用 decode_text 的降级逻辑（加密字符→□）
            for item in book_list:
                for field in ("bookName", "author", "abstract"):
                    val = item.get(field, "")
                    if val:
                        item[field] = self._font_decoder.decode_text(val)
            return

        for item in book_list:
            for field in ("bookName", "author", "abstract"):
                val = item.get(field, "")
                if val:
                    item[field] = self._font_decoder.decode_text(val)

    async def _enrich_books_from_detail_pages(
        self,
        client: httpx.AsyncClient,
        book_list: list[dict],
        limit: int,
    ) -> None:
        """Fill obfuscated ranking fields from the plaintext detail page."""
        target_items = [
            item for item in book_list[:limit] if self._needs_detail_fallback(item)
        ]
        if not target_items:
            return

        semaphore = asyncio.Semaphore(6)

        async def enrich_one(item: dict) -> None:
            book_id = str(item.get("bookId", "")).strip()
            if not book_id:
                return

            if book_id not in self._detail_cache:
                async with semaphore:
                    self._detail_cache[book_id] = await self._fetch_book_detail_page(
                        client, book_id
                    )

            detail = self._detail_cache.get(book_id)
            if not detail:
                return

            for item_field, detail_field in (
                ("bookName", "bookName"),
                ("author", "author"),
                ("abstract", "abstract"),
            ):
                current_value = item.get(item_field, "")
                fallback_value = detail.get(detail_field, "")
                if fallback_value and (
                    not current_value or self._contains_obfuscated_text(current_value)
                ):
                    item[item_field] = fallback_value

            if not item.get("category"):
                category_name = detail.get("category", "")
                if category_name:
                    item["category"] = category_name

        await asyncio.gather(*(enrich_one(item) for item in target_items))
        logger.info("番茄详情页明文回填完成: %d 本", len(target_items))

    async def _fetch_book_detail_page(
        self, client: httpx.AsyncClient, book_id: str
    ) -> Optional[dict[str, str]]:
        """Fetch plaintext metadata from the book detail page source."""
        try:
            resp = await client.get(f"{self.base_url}/page/{book_id}", timeout=20.0)
            resp.raise_for_status()
            html = resp.text
        except Exception as e:
            logger.debug("番茄详情页抓取失败 %s: %s", book_id, e)
            return None

        detail = {
            "bookName": self._extract_detail_field(html, "bookName"),
            "author": self._extract_detail_field(html, "author"),
            "abstract": self._extract_detail_field(html, "abstract"),
            "category": self._extract_detail_category(html),
        }
        return detail if any(detail.values()) else None

    @staticmethod
    def _needs_detail_fallback(item: dict) -> bool:
        for field in ("bookName", "author", "abstract"):
            if FanqieScraper._contains_obfuscated_text(item.get(field, "")):
                return True
        return False

    @staticmethod
    def _contains_obfuscated_text(text: str) -> bool:
        if not text:
            return False
        return any(char == "\u25A1" or is_likely_encrypted(char) for char in text)

    @staticmethod
    def _extract_detail_field(html: str, field_name: str) -> str:
        match = re.search(fr'"{field_name}":"((?:\\.|[^"])*)"', html)
        if not match:
            return ""
        return FanqieScraper._decode_json_string(match.group(1))

    @staticmethod
    def _extract_detail_category(html: str) -> str:
        raw = FanqieScraper._extract_detail_field(html, "categoryV2")
        if not raw:
            return ""

        try:
            categories = json.loads(raw)
        except json.JSONDecodeError:
            return ""

        if isinstance(categories, list):
            for category in categories:
                if isinstance(category, dict):
                    name = str(category.get("Name", "")).strip()
                    if name:
                        return name
        return ""

    @staticmethod
    def _decode_json_string(raw_value: str) -> str:
        if not raw_value:
            return ""

        try:
            return json.loads(f'"{raw_value}"')
        except json.JSONDecodeError:
            return raw_value.replace('\\"', '"').replace("\\/", "/")

    # ------------------------------------------------------------------
    # HTML / JSON 解析
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_initial_state(html: str) -> Optional[dict]:
        """从 HTML 中提取 window.__INITIAL_STATE__ JSON 数据。"""
        needle = "window.__INITIAL_STATE__="
        start = html.find(needle)
        if start == -1:
            return None

        start += len(needle)
        brace_count = 0
        in_string = False
        escaped = False
        end: Optional[int] = None

        for idx, ch in enumerate(html[start:], start=start):
            if in_string:
                if escaped:
                    escaped = False
                elif ch == "\\":
                    escaped = True
                elif ch == '"':
                    in_string = False
                continue

            if ch == '"':
                in_string = True
            elif ch == "{":
                brace_count += 1
            elif ch == "}":
                brace_count -= 1
                if brace_count == 0:
                    end = idx + 1
                    break

        if end is None:
            return None

        try:
            json_text = html[start:end]
            json_text = re.sub(r":undefined(?=[,}])", ":null", json_text)
            return json.loads(json_text)
        except json.JSONDecodeError as e:
            logger.warning("JSON 解析失败: %s", e)
        return None

    @staticmethod
    def _extract_font_url(data: dict) -> Optional[str]:
        """从 __INITIAL_STATE__.common.css 中提取自定义字体 URL。"""
        css = data.get("common", {}).get("css", "")
        if not css:
            return None

        # 匹配 @font-face 中的 woff2 URL
        match = re.search(r"src:url\((https?://[^)]+\.woff2)\)", css)
        if match:
            return match.group(1)

        # 降级：匹配 woff URL
        match = re.search(r"src:url\((https?://[^)]+\.woff)\)", css)
        if match:
            return match.group(1)

        return None

    # ------------------------------------------------------------------
    # 分类映射
    # ------------------------------------------------------------------

    def _update_category_map(self, rank_data: dict) -> None:
        """从排行数据中更新分类 ID → 名称的映射。"""
        cat_type_list = rank_data.get("rankCategoryTypeList", {})
        if not isinstance(cat_type_list, dict):
            return

        for gender, cats in cat_type_list.items():
            if not isinstance(cats, list):
                continue
            self._category_id_to_name.setdefault(gender, {})
            for cat in cats:
                cat_id = str(cat.get("id", ""))
                cat_name = cat.get("name", "")
                if cat_id and cat_name:
                    self._category_id_to_name[gender][cat_id] = cat_name

    def _category_to_params(self, category: str) -> tuple[int, int, str]:
        """将前端分类 key 转换为 API 参数 (gender, rank_type, category_id)。"""
        normalized_category = self._normalize_category(category)

        ranking_params = FANQIE_MAIN_RANKING_PARAMS.get(normalized_category)
        if ranking_params:
            return ranking_params

        structured = self._parse_structured_category(normalized_category)
        if structured:
            _gender_key, gender, rank_type, category_id = structured
            return gender, rank_type, category_id

        slug = self._parse_rank_page_slug(normalized_category)
        if slug:
            return slug

        # 兼容旧的分类 ID：默认按阅读榜抓取该题材
        gender = 0
        rank_type = 2
        category_id = ""

        # 分类 ID 作为 category_id
        category_id = normalized_category
        # 判断所属频道
        if normalized_category in MALE_CATEGORY_IDS and normalized_category not in FEMALE_CATEGORY_IDS:
            gender = 1

        return gender, rank_type, category_id

    def _build_rank_page_url(self, category: str) -> str:
        """根据分类 key 构造番茄榜单页面 URL。"""
        normalized_category = self._normalize_category(category)
        config = self.supported_categories.get(normalized_category)
        if isinstance(config, tuple):
            return f"{FANQIE_RANK_URL}/{config[1]}"

        if self._parse_rank_page_slug(normalized_category):
            return f"{FANQIE_RANK_URL}/{normalized_category}"

        structured = self._parse_structured_category(normalized_category)
        if structured:
            _gender_key, gender, rank_type, category_id = structured
            return f"{FANQIE_RANK_URL}/{gender}_{rank_type}_{category_id}"

        gender, rank_type, category_id = self._category_to_params(normalized_category)
        if category_id:
            return f"{FANQIE_RANK_URL}/{gender}_{rank_type}_{category_id}"
        return FANQIE_RANK_URL

    @staticmethod
    def _normalize_category(category: str) -> str:
        """将旧分类 key 归一化到当前主榜单 key。"""
        return LEGACY_CATEGORY_ALIASES.get(category, category)

    @staticmethod
    def _parse_structured_category(category: str) -> Optional[tuple[str, int, int, str]]:
        """解析前端结构化 category key: male:1140:read。"""
        match = STRUCTURED_CATEGORY_PATTERN.match(category)
        if not match:
            return None

        gender_key = match.group("gender")
        category_id = match.group("category_id")
        rank_kind = match.group("rank_kind")

        gender = 1 if gender_key == "male" else 0
        rank_type = 2 if rank_kind == "read" else 1
        return gender_key, gender, rank_type, category_id

    @staticmethod
    def _parse_rank_page_slug(category: str) -> Optional[tuple[int, int, str]]:
        """解析番茄榜单页 slug: 1_2_1140。"""
        match = RANK_PAGE_SLUG_PATTERN.match(category)
        if not match:
            return None

        return (
            int(match.group("gender")),
            int(match.group("rank_type")),
            match.group("category_id"),
        )

    def _resolve_category_name(self, item: dict) -> str:
        """从书籍数据中解析分类名称。"""
        pos_cat_id = str(item.get("pos_category_id", ""))
        if pos_cat_id:
            for gender_map in self._category_id_to_name.values():
                if pos_cat_id in gender_map:
                    return gender_map[pos_cat_id]

        return item.get("category", "").strip()

    # ------------------------------------------------------------------
    # 书籍解析
    # ------------------------------------------------------------------

    def _parse_books(self, book_list: list[dict], limit: int) -> list[ScrapedBook]:
        """将原始书籍数据解析为 ScrapedBook 列表。"""
        books: list[ScrapedBook] = []
        for idx, item in enumerate(book_list[:limit], start=1):
            book = self._parse_book_item(item, idx)
            if book:
                books.append(book)
        return books

    def _parse_book_item(self, item: dict, rank: int) -> Optional[ScrapedBook]:
        """解析单本书籍数据。"""
        book_name = item.get("bookName", "").strip()
        if not book_name:
            return None

        author = item.get("author", "").strip()
        category = self._resolve_category_name(item)
        abstract = item.get("abstract", "").strip()
        book_id = item.get("bookId", "")
        word_number = item.get("wordNumber", "")
        read_count = item.get("read_count", "0")
        thumb_uri = item.get("thumbUri", "")

        book_url = f"{self.base_url}/page/{book_id}" if book_id else ""

        try:
            heat_score = int(read_count) if read_count else 0
        except (ValueError, TypeError):
            heat_score = 0

        return ScrapedBook(
            rank=rank,
            title=book_name,
            author=author,
            genre=category,
            word_count=self._format_word_count(word_number),
            description=abstract[:200] if abstract else "",
            heat_score=heat_score,
            book_url=book_url,
            cover_url=thumb_uri,
        )

    @staticmethod
    def _format_word_count(count: str | int) -> str:
        """格式化字数显示。"""
        try:
            num = int(count)
            if num >= 10000:
                return f"{num / 10000:.1f}万字"
            return f"{num}字"
        except (ValueError, TypeError):
            return str(count) if count else ""
