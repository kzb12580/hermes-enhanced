/**
 * Hermes Desktop - 主窗口管理
 */
import { BrowserWindow, shell, app, Menu } from 'electron'
import { join } from 'path'
import { is } from '@electron-toolkit/utils'

let mainWindow: BrowserWindow | null = null

/**
 * 创建主窗口
 */
export function createMainWindow(): BrowserWindow {
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
    webPreferences: {
      preload: join(__dirname, '../preload/index.js'),
      // sandbox must be false for preload to use Node/Electron APIs
      // (contextIsolation still protects the renderer world)
      sandbox: false,
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

  // Right-click context menu (Cut, Copy, Paste, Select All)
  mainWindow.webContents.on('context-menu', (_event, params) => {
    const template: Electron.MenuItemConstructorOptions[] = []

    if (params.isEditable) {
      template.push(
        { role: 'cut', label: '剪切' },
        { role: 'copy', label: '复制' },
        { role: 'paste', label: '粘贴' },
        { type: 'separator' },
        { role: 'selectAll', label: '全选' }
      )
    } else if (params.selectionText) {
      template.push({ role: 'copy', label: '复制' })
    }

    if (template.length > 0) {
      const menu = Menu.buildFromTemplate(template)
      menu.popup({ window: mainWindow! })
    }
  })

  // 处理新窗口打开请求（在默认浏览器中打开）
  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    // Validate URL to prevent arbitrary protocol execution
    try {
      const parsed = new URL(url)
      if (parsed.protocol === 'http:' || parsed.protocol === 'https:') {
        shell.openExternal(url)
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
