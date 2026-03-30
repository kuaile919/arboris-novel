# AIMETA P=优化器API_内容优化建议|R=内容优化_建议生成|NR=不含内容修改|E=route:POST_/api/optimizer/*|X=http|A=优化建议|D=fastapi|S=net|RD=./README.ai
"""
章节内容分层优化API
支持对话、环境描写、心理活动、节奏韵律四个维度的深度优化
"""
import asyncio
import json
import logging
import re
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select as sa_select
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.config import settings
from ...core.dependencies import get_current_user
from ...db.session import AsyncSessionLocal, get_session
from ...models.chapter_optimization_task import ChapterOptimizationTask
from ...models.novel import Chapter, ChapterOutline
from ...schemas.user import UserInDB
from ...services.chapter_ingest_service import ChapterIngestionService
from ...services.llm_service import LLMService
from ...services.novel_service import NovelService
from ...services.prompt_service import PromptService
from ...utils.json_utils import remove_think_tags, unwrap_markdown_json

router = APIRouter(prefix="/api/optimizer", tags=["Optimizer"])
logger = logging.getLogger(__name__)

# 写作风格库文件写入锁，防止并发覆盖
_style_file_lock = asyncio.Lock()


class OptimizeRequest(BaseModel):
    """优化请求"""
    project_id: str = Field(..., description="项目ID")
    chapter_number: int = Field(..., description="章节编号")
    dimension: str = Field(..., description="优化维度: dialogue/environment/psychology/rhythm")
    additional_notes: Optional[str] = Field(default=None, description="额外优化指令")


class OptimizeResponse(BaseModel):
    """优化响应"""
    optimized_content: str = Field(..., description="优化后的内容")
    optimization_notes: str = Field(..., description="优化说明")
    dimension: str = Field(..., description="优化维度")


class SummaryResponse(BaseModel):
    """摘要响应"""
    summary: Optional[str] = Field(None, description="章节摘要")
    has_summary: bool = Field(..., description="是否有摘要")


class UpdateSummaryRequest(BaseModel):
    """更新摘要请求"""
    project_id: str = Field(..., description="项目ID")
    chapter_number: int = Field(..., description="章节编号")
    summary: str = Field(..., description="新的摘要内容")


class AppendStyleRequest(BaseModel):
    """追加写作风格请求"""
    dimension: str = Field(..., description="优化维度")
    additional_notes: str = Field(..., description="用户的额外优化指令")
    optimization_notes: str = Field(..., description="AI返回的优化说明")


# 优化维度到提示词的映射
class StartOptimizeResponse(BaseModel):
    task_id: str
    status: str
    message: str


class OptimizeTaskStatusResponse(BaseModel):
    task_id: str
    status: str
    dimension: str
    project_id: str
    chapter_number: int
    original_content: Optional[str] = None
    optimized_content: Optional[str] = None
    optimization_notes: Optional[str] = None
    error_message: Optional[str] = None


DIMENSION_PROMPT_MAP = {
    "dialogue": "optimize_dialogue",
    "environment": "optimize_environment",
    "psychology": "optimize_psychology",
    "logic": "optimize_logic",
    "rhythm": "optimize_rhythm"
}

# 默认的节奏优化提示词（如果数据库中没有）
DEFAULT_RHYTHM_PROMPT = """# 节奏韵律优化专家

你是一位专注于小说节奏和韵律的编辑大师。你的任务是优化文章的节奏感，让阅读体验更加流畅和沉浸。

## 优化原则

### 1. 句子长度变化
- 长短句交替，像呼吸一样自然
- 紧张时用短句，舒缓时用长句
- 避免连续多个相同长度的句子

### 2. 段落节奏
- 重要情节放慢，细致描写
- 过渡情节加快，简洁带过
- 高潮部分可以用单句成段

### 3. 标点符号
- 善用省略号表示思绪飘散
- 用破折号表示突然转念
- 感叹号要克制使用

### 4. 韵律感
- 注意句尾的音节变化
- 避免重复的句式结构
- 适当使用排比增强气势

## 输入格式
```json
{
  "original_content": "需要优化的章节内容",
  "additional_notes": "额外优化指令"
}
```

## 输出格式
```json
{
  "optimized_content": "优化后的完整章节内容",
  "optimization_notes": "优化说明"
}
```
"""


