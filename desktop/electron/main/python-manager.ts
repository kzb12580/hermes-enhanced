/**
 * Hermes Desktop - Python 后端进程管理器
 * 负责启动、停止、重启 Python 后端服务，健康检查和日志流
 */
import { ChildProcess, spawn, execSync } from 'child_process'
import { app, BrowserWindow } from 'electron'
import { net } from 'electron'
import { join } from 'path'
import { existsSync } from 'fs'
import { IPC_CHANNELS, PythonState, PythonHealthResponse, PythonStatus } from '../shared/types'
import { settingsStore } from './store'

interface PythonManagerOptions {
  port?: number
  host?: string
  maxRestarts?: number
  healthCheckInterval?: number
  healthCheckTimeout?: number
}

/** Sliding window duration for restart count reset (5 minutes) */
const RESTART_WINDOW_MS = 5 * 60 * 1000

export class PythonManager {
  private process: ChildProcess | null = null
  private state: PythonState
  private healthCheckTimer: ReturnType<typeof setInterval> | null = null
  private restartTimer: ReturnType<typeof setTimeout> | null = null
  private mainWindow: BrowserWindow | null = null
  private options: Required<PythonManagerOptions>
  private startTime: number | null = null
  private logBuffer: string[] = []
  private readonly maxLogBuffer = 500
  private consecutiveHealthFailures = 0
  private readonly maxConsecutiveHealthFailures = 3
  private lineBuffer = ''
  private destroyed = false
  // FIX #5: Prevent concurrent health checks
  private healthCheckInProgress = false
  // FIX #2: Track restart timestamps for sliding window
  private restartTimestamps: number[] = []

  constructor(options: PythonManagerOptions = {}) {
    const port = options.port ?? settingsStore.get('pythonPort')
    this.options = {
      port,
      host: options.host ?? '127.0.0.1',
      maxRestarts: options.maxRestarts ?? settingsStore.get('pythonMaxRestarts'),
      healthCheckInterval: options.healthCheckInterval ?? 5000,
      healthCheckTimeout: options.healthCheckTimeout ?? 3000
    }

    this.state = {
      status: 'stopped',
      pid: null,
      port: this.options.port,
      uptime: null,
      lastError: null,
      restartCount: 0
    }

    // Register cleanup on app quit so Python backend is properly destroyed
    app.on('will-quit', () => {
      this.destroy()
    })
  }

  /** 设置主窗口引用，用于发送事件 */
  setMainWindow(window: BrowserWindow): void {
    this.mainWindow = window
  }

  /** 获取当前状态 */
  getState(): PythonState {
    return {
      ...this.state,
      uptime: this.startTime ? Date.now() - this.startTime : null
    }
  }

  /** 获取日志缓冲区 */
  getLogs(): string[] {
    return [...this.logBuffer]
  }

  /** 查找 Python 可执行文件路径 */
  private findPythonPath(): string {
    // 1. 优先使用打包后的 sidecar
    const isDev = !app.isPackaged
    if (!isDev) {
      const platform = process.platform
      const ext = platform === 'win32' ? '.exe' : ''
      const sidecarPath = join(
        process.resourcesPath,
        'python-backend',
        `hermes-backend${ext}`
      )
      if (existsSync(sidecarPath)) {
        return sidecarPath
      }
    }

    // 2. 开发模式：查找 python 后端目录
    // python-backend/ is a child directory of the app root (app.getAppPath())
    const appRoot = app.getAppPath()
    const backendDir = join(appRoot, 'python-backend')
    const devPaths = [
      join(backendDir, '.venv', 'bin', 'python'),
      join(backendDir, 'venv', 'bin', 'python'),
      join(backendDir, '.venv', 'Scripts', 'python.exe'),
      join(backendDir, 'venv', 'Scripts', 'python.exe')
    ]

    for (const p of devPaths) {
      if (existsSync(p)) return p
    }

    // 3. 退回系统 Python
    try {
      if (process.platform === 'win32') {
        return execSync('where python', { encoding: 'utf-8' }).trim().split('\n')[0]
      }
      return execSync('which python3 || which python', { encoding: 'utf-8' }).trim()
    } catch {
      return 'python3'
    }
  }

