/**
 * Hermes Desktop - 预加载脚本
 * 通过 contextBridge 安全地暴露 IPC API 给渲染进程
 */
import { contextBridge, ipcRenderer } from 'electron'
import { IPC_CHANNELS } from '../shared/types'
import type {
  PythonState,
  PythonHealthResponse,
  AppSettings,
  UpdateInfo,
  UpdateProgress,
  UpdateStatusPayload,
  IPCResponse
} from '../shared/types'

/**
 * 暴露给渲染进程的安全 API
 */
const api = {
  // ==================== 窗口控制 ====================
  window: {
    minimize: () => ipcRenderer.invoke(IPC_CHANNELS.WINDOW_MINIMIZE),
    maximize: () => ipcRenderer.invoke(IPC_CHANNELS.WINDOW_MAXIMIZE),
    close: () => ipcRenderer.invoke(IPC_CHANNELS.WINDOW_CLOSE),
    restore: () => ipcRenderer.invoke(IPC_CHANNELS.WINDOW_RESTORE),
    isMaximized: (): Promise<boolean> => ipcRenderer.invoke(IPC_CHANNELS.WINDOW_IS_MAXIMIZED),

    /** 监听最大化状态变化 */
    onMaximizedChange: (callback: (isMaximized: boolean) => void) => {
      const handler = (_event: Electron.IpcRendererEvent, isMaximized: boolean) =>
        callback(isMaximized)
      ipcRenderer.on('window:maximized', handler)
      return () => ipcRenderer.removeListener('window:maximized', handler)
    }
  },

  // ==================== Python 后端管理 ====================
  python: {
    start: (): Promise<IPCResponse<PythonState>> =>
      ipcRenderer.invoke(IPC_CHANNELS.PYTHON_START),
    stop: (): Promise<IPCResponse<PythonState>> =>
      ipcRenderer.invoke(IPC_CHANNELS.PYTHON_STOP),
    restart: (): Promise<IPCResponse<PythonState>> =>
      ipcRenderer.invoke(IPC_CHANNELS.PYTHON_RESTART),
    getStatus: (): Promise<IPCResponse<PythonState>> =>
      ipcRenderer.invoke(IPC_CHANNELS.PYTHON_STATUS),
    checkHealth: (): Promise<IPCResponse<PythonHealthResponse>> =>
      ipcRenderer.invoke(IPC_CHANNELS.PYTHON_HEALTH),
    getLogs: (): Promise<IPCResponse<string[]>> =>
      ipcRenderer.invoke(IPC_CHANNELS.PYTHON_LOGS),

    /** 监听状态变化 */
    onStatusChange: (callback: (state: PythonState) => void) => {
      const handler = (_event: Electron.IpcRendererEvent, state: PythonState) => callback(state)
      ipcRenderer.on(IPC_CHANNELS.PYTHON_STATUS_CHANGE, handler)
      return () => ipcRenderer.removeListener(IPC_CHANNELS.PYTHON_STATUS_CHANGE, handler)
    },

    /** 监听日志流 */
    onLogStream: (callback: (log: { type: string; message: string }) => void) => {
      const handler = (_event: Electron.IpcRendererEvent, log: { type: string; message: string }) =>
        callback(log)
      ipcRenderer.on(IPC_CHANNELS.PYTHON_LOG_STREAM, handler)
      return () => ipcRenderer.removeListener(IPC_CHANNELS.PYTHON_LOG_STREAM, handler)
    }
  },

  // ==================== 应用信息 ====================
  app: {
    getVersion: (): Promise<string> => ipcRenderer.invoke(IPC_CHANNELS.APP_VERSION),
    quit: () => ipcRenderer.invoke(IPC_CHANNELS.APP_QUIT),
    restart: () => ipcRenderer.invoke(IPC_CHANNELS.APP_RESTART),

    /** 监听 show-about 事件（来自托盘菜单） */
    onShowAbout: (callback: () => void) => {
      const handler = () => callback()
      ipcRenderer.on(IPC_CHANNELS.SHOW_ABOUT, handler)
      return () => ipcRenderer.removeListener(IPC_CHANNELS.SHOW_ABOUT, handler)
    }
  },

  // ==================== 更新器 ====================
  updater: {
    checkForUpdates: (): Promise<IPCResponse> => ipcRenderer.invoke(IPC_CHANNELS.UPDATE_CHECK),
    downloadUpdate: (): Promise<IPCResponse> => ipcRenderer.invoke(IPC_CHANNELS.UPDATE_DOWNLOAD),
    installUpdate: (): Promise<IPCResponse> => ipcRenderer.invoke(IPC_CHANNELS.UPDATE_INSTALL),

    /** 监听更新可用事件 */
    onUpdateAvailable: (callback: (info: UpdateInfo) => void) => {
      const handler = (_event: Electron.IpcRendererEvent, info: UpdateInfo) => callback(info)
      ipcRenderer.on(IPC_CHANNELS.UPDATE_AVAILABLE, handler)
      return () => ipcRenderer.removeListener(IPC_CHANNELS.UPDATE_AVAILABLE, handler)
    },

    /** 监听下载进度 */
    onDownloadProgress: (callback: (progress: UpdateProgress) => void) => {
      const handler = (_event: Electron.IpcRendererEvent, progress: UpdateProgress) =>
        callback(progress)
      ipcRenderer.on(IPC_CHANNELS.UPDATE_PROGRESS, handler)
      return () => ipcRenderer.removeListener(IPC_CHANNELS.UPDATE_PROGRESS, handler)
    },

    /** 监听下载完成 */
    onUpdateDownloaded: (callback: (info: UpdateInfo) => void) => {
      const handler = (_event: Electron.IpcRendererEvent, info: UpdateInfo) => callback(info)
      ipcRenderer.on(IPC_CHANNELS.UPDATE_DOWNLOADED, handler)
      return () => ipcRenderer.removeListener(IPC_CHANNELS.UPDATE_DOWNLOADED, handler)
    },

    /** 监听更新状态变化 */
    onStatusChange: (callback: (payload: UpdateStatusPayload) => void) => {
      const handler = (_event: Electron.IpcRendererEvent, payload: UpdateStatusPayload) =>
        callback(payload)
      ipcRenderer.on(IPC_CHANNELS.UPDATE_STATUS, handler)
      return () => ipcRenderer.removeListener(IPC_CHANNELS.UPDATE_STATUS, handler)
    }
  },

  // ==================== 设置 ====================
  settings: {
    get: <K extends keyof AppSettings>(key: K): Promise<AppSettings[K]> =>
      ipcRenderer.invoke(IPC_CHANNELS.SETTINGS_GET, key),
    set: <K extends keyof AppSettings>(key: K, value: AppSettings[K]): Promise<void> =>
      ipcRenderer.invoke(IPC_CHANNELS.SETTINGS_SET, key, value),
    getAll: (): Promise<AppSettings> => ipcRenderer.invoke(IPC_CHANNELS.SETTINGS_GET_ALL)
  },

  // ==================== 对话框 ====================
  dialog: {
    showMessageBox: (options: {
      type?: 'info' | 'warning' | 'error' | 'question'
      title?: string
      message: string
      detail?: string
      buttons?: string[]
    }): Promise<{ response: number; checkboxChecked: boolean }> =>
      ipcRenderer.invoke(IPC_CHANNELS.SHOW_MESSAGE_BOX, options)
  },

  // ==================== Shell ====================
  shell: {
    openExternal: (url: string): Promise<void> =>
      ipcRenderer.invoke(IPC_CHANNELS.OPEN_EXTERNAL_URL, url)
  }
}

// 通过 contextBridge 安全地暴露 API
contextBridge.exposeInMainWorld('api', api)

// 导出类型供渲染进程使用
export type API = typeof api
