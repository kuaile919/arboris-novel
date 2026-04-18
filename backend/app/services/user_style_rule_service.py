import hashlib
from typing import List, Optional

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.user_style_rule import UserStyleRule


class UserStyleRuleService:
    """用户个人风格规则服务。"""

    MAX_RULE_LENGTH = 200

    def __init__(self, session: AsyncSession):
        self.session = session

    @staticmethod
    def _normalize_rule(rule: str) -> str:
        text = (rule or "").strip()
        if not text:
            return ""
        if text.startswith("- "):
            text = text[2:].strip()
        return text[: UserStyleRuleService.MAX_RULE_LENGTH].strip()

    @staticmethod
    def _hash(user_id: int, project_id: Optional[str], rule_type: str, content: str) -> str:
        payload = f"{user_id}|{project_id or ''}|{rule_type}|{content}"
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    async def add_rule(
        self,
        *,
        user_id: int,
        content: str,
        project_id: Optional[str] = None,
        rule_type: str = "general",
        source: Optional[str] = None,
    ) -> Optional[UserStyleRule]:
        normalized = self._normalize_rule(content)
        if not normalized:
            return None

        content_hash = self._hash(user_id, project_id, rule_type, normalized)
        stmt = select(UserStyleRule).where(UserStyleRule.content_hash == content_hash)
        existing = (await self.session.execute(stmt)).scalar_one_or_none()
        if existing:
            if not existing.is_active:
                existing.is_active = True
                await self.session.commit()
            return existing

        rule = UserStyleRule(
            user_id=user_id,
            project_id=project_id,
            rule_type=rule_type,
            content=normalized,
            content_hash=content_hash,
            source=source,
            is_active=True,
        )
        self.session.add(rule)
        await self.session.commit()
        await self.session.refresh(rule)
        return rule

    async def get_effective_rules(
        self,
        *,
        user_id: int,
        project_id: Optional[str],
        rule_types: Optional[List[str]] = None,
        limit: int = 30,
    ) -> List[str]:
        stmt = select(UserStyleRule).where(
            UserStyleRule.user_id == user_id,
            UserStyleRule.is_active.is_(True),
            or_(UserStyleRule.project_id.is_(None), UserStyleRule.project_id == project_id),
        )
        if rule_types:
            stmt = stmt.where(UserStyleRule.rule_type.in_(rule_types))
        stmt = stmt.order_by(UserStyleRule.created_at.asc())
        rows = list((await self.session.execute(stmt)).scalars().all())

        project_rules = [r.content for r in rows if r.project_id == project_id]
        global_rules = [r.content for r in rows if r.project_id is None]

        # 项目级优先，再回退到用户全局规则，且去重
        ordered = project_rules + global_rules
        deduped: List[str] = []
        seen = set()
        for item in ordered:
            key = item.strip()
            if not key or key in seen:
                continue
            seen.add(key)
            deduped.append(key)
            if len(deduped) >= limit:
                break
        return deduped
