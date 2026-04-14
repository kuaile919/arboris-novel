import json
import logging
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.dependencies import get_current_user
from ...db.session import get_session
from ...schemas.novel import (
    ApplyBlueprintSettingPatchRequest,
    BlueprintPatch,
    BlueprintSettingChatMessage,
    BlueprintSettingConverseRequest,
    BlueprintSettingConverseResponse,
    BlueprintSettingHistoryResponse,
    BlueprintSettingImpactAnalysis,
    NovelProject as NovelProjectSchema,
)
from ...schemas.user import UserInDB
from ...services.llm_service import LLMService
from ...services.novel_service import NovelService
from ...utils.json_utils import remove_think_tags, sanitize_json_like_text, unwrap_markdown_json

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/novels", tags=["Novels"])

CONCEPT_PHASE = "concept"
BLUEPRINT_SETTING_PHASE = "post_blueprint_setting"
BLUEPRINT_SETTING_SOURCE = "blueprint_setting"


def _extract_user_message(content: str) -> str:
    if not content:
        return ""
    normalized = unwrap_markdown_json(content)
    try:
        parsed = json.loads(normalized)
        if isinstance(parsed, dict):
            for key in ("message", "value", "content"):
                value = parsed.get(key)
                if isinstance(value, str) and value.strip():
                    return value
    except (json.JSONDecodeError, TypeError):
        pass
    return content


def _normalize_blueprint_setting_patch(raw_patch: Any) -> BlueprintPatch | None:
    if not isinstance(raw_patch, dict):
        return None

    try:
        patch_model = BlueprintPatch.model_validate(raw_patch)
    except Exception:
        return None

    patch_data = {
        key: value
        for key, value in patch_model.model_dump(exclude_none=True).items()
        if value not in (None, "", [], {})
    }
    if not patch_data:
        return None
    return BlueprintPatch.model_validate(patch_data)


def _extract_concept_ai_message(content: str) -> str:
    if not content:
        return ""
    normalized = unwrap_markdown_json(content)
    try:
        parsed = json.loads(normalized)
        if isinstance(parsed, dict):
            message = parsed.get("ai_message")
            if isinstance(message, str) and message.strip():
                return message
    except (json.JSONDecodeError, TypeError):
        pass
    return content


def _build_blueprint_setting_context(project_schema: NovelProjectSchema) -> str:
    blueprint = project_schema.blueprint
    if not blueprint:
        return "当前项目尚未生成完整蓝图。"

    blueprint_snapshot = {
        "title": blueprint.title,
        "target_audience": blueprint.target_audience,
        "genre": blueprint.genre,
        "style": blueprint.style,
        "tone": blueprint.tone,
        "one_sentence_summary": blueprint.one_sentence_summary,
        "full_synopsis": blueprint.full_synopsis,
        "world_setting": blueprint.world_setting,
        "characters": blueprint.characters,
        "relationships": [
            relation.model_dump() if hasattr(relation, "model_dump") else relation
            for relation in (blueprint.relationships or [])
        ],
        "chapter_outline": [
            outline.model_dump() if hasattr(outline, "model_dump") else outline
            for outline in (blueprint.chapter_outline or [])
        ],
    }
    written_chapters = [
        chapter.chapter_number
        for chapter in (project_schema.chapters or [])
        if chapter.content
    ]
    return (
        f"当前蓝图:\n{json.dumps(blueprint_snapshot, ensure_ascii=False, indent=2)}\n\n"
        f"已写正文章节: {written_chapters or '暂无'}"
    )


