/**
 * 渲染进程使用的 Electron IPC API 类型。
 *
 * 不直接从 electron/preload 或 electron/shared 引入，避免 Web tsconfig 把主进程/
 * preload 文件纳入编译图导致 TS6307。这里保持与 preload 暴露的 window.api 合约一致。
 */

export type PythonStatus = 'stopped' | 'starting' | 'running' | 'error' | 'restarting' | 'stopping';

export interface PythonState {
  status: PythonStatus;
  pid: number | null;
  port: number;
  uptime: number | null;
  lastError: string | null;
  restartCount: number;
}

export interface PythonHealthResponse {
  status: string;
  version?: string;
  uptime_seconds?: number;
}

export type UpdateStatus = 'idle' | 'checking' | 'available' | 'not-available' | 'downloading' | 'downloaded' | 'error';

export interface UpdateInfo {
  version: string;
  releaseDate: string;
  releaseNotes?: string;
}

export interface UpdateProgress {
  percent: number;
  bytesPerSecond: number;
  total: number;
  transferred: number;
}

export interface UpdateStatusPayload {
  status: string;
  info?: UpdateInfo;
  error?: string;
  version?: string;
}

export interface MainProcessSettings {
  theme: 'light' | 'dark' | 'system';
  language: 'zh-CN' | 'en-US';
  startMinimized: boolean;
  closeToTray: boolean;
  autoStart: boolean;
  workspacePath: string;
  pythonPort: number;
  pythonAutoStart: boolean;
  pythonMaxRestarts: number;
  logLevel: 'debug' | 'info' | 'warn' | 'error';
  proxyUrl?: string;
  openLinksInExternalBrowser: boolean;
}

export interface IPCResponse<T = unknown> {
  success: boolean;
  data?: T;
  error?: string;
}

export interface ElectronAPI {
  window: {
    minimize: () => Promise<void>;
    maximize: () => Promise<void>;
    close: () => Promise<void>;
    restore: () => Promise<void>;
    isMaximized: () => Promise<boolean>;
    onMaximizedChange: (callback: (isMaximized: boolean) => void) => () => void;
  };
  python: {
    start: () => Promise<IPCResponse<PythonState>>;
    stop: () => Promise<IPCResponse<PythonState>>;
    restart: () => Promise<IPCResponse<PythonState>>;
    getStatus: () => Promise<IPCResponse<PythonState>>;
    checkHealth: () => Promise<IPCResponse<PythonHealthResponse>>;
    getLogs: () => Promise<IPCResponse<string[]>>;
    onStatusChange: (callback: (state: PythonState) => void) => () => void;
    onLogStream: (callback: (log: { type: string; message: string }) => void) => () => void;
  };
  app: {
    getVersion: () => Promise<string>;
    quit: () => Promise<void>;
    restart: () => Promise<void>;
    onShowAbout: (callback: () => void) => () => void;
  };
  updater: {
    checkForUpdates: () => Promise<IPCResponse>;
    downloadUpdate: () => Promise<IPCResponse>;
    installUpdate: () => Promise<IPCResponse>;
    onUpdateAvailable: (callback: (info: UpdateInfo) => void) => () => void;
    onDownloadProgress: (callback: (progress: UpdateProgress) => void) => () => void;
    onUpdateDownloaded: (callback: (info: UpdateInfo) => void) => () => void;
    onStatusChange: (callback: (payload: UpdateStatusPayload) => void) => () => void;
  };
  settings: {
    get: <K extends keyof MainProcessSettings>(key: K) => Promise<MainProcessSettings[K]>;
    set: <K extends keyof MainProcessSettings>(key: K, value: MainProcessSettings[K]) => Promise<void>;
    getAll: () => Promise<MainProcessSettings>;
  };
  dialog: {
    showMessageBox: (options: {
      type?: 'info' | 'warning' | 'error' | 'question';
      title?: string;
      message: string;
      buttons?: string[];
    }) => Promise<{ response: number }>;
    selectFolder: () => Promise<string | null>;
  };
  shell: {
    openExternal: (url: string) => Promise<void>;
  };
}
