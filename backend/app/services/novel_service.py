# AIMETA P=小说服务_小说管理业务逻辑|R=小说CRUD_章节管理|NR=不含内容生成|E=NovelService|X=internal|A=服务类|D=sqlalchemy|S=db|RD=./README.ai
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional

_PREFERRED_CONTENT_KEYS: tuple[str, ...] = (
    "content",
    "chapter_content",
    "chapter_text",
    "full_content",
    "text",
    "body",
    "story",
    "chapter",
    "real_summary",
    "summary",
)


def _normalize_version_content(raw_content: Any, metadata: Any) -> str:
    # 优先使用原始内容
    text = _coerce_text(raw_content)
    if text:
        return text
    
    # 如果没有原始内容，尝试从元数据提取（兼容旧逻辑）
    text = _coerce_text(metadata)
    return text or ""


def _coerce_text(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, str):
        return _clean_string(value)
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, dict):
        for key in _PREFERRED_CONTENT_KEYS:
            if key in value and value[key]:
                nested = _coerce_text(value[key])
                if nested:
                    return nested
        return _clean_string(json.dumps(value, ensure_ascii=False), parse_json=False)
    if isinstance(value, (list, tuple, set)):
        parts = [text for text in (_coerce_text(item) for item in value) if text]
        if parts:
            return "\n".join(parts)
        return None
    return _clean_string(str(value))


def _clean_string(text: str, parse_json: bool = True) -> str:
    stripped = text.strip()
    if not stripped:
        return stripped
    if parse_json and (
        (stripped.startswith("{") and stripped.endswith("}"))
        or (stripped.startswith("[") and stripped.endswith("]"))
    ):
        try:
            parsed = json.loads(stripped)
            coerced = _coerce_text(parsed)
            if coerced:
                return coerced
        except json.JSONDecodeError:
            pass
    if stripped.startswith('"') and stripped.endswith('"') and len(stripped) >= 2:
        stripped = stripped[1:-1]
    return (
        stripped.replace("\\n", "\n")
        .replace("\\t", "\t")
        .replace('\\"', '"')
        .replace("\\\\", "\\")
    )

from fastapi import HTTPException, status
from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import (
    BlueprintCharacter,
    BlueprintRelationship,
    Chapter,
    ChapterEvaluation,
    ChapterOutline,
    ChapterVersion,
    NovelBlueprint,
    NovelConversation,
    NovelProject,
)
from ..models.key_location import KeyLocation
from ..models.faction import Faction
from ..models.foreshadowing import (
    ForeshadowingAnalysis,
    Foreshadowing,
    ForeshadowingReminder,
    ForeshadowingResolution,
    ForeshadowingStatusHistory,
)
from ..models.chapter_blueprint import ChapterBlueprint
from ..repositories.novel_repository import NovelRepository
from ..schemas.admin import AdminNovelSummary
from ..schemas.novel import (
    Blueprint,
    Chapter as ChapterSchema,
    ChapterGenerationStatus,
    ChapterRuntimeStatus,
    ChapterOutline as ChapterOutlineSchema,
    NovelProject as NovelProjectSchema,
    NovelProjectSummary,
    NovelSectionResponse,
    NovelSectionType,
)


