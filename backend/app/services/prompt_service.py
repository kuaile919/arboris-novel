# AIMETA P=提示词服务_提示模板管理|R=提示词加载_缓存|NR=不含内容生成|E=PromptService|X=internal|A=服务类|D=sqlalchemy|S=db,fs|RD=./README.ai
import asyncio
import logging
from typing import Dict, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Prompt
from ..repositories.prompt_repository import PromptRepository
from ..schemas.prompt import PromptCreate, PromptRead, PromptUpdate

_CACHE: Dict[str, PromptRead] = {}
_LOCK = asyncio.Lock()
_LOADED = False


class PromptService:
    """提示词服务，提供缓存加速与 CRUD 能力。"""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.repo = PromptRepository(session)

    async def preload(self) -> None:
        global _CACHE, _LOADED
        prompts = await self.repo.list_all()
        async with _LOCK:
            _CACHE = {item.name: PromptRead.model_validate(item) for item in prompts}
            _LOADED = True

    async def get_prompt(self, name: str) -> Optional[str]:
        global _LOADED
        async with _LOCK:
            if not _LOADED:
                prompts = await self.repo.list_all()
                _CACHE.update({item.name: PromptRead.model_validate(item) for item in prompts})
                _LOADED = True
            cached = _CACHE.get(name)
        if cached:
            return cached.content

        prompt = await self.repo.get_by_name(name)
        if not prompt:
            return None

        prompt_read = PromptRead.model_validate(prompt)
        async with _LOCK:
            _CACHE[name] = prompt_read
        return prompt_read.content

    async def list_prompts(self) -> list[PromptRead]:
        prompts = await self.repo.list_all()
        return [PromptRead.model_validate(item) for item in prompts]

    async def get_prompt_by_id(self, prompt_id: int) -> Optional[PromptRead]:
        instance = await self.repo.get(id=prompt_id)
        if not instance:
            return None
        return PromptRead.model_validate(instance)

    async def create_prompt(self, payload: PromptCreate) -> PromptRead:
        data = payload.model_dump()
        tags = data.get("tags")
        if tags is not None:
            data["tags"] = ",".join(tags)
        prompt = Prompt(**data)
        await self.repo.add(prompt)
        await self.session.commit()
        prompt_read = PromptRead.model_validate(prompt)
        async with _LOCK:
            _CACHE[prompt_read.name] = prompt_read
            global _LOADED
            _LOADED = True
        return prompt_read

    async def update_prompt(self, prompt_id: int, payload: PromptUpdate) -> Optional[PromptRead]:
        instance = await self.repo.get(id=prompt_id)
        if not instance:
            return None
        update_data = payload.model_dump(exclude_unset=True)
        if "tags" in update_data and update_data["tags"] is not None:
            update_data["tags"] = ",".join(update_data["tags"])
        await self.repo.update_fields(instance, **update_data)
        await self.session.commit()
        prompt_read = PromptRead.model_validate(instance)
        async with _LOCK:
            _CACHE[prompt_read.name] = prompt_read
        return prompt_read

    async def delete_prompt(self, prompt_id: int) -> bool:
        instance = await self.repo.get(id=prompt_id)
        if not instance:
            return False
        await self.repo.delete(instance)
        await self.session.commit()
        async with _LOCK:
            _CACHE.pop(instance.name, None)
        return True

    async def append_to_prompt(self, name: str, content: str, sync_to_file: bool = True) -> bool:
        """追加内容到指定名称的提示词末尾。

        Args:
            name: 提示词名称
            content: 要追加的内容
            sync_to_file: 是否同步写入到文件系统（默认为 True）

        Returns:
            bool: 是否追加成功
        """
        import os
        import logging
        _logger = logging.getLogger(__name__)

        prompt = await self.repo.get_by_name(name)
        if not prompt:
            return False

        # 追加内容
        prompt.content = (prompt.content or "") + "\n" + content
        await self.session.commit()

        # 更新缓存
        prompt_read = PromptRead.model_validate(prompt)
        async with _LOCK:
            _CACHE[name] = prompt_read

        # 同步写入到文件系统（全量覆写，与 DB 保持一致）
        if sync_to_file:
            self._sync_prompt_to_file(name, prompt.content, _logger)

        return True

    async def append_user_feedback_rule(self, name: str, rule: str) -> bool:
        """将用户反馈规则追加到提示词的「用户反馈规则（自动添加）」区块中。

        与 append_to_prompt 不同，此方法会将所有规则合并到同一个二级标题下，
        避免反复创建重复的标题块。

        Args:
            name: 提示词名称
            rule: 要追加的规则文本

        Returns:
            bool: 是否追加成功
        """
        import logging
        _logger = logging.getLogger(__name__)

        prompt = await self.repo.get_by_name(name)
        if not prompt:
            return False

        existing = prompt.content or ""
        section_marker = "## 用户反馈规则（自动添加）"

        # 确保规则以 "- " 开头，保持列表格式
        formatted_rule = rule.strip()
        if not formatted_rule.startswith("- "):
            formatted_rule = "- " + formatted_rule

        if section_marker in existing:
            # 已有区块：将规则追加到该区块内
            parts = existing.split(section_marker, 1)
            after_section = parts[1]

            # 找到下一个二级标题的位置
            next_h2_idx = after_section.find("\n## ")
            new_content = formatted_rule + "\n"

            if next_h2_idx != -1:
                # 区块后面还有其他二级标题，在其前面插入
                updated = parts[0] + section_marker + after_section[:next_h2_idx] + "\n" + new_content + after_section[next_h2_idx:]
            else:
                # 区块在文件末尾，直接追加
                updated = parts[0] + section_marker + after_section.rstrip() + "\n" + new_content
        else:
            # 没有区块：在文件末尾创建新区块
            updated = existing.rstrip() + "\n\n---\n\n" + section_marker + "\n\n" + formatted_rule + "\n"

        # 写入 DB
        prompt.content = updated
        await self.session.commit()

        # 更新缓存
        prompt_read = PromptRead.model_validate(prompt)
        async with _LOCK:
            _CACHE[name] = prompt_read

        # 同步到文件
        self._sync_prompt_to_file(name, updated, _logger)

        return True

    @staticmethod
    def _sync_prompt_to_file(name: str, content: str, logger: logging.Logger) -> None:
        """将提示词内容全量写入文件，保持文件与 DB 一致。"""
        import os

        current_dir = os.path.dirname(os.path.abspath(__file__))
        app_dir = os.path.dirname(current_dir)
        backend_dir = os.path.dirname(app_dir)
        prompts_dir = os.path.join(backend_dir, "prompts")
        file_path = os.path.join(prompts_dir, f"{name}.md")

        logger.info(f"尝试同步写入文件: {file_path}")

        if os.path.exists(file_path):
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(content)
            logger.info(f"已同步写入文件: {file_path}")
        else:
            logger.warning(f"提示词文件不存在，跳过文件同步: {file_path}")

    async def get_prompt_id_by_name(self, name: str) -> Optional[int]:
        """根据名称获取提示词ID。"""
        prompt = await self.repo.get_by_name(name)
        return prompt.id if prompt else None
