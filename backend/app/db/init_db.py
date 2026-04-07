# AIMETA P=数据库初始化_创建表和默认数据|R=创建表_初始化管理员|NR=不含业务逻辑|E=init_db|X=internal|A=初始化函数|D=sqlalchemy|S=db|RD=./README.ai
import logging

from pathlib import Path

from sqlalchemy import inspect, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.engine import URL, make_url
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from ..core.config import settings
from ..core.security import hash_password
from ..models import Prompt, SystemConfig, User
from ..models.key_location import KeyLocation
from ..models.faction import Faction
from ..models.novel import NovelBlueprint
from .base import Base
from .system_config_defaults import SYSTEM_CONFIG_DEFAULTS
from .session import AsyncSessionLocal, engine

logger = logging.getLogger(__name__)


async def init_db() -> None:
    """初始化数据库结构并确保默认管理员存在。"""

    await _ensure_database_exists()

    # ---- 第一步：创建所有表结构 ----
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("数据库表结构已初始化")
    await _ensure_schema_updates()

    # ---- 第二步：确保管理员账号至少存在一个 ----
    async with AsyncSessionLocal() as session:
        admin_exists = await session.execute(select(User).where(User.is_admin.is_(True)))
        if not admin_exists.scalars().first():
            logger.warning("未检测到管理员账号，正在创建默认管理员 ...")
            admin_user = User(
                username=settings.admin_default_username,
                email=settings.admin_default_email,
                hashed_password=hash_password(settings.admin_default_password),
                is_admin=True,
            )

            session.add(admin_user)
            try:
                await session.commit()
                logger.info("默认管理员创建完成：%s", settings.admin_default_username)
            except IntegrityError:
                await session.rollback()
                logger.exception("默认管理员创建失败，可能是并发启动导致，请检查数据库状态")

        # ---- 第三步：同步系统配置到数据库 ----
        for entry in SYSTEM_CONFIG_DEFAULTS:
            value = entry.value_getter(settings)
            if value is None:
                continue
            existing = await session.get(SystemConfig, entry.key)
            if existing:
                if entry.description and existing.description != entry.description:
                    existing.description = entry.description
                continue
            session.add(
                SystemConfig(
                    key=entry.key,
                    value=value,
                    description=entry.description,
                )
            )

        await _ensure_default_prompts(session)

        await session.commit()


async def _ensure_database_exists() -> None:
    """在首次连接前确认数据库存在，针对不同驱动做最小化准备工作。"""
    if settings.arboris_skip_database_create:
        return

    url = make_url(settings.sqlalchemy_database_uri)

    if url.get_backend_name() == "sqlite":
        # SQLite 采用文件数据库，确保父目录存在即可，无需额外建库语句
        db_path = Path(url.database or "").expanduser()
        if not db_path.is_absolute():
            project_root = Path(__file__).resolve().parents[2]
            db_path = (project_root / db_path).resolve()
        db_path.parent.mkdir(parents=True, exist_ok=True)
        return

    database = (url.database or "").strip("/")
    if not database:
        return

    admin_url = URL.create(
        drivername=url.drivername,
        username=url.username,
        password=url.password,
        host=url.host,
        port=url.port,
        database=None,
        query=url.query,
    )

    admin_engine = create_async_engine(
        admin_url.render_as_string(hide_password=False),
        isolation_level="AUTOCOMMIT",
    )
    async with admin_engine.begin() as conn:
        await conn.execute(text(f"CREATE DATABASE IF NOT EXISTS `{database}`"))
    await admin_engine.dispose()


