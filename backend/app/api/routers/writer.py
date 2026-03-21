# AIMETA P=写作API_章节生成和大纲创建|R=章节生成_大纲生成_评审_L2导演脚本_护栏检查|NR=不含数据存储|E=route:POST_/api/writer/*|X=http|A=生成_评审_过滤|D=fastapi,openai|S=net,db|RD=./README.ai
"""
Writer API Router - 人类化起点长篇写作系统

核心架构：
- L1 Planner：全知规划层（蓝图/大纲）
- L2 Director：章节导演脚本（ChapterMission）
- L3 Writer：有限视角正文生成

关键改进：
1. 信息可见性过滤：L3 Writer 只能看到已登场角色
2. 跨章 1234 逻辑：通过 ChapterMission 控制每章只写一个节拍
3. 后置护栏检查：自动检测并修复违规内容
"""
import asyncio
import json
import logging
import os
from typing import Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ...core.config import settings
from ...core.dependencies import get_current_user
from ...db.session import AsyncSessionLocal, get_session
from ...models.novel import Chapter, ChapterOutline, ChapterVersion
from ...schemas.novel import (
    Chapter as ChapterSchema,
    ChapterGenerationStatus,
    AdvancedGenerateRequest,
    AdvancedGenerateResponse,
    DeleteChapterRequest,
    EditChapterRequest,
    EvaluateChapterRequest,
    FinalizeChapterRequest,
    FinalizeChapterResponse,
    GenerateChapterRequest,
    GenerateOutlineRequest,
    NovelProject as NovelProjectSchema,
    SelectVersionRequest,
    UpdateChapterOutlineRequest,
    ChapterOutlineConverseRequest,
    ChapterOutlineConverseResponse,
    ProposedOutline,
    OutlinePreviewRequest,
    OutlinePreviewResponse,
    OutlineConfirmRequest,
)
from ...schemas.user import UserInDB
from ...services.chapter_context_service import ChapterContextService
from ...services.chapter_ingest_service import ChapterIngestionService
from ...services.llm_service import LLMService
from ...services.novel_service import NovelService
from ...services.prompt_service import PromptService
from ...services.vector_store_service import VectorStoreService
from ...services.writer_context_builder import WriterContextBuilder
from ...services.chapter_guardrails import ChapterGuardrails
from ...services.ai_review_service import AIReviewService
from ...services.finalize_service import FinalizeService
from ...services.foreshadowing_service import ForeshadowingService
from ...utils.json_utils import remove_think_tags, unwrap_markdown_json, sanitize_json_like_text
from ...repositories.system_config_repository import SystemConfigRepository
from ...services.pipeline_orchestrator import PipelineOrchestrator

router = APIRouter(prefix="/api/writer", tags=["Writer"])
logger = logging.getLogger(__name__)


async def _load_project_schema(service: NovelService, project_id: str, user_id: int) -> NovelProjectSchema:
    return await service.get_project_schema(project_id, user_id)


def _extract_tail_excerpt(text: Optional[str], limit: int = 500) -> str:
    """截取章节结尾文本，默认保留 500 字。"""
    if not text:
        return ""
    stripped = text.strip()
    if len(stripped) <= limit:
        return stripped
    return stripped[-limit:]


async def _resolve_version_count(session: AsyncSession) -> int:
    """
    解析章节版本数量配置，优先级：
    1) SystemConfig: writer.chapter_versions
    2) SystemConfig: writer.version_count（兼容旧键）
    3) ENV: WRITER_CHAPTER_VERSION_COUNT / WRITER_CHAPTER_VERSIONS（与 config.py 对齐）
    4) ENV: WRITER_VERSION_COUNT（兼容旧）
    5) settings.writer_chapter_versions（默认=2）
    """
    repo = SystemConfigRepository(session)
    # 1) 新键优先，兼容旧键
    for key in ("writer.chapter_versions", "writer.version_count"):
        record = await repo.get_by_key(key)
        if record and record.value:
            try:
                val = int(record.value)
                if val >= 1:
                    return val
            except ValueError:
                pass
    # 2) 环境变量（与 Settings 对齐）
    for env in ("WRITER_CHAPTER_VERSION_COUNT", "WRITER_CHAPTER_VERSIONS", "WRITER_VERSION_COUNT"):
        v = os.getenv(env)
        if v:
            try:
                val = int(v)
                if val >= 1:
                    return val
            except ValueError:
                pass
    # 3) 默认值
    return int(settings.writer_chapter_versions)


async def _generate_chapter_mission(
    llm_service: LLMService,
    prompt_service: PromptService,
    blueprint_dict: dict,
    previous_summary: str,
    previous_tail: str,
    outline_title: str,
    outline_summary: str,
    writing_notes: str,
    introduced_characters: List[str],
    all_characters: List[str],
    user_id: int,
) -> Optional[dict]:
    """
    L2 Director: 生成章节导演脚本（ChapterMission）
    """
    plan_prompt = await prompt_service.get_prompt("chapter_plan")
    if not plan_prompt:
        logger.warning("未配置 chapter_plan 提示词，跳过导演脚本生成")
        return None

    plan_input = f"""
[上一章摘要]
{previous_summary or "暂无（这是第一章）"}

[上一章结尾]
{previous_tail or "暂无（这是第一章）"}

[当前章节大纲]
标题：{outline_title}
摘要：{outline_summary}

[已登场角色]
{json.dumps(introduced_characters, ensure_ascii=False) if introduced_characters else "暂无"}

[全部角色]
{json.dumps(all_characters, ensure_ascii=False)}

[写作指令]
{writing_notes or "无额外指令"}
"""

    try:
        response = await llm_service.get_llm_response(
            system_prompt=plan_prompt,
            conversation_history=[{"role": "user", "content": plan_input}],
            temperature=0.3,
            user_id=user_id,
            timeout=120.0,
        )
        cleaned = remove_think_tags(response)
        normalized = unwrap_markdown_json(cleaned)
        mission = json.loads(normalized)
        logger.info("成功生成章节导演脚本: macro_beat=%s", mission.get("macro_beat"))
        return mission
    except Exception as exc:
        logger.warning("生成章节导演脚本失败，将使用默认模式: %s", exc)
        return None


async def _rewrite_with_guardrails(
    llm_service: LLMService,
    prompt_service: PromptService,
    original_text: str,
    chapter_mission: Optional[dict],
    violations_text: str,
    user_id: int,
) -> str:
    """
    使用护栏修复提示词重写违规内容
    """
    rewrite_prompt = await prompt_service.get_prompt("rewrite_guardrails")
    if not rewrite_prompt:
        logger.warning("未配置 rewrite_guardrails 提示词，跳过自动修复")
        return original_text

    rewrite_input = f"""
[原文]
{original_text}

[章节导演脚本]
{json.dumps(chapter_mission, ensure_ascii=False, indent=2) if chapter_mission else "无"}

[违规列表]
{violations_text}
"""

    try:
        response = await llm_service.get_llm_response(
            system_prompt=rewrite_prompt,
            conversation_history=[{"role": "user", "content": rewrite_input}],
            temperature=0.3,
            user_id=user_id,
            timeout=300.0,
            response_format=None,
        )
        cleaned = remove_think_tags(response)
        logger.info("成功修复违规内容")
        return cleaned
    except Exception as exc:
        logger.warning("自动修复失败，返回原文: %s", exc)
        return original_text


async def _refresh_edit_summary_and_ingest(
    project_id: str,
    chapter_number: int,
    content: str,
    user_id: Optional[int],
) -> None:
    async with AsyncSessionLocal() as session:
        llm_service = LLMService(session)

        stmt = (
            select(Chapter)
            .options(selectinload(Chapter.selected_version))
            .where(
                Chapter.project_id == project_id,
                Chapter.chapter_number == chapter_number,
            )
        )
        result = await session.execute(stmt)
        chapter = result.scalars().first()
        if not chapter:
            return

        summary_text = None
        try:
            summary = await llm_service.get_summary(
                content,
                temperature=0.15,
                user_id=user_id,
            )
            summary_text = remove_think_tags(summary)
        except Exception as exc:
            logger.warning("编辑章节后自动生成摘要失败: %s", exc)

        if summary_text:
            try:
                if chapter.selected_version and chapter.selected_version.content == content:
                    chapter.real_summary = summary_text
                    await session.commit()
            except Exception as exc:
                logger.warning("编辑章节后保存摘要到 DB 失败: %s", exc)

        try:
            outline_stmt = select(ChapterOutline).where(
                ChapterOutline.project_id == project_id,
                ChapterOutline.chapter_number == chapter_number,
            )
            outline_result = await session.execute(outline_stmt)
            outline = outline_result.scalars().first()
            title = outline.title if outline and outline.title else f"第{chapter_number}章"
            ingest_service = ChapterIngestionService(llm_service=llm_service)
            await ingest_service.ingest_chapter(
                project_id=project_id,
                chapter_number=chapter_number,
                title=title,
                content=content,
                summary=summary_text,
                user_id=user_id or 0,
            )
            logger.info("章节 %s 向量化入库成功", chapter_number)
        except Exception as exc:
            logger.error("章节 %s 向量化入库失败: %s", chapter_number, exc)


