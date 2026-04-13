from __future__ import annotations

import hashlib
import hmac
import json
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Iterable, Literal, Optional, Sequence
import asyncio
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen

import httpx
from fastapi import UploadFile

from ..core.config import settings
from .minimax_mcp_service import MiniMaxMCPError, MiniMaxMCPService


IMA_OPENAPI_BASE_PATH = "/openapi/wiki/v1"
IMA_CREDENTIAL_DIR = Path.home() / ".config" / "ima"

MB = 1024 * 1024


@dataclass(frozen=True)
class SupportedFileType:
    media_type: int
    content_type: str
    max_size: int


SUPPORTED_FILE_TYPES: dict[str, SupportedFileType] = {
    "pdf": SupportedFileType(media_type=1, content_type="application/pdf", max_size=200 * MB),
    "doc": SupportedFileType(media_type=3, content_type="application/msword", max_size=200 * MB),
    "docx": SupportedFileType(
        media_type=3,
        content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        max_size=200 * MB,
    ),
    "ppt": SupportedFileType(
        media_type=4,
        content_type="application/vnd.ms-powerpoint",
        max_size=200 * MB,
    ),
    "pptx": SupportedFileType(
        media_type=4,
        content_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        max_size=200 * MB,
    ),
    "xls": SupportedFileType(media_type=5, content_type="application/vnd.ms-excel", max_size=10 * MB),
    "xlsx": SupportedFileType(
        media_type=5,
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        max_size=10 * MB,
    ),
    "csv": SupportedFileType(media_type=5, content_type="text/csv", max_size=10 * MB),
    "md": SupportedFileType(media_type=7, content_type="text/markdown", max_size=10 * MB),
    "markdown": SupportedFileType(media_type=7, content_type="text/markdown", max_size=10 * MB),
    "png": SupportedFileType(media_type=9, content_type="image/png", max_size=30 * MB),
    "jpg": SupportedFileType(media_type=9, content_type="image/jpeg", max_size=30 * MB),
    "jpeg": SupportedFileType(media_type=9, content_type="image/jpeg", max_size=30 * MB),
    "webp": SupportedFileType(media_type=9, content_type="image/webp", max_size=30 * MB),
    "txt": SupportedFileType(media_type=13, content_type="text/plain", max_size=10 * MB),
    "xmind": SupportedFileType(media_type=14, content_type="application/x-xmind", max_size=10 * MB),
}

UNSUPPORTED_VIDEO_EXTENSIONS = {
    "mp4",
    "avi",
    "mov",
    "mkv",
    "wmv",
    "flv",
    "webm",
    "m4v",
    "rmvb",
    "rm",
    "3gp",
}
UNSUPPORTED_AUDIO_EXTENSIONS = {"mp3", "m4a", "wav", "aac"}
FILE_URL_EXTENSIONS = set(SUPPORTED_FILE_TYPES.keys()) | UNSUPPORTED_VIDEO_EXTENSIONS | UNSUPPORTED_AUDIO_EXTENSIONS
FILE_URL_PATH_HINTS = ("/pdf/",)
ROOT_FOLDER_PREFIX = "folder_"


class IMAServiceError(RuntimeError):
    def __init__(self, message: str, *, status_code: int = 502) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


class IMAMisconfigurationError(IMAServiceError):
    def __init__(self, message: str) -> None:
        super().__init__(message, status_code=500)


class IMAValidationError(IMAServiceError):
    def __init__(self, message: str) -> None:
        super().__init__(message, status_code=400)


class IMADuplicateNameError(IMAServiceError):
    def __init__(self, *, original_name: str, suggested_name: str) -> None:
        super().__init__(f"知识库中已存在同名文件：{original_name}", status_code=409)
        self.original_name = original_name
        self.suggested_name = suggested_name


def _coerce_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return str(value)


def _coerce_int(value: Any) -> Optional[int]:
    text = _coerce_text(value).strip()
    if not text:
        return None
    try:
        return int(text)
    except ValueError:
        return None


