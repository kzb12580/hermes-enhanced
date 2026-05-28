# Hermes Desktop v1.0.0

> 智能 AI 桌面客户端 — 支持多模型、工具调用、技能系统
> 基于 Electron + React + Python 构建

![Hermes Desktop](desktop/buildResources/icon.png)

## ✨ 功能特性

- **多模型支持** — DeepSeek、GPT、Claude、Gemini 等主流模型
- **工具调用** — 文件读写、终端执行、搜索、内存管理等 7 个工具
- **技能系统** — 25 个内置技能，涵盖研究、开发、设计等领域
- **流式响应** — SSE 实时显示 AI 回复
- **多会话** — 创建、切换、管理多个对话
- **自定义设置** — API Key、模型切换、参数调整

## 📥 下载安装

### Windows
1. 下载 `hermes-desktop-1.0.0-setup.exe`
2. 双击运行安装程序
3. 按向导完成安装
4. 桌面会出现 "Hermes Desktop" 快捷方式

### macOS
1. 下载 `hermes-desktop-1.0.0.dmg`（Intel）或 `Hermes.Desktop-1.0.0-arm64-mac.zip`（Apple Silicon）
2. 打开 DMG，将应用拖入 Applications 文件夹
3. 首次打开可能需要在"系统偏好设置 > 安全性与隐私"中允许运行

### Linux
1. 下载 `hermes-desktop-1.0.0.AppImage`
2. 添加执行权限：`chmod +x hermes-desktop-1.0.0.AppImage`
3. 双击运行或终端执行：`./hermes-desktop-1.0.0.AppImage`

## 🚀 快速开始

### 1. 首次启动

启动应用后，点击左下角 **⚙️ 设置** 按钮配置 API：

### 2. 配置 API Key

在设置面板中：

| 设置项 | 说明 |
|--------|------|
| **API 地址** | 模型 API 的 Base URL（如 `https://api.deepseek.com/v1`） |
| **API Key** | 你的 API 密钥 |
| **默认模型** | 选择要使用的模型（如 `deepseek-v4-flash`） |

#### 常见 API 配置示例

**DeepSeek:**
```
API 地址: https://api.deepseek.com/v1
API Key: sk-xxxxxxxxxxxxxxxx
模型: deepseek-v4-flash
```

**OpenAI:**
```
API 地址: https://api.openai.com/v1
API Key: sk-xxxxxxxxxxxxxxxx
模型: gpt-4o
```

**Claude (通过代理):**
```
API 地址: https://your-proxy.com/v1
API Key: your-key
模型: claude-sonnet-4
```

### 3. 开始对话

1. 点击 **➕ 新建会话** 创建对话
2. 在输入框输入问题或指令
3. 按 Enter 或点击发送按钮
4. AI 会实时流式回复

### 4. 使用工具

AI 可以调用以下工具：
- 📄 **文件读写** — 读取、创建、编辑文件
- 🔍 **搜索** — 搜索文件和内容
- 💻 **终端** — 执行命令行操作
- 🧠 **内存** — 保存和读取记忆
- ⏰ **定时任务** — 创建定时任务
- 🌐 **网页** — 搜索和提取网页内容

### 5. 使用技能

点击左侧边栏 **🧩 技能** 按钮打开技能面板：

1. **切换类别** — 点击顶部标签（研究、开发、设计等）
2. **查看技能** — 点击技能列表中的项目查看详情
3. **激活技能** — 点击技能右侧的开关按钮激活
4. **多技能激活** — 可以同时激活多个技能
5. **发送指令** — 在聊天框输入相关指令，AI 会按激活的技能执行

#### 内置技能分类

| 类别 | 技能数 | 说明 |
|------|--------|------|
| 🎯 研究 | 3 | 深度研究、市场调研、论文分析 |
| 💻 开发 | 8 | 代码审查、TDD、调试、架构设计 |
| 🎨 设计 | 5 | 设计系统、原型、UI 审查 |
| 📝 内容 | 4 | 文档撰写、SEO、技术写作 |
| 🔧 工具 | 5 | Git、CI/CD、部署、监控 |

## ⚙️ 高级配置

### 环境变量

应用数据存储在：
- **Windows:** `%APPDATA%/hermes-desktop/`
- **macOS:** `~/Library/Application Support/hermes-desktop/`
- **Linux:** `~/.config/hermes-desktop/`

### 配置文件

设置保存在 localStorage，包括：
- API 配置（Base URL、API Key、模型）
- 界面偏好（主题、字体大小）
- 会话历史

### 开发模式

```bash
# 克隆仓库
git clone https://github.com/kzb12580/hermes-enhanced.git
cd hermes-enhanced/desktop

# 安装依赖
npm install

# 启动开发模式
npm run dev

# 构建生产版本
npm run build:all
```

## 🔧 故障排除

### 无法连接 API

1. 检查 API 地址是否正确（需要包含 `/v1`）
2. 检查 API Key 是否有效
3. 检查网络连接

### 工具调用失败

1. 确保 Python 后端已正确启动
2. 检查终端输出的错误信息
3. 查看日志文件：`~/.hermes/logs/`

### 技能面板无法激活

1. 确保应用已更新到最新版本
2. 重启应用后重试
3. 检查技能文件是否完整：`~/.hermes/skills/builtin/`

### Windows 安全警告

首次运行可能触发 Windows Defender 警告：
1. 点击 "更多信息"
2. 点击 "仍要运行"

## 📊 系统要求

| 平台 | 最低版本 |
|------|----------|
| Windows | Windows 10 (64-bit) |
| macOS | macOS 10.15 (Catalina) |
| Linux | Ubuntu 20.04 / Fedora 32 |

- 内存：4GB+ 推荐
- 磁盘：500MB+ 可用空间
- 网络：需要互联网连接

## 📝 更新日志

### v1.0.0 (2026-05-28)

**首个正式版本**

- ✅ 聊天功能 — 多模型支持、流式响应
- ✅ 工具调用 — 7 个工具（文件、终端、搜索、内存等）
- ✅ 技能系统 — 25 个内置技能
- ✅ 会话管理 — 多会话、切换、删除
- ✅ 设置面板 — API 配置、模型选择
- ✅ 全平台支持 — Windows、macOS、Linux
- ✅ 新图标 — 专业级 Hermes 翼形 H 图标

## 🔗 相关链接

- [GitHub 仓库](https://github.com/kzb12580/hermes-enhanced)
- [问题反馈](https://github.com/kzb12580/hermes-enhanced/issues)
- [发布页面](https://github.com/kzb12580/hermes-enhanced/releases)

## 📄 许可证

MIT License

---

**Hermes Desktop** — 您的智能 AI 助手桌面客户端
