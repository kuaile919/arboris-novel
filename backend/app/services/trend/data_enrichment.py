# AIMETA P=数据补全服务_使用LLM补全缺失字段|R=书籍数据智能补全|NR=不含爬虫逻辑|E=DataEnrichmentService|X=internal|A=服务类|D=sqlalchemy,httpx|S=net,db|RD=./README.ai
from __future__ import annotations

import json
import logging
import re
from dataclasses import replace
from typing import Optional

from cachetools import TTLCache
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import SQLAlchemyError

from ...services.llm_service import LLMService
from .base_scraper import ScrapedBook

logger = logging.getLogger(__name__)

# 缓存已补全的结果，避免重复调用 LLM（最多5000条，1天过期）
_genre_cache: TTLCache = TTLCache(maxsize=5000, ttl=86400)

# 常见题材映射表（用于快速匹配）
COMMON_GENRES = {
    "玄幻": ["玄幻", "东方玄幻", "异世大陆", "王朝争霸", "高武世界"],
    "奇幻": ["奇幻", "剑与魔法", "史诗奇幻", "黑暗奇幻", "现代魔法"],
    "武侠": ["武侠", "传统武侠", "武侠幻想", "古武未来", "国术无双"],
    "仙侠": ["仙侠", "修真文明", "幻想修仙", "现代修真", "神话修真"],
    "都市": ["都市", "都市生活", "都市异能", "异术超能", "恩怨情仇"],
    "现实": ["现实", "现实百态", "爱情婚姻", "社会生活", "乡土小说"],
    "军事": ["军事", "战争幻想", "抗战烽火", "谍战特工", "军旅生涯"],
    "历史": ["历史", "架空历史", "上古先秦", "秦汉三国", "两晋隋唐", "五代十国", "两宋元明", "清史民国", "外国历史"],
    "游戏": ["游戏", "虚拟网游", "电子竞技", "游戏异界", "游戏系统"],
    "体育": ["体育", "篮球运动", "足球运动", "弈林生涯", "搏击运动"],
    "科幻": ["科幻", "星际文明", "时空穿梭", "未来世界", "古武机甲", "超级科技", "进化变异", "末世危机"],
    "悬疑": ["悬疑", "悬疑侦探", "诡秘悬疑", "奇妙世界", "探险生存"],
    "灵异": ["灵异", "恐怖惊悚", "灵异鬼怪", "僵尸修道", "灵异奇谈"],
    "二次元": ["二次元", "衍生同人", "原生幻想", "轻小说", "搞笑吐槽", "青春日常"],
    "古代言情": ["古代言情", "古代情缘", "宫闱宅斗", "经商种田", "古典架空", "穿越奇情", "女尊王朝", "权谋争霸"],
    "现代言情": ["现代言情", "婚恋情缘", "都市情缘", "豪门世家", "娱乐圈", "职场商战"],
    "浪漫青春": ["浪漫青春", "青春校园", "叛逆成长", "青春纯爱"],
    "玄幻言情": ["玄幻言情", "东方玄幻", "异世大陆", "西方奇幻", "异能超术"],
    "仙侠奇缘": ["仙侠奇缘", "武侠仙侠", "古典仙侠", "奇幻仙侠", "修真仙侠"],
}


