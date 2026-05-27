/**
 * Hermes Desktop - 主进程入口
 * 负责应用生命周期、窗口管理、Python 后端管理、IPC 处理
 */
import { app, BrowserWindow, Menu, ipcMain, dialog, shell, nativeTheme } from 'electron'
import { createMainWindow, getMainWindow, showMainWindow } from './window'
import { createTray, destroyTray } from './tray'
import { PythonManager } from './python-manager'
import { initUpdater, checkForUpdates, downloadUpdate, installUpdate } from './updater'
import { settingsStore } from './store'
import { IPC_CHANNELS, IPCResponse } from '../shared/types'
import type { AppSettings } from '../shared/types'

// 单实例锁
const gotTheLock = app.requestSingleInstanceLock()
if (!gotTheLock) {
  app.quit()
}

// 全局引用
let pythonManager: PythonManager

/**
 * 应用初始化
 */
app.whenReady().then(async () => {
  // 初始化 Python 管理器
  pythonManager = new PythonManager({
    port: settingsStore.get('pythonPort'),
    maxRestarts: settingsStore.get('pythonMaxRestarts')
  })

  // 创建主窗口
  const mainWindow = createMainWindow()

  // 将主窗口引用传给 Python 管理器
  pythonManager.setMainWindow(mainWindow)

  // 创建系统托盘
  createTray(pythonManager)

  // 初始化自动更新
  initUpdater(mainWindow)

  // 注册所有 IPC 处理器
  registerIPCHandlers()

  // 设置应用菜单
  setupApplicationMenu()

  // 第二实例尝试启动时，显示主窗口
  app.on('second-instance', () => {
    showMainWindow()
  })

  // 根据设置决定是否自动启动 Python 后端
  if (settingsStore.get('pythonAutoStart')) {
    // 延迟启动，等待渲染进程加载完成
    mainWindow.webContents.on('did-finish-load', () => {
      pythonManager.start().catch(console.error)
    })
  }

  // 启动后自动检查更新（生产模式）
  if (!process.env['ELECTRON_RENDERER_URL']) {
    setTimeout(() => checkForUpdates(), 5000)
  }

  // 主题跟随系统
  nativeTheme.themeSource = settingsStore.get('theme')

  console.log('[主进程] Hermes Desktop 已启动')
})

/**
 * 所有窗口关闭时
 */
app.on('window-all-closed', () => {
  // macOS 上保持应用运行
  if (process.platform !== 'darwin') {
    // 不退出，保持在托盘
  }
})

/**
 * 应用即将退出
 */
let isQuittingCleanupDone = false

app.on('before-quit', (event) => {
  if (isQuittingCleanupDone) return // cleanup already done, allow quit to proceed

  event.preventDefault()
  app.isQuitting = true
  console.log('[主进程] 正在清理资源...')

  // Async cleanup, then force-quit
  const cleanup = async () => {
    try {
      if (pythonManager) {
        await pythonManager.stop()
      }
    } catch (err) {
      console.error('[主进程] Error stopping Python:', err)
    }
    destroyTray()
    isQuittingCleanupDone = true
    app.quit() // re-emits before-quit, but isQuittingCleanupDone prevents loop
  }
  cleanup()
})

/**
 * 激活事件（macOS）
 */
app.on('activate', () => {
  const mainWindow = getMainWindow()
  if (mainWindow) {
    showMainWindow()
  } else {
    const newWindow = createMainWindow()
    if (pythonManager) {
      pythonManager.setMainWindow(newWindow)
    }
    initUpdater(newWindow)
  }
})

/**
 * Validate a URL before opening externally.
 * Only allows http: and https: protocols to prevent arbitrary command execution.
 */
function isAllowedUrl(url: string): boolean {
  try {
    const parsed = new URL(url)
    return parsed.protocol === 'http:' || parsed.protocol === 'https:'
  } catch {
    return false
  }
}

