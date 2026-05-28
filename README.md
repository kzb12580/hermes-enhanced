# Hermes 增强版

> 将 Claude Code 核心架构能力移植到 Hermes Agent 的 Python 生态
> **v1.0.0** — 正式版，生产就绪

## 📊 项目状态

| 指标 | 数值 |
|------|------|
| 增强模块 | 12 个 |
| 单元测试 | 980/980 ✅ |
| 集成测试 | 33/33 ✅ |
| 外部依赖 | 0（纯 Python stdlib） |
| BUG 修复 | 67 处 |
| 压力测试 | 2 轮全通过 |

## 📁 仓库结构

```
hermes-enhanced/
├── iteration/
│   └── hermes_upgrades/          # ← 核心增强模块
│       ├── hermes2_adapter.py    # 主引擎
│       ├── tool_orchestrator.py  # 8路并发工具编排
│       ├── memory_system.py      # TF-IDF 记忆系统
│       ├── context_compressor_v2.py  # 三级上下文压缩
│       ├── permission_pipeline.py    # 权限管线
│       ├── smart_retry.py        # 断路器+指数退避
│       ├── auto_dream.py         # 后台记忆整合
│       ├── post_turn_hooks.py    # 回合后钩子
│       ├── mcp_transport.py      # MCP 四种传输
│       ├── coordinator.py        # 多 Agent 协调
│       ├── async_pipeline.py     # 异步管线
│       ├── token_budget_manager.py   # Token 预算管理
│       └── tests/                # 测试套件
├── desktop/                      # Hermes Desktop 桌面客户端
├── analysis/                     # Claude Code 架构分析
└── source-map/                   # 源码还原
```

## 🚀 安装部署

### 前置条件

- Python 3.11+
- Hermes Agent 已安装（`pip install hermes-agent` 或源码安装）

### 方式一：源码安装（推荐）

```bash
# 1. 克隆仓库
git clone https://github.com/kzb12580/hermes-enhanced.git
cd hermes-enhanced

# 2. 复制 hermes2 模块到 Hermes Agent
cp -r iteration/hermes_upgrades /usr/local/lib/hermes-agent/agent/hermes2/

# 3. 创建 __init__.py（如果不存在）
touch /usr/local/lib/hermes-agent/agent/hermes2/__init__.py

# 4. 重启 Hermes 网关
hermes gateway restart
```

### 方式二：符号链接（开发模式）

```bash
# 便于开发时实时同步修改
ln -sf $(pwd)/iteration/hermes_upgrades /usr/local/lib/hermes-agent/agent/hermes2/hermes_upgrades
```

### 验证安装

```bash
# 检查模块是否加载
python3 -c "
import sys
sys.path.insert(0, '/usr/local/lib/hermes-agent')
from agent.hermes2.integration import get_engine, get_stats
e = get_engine()
print('✅ Engine:', 'ready' if e else '❌ failed')
import json
print(json.dumps(get_stats(), indent=2, ensure_ascii=False))
"
```

## ⚙️ 模型配置

Hermes 增强版对模型无特殊要求，但推荐使用付费模型以获得最佳效果。

### 推荐配置：DeepSeek V4 Flash

在 `~/.hermes/config.yaml` 中配置：

```yaml
model:
  default: deepseek-v4-flash
  provider: custom
  base_url: https://api.deepseek.com
  api_key: sk-xxxxxxxxxxxxxxxxxxxxxxxx
```

### 通过 CLIProxyAPI 代理

```yaml
model:
  default: deepseek-v4-flash
  provider: custom
  base_url: http://localhost:8317/v1
  api_key: your-proxy-api-key
```

## ✨ 12 大增强模块

| 模块 | 功能 | 性能 |
|------|------|------|
| ToolOrchestrator | 8路并发，文件冲突检测 | 分批 <100μs |
| ToolResultManager | SHA256去重+智能截断+磁盘缓存 | 去重 ~1μs |
| ContextCompressorV2 | 三级压缩(微/反应/全量) | 微压缩 <1ms |
| MemorySystem | TF-IDF四类记忆+持久化 | 搜索 <5ms |
| HookPipeline ×4 | 记忆提取/用量追踪/提示建议/上下文健康 | — |
| AutoDream | 后台自省巩固记忆(5次会话触发) | — |
| SmartRetryManager | 断路器+指数退避+错误分类 | — |
| PermissionPipeline | 三层权限+危险命令检测(30+模式) | 检查 <50μs |
| AsyncPipeline | 异步流式管线架构 | — |
| Coordinator | 多智能体计划-分配-执行-审核 | — |
| MCPTransport | STDIO/SSE/HTTP/WS四种传输 | — |
| TokenUtils | 统一token估算和内容提取 | 估算 <1μs |