def _analyze_blueprint_patch_impact(
    project_schema: NovelProjectSchema,
    patch_model: BlueprintPatch | None,
) -> BlueprintSettingImpactAnalysis | None:
    if not patch_model:
        return None

    patch = patch_model.model_dump(exclude_none=True)
    impacted_sections: List[str] = []
    overview_fields = {
        "title",
        "target_audience",
        "genre",
        "style",
        "tone",
        "one_sentence_summary",
        "full_synopsis",
    }

    if any(field in patch for field in overview_fields):
        impacted_sections.append("overview")
    if "world_setting" in patch:
        impacted_sections.append("world_setting")
    if "characters" in patch:
        impacted_sections.append("characters")
    if "relationships" in patch:
        impacted_sections.append("relationships")
    if "chapter_outline" in patch:
        impacted_sections.append("chapter_outline")

    written_chapters = sorted(
        chapter.chapter_number
        for chapter in (project_schema.chapters or [])
        if chapter.content
    )
    outlined_chapters = sorted(
        outline.chapter_number
        for outline in (project_schema.blueprint.chapter_outline if project_schema.blueprint else [])
    )

    impacted_chapters: List[int] = []
    if "chapter_outline" in patch:
        patch_outline = patch.get("chapter_outline") or []
        patch_numbers = []
        for outline in patch_outline:
            if hasattr(outline, "chapter_number"):
                patch_numbers.append(outline.chapter_number)
            elif isinstance(outline, dict) and outline.get("chapter_number") is not None:
                patch_numbers.append(int(outline["chapter_number"]))
        impacted_chapters = sorted(set(outlined_chapters) | set(patch_numbers))
    elif any(field in patch for field in ("world_setting", "characters", "relationships")):
        impacted_chapters = written_chapters

    score = 1
    if any(field in patch for field in ("world_setting", "characters", "relationships")):
        score = max(score, 2)
    if "chapter_outline" in patch:
        score = max(score, 3)
    if written_chapters and any(field in patch for field in ("world_setting", "characters", "relationships", "chapter_outline")):
        score = max(score, 3)

    impact_level = {1: "low", 2: "medium", 3: "high"}[score]
    if impact_level == "low":
        summary = "这次调整主要落在蓝图概览层，通常不会直接影响已写正文。"
        recommended_actions = ["更新蓝图后，简单复核作品简介和书名展示即可。"]
    elif impact_level == "medium":
        summary = "这次调整涉及核心设定层，建议同步复核人物、关系与相关剧情大纲。"
        recommended_actions = ["应用修改后，检查相关人物卡和世界设定是否仍然一致。"]
    else:
        summary = "这次调整会影响故事结构或已写内容，建议在应用后复核受影响章节与大纲。"
        recommended_actions = ["应用修改后，优先检查受影响章节。", "必要时同步调整章节大纲。"]

    if written_chapters and impact_level != "low":
        recommended_actions.append("已写正文存在受影响风险，建议至少做一次一致性复查。")

    return BlueprintSettingImpactAnalysis(
        impact_level=impact_level,
        summary=summary,
        impacted_sections=impacted_sections,
        impacted_chapters=impacted_chapters,
        recommended_actions=recommended_actions,
    )


def _serialize_blueprint_setting_message(record: Any) -> BlueprintSettingChatMessage:
    metadata = record.metadata if isinstance(getattr(record, "metadata", None), dict) else {}
    created_at = record.created_at.isoformat() if getattr(record, "created_at", None) else None

    if record.role == "assistant":
        message = record.content
        proposed_patch = None
        impact_analysis = None
        source = metadata.get("source") or BLUEPRINT_SETTING_SOURCE
        try:
            payload = json.loads(unwrap_markdown_json(record.content))
            if isinstance(payload, dict):
                message = payload.get("ai_message") or payload.get("message") or message
                proposed_patch = _normalize_blueprint_setting_patch(payload.get("proposed_patch"))
                raw_impact = payload.get("impact_analysis")
                if isinstance(raw_impact, dict):
                    impact_analysis = BlueprintSettingImpactAnalysis.model_validate(raw_impact)
                source = payload.get("source") or source
        except (json.JSONDecodeError, TypeError, ValueError):
            pass

        return BlueprintSettingChatMessage(
            id=record.id,
            role=record.role,
            message=message,
            phase=BLUEPRINT_SETTING_PHASE,
            created_at=created_at,
            applied_to_blueprint=bool(metadata.get("applied_to_blueprint", False)),
            proposed_patch=proposed_patch,
            impact_analysis=impact_analysis,
            source=str(source),
        )

    return BlueprintSettingChatMessage(
        id=record.id,
        role=record.role,
        message=_extract_user_message(record.content),
        phase=BLUEPRINT_SETTING_PHASE,
        created_at=created_at,
        applied_to_blueprint=bool(metadata.get("applied_to_blueprint", False)),
        source=str(metadata.get("source") or BLUEPRINT_SETTING_SOURCE),
    )


