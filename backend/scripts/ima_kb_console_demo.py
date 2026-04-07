#!/usr/bin/env python3
"""Interactive IMA personal knowledge base search demo.

Run in PyCharm terminal/console:
  python backend/scripts/ima_kb_console_demo.py
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

BASE_URL = "https://ima.qq.com/openapi/wiki/v1"
DEFAULT_TIMEOUT = 30
DEFAULT_LIMIT = 20
MAX_PAGES = 20


class IMAAPIError(RuntimeError):
    """Raised when an IMA OpenAPI request fails."""


def _as_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return str(value)


def _bounded_int(value: str, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"{value!r} is not a valid integer.") from exc

    if not minimum <= parsed <= maximum:
        raise argparse.ArgumentTypeError(f"Value must be between {minimum} and {maximum}.")
    return parsed


def _limit_value(value: str) -> int:
    return _bounded_int(value, 1, 50)


def _timeout_value(value: str) -> int:
    return _bounded_int(value, 1, 120)


def _load_secret(env_name: str, file_name: str) -> str:
    value = os.getenv(env_name)
    if value and value.strip():
        return value.strip().lstrip("\ufeff")

    config_path = Path.home() / ".config" / "ima" / file_name
    if config_path.exists():
        return config_path.read_text(encoding="utf-8-sig").strip().lstrip("\ufeff")

    raise IMAAPIError(
        "Missing IMA credentials. Set environment variables "
        "`IMA_OPENAPI_CLIENTID` and `IMA_OPENAPI_APIKEY`, or create files "
        "`~/.config/ima/client_id` and `~/.config/ima/api_key`."
    )


def _print_json(payload: Any) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


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
                f"HTTP {exc.code} calling `{path}`. Response: {detail}"
            ) from exc
        except URLError as exc:
            raise IMAAPIError(f"Failed to connect to IMA API: {exc}") from exc

        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise IMAAPIError(f"IMA API returned invalid JSON: {raw}") from exc

        if not isinstance(parsed, dict):
            raise IMAAPIError(
                f"IMA API returned an unexpected response type: {type(parsed).__name__}"
            )

        if "retcode" in parsed:
            retcode = parsed.get("retcode")
            if retcode != 0:
                errmsg = _as_text(parsed.get("errmsg")) or "Unknown error"
                raise IMAAPIError(f"IMA API error retcode={retcode}: {errmsg}")
            data = parsed.get("data")
            if data is None:
                return {}
            if not isinstance(data, dict):
                raise IMAAPIError(
                    f"IMA API returned invalid `data` type: {type(data).__name__}"
                )
            return data

        return parsed

    def search_knowledge_base(
        self,
        query: str,
        *,
        cursor: str = "",
        limit: int = DEFAULT_LIMIT,
    ) -> dict[str, Any]:
        return self.post(
            "search_knowledge_base",
            {"query": query, "cursor": cursor, "limit": limit},
        )

    def get_addable_knowledge_base_list(
        self,
        *,
        cursor: str = "",
        limit: int = DEFAULT_LIMIT,
    ) -> dict[str, Any]:
        return self.post(
            "get_addable_knowledge_base_list",
            {"cursor": cursor, "limit": limit},
        )

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
                "query": query,
                "cursor": cursor,
                "knowledge_base_id": knowledge_base_id,
            },
        )


def _fetch_all_pages(
    fetch_page: Callable[[str, int], dict[str, Any]],
    list_key: str,
    *,
    limit: int,
    max_pages: int = MAX_PAGES,
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    cursor = ""

    for _ in range(max_pages):
        response = fetch_page(cursor, limit)
        page_items = response.get(list_key) or []
        if isinstance(page_items, list):
            for item in page_items:
                if isinstance(item, dict):
                    items.append(item)

        is_end = bool(response.get("is_end", True))
        next_cursor = _as_text(response.get("next_cursor"))
        if is_end or not next_cursor:
            break
        cursor = next_cursor

    return items


def _merge_knowledge_bases(
    visible_items: list[dict[str, Any]],
    addable_items: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}

    def upsert(item: dict[str, Any], source: str) -> None:
        kb_id = _as_text(item.get("id")).strip()
        if not kb_id:
            return

        kb_name = _as_text(item.get("name")).strip() or "(Unnamed knowledge base)"
        existing = merged.get(kb_id)
        if existing is None:
            existing = {"id": kb_id, "name": kb_name, "sources": set()}
            merged[kb_id] = existing
        elif existing["name"] == "(Unnamed knowledge base)" and kb_name != "(Unnamed knowledge base)":
            existing["name"] = kb_name

        existing["sources"].add(source)

    for item in visible_items:
        upsert(item, "visible")
    for item in addable_items:
        upsert(item, "addable")

    result: list[dict[str, Any]] = []
    for entry in merged.values():
        result.append(
            {
                "id": _as_text(entry["id"]),
                "name": _as_text(entry["name"]),
                "sources": sorted(entry["sources"]),
            }
        )

    result.sort(key=lambda item: item["name"].lower())
    return result


def load_knowledge_base_list(
    client: IMAKnowledgeBaseClient,
    *,
    list_source: str,
    limit: int,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    visible_items: list[dict[str, Any]] = []
    addable_items: list[dict[str, Any]] = []

    if list_source in ("both", "search"):
        visible_items = _fetch_all_pages(
            lambda cursor, page_limit: client.search_knowledge_base(
                "", cursor=cursor, limit=page_limit
            ),
            "info_list",
            limit=limit,
        )

    if list_source in ("both", "addable"):
        addable_items = _fetch_all_pages(
            lambda cursor, page_limit: client.get_addable_knowledge_base_list(
                cursor=cursor, limit=page_limit
            ),
            "addable_knowledge_base_list",
            limit=limit,
        )

    merged = _merge_knowledge_bases(visible_items, addable_items)
    stats = {
        "visible_items": len(visible_items),
        "addable_items": len(addable_items),
        "merged_items": len(merged),
    }
    return merged, stats


def _format_sources(sources: list[str]) -> str:
    if not sources:
        return "unknown"
    return "/".join(sources)


def _print_knowledge_base_menu(items: list[dict[str, Any]]) -> None:
    print("\nYour personal knowledge bases:")
    for index, item in enumerate(items, start=1):
        print(f"{index}. {item['name']} [{_format_sources(item.get('sources', []))}]")
    print("Use a number to select, or type /quit to exit.")


def _prompt_knowledge_base(items: list[dict[str, Any]]) -> dict[str, Any] | None:
    while True:
        raw = input("\nSelect knowledge base: ").strip()
        lowered = raw.lower()
        if lowered in {"/quit", "quit", "q", "exit"}:
            return None
        if not raw:
            print("Please enter a number.")
            continue
        if not raw.isdigit():
            print("Invalid input. Please enter a number.")
            continue

        index = int(raw)
        if 1 <= index <= len(items):
            return items[index - 1]
        print(f"Please enter a number between 1 and {len(items)}.")


def _print_search_results(
    *,
    kb_name: str,
    query: str,
    page: int,
    response: dict[str, Any],
) -> None:
    info_list = response.get("info_list") or []
    if page == 1:
        print(f"\nSearch in '{kb_name}' with query: {query}")

    if not info_list:
        if page == 1:
            print("No matches found.")
        else:
            print("No additional matches on this page.")
        return

    print(f"Page {page}, {len(info_list)} hit(s):")
    for index, item in enumerate(info_list, start=1):
        title = _as_text(item.get("title") or item.get("name")).strip() or "(Untitled)"
        print(f"{index}. {title}")

        highlight = _as_text(item.get("highlight_content")).strip()
        if highlight:
            print(f"   highlight: {highlight}")


def _should_continue_next_page() -> bool:
    raw = input("More results available. Load next page? [y/N]: ").strip().lower()
    return raw in {"y", "yes"}


def run_query_loop(
    client: IMAKnowledgeBaseClient,
    *,
    knowledge_base: dict[str, Any],
    json_mode: bool,
) -> str:
    kb_name = _as_text(knowledge_base.get("name")) or "(Unnamed knowledge base)"
    kb_id = _as_text(knowledge_base.get("id"))

    print(f"\nSelected knowledge base: {kb_name}")
    print("Type your question to search.")
    print("Commands: /switch (choose another knowledge base), /quit (exit)")

    while True:
        query = input("\nQuestion: ").strip()
        lowered = query.lower()
        if lowered in {"/quit", "quit", "q", "exit"}:
            return "quit"
        if lowered in {"/switch", "/back", "back"}:
            return "switch"
        if not query:
            print("Please enter a non-empty question.")
            continue

        cursor = ""
        page = 1
        while True:
            result = client.search_knowledge(kb_id, query, cursor=cursor)
            if json_mode:
                _print_json(
                    {
                        "knowledge_base": {
                            "name": kb_name,
                            "id": kb_id,
                        },
                        "query": query,
                        "page": page,
                        "response": result,
                    }
                )
            else:
                _print_search_results(
                    kb_name=kb_name,
                    query=query,
                    page=page,
                    response=result,
                )

            is_end = bool(result.get("is_end", True))
            next_cursor = _as_text(result.get("next_cursor"))
            if is_end or not next_cursor:
                break

            if not _should_continue_next_page():
                break
            cursor = next_cursor
            page += 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Interactive demo for querying personal IMA knowledge bases."
    )
    parser.add_argument(
        "--list-source",
        choices=("both", "search", "addable"),
        default="both",
        help="Where to load personal knowledge base list from.",
    )
    parser.add_argument(
        "--limit",
        type=_limit_value,
        default=DEFAULT_LIMIT,
        help="Page size for list endpoints (1-50).",
    )
    parser.add_argument(
        "--timeout",
        type=_timeout_value,
        default=DEFAULT_TIMEOUT,
        help="HTTP timeout in seconds (1-120).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print raw JSON responses for debugging.",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    try:
        client = IMAKnowledgeBaseClient(timeout=args.timeout)
        kb_items, stats = load_knowledge_base_list(
            client,
            list_source=args.list_source,
            limit=args.limit,
        )

        if args.json:
            _print_json(
                {
                    "list_source": args.list_source,
                    "limit": args.limit,
                    "stats": stats,
                    "knowledge_bases": kb_items,
                }
            )

        if not kb_items:
            print("No personal knowledge base found for the selected source.")
            return 0

        while True:
            _print_knowledge_base_menu(kb_items)
            selected = _prompt_knowledge_base(kb_items)
            if selected is None:
                print("Exit.")
                return 0

            action = run_query_loop(
                client,
                knowledge_base=selected,
                json_mode=args.json,
            )
            if action == "quit":
                print("Exit.")
                return 0

    except KeyboardInterrupt:
        print("\nInterrupted by user.")
        return 130
    except IMAAPIError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
