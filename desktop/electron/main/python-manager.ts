/**
 * Hermes Desktop - Python 后端进程管理器
 * 负责启动、停止、重启 Python 后端服务，健康检查和日志流
 *
 * 启动策略（按优先级）：
 * 1. PyInstaller sidecar (hermes-backend.exe) — 打包好的独立二进制
 * 2. 系统 Python + 源码 — 自动检测 Python、自动安装依赖
 */
import { ChildProcess, spawn, exec as execCb } from 'child_process'
import { promisify } from 'util'

const execAsync = promisify(execCb)
import { app, BrowserWindow } from 'electron'
import { net } from 'electron'
import { join } from 'path'
import { existsSync, mkdirSync, appendFileSync, writeFileSync } from 'fs'
import { createServer } from 'net'
import treeKill from 'tree-kill'
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

/** Environment variable whitelist for spawned Python processes */
const ENV_WHITELIST_KEYS = [
  'PATH', 'HOME', 'USERPROFILE', 'TEMP', 'TMP', 'TMPDIR',
  'SYSTEMROOT', 'WINDIR', 'COMSPEC', 'PATHEXT', 'LANG', 'LC_ALL', 'LC_CTYPE', 'TERM',
  'SHELL', 'USER', 'LOGNAME',
  'XDG_RUNTIME_DIR', 'XDG_DATA_HOME', 'XDG_CONFIG_HOME',
  'HTTP_PROXY', 'HTTPS_PROXY', 'NO_PROXY',
  'http_proxy', 'https_proxy', 'no_proxy',
]

