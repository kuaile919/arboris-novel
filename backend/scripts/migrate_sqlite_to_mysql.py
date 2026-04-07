#!/usr/bin/env python
"""
Migrate Arboris primary data from SQLite to MySQL.

Goals:
- Keep migration operationally simple for single-server deployments.
- Do not miss schema drift: compare table/column differences and report them.
- Preserve data as much as possible: copy all rows from source tables into target.

Notes:
- This script migrates the primary business database only.
- Vector DB (rag_vectors.db / libsql) is not migrated by this script.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus, urlparse

from sqlalchemy import JSON, Column, MetaData, Table, Text, inspect, insert, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, create_async_engine
from sqlalchemy.sql.sqltypes import NullType


SCRIPT_PATH = Path(__file__).resolve()
BACKEND_ROOT = SCRIPT_PATH.parents[1]
PROJECT_ROOT = SCRIPT_PATH.parents[2]
DEFAULT_MYSQL_HOST = "123.207.213.21"
DEFAULT_MYSQL_PORT = 3306
DEFAULT_MYSQL_USER = "arboris-novel"
DEFAULT_MYSQL_DATABASE = "arboris-novel"


def _quote_ident(identifier: str) -> str:
    return f"`{identifier.replace('`', '``')}`"


def _normalize_json_value(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (dict, list, int, float, bool)):
        return value
    if isinstance(value, str):
        candidate = value.strip()
        if not candidate:
            return None
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            # MySQL JSON accepts strings, SQLAlchemy will serialize them as JSON strings.
            return value
    return value


def _normalize_mysql_host(host: str) -> str:
    candidate = host.strip()
    if not candidate:
        return candidate

    if "://" in candidate:
        parsed = urlparse(candidate)
        if parsed.hostname:
            return parsed.hostname

    return candidate.rstrip("/")


def _build_mysql_urls(
    host: str,
    port: int,
    user: str,
    password: str,
    database: str,
) -> tuple[str, str]:
    encoded_password = quote_plus(password)
    base = f"mysql+aiomysql://{user}:{encoded_password}@{host}:{port}"
    admin_url = f"{base}/?charset=utf8mb4"
    db_url = f"{base}/{database}?charset=utf8mb4"
    return admin_url, db_url


@dataclass
class TableResult:
    table: str
    source_rows: int = 0
    target_rows: int = 0
    copied_rows: int = 0
    status: str = "pending"
    message: str = ""
    source_only_columns: list[str] = field(default_factory=list)
    target_only_columns: list[str] = field(default_factory=list)


@dataclass
class MigrationReport:
    started_at: str
    finished_at: str = ""
    source_sqlite: str = ""
    target_mysql: str = ""
    bootstrap_schema: bool = True
    truncate_target: bool = False
    chunk_size: int = 1000
    source_tables: list[str] = field(default_factory=list)
    target_tables_before: list[str] = field(default_factory=list)
    target_tables_after: list[str] = field(default_factory=list)
    source_only_tables: list[str] = field(default_factory=list)
    target_only_tables: list[str] = field(default_factory=list)
    created_missing_tables: list[str] = field(default_factory=list)
    table_results: list[TableResult] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        if self.errors:
            return False
        return all(item.status in {"ok", "skipped"} for item in self.table_results)


async def _get_tables(conn: AsyncConnection, *, sqlite: bool = False) -> list[str]:
    def _inner(sync_conn):
        tables = inspect(sync_conn).get_table_names()
        if sqlite:
            tables = [t for t in tables if t != "sqlite_sequence"]
        return sorted(tables)

    return await conn.run_sync(_inner)


async def _reflect_table(conn: AsyncConnection, table_name: str) -> Table:
    def _inner(sync_conn):
        metadata = MetaData()
        return Table(table_name, metadata, autoload_with=sync_conn)

    return await conn.run_sync(_inner)


async def _count_rows(conn: AsyncConnection, table_name: str) -> int:
    result = await conn.execute(text(f"SELECT COUNT(*) AS c FROM {_quote_ident(table_name)}"))
    row = result.first()
    return int(row[0] if row is not None else 0)


async def _ensure_mysql_database(admin_engine: AsyncEngine, database: str) -> None:
    async with admin_engine.connect() as conn:
        await conn.execute(
            text(
                f"CREATE DATABASE IF NOT EXISTS {_quote_ident(database)} "
                "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
            )
        )
        await conn.commit()


async def _target_database_accessible(target_engine: AsyncEngine) -> bool:
    try:
        async with target_engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except SQLAlchemyError:
        return False


async def _bootstrap_schema_with_app(mysql_db_url: str, *, skip_database_create: bool) -> None:
    """
    Use app init flow to create the latest schema and compatibility patches.
    """
    if str(BACKEND_ROOT) not in sys.path:
        sys.path.insert(0, str(BACKEND_ROOT))

    os.environ["DB_PROVIDER"] = "mysql"
    os.environ["DATABASE_URL"] = mysql_db_url
    os.environ["ARBORIS_SKIP_DATABASE_CREATE"] = "1" if skip_database_create else "0"

    from app.db.init_db import init_db  # pylint: disable=import-outside-toplevel

    await init_db()


async def _clone_missing_table(
    source_conn: AsyncConnection,
    target_conn: AsyncConnection,
    table_name: str,
) -> bool:
    src_table = await _reflect_table(source_conn, table_name)

    cloned_metadata = MetaData()
    clone = Table(table_name, cloned_metadata)

    for col in src_table.columns:
        col_type = col.type
        if isinstance(col_type, NullType):
            # SQLite reflection can return NullType for unknown types.
            # Use TEXT-like fallback to avoid migration abort.
            col_type = Text()
        clone.append_column(
            Column(
                col.name,
                col_type,
                primary_key=bool(col.primary_key),
                nullable=bool(col.nullable),
            )
        )

    def _create(sync_conn):
        cloned_metadata.create_all(sync_conn, tables=[clone], checkfirst=True)

    try:
        await target_conn.run_sync(_create)
        await target_conn.commit()
        return True
    except SQLAlchemyError:
        await target_conn.rollback()
        return False


async def _copy_table_data(
    source_conn: AsyncConnection,
    target_conn: AsyncConnection,
    table_name: str,
    *,
    chunk_size: int,
    truncate_target: bool,
) -> TableResult:
    result = TableResult(table=table_name)

    src_table = await _reflect_table(source_conn, table_name)
    tgt_table = await _reflect_table(target_conn, table_name)

    src_columns = [col.name for col in src_table.columns]
    tgt_columns = [col.name for col in tgt_table.columns]

    source_only = sorted(set(src_columns) - set(tgt_columns))
    target_only = sorted(set(tgt_columns) - set(src_columns))

    result.source_only_columns = source_only
    result.target_only_columns = target_only

    common_columns = [name for name in src_columns if name in set(tgt_columns)]
    if not common_columns:
        result.status = "skipped"
        result.message = "no common columns"
        return result

    target_json_columns = {
        col.name
        for col in tgt_table.columns
        if isinstance(col.type, JSON) or col.type.__class__.__name__.lower() == "json"
    }

    result.source_rows = await _count_rows(source_conn, table_name)

    if truncate_target:
        await target_conn.execute(text(f"TRUNCATE TABLE {_quote_ident(table_name)}"))
        await target_conn.commit()

    stream = await source_conn.stream(select(src_table))
    buffer: list[dict[str, Any]] = []
    inserted = 0

    async for row in stream.mappings():
        payload: dict[str, Any] = {}
        for col in common_columns:
            value = row.get(col)
            if col in target_json_columns:
                value = _normalize_json_value(value)
            payload[col] = value
        buffer.append(payload)

        if len(buffer) >= chunk_size:
            await target_conn.execute(insert(tgt_table), buffer)
            await target_conn.commit()
            inserted += len(buffer)
            buffer.clear()

    if buffer:
        await target_conn.execute(insert(tgt_table), buffer)
        await target_conn.commit()
        inserted += len(buffer)

    result.copied_rows = inserted
    result.target_rows = await _count_rows(target_conn, table_name)

    if result.target_rows < result.copied_rows:
        result.status = "warning"
        result.message = "target row count is smaller than copied rows"
    else:
        result.status = "ok"
        result.message = "copied"

    return result


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Migrate Arboris primary SQLite DB to MySQL and validate table/column differences."
    )
    parser.add_argument(
        "--sqlite-path",
        default="backend/storage/arboris.db",
        help="Path to SQLite DB file (default: backend/storage/arboris.db)",
    )
    parser.add_argument("--mysql-host", default=os.getenv("MYSQL_HOST", DEFAULT_MYSQL_HOST))
    parser.add_argument(
        "--mysql-port",
        type=int,
        default=int(os.getenv("MYSQL_PORT", str(DEFAULT_MYSQL_PORT))),
    )
    parser.add_argument("--mysql-user", default=os.getenv("MYSQL_USER", DEFAULT_MYSQL_USER))
    parser.add_argument("--mysql-password", default=os.getenv("MYSQL_PASSWORD", ""))
    parser.add_argument("--mysql-db", default=os.getenv("MYSQL_DATABASE", DEFAULT_MYSQL_DATABASE))
    parser.add_argument("--chunk-size", type=int, default=1000)
    parser.add_argument(
        "--no-bootstrap-schema",
        action="store_true",
        help="Skip app-level schema bootstrap (not recommended).",
    )
    parser.add_argument(
        "--skip-create-db",
        action="store_true",
        help="Assume target database already exists and never run CREATE DATABASE.",
    )
    parser.add_argument(
        "--truncate-target",
        action="store_true",
        help="TRUNCATE target tables before copy (recommended for first full migration).",
    )
    parser.add_argument(
        "--report-file",
        default="backend/storage/logs/sqlite_to_mysql_report.json",
        help="Path to write migration report JSON.",
    )
    return parser.parse_args()


async def _run() -> int:
    args = _parse_args()
    args.mysql_host = _normalize_mysql_host(args.mysql_host)

    if not args.mysql_password:
        print("ERROR: MYSQL_PASSWORD is required (pass --mysql-password or env MYSQL_PASSWORD).")
        return 2

    if not args.mysql_host:
        print("ERROR: MYSQL_HOST is required and must be a plain hostname or IP.")
        return 2

    sqlite_path = Path(args.sqlite_path).expanduser()
    if not sqlite_path.is_absolute():
        sqlite_path = (PROJECT_ROOT / sqlite_path).resolve()
    if not sqlite_path.exists():
        print(f"ERROR: SQLite file not found: {sqlite_path}")
        return 2

    admin_url, mysql_db_url = _build_mysql_urls(
        host=args.mysql_host,
        port=args.mysql_port,
        user=args.mysql_user,
        password=args.mysql_password,
        database=args.mysql_db,
    )
    sqlite_url = f"sqlite+aiosqlite:///{sqlite_path.as_posix()}"

    report = MigrationReport(
        started_at=datetime.now().isoformat(timespec="seconds"),
        source_sqlite=str(sqlite_path),
        target_mysql=f"{args.mysql_user}@{args.mysql_host}:{args.mysql_port}/{args.mysql_db}",
        bootstrap_schema=not args.no_bootstrap_schema,
        truncate_target=args.truncate_target,
        chunk_size=args.chunk_size,
    )

    source_engine = create_async_engine(sqlite_url, future=True)
    admin_engine = create_async_engine(admin_url, future=True)
    target_engine = create_async_engine(mysql_db_url, future=True)

    try:
        target_database_ready = await _target_database_accessible(target_engine)

        if not target_database_ready:
            if args.skip_create_db:
                raise RuntimeError(
                    "Target database is not accessible while --skip-create-db is enabled. "
                    "Ensure the database already exists and the user can connect to it."
                )
            await _ensure_mysql_database(admin_engine, args.mysql_db)
            target_database_ready = await _target_database_accessible(target_engine)
            if not target_database_ready:
                raise RuntimeError(
                    "Target database is still not accessible after CREATE DATABASE."
                )

        if not args.no_bootstrap_schema:
            await _bootstrap_schema_with_app(
                mysql_db_url,
                skip_database_create=True,
            )

        async with source_engine.connect() as source_conn, target_engine.connect() as target_conn:
            report.source_tables = await _get_tables(source_conn, sqlite=True)
            report.target_tables_before = await _get_tables(target_conn)

            source_set = set(report.source_tables)
            target_before_set = set(report.target_tables_before)
            report.source_only_tables = sorted(source_set - target_before_set)
            report.target_only_tables = sorted(target_before_set - source_set)

            if report.source_only_tables:
                await target_conn.execute(text("SET FOREIGN_KEY_CHECKS=0"))
                await target_conn.commit()
                for table_name in report.source_only_tables:
                    created = await _clone_missing_table(source_conn, target_conn, table_name)
                    if created:
                        report.created_missing_tables.append(table_name)
                    else:
                        report.errors.append(
                            f"Failed to create missing table on MySQL: {table_name}"
                        )
                await target_conn.execute(text("SET FOREIGN_KEY_CHECKS=1"))
                await target_conn.commit()

            report.target_tables_after = await _get_tables(target_conn)
            target_after_set = set(report.target_tables_after)

            tables_to_copy = [t for t in report.source_tables if t in target_after_set]
            await target_conn.execute(text("SET FOREIGN_KEY_CHECKS=0"))
            await target_conn.commit()

            for table_name in tables_to_copy:
                try:
                    table_result = await _copy_table_data(
                        source_conn,
                        target_conn,
                        table_name,
                        chunk_size=args.chunk_size,
                        truncate_target=args.truncate_target,
                    )
                    report.table_results.append(table_result)
                except SQLAlchemyError as exc:
                    await target_conn.rollback()
                    report.table_results.append(
                        TableResult(
                            table=table_name,
                            status="error",
                            message=str(exc),
                        )
                    )
                    report.errors.append(f"{table_name}: {exc}")

            await target_conn.execute(text("SET FOREIGN_KEY_CHECKS=1"))
            await target_conn.commit()

    except Exception as exc:  # noqa: BLE001
        report.errors.append(str(exc))
    finally:
        report.finished_at = datetime.now().isoformat(timespec="seconds")
        await source_engine.dispose()
        await admin_engine.dispose()
        await target_engine.dispose()

    report_path = Path(args.report_file).expanduser()
    if not report_path.is_absolute():
        report_path = (PROJECT_ROOT / report_path).resolve()
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(
            {
                "started_at": report.started_at,
                "finished_at": report.finished_at,
                "source_sqlite": report.source_sqlite,
                "target_mysql": report.target_mysql,
                "bootstrap_schema": report.bootstrap_schema,
                "truncate_target": report.truncate_target,
                "chunk_size": report.chunk_size,
                "source_tables": report.source_tables,
                "target_tables_before": report.target_tables_before,
                "target_tables_after": report.target_tables_after,
                "source_only_tables": report.source_only_tables,
                "target_only_tables": report.target_only_tables,
                "created_missing_tables": report.created_missing_tables,
                "table_results": [
                    {
                        "table": item.table,
                        "source_rows": item.source_rows,
                        "target_rows": item.target_rows,
                        "copied_rows": item.copied_rows,
                        "status": item.status,
                        "message": item.message,
                        "source_only_columns": item.source_only_columns,
                        "target_only_columns": item.target_only_columns,
                    }
                    for item in report.table_results
                ],
                "errors": report.errors,
                "ok": report.ok,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    copied_ok = sum(1 for t in report.table_results if t.status == "ok")
    copied_warn = sum(1 for t in report.table_results if t.status == "warning")
    copied_skip = sum(1 for t in report.table_results if t.status == "skipped")
    copied_err = sum(1 for t in report.table_results if t.status == "error")

    print("")
    print("=== SQLite -> MySQL migration summary ===")
    print(f"Source DB     : {report.source_sqlite}")
    print(f"Target DB     : {report.target_mysql}")
    print(f"Tables(source): {len(report.source_tables)}")
    print(f"Created tables: {len(report.created_missing_tables)}")
    print(f"Results       : ok={copied_ok}, warning={copied_warn}, skipped={copied_skip}, error={copied_err}")
    print(f"Report file   : {report_path}")
    if report.errors:
        print("Errors:")
        for err in report.errors:
            print(f"  - {err}")
    print("=========================================")

    return 0 if report.ok else 1


def main() -> None:
    exit_code = asyncio.run(_run())
    raise SystemExit(exit_code)


if __name__ == "__main__":
    main()
