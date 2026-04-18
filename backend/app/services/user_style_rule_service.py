import hashlib
import re
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
        text = re.sub(r"^(\d+[\.\)]\s*|[-*•]\s*)", "", text).strip()
        return text[: UserStyleRuleService.MAX_RULE_LENGTH].strip()

    @staticmethod
    def _normalize_rule_block(content: str) -> str:
        return (content or "").replace("\r\n", "\n").strip()

    @staticmethod
    def split_rules_text(content: str) -> List[str]:
        """将多行文本拆分为规则列表（兼容序号/项目符号）。"""
        lines = [(line or "").strip() for line in (content or "").splitlines()]
        rules: List[str] = []
        seen = set()
        for line in lines:
            if not line:
                continue
            normalized = UserStyleRuleService._normalize_rule(line)
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            rules.append(normalized)
        return rules

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

        project_rules: List[str] = []
        global_rules: List[str] = []
        for row in rows:
            expanded = self.split_rules_text(row.content or "")
            if row.project_id == project_id:
                project_rules.extend(expanded)
            elif row.project_id is None:
                global_rules.extend(expanded)

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

    async def get_account_rules_by_type(
        self,
        *,
        user_id: int,
        rule_type: str,
        limit: int = 200,
    ) -> List[str]:
        """获取账号级（project_id 为空）激活规则（按行拆分）。"""
        content = await self.get_account_rule_text_by_type(user_id=user_id, rule_type=rule_type)
        return self.split_rules_text(content)[:limit]

    async def get_account_rule_text_by_type(
        self,
        *,
        user_id: int,
        rule_type: str,
    ) -> str:
        """
        获取账号级规则文本。
        兼容历史多条记录，读取时按时间顺序拼接为单个文本块。
        """
        stmt = (
            select(UserStyleRule)
            .where(
                UserStyleRule.user_id == user_id,
                UserStyleRule.project_id.is_(None),
                UserStyleRule.rule_type == rule_type,
                UserStyleRule.is_active.is_(True),
            )
            .order_by(UserStyleRule.created_at.asc())
        )
        rows = list((await self.session.execute(stmt)).scalars().all())
        merged_parts: List[str] = []
        for row in rows:
            content = (row.content or "").strip()
            if content:
                merged_parts.append(content)
        return "\n".join(merged_parts).strip()

    async def replace_account_rules_by_type(
        self,
        *,
        user_id: int,
        rule_type: str,
        rules: List[str],
        source: Optional[str] = None,
    ) -> List[str]:
        """
        全量替换账号级规则：
        - 新规则插入
        - 已存在规则激活
        - 不在新集合中的旧规则停用
        """
        normalized: List[str] = []
        seen = set()
        for rule in rules:
            item = self._normalize_rule(rule)
            if not item or item in seen:
                continue
            seen.add(item)
            normalized.append(item)

        stmt = select(UserStyleRule).where(
            UserStyleRule.user_id == user_id,
            UserStyleRule.project_id.is_(None),
            UserStyleRule.rule_type == rule_type,
        )
        existing_rows = list((await self.session.execute(stmt)).scalars().all())
        by_content = {row.content: row for row in existing_rows}
        target_set = set(normalized)

        for item in normalized:
            existing = by_content.get(item)
            if existing:
                existing.is_active = True
                if source:
                    existing.source = source
                continue
            content_hash = self._hash(user_id, None, rule_type, item)
            self.session.add(
                UserStyleRule(
                    user_id=user_id,
                    project_id=None,
                    rule_type=rule_type,
                    content=item,
                    content_hash=content_hash,
                    source=source,
                    is_active=True,
                )
            )

        for row in existing_rows:
            if row.content not in target_set:
                row.is_active = False

        await self.session.commit()
        return normalized

    async def set_account_rule_text_by_type(
        self,
        *,
        user_id: int,
        rule_type: str,
        content: str,
        source: Optional[str] = None,
    ) -> str:
        """
        设置账号级规则文本：最终仅保留一条激活记录。
        """
        normalized_content = self._normalize_rule_block(content)
        stmt = (
            select(UserStyleRule)
            .where(
                UserStyleRule.user_id == user_id,
                UserStyleRule.project_id.is_(None),
                UserStyleRule.rule_type == rule_type,
            )
            .order_by(UserStyleRule.created_at.asc())
        )
        rows = list((await self.session.execute(stmt)).scalars().all())

        for row in rows:
            row.is_active = False

        if not normalized_content:
            await self.session.commit()
            return ""

        matched = next((row for row in rows if (row.content or "").strip() == normalized_content), None)
        if matched:
            matched.is_active = True
            if source:
                matched.source = source
            await self.session.commit()
            return normalized_content

        content_hash = self._hash(user_id, None, rule_type, normalized_content)
        new_row = UserStyleRule(
            user_id=user_id,
            project_id=None,
            rule_type=rule_type,
            content=normalized_content,
            content_hash=content_hash,
            source=source,
            is_active=True,
        )
        self.session.add(new_row)
        await self.session.commit()
        return normalized_content