  /** 查找后端入口脚本 */
  private findServerScript(): string | null {
    const isDev = !app.isPackaged
    if (!isDev) {
      // 生产模式使用 sidecar，不需要脚本路径
      return null
    }

    const appRoot = app.getAppPath()
    const backendDir = join(appRoot, 'python-backend')
    const candidates = [
      join(backendDir, 'main.py'),
      join(backendDir, 'server.py'),
      join(backendDir, 'app.py')
    ]

    for (const p of candidates) {
      if (existsSync(p)) return p
    }
    return null
  }

  /** 启动 Python 后端 */
  async start(): Promise<void> {
    if (this.process) {
      this.addLog('[管理器] Python 后端已在运行中')
      return
    }

    this.destroyed = false
    this.consecutiveHealthFailures = 0
    this.updateStatus('starting')
    this.addLog('[管理器] 正在启动 Python 后端...')

    const pythonPath = this.findPythonPath()
    const serverScript = this.findServerScript()

    const args: string[] = []
    if (serverScript) {
      args.push(serverScript)
    }
    args.push('--port', String(this.options.port))
    args.push('--host', this.options.host)

    try {
      this.process = spawn(pythonPath, args, {
        stdio: ['pipe', 'pipe', 'pipe'],
        env: {
          ...process.env,
          HERMES_PORT: String(this.options.port),
          HERMES_HOST: this.options.host,
          HERMES_LOG_LEVEL: settingsStore.get('logLevel'),
          PYTHONUNBUFFERED: '1'
        },
        // 生产模式下隐藏控制台窗口
        windowsHide: true
      })

      this.process.stdout?.on('data', (data: Buffer) => {
        this.processLogData(data, 'stdout')
      })

      this.process.stderr?.on('data', (data: Buffer) => {
        this.processLogData(data, 'stderr')
      })

      this.process.on('error', (err) => {
        this.addLog(`[错误] 进程错误: ${err.message}`)
        this.state.lastError = err.message
        this.updateStatus('error')
        this.handleUnexpectedExit()
      })

      this.process.on('exit', (code, signal) => {
        this.addLog(`[退出] 进程退出，code=${code}, signal=${signal}`)

        // FIX #4: Flush remaining lineBuffer on process exit
        this.flushLineBuffer()

        this.state.pid = null
        if (!this.destroyed && this.state.status !== 'stopping' && this.state.status !== 'stopped') {
          this.state.lastError = `意外退出: code=${code}, signal=${signal}`
          this.updateStatus('error')
          this.handleUnexpectedExit()
        } else {
          this.updateStatus('stopped')
        }
        this.process = null
        this.stopHealthCheck()
      })

      this.state.pid = this.process.pid ?? null
      this.startTime = Date.now()

      // 等待服务就绪
      const ready = await this.waitForReady(15000)
      if (ready) {
        this.updateStatus('running')
        this.state.lastError = null
        this.state.restartCount = 0
        this.restartTimestamps = []
        this.startHealthCheck()
        this.addLog(`[管理器] Python 后端已启动，端口: ${this.options.port}`)
      } else {
        this.addLog('[管理器] Python 后端启动超时')
        this.state.lastError = '服务启动超时'
        this.updateStatus('error')
        await this.stop()
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err)
      this.addLog(`[错误] 启动失败: ${msg}`)
      this.state.lastError = msg
      this.updateStatus('error')
    }
  }

