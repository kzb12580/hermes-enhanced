/**
 * Hermes Desktop - 系统托盘管理
 */
import { Tray, Menu, nativeImage, app, BrowserWindow } from 'electron'
import { join } from 'path'
import { showMainWindow, toggleMainWindow } from './window'
import { PythonManager } from './python-manager'
import { IPC_CHANNELS } from '../shared/types'

let tray: Tray | null = null

/**
 * Resolve the icon path, handling both dev and packaged modes.
 */
function resolveIconPath(iconName: string): string {
  // In dev mode __dirname is electron/main/, icons are at projectRoot/buildResources/
  // In packaged mode resources are under process.resourcesPath
  if (app.isPackaged) {
    return join(process.resourcesPath, 'buildResources', iconName)
  }
  return join(__dirname, '../../buildResources', iconName)
}

/**
 * 创建系统托盘图标
 */
export function createTray(pythonManager: PythonManager): Tray {
  // 创建托盘图标
  const iconPath = resolveIconPath('icon.png')
  const icon = nativeImage.createFromPath(iconPath)
  const resizedIcon = icon.isEmpty()
    ? nativeImage.createEmpty()
    : icon.resize({ width: 16, height: 16 })

  tray = new Tray(resizedIcon)
  tray.setToolTip('Hermes Desktop - AI 智能助手')

  // 构建右键菜单
  const updateContextMenu = () => {
    const pythonState = pythonManager.getState()
    const isRunning = pythonState.status === 'running'

    const contextMenu = Menu.buildFromTemplate([
      {
        label: '显示主窗口',
        click: () => showMainWindow()
      },
      { type: 'separator' },
      {
        label: `后端状态: ${getStatusLabel(pythonState.status)}`,
        enabled: false
      },
      {
        label: isRunning ? '重启后端' : '启动后端',
        click: async () => {
          if (isRunning) {
            await pythonManager.restart()
          } else {
            await pythonManager.start()
          }
          updateContextMenu()
        }
      },
      ...(isRunning
        ? [
            {
              label: '停止后端',
              click: async () => {
                await pythonManager.stop()
                updateContextMenu()
              }
            }
          ]
        : []),
      { type: 'separator' },
      {
        label: '关于',
        click: () => {
          const windows = BrowserWindow.getAllWindows()
          if (windows.length > 0) {
            windows[0].webContents.send(IPC_CHANNELS.SHOW_ABOUT)
          }
          showMainWindow()
        }
      },
      { type: 'separator' },
      {
        label: '退出',
        click: () => {
          app.isQuitting = true
          app.quit()
        }
      }
    ])

    tray?.setContextMenu(contextMenu)
  }

  // 初始构建菜单
  updateContextMenu()

  // 监听 PythonManager 发出的应用级事件，更新菜单
  app.on('python-status-changed', updateContextMenu)

  // 单击托盘图标显示/隐藏窗口
  tray.on('click', () => {
    toggleMainWindow()
  })

  // 双击显示窗口
  tray.on('double-click', () => {
    showMainWindow()
  })

  return tray
}

/**
 * 获取状态标签中文
 */
function getStatusLabel(status: string): string {
  const labels: Record<string, string> = {
    stopped: '已停止',
    starting: '启动中...',
    running: '运行中',
    error: '错误',
    restarting: '重启中...'
  }
  return labels[status] ?? status
}

/**
 * 更新托盘图标（可用于状态指示）
 */
export function updateTrayIcon(isRunning: boolean): void {
  if (!tray) return

  const iconName = isRunning ? 'icon-active.png' : 'icon.png'
  const iconPath = resolveIconPath(iconName)
  const icon = nativeImage.createFromPath(iconPath)
  const resizedIcon = icon.isEmpty()
    ? nativeImage.createEmpty()
    : icon.resize({ width: 16, height: 16 })
  tray.setImage(resizedIcon)
}

/**
 * 更新托盘提示文字
 */
export function updateTrayTooltip(text: string): void {
  tray?.setToolTip(text)
}

/**
 * 销毁托盘
 */
export function destroyTray(): void {
  if (tray) {
    tray.destroy()
    tray = null
  }
}
