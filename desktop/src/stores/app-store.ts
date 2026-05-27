/**
 * Hermes Desktop - 应用状态管理 (Zustand)
 * Wires up IPC event listeners from the main process to keep state in sync.
 */
import { create } from 'zustand'
import type { PythonState, AppSettings, UpdateStatus, UpdateInfo, UpdateProgress } from '../../electron/shared/types'

interface AppState {
  // Python 后端状态
  pythonState: PythonState
  setPythonState: (state: PythonState) => void

  // 应用设置
  settings: AppSettings | null
  setSettings: (settings: AppSettings) => void

  // 更新状态
  updateStatus: UpdateStatus
  updateInfo: UpdateInfo | null
  updateProgress: UpdateProgress | null
  setUpdateStatus: (status: UpdateStatus, info?: UpdateInfo) => void
  setUpdateProgress: (progress: UpdateProgress) => void

  // UI 状态
  sidebarOpen: boolean
  toggleSidebar: () => void
  activeView: 'chat' | 'settings' | 'logs'
  setActiveView: (view: 'chat' | 'settings' | 'logs') => void

  // 日志
  logs: string[]
  addLog: (log: string) => void
  setLogs: (logs: string[]) => void
  clearLogs: () => void

  // IPC listener setup (call once at app start)
  initIpcListeners: () => (() => void) | void
}

export const useAppStore = create<AppState>((set, get) => ({
  // Python 后端状态
  pythonState: {
    status: 'stopped',
    pid: null,
    port: 9876,
    uptime: null,
    lastError: null,
    restartCount: 0
  },
  setPythonState: (state) => set({ pythonState: state }),

  // 应用设置
  settings: null,
  setSettings: (settings) => set({ settings }),

  // 更新状态
  updateStatus: 'idle',
  updateInfo: null,
  updateProgress: null,
  setUpdateStatus: (status, info) =>
    set({ updateStatus: status, updateInfo: info ?? null }),
  setUpdateProgress: (progress) => set({ updateProgress: progress }),

  // UI 状态
  sidebarOpen: true,
  toggleSidebar: () => set((state) => ({ sidebarOpen: !state.sidebarOpen })),
  activeView: 'chat',
  setActiveView: (view) => set({ activeView: view }),

  // 日志
  logs: [],
  addLog: (log) =>
    set((state) => ({
      logs: [...state.logs.slice(-499), log]
    })),
  setLogs: (logs) => set({ logs }),
  clearLogs: () => set({ logs: [] }),

  /**
   * Wire up IPC event listeners from the Electron main process.
   * Returns a cleanup function that removes all listeners.
   * Call this once in the root component's useEffect.
   */
  initIpcListeners: () => {
    const api = (window as any).api;
    if (!api) return; // Not running in Electron

    const cleanups: (() => void)[] = [];

    // Listen for Python backend state changes
    if (api.python?.onStatusChange) {
      cleanups.push(
        api.python.onStatusChange((state: PythonState) => {
          get().setPythonState(state);
        })
      );
    }

    // Listen for Python log stream
    if (api.python?.onLogStream) {
      cleanups.push(
        api.python.onLogStream((log: { type: string; message: string }) => {
          get().addLog(`[${log.type}] ${log.message}`);
        })
      );
    }

    // Listen for update events
    if (api.updater?.onUpdateAvailable) {
      cleanups.push(
        api.updater.onUpdateAvailable((info: UpdateInfo) => {
          get().setUpdateStatus('available', info);
        })
      );
    }

    if (api.updater?.onDownloadProgress) {
      cleanups.push(
        api.updater.onDownloadProgress((progress: UpdateProgress) => {
          get().setUpdateProgress(progress);
        })
      );
    }

    if (api.updater?.onUpdateDownloaded) {
      cleanups.push(
        api.updater.onUpdateDownloaded((info: UpdateInfo) => {
          get().setUpdateStatus('downloaded', info);
        })
      );
    }

    if (api.updater?.onStatusChange) {
      cleanups.push(
        api.updater.onStatusChange((data: { status: string; info?: UpdateInfo; error?: string }) => {
          get().setUpdateStatus(data.status as UpdateStatus, data.info);
        })
      );
    }

    // Return cleanup function
    return () => {
      cleanups.forEach((cleanup) => cleanup());
    };
  }
}))
