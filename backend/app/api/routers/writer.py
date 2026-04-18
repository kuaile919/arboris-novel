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
import re
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ...core.config import settings
from ...core.dependencies import get_current_user
from ...db.session import AsyncSessionLocal, get_session
from ...models.foreshadowing import Foreshadowing
from ...models.novel import Chapter, ChapterOutline, ChapterVersion
from ...schemas.novel import (
    Chapter as ChapterSchema,
    ChapterGenerationStatus,
    ChapterRuntimeStatus,
    WritingStyleLibrary,
    UpdateWritingStyleLibraryRequest,
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
from ...services.user_style_rule_service import UserStyleRuleService
from ...services.key_location_service import KeyLocationService
from ...services.faction_service import FactionService
from ...utils.json_utils import remove_think_tags, unwrap_markdown_json, sanitize_json_like_text
from ...repositories.system_config_repository import SystemConfigRepository
from ...services.pipeline_orchestrator import PipelineOrchestrator

router = APIRouter(prefix="/api/writer", tags=["Writer"])
logger = logging.getLogger(__name__)


async def _load_project_schema(service: NovelService, project_id: str, user_id: int) -> NovelProjectSchema:
    return await service.get_project_schema(project_id, user_id)


def _format_personal_rules_section(rules: List[str]) -> str:
    if not rules:
        return "无"
    lines = [f"- {rule}" for rule in rules]
    return "\n".join(lines)


def _extract_tail_excerpt(text: Optional[str], limit: int = 500) -> str:
    """截取章节结尾文本，默认保留 500 字。"""
    if not text:
        return ""
    stripped = text.strip()
    if len(stripped) <= limit:
        return stripped
    return stripped[-limit:]


def _is_tail_incomplete(text: str) -> bool:
    """粗判正文尾句是否未收束（用于兜底修复 token 截断）。"""
    value = (text or "").rstrip()
    if not value:
        return False
    # 常见完整结尾标记（包含中文/英文及引号闭合）
    terminal_chars = set("。！？…?!”’」』》）)]")
    if value[-1] in terminal_chars:
        return False
    # 末尾若是逗号、顿号、冒号等高概率为未完句
    if value[-1] in {",", "，", "、", ":", "：", ";", "；", "-", "—"}:
        return True
    # 末尾是汉字/字母/数字且没有句末符，也视为可疑
    return True


def _trim_to_sentence_boundary(text: str, max_chars: int) -> str:
    """在不超过 max_chars 的前提下，尽量按句号边界截断，避免半句。"""
    value = (text or "").strip()
    if len(value) <= max_chars:
        return value

    candidate = value[:max_chars]
    punctuation = "。！？…?!”’」』》）)]"
    last_idx = -1
    for ch in punctuation:
        idx = candidate.rfind(ch)
        if idx > last_idx:
            last_idx = idx

    # 留至少 70% 内容，避免截得过短
    if last_idx >= int(max_chars * 0.7):
        return candidate[: last_idx + 1].rstrip()
    return candidate.rstrip()


def _truncate_text(text: Optional[str], max_chars: int) -> str:
    value = (text or "").strip()
    if len(value) <= max_chars:
        return value
    return value[:max_chars].rstrip() + "\n...(已截断)"


def _trim_rules_block(rules_text: str, max_rules: int = 8, max_chars: int = 480) -> str:
    lines = [line.strip() for line in (rules_text or "").splitlines() if line.strip()]
    selected = lines[:max_rules]
    return _truncate_text("\n".join(selected), max_chars)


def _compact_writer_blueprint(blueprint: Dict[str, Any]) -> Dict[str, Any]:
    compact: Dict[str, Any] = {
        "title": blueprint.get("title"),
        "genre": blueprint.get("genre"),
        "style": blueprint.get("style"),
        "tone": blueprint.get("tone"),
        "world_setting": {},
        "characters": [],
        "relationships": [],
    }

    ws = blueprint.get("world_setting") if isinstance(blueprint.get("world_setting"), dict) else {}
    compact["world_setting"] = {
        "core_rules": _truncate_text(str(ws.get("core_rules") or ""), 280),
        "key_locations": [
            {
                "name": item.get("name"),
                "description": _truncate_text(str(item.get("description") or ""), 80),
            }
            for item in (ws.get("key_locations") or [])[:6]
            if isinstance(item, dict)
        ],
        "factions": [
            {
                "name": item.get("name"),
                "description": _truncate_text(str(item.get("description") or ""), 80),
            }
            for item in (ws.get("factions") or [])[:6]
            if isinstance(item, dict)
        ],
    }

    compact["characters"] = [
        {
            "name": item.get("name"),
            "identity": _truncate_text(str(item.get("identity") or ""), 80),
            "personality": _truncate_text(str(item.get("personality") or ""), 80),
            "goals": _truncate_text(str(item.get("goals") or ""), 80),
            "first_appear_chapter": item.get("first_appear_chapter"),
        }
        for item in (blueprint.get("characters") or [])[:10]
        if isinstance(item, dict) and item.get("name")
    ]

    compact["relationships"] = [
        {
            "from": item.get("from") or item.get("character_from"),
            "to": item.get("to") or item.get("character_to"),
            "description": _truncate_text(str(item.get("description") or ""), 80),
        }
        for item in (blueprint.get("relationships") or [])[:12]
        if isinstance(item, dict)
    ]
    return compact


def _compact_chapter_mission(mission: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not isinstance(mission, dict):
        return {}
    return {
        "macro_beat": mission.get("macro_beat"),
        "pov": mission.get("pov"),
        "narrative_goal": _truncate_text(str(mission.get("narrative_goal") or ""), 140),
        "must_happen": (mission.get("must_happen") or [])[:6],
        "forbidden": (mission.get("forbidden") or [])[:6],
        "ending_hook": _truncate_text(str(mission.get("ending_hook") or ""), 120),
        "allowed_new_characters": (mission.get("allowed_new_characters") or [])[:4],
    }


def _collect_foreshadowing_terms(item: Dict[str, Any]) -> List[str]:
    """提取用于粗匹配的伏笔关键词。"""
    terms: List[str] = []

    keywords = item.get("keywords") or []
    if isinstance(keywords, list):
        for kw in keywords:
            if isinstance(kw, str):
                normalized = kw.strip()
                if len(normalized) >= 2:
                    terms.append(normalized)

    content = str(item.get("content") or "").strip()
    if content:
        parts = [seg.strip() for seg in re.split(r"[，。！？；、,.;:：\s]+", content) if seg and len(seg.strip()) >= 2]
        parts.sort(key=len, reverse=True)
        terms.extend(parts[:3])

    # 去重，保持顺序
    deduped: List[str] = []
    seen = set()
    for term in terms:
        if term not in seen:
            seen.add(term)
            deduped.append(term)
    return deduped


def _check_foreshadowing_contract(generated_text: str, must_payoff_items: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    伏笔执行检查（轻量规则版）：
    - 对每个“本章必须回收”的伏笔，检查正文是否至少出现一个核心关键词。
    """
    if not must_payoff_items:
        return {"passed": True, "missing": []}

    text = generated_text or ""
    missing: List[Dict[str, Any]] = []
    for item in must_payoff_items:
        terms = _collect_foreshadowing_terms(item)
        matched = any(term in text for term in terms) if terms else False
        if not matched:
            missing.append(
                {
                    "id": item.get("id"),
                    "content": item.get("content"),
                    "terms": terms,
                }
            )

    return {"passed": len(missing) == 0, "missing": missing}


async def _check_chapter_execution_contract(
    *,
    llm_service: LLMService,
    user_id: int,
    chapter_number: int,
    generated_text: str,
    outline_title: str,
    outline_summary: str,
    must_plant_items: List[Dict[str, Any]],
    must_payoff_items: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    章节执行硬约束检查（大纲目标 + 本章埋伏笔 + 本章收伏笔）。
    使用 LLM 做语义判定，避免纯关键词匹配误判。
    """
    if not generated_text.strip():
        return {
            "passed": False,
            "outline_covered": False,
            "missing_outline_points": ["正文为空"],
            "missing_plants": must_plant_items,
            "missing_payoffs": must_payoff_items,
        }

    requirement_payload = {
        "outline": {"title": outline_title, "summary": outline_summary},
        "must_plants": [
            {"id": item.get("id"), "content": item.get("content")}
            for item in must_plant_items
        ],
        "must_payoffs": [
            {"id": item.get("id"), "content": item.get("content")}
            for item in must_payoff_items
        ],
    }

    judge_system_prompt = (
        "你是小说章节执行审校器。"
        "请严格判断：正文是否覆盖本章大纲目标，是否包含所有“必须埋设”的伏笔，"
        "是否包含所有“必须回收”的伏笔。"
        "仅输出 JSON，不要任何解释。"
    )
    judge_input = (
        f"[当前章节号]\n{chapter_number}\n\n"
        f"[硬约束要求]\n{json.dumps(requirement_payload, ensure_ascii=False, indent=2)}\n\n"
        f"[章节正文]\n{generated_text[:9000]}\n\n"
        "[输出格式]\n"
        '{'
        '"outline_covered":true,'
        '"missing_outline_points":["缺失点1"],'
        '"missing_plant_ids":[1],'
        '"missing_payoff_ids":[2]'
        "}\n"
        "注意：必须严格；只要未明确体现就视为缺失。"
    )

    try:
        response = await llm_service.get_llm_response(
            system_prompt=judge_system_prompt,
            conversation_history=[{"role": "user", "content": judge_input}],
            temperature=0.1,
            user_id=user_id,
            timeout=120.0,
            response_format=None,
        )
        cleaned = remove_think_tags(response)
        normalized = unwrap_markdown_json(cleaned)
        sanitized = sanitize_json_like_text(normalized)
        parsed = json.loads(sanitized)
    except Exception as exc:
        logger.warning("章节执行硬约束检查失败，降级为关键词检查: chapter=%s err=%s", chapter_number, exc)
        plant_check = _check_foreshadowing_contract(generated_text, must_plant_items)
        payoff_check = _check_foreshadowing_contract(generated_text, must_payoff_items)
        outline_covered = bool((outline_title or "").strip()) and (outline_title.strip() in generated_text)
        return {
            "passed": outline_covered and plant_check["passed"] and payoff_check["passed"],
            "outline_covered": outline_covered,
            "missing_outline_points": [] if outline_covered else ["标题主目标未明确体现"],
            "missing_plants": plant_check.get("missing", []),
            "missing_payoffs": payoff_check.get("missing", []),
        }

    outline_covered = bool(parsed.get("outline_covered", False))
    missing_outline_points_raw = parsed.get("missing_outline_points", [])
    missing_outline_points = (
        [str(item).strip() for item in missing_outline_points_raw if str(item).strip()]
        if isinstance(missing_outline_points_raw, list)
        else []
    )

    def _normalize_missing_ids(raw_value: Any) -> List[int]:
        ids: List[int] = []
        if not isinstance(raw_value, list):
            return ids
        for item in raw_value:
            try:
                ids.append(int(item))
            except (TypeError, ValueError):
                continue
        return ids

    missing_plant_ids = set(_normalize_missing_ids(parsed.get("missing_plant_ids", [])))
    missing_payoff_ids = set(_normalize_missing_ids(parsed.get("missing_payoff_ids", [])))

    missing_plants = [item for item in must_plant_items if item.get("id") in missing_plant_ids]
    missing_payoffs = [item for item in must_payoff_items if item.get("id") in missing_payoff_ids]

    passed = outline_covered and not missing_plants and not missing_payoffs
    return {
        "passed": passed,
        "outline_covered": outline_covered,
        "missing_outline_points": missing_outline_points,
        "missing_plants": missing_plants,
        "missing_payoffs": missing_payoffs,
    }


def _normalize_foreshadowing_entry(entry: Any) -> Optional[Dict[str, Any]]:
    """统一解析伏笔条目，兼容 str 和 dict 两种格式。"""
    if isinstance(entry, str):
        content = entry.strip()
        if not content:
            return None
        return {
            "content": content,
            "target_reveal_chapter": None,
            "importance": None,
            "keywords": [],
            "foreshadowing_id": None,
        }

    if isinstance(entry, dict):
        raw_content = entry.get("content") or entry.get("description") or entry.get("text")
        content = str(raw_content or "").strip()
        if not content:
            return None

        target = entry.get("target_reveal_chapter")
        if target is None:
            target = entry.get("target_chapter")
        if target is None:
            target = entry.get("expected_payoff_chapter")
        try:
            target_chapter = int(target) if target is not None else None
        except (TypeError, ValueError):
            target_chapter = None

        importance = entry.get("importance")
        if isinstance(importance, str):
            importance = importance.strip().lower()
        if importance not in {"major", "minor", "subtle"}:
            importance = None

        keywords = entry.get("keywords") or []
        if not isinstance(keywords, list):
            keywords = []
        keywords = [str(k).strip() for k in keywords if str(k).strip()]

        foreshadowing_id = entry.get("foreshadowing_id") or entry.get("id")
        try:
            foreshadowing_id = int(foreshadowing_id) if foreshadowing_id is not None else None
        except (TypeError, ValueError):
            foreshadowing_id = None

        return {
            "content": content,
            "target_reveal_chapter": target_chapter,
            "importance": importance,
            "keywords": keywords,
            "foreshadowing_id": foreshadowing_id,
        }

    return None


async def _auto_resolve_foreshadowings_from_chapter(
    *,
    session: AsyncSession,
    llm_service: LLMService,
    project_id: str,
    chapter_id: int,
    chapter_number: int,
    chapter_text: str,
    user_id: int,
) -> Dict[str, Any]:
    """
    基于章节正文自动识别并回收已触发的伏笔。
    使用 LLM 做轻量判定，避免纯字符串匹配遗漏。
    """
    if not chapter_text.strip():
        return {"resolved_count": 0, "candidate_count": 0}

    foreshadowing_service = ForeshadowingService(session)
    unresolved = await foreshadowing_service.get_unresolved_foreshadowings(
        project_id=project_id,
        current_chapter_number=chapter_number,
    )
    candidates = [fs for fs in unresolved if fs.chapter_number < chapter_number]
    if not candidates:
        return {"resolved_count": 0, "candidate_count": 0}

    def _sort_key(fs: Any) -> tuple:
        due_rank = 0 if (fs.target_reveal_chapter is not None and fs.target_reveal_chapter <= chapter_number) else 1
        target_rank = fs.target_reveal_chapter if fs.target_reveal_chapter is not None else 10**9
        urgency_rank = -(fs.urgency or 0)
        age_rank = -(chapter_number - fs.chapter_number)
        return (due_rank, target_rank, urgency_rank, age_rank)

    candidates.sort(key=_sort_key)
    candidates = candidates[:8]
    candidate_map = {fs.id: fs for fs in candidates}

    payload = []
    for fs in candidates:
        payload.append(
            {
                "id": fs.id,
                "content": fs.content,
                "planted_chapter": fs.chapter_number,
                "target_reveal_chapter": fs.target_reveal_chapter,
                "keywords": fs.keywords if isinstance(fs.keywords, list) else [],
            }
        )

    judge_system_prompt = (
        "你是小说伏笔追踪编辑。你将收到一章正文和候选未回收伏笔列表。"
        "判断哪些伏笔在本章已经被明确回收或实质推进到可视为回收。"
        "只输出 JSON，不要额外说明。"
    )
    judge_input = (
        f"[当前章节号]\n{chapter_number}\n\n"
        f"[本章正文]\n{chapter_text[:7000]}\n\n"
        f"[候选伏笔]\n{json.dumps(payload, ensure_ascii=False, indent=2)}\n\n"
        "[输出格式]\n"
        '{"resolved_ids":[1,2],"reason_by_id":{"1":"一句话原因"}}\n'
        "注意：不确定时不要选。"
    )

    try:
        response = await llm_service.get_llm_response(
            system_prompt=judge_system_prompt,
            conversation_history=[{"role": "user", "content": judge_input}],
            temperature=0.1,
            user_id=user_id,
            timeout=120.0,
            response_format=None,
        )
        cleaned = remove_think_tags(response)
        normalized = unwrap_markdown_json(cleaned)
        sanitized = sanitize_json_like_text(normalized)
        parsed = json.loads(sanitized)
    except Exception as exc:
        logger.warning("自动回收伏笔判定失败，跳过本次: project=%s chapter=%s err=%s", project_id, chapter_number, exc)
        return {"resolved_count": 0, "candidate_count": len(candidates)}

    resolved_ids_raw = parsed.get("resolved_ids", [])
    reason_by_id = parsed.get("reason_by_id", {}) if isinstance(parsed.get("reason_by_id"), dict) else {}
    resolved_ids: List[int] = []
    for rid in resolved_ids_raw if isinstance(resolved_ids_raw, list) else []:
        try:
            rid_int = int(rid)
        except (TypeError, ValueError):
            continue
        if rid_int in candidate_map:
            resolved_ids.append(rid_int)

    if not resolved_ids:
        return {"resolved_count": 0, "candidate_count": len(candidates)}

    resolved_count = 0
    for rid in resolved_ids:
        fs = candidate_map.get(rid)
        if not fs:
            continue
        reason = str(reason_by_id.get(str(rid)) or reason_by_id.get(rid) or "").strip()
        resolution_text = reason or f"自动判定在第{chapter_number}章完成回收"
        try:
            await foreshadowing_service.resolve_foreshadowing(
                foreshadowing_id=rid,
                resolved_chapter_id=chapter_id,
                resolved_chapter_number=chapter_number,
                resolution_text=resolution_text,
                resolution_type="auto_detected",
            )
            resolved_count += 1
        except Exception as exc:
            logger.warning("自动回收伏笔写入失败: fs=%s chapter=%s err=%s", rid, chapter_number, exc)

    if resolved_count > 0:
        logger.info(
            "自动回收伏笔完成: project=%s chapter=%s resolved=%s candidate=%s",
            project_id,
            chapter_number,
            resolved_count,
            len(candidates),
        )
    return {"resolved_count": resolved_count, "candidate_count": len(candidates)}


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
        try:
            response = await llm_service.get_llm_response(
                system_prompt=plan_prompt,
                conversation_history=[{"role": "user", "content": plan_input}],
                temperature=0.3,
                user_id=user_id,
                timeout=120.0,
            )
        except HTTPException as exc:
            detail_text = str(exc.detail)
            # 个别模型会返回 finish_reason=stop 但正文为空，这里做一次轻量重试。
            if exc.status_code == 503 and "未返回有效内容" in detail_text:
                logger.warning("章节导演脚本首轮空响应，立即重试一次: user_id=%s", user_id)
                response = await llm_service.get_llm_response(
                    system_prompt=plan_prompt,
                    conversation_history=[{"role": "user", "content": plan_input}],
                    temperature=0.3,
                    user_id=user_id,
                    timeout=120.0,
                )
            else:
                raise
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
    min_chars: Optional[int] = None,
    max_chars: Optional[int] = None,
    max_tokens: int = 2200,
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
    if min_chars is not None and max_chars is not None:
        rewrite_input += (
            f"\n\n[字数硬约束]\n"
            f"- 改写后正文必须控制在 {min_chars}-{max_chars} 字\n"
            f"- 不得超过 {max_chars} 字\n"
            f"- 必须保留完整结尾，禁止半句截断\n"
        )

    try:
        response = await llm_service.get_llm_response(
            system_prompt=rewrite_prompt,
            conversation_history=[{"role": "user", "content": rewrite_input}],
            temperature=0.3,
            user_id=user_id,
            timeout=300.0,
            response_format=None,
            max_tokens=max_tokens,
        )
        cleaned = remove_think_tags(response)
        logger.info("成功修复违规内容")
        return cleaned
    except Exception as exc:
        logger.warning("自动修复失败，返回原文: %s", exc)
        return original_text


async def _rewrite_to_target_length(
    llm_service: LLMService,
    original_text: str,
    chapter_mission: Optional[dict],
    outline_title: str,
    outline_summary: str,
    min_chars: int,
    target_max_chars: int,
    hard_max_chars: int,
    user_id: int,
) -> str:
    """在不丢失关键剧情与伏笔的前提下压缩正文长度。"""
    system_prompt = (
        "你是网文编辑。请将正文压缩到目标字数范围，同时保证剧情连贯和章节钩子完整。"
        "不得删除本章关键事件、大纲目标和已执行伏笔。只输出正文，不要解释。"
    )
    rewrite_input = f"""
[原文]
{original_text}

[本章大纲]
标题：{outline_title}
摘要：{outline_summary}

[章节导演脚本]
{json.dumps(chapter_mission, ensure_ascii=False, indent=2) if chapter_mission else "无"}

[压缩目标]
- 目标范围：{min_chars}-{target_max_chars} 字
- 硬上限：{hard_max_chars} 字

[要求]
1. 保留起-承-转-钩结构，不写成摘要。
2. 保留关键事件与伏笔触发点。
3. 优先压缩重复描写、赘余修饰、无效对话。
4. 结尾必须完整，不允许断句或突然中断。
"""
    try:
        response = await llm_service.get_llm_response(
            system_prompt=system_prompt,
            conversation_history=[{"role": "user", "content": rewrite_input}],
            temperature=0.2,
            user_id=user_id,
            timeout=240.0,
            response_format=None,
            max_tokens=3600,
        )
        return remove_think_tags(response).strip()
    except Exception as exc:
        logger.warning("压缩重写失败，返回原文: %s", exc)
        return original_text


async def _complete_tail_sentence(
    llm_service: LLMService,
    text: str,
    *,
    user_id: int,
) -> str:
    """若正文尾句疑似被截断，尝试最小补全最后一句。"""
    current = (text or "").rstrip()
    if not current or not _is_tail_incomplete(current):
        return current

    tail_context = current[-500:]
    prompt = f"""
[正文尾部上下文]
{tail_context}

最后一句疑似被中断。请仅补全最后一句，使其语义与语气自然闭合。

要求：
1. 只输出“续写补全文字”，不要重复原文。
2. 长度尽量短（建议 10-80 字）。
3. 不能改动已有剧情，只做句子收束。
4. 补全后必须有完整句末标点（。！？…）。
"""
    try:
        response = await llm_service.get_llm_response(
            system_prompt="你是中文小说文本修复器，专门补全被截断的尾句。",
            conversation_history=[{"role": "user", "content": prompt}],
            temperature=0.2,
            user_id=user_id,
            timeout=60.0,
            response_format=None,
            max_tokens=180,
        )
        continuation = remove_think_tags(response).strip()
        continuation = re.sub(r"^([\"'“”‘’\s]+)", "", continuation)
        if not continuation:
            return current + "。"
        if len(continuation) > 160:
            continuation = continuation[:160]
        completed = current + continuation
        if _is_tail_incomplete(completed):
            completed += "。"
        return completed
    except Exception as exc:
        logger.warning("尾句补全失败，使用兜底标点收束: %s", exc)
        return current + "。"


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
        try:
            await _auto_resolve_foreshadowings_from_chapter(
                session=session,
                llm_service=llm_service,
                project_id=project_id,
                chapter_id=chapter.id,
                chapter_number=chapter_number,
                chapter_text=selected_version.content,
                user_id=user_id,
            )
            await session.commit()
        except Exception as exc:
            logger.warning("异步定稿后自动回收伏笔失败: project=%s chapter=%s err=%s", project_id, chapter_number, exc)


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
    try:
        llm_service = LLMService(session)
        auto_resolve_result = await _auto_resolve_foreshadowings_from_chapter(
            session=session,
            llm_service=llm_service,
            project_id=request.project_id,
            chapter_id=chapter.id,
            chapter_number=chapter_number,
            chapter_text=selected_version.content,
            user_id=current_user.id,
        )
        if auto_resolve_result.get("resolved_count", 0) > 0:
            await session.commit()
            finalize_result.setdefault("updates", {})
            finalize_result["updates"]["foreshadowing_auto_resolve"] = auto_resolve_result["resolved_count"]
    except Exception as exc:
        logger.warning("定稿后自动回收伏笔失败: project=%s chapter=%s err=%s", request.project_id, chapter_number, exc)

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
    style_rule_service = UserStyleRuleService(session)
    chapter_min_chars = 2400
    chapter_target_max_chars = 3000
    chapter_hard_max_chars = 3000

    project = await novel_service.ensure_project_owner(project_id, current_user.id)
    logger.info("用户 %s 开始为项目 %s 生成第 %s 章", current_user.id, project_id, request.chapter_number)
    personal_rules = await style_rule_service.get_effective_rules(
        user_id=current_user.id,
        project_id=project_id,
        rule_types=["general", "chapter_writing"],
        limit=20,
    )
    personal_rules_text = _format_personal_rules_section(personal_rules)
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
    writing_notes_for_director = writing_notes
    if personal_rules:
        director_rules = _trim_rules_block(personal_rules_text, max_rules=6, max_chars=360)
        writing_notes_for_director = (
            f"{writing_notes}\n\n[用户个人风格规则]\n{director_rules}\n"
            "请将以上规则作为优先风格约束。"
        )

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
        writing_notes=writing_notes_for_director,
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
        max_chapter_exclusive=request.chapter_number,
    )
    # 剧情片段上下文策略（防时间穿越）：
    # 1) 仅允许当前章之前的片段进入上下文（严格排除当前章与未来章节）
    # 2) 上一章片段作为主干硬约束（最多 2 条）
    # 3) 额外补 1 条更早章节的语义相关片段（可选）
    temporal_chunks = [
        chunk
        for chunk in rag_context.chunks
        if chunk.chapter_number > 0
        and chunk.chapter_number < request.chapter_number
        and (chunk.content or "").strip()
    ]
    previous_chapter_number = request.chapter_number - 1
    chunk_backbone_limit = 2
    backbone_chunks = [
        chunk for chunk in temporal_chunks if chunk.chapter_number == previous_chapter_number
    ][:chunk_backbone_limit]

    # 若上一章未命中，则回退到“最近的已存在前章”
    if not backbone_chunks:
        available_prev_numbers = [chunk.chapter_number for chunk in temporal_chunks]
        latest_available_prev = max(available_prev_numbers) if available_prev_numbers else None
        if latest_available_prev is not None:
            backbone_chunks = [
                chunk for chunk in temporal_chunks if chunk.chapter_number == latest_available_prev
            ][:chunk_backbone_limit]

    backbone_numbers = {chunk.chapter_number for chunk in backbone_chunks}

    remote_semantic_chunk = None
    for chunk in temporal_chunks:
        # 远章补充只从非主干章节中选
        if chunk.chapter_number in backbone_numbers:
            continue
        remote_semantic_chunk = chunk
        break

    chunk_blocks = [
        "优先级规则：近章剧情片段 > 远章语义片段。必须先保证与上一章连续，远章仅用于伏笔回收或背景补充。"
    ]
    if backbone_chunks:
        backbone_lines = []
        for idx, chunk in enumerate(backbone_chunks, start=1):
            title = chunk.chapter_title or f"第{chunk.chapter_number}章"
            backbone_lines.append(f"### Backbone Chunk {idx}(来源：{title})\n{chunk.content.strip()}")
        chunk_blocks.append("### 近章主干（硬约束）\n" + "\n\n".join(backbone_lines))
    else:
        chunk_blocks.append("### 近章主干（硬约束）\n- 无（暂无可用前章片段）")

    if remote_semantic_chunk:
        remote_title = remote_semantic_chunk.chapter_title or f"第{remote_semantic_chunk.chapter_number}章"
        chunk_blocks.append(
            "### 远章补充（可选，软参考）\n"
            + f"### Remote Chunk(来源：{remote_title})\n{remote_semantic_chunk.content.strip()}"
        )
    else:
        chunk_blocks.append("### 远章补充（可选，软参考）\n- 无")

    rag_chunks_text = _truncate_text("\n\n".join(chunk_blocks), 1300)
    logger.info(
        "章节剧情上下文已构建: project=%s chapter=%s backbone_chapters=%s remote_chapter=%s dropped_current_or_future=%s",
        project_id,
        request.chapter_number,
        sorted(list(backbone_numbers)),
        remote_semantic_chunk.chapter_number if remote_semantic_chunk else None,
        sorted(
            {
                chunk.chapter_number
                for chunk in rag_context.chunks
                if chunk.chapter_number >= request.chapter_number
            }
        ),
    )

    # 摘要上下文策略：最近 3 章作为主干硬约束，额外补 1 条远章语义相关摘要（可选）
    recent_summary_window = 3
    completed_summary_rows = [
        row
        for row in completed_chapters
        if row.get("chapter_number", 0) < request.chapter_number and (row.get("summary") or "").strip()
    ]
    completed_summary_rows.sort(key=lambda row: row.get("chapter_number", 0))
    recent_backbone_rows = completed_summary_rows[-recent_summary_window:]
    recent_backbone_numbers = {row.get("chapter_number", 0) for row in recent_backbone_rows}

    recent_backbone_lines = []
    for row in recent_backbone_rows:
        chapter_no = row.get("chapter_number", 0)
        chapter_title = row.get("title") or f"第{chapter_no}章"
        chapter_summary = (row.get("summary") or "").strip()
        recent_backbone_lines.append(f"- 第{chapter_no}章 - {chapter_title}:{chapter_summary}")

    remote_semantic_line = None
    for item in rag_context.summaries:
        chapter_no = item.chapter_number
        if chapter_no >= request.chapter_number:
            continue
        if chapter_no in recent_backbone_numbers:
            continue
        summary_text = (item.summary or "").strip()
        if not summary_text:
            continue
        remote_semantic_line = f"- 第{chapter_no}章 - {item.title}:{summary_text}"
        break

    summary_blocks = [
        "优先级规则：近章摘要 > 远章语义补充。写作时必须先遵循最近3章的连续性，远章只用于伏笔回收或背景补充。"
    ]
    if recent_backbone_lines:
        summary_blocks.append("### 近章主干（硬约束，按章节顺序）\n" + "\n".join(recent_backbone_lines))
    else:
        summary_blocks.append("### 近章主干（硬约束，按章节顺序）\n- 暂无（这是前几章）")

    if remote_semantic_line:
        summary_blocks.append("### 远章补充（可选，软参考）\n" + remote_semantic_line)
    else:
        summary_blocks.append("### 远章补充（可选，软参考）\n- 无")

    rag_summaries_text = _truncate_text("\n\n".join(summary_blocks), 1000)
    logger.info(
        "章节摘要上下文已构建: project=%s chapter=%s recent_backbone=%s remote_semantic=%s",
        project_id,
        request.chapter_number,
        [row.get("chapter_number", 0) for row in recent_backbone_rows],
        remote_semantic_line is not None,
    )

    # ========== 5. 构建写作提示词 ==========
    # 优先使用 writing_v2，fallback 到 writing
    writer_prompt = await prompt_service.get_prompt("writing_v2")
    if not writer_prompt:
        writer_prompt = await prompt_service.get_prompt("writing")
    if not writer_prompt:
        logger.error("未配置写作提示词，无法生成章节内容")
        raise HTTPException(status_code=500, detail="缺少写作提示词，请联系管理员配置")

    # 使用进一步压缩后的蓝图，控制提示词体积
    compact_blueprint = _compact_writer_blueprint(writer_blueprint)
    blueprint_text = json.dumps(compact_blueprint, ensure_ascii=False, indent=2)
    
    # 构建压缩版导演脚本
    mission_compact = _compact_chapter_mission(chapter_mission)
    mission_text = json.dumps(mission_compact, ensure_ascii=False, indent=2) if mission_compact else "无导演脚本"
    
    # 构建禁止角色列表
    forbidden_text = json.dumps(forbidden_characters[:12], ensure_ascii=False) if forbidden_characters else "无"
    personal_rules_compact = _trim_rules_block(personal_rules_text, max_rules=8, max_chars=480)

    # 构建伏笔执行清单（硬约束）
    foreshadowing_service = ForeshadowingService(session)
    planted_stmt = (
        select(Foreshadowing)
        .where(
            Foreshadowing.project_id == project_id,
            Foreshadowing.chapter_number == request.chapter_number,
            Foreshadowing.status != "abandoned",
        )
        .order_by(Foreshadowing.id)
    )
    planted_result = await session.execute(planted_stmt)
    planted_for_current = planted_result.scalars().all()
    must_plant_items: List[Dict[str, Any]] = []
    seen_plant_contents = set()
    for fs in planted_for_current:
        content = str(fs.content or "").strip()
        if not content or content in seen_plant_contents:
            continue
        seen_plant_contents.add(content)
        must_plant_items.append(
            {
                "id": fs.id,
                "name": fs.name,
                "content": content,
                "chapter_number": fs.chapter_number,
                "urgency": fs.urgency,
                "keywords": fs.keywords if isinstance(fs.keywords, list) else [],
            }
        )
    must_plant_items = must_plant_items[:5]

    unresolved_foreshadowings = await foreshadowing_service.get_unresolved_foreshadowings(
        project_id=project_id,
        current_chapter_number=request.chapter_number,
    )
    due_payoff_items: List[Dict[str, Any]] = []
    soft_reminder_items: List[Dict[str, Any]] = []
    overdue_escalation_chapters = max(1, int(settings.foreshadowing_overdue_escalation_chapters))
    for fs in unresolved_foreshadowings:
        target_chapter = fs.target_reveal_chapter
        if target_chapter is None:
            soft_reminder_items.append(
                {
                    "id": fs.id,
                    "name": fs.name,
                    "content": fs.content,
                    "chapter_number": fs.chapter_number,
                    "urgency": fs.urgency,
                    "keywords": fs.keywords if isinstance(fs.keywords, list) else [],
                }
            )
            continue
        if target_chapter > request.chapter_number:
            continue
        overdue_chapters = max(0, request.chapter_number - target_chapter)
        is_overdue_escalated = overdue_chapters >= overdue_escalation_chapters
        due_payoff_items.append(
            {
                "id": fs.id,
                "name": fs.name,
                "content": fs.content,
                "chapter_number": fs.chapter_number,
                "target_reveal_chapter": target_chapter,
                "urgency": fs.urgency,
                "overdue_chapters": overdue_chapters,
                "is_overdue_escalated": is_overdue_escalated,
                "keywords": fs.keywords if isinstance(fs.keywords, list) else [],
            }
        )

    due_payoff_items.sort(
        key=lambda item: (
            -(1 if item.get("is_overdue_escalated") else 0),
            item.get("target_reveal_chapter") if item.get("target_reveal_chapter") is not None else 10**9,
            -(item.get("urgency") or 0),
            item.get("chapter_number") or 0,
        )
    )
    # 限制硬约束数量，避免过载
    due_payoff_items = due_payoff_items[:3]
    soft_reminder_items.sort(
        key=lambda item: (
            -(item.get("urgency") or 0),
            item.get("chapter_number") or 0,
        )
    )
    soft_reminder_items = soft_reminder_items[:5]

    hard_contract_lines: List[str] = []
    hard_contract_lines.append("本章硬约束（必须满足）：")
    hard_contract_lines.append(
        f"- 必须覆盖本章大纲目标：标题《{outline_title}》；摘要要点：{outline_summary}"
    )

    if must_plant_items:
        hard_contract_lines.append("- 必须埋设以下伏笔（每条都需在正文中明确出现）：")
        for item in must_plant_items:
            name = item.get("name") or f"伏笔#{item.get('id')}"
            hard_contract_lines.append(f"  - [{name}] 内容：{item.get('content')}")
    else:
        hard_contract_lines.append("- 本章无“必埋伏笔”硬性条目。")

    if due_payoff_items:
        hard_contract_lines.append("- 必须回收以下伏笔（每条都需在正文中明确体现）：")
        for item in due_payoff_items:
            name = item.get("name") or f"伏笔#{item.get('id')}"
            planted = item.get("chapter_number")
            target = item.get("target_reveal_chapter")
            content = str(item.get("content") or "").strip()
            escalation_tag = ""
            if item.get("is_overdue_escalated"):
                escalation_tag = f"【超期升级：已连续{item.get('overdue_chapters')}章未回收】"
            hard_contract_lines.append(
                f"  - [{name}] 埋设章={planted} 目标回收章={target if target is not None else '未指定'} {escalation_tag} 内容：{content}"
            )
    else:
        hard_contract_lines.append("- 本章无“必收伏笔”硬性条目。")

    hard_contract_lines.append(
        f"- 若标记为【超期升级】（到期后连续{overdue_escalation_chapters}章未回收），应优先处理。"
    )
    foreshadowing_contract_text = "\n".join(hard_contract_lines)
    strict_execution_protocol = (
        "强制执行协议（违背即判定失败并丢弃重生成）：\n"
        "1. 必须完整覆盖本章大纲标题与摘要目标。\n"
        "2. 必须逐条落地“必埋伏笔”。\n"
        "3. 必须逐条落地“必收伏笔”。\n"
        "4. 任一条缺失都视为不合格版本，系统会直接重生成。\n"
        "5. 首次生成就必须满足 1-4 条，不能依赖后续校验补救。"
    )
    first_pass_hit_protocol = (
        "首轮命中执行法（仅内部执行，不要输出这些步骤）：\n"
        "A. 写作前先做“约束映射”：把大纲主目标、每条必埋、每条必收分别绑定到正文中的具体段落位置。\n"
        "B. 每条必埋/必收都要有可被读者直接识别的明确描写，不能只做暗示性擦边。\n"
        "C. 收尾前做一次自检：逐条确认都已落地，再输出正文。\n"
        "D. 若字数接近上限，优先压缩修辞，不得删减任何硬约束条目。"
    )

    if soft_reminder_items:
        soft_lines = []
        for item in soft_reminder_items:
            name = item.get("name") or f"伏笔#{item.get('id')}"
            planted = item.get("chapter_number")
            content = str(item.get("content") or "").strip()
            soft_lines.append(f"- [{name}] 埋设章={planted} 内容：{content}")
        foreshadowing_soft_reminder_text = (
            "本章软提醒：以下伏笔尚未设置目标回收章，仅在不破坏主线节奏时酌情提及或轻推。\n"
            + "\n".join(soft_lines)
        )
    else:
        foreshadowing_soft_reminder_text = "本章无伏笔软提醒。"

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
        ("[强制执行协议]", strict_execution_protocol),
        ("[首轮命中执行法]", first_pass_hit_protocol),
        ("[世界蓝图](JSON，已裁剪)", blueprint_text),
        ("[上一章摘要]", previous_summary_text or "暂无（这是第一章）"),
        ("[章节衔接要求]", continuity_hint),
        ("[章节导演脚本](JSON)", mission_text),
        ("[检索到的剧情上下文](Markdown)", rag_chunks_text),
        ("[章节摘要上下文](Markdown)", rag_summaries_text),
        ("[本章伏笔执行清单](硬约束)", foreshadowing_contract_text),
        ("[本章伏笔提醒](软提醒)", foreshadowing_soft_reminder_text),
        ("[用户个人风格规则](优先约束)", personal_rules_compact),
        ("[当前章节目标]", f"标题：{outline_title}\n摘要：{outline_summary}\n写作要求：{writing_notes}"),
        ("[禁止角色](本章不允许提及)", forbidden_text),
        ("[字数要求]", "本章节正文字数必须控制在 2400-3000 字，3000 字是硬上限。请在心里将全章分为「开场(约600字)→发展(约1100字)→转折(约800字)→钩子(约300字)」四段，累计到约 2700 字时主动进入钩子收尾。注意：这只是心理规划，绝对不要在正文中写出「**【开场】**」「**【发展】**」等结构标记。"),
    ]
    prompt_input = "\n\n".join(f"{title}\n{content}" for title, content in prompt_sections if content)
    logger.debug(
        "章节写作提示词长度: total=%s blueprint=%s mission=%s rag_chunks=%s rag_summaries=%s rules=%s",
        len(prompt_input),
        len(blueprint_text),
        len(mission_text),
        len(rag_chunks_text),
        len(rag_summaries_text),
        len(personal_rules_compact),
    )

    # ========== 6. L3 Writer: 生成正文 ==========
    async def _generate_single_version(idx: int, version_style_hint: Optional[str] = None) -> Dict:
        """生成单个版本，支持差异化风格提示"""
        max_version_attempts = 1
        for attempt in range(1, max_version_attempts + 1):
            try:
                final_prompt_input = prompt_input
                if version_style_hint:
                    final_prompt_input += f"\n\n[版本风格提示]\n{version_style_hint}"

                generation_temperature = 0.78 if attempt == 1 else 0.72
                generation_max_tokens = 3200
                try:
                    response = await llm_service.get_llm_response(
                        system_prompt=writer_prompt,
                        conversation_history=[{"role": "user", "content": final_prompt_input}],
                        temperature=generation_temperature,
                        user_id=current_user.id,
                        timeout=600.0,
                        response_format=None,
                        max_tokens=generation_max_tokens,
                    )
                except HTTPException as exc:
                    detail_text = str(exc.detail)
                    if exc.status_code == 503 and "长度限制" in detail_text:
                        logger.warning(
                            "项目 %s 第 %s 章版本 %s 第 %s 轮空响应(length) ，放宽 max_tokens 重试一次",
                            project_id,
                            request.chapter_number,
                            idx + 1,
                            attempt,
                        )
                        response = await llm_service.get_llm_response(
                            system_prompt=writer_prompt,
                            conversation_history=[{"role": "user", "content": final_prompt_input}],
                            temperature=generation_temperature,
                            user_id=current_user.id,
                            timeout=600.0,
                            response_format=None,
                            max_tokens=3800,
                        )
                    else:
                        raise
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
                        min_chars=chapter_min_chars,
                        max_chars=chapter_hard_max_chars,
                        max_tokens=3200,
                    )

                # ========== 8. 章节执行硬约束检查（大纲 + 埋 + 收） ==========
                contract_check = await _check_chapter_execution_contract(
                    llm_service=llm_service,
                    user_id=current_user.id,
                    chapter_number=request.chapter_number,
                    generated_text=final_content,
                    outline_title=outline_title,
                    outline_summary=outline_summary,
                    must_plant_items=must_plant_items,
                    must_payoff_items=due_payoff_items,
                )
                if not contract_check["passed"]:
                    logger.info(
                        "项目 %s 第 %s 章版本 %s 第 %s 轮未满足硬约束: outline_covered=%s missing_plants=%s missing_payoffs=%s，速度优先模式直接返回",
                        project_id,
                        request.chapter_number,
                        idx + 1,
                        attempt,
                        contract_check.get("outline_covered", False),
                        len(contract_check.get("missing_plants", [])),
                        len(contract_check.get("missing_payoffs", [])),
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

                result_text = (extracted_text or final_content or "").strip()
                if _is_tail_incomplete(result_text):
                    logger.warning(
                        "项目 %s 第 %s 章版本 %s 检测到尾句疑似中断，触发尾句补全",
                        project_id,
                        request.chapter_number,
                        idx + 1,
                    )
                    result_text = await _complete_tail_sentence(
                        llm_service=llm_service,
                        text=result_text,
                        user_id=current_user.id,
                    )

                return {
                    "content": result_text,
                    "parsed_json": parsed_json,
                    "guardrail": guardrail_metadata,
                    "foreshadowing_contract": {
                        "outline_required": {
                            "title": outline_title,
                            "summary": outline_summary,
                        },
                        "required_plants": [
                            {
                                "id": item.get("id"),
                                "name": item.get("name"),
                                "chapter_number": item.get("chapter_number"),
                                "content": item.get("content"),
                            }
                            for item in must_plant_items
                        ],
                        "required_payoffs": [
                            {
                                "id": item.get("id"),
                                "name": item.get("name"),
                                "planted_chapter": item.get("chapter_number"),
                                "target_reveal_chapter": item.get("target_reveal_chapter"),
                                "content": item.get("content"),
                            }
                            for item in due_payoff_items
                        ],
                        "passed": contract_check["passed"],
                        "outline_covered": contract_check.get("outline_covered", False),
                        "missing_outline_points": contract_check.get("missing_outline_points", []),
                        "missing_plants": contract_check.get("missing_plants", []),
                        "missing_payoffs": contract_check.get("missing_payoffs", []),
                    },
                    "chapter_mission": chapter_mission,
                }
            except HTTPException:
                raise
            except Exception as exc:
                logger.exception(
                    "项目 %s 生成第 %s 章第 %s 个版本第 %s 轮时发生异常: %s",
                    project_id,
                    request.chapter_number,
                    idx + 1,
                    attempt,
                    exc,
                )
                if attempt >= max_version_attempts:
                    raise HTTPException(
                        status_code=500,
                        detail=f"生成章节第 {idx + 1} 个版本时失败: {str(exc)[:200]}"
                    )
                attempt_feedback = f"第{attempt}轮生成异常：{str(exc)[:200]}"
                continue

        raise HTTPException(status_code=500, detail=f"生成章节第 {idx + 1} 个版本失败：重试耗尽")

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

    # 字数审计日志（不做常规截断）
    for i, content in enumerate(contents):
        word_count = len(content)
        if word_count > chapter_hard_max_chars:
            logger.warning(
                "项目 %s 第 %s 章版本 %s 字数超出硬上限: %s 字（目标: %s-%s，硬上限: %s）",
                project_id,
                request.chapter_number,
                i + 1,
                word_count,
                chapter_min_chars,
                chapter_target_max_chars,
                chapter_hard_max_chars,
            )
        elif word_count < chapter_min_chars:
            logger.warning(
                "项目 %s 第 %s 章版本 %s 字数偏短: %s 字（目标: %s-%s）",
                project_id,
                request.chapter_number,
                i + 1,
                word_count,
                chapter_min_chars,
                chapter_target_max_chars,
            )
        else:
            logger.info(
                "项目 %s 第 %s 章版本 %s 字数在目标区间内: %s 字（目标: %s-%s）",
                project_id,
                request.chapter_number,
                i + 1,
                word_count,
                chapter_min_chars,
                chapter_target_max_chars,
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

    # 自动回收伏笔（选版即定稿场景）
    try:
        llm_service = LLMService(session)
        auto_resolve_result = await _auto_resolve_foreshadowings_from_chapter(
            session=session,
            llm_service=llm_service,
            project_id=project_id,
            chapter_id=chapter.id,
            chapter_number=request.chapter_number,
            chapter_text=selected_version.content,
            user_id=current_user.id,
        )
        if auto_resolve_result.get("resolved_count", 0) > 0:
            await session.commit()
    except Exception as exc:
        logger.warning(
            "选版后自动回收伏笔失败: project=%s chapter=%s err=%s",
            project_id,
            request.chapter_number,
            exc,
        )

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

        # 组装“执行校验总结”（大纲覆盖 + 本章必埋 + 本章必收）
        outline_title = f"第{request.chapter_number}章"
        outline_summary = ""
        if blueprint and blueprint.chapter_outline:
            target_outline = next(
                (o for o in blueprint.chapter_outline if o.chapter_number == request.chapter_number),
                None,
            )
            if target_outline:
                outline_title = target_outline.title or outline_title
                outline_summary = target_outline.summary or ""

        planted_stmt = (
            select(Foreshadowing)
            .where(
                Foreshadowing.project_id == project_id,
                Foreshadowing.chapter_number == request.chapter_number,
                Foreshadowing.status != "abandoned",
            )
            .order_by(Foreshadowing.id)
        )
        planted_result = await session.execute(planted_stmt)
        planted_for_current = planted_result.scalars().all()
        must_plant_items: List[Dict[str, Any]] = []
        seen_plant_contents = set()
        for fs in planted_for_current:
            content = str(fs.content or "").strip()
            if not content or content in seen_plant_contents:
                continue
            seen_plant_contents.add(content)
            must_plant_items.append(
                {
                    "id": fs.id,
                    "name": fs.name,
                    "content": content,
                    "chapter_number": fs.chapter_number,
                    "urgency": fs.urgency,
                    "keywords": fs.keywords if isinstance(fs.keywords, list) else [],
                }
            )
        must_plant_items = must_plant_items[:5]

        foreshadowing_service = ForeshadowingService(session)
        unresolved_foreshadowings = await foreshadowing_service.get_unresolved_foreshadowings(
            project_id=project_id,
            current_chapter_number=request.chapter_number,
        )
        due_payoff_items: List[Dict[str, Any]] = []
        overdue_escalation_chapters = max(1, int(settings.foreshadowing_overdue_escalation_chapters))
        for fs in unresolved_foreshadowings:
            target_chapter = fs.target_reveal_chapter
            if target_chapter is None or target_chapter > request.chapter_number:
                continue
            overdue_chapters = max(0, request.chapter_number - target_chapter)
            is_overdue_escalated = overdue_chapters >= overdue_escalation_chapters
            due_payoff_items.append(
                {
                    "id": fs.id,
                    "name": fs.name,
                    "content": fs.content,
                    "chapter_number": fs.chapter_number,
                    "target_reveal_chapter": target_chapter,
                    "urgency": fs.urgency,
                    "overdue_chapters": overdue_chapters,
                    "is_overdue_escalated": is_overdue_escalated,
                    "keywords": fs.keywords if isinstance(fs.keywords, list) else [],
                }
            )
        due_payoff_items.sort(
            key=lambda item: (
                -(1 if item.get("is_overdue_escalated") else 0),
                item.get("target_reveal_chapter") if item.get("target_reveal_chapter") is not None else 10**9,
                -(item.get("urgency") or 0),
                item.get("chapter_number") or 0,
            )
        )
        due_payoff_items = due_payoff_items[:3]

        execution_summary: Dict[str, Any] = {
            "outline": {"title": outline_title, "summary": outline_summary},
            "required_plants": [
                {
                    "id": item.get("id"),
                    "name": item.get("name"),
                    "content": item.get("content"),
                }
                for item in must_plant_items
            ],
            "required_payoffs": [
                {
                    "id": item.get("id"),
                    "name": item.get("name"),
                    "content": item.get("content"),
                    "target_reveal_chapter": item.get("target_reveal_chapter"),
                }
                for item in due_payoff_items
            ],
            "version_results": {},
        }
        for idx, version in enumerate(versions_to_evaluate, start=1):
            check = await _check_chapter_execution_contract(
                llm_service=llm_service,
                user_id=current_user.id,
                chapter_number=request.chapter_number,
                generated_text=version.content or "",
                outline_title=outline_title,
                outline_summary=outline_summary,
                must_plant_items=must_plant_items,
                must_payoff_items=due_payoff_items,
            )
            execution_summary["version_results"][f"version{idx}"] = {
                "passed": bool(check.get("passed", False)),
                "outline_covered": bool(check.get("outline_covered", False)),
                "missing_outline_points": check.get("missing_outline_points", []),
                "missing_plants": [
                    {"id": item.get("id"), "name": item.get("name"), "content": item.get("content")}
                    for item in check.get("missing_plants", [])
                ],
                "missing_payoffs": [
                    {"id": item.get("id"), "name": item.get("name"), "content": item.get("content")}
                    for item in check.get("missing_payoffs", [])
                ],
            }

        # 解析评审结果以获取最佳版本索引
        try:
            evaluation_data = json.loads(evaluation_text)
            if isinstance(evaluation_data, dict):
                evaluation_data["execution_summary"] = execution_summary
                evaluation_text = json.dumps(evaluation_data, ensure_ascii=False)
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
            llm_service = LLMService(session)
            style_rule_service = UserStyleRuleService(session)

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
                saved = await style_rule_service.add_rule(
                    user_id=current_user.id,
                    project_id=project_id,
                    rule_type="outline_generation",
                    content=extracted_rule.strip(),
                    source="update_outline_ai_message",
                )
                if saved:
                    logger.info("已将 AI 建议提炼为个人规则: user=%s project=%s", current_user.id, project_id)
                else:
                    logger.warning("个人规则保存失败（可能为空或重复）: user=%s project=%s", current_user.id, project_id)
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


@router.get("/novels/{project_id}/chapters/{chapter_number}/status", response_model=ChapterRuntimeStatus)
async def get_chapter_runtime_status(
    project_id: str,
    chapter_number: int,
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> ChapterRuntimeStatus:
    novel_service = NovelService(session)
    return await novel_service.get_chapter_runtime_status(project_id, current_user.id, chapter_number)


@router.get("/style-library", response_model=WritingStyleLibrary)
async def get_writing_style_library(
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> WritingStyleLibrary:
    style_rule_service = UserStyleRuleService(session)
    outline_text = await style_rule_service.get_account_rule_text_by_type(
        user_id=current_user.id,
        rule_type="outline_generation",
    )
    chapter_text = await style_rule_service.get_account_rule_text_by_type(
        user_id=current_user.id,
        rule_type="chapter_writing",
    )
    return WritingStyleLibrary(outline_text=outline_text, chapter_text=chapter_text)


@router.put("/style-library", response_model=WritingStyleLibrary)
async def update_writing_style_library(
    request: UpdateWritingStyleLibraryRequest,
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> WritingStyleLibrary:
    style_rule_service = UserStyleRuleService(session)
    outline_text = await style_rule_service.set_account_rule_text_by_type(
        user_id=current_user.id,
        rule_type="outline_generation",
        content=request.outline_text,
        source="style_library_manual",
    )
    chapter_text = await style_rule_service.set_account_rule_text_by_type(
        user_id=current_user.id,
        rule_type="chapter_writing",
        content=request.chapter_text,
        source="style_library_manual",
    )

    return WritingStyleLibrary(outline_text=outline_text, chapter_text=chapter_text)


@router.post("/novels/{project_id}/chapters/outline", response_model=NovelProjectSchema)
async def generate_chapters_outline(
    project_id: str,
    request: GenerateOutlineRequest,
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> NovelProjectSchema:
    novel_service = NovelService(session)
    await novel_service.ensure_project_owner(project_id, current_user.id)

    # 兼容旧接口：统一走预览 + 确认流程，避免两套大纲生成逻辑长期分叉
    preview = await preview_chapters_outline(
        project_id=project_id,
        request=OutlinePreviewRequest(
            start_chapter=request.start_chapter,
            num_chapters=request.num_chapters,
            total_chapters=request.total_chapters,
            user_hint=request.user_hint,
        ),
        session=session,
        current_user=current_user,
    )
    return await confirm_chapters_outline(
        project_id=project_id,
        request=OutlineConfirmRequest(
            start_chapter=request.start_chapter,
            preview_data=preview.model_dump(),
        ),
        session=session,
        current_user=current_user,
    )

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
            location_service = KeyLocationService(session)
            await location_service.upsert_locations(project_id, new_locations)
            logger.info(f"新增地点（写入 key_locations 表）: {len(new_locations)} 条")

        # 处理新势力
        new_factions = data.get("new_factions", [])
        if new_factions and project_schema.blueprint:
            faction_service = FactionService(session, prompt_service)
            await faction_service.upsert_factions(project_id, new_factions)
            logger.info(f"新增势力（写入 factions 表）: {len(new_factions)} 条")

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
            for raw_plant in plant_list:
                plant = _normalize_foreshadowing_entry(raw_plant)
                if not plant:
                    continue
                try:
                    await foreshadowing_service.create_foreshadowing(
                        project_id=project_id,
                        chapter_id=chapter.id,
                        chapter_number=chapter_number,
                        content=plant["content"],
                        foreshadowing_type="hint",
                        keywords=plant.get("keywords"),
                        is_manual=False,
                        ai_confidence=0.8,
                        target_reveal_chapter=plant.get("target_reveal_chapter"),
                        importance=plant.get("importance"),
                    )
                    logger.info(
                        "新增伏笔: project=%s chapter=%s target=%s content=%s...",
                        project_id,
                        chapter_number,
                        plant.get("target_reveal_chapter"),
                        plant["content"][:50],
                    )
                except Exception as fe:
                    logger.warning(f"创建伏笔失败: {fe}")

            # 处理回收的伏笔
            for raw_payoff in payoff_list:
                payoff = _normalize_foreshadowing_entry(raw_payoff)
                if not payoff:
                    continue
                payoff_content = payoff["content"]
                try:
                    unresolved_foreshadowings = await foreshadowing_service.get_unresolved_foreshadowings(
                        project_id, chapter_number
                    )
                    matched = None
                    payoff_id = payoff.get("foreshadowing_id")
                    if payoff_id is not None:
                        matched = next((fs for fs in unresolved_foreshadowings if fs.id == payoff_id), None)
                    if not matched:
                        for fs in unresolved_foreshadowings:
                            if payoff_content in fs.content or fs.content in payoff_content:
                                matched = fs
                                break

                    if matched:
                        matched.target_reveal_chapter = chapter_number
                        if payoff_content:
                            previous_note = (matched.author_note or "").strip()
                            schedule_note = f"[计划回收章]: 第{chapter_number}章"
                            matched.author_note = (
                                f"{previous_note}\n{schedule_note}".strip()
                                if previous_note
                                else schedule_note
                            )
                        logger.info(
                            "伏笔回收计划已更新: project=%s fs=%s target_chapter=%s content=%s...",
                            project_id,
                            matched.id,
                            chapter_number,
                            payoff_content[:50],
                        )
                    else:
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
    style_rule_service = UserStyleRuleService(session)

    project = await novel_service.ensure_project_owner(project_id, current_user.id)
    personal_rules = await style_rule_service.get_effective_rules(
        user_id=current_user.id,
        project_id=project_id,
        rule_types=["general", "outline_generation"],
        limit=20,
    )
    personal_rules_text = _format_personal_rules_section(personal_rules)

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
[用户个人风格规则]
{personal_rules_text}
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
[用户个人风格规则]
{personal_rules_text}
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

            for raw_plant in plant_list:
                plant = _normalize_foreshadowing_entry(raw_plant)
                if not plant:
                    continue
                foreshadowing_plants.append({
                    "chapter_number": chapter_number,
                    "content": plant["content"],
                    "target_reveal_chapter": plant.get("target_reveal_chapter"),
                    "importance": plant.get("importance"),
                    "keywords": plant.get("keywords", []),
                })

            for raw_payoff in payoff_list:
                payoff = _normalize_foreshadowing_entry(raw_payoff)
                if not payoff:
                    continue
                foreshadowing_payoffs.append({
                    "chapter_number": chapter_number,
                    "content": payoff["content"],
                    "foreshadowing_id": payoff.get("foreshadowing_id"),
                    "keywords": payoff.get("keywords", []),
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
    prompt_service = PromptService(session)

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

        # 处理新地点和新势力（统一写入独立表，不再写 world_setting JSON）
        new_locations = preview_data.get("new_locations", [])
        new_factions = preview_data.get("new_factions", [])

        if (new_locations or new_factions) and project_schema.blueprint:
            location_service = KeyLocationService(session)
            if new_locations:
                await location_service.upsert_locations(project_id, new_locations)
                logger.info(f"新增地点（写入 key_locations 表）: {len(new_locations)} 条")

            faction_service = FactionService(session, prompt_service)
            if new_factions:
                await faction_service.upsert_factions(project_id, new_factions)
                logger.info(f"新增势力（写入 factions 表）: {len(new_factions)} 条")

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

                target_reveal = plant.get("target_reveal_chapter")
                try:
                    target_reveal = int(target_reveal) if target_reveal is not None else None
                except (TypeError, ValueError):
                    target_reveal = None

                fs_importance = plant.get("importance")
                if isinstance(fs_importance, str):
                    fs_importance = fs_importance.strip().lower()
                if fs_importance not in {"major", "minor", "subtle"}:
                    fs_importance = None

                keywords = plant.get("keywords")
                if not isinstance(keywords, list):
                    keywords = []
                keywords = [str(k).strip() for k in keywords if str(k).strip()]

                await foreshadowing_service.create_foreshadowing(
                    project_id=project_id,
                    chapter_id=chapter.id,
                    chapter_number=chapter_number,
                    content=content,
                    foreshadowing_type="hint",
                    keywords=keywords,
                    is_manual=False,
                    ai_confidence=0.8,
                    target_reveal_chapter=target_reveal,
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
                payoff_id = payoff.get("foreshadowing_id")
                try:
                    payoff_id = int(payoff_id) if payoff_id is not None else None
                except (TypeError, ValueError):
                    payoff_id = None
                if payoff_id is not None:
                    matched = next((fs for fs in unresolved_foreshadowings if fs.id == payoff_id), None)
                for fs in unresolved_foreshadowings:
                    if matched:
                        break
                    if content in fs.content or fs.content in content:
                        matched = fs
                        break

                if matched:
                    matched.target_reveal_chapter = chapter_number
                    if content:
                        previous_note = (matched.author_note or "").strip()
                        schedule_note = f"[计划回收章]: 第{chapter_number}章"
                        matched.author_note = (
                            f"{previous_note}\n{schedule_note}".strip()
                            if previous_note
                            else schedule_note
                        )
                    logger.info(
                        "伏笔回收计划已更新: project=%s fs=%s target_chapter=%s content=%s...",
                        project_id,
                        matched.id,
                        chapter_number,
                        content[:50],
                    )
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