async def _finalize_chapter_async(
    project_id: str,
    chapter_number: int,
    selected_version_id: int,
    user_id: int,
    skip_vector_update: bool = False,
) -> None:
    async with AsyncSessionLocal() as session:
        llm_service = LLMService(session)

        stmt = (
            select(Chapter)
            .options(selectinload(Chapter.versions))
            .where(
                Chapter.project_id == project_id,
                Chapter.chapter_number == chapter_number,
            )
        )
        result = await session.execute(stmt)
        chapter = result.scalars().first()
        if not chapter:
            return

        selected_version = next(
            (v for v in chapter.versions if v.id == selected_version_id),
            None,
        )
        if not selected_version or not selected_version.content:
            return

        chapter.selected_version_id = selected_version.id
        chapter.status = ChapterGenerationStatus.SUCCESSFUL.value
        chapter.word_count = len(selected_version.content or "")
        await session.commit()

        vector_store = None
        if settings.vector_store_enabled:
            try:
                vector_store = VectorStoreService()
            except RuntimeError as exc:
                logger.warning("向量库初始化失败，跳过定稿写入: %s", exc)

        sync_session = getattr(session, "sync_session", session)
        finalize_service = FinalizeService(sync_session, llm_service, vector_store)
        await finalize_service.finalize_chapter(
            project_id=project_id,
            chapter_number=chapter_number,
            chapter_text=selected_version.content,
            user_id=user_id,
            skip_vector_update=skip_vector_update,
        )


def _schedule_finalize_task(
    project_id: str,
    chapter_number: int,
    selected_version_id: int,
    user_id: int,
    skip_vector_update: bool = False,
) -> None:
    asyncio.create_task(
        _finalize_chapter_async(
            project_id=project_id,
            chapter_number=chapter_number,
            selected_version_id=selected_version_id,
            user_id=user_id,
            skip_vector_update=skip_vector_update,
        )
    )