/** Build a sanitized env object with only whitelisted keys plus Hermes overrides */
function buildSafeEnv(overrides: Record<string, string> = {}): NodeJS.ProcessEnv {
  const safe: Record<string, string> = {}
  for (const key of ENV_WHITELIST_KEYS) {
    const val = process.env[key]
    if (val !== undefined) safe[key] = val
  }
  return { ...safe, ...overrides }
}

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
  private lastStderrLines: string[] = []
  private destroyed = false
  private healthCheckInProgress = false
  private restartTimestamps: number[] = []
  private operationLock = false  // 防止并发操作

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
    const logDir = join(process.env.HOME || process.env.USERPROFILE || '', '.hermes', 'desktop', 'logs')
    mkdirSync(logDir, { recursive: true })
    this.logFilePath = join(logDir, 'python-backend.log')
  }

  /** 注册主窗口引用（用于发送事件） */
  setMainWindow(win: BrowserWindow | null): void {
    this.mainWindow = win
  }

  // ─── 状态管理 ───
  private updateStatus(status: PythonStatus): void {
    this.state.status = status
    this.state.uptime = this.startTime ? Date.now() - this.startTime : null
    this.mainWindow?.webContents.send(IPC_CHANNELS.PYTHON_STATUS_CHANGE, { ...this.state })
  }

  getState(): PythonState {
    return {
      ...this.state,
      uptime: this.startTime ? Date.now() - this.startTime : null
    }
  }

  // ─── 日志 ───
  private addLog(line: string): void {
    const ts = new Date().toISOString().replace('T', ' ').slice(0, 19)
    const entry = `[${ts}] ${line}`
    this.logBuffer.push(entry)
    if (this.logBuffer.length > this.maxLogBuffer) {
      this.logBuffer.shift()
    }
    try {
      appendFileSync(this.logFilePath, entry + '\n')
    } catch { /* ignore */ }
    this.mainWindow?.webContents.send(IPC_CHANNELS.PYTHON_LOG_STREAM, line)
  }

  getLogs(): string[] {
    return [...this.logBuffer]
  }

  // ─── 端口检测 ───
  private findAvailablePort(startPort: number): Promise<number> {
    return new Promise((resolve) => {
      const server = createServer()
      server.listen(startPort, this.options.host, () => {
        server.close(() => resolve(startPort))
      })
      server.on('error', () => {
        // 端口被占用，尝试下一个
        resolve(this.findAvailablePort(startPort + 1))
      })
    })
  }

  // ─── 进程树清理 ───
  private killProcessTree(proc: ChildProcess, signal: string): Promise<void> {
    return new Promise((resolve) => {
      if (!proc.pid) {
        resolve()
        return
      }
      treeKill(proc.pid, signal as NodeJS.Signals, (err) => {
        if (err) {
          // fallback: 直接 kill
          try { proc.kill(signal as NodeJS.Signals) } catch { /* already dead */ }
        }
        resolve()
      })
    })
  }

  // ─── Python 检测 ───
  private async findSystemPython(): Promise<string | null> {
    // 检查缓存
    if (this.cachedPythonPath && this.cachedBackendMode === 'system-python') {
      return this.cachedPythonPath
    }

    const candidates = process.platform === 'win32'
      ? ['python', 'python3', 'py -3']
      : ['python3', 'python']

    for (const cmd of candidates) {
      try {
        const { stdout } = await execAsync(`${cmd} --version`, { timeout: 5000 })
        const versionMatch = stdout.match(/Python (\d+)\.(\d+)/)
        if (versionMatch) {
          const major = parseInt(versionMatch[1])
          const minor = parseInt(versionMatch[2])
          if (major >= 3 && minor >= 9) {
            // 获取完整路径
            const { stdout: pathOut } = await execAsync(
              process.platform === 'win32'
                ? `where ${cmd.split(' ')[0]}`
                : `which ${cmd}`,
              { timeout: 5000 }
            )
            const pythonPath = pathOut.trim().split('\n')[0].trim()
            this.cachedPythonPath = pythonPath
            this.cachedBackendMode = 'system-python'
            this.addLog(`[检测] 找到系统 Python: ${pythonPath} (${major}.${minor})`)
            return pythonPath
          }
        }
      } catch {
        // 继续尝试下一个
      }
    }
    return null
  }

  private async validatePython(pythonPath: string): Promise<boolean> {
    try {
      const { stdout } = await execAsync(`"${pythonPath}" -c "import sys; print(sys.version_info[:2])"`, { timeout: 5000 })
      const match = stdout.match(/\((\d+),\s*(\d+)\)/)
      if (match) {
        const major = parseInt(match[1])
        const minor = parseInt(match[2])
        return major >= 3 && minor >= 9
      }
    } catch { /* ignore */ }
    return false
  }

  private getBackendSourceDir(): string {
    // 源码模式：从 electron 目录向上找到 desktop/python-backend
    const electronDir = __dirname
    return join(electronDir, '..', 'python-backend')
  }

  private detectDllLoadFailure(): boolean {
    // Windows: 检查最近的日志中是否有 DLL 加载失败
    if (process.platform !== 'win32') return false
    const recentLogs = this.lastStderrLines.join('\n')
    return recentLogs.includes('DLL') || recentLogs.includes('0xc000007b')
  }

  // ─── 依赖安装 ───
  private async installDependencies(pythonPath: string): Promise<boolean> {
    this.addLog('[依赖] 正在安装 Python 依赖...')
    try {
      const sourceDir = this.getBackendSourceDir()
      const requirementsPath = join(sourceDir, 'requirements.txt')

      if (!existsSync(requirementsPath)) {
        this.addLog('[依赖] requirements.txt 不存在，跳过')
        return true
      }

      await execAsync(
        `"${pythonPath}" -m pip install -r "${requirementsPath}" --quiet`,
        { timeout: 120000, cwd: sourceDir }
      )
      this.depsInstalled = true
      this.addLog('[依赖] ✅ 依赖安装完成')
      return true
    } catch (e: any) {
      this.addLog(`[依赖] ❌ 依赖安装失败: ${e.message}`)
      return false
    }
  }

  // ─── VC++ Runtime (Windows) ───
  private async ensureVCppRuntime(): Promise<void> {
    if (process.platform !== 'win32') return
    try {
      const sourceDir = this.getBackendSourceDir()
      const vcredistPath = join(sourceDir, 'buildResources', 'vcredist', 'vc_redist.x64.exe')
      if (existsSync(vcredistPath)) {
        this.addLog('[Windows] 安装 VC++ Runtime...')
        await execAsync(`"${vcredistPath}" /install /quiet /norestart`, { timeout: 60000 })
        this.addLog('[Windows] VC++ Runtime 安装完成')
      }
    } catch (e: any) {
      this.addLog(`[Windows] VC++ Runtime 安装失败（可忽略）: ${e.message}`)
    }
  }

  // ─── 启动后端（带 fallback） ───
  async start(): Promise<void> {
    if (this.process) {
      this.addLog('[管理器] Python 后端已在运行中')
      return
    }

    // 防止并发操作
    if (this.operationLock) {
      this.addLog('[管理器] 操作正在进行中，请稍后重试')
      return
    }
    this.operationLock = true

    try {
      this.destroyed = false
      this.consecutiveHealthFailures = 0
      this.updateStatus('starting')
      this.addLog('[管理器] 正在启动 Python 后端...')

      // ── P1: 端口碰撞检测，自动递增 ──
      const originalPort = this.options.port
      this.options.port = await this.findAvailablePort(this.options.port)
      if (this.options.port !== originalPort) {
        this.addLog(`[端口] 原端口 ${originalPort} 被占用，自动切换到 ${this.options.port}`)
      }

      // 检测启动模式
      const detection = await this.detectBackendMode()

      if (detection.mode === 'none') {
        const errorMsg = '无法启动后端：未找到 PyInstaller 二进制，也未找到系统 Python (>= 3.9)。请安装 Python 3.9+ 后重试。'
        this.addLog(`[错误] ${errorMsg}`)
        this.state.lastError = errorMsg
        this.updateStatus('error')
        return
      }

      // ── 策略1: 尝试 sidecar ──
      if (detection.mode === 'sidecar') {
        // Windows: 确保 VC++ Runtime 已安装（sidecar DLL 依赖）
        if (process.platform === 'win32') {
          await this.ensureVCppRuntime()
        }
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
        if (this.detectDllLoadFailure()) {
          this.addLog('[启动] ❌ sidecar 因 DLL 加载失败而退出')
          this.addLog('[启动] 💡 这通常是因为缺少 Microsoft Visual C++ 2015-2022 Redistributable (x64)')
          this.addLog('[启动] 💡 请从 https://aka.ms/vs/17/release/vc_redist.x64.exe 下载并安装后重试')
          this.addLog('[启动] 🔄 当前尝试 fallback 到系统 Python...')
        } else {
          this.addLog('[启动] ❌ sidecar 失败，尝试 fallback 到系统 Python...')
        }
        this.cachedBackendMode = null
        this.cachedPythonPath = null
      }

      // ── 策略2: 系统 Python + 源码 ──
      const sysPython = await this.findSystemPython()
      const sourceDir = this.getBackendSourceDir()
      const mainPy = join(sourceDir, 'main.py')

      if (!sysPython) {
        this.addLog('[启动] ❌ 未找到系统 Python')
        this.state.lastError = '后端启动失败：sidecar 不可用且未安装 Python 3.9+'
        this.updateStatus('error')
        return
      }

      if (!(await this.validatePython(sysPython))) {
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
    } finally {
      this.operationLock = false
    }
  }

  // ─── 停止后端 ───
  async stop(): Promise<void> {
    if (!this.process) {
      this.updateStatus('stopped')
      return
    }

    // 防止并发操作
    if (this.operationLock) {
      this.addLog('[管理器] 操作正在进行中，请稍后重试')
      return
    }
    this.operationLock = true

    try {
      this.updateStatus('stopping')
      this.addLog('[管理器] 正在停止 Python 后端...')
      this.stopHealthCheck()
      this.clearRestartTimer()

      await new Promise<void>((resolve) => {
        const proc = this.process
        if (!proc) {
          this.updateStatus('stopped')
          resolve()
          return
        }

        const timeout = setTimeout(async () => {
          this.addLog('[管理器] SIGTERM 超时，强制终止进程树')
          await this.killProcessTree(proc, 'SIGKILL')
          this.process = null
          this.state.pid = null
          this.startTime = null
          this.updateStatus('stopped')
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

        // P1: 用 tree-kill 杀掉整个进程树
        this.killProcessTree(proc, 'SIGTERM').catch(() => {
          try { proc.kill('SIGTERM') } catch { /* already dead */ }
        })
      })
    } finally {
      this.operationLock = false
    }
  }

  // ─── 重启后端 ───
  async restart(): Promise<void> {
    // 防止并发操作
    if (this.operationLock) {
      this.addLog('[管理器] 操作正在进行中，请稍后重试')
      return
    }

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
        let data = ''
        response.on('data', (chunk) => { data += chunk })
        response.on('end', () => {
          clearTimeout(timeout)
          try {
            resolve(JSON.parse(data))
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

  private startHealthCheck(): void {
    this.stopHealthCheck()
    this.healthCheckTimer = setInterval(async () => {
      if (this.healthCheckInProgress || this.state.status !== 'running') return
      this.healthCheckInProgress = true

      try {
        const health = await this.checkHealth()
        if (health && health.status === 'ok') {
          this.consecutiveHealthFailures = 0
        } else {
          this.consecutiveHealthFailures++
          if (this.consecutiveHealthFailures >= this.maxConsecutiveHealthFailures) {
            this.addLog('[健康检查] ❌ 连续失败，触发重启')
            this.consecutiveHealthFailures = 0
            this.scheduleRestart()
          }
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
  }

  // ─── 重启调度（滑动窗口限流） ───
  private scheduleRestart(): void {
    const now = Date.now()
    // 清理过期时间戳
    this.restartTimestamps = this.restartTimestamps.filter(t => now - t < RESTART_WINDOW_MS)

    if (this.restartTimestamps.length >= this.options.maxRestarts) {
      this.addLog(`[管理器] ❌ 重启次数超限（${this.options.maxRestarts}次/${RESTART_WINDOW_MS / 60000}分钟），停止重启`)
      this.state.lastError = '重启次数超限，请手动重启'
      this.updateStatus('error')
      return
    }

    this.restartTimer = setTimeout(async () => {
      this.restartTimer = null
      await this.restart()
    }, 2000)
  }

  private clearRestartTimer(): void {
    if (this.restartTimer) {
      clearTimeout(this.restartTimer)
      this.restartTimer = null
    }
  }

  // ─── 检测后端模式 ───
  private async detectBackendMode(): Promise<{ mode: BackendMode; pythonPath: string | null }> {
    if (this.cachedBackendMode && this.cachedPythonPath) {
      return { mode: this.cachedBackendMode, pythonPath: this.cachedPythonPath }
    }

    // 尝试 sidecar
    const sourceDir = this.getBackendSourceDir()
    const sidecarName = process.platform === 'win32' ? 'hermes-backend.exe' : 'hermes-backend'
    const sidecarPath = join(sourceDir, '..', 'dist-backend', sidecarName)

    if (existsSync(sidecarPath)) {
      this.cachedBackendMode = 'sidecar'
      this.cachedPythonPath = sidecarPath
      return { mode: 'sidecar', pythonPath: sidecarPath }
    }

    // 尝试系统 Python
    const sysPython = await this.findSystemPython()
    if (sysPython) {
      return { mode: 'system-python', pythonPath: sysPython }
    }

    return { mode: 'none', pythonPath: null }
  }

  // ─── 尝试启动进程 ───
  private async tryStart(
    pythonPath: string,
    scriptPath: string | null,
    mode: BackendMode
  ): Promise<boolean> {
    return new Promise((resolve) => {
      try {
        const args = mode === 'sidecar'
          ? []
          : [scriptPath!, '--port', String(this.options.port), '--host', this.options.host]

        const env = buildSafeEnv({
          HERMES_PORT: String(this.options.port),
          HERMES_HOST: this.options.host,
        })

        const proc = spawn(pythonPath, args, {
          env,
          stdio: ['ignore', 'pipe', 'pipe'],
          detached: false,
        })

        this.process = proc
        this.startTime = Date.now()
        this.state.pid = proc.pid || null
        this.lineBuffer = ''
        this.lastStderrLines = []

        // 收集 stdout
        proc.stdout?.on('data', (data: Buffer) => {
          const text = data.toString()
          this.lineBuffer += text
          const lines = this.lineBuffer.split('\n')
          this.lineBuffer = lines.pop() || ''
          for (const line of lines) {
            if (line.trim()) this.addLog(`[后端] ${line}`)
          }
        })

        // 收集 stderr
        proc.stderr?.on('data', (data: Buffer) => {
          const text = data.toString()
          const lines = text.split('\n')
          for (const line of lines) {
            if (line.trim()) {
              this.addLog(`[后端 STDERR] ${line}`)
              this.lastStderrLines.push(line)
              if (this.lastStderrLines.length > 20) {
                this.lastStderrLines.shift()
              }
            }
          }
        })

        proc.on('error', (err) => {
          this.addLog(`[管理器] 进程错误: ${err.message}`)
          this.process = null
          this.state.pid = null
          this.updateStatus('error')
          resolve(false)
        })

        proc.on('exit', (code, signal) => {
          this.addLog(`[管理器] 进程退出: code=${code}, signal=${signal}`)
          if (this.state.status === 'running' || this.state.status === 'starting') {
            this.process = null
            this.state.pid = null
            this.updateStatus('error')
            this.state.lastError = `进程异常退出 (code=${code})`
          }
        })

        // 等待一小段时间，检查进程是否立即退出
        setTimeout(() => {
          if (this.process && !this.process.killed) {
            this.addLog(`[管理器] 进程已启动 (PID: ${proc.pid})`)
            resolve(true)
          } else {
            resolve(false)
          }
        }, 1500)
      } catch (err: any) {
        this.addLog(`[管理器] 启动失败: ${err.message}`)
        resolve(false)
      }
    })
  }

  // ─── 销毁 ───
  async destroy(): Promise<void> {
    this.destroyed = true
    this.stopHealthCheck()
    this.clearRestartTimer()
    if (this.process) {
      await this.killProcessTree(this.process, 'SIGKILL')
      this.process = null
    }
  }
}