async def _ensure_schema_updates() -> None:
    """补齐历史版本缺失的列，避免旧库在新版本报错。"""
    async with engine.begin() as conn:
        def _upgrade(sync_conn):
            inspector = inspect(sync_conn)

            def _ensure_index(table_name: str, index_name: str, columns_sql: str) -> None:
                if not inspector.has_table(table_name):
                    return
                existing_indexes = {idx["name"] for idx in inspector.get_indexes(table_name)}
                if index_name in existing_indexes:
                    return
                sync_conn.execute(
                    text(f"CREATE INDEX {index_name} ON {table_name} ({columns_sql})")
                )
                logger.info("已为 %s 表补充索引 %s", table_name, index_name)

            # chapter_outlines.metadata 补列
            columns = {col["name"] for col in inspector.get_columns("chapter_outlines")}
            if "metadata" not in columns:
                sync_conn.execute(text("ALTER TABLE chapter_outlines ADD COLUMN metadata JSON"))

            # factions.first_appear_chapter 补列（新增字段）
            if inspector.has_table("factions"):
                faction_cols = {col["name"] for col in inspector.get_columns("factions")}
                if "first_appear_chapter" not in faction_cols:
                    sync_conn.execute(
                        text("ALTER TABLE factions ADD COLUMN first_appear_chapter INTEGER NULL")
                    )
                    logger.info("已为 factions 表补充 first_appear_chapter 列")

            # blueprint_characters.is_protagonist 补列（新增字段）
            if inspector.has_table("blueprint_characters"):
                char_cols = {col["name"] for col in inspector.get_columns("blueprint_characters")}
                if "is_protagonist" not in char_cols:
                    sync_conn.execute(
                        text("ALTER TABLE blueprint_characters ADD COLUMN is_protagonist INTEGER DEFAULT 0")
                    )
                    logger.info("已为 blueprint_characters 表补充 is_protagonist 列")

            if inspector.has_table("novel_blueprints"):
                blueprint_cols = {col["name"] for col in inspector.get_columns("novel_blueprints")}
                if "total_chapters" not in blueprint_cols:
                    sync_conn.execute(
                        text("ALTER TABLE novel_blueprints ADD COLUMN total_chapters INTEGER DEFAULT 0")
                    )
                    logger.info("Added missing novel_blueprints.total_chapters column")

            _ensure_index(
                "novel_conversations",
                "ix_novel_conversations_project_id_seq",
                "project_id, seq",
            )
            _ensure_index(
                "chapter_outlines",
                "ix_chapter_outlines_project_id_chapter_number",
                "project_id, chapter_number",
            )
            _ensure_index(
                "chapters",
                "ix_chapters_project_id_chapter_number",
                "project_id, chapter_number",
            )
            _ensure_index(
                "chapter_versions",
                "ix_chapter_versions_chapter_id_created_at",
                "chapter_id, created_at",
            )
            _ensure_index(
                "chapter_evaluations",
                "ix_chapter_evaluations_chapter_id_created_at",
                "chapter_id, created_at",
            )
            _ensure_index(
                "key_locations",
                "ix_key_locations_project_id_first_appear_chapter_id",
                "project_id, first_appear_chapter, id",
            )

            # ---- 趋势数据表新字段 ----
            if inspector.has_table("trend_snapshots"):
                snapshot_cols = {col["name"] for col in inspector.get_columns("trend_snapshots")}
                if "data_source" not in snapshot_cols:
                    sync_conn.execute(text("ALTER TABLE trend_snapshots ADD COLUMN data_source VARCHAR(32) DEFAULT 'scraping'"))
                    logger.info("已为 trend_snapshots 表补充 data_source 列")
                if "data_quality_score" not in snapshot_cols:
                    sync_conn.execute(text("ALTER TABLE trend_snapshots ADD COLUMN data_quality_score FLOAT DEFAULT 0.0"))
                    logger.info("已为 trend_snapshots 表补充 data_quality_score 列")
                if "fetch_duration_ms" not in snapshot_cols:
                    sync_conn.execute(text("ALTER TABLE trend_snapshots ADD COLUMN fetch_duration_ms INTEGER DEFAULT 0"))
                    logger.info("已为 trend_snapshots 表补充 fetch_duration_ms 列")
                if "error_message" not in snapshot_cols:
                    sync_conn.execute(text("ALTER TABLE trend_snapshots ADD COLUMN error_message VARCHAR(512)"))
                    logger.info("已为 trend_snapshots 表补充 error_message 列")

            if inspector.has_table("ranking_books"):
                book_cols = {col["name"] for col in inspector.get_columns("ranking_books")}
                if "is_enriched" not in book_cols:
                    sync_conn.execute(text("ALTER TABLE ranking_books ADD COLUMN is_enriched BOOLEAN DEFAULT 0"))
                    logger.info("已为 ranking_books 表补充 is_enriched 列")
                if "original_data" not in book_cols:
                    sync_conn.execute(text("ALTER TABLE ranking_books ADD COLUMN original_data JSON"))
                    logger.info("已为 ranking_books 表补充 original_data 列")

            # ---- trend_reports 表新字段 ----
            if inspector.has_table("trend_reports"):
                report_cols = {col["name"] for col in inspector.get_columns("trend_reports")}
                if "category" not in report_cols:
                    sync_conn.execute(text("ALTER TABLE trend_reports ADD COLUMN category VARCHAR(64) DEFAULT 'all'"))
                    sync_conn.execute(text("UPDATE trend_reports SET category = 'all' WHERE category IS NULL"))
                    logger.info("已为 trend_reports 表补充 category 列")
                if "hot_elements" not in report_cols:
                    sync_conn.execute(text("ALTER TABLE trend_reports ADD COLUMN hot_elements JSON"))
                    logger.info("已为 trend_reports 表补充 hot_elements 列")
                if "reader_preferences" not in report_cols:
                    sync_conn.execute(text("ALTER TABLE trend_reports ADD COLUMN reader_preferences JSON"))
                    logger.info("已为 trend_reports 表补充 reader_preferences 列")
                if "opportunities" not in report_cols:
                    sync_conn.execute(text("ALTER TABLE trend_reports ADD COLUMN opportunities JSON"))
                    logger.info("已为 trend_reports 表补充 opportunities 列")
                if "creation_suggestions" not in report_cols:
                    sync_conn.execute(text("ALTER TABLE trend_reports ADD COLUMN creation_suggestions JSON"))
                    logger.info("已为 trend_reports 表补充 creation_suggestions 列")
                _ensure_index(
                    "trend_reports",
                    "ix_trend_reports_platform_category_date",
                    "platform, category, report_date",
                )

        await conn.run_sync(_upgrade)

    # 迁移旧 world_setting JSON 数据到新表
    await _migrate_world_setting_to_tables()


