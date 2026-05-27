/**
 * Hermes Desktop - Python 后端进程管理器
 * 负责启动、停止、重启 Python 后端服务，健康检查和日志流
 *
 * 启动策略（按优先级）：
 * 1. PyInstaller sidecar (hermes-backend.exe) — 打包好的独立二进制
 * 2. 系统 Python + 源码 — 自动检测 Python、自动安装依赖
 */
import { ChildProcess, spawn, execSync } from 'child_process'
import { app, BrowserWindow } from 'electron'
import { net } from 'electron'
import { join } from 'path'
import { existsSync, mkdirSync, appendFileSync, writeFileSync } from 'fs'
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

/** 后端启动模式 */
type BackendMode = 'sidecar' | 'system-python' | 'none'

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
  private readonly logFilePath: string
  private consecutiveHealthFailures = 0
  private readonly maxConsecutiveHealthFailures = 3
  private lineBuffer = ''
  private destroyed = false
  private healthCheckInProgress = false
  private restartTimestamps: number[] = []

  // 缓存：避免重复检测
  private cachedPythonPath: string | null = null
  private cachedBackendMode: BackendMode | null = null
  private depsInstalled = false

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

    // 初始化日志文件
    const logDir = join(app.getPath('userData'), 'logs')
    if (!existsSync(logDir)) {
      mkdirSync(logDir, { recursive: true })
    }
    const now = new Date()
    const dateStr = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`
    this.logFilePath = join(logDir, `hermes-${dateStr}.log`)
    // 写入启动标记
    try {
      writeFileSync(this.logFilePath, `\n${'='.repeat(60)}\n[Hermes Desktop] 启动于 ${now.toISOString()}\n${'='.repeat(60)}\n`, { flag: 'a' })
    } catch { /* ignore */ }

    app.on('will-quit', () => {
      this.destroy()
    })
  }

  setMainWindow(window: BrowserWindow): void {
    this.mainWindow = window
  }

  getState(): PythonState {
    return {
      ...this.state,
      uptime: this.startTime ? Date.now() - this.startTime : null
    }
  }

  getLogs(): string[] {
    return [...this.logBuffer]
  }

  // ─── 获取后端源码目录（打包在 resources 里） ───
  private getBackendSourceDir(): string {
    return join(process.resourcesPath, 'python-backend-source')
  }

  // ─── 获取 requirements.txt 路径 ───
  private getRequirementsPath(): string {
    return join(this.getBackendSourceDir(), 'requirements.txt')
  }

  // ─── 检测系统 Python ───
  private findSystemPython(): string | null {
    this.addLog('[检测] 正在搜索系统 Python...')

    if (process.platform === 'win32') {
      // 方法1: py launcher (Python 官方安装器会注册)
      try {
        const pyResult = execSync('py -3 -c "import sys; print(sys.executable)"', {
          encoding: 'utf-8',
          timeout: 5000
        }).trim()
        if (pyResult && existsSync(pyResult)) {
          this.addLog(`[检测] 通过 py launcher 找到: ${pyResult}`)
          return pyResult
        }
      } catch { /* py launcher not available */ }

      // 方法2: where python（过滤掉 Windows Store stub）
      try {
        const whereResult = execSync('where python 2>nul', {
          encoding: 'utf-8',
          timeout: 5000
        }).trim()
        for (const line of whereResult.split('\n')) {
          const p = line.trim()
          if (!p || p.includes('WindowsApps')) continue // 跳过 Store stub
          if (existsSync(p)) {
            this.addLog(`[检测] 通过 where 找到: ${p}`)
            return p
          }
        }
      } catch { /* where failed */ }

      // 方法3: 常见安装路径
      const username = process.env.USERNAME || process.env.USER || 'Administrator'
      const commonPaths = [
        `C:\\Python312\\python.exe`,
        `C:\\Python311\\python.exe`,
        `C:\\Python310\\python.exe`,
        `C:\\Python39\\python.exe`,
        `C:\\Program Files\\Python312\\python.exe`,
        `C:\\Program Files\\Python311\\python.exe`,
        `C:\\Program Files\\Python310\\python.exe`,
        `C:\\Program Files\\Python39\\python.exe`,
        `C:\\Users\\${username}\\AppData\\Local\\Programs\\Python\\Python312\\python.exe`,
        `C:\\Users\\${username}\\AppData\\Local\\Programs\\Python\\Python311\\python.exe`,
        `C:\\Users\\${username}\\AppData\\Local\\Programs\\Python\\Python310\\python.exe`,
        `C:\\Users\\${username}\\AppData\\Local\\Programs\\Python\\Python39\\python.exe`,
      ]
      for (const p of commonPaths) {
        if (existsSync(p)) {
          this.addLog(`[检测] 通过常见路径找到: ${p}`)
          return p
        }
      }

      // 方法4: 从 PATH 中搜索
      const pathEnv = process.env.PATH || ''
      for (const dir of pathEnv.split(';')) {
        if (!dir || dir.includes('WindowsApps')) continue
        const candidate = join(dir, 'python.exe')
        if (existsSync(candidate)) {
          this.addLog(`[检测] 通过 PATH 找到: ${candidate}`)
          return candidate
        }
      }

      this.addLog('[检测] ❌ Windows 上未找到 Python (尝试了 py launcher / where / 常见路径 / PATH)')
    } else {
      // Linux/macOS
      try {
        const result = execSync('which python3 || which python', {
          encoding: 'utf-8',
          timeout: 5000
        }).trim()
        if (result && existsSync(result)) {
          this.addLog(`[检测] 找到: ${result}`)
          return result
        }
      } catch { /* not found */ }
    }

    return null
  }

  // ─── 验证 Python 版本 >= 3.9 ───
  private validatePython(pythonPath: string): boolean {
    try {
      const version = execSync(`"${pythonPath}" --version`, {
        encoding: 'utf-8',
        timeout: 5000
      }).trim()
      const match = version.match(/Python (\d+)\.(\d+)/)
      if (!match) return false
      const major = parseInt(match[1])
      const minor = parseInt(match[2])
      return major === 3 && minor >= 9
    } catch {
      return false
    }
  }

  // ─── 安装后端依赖 ───
  private async installDependencies(pythonPath: string): Promise<boolean> {
    const reqPath = this.getRequirementsPath()
    if (!existsSync(reqPath)) {
      this.addLog('[依赖] requirements.txt 不存在，跳过安装')
      return true // 没有 requirements 就当成功
    }

    this.addLog('[依赖] 正在安装后端依赖（首次运行可能需要 1-2 分钟）...')
    this.sendToRenderer(IPC_CHANNELS.PYTHON_STATUS_CHANGE, {
      ...this.getState(),
      status: 'starting',
      lastError: '正在安装 Python 依赖...'
    })

    return new Promise<boolean>((resolve) => {
      const pip = spawn(pythonPath, ['-m', 'pip', 'install', '-r', reqPath, '--quiet', '--disable-pip-version-check'], {
        stdio: ['pipe', 'pipe', 'pipe'],
        env: { ...process.env, PYTHONUNBUFFERED: '1' },
        windowsHide: true
      })

      let stderr = ''
      pip.stderr?.on('data', (data: Buffer) => {
        stderr += data.toString()
      })

      pip.on('error', (err) => {
        this.addLog(`[依赖] pip 启动失败: ${err.message}`)
        resolve(false)
      })

      pip.on('exit', (code) => {
        if (code === 0) {
          this.addLog('[依赖] ✅ 依赖安装完成')
          this.depsInstalled = true
          resolve(true)
        } else {
          this.addLog(`[依赖] ❌ 安装失败 (code=${code}): ${stderr.slice(-200)}`)
          resolve(false)
        }
      })
    })
  }

  // ─── 检测后端启动模式 ───
  private detectBackendMode(): { mode: BackendMode; pythonPath: string; serverScript: string | null } {
    // 缓存结果
    if (this.cachedBackendMode && this.cachedPythonPath) {
      return {
        mode: this.cachedBackendMode,
        pythonPath: this.cachedPythonPath,
        serverScript: this.cachedBackendMode === 'sidecar' ? null : join(this.getBackendSourceDir(), 'main.py')
      }
    }

    const isDev = !app.isPackaged

    // ── 开发模式：直接用 venv ──
    if (isDev) {
      const appRoot = app.getAppPath()
      const backendDir = join(appRoot, 'python-backend')
      const venvPaths = [
        join(backendDir, '.venv', 'Scripts', 'python.exe'),
        join(backendDir, '.venv', 'bin', 'python'),
        join(backendDir, 'venv', 'Scripts', 'python.exe'),
        join(backendDir, 'venv', 'bin', 'python')
      ]
      for (const p of venvPaths) {
        if (existsSync(p)) {
          this.cachedBackendMode = 'sidecar'
          this.cachedPythonPath = p
          return { mode: 'sidecar', pythonPath: p, serverScript: join(backendDir, 'main.py') }
        }
      }
    }

    // ── 生产模式 ──
    // 策略1: PyInstaller sidecar
    if (!isDev) {
      const ext = process.platform === 'win32' ? '.exe' : ''
      const sidecarPath = join(process.resourcesPath, 'python-backend', `hermes-backend${ext}`)
      this.addLog(`[检测] 查找 sidecar: ${sidecarPath} → ${existsSync(sidecarPath)}`)

      if (existsSync(sidecarPath)) {
        this.cachedBackendMode = 'sidecar'
        this.cachedPythonPath = sidecarPath
        return { mode: 'sidecar', pythonPath: sidecarPath, serverScript: null }
      }
    }

    // 策略2: 系统 Python + 源码
    const sysPython = this.findSystemPython()
    if (sysPython) {
      this.addLog(`[检测] 找到系统 Python: ${sysPython}`)
      if (this.validatePython(sysPython)) {
        const sourceDir = this.getBackendSourceDir()
        const mainPy = join(sourceDir, 'main.py')
        this.addLog(`[检测] 后端源码: ${sourceDir} → main.py=${existsSync(mainPy)}`)

        if (existsSync(mainPy)) {
          this.cachedBackendMode = 'system-python'
          this.cachedPythonPath = sysPython
          return { mode: 'system-python', pythonPath: sysPython, serverScript: mainPy }
        } else {
          this.addLog('[检测] ❌ 后端源码目录不存在')
        }
      } else {
        this.addLog(`[检测] ❌ Python 版本过低（需要 >= 3.9）`)
      }
    } else {
      this.addLog('[检测] ❌ 未找到系统 Python')
    }

    this.cachedBackendMode = 'none'
    this.cachedPythonPath = null
    return { mode: 'none', pythonPath: '', serverScript: null }
  }

    // ─── 尝试用指定模式启动后端 ───
  private async tryStart(pythonPath: string, serverScript: string | null, mode: string): Promise<boolean> {
    const args: string[] = []
    if (serverScript) args.push(serverScript)
    args.push('--port', String(this.options.port))
    args.push('--host', this.options.host)

    this.process = spawn(pythonPath, args, {
      stdio: ['pipe', 'pipe', 'pipe'],
      env: {
        ...process.env,
        HERMES_PORT: String(this.options.port),
        HERMES_HOST: this.options.host,
        HERMES_LOG_LEVEL: settingsStore.get('logLevel'),
        PYTHONUNBUFFERED: '1'
      },
      windowsHide: true,
      ...(serverScript ? { cwd: this.getBackendSourceDir() } : {})
    })

    // 收集 stderr 用于判断是否立即失败
    let earlyExit = false
    let exitCode: number | null = null

    this.process.stdout?.on('data', (data: Buffer) => this.processLogData(data, 'stdout'))
    this.process.stderr?.on('data', (data: Buffer) => this.processLogData(data, 'stderr'))

    this.process.on('error', (err) => {
      this.addLog(`[错误] 进程错误: ${err.message}`)
    })

    this.process.on('exit', (code, signal) => {
      this.addLog(`[退出] 进程退出，code=${code}, signal=${signal}`)
      this.flushLineBuffer()
      exitCode = code
      earlyExit = true
      this.process = null
    })

    this.state.pid = this.process.pid ?? null
    this.startTime = Date.now()

    // 等待服务就绪（最多 15 秒）
    const ready = await this.waitForReady(15000)
    if (ready) {
      // 成功！注册正常的退出处理器
      this.setupExitHandlers()
      return true
    }

    // 没有就绪，检查是否是立即失败（3秒内退出）
    if (earlyExit && exitCode !== 0) {
      this.addLog(`[启动] ${mode} 模式立即失败 (code=${exitCode})`)
      return false
    }

    // 超时
    this.addLog(`[启动] ${mode} 模式超时`)
    return false
  }

  // ─── 注册正常的退出/重启处理器（后端成功启动后调用） ───
  private setupExitHandlers(): void {
    if (!this.process) return
    // 移除旧的监听器，注册正式的
    this.process.removeAllListeners('exit')
    this.process.on('exit', (code, signal) => {
      this.addLog(`[退出] 进程退出，code=${code}, signal=${signal}`)
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
  }

  // ─── 启动后端（带 fallback） ───
  async start(): Promise<void> {
    if (this.process) {
      this.addLog('[管理器] Python 后端已在运行中')
      return
    }

    this.destroyed = false
    this.consecutiveHealthFailures = 0
    this.updateStatus('starting')
    this.addLog('[管理器] 正在启动 Python 后端...')

    // 检测启动模式
    const detection = this.detectBackendMode()

    if (detection.mode === 'none') {
      const errorMsg = '无法启动后端：未找到 PyInstaller 二进制，也未找到系统 Python (>= 3.9)。请安装 Python 3.9+ 后重试。'
      this.addLog(`[错误] ${errorMsg}`)
      this.state.lastError = errorMsg
      this.updateStatus('error')
      return
    }

    // ── 策略1: 尝试 sidecar ──
    if (detection.mode === 'sidecar') {
      this.addLog(`[启动] 尝试 sidecar 模式: ${detection.pythonPath}`)
      const sidecarOk = await this.tryStart(detection.pythonPath, null, 'sidecar')
      if (sidecarOk) {
        this.updateStatus('running')
        this.state.lastError = null
        this.state.restartCount = 0
        this.restartTimestamps = []
        this.startHealthCheck()
        this.addLog(`[管理器] ✅ 后端已启动 (sidecar 模式)，端口: ${this.options.port}`)
        return
      }
      // sidecar 失败，清除缓存，fallback 到系统 Python
      this.addLog('[启动] ❌ sidecar 失败，尝试 fallback 到系统 Python...')
      this.cachedBackendMode = null
      this.cachedPythonPath = null
    }

    // ── 策略2: 系统 Python + 源码 ──
    const sysPython = this.findSystemPython()
    const sourceDir = this.getBackendSourceDir()
    const mainPy = join(sourceDir, 'main.py')

    if (!sysPython) {
      this.addLog('[启动] ❌ 未找到系统 Python')
      this.state.lastError = '后端启动失败：sidecar 不可用且未安装 Python 3.9+'
      this.updateStatus('error')
      return
    }

    if (!this.validatePython(sysPython)) {
      this.addLog('[启动] ❌ Python 版本过低 (需要 >= 3.9)')
      this.state.lastError = '后端启动失败：Python 版本过低，需要 3.9+'
      this.updateStatus('error')
      return
    }

    if (!existsSync(mainPy)) {
      this.addLog(`[启动] ❌ 后端源码不存在: ${mainPy}`)
      this.state.lastError = '后端启动失败：源码文件缺失'
      this.updateStatus('error')
      return
    }

    this.addLog(`[启动] 使用系统 Python: ${sysPython}`)

    // 安装依赖
    if (!this.depsInstalled) {
      const ok = await this.installDependencies(sysPython)
      if (!ok) {
        this.state.lastError = 'Python 依赖安装失败，请检查网络连接'
        this.updateStatus('error')
        return
      }
    }

    // 启动
    const ok = await this.tryStart(sysPython, mainPy, 'system-python')
    if (ok) {
      this.updateStatus('running')
      this.state.lastError = null
      this.state.restartCount = 0
      this.restartTimestamps = []
      this.startHealthCheck()
      this.addLog(`[管理器] ✅ 后端已启动 (系统 Python 模式)，端口: ${this.options.port}`)
    } else {
      this.state.lastError = '后端启动失败：sidecar 和系统 Python 均无法启动'
      this.updateStatus('error')
    }
  }

  // ─── 停止后端 ───
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

      try { proc.kill('SIGTERM') } catch { /* already dead */ }
    })
  }

  // ─── 重启后端 ───
  async restart(): Promise<void> {
    this.addLog('[管理器] 正在重启 Python 后端...')
    this.state.restartCount++
    this.restartTimestamps.push(Date.now())
    this.updateStatus('restarting')
    await this.stop()
    await this.start()
  }

  // ─── 健康检查 ───
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

  // ─── 等待服务就绪 ───
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

  // ─── 健康检查定时器 ───
  private startHealthCheck(): void {
    this.stopHealthCheck()
    this.consecutiveHealthFailures = 0
    this.healthCheckInProgress = false
    this.healthCheckTimer = setInterval(async () => {
      if (this.healthCheckInProgress) return
      this.healthCheckInProgress = true
      try {
        const health = await this.checkHealth()
        if (!health && this.state.status === 'running') {
          this.consecutiveHealthFailures++
          this.addLog(`[健康检查] 服务无响应 (${this.consecutiveHealthFailures}/${this.maxConsecutiveHealthFailures})`)

          if (this.consecutiveHealthFailures >= this.maxConsecutiveHealthFailures) {
            this.state.lastError = '健康检查失败'
            this.updateStatus('error')
            this.consecutiveHealthFailures = 0
            this.handleUnexpectedExit()
          }
        } else if (health) {
          this.consecutiveHealthFailures = 0
        }
      } finally {
        this.healthCheckInProgress = false
      }
    }, this.options.healthCheckInterval)
  }

  private stopHealthCheck(): void {
    if (this.healthCheckTimer) {
      clearInterval(this.healthCheckTimer)
      this.healthCheckTimer = null
    }
    this.consecutiveHealthFailures = 0
    this.healthCheckInProgress = false
  }

  private clearRestartTimer(): void {
    if (this.restartTimer) {
      clearTimeout(this.restartTimer)
      this.restartTimer = null
    }
  }

  private getEffectiveRestartCount(): number {
    const now = Date.now()
    this.restartTimestamps = this.restartTimestamps.filter(
      (ts) => now - ts < RESTART_WINDOW_MS
    )
    return this.restartTimestamps.length
  }

  private async handleUnexpectedExit(): Promise<void> {
    if (this.destroyed) return

    const effectiveCount = this.getEffectiveRestartCount()

    if (effectiveCount < this.options.maxRestarts) {
      this.addLog(
        `[管理器] 将在 3 秒后尝试重启 (${effectiveCount + 1}/${this.options.maxRestarts})`
      )
      this.restartTimer = setTimeout(async () => {
        this.restartTimer = null
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

  private updateStatus(status: PythonStatus): void {
    this.state.status = status
    this.sendToRenderer(IPC_CHANNELS.PYTHON_STATUS_CHANGE, this.getState())
    app.emit('python-status-changed', this.getState())
  }

  private sendToRenderer(channel: string, data: unknown): void {
    if (this.mainWindow && !this.mainWindow.isDestroyed()) {
      this.mainWindow.webContents.send(channel, data)
    }
  }

  private processLogData(data: Buffer, source: 'stdout' | 'stderr'): void {
    this.lineBuffer += data.toString()
    const lines = this.lineBuffer.split('\n')
    this.lineBuffer = lines.pop() ?? ''
    for (const line of lines) {
      const trimmed = line.trim()
      if (trimmed) {
        this.addLog(`[${source}] ${trimmed}`)
        this.sendToRenderer(IPC_CHANNELS.PYTHON_LOG_STREAM, { type: source, message: trimmed })
      }
    }
  }

  private flushLineBuffer(): void {
    if (this.lineBuffer.trim()) {
      const remaining = this.lineBuffer.trim()
      this.addLog(`[stdout] ${remaining}`)
      this.sendToRenderer(IPC_CHANNELS.PYTHON_LOG_STREAM, { type: 'stdout', message: remaining })
    }
    this.lineBuffer = ''
  }

  /** 获取日志文件路径（供渲染进程显示） */
  getLogFilePath(): string {
    return this.logFilePath
  }

  private addLog(message: string): void {
    const timestamp = new Date().toISOString()
    const logEntry = `[${timestamp}] ${message}`
    this.logBuffer.push(logEntry)
    if (this.logBuffer.length > this.maxLogBuffer) {
      this.logBuffer.shift()
    }
    console.log(logEntry)
    // 写入日志文件
    try {
      appendFileSync(this.logFilePath, logEntry + '\n')
    } catch { /* ignore */ }
  }

  destroy(): void {
    this.destroyed = true
    this.stopHealthCheck()
    this.clearRestartTimer()
    if (this.process) {
      try { this.process.kill('SIGKILL') } catch { /* already dead */ }
    }
    this.flushLineBuffer()
  }
}
