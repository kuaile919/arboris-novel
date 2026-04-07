#!/usr/bin/env python3
"""测试手动导入功能"""
import asyncio
import sys
from datetime import datetime

sys.path.insert(0, '/backend')

from app.db.session import AsyncSessionLocal
from app.services.trend.scraping_service import TrendScrapingService

# 测试数据 - 模拟排行榜文本
TEST_DATA = """
1. 《斗破苍穹》 天蚕土豆 玄幻 已完结 523万字
2. 《凡人修仙传》 忘语 仙侠 已完结 771万字
3. 《诡秘之主》 爱潜水的乌贼 玄幻 已完结 447万字
4. 《大奉打更人》 卖报小郎君 仙侠 已完结 380万字
5. 《雪中悍刀行》 烽火戏诸侯 玄幻 已完结 454万字
"""


async def test_manual_import():
    """测试手动导入"""
    print("=" * 60)
    print("[测试] 手动导入功能")
    print("=" * 60)

    async with AsyncSessionLocal() as session:
        try:
            service = TrendScrapingService(session)

            # 执行导入
            books = await service.import_manual_data(
                text=TEST_DATA,
                platform="qidian",
                category="manual_test"
            )

            print(f"\n导入成功!")
            print(f"导入书籍数: {len(books)}")

            for book in books[:3]:
                print(f"\n  - {book['title']}")
                print(f"    作者: {book.get('author', '未知')}")
                print(f"    题材: {book.get('genre', '未分类')}")

            # 提交事务
            await session.commit()
            print("\n数据已保存到数据库")
            return True

        except Exception as e:
            await session.rollback()
            print(f"\n导入失败: {e}")
            import traceback
            traceback.print_exc()
            return False


async def test_data_enrichment():
    """测试数据补全服务"""
    print("\n" + "=" * 60)
    print("[测试] 数据补全服务")
    print("=" * 60)

    from app.services.trend.data_enrichment import DataEnrichmentService
    from app.services.trend.base_scraper import ScrapedBook

    async with AsyncSessionLocal() as session:
        try:
            service = DataEnrichmentService(session)

            # 测试数据 - 缺少题材和标签
            test_book = ScrapedBook(
                rank=1,
                title="重生之都市修仙",
                author="十里剑神",
                genre="",  # 空
                tags="",   # 空
                description="渡劫期大修士陈凡陨落在天劫中，却一梦五百年重回地球的年少时代。",
                word_count="500万字"
            )

            print(f"补全前:")
            print(f"  标题: {test_book.title}")
            print(f"  题材: {test_book.genre or '(空)'}")
            print(f"  标签: {test_book.tags or '(空)'}")

            enriched = await service.enrich_book(test_book)

            print(f"\n补全后:")
            print(f"  标题: {enriched.title}")
            print(f"  题材: {enriched.genre or '(空)'}")
            print(f"  标签: {enriched.tags or '(空)'}")

            return bool(enriched.genre or enriched.tags)

        except Exception as e:
            print(f"\n补全失败: {e}")
            import traceback
            traceback.print_exc()
            return False


async def main():
    print("\n" + "=" * 60)
    print("         网文趋势服务测试")
    print("=" * 60)
    print()

    results = {
        "手动导入": await test_manual_import(),
        "数据补全": await test_data_enrichment(),
    }

    print("\n" + "=" * 60)
    print("[测试结果汇总]")
    print("=" * 60)
    for name, passed in results.items():
        status = "通过" if passed else "失败"
        print(f"  {name}: {status}")

    all_passed = all(results.values())
    print()
    if all_passed:
        print("测试通过!")
    else:
        print("部分测试失败")

    return all_passed


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
