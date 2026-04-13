# -*- coding: utf-8 -*-
# AIMETA P=LLM工具_大模型调用辅助|R=请求构建_响应解析|NR=不含业务逻辑|E=LLMTool|X=internal|A=工具类|D=httpx,anthropic|S=net|RD=./README.ai
"""多提供方 LLM 工具封装，支持 OpenAI 和 Anthropic。"""

import os
from dataclasses import asdict, dataclass
from typing import AsyncGenerator, Dict, List, Literal, Optional, Union

from openai import AsyncOpenAI

from ..core.config import settings


@dataclass
class ChatMessage:
    role: str
    content: str

    def to_dict(self) -> Dict[str, str]:
        return asdict(self)


class LLMClient:
    """异步流式调用封装，支持 OpenAI 和 Anthropic SDK。"""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        provider: Optional[Literal["openai", "anthropic"]] = None,
    ):
        self.provider = provider or settings.llm_provider

        if self.provider == "anthropic":
            self._init_anthropic(api_key, base_url)
        else:
            self._init_openai(api_key, base_url)

    def _init_anthropic(self, api_key: Optional[str], base_url: Optional[str]) -> None:
        """初始化智谱 BigModel (Zhipu) 客户端。"""
        try:
            from anthropic import AsyncAnthropic
        except ImportError as exc:
            raise ImportError("请安装 anthropic 包: pip install anthropic") from exc

        # 使用 Zhipu (智谱 BigModel) 配置
        import logging
        logger = logging.getLogger(__name__)
        logger.info("[LLMClient] 初始化智谱客户端: api_key=%s, base_url=%s, model=%s",
            (api_key or settings.zhipu_api_key or os.environ.get("ZHIPU_API_KEY"))[:20] + "...",
            base_url or settings.zhipu_base_url,
            settings.zhipu_model_name or "glm-5")

        key = api_key or settings.zhipu_api_key or os.environ.get("ZHIPU_API_KEY")
        if not key:
            raise ValueError("缺少 ZHIPU_API_KEY 配置，请在数据库或环境变量中补全。")

        client_kwargs: Dict = {"api_key": key}
        if base_url or settings.zhipu_base_url:
            client_kwargs["base_url"] = base_url or settings.zhipu_base_url

        self._client = AsyncAnthropic(**client_kwargs)
        self._default_model = settings.zhipu_model_name or "glm-5"

    def _init_openai(self, api_key: Optional[str], base_url: Optional[str]) -> None:
        """初始化 OpenAI 客户端。"""
        key = api_key or settings.openai_api_key or os.environ.get("OPENAI_API_KEY")
        if not key:
            raise ValueError("缺少 OPENAI_API_KEY 配置，请在数据库或环境变量中补全。")

        resolved_base_url = (
            base_url
            or (str(settings.openai_base_url) if settings.openai_base_url else None)
            or os.environ.get("OPENAI_API_BASE_URL")
            or os.environ.get("OPENAI_API_BASE")
        )

        self._client = AsyncOpenAI(
            api_key=key,
            base_url=resolved_base_url,
        )
        self._default_model = settings.openai_model_name or "gpt-4o-mini"

    async def stream_chat(
        self,
        messages: List[ChatMessage],
        model: Optional[str] = None,
        response_format: Optional[str] = None,
        temperature: Optional[float] = None,
        top_p: Optional[float] = None,
        max_tokens: Optional[int] = None,
        timeout: int = 120,
        **kwargs,
    ) -> AsyncGenerator[Dict[str, Optional[str]], None]:
        if self.provider == "anthropic":
            async for chunk in self._stream_anthropic(
                messages=messages,
                model=model,
                temperature=temperature,
                top_p=top_p,
                max_tokens=max_tokens,
                timeout=timeout,
                **kwargs,
            ):
                yield chunk
        else:
            async for chunk in self._stream_openai(
                messages=messages,
                model=model,
                response_format=response_format,
                temperature=temperature,
                top_p=top_p,
                max_tokens=max_tokens,
                timeout=timeout,
                **kwargs,
            ):
                yield chunk

    async def _stream_anthropic(
        self,
        messages: List[ChatMessage],
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        top_p: Optional[float] = None,
        max_tokens: Optional[int] = None,
        timeout: int = 120,
        **kwargs,
    ) -> AsyncGenerator[Dict[str, Optional[str]], None]:
        """Anthropic 流式调用。"""
        import logging
        logger = logging.getLogger(__name__)

        # 分离 system 消息和对话消息
        system_prompt = None
        chat_messages = []

        for msg in messages:
            if msg.role == "system":
                system_prompt = msg.content
            else:
                chat_messages.append({"role": msg.role, "content": msg.content})

        # 构建请求参数
        request_params: Dict = {
            "model": model or self._default_model,
            "messages": chat_messages,
            "max_tokens": max_tokens or 4096,
        }

        if system_prompt:
            request_params["system"] = system_prompt
        if temperature is not None:
            request_params["temperature"] = temperature
        if top_p is not None:
            request_params["top_p"] = top_p

        # 设置超时
        self._client.timeout = timeout

        # 详细日志
        logger.info("[LLMClient] _stream_anthropic 开始调用")
        logger.info("[LLMClient] model=%s, base_url=%s", request_params["model"], getattr(self._client, 'base_url', 'N/A'))
        logger.info("[LLMClient] messages_count=%d, max_tokens=%d", len(chat_messages), request_params["max_tokens"])
        logger.debug("[LLMClient] request_params=%s", request_params)

        try:
            async with self._client.messages.stream(**request_params) as stream:
                async for text in stream.text_stream:
                    yield {"content": text, "finish_reason": None}

                # 获取最终响应以确定结束原因
                final_message = await stream.get_final_message()
                logger.info("[LLMClient] _stream_anthropic 完成, stop_reason=%s", final_message.stop_reason)
                yield {"content": None, "finish_reason": final_message.stop_reason}
        except Exception as e:
            logger.error("[LLMClient] _stream_anthropic 异常: %s, type=%s", str(e), type(e).__name__)
            logger.error("[LLMClient] 异常详情", exc_info=True)
            raise

    async def _stream_openai(
        self,
        messages: List[ChatMessage],
        model: Optional[str] = None,
        response_format: Optional[str] = None,
        temperature: Optional[float] = None,
        top_p: Optional[float] = None,
        max_tokens: Optional[int] = None,
        timeout: int = 120,
        **kwargs,
    ) -> AsyncGenerator[Dict[str, Optional[str]], None]:
        """OpenAI 流式调用。"""
        payload = {
            "model": model or self._default_model,
            "messages": [msg.to_dict() for msg in messages],
            "stream": True,
            "timeout": timeout,
            **kwargs,
        }
        if response_format:
            payload["response_format"] = {"type": response_format}
        if temperature is not None:
            payload["temperature"] = temperature
        if top_p is not None:
            payload["top_p"] = top_p
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens

        stream = await self._client.chat.completions.create(**payload)
        async for chunk in stream:
            if not chunk.choices:
                continue
            choice = chunk.choices[0]
            yield {
                "content": choice.delta.content,
                "finish_reason": choice.finish_reason,
            }