## 🔌 集成架构

通过 4 个微创注入点集成到 `run_agent.py`：

```
注入点 1: AIAgent.__init__ (line ~2500)
  → 初始化 Hermes2Engine，启动 banner

注入点 2: _execute_tool_calls (line ~10600)
  → Hermes2 智能编排：分类→分批→去重截断→权限检查

注入点 3: _execute_tool_calls 末尾
  → 每轮工具执行后自动跑 Post-Turn Hooks

注入点 4: run_conversation 返回前 (line ~15800)
  → 后台 AutoDream 记忆巩固检查
```

**回退方式：** 在 `AIAgent.__init__` 中注释掉 `_hermes2_enabled = True` 即可回退到纯原生模式。

## 🖥️ Hermes Desktop 桌面客户端

本仓库同时包含 **Hermes Desktop** 桌面客户端，提供图形化界面：

### 下载

| 平台 | 文件 |
|------|------|
| 🪟 Windows | `hermes-desktop-1.0.0-setup.exe` |
| 🍎 macOS Intel | `Hermes-Desktop-1.0.0-mac.zip` |
| 🍎 macOS ARM | `Hermes-Desktop-1.0.0-arm64-mac.zip` |
| 🐧 Linux | `hermes-desktop-1.0.0.AppImage` |

下载地址：[GitHub Releases](https://github.com/kzb12580/hermes-enhanced/releases/tag/v1.0.0)

### 功能特性

- 多模型支持（DeepSeek、GPT、Claude、Gemini）
- 工具调用（文件、终端、搜索、内存等 7 个工具）
- 技能系统（25 个内置技能）
- 流式响应、多会话管理

### 从源码构建

```bash
cd desktop
npm install
npm run dev        # 开发模式
npm run build:all  # 构建生产版本
```

## 🔍 与 Claude Code 对比

| 维度 | Claude Code | Hermes 增强版 |
|------|------------|------------|
| 语言 | TypeScript | Python |
| Agent循环 | AsyncGenerator流水线 | 同步+异步混合 |
| 工具系统 | 工厂模式+并发分区 | ToolOrchestrator 8路并发 |
| 权限 | 7层管线 | PermissionPipeline 3层 |
| 压缩 | 5层自适应 | ContextCompressorV2 3级 |
| MCP | 6种传输 | MCPTransport 4种 |
| 记忆 | 双系统+后台提取 | MemorySystem + AutoDream |
| 多Agent | Coordinator模式 | Coordinator 计划-分配-执行-审核 |

## 📝 更新日志

### v1.0.0 (2026-05-28)

**首个正式版本**

- ✅ 12 个核心增强模块
- ✅ 67 处 BUG 修复
- ✅ 980 单元测试 + 33 集成测试全通过
- ✅ 压力测试：18µs/权限检查，165并发/秒，27.5MB峰值RSS
- ✅ Hermes Desktop 桌面客户端
- ✅ 专业级 Hermes 翼形 H 图标

### v2.1 (2026-05-27)

- 67处BUG修复，压力测试通过
- CRITICAL: PermissionPipeline 空规则列表修复
- CRITICAL: `allow_tool("*")` 确保增强版生效

### v2.0 (2026-05-25)

- 934 单元测试 + 50 集成测试全部通过
- 4 个注入点确认正确接线
- 测试服务器部署验证通过

## 🔗 相关链接

- [GitHub 仓库](https://github.com/kzb12580/hermes-enhanced)
- [问题反馈](https://github.com/kzb12580/hermes-enhanced/issues)
- [Release 下载](https://github.com/kzb12580/hermes-enhanced/releases)

## 📄 许可证

MIT License

---

**Hermes 增强版** — Claude Code 架构精华移植到 Hermes Agent