def _serialize_concept_history_message(record: Any) -> BlueprintSettingChatMessage:
    if record.role == "assistant":
        message = _extract_concept_ai_message(record.content)
    else:
        message = _extract_user_message(record.content)

    return BlueprintSettingChatMessage(
        id=record.id,
        role=record.role,
        message=message,
        phase=CONCEPT_PHASE,
        created_at=record.created_at.isoformat() if getattr(record, "created_at", None) else None,
        applied_to_blueprint=False,
        source="concept_history",
    )


def _serialize_display_history_message(record: Any) -> BlueprintSettingChatMessage | None:
    metadata = record.metadata if isinstance(getattr(record, "metadata", None), dict) else {}
    phase = str(metadata.get("phase") or CONCEPT_PHASE)
    if phase == BLUEPRINT_SETTING_PHASE:
        return _serialize_blueprint_setting_message(record)
    if phase == CONCEPT_PHASE:
        return _serialize_concept_history_message(record)
    return None


async def _build_display_history(novel_service: NovelService, project_id: str) -> List[BlueprintSettingChatMessage]:
    all_records = await novel_service.list_conversations(project_id)
    history: List[BlueprintSettingChatMessage] = []
    for record in all_records:
        message = _serialize_display_history_message(record)
        if message and message.message:
            history.append(message)
    return history


