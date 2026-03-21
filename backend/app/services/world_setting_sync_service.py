"""
世界设定同步服务

从章节大纲和摘要中提取关键地点和主要阵营，写入独立的数据库表。
"""
import json
import logging
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.novel import ChapterOutline, Chapter, NovelBlueprint
from ..models.key_location import KeyLocation
from ..models.faction import Faction
from .key_location_service import KeyLocationService
from .faction_service import FactionService
from .llm_service import LLMService
from .prompt_service import PromptService

logger = logging.getLogger(__name__)


class WorldSettingSyncResult:
    """同步结果"""
    def __init__(self):
        self.new_locations: List[Dict[str, Any]] = []
        self.new_factions: List[Dict[str, Any]] = []
        self.total_locations: int = 0
        self.total_factions: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "new_locations": self.new_locations,
            "new_factions": self.new_factions,
            "total_locations": self.total_locations,
            "total_factions": self.total_factions,
            "added_count": len(self.new_locations) + len(self.new_factions)
        }


class WorldSettingSyncService:
    """世界设定同步服务"""

    def __init__(self, db: AsyncSession, llm_service: LLMService, prompt_service: PromptService):
        self.db = db
        self.llm_service = llm_service
        self.prompt_service = prompt_service

    async def sync_from_chapters(self, project_id: str) -> WorldSettingSyncResult:
        """
        从所有章节大纲和摘要中提取地点和阵营，写入 key_locations / factions 表。
        同时为已有条目补充缺失的 first_appear_chapter。
        """
        result = WorldSettingSyncResult()

        # 1. 确认项目蓝图存在
        blueprint_result = await self.db.execute(
            select(NovelBlueprint).where(NovelBlueprint.project_id == project_id)
        )
        blueprint = blueprint_result.scalar_one_or_none()
        if not blueprint:
            logger.warning(f"[Sync] Project {project_id} has no blueprint")
            return result

        # 2. 获取所有章节大纲
        outlines_result = await self.db.execute(
            select(ChapterOutline)
            .where(ChapterOutline.project_id == project_id)
            .order_by(ChapterOutline.chapter_number)
        )
        outlines = list(outlines_result.scalars().all())

        # 3. 获取所有章节摘要
        chapters_result = await self.db.execute(
            select(Chapter)
            .where(Chapter.project_id == project_id)
            .order_by(Chapter.chapter_number)
        )
        chapters = list(chapters_result.scalars().all())

        logger.info(f"[Sync] Project {project_id}: {len(outlines)} outlines, {len(chapters)} chapters")

        if not outlines and not chapters:
            logger.warning(f"[Sync] Project {project_id} has no chapter content to analyze")
            return result

        # 建立章节内容映射（用于查找首次出现）
        self._chapter_contents_map = self._build_chapter_contents_map(outlines, chapters)

        # 4. 从新表读取已有的地点和阵营名称
        loc_result = await self.db.execute(
            select(KeyLocation).where(KeyLocation.project_id == project_id)
        )
        existing_loc_rows = list(loc_result.scalars().all())

        fac_result = await self.db.execute(
            select(Faction).where(Faction.project_id == project_id)
        )
        existing_fac_rows = list(fac_result.scalars().all())

        existing_locations = [row.name for row in existing_loc_rows]
        existing_factions = [row.name for row in existing_fac_rows]

        logger.info(
            f"[Sync] Existing (from tables): {len(existing_locations)} locations, "
            f"{len(existing_factions)} factions"
        )

        # 5. 为已有条目补充缺失的 first_appear_chapter
        for loc in existing_loc_rows:
            if loc.first_appear_chapter is None:
                chapter = self._find_first_appear_chapter(loc.name)
                if chapter is not None:
                    loc.first_appear_chapter = chapter
                    logger.debug(f"[Sync] Updated existing location chapter: {loc.name} -> {chapter}")

        for fac in existing_fac_rows:
            if fac.first_appear_chapter is None:
                chapter = self._find_first_appear_chapter(fac.name)
                if chapter is not None:
                    fac.first_appear_chapter = chapter
                    logger.debug(f"[Sync] Updated existing faction chapter: {fac.name} -> {chapter}")

        await self.db.commit()

        # 6. 构建章节内容文本，交给 LLM 提取新条目
        chapter_contents = self._build_chapter_contents(outlines, chapters)
        if not chapter_contents.strip():
            return result

        new_items = await self._extract_new_items(
            existing_locations=existing_locations,
            existing_factions=existing_factions,
            chapter_contents=chapter_contents
        )

        logger.info(
            f"[Sync] LLM extracted: {len(new_items['new_locations'])} locations, "
            f"{len(new_items['new_factions'])} factions"
        )

        # 7. 写入新表
        key_loc_svc = KeyLocationService(self.db)
        faction_svc = FactionService(self.db, self.prompt_service)

        if new_items["new_locations"]:
            await key_loc_svc.upsert_locations(project_id, new_items["new_locations"])
        if new_items["new_factions"]:
            await faction_svc.upsert_factions(project_id, new_items["new_factions"])

        # 8. 统计结果
        all_locs = await key_loc_svc.get_locations_by_project(project_id)
        all_facs = await faction_svc.get_factions_by_project(project_id)

        result.new_locations = new_items["new_locations"]
        result.new_factions = new_items["new_factions"]
        result.total_locations = len(all_locs)
        result.total_factions = len(all_facs)

        logger.info(
            f"[Sync] Success for project {project_id}: "
            f"+{len(result.new_locations)} locations, +{len(result.new_factions)} factions, "
            f"total {result.total_locations} locations, {result.total_factions} factions"
        )

        return result

    def _build_chapter_contents_map(
        self,
        outlines: List[ChapterOutline],
        chapters: List[Chapter]
    ) -> Dict[int, str]:
        """构建章节内容映射（章节号 -> 内容文本）"""
        contents_map = {}
        outline_map = {o.chapter_number: o for o in outlines}
        chapter_map = {c.chapter_number: c for c in chapters}
        all_chapter_numbers = sorted(set(outline_map.keys()) | set(chapter_map.keys()))

        for num in all_chapter_numbers:
            lines = []
            outline = outline_map.get(num)
            chapter = chapter_map.get(num)
            if outline:
                lines.append(f"【第{num}章大纲】{outline.title}")
                if outline.summary:
                    lines.append(f"摘要：{outline.summary}")
            if chapter and chapter.real_summary:
                lines.append(f"【第{num}章实际内容摘要】")
                lines.append(chapter.real_summary)
            if lines:
                contents_map[num] = "\n".join(lines)

        return contents_map

    def _build_chapter_contents(
        self,
        outlines: List[ChapterOutline],
        chapters: List[Chapter]
    ) -> str:
        """构建章节内容文本（供 LLM 分析）"""
        lines = []
        outline_map = {o.chapter_number: o for o in outlines}
        chapter_map = {c.chapter_number: c for c in chapters}
        all_chapter_numbers = sorted(set(outline_map.keys()) | set(chapter_map.keys()))

        for num in all_chapter_numbers:
            outline = outline_map.get(num)
            chapter = chapter_map.get(num)
            if outline:
                lines.append(f"【第{num}章大纲】{outline.title}")
                if outline.summary:
                    lines.append(f"摘要：{outline.summary}")
                lines.append("")
            if chapter and chapter.real_summary:
                lines.append(f"【第{num}章实际内容摘要】")
                lines.append(chapter.real_summary)
                lines.append("")

        return "\n".join(lines)

    def _find_first_appear_chapter(self, name: str) -> Optional[int]:
        """查找地点/阵营首次出现的章节号，支持多种名称变体匹配"""
        if not hasattr(self, '_chapter_contents_map'):
            return None

        candidates = [name]

        for left_paren in ('（', '('):
            if left_paren in name:
                short = name.split(left_paren)[0].strip()
                if short and short not in candidates:
                    candidates.append(short)
                right_paren = '）' if left_paren == '（' else ')'
                inner = name.split(left_paren)[1].split(right_paren)[0].strip()
                if inner and inner not in candidates:
                    candidates.append(inner)

        if '·' in name:
            for part in name.split('·'):
                part = part.strip()
                if part and part not in candidates:
                    candidates.append(part)

        for chapter_num, content in sorted(self._chapter_contents_map.items()):
            if any(candidate in content for candidate in candidates):
                return chapter_num

        return None

    def _extract_names(self, items: List[Any]) -> List[str]:
        """从地点/阵营列表中提取名称"""
        names = []
        for item in items:
            if isinstance(item, dict):
                name = item.get("name") or item.get("title")
                if name:
                    names.append(name.strip())
            elif isinstance(item, str):
                name = item.split("：")[0].split(":")[0].strip()
                if name:
                    names.append(name)
        return names

    async def _extract_new_items(
        self,
        existing_locations: List[str],
        existing_factions: List[str],
        chapter_contents: str
    ) -> Dict[str, List[Dict[str, Any]]]:
        """调用 LLM 提取新地点和阵营"""
        prompt_template = await self.prompt_service.get_prompt("sync_world_setting")
        if not prompt_template:
            logger.warning("sync_world_setting prompt not found, using default")
            prompt_template = self._get_default_prompt()

        prompt = prompt_template.replace("{{existing_locations}}", json.dumps(existing_locations, ensure_ascii=False))
        prompt = prompt.replace("{{existing_factions}}", json.dumps(existing_factions, ensure_ascii=False))
        prompt = prompt.replace("{{chapter_contents}}", chapter_contents[:8000])

        try:
            content = await self.llm_service.generate(
                prompt=prompt,
                temperature=0.3,
                max_tokens=2000,
                response_format="json_object"
            )
            return self._parse_llm_response(content, existing_locations, existing_factions)
        except Exception as e:
            logger.error(f"Failed to extract new items from LLM: {e}")
            return {"new_locations": [], "new_factions": []}

    def _parse_llm_response(
        self,
        content: str,
        existing_locations: List[str],
        existing_factions: List[str]
    ) -> Dict[str, List[Dict[str, Any]]]:
        """解析 LLM 响应，兼容多种字段名变体"""
        result: Dict[str, List[Dict[str, Any]]] = {
            "new_locations": [],
            "new_factions": []
        }

        try:
            json_str = content.strip()
            if json_str.startswith("```"):
                lines = json_str.split("\n")
                json_str = "\n".join(lines[1:-1] if lines[-1] == "```" else lines[1:])

            data = json.loads(json_str)

            # 兼容多种字段名：new_locations / locations / location
            raw_locations = (
                data.get("new_locations")
                or data.get("locations")
                or data.get("location")
                or []
            )

            for loc in raw_locations:
                if not isinstance(loc, dict):
                    continue
                name = loc.get("name", "").strip()
                desc = loc.get("description", "").strip()
                if name and desc and len(desc) >= 10 and name not in existing_locations:
                    first_chapter = self._find_first_appear_chapter(name)
                    result["new_locations"].append({
                        "name": name,
                        "description": desc,
                        "first_appear_chapter": first_chapter
                    })
                    existing_locations.append(name)
                    logger.debug(f"[Sync] Added new location: {name} (chapter {first_chapter})")

            # 兼容多种字段名：new_factions / factions / faction
            raw_factions = (
                data.get("new_factions")
                or data.get("factions")
                or data.get("faction")
                or []
            )

            for fac in raw_factions:
                if not isinstance(fac, dict):
                    continue
                name = fac.get("name", "").strip()
                desc = fac.get("description", "").strip()
                if name and desc and len(desc) >= 10 and name not in existing_factions:
                    first_chapter = self._find_first_appear_chapter(name)
                    result["new_factions"].append({
                        "name": name,
                        "description": desc,
                        "first_appear_chapter": first_chapter
                    })
                    existing_factions.append(name)
                    logger.debug(f"[Sync] Added new faction: {name} (chapter {first_chapter})")

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse LLM response as JSON: {e}")
            logger.debug(f"Response content: {content[:500]}")
        except Exception as e:
            logger.error(f"Error parsing LLM response: {e}")

        return result

    def _get_default_prompt(self) -> str:
        """获取默认提示词"""
        return """# Role
你是一个专业的文学分析师，擅长从小说文本中提取地点和势力信息。

# Goal
分析提供的章节大纲和摘要文本，从中提取新出现的关键地点和主要阵营/势力。

# Input
- 现有地点列表: {{existing_locations}}
- 现有阵营列表: {{existing_factions}}
- 章节内容:
{{chapter_contents}}

# Output Format
请严格按照以下 JSON 格式输出，不要包含 Markdown 代码块标记：
{
  "new_locations": [
    {"name": "地点名称", "description": "地点描述（不少于10字）"}
  ],
  "new_factions": [
    {"name": "阵营名称", "description": "阵营描述（不少于10字）"}
  ]
}

# Rules
1. 只提取现有列表中不存在的地点/阵营（进行名称匹配，不要重复添加）
2. 描述必须包含有意义的信息，不少于10字
3. 如果没有新地点或新阵营，对应数组返回空数组 []
4. 关键地点：故事发生的重要场所、地理区域、建筑、山脉、山谷、洞穴、岛屿等
5. 主要阵营：有组织的势力、门派、国家、家族、帮派、组织、联盟等
6. 即使地点/阵营在文本中只出现一次，只要是重要的，也要提取
7. 描述应该简洁明了，说明该地点/阵营是什么、有什么特点、在故事中的作用
"""
