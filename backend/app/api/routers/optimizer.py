# AIMETA P=优化器API_内容优化建议|R=内容优化_建议生成|NR=不含内容修改|E=route:POST_/api/optimizer/*|X=http|A=优化建议|D=fastapi|S=net|RD=./README.ai
"""
章节内容分层优化API
支持对话、环境描写、心理活动、节奏韵律四个维度的深度优化
"""
import json
import logging
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select as sa_select
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.config import settings
from ...core.dependencies import get_current_user
from ...db.session import AsyncSessionLocal, get_session
from ...models.novel import Chapter, ChapterOutline
from ...schemas.user import UserInDB
from ...services.chapter_ingest_service import ChapterIngestionService
from ...services.llm_service import LLMService
from ...services.novel_service import NovelService
from ...services.prompt_service import PromptService
from ...utils.json_utils import remove_think_tags, unwrap_markdown_json

router = APIRouter(prefix="/api/optimizer", tags=["Optimizer"])
logger = logging.getLogger(__name__)


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


# 优化维度到提示词的映射
DIMENSION_PROMPT_MAP = {
    "dialogue": "optimize_dialogue",
    "environment": "optimize_environment", 
    "psychology": "optimize_psychology",
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


async def _ingest_optimized_chapter(
    project_id: str,
    chapter_number: int,
    title: str,
    content: str,
    user_id: int,
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
            if not summary_text:
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
