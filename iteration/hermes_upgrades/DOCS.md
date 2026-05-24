# Hermes 2.0 开发文档

> **版本:** v1.0 | **日期:** 2026-05-24 | **源码:** 4,953行 / 12模块 | **测试:** 717个全通过

---

## 1. 架构概览

```
                     ┌──────────────────┐
                     │   Hermes2Engine   │  ← 入口 (hermes2_adapter.py)
                     └────────┬─────────┘
       ┌──────────┬──────────┼──────────┬──────────┐
       ▼          ▼          ▼          ▼          ▼
  ┌─────────┐ ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐
  │ToolOrch.│ │ToolRes.│ │PermPipe│ │CtxComp.│ │Memory  │
  │(分批执行)│ │(去重截断)│ │(权限检查)│ │(三级压缩)│ │(TF-IDF)│
  └─────────┘ └───┬────┘ └────────┘ └────────┘ └───┬────┘
              ┌───┴───┐                        ┌───┴────┐
              │Smart  │                        │Auto    │
              │Retry  │                        │Dream   │
              └───────┘                        └────────┘
       ┌──────────┬──────────┐
       ▼          ▼          ▼
  ┌─────────┐ ┌────────┐ ┌─────────┐
  │PostTurn │ │MCP     │ │Async    │
  │Hooks    │ │Transport│ │Pipeline │
  └─────────┘ └────────┘ └─────────┘
                   ┌────────┐
                   │Coordin.│  ← 多Agent协调
                   └────────┘
```

**数据流:** 请求 → 权限检查 → 工具分批 → 并发执行 → 结果处理 → 后置钩子 → 记忆提取 → 压缩 → 返回

---

## 2. 快速开始

```python
from hermes_upgrades.hermes2_adapter import Hermes2Engine, Hermes2Config

# 创建引擎
engine = Hermes2Engine()

# 处理工具调用
result = engine.process_tool_calls(
    tool_calls=[
        {"name": "read_file", "args": {"path": "/etc/hostname"}},
        {"name": "search_files", "args": {"pattern": "*.py"}},
    ],
    executor_fn=lambda tc: run_tool(tc.name, tc.args),
)

# 查看结果
for tid, info in result["processed"].items():
    print(f"{tid}: {info['token_count']} tokens, 截断={info['was_truncated']}")
```

**启用写操作：**

```python
engine = Hermes2Engine()
engine.allow_tool("write_file")     # 方式1: 直接允许
engine.allow_tool("terminal")

# 方式2: 确认回调
config = Hermes2Config(on_permission_prompt=lambda name, args, reason: True)
engine = Hermes2Engine(config)
```

**回合后处理：**

```python
turn = engine.process_turn(messages, tool_calls, tool_results)
if turn["compression_applied"]:
    messages = turn["compressed_messages"]
```

---

## 3. 模块详解

### 3.1 tool_orchestrator.py — 工具编排器

自动分类工具并发安全性，检测文件路径冲突，分批并行执行。

- `ToolOrchestrator` — 顶层编排，`partition()` 分批，`execute()` 执行
- `ToolConcurrencyClassifier` — 分为 READ_ONLY / WRITE_SERIAL / AMBIGUOUS
- `FileConflictDetector` — 同路径工具强制串行

```python
orch = ToolOrchestrator(max_workers=8)
batches = orch.partition(tool_calls)
results = orch.execute(batches, executor_fn)
```

### 3.2 tool_result_manager.py — 工具结果管理器

Token 估算（~4字符/token）、SHA-256 去重（LRU 1000）、智能截断（头30%+尾20%）、大结果磁盘持久化（原子写入）。

```python
mgr = ToolResultManager(max_tokens=80000, disk_dir="/tmp/hermes-results")
processed = mgr.process(tool_name="read_file", content=raw_output)
```

默认预算: read_file=15K, terminal=10K, search_files=8K, web_extract=12K tokens。

### 3.3 context_compressor_v2.py — 上下文压缩器 V2

三级压缩: **Microcompact**（裁剪旧工具结果，无LLM）→ **Reactive**（截断+合并，无LLM）→ **Full**（LLM摘要接口）。

