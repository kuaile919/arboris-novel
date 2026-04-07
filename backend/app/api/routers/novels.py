# AIMETA P=小说API_项目和章节管理|R=小说CRUD_章节管理|NR=不含内容生成|E=route:GET_POST_/api/novels/*|X=http|A=小说CRUD_章节|D=fastapi,sqlalchemy|S=db|RD=./README.ai
import json
import logging
from typing import Any, Dict, List

from fastapi import APIRouter, Body, Depends, HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.dependencies import get_current_user
from ...db.session import get_session
from ...schemas.novel import (
    ApplyBlueprintSettingPatchRequest,
    Blueprint,
    BlueprintGenerationResponse,
    BlueprintPatch,
    BlueprintSettingChatMessage,
    BlueprintSettingConverseRequest,
    BlueprintSettingConverseResponse,
    BlueprintSettingHistoryResponse,
    BlueprintSettingImpactAnalysis,
    Chapter as ChapterSchema,
    ConverseRequest,
    ConverseResponse,
    NovelProject as NovelProjectSchema,
    NovelProjectSummary,
    NovelSectionResponse,
    NovelSectionType,
)
from ...schemas.user import UserInDB
from ...services.import_service import ImportService
from ...services.llm_service import LLMService
from ...services.novel_service import NovelService
from ...services.prompt_service import PromptService
from ...utils.json_utils import remove_think_tags, sanitize_json_like_text, unwrap_markdown_json

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/novels", tags=["Novels"])

CONCEPT_PHASE = "concept"
BLUEPRINT_SETTING_PHASE = "post_blueprint_setting"
BLUEPRINT_SETTING_SOURCE = "blueprint_setting"

JSON_RESPONSE_INSTRUCTION = """
IMPORTANT: 你的回复必须是合法的 JSON 对象，并严格包含以下字段：
{
  "ai_message": "string",
  "ui_control": {
    "type": "single_choice | text_input | info_display",
    "options": [
      {"id": "option_1", "label": "string"}
    ],
    "placeholder": "string"
  },
  "conversation_state": {},
  "is_complete": false
}
不要输出额外的文本或解释。
"""


def _ensure_prompt(prompt: str | None, name: str) -> str:
    if not prompt:
        raise HTTPException(status_code=500, detail=f"未配置名为 {name} 的提示词，请联系管理员")
    return prompt


def _build_market_context_prompt(market_context: dict, history_records: list) -> str:
    """根据市场数据和对话历史构建针对性的市场提示词。

    只在合适的时机（第二轮对话）注入市场数据，避免过早或过晚。
    """
    if not market_context.get("has_data"):
        return ""

    top_genres = market_context.get("top_genres", [])
    hot_keywords = market_context.get("hot_keywords", [])
    suggestions = market_context.get("creation_suggestions", [])

    # 构建热门题材占比文本
    genre_text = ""
    if top_genres:
        genre_parts = []
        for i, genre in enumerate(top_genres[:5], 1):
            # 简化的占比展示（实际应从数据中获取）
            percentage = max(35 - i * 5, 5)
            genre_parts.append(f"{genre}({percentage}%)")
        genre_text = "、".join(genre_parts)

    # 构建热门元素文本
    elements_text = "、".join(hot_keywords[:8]) if hot_keywords else "暂无数据"

    # 构建创作建议文本
    suggestions_text = ""
    if suggestions:
        suggestions_text = "\n".join(f"- {s}" for s in suggestions[:3])

    prompt = f"""## 当前网文市场风向（供参考，非强制）

热门题材分布: {genre_text}
热门元素: {elements_text}

创作机会:
{suggestions_text}

使用指南：
- 如果用户询问"现在流行什么""什么题材好写"，基于以上数据回答
- 如果用户已确定题材，可简要提及该题材的市场竞争情况
- 热门题材意味着读者多但竞争大，冷门题材有蓝海机会
- 尊重用户选择，市场数据仅供参考，非创作唯一标准"""

    return prompt


def _default_converse_message(ui_control: Dict[str, Any]) -> str:
    control_type = str(ui_control.get("type") or "").strip()
    if control_type == "single_choice":
        return "我先把几个方向整理出来了，你选一个，我们继续往下细化。"
    if control_type == "text_input":
        return "我先把关键点收拢好了，你直接补充想法，我继续帮你整理。"
    return "我先整理了当前建议，我们继续往下推进。"


