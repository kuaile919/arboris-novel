"""
关键地点服务

提供关键地点的 CRUD 和批量 upsert 操作。
"""
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.key_location import KeyLocation


class KeyLocationService:
    """关键地点服务"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_locations_by_project(self, project_id: str) -> List[KeyLocation]:
        result = await self.db.execute(
            select(KeyLocation)
            .where(KeyLocation.project_id == project_id)
            .order_by(KeyLocation.first_appear_chapter.asc().nullslast(), KeyLocation.id.asc())
        )
        return list(result.scalars().all())

    async def get_location(self, location_id: int) -> Optional[KeyLocation]:
        result = await self.db.execute(
            select(KeyLocation).where(KeyLocation.id == location_id)
        )
        return result.scalar_one_or_none()

    async def create_location(self, project_id: str, data: dict) -> KeyLocation:
        loc = KeyLocation(project_id=project_id)
        for key, value in data.items():
            if hasattr(loc, key):
                setattr(loc, key, value)
        self.db.add(loc)
        await self.db.commit()
        await self.db.refresh(loc)
        return loc

    async def update_location(self, location_id: int, data: dict) -> Optional[KeyLocation]:
        loc = await self.get_location(location_id)
        if loc is None:
            return None
        for key, value in data.items():
            if hasattr(loc, key):
                setattr(loc, key, value)
        await self.db.commit()
        await self.db.refresh(loc)
        return loc

    async def delete_location(self, location_id: int) -> bool:
        loc = await self.get_location(location_id)
        if loc is None:
            return False
        await self.db.delete(loc)
        await self.db.commit()
        return True

    async def upsert_locations(
        self, project_id: str, locations: List[dict]
    ) -> List[KeyLocation]:
        """
        批量 upsert：按 project_id + name 查重，已存在则更新 first_appear_chapter，
        不存在则新增。返回全量地点列表。
        """
        for item in locations:
            name = (item.get("name") or "").strip()
            if not name:
                continue

            existing_result = await self.db.execute(
                select(KeyLocation).where(
                    KeyLocation.project_id == project_id,
                    KeyLocation.name == name,
                )
            )
            existing = existing_result.scalar_one_or_none()

            if existing:
                # 仅在新值不为空时更新 first_appear_chapter
                new_chapter = item.get("first_appear_chapter")
                if new_chapter is not None and existing.first_appear_chapter is None:
                    existing.first_appear_chapter = new_chapter
                if item.get("description") and not existing.description:
                    existing.description = item["description"]
            else:
                loc = KeyLocation(
                    project_id=project_id,
                    name=name,
                    description=item.get("description") or "",
                    first_appear_chapter=item.get("first_appear_chapter"),
                    location_type=item.get("location_type") or item.get("type"),
                )
                self.db.add(loc)

        await self.db.commit()
        return await self.get_locations_by_project(project_id)

    async def replace_all(self, project_id: str, locations: List[dict]) -> List[KeyLocation]:
        """
        全量替换：删除该项目的所有地点，再批量插入。
        用于前端编辑器提交整体列表的场景。
        """
        existing_result = await self.db.execute(
            select(KeyLocation).where(KeyLocation.project_id == project_id)
        )
        for loc in existing_result.scalars().all():
            await self.db.delete(loc)

        for item in locations:
            name = (item.get("name") or "").strip()
            if not name:
                continue
            self.db.add(KeyLocation(
                project_id=project_id,
                name=name,
                description=item.get("description") or "",
                first_appear_chapter=item.get("first_appear_chapter"),
                location_type=item.get("location_type") or item.get("type"),
            ))

        await self.db.commit()
        return await self.get_locations_by_project(project_id)
