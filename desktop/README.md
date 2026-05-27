# Hermes Desktop

AI 智能助手桌面客户端，基于 Electron + React + TypeScript 构建。

## 技术栈

- **前端**: React 18 + TypeScript + TailwindCSS + Zustand
- **桌面框架**: Electron 28 + electron-vite
- **构建工具**: electron-vite (Vite)
- **自动更新**: electron-updater (GitHub Releases)
- **后端**: Python HTTP 服务 (localhost:9876)

## 开发

```bash
# 安装依赖
npm install

# 启动开发模式
npm run dev

# 构建
npm run build

# 打包
npm run build:win   # Windows
npm run build:mac   # macOS
npm run build:linux # Linux
```

## 项目结构

```
desktop/
├── electron/
│   ├── main/           # 主进程
│   │   ├── index.ts    # 入口：窗口、托盘、IPC、更新
│   │   ├── window.ts   # 窗口管理
│   │   ├── tray.ts     # 系统托盘
│   │   ├── updater.ts  # 自动更新
│   │   ├── store.ts    # 持久化设置
│   │   └── python-manager.ts  # Python 后端管理
│   ├── preload/        # 预加载脚本
│   │   └── index.ts    # contextBridge API
│   └── shared/         # 共享类型
│       └── types.ts    # IPC 消息类型
├── src/                # 渲染进程 (React)
│   ├── main.tsx        # 入口
│   ├── App.tsx         # 根组件
│   ├── stores/         # Zustand 状态
│   ├── styles/         # 全局样式
│   └── lib/            # 工具函数
├── buildResources/     # 构建资源 (图标等)
├── electron.vite.config.ts
├── electron-builder.yml
└── package.json
```

## 许可证

MIT