/**
 * 注册所有 IPC 处理器
 */
function registerIPCHandlers(): void {
  // ---------- 窗口控制 ----------
  ipcMain.handle(IPC_CHANNELS.WINDOW_MINIMIZE, () => {
    getMainWindow()?.minimize()
  })

  ipcMain.handle(IPC_CHANNELS.WINDOW_MAXIMIZE, () => {
    const win = getMainWindow()
    if (win?.isMaximized()) {
      win.unmaximize()
    } else {
      win?.maximize()
    }
  })

  ipcMain.handle(IPC_CHANNELS.WINDOW_CLOSE, () => {
    getMainWindow()?.close()
  })

  ipcMain.handle(IPC_CHANNELS.WINDOW_RESTORE, () => {
    showMainWindow()
  })

  ipcMain.handle(IPC_CHANNELS.WINDOW_IS_MAXIMIZED, (): boolean => {
    return getMainWindow()?.isMaximized() ?? false
  })

  // ---------- Python 后端管理 ----------
  ipcMain.handle(IPC_CHANNELS.PYTHON_START, async (): Promise<IPCResponse> => {
    try {
      await pythonManager.start()
      return { success: true, data: pythonManager.getState() }
    } catch (err) {
      return { success: false, error: String(err) }
    }
  })

  ipcMain.handle(IPC_CHANNELS.PYTHON_STOP, async (): Promise<IPCResponse> => {
    try {
      await pythonManager.stop()
      return { success: true, data: pythonManager.getState() }
    } catch (err) {
      return { success: false, error: String(err) }
    }
  })

  ipcMain.handle(IPC_CHANNELS.PYTHON_RESTART, async (): Promise<IPCResponse> => {
    try {
      await pythonManager.restart()
      return { success: true, data: pythonManager.getState() }
    } catch (err) {
      return { success: false, error: String(err) }
    }
  })

  ipcMain.handle(IPC_CHANNELS.PYTHON_STATUS, (): IPCResponse => {
    return { success: true, data: pythonManager.getState() }
  })

  ipcMain.handle(IPC_CHANNELS.PYTHON_HEALTH, async (): Promise<IPCResponse> => {
    try {
      const health = await pythonManager.checkHealth()
      return { success: true, data: health }
    } catch (err) {
      return { success: false, error: String(err) }
    }
  })

  ipcMain.handle(IPC_CHANNELS.PYTHON_LOGS, (): IPCResponse => {
    return { success: true, data: pythonManager.getLogs() }
  })

  // ---------- 应用信息 ----------
  ipcMain.handle(IPC_CHANNELS.APP_VERSION, (): string => {
    return app.getVersion()
  })

  ipcMain.handle(IPC_CHANNELS.APP_QUIT, () => {
    app.isQuitting = true
    app.quit()
  })

  ipcMain.handle(IPC_CHANNELS.APP_RESTART, () => {
    // Stop Python backend before relaunching
    const cleanup = async () => {
      try {
        if (pythonManager) await pythonManager.stop()
      } catch (err) {
        console.error('[主进程] Error stopping Python before restart:', err)
      }
      app.relaunch()
      app.exit(0)
    }
    cleanup()
  })

  // ---------- 更新器 ----------
  ipcMain.handle(IPC_CHANNELS.UPDATE_CHECK, async (): Promise<IPCResponse> => {
    try {
      await checkForUpdates()
      return { success: true }
    } catch (err) {
      return { success: false, error: String(err) }
    }
  })

  ipcMain.handle(IPC_CHANNELS.UPDATE_DOWNLOAD, async (): Promise<IPCResponse> => {
    try {
      await downloadUpdate()
      return { success: true }
    } catch (err) {
      return { success: false, error: String(err) }
    }
  })

  ipcMain.handle(IPC_CHANNELS.UPDATE_INSTALL, (): IPCResponse => {
    try {
      installUpdate()
      return { success: true }
    } catch (err) {
      return { success: false, error: String(err) }
    }
  })

  // ---------- 设置 ----------
  ipcMain.handle(IPC_CHANNELS.SETTINGS_GET, (_event, key: keyof AppSettings) => {
    return settingsStore.get(key)
  })

  ipcMain.handle(IPC_CHANNELS.SETTINGS_SET, (_event, key: keyof AppSettings, value: AppSettings[typeof key]) => {
    settingsStore.set(key, value)
    return { success: true }
  })

  ipcMain.handle(IPC_CHANNELS.SETTINGS_GET_ALL, () => {
    return settingsStore.getAll()
  })

  // ---------- 对话框 ----------
  ipcMain.handle(IPC_CHANNELS.SHOW_MESSAGE_BOX, async (_event, options) => {
    const win = getMainWindow()
    if (win && !win.isDestroyed()) {
      return dialog.showMessageBox(win, options)
    }
    return dialog.showMessageBox(options)
  })

  // ---------- Shell ----------
  ipcMain.handle(IPC_CHANNELS.OPEN_EXTERNAL_URL, (_event, url: string) => {
    if (!isAllowedUrl(url)) {
      console.warn(`[主进程] Blocked unsafe external URL: ${url}`)
      return { success: false, error: `Blocked unsafe URL: ${url}` }
    }
    return shell.openExternal(url).then(() => ({ success: true })).catch((err) => ({ success: false, error: String(err) }))
  })
}

