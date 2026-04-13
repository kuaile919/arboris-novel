from __future__ import annotations

import asyncio
import json
import os
from datetime import timedelta
from typing import Any, Optional

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

from ..core.config import settings


class MiniMaxMCPError(RuntimeError):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class MiniMaxMCPService:
    def __init__(self) -> None:
        self._api_key = settings.minimax_api_key
        self._api_host = settings.minimax_api_host
        self._command = settings.minimax_mcp_command
        self._package = settings.minimax_mcp_server_package
        self._timeout_seconds = settings.minimax_mcp_timeout_seconds

    @property
    def enabled(self) -> bool:
        return bool(self._api_key and self._api_host and self._command and self._package)

    async def web_search(self, query: str) -> dict[str, Any]:
        if not self.enabled:
            raise MiniMaxMCPError("MiniMax MCP 未配置，无法执行搜索降级")

        params = StdioServerParameters(
            command=self._command,
            args=["--from", self._package, self._package],
            env={
                **os.environ,
                "MINIMAX_API_KEY": self._api_key or "",
                "MINIMAX_API_HOST": self._api_host,
                "FASTMCP_LOG_LEVEL": "ERROR",
            },
        )

        try:
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    result = await session.call_tool(
                        "web_search",
                        {"query": query},
                        read_timeout_seconds=timedelta(seconds=self._timeout_seconds),
                    )
        except Exception as exc:  # pragma: no cover - 外部 mcp 服务异常
            raise MiniMaxMCPError(f"MiniMax MCP 调用失败：{exc}") from exc

        parsed = self._parse_call_tool_result(result)
        if not isinstance(parsed, dict):
            raise MiniMaxMCPError("MiniMax MCP 返回了无法识别的数据结构")
        return parsed

    @staticmethod
    def _parse_call_tool_result(result: Any) -> dict[str, Any]:
        structured = getattr(result, "structuredContent", None)
        if isinstance(structured, dict):
            text = structured.get("text")
            if isinstance(text, str) and text.strip():
                try:
                    return json.loads(text)
                except json.JSONDecodeError:
                    pass

        content = getattr(result, "content", None)
        if isinstance(content, list):
            for item in content:
                text = str(getattr(item, "text", "") or "").strip()
                if not text:
                    continue
                try:
                    return json.loads(text)
                except json.JSONDecodeError:
                    continue

        return {}


__all__ = ["MiniMaxMCPService", "MiniMaxMCPError"]