class DataEnrichmentService:
    """书籍数据智能补全服务。

    使用轻量级 LLM 调用补全缺失的题材和标签信息。
    支持缓存避免重复调用。
    """

    def __init__(self, session: AsyncSession):
        self.session = session
        self.llm_service = LLMService(session)

    async def _rollback_if_needed(self) -> None:
        """当数据库异常被吞掉继续处理时，显式清理脏事务。"""
        try:
            await self.session.rollback()
        except Exception:
            logger.debug("数据补全回滚失败", exc_info=True)

    async def enrich_book(self, book: ScrapedBook) -> ScrapedBook:
        """补全单本书籍的缺失字段。

        如果题材和标签都已存在，直接返回原对象。
        否则调用 LLM 进行智能补全。
        返回新的 ScrapedBook 对象，不修改原对象（不可变模式）。
        """
        # 如果数据完整，无需补全
        if book.genre and book.tags:
            return book

        # 生成缓存键
        cache_key = f"{book.title}:{book.author}:{book.description[:50] if book.description else ''}"

        # 初始化补全后的值
        new_genre = book.genre
        new_tags = book.tags

        # 检查缓存
        if cache_key in _genre_cache:
            cached = _genre_cache[cache_key]
            new_genre = new_genre or cached.get("genre", "")
            new_tags = new_tags or cached.get("tags", "")
            return replace(book, genre=new_genre, tags=new_tags)

        # 尝试基于标题和描述快速匹配题材
        if not new_genre:
            new_genre = self._quick_genre_match(book.title, book.description or "")

        # 如果仍然没有题材或标签，调用 LLM 补全
        if not new_genre or not new_tags:
            try:
                enriched = await self._llm_enrich(book)
                new_genre = new_genre or enriched.get("genre", "")
                new_tags = new_tags or enriched.get("tags", "")

                # 缓存结果
                _genre_cache[cache_key] = {
                    "genre": new_genre,
                    "tags": new_tags,
                }
            except SQLAlchemyError as e:
                await self._rollback_if_needed()
                logger.debug("LLM 补全触发数据库异常，已回滚: %s", e)
            except Exception as e:
                logger.debug("LLM 补全失败: %s", e)

        return replace(book, genre=new_genre, tags=new_tags)

    async def enrich_books(self, books: list[ScrapedBook]) -> list[ScrapedBook]:
        """批量补全书籍数据。"""
        results = []
        for book in books:
            try:
                enriched = await self.enrich_book(book)
                results.append(enriched)
            except SQLAlchemyError as e:
                await self._rollback_if_needed()
                logger.debug("书籍补全数据库异常 %s: %s", book.title, e)
                results.append(book)
            except Exception as e:
                logger.debug("书籍补全失败 %s: %s", book.title, e)
                results.append(book)
        return results

    def _quick_genre_match(self, title: str, description: str) -> str:
        """基于关键词快速匹配题材。"""
        text = f"{title} {description}".lower()

        genre_scores = {}
        for main_genre, keywords in COMMON_GENRES.items():
            score = 0
            for keyword in keywords:
                if keyword.lower() in text:
                    score += 1
                    # 标题匹配权重更高
                    if keyword.lower() in title.lower():
                        score += 2
            if score > 0:
                genre_scores[main_genre] = score

        if genre_scores:
            # 返回得分最高的题材
            return max(genre_scores.items(), key=lambda x: x[1])[0]

        return ""

    async def _llm_enrich(self, book: ScrapedBook) -> dict:
        """调用 LLM 补全书籍信息。"""
        system_prompt = """你是一个网文分类专家。根据书名和简介，判断这本书最可能属于哪个题材分类，并提取3-5个标签。

## 题材分类选项（必须严格选择其一）
男频分类：玄幻、奇幻、武侠、仙侠、都市、现实、军事、历史、游戏、体育、科幻、悬疑、灵异、二次元
女频分类：古代言情、现代言情、浪漫青春、玄幻言情、仙侠奇缘

## 输出格式
必须以 JSON 格式输出，不要包含其他内容：
{
  "genre": "题材名称",
  "tags": ["标签1", "标签2", "标签3"],
  "reason": "分类理由（一句话）"
}

## 标签提取规则
- 提取书籍的核心元素作为标签
- 常见标签：系统流、穿越、重生、修仙、异能、甜宠、虐恋、豪门等
- 标签应简洁，2-4个字为佳
"""

        user_prompt = f"""请为以下网文进行分类：

书名：{book.title}
作者：{book.author or '未知'}
简介：{book.description or '暂无简介'}

请输出 JSON 格式的分类结果。"""

        try:
            response = await self.llm_service.generate(
                user_prompt,
                system_prompt=system_prompt,
                temperature=0.3,
                max_tokens=200,
            )

            # 解析 JSON 响应
            result = self._parse_llm_response(response)
            return result
        except SQLAlchemyError as e:
            await self._rollback_if_needed()
            logger.warning("LLM 书籍分类失败 %s: %s", book.title, e)
            return {"genre": "", "tags": ""}
        except Exception as e:
            logger.warning("LLM 书籍分类失败 %s: %s", book.title, e)
            return {"genre": "", "tags": ""}

    def _parse_llm_response(self, response: str) -> dict:
        """解析 LLM 返回的 JSON，并确保 tags 是字符串格式。"""
        parsed = {"genre": "", "tags": ""}

        # 尝试直接解析
        try:
            parsed = json.loads(response)
        except json.JSONDecodeError:
            # 尝试从 markdown 代码块中提取
            json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', response, re.DOTALL)
            if json_match:
                try:
                    parsed = json.loads(json_match.group(1))
                except json.JSONDecodeError:
                    pass

            # 尝试从文本中提取 JSON 对象
            if not parsed.get("genre"):
                json_match = re.search(r'(\{[^{}]*"genre"[^{}]*\})', response, re.DOTALL)
                if json_match:
                    try:
                        parsed = json.loads(json_match.group(1))
                    except json.JSONDecodeError:
                        pass

        # 确保 tags 是字符串（将列表转换为逗号分隔）
        tags = parsed.get("tags", "")
        if isinstance(tags, list):
            parsed["tags"] = ",".join(tags)
        elif not isinstance(tags, str):
            parsed["tags"] = str(tags)

        # 确保 genre 是字符串
        genre = parsed.get("genre", "")
        if not isinstance(genre, str):
            parsed["genre"] = str(genre)

        return parsed

    async def batch_classify_titles(self, titles: list[str]) -> list[dict]:
        """批量分类书名（用于手动导入的数据补全）。"""
        if not titles:
            return []

        system_prompt = """你是一个网文分类专家。请为给定的书名列表判断题材分类。

## 题材分类选项
男频：玄幻、奇幻、武侠、仙侠、都市、现实、军事、历史、游戏、体育、科幻、悬疑、灵异、二次元
女频：古代言情、现代言情、浪漫青春、玄幻言情、仙侠奇缘

## 输出格式
返回 JSON 数组，每个元素包含 title 和 genre：
[
  {"title": "书名1", "genre": "题材1"},
  {"title": "书名2", "genre": "题材2"}
]
"""

        user_prompt = f"请为以下书名分类：\n\n" + "\n".join(f"- {t}" for t in titles)

        try:
            response = await self.llm_service.generate(
                user_prompt,
                system_prompt=system_prompt,
                temperature=0.3,
                max_tokens=500,
            )

            # 尝试解析 JSON 数组
            try:
                return json.loads(response)
            except json.JSONDecodeError:
                # 尝试从代码块提取
                match = re.search(r'```(?:json)?\s*(\[.*?\])\s*```', response, re.DOTALL)
                if match:
                    return json.loads(match.group(1))
        except Exception as e:
            logger.warning("批量分类失败: %s", e)

        # 兜底：返回空分类
        return [{"title": t, "genre": ""} for t in titles]