/**
 * 设置应用菜单
 */
function setupApplicationMenu(): void {
  const isMac = process.platform === 'darwin'

  const template: Electron.MenuItemConstructorOptions[] = [
    ...(isMac
      ? [
          {
            label: app.name,
            submenu: [
              { role: 'about' as const, label: '关于 Hermes Desktop' },
              { type: 'separator' as const },
              { role: 'services' as const, label: '服务' },
              { type: 'separator' as const },
              { role: 'hide' as const, label: '隐藏' },
              { role: 'hideOthers' as const, label: '隐藏其他' },
              { role: 'unhide' as const, label: '显示全部' },
              { type: 'separator' as const },
              { role: 'quit' as const, label: '退出' }
            ]
          }
        ]
      : []),
    {
      label: '编辑',
      submenu: [
        { role: 'undo', label: '撤销' },
        { role: 'redo', label: '重做' },
        { type: 'separator' },
        { role: 'cut', label: '剪切' },
        { role: 'copy', label: '复制' },
        { role: 'paste', label: '粘贴' },
        { role: 'selectAll', label: '全选' }
      ]
    },
    {
      label: '视图',
      submenu: [
        { role: 'reload', label: '重新加载' },
        { role: 'forceReload', label: '强制重新加载' },
        { role: 'toggleDevTools', label: '开发者工具' },
        { type: 'separator' },
        { role: 'resetZoom', label: '重置缩放' },
        { role: 'zoomIn', label: '放大' },
        { role: 'zoomOut', label: '缩小' },
        { type: 'separator' },
        { role: 'togglefullscreen', label: '全屏' }
      ]
    },
    {
      label: '帮助',
      submenu: [
        {
          label: '检查更新',
          click: () => checkForUpdates()
        },
        { type: 'separator' },
        {
          label: 'GitHub 仓库',
          click: () => shell.openExternal('https://github.com/kzb12580/hermes-desktop')
        },
        { type: 'separator' },
        {
          label: '关于',
          click: () => {
            dialog.showMessageBox(getMainWindow()!, {
              type: 'info',
              title: '关于 Hermes Desktop',
              message: 'Hermes Desktop',
              detail: `版本: ${app.getVersion()}\nAI 智能助手桌面客户端\n\nCopyright © 2024 kzb12580`,
              buttons: ['确定']
            })
          }
        }
      ]
    }
  ]

  const menu = Menu.buildFromTemplate(template)
  Menu.setApplicationMenu(menu)
}