@router.post("/optimize", response_model=OptimizeResponse)
async def optimize_chapter(
    request: OptimizeRequest,
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> OptimizeResponse:
    """
    对章节内容进行分层优化
    """
    novel_service = NovelService(session)
    prompt_service = PromptService(session)
    llm_service = LLMService(session)

    # 验证项目所有权
    project = await novel_service.ensure_project_owner(request.project_id, current_user.id)

    # 获取章节内容
    chapter = next(
        (ch for ch in project.chapters if ch.chapter_number == request.chapter_number),
        None
    )
    if not chapter:
        raise HTTPException(status_code=404, detail="章节不存在")

    if not chapter.selected_version or not chapter.selected_version.content:
        raise HTTPException(status_code=400, detail="章节尚未生成内容")

    original_content = chapter.selected_version.content

    # 验证优化维度
    if request.dimension not in DIMENSION_PROMPT_MAP:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的优化维度: {request.dimension}，支持的维度: {list(DIMENSION_PROMPT_MAP.keys())}"
        )

    # 获取对应的优化提示词
    prompt_name = DIMENSION_PROMPT_MAP[request.dimension]
    optimizer_prompt = await prompt_service.get_prompt(prompt_name)

    # 如果没有找到提示词，使用默认提示词（仅对rhythm维度）
    if not optimizer_prompt:
        if request.dimension == "rhythm":
            optimizer_prompt = DEFAULT_RHYTHM_PROMPT
        else:
            raise HTTPException(
                status_code=500,
                detail=f"缺少{request.dimension}优化提示词，请联系管理员配置 '{prompt_name}' 提示词"
            )

    # 获取角色DNA信息（用于心理活动优化）
    character_dna = {}
    if request.dimension == "psychology":
        project_schema = await novel_service._serialize_project(project)
        for char in project_schema.blueprint.characters:
            if "extra" in char and "dna_profile" in char.get("extra", {}):
                character_dna[char.get("name", "")] = char["extra"]["dna_profile"]

    # 构建优化请求
    content_char_count = len(original_content)
    optimize_input = {
        "original_content": original_content,
        "additional_notes": request.additional_notes or "无额外指令",
        "length_constraint": f"优化后内容字数应与原文相近（原文约 {content_char_count} 字），不要大幅扩写，保持在原文字数的 90%~110% 范围内"
    }

    # 如果是心理活动优化，添加角色DNA信息
    if character_dna:
        optimize_input["character_dna"] = character_dna

    logger.info(
        "用户 %s 开始优化项目 %s 第 %s 章，维度: %s",
        current_user.id,
        request.project_id,
        request.chapter_number,
        request.dimension
    )

    # 根据原始内容长度动态计算 max_tokens，避免截断
    # 中文约 1~1.5 字/token，加上 JSON 结构和优化说明的额外开销
    estimated_output_tokens = int(content_char_count / 1.2) + 2000
    max_tokens = max(8000, estimated_output_tokens)

    # 调用LLM进行优化
    try:
        response = await llm_service.get_llm_response(
            system_prompt=optimizer_prompt,
            conversation_history=[{
                "role": "user",
                "content": json.dumps(optimize_input, ensure_ascii=False)
            }],
            temperature=0.7,
            user_id=current_user.id,
            timeout=600.0,
            max_tokens=max_tokens,
        )

        cleaned = remove_think_tags(response)
        normalized = unwrap_markdown_json(cleaned)

        try:
            result = json.loads(normalized)

            # 检查是否存在嵌套的 JSON 字符串（LLM 可能返回了包含 JSON 字符串的 JSON）
            if isinstance(result.get("optimized_content"), str):
                content = result["optimized_content"].strip()
                # 如果 optimized_content 本身是一个 JSON 字符串，尝试解析它
                if content.startswith("{") or content.startswith("```"):
                    try:
                        nested_normalized = unwrap_markdown_json(content)
                        nested_result = json.loads(nested_normalized)
                        if "optimized_content" in nested_result:
                            result = nested_result
                    except (json.JSONDecodeError, ValueError):
                        pass  # 不是嵌套 JSON，保持原样

            optimized_content = result.get("optimized_content", cleaned)
            optimization_notes = result.get("optimization_notes", "优化完成")
        except json.JSONDecodeError:
            # 如果无法解析JSON，将整个响应作为优化后的内容
            optimized_content = cleaned
            optimization_notes = "优化完成（响应格式非标准JSON）"

        logger.info(
            "项目 %s 第 %s 章 %s 优化完成",
            request.project_id,
            request.chapter_number,
            request.dimension
        )

        return OptimizeResponse(
            optimized_content=optimized_content,
            optimization_notes=optimization_notes,
            dimension=request.dimension
        )

    except Exception as exc:
        logger.exception(
            "项目 %s 第 %s 章优化失败: %s",
            request.project_id,
            request.chapter_number,
            exc
        )
        raise HTTPException(
            status_code=500,
            detail=f"优化过程中发生错误: {str(exc)[:200]}"
        )