def _normalize_converse_payload(parsed: Any, fallback_state: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(parsed, dict):
        raise HTTPException(status_code=500, detail="概念对话失败：AI 返回的数据不是 JSON 对象。")

    data = dict(parsed)

    if "ui_control" not in data and any(key in data for key in ("type", "options", "placeholder")):
        ui_control = {
            "type": data.get("type", "info_display"),
            "options": data.get("options"),
            "placeholder": data.get("placeholder"),
        }
        data = {
            "ai_message": data.get("ai_message") or _default_converse_message(ui_control),
            "ui_control": ui_control,
            "conversation_state": data.get("conversation_state") or dict(fallback_state or {}),
            "is_complete": bool(data.get("is_complete", False)),
            "ready_for_blueprint": data.get("ready_for_blueprint"),
        }

    ui_control = data.get("ui_control")
    if not isinstance(ui_control, dict):
        ui_control = {"type": "info_display", "options": None, "placeholder": None}

    ui_control.setdefault("type", "info_display")
    ui_control.setdefault("options", ui_control.get("options"))
    ui_control.setdefault("placeholder", ui_control.get("placeholder"))
    data["ui_control"] = ui_control

    ai_message = data.get("ai_message")
    if not isinstance(ai_message, str) or not ai_message.strip():
        data["ai_message"] = _default_converse_message(ui_control)

    conversation_state = data.get("conversation_state")
    if not isinstance(conversation_state, dict) or not conversation_state:
        data["conversation_state"] = dict(fallback_state or {})

    data["is_complete"] = bool(data.get("is_complete", False))
    return data


def _conversation_metadata(record: Any) -> Dict[str, Any]:
    metadata = getattr(record, "metadata", None)
    return metadata if isinstance(metadata, dict) else {}


def _conversation_phase(record: Any) -> str:
    metadata = _conversation_metadata(record)
    return str(metadata.get("phase") or CONCEPT_PHASE)


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
    metadata = _conversation_metadata(record)
    created_at = record.created_at.isoformat() if getattr(record, "created_at", None) else None
    phase = _conversation_phase(record)

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
            phase=phase,
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
        phase=phase,
        created_at=created_at,
        applied_to_blueprint=bool(metadata.get("applied_to_blueprint", False)),
        source=str(metadata.get("source") or BLUEPRINT_SETTING_SOURCE),
    )