@router.post("/advanced/generate", response_model=AdvancedGenerateResponse)
async def advanced_generate_chapter(
    request: AdvancedGenerateRequest,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> AdvancedGenerateResponse:
    """
    高级写作入口：通过 PipelineOrchestrator 统一编排生成流程。
    """
    orchestrator = PipelineOrchestrator(session)
    result = await orchestrator.generate_chapter(
        project_id=request.project_id,
        chapter_number=request.chapter_number,
        writing_notes=request.writing_notes,
        user_id=current_user.id,
        flow_config=request.flow_config.model_dump(),
    )

    flow_config = request.flow_config
    if flow_config.async_finalize and result.get("variants"):
        best_index = result.get("best_version_index", 0)
        variants = result["variants"]
        if 0 <= best_index < len(variants):
            selected_version_id = variants[best_index]["version_id"]
            background_tasks.add_task(
                _schedule_finalize_task,
                request.project_id,
                request.chapter_number,
                selected_version_id,
                current_user.id,
                False,
            )

    return AdvancedGenerateResponse(**result)


@router.post("/chapters/{chapter_number}/finalize", response_model=FinalizeChapterResponse)
async def finalize_chapter(
    chapter_number: int,
    request: FinalizeChapterRequest,
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> FinalizeChapterResponse:
    """
    定稿入口：选中版本后触发 FinalizeService 进行记忆更新与快照写入。
    """
    novel_service = NovelService(session)
    await novel_service.ensure_project_owner(request.project_id, current_user.id)

    stmt = (
        select(Chapter)
        .options(selectinload(Chapter.versions))
        .where(
            Chapter.project_id == request.project_id,
            Chapter.chapter_number == chapter_number,
        )
    )
    result = await session.execute(stmt)
    chapter = result.scalars().first()
    if not chapter:
        raise HTTPException(status_code=404, detail="章节不存在")

    selected_version = next(
        (v for v in chapter.versions if v.id == request.selected_version_id),
        None,
    )
    if not selected_version or not selected_version.content:
        raise HTTPException(status_code=400, detail="选中的版本不存在或内容为空")

    chapter.selected_version_id = selected_version.id
    chapter.status = ChapterGenerationStatus.SUCCESSFUL.value
    chapter.word_count = len(selected_version.content or "")
    await session.commit()

    vector_store = None
    if settings.vector_store_enabled and not request.skip_vector_update:
        try:
            vector_store = VectorStoreService()
        except RuntimeError as exc:
            logger.warning("向量库初始化失败，跳过定稿写入: %s", exc)

    sync_session = getattr(session, "sync_session", session)
    finalize_service = FinalizeService(sync_session, LLMService(session), vector_store)
    finalize_result = await finalize_service.finalize_chapter(
        project_id=request.project_id,
        chapter_number=chapter_number,
        chapter_text=selected_version.content,
        user_id=current_user.id,
        skip_vector_update=request.skip_vector_update or False,
    )

    return FinalizeChapterResponse(
        project_id=request.project_id,
        chapter_number=chapter_number,
        selected_version_id=selected_version.id,
        result=finalize_result,
    )


@router.post("/novels/{project_id}/chapters/generate", response_model=NovelProjectSchema)
async def generate_chapter(
    project_id: str,
    request: GenerateChapterRequest,
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> NovelProjectSchema:
    """
    生成章节正文 - 三层架构流程：
    1. 收集上下文和历史摘要
    2. L2 Director: 生成章节导演脚本（ChapterMission）
    3. 信息可见性过滤：裁剪蓝图，移除未登场角色
    4. L3 Writer: 生成正文（使用 writing_v2 提示词）
    5. 护栏检查：检测并修复违规内容
    """
    novel_service = NovelService(session)
    prompt_service = PromptService(session)
    llm_service = LLMService(session)
    context_builder = WriterContextBuilder()
    guardrails = ChapterGuardrails()

    project = await novel_service.ensure_project_owner(project_id, current_user.id)
    logger.info("用户 %s 开始为项目 %s 生成第 %s 章", current_user.id, project_id, request.chapter_number)
    outline = await novel_service.get_outline(project_id, request.chapter_number)
    if not outline:
        logger.warning("项目 %s 未找到第 %s 章纲要，生成流程终止", project_id, request.chapter_number)
        raise HTTPException(status_code=404, detail="蓝图中未找到对应章节纲要")

    chapter = await novel_service.get_or_create_chapter(project_id, request.chapter_number)
    chapter.real_summary = None
    chapter.selected_version_id = None
    chapter.status = "generating"
    await session.commit()

    outlines_map = {item.chapter_number: item for item in project.outlines}
    
    # ========== 1. 收集历史上下文 ==========
    completed_chapters = []
    completed_summaries = []
    latest_prev_number = -1
    previous_summary_text = ""
    previous_tail_excerpt = ""
    
    for existing in project.chapters:
        if existing.chapter_number >= request.chapter_number:
            continue
        if existing.selected_version is None or not existing.selected_version.content:
            continue
        if not existing.real_summary:
            summary = await llm_service.get_summary(
                existing.selected_version.content,
                temperature=0.15,
                user_id=current_user.id,
                timeout=180.0,
            )
            existing.real_summary = remove_think_tags(summary)
            await session.commit()
        completed_chapters.append({
            "chapter_number": existing.chapter_number,
            "title": outlines_map.get(existing.chapter_number).title if outlines_map.get(existing.chapter_number) else f"第{existing.chapter_number}章",
            "summary": existing.real_summary,
        })
        completed_summaries.append(existing.real_summary or "")
        if existing.chapter_number > latest_prev_number:
            latest_prev_number = existing.chapter_number
            previous_summary_text = existing.real_summary or ""
            previous_tail_excerpt = _extract_tail_excerpt(existing.selected_version.content)

    project_schema = await novel_service._serialize_project(project)
    blueprint_dict = project_schema.blueprint.model_dump()

    # 处理关系字段名
    if "relationships" in blueprint_dict and blueprint_dict["relationships"]:
        for relation in blueprint_dict["relationships"]:
            if "character_from" in relation:
                relation["from"] = relation.pop("character_from")
            if "character_to" in relation:
                relation["to"] = relation.pop("character_to")

    outline_title = outline.title or f"第{outline.chapter_number}章"
    outline_summary = outline.summary or "暂无摘要"
    writing_notes = request.writing_notes or "无额外写作指令"

    # 提取所有角色名
    all_characters = [c.get("name") for c in blueprint_dict.get("characters", []) if c.get("name")]

    # ========== 2. L2 Director: 生成章节导演脚本 ==========
    chapter_mission = await _generate_chapter_mission(
        llm_service=llm_service,
        prompt_service=prompt_service,
        blueprint_dict=blueprint_dict,
        previous_summary=previous_summary_text,
        previous_tail=previous_tail_excerpt,
        outline_title=outline_title,
        outline_summary=outline_summary,
        writing_notes=writing_notes,
        introduced_characters=[],  # 将在下一步填充
        all_characters=all_characters,
        user_id=current_user.id,
    )

    # 从导演脚本中提取允许登场的新角色
    allowed_new_characters = []
    if chapter_mission:
        allowed_new_characters = chapter_mission.get("allowed_new_characters", [])

    # ========== 3. 信息可见性过滤 ==========
    visibility_context = context_builder.build_visibility_context(
        blueprint=blueprint_dict,
        completed_summaries=completed_summaries,
        previous_tail=previous_tail_excerpt,
        outline_title=outline_title,
        outline_summary=outline_summary,
        writing_notes=writing_notes,
        allowed_new_characters=allowed_new_characters,
    )

    writer_blueprint = visibility_context["writer_blueprint"]
    forbidden_characters = visibility_context["forbidden_characters"]
    introduced_characters = visibility_context["introduced_characters"]

    logger.info(
        "项目 %s 第 %s 章信息可见性: 已登场=%s, 允许新登场=%s, 禁止=%s",
        project_id,
        request.chapter_number,
        len(introduced_characters),
        len(allowed_new_characters),
        len(forbidden_characters),
    )

    # ========== 4. 准备 RAG 上下文 ==========
    vector_store: Optional[VectorStoreService]
    if not settings.vector_store_enabled:
        vector_store = None
    else:
        try:
            vector_store = VectorStoreService()
        except RuntimeError as exc:
            logger.warning("向量库初始化失败，RAG 检索被禁用: %s", exc)
            vector_store = None
    context_service = ChapterContextService(llm_service=llm_service, vector_store=vector_store)

    query_parts = [outline_title, outline_summary]
    if request.writing_notes:
        query_parts.append(request.writing_notes)
    rag_query = "\n".join(part for part in query_parts if part)
    rag_context = await context_service.retrieve_for_generation(
        project_id=project_id,
        query_text=rag_query or outline.title or outline.summary or "",
        user_id=current_user.id,
    )
    rag_chunks_text = "\n\n".join(rag_context.chunk_texts()) if rag_context.chunks else "未检索到章节片段"
    rag_summaries_text = "\n".join(rag_context.summary_lines()) if rag_context.summaries else "未检索到章节摘要"

    # ========== 5. 构建写作提示词 ==========
    # 优先使用 writing_v2，fallback 到 writing
    writer_prompt = await prompt_service.get_prompt("writing_v2")
    if not writer_prompt:
        writer_prompt = await prompt_service.get_prompt("writing")
    if not writer_prompt:
        logger.error("未配置写作提示词，无法生成章节内容")
        raise HTTPException(status_code=500, detail="缺少写作提示词，请联系管理员配置")

    # 使用裁剪后的蓝图（移除了 full_synopsis 和未登场角色）
    blueprint_text = json.dumps(writer_blueprint, ensure_ascii=False, indent=2)
    
    # 构建导演脚本文本
    mission_text = json.dumps(chapter_mission, ensure_ascii=False, indent=2) if chapter_mission else "无导演脚本"
    
    # 构建禁止角色列表
    forbidden_text = json.dumps(forbidden_characters, ensure_ascii=False) if forbidden_characters else "无"

    # 构建衔接提示
    if previous_tail_excerpt and previous_tail_excerpt != "暂无（这是第一章）":
        continuity_hint = f"""**【核心红线：章节衔接】**
上一章结尾是：
{previous_tail_excerpt}

本章开头必须从上一章结尾的最后一句话/动作/对话直接延续，不得重新起笔。
- 如果上一章结尾是对话（如例子中的"为什么？"），本章开头必须接着这句对话，写对方的回答或反应
- 如果上一章结尾是动作，本章开头接着动作的后续或结果
- 如果上一章结尾是悬念，本章开头立即揭示或推进
- 绝对禁止用「疼痛」「黑暗」「他醒来」「这是XX的第一个感觉」等重置式开场
- 让读者感觉是同一个连续故事，没有时间跳跃或场景重置"""
    else:
        continuity_hint = "这是第一章，可以用感官冲击开场。"

    prompt_sections = [
        ("[世界蓝图](JSON，已裁剪)", blueprint_text),
        ("[上一章摘要]", previous_summary_text or "暂无（这是第一章）"),
        ("[章节衔接要求]", continuity_hint),
        ("[章节导演脚本](JSON)", mission_text),
        ("[检索到的剧情上下文](Markdown)", rag_chunks_text),
        ("[检索到的章节摘要](Markdown)", rag_summaries_text),
        ("[当前章节目标]", f"标题：{outline_title}\n摘要：{outline_summary}\n写作要求：{writing_notes}"),
        ("[禁止角色](本章不允许提及)", forbidden_text),
        ("[字数要求]", "本章节正文字数必须严格控制在 3000-4000 字之间。超过 4000 字或低于 3000 字均不符合要求。在心里将全章分为「开场(约800字)→发展(约1500字)→转折(约1000字)→钩子(约400字)」四段，每段写完后心算累计字数，到达 3500 字时立即进入钩子收尾，绝不继续展开新内容。注意：这只是心理规划，绝对不要在正文中写出「**【开场】**」「**【发展】**」等结构标记。"),
    ]
    prompt_input = "\n\n".join(f"{title}\n{content}" for title, content in prompt_sections if content)
    logger.debug("章节写作提示词长度: %s 字符", len(prompt_input))

    # ========== 6. L3 Writer: 生成正文 ==========
    async def _generate_single_version(idx: int, version_style_hint: Optional[str] = None) -> Dict:
        """生成单个版本，支持差异化风格提示"""
        try:
            # 如果有版本风格提示，添加到 prompt_input
            final_prompt_input = prompt_input
            if version_style_hint:
                final_prompt_input += f"\n\n[版本风格提示]\n{version_style_hint}"

            response = await llm_service.get_llm_response(
                system_prompt=writer_prompt,
                conversation_history=[{"role": "user", "content": final_prompt_input}],
                temperature=0.9,
                user_id=current_user.id,
                timeout=600.0,
                response_format=None,
                max_tokens=5500,  # 目标 3000-4000 字，中文约 1.5 字/token，5500 为硬限制（强制模型在 4000 字内收尾）
            )
            cleaned = remove_think_tags(response)
            normalized = unwrap_markdown_json(cleaned)
            
            # ========== 7. 护栏检查 ==========
            guardrail_result = guardrails.check(
                generated_text=normalized,
                forbidden_characters=forbidden_characters,
                allowed_new_characters=allowed_new_characters,
                pov=chapter_mission.get("pov") if chapter_mission else None,
            )

            final_content = normalized
            guardrail_metadata = {"passed": guardrail_result.passed, "violations": []}

            if not guardrail_result.passed:
                logger.warning(
                    "项目 %s 第 %s 章版本 %s 检测到 %s 个违规",
                    project_id,
                    request.chapter_number,
                    idx + 1,
                    len(guardrail_result.violations),
                )
                guardrail_metadata["violations"] = [
                    {"type": v.type, "severity": v.severity, "description": v.description}
                    for v in guardrail_result.violations
                ]

                # 尝试自动修复
                violations_text = guardrails.format_violations_for_rewrite(guardrail_result)
                final_content = await _rewrite_with_guardrails(
                    llm_service=llm_service,
                    prompt_service=prompt_service,
                    original_text=normalized,
                    chapter_mission=chapter_mission,
                    violations_text=violations_text,
                    user_id=current_user.id,
                )

            def _extract_text(value: object) -> Optional[str]:
                if not value:
                    return None
                if isinstance(value, str):
                    return value
                if isinstance(value, dict):
                    for key in ("content", "chapter_content", "chapter_text", "text", "body", "story"):
                        if value.get(key):
                            nested = _extract_text(value.get(key))
                            if nested:
                                return nested
                    return None
                if isinstance(value, list):
                    for item in value:
                        nested = _extract_text(item)
                        if nested:
                            return nested
                return None

            parsed_json = None
            extracted_text = None
            try:
                parsed_json = json.loads(final_content)
                extracted_text = _extract_text(parsed_json)
            except Exception:
                parsed_json = None

            return {
                "content": extracted_text or final_content,
                "parsed_json": parsed_json,
                "guardrail": guardrail_metadata,
                "chapter_mission": chapter_mission,
            }
        except HTTPException:
            raise
        except Exception as exc:
            logger.exception(
                "项目 %s 生成第 %s 章第 %s 个版本时发生异常: %s",
                project_id,
                request.chapter_number,
                idx + 1,
                exc,
            )
            raise HTTPException(
                status_code=500,
                detail=f"生成章节第 {idx + 1} 个版本时失败: {str(exc)[:200]}"
            )

    version_count = await _resolve_version_count(session)
    logger.info(
        "项目 %s 第 %s 章计划生成 %s 个版本",
        project_id,
        request.chapter_number,
        version_count,
    )

    # 版本差异化风格提示
    version_style_hints = [
        "情绪更细腻，节奏更慢，多写内心戏和感官描写",
        "冲突更强，节奏更快，多写动作和对话",
        "悬念更重，多埋伏笔，结尾钩子更强",
    ]

    raw_versions = []
    try:
        for idx in range(version_count):
            style_hint = version_style_hints[idx] if idx < len(version_style_hints) else None
            raw_versions.append(await _generate_single_version(idx, style_hint))
    except Exception as exc:
        logger.exception("项目 %s 生成第 %s 章时发生异常: %s", project_id, request.chapter_number, exc)
        chapter.status = "failed"
        await session.commit()
        if isinstance(exc, HTTPException):
            raise exc
        raise HTTPException(
            status_code=500,
            detail=f"生成章节失败: {str(exc)[:200]}"
        )

    contents: List[str] = []
    metadata: List[Dict] = []
    for variant in raw_versions:
        if isinstance(variant, dict):
            if "content" in variant and isinstance(variant["content"], str):
                contents.append(variant["content"])
            elif "chapter_content" in variant:
                contents.append(str(variant["chapter_content"]))
            else:
                contents.append(json.dumps(variant, ensure_ascii=False))
            metadata.append(variant)
        else:
            contents.append(str(variant))
            metadata.append({"raw": variant})

    # 字数验证与截断
    TARGET_MAX = 4000
    for i, content in enumerate(contents):
        word_count = len(content)
        if word_count > TARGET_MAX:
            # 在段落边界截断，避免截断到句子中间
            truncated = content[:TARGET_MAX]
            last_para = truncated.rfind("\n\n")
            last_newline = truncated.rfind("\n")
            cut_pos = last_para if last_para > TARGET_MAX * 0.85 else (last_newline if last_newline > TARGET_MAX * 0.85 else TARGET_MAX)
            contents[i] = content[:cut_pos].rstrip()
            logger.warning(
                "项目 %s 第 %s 章版本 %s 字数超出上限: %s 字，已截断至 %s 字",
                project_id,
                request.chapter_number,
                i + 1,
                word_count,
                len(contents[i]),
            )
        elif word_count < 3000:
            logger.warning(
                "项目 %s 第 %s 章版本 %s 字数不足: %s 字（目标: 3500-4000 字）",
                project_id,
                request.chapter_number,
                i + 1,
                word_count,
            )
        else:
            logger.info(
                "项目 %s 第 %s 章版本 %s 字数符合要求: %s 字",
                project_id,
                request.chapter_number,
                i + 1,
                word_count,
            )

    # ========== 8. AI Review: 自动评审多版本 ==========
    ai_review_result = None
    if len(contents) > 1:
        try:
            ai_review_service = AIReviewService(llm_service, prompt_service)
            ai_review_result = await ai_review_service.review_versions(
                versions=contents,
                chapter_mission=chapter_mission,
                user_id=current_user.id,
            )
            if ai_review_result:
                logger.info(
                    "项目 %s 第 %s 章 AI 评审完成: 推荐版本=%s",
                    project_id,
                    request.chapter_number,
                    ai_review_result.best_version_index,
                )
                # 将评审结果附加到 metadata（所有版本都显示完整内容）
                for i, m in enumerate(metadata):
                    m["ai_review"] = {
                        "is_best": i == ai_review_result.best_version_index,
                        "scores": ai_review_result.scores,
                        "evaluation": ai_review_result.overall_evaluation,
                        "flaws": ai_review_result.critical_flaws,
                        "suggestions": ai_review_result.refinement_suggestions,
                    }
        except Exception as exc:
            logger.warning("AI 评审失败，跳过: %s", exc)

    await novel_service.replace_chapter_versions(chapter, contents, metadata)
    logger.info(
        "项目 %s 第 %s 章生成完成，已写入 %s 个版本",
        project_id,
        request.chapter_number,
        len(contents),
    )
    return await _load_project_schema(novel_service, project_id, current_user.id)


@router.post("/novels/{project_id}/chapters/select", response_model=NovelProjectSchema)
async def select_chapter_version(
    project_id: str,
    request: SelectVersionRequest,
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> NovelProjectSchema:
    novel_service = NovelService(session)
    project = await novel_service.ensure_project_owner(project_id, current_user.id)
    chapter = await novel_service.get_or_create_chapter(project_id, request.chapter_number)

    # 使用 novel_service.select_chapter_version 确保排序一致
    # 该函数会按 created_at 排序并校验索引
    selected_version = await novel_service.select_chapter_version(chapter, request.version_index)
    
    # 校验内容是否为空
    if not selected_version.content or len(selected_version.content.strip()) == 0:
        # 回滚状态，不标记为 successful
        await session.rollback()
        raise HTTPException(status_code=400, detail="选中的版本内容为空，无法确认为最终版")

    # 查询章节大纲标题（Chapter 模型本身无 title 字段）
    outline_stmt = select(ChapterOutline).where(
        ChapterOutline.project_id == project_id,
        ChapterOutline.chapter_number == request.chapter_number,
    )
    outline_result = await session.execute(outline_stmt)
    outline = outline_result.scalar_one_or_none()
    chapter_title = outline.title if outline else f"第{request.chapter_number}章"

    # 异步触发向量化入库
    try:
        llm_service = LLMService(session)
        ingest_service = ChapterIngestionService(llm_service=llm_service)
        await ingest_service.ingest_chapter(
            project_id=project_id,
            chapter_number=request.chapter_number,
            title=chapter_title,
            content=selected_version.content,
            summary=chapter.real_summary or None,
            user_id=current_user.id,
        )
        logger.info(f"章节 {request.chapter_number} 向量化入库成功")
    except Exception as e:
        logger.error(f"章节 {request.chapter_number} 向量化入库失败: {e}")
        # 向量化失败不应阻止版本选择，仅记录错误

    return await _load_project_schema(novel_service, project_id, current_user.id)


@router.post("/novels/{project_id}/chapters/evaluate", response_model=NovelProjectSchema)
async def evaluate_chapter(
    project_id: str,
    request: EvaluateChapterRequest,
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> NovelProjectSchema:
    """评审章节所有版本 - 使用多版本对比评审"""
    novel_service = NovelService(session)
    prompt_service = PromptService(session)
    llm_service = LLMService(session)

    project = await novel_service.ensure_project_owner(project_id, current_user.id)

    # 获取该章节的所有版本
    stmt = (
        select(Chapter)
        .options(selectinload(Chapter.versions), selectinload(Chapter.selected_version))
        .where(
            Chapter.project_id == project_id,
            Chapter.chapter_number == request.chapter_number,
        )
    )
    result = await session.execute(stmt)
    chapter = result.scalars().first()

    if not chapter:
        chapter = await novel_service.get_or_create_chapter(project_id, request.chapter_number)

    if not chapter.versions:
        raise HTTPException(status_code=400, detail="该章节还没有生成任何版本，无法进行评审")

    # 获取所有版本（按创建时间排序）
    all_versions = sorted(chapter.versions, key=lambda v: v.created_at)
    versions_to_evaluate = [v for v in all_versions if v.content]

    if not versions_to_evaluate:
        raise HTTPException(status_code=400, detail="所有版本内容为空，无法进行评审")

    chapter.status = "evaluating"
    await session.commit()

    # 获取评审提示词
    eval_prompt = await prompt_service.get_prompt("evaluation")
    if not eval_prompt:
        logger.warning("未配置名为 'evaluation' 的评审提示词，将跳过 AI 评审")
        for version in versions_to_evaluate:
            await novel_service.add_chapter_evaluation(
                chapter=chapter,
                version=version,
                feedback="未配置评审提示词",
                decision="skipped"
            )
        return await _load_project_schema(novel_service, project_id, current_user.id)

    try:
        logger.info(
            "项目 %s 第 %s 章开始多版本对比评审，共 %s 个版本",
            project_id, request.chapter_number, len(versions_to_evaluate)
        )

        # 构建评审输入 JSON（evaluation.md 提示词期望的格式）
        project_schema = await novel_service._serialize_project(project)
        blueprint = project_schema.blueprint

        # 获取前序章节摘要
        completed_chapters = []
        if project.chapters:
            for ch in sorted(project.chapters, key=lambda c: c.chapter_number):
                if ch.chapter_number < request.chapter_number and ch.real_summary:
                    completed_chapters.append({
                        "chapter_number": ch.chapter_number,
                        "summary": ch.real_summary
                    })

        # 构建输入
        eval_input = {
            "novel_blueprint": {
                "title": blueprint.title if blueprint else "",
                "genre": blueprint.genre if blueprint else "",
                "style": blueprint.style if blueprint else "",
                "tone": blueprint.tone if blueprint else "",
                "world_setting": blueprint.world_setting if blueprint else {},
                "characters": blueprint.characters if blueprint else [],
                "relationships": [r.model_dump() for r in blueprint.relationships] if blueprint else [],
                "chapter_outline": [
                    {"chapter_number": o.chapter_number, "title": o.title, "summary": o.summary}
                    for o in blueprint.chapter_outline
                ] if blueprint and blueprint.chapter_outline else [],
            },
            "completed_chapters": completed_chapters,
            "content_to_evaluate": {
                "chapter_title": f"第{request.chapter_number}章",
                "versions": [v.content for v in versions_to_evaluate]
            }
        }

        # 调用 LLM 进行评审
        evaluation_raw = await llm_service.get_llm_response(
            system_prompt=eval_prompt,
            conversation_history=[{"role": "user", "content": json.dumps(eval_input, ensure_ascii=False, indent=2)}],
            temperature=0.3,
            user_id=current_user.id,
            timeout=180.0,
        )
        evaluation_text = remove_think_tags(evaluation_raw)
        evaluation_text = unwrap_markdown_json(evaluation_text)
        evaluation_text = sanitize_json_like_text(evaluation_text)

        if not evaluation_text or len(evaluation_text.strip()) == 0:
            raise ValueError("评审结果为空")

        # 解析评审结果以获取最佳版本索引
        try:
            evaluation_data = json.loads(evaluation_text)
            best_choice = evaluation_data.get("best_choice", 1)
            # best_choice 是 1-based 索引
            best_version_index = best_choice - 1 if isinstance(best_choice, int) else 0
        except json.JSONDecodeError:
            best_version_index = 0
            logger.warning("评审结果不是有效 JSON，默认选择第一个版本")

        # 为每个版本存储评审结果（同一个评审结果）
        for idx, version in enumerate(versions_to_evaluate):
            is_best = (idx == best_version_index)
            await novel_service.add_chapter_evaluation(
                chapter=chapter,
                version=version,
                feedback=evaluation_text,
                decision="best" if is_best else "reviewed",
            )

        chapter.status = "waiting_for_confirm"
        await session.commit()

        logger.info(
            "项目 %s 第 %s 章评审完成，最佳版本: %s",
            project_id, request.chapter_number, best_version_index + 1
        )

    except Exception as exc:
        logger.exception("项目 %s 第 %s 章评审失败: %s", project_id, request.chapter_number, exc)
        chapter.status = "evaluation_failed"
        await session.commit()

        # 为所有版本创建失败记录
        from app.models.novel import ChapterEvaluation
        for version in versions_to_evaluate:
            evaluation_record = ChapterEvaluation(
                chapter_id=chapter.id,
                version_id=version.id,
                decision="failed",
                feedback=f"评审失败: {str(exc)}",
                score=None
            )
            session.add(evaluation_record)
        await session.commit()

        raise HTTPException(status_code=500, detail=f"评审失败: {str(exc)}")

    return await _load_project_schema(novel_service, project_id, current_user.id)


@router.post("/novels/{project_id}/chapters/update-outline", response_model=NovelProjectSchema)
async def update_chapter_outline(
    project_id: str,
    request: UpdateChapterOutlineRequest,
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> NovelProjectSchema:
    novel_service = NovelService(session)
    await novel_service.ensure_project_owner(project_id, current_user.id)

    outline = await novel_service.get_outline(project_id, request.chapter_number)
    if not outline:
        raise HTTPException(status_code=404, detail="未找到对应章节大纲")

    outline.title = request.title
    outline.summary = request.summary
    await session.commit()

    # 如果提供了 AI 建议，将其提炼为规则并追加到提示词文件中
    if request.ai_message and request.ai_message.strip():
        try:
            prompt_service = PromptService(session)
            llm_service = LLMService(session)

            # 调用 LLM 将 AI 建议提炼为简洁的规则
            extract_prompt = f"""请将以下关于小说大纲生成的建议提炼为一条简洁、通用的规则。

要求：
1. 规则应该是通用的，适用于所有小说大纲生成场景
2. 规则应该简洁明了，不超过100字
3. 规则应该以"应该"或"必须"开头
4. 去除具体的章节号、角色名等特定信息

AI建议内容：
{request.ai_message.strip()}

请直接输出提炼后的规则，不要有任何前缀或解释。"""

            extracted_rule = await llm_service.generate(
                prompt=extract_prompt,
                system_prompt="你是一个规则提炼专家，擅长从具体建议中提取通用规则。",
                temperature=0.3,
                max_tokens=200
            )

            if extracted_rule and extracted_rule.strip():
                # 格式化为规则块
                rule_content = f"""

---

## 用户反馈规则（自动添加）

{extracted_rule.strip()}
"""
                # 追加到 outline_generation 提示词
                success = await prompt_service.append_to_prompt("outline_generation", rule_content)
                if success:
                    logger.info(f"已将 AI 建议提炼为规则并追加到 outline_generation 提示词")
                else:
                    logger.warning(f"追加规则到 outline_generation 提示词失败")
        except Exception as e:
            logger.error(f"处理 AI 建议时出错: {str(e)}")
            # 不影响主流程，继续返回

    return await _load_project_schema(novel_service, project_id, current_user.id)


@router.post("/novels/{project_id}/chapters/outline-converse", response_model=ChapterOutlineConverseResponse)
async def converse_chapter_outline(
    project_id: str,
    request: ChapterOutlineConverseRequest,
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> ChapterOutlineConverseResponse:
    """通过对话方式修改章节大纲"""
    novel_service = NovelService(session)
    llm_service = LLMService(session)

    project = await novel_service.ensure_project_owner(project_id, current_user.id)

    # 获取当前章节大纲
    outline = await novel_service.get_outline(project_id, request.chapter_number)
    if not outline:
        raise HTTPException(status_code=404, detail="未找到对应章节大纲")

    # 获取蓝图信息作为上下文
    project_schema = await novel_service._serialize_project(project)
    blueprint_context = ""
    if project_schema.blueprint:
        bp = project_schema.blueprint
        blueprint_context = f"""
故事标题: {bp.title or '未设定'}
故事概要: {bp.one_sentence_summary or '未设定'}
风格: {bp.style or '未设定'}
基调: {bp.tone or '未设定'}
"""
        if bp.chapter_outline:
            # 获取前后章节作为上下文
            prev_chapters = [
                f"第{ch.chapter_number}章 - {ch.title}: {ch.summary}"
                for ch in bp.chapter_outline
                if ch.chapter_number < request.chapter_number
            ][-3:]  # 最多显示前3章
            next_chapters = [
                f"第{ch.chapter_number}章 - {ch.title}: {ch.summary}"
                for ch in bp.chapter_outline
                if ch.chapter_number > request.chapter_number
            ][:3]  # 最多显示后3章

            if prev_chapters:
                blueprint_context += f"\n前文章节:\n" + "\n".join(prev_chapters)
            if next_chapters:
                blueprint_context += f"\n后续章节:\n" + "\n".join(next_chapters)

    # 构建对话消息
    current_outline = f"第{outline.chapter_number}章 - {outline.title}: {outline.summary}"

    system_prompt = f"""你是一个专业的小说创作助手。用户正在通过对话修改章节大纲。

当前小说蓝图信息:
{blueprint_context}

当前章节大纲:
{current_outline}

你的任务是:
1. 理解用户对章节大纲的修改需求
2. 根据故事连贯性和整体结构，给出专业建议
3. 如果用户的修改合理，生成修改后的大纲建议
4. 保持修改后的风格与整体故事一致

回复格式要求（JSON）:
{{
    "message": "你的回复内容，解释修改建议或询问更多细节",
    "proposed_outline": {{
        "title": "修改后的章节标题",
        "summary": "修改后的章节摘要"
    }}
}}

注意:
- 只有当用户明确提出修改意图时才生成 proposed_outline
- 如果用户只是在讨论或询问，proposed_outline 设为 null
- 确保修改后的标题简洁有力，摘要详细但不冗长
- 保持与前后章节的连贯性"""

    # 构建对话历史
    conversation_history = list(request.conversation_history)
    conversation_history.append({"role": "user", "content": request.user_message})

    try:
        # 调用 LLM
        content = await llm_service.get_llm_response(
            system_prompt=system_prompt,
            conversation_history=conversation_history,
            temperature=0.7,
            user_id=current_user.id,
            response_format="json_object"
        )

        # 尝试提取 JSON
        import re
        json_match = re.search(r'\{[\s\S]*\}', content)
        if json_match:
            try:
                data = json.loads(json_match.group())
                ai_message = data.get("message", content)
                proposed = data.get("proposed_outline")

                proposed_outline = None
                if proposed and isinstance(proposed, dict):
                    proposed_outline = ProposedOutline(
                        title=proposed.get("title", outline.title),
                        summary=proposed.get("summary", outline.summary)
                    )

                return ChapterOutlineConverseResponse(
                    ai_message=ai_message,
                    proposed_outline=proposed_outline
                )
            except json.JSONDecodeError:
                pass

        # 如果无法解析 JSON，直接返回内容
        return ChapterOutlineConverseResponse(
            ai_message=content,
            proposed_outline=None
        )

    except Exception as e:
        logger.error(f"章节大纲对话失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"对话处理失败: {str(e)}")


@router.post("/novels/{project_id}/chapters/delete", response_model=NovelProjectSchema)
async def delete_chapters(
    project_id: str,
    request: DeleteChapterRequest,
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> NovelProjectSchema:
    novel_service = NovelService(session)
    await novel_service.ensure_project_owner(project_id, current_user.id)

    await novel_service.delete_chapters(project_id, request.chapter_numbers)

    await session.commit()
    return await _load_project_schema(novel_service, project_id, current_user.id)


@router.post("/novels/{project_id}/chapters/outline", response_model=NovelProjectSchema)
async def generate_chapters_outline(
    project_id: str,
    request: GenerateOutlineRequest,
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> NovelProjectSchema:
    novel_service = NovelService(session)
    prompt_service = PromptService(session)
    llm_service = LLMService(session)

    project = await novel_service.ensure_project_owner(project_id, current_user.id)

    # 获取蓝图信息
    project_schema = await novel_service._serialize_project(project)
    blueprint_text = json.dumps(project_schema.blueprint.model_dump(), ensure_ascii=False, indent=2)

    # 获取已有的章节大纲
    existing_outlines = [
        f"第{o.chapter_number}章 - {o.title}: {o.summary}"
        for o in sorted(project.outlines, key=lambda x: x.chapter_number)
    ]
    existing_outlines_text = "\n".join(existing_outlines) if existing_outlines else "暂无"

    # 确定总章节数：优先使用请求参数，其次使用蓝图中的设置
    total_chapters = request.total_chapters
    if not total_chapters and project_schema.blueprint:
        total_chapters = project_schema.blueprint.total_chapters or 0
    if not total_chapters:
        # 如果都没有设置，根据现有大纲数量估算（至少是当前章节数的3倍）
        total_chapters = max(request.start_chapter * 3, 100)

    outline_prompt = await prompt_service.get_prompt("outline_generation")
    if not outline_prompt:
        raise HTTPException(status_code=500, detail="未配置大纲生成提示词")

    # 计算当前进度
    current_progress = request.start_chapter / total_chapters * 100 if total_chapters > 0 else 0

    # 构建用户提示部分（如果有）
    user_hint_section = ""
    if request.user_hint and request.user_hint.strip():
        user_hint_section = f"""
[用户提示]
{request.user_hint.strip()}

**请参考上述用户提示来规划后续章节的发展方向。**
"""

    prompt_input = f"""
[世界蓝图]
{blueprint_text}

[已有章节大纲]
{existing_outlines_text}
{user_hint_section}
[生成任务]
- 总章节数：{total_chapters} 章
- 当前位置：第 {request.start_chapter} 章（进度 {current_progress:.1f}%）
- 生成数量：{request.num_chapters} 章

请从第 {request.start_chapter} 章开始，续写接下来的 {request.num_chapters} 章的大纲。

**重要提示**：
1. 你必须根据总章节数 {total_chapters} 和当前进度 {current_progress:.1f}% 来控制故事节奏
2. 禁止在当前进度阶段让故事完结或进入结局阶段
3. 确保故事发展符合当前进度的阶段特征

要求返回 JSON 格式，包含一个 chapters 数组，每个元素包含 chapter_number, title, summary。
"""

    response = await llm_service.get_llm_response(
        system_prompt=outline_prompt,
        conversation_history=[{"role": "user", "content": prompt_input}],
        temperature=0.7,
        user_id=current_user.id,
    )

    cleaned = remove_think_tags(response)
    normalized = unwrap_markdown_json(cleaned)
    try:
        data = json.loads(normalized)

        # 处理章节大纲
        new_outlines = data.get("chapters", [])
        for item in new_outlines:
            await novel_service.update_or_create_outline(
                project_id,
                item["chapter_number"],
                item["title"],
                item["summary"]
            )

        # 处理新角色
        new_characters = data.get("new_characters", [])
        if new_characters and project_schema.blueprint:
            existing_names = {c.get("name") for c in project_schema.blueprint.characters}
            updated_characters = list(project_schema.blueprint.characters)
            for char in new_characters:
                if char.get("name") and char["name"] not in existing_names:
                    updated_characters.append({
                        "name": char.get("name"),
                        "description": char.get("description", ""),
                        "identity": char.get("identity", ""),
                        "personality": char.get("personality", ""),
                        "goals": char.get("goals", ""),
                        "abilities": char.get("abilities", ""),
                        "first_appear_chapter": char.get("first_appear_chapter")
                    })
                    existing_names.add(char["name"])
                    logger.info(f"新增角色: {char.get('name')}")

            # 更新蓝图中的角色列表
            await novel_service.update_blueprint_characters(project_id, updated_characters)

        # 处理新关系
        new_relationships = data.get("new_relationships", [])
        if new_relationships and project_schema.blueprint:
            updated_relationships = list(project_schema.blueprint.relationships)
            for rel in new_relationships:
                if rel.get("character_from") and rel.get("character_to"):
                    # 转换为蓝图格式
                    rel_data = {
                        "from": rel.get("character_from"),
                        "to": rel.get("character_to"),
                        "character_from": rel.get("character_from"),
                        "character_to": rel.get("character_to"),
                        "description": rel.get("description", ""),
                        "first_appear_chapter": rel.get("first_appear_chapter")
                    }
                    updated_relationships.append(rel_data)
                    logger.info(f"新增关系: {rel.get('character_from')} -> {rel.get('character_to')}")

            await novel_service.update_blueprint_relationships(project_id, updated_relationships)

        # 处理新地点
        new_locations = data.get("new_locations", [])
        if new_locations and project_schema.blueprint:
            existing_world = project_schema.blueprint.world_setting or {}
            existing_locations = existing_world.get("locations", [])
            existing_location_names = {loc.get("name") for loc in existing_locations}

            for loc in new_locations:
                if loc.get("name") and loc["name"] not in existing_location_names:
                    existing_locations.append({
                        "name": loc.get("name"),
                        "description": loc.get("description", ""),
                        "type": loc.get("type", ""),
                        "first_appear_chapter": loc.get("first_appear_chapter")
                    })
                    logger.info(f"新增地点: {loc.get('name')}")

            existing_world["locations"] = existing_locations
            await novel_service.update_blueprint_world_setting(project_id, existing_world)

        # 处理新势力
        new_factions = data.get("new_factions", [])
        if new_factions and project_schema.blueprint:
            existing_world = project_schema.blueprint.world_setting or {}
            existing_factions = existing_world.get("factions", [])
            existing_faction_names = {fac.get("name") for fac in existing_factions}

            for fac in new_factions:
                if fac.get("name") and fac["name"] not in existing_faction_names:
                    existing_factions.append({
                        "name": fac.get("name"),
                        "description": fac.get("description", ""),
                        "leader": fac.get("leader", ""),
                        "goals": fac.get("goals", ""),
                        "first_appear_chapter": fac.get("first_appear_chapter")
                    })
                    logger.info(f"新增势力: {fac.get('name')}")

            existing_world["factions"] = existing_factions
            await novel_service.update_blueprint_world_setting(project_id, existing_world)

        # 处理伏笔：从大纲中提取伏笔并添加到伏笔管理系统
        foreshadowing_service = ForeshadowingService(session)
        for item in new_outlines:
            chapter_number = item.get("chapter_number")
            foreshadowing_data = item.get("foreshadowing", {})
            plant_list = foreshadowing_data.get("plant", [])
            payoff_list = foreshadowing_data.get("payoff", [])

            # 获取或创建章节记录
            chapter = await novel_service.get_or_create_chapter(project_id, chapter_number)

            # 处理埋设的伏笔
            for plant_content in plant_list:
                if plant_content and isinstance(plant_content, str) and plant_content.strip():
                    try:
                        await foreshadowing_service.create_foreshadowing(
                            project_id=project_id,
                            chapter_id=chapter.id,
                            chapter_number=chapter_number,
                            content=plant_content.strip(),
                            foreshadowing_type="hint",  # 默认类型为 hint
                            is_manual=False,  # AI 生成的伏笔
                            ai_confidence=0.8,  # 默认置信度
                        )
                        logger.info(f"新增伏笔: project={project_id}, chapter={chapter_number}, content={plant_content[:50]}...")
                    except Exception as fe:
                        logger.warning(f"创建伏笔失败: {fe}")

            # 处理回收的伏笔
            for payoff_content in payoff_list:
                if payoff_content and isinstance(payoff_content, str) and payoff_content.strip():
                    try:
                        # 尝试匹配未回收的伏笔
                        unresolved_foreshadowings = await foreshadowing_service.get_unresolved_foreshadowings(
                            project_id, chapter_number
                        )
                        # 简单匹配：查找内容相似的伏笔
                        matched = None
                        for fs in unresolved_foreshadowings:
                            if payoff_content.strip() in fs.content or fs.content in payoff_content.strip():
                                matched = fs
                                break

                        if matched:
                            await foreshadowing_service.resolve_foreshadowing(
                                foreshadowing_id=matched.id,
                                resolved_chapter_id=chapter.id,
                                resolved_chapter_number=chapter_number,
                                resolution_text=payoff_content.strip(),
                                resolution_type="direct",
                            )
                            logger.info(f"伏笔回收: project={project_id}, chapter={chapter_number}, content={payoff_content[:50]}...")
                        else:
                            # 如果没有匹配到，记录日志但不创建新伏笔
                            logger.info(f"未找到匹配的伏笔进行回收: {payoff_content[:50]}...")
                    except Exception as fe:
                        logger.warning(f"伏笔回收失败: {fe}")

        await session.commit()
    except Exception as exc:
        logger.exception("生成大纲解析失败: %s", exc)
        raise HTTPException(status_code=500, detail=f"大纲生成失败: {str(exc)}")

    return await _load_project_schema(novel_service, project_id, current_user.id)


@router.post("/novels/{project_id}/chapters/outline/preview", response_model=OutlinePreviewResponse)
async def preview_chapters_outline(
    project_id: str,
    request: OutlinePreviewRequest,
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> OutlinePreviewResponse:
    """预览大纲生成 - 分两步：先生成新元素，再生成章节大纲"""
    novel_service = NovelService(session)
    prompt_service = PromptService(session)
    llm_service = LLMService(session)

    project = await novel_service.ensure_project_owner(project_id, current_user.id)

    # 获取蓝图信息
    project_schema = await novel_service._serialize_project(project)
    blueprint_text = json.dumps(project_schema.blueprint.model_dump(), ensure_ascii=False, indent=2) if project_schema.blueprint else "{}"

    # 获取已有的章节大纲
    existing_outlines = [
        f"第{o.chapter_number}章 - {o.title}: {o.summary}"
        for o in sorted(project.outlines, key=lambda x: x.chapter_number)
    ]
    existing_outlines_text = "\n".join(existing_outlines) if existing_outlines else "暂无"

    # 确定总章节数
    total_chapters = request.total_chapters
    if not total_chapters and project_schema.blueprint:
        total_chapters = project_schema.blueprint.total_chapters or 0
    if not total_chapters:
        total_chapters = max(request.start_chapter * 3, 100)

    # 计算当前进度和故事阶段
    current_progress = request.start_chapter / total_chapters * 100 if total_chapters > 0 else 0
    if current_progress <= 10:
        story_phase = "开篇"
    elif current_progress <= 25:
        story_phase = "发展初期"
    elif current_progress <= 50:
        story_phase = "发展中期"
    elif current_progress <= 75:
        story_phase = "高潮铺垫"
    elif current_progress <= 90:
        story_phase = "高潮"
    else:
        story_phase = "结局"

    # 构建用户提示部分
    user_hint_section = ""
    if request.user_hint and request.user_hint.strip():
        user_hint_section = f"""
[用户提示]
{request.user_hint.strip()}

**请参考上述用户提示来规划后续章节的发展方向。**
"""

    # ========== 第一步：生成新元素（角色、关系、地点、势力） ==========
    element_prompt = await prompt_service.get_prompt("element_generation")
    if not element_prompt:
        raise HTTPException(status_code=500, detail="未配置元素生成提示词")

    element_input = f"""
[世界蓝图]
{blueprint_text}

[已有章节大纲]
{existing_outlines_text}
{user_hint_section}
[生成上下文]
- 起始章节：第 {request.start_chapter} 章
- 生成章节数：{request.num_chapters} 章
- 故事进度：{story_phase}（{current_progress:.1f}%）
- 总章节数：{total_chapters} 章

请为接下来 {request.num_chapters} 章的内容设计新的角色、人物关系、地点和势力。
"""

    element_response = await llm_service.get_llm_response(
        system_prompt=element_prompt,
        conversation_history=[{"role": "user", "content": element_input}],
        temperature=0.8,  # 稍高的温度增加创意
        user_id=current_user.id,
    )

    element_cleaned = remove_think_tags(element_response)
    element_normalized = unwrap_markdown_json(element_cleaned)

    logger.debug(f"元素生成原始响应长度: {len(element_normalized)} 字符")

    # 解析新元素
    try:
        element_data = json.loads(element_normalized)
    except json.JSONDecodeError as exc:
        logger.exception("解析元素生成响应失败: %s", exc)
        element_data = {
            "new_characters": [],
            "new_relationships": [],
            "new_locations": [],
            "new_factions": []
        }

    new_characters = element_data.get("new_characters", [])
    new_relationships = element_data.get("new_relationships", [])
    new_locations = element_data.get("new_locations", [])
    new_factions = element_data.get("new_factions", [])

    logger.info(f"元素生成完成: {len(new_characters)} 个角色, {len(new_relationships)} 个关系, {len(new_locations)} 个地点, {len(new_factions)} 个势力")

    # ========== 第二步：生成章节大纲 ==========
    outline_prompt = await prompt_service.get_prompt("outline_generation")
    if not outline_prompt:
        raise HTTPException(status_code=500, detail="未配置大纲生成提示词")

    # 构建新元素的简化摘要（供大纲生成参考）
    new_elements_summary = {
        "new_characters": [
            {"name": c.get("name"), "identity": c.get("identity"), "first_appear_chapter": c.get("first_appear_chapter")}
            for c in new_characters
        ],
        "new_relationships": [
            {"character_from": r.get("character_from"), "character_to": r.get("character_to"), "description": r.get("description"), "first_appear_chapter": r.get("first_appear_chapter")}
            for r in new_relationships
        ],
        "new_locations": [
            {"name": l.get("name"), "type": l.get("type"), "first_appear_chapter": l.get("first_appear_chapter")}
            for l in new_locations
        ],
        "new_factions": [
            {"name": f.get("name"), "first_appear_chapter": f.get("first_appear_chapter")}
            for f in new_factions
        ]
    }
    new_elements_text = json.dumps(new_elements_summary, ensure_ascii=False, indent=2)

    outline_input = f"""
[世界蓝图]
{blueprint_text}

[已有章节大纲]
{existing_outlines_text}

[新生成的元素]
以下元素已经在前面为你设计好了，请在对应章节安排它们的登场：
{new_elements_text}
{user_hint_section}
[生成任务]
- 总章节数：{total_chapters} 章
- 当前位置：第 {request.start_chapter} 章（进度 {current_progress:.1f}%）
- 生成数量：{request.num_chapters} 章

请从第 {request.start_chapter} 章开始，续写接下来的 {request.num_chapters} 章的大纲。

**重要提示**：
1. 你必须根据总章节数 {total_chapters} 和当前进度 {current_progress:.1f}% 来控制故事节奏
2. 禁止在当前进度阶段让故事完结或进入结局阶段
3. 确保故事发展符合当前进度的阶段特征
4. 根据新元素的 first_appear_chapter，在对应章节安排它们的首次登场
"""

    outline_response = await llm_service.get_llm_response(
        system_prompt=outline_prompt,
        conversation_history=[{"role": "user", "content": outline_input}],
        temperature=0.7,
        user_id=current_user.id,
    )

    outline_cleaned = remove_think_tags(outline_response)
    outline_normalized = unwrap_markdown_json(outline_cleaned)
    outline_sanitized = sanitize_json_like_text(outline_normalized)

    logger.debug(f"大纲预览原始响应长度: {len(outline_sanitized)} 字符")

    try:
        outline_data = json.loads(outline_sanitized)

        # 构建预览响应
        chapters_data = outline_data.get("chapters", [])
        chapters_preview = []
        for item in chapters_data:
            chapters_preview.append({
                "chapter_number": item.get("chapter_number"),
                "title": item.get("title", ""),
                "summary": item.get("summary", ""),
                "narrative_phase": item.get("narrative_phase"),
                "story_progress": item.get("story_progress"),
                "foreshadowing": item.get("foreshadowing"),
                "emotion_hook": item.get("emotion_hook"),
            })

        # 提取伏笔信息
        foreshadowing_plants = []
        foreshadowing_payoffs = []
        for item in chapters_data:
            chapter_number = item.get("chapter_number")
            foreshadowing_data = item.get("foreshadowing", {})
            plant_list = foreshadowing_data.get("plant", [])
            payoff_list = foreshadowing_data.get("payoff", [])

            for plant_content in plant_list:
                if plant_content and isinstance(plant_content, str) and plant_content.strip():
                    foreshadowing_plants.append({
                        "chapter_number": chapter_number,
                        "content": plant_content.strip()
                    })

            for payoff_content in payoff_list:
                if payoff_content and isinstance(payoff_content, str) and payoff_content.strip():
                    foreshadowing_payoffs.append({
                        "chapter_number": chapter_number,
                        "content": payoff_content.strip()
                    })

        return OutlinePreviewResponse(
            chapters=chapters_preview,
            new_characters=new_characters,
            new_relationships=new_relationships,
            new_locations=new_locations,
            new_factions=new_factions,
            foreshadowing_plants=foreshadowing_plants,
            foreshadowing_payoffs=foreshadowing_payoffs,
            ai_message=f"已生成 {len(chapters_preview)} 章大纲预览，包含 {len(new_characters)} 个新角色、{len(new_relationships)} 个新关系、{len(new_locations)} 个新地点、{len(new_factions)} 个新势力、{len(foreshadowing_plants)} 个待埋设伏笔、{len(foreshadowing_payoffs)} 个待回收伏笔。"
        )

    except json.JSONDecodeError as exc:
        logger.exception("解析大纲预览失败: %s, 位置: line %s col %s", exc.msg, exc.lineno, exc.colno)
        # 记录出错的JSON片段
        error_context = outline_sanitized[max(0, exc.pos - 100):exc.pos + 100] if exc.pos else outline_sanitized[:200]
        logger.error(f"JSON解析出错附近的文本: ...{error_context}...")
        raise HTTPException(status_code=500, detail=f"AI返回的数据格式有误，请重试。错误: {exc.msg}")


@router.post("/novels/{project_id}/chapters/outline/confirm", response_model=NovelProjectSchema)
async def confirm_chapters_outline(
    project_id: str,
    request: OutlineConfirmRequest,
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> NovelProjectSchema:
    """确认大纲 - 用户确认后保存到数据库"""
    novel_service = NovelService(session)
    foreshadowing_service = ForeshadowingService(session)

    project = await novel_service.ensure_project_owner(project_id, current_user.id)
    project_schema = await novel_service._serialize_project(project)

    preview_data = request.preview_data

    try:
        # 处理章节大纲
        chapters_data = preview_data.get("chapters", [])
        for item in chapters_data:
            await novel_service.update_or_create_outline(
                project_id,
                item["chapter_number"],
                item.get("title", ""),
                item.get("summary", "")
            )

        # 处理新角色
        new_characters = preview_data.get("new_characters", [])
        if new_characters and project_schema.blueprint:
            existing_names = {c.get("name") for c in project_schema.blueprint.characters}
            updated_characters = list(project_schema.blueprint.characters)
            for char in new_characters:
                if char.get("name") and char["name"] not in existing_names:
                    updated_characters.append({
                        "name": char.get("name"),
                        "description": char.get("description", ""),
                        "identity": char.get("identity", ""),
                        "personality": char.get("personality", ""),
                        "goals": char.get("goals", ""),
                        "abilities": char.get("abilities", ""),
                        "first_appear_chapter": char.get("first_appear_chapter")
                    })
                    existing_names.add(char["name"])
                    logger.info(f"新增角色: {char.get('name')}")

            await novel_service.update_blueprint_characters(project_id, updated_characters)

        # 处理新关系
        new_relationships = preview_data.get("new_relationships", [])
        if new_relationships and project_schema.blueprint:
            updated_relationships = list(project_schema.blueprint.relationships)
            # 构建已有关系的唯一键集合 (character_from, character_to)
            # relationships 是 Pydantic Relationship 模型列表，使用属性访问
            existing_rel_keys = {
                (r.character_from, r.character_to)
                for r in updated_relationships
                if hasattr(r, 'character_from') and hasattr(r, 'character_to')
            }
            for rel in new_relationships:
                if rel.get("character_from") and rel.get("character_to"):
                    rel_key = (rel.get("character_from"), rel.get("character_to"))
                    if rel_key in existing_rel_keys:
                        logger.info(f"关系已存在，跳过: {rel.get('character_from')} -> {rel.get('character_to')}")
                        continue
                    rel_data = {
                        "from": rel.get("character_from"),
                        "to": rel.get("character_to"),
                        "character_from": rel.get("character_from"),
                        "character_to": rel.get("character_to"),
                        "description": rel.get("description", ""),
                        "first_appear_chapter": rel.get("first_appear_chapter")
                    }
                    updated_relationships.append(rel_data)
                    existing_rel_keys.add(rel_key)
                    logger.info(f"新增关系: {rel.get('character_from')} -> {rel.get('character_to')}")

            await novel_service.update_blueprint_relationships(project_id, updated_relationships)

        # 处理新地点和新势力 - 合并处理避免多次调用 update_blueprint_world_setting
        new_locations = preview_data.get("new_locations", [])
        new_factions = preview_data.get("new_factions", [])

        if (new_locations or new_factions) and project_schema.blueprint:
            existing_world = dict(project_schema.blueprint.world_setting or {})

            # 处理地点
            if new_locations:
                existing_locations = list(existing_world.get("locations", []))
                existing_location_names = {loc.get("name") for loc in existing_locations}

                for loc in new_locations:
                    if loc.get("name") and loc["name"] not in existing_location_names:
                        existing_locations.append({
                            "name": loc.get("name"),
                            "description": loc.get("description", ""),
                            "type": loc.get("type", ""),
                            "first_appear_chapter": loc.get("first_appear_chapter")
                        })
                        logger.info(f"新增地点: {loc.get('name')}")

                existing_world["locations"] = existing_locations

            # 处理势力
            if new_factions:
                existing_factions = list(existing_world.get("factions", []))
                existing_faction_names = {fac.get("name") for fac in existing_factions}

                for fac in new_factions:
                    if fac.get("name") and fac["name"] not in existing_faction_names:
                        existing_factions.append({
                            "name": fac.get("name"),
                            "description": fac.get("description", ""),
                            "leader": fac.get("leader", ""),
                            "goals": fac.get("goals", ""),
                            "first_appear_chapter": fac.get("first_appear_chapter")
                        })
                        logger.info(f"新增势力: {fac.get('name')}")

                existing_world["factions"] = existing_factions

            # 只调用一次更新
            await novel_service.update_blueprint_world_setting(project_id, existing_world)

        # 处理伏笔
        foreshadowing_plants = preview_data.get("foreshadowing_plants", [])
        foreshadowing_payoffs = preview_data.get("foreshadowing_payoffs", [])

        logger.info(f"伏笔数据: plants={len(foreshadowing_plants)}, payoffs={len(foreshadowing_payoffs)}")

        # 获取章节映射 - 使用 auto_commit=False 避免多次提交
        chapter_map = {}
        for item in chapters_data:
            chapter_number = item.get("chapter_number")
            chapter = await novel_service.get_or_create_chapter(project_id, chapter_number, auto_commit=False)
            chapter_map[chapter_number] = chapter

        # 获取已存在的伏笔内容，用于去重
        existing_foreshadowings, _ = await foreshadowing_service.get_foreshadowings(project_id, limit=1000)
        existing_fs_contents = {fs.content for fs in existing_foreshadowings}
        logger.info(f"已存在伏笔数量: {len(existing_foreshadowings)}")

        # 处理埋设的伏笔
        logger.info(f"开始处理伏笔埋设，共 {len(foreshadowing_plants)} 条，chapter_map 包含章节: {list(chapter_map.keys())}")
        for plant in foreshadowing_plants:
            chapter_number = plant.get("chapter_number")
            content = plant.get("content", "")
            logger.debug(f"处理伏笔: chapter={chapter_number}, content={content[:30] if content else 'empty'}...")

            if chapter_number not in chapter_map:
                logger.warning(f"伏笔章节 {chapter_number} 不在 chapter_map 中，跳过")
                continue
            if not content:
                logger.warning(f"伏笔内容为空，跳过: chapter={chapter_number}")
                continue

            # 检查伏笔是否已存在
            if content in existing_fs_contents:
                logger.info(f"伏笔已存在，跳过: chapter={chapter_number}, content={content[:50]}...")
                continue

            try:
                chapter = chapter_map[chapter_number]
                if not chapter.id:
                    logger.error(f"章节 {chapter_number} 的 ID 为 None，无法创建伏笔")
                    continue

                # 设置默认的预期回收章节和重要性
                # importance: major (长期), minor (中期), subtle (短期)
                # 根据内容长度简单判断重要性
                if len(content) > 100:
                    fs_importance = "major"
                    fs_target_offset = 15  # 长期伏笔，15章后回收
                elif len(content) > 50:
                    fs_importance = "minor"
                    fs_target_offset = 10  # 中期伏笔，10章后回收
                else:
                    fs_importance = "subtle"
                    fs_target_offset = 5   # 短期伏笔，5章后回收

                fs_target_reveal = chapter_number + fs_target_offset

                await foreshadowing_service.create_foreshadowing(
                    project_id=project_id,
                    chapter_id=chapter.id,
                    chapter_number=chapter_number,
                    content=content,
                    foreshadowing_type="hint",
                    is_manual=False,
                    ai_confidence=0.8,
                    target_reveal_chapter=fs_target_reveal,
                    importance=fs_importance,
                )
                existing_fs_contents.add(content)  # 添加到已存在集合，防止批量新增时重复
                logger.info(f"新增伏笔成功: project={project_id}, chapter={chapter_number}, content={content[:50]}...")
            except Exception as fe:
                logger.exception(f"创建伏笔失败: chapter={chapter_number}, error={fe}")

        # 处理回收的伏笔
        logger.info(f"开始处理伏笔回收，共 {len(foreshadowing_payoffs)} 条")
        for payoff in foreshadowing_payoffs:
            chapter_number = payoff.get("chapter_number")
            content = payoff.get("content", "")

            if chapter_number not in chapter_map:
                logger.warning(f"伏笔回收章节 {chapter_number} 不在 chapter_map 中，跳过")
                continue
            if not content:
                continue

            try:
                unresolved_foreshadowings = await foreshadowing_service.get_unresolved_foreshadowings(
                    project_id, chapter_number
                )
                matched = None
                for fs in unresolved_foreshadowings:
                    if content in fs.content or fs.content in content:
                        matched = fs
                        break

                if matched:
                    await foreshadowing_service.resolve_foreshadowing(
                        foreshadowing_id=matched.id,
                        resolved_chapter_id=chapter_map[chapter_number].id,
                        resolved_chapter_number=chapter_number,
                        resolution_text=content,
                        resolution_type="direct",
                    )
                    logger.info(f"伏笔回收成功: project={project_id}, chapter={chapter_number}, content={content[:50]}...")
                else:
                    logger.info(f"未找到匹配的伏笔进行回收: {content[:50]}...")
            except Exception as fe:
                logger.exception(f"伏笔回收失败: chapter={chapter_number}, error={fe}")

        await session.commit()

    except Exception as exc:
        logger.exception("确认大纲失败: %s", exc)
        raise HTTPException(status_code=500, detail=f"大纲确认失败: {str(exc)}")

    return await _load_project_schema(novel_service, project_id, current_user.id)


@router.post("/novels/{project_id}/chapters/edit", response_model=NovelProjectSchema)
async def edit_chapter_content(
    project_id: str,
    request: EditChapterRequest,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> NovelProjectSchema:
    novel_service = NovelService(session)
    
    await novel_service.ensure_project_owner(project_id, current_user.id)
    chapter = await novel_service.get_or_create_chapter(project_id, request.chapter_number)
    
    # 更新内容：优先更新选中版本，否则选最新版本或创建新版本
    target_version = chapter.selected_version
    if not target_version and chapter.versions:
        target_version = sorted(chapter.versions, key=lambda item: item.created_at)[-1]

    if target_version:
        target_version.content = request.content
        if not chapter.selected_version_id:
            chapter.selected_version_id = target_version.id
    else:
        target_version = ChapterVersion(
            chapter_id=chapter.id,
            content=request.content,
            version_label="manual_edit",
        )
        session.add(target_version)
        await session.flush()
        chapter.selected_version_id = target_version.id
    
    chapter.status = "successful"
    chapter.word_count = len(request.content or "")
    await session.commit()

    background_tasks.add_task(
        _refresh_edit_summary_and_ingest,
        project_id,
        request.chapter_number,
        request.content,
        current_user.id,
    )

    return await _load_project_schema(novel_service, project_id, current_user.id)


@router.post("/novels/{project_id}/chapters/edit-fast", response_model=ChapterSchema)
async def edit_chapter_content_fast(
    project_id: str,
    request: EditChapterRequest,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> ChapterSchema:
    novel_service = NovelService(session)

    await novel_service.ensure_project_owner(project_id, current_user.id)
    chapter = await novel_service.get_or_create_chapter(project_id, request.chapter_number)

    target_version = chapter.selected_version
    if not target_version and chapter.versions:
        target_version = sorted(chapter.versions, key=lambda item: item.created_at)[-1]

    if target_version:
        target_version.content = request.content
        if not chapter.selected_version_id:
            chapter.selected_version_id = target_version.id
    else:
        target_version = ChapterVersion(
            chapter_id=chapter.id,
            content=request.content,
            version_label="manual_edit",
        )
        session.add(target_version)
        await session.flush()
        chapter.selected_version_id = target_version.id

    chapter.status = "successful"
    chapter.word_count = len(request.content or "")
    await session.commit()

    background_tasks.add_task(
        _refresh_edit_summary_and_ingest,
        project_id,
        request.chapter_number,
        request.content,
        current_user.id,
    )

    stmt = (
        select(Chapter)
        .options(
            selectinload(Chapter.versions),
            selectinload(Chapter.evaluations),
            selectinload(Chapter.selected_version),
        )
        .where(
            Chapter.project_id == project_id,
            Chapter.chapter_number == request.chapter_number,
        )
    )
    result = await session.execute(stmt)
    chapter = result.scalars().first()
    if not chapter:
        raise HTTPException(status_code=404, detail="章节不存在")

    outline_stmt = select(ChapterOutline).where(
        ChapterOutline.project_id == project_id,
        ChapterOutline.chapter_number == request.chapter_number,
    )
    outline_result = await session.execute(outline_stmt)
    outline = outline_result.scalars().first()

    title = outline.title if outline else f"第{request.chapter_number}章"
    summary = outline.summary if outline else ""
    real_summary = chapter.real_summary
    content = chapter.selected_version.content if chapter.selected_version else None
    versions = (
        [v.content for v in sorted(chapter.versions, key=lambda item: item.created_at)]
        if chapter.versions
        else None
    )
    evaluation_text = None
    if chapter.evaluations:
        latest = sorted(chapter.evaluations, key=lambda item: item.created_at)[-1]
        evaluation_text = latest.feedback or latest.decision
    status_value = chapter.status or ChapterGenerationStatus.NOT_GENERATED.value

    return ChapterSchema(
        chapter_number=request.chapter_number,
        title=title,
        summary=summary,
        real_summary=real_summary,
        content=content,
        versions=versions,
        evaluation=evaluation_text,
        generation_status=ChapterGenerationStatus(status_value),
        word_count=chapter.word_count or 0,
    )
