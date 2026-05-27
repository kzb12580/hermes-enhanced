# Hermes Desktop — 技术设计文档

## 研究总结

### 参考项目分析

| 项目 | Stars | 框架 | 关键借鉴 |
|------|-------|------|----------|
| **LobeHub** | 77.7k | Electron 37 | IoC/DI 架构、@IpcMethod 装饰器、3通道发布 |
| **Chatbox** | 40.1k | Electron 26 | electron-vite、Zustand+Jotai、MCP SDK、Vercel AI SDK |
| **AnythingLLM** | 60.6k | Electron | 3进程模型、Express 后端、文档收集器独立服务 |
| **Jan** | 42.7k | Tauri 2 | 从 Electron 迁移到 Tauri（体积考量） |
| **ChatGPT Desktop** | 54.4k | Tauri | 原生特性（托盘、快捷键、通知） |

### 核心技术决策

| 决策 | 选择 | 理由 |
|------|------|------|
| 框架 | **Electron + electron-vite** | Chatbox 模式，Vite 快速构建，生态成熟 |
| 前端 | **React 18 + TypeScript + TailwindCSS** | 团队已有技能，LobeHub/Chatbox 验证 |
| 状态管理 | **Zustand** | 轻量，Chatbox 验证，TypeScript 友好 |
| UI 组件 | **Shadcn/ui** | 现代、可定制、无依赖锁定 |
| IPC | **contextBridge + 事件总线** | Electron 安全规范 |
| Python 通信 | **HTTP API (localhost)** | 解耦、易调试、支持远程部署 |
| Python 打包 | **PyInstaller --onefile** | 独立可执行文件，无需用户安装 Python |
| 自动更新 | **electron-updater + GitHub Releases** | 开箱即用，3通道支持 |
| CI/CD | **GitHub Actions** | 官方模板，跨平台矩阵构建 |
| 本地存储 | **electron-store** | 简单可靠，加密支持 |

---

## 架构设计

```
┌─────────────────────────────────────────────────────────┐
│                    Electron App                          │
│                                                         │
│  ┌─────────────────────────────────────────────────┐    │
│  │              Renderer Process                    │    │
│  │         React + TypeScript + TailwindCSS         │    │
│  │                                                  │    │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────────┐    │    │
│  │  │  Chat UI │ │ Skills   │ │  Settings    │    │    │
│  │  │          │ │ Manager  │ │  Panel       │    │    │
│  │  └──────────┘ └──────────┘ └──────────────┘    │    │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────────┐    │    │
│  │  │ Memory   │ │ Cron     │ │  System      │    │    │
│  │  │ Browser  │ │ Jobs     │ │  Monitor     │    │    │
│  │  └──────────┘ └──────────┘ └──────────────┘    │    │
│  └──────────────────┬──────────────────────────────┘    │
│                     │ contextBridge (IPC)                │
│  ┌──────────────────▼──────────────────────────────┐    │
│  │              Main Process (Node.js)              │    │
│  │                                                  │    │
│  │  ┌──────────────┐  ┌──────────────────────┐     │    │
│  │  │ Window Mgr   │  │ PythonProcessManager │     │    │
│  │  │ Tray Mgr     │  │  - start/stop/restart│     │    │
│  │  │ Menu Mgr     │  │  - health check      │     │    │
│  │  │ Updater Mgr  │  │  - log streaming     │     │    │
│  │  │ Store Mgr    │  │  - port management   │     │    │
│  │  └──────────────┘  └──────────┬───────────┘     │    │
│  └───────────────────────────────┼──────────────────┘    │
│                                  │ HTTP (localhost)       │
│  ┌───────────────────────────────▼──────────────────┐    │
│  │           Python Sidecar Process                 │    │
│  │           (PyInstaller 打包)                      │    │
│  │                                                  │    │
│  │  ┌──────────────┐  ┌──────────────────────┐     │    │
│  │  │ FastAPI      │  │ Hermes Agent Core    │     │    │
│  │  │ /chat        │  │  - Agent Loop        │     │    │
│  │  │ /skills      │  │  - Tools System      │     │    │
│  │  │ /memory      │  │  - Memory System     │     │    │
│  │  │ /config      │  │  - Skills Engine     │     │    │
│  │  │ /health      │  │  - Cron Scheduler    │     │    │
│  │  └──────────────┘  └──────────────────────┘     │    │
│  └──────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────┘
```

---

## 目录结构

