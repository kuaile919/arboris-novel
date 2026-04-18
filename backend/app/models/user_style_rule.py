from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from ..db.base import Base


class UserStyleRule(Base):
    """用户个人风格规则（可选项目级覆盖）。"""

    __tablename__ = "user_style_rules"
    __table_args__ = (
        Index("ix_user_style_rules_user_id", "user_id"),
        Index("ix_user_style_rules_user_project", "user_id", "project_id"),
        Index("ix_user_style_rules_user_type_active", "user_id", "rule_type", "is_active"),
        Index("ix_user_style_rules_content_hash", "content_hash"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False)
    project_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    rule_type: Mapped[str] = mapped_column(String(32), default="general", nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    source: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )
