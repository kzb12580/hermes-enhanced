/**
 * Hermes Desktop - 主窗口管理
 */
import { BrowserWindow, shell, app, Menu, MenuItem } from 'electron'
import { join } from 'path'
import { is } from '@electron-toolkit/utils'
import { settingsStore } from './store'

let mainWindow: BrowserWindow | null = null

/**
 * 创建主窗口
 */
export function createMainWindow(): BrowserWindow {
  // 解析图标路径（兼容开发和打包模式）
  const iconPath = app.isPackaged
    ? join(process.resourcesPath, 'icon.png')
    : join(__dirname, '../../buildResources/icon.png')

  mainWindow = new BrowserWindow({
    width: 1200,
    height: 800,
    minWidth: 800,
    minHeight: 600,
    show: false,
    frame: false, // 无边框窗口，使用自定义标题栏
    titleBarStyle: process.platform === 'darwin' ? 'hiddenInset' : 'hidden',
    trafficLightPosition: { x: 15, y: 10 },
    backgroundColor: '#0a0a0a',
    icon: iconPath, // 设置窗口图标（任务栏/标题栏）
    webPreferences: {
      preload: join(__dirname, '../preload/index.js'),
      // sandbox: true 提供更好的安全隔离（preload 只使用 contextBridge/ipcRenderer，不需要 Node）
      sandbox: true,
      contextIsolation: true,
      nodeIntegration: false,
      webSecurity: true
    }
  })

  // 窗口准备好后显示，避免白屏闪烁
  mainWindow.on('ready-to-show', () => {
    mainWindow?.show()
    mainWindow?.focus()
  })

  // 捕获渲染进程加载失败
  mainWindow.webContents.on('did-fail-load', (_event, errorCode, errorDescription, validatedURL) => {
    console.error(`[窗口] 页面加载失败: ${errorDescription} (${errorCode}), URL: ${validatedURL}`)
  })

  // 捕获渲染进程崩溃
  mainWindow.webContents.on('render-process-gone', (_event, details) => {
    console.error(`[窗口] 渲染进程崩溃: ${details.reason}, 退出码: ${details.exitCode}`)
  })

  // 捕获渲染进程控制台错误
  mainWindow.webContents.on('console-message', (_event, level, message, line, sourceId) => {
    if (level >= 2) { // 2=warning, 3=error
      console.error(`[渲染进程] ${message} (${sourceId}:${line})`)
    }
  })

  // Right-click context menu handled by React ContextMenu component
  // (see src/components/ui/ContextMenu.tsx)
  // Also add native fallback for input fields not covered by React context menu
  mainWindow.webContents.on('context-menu', (_event, params) => {
    const menu = new Menu()

    if (params.isEditable) {
      if (params.selectionText) {
        menu.append(new MenuItem({ label: '剪切', accelerator: 'CmdOrCtrl+X', role: 'cut' }))
        menu.append(new MenuItem({ label: '复制', accelerator: 'CmdOrCtrl+C', role: 'copy' }))
      }
      menu.append(new MenuItem({ label: '粘贴', accelerator: 'CmdOrCtrl+V', role: 'paste' }))
      menu.append(new MenuItem({ type: 'separator' }))
      menu.append(new MenuItem({ label: '全选', accelerator: 'CmdOrCtrl+A', role: 'selectAll' }))
    } else if (params.selectionText) {
      menu.append(new MenuItem({ label: '复制', accelerator: 'CmdOrCtrl+C', role: 'copy' }))
    }

    if (menu.items.length > 0) {
      menu.popup({ window: mainWindow ?? undefined })
    }
  })

  // 处理新窗口打开请求（在默认浏览器中打开）
  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    // Validate URL to prevent arbitrary protocol execution
    try {
      const parsed = new URL(url)
      if (parsed.protocol === 'http:' || parsed.protocol === 'https:') {
        // 检查是否设置为使用外部浏览器
        const openExternal = settingsStore.get('openLinksInExternalBrowser')
        if (openExternal !== false) {
          shell.openExternal(url)
        }
      }
    } catch {
      // Invalid URL — ignore
    }
    return { action: 'deny' }
  })

  // 监听最大化状态变化
  mainWindow.on('maximize', () => {
    mainWindow?.webContents.send('window:maximized', true)
  })

  mainWindow.on('unmaximize', () => {
    mainWindow?.webContents.send('window:maximized', false)
  })

  // 关闭时隐藏到托盘而非退出
  let hasShownTrayNotification = false
  mainWindow.on('close', (event) => {
    if (!app.isQuitting) {
      event.preventDefault()
      mainWindow?.hide()
      if (!hasShownTrayNotification) {
        hasShownTrayNotification = true
        mainWindow?.webContents.send('window:minimized-to-tray')
      }
    }
  })

  // 加载页面
  if (is.dev && process.env['ELECTRON_RENDERER_URL']) {
    mainWindow.loadURL(process.env['ELECTRON_RENDERER_URL'])
  } else {
    mainWindow.loadFile(join(__dirname, '../renderer/index.html'))
  }

  return mainWindow
}

/**
 * 获取主窗口实例
 */
export function getMainWindow(): BrowserWindow | null {
  return mainWindow
}

/**
 * 显示主窗口
 */
export function showMainWindow(): void {
  if (mainWindow) {
    if (mainWindow.isMinimized()) {
      mainWindow.restore()
    }
    mainWindow.show()
    mainWindow.focus()
  }
}

/**
 * 切换主窗口显示/隐藏
 */
export function toggleMainWindow(): void {
  if (mainWindow) {
    if (mainWindow.isVisible()) {
      mainWindow.hide()
    } else {
      showMainWindow()
    }
  }
}

/**
 * 销毁主窗口
 */
export function destroyMainWindow(): void {
  if (mainWindow) {
    mainWindow.destroy()
    mainWindow = null
  }
}
