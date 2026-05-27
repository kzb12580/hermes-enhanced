/**
 * Hermes Desktop - 共享类型定义
 * 主进程和渲染进程之间通信使用的类型
 */

// ==================== IPC 频道名称 ====================
export const IPC_CHANNELS = {
  // 窗口控制
  WINDOW_MINIMIZE: 'window:minimize',
  WINDOW_MAXIMIZE: 'window:maximize',
  WINDOW_CLOSE: 'window:close',
  WINDOW_RESTORE: 'window:restore',
  WINDOW_IS_MAXIMIZED: 'window:is-maximized',

  // Python 后端管理
  PYTHON_START: 'python:start',
  PYTHON_STOP: 'python:stop',
  PYTHON_RESTART: 'python:restart',
  PYTHON_STATUS: 'python:status',
  PYTHON_HEALTH: 'python:health',
  PYTHON_LOGS: 'python:logs',

  // 应用信息
  APP_VERSION: 'app:version',
  APP_QUIT: 'app:quit',
  APP_RESTART: 'app:restart',

  // 更新器
  UPDATE_CHECK: 'update:check',
  UPDATE_DOWNLOAD: 'update:download',
  UPDATE_INSTALL: 'update:install',
  UPDATE_STATUS: 'update:status',

  // 设置
  SETTINGS_GET: 'settings:get',
  SETTINGS_SET: 'settings:set',
  SETTINGS_GET_ALL: 'settings:get-all',

  // 通用
  SHOW_MESSAGE_BOX: 'dialog:show-message-box',
  OPEN_EXTERNAL_URL: 'shell:open-external',
  SHOW_ABOUT: 'show-about',

  // 事件（主进程 -> 渲染进程）
  PYTHON_LOG_STREAM: 'python:log-stream',
  PYTHON_STATUS_CHANGE: 'python:status-change',
  UPDATE_AVAILABLE: 'update:available',
  UPDATE_PROGRESS: 'update:progress',
  UPDATE_DOWNLOADED: 'update:downloaded'
} as const

// ==================== App.isQuitting augmentation ====================
// Declared here (single source of truth) so both main/window.ts and
// main/index.ts can reference it without duplicate declarations.
declare module 'electron' {
  interface App {
    isQuitting: boolean
  }
}

// ==================== Python 后端状态 ====================
export type PythonStatus = 'stopped' | 'starting' | 'running' | 'error' | 'restarting'

export interface PythonState {
  status: PythonStatus
  pid: number | null
  port: number
  uptime: number | null
  lastError: string | null
  restartCount: number
}

export interface PythonHealthResponse {
  status: string
  version?: string
  uptime_seconds?: number
}

// ==================== 更新器状态 ====================
export type UpdateStatus = 'idle' | 'checking' | 'available' | 'not-available' | 'downloading' | 'downloaded' | 'error'

export interface UpdateInfo {
  version: string
  releaseDate: string
  releaseNotes?: string
}

export interface UpdateProgress {
  percent: number
  bytesPerSecond: number
  total: number
  transferred: number
}

/** Payload sent via IPC_CHANNELS.UPDATE_STATUS */
export interface UpdateStatusPayload {
  status: string
  info?: UpdateInfo
  error?: string
}

// ==================== 设置 ====================
export interface AppSettings {
  // 应用设置
  theme: 'light' | 'dark' | 'system'
  language: 'zh-CN' | 'en-US'
  startMinimized: boolean
  closeToTray: boolean
  autoStart: boolean

  // Python 后端设置
  pythonPort: number
  pythonAutoStart: boolean
  pythonMaxRestarts: number

  // 高级设置
  logLevel: 'debug' | 'info' | 'warn' | 'error'
  proxyUrl?: string
}

export const DEFAULT_SETTINGS: AppSettings = {
  theme: 'system',
  language: 'zh-CN',
  startMinimized: false,
  closeToTray: true,
  autoStart: false,
  pythonPort: 9876,
  pythonAutoStart: true,
  pythonMaxRestarts: 3,
  logLevel: 'info'
}

// ==================== IPC 消息类型 ====================
export interface IPCMessage<T = unknown> {
  channel: string
  data?: T
  error?: string
}

export interface IPCResponse<T = unknown> {
  success: boolean
  data?: T
  error?: string
}

// ==================== API 代理请求 ====================
export interface ProxyRequest {
  method: 'GET' | 'POST' | 'PUT' | 'DELETE' | 'PATCH'
  path: string
  body?: unknown
  headers?: Record<string, string>
}

export interface ProxyResponse<T = unknown> {
  status: number
  data: T
  error?: string
}