async def _run_chapter_optimization_async(
    request: OptimizeRequest,
    *,
    session: AsyncSession,
    user_id: int,
) -> tuple[str, str, str]:
    """
    后台任务版优化逻辑，返回(原文, 优化后)和优化说明。
    """
    novel_service = NovelService(session)
    prompt_service = PromptService(session)
    llm_service = LLMService(session)

    project = await novel_service.ensure_project_owner(request.project_id, user_id)
    chapter = next((ch for ch in project.chapters if ch.chapter_number == request.chapter_number), None)
    if not chapter:
        raise HTTPException(status_code=404, detail="章节不存在")
    if not chapter.selected_version or not chapter.selected_version.content:
        raise HTTPException(status_code=400, detail="章节尚未生成内容")

    original_content = chapter.selected_version.content

    if request.dimension not in DIMENSION_PROMPT_MAP:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的优化维度: {request.dimension}，支持的维度: {list(DIMENSION_PROMPT_MAP.keys())}",
        )

    prompt_name = DIMENSION_PROMPT_MAP[request.dimension]
    optimizer_prompt = await prompt_service.get_prompt(prompt_name)
    if not optimizer_prompt:
        if request.dimension == "rhythm":
            optimizer_prompt = DEFAULT_RHYTHM_PROMPT
        else:
            raise HTTPException(status_code=500, detail=f"缺少{request.dimension}优化提示词，请联系管理员配置 '{prompt_name}' 提示词")

    character_dna = {}
    if request.dimension == "psychology":
        project_schema = await novel_service._serialize_project(project)
        for char in project_schema.blueprint.characters:
            if "extra" in char and "dna_profile" in char.get("extra", {}):
                character_dna[char.get("name", "")] = char["extra"]["dna_profile"]

    content_char_count = len(original_content)
    optimize_input = {
        "original_content": original_content,
        "additional_notes": request.additional_notes or "无额外指令",
        "length_constraint": f"优化后内容字数应与原文相近（原文约{content_char_count}字），不要大幅扩写，保持在原文字数的 90%~110% 范围",
    }
    if character_dna:
        optimize_input["character_dna"] = character_dna

    estimated_output_tokens = int(content_char_count / 1.2) + 2000
    max_tokens = max(8000, estimated_output_tokens)

    response = await llm_service.get_llm_response(
        system_prompt=optimizer_prompt,
        conversation_history=[{"role": "user", "content": json.dumps(optimize_input, ensure_ascii=False)}],
        temperature=0.7,
        user_id=user_id,
        timeout=600.0,
        max_tokens=max_tokens,
    )

    cleaned = remove_think_tags(response)
    normalized = unwrap_markdown_json(cleaned)
    try:
        result = json.loads(normalized)
        if isinstance(result.get("optimized_content"), str):
            content = result["optimized_content"].strip()
            if content.startswith("{") or content.startswith("```"):
                try:
                    nested_normalized = unwrap_markdown_json(content)
                    nested_result = json.loads(nested_normalized)
                    if "optimized_content" in nested_result:
                        result = nested_result
                except (json.JSONDecodeError, ValueError):
                    pass

        optimized_content = result.get("optimized_content", cleaned)
        optimization_notes = result.get("optimization_notes", "优化完成")
    except json.JSONDecodeError:
        optimized_content = cleaned
        optimization_notes = "优化完成（响应格式非标准JSON）"

    return original_content, optimized_content, optimization_notes