  /** 停止 Python 后端 */
  async stop(): Promise<void> {
    if (!this.process) {
      this.updateStatus('stopped')
      return
    }

    this.updateStatus('stopping')
    this.addLog('[管理器] 正在停止 Python 后端...')
    this.stopHealthCheck()
    this.clearRestartTimer()

    return new Promise<void>((resolve) => {
      const proc = this.process
      if (!proc) {
        this.updateStatus('stopped')
        resolve()
        return
      }

      const timeout = setTimeout(() => {
        this.addLog('[管理器] 强制终止进程')
        try { proc.kill('SIGKILL') } catch { /* already dead */ }
        resolve()
      }, 5000)

      proc.on('exit', () => {
        clearTimeout(timeout)
        this.process = null
        this.state.pid = null
        this.startTime = null
        this.updateStatus('stopped')
        this.addLog('[管理器] Python 后端已停止')
        resolve()
      })

      // 优雅关闭
      try { proc.kill('SIGTERM') } catch { /* already dead */ }
    })
  }

  /** 重启 Python 后端 */
  async restart(): Promise<void> {
    this.addLog('[管理器] 正在重启 Python 后端...')
    this.state.restartCount++
    // FIX #2: Track restart timestamp for sliding window
    this.restartTimestamps.push(Date.now())
    this.updateStatus('restarting')
    await this.stop()
    await this.start()
  }

  /** 健康检查 */
  async checkHealth(): Promise<PythonHealthResponse | null> {
    return new Promise((resolve) => {
      const request = net.request({
        method: 'GET',
        url: `http://${this.options.host}:${this.options.port}/api/health`
      })

      const timeout = setTimeout(() => {
        request.abort()
        resolve(null)
      }, this.options.healthCheckTimeout)

      request.on('response', (response) => {
        // Verify status code is 200
        const statusCode = response.statusCode
        if (statusCode !== 200) {
          clearTimeout(timeout)
          resolve(null)
          return
        }

        let body = ''
        response.on('data', (chunk) => {
          body += chunk.toString()
        })
        response.on('end', () => {
          clearTimeout(timeout)
          try {
            resolve(JSON.parse(body) as PythonHealthResponse)
          } catch {
            resolve(null)
          }
        })
      })

      request.on('error', () => {
        clearTimeout(timeout)
        resolve(null)
      })

      request.end()
    })
  }

  /** 等待服务就绪 */
  private async waitForReady(timeout: number): Promise<boolean> {
    const start = Date.now()
    const interval = 500

    while (Date.now() - start < timeout) {
      const health = await this.checkHealth()
      if (health) return true
      await new Promise((r) => setTimeout(r, interval))
    }
    return false
  }

  /** 启动定时健康检查 */
  private startHealthCheck(): void {
    this.stopHealthCheck()
    this.consecutiveHealthFailures = 0
    this.healthCheckInProgress = false
    this.healthCheckTimer = setInterval(async () => {
      // FIX #5: Don't run concurrent health checks
      if (this.healthCheckInProgress) {
        this.addLog('[健康检查] 跳过——上一次检查仍在进行中')
        return
      }
      this.healthCheckInProgress = true
      try {
        const health = await this.checkHealth()
        if (!health && this.state.status === 'running') {
          this.consecutiveHealthFailures++
          this.addLog(`[健康检查] 服务无响应 (连续失败: ${this.consecutiveHealthFailures}/${this.maxConsecutiveHealthFailures})`)

          if (this.consecutiveHealthFailures >= this.maxConsecutiveHealthFailures) {
            this.state.lastError = '健康检查失败'
            this.updateStatus('error')
            this.consecutiveHealthFailures = 0
            this.handleUnexpectedExit()
          }
        } else if (health) {
          // Reset counter on successful check
          this.consecutiveHealthFailures = 0
        }
      } finally {
        this.healthCheckInProgress = false
      }
    }, this.options.healthCheckInterval)
  }

  /** 停止健康检查 */
  private stopHealthCheck(): void {
    if (this.healthCheckTimer) {
      clearInterval(this.healthCheckTimer)
      this.healthCheckTimer = null
    }
    this.consecutiveHealthFailures = 0
    this.healthCheckInProgress = false
  }

  /** 清除待执行的重启计时器 */
  private clearRestartTimer(): void {
    if (this.restartTimer) {
      clearTimeout(this.restartTimer)
      this.restartTimer = null
    }
  }

