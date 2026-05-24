# Hermes 增强版 开发文档

> **版本:** v2.0 | **日期:** 2026-05-25 | **源码:** 18 模块 / 零外部依赖 | **测试:** 934 单元 + 50 集成全通过

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
  │(8路并发) │ │(去重截断)│ │(权限检查)│ │(三级压缩)│ │(TF-IDF)│
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

## 2. 安装部署

### 2.1 环境要求

- Python 3.11+（推荐 3.14）
- Hermes Agent 已安装
- 无外部依赖（纯 stdlib）

### 2.2 安装步骤

```bash
# 克隆仓库
git clone https://github.com/kzb12580/claude-code-study.git
cd claude-code-study

# 复制到 Hermes Agent 目录
cp -r iteration/hermes_upgrades /usr/local/lib/hermes-agent/agent/hermes2/

# 确保 __init__.py 存在
touch /usr/local/lib/hermes-agent/agent/hermes2/__init__.py

# 重启网关
hermes gateway restart
```

### 2.3 验证安装

```bash
python3 -c "
import sys
sys.path.insert(0, '/usr/local/lib/hermes-agent')
from agent.hermes2.integration import get_engine, get_stats
import json

engine = get_engine()
print('✅ Engine ready' if engine else '❌ Engine failed')

stats = get_stats()
print(f'Turn count: {stats.get(\"turn_count\", 0)}')
print(f'Hooks: {len([h for h in stats.get(\"hooks\", []) if h.get(\"enabled\")])}')
print(f'Memory entries: {stats.get(\"memory\", {}).get(\"total_entries\", 0)}')
"
```

### 2.4 模型配置

在 `~/.hermes/config.yaml` 中配置模型：

```yaml
# DeepSeek V4 Flash（推荐，性价比高）
model:
  default: deepseek-v4-flash
  provider: custom
  base_url: https://api.deepseek.com
  api_key: sk-your-api-key

# 或通过 CLIProxyAPI 代理池
model:
  default: ds-flash
  provider: custom
  base_url: http://localhost:8317/v1
  api-key: your-proxy-key
```

---

## 3. 集成指南

### 3.1 集成点说明

Hermes 增强版 通过 `integration.py` 桥接模块注入 `run_agent.py`：

| 注入点 | 位置 | 功能 |
|--------|------|------|
| 1. 初始化 | `AIAgent.__init__` | 创建 Hermes2Engine 单例 |
| 2. 工具增强 | `_execute_tool_calls` | 智能编排：分批+去重+权限 |
| 3. 后置钩子 | `_execute_tool_calls` 末尾 | Post-Turn Hooks 自动执行 |
| 4. 记忆整合 | `run_conversation` 返回前 | AutoDream 后台检查 |

### 3.2 集成代码示例

```python
# 在 AIAgent.__init__ 中
from agent.hermes2.integration import get_engine
self._hermes2_engine = get_engine()
self._hermes2_enabled = self._hermes2_engine is not None

# 在 _execute_tool_calls 中
from agent.hermes2.integration import enhance_tool_execution
if self._hermes2_enabled:
    result = enhance_tool_execution(tool_calls, executor_fn)
    # 使用 result["results"] 替代原始结果

# 在回合结束后
from agent.hermes2.integration import process_turn
if self._hermes2_enabled:
    turn = process_turn(messages, tool_calls, tool_results)
    if turn["compression_applied"]:
        messages = turn["compressed_messages"]

# 在会话结束时
from agent.hermes2.integration import check_and_dream
check_and_dream()
```

### 3.3 回退方式

在 `AIAgent.__init__` 中注释掉启用代码：

```python
# self._hermes2_enabled = True  # ← 注释这行
self._hermes2_enabled = False    # ← 改为 False
```

---

## 4. 模块详解

### 4.1 tool_orchestrator.py — 工具编排器

自动分类工具并发安全性，检测文件路径冲突，分批并行执行。

- `ToolOrchestrator` — 顶层编排，`partition()` 分批，`execute()` 执行
- `ToolConcurrencyClassifier` — 分为 READ_ONLY / WRITE_SERIAL / AMBIGUOUS
- `FileConflictDetector` — 同路径工具强制串行

### 4.2 tool_result_manager.py — 工具结果管理器

Token 估算（~4字符/token）、SHA-256 去重（LRU 1000）、智能截断（头30%+尾20%）、大结果磁盘持久化。