async def _execute_optimize_task(task_id: str) -> None:
    async with AsyncSessionLocal() as session:
        task = await session.get(ChapterOptimizationTask, task_id)
        if not task:
            return

        try:
            task.status = "running"
            await session.commit()

            req = OptimizeRequest(
                project_id=task.project_id,
                chapter_number=task.chapter_number,
                dimension=task.dimension,
                additional_notes=task.additional_notes,
            )
            original_content, optimized_content, optimization_notes = await _run_chapter_optimization_async(
                req,
                session=session,
                user_id=task.user_id,
            )

            task.status = "completed"
            task.original_content = original_content
            task.optimized_content = optimized_content
            task.optimization_notes = optimization_notes
            task.error_message = None
            task.completed_at = datetime.now(timezone.utc)
            await session.commit()
        except Exception as exc:
            task.status = "failed"
            task.error_message = str(exc)[:500]
            task.completed_at = datetime.now(timezone.utc)
            await session.commit()
            logger.exception("优化后台任务失败: task_id=%s error=%s", task_id, exc)


@router.post("/optimize-async", response_model=StartOptimizeResponse)
async def optimize_chapter_async(
    request: OptimizeRequest,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> StartOptimizeResponse:
    task = ChapterOptimizationTask(
        project_id=request.project_id,
        chapter_number=request.chapter_number,
        user_id=current_user.id,
        dimension=request.dimension,
        additional_notes=request.additional_notes,
        status="pending",
    )
    session.add(task)
    await session.commit()
    await session.refresh(task)

    background_tasks.add_task(_execute_optimize_task, task.id)
    return StartOptimizeResponse(task_id=task.id, status=task.status, message="优化任务已启动")


@router.get("/optimize-task/{task_id}", response_model=OptimizeTaskStatusResponse)
async def get_optimize_task_status(
    task_id: str,
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> OptimizeTaskStatusResponse:
    task = await session.get(ChapterOptimizationTask, task_id)
    if not task or task.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="优化任务不存在")

    return OptimizeTaskStatusResponse(
        task_id=task.id,
        status=task.status,
        dimension=task.dimension,
        project_id=task.project_id,
        chapter_number=task.chapter_number,
        original_content=task.original_content,
        optimized_content=task.optimized_content,
        optimization_notes=task.optimization_notes,
        error_message=task.error_message,
    )


@router.get("/latest-optimization-result", response_model=OptimizeTaskStatusResponse)
async def get_latest_optimization_result(
    project_id: str,
    chapter_number: int,
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> OptimizeTaskStatusResponse:
    stmt = (
        sa_select(ChapterOptimizationTask)
        .where(
            ChapterOptimizationTask.project_id == project_id,
            ChapterOptimizationTask.chapter_number == chapter_number,
            ChapterOptimizationTask.user_id == current_user.id,
        )
        .order_by(ChapterOptimizationTask.created_at.desc())
    )
    result = await session.execute(stmt)
    task = result.scalars().first()
    if not task:
        raise HTTPException(status_code=404, detail="暂无优化结果")

    return OptimizeTaskStatusResponse(
        task_id=task.id,
        status=task.status,
        dimension=task.dimension,
        project_id=task.project_id,
        chapter_number=task.chapter_number,
        original_content=task.original_content,
        optimized_content=task.optimized_content,
        optimization_notes=task.optimization_notes,
        error_message=task.error_message,
    )


async def _ingest_optimized_chapter(
    project_id: str,
    chapter_number: int,
    title: str,
    content: str,
    user_id: int,
    force_regenerate_summary: bool = False,
) -> None:
    """应用优化后触发向量库重新入库（后台任务）"""
    if not settings.vector_store_enabled:
        return
    async with AsyncSessionLocal() as session:
        llm_service = LLMService(session)
        try:
            # 获取现有摘要，没有则用 LLM 生成
            chapter_stmt = sa_select(Chapter).where(
                Chapter.project_id == project_id,
                Chapter.chapter_number == chapter_number,
            )
            chapter_result = await session.execute(chapter_stmt)
            chapter = chapter_result.scalars().first()

            summary_text = chapter.real_summary if chapter else None
            if force_regenerate_summary or not summary_text:
                try:
                    raw = await llm_service.get_summary(content, temperature=0.15, user_id=user_id)
                    summary_text = remove_think_tags(raw) if raw else None
                    if summary_text and chapter:
                        chapter.real_summary = summary_text
                        await session.commit()
                except Exception as exc:
                    logger.warning("章节 %s 优化后生成摘要失败: %s", chapter_number, exc)

            ingest_service = ChapterIngestionService(llm_service=llm_service)
            await ingest_service.ingest_chapter(
                project_id=project_id,
                chapter_number=chapter_number,
                title=title,
                content=content,
                summary=summary_text,
                user_id=user_id,
            )
            logger.info("章节 %s 优化后向量化入库成功", chapter_number)
        except Exception as exc:
            logger.error("章节 %s 优化后向量化入库失败: %s", chapter_number, exc)


async def _update_summary_vector(
    project_id: str,
    chapter_number: int,
    title: str,
    summary: str,
    user_id: int,
) -> None:
    """更新摘要向量（后台任务）"""
    if not settings.vector_store_enabled:
        return
    async with AsyncSessionLocal() as session:
        llm_service = LLMService(session)
        try:
            # 生成摘要的嵌入向量
            cleaned_summary = summary.strip()
            if not cleaned_summary:
                logger.warning("摘要为空，跳过向量更新: project=%s chapter=%s", project_id, chapter_number)
                return

            summary_embedding = await llm_service.get_embedding(
                cleaned_summary,
                user_id=user_id,
            )
            if not summary_embedding:
                logger.warning("生成摘要向量失败: project=%s chapter=%s", project_id, chapter_number)
                return

            # 更新向量库中的摘要
            from ...services.vector_store_service import VectorStoreService
            vector_store = VectorStoreService()
            summary_id = f"{project_id}:{chapter_number}:summary"
            await vector_store.upsert_summaries(
                records=[
                    {
                        "id": summary_id,
                        "project_id": project_id,
                        "chapter_number": chapter_number,
                        "title": title,
                        "summary": cleaned_summary,
                        "embedding": summary_embedding,
                    }
                ]
            )
            logger.info("摘要向量更新成功: project=%s chapter=%s", project_id, chapter_number)
        except Exception as exc:
            logger.error("摘要向量更新失败: project=%s chapter=%s error=%s", project_id, chapter_number, exc)


@router.post("/apply-optimization")
async def apply_optimization(
    project_id: str,
    chapter_number: int,
    optimized_content: str,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
):
    """
    应用优化后的内容到章节
    """
    novel_service = NovelService(session)

    # 验证项目所有权
    project = await novel_service.ensure_project_owner(project_id, current_user.id)

    # 获取章节
    chapter = next(
        (ch for ch in project.chapters if ch.chapter_number == chapter_number),
        None
    )
    if not chapter:
        raise HTTPException(status_code=404, detail="章节不存在")

    if not chapter.selected_version:
        raise HTTPException(status_code=400, detail="章节尚未选择版本")

    # 更新内容
    chapter.selected_version.content = optimized_content
    await session.commit()

    # 获取章节标题用于向量化
    outline_stmt = sa_select(ChapterOutline).where(
        ChapterOutline.project_id == project_id,
        ChapterOutline.chapter_number == chapter_number,
    )
    outline_result = await session.execute(outline_stmt)
    outline = outline_result.scalars().first()
    title = outline.title if outline and outline.title else f"第{chapter_number}章"

    background_tasks.add_task(
        _ingest_optimized_chapter,
        project_id,
        chapter_number,
        title,
        optimized_content,
        current_user.id,
    )

    logger.info(
        "用户 %s 应用了项目 %s 第 %s 章的优化内容",
        current_user.id,
        project_id,
        chapter_number
    )

    return {"status": "success", "message": "优化内容已应用"}


@router.get("/summary/{project_id}/{chapter_number}", response_model=SummaryResponse)
async def get_chapter_summary(
    project_id: str,
    chapter_number: int,
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> SummaryResponse:
    """
    获取章节摘要
    """
    novel_service = NovelService(session)

    # 验证项目所有权
    project = await novel_service.ensure_project_owner(project_id, current_user.id)

    # 获取章节
    chapter = next(
        (ch for ch in project.chapters if ch.chapter_number == chapter_number),
        None
    )
    if not chapter:
        raise HTTPException(status_code=404, detail="章节不存在")

    return SummaryResponse(
        summary=chapter.real_summary,
        has_summary=bool(chapter.real_summary)
    )


@router.post("/generate-summary")
async def generate_chapter_summary(
    project_id: str,
    chapter_number: int,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
):
    """
    立即生成章节摘要并入向量库
    """
    novel_service = NovelService(session)

    # 验证项目所有权
    project = await novel_service.ensure_project_owner(project_id, current_user.id)

    # 获取章节
    chapter = next(
        (ch for ch in project.chapters if ch.chapter_number == chapter_number),
        None
    )
    if not chapter:
        raise HTTPException(status_code=404, detail="章节不存在")

    if not chapter.selected_version or not chapter.selected_version.content:
        raise HTTPException(status_code=400, detail="章节尚未生成内容")

    # 获取章节标题
    outline_stmt = sa_select(ChapterOutline).where(
        ChapterOutline.project_id == project_id,
        ChapterOutline.chapter_number == chapter_number,
    )
    outline_result = await session.execute(outline_stmt)
    outline = outline_result.scalars().first()
    title = outline.title if outline and outline.title else f"第{chapter_number}章"

    # 后台任务生成摘要并入库
    background_tasks.add_task(
        _ingest_optimized_chapter,
        project_id,
        chapter_number,
        title,
        chapter.selected_version.content,
        current_user.id,
        True,
    )

    logger.info(
        "用户 %s 触发项目 %s 第 %s 章的摘要生成",
        current_user.id,
        project_id,
        chapter_number
    )

    return {"status": "success", "message": "摘要生成任务已启动，请稍后刷新查看"}


@router.put("/summary")
async def update_chapter_summary(
    request: UpdateSummaryRequest,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
):
    """
    更新章节摘要（同时更新向量库）
    """
    novel_service = NovelService(session)

    # 验证项目所有权
    project = await novel_service.ensure_project_owner(request.project_id, current_user.id)

    # 获取章节
    chapter = next(
        (ch for ch in project.chapters if ch.chapter_number == request.chapter_number),
        None
    )
    if not chapter:
        raise HTTPException(status_code=404, detail="章节不存在")

    # 获取章节标题
    outline_stmt = sa_select(ChapterOutline).where(
        ChapterOutline.project_id == request.project_id,
        ChapterOutline.chapter_number == request.chapter_number,
    )
    outline_result = await session.execute(outline_stmt)
    outline = outline_result.scalars().first()
    title = outline.title if outline and outline.title else f"第{request.chapter_number}章"

    # 更新摘要
    chapter.real_summary = request.summary.strip()
    await session.commit()

    # 后台任务更新向量库
    background_tasks.add_task(
        _update_summary_vector,
        request.project_id,
        request.chapter_number,
        title,
        request.summary.strip(),
        current_user.id,
    )

    logger.info(
        "用户 %s 更新项目 %s 第 %s 章的摘要",
        current_user.id,
        request.project_id,
        request.chapter_number
    )

    return {"status": "success", "message": "摘要已更新"}


@router.post("/append-style")
async def append_writing_style(
    request: AppendStyleRequest,
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
):
    """
    将用户的额外优化指令和AI返回的优化点总结后，追加到 writing_v2.md 形成写作风格库
    """
    import os
    from pathlib import Path

    # 获取 writing_v2.md 的路径
    prompt_file = Path(__file__).parent.parent.parent.parent / "prompts" / "writing_v2.md"

    if not prompt_file.exists():
        raise HTTPException(status_code=404, detail="writing_v2.md 文件不存在")

    # 维度名称映射
    dimension_names = {
        "dialogue": "对话优化",
        "environment": "环境描写",
        "psychology": "心理活动",
        "logic": "逻辑优化",
        "rhythm": "节奏韵律"
    }

    dimension_name = dimension_names.get(request.dimension, request.dimension)

    # 使用 LLM 总结优化经验
    llm_service = LLMService(session)

    summary_prompt = f"""你是一位写作风格提炼专家。请根据以下信息，提炼出可复用的写作风格指导原则。

**优化维度**: {dimension_name}

**用户的优化指令**:
{request.additional_notes if request.additional_notes else "无"}

**AI的优化说明**:
{request.optimization_notes}

请提炼出 2-4 条具体的、可操作的写作指导原则，每条原则应该：
1. 简洁明确（不超过30字）
2. 可直接应用于后续写作
3. 避免重复已有的通用规则

输出格式（纯文本，每条一行，以 "- " 开头）：
- 原则1
- 原则2
..."""

    try:
        summary_response = await llm_service.get_llm_response(
            system_prompt="你是一位写作风格提炼专家，擅长从具体案例中提炼可复用的写作原则。",
            conversation_history=[{"role": "user", "content": summary_prompt}],
            temperature=0.3,
            user_id=current_user.id,
            timeout=60.0,
            max_tokens=500,
            response_format=None
        )

        cleaned_summary = remove_think_tags(summary_response).strip()

        # 清洗 LLM 输出中的 markdown 标题标记，防止破坏文件结构
        cleaned_summary = re.sub(r'^(#{1,3}\s+)', '- ', cleaned_summary, flags=re.MULTILINE)

        # 加锁防止并发写入覆盖
        async with _style_file_lock:
            # 读取现有内容
            with open(prompt_file, "r", encoding="utf-8") as f:
                existing_content = f.read()

            # 检查是否已有"写作风格库"章节
            if "# 写作风格库" not in existing_content:
                # 如果没有，在文件末尾添加新章节
                style_section = f"""

---

# 写作风格库

本章节记录从实际优化中提炼的写作风格指导原则，会随着使用逐步积累。

## {dimension_name}

{cleaned_summary}
"""
            else:
                # 如果已有，检查是否已有该维度的子章节
                if f"## {dimension_name}" in existing_content:
                    # 追加到该维度下（用 maxsplit=1 防止多次匹配丢失内容）
                    dimension_marker = f"## {dimension_name}"
                    parts = existing_content.split(dimension_marker, 1)

                    # 精确匹配 "\n## " （带空格），排除 ### 误匹配
                    after_dimension = parts[1]
                    next_section_idx = after_dimension.find("\n## ")

                    if next_section_idx != -1:
                        # 在下一个二级章节前插入
                        before_next = after_dimension[:next_section_idx]
                        after_next = after_dimension[next_section_idx:]
                        style_section = parts[0] + dimension_marker + before_next + "\n" + cleaned_summary + "\n" + after_next
                    else:
                        # 追加到文件末尾
                        style_section = existing_content + "\n" + cleaned_summary + "\n"
                else:
                    # 在"写作风格库"章节下添加新维度（用 maxsplit=1）
                    style_marker = "# 写作风格库"
                    parts = existing_content.split(style_marker, 1)

                    # 找到下一个一级标题的位置（如果有）
                    after_style = parts[1]
                    next_chapter_idx = after_style.find("\n# ")

                    if next_chapter_idx != -1:
                        before_next = after_style[:next_chapter_idx]
                        after_next = after_style[next_chapter_idx:]
                        new_dimension_section = f"\n\n## {dimension_name}\n\n{cleaned_summary}\n"
                        style_section = parts[0] + style_marker + before_next + new_dimension_section + after_next
                    else:
                        new_dimension_section = f"\n\n## {dimension_name}\n\n{cleaned_summary}\n"
                        style_section = existing_content + new_dimension_section

            # 写回文件
            with open(prompt_file, "w", encoding="utf-8") as f:
                f.write(style_section)

        logger.info(
            "用户 %s 追加了 %s 维度的写作风格到 writing_v2.md",
            current_user.id,
            dimension_name
        )

        return {
            "status": "success",
            "message": f"已将 {dimension_name} 的优化经验追加到写作风格库",
            "summary": cleaned_summary
        }

    except Exception as exc:
        logger.exception("追加写作风格失败: %s", exc)
        raise HTTPException(
            status_code=500,
            detail=f"追加写作风格失败: {str(exc)[:200]}"
        )
