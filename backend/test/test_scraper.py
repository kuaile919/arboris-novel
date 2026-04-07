#!/usr/bin/env python3
"""测试网文平台爬虫功能"""
import asyncio
import sys
import json
from datetime import datetime

sys.path.insert(0, '/backend')

from app.services.trend.qidian_scraper import QidianScraper
from app.services.trend.fanqie_scraper import FanqieScraper


async def test_qidian():
    """测试起点爬虫"""
    print("=" * 60)
    print("[测试1] 起点中文网爬虫")
    print("=" * 60)

    scraper = QidianScraper()

    try:
        result = await scraper.fetch_ranking(category="hot", limit=10)

        print(f"平台: {result.platform}")
        print(f"分类: {result.category}")
        print(f"书籍数量: {len(result.books)}")
        print()

        if result.books:
            print("前5本书籍:")
            for i, book in enumerate(result.books[:5], 1):
                print(f"  {i}. {book.title}")
                print(f"     作者: {book.author or '未知'}")
                print(f"     题材: {book.genre or '未分类'}")
                print(f"     热度: {book.heat_score}")
                print(f"     字数: {book.word_count or '未知'}")
                print()
            return True
        else:
            print("警告: 没有抓取到书籍")
            return False

    except Exception as e:
        print(f"起点爬虫测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_fanqie():
    """测试番茄爬虫"""
    print("=" * 60)
    print("[测试2] 番茄小说爬虫")
    print("=" * 60)

    scraper = FanqieScraper()

    try:
        result = await scraper.fetch_ranking(category="hot", limit=10)

        print(f"平台: {result.platform}")
        print(f"分类: {result.category}")
        print(f"书籍数量: {len(result.books)}")
        print()

        if result.books:
            print("前5本书籍:")
            for i, book in enumerate(result.books[:5], 1):
                print(f"  {i}. {book.title}")
                print(f"     作者: {book.author or '未知'}")
                print(f"     题材: {book.genre or '未分类'}")
                print(f"     热度: {book.heat_score}")
                print(f"     字数: {book.word_count or '未知'}")
                print()
            return True
        else:
            print("警告: 没有抓取到书籍")
            return False

    except Exception as e:
        print(f"番茄爬虫测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_data_quality():
    """测试数据质量评估"""
    print("=" * 60)
    print("[测试3] 数据质量评估")
    print("=" * 60)

    scraper = QidianScraper()

    try:
        result = await scraper.fetch_ranking(category="hot", limit=5)

        if not result.books:
            print("错误: 没有抓取到书籍，无法评估质量")
            return False

        print(f"总书籍数: {len(result.books)}")

        # 统计字段完整度
        has_author = sum(1 for b in result.books if b.author)
        has_genre = sum(1 for b in result.books if b.genre)
        has_description = sum(1 for b in result.books if b.description)
        has_heat_score = sum(1 for b in result.books if b.heat_score > 0)
        has_word_count = sum(1 for b in result.books if b.word_count)

        total = len(result.books)
        print(f"有作者: {has_author}/{total} ({has_author/total*100:.1f}%)")
        print(f"有题材: {has_genre}/{total} ({has_genre/total*100:.1f}%)")
        print(f"有简介: {has_description}/{total} ({has_description/total*100:.1f}%)")
        print(f"有热度: {has_heat_score}/{total} ({has_heat_score/total*100:.1f}%)")
        print(f"有字数: {has_word_count}/{total} ({has_word_count/total*100:.1f}%)")
        print()

        return has_author > 0 and has_genre > 0

    except Exception as e:
        print(f"数据质量测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


async def main():
    print("\n")
    print("=" * 60)
    print("         网文爬虫功能测试")
    print("=" * 60)
    print()

    results = {
        "起点中文网": await test_qidian(),
        "番茄小说": await test_fanqie(),
        "数据质量": await test_data_quality(),
    }

    print("=" * 60)
    print("[测试结果汇总]")
    print("=" * 60)
    for name, passed in results.items():
        status = "通过" if passed else "失败"
        print(f"  {name}: {status}")
    print()

    all_passed = all(results.values())
    if all_passed:
        print("所有测试通过!")
    else:
        print("部分测试失败，请检查日志")

    return all_passed


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