async def _migrate_world_setting_to_tables() -> None:
    """
    一次性将 novel_blueprints.world_setting 中的 key_locations 和 factions
    迁移到对应的独立表，按 project_id + name 唯一性检查保证幂等。
    """
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(NovelBlueprint))
        blueprints = list(result.scalars().all())

        migrated_loc = 0
        migrated_fac = 0

        for bp in blueprints:
            ws = bp.world_setting or {}
            project_id = bp.project_id

            # ── 迁移 key_locations ──
            raw_locations = ws.get("key_locations", []) or ws.get("locations", [])
            for item in raw_locations:
                if not isinstance(item, dict):
                    continue
                name = (item.get("name") or "").strip()
                if not name:
                    continue
                try:
                    existing = await session.execute(
                        select(KeyLocation).where(
                            KeyLocation.project_id == project_id,
                            KeyLocation.name == name,
                        )
                    )
                    if existing.scalar_one_or_none() is None:
                        session.add(KeyLocation(
                            project_id=project_id,
                            name=name,
                            description=item.get("description") or "",
                            first_appear_chapter=item.get("first_appear_chapter"),
                        ))
                        migrated_loc += 1
                except Exception as e:
                    logger.warning(f"[Migration] key_location 迁移失败 ({project_id}/{name}): {e}")

            # ── 迁移 factions ──
            raw_factions = ws.get("factions", [])
            for item in raw_factions:
                if not isinstance(item, dict):
                    continue
                name = (item.get("name") or "").strip()
                if not name:
                    continue
                try:
                    existing = await session.execute(
                        select(Faction).where(
                            Faction.project_id == project_id,
                            Faction.name == name,
                        )
                    )
                    if existing.scalar_one_or_none() is None:
                        session.add(Faction(
                            project_id=project_id,
                            name=name,
                            description=item.get("description") or "",
                            first_appear_chapter=item.get("first_appear_chapter"),
                        ))
                        migrated_fac += 1
                except Exception as e:
                    logger.warning(f"[Migration] faction 迁移失败 ({project_id}/{name}): {e}")

        await session.commit()
        if migrated_loc or migrated_fac:
            logger.info(f"[Migration] world_setting 数据迁移完成: +{migrated_loc} 地点, +{migrated_fac} 阵营")


async def _ensure_default_prompts(session: AsyncSession) -> None:
    prompts_dir = Path(__file__).resolve().parents[2] / "prompts"
    if not prompts_dir.is_dir():
        return

    result = await session.execute(select(Prompt.name))
    existing_names = set(result.scalars().all())

    for prompt_file in sorted(prompts_dir.glob("*.md")):
        name = prompt_file.stem
        if name in existing_names:
            continue
        content = prompt_file.read_text(encoding="utf-8")
        session.add(Prompt(name=name, content=content))