```
hermes-desktop/
├── .github/
│   └── workflows/
│       ├── build.yml          # CI: 跨平台构建
│       └── release.yml        # CD: 发布到 GitHub Releases
├── electron/                  # Electron 主进程
│   ├── main/
│   │   ├── index.ts           # 入口
│   │   ├── window.ts          # 窗口管理
│   │   ├── tray.ts            # 系统托盘
│   │   ├── menu.ts            # 菜单栏
│   │   ├── updater.ts         # 自动更新
│   │   ├── python-manager.ts  # Python 侧车管理
│   │   ├── ipc-handlers.ts    # IPC 处理器
│   │   └── store.ts           # 持久化存储
│   ├── preload/
│   │   └── index.ts           # contextBridge 暴露 API
│   └── shared/
│       └── types.ts           # 共享类型定义
├── src/                       # React 前端
│   ├── App.tsx
│   ├── main.tsx
│   ├── components/
│   │   ├── chat/
│   │   │   ├── ChatView.tsx       # 聊天主视图
│   │   │   ├── MessageBubble.tsx  # 消息气泡
│   │   │   ├── InputBar.tsx       # 输入栏
│   │   │   ├── ToolCallCard.tsx   # 工具调用展示
│   │   │   └── CodeBlock.tsx      # 代码块高亮
│   │   ├── sidebar/
│   │   │   ├── Sidebar.tsx        # 侧边栏
│   │   │   ├── SessionList.tsx    # 会话列表
│   │   │   └── QuickActions.tsx   # 快捷操作
│   │   ├── skills/
│   │   │   ├── SkillManager.tsx   # 技能管理
│   │   │   └── SkillEditor.tsx    # 技能编辑器
│   │   ├── settings/
│   │   │   ├── SettingsPanel.tsx  # 设置面板
│   │   │   ├── ModelConfig.tsx    # 模型配置
│   │   │   └── ApiKeyManager.tsx  # API Key 管理
│   │   ├── memory/
│   │   │   └── MemoryBrowser.tsx  # 记忆浏览
│   │   └── monitor/
│   │       ├── SystemStatus.tsx   # 系统状态
│   │       └── CronJobs.tsx       # 定时任务
│   ├── stores/
│   │   ├── chatStore.ts       # 聊天状态
│   │   ├── settingsStore.ts   # 设置状态
│   │   └── systemStore.ts     # 系统状态
│   ├── hooks/
│   │   ├── useIpc.ts          # IPC 通信 hook
│   │   └── usePython.ts       # Python 后端 hook
│   └── lib/
│       ├── api.ts             # Python 后端 API 客户端
│       └── utils.ts           # 工具函数
├── python-backend/            # Python 后端
│   ├── main.py                # FastAPI 入口
│   ├── requirements.txt
│   ├── build.spec             # PyInstaller 配置
│   └── api/
│       ├── chat.py            # 聊天 API
│       ├── skills.py          # 技能 API
│       ├── memory.py          # 记忆 API
│       ├── config.py          # 配置 API
│       └── health.py          # 健康检查
├── resources/
│   ├── icon.ico               # Windows 图标
│   ├── icon.icns              # macOS 图标
│   └── icon.png               # Linux 图标
├── electron-builder.yml       # electron-builder 配置
├── electron.vite.config.ts    # Vite 配置
├── package.json
├── tsconfig.json
└── README.md
```

---

## 功能清单 (MVP → 完整版)

### Phase 1: MVP (核心可用)
- [x] 项目骨架搭建 (electron-vite + React + TS)
- [ ] Electron 主进程 (窗口、托盘、菜单)
- [ ] Python 侧车进程管理 (启动、停止、健康检查)
- [ ] 基础聊天 UI (消息列表、输入框、Markdown 渲染)
- [ ] IPC 通信层 (前后端桥接)
- [ ] Python FastAPI 后端 (聊天接口)
- [ ] 基础设置面板 (API Key 配置)
- [ ] GitHub Actions CI (Windows 构建)

### Phase 2: 完整功能
- [ ] 工具调用可视化 (ToolCallCard)
- [ ] 技能管理界面
- [ ] 记忆浏览器
- [ ] 多会话管理
- [ ] 系统状态监控
- [ ] 定时任务管理
- [ ] 自动更新 (electron-updater)
- [ ] 跨平台构建 (macOS, Linux)
- [ ] 深色/浅色主题

### Phase 3: 高级特性
- [ ] 本地模型支持 (Ollama 集成)
- [ ] MCP 协议支持
- [ ] 语音输入/输出
- [ ] 插件系统
- [ ] 多语言支持

---

## CI/CD 流水线

```
Push to main → GitHub Actions
  ├── Windows: build .exe (NSIS installer)
  ├── macOS:   build .dmg
  └── Linux:   build .AppImage

Tag v* → GitHub Releases
  ├── 自动发布 (draft → 审核 → publish)
  └── electron-updater 检测到新版本 → 用户一键更新
```

---

## 安全考虑

1. **IPC 安全**: 只通过 contextBridge 暴露必要 API，不暴露 Node.js 全局对象
2. **Python 进程隔离**: 运行在独立进程，崩溃不影响 Electron
3. **localhost 通信**: Python 只监听 127.0.0.1，不暴露到网络
4. **API Key 加密**: 使用 electron-store 的加密存储
5. **CSP 策略**: 严格的内容安全策略
6. **代码签名**: Windows (Authenticode) + macOS (Notarization)