@router.get("/{project_id}/blueprint/setting-chat/history", response_model=BlueprintSettingHistoryResponse)
async def get_blueprint_setting_chat_history(
    project_id: str,
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> BlueprintSettingHistoryResponse:
    novel_service = NovelService(session)
    await novel_service.ensure_project_owner(project_id, current_user.id)

    history = await _build_display_history(novel_service, project_id)
    return BlueprintSettingHistoryResponse(history=history)


@router.post("/{project_id}/blueprint/setting-chat/converse", response_model=BlueprintSettingConverseResponse)
async def converse_with_blueprint_setting(
    project_id: str,
    request: BlueprintSettingConverseRequest,
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> BlueprintSettingConverseResponse:
    novel_service = NovelService(session)
    llm_service = LLMService(session)

    user_message = request.user_message.strip()
    if not user_message:
        raise HTTPException(status_code=400, detail="补充设定内容不能为空")

    await novel_service.ensure_project_owner(project_id, current_user.id)
    project_schema = await novel_service.get_project_schema(project_id, current_user.id)

    history_records = await novel_service.list_conversations(project_id, phase=BLUEPRINT_SETTING_PHASE)
    conversation_history: List[Dict[str, str]] = []
    for record in history_records:
        message = _extract_user_message(record.content) if record.role == "user" else _serialize_blueprint_setting_message(record).message
        if message:
            conversation_history.append({"role": record.role, "content": message})
    conversation_history.append({"role": "user", "content": user_message})

    system_prompt = f"""你是一名小说蓝图后期设定助手。用户已经拥有一份蓝图，现在希望通过对话继续补充、修正、细化设定。

你的任务：
1. 先自然回应用户，延续创作讨论。
2. 如果用户明确提出“要加入、修改、替换、补充”某部分设定，就输出最小必要的 proposed_patch。
3. 如果用户只是讨论、试探、提问，proposed_patch 设为 null。
4. 只修改用户提到的部分，不要无端重写整份蓝图。
5. 若 proposed_patch 包含 characters、relationships、chapter_outline，这三个字段必须返回完整更新后的数组，不能只返回局部增量。

当前项目信息：
{_build_blueprint_setting_context(project_schema)}

仅允许修改以下字段：
- title
- target_audience
- genre
- style
- tone
- one_sentence_summary
- full_synopsis
- world_setting
- characters
- relationships
- chapter_outline

请严格输出 JSON 对象：
{{
  "ai_message": "给用户的自然回复",
  "proposed_patch": null,
  "need_confirm": false
}}

规则：
- 当 proposed_patch 不为空时，need_confirm 通常应为 true。
- 不要输出 markdown，不要输出额外解释。
- world_setting 可以只返回需要补充或覆盖的子字段。
"""

    llm_response = await llm_service.get_llm_response(
        system_prompt=system_prompt,
        conversation_history=conversation_history,
        temperature=0.5,
        user_id=current_user.id,
        timeout=240.0,
        response_format="json_object",
    )
    llm_response = remove_think_tags(llm_response)

    parsed: Dict[str, Any] = {}
    try:
        normalized = unwrap_markdown_json(llm_response)
        sanitized = sanitize_json_like_text(normalized)
        parsed = json.loads(sanitized)
    except (json.JSONDecodeError, TypeError, ValueError):
        parsed = {"ai_message": llm_response}

    ai_message = parsed.get("ai_message") or parsed.get("message") or "我先把这条补充设定记下来了，我们可以继续细化。"
    proposed_patch = _normalize_blueprint_setting_patch(parsed.get("proposed_patch"))
    impact_analysis = _analyze_blueprint_patch_impact(project_schema, proposed_patch)
    need_confirm = bool(parsed.get("need_confirm", bool(proposed_patch)))

    await novel_service.append_conversation(
        project_id,
        "user",
        user_message,
        metadata={"phase": BLUEPRINT_SETTING_PHASE, "source": BLUEPRINT_SETTING_SOURCE},
    )

    assistant_payload = {
        "ai_message": ai_message,
        "proposed_patch": proposed_patch.model_dump(exclude_none=True) if proposed_patch else None,
        "impact_analysis": impact_analysis.model_dump() if impact_analysis else None,
        "need_confirm": need_confirm,
        "source": BLUEPRINT_SETTING_SOURCE,
    }
    await novel_service.append_conversation(
        project_id,
        "assistant",
        json.dumps(assistant_payload, ensure_ascii=False),
        metadata={
            "phase": BLUEPRINT_SETTING_PHASE,
            "source": BLUEPRINT_SETTING_SOURCE,
            "applied_to_blueprint": False,
        },
    )

    history = await _build_display_history(novel_service, project_id)
    latest_message_id = history[-1].id if history else None

    logger.info(
        "项目 %s 蓝图后设定对话完成，proposed_patch=%s impact=%s",
        project_id,
        bool(proposed_patch),
        impact_analysis.impact_level if impact_analysis else "none",
    )

    return BlueprintSettingConverseResponse(
        ai_message=str(ai_message),
        history=history,
        proposed_patch=proposed_patch,
        impact_analysis=impact_analysis,
        need_confirm=need_confirm,
        latest_message_id=latest_message_id,
    )


@router.post("/{project_id}/blueprint/setting-chat/apply", response_model=NovelProjectSchema)
async def apply_blueprint_setting_patch(
    project_id: str,
    payload: ApplyBlueprintSettingPatchRequest,
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> NovelProjectSchema:
    novel_service = NovelService(session)
    await novel_service.ensure_project_owner(project_id, current_user.id)

    patch_data = {
        key: value
        for key, value in payload.patch.model_dump(exclude_none=True).items()
        if value not in (None, "", [], {})
    }
    if not patch_data:
        raise HTTPException(status_code=400, detail="没有可应用的蓝图修改内容")

    await novel_service.patch_blueprint(project_id, patch_data)

    if payload.assistant_message_id is not None:
        await novel_service.merge_conversation_metadata(
            project_id,
            payload.assistant_message_id,
            {
                "phase": BLUEPRINT_SETTING_PHASE,
                "source": BLUEPRINT_SETTING_SOURCE,
                "applied_to_blueprint": True,
            },
        )

    logger.info("项目 %s 应用蓝图后设定补丁：%s", project_id, list(patch_data.keys()))
    return await novel_service.get_project_schema(project_id, current_user.id)