def normalize_ima_response(payload: dict[str, Any]) -> dict[str, Any]:
    code = payload.get("retcode", payload.get("code", 0))
    if code not in (0, None):
        errmsg = payload.get("errmsg") or payload.get("msg") or payload.get("message") or "IMA 接口调用失败"
        raise IMAServiceError(errmsg, status_code=502)

    data = payload.get("data")
    if isinstance(data, dict):
        return data

    if isinstance(payload, dict):
        return payload

    raise IMAServiceError("IMA 接口返回了无法识别的数据结构", status_code=502)


def normalize_folder_id(folder_id: Optional[str]) -> Optional[str]:
    folder_text = _coerce_text(folder_id).strip()
    if not folder_text or not folder_text.startswith(ROOT_FOLDER_PREFIX):
        return None
    return folder_text


def is_folder_item(item: dict[str, Any]) -> bool:
    media_id = _coerce_text(item.get("media_id"))
    media_type = item.get("media_type")
    return media_id.startswith(ROOT_FOLDER_PREFIX) or media_type == 99


def normalize_knowledge_item(item: dict[str, Any]) -> dict[str, Any]:
    tags = item.get("tags") if isinstance(item.get("tags"), list) else []
    return {
        "id": _coerce_text(item.get("media_id")),
        "title": _coerce_text(item.get("title") or item.get("name")) or "未命名条目",
        "is_folder": is_folder_item(item),
        "media_type": _coerce_int(item.get("media_type")) or 0,
        "parent_folder_id": _coerce_text(item.get("parent_folder_id")) or None,
        "tags": [_coerce_text(tag) for tag in tags if _coerce_text(tag)],
        "highlight_content": _coerce_text(item.get("highlight_content")) or None,
    }


