# Hermes Desktop

> AI 桌面助手 — 终端、文件、Office、Web、GUI 全能操作
> **v1.1.6** — 正式定板

## 📥 下载

| 平台 | 文件 | 说明 |
|------|------|------|
| 🪟 Windows | `hermes-desktop-1.1.6-setup.exe` | 安装版 |
| 🪟 Windows | `Hermes-Desktop-1.1.6-win.zip` | 便携版（解压即用） |
| 🍎 macOS Intel | `Hermes-Desktop-1.1.6-mac.zip` | Intel 芯片 |
| 🍎 macOS ARM | `Hermes-Desktop-1.1.6-arm64-mac.zip` | M1/M2/M3/M4 |
| 🐧 Linux | `hermes-desktop-1.1.6.AppImage` | 通用版 |

**下载地址：** [GitHub Releases](https://github.com/kzb12580/hermes-enhanced/releases/tag/v1.1.6)

### Windows 用户

- 推荐下载 `.exe` 安装版，支持自动更新
- `.zip` 便携版解压后直接运行 `hermes-desktop.exe`
- 首次启动自动安装 VC++ 运行库（如缺失）

## ⚡ 快速开始

1. 下载安装后打开 Hermes Desktop
2. 进入 **设置** 配置模型 API：
   - **API 地址**：你的模型 API 端点（如 `https://api.deepseek.com/v1`）
   - **API Key**：你的密钥
   - **模型**：选择或输入模型名
3. 新建对话，开始使用

### 支持的模型

Hermes Desktop 兼容所有 OpenAI 格式的 API：

- DeepSeek（V3/V4/Flash）
- OpenAI（GPT-4o/GPT-5）
- Claude（通过 API 代理）
- Gemini（通过 API 代理）
- 小米 MiMo
- 本地模型（Ollama/vLLM 等）

## 🛠️ 内置工具（20+）

### 系统操作
- **终端** — 执行命令（PowerShell/bash），自动处理 GBK 编码
- **文件读写** — 读取、写入、搜索文件
- **代码执行** — 运行 Python 脚本

### Office 文档（OfficeCLI 引擎）
- **Word** — 创建、读取、编辑 .docx 文档
- **Excel** — 创建、读取、编辑 .xlsx 表格
- **PowerPoint** — 创建、读取、编辑 .pptx 演示文稿
- **动画支持** — 入场/退出/强调/运动路径动画（原生 OOXML）
- **渲染预览** — 生成 HTML/PNG 预览，AI 可以"看到"文档效果

### 网络 & 搜索
- **Web 搜索** — DuckDuckGo + Bing 多源搜索
- **网页提取** — 抓取网页内容转 Markdown
- **内容提取** — 智能提取关键信息

### 屏幕 & GUI
- **屏幕截图** — 捕获当前屏幕
- **OCR** — 识别图片中的文字（Tesseract）
- **窗口管理** — 查找、切换、移动窗口
- **鼠标键盘** — 自动化 GUI 操作

### 记忆 & 任务
- **记忆系统** — 保存和检索长期记忆
- **任务管理** — 创建、更新、跟踪任务列表
- **会话管理** — 多会话切换，历史记录持久化

## 🧠 智能特性

### ContextCompressorV2 — 上下文智能压缩

长对话不会丢失重要信息。三级自动压缩：

1. **Micro** — 裁剪旧工具结果（<1ms）
2. **Reactive** — 渐进压缩，截断+去重
3. **Full** — LLM 摘要（预留接口）

当上下文占用超过 75% 时自动触发，日志中可以看到压缩效果。

### 安全文件搜索

搜索文件时自动应用 5 重保护，避免全盘扫描导致崩溃：

- 最多 500 文件 / 2000 目录 / 8 层深度
- 30 秒超时
- 自动跳过 Windows、Program Files 等系统目录
- 每 100 目录自动 GC 回收内存

### GBK 编码兼容

Windows 终端自动处理中文编码：

- `chcp 65001` 设置 UTF-8 代码页
- GBK 兜底解码（`systeminfo` 等顽固程序也能正确显示）

## 🔧 技能系统（25+）

内置技能让 AI 专业处理特定任务：

- 文件管理、代码搜索、正则表达式
- Excel 处理、PDF 处理、图片处理
- 视频处理、OCR 识别、批量处理
- SSH 操作、Cron 定时任务
- JSON 处理、CSV 处理、Markdown
- 日志分析、Markdown 渲染
- ...更多

## 🏗️ 从源码构建

```bash
# 克隆仓库
git clone https://github.com/kzb12580/hermes-enhanced.git
cd hermes-enhanced/desktop

# 安装依赖
npm install

# 开发模式
npm run dev

# 构建生产版本
npm run build:all
```

### 项目结构

```
hermes-enhanced/
├── desktop/                          # 桌面客户端
│   ├── electron/                     # Electron 主进程
│   │   └── main/
│   │       ├── index.ts              # 入口
│   │       ├── python-manager.ts     # Python 后端管理
│   │       ├── window.ts             # 窗口管理
│   │       ├── store.ts              # 配置存储
│   │       └── tray.ts               # 系统托盘
│   ├── src/                          # React 前端
│   │   ├── components/
│   │   │   ├── chat/                 # 聊天界面
│   │   │   ├── sidebar/              # 侧边栏
│   │   │   ├── settings/             # 设置面板
│   │   │   └── skills/               # 技能面板
│   │   └── stores/                   # 状态管理
│   ├── python-backend/               # Python 后端
│   │   ├── main.py                   # FastAPI 入口
│   │   ├── api/                      # API 路由
│   │   │   ├── chat.py               # 聊天 + 工具执行
│   │   │   ├── models.py             # 模型管理
│   │   │   └── session_manager.py    # 会话管理
│   │   ├── tools/                    # 工具实现
│   │   │   ├── file_tools.py         # 文件操作
│   │   │   ├── terminal_tools.py     # 终端
│   │   │   ├── office_tools.py       # Office 文档
│   │   │   ├── web_tools.py          # 网络搜索
│   │   │   ├── automation_tools.py   # GUI 自动化
│   │   │   └── memory_tools.py       # 记忆系统
│   │   ├── skills/                   # 技能系统
│   │   ├── context_compressor_v2.py  # 上下文压缩引擎
│   │   └── token_utils.py            # Token 估算
│   └── electron-builder.yml          # 打包配置
└── iteration/hermes_upgrades/        # CLI 增强模块
```

## 📋 更新日志

### v0.1.0 (2026-06-02)

**正式定板版本**

**功能：**
- ✅ 20+ 内置工具（终端、文件、Office、Web、GUI、记忆）
- ✅ 25+ 内置技能系统
- ✅ ContextCompressorV2 智能上下文压缩（三级自动）
- ✅ 安全文件搜索（BFS 增量遍历 + 5 重保护）
- ✅ GBK 编码完全兼容（chcp 65001 + GBK 兜底）
- ✅ 多模型支持（OpenAI 格式兼容）
- ✅ 流式响应 + SSE 推送
- ✅ 多会话管理 + 历史持久化
- ✅ VC++ 运行库自动安装
- ✅ Windows EXE + ZIP 双格式发布

**修复：**
- ✅ 400 错误 — tool_call JSON 验证，截断数据不再发回 API
- ✅ search_files 全盘扫描崩溃 — 增量 BFS + 多重限制
- ✅ 日志文件写入 — appendFile → appendFileSync
- ✅ GBK 乱码 — 双层编码处理

## 📄 许可证

MIT License

---

## 📦 Hermes 增强模块（CLI 版）

桌面版之外，本仓库还包含 **Hermes2 增强模块**，可注入到 Hermes Agent CLI 中，获得更强的 Agent 能力。

### 12 大增强模块

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

### 安装（CLI 版）

```bash
# 前置条件：Hermes Agent 已安装
pip install hermes-agent

# 克隆仓库
git clone https://github.com/kzb12580/hermes-enhanced.git
cd hermes-enhanced

# 复制 hermes2 模块到 Hermes Agent
cp -r iteration/hermes_upgrades /usr/local/lib/hermes-agent/agent/hermes2/

# 重启 Hermes 网关
hermes gateway restart
```

### 集成架构

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

**回退方式：** 注释掉 `_hermes2_enabled = True` 即可回退到纯原生模式。

### 与 Claude Code 对比

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

### 测试状态

| 指标 | 数值 |
|------|------|
| 增强模块 | 12 个 |
| 单元测试 | 980/980 ✅ |
| 集成测试 | 33/33 ✅ |
| 外部依赖 | 0（纯 Python stdlib） |
| BUG 修复 | 67 处 |

---

**Hermes Desktop** — 让 AI 成为你的桌面助手
**Hermes 增强版** — Claude Code 架构精华移植到 Hermes Agent
