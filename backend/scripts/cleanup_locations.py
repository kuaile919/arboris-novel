"""
清理 world_setting 中的 locations 字段，只保留 key_locations 和 factions
用法: python cleanup_locations.py [project_id]
如果不指定 project_id，则清理所有项目
"""
import asyncio
import sys
import os

# 添加项目路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select

# 数据库配置 - 从环境变量读取或使用默认路径
import os
db_path = os.environ.get('SQLITE_DB_PATH', './storage/arboris.db')
DATABASE_URL = f"sqlite+aiosqlite:///{db_path}"

async def cleanup_locations(project_id: str = None):
    """清理指定项目的 locations 字段"""
    engine = create_async_engine(DATABASE_URL)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        from app.models.novel import NovelBlueprint

        if project_id:
            # 只清理指定项目
            result = await session.execute(
                select(NovelBlueprint).where(NovelBlueprint.project_id == project_id)
            )
            blueprint = result.scalar_one_or_none()

            if not blueprint:
                print(f"项目 {project_id} 不存在")
                return

            blueprints = [blueprint]
        else:
            # 清理所有项目
            result = await session.execute(select(NovelBlueprint))
            blueprints = result.scalars().all()

        print(f"处理 {len(blueprints)} 个项目的蓝图")

        for blueprint in blueprints:
            world_setting = blueprint.world_setting or {}

            # 检查是否有 locations 字段
            if 'locations' in world_setting:
                locations_count = len(world_setting.get('locations', []))
                key_locations_count = len(world_setting.get('key_locations', []))
                factions_count = len(world_setting.get('factions', []))

                print(f"\n项目 {blueprint.project_id}:")
                print(f"  - key_locations: {key_locations_count} 个")
                print(f"  - factions: {factions_count} 个")
                print(f"  - locations: {locations_count} 个 (将被删除)")

                # 删除 locations 字段
                del world_setting['locations']
                blueprint.world_setting = world_setting

                print(f"  [OK] 已删除 locations 字段")
            else:
                print(f"\n项目 {blueprint.project_id}: 没有 locations 字段，跳过")

        await session.commit()
        print("\n[OK] 清理完成")

if __name__ == "__main__":
    # 从命令行参数获取项目ID，如果没有则清理所有
    project_id = sys.argv[1] if len(sys.argv) > 1 else None
    asyncio.run(cleanup_locations(project_id))
