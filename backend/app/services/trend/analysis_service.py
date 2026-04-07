# AIMETA P=趋势分析服务_利用LLM分析排行榜数据|R=趋势分析_报告生成|NR=不含爬虫逻辑|E=TrendAnalysisService|X=internal|A=服务类|D=sqlalchemy|S=db,net|RD=./README.ai
from __future__ import annotations

import json
import logging
import re
from collections import Counter
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import desc, select, func
from sqlalchemy.ext.asyncio import AsyncSession

from ...models.trend import TrendSnapshot, RankingBook, TrendReport
from ...repositories.trend_repository import (
    RankingBookRepository,
    TrendReportRepository,
    TrendSnapshotRepository,
)
from ...services.llm_service import LLMService
from ...services.prompt_service import PromptService
from .scraping_service import TrendScrapingService

logger = logging.getLogger(__name__)

# 报告缓存 TTL
PLATFORM_OVERVIEW_CATEGORY = "all"


class TrendAnalysisService:
    """利用 LLM 分析平台排行榜趋势。"""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.llm_service = LLMService(session)
        self.prompt_service = PromptService(session)
        self.scraping_service = TrendScrapingService(session)
        self.snapshot_repo = TrendSnapshotRepository(session)
        self.book_repo = RankingBookRepository(session)
        self.report_repo = TrendReportRepository(session)

    def _resolve_platform_category(self, platform: str, category: str) -> str:
        """当调用方仍使用默认 hot 时，自动回退到平台当前支持的首个榜单。"""
        scraper = self.scraping_service.scrapers.get(platform)
        if not scraper:
            return category

        supported_categories = scraper.get_supported_categories()
        if category in supported_categories:
            return category

        if category == "hot" and supported_categories:
            return next(iter(supported_categories))

        return category

    def _resolve_report_category(self, platform: str, category: str = PLATFORM_OVERVIEW_CATEGORY) -> str:
        """解析趋势报告维度，支持平台总览(all)与具体榜单分类。"""
        normalized = (category or PLATFORM_OVERVIEW_CATEGORY).strip()
        if normalized == PLATFORM_OVERVIEW_CATEGORY:
            return PLATFORM_OVERVIEW_CATEGORY
        return self._resolve_platform_category(platform, normalized)

    def _get_report_categories(self, platform: str, category: str) -> list[str]:
        """返回生成报告时需要分析的榜单分类列表。"""
        scraper = self.scraping_service.scrapers.get(platform)
        if not scraper:
            return []

        if category == PLATFORM_OVERVIEW_CATEGORY:
            return list(scraper.get_supported_categories())

        if platform == "fanqie":
            match = re.match(r"^(male|female):(\d+):(read|new)$", category)
            if match:
                gender, category_id, _rank_kind = match.groups()
                return [
                    f"{gender}:{category_id}:read",
                    f"{gender}:{category_id}:new",
                ]

        return [category]

    def _looks_like_json_payload(self, text: str) -> bool:
        stripped = (text or "").strip()
        if not stripped:
            return False

        return (
            stripped.startswith("{")
            or stripped.startswith("```json")
            or stripped.startswith("```")
            or ('"summary"' in stripped and ('"genre_distribution"' in stripped or '"hot_keywords"' in stripped))
        )

    def _decode_json_string(self, value: str) -> str:
        if not value:
            return ""

        try:
            return json.loads(f'"{value}"').strip()
        except json.JSONDecodeError:
            return value.replace("\\n", "\n").replace("\\r", "").replace('\\"', '"').strip()

    def _extract_string_field_from_text(self, text: str, field_name: str) -> str:
        match = re.search(rf'"{re.escape(field_name)}"\s*:\s*"', text)
        if not match:
            return ""

        chars: list[str] = []
        escaped = False
        for ch in text[match.end():]:
            if escaped:
                chars.append(ch)
                escaped = False
                continue
            if ch == "\\":
                chars.append(ch)
                escaped = True
                continue
            if ch == '"':
                break
            chars.append(ch)

        return self._decode_json_string("".join(chars))

    def _extract_string_array_from_text(self, text: str, field_name: str, limit: int = 10) -> list[str]:
        match = re.search(rf'"{re.escape(field_name)}"\s*:\s*\[', text)
        if not match:
            return []

        items: list[str] = []
        chars: list[str] = []
        in_string = False
        escaped = False

        for ch in text[match.end():]:
            if in_string:
                if escaped:
                    chars.append(ch)
                    escaped = False
                    continue
                if ch == "\\":
                    chars.append(ch)
                    escaped = True
                    continue
                if ch == '"':
                    decoded = self._decode_json_string("".join(chars))
                    if decoded:
                        items.append(decoded)
                        if len(items) >= limit:
                            break
                    chars = []
                    in_string = False
                    continue
                chars.append(ch)
                continue

            if ch == '"':
                in_string = True
                chars = []
                continue
            if ch == "]":
                break

        return items

    def _merge_report_fields(self, primary: dict[str, Any], fallback: dict[str, Any]) -> dict[str, Any]:
        merged = dict(primary)

        for field in (
            "genre_distribution",
            "hot_keywords",
            "hot_elements",
            "reader_preferences",
            "opportunities",
            "creation_suggestions",
        ):
            if not merged.get(field):
                fallback_value = fallback.get(field)
                if fallback_value:
                    merged[field] = fallback_value

        if not merged.get("trend_summary") or self._looks_like_json_payload(str(merged.get("trend_summary", ""))):
            merged["trend_summary"] = fallback.get("trend_summary", "")

        if not merged.get("ai_full_report"):
            merged["ai_full_report"] = fallback.get("ai_full_report", "")

        return merged

    def _extract_report_fields_from_partial_text(self, text: str) -> dict[str, Any]:
        summary = self._extract_string_field_from_text(text, "summary")
        hot_keywords = self._extract_string_array_from_text(text, "hot_keywords")
        creation_suggestions = self._extract_string_array_from_text(text, "creation_suggestions")

        result: dict[str, Any] = {}
        if summary:
            result["trend_summary"] = summary
        if hot_keywords:
            result["hot_keywords"] = hot_keywords
        if creation_suggestions:
            result["creation_suggestions"] = creation_suggestions
        if result:
            result["ai_full_report"] = text
        return result

    def _extract_report_fields_from_mapping(self, data: dict[str, Any], raw_text: str = "") -> dict[str, Any]:
        result: dict[str, Any] = {
            "genre_distribution": data.get("genre_distribution") if isinstance(data.get("genre_distribution"), dict) else {},
            "hot_keywords": [item for item in data.get("hot_keywords", []) if isinstance(item, str) and item.strip()]
            if isinstance(data.get("hot_keywords"), list)
            else [],
            "trend_summary": data.get("summary", "").strip() if isinstance(data.get("summary"), str) else "",
            "hot_elements": data.get("hot_elements") if isinstance(data.get("hot_elements"), list) else [],
            "reader_preferences": data.get("reader_preferences") if isinstance(data.get("reader_preferences"), dict) else {},
            "opportunities": data.get("opportunities") if isinstance(data.get("opportunities"), list) else [],
            "creation_suggestions": [
                item for item in data.get("creation_suggestions", []) if isinstance(item, str) and item.strip()
            ]
            if isinstance(data.get("creation_suggestions"), list)
            else [],
            "ai_full_report": data.get("full_report", "").strip() if isinstance(data.get("full_report"), str) else "",
        }

        nested_source = ""
        if self._looks_like_json_payload(result["trend_summary"]):
            nested_source = result["trend_summary"]
        elif self._looks_like_json_payload(result["ai_full_report"]):
            nested_source = result["ai_full_report"]

        if nested_source and nested_source != raw_text:
            nested_result = self._extract_report_fields_from_text(nested_source, allow_plain_summary=False)
            if nested_result:
                result = self._merge_report_fields(result, nested_result)

        if raw_text and not result["ai_full_report"]:
            result["ai_full_report"] = raw_text

        return result

    def _extract_report_fields_from_text(self, text: str, allow_plain_summary: bool = True) -> dict[str, Any]:
        stripped = (text or "").strip()
        if not stripped:
            return {}

        try:
            data = json.loads(stripped)
        except json.JSONDecodeError:
            data = None

        if isinstance(data, dict):
            return self._extract_report_fields_from_mapping(data, stripped)

        json_str = self._extract_json_from_text(stripped)
        if json_str:
            try:
                data = json.loads(json_str)
            except json.JSONDecodeError:
                data = None
            if isinstance(data, dict):
                return self._extract_report_fields_from_mapping(data, stripped)

        partial = self._extract_report_fields_from_partial_text(stripped)
        if partial:
            return partial

        if allow_plain_summary and not self._looks_like_json_payload(stripped):
            return {
                "trend_summary": stripped[:500],
                "ai_full_report": stripped,
            }

        return {}

    def _build_report_result(self, platform: str, fields: dict[str, Any], raw_text: str = "") -> dict:
        fallback_summary = raw_text[:500] if raw_text and not self._looks_like_json_payload(raw_text) else ""
        return {
            "platform": platform,
            "report_date": datetime.utcnow().isoformat(),
            "genre_distribution": fields.get("genre_distribution") or {},
            "hot_keywords": fields.get("hot_keywords") or [],
            "trend_summary": fields.get("trend_summary") or fallback_summary,
            "ai_full_report": fields.get("ai_full_report") or raw_text or "",
            "hot_elements": fields.get("hot_elements") or [],
            "reader_preferences": fields.get("reader_preferences") or {},
            "opportunities": fields.get("opportunities") or [],
            "creation_suggestions": fields.get("creation_suggestions") or [],
        }

    def _merge_report_result(self, primary: dict[str, Any], fallback: dict[str, Any]) -> dict[str, Any]:
        merged = dict(fallback)

        for field in (
            "genre_distribution",
            "hot_keywords",
            "trend_summary",
            "ai_full_report",
            "hot_elements",
            "reader_preferences",
            "opportunities",
            "creation_suggestions",
        ):
            value = primary.get(field)
            if value:
                merged[field] = value

        merged["platform"] = primary.get("platform") or fallback.get("platform")
        merged["report_date"] = primary.get("report_date") or fallback.get("report_date")
        return merged

    def _normalize_report_record(self, report: TrendReport) -> dict[str, Any]:
        recovered = self._extract_report_fields_from_text(
            report.ai_full_report or report.trend_summary or "",
            allow_plain_summary=False,
        )

        trend_summary = report.trend_summary or ""
        if not trend_summary or self._looks_like_json_payload(trend_summary):
            trend_summary = recovered.get("trend_summary", "")

        return {
            "platform": report.platform,
            "category": report.category or PLATFORM_OVERVIEW_CATEGORY,
            "report_date": report.report_date.isoformat(),
            "genre_distribution": report.genre_distribution or recovered.get("genre_distribution") or {},
            "hot_keywords": report.hot_keywords or recovered.get("hot_keywords") or [],
            "trend_summary": trend_summary,
            "ai_full_report": report.ai_full_report or recovered.get("ai_full_report") or "",
            "hot_elements": report.hot_elements or recovered.get("hot_elements") or [],
            "reader_preferences": report.reader_preferences or recovered.get("reader_preferences") or {},
            "opportunities": report.opportunities or recovered.get("opportunities") or [],
            "creation_suggestions": report.creation_suggestions or recovered.get("creation_suggestions") or [],
        }

    async def _serialize_cached_report(self, report: TrendReport, category: str) -> dict:
        payload = self._normalize_report_record(report)
        changed = False

        if category != PLATFORM_OVERVIEW_CATEGORY and not payload["genre_distribution"]:
            fallback_distribution = await self.get_genre_distribution(report.platform, category)
            if fallback_distribution.get("genres"):
                payload["genre_distribution"] = fallback_distribution["genres"]

        if category != PLATFORM_OVERVIEW_CATEGORY and not payload["hot_keywords"]:
            payload["hot_keywords"] = await self.get_hot_keywords(report.platform, category)

        for field in (
            "genre_distribution",
            "hot_keywords",
            "trend_summary",
            "ai_full_report",
            "hot_elements",
            "reader_preferences",
            "opportunities",
            "creation_suggestions",
        ):
            value = payload[field]
            current = getattr(report, field)
            if value and current != value:
                setattr(report, field, value)
                changed = True

        if changed:
            await self.session.flush()

        return payload

    def _serialize_report(self, report: TrendReport) -> dict:
        """将 ORM 报告对象转换为接口响应。"""
        return self._normalize_report_record(report)

    async def _get_latest_market_report(self, platform: str) -> Optional[TrendReport]:
        """获取平台总览报告，若不存在则回退到任意分类的最新报告。"""
        return (
            await self.report_repo.get_latest_report(platform, PLATFORM_OVERVIEW_CATEGORY)
            or await self.report_repo.get_latest_report_any_category(platform)
        )

    async def get_genre_distribution(self, platform: str, category: str = "hot") -> dict:
        """获取题材分布统计（不依赖 LLM）。"""
        category = self._resolve_platform_category(platform, category)
        snapshot = await self.snapshot_repo.get_latest_snapshot_any_age(platform, category)
        if not snapshot:
            # 先尝试抓取数据
            await self.scraping_service.get_ranking(platform, category)
            snapshot = await self.snapshot_repo.get_latest_snapshot_any_age(platform, category)

        if not snapshot:
            return {"genres": {}, "total": 0, "snapshot_date": None}

        distribution = await self.book_repo.get_genre_distribution(snapshot.id)
        total = sum(distribution.values())

        # 计算百分比
        genres_with_pct = {}
        for genre, count in distribution.items():
            genres_with_pct[genre] = {
                "count": count,
                "percentage": round(count / total * 100, 1) if total > 0 else 0,
            }

        return {
            "genres": genres_with_pct,
            "total": total,
            "snapshot_date": snapshot.snapshot_date.isoformat() if snapshot.snapshot_date else None,
        }

    # 常见网文元素关键词（用于从书名/描述中提取）
    COMMON_NOVEL_KEYWORDS = [
        "系统", "穿越", "重生", "修仙", "都市", "玄幻", "奇幻", "武侠", "仙侠",
        "异能", "星际", "科幻", "游戏", "异界", "末日", "洪荒", "上古",
        "甜宠", "虐恋", "爽文", "无敌", "废柴", "逆袭", "成神", "成仙",
        "丹药", "阵法", "炼器", "符文", "血脉", "天赋", "觉醒", "进化",
        "校花", "总裁", "霸道", "萌宝", "团宠", "马甲", "大佬", "神医",
        "兵王", "杀手", "特工", "黑客", "农民", "山村", "乡村", "直播",
        "娱乐", "宠溺", "占有", "契约", "婚约", "闪婚", "暗恋", "追妻",
        "复仇", "打脸", "装逼", "崛起", "称霸", "热血", "冷酷", "深情",
        "种田", "空间", "随身", "农场", "牧场", "钓鱼", "悠闲", "致富",
        "玄幻", "都市", "历史", "军事", "悬疑", "灵异", "同人", "现实",
    ]

    # 题材关键词（用于补充 genre）
    GENRE_KEYWORDS = [
        "玄幻", "仙侠", "都市", "历史", "军事", "悬疑", "科幻", "游戏",
        "体育", "灵异", "同人", "武侠", "奇幻", "二次元", "现实", "短篇",
    ]

    async def get_hot_keywords(self, platform: str, category: str = "hot") -> list[str]:
        """从书名、标签和题材中提取热门关键词。"""
        category = self._resolve_platform_category(platform, category)
        snapshot = await self.snapshot_repo.get_latest_snapshot_any_age(platform, category)
        if not snapshot:
            return []

        books = await self.book_repo.get_books_by_snapshot(snapshot.id)
        all_keywords: list[str] = []

        # 1. 从 tags 提取
        for book in books:
            if book.tags:
                all_keywords.extend(t.strip() for t in book.tags.split(",") if t.strip())

        # 2. 从 genre 提取（题材本身也是关键词）
        for book in books:
            if book.genre:
                all_keywords.append(book.genre)

        # 3. 从书名中提取常见网文元素
        for book in books:
            title = book.title or ""
            desc = book.description or ""
            text = title + " " + desc

            for keyword in self.COMMON_NOVEL_KEYWORDS:
                if keyword in text:
                    all_keywords.append(keyword)

        counter = Counter(all_keywords)
        return [kw for kw, _ in counter.most_common(30)]

    async def get_trend_report(
        self,
        platform: str,
        category: str = PLATFORM_OVERVIEW_CATEGORY,
        force_regenerate: bool = False,
    ) -> dict:
        """获取或生成趋势分析报告。"""
        category = self._resolve_report_category(platform, category)

        # 检查是否有缓存的报告
        if not force_regenerate:
            existing = await self.report_repo.get_latest_report(platform, category)
            if existing:
                return await self._serialize_cached_report(existing, category)

        # 获取各分类排行榜数据用于分析
        all_books_data = []
        scraper = self.scraping_service.scrapers.get(platform)
        if not scraper:
            return {"error": f"不支持的平台: {platform}", "platform": platform, "category": category}

        for cat_key in self._get_report_categories(platform, category):
            books = await self.scraping_service.get_ranking(platform, cat_key, limit=20)
            all_books_data.append({
                "category": cat_key,
                "category_name": scraper.get_category_name(cat_key),
                "books": books,
            })

        if not any(cat["books"] for cat in all_books_data):
            return {"error": "无法获取排行榜数据", "platform": platform, "category": category}

        # 生成 LLM 分析报告
        report = await self._generate_llm_report(platform, all_books_data)
        report["category"] = category

        # 保存到数据库
        await self._save_report(platform, category, report)

        return report

    async def get_creation_suggestion(self, context: str = "") -> str:
        """基于所有平台的风向数据给出创作建议（给灵感模式用）。"""
        # 优先使用已缓存的完整报告中的 creation_suggestions，避免重复 LLM 调用
        all_suggestions: list[str] = []
        genre_summaries: list[str] = []

        for platform in ["qidian", "fanqie"]:
            existing = await self._get_latest_market_report(platform)
            if existing:
                if existing.creation_suggestions:
                    all_suggestions.extend(existing.creation_suggestions[:3])
                if existing.genre_distribution:
                    top_genres = list(existing.genre_distribution.keys())[:3]
                    genre_summaries.append(f"【{existing.hot_keywords and existing.hot_keywords[0] or platform}】热门: {', '.join(top_genres)}")

        if all_suggestions:
            return "\n".join(all_suggestions[:5])

        # 降级：从排行榜数据统计
        suggestions = []
        for platform in ["qidian", "fanqie"]:
            genre_dist = await self.get_genre_distribution(platform)
            keywords = await self.get_hot_keywords(platform)
            if genre_dist.get("genres"):
                top_genres = list(genre_dist["genres"].keys())[:5]
                suggestions.append(
                    f"【{platform}平台】热门题材: {', '.join(top_genres)}; "
                    f"热门关键词: {', '.join(keywords[:10])}"
                )

        if not suggestions:
            return ""

        prompt = (
            "请根据以下网文平台市场数据，用一段话（100字以内）给出当前的市场风向总结和创作建议。"
            f"用户当前创作上下文: {context or '灵感模式启动'}\n\n"
            f"市场数据:\n" + "\n".join(suggestions)
        )

        try:
            return await self.llm_service.generate(
                prompt,
                system_prompt="你是网文市场分析师，请简洁地总结市场趋势并给出创作建议。",
                temperature=0.5,
                max_tokens=300,
            )
        except Exception as e:
            logger.error("生成创作建议失败: %s", e)
            return " | ".join(suggestions)

    async def get_inspiration_summary(self) -> dict:
        """聚合两个平台最新报告，返回灵感模式用的轻量摘要（纯 DB 查询，不触发 LLM）。"""
        all_genres: Counter = Counter()
        all_keywords: list[str] = []
        all_suggestions: list[str] = []
        latest_date: Optional[str] = None

        for platform in ["qidian", "fanqie"]:
            report = await self._get_latest_market_report(platform)
            if not report:
                continue
            if report.genre_distribution:
                for genre, data in report.genre_distribution.items():
                    count = data.get("count", 1) if isinstance(data, dict) else 1
                    all_genres[genre] += count
            if report.hot_keywords:
                all_keywords.extend(report.hot_keywords[:15])
            if report.creation_suggestions:
                all_suggestions.extend(report.creation_suggestions[:3])
            if report.report_date:
                date_str = report.report_date.isoformat()
                if not latest_date or date_str > latest_date:
                    latest_date = date_str

        # 去重并排序
        top_genres = [g for g, _ in all_genres.most_common(5)]
        seen_kw: set[str] = set()
        deduped_keywords: list[str] = []
        for kw in all_keywords:
            if kw not in seen_kw:
                seen_kw.add(kw)
                deduped_keywords.append(kw)
            if len(deduped_keywords) >= 10:
                break

        return {
            "top_genres": top_genres,
            "hot_keywords": deduped_keywords,
            "creation_suggestions": all_suggestions[:5],
            "data_date": latest_date,
            "has_data": bool(top_genres or deduped_keywords),
        }

    async def get_market_context_for_inspiration(self) -> dict:
        """获取灵感模式用的市场上下文数据（get_inspiration_summary 的别名）。"""
        return await self.get_inspiration_summary()

    # ==================== 私有方法 ====================

    async def _generate_llm_report(self, platform: str, all_books_data: list[dict]) -> dict:
        """调用 LLM 生成趋势分析报告。"""
        # 准备输入数据
        data_summary = json.dumps(all_books_data, ensure_ascii=False, indent=2)

        # 截断过长数据
        if len(data_summary) > 8000:
            data_summary = data_summary[:8000] + "\n... (数据已截断)"

        try:
            prompt_content = await self.prompt_service.get_prompt("trend_analysis")
        except Exception:
            prompt_content = "你是网文市场趋势分析师，请分析以下排行榜数据并给出趋势报告。"

        user_message = (
            f"请分析以下 {platform} 平台的排行榜数据，生成市场趋势报告。\n\n"
            f"排行榜数据:\n{data_summary}"
        )

        try:
            response = await self.llm_service.get_llm_response(
                system_prompt=prompt_content,
                conversation_history=[{"role": "user", "content": user_message}],
                temperature=0.3,
                max_tokens=2000,
                response_format="json_object",
            )

            return self._parse_llm_response(platform, response)
        except Exception as e:
            logger.error("LLM 趋势报告生成失败: %s", e)
            return self._generate_basic_report(platform, all_books_data)

    def _parse_llm_response(self, platform: str, response: str) -> dict:
        """解析 LLM 返回的 JSON 报告。

        LLM 可能返回两种格式：
        1. 标准格式：顶层直接有 hot_keywords, genre_distribution 等字段
        2. 嵌套格式：summary 字段是包含所有数据的 JSON 字符串
        """
        try:
            data = json.loads(response)

            # 检查顶层是否有 hot_keywords
            hot_keywords = data.get("hot_keywords", [])
            if hot_keywords:
                # 标准格式
                return {
                    "platform": platform,
                    "report_date": datetime.utcnow().isoformat(),
                    "genre_distribution": data.get("genre_distribution", {}),
                    "hot_keywords": hot_keywords,
                    "trend_summary": data.get("summary", ""),
                    "hot_elements": data.get("hot_elements", []),
                    "reader_preferences": data.get("reader_preferences", {}),
                    "opportunities": data.get("opportunities", []),
                    "creation_suggestions": data.get("creation_suggestions", []),
                    "ai_full_report": data.get("full_report", ""),
                }

            # 嵌套格式：尝试从 summary 或 full_report 中解析内部 JSON
            summary_str = data.get("summary", "") or data.get("full_report", "") or ""
            if summary_str:
                # 尝试提取 JSON（可能包含在 markdown 代码块中）
                json_str = self._extract_json_from_text(summary_str)
                if json_str:
                    inner_data = json.loads(json_str)
                    return {
                        "platform": platform,
                        "report_date": datetime.utcnow().isoformat(),
                        "genre_distribution": inner_data.get("genre_distribution", {}),
                        "hot_keywords": inner_data.get("hot_keywords", []),
                        "trend_summary": inner_data.get("summary", summary_str[:500]),
                        "hot_elements": inner_data.get("hot_elements", []),
                        "reader_preferences": inner_data.get("reader_preferences", {}),
                        "opportunities": inner_data.get("opportunities", []),
                        "creation_suggestions": inner_data.get("creation_suggestions", []),
                        "ai_full_report": summary_str,
                    }

            # 无法解析，返回基础格式
            return {
                "platform": platform,
                "report_date": datetime.utcnow().isoformat(),
                "trend_summary": summary_str[:500] if summary_str else response[:500],
                "ai_full_report": response if response else "",
            }
        except json.JSONDecodeError:
            # 响应本身不是有效 JSON，尝试从中提取 JSON
            json_str = self._extract_json_from_text(response)
            if json_str:
                try:
                    data = json.loads(json_str)
                    return {
                        "platform": platform,
                        "report_date": datetime.utcnow().isoformat(),
                        "genre_distribution": data.get("genre_distribution", {}),
                        "hot_keywords": data.get("hot_keywords", []),
                        "trend_summary": data.get("summary", "")[:500],
                        "hot_elements": data.get("hot_elements", []),
                        "reader_preferences": data.get("reader_preferences", {}),
                        "opportunities": data.get("opportunities", []),
                        "creation_suggestions": data.get("creation_suggestions", []),
                        "ai_full_report": json_str,
                    }
                except json.JSONDecodeError:
                    pass

            return {
                "platform": platform,
                "report_date": datetime.utcnow().isoformat(),
                "trend_summary": response[:500] if response else "",
                "ai_full_report": response if response else "",
            }

    def _extract_json_from_text(self, text: str) -> str | None:
        """从文本中提取 JSON 字符串。"""
        import re

        # 查找 ```json ... ``` 代码块
        match = re.search(r'```json\s*', text)
        if match:
            start = match.end()
            # 找到代码块结束位置（处理嵌套大括号）
            json_text = text[start:]
            brace_count = 0
            in_string = False
            escaped = False

            for i, ch in enumerate(json_text):
                if escaped:
                    escaped = False
                    continue
                if ch == '\\' and in_string:
                    escaped = True
                    continue
                if ch == '"' and not escaped:
                    in_string = not in_string
                    continue
                if in_string:
                    continue

                if ch == '{':
                    if brace_count == 0:
                        start = start + i
                    brace_count += 1
                elif ch == '}':
                    brace_count -= 1
                    if brace_count == 0:
                        end = start + i + 1
                        potential_json = text[start:end]
                        # 验证是否是有效 JSON
                        try:
                            json.loads(potential_json)
                            return potential_json
                        except json.JSONDecodeError:
                            pass
                        break

        # 直接尝试解析整个文本（去除首尾空白）
        text = text.strip()
        if text.startswith('{') and text.endswith('}'):
            try:
                json.loads(text)
                return text
            except json.JSONDecodeError:
                pass

        return None

    async def _generate_llm_report(self, platform: str, all_books_data: list[dict]) -> dict:
        data_summary = json.dumps(all_books_data, ensure_ascii=False, indent=2)
        if len(data_summary) > 8000:
            data_summary = data_summary[:8000] + "\n... (鏁版嵁宸叉埅鏂?"

        try:
            prompt_content = await self.prompt_service.get_prompt("trend_analysis")
        except Exception:
            prompt_content = "浣犳槸缃戞枃甯傚満瓒嬪娍鍒嗘瀽甯堬紝璇峰垎鏋愪互涓嬫帓琛屾鏁版嵁骞剁粰鍑鸿秼鍔挎姤鍛娿€?"

        base_user_message = (
            f"璇峰垎鏋愪互涓?{platform} 骞冲彴鐨勬帓琛屾鏁版嵁锛岀敓鎴愬競鍦鸿秼鍔挎姤鍛娿€俓n\n"
            f"鎺掕姒滄暟鎹?\n{data_summary}"
        )
        basic_report = self._generate_basic_report(platform, all_books_data)
        last_report = basic_report

        try:
            for attempt in range(2):
                extra_instruction = ""
                if attempt == 1:
                    extra_instruction = (
                        "\n\n涓婁竴娆¤緭鍑哄お闀挎垨涓嶅畬鏁淬€傝繖娆¤涓ユ牸閬靛畧锛?\n"
                        "1. 鍙繑鍥炵函 JSON 瀵硅薄锛屼笉瑕佺敤 Markdown 浠ｇ爜鍧椼€?\n"
                        "2. summary 鎺у埗鍦?80-160 瀛椼€?\n"
                        "3. hot_keywords 鏈€澶?10 涓紝hot_elements/opportunities/creation_suggestions 鍚勬渶澶?3 鏉°€?\n"
                        "4. full_report 涓嶆槸蹇呴』瀛楁锛屽彲浠ヨ繑鍥炵┖瀛楃涓诧紝濡傛灉杩斿洖璇蜂笉瑕佽秴杩?200 瀛椼€?\n"
                    )

                response = await self.llm_service.get_llm_response(
                    system_prompt=prompt_content,
                    conversation_history=[{"role": "user", "content": base_user_message + extra_instruction}],
                    temperature=0.3,
                    max_tokens=3000,
                    response_format="json_object",
                )

                parsed_report = self._parse_llm_response(platform, response)
                merged_report = self._merge_report_result(parsed_report, basic_report)
                last_report = merged_report

                if not self._response_needs_retry(response, merged_report):
                    return merged_report

                logger.warning(
                    "Trend report response appears truncated; retrying with stricter constraints: platform=%s attempt=%s",
                    platform,
                    attempt + 1,
                )

            return last_report
        except Exception as e:
            logger.error("LLM 瓒嬪娍鎶ュ憡鐢熸垚澶辫触: %s", e)
            return basic_report

    def _response_needs_retry(self, raw_response: str, report: dict[str, Any]) -> bool:
        if not report.get("trend_summary"):
            return True

        if self._looks_like_json_payload(str(report.get("trend_summary", ""))):
            return True

        return self._looks_like_json_payload(raw_response) and not self._extract_json_from_text(raw_response)

    def _parse_llm_response(self, platform: str, response: str) -> dict:
        fields = self._extract_report_fields_from_text(response)
        return self._build_report_result(platform, fields, raw_text=response)

    def _extract_json_from_text(self, text: str) -> str | None:
        stripped = (text or "").strip()
        if not stripped:
            return None

        fence_match = re.search(r"```(?:json)?\s*", stripped, flags=re.IGNORECASE)
        if fence_match:
            stripped = stripped[fence_match.end():]

        start_index = stripped.find("{")
        if start_index == -1:
            return None

        candidate = stripped[start_index:]
        brace_count = 0
        in_string = False
        escaped = False
        json_start: Optional[int] = None

        for idx, ch in enumerate(candidate):
            if escaped:
                escaped = False
                continue
            if ch == "\\" and in_string:
                escaped = True
                continue
            if ch == '"':
                in_string = not in_string
                continue
            if in_string:
                continue

            if ch == "{":
                if json_start is None:
                    json_start = idx
                brace_count += 1
                continue

            if ch == "}":
                brace_count -= 1
                if brace_count == 0 and json_start is not None:
                    potential_json = candidate[json_start:idx + 1]
                    try:
                        json.loads(potential_json)
                        return potential_json
                    except json.JSONDecodeError:
                        return None

        if stripped.startswith("{") and stripped.endswith("}"):
            try:
                json.loads(stripped)
                return stripped
            except json.JSONDecodeError:
                return None

        return None

    def _generate_basic_report(self, platform: str, all_books_data: list[dict]) -> dict:
        """当 LLM 不可用时，生成基础统计报告。"""
        all_genres = Counter()
        all_keywords = []
        total_books = 0

        for cat_data in all_books_data:
            for book in cat_data.get("books", []):
                total_books += 1
                genre = book.get("genre", "")
                if genre:
                    all_genres[genre] += 1
                    all_keywords.append(genre)  # genre 也是关键词
                tags = book.get("tags", "")
                if tags:
                    all_keywords.extend(t.strip() for t in tags.split(",") if t.strip())

                # 从书名和描述中提取常见网文元素
                title = book.get("title", "") or ""
                desc = book.get("description", "") or ""
                text = title + " " + desc
                for keyword in self.COMMON_NOVEL_KEYWORDS:
                    if keyword in text:
                        all_keywords.append(keyword)

        top_genres = dict(all_genres.most_common(10))
        keywords_counter = Counter(all_keywords)

        return {
            "platform": platform,
            "report_date": datetime.utcnow().isoformat(),
            "genre_distribution": {
                k: {"count": v, "percentage": round(v / total_books * 100, 1)}
                for k, v in top_genres.items()
            } if total_books > 0 else {},
            "hot_keywords": [kw for kw, _ in keywords_counter.most_common(20)],
            "trend_summary": f"共分析 {total_books} 本书，涉及 {len(top_genres)} 个题材分类。",
            "ai_full_report": "",
        }

    async def _save_report(self, platform: str, category: str, report: dict) -> None:
        """保存报告到数据库。"""
        report_obj = TrendReport(
            platform=platform,
            category=category,
            genre_distribution=report.get("genre_distribution"),
            hot_keywords=report.get("hot_keywords", []),
            trend_summary=report.get("trend_summary", ""),
            ai_full_report=report.get("ai_full_report", ""),
            hot_elements=report.get("hot_elements", []),
            reader_preferences=report.get("reader_preferences", {}),
            opportunities=report.get("opportunities", []),
            creation_suggestions=report.get("creation_suggestions", []),
        )
        self.session.add(report_obj)
        await self.session.flush()
        logger.info("趋势报告已保存: %s/%s", platform, category)
