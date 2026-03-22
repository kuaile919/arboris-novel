# AIMETA P=LLM服务_大模型调用封装|R=API调用_流式生成|NR=不含业务逻辑|E=LLMService|X=internal|A=服务类|D=openai,anthropic,httpx|S=net|RD=./README.ai
import asyncio
import logging
import os
import time
from typing import Any, Dict, List, Literal, Optional

# 模块级配置缓存，TTL 5分钟，进程重启自动清空
_config_cache: Dict[str, tuple] = {}
_CONFIG_TTL = 300

import httpx
from fastapi import HTTPException, status
from openai import APIConnectionError, APITimeoutError, AsyncOpenAI, InternalServerError

from ..core.config import settings
from ..repositories.llm_config_repository import LLMConfigRepository
from ..repositories.system_config_repository import SystemConfigRepository
from ..repositories.user_repository import UserRepository
from ..services.admin_setting_service import AdminSettingService
from ..services.prompt_service import PromptService
from ..services.usage_service import UsageService
from ..utils.llm_tool import ChatMessage, LLMClient

logger = logging.getLogger(__name__)

try:  # pragma: no cover - 运行环境未安装时兼容
    from ollama import AsyncClient as OllamaAsyncClient
except ImportError:  # pragma: no cover - Ollama 为可选依赖
    OllamaAsyncClient = None