def normalize_knowledge_base_item(item: dict[str, Any], details: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    details = details or {}
    recommended_questions = details.get("recommended_questions")
    if not isinstance(recommended_questions, list):
        recommended_questions = []

    return {
        "id": _coerce_text(item.get("id") or item.get("kb_id") or details.get("id")),
        "name": _coerce_text(item.get("name") or item.get("kb_name") or details.get("name")) or "未命名知识库",
        "cover_url": _coerce_text(item.get("cover_url") or details.get("cover_url")) or None,
        "description": _coerce_text(item.get("description") or details.get("description")) or None,
        "recommended_questions": [
            _coerce_text(question) for question in recommended_questions if _coerce_text(question)
        ],
        "member_count": _coerce_int(item.get("member_count") or details.get("member_count")),
        "content_count": _coerce_int(item.get("content_count") or details.get("content_count")),
        "creator": _coerce_text(item.get("creator") or details.get("creator")) or None,
        "role_type": _coerce_text(item.get("role_type") or details.get("role_type")) or None,
    }


def detect_supported_file(*, filename: str, file_size: int, content_type: Optional[str] = None) -> SupportedFileType:
    clean_name = Path(filename or "").name
    suffix = Path(clean_name).suffix.lower().lstrip(".")
    if not suffix:
        raise IMAValidationError("上传文件缺少扩展名，无法识别文件类型")

    if suffix in UNSUPPORTED_VIDEO_EXTENSIONS:
        raise IMAValidationError("当前版本不支持上传视频文件，请改用 ima 桌面端")
    if suffix in UNSUPPORTED_AUDIO_EXTENSIONS:
        raise IMAValidationError("当前版本不支持上传音频文件")

    spec = SUPPORTED_FILE_TYPES.get(suffix)
    if not spec:
        supported_ext = ", ".join(sorted(SUPPORTED_FILE_TYPES))
        raise IMAValidationError(f"当前仅支持以下文件类型：{supported_ext}")

    content_type_text = _coerce_text(content_type).lower()
    if content_type_text.startswith("video/"):
        raise IMAValidationError("当前版本不支持上传视频文件，请改用 ima 桌面端")
    if content_type_text.startswith("audio/"):
        raise IMAValidationError("当前版本不支持上传音频文件")

    if file_size <= 0:
        raise IMAValidationError("上传文件为空")
    if file_size > spec.max_size:
        raise IMAValidationError(f"文件过大，当前类型文件最大支持 {int(spec.max_size / MB)}MB")

    return spec


def build_duplicate_filename(filename: str, *, now: Optional[datetime] = None) -> str:
    path = Path(filename)
    timestamp = (now or datetime.now()).strftime("%Y%m%d%H%M%S")
    return f"{path.stem}_{timestamp}{path.suffix}"


def validate_importable_url(url: str) -> str:
    candidate = url.strip()
    parsed = urlparse(candidate)
    if parsed.scheme not in {"http", "https"}:
        raise IMAValidationError(f"URL 不合法或暂不支持：{candidate}")

    host = (parsed.netloc or "").lower()
    path = (parsed.path or "").lower()

    if candidate.startswith("file://"):
        raise IMAValidationError("本地 HTML 文件仅支持在 ima 桌面端内添加进知识库")
    if "bilibili.com" in host and path.startswith("/video/"):
        raise IMAValidationError("Bilibili 视频链接仅支持在 ima 桌面端内添加进知识库")
    if ("youtube.com" in host and path.startswith("/watch")) or "youtu.be" in host:
        raise IMAValidationError("YouTube 视频链接仅支持在 ima 桌面端内添加进知识库")

    suffix = Path(path).suffix.lower().lstrip(".")
    if suffix and suffix in FILE_URL_EXTENSIONS:
        raise IMAValidationError(f"当前版本不支持导入文件型 URL：{candidate}")
    if any(hint in path for hint in FILE_URL_PATH_HINTS):
        raise IMAValidationError(f"当前版本不支持导入文件型 URL：{candidate}")

    return candidate


class IMAKnowledgeBaseClient:
    def __init__(self) -> None:
        self.base_url = settings.ima_base_url.rstrip("/")
        self.timeout = settings.ima_timeout_seconds
        self.headers = {
            "ima-openapi-clientid": self._load_secret(settings.ima_openapi_clientid, "client_id"),
            "ima-openapi-apikey": self._load_secret(settings.ima_openapi_apikey, "api_key"),
            "Content-Type": "application/json; charset=utf-8",
        }

    @staticmethod
    def _load_secret(env_value: Optional[str], file_name: str) -> str:
        if env_value and env_value.strip():
            return env_value.strip().lstrip("\ufeff")

        file_path = IMA_CREDENTIAL_DIR / file_name
        if file_path.exists():
            return file_path.read_text(encoding="utf-8-sig").strip().lstrip("\ufeff")

        raise IMAMisconfigurationError(
            "缺少 IMA 凭证，请配置 IMA_OPENAPI_CLIENTID / IMA_OPENAPI_APIKEY 或 ~/.config/ima 下的凭证文件"
        )

    async def post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        url = f"{self.base_url}{IMA_OPENAPI_BASE_PATH}/{path}"
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")

        def _post_sync() -> dict[str, Any]:
            last_error: Optional[Exception] = None
            raw = ""
            for attempt in range(3):
                request = Request(url, data=body, headers=self.headers, method="POST")
                try:
                    with urlopen(request, timeout=self.timeout) as response:
                        raw = response.read().decode("utf-8")
                    break
                except HTTPError as exc:
                    detail = exc.read().decode("utf-8", errors="replace")
                    raise IMAServiceError(
                        f"IMA 接口 `{path}` 调用失败，HTTP {exc.code}: {detail}",
                        status_code=502,
                    ) from exc
                except URLError as exc:
                    last_error = exc
                except Exception as exc:  # pragma: no cover - 网络瞬断兜底
                    last_error = exc

                if attempt < 2:
                    time.sleep(1)

            if last_error is not None and not raw:
                raise IMAServiceError(f"无法连接到 IMA 接口：{last_error}", status_code=502) from last_error

            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise IMAServiceError("IMA 接口返回了无法解析的 JSON", status_code=502) from exc

            if not isinstance(parsed, dict):
                raise IMAServiceError("IMA 接口返回了无法识别的数据结构", status_code=502)
            return parsed

        parsed = await asyncio.to_thread(_post_sync)

        return normalize_ima_response(parsed)

    async def get_addable_knowledge_base_list(self, *, cursor: str = "", limit: int = 20) -> dict[str, Any]:
        return await self.post("get_addable_knowledge_base_list", {"cursor": cursor, "limit": limit})

    async def search_knowledge_base(self, query: str, *, cursor: str = "", limit: int = 20) -> dict[str, Any]:
        return await self.post("search_knowledge_base", {"query": query, "cursor": cursor, "limit": limit})

    async def get_knowledge_base(self, ids: Sequence[str]) -> dict[str, Any]:
        return await self.post("get_knowledge_base", {"ids": list(ids)})

    async def get_knowledge_list(
        self,
        knowledge_base_id: str,
        *,
        cursor: str = "",
        limit: int = 20,
        folder_id: Optional[str] = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "knowledge_base_id": knowledge_base_id,
            "cursor": cursor,
            "limit": limit,
        }
        normalized_folder_id = normalize_folder_id(folder_id)
        if normalized_folder_id:
            payload["folder_id"] = normalized_folder_id
        return await self.post("get_knowledge_list", payload)

    async def search_knowledge(self, knowledge_base_id: str, query: str, *, cursor: str = "") -> dict[str, Any]:
        return await self.post(
            "search_knowledge",
            {"knowledge_base_id": knowledge_base_id, "query": query, "cursor": cursor},
        )

    async def check_repeated_names(
        self,
        *,
        knowledge_base_id: str,
        params: list[dict[str, Any]],
        folder_id: Optional[str] = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"knowledge_base_id": knowledge_base_id, "params": params}
        normalized_folder_id = normalize_folder_id(folder_id)
        if normalized_folder_id:
            payload["folder_id"] = normalized_folder_id
        return await self.post("check_repeated_names", payload)

    async def create_media(
        self,
        *,
        file_name: str,
        file_size: int,
        content_type: str,
        knowledge_base_id: str,
        file_ext: str,
    ) -> dict[str, Any]:
        return await self.post(
            "create_media",
            {
                "file_name": file_name,
                "file_size": file_size,
                "content_type": content_type,
                "knowledge_base_id": knowledge_base_id,
                "file_ext": file_ext,
            },
        )

    async def add_knowledge(self, payload: dict[str, Any]) -> dict[str, Any]:
        normalized_folder_id = normalize_folder_id(payload.get("folder_id"))
        payload_to_send = dict(payload)
        if normalized_folder_id:
            payload_to_send["folder_id"] = normalized_folder_id
        else:
            payload_to_send.pop("folder_id", None)
        return await self.post("add_knowledge", payload_to_send)

    async def import_urls(
        self,
        *,
        knowledge_base_id: str,
        urls: Sequence[str],
        folder_id: Optional[str] = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"knowledge_base_id": knowledge_base_id, "urls": list(urls)}
        normalized_folder_id = normalize_folder_id(folder_id)
        if normalized_folder_id:
            payload["folder_id"] = normalized_folder_id
        return await self.post("import_urls", payload)


class IMAKnowledgeBaseService:
    def __init__(self, client: Optional[IMAKnowledgeBaseClient] = None) -> None:
        self.client = client or IMAKnowledgeBaseClient()
        self.minimax_service = MiniMaxMCPService()

    async def list_addable_knowledge_bases(self, *, cursor: str = "", limit: int = 20) -> dict[str, Any]:
        data = await self.client.get_addable_knowledge_base_list(cursor=cursor, limit=limit)
        raw_items = data.get("addable_knowledge_base_list") if isinstance(data.get("addable_knowledge_base_list"), list) else []
        detail_map = await self._fetch_knowledge_base_details_map(
            [_coerce_text(item.get("id") or item.get("kb_id")) for item in raw_items]
        )
        items = [
            normalize_knowledge_base_item(item, detail_map.get(_coerce_text(item.get("id") or item.get("kb_id"))))
            for item in raw_items
        ]
        return {
            "items": items,
            "next_cursor": _coerce_text(data.get("next_cursor")),
            "is_end": bool(data.get("is_end", True)),
        }

    async def search_knowledge_bases(self, query: str, *, cursor: str = "", limit: int = 20) -> dict[str, Any]:
        data = await self.client.search_knowledge_base(query=query, cursor=cursor, limit=limit)
        raw_items = data.get("info_list") if isinstance(data.get("info_list"), list) else []
        detail_map = await self._fetch_knowledge_base_details_map(
            [_coerce_text(item.get("id") or item.get("kb_id")) for item in raw_items]
        )
        items = [
            normalize_knowledge_base_item(item, detail_map.get(_coerce_text(item.get("id") or item.get("kb_id"))))
            for item in raw_items
        ]
        return {
            "items": items,
            "next_cursor": _coerce_text(data.get("next_cursor")),
            "is_end": bool(data.get("is_end", True)),
        }

    async def get_knowledge_base(self, knowledge_base_id: str) -> dict[str, Any]:
        detail_map = await self._fetch_knowledge_base_details_map([knowledge_base_id])
        detail = detail_map.get(knowledge_base_id)
        if not detail:
            raise IMAValidationError("知识库不存在或无权限访问")
        return detail

    async def list_items(
        self,
        knowledge_base_id: str,
        *,
        cursor: str = "",
        limit: int = 20,
        folder_id: Optional[str] = None,
    ) -> dict[str, Any]:
        data = await self.client.get_knowledge_list(
            knowledge_base_id,
            cursor=cursor,
            limit=limit,
            folder_id=folder_id,
        )
        raw_items = data.get("knowledge_list") if isinstance(data.get("knowledge_list"), list) else []
        current_path = data.get("current_path") if isinstance(data.get("current_path"), list) else []
        path_entries = [
            {
                "id": _coerce_text(item.get("folder_id")),
                "name": _coerce_text(item.get("name")) or ("根目录" if index == 0 else "未命名文件夹"),
                "is_root": index == 0,
            }
            for index, item in enumerate(current_path)
        ]
        return {
            "items": [normalize_knowledge_item(item) for item in raw_items],
            "current_path": path_entries,
            "next_cursor": _coerce_text(data.get("next_cursor")),
            "is_end": bool(data.get("is_end", True)),
        }

    async def search_items(self, knowledge_base_id: str, query: str, *, cursor: str = "") -> dict[str, Any]:
        data = await self.client.search_knowledge(knowledge_base_id, query=query, cursor=cursor)
        raw_items = data.get("info_list") if isinstance(data.get("info_list"), list) else []
        normalized_items = [normalize_knowledge_item(item) for item in raw_items]
        response = {
            "items": normalized_items,
            "next_cursor": _coerce_text(data.get("next_cursor")),
            "is_end": bool(data.get("is_end", not raw_items)),
            "fallback_used": False,
            "fallback_provider": None,
            "fallback_message": None,
            "fallback_results": [],
        }
        if normalized_items or not query.strip():
            return response

        fallback_results = await self._search_with_minimax_fallback(query)
        if fallback_results:
            response["fallback_used"] = True
            response["fallback_provider"] = "MiniMax MCP"
            response["fallback_message"] = "IMA 未命中，已切换到 MiniMax 联网搜索结果"
            response["fallback_results"] = fallback_results
        return response

    async def _search_with_minimax_fallback(self, query: str) -> list[dict[str, Any]]:
        if not self.minimax_service.enabled:
            return []
        try:
            data = await self.minimax_service.web_search(query)
        except MiniMaxMCPError:
            return []

        organic = data.get("organic") if isinstance(data.get("organic"), list) else []
        results: list[dict[str, Any]] = []
        for item in organic[:8]:
            if not isinstance(item, dict):
                continue
            title = _coerce_text(item.get("title")).strip()
            link = _coerce_text(item.get("link")).strip()
            if not title or not link:
                continue
            results.append(
                {
                    "title": title,
                    "link": link,
                    "snippet": _coerce_text(item.get("snippet")) or None,
                    "date": _coerce_text(item.get("date")) or None,
                }
            )
        return results

    async def upload_file(
        self,
        knowledge_base_id: str,
        *,
        file: UploadFile,
        folder_id: Optional[str] = None,
        on_duplicate: Literal["error", "rename"] = "error",
    ) -> dict[str, Any]:
        clean_filename = Path(file.filename or "").name
        temp_path, file_size = await self._persist_upload_to_temp(file, clean_filename)
        try:
            spec = detect_supported_file(
                filename=clean_filename,
                file_size=file_size,
                content_type=file.content_type,
            )
            final_name, duplicate_handling = await self._resolve_duplicate_name(
                knowledge_base_id=knowledge_base_id,
                folder_id=folder_id,
                filename=clean_filename,
                media_type=spec.media_type,
                on_duplicate=on_duplicate,
            )
            create_media = await self.client.create_media(
                file_name=final_name,
                file_size=file_size,
                content_type=spec.content_type,
                knowledge_base_id=knowledge_base_id,
                file_ext=Path(final_name).suffix.lower().lstrip("."),
            )
            media_id = _coerce_text(create_media.get("media_id"))
            credential = create_media.get("cos_credential") or create_media.get("credential") or {}
            if not media_id or not isinstance(credential, dict):
                raise IMAServiceError("IMA create_media 返回缺少必要字段", status_code=502)

            await self._upload_file_to_cos(
                file_path=temp_path,
                credential=credential,
                content_type=spec.content_type,
                file_size=file_size,
            )

            add_result = await self.client.add_knowledge(
                {
                    "media_type": spec.media_type,
                    "media_id": media_id,
                    "title": final_name,
                    "knowledge_base_id": knowledge_base_id,
                    "folder_id": folder_id,
                    "file_info": {
                        "cos_key": _coerce_text(credential.get("cos_key")),
                        "file_size": file_size,
                        "file_name": final_name,
                    },
                }
            )
            knowledge_base = await self.get_knowledge_base(knowledge_base_id)
            return {
                "message": f"已添加到知识库「{knowledge_base['name']}」",
                "knowledge_base": knowledge_base,
                "item": {
                    "id": _coerce_text(add_result.get("media_id") or media_id),
                    "title": final_name,
                    "is_folder": False,
                    "media_type": spec.media_type,
                    "parent_folder_id": normalize_folder_id(folder_id),
                    "tags": [],
                    "highlight_content": None,
                },
                "duplicate_handling": duplicate_handling,
                "original_name": clean_filename,
                "final_name": final_name,
            }
        finally:
            temp_path.unlink(missing_ok=True)

    async def import_urls(
        self,
        knowledge_base_id: str,
        *,
        urls: Sequence[str],
        folder_id: Optional[str] = None,
    ) -> dict[str, Any]:
        cleaned_urls = [validate_importable_url(item) for item in urls]
        await self._ensure_html_like_urls(cleaned_urls)
        data = await self.client.import_urls(
            knowledge_base_id=knowledge_base_id,
            urls=cleaned_urls,
            folder_id=folder_id,
        )
        raw_results = data.get("results") if isinstance(data.get("results"), dict) else {}
        results = []
        success_count = 0
        failure_count = 0
        for url in cleaned_urls:
            result = raw_results.get(url) if isinstance(raw_results, dict) else {}
            if not isinstance(result, dict):
                result = {}
            success = _coerce_int(result.get("ret_code")) in (0, None)
            if success:
                success_count += 1
            else:
                failure_count += 1
            results.append(
                {
                    "url": url,
                    "success": success,
                    "media_id": _coerce_text(result.get("media_id")) or None,
                    "error": None if success else (_coerce_text(result.get("errmsg")) or "导入失败"),
                }
            )
        knowledge_base = await self.get_knowledge_base(knowledge_base_id)
        return {
            "message": f"已向「{knowledge_base['name']}」导入 {success_count} 个 URL",
            "success_count": success_count,
            "failure_count": failure_count,
            "results": results,
        }

    async def _fetch_knowledge_base_details_map(self, ids: Sequence[str]) -> dict[str, dict[str, Any]]:
        normalized_ids = [item for item in {_coerce_text(kb_id).strip() for kb_id in ids} if item]
        if not normalized_ids:
            return {}

        detail_map: dict[str, dict[str, Any]] = {}
        for index in range(0, len(normalized_ids), 20):
            chunk = normalized_ids[index:index + 20]
            data = await self.client.get_knowledge_base(chunk)
            infos = data.get("infos") if isinstance(data.get("infos"), dict) else {}
            for knowledge_base_id in chunk:
                detail_raw = infos.get(knowledge_base_id)
                if isinstance(detail_raw, dict):
                    detail_map[knowledge_base_id] = normalize_knowledge_base_item(detail_raw)
        return detail_map

    async def _resolve_duplicate_name(
        self,
        *,
        knowledge_base_id: str,
        folder_id: Optional[str],
        filename: str,
        media_type: int,
        on_duplicate: Literal["error", "rename"],
    ) -> tuple[str, Literal["original", "renamed"]]:
        repeated = await self._is_duplicate_name(
            knowledge_base_id=knowledge_base_id,
            folder_id=folder_id,
            filename=filename,
            media_type=media_type,
        )
        if not repeated:
            return filename, "original"

        if on_duplicate != "rename":
            raise IMADuplicateNameError(
                original_name=filename,
                suggested_name=build_duplicate_filename(filename),
            )

        for offset in range(5):
            candidate = build_duplicate_filename(filename, now=datetime.now() + timedelta(seconds=offset))
            if not await self._is_duplicate_name(
                knowledge_base_id=knowledge_base_id,
                folder_id=folder_id,
                filename=candidate,
                media_type=media_type,
            ):
                return candidate, "renamed"

        raise IMAServiceError("重命名后仍存在同名冲突，请稍后再试", status_code=409)

    async def _is_duplicate_name(
        self,
        *,
        knowledge_base_id: str,
        folder_id: Optional[str],
        filename: str,
        media_type: int,
    ) -> bool:
        data = await self.client.check_repeated_names(
            knowledge_base_id=knowledge_base_id,
            folder_id=folder_id,
            params=[{"name": filename, "media_type": media_type}],
        )
        results = data.get("results") if isinstance(data.get("results"), list) else []
        for item in results:
            if isinstance(item, dict) and _coerce_text(item.get("name")) == filename:
                return bool(item.get("is_repeated"))
        return False

    async def _persist_upload_to_temp(self, file: UploadFile, clean_filename: str) -> tuple[Path, int]:
        suffix = Path(clean_filename).suffix
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
            temp_path = Path(temp_file.name)
            file_size = 0
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                temp_file.write(chunk)
                file_size += len(chunk)
        return temp_path, file_size

    async def _ensure_html_like_urls(self, urls: Sequence[str]) -> None:
        for url in urls:
            parsed = urlparse(url)
            host = (parsed.netloc or "").lower()
            path = (parsed.path or "").lower()
            if "mp.weixin.qq.com" in host and path.startswith("/s"):
                continue

            try:
                content_type = await self._probe_content_type(url)
            except IMAServiceError:
                continue

            if content_type and not content_type.startswith("text/html"):
                raise IMAValidationError(f"当前版本仅支持导入网页 URL，不支持文件型 URL：{url}")

    async def _probe_content_type(self, url: str) -> str:
        async with httpx.AsyncClient(
            timeout=settings.ima_timeout_seconds,
            follow_redirects=True,
            trust_env=False,
        ) as client:
            try:
                response = await client.head(url)
                if response.status_code < 400:
                    content_type = response.headers.get("content-type", "")
                    if content_type:
                        return content_type.split(";")[0].strip().lower()
            except httpx.RequestError:
                pass

            try:
                response = await client.get(url, headers={"Range": "bytes=0-0"})
                content_type = response.headers.get("content-type", "")
                if content_type:
                    return content_type.split(";")[0].strip().lower()
            except httpx.RequestError as exc:
                raise IMAServiceError(f"URL 类型探测失败：{url}", status_code=502) from exc

        return ""

    async def _upload_file_to_cos(
        self,
        *,
        file_path: Path,
        credential: dict[str, Any],
        content_type: str,
        file_size: int,
    ) -> None:
        secret_id = _coerce_text(credential.get("secret_id"))
        secret_key = _coerce_text(credential.get("secret_key"))
        token = _coerce_text(credential.get("token"))
        bucket_name = _coerce_text(credential.get("bucket_name"))
        region = _coerce_text(credential.get("region"))
        cos_key = _coerce_text(credential.get("cos_key")).lstrip("/")
        if not all([secret_id, secret_key, token, bucket_name, region, cos_key]):
            raise IMAServiceError("IMA 返回的 COS 凭证不完整", status_code=502)

        hostname = f"{bucket_name}.cos.{region}.myqcloud.com"
        pathname = f"/{cos_key}"
        authorization = self._build_cos_authorization(
            secret_id=secret_id,
            secret_key=secret_key,
            method="PUT",
            pathname=pathname,
            headers_to_sign={"content-length": str(file_size), "host": hostname},
            start_time=_coerce_text(credential.get("start_time")),
            expired_time=_coerce_text(credential.get("expired_time")),
        )
        headers = {
            "Content-Type": content_type,
            "Content-Length": str(file_size),
            "Authorization": authorization,
            "x-cos-security-token": token,
        }
        url = f"https://{hostname}{pathname}"

        def _put_sync() -> None:
            request = Request(url, data=file_path.read_bytes(), headers=headers, method="PUT")
            try:
                with urlopen(request, timeout=settings.ima_timeout_seconds) as response:
                    if not 200 <= response.status < 300:
                        detail = response.read().decode("utf-8", errors="replace")
                        raise IMAServiceError(
                            f"COS 上传失败，HTTP {response.status}: {detail}",
                            status_code=502,
                        )
            except HTTPError as exc:
                detail = exc.read().decode("utf-8", errors="replace")
                raise IMAServiceError(
                    f"COS 上传失败，HTTP {exc.code}: {detail}",
                    status_code=502,
                ) from exc
            except URLError as exc:
                raise IMAServiceError(f"COS 上传失败：{exc}", status_code=502) from exc

        await asyncio.to_thread(_put_sync)

    @staticmethod
    def _build_cos_authorization(
        *,
        secret_id: str,
        secret_key: str,
        method: str,
        pathname: str,
        headers_to_sign: dict[str, str],
        start_time: str,
        expired_time: str,
    ) -> str:
        start = start_time or str(int(datetime.now().timestamp()))
        expired = expired_time or str(int(datetime.now().timestamp()) + 3600)
        key_time = f"{start};{expired}"

        sign_key = hmac.new(secret_key.encode("utf-8"), key_time.encode("utf-8"), hashlib.sha1).hexdigest()
        header_keys = sorted(headers_to_sign)
        http_headers = "&".join(
            f"{key.lower()}={quote(headers_to_sign[key], safe='')}" for key in header_keys
        )
        http_string = f"{method.lower()}\n{pathname}\n\n{http_headers}\n"
        string_to_sign = f"sha1\n{key_time}\n{hashlib.sha1(http_string.encode('utf-8')).hexdigest()}\n"
        signature = hmac.new(
            sign_key.encode("utf-8"),
            string_to_sign.encode("utf-8"),
            hashlib.sha1,
        ).hexdigest()
        return "&".join(
            [
                "q-sign-algorithm=sha1",
                f"q-ak={secret_id}",
                f"q-sign-time={key_time}",
                f"q-key-time={key_time}",
                f"q-header-list={';'.join(key.lower() for key in header_keys)}",
                "q-url-param-list=",
                f"q-signature={signature}",
            ]
        )


__all__ = [
    "IMAKnowledgeBaseClient",
    "IMAKnowledgeBaseService",
    "IMADuplicateNameError",
    "IMAServiceError",
    "IMAValidationError",
    "build_duplicate_filename",
    "detect_supported_file",
    "is_folder_item",
    "normalize_folder_id",
    "normalize_ima_response",
    "normalize_knowledge_base_item",
    "normalize_knowledge_item",
    "validate_importable_url",
]
