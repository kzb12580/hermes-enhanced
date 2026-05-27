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

export class PythonManager {
  private process: ChildProcess | null = null
  private state: PythonState
  private healthCheckTimer: ReturnType<typeof setInterval> | null = null
  private mainWindow: BrowserWindow | null = null
  private options: Required<PythonManagerOptions>
  private startTime: number | null = null
  private logBuffer: string[] = []
  private readonly maxLogBuffer = 500

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
    const devPaths = [
      join(app.getAppPath(), '..', '..', 'python-backend', 'venv', 'bin', 'python'),
      join(app.getAppPath(), '..', '..', 'python-backend', '.venv', 'Scripts', 'python.exe'),
      join(app.getAppPath(), '..', '..', 'python-backend', 'venv', 'Scripts', 'python.exe')
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

    const candidates = [
      join(app.getAppPath(), '..', '..', 'python-backend', 'main.py'),
      join(app.getAppPath(), '..', '..', 'python-backend', 'server.py'),
      join(app.getAppPath(), '..', '..', 'python-backend', 'app.py')
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
        const msg = data.toString().trim()
        if (msg) {
          this.addLog(`[stdout] ${msg}`)
          this.sendToRenderer(IPC_CHANNELS.PYTHON_LOG_STREAM, { type: 'stdout', message: msg })
        }
      })

      this.process.stderr?.on('data', (data: Buffer) => {
        const msg = data.toString().trim()
        if (msg) {
          this.addLog(`[stderr] ${msg}`)
          this.sendToRenderer(IPC_CHANNELS.PYTHON_LOG_STREAM, { type: 'stderr', message: msg })
        }
      })

      this.process.on('error', (err) => {
        this.addLog(`[错误] 进程错误: ${err.message}`)
        this.state.lastError = err.message
        this.updateStatus('error')
        this.handleUnexpectedExit()
      })

      this.process.on('exit', (code, signal) => {
        this.addLog(`[退出] 进程退出，code=${code}, signal=${signal}`)
        this.state.pid = null
        if (this.state.status !== 'stopping' && this.state.status !== 'stopped') {
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

    this.addLog('[管理器] 正在停止 Python 后端...')
    this.stopHealthCheck()

    return new Promise<void>((resolve) => {
      const timeout = setTimeout(() => {
        this.addLog('[管理器] 强制终止进程')
        this.process?.kill('SIGKILL')
        resolve()
      }, 5000)

      this.process!.on('exit', () => {
        clearTimeout(timeout)
        this.process = null
        this.state.pid = null
        this.startTime = null
        this.updateStatus('stopped')
        this.addLog('[管理器] Python 后端已停止')
        resolve()
      })

      // 优雅关闭
      this.process!.kill('SIGTERM')
    })
  }

  /** 重启 Python 后端 */
  async restart(): Promise<void> {
    this.addLog('[管理器] 正在重启 Python 后端...')
    this.state.restartCount++
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
    this.healthCheckTimer = setInterval(async () => {
      const health = await this.checkHealth()
      if (!health && this.state.status === 'running') {
        this.addLog('[健康检查] 服务无响应')
        this.state.lastError = '健康检查失败'
        this.updateStatus('error')
        this.handleUnexpectedExit()
      }
    }, this.options.healthCheckInterval)
  }

  /** 停止健康检查 */
  private stopHealthCheck(): void {
    if (this.healthCheckTimer) {
      clearInterval(this.healthCheckTimer)
      this.healthCheckTimer = null
    }
  }

  /** 处理意外退出（自动重启） */
  private async handleUnexpectedExit(): Promise<void> {
    if (this.state.restartCount < this.options.maxRestarts) {
      this.addLog(
        `[管理器] 将在 3 秒后尝试重启 (${this.state.restartCount + 1}/${this.options.maxRestarts})`
      )
      setTimeout(() => this.restart(), 3000)
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

  /** 销毁管理器 */
  destroy(): void {
    this.stopHealthCheck()
    if (this.process) {
      this.process.kill('SIGKILL')
      this.process = null
    }
  }
}
