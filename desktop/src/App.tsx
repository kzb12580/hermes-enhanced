/**
 * Hermes Desktop - 根组件
 */
import React from 'react'

export default function App() {
  return (
    <div className="flex h-screen bg-background text-foreground">
      {/* 自定义标题栏 */}
      <TitleBar />

      {/* 主内容区域 */}
      <main className="flex-1 pt-8 flex items-center justify-center">
        <div className="text-center space-y-4">
          <h1 className="text-4xl font-bold">Hermes Desktop</h1>
          <p className="text-muted-foreground">AI 智能助手桌面客户端</p>
          <p className="text-sm text-muted-foreground">
            正在加载后端服务...
          </p>
        </div>
      </main>
    </div>
  )
}

/**
 * 自定义无边框窗口标题栏
 */
function TitleBar() {
  return (
    <div className="fixed top-0 left-0 right-0 h-8 bg-background/80 backdrop-blur-sm border-b flex items-center justify-between px-4 select-none app-drag z-50">
      <div className="flex items-center gap-2">
        <span className="text-xs font-medium text-muted-foreground">
          Hermes Desktop
        </span>
      </div>
      <div className="flex items-center app-no-drag">
        <button
          className="h-8 w-12 flex items-center justify-center hover:bg-muted transition-colors"
          onClick={() => window.api.window.minimize()}
          title="最小化"
        >
          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeWidth={2} d="M20 12H4" />
          </svg>
        </button>
        <button
          className="h-8 w-12 flex items-center justify-center hover:bg-muted transition-colors"
          onClick={() => window.api.window.maximize()}
          title="最大化"
        >
          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeWidth={2} d="M4 8V4h4M20 8V4h-4M4 16v4h4M20 16v4h-4" />
          </svg>
        </button>
        <button
          className="h-8 w-12 flex items-center justify-center hover:bg-destructive hover:text-destructive-foreground transition-colors"
          onClick={() => window.api.window.close()}
          title="关闭"
        >
          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
      </div>
    </div>
  )
}