配置: `aggressive`(阈值60%) / `balanced`(75%) / `gentle`(85%)

```python
comp = ContextCompressorV2(model_token_limit=200_000, profile="balanced")
should, reason = comp.should_compress(messages)
if should:
    result = comp.compress(messages, level="auto")
```

### 3.4 memory_system.py — 记忆系统

TF-IDF 搜索 + 标签/时间/频率评分，规则提取，JSON 持久化。

记忆类型: USER > PROCEDURAL > MEMORY > EPISODIC（按注入优先级）

```python
store = MemoryStore(storage_path="./memories.json", max_entries=500)
store.add(MemoryEntry(type=MemoryType.USER, content="用户偏好Python", tags=["python"]))
results = store.search("编程", limit=5)
```

- `MemoryExtractor` — 从对话提取记忆（"remember that", "I prefer" 等模式）
- `MemoryInjector` — 按优先级格式化为系统提示文本（2000 token 预算）

### 3.5 permission_pipeline.py — 权限管线

glob 模式匹配，首个规则生效。支持 Pre-Hook / Post-Hook。

- `AUTO` — read_file, search_files, web_search 等
- `PROMPT` — write_file, patch, terminal, send_message
- `DENY` — 终端危险命令自动拒绝（30+ 正则模式）

```python
pipeline = PermissionPipeline()
decision = pipeline.check("terminal", {"command": "ls -la"})
pipeline.add_rule(PermissionRule("my_tool", PermissionLevel.AUTO))
```

### 3.6 mcp_transport.py — MCP 传输层

STDIO（子进程+JSON-RPC）/ HTTP / SSE / WebSocket。兼容 Claude Code mcpServers 格式。

```python
configs = from_dict({"mcpServers": {"srv": {"command": "node", "args": ["s.js"]}}})
manager = McpManager(configs)
await manager.connect_all()
result = await manager.call_tool("srv", "search", {"q": "test"})
await manager.disconnect_all()
```

安全: 内置命令拒绝列表 + shell 元字符检测。

### 3.7 coordinator.py — 多 Agent 协调器

目标分解 → 任务调度 → 执行 → 审查 → 聚合。

```python
coord = Coordinator()
result = coord.run_full_cycle(
    objective="实现登录功能; 编写测试; 审查代码",
    executor_fn=lambda task: {"done": True},
)
```

Agent 角色: ORCHESTRATOR / WORKER / REVIEWER。按关键词推断能力需求（code/research/test/deploy/review/design/data）。

### 3.8 auto_dream.py — 自动梦境记忆整合

每 5 个会话或 24 小时触发，分析会话 → 提取关键决策/错误/偏好 → 合并相似记忆 → 提升/降级记忆。

```python
dreamer = AutoDreamer(memory_store=store)
if dreamer.should_dream():
    report = dreamer.dream()
```

### 3.9 post_turn_hooks.py — 回合后钩子

按优先级执行: MemoryExtraction(10) → UsageTracking(20) → PromptSuggestion(30) → ContextHealth(40)

```python
pipeline = HookPipeline()
pipeline.register(MemoryExtractionHook())
results = await pipeline.run_all(HookContext(messages=msgs))
```

### 3.10 async_pipeline.py — 异步管线

`Pipeline`（map/filter/flat_map）、`StreamingToolExecutor`（按完成顺序产出）、`ContextWindow`（Token缓冲）、`BackPressureController`（迟滞流控）。

### 3.11 tool_result_summarizer.py — 智能摘要

结构感知: CODE_FILE（提取签名/导入）、TERMINAL（提取错误/退出码）、SEARCH（提取路径）、JSON（提取键结构）。

### 3.12 smart_retry.py — 智能重试

错误分类（TRANSIENT/PERMANENT/RATE_LIMITED）+ 指数退避 + 熔断器（连续5次失败→打开→60秒后半开）。

```python
retry_mgr = SmartRetryManager()
result = retry_mgr.execute_with_retry(tool_call=ToolCall(name="web_extract", args={...}), executor_fn=fn)
```

### 3.13 token_budget_manager.py — 会话级 Token 预算