  // FIX #2: Get effective restart count within the sliding window
  private getEffectiveRestartCount(): number {
    const now = Date.now()
    // Prune timestamps outside the window
    this.restartTimestamps = this.restartTimestamps.filter(
      (ts) => now - ts < RESTART_WINDOW_MS
    )
    return this.restartTimestamps.length
  }

  /** 处理意外退出（自动重启） */
  // FIX #3: Make handleUnexpectedExit async to await restart()
  private async handleUnexpectedExit(): Promise<void> {
    if (this.destroyed) return

    // FIX #2: Use sliding window count instead of simple counter
    const effectiveCount = this.getEffectiveRestartCount()

    if (effectiveCount < this.options.maxRestarts) {
      this.addLog(
        `[管理器] 将在 3 秒后尝试重启 (${effectiveCount + 1}/${this.options.maxRestarts})`
      )
      this.restartTimer = setTimeout(async () => {
        this.restartTimer = null
        // FIX #3: Await the restart to properly sequence operations
        try {
          await this.restart()
        } catch (err) {
          const msg = err instanceof Error ? err.message : String(err)
          this.addLog(`[错误] 重启失败: ${msg}`)
        }
      }, 3000)
    } else {
      this.addLog('[管理器] 已达到最大重启次数，停止重启')
    }
  }

  /** 更新状态并通知渲染进程和应用级事件 */
  private updateStatus(status: PythonStatus): void {
    this.state.status = status
    this.sendToRenderer(IPC_CHANNELS.PYTHON_STATUS_CHANGE, this.getState())
    // Emit app-level event so tray and other listeners can react
    app.emit('python-status-changed', this.getState())
  }

  /** 向渲染进程发送消息 */
  private sendToRenderer(channel: string, data: unknown): void {
    if (this.mainWindow && !this.mainWindow.isDestroyed()) {
      this.mainWindow.webContents.send(channel, data)
    }
  }

  /** Process stdout/stderr data with line buffering to handle partial lines */
  private processLogData(data: Buffer, source: 'stdout' | 'stderr'): void {
    this.lineBuffer += data.toString()
    const lines = this.lineBuffer.split('\n')
    // Keep the last element as it may be an incomplete line
    this.lineBuffer = lines.pop() ?? ''
    for (const line of lines) {
      const trimmed = line.trim()
      if (trimmed) {
        this.addLog(`[${source}] ${trimmed}`)
        this.sendToRenderer(IPC_CHANNELS.PYTHON_LOG_STREAM, { type: source, message: trimmed })
      }
    }
  }

  // FIX #4: Flush any remaining content in the line buffer
  private flushLineBuffer(): void {
    if (this.lineBuffer.trim()) {
      const remaining = this.lineBuffer.trim()
      this.addLog(`[stdout] ${remaining}`)
      this.sendToRenderer(IPC_CHANNELS.PYTHON_LOG_STREAM, { type: 'stdout', message: remaining })
    }
    this.lineBuffer = ''
  }

  /** 添加日志到缓冲区 */
  private addLog(message: string): void {
    const timestamp = new Date().toISOString()
    const logEntry = `[${timestamp}] ${message}`
    this.logBuffer.push(logEntry)
    if (this.logBuffer.length > this.maxLogBuffer) {
      this.logBuffer.shift()
    }
    console.log(logEntry)
  }

  /** 销毁管理器 — safe for app quit, does NOT trigger handleUnexpectedExit */
  destroy(): void {
    this.destroyed = true
    this.stopHealthCheck()
    this.clearRestartTimer()
    // FIX #1: Don't remove exit listeners — let them fire naturally.
    // The exit handler checks `this.destroyed` and skips handleUnexpectedExit.
    // Removing listeners could cause the process to become a zombie if the
    // exit event is lost. Just kill the process and let the exit handler clean up.
    if (this.process) {
      try { this.process.kill('SIGKILL') } catch { /* already dead */ }
      // Don't null out this.process here — the exit handler will do it
    }
    // FIX #4: Flush any remaining line buffer on destroy
    this.flushLineBuffer()
  }
}


