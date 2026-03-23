"""
关键地点数据模型

存储小说中重要地理位置、场所、建筑等信息：
- 地点名称和描述
- 首次出现章节
- 地点类型和所属区域
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import JSON, DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.dialects.mysql import LONGTEXT
from sqlalchemy.orm import Mapped, mapped_column

from ..db.base import Base

LONG_TEXT_TYPE = Text().with_variant(LONGTEXT, "mysql")


class KeyLocation(Base):
    """关键地点实体"""

    __tablename__ = "key_locations"
    __table_args__ = (
        Index(
            "ix_key_locations_project_id_first_appear_chapter_id",
            "project_id",
            "first_appear_chapter",
            "id",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("novel_projects.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # ===== 基础信息 =====
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(LONG_TEXT_TYPE)

    # ===== 地点属性 =====
    location_type: Mapped[Optional[str]] = mapped_column(String(64))   # 城市/山脉/建筑/洞穴等
    region: Mapped[Optional[str]] = mapped_column(String(255))          # 所属地区/大陆
    significance: Mapped[Optional[str]] = mapped_column(LONG_TEXT_TYPE) # 在故事中的意义

    # ===== 故事追踪 =====
    first_appear_chapter: Mapped[Optional[int]] = mapped_column(Integer)

    # ===== 元数据 =====
    extra: Mapped[Optional[dict]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
