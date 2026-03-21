# 摘要生成错误处理说明

## 问题描述

在章节优化后生成摘要时，遇到 API 错误：

```
APIStatusError: {'type': 'error', 'error': {'type': 'api_error', 'message': 'Internal Network Failure'}, 'request_id': '2026031721532580d55bec1ca94a0d'}
```

## 错误原因

1. **API 服务端问题**：智谱 AI (BigModel) 的服务端返回 `Internal Network Failure`
2. **网络不稳定**：流式响应过程中连接中断
3. **临时性故障**：这类错误通常是暂时的，重试可以解决

## 解决方案

### 1. 添加重试机制

在 `llm_service.py` 的 `get_summary` 方法中添加了自动重试：

```python
async def get_summary(
    self,
    chapter_content: str,
    *,
    temperature: float = 0.2,
    user_id: Optional[int] = None,
    timeout: float = 180.0,
    system_prompt: Optional[str] = None,
    max_retries: int = 3,  # 最多重试3次
) -> str:
    # 重试机制
    last_error = None
    for attempt in range(max_retries):
        try:
            return await self._stream_and_collect(...)
        except HTTPException as exc:
            if exc.status_code == 503 and attempt < max_retries - 1:
                # 网络错误，等待后重试
                wait_time = 2 ** attempt  # 指数退避：1s, 2s, 4s
                await asyncio.sleep(wait_time)
                continue
            raise
```

**重试策略：**
- 最多重试 3 次
- 指数退避：第1次等待1秒，第2次等待2秒，第3次等待4秒
- 只对 503 错误（服务不可用）进行重试
- 其他错误（如认证失败）直接抛出

### 2. 错误处理优化

在 `optimizer.py` 中，摘要生成失败不会影响主流程：

```python
try:
    raw = await llm_service.get_summary(content, temperature=0.15, user_id=user_id)
    summary_text = remove_think_tags(raw) if raw else None
    if summary_text and chapter:
        chapter.real_summary = summary_text
        await session.commit()
except Exception as exc:
    logger.warning("章节 %s 优化后生成摘要失败: %s", chapter_number, exc)
    # 不抛出异常，继续执行向量化入库
```

**设计理念：**
- 摘要生成失败不影响优化内容的应用
- 向量化入库可以使用现有摘要或不使用摘要
- 用户可以稍后手动重新生成摘要

## 影响范围

**不影响���功能：**
- ✅ 章节优化功能正常工作
- ✅ 优化内容可以正常应用
- ✅ 向量化入库继续执行（使用现有摘要或无摘要）

**受影响的功能：**
- ⚠️ 新章节的摘要可能生成失败
- ⚠️ 向量检索可能缺少摘要信息（影响检索质量）

## 用户操作建议

### 遇到此错误时：

1. **不用担心**：优化内容已经成功应用
2. **稍后重试**：API 服务恢复后，摘要会自动生成
3. **检查网络**：确保网络连接稳定
4. **联系管理员**：如果持续失败，可能需要检查 API 配置

### 管理员操作：

1. **检查 API 状态**：访问智谱 AI 控制台查看服务状态
2. **查看日志**：检查 `backend/storage/logs/app.log` 了解详细错误
3. **调整重试参数**：如果需要，可以增加重试次数或等待时间
4. **切换 API 提供商**：考虑配置备用 API（如 OpenAI）

## 技术细节

### 错误类型

- **APIStatusError**: Anthropic SDK 的 API 状态错误
- **503 Service Unavailable**: 服务不可用（可重试）
- **Internal Network Failure**: 服务端网络故障

### 日志级别

- `WARNING`: 摘要生成失败（不影响主流程）
- `ERROR`: LLM 流式响应失败（记录详细信息）
- `INFO`: 重试信息（记录重试次数和等待时间）

### 监控建议

1. 监控 503 错误频率
2. 统计重试成功率
3. 记录平均响应时间
4. 设置告警阈值

## 后续优化

1. **添加降级策略**：摘要生成失败时使用简单的文本截取
2. **异步重试队列**：失败的摘要任务加入队列，后台重试
3. **多 API 提供商**：自动切换到备用 API
4. **缓存机制**：缓存成功的摘要，避免重复生成
5. **健康检查**：定期检查 API 服务健康状态

## 相关文件

```
backend/app/services/llm_service.py      # 添加重试机制
backend/app/api/routers/optimizer.py     # 错误处理
backend/app/utils/llm_tool.py            # LLM 客户端
```

## 测试建议

1. 模拟网络故障，验证重试机制
2. 测试不同错误类型的处理
3. 验证摘要失败不影响主流程
4. 检查日志记录是否完整
