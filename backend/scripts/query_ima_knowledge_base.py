#!/usr/bin/env python3
"""Query a specified IMA knowledge base from the command line.

Examples:
  python backend/scripts/query_ima_knowledge_base.py bases --query 小说
  python backend/scripts/query_ima_knowledge_base.py info --knowledge-base-name "个人知识库"
  python backend/scripts/query_ima_knowledge_base.py list --knowledge-base-id "<kb_id>" --limit 10
  python backend/scripts/query_ima_knowledge_base.py search --knowledge-base-name "个人知识库" --query 角色设定
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

BASE_URL = "https://ima.qq.com/openapi/wiki/v1"
DEFAULT_TIMEOUT = 30


class IMAAPIError(RuntimeError):
    """Raised when the IMA OpenAPI request or resolution flow fails."""


def _load_secret(env_name: str, file_name: str) -> str:
    value = os.getenv(env_name)
    if value and value.strip():
        return value.strip().lstrip("\ufeff")

    config_path = Path.home() / ".config" / "ima" / file_name
    if config_path.exists():
        return config_path.read_text(encoding="utf-8-sig").strip().lstrip("\ufeff")

    raise IMAAPIError(
        "缺少 IMA 凭证。请先设置环境变量 "
        "`IMA_OPENAPI_CLIENTID` / `IMA_OPENAPI_APIKEY`，"
        "或者在 `~/.config/ima/` 下提供 `client_id` 和 `api_key` 文件。"
    )


def _bounded_int(value: str, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"{value!r} 不是有效整数") from exc

    if not minimum <= parsed <= maximum:
        raise argparse.ArgumentTypeError(f"取值必须在 {minimum} 到 {maximum} 之间")
    return parsed


def _limit_value(value: str) -> int:
    return _bounded_int(value, 1, 50)


def _coerce_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return str(value)


class IMAKnowledgeBaseClient:
    def __init__(self, timeout: int = DEFAULT_TIMEOUT) -> None:
        self.timeout = timeout
        self.headers = {
            "ima-openapi-clientid": _load_secret("IMA_OPENAPI_CLIENTID", "client_id"),
            "ima-openapi-apikey": _load_secret("IMA_OPENAPI_APIKEY", "api_key"),
            "Content-Type": "application/json; charset=utf-8",
        }

    def post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = Request(
            f"{BASE_URL}/{path}",
            data=body,
            headers=self.headers,
            method="POST",
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:
                raw = response.read().decode("utf-8")
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise IMAAPIError(
                f"IMA API 请求失败，HTTP {exc.code}，接口 `{path}`，响应：{detail}"
            ) from exc
        except URLError as exc:
            raise IMAAPIError(f"无法连接到 IMA API：{exc}") from exc

        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise IMAAPIError(f"IMA API 返回了无法解析的 JSON：{raw}") from exc

        if isinstance(parsed, dict):
            retcode = parsed.get("retcode")
            if retcode not in (None, 0):
                errmsg = parsed.get("errmsg") or parsed.get("message") or "未知错误"
                raise IMAAPIError(f"IMA API 返回错误 retcode={retcode}: {errmsg}")
            return parsed

        raise IMAAPIError(f"IMA API 返回了意外数据结构：{type(parsed).__name__}")

    def search_knowledge_base(
        self,
        query: str,
        *,
        cursor: str = "",
        limit: int = 10,
    ) -> dict[str, Any]:
        return self.post(
            "search_knowledge_base",
            {"query": query, "cursor": cursor, "limit": limit},
        )

    def list_all_knowledge_bases(self, *, page_limit: int = 50, max_pages: int = 10) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        cursor = ""

        for _ in range(max_pages):
            response = self.search_knowledge_base("", cursor=cursor, limit=page_limit)
            page_items = response.get("info_list") or []
            items.extend(page_items)
            if response.get("is_end"):
                break
            cursor = _coerce_text(response.get("next_cursor"))
            if not cursor:
                break

        deduped: dict[str, dict[str, Any]] = {}
        for item in items:
            item_id = _coerce_text(item.get("id"))
            if item_id:
                deduped[item_id] = item
        return list(deduped.values())

    def get_knowledge_base(self, knowledge_base_id: str) -> dict[str, Any]:
        return self.post("get_knowledge_base", {"ids": [knowledge_base_id]})

    def get_knowledge_list(
        self,
        knowledge_base_id: str,
        *,
        cursor: str = "",
        limit: int = 20,
        folder_id: str | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "knowledge_base_id": knowledge_base_id,
            "cursor": cursor,
            "limit": limit,
        }
        if folder_id:
            payload["folder_id"] = folder_id
        return self.post("get_knowledge_list", payload)

    def search_knowledge(
        self,
        knowledge_base_id: str,
        query: str,
        *,
        cursor: str = "",
    ) -> dict[str, Any]:
        return self.post(
            "search_knowledge",
            {
                "knowledge_base_id": knowledge_base_id,
                "query": query,
                "cursor": cursor,
            },
        )

    def resolve_knowledge_base(
        self,
        *,
        knowledge_base_id: str | None,
        knowledge_base_name: str | None,
    ) -> dict[str, str]:
        if knowledge_base_id:
            info_map = self.get_knowledge_base(knowledge_base_id).get("infos") or {}
            info = info_map.get(knowledge_base_id) or {}
            return {
                "id": knowledge_base_id,
                "name": _coerce_text(info.get("name")) or "(unknown)",
            }

        if not knowledge_base_name:
            raise IMAAPIError("请提供 `--knowledge-base-id` 或 `--knowledge-base-name`。")

        response = self.search_knowledge_base(knowledge_base_name, limit=20)
        matches = response.get("info_list") or []
        exact_matches = [item for item in matches if item.get("name") == knowledge_base_name]

        if not matches:
            all_items = self.list_all_knowledge_bases()
            exact_matches = [item for item in all_items if item.get("name") == knowledge_base_name]
            fuzzy_matches = [
                item for item in all_items if knowledge_base_name in _coerce_text(item.get("name"))
            ]
            if len(exact_matches) == 1:
                chosen = exact_matches[0]
                return {
                    "id": _coerce_text(chosen.get("id")),
                    "name": _coerce_text(chosen.get("name")) or knowledge_base_name,
                }
            if len(fuzzy_matches) == 1:
                chosen = fuzzy_matches[0]
                return {
                    "id": _coerce_text(chosen.get("id")),
                    "name": _coerce_text(chosen.get("name")) or knowledge_base_name,
                }
            matches = fuzzy_matches

        if len(exact_matches) == 1:
            chosen = exact_matches[0]
        elif len(matches) == 1:
            chosen = matches[0]
        elif not matches:
            raise IMAAPIError(f"未找到名为 `{knowledge_base_name}` 的知识库。")
        else:
            candidates = "\n".join(
                f"- {item.get('name')} ({item.get('id')})" for item in matches[:10]
            )
            raise IMAAPIError(
                f"知识库名称 `{knowledge_base_name}` 命中了多个结果，请改用更精确的名称或 ID：\n"
                f"{candidates}"
            )

        return {
            "id": _coerce_text(chosen.get("id")),
            "name": _coerce_text(chosen.get("name")) or knowledge_base_name,
        }


def _print_json(payload: Any) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def _print_base_list(response: dict[str, Any]) -> None:
    info_list = response.get("info_list") or []
    if not info_list:
        print("没有找到知识库。")
    else:
        print(f"共找到 {len(info_list)} 个知识库：")
        for index, item in enumerate(info_list, start=1):
            print(f"{index}. {_coerce_text(item.get('name'))}")
            print(f"   id: {_coerce_text(item.get('id'))}")
            cover_url = _coerce_text(item.get("cover_url"))
            if cover_url:
                print(f"   cover_url: {cover_url}")
    print(f"is_end: {response.get('is_end')}  next_cursor: {_coerce_text(response.get('next_cursor'))}")


def _print_info(resolved: dict[str, str], response: dict[str, Any]) -> None:
    info_map = response.get("infos") or {}
    info = info_map.get(resolved["id"]) or {}
    print(f"知识库: {resolved['name']}")
    print(f"id: {resolved['id']}")
    print(f"description: {_coerce_text(info.get('description'))}")
    recommended_questions = info.get("recommended_questions") or []
    print(f"recommended_questions_count: {len(recommended_questions)}")
    if recommended_questions:
        print("recommended_questions:")
        for question in recommended_questions:
            print(f"- {_coerce_text(question)}")


def _print_list_result(resolved: dict[str, str], response: dict[str, Any]) -> None:
    items = response.get("knowledge_list") or []
    current_path = response.get("current_path") or []
    print(f"知识库: {resolved['name']} ({resolved['id']})")
    if current_path:
        path_text = " / ".join(_coerce_text(item.get("name")) for item in current_path)
        print(f"当前路径: {path_text}")
    print(f"共返回 {len(items)} 条记录：")
    for index, item in enumerate(items, start=1):
        print(f"{index}. {_coerce_text(item.get('title'))}")
        print(f"   media_id: {_coerce_text(item.get('media_id'))}")
        parent_folder_id = _coerce_text(item.get("parent_folder_id"))
        if parent_folder_id:
            print(f"   parent_folder_id: {parent_folder_id}")
        tags = item.get("tags") or []
        if tags:
            print(f"   tags: {', '.join(_coerce_text(tag) for tag in tags)}")
    print(f"is_end: {response.get('is_end')}  next_cursor: {_coerce_text(response.get('next_cursor'))}")


def _print_search_result(resolved: dict[str, str], query: str, response: dict[str, Any]) -> None:
    items = response.get("info_list") or []
    searched_tags = response.get("searched_tags") or []
    print(f"知识库: {resolved['name']} ({resolved['id']})")
    print(f"关键词: {query}")
    print(f"共命中 {len(items)} 条记录：")
    for index, item in enumerate(items, start=1):
        print(f"{index}. {_coerce_text(item.get('title'))}")
        print(f"   media_id: {_coerce_text(item.get('media_id'))}")
        parent_folder_id = _coerce_text(item.get("parent_folder_id"))
        if parent_folder_id:
            print(f"   parent_folder_id: {parent_folder_id}")
        highlight = _coerce_text(item.get("highlight_content"))
        if highlight:
            print(f"   highlight: {highlight}")
    if searched_tags:
        print(f"searched_tags: {', '.join(_coerce_text(tag) for tag in searched_tags)}")
    print(f"is_end: {response.get('is_end')}  next_cursor: {_coerce_text(response.get('next_cursor'))}")


def _add_knowledge_base_locator(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--knowledge-base-id", help="指定知识库 ID")
    parser.add_argument("--knowledge-base-name", help="指定知识库名称，会自动解析为 ID")


def _add_common_output_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--json", action="store_true", help="以 JSON 输出结果")
    parser.add_argument(
        "--timeout",
        type=lambda value: _bounded_int(value, 1, 120),
        default=DEFAULT_TIMEOUT,
        help="接口超时时间，单位秒，默认 30",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="查询 IMA 指定知识库。")
    _add_common_output_args(parser)

    subparsers = parser.add_subparsers(dest="command", required=True)

    bases_parser = subparsers.add_parser("bases", help="按名称搜索知识库，query 为空时列出知识库")
    _add_common_output_args(bases_parser)
    bases_parser.add_argument("--query", default="", help="知识库名称关键词，默认空字符串")
    bases_parser.add_argument("--cursor", default="", help="分页游标")
    bases_parser.add_argument("--limit", type=_limit_value, default=10, help="返回数量，1-50")

    info_parser = subparsers.add_parser("info", help="查看指定知识库详情")
    _add_common_output_args(info_parser)
    _add_knowledge_base_locator(info_parser)

    list_parser = subparsers.add_parser("list", help="浏览指定知识库内容")
    _add_common_output_args(list_parser)
    _add_knowledge_base_locator(list_parser)
    list_parser.add_argument("--cursor", default="", help="分页游标")
    list_parser.add_argument("--limit", type=_limit_value, default=20, help="返回数量，1-50")
    list_parser.add_argument("--folder-id", help="指定文件夹 ID，不传则浏览根目录")

    search_parser = subparsers.add_parser("search", help="在指定知识库中搜索内容")
    _add_common_output_args(search_parser)
    _add_knowledge_base_locator(search_parser)
    search_parser.add_argument("--query", required=True, help="搜索关键词")
    search_parser.add_argument("--cursor", default="", help="分页游标")

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    try:
        client = IMAKnowledgeBaseClient(timeout=args.timeout)

        if args.command == "bases":
            response = client.search_knowledge_base(
                args.query,
                cursor=args.cursor,
                limit=args.limit,
            )
            if args.json:
                _print_json(response)
            else:
                _print_base_list(response)
            return 0

        resolved = client.resolve_knowledge_base(
            knowledge_base_id=getattr(args, "knowledge_base_id", None),
            knowledge_base_name=getattr(args, "knowledge_base_name", None),
        )

        if args.command == "info":
            response = client.get_knowledge_base(resolved["id"])
            if args.json:
                _print_json({"resolved_knowledge_base": resolved, "result": response})
            else:
                _print_info(resolved, response)
            return 0

        if args.command == "list":
            response = client.get_knowledge_list(
                resolved["id"],
                cursor=args.cursor,
                limit=args.limit,
                folder_id=args.folder_id,
            )
            if args.json:
                _print_json({"resolved_knowledge_base": resolved, "result": response})
            else:
                _print_list_result(resolved, response)
            return 0

        if args.command == "search":
            response = client.search_knowledge(
                resolved["id"],
                args.query,
                cursor=args.cursor,
            )
            if args.json:
                _print_json({"resolved_knowledge_base": resolved, "result": response})
            else:
                _print_search_result(resolved, args.query, response)
            return 0

        parser.error(f"不支持的命令：{args.command}")
        return 2
    except IMAAPIError as exc:
        print(f"错误: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
