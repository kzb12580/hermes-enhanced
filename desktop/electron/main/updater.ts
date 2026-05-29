/**
 * Hermes Desktop - 自动更新管理
 */
import { autoUpdater, UpdateInfo as ElectronUpdateInfo } from 'electron-updater'
import { app, BrowserWindow, dialog } from 'electron'
import { IPC_CHANNELS, UpdateStatus, UpdateInfo, UpdateProgress } from '../shared/types'

let mainWindow: BrowserWindow | null = null
let currentStatus: UpdateStatus = 'idle'
let handlersRegistered = false

/**
 * 初始化自动更新器
 */
export function initUpdater(window: BrowserWindow): void {
  mainWindow = window

  // 配置更新器
  autoUpdater.autoDownload = false
  autoUpdater.autoInstallOnAppQuit = true
  autoUpdater.allowDowngrade = false

  // GitHub 发布配置
  autoUpdater.setFeedURL({
    provider: 'github',
    owner: 'kzb12580',
    repo: 'hermes-enhanced',
    releaseType: 'release'
  })

  // 注册事件处理器
  setupEventHandlers()
}

/**
 * 注册更新器事件处理
 */
function setupEventHandlers(): void {
  if (handlersRegistered) return
  handlersRegistered = true

  // 检查更新中
  autoUpdater.on('checking-for-update', () => {
    updateStatus('checking')
    sendToRenderer(IPC_CHANNELS.UPDATE_STATUS, { status: 'checking' })
  })

  // 发现新版本
  autoUpdater.on('update-available', (info: ElectronUpdateInfo) => {
    updateStatus('available')
    const rd = info.releaseDate as unknown
    const updateInfo: UpdateInfo = {
      version: info.version,
      releaseDate: typeof rd === 'string' ? rd : rd instanceof Date ? rd.toISOString() : new Date().toISOString(),
      releaseNotes: typeof info.releaseNotes === 'string' ? info.releaseNotes : undefined
    }
    sendToRenderer(IPC_CHANNELS.UPDATE_STATUS, { status: 'available', info: updateInfo })

    // 弹窗询问是否下载
    if (!mainWindow || mainWindow.isDestroyed()) return
    dialog
      .showMessageBox(mainWindow, {
        type: 'info',
        title: '发现新版本',
        message: `Hermes Desktop ${info.version} 可用`,
        detail: '是否立即下载更新？',
        buttons: ['下载', '稍后'],
        defaultId: 0,
        cancelId: 1
      })
      .then(({ response }) => {
        if (response === 0) {
          autoUpdater.downloadUpdate()
        }
      })
  })

  // 没有可用更新
  autoUpdater.on('update-not-available', (info: ElectronUpdateInfo) => {
    updateStatus('not-available')
    sendToRenderer(IPC_CHANNELS.UPDATE_STATUS, {
      status: 'not-available',
      version: info.version
    })
  })

  // 下载进度
  autoUpdater.on('download-progress', (progress) => {
    const progressInfo: UpdateProgress = {
      percent: progress.percent,
      bytesPerSecond: progress.bytesPerSecond,
      total: progress.total,
      transferred: progress.transferred
    }
    updateStatus('downloading')
    sendToRenderer(IPC_CHANNELS.UPDATE_PROGRESS, progressInfo)
  })

  // 下载完成
  autoUpdater.on('update-downloaded', (info: ElectronUpdateInfo) => {
    updateStatus('downloaded')
    const rd = info.releaseDate as unknown
    const updateInfo: UpdateInfo = {
      version: info.version,
      releaseDate: typeof rd === 'string' ? rd : rd instanceof Date ? rd.toISOString() : new Date().toISOString(),
      releaseNotes: typeof info.releaseNotes === 'string' ? info.releaseNotes : undefined
    }
    sendToRenderer(IPC_CHANNELS.UPDATE_STATUS, { status: 'downloaded', info: updateInfo })

    // 弹窗询问是否立即安装
    if (!mainWindow || mainWindow.isDestroyed()) return
    dialog
      .showMessageBox(mainWindow, {
        type: 'info',
        title: '更新已下载',
        message: `版本 ${info.version} 已准备就绪`,
        detail: '应用需要重启以完成更新。是否立即重启？',
        buttons: ['立即重启', '稍后重启'],
        defaultId: 0,
        cancelId: 1
      })
      .then(({ response }) => {
        if (response === 0) {
          autoUpdater.quitAndInstall(false, true)
        }
      })
  })

  // 更新错误
  autoUpdater.on('error', (error) => {
    updateStatus('error')
    sendToRenderer(IPC_CHANNELS.UPDATE_STATUS, {
      status: 'error',
      error: error.message
    })
    console.error('[更新器] 错误:', error.message)
  })
}

/**
 * 手动检查更新
 */
export async function checkForUpdates(): Promise<void> {
  try {
    await autoUpdater.checkForUpdates()
  } catch (err) {
    console.error('[更新器] 检查更新失败:', err)
    updateStatus('error')
  }
}

/**
 * 下载更新
 */
export async function downloadUpdate(): Promise<void> {
  try {
    await autoUpdater.downloadUpdate()
  } catch (err) {
    console.error('[更新器] 下载更新失败:', err)
  }
}

/**
 * 安装更新并重启
 */
export function installUpdate(): void {
  autoUpdater.quitAndInstall(false, true)
}

/**
 * 获取当前更新状态
 */
export function getUpdateStatus(): UpdateStatus {
  return currentStatus
}

/**
 * 更新状态并通知渲染进程
 */
function updateStatus(status: UpdateStatus): void {
  currentStatus = status
}

/**
 * 向渲染进程发送消息
 */
function sendToRenderer(channel: string, data: unknown): void {
  if (mainWindow && !mainWindow.isDestroyed()) {
    mainWindow.webContents.send(channel, data)
  }
}
