# REVIEW_29.md — 第 29 轮: 多模型压力审查 (9 模型 + 人工深度审查)

**日期**: 2026-05-24
**审查模型**: DeepSeek 3.2, GLM-5, Claude Sonnet 4.6, Claude Opus 4.7, Qwen3-Coder-Next, Minimax M2.5, Claude Haiku 4.5, GPT-5.2-Codex, Claude Opus 4.6 + 人工全量审查
**审查范围**: 全部 16 个模块 (7,089 行源码 + 10,393 行测试)
**测试结果**: 859/859 PASSED ✅

## 修复的 Bug (8 个 HIGH)

### 1. 🔴 permission_pipeline.py:52 — evaluate_condition 异常传播
- **问题**: 用户提供的 condition callable 如果抛异常，会直接传播到权限系统上层，导致整个权限检查崩溃
- **修复**: 包裹 try-except，异常时返回 False (fail-safe deny)
- **影响**: 安全性 — 恶意/错误的 condition 不再能崩溃权限系统

### 2. 🔴 memory_system.py:260 — update() 无类型验证
- **问题**: `relevance_score`、`access_count` 等字段接受任意类型，设置错误类型会破坏评分/排序/序列化
- **修复**: 添加 isinstance 验证，自动类型转换 (float/int)，拒绝无效类型
- **影响**: 数据完整性 — 防止类型污染

### 3. 🔴 tool_result_summarizer.py:523 — JSON 检测逻辑错误
- **问题**: 尝试解析 JSON 片段 (`content[:1000]`) 来判断是否为 JSON，这几乎永远不会成功
- **修复**: 改为直接 `json.loads(content)` 全量解析，失败则跳过
- **影响**: 功能正确性 — JSON 内容现在能正确识别和摘要

### 4. 🔴 hermes2_adapter.py — _hook_executor 资源泄漏
- **问题**: ThreadPoolExecutor 在 `__init__` 创建但从不关闭，GC 时泄漏线程
- **修复**: 添加 `shutdown()`、`__enter__/__exit__`、`__del__` 三重保护
- **影响**: 资源管理 — 防止线程泄漏

### 5. 🔴 async_pipeline.py:BackPressureController — 竞态条件
- **问题**: `_pressure` 和 `_paused` 字段无线程保护，多线程并发读写导致状态不一致
- **修复**: 添加 threading.Lock，所有读写方法加锁
- **影响**: 并发安全 — 消除竞态条件

### 6. 🔴 async_pipeline.py:ContextWindow — 竞态条件
- **问题**: `_messages` 列表无线程保护，`add()`/`get_messages()`/`auto_compact()` 并发不安全
- **修复**: 添加 RLock，所有方法加锁；`auto_compact` 改为快照模式避免 await 期间持锁
- **影响**: 并发安全 — 消除竞态条件

### 7. 🔴 async_pipeline.py:ContextWindow — 重复属性定义
- **问题**: `max_tokens` 和 `pressure` 属性被定义了两次 (代码合并残留)
- **修复**: 删除重复定义
- **影响**: 代码质量

### 8. 🔴 token_budget_manager.py — 全模块无线程安全
- **问题**: `begin_turn`/`end_turn`/`allocate`/`record_usage` 等所有方法无锁保护
- **修复**: 添加 RLock，所有公开方法加锁
- **影响**: 并发安全 — 消除竞态条件

## 审查覆盖

| 模型 | 分组 | 结果 |
|------|------|------|
| DeepSeek 3.2 | Group B (Safety) | 5 bugs found (1 real: evaluate_condition) |
| GLM-5 | Group C (Async) | 6 bugs found (2 real: thread safety) |
| Claude Sonnet 4.6 | Group A | Response timeout |
| Claude Opus 4.7 | Group B | Response timeout |
| Qwen3-Coder-Next | Group A | Empty response |
| Minimax M2.5 | Group C | Empty response |
| Claude Haiku 4.5 | Group B | Response timeout |
| GPT-5.2-Codex | Group C | Response timeout |
| Claude Opus 4.6 | Group C | Response timeout |
| **人工审查** | **全部 16 模块** | **8 real bugs found + fixed** |

## 统计

- **总修复**: 8 个 HIGH 级别 bug
- **CRITICAL**: 0 (保持清零)
- **测试**: 859/859 PASSED
- **累计轮次**: 29
- **累计模型**: 17+
- **累计修复**: 140+ bugs