class NovelService:
    """小说项目服务，基于拆表后的结构提供聚合与业务操作。"""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.repo = NovelRepository(session)

    @staticmethod
    def _split_world_setting_entities(
        world_setting: Optional[Dict[str, Any]]
    ) -> tuple[Dict[str, Any], List[Dict[str, Any]], List[Dict[str, Any]]]:
        """拆分 world_setting 中的结构化实体，保留基础设定字段。"""
        ws = dict(world_setting or {})
        key_locations = ws.pop("key_locations", None)
        locations = ws.pop("locations", None)
        ws.pop("location", None)
        factions = ws.pop("factions", None)

        location_items_raw = key_locations if isinstance(key_locations, list) and key_locations else locations
        location_items: List[Dict[str, Any]] = []
        if isinstance(location_items_raw, list):
            for item in location_items_raw:
                if not isinstance(item, dict):
                    continue
                name = str(item.get("name") or "").strip()
                if not name:
                    continue
                location_items.append(
                    {
                        "name": name,
                        "description": item.get("description") or "",
                        "location_type": item.get("location_type") or item.get("type"),
                        "first_appear_chapter": item.get("first_appear_chapter"),
                    }
                )

        faction_items: List[Dict[str, Any]] = []
        if isinstance(factions, list):
            for item in factions:
                if not isinstance(item, dict):
                    continue
                name = str(item.get("name") or "").strip()
                if not name:
                    continue
                faction_items.append(
                    {
                        "name": name,
                        "description": item.get("description") or "",
                        "first_appear_chapter": item.get("first_appear_chapter"),
                    }
                )

        return ws, location_items, faction_items

    async def _upsert_key_locations(self, project_id: str, items: List[Dict[str, Any]]) -> None:
        for item in items:
            name = str(item.get("name") or "").strip()
            if not name:
                continue
            existing_result = await self.session.execute(
                select(KeyLocation).where(
                    KeyLocation.project_id == project_id,
                    KeyLocation.name == name,
                )
            )
            existing = existing_result.scalar_one_or_none()
            if existing:
                if item.get("description") and not existing.description:
                    existing.description = item["description"]
                if item.get("location_type") and not existing.location_type:
                    existing.location_type = item["location_type"]
                if item.get("first_appear_chapter") is not None and existing.first_appear_chapter is None:
                    existing.first_appear_chapter = item["first_appear_chapter"]
            else:
                self.session.add(
                    KeyLocation(
                        project_id=project_id,
                        name=name,
                        description=item.get("description") or "",
                        location_type=item.get("location_type"),
                        first_appear_chapter=item.get("first_appear_chapter"),
                    )
                )

    async def _upsert_factions(self, project_id: str, items: List[Dict[str, Any]]) -> None:
        for item in items:
            name = str(item.get("name") or "").strip()
            if not name:
                continue
            existing_result = await self.session.execute(
                select(Faction).where(
                    Faction.project_id == project_id,
                    Faction.name == name,
                )
            )
            existing = existing_result.scalar_one_or_none()
            if existing:
                if item.get("description") and not existing.description:
                    existing.description = item["description"]
                if item.get("first_appear_chapter") is not None and existing.first_appear_chapter is None:
                    existing.first_appear_chapter = item["first_appear_chapter"]
            else:
                self.session.add(
                    Faction(
                        project_id=project_id,
                        name=name,
                        description=item.get("description") or "",
                        first_appear_chapter=item.get("first_appear_chapter"),
                    )
                )

    # ------------------------------------------------------------------
    # 项目与摘要
    # ------------------------------------------------------------------
    async def create_project(self, user_id: int, title: str, initial_prompt: str) -> NovelProject:
        project = NovelProject(
            id=str(uuid.uuid4()),
            user_id=user_id,
            title=title,
            initial_prompt=initial_prompt,
        )
        blueprint = NovelBlueprint(project=project)
        self.session.add_all([project, blueprint])
        await self.session.commit()
        await self.session.refresh(project)
        return project

    async def ensure_project_owner(self, project_id: str, user_id: int) -> NovelProject:
        project = await self.repo.get_by_id(project_id)
        if not project:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="项目不存在")
        if project.user_id != user_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权访问该项目")
        return project

    async def ensure_project_owner_light(self, project_id: str, user_id: int) -> None:
        owner_result = await self.session.execute(
            select(NovelProject.user_id).where(NovelProject.id == project_id)
        )
        owner_id = owner_result.scalar_one_or_none()
        if owner_id is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="项目不存在")
        if owner_id != user_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权访问该项目")

    async def get_project_schema(self, project_id: str, user_id: int) -> NovelProjectSchema:
        project = await self.ensure_project_owner(project_id, user_id)
        return await self._serialize_project(project)

    async def get_section_data(
        self,
        project_id: str,
        user_id: int,
        section: NovelSectionType,
    ) -> NovelSectionResponse:
        project = await self.ensure_project_owner(project_id, user_id)
        return await self._build_section_response(project, section)

    async def get_chapter_schema(
        self,
        project_id: str,
        user_id: int,
        chapter_number: int,
    ) -> ChapterSchema:
        project = await self.ensure_project_owner(project_id, user_id)
        return self._build_chapter_schema(project, chapter_number)

    async def get_chapter_runtime_status(
        self,
        project_id: str,
        user_id: int,
        chapter_number: int,
    ) -> ChapterRuntimeStatus:
        await self.ensure_project_owner_light(project_id, user_id)

        status_result = await self.session.execute(
            select(
                Chapter.chapter_number,
                Chapter.status,
                Chapter.word_count,
                Chapter.updated_at,
                Chapter.selected_version_id,
                func.count(ChapterVersion.id).label("versions_count"),
                func.count(ChapterEvaluation.id).label("evaluations_count"),
            )
            .outerjoin(ChapterVersion, ChapterVersion.chapter_id == Chapter.id)
            .outerjoin(ChapterEvaluation, ChapterEvaluation.chapter_id == Chapter.id)
            .where(
                Chapter.project_id == project_id,
                Chapter.chapter_number == chapter_number,
            )
            .group_by(
                Chapter.id,
                Chapter.chapter_number,
                Chapter.status,
                Chapter.word_count,
                Chapter.updated_at,
                Chapter.selected_version_id,
            )
        )
        row = status_result.mappings().first()
        if not row:
            return ChapterRuntimeStatus(
                chapter_number=chapter_number,
                generation_status=ChapterGenerationStatus.NOT_GENERATED,
            )

        generation_status = row.get("status") or ChapterGenerationStatus.NOT_GENERATED.value
        try:
            enum_status = ChapterGenerationStatus(generation_status)
        except ValueError:
            enum_status = ChapterGenerationStatus.NOT_GENERATED

        versions_count = int(row.get("versions_count") or 0)
        evaluations_count = int(row.get("evaluations_count") or 0)
        word_count = int(row.get("word_count") or 0)
        selected_version_id = row.get("selected_version_id")
        updated_at = row.get("updated_at")

        return ChapterRuntimeStatus(
            chapter_number=int(row.get("chapter_number") or chapter_number),
            generation_status=enum_status,
            word_count=word_count,
            updated_at=updated_at.isoformat() if updated_at else None,
            has_content=word_count > 0 or bool(selected_version_id),
            versions_count=versions_count,
            has_evaluation=evaluations_count > 0,
            selected_version_id=int(selected_version_id) if selected_version_id else None,
        )

    async def list_projects_for_user(self, user_id: int) -> List[NovelProjectSummary]:
        projects = await self.repo.list_by_user(user_id)
        summaries: List[NovelProjectSummary] = []
        for project in projects:
            blueprint = project.blueprint
            genre = blueprint.genre if blueprint and blueprint.genre else "未知"
            outlines = project.outlines
            chapters = project.chapters
            total = len(outlines) or len(chapters)
            completed = sum(1 for chapter in chapters if chapter.selected_version_id)
            summaries.append(
                NovelProjectSummary(
                    id=project.id,
                    title=project.title,
                    genre=genre,
                    last_edited=project.updated_at.isoformat() if project.updated_at else "未知",
                    completed_chapters=completed,
                    total_chapters=total,
                )
            )
        return summaries

    async def list_projects_for_admin(self) -> List[AdminNovelSummary]:
        projects = await self.repo.list_all()
        summaries: List[AdminNovelSummary] = []
        for project in projects:
            blueprint = project.blueprint
            genre = blueprint.genre if blueprint and blueprint.genre else "未知"
            outlines = project.outlines
            chapters = project.chapters
            total = len(outlines) or len(chapters)
            completed = sum(1 for chapter in chapters if chapter.selected_version_id)
            owner = project.owner
            summaries.append(
                AdminNovelSummary(
                    id=project.id,
                    title=project.title,
                    owner_id=owner.id if owner else 0,
                    owner_username=owner.username if owner else "未知",
                    genre=genre,
                    last_edited=project.updated_at.isoformat() if project.updated_at else "",
                    completed_chapters=completed,
                    total_chapters=total,
                )
            )
        return summaries

    async def delete_projects(self, project_ids: List[str], user_id: int) -> None:
        for pid in project_ids:
            project = await self.ensure_project_owner(pid, user_id)
            await self.repo.delete(project)
        await self.session.commit()

    async def count_projects(self) -> int:
        result = await self.session.execute(select(func.count(NovelProject.id)))
        return result.scalar_one()

    # ------------------------------------------------------------------
    # 对话管理
    # ------------------------------------------------------------------
    @staticmethod
    def _get_conversation_phase(conversation: NovelConversation) -> Optional[str]:
        metadata = conversation.metadata if isinstance(conversation.metadata, dict) else {}
        phase = metadata.get("phase")
        return str(phase) if phase else None

    @classmethod
    def _matches_conversation_phase(
        cls,
        conversation: NovelConversation,
        phase: str,
        *,
        include_legacy: bool = False,
    ) -> bool:
        conversation_phase = cls._get_conversation_phase(conversation)
        if conversation_phase == phase:
            return True
        return include_legacy and phase == "concept" and not conversation_phase

    async def list_conversations(
        self,
        project_id: str,
        *,
        phase: Optional[str] = None,
        include_legacy: bool = False,
    ) -> List[NovelConversation]:
        stmt = (
            select(NovelConversation)
            .where(NovelConversation.project_id == project_id)
            .order_by(NovelConversation.seq.asc())
        )
        result = await self.session.execute(stmt)
        conversations = list(result.scalars())
        if not phase:
            return conversations
        return [
            conversation
            for conversation in conversations
            if self._matches_conversation_phase(
                conversation,
                phase,
                include_legacy=include_legacy,
            )
        ]

    async def append_conversation(self, project_id: str, role: str, content: str, metadata: Optional[Dict] = None) -> None:
        result = await self.session.execute(
            select(func.max(NovelConversation.seq)).where(NovelConversation.project_id == project_id)
        )
        current_max = result.scalar()
        next_seq = (current_max or 0) + 1
        convo = NovelConversation(
            project_id=project_id,
            seq=next_seq,
            role=role,
            content=content,
            metadata=metadata,
        )
        self.session.add(convo)
        await self.session.commit()
        await self._touch_project(project_id)

    async def merge_conversation_metadata(self, project_id: str, conversation_id: int, metadata_patch: Dict[str, Any]) -> None:
        conversation = await self.session.get(NovelConversation, conversation_id)
        if not conversation or conversation.project_id != project_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="对话记录不存在")

        existing_metadata = conversation.metadata if isinstance(conversation.metadata, dict) else {}
        conversation.metadata = {**existing_metadata, **metadata_patch}
        await self.session.commit()
        await self._touch_project(project_id)

    # ------------------------------------------------------------------
    # 蓝图管理
    # ------------------------------------------------------------------
    async def replace_blueprint(self, project_id: str, blueprint: Blueprint) -> None:
        record = await self.session.get(NovelBlueprint, project_id)
        if not record:
            record = NovelBlueprint(project_id=project_id)
            self.session.add(record)
        record.title = blueprint.title
        record.target_audience = blueprint.target_audience
        record.genre = blueprint.genre
        record.style = blueprint.style
        record.tone = blueprint.tone
        record.one_sentence_summary = blueprint.one_sentence_summary
        record.full_synopsis = blueprint.full_synopsis
        record.total_chapters = blueprint.total_chapters or 0
        sanitized_world_setting, location_items, faction_items = self._split_world_setting_entities(
            blueprint.world_setting
        )
        record.world_setting = sanitized_world_setting

        await self.session.execute(delete(BlueprintCharacter).where(BlueprintCharacter.project_id == project_id))
        for index, data in enumerate(blueprint.characters):
            self.session.add(
                BlueprintCharacter(
                    project_id=project_id,
                    name=data.get("name", ""),
                    identity=data.get("identity"),
                    personality=data.get("personality"),
                    goals=data.get("goals"),
                    abilities=data.get("abilities"),
                    relationship_to_protagonist=data.get("relationship_to_protagonist"),
                    is_protagonist=bool(data.get("is_protagonist", False)),
                    extra={k: v for k, v in data.items() if k not in {
                        "name",
                        "identity",
                        "personality",
                        "goals",
                        "abilities",
                        "relationship_to_protagonist",
                        "is_protagonist",
                    }},
                    position=index,
                )
            )

        await self.session.execute(delete(BlueprintRelationship).where(BlueprintRelationship.project_id == project_id))
        for index, relation in enumerate(blueprint.relationships):
            self.session.add(
                BlueprintRelationship(
                    project_id=project_id,
                    character_from=relation.character_from,
                    character_to=relation.character_to,
                    description=relation.description,
                    position=index,
                )
            )

        await self.session.execute(delete(ChapterOutline).where(ChapterOutline.project_id == project_id))
        for outline in blueprint.chapter_outline:
            self.session.add(
                ChapterOutline(
                    project_id=project_id,
                    chapter_number=outline.chapter_number,
                    title=outline.title,
                    summary=outline.summary,
                )
            )

        await self._upsert_key_locations(project_id, location_items)
        await self._upsert_factions(project_id, faction_items)
        await self.session.commit()
        await self._touch_project(project_id)

    async def patch_blueprint(self, project_id: str, patch: Dict) -> None:
        blueprint = await self.session.get(NovelBlueprint, project_id)
        if not blueprint:
            blueprint = NovelBlueprint(project_id=project_id)
            self.session.add(blueprint)

        if "title" in patch:
            blueprint.title = patch["title"]
            await self.session.execute(
                update(NovelProject)
                .where(NovelProject.id == project_id)
                .values(title=patch["title"] or "未命名灵感")
            )
        if "target_audience" in patch:
            blueprint.target_audience = patch["target_audience"]
        if "genre" in patch:
            blueprint.genre = patch["genre"]
        if "style" in patch:
            blueprint.style = patch["style"]
        if "tone" in patch:
            blueprint.tone = patch["tone"]
        if "one_sentence_summary" in patch:
            blueprint.one_sentence_summary = patch["one_sentence_summary"]
        if "full_synopsis" in patch:
            blueprint.full_synopsis = patch["full_synopsis"]
        if "total_chapters" in patch:
            blueprint.total_chapters = patch["total_chapters"] or 0
        if "world_setting" in patch and patch["world_setting"] is not None:
            patch_world_setting, location_items, faction_items = self._split_world_setting_entities(
                patch["world_setting"]
            )
            # 创建新字典对象以触发 SQLAlchemy 的变更检测
            existing = blueprint.world_setting or {}
            blueprint.world_setting = {**existing, **patch_world_setting}
            await self._upsert_key_locations(project_id, location_items)
            await self._upsert_factions(project_id, faction_items)
        if "characters" in patch and patch["characters"] is not None:
            await self.session.execute(delete(BlueprintCharacter).where(BlueprintCharacter.project_id == project_id))
            for index, data in enumerate(patch["characters"]):
                self.session.add(
                    BlueprintCharacter(
                        project_id=project_id,
                        name=data.get("name", ""),
                        identity=data.get("identity"),
                        personality=data.get("personality"),
                        goals=data.get("goals"),
                        abilities=data.get("abilities"),
                        relationship_to_protagonist=data.get("relationship_to_protagonist"),
                        is_protagonist=bool(data.get("is_protagonist", False)),
                        extra={k: v for k, v in data.items() if k not in {
                            "name",
                            "identity",
                            "personality",
                            "goals",
                            "abilities",
                            "relationship_to_protagonist",
                            "is_protagonist",
                        }},
                        position=index,
                    )
                )
        if "relationships" in patch and patch["relationships"] is not None:
            await self.session.execute(delete(BlueprintRelationship).where(BlueprintRelationship.project_id == project_id))
            for index, relation in enumerate(patch["relationships"]):
                self.session.add(
                    BlueprintRelationship(
                        project_id=project_id,
                        character_from=relation.get("character_from"),
                        character_to=relation.get("character_to"),
                        description=relation.get("description"),
                        position=index,
                    )
                )
        if "chapter_outline" in patch and patch["chapter_outline"] is not None:
            await self.session.execute(delete(ChapterOutline).where(ChapterOutline.project_id == project_id))
            for outline in patch["chapter_outline"]:
                self.session.add(
                    ChapterOutline(
                        project_id=project_id,
                        chapter_number=outline.get("chapter_number"),
                        title=outline.get("title", ""),
                        summary=outline.get("summary"),
                    )
                )
        await self.session.commit()
        await self._touch_project(project_id)

    # ------------------------------------------------------------------
    # 章节与版本
    # ------------------------------------------------------------------
    async def get_outline(self, project_id: str, chapter_number: int) -> Optional[ChapterOutline]:
        stmt = (
            select(ChapterOutline)
            .where(
                ChapterOutline.project_id == project_id,
                ChapterOutline.chapter_number == chapter_number,
            )
        )
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def update_or_create_outline(
        self,
        project_id: str,
        chapter_number: int,
        title: str,
        summary: str,
        metadata: Optional[dict] = None,
    ) -> ChapterOutline:
        """更新或创建章节大纲，支持 metadata 存储导演脚本等信息。"""
        stmt = select(ChapterOutline).where(
            ChapterOutline.project_id == project_id,
            ChapterOutline.chapter_number == chapter_number,
        )
        result = await self.session.execute(stmt)
        outline = result.scalars().first()
        if outline:
            outline.title = title
            outline.summary = summary
            if metadata is not None:
                outline.metadata = metadata
        else:
            outline = ChapterOutline(
                project_id=project_id,
                chapter_number=chapter_number,
                title=title,
                summary=summary,
                metadata=metadata,
            )
            self.session.add(outline)
        await self.session.flush()
        return outline

    async def get_or_create_chapter(self, project_id: str, chapter_number: int, auto_commit: bool = True) -> Chapter:
        stmt = (
            select(Chapter)
            .options(selectinload(Chapter.selected_version))
            .where(
                Chapter.project_id == project_id,
                Chapter.chapter_number == chapter_number,
            )
        )
        result = await self.session.execute(stmt)
        chapter = result.scalars().first()
        if chapter:
            return chapter
        chapter = Chapter(project_id=project_id, chapter_number=chapter_number)
        self.session.add(chapter)
        if auto_commit:
            await self.session.commit()
            await self.session.refresh(chapter)
        else:
            await self.session.flush()
            await self.session.refresh(chapter)
        return chapter

    async def replace_chapter_versions(self, chapter: Chapter, contents: List[str], metadata: Optional[List[Dict]] = None) -> List[ChapterVersion]:
        await self.session.execute(delete(ChapterVersion).where(ChapterVersion.chapter_id == chapter.id))
        versions: List[ChapterVersion] = []
        for index, content in enumerate(contents):
            extra = metadata[index] if metadata and index < len(metadata) else None
            text_content = _normalize_version_content(content, extra)
            version = ChapterVersion(
                chapter_id=chapter.id,
                content=text_content,
                metadata=extra,  # ✅ 落盘 metadata
                version_label=f"v{index+1}",
            )
            self.session.add(version)
            versions.append(version)
        chapter.status = ChapterGenerationStatus.WAITING_FOR_CONFIRM.value
        await self.session.commit()
        await self.session.refresh(chapter)
        await self._touch_project(chapter.project_id)
        return versions

    async def select_chapter_version(self, chapter: Chapter, version_index: int) -> ChapterVersion:
        stmt = select(ChapterVersion).where(ChapterVersion.chapter_id == chapter.id).order_by(ChapterVersion.created_at)
        result = await self.session.execute(stmt)
        versions = result.scalars().all()
        
        if not versions or version_index < 0 or version_index >= len(versions):
            raise HTTPException(status_code=400, detail="版本索引无效")
        selected = versions[version_index]
        
        # 校验内容是否为空
        if not selected.content or len(selected.content.strip()) == 0:
            raise HTTPException(status_code=400, detail="选中的版本内容为空，无法确认为最终版")
        
        chapter.selected_version_id = selected.id
        chapter.status = ChapterGenerationStatus.SUCCESSFUL.value
        chapter.word_count = len(selected.content or "")
        await self.session.commit()
        await self.session.refresh(chapter)
        await self._touch_project(chapter.project_id)
        return selected

    async def add_chapter_evaluation(
        self,
        chapter: Chapter,
        version: Optional[ChapterVersion],
        feedback: str,
        decision: Optional[str] = None,
        score: Optional[float] = None,
    ) -> None:
        evaluation = ChapterEvaluation(
            chapter_id=chapter.id,
            version_id=version.id if version else None,
            feedback=feedback,
            decision=decision,
            score=score,
        )
        self.session.add(evaluation)
        chapter.status = ChapterGenerationStatus.WAITING_FOR_CONFIRM.value
        await self.session.commit()
        await self.session.refresh(chapter)
        await self._touch_project(chapter.project_id)

    async def delete_chapters(self, project_id: str, chapter_numbers: Iterable[int]) -> None:
        chapter_numbers_set = {int(n) for n in chapter_numbers}
        if not chapter_numbers_set:
            return
        chapter_numbers_list = sorted(chapter_numbers_set)

        # 先删除与章节号强关联的数据
        await self._cleanup_foreshadowing_for_deleted_chapters(project_id, chapter_numbers_list)
        await self.session.execute(
            delete(ChapterBlueprint).where(
                ChapterBlueprint.project_id == project_id,
                ChapterBlueprint.chapter_number.in_(chapter_numbers_list),
            )
        )
        await self.session.execute(
            delete(Chapter).where(
                Chapter.project_id == project_id,
                Chapter.chapter_number.in_(chapter_numbers_list),
            )
        )
        await self.session.execute(
            delete(ChapterOutline).where(
                ChapterOutline.project_id == project_id,
                ChapterOutline.chapter_number.in_(chapter_numbers_list),
            )
        )
        await self._cleanup_blueprint_entities_for_deleted_chapters(project_id, chapter_numbers_set)
        await self.session.commit()
        await self._touch_project(project_id)

    async def _cleanup_foreshadowing_for_deleted_chapters(
        self,
        project_id: str,
        chapter_numbers: List[int],
    ) -> None:
        # 删除“在被删章节回收”的回收记录
        project_foreshadowing_ids = select(Foreshadowing.id).where(Foreshadowing.project_id == project_id)
        await self.session.execute(
            delete(ForeshadowingResolution).where(
                ForeshadowingResolution.foreshadowing_id.in_(project_foreshadowing_ids),
                ForeshadowingResolution.resolved_at_chapter_number.in_(chapter_numbers)
            )
        )
        await self.session.execute(
            delete(ForeshadowingStatusHistory).where(
                ForeshadowingStatusHistory.foreshadowing_id.in_(project_foreshadowing_ids),
                ForeshadowingStatusHistory.chapter_number.in_(chapter_numbers),
            )
        )

        # 删除“埋设在被删章节”的伏笔（其提醒会因外键级联删除）
        fs_ids_result = await self.session.execute(
            select(Foreshadowing.id).where(
                Foreshadowing.project_id == project_id,
                Foreshadowing.chapter_number.in_(chapter_numbers),
            )
        )
        fs_ids = [row[0] for row in fs_ids_result.all()]
        if fs_ids:
            await self.session.execute(
                delete(ForeshadowingReminder).where(ForeshadowingReminder.foreshadowing_id.in_(fs_ids))
            )
            await self.session.execute(
                delete(ForeshadowingResolution).where(ForeshadowingResolution.foreshadowing_id.in_(fs_ids))
            )
            await self.session.execute(
                delete(ForeshadowingStatusHistory).where(ForeshadowingStatusHistory.foreshadowing_id.in_(fs_ids))
            )
            await self.session.execute(delete(Foreshadowing).where(Foreshadowing.id.in_(fs_ids)))

        # 对“回收章被删除”的伏笔，回退为未回收状态并清空计划回收章
        resolved_result = await self.session.execute(
            select(Foreshadowing).where(
                Foreshadowing.project_id == project_id,
                or_(
                    Foreshadowing.resolved_chapter_number.in_(chapter_numbers),
                    Foreshadowing.target_reveal_chapter.in_(chapter_numbers),
                ),
            )
        )
        for fs in resolved_result.scalars().all():
            if fs.resolved_chapter_number in chapter_numbers:
                fs.resolved_chapter_number = None
                fs.resolved_chapter_id = None
                if (fs.status or "").lower() in {"resolved", "revealed", "partial"}:
                    fs.status = "planted"
            if fs.target_reveal_chapter in chapter_numbers:
                fs.target_reveal_chapter = None

        # 删除分析缓存，避免统计显示陈旧数据
        await self.session.execute(
            delete(ForeshadowingAnalysis).where(ForeshadowingAnalysis.project_id == project_id)
        )

    async def _cleanup_blueprint_entities_for_deleted_chapters(
        self,
        project_id: str,
        deleted_chapters: set[int],
    ) -> None:
        remaining_text = await self._build_remaining_chapter_text(project_id, deleted_chapters)

        # 角色：仅删除首次出现在被删章节且在剩余章节未被引用的角色
        chars_result = await self.session.execute(
            select(BlueprintCharacter).where(BlueprintCharacter.project_id == project_id)
        )
        stale_char_names: set[str] = set()
        for char in chars_result.scalars().all():
            first_appear = self._parse_first_appear_from_extra(char.extra)
            if first_appear not in deleted_chapters:
                continue
            if char.is_protagonist:
                continue
            if self._is_name_referenced(char.name, remaining_text):
                continue
            stale_char_names.add(char.name)
            await self.session.delete(char)

        if stale_char_names:
            await self.session.execute(
                delete(BlueprintRelationship).where(
                    BlueprintRelationship.project_id == project_id,
                    or_(
                        BlueprintRelationship.character_from.in_(list(stale_char_names)),
                        BlueprintRelationship.character_to.in_(list(stale_char_names)),
                    ),
                )
            )

        # 地点：首次出现在被删章节且在剩余章节未被引用则删除
        loc_result = await self.session.execute(
            select(KeyLocation).where(KeyLocation.project_id == project_id)
        )
        for loc in loc_result.scalars().all():
            if loc.first_appear_chapter not in deleted_chapters:
                continue
            if self._is_name_referenced(loc.name, remaining_text):
                continue
            await self.session.delete(loc)

        # 势力：首次出现在被删章节且在剩余章节未被引用则删除
        fac_result = await self.session.execute(
            select(Faction).where(Faction.project_id == project_id)
        )
        for fac in fac_result.scalars().all():
            if fac.first_appear_chapter not in deleted_chapters:
                continue
            if self._is_name_referenced(fac.name, remaining_text):
                continue
            await self.session.delete(fac)

    async def _build_remaining_chapter_text(self, project_id: str, deleted_chapters: set[int]) -> str:
        outlines_result = await self.session.execute(
            select(ChapterOutline).where(
                ChapterOutline.project_id == project_id,
                ~ChapterOutline.chapter_number.in_(list(deleted_chapters)),
            )
        )
        chapters_result = await self.session.execute(
            select(Chapter).where(
                Chapter.project_id == project_id,
                ~Chapter.chapter_number.in_(list(deleted_chapters)),
            )
        )

        parts: List[str] = []
        for outline in outlines_result.scalars().all():
            if outline.title:
                parts.append(str(outline.title))
            if outline.summary:
                parts.append(str(outline.summary))
        for chapter in chapters_result.scalars().all():
            if chapter.real_summary:
                parts.append(str(chapter.real_summary))
        return "\n".join(parts)

    @staticmethod
    def _parse_first_appear_from_extra(extra: Optional[Dict[str, Any]]) -> Optional[int]:
        if not isinstance(extra, dict):
            return None
        raw = extra.get("first_appear_chapter")
        try:
            return int(raw) if raw is not None else None
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _is_name_referenced(name: Optional[str], corpus: str) -> bool:
        if not name:
            return False
        token = str(name).strip()
        if not token:
            return False
        return token in corpus

    async def update_blueprint_characters(self, project_id: str, characters: List) -> None:
        """更新蓝图中的角色列表"""
        project = await self.repo.get_by_id(project_id)
        if not project:
            raise HTTPException(status_code=404, detail="项目不存在")

        # 删除现有角色
        await self.session.execute(delete(BlueprintCharacter).where(BlueprintCharacter.project_id == project_id))

        # 添加新角色 - 支持字典和Pydantic模型
        for index, char in enumerate(characters):
            # 兼容字典和Pydantic模型
            if hasattr(char, "model_dump"):
                data = char.model_dump()
            elif hasattr(char, "dict"):
                data = char.dict()
            elif isinstance(char, dict):
                data = char
            else:
                data = {}

            # 将 description 和 first_appear_chapter 等非标准字段存入 extra
            standard_fields = {
                "name",
                "identity",
                "personality",
                "goals",
                "abilities",
                "relationship_to_protagonist",
                "is_protagonist",
            }
            extra = {k: v for k, v in data.items() if k not in standard_fields}

            self.session.add(
                BlueprintCharacter(
                    project_id=project_id,
                    name=data.get("name", ""),
                    identity=data.get("identity"),
                    personality=data.get("personality"),
                    goals=data.get("goals"),
                    abilities=data.get("abilities"),
                    relationship_to_protagonist=data.get("relationship_to_protagonist"),
                    is_protagonist=bool(data.get("is_protagonist", False)),
                    extra=extra if extra else None,
                    position=index,
                )
            )

        await self.session.commit()
        await self._touch_project(project_id)

    async def update_blueprint_relationships(self, project_id: str, relationships: List) -> None:
        """更新蓝图中的关系列表"""
        project = await self.repo.get_by_id(project_id)
        if not project:
            raise HTTPException(status_code=404, detail="项目不存在")

        # 删除现有关系
        await self.session.execute(delete(BlueprintRelationship).where(BlueprintRelationship.project_id == project_id))

        # 添加新关系 - 支持字典和Pydantic模型
        for index, relation in enumerate(relationships):
            # 兼容字典和Pydantic模型
            if hasattr(relation, "model_dump"):
                rel_dict = relation.model_dump()
            elif hasattr(relation, "dict"):
                rel_dict = relation.dict()
            elif isinstance(relation, dict):
                rel_dict = relation
            else:
                rel_dict = {}

            self.session.add(
                BlueprintRelationship(
                    project_id=project_id,
                    character_from=rel_dict.get("character_from") or rel_dict.get("from", ""),
                    character_to=rel_dict.get("character_to") or rel_dict.get("to", ""),
                    description=rel_dict.get("description"),
                    position=index,
                )
            )

        await self.session.commit()
        await self._touch_project(project_id)

    async def update_blueprint_world_setting(self, project_id: str, world_setting: Dict[str, Any]) -> None:
        """更新蓝图中的世界设定"""
        blueprint = await self.session.get(NovelBlueprint, project_id)
        if not blueprint:
            # 如果蓝图不存在，创建一个新的
            blueprint = NovelBlueprint(project_id=project_id)
            self.session.add(blueprint)

        sanitized_world_setting, location_items, faction_items = self._split_world_setting_entities(world_setting)
        blueprint.world_setting = sanitized_world_setting
        await self._upsert_key_locations(project_id, location_items)
        await self._upsert_factions(project_id, faction_items)
        await self.session.commit()
        await self._touch_project(project_id)

    # ------------------------------------------------------------------
    # 序列化辅助
    # ------------------------------------------------------------------
    async def get_project_schema_for_admin(self, project_id: str) -> NovelProjectSchema:
        project = await self.repo.get_by_id(project_id)
        if not project:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="项目不存在")
        return await self._serialize_project(project)

    async def get_section_data_for_admin(
        self,
        project_id: str,
        section: NovelSectionType,
    ) -> NovelSectionResponse:
        project = await self.repo.get_by_id(project_id)
        if not project:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="项目不存在")
        return await self._build_section_response(project, section)

    async def get_chapter_schema_for_admin(
        self,
        project_id: str,
        chapter_number: int,
    ) -> ChapterSchema:
        project = await self.repo.get_by_id(project_id)
        if not project:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="项目不存在")
        return self._build_chapter_schema(project, chapter_number)

    async def _serialize_project(self, project: NovelProject) -> NovelProjectSchema:
        conversations = [
            {"role": convo.role, "content": convo.content}
            for convo in sorted(project.conversations, key=lambda c: c.seq)
            if self._matches_conversation_phase(convo, "concept", include_legacy=True)
        ]

        blueprint_schema = self._build_blueprint_schema(project)
        if blueprint_schema:
            _loc_result = await self.session.execute(
                select(KeyLocation)
                .where(KeyLocation.project_id == project.id)
                .order_by(
                    KeyLocation.first_appear_chapter.is_(None),
                    KeyLocation.first_appear_chapter.asc(),
                    KeyLocation.id.asc(),
                )
            )
            _fac_result = await self.session.execute(
                select(Faction).where(Faction.project_id == project.id)
            )
            ws = dict(blueprint_schema.world_setting or {})
            ws["key_locations"] = [
                {
                    "id": loc.id,
                    "name": loc.name,
                    "description": loc.description or "",
                    "type": loc.location_type,
                    "location_type": loc.location_type,
                    "first_appear_chapter": loc.first_appear_chapter,
                }
                for loc in _loc_result.scalars().all()
            ]
            ws["factions"] = [
                {
                    "id": fac.id,
                    "name": fac.name,
                    "description": fac.description or "",
                    "faction_type": fac.faction_type,
                    "first_appear_chapter": fac.first_appear_chapter,
                }
                for fac in _fac_result.scalars().all()
            ]
            blueprint_schema.world_setting = ws

        outlines_map = {outline.chapter_number: outline for outline in project.outlines}
        chapters_map = {chapter.chapter_number: chapter for chapter in project.chapters}
        chapter_numbers = sorted(set(outlines_map.keys()) | set(chapters_map.keys()))
        chapters_schema: List[ChapterSchema] = [
            self._build_chapter_schema(
                project,
                number,
                outlines_map=outlines_map,
                chapters_map=chapters_map,
            )
            for number in chapter_numbers
        ]

        return NovelProjectSchema(
            id=project.id,
            user_id=project.user_id,
            title=project.title,
            initial_prompt=project.initial_prompt or "",
            conversation_history=conversations,
            blueprint=blueprint_schema,
            chapters=chapters_schema,
        )

    async def _touch_project(self, project_id: str) -> None:
        await self.session.execute(
            update(NovelProject)
            .where(NovelProject.id == project_id)
            .values(updated_at=datetime.now(timezone.utc))
        )
        await self.session.commit()

    def _build_blueprint_schema(self, project: NovelProject) -> Blueprint:
        blueprint_obj = project.blueprint
        if blueprint_obj:
            return Blueprint(
                title=blueprint_obj.title or "",
                target_audience=blueprint_obj.target_audience or "",
                genre=blueprint_obj.genre or "",
                style=blueprint_obj.style or "",
                tone=blueprint_obj.tone or "",
                one_sentence_summary=blueprint_obj.one_sentence_summary or "",
                full_synopsis=blueprint_obj.full_synopsis or "",
                total_chapters=blueprint_obj.total_chapters or 0,
                world_setting=blueprint_obj.world_setting or {},
                characters=[
                    {
                        "name": character.name,
                        "identity": character.identity,
                        "personality": character.personality,
                        "goals": character.goals,
                        "abilities": character.abilities,
                        "relationship_to_protagonist": character.relationship_to_protagonist,
                        "is_protagonist": bool(character.is_protagonist),
                        **(character.extra or {}),
                    }
                    for character in sorted(project.characters, key=lambda c: c.position)
                ],
                relationships=[
                    {
                        "character_from": relation.character_from,
                        "character_to": relation.character_to,
                        "description": relation.description or "",
                        "relationship_type": getattr(relation, "relationship_type", None),
                    }
                    for relation in sorted(project.relationships_, key=lambda r: r.position)
                ],
                chapter_outline=[
                    ChapterOutlineSchema(
                        chapter_number=outline.chapter_number,
                        title=outline.title,
                        summary=outline.summary or "",
                    )
                    for outline in sorted(project.outlines, key=lambda o: o.chapter_number)
                ],
            )
        return Blueprint(
            title="",
            target_audience="",
            genre="",
            style="",
            tone="",
            one_sentence_summary="",
            full_synopsis="",
            total_chapters=0,
            world_setting={},
            characters=[],
            relationships=[],
            chapter_outline=[],
        )

    async def _build_section_response(
        self,
        project: NovelProject,
        section: NovelSectionType,
    ) -> NovelSectionResponse:
        blueprint = self._build_blueprint_schema(project)

        if section == NovelSectionType.OVERVIEW:
            data = {
                "title": project.title,
                "initial_prompt": project.initial_prompt or "",
                "status": project.status,
                "one_sentence_summary": blueprint.one_sentence_summary,
                "target_audience": blueprint.target_audience,
                "genre": blueprint.genre,
                "style": blueprint.style,
                "tone": blueprint.tone,
                "full_synopsis": blueprint.full_synopsis,
                "updated_at": project.updated_at.isoformat() if project.updated_at else None,
            }
        elif section == NovelSectionType.WORLD_SETTING:
            _loc_result = await self.session.execute(
                select(KeyLocation)
                .where(KeyLocation.project_id == project.id)
                .order_by(
                    KeyLocation.first_appear_chapter.is_(None),
                    KeyLocation.first_appear_chapter.asc(),
                    KeyLocation.id.asc(),
                )
            )
            _fac_result = await self.session.execute(
                select(Faction).where(Faction.project_id == project.id)
            )
            _ws = blueprint.world_setting if isinstance(blueprint.world_setting, dict) else {}
            data = {
                "world_setting": {
                    k: v for k, v in _ws.items()
                    if k not in ("key_locations", "factions", "locations", "location")
                },
                "key_locations": [
                    {
                        "id": loc.id,
                        "name": loc.name,
                        "description": loc.description or "",
                        "location_type": loc.location_type,
                        "first_appear_chapter": loc.first_appear_chapter,
                    }
                    for loc in _loc_result.scalars().all()
                ],
                "factions": [
                    {
                        "id": fac.id,
                        "name": fac.name,
                        "description": fac.description or "",
                        "faction_type": fac.faction_type,
                        "first_appear_chapter": fac.first_appear_chapter,
                    }
                    for fac in _fac_result.scalars().all()
                ],
            }
        elif section == NovelSectionType.CHARACTERS:
            data = {
                "characters": blueprint.characters,
            }
        elif section == NovelSectionType.RELATIONSHIPS:
            data = {
                "relationships": blueprint.relationships,
            }
        elif section == NovelSectionType.CHAPTER_OUTLINE:
            data = {
                "chapter_outline": [outline.model_dump() for outline in blueprint.chapter_outline],
            }
        elif section == NovelSectionType.CHAPTERS:
            outlines_map = {outline.chapter_number: outline for outline in project.outlines}
            chapters_map = {chapter.chapter_number: chapter for chapter in project.chapters}
            chapter_numbers = sorted(set(outlines_map.keys()) | set(chapters_map.keys()))
            # 章节列表只返回元数据，不包含完整内容
            chapters = [
                self._build_chapter_schema(
                    project,
                    number,
                    outlines_map=outlines_map,
                    chapters_map=chapters_map,
                    include_content=False,
                ).model_dump()
                for number in chapter_numbers
            ]
            data = {
                "chapters": chapters,
                "total": len(chapters),
            }
        else:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="未知的章节类型")

        return NovelSectionResponse(section=section, data=data)

    def _build_chapter_schema(
        self,
        project: NovelProject,
        chapter_number: int,
        *,
        outlines_map: Optional[Dict[int, ChapterOutline]] = None,
        chapters_map: Optional[Dict[int, Chapter]] = None,
        include_content: bool = True,
    ) -> ChapterSchema:
        outlines = outlines_map or {outline.chapter_number: outline for outline in project.outlines}
        chapters = chapters_map or {chapter.chapter_number: chapter for chapter in project.chapters}
        outline = outlines.get(chapter_number)
        chapter = chapters.get(chapter_number)

        if not outline and not chapter:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="章节不存在")

        title = outline.title if outline else f"第{chapter_number}章"
        summary = outline.summary if outline else ""
        real_summary = chapter.real_summary if chapter else None
        content = None
        versions: Optional[List[str]] = None
        evaluation_text: Optional[str] = None
        status_value = ChapterGenerationStatus.NOT_GENERATED.value
        word_count = 0

        if chapter:
            status_value = chapter.status or ChapterGenerationStatus.NOT_GENERATED.value
            word_count = chapter.word_count or 0

            # 只有在 include_content=True 时才包含完整内容
            if include_content:
                if chapter.selected_version:
                    content = chapter.selected_version.content
                if chapter.versions:
                    versions = [
                        v.content
                        for v in sorted(chapter.versions, key=lambda item: item.created_at)
                    ]
                if chapter.evaluations:
                    # 返回最新的评审结果（多版本对比评审的完整 JSON）
                    # 所有版本的评审结果相同，取最新的即可
                    latest_evaluation = max(chapter.evaluations, key=lambda item: item.created_at)
                    evaluation_text = latest_evaluation.feedback if latest_evaluation.feedback else None

        return ChapterSchema(
            chapter_number=chapter_number,
            title=title,
            summary=summary,
            real_summary=real_summary,
            content=content,
            versions=versions,
            evaluation=evaluation_text,
            generation_status=ChapterGenerationStatus(status_value),
            word_count=word_count,
        )