@router.post("", response_model=NovelProjectSchema, status_code=status.HTTP_201_CREATED)
async def create_novel(
    title: str = Body(...),
    initial_prompt: str = Body(...),
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> NovelProjectSchema:
    """为当前用户创建一个新的小说项目。"""
    novel_service = NovelService(session)
    project = await novel_service.create_project(current_user.id, title, initial_prompt)
    logger.info("用户 %s 创建项目 %s", current_user.id, project.id)
    return await novel_service.get_project_schema(project.id, current_user.id)


@router.post("/import", response_model=Dict[str, str], status_code=status.HTTP_201_CREATED)
async def import_novel(
    file: UploadFile,
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> Dict[str, str]:
    """上传并导入小说文件。"""
    import_service = ImportService(session)
    project_id = await import_service.import_novel_from_file(current_user.id, file)
    logger.info("用户 %s 导入项目 %s", current_user.id, project_id)
    return {"id": project_id}


@router.get("", response_model=List[NovelProjectSummary])
async def list_novels(
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> List[NovelProjectSummary]:
    """列出用户的全部小说项目摘要信息。"""
    novel_service = NovelService(session)
    projects = await novel_service.list_projects_for_user(current_user.id)
    logger.info("用户 %s 获取项目列表，共 %s 个", current_user.id, len(projects))
    return projects


@router.get("/{project_id}", response_model=NovelProjectSchema)
async def get_novel(
    project_id: str,
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> NovelProjectSchema:
    novel_service = NovelService(session)
    logger.info("用户 %s 查询项目 %s", current_user.id, project_id)
    return await novel_service.get_project_schema(project_id, current_user.id)


@router.get("/{project_id}/sections/{section}", response_model=NovelSectionResponse)
async def get_novel_section(
    project_id: str,
    section: NovelSectionType,
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> NovelSectionResponse:
    novel_service = NovelService(session)
    logger.info("用户 %s 获取项目 %s 的 %s 区段", current_user.id, project_id, section)
    return await novel_service.get_section_data(project_id, current_user.id, section)


@router.get("/{project_id}/chapters/{chapter_number}", response_model=ChapterSchema)
async def get_chapter(
    project_id: str,
    chapter_number: int,
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> ChapterSchema:
    novel_service = NovelService(session)
    logger.info("用户 %s 获取项目 %s 第 %s 章", current_user.id, project_id, chapter_number)
    return await novel_service.get_chapter_schema(project_id, current_user.id, chapter_number)


@router.delete("", status_code=status.HTTP_200_OK)
async def delete_novels(
    project_ids: List[str] = Body(...),
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> Dict[str, str]:
    novel_service = NovelService(session)
    await novel_service.delete_projects(project_ids, current_user.id)
    logger.info("用户 %s 删除项目 %s", current_user.id, project_ids)
    return {"status": "success", "message": f"成功删除 {len(project_ids)} 个项目"}


@router.post("/{project_id}/concept/converse", response_model=ConverseResponse)
async def converse_with_concept(
    project_id: str,
    request: ConverseRequest,
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> ConverseResponse:
    """与概念设计师（LLM）进行对话，引导蓝图筹备。"""
    novel_service = NovelService(session)
    prompt_service = PromptService(session)
    llm_service = LLMService(session)

    project = await novel_service.ensure_project_owner(project_id, current_user.id)

    history_records = await novel_service.list_conversations(
        project_id,
        phase=CONCEPT_PHASE,
        include_legacy=True,
    )
    logger.info(
        "项目 %s 概念对话请求，用户 %s，历史记录 %s 条",
        project_id,
        current_user.id,
        len(history_records),
    )
    conversation_history = [
        {"role": record.role, "content": record.content}
        for record in history_records
    ]
    user_content = json.dumps(request.user_input, ensure_ascii=False)
    conversation_history.append({"role": "user", "content": user_content})

    # 选择提示词：优先使用市场感知版，否则使用标准版
    concept_prompt = await prompt_service.get_prompt("market_aware_concept")
    if not concept_prompt:
        concept_prompt = await prompt_service.get_prompt("concept")
    system_prompt = _ensure_prompt(concept_prompt, "concept")
    system_prompt = f"{system_prompt}\n{JSON_RESPONSE_INSTRUCTION}"

    # 智能注入市场风向数据（第二轮对话时注入，此时用户已表达创作意图）
    if len(history_records) >= 1:  # 第二轮及以后
        try:
            from ...services.trend.analysis_service import TrendAnalysisService
            trend_service = TrendAnalysisService(session)
            market_context = await trend_service.get_market_context_for_inspiration()

            if market_context and market_context.get("has_data"):
                # 构建针对性的市场提示词
                trend_prompt = _build_market_context_prompt(market_context, history_records)
                if trend_prompt:
                    system_prompt = f"{system_prompt}\n\n{trend_prompt}"
                    logger.debug("市场数据已注入对话上下文")
        except Exception as e:
            logger.debug("市场风向数据注入失败（非致命）: %s", e)

    llm_response = await llm_service.get_llm_response(
        system_prompt=system_prompt,
        conversation_history=conversation_history,
        temperature=0.8,
        user_id=current_user.id,
        timeout=240.0,
    )
    llm_response = remove_think_tags(llm_response)

    try:
        normalized = unwrap_markdown_json(llm_response)
        sanitized = sanitize_json_like_text(normalized)
        parsed = json.loads(sanitized)
        parsed = _normalize_converse_payload(parsed, request.conversation_state)
    except json.JSONDecodeError as exc:
        logger.exception(
            "Failed to parse concept converse response: project_id=%s user_id=%s error=%s\nOriginal response: %s\nNormalized: %s\nSanitized: %s",
            project_id,
            current_user.id,
            exc,
            llm_response[:1000],
            normalized[:1000] if 'normalized' in locals() else "N/A",
            sanitized[:1000] if 'sanitized' in locals() else "N/A",
        )
        raise HTTPException(
            status_code=500,
            detail=f"概念对话失败，AI 返回的内容格式不正确。请重试或联系管理员。错误详情: {str(exc)}"
        ) from exc

    assistant_content = json.dumps(parsed, ensure_ascii=False)
    await novel_service.append_conversation(
        project_id,
        "user",
        user_content,
        metadata={"phase": CONCEPT_PHASE},
    )
    await novel_service.append_conversation(
        project_id,
        "assistant",
        assistant_content,
        metadata={"phase": CONCEPT_PHASE},
    )

    logger.info("项目 %s 概念对话完成，is_complete=%s", project_id, parsed.get("is_complete"))

    if parsed.get("is_complete"):
        parsed["ready_for_blueprint"] = True

    parsed.setdefault("conversation_state", parsed.get("conversation_state", {}))
    return ConverseResponse(**parsed)


@router.post("/{project_id}/blueprint/generate", response_model=BlueprintGenerationResponse)
async def generate_blueprint(
    project_id: str,
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> BlueprintGenerationResponse:
    """根据完整对话生成可执行的小说蓝图。"""
    novel_service = NovelService(session)
    prompt_service = PromptService(session)
    llm_service = LLMService(session)

    project = await novel_service.ensure_project_owner(project_id, current_user.id)
    logger.info("项目 %s 开始生成蓝图", project_id)

    history_records = await novel_service.list_conversations(
        project_id,
        phase=CONCEPT_PHASE,
        include_legacy=True,
    )
    if not history_records:
        logger.warning("项目 %s 缺少对话历史，无法生成蓝图", project_id)
        raise HTTPException(status_code=400, detail="缺少对话历史，请先完成概念对话后再生成蓝图")

    formatted_history: List[Dict[str, str]] = []
    for record in history_records:
        role = record.role
        content = record.content
        if not role or not content:
            continue
        try:
            normalized = unwrap_markdown_json(content)
            data = json.loads(normalized)
            if role == "user":
                user_value = data.get("value", data)
                if isinstance(user_value, str):
                    formatted_history.append({"role": "user", "content": user_value})
            elif role == "assistant":
                ai_message = data.get("ai_message") if isinstance(data, dict) else None
                if ai_message:
                    formatted_history.append({"role": "assistant", "content": ai_message})
        except (json.JSONDecodeError, AttributeError):
            continue

    if not formatted_history:
        logger.warning("项目 %s 对话历史格式异常，无法提取有效内容", project_id)
        raise HTTPException(
            status_code=400,
            detail="无法从历史对话中提取有效内容，请检查对话历史格式或重新进行概念对话"
        )

    system_prompt = _ensure_prompt(await prompt_service.get_prompt("screenwriting"), "screenwriting")
    blueprint_raw = await llm_service.get_llm_response(
        system_prompt=system_prompt,
        conversation_history=formatted_history,
        temperature=0.3,
        user_id=current_user.id,
        timeout=480.0,
    )
    blueprint_raw = remove_think_tags(blueprint_raw)

    blueprint_normalized = unwrap_markdown_json(blueprint_raw)
    blueprint_sanitized = sanitize_json_like_text(blueprint_normalized)
    try:
        blueprint_data = json.loads(blueprint_sanitized)
    except json.JSONDecodeError as exc:
        logger.error(
            "项目 %s 蓝图生成 JSON 解析失败: %s\n原始响应: %s\n标准化后: %s\n清洗后: %s",
            project_id,
            exc,
            blueprint_raw[:500],
            blueprint_normalized[:500],
            blueprint_sanitized[:500],
        )
        raise HTTPException(
            status_code=500,
            detail=f"蓝图生成失败，AI 返回的内容格式不正确。请重试或联系管理员。错误详情: {str(exc)}"
        ) from exc

    if isinstance(blueprint_data, dict):
        blueprint_data["chapter_outline"] = []

    blueprint = Blueprint(**blueprint_data)
    await novel_service.replace_blueprint(project_id, blueprint)
    if blueprint.title:
        project.title = blueprint.title
        project.status = "blueprint_ready"
        await session.commit()
        logger.info("项目 %s 更新标题为 %s，并标记为 blueprint_ready", project_id, blueprint.title)

    ai_message = (
        "太棒了！我已经根据我们的对话整理出完整的小说蓝图。请确认是否进入写作阶段，或提出修改意见。"
    )
    return BlueprintGenerationResponse(blueprint=blueprint, ai_message=ai_message)


@router.post("/{project_id}/blueprint/save", response_model=NovelProjectSchema)
async def save_blueprint(
    project_id: str,
    blueprint_data: Blueprint | None = Body(None),
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> NovelProjectSchema:
    """保存蓝图信息，可用于手动覆盖自动生成结果。"""
    novel_service = NovelService(session)
    project = await novel_service.ensure_project_owner(project_id, current_user.id)

    if blueprint_data:
        await novel_service.replace_blueprint(project_id, blueprint_data)
        if blueprint_data.title:
            project.title = blueprint_data.title
            await session.commit()
        logger.info("项目 %s 手动保存蓝图", project_id)
    else:
        logger.warning("项目 %s 保存蓝图时未提供蓝图数据", project_id)
        raise HTTPException(status_code=400, detail="缺少蓝图数据，请提供有效的蓝图内容")

    return await novel_service.get_project_schema(project_id, current_user.id)


@router.patch("/{project_id}/blueprint", response_model=NovelProjectSchema)
async def patch_blueprint(
    project_id: str,
    payload: BlueprintPatch,
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> NovelProjectSchema:
    """局部更新蓝图字段，对世界观或角色做微调。"""
    novel_service = NovelService(session)
    project = await novel_service.ensure_project_owner(project_id, current_user.id)

    update_data = payload.model_dump(exclude_unset=True)
    await novel_service.patch_blueprint(project_id, update_data)
    logger.info("项目 %s 局部更新蓝图字段：%s", project_id, list(update_data.keys()))
    return await novel_service.get_project_schema(project_id, current_user.id)
