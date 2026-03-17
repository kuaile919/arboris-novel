#!/usr/bin/env python
# -*- coding:utf-8 -*-
"""
# @File : test-local-embedding.py
# @Time : 2026/3/17 下午3:47
# @Author : lucho

测试本地 LM Studio Qwen3-Embedding-0.6B 集成
验证项目 .env 配置是否正确生效
"""
import sys
import os
import math

# ── 1. 直接调用 LM Studio API（快速连通性测试） ────────────────────────────
from openai import OpenAI

BASE_URL = "http://127.0.0.1:1234/v1"
API_KEY = "lm-studio"
MODEL = "text-embedding-qwen3-embedding-0.6b"

client = OpenAI(base_url=BASE_URL, api_key=API_KEY)


def get_embedding(text: str) -> list[float]:
    text = text.replace("\n", " ")
    return client.embeddings.create(input=[text], model=MODEL).data[0].embedding


def cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    return dot / (norm_a * norm_b) if norm_a and norm_b else 0.0


print("=" * 60)
print("【测试 1】LM Studio API 直连")
print("=" * 60)

try:
    vec = get_embedding("从前有一只猫。")
    print(f"  ✓ 向量维度: {len(vec)}")
    print(f"  ✓ 前 5 个值: {vec[:5]}")
except Exception as e:
    print(f"  ✗ 连接失败: {e}")
    print("  请确认 LM Studio 已启动并加载了 Qwen3-Embedding-0.6B 模型")
    sys.exit(1)

# ── 2. 语义相似度验证 ──────────────────────────────────────────────────────
print("\n【测试 2】语义相似度")
print("=" * 60)

pairs = [
    ("从前有一只猫。", "Once upon a time, there was a cat.", "中英互译（应高相似）"),
    ("今天天气很好。", "机器学习是人工智能的子领域。", "无关句子（应低相似）"),
]

for text_a, text_b, desc in pairs:
    vec_a = get_embedding(text_a)
    vec_b = get_embedding(text_b)
    sim = cosine_similarity(vec_a, vec_b)
    print(f"  {desc}: {sim:.4f}")

# ── 3. 项目配置加载验证 ────────────────────────────────────────────────────
print("\n【测试 3】项目 .env 配置加载")
print("=" * 60)

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "backend"))
try:
    from app.core.config import settings
    print(f"  embedding_provider        = {settings.embedding_provider}")
    print(f"  embedding_base_url        = {settings.embedding_base_url}")
    print(f"  embedding_api_key         = {settings.embedding_api_key}")
    print(f"  embedding_model           = {settings.embedding_model}")
    print(f"  embedding_model_vector_size = {settings.embedding_model_vector_size}")

    assert str(settings.embedding_base_url).startswith("http://127.0.0.1:1234"), \
        "embedding_base_url 未指向 LM Studio"
    assert settings.embedding_model == MODEL, \
        f"embedding_model 不匹配，期望 {MODEL}"
    print("  ✓ 配置加载正确")
except Exception as e:
    print(f"  ✗ 配置加载失败: {e}")

# ── 4. EmbeddingService 集成测试 ──────────────────────────────────────────
print("\n【测试 4】EmbeddingService 集成")
print("=" * 60)

import asyncio

async def test_embedding_service():
    from app.services.embedding_service import EmbeddingService
    svc = EmbeddingService()
    if not svc.is_available:
        print("  ✗ EmbeddingService 初始化失败，检查配置")
        return
    vec = await svc.get_embedding("测试文本")
    if vec:
        print(f"  ✓ EmbeddingService 可用，向量维度: {len(vec)}")
    else:
        print("  ✗ get_embedding 返回 None")

try:
    asyncio.run(test_embedding_service())
except Exception as e:
    print(f"  ✗ EmbeddingService 测试失败: {e}")

print("\n" + "=" * 60)
print("测试完成")