压力区域: GREEN(<50%) → YELLOW(50-70%, 减20%) → ORANGE(70-85%, 减50%) → RED(85-95%, 减75%) → EXCEEDED(>95%)

```python
budget = TokenBudgetManager(session_budget=160_000)
budget.begin_turn(1)
alloc = budget.allocate("read_file", requested_tokens=15000)
budget.record_usage("read_file", actual_tokens=12000)
budget.end_turn()
```

---

## 4. 配置指南 — Hermes2Config

```python
Hermes2Config(
    max_workers=8,                    # 最大并发数
    max_context_tokens=200_000,       # 上下文窗口 Token 上限
    compression_profile="balanced",   # "aggressive" | "balanced" | "gentle"
    memory_storage_path=None,         # 记忆持久化路径（None=仅内存）
    disk_result_dir=None,             # 大结果磁盘目录（None=不持久化）
    permission_rules=None,            # 自定义权限规则（None=内置规则）
    auto_dream_threshold=5,           # 梦境触发会话数
    enable_hooks=True,                # 启用回合后钩子
    enable_auto_dream=True,           # 启用自动梦境
    on_permission_prompt=None,        # 确认回调 (name, args, reason) -> bool
)
```

从字典创建（未知键会警告）:
```python
engine = Hermes2Engine.from_config({"max_workers": 4, "compression_profile": "aggressive"})
```

---

## 5. 集成指南

```python
from hermes_upgrades.hermes2_adapter import Hermes2Engine

engine = Hermes2Engine()

# 1. 构建 LLM 请求前注入记忆
messages = engine.get_context_messages(messages)

# 2. LLM 返回后处理工具调用
if response.tool_calls:
    results = engine.process_tool_calls(response.tool_calls, executor_fn=execute_tool)

# 3. 回合结束后
turn = engine.process_turn(messages, tool_calls, tool_results)
```

**步骤:** 将 `hermes_upgrades/` 放入项目 → 导入 `Hermes2Engine` → 在工具执行前调 `process_tool_calls()` → 回合后调 `process_turn()` → 构建请求前调 `get_context_messages()`。

---

## 6. 性能特性

- **零外部依赖**（纯 stdlib）
- Token 估算: ~4字符/token，微秒级
- 去重: SHA-256 + LRU(1000)，~1μs/次
- 分批(10工具): <100μs
- 记忆搜索(500条): <5ms
- Microcompact 压缩: <1ms
- 权限检查: <50μs/次
- 磁盘写入: temp + os.replace() 原子操作
- 正则全部预编译
- 记忆合并: O(n log n) + 长度预过滤

---

## 7. 安全模型

**权限管线流程:** Pre-Hook → 规则匹配（首个生效）→ 条件评估 → Post-Hook → 决策

**默认规则:** read_file/search_files/web_search=AUTO; write_file/patch/terminal/send_message=PROMPT

**危险命令检测（terminal）:** `rm -rf`, `sudo`, `curl|sh`, 反弹shell, `chmod 777`, `cat /etc/shadow` 等 30+ 模式

**MCP 安全:** 命令拒绝列表（rm/sudo/curl/python/bash 等）+ shell 元字符注入检测

---

## 8. 常见问题

**Q: 调整工具 Token 预算？**
```python
ToolResultManager(per_tool_budgets={"read_file": 20000})
TokenBudgetManager(tool_budgets={"read_file": 20000})
```

**Q: 禁用记忆提取？** `enable_hooks=False` 或 `engine.hooks.set_enabled("memory_extraction", False)`

**Q: 手动触发梦境？** `engine.dream()`

**Q: 查看统计？** `engine.get_stats()` / `engine.pressure`

**Q: 自定义权限？**
```python
engine.permissions.add_rule(PermissionRule("my_tool", PermissionLevel.AUTO), index=0)
engine.permissions.add_rule(PermissionRule("dangerous_*", PermissionLevel.DENY))
```

**Q: 压缩级别选择？** aggressive=长会话/紧张预算; balanced=推荐默认; gentle=需保留上下文

**Q: 异步使用？** `process_tool_calls`/`process_turn` 为同步；`StreamingToolExecutor` 可独立异步使用