class LLMService:
    """封装与大模型交互的所有逻辑，包括配额控制与配置选择。"""

    def __init__(self, session):
        self.session = session
        self.llm_repo = LLMConfigRepository(session)
        self.system_config_repo = SystemConfigRepository(session)
        self.user_repo = UserRepository(session)
        self.admin_setting_service = AdminSettingService(session)
        self.usage_service = UsageService(session)
        self._embedding_dimensions: Dict[str, int] = {}

    async def get_llm_response(
        self,
        system_prompt: str,
        conversation_history: List[Dict[str, str]],
        *,
        temperature: float = 0.7,
        user_id: Optional[int] = None,
        timeout: float = 300.0,
        response_format: Optional[str] = "json_object",
        max_tokens: Optional[int] = None,
        top_p: Optional[float] = None,
    ) -> str:
        messages = [{"role": "system", "content": system_prompt}, *conversation_history]
        return await self._stream_and_collect(
            messages,
            temperature=temperature,
            user_id=user_id,
            timeout=timeout,
            response_format=response_format,
            max_tokens=max_tokens,
            top_p=top_p,
        )

    async def generate(
        self,
        prompt: str,
        *,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        user_id: Optional[int] = None,
        timeout: float = 300.0,
        max_tokens: Optional[int] = None,
        response_format: Optional[str] = None,
        top_p: Optional[float] = None,
    ) -> str:
        """兼容旧版接口的文本生成入口，统一走 get_llm_response。"""
        return await self.get_llm_response(
            system_prompt=system_prompt or "你是一位专业写作助手。",
            conversation_history=[{"role": "user", "content": prompt}],
            temperature=temperature,
            user_id=user_id,
            timeout=timeout,
            response_format=response_format,
            max_tokens=max_tokens,
            top_p=top_p,
        )

    async def get_summary(
        self,
        chapter_content: str,
        *,
        temperature: float = 0.2,
        user_id: Optional[int] = None,
        timeout: float = 180.0,
        system_prompt: Optional[str] = None,
        max_retries: int = 3,
    ) -> str:
        """生成章节摘要，支持重试机制"""
        if not system_prompt:
            prompt_service = PromptService(self.session)
            system_prompt = await prompt_service.get_prompt("extraction")
        if not system_prompt:
            logger.error("未配置名为 'extraction' 的摘要提示词，无法生成章节摘要")
            raise HTTPException(status_code=500, detail="未配置摘要提示词，请联系管理员配置 'extraction' 提示词")

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": chapter_content},
        ]

        # 重试机制
        last_error = None
        for attempt in range(max_retries):
            try:
                return await self._stream_and_collect(
                    messages,
                    temperature=temperature,
                    user_id=user_id,
                    timeout=timeout
                )
            except HTTPException as exc:
                last_error = exc
                if exc.status_code == 503 and attempt < max_retries - 1:
                    # 网络错误，等待后重试
                    wait_time = 2 ** attempt  # 指数退避：1s, 2s, 4s
                    logger.warning(
                        "摘要生成失败，%d秒后重试 (尝试 %d/%d): %s",
                        wait_time,
                        attempt + 1,
                        max_retries,
                        exc.detail
                    )
                    await asyncio.sleep(wait_time)
                    continue
                raise

        # 所有重试都失败
        if last_error:
            raise last_error
        raise HTTPException(status_code=500, detail="摘要生成失败")

    async def _stream_and_collect(
        self,
        messages: List[Dict[str, str]],
        *,
        temperature: float,
        user_id: Optional[int],
        timeout: float,
        response_format: Optional[str] = None,
        max_tokens: Optional[int] = None,
        top_p: Optional[float] = None,
    ) -> str:
        config = await self._resolve_llm_config(user_id)
        client = LLMClient(
            api_key=config["api_key"],
            base_url=config.get("base_url"),
            provider=config.get("provider"),
        )

        chat_messages = [ChatMessage(role=msg["role"], content=msg["content"]) for msg in messages]

        full_response = ""
        finish_reason = None

        logger.info(
            "Streaming LLM response: provider=%s model=%s user_id=%s messages=%d",
            config.get("provider"),
            config.get("model"),
            user_id,
            len(messages),
        )

        try:
            async for part in client.stream_chat(
                messages=chat_messages,
                model=config.get("model"),
                temperature=temperature,
                timeout=int(timeout),
                response_format=response_format if config.get("provider") == "openai" else None,
                max_tokens=max_tokens,
                top_p=top_p,
            ):
                if part.get("content"):
                    full_response += part["content"]
                if part.get("finish_reason"):
                    finish_reason = part["finish_reason"]
        except InternalServerError as exc:
            detail = "AI 服务内部错误，请稍后重试"
            response = getattr(exc, "response", None)
            if response is not None:
                try:
                    payload = response.json()
                    error_data = payload.get("error", {}) if isinstance(payload, dict) else {}
                    detail = error_data.get("message_zh") or error_data.get("message") or detail
                except Exception:
                    detail = str(exc) or detail
            else:
                detail = str(exc) or detail
            logger.error(
                "LLM stream internal error: provider=%s model=%s user_id=%s detail=%s",
                config.get("provider"),
                config.get("model"),
                user_id,
                detail,
                exc_info=exc,
            )
            raise HTTPException(status_code=503, detail=detail)
        except (httpx.RemoteProtocolError, httpx.ReadTimeout, APIConnectionError, APITimeoutError) as exc:
            if isinstance(exc, httpx.RemoteProtocolError):
                detail = "AI 服务连接被意外中断，请稍后重试"
            elif isinstance(exc, (httpx.ReadTimeout, APITimeoutError)):
                detail = "AI 服务响应超时，请稍后重试"
            else:
                detail = "无法连接到 AI 服务，请稍后重试"
            logger.error(
                "LLM stream failed: provider=%s model=%s user_id=%s detail=%s",
                config.get("provider"),
                config.get("model"),
                user_id,
                detail,
                exc_info=exc,
            )
            raise HTTPException(status_code=503, detail=detail) from exc
        except Exception as exc:
            # 处理 Anthropic 特定错误
            error_type = type(exc).__name__
            error_msg = str(exc)
            logger.error(
                "LLM stream failed: provider=%s model=%s user_id=%s error_type=%s error=%s",
                config.get("provider"),
                config.get("model"),
                user_id,
                error_type,
                error_msg,
                exc_info=exc,
            )
            if "api_key" in error_msg.lower() or "authentication" in error_msg.lower():
                raise HTTPException(status_code=401, detail="API Key 无效或未配置")
            raise HTTPException(status_code=503, detail=f"AI 服务错误: {error_msg}")

        logger.debug(
            "LLM response collected: provider=%s model=%s user_id=%s finish_reason=%s preview=%s",
            config.get("provider"),
            config.get("model"),
            user_id,
            finish_reason,
            full_response[:500],
        )

        if finish_reason == "length" or finish_reason == "max_tokens":
            logger.warning(
                "LLM response truncated by token limit: provider=%s model=%s user_id=%s response_length=%d — returning partial content",
                config.get("provider"),
                config.get("model"),
                user_id,
                len(full_response),
            )
            # Return partial content rather than raising — callers can use what was generated

        if not full_response:
            logger.error(
                "LLM returned empty response: provider=%s model=%s user_id=%s finish_reason=%s",
                config.get("provider"),
                config.get("model"),
                user_id,
                finish_reason,
            )
            raise HTTPException(
                status_code=500,
                detail=f"AI 未返回有效内容（结束原因: {finish_reason or '未知'}），请稍后重试或联系管理员"
            )

        await self.usage_service.increment("api_request_count")
        logger.info(
            "LLM response success: provider=%s model=%s user_id=%s chars=%d",
            config.get("provider"),
            config.get("model"),
            user_id,
            len(full_response),
        )
        return full_response

    async def _resolve_llm_config(self, user_id: Optional[int]) -> Dict[str, Optional[str]]:
        logger.debug("[llm-config] resolve called, user_id=%s", user_id)

        # 检查用户是否有自定义配置
        if user_id:
            config = await self.llm_repo.get_by_user(user_id)
            logger.debug("[llm-config] user custom config exists=%s", bool(config))
            if config and config.llm_provider_api_key:
                return {
                    "api_key": config.llm_provider_api_key,
                    "base_url": config.llm_provider_url,
                    "model": config.llm_provider_model,
                    "provider": getattr(config, "llm_provider", settings.llm_provider),
                }

        # 检查每日使用次数限制
        if user_id:
            await self._enforce_daily_limit(user_id)

        # 根据 LLM 提供方获取配置
        provider = await self._get_config_value("llm_provider") or settings.llm_provider
        logger.debug("[llm-config] provider from config=%s", provider)

        if provider == "anthropic":
            # 智谱 BigModel (Zhipu) 配置
            db_zhipu_api_key = await self._get_config_value("zhipu_api_key")
            db_zhipu_base_url = await self._get_config_value("zhipu_base_url")
            db_zhipu_model = await self._get_config_value("zhipu_model_name")

            logger.debug("[llm-config] DB zhipu config: api_key=%s, base_url=%s, model=%s",
                db_zhipu_api_key[:20] + "..." if db_zhipu_api_key else None,
                db_zhipu_base_url, db_zhipu_model)

            api_key = db_zhipu_api_key or settings.zhipu_api_key
            base_url = db_zhipu_base_url or settings.zhipu_base_url
            model = db_zhipu_model or settings.zhipu_model_name

            logger.debug("[llm-config] final zhipu config: api_key=%s, base_url=%s, model=%s",
                api_key[:20] + "..." if api_key else None, base_url, model)
        else:
            api_key = await self._get_config_value("openai_api_key") or settings.openai_api_key
            base_url = await self._get_config_value("openai_base_url") or str(settings.openai_base_url) if settings.openai_base_url else None
            model = await self._get_config_value("openai_model_name") or settings.openai_model_name

        if not api_key:
            logger.error("未配置默认 LLM API Key，且用户 %s 未设置自定义 API Key", user_id)
            raise HTTPException(
                status_code=500,
                detail=f"未配置默认 {provider.upper()} API Key，请联系管理员配置系统默认 API Key 或在个人设置中配置自定义 API Key"
            )

        return {"api_key": api_key, "base_url": base_url, "model": model, "provider": provider}

    async def get_embedding(
        self,
        text: str,
        *,
        user_id: Optional[int] = None,
        model: Optional[str] = None,
    ) -> List[float]:
        """生成文本向量，用于章节 RAG 检索，支持 openai 与 ollama 双提供方。"""
        provider = await self._get_config_value("embedding.provider") or "openai"
        default_model = (
            await self._get_config_value("ollama.embedding_model") or "nomic-embed-text:latest"
            if provider == "ollama"
            else await self._get_config_value("embedding.model") or "text-embedding-3-large"
        )
        target_model = model or default_model

        if provider == "ollama":
            if OllamaAsyncClient is None:
                logger.error("未安装 ollama 依赖，无法调用本地嵌入模型。")
                raise HTTPException(status_code=500, detail="缺少 Ollama 依赖，请先安装 ollama 包。")

            base_url = (
                await self._get_config_value("ollama.embedding_base_url")
                or await self._get_config_value("embedding.base_url")
            )
            logger.info(
                "[embedding] provider=ollama model=%s base_url=%s user_id=%s",
                target_model,
                base_url,
                user_id,
            )
            client = OllamaAsyncClient(host=base_url)
            try:
                response = await client.embeddings(model=target_model, prompt=text)
            except Exception as exc:  # pragma: no cover - 本地服务调用失败
                logger.error(
                    "Ollama 嵌入请求失败: model=%s base_url=%s error=%s",
                    target_model,
                    base_url,
                    exc,
                    exc_info=True,
                )
                return []
            embedding: Optional[List[float]]
            if isinstance(response, dict):
                embedding = response.get("embedding")
            else:
                embedding = getattr(response, "embedding", None)
            if not embedding:
                logger.warning("Ollama 返回空向量: model=%s", target_model)
                return []
            if not isinstance(embedding, list):
                embedding = list(embedding)
        else:
            embedding_api_key = await self._get_config_value("embedding.api_key")
            embedding_base_url = await self._get_config_value("embedding.base_url")
            config: Dict[str, Optional[str]] = {}
            if not embedding_api_key:
                config = await self._resolve_llm_config(user_id)
            api_key = embedding_api_key or config.get("api_key")
            base_url = embedding_base_url or config.get("base_url")
            logger.info(
                "[embedding] provider=openai-compatible model=%s base_url=%s user_id=%s",
                target_model,
                base_url,
                user_id,
            )
            client = AsyncOpenAI(api_key=api_key, base_url=base_url)
            try:
                response = await client.embeddings.create(
                    input=text,
                    model=target_model,
                )
            except Exception as exc:  # pragma: no cover - 网络或鉴权失败
                logger.error(
                    "OpenAI 嵌入请求失败: model=%s base_url=%s user_id=%s error=%s",
                    target_model,
                    base_url,
                    user_id,
                    exc,
                    exc_info=True,
                )
                return []
            if not response.data:
                logger.warning("OpenAI 嵌入请求返回空数据: model=%s user_id=%s", target_model, user_id)
                return []
            embedding = response.data[0].embedding

        if not isinstance(embedding, list):
            embedding = list(embedding)

        dimension = len(embedding)
        if not dimension:
            vector_size_str = await self._get_config_value("embedding.model_vector_size")
            if vector_size_str:
                dimension = int(vector_size_str)
        if dimension:
            self._embedding_dimensions[target_model] = dimension
        return embedding

    async def get_embedding_dimension(self, model: Optional[str] = None) -> Optional[int]:
        """获取嵌入向量维度，优先返回缓存结果，其次读取配置。"""
        provider = await self._get_config_value("embedding.provider") or "openai"
        default_model = (
            await self._get_config_value("ollama.embedding_model") or "nomic-embed-text:latest"
            if provider == "ollama"
            else await self._get_config_value("embedding.model") or "text-embedding-3-large"
        )
        target_model = model or default_model
        if target_model in self._embedding_dimensions:
            return self._embedding_dimensions[target_model]
        vector_size_str = await self._get_config_value("embedding.model_vector_size")
        return int(vector_size_str) if vector_size_str else None

    async def _enforce_daily_limit(self, user_id: int) -> None:
        limit_str = await self.admin_setting_service.get("daily_request_limit", "100")
        limit = int(limit_str or 10)
        used = await self.user_repo.get_daily_request(user_id)
        if used >= limit:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="今日请求次数已达上限，请明日再试或设置自定义 API Key。",
            )
        await self.user_repo.increment_daily_request(user_id)
        await self.session.commit()

    async def _get_config_value(self, key: str) -> Optional[str]:
        now = time.monotonic()
        if key in _config_cache:
            value, cached_at = _config_cache[key]
            if now - cached_at < _CONFIG_TTL:
                return value

        record = await self.system_config_repo.get_by_key(key)
        value = record.value if record else os.getenv(key.upper().replace(".", "_"))
        _config_cache[key] = (value, now)
        return value
