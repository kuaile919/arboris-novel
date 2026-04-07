#!/usr/bin/env python3
"""最终测试 - 验证爬虫功能"""
import asyncio
import sys
sys.path.insert(0, '..')

from app.services.trend.fanqie_scraper import FanqieScraper
from app.services.trend.qidian_scraper import QidianScraper
from app.services.trend.base_scraper import ScrapedBook

async def test_fanqie():
    """测试番茄爬虫"""
    print("=" * 60)
    print("测试番茄小说爬虫")
    print("=" * 60)

    scraper = FanqieScraper()
    result = await scraper.fetch_ranking('hot', 10)

    print(f"平台: {result.platform}")
    print(f"分类: {result.category}")
    print(f"抓取数量: {len(result.books)}")

    if result.books:
        print("\n抓取结果 (前5本):")
        for b in result.books[:5]:
            print(f"  {b.rank}. {b.title}")
            print(f"     作者: {b.author}")
            print(f"     题材: {b.genre}")
            print(f"     字数: {b.word_count}")
        return True
    else:
        print("错误: 未抓取到书籍")
        return False

async def test_qidian():
    """测试起点爬虫"""
    print("\n" + "=" * 60)
    print("测试起点中文网爬虫")
    print("=" * 60)

    scraper = QidianScraper()
    result = await scraper.fetch_ranking('hot', 10)

    print(f"平台: {result.platform}")
    print(f"分类: {result.category}")
    print(f"抓取数量: {len(result.books)}")

    if result.books:
        print("\n抓取结果 (前5本):")
        for b in result.books[:5]:
            print(f"  {b.rank}. {b.title}")
            print(f"     作者: {b.author}")
            print(f"     题材: {b.genre}")
        return True
    else:
        print("未抓取到书籍 (网络受限或网站变更)")
        return False

async def test_manual_import():
    """测试手动导入功能"""
    print("\n" + "=" * 60)
    print("测试手动导入功能")
    print("=" * 60)

    from app.services.trend.manual_import import ManualImportHandler

    handler = ManualImportHandler()

    test_text = """
1. 《斗破苍穹》 天蚕土豆 玄幻 523万字
2. 《凡人修仙传》 忘语 仙侠 771万字
3. 《诡秘之主》 爱潜水的乌贼 玄幻 447万字
    """

    result = await handler.parse_text(test_text, 'qidian', 'manual')
    print(f"导入数量: {len(result.books)}")

    for b in result.books[:3]:
        print(f"  {b.rank}. {b.title} - {b.author}")

    return len(result.books) > 0

async def main():
    print("\n" + "=" * 60)
    print("网文爬虫功能最终测试")
    print("=" * 60)

    results = {
        '番茄小说': await test_fanqie(),
        '起点中文网': await test_qidian(),
        '手动导入': await test_manual_import(),
    }

    print("\n" + "=" * 60)
    print("测试结果汇总")
    print("=" * 60)
    for name, status in results.items():
        print(f"  {name}: {'通过' if status else '未通过/受限'}")

    print("\n说明:")
    print("- 番茄爬虫: 从 https://fanqienovel.com/rank 抓取")
    print("- 起点爬虫: 依赖网络环境，当前环境受限")
    print("- 手动导入: 作为起点无法爬取时的备用方案")

if __name__ == "__main__":
    asyncio.run(main())