默认预算: read_file=15K, terminal=10K, search_files=8K, web_extract=12K tokens。

### 4.3 context_compressor_v2.py — 上下文压缩器 V2

三级压缩:
- **Microcompact** — 裁剪旧工具结果，无 LLM
- **Reactive** — 截断+合并，无 LLM
- **Full** — LLM 摘要接口

配置: `aggressive`(阈值60%) / `balanced`(75%) / `gentle`(85%)

### 4.4 memory_system.py — 记忆系统

TF-IDF 搜索 + 标签/时间/频率评分，规则提取，JSON 持久化。

记忆类型: USER > PROCEDURAL > MEMORY > EPISODIC（按注入优先级）

### 4.5 permission_pipeline.py — 权限管线

glob 模式匹配，首个规则生效。

- `AUTO` — read_file, search_files, web_search 等
- `PROMPT` — write_file, patch, terminal, send_message
- `DENY` — 终端危险命令自动拒绝（30+ 正则模式）

### 4.6 mcp_transport.py — MCP 传输层

STDIO / HTTP / SSE / WebSocket。兼容 Claude Code mcpServers 格式。

### 4.7 coordinator.py — 多 Agent 协调器

目标分解 → 任务调度 → 执行 → 审查 → 聚合。

Agent 角色: ORCHESTRATOR / WORKER / REVIEWER。

### 4.8 auto_dream.py — 自动梦境记忆整合

每 5 个会话或 24 小时触发，分析会话 → 提取关键决策/错误/偏好 → 合并相似记忆。

### 4.9 post_turn_hooks.py — 回合后钩子

按优先级执行: MemoryExtraction(10) → UsageTracking(20) → PromptSuggestion(30) → ContextHealth(40)

### 4.10 smart_retry.py — 智能重试

错误分类（TRANSIENT/PERMANENT/RATE_LIMITED）+ 指数退避 + 熔断器（连续5次失败→打开→60秒后半开）。

### 4.11 async_pipeline.py — 异步管线

`Pipeline`（map/filter/flat_map）、`StreamingToolExecutor`、`ContextWindow`、`BackPressureController`。

### 4.12 token_budget_manager.py — 会话级 Token 预算

压力区域: GREEN(<50%) → YELLOW(50-70%) → ORANGE(70-85%) → RED(85-95%) → EXCEEDED(>95%)

---

## 5. 故障排查

### 5.1 Telegram 重启后无响应

**症状：** 网关重启后，Telegram bot 不响应消息

**原因：** Telegram long-polling offset 卡在旧位置

**解决：**
```bash
# 停止网关
systemctl --user stop hermes-gateway

# 清空 polling offset
curl -s "https://api.telegram.org/bot<BOT_TOKEN>/getUpdates?offset=-1" > /dev/null

# 重启网关
systemctl --user start hermes-gateway
```

### 5.2 Gemini API 429 错误

**症状：** `HTTP 429: You exceeded your current quota`

**原因：** Gemini API 额度用完或区域封控

**解决：** 切换到 DeepSeek 或其他付费模型

### 5.3 Hermes2Engine 未初始化

**症状：** `turn_count` 始终为 0

**排查：**
```bash
# 检查模块路径
ls -la /usr/local/lib/hermes-agent/agent/hermes2/

# 检查导入
python3 -c "from agent.hermes2.integration import get_engine; print(get_engine())"

# 检查日志
journalctl --user -u hermes-gateway | grep -i hermes2
```

### 5.4 YAML 配置解析错误

**症状：** `Failed to parse /root/.hermes/config.yaml`

**原因：** YAML 语法错误（缩进、特殊字符）

**解决：**
```bash
# 验证 YAML
python3 -c "import yaml; yaml.safe_load(open('/root/.hermes/config.yaml')); print('OK')"

# 检查缩进（必须用空格，不能用 Tab）
cat -A ~/.hermes/config.yaml | grep $'\t'
```

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

---

## 7. 安全模型

**权限管线流程:** Pre-Hook → 规则匹配 → 条件评估 → Post-Hook → 决策

**危险命令检测:** `rm -rf`, `sudo`, `curl|sh`, 反弹shell, `chmod 777`, `cat /etc/shadow` 等 30+ 模式

**MCP 安全:** 命令拒绝列表 + shell 元字符注入检测
