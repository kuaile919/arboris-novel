"""
回滚“提前回收”的伏笔：
- 条件：伏笔状态已回收，但对应回收章节没有选中的正文版本内容。
- 动作：恢复为 planted，清空 resolved 字段，删除对应回收记录。

用法：
  python backend/scripts/repair_premature_foreshadowing_resolutions.py --dry-run
  python backend/scripts/repair_premature_foreshadowing_resolutions.py --apply
  python backend/scripts/repair_premature_foreshadowing_resolutions.py --apply --project-id <project_id>
"""

from __future__ import annotations

import argparse
from datetime import datetime
from typing import List

from sqlalchemy import delete, select
from sqlalchemy.orm import selectinload

from app.db.session import AsyncSessionLocal
from app.models.foreshadowing import Foreshadowing, ForeshadowingResolution
from app.models.novel import Chapter, ChapterVersion


def _append_note(old_note: str | None, new_line: str) -> str:
    old = (old_note or "").strip()
    return f"{old}\n{new_line}".strip() if old else new_line


async def run_repair(*, apply: bool, project_id: str | None) -> int:
    async with AsyncSessionLocal() as session:
        stmt = select(Foreshadowing).where(
            Foreshadowing.status.in_(["resolved", "revealed"])
        )
        if project_id:
            stmt = stmt.where(Foreshadowing.project_id == project_id)
        result = await session.execute(stmt)
        foreshadowings = list(result.scalars().all())

        candidate_ids: List[int] = []

        for fs in foreshadowings:
            if not fs.resolved_chapter_id:
                candidate_ids.append(fs.id)
                continue

            chapter = await session.get(Chapter, fs.resolved_chapter_id)
            if chapter is None:
                candidate_ids.append(fs.id)
                continue

            if chapter.project_id != fs.project_id:
                candidate_ids.append(fs.id)
                continue

            if not chapter.selected_version_id:
                candidate_ids.append(fs.id)
                continue

            selected_version = await session.get(ChapterVersion, chapter.selected_version_id)
            if selected_version is None:
                candidate_ids.append(fs.id)
                continue

            if not (selected_version.content or "").strip():
                candidate_ids.append(fs.id)

        print(f"[scan] resolved foreshadowings={len(foreshadowings)} candidates={len(candidate_ids)}")

        if not apply:
            if candidate_ids:
                preview = ",".join(str(i) for i in candidate_ids[:20])
                suffix = "..." if len(candidate_ids) > 20 else ""
                print(f"[dry-run] candidate_ids={preview}{suffix}")
            return len(candidate_ids)

        if not candidate_ids:
            print("[apply] no candidates, nothing changed")
            return 0

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # 恢复伏笔状态
        fs_stmt = select(Foreshadowing).where(Foreshadowing.id.in_(candidate_ids))
        fs_result = await session.execute(fs_stmt)
        candidate_fs = list(fs_result.scalars().all())
        for fs in candidate_fs:
            fs.status = "planted"
            fs.resolved_chapter_id = None
            fs.resolved_chapter_number = None
            fs.author_note = _append_note(
                fs.author_note,
                f"[系统修复 {now}] 回滚提前回收标记：回收章节缺少已选正文版本。",
            )

        # 删除对应回收记录
        await session.execute(
            delete(ForeshadowingResolution).where(
                ForeshadowingResolution.foreshadowing_id.in_(candidate_ids)
            )
        )

        await session.commit()
        print(f"[apply] reverted={len(candidate_ids)}")
        return len(candidate_ids)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="修复提前回收的伏笔标记")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--apply", action="store_true", help="执行修复")
    mode.add_argument("--dry-run", action="store_true", help="仅扫描，不写入")
    parser.add_argument("--project-id", type=str, default=None, help="仅处理指定项目")
    return parser.parse_args()


async def _main() -> None:
    args = parse_args()
    apply = bool(args.apply)
    await run_repair(apply=apply, project_id=args.project_id)


if __name__ == "__main__":
    import asyncio

    asyncio.run(_main())

