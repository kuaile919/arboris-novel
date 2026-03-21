# AIMETA P=提示词服务_提示模板管理|R=提示词加载_缓存|NR=不含内容生成|E=PromptService|X=internal|A=服务类|D=sqlalchemy|S=db,fs|RD=./README.ai
import asyncio
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

        # 同步写入到文件系统
        if sync_to_file:
            try:
                # 获取 prompts 目录路径
                # 当前文件: backend/app/services/prompt_service.py
                # 目标目录: backend/prompts/
                current_dir = os.path.dirname(os.path.abspath(__file__))  # backend/app/services
                app_dir = os.path.dirname(current_dir)  # backend/app
                backend_dir = os.path.dirname(app_dir)  # backend
                prompts_dir = os.path.join(backend_dir, "prompts")  # backend/prompts
                file_path = os.path.join(prompts_dir, f"{name}.md")

                _logger.info(f"尝试同步写入文件: {file_path}")

                if os.path.exists(file_path):
                    with open(file_path, "a", encoding="utf-8") as f:
                        f.write(content)
                    _logger.info(f"已同步追加内容到文件: {file_path}")
                else:
                    _logger.warning(f"提示词文件不存在，跳过文件同步: {file_path}")
            except Exception as e:
                _logger.error(f"同步写入提示词文件失败: {e}")

        return True

    async def get_prompt_id_by_name(self, name: str) -> Optional[int]:
        """根据名称获取提示词ID。"""
        prompt = await self.repo.get_by_name(name)
        return prompt.id if prompt else None
