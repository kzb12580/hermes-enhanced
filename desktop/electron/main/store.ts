/**
 * Hermes Desktop - electron-store 持久化设置管理
 */
import Store from 'electron-store'
import { AppSettings, DEFAULT_SETTINGS } from '../shared/types'

class SettingsStore {
  private store: Store<AppSettings>

  constructor() {
    this.store = new Store<AppSettings>({
      name: 'hermes-settings',
      defaults: DEFAULT_SETTINGS,
      schema: {
        theme: {
          type: 'string',
          enum: ['light', 'dark', 'system'],
          default: 'system'
        },
        language: {
          type: 'string',
          enum: ['zh-CN', 'en-US'],
          default: 'zh-CN'
        },
        startMinimized: {
          type: 'boolean',
          default: false
        },
        closeToTray: {
          type: 'boolean',
          default: true
        },
        autoStart: {
          type: 'boolean',
          default: false
        },
        pythonPort: {
          type: 'number',
          default: 9876,
          minimum: 1024,
          maximum: 65535
        },
        pythonAutoStart: {
          type: 'boolean',
          default: true
        },
        pythonMaxRestarts: {
          type: 'number',
          default: 3,
          minimum: 0,
          maximum: 10
        },
        logLevel: {
          type: 'string',
          enum: ['debug', 'info', 'warn', 'error'],
          default: 'info'
        }
      }
    })
  }

  /** 获取单个设置项 */
  get<K extends keyof AppSettings>(key: K): AppSettings[K] {
    return this.store.get(key)
  }

  /** 设置单个设置项 */
  set<K extends keyof AppSettings>(key: K, value: AppSettings[K]): void {
    this.store.set(key, value)
  }

  /** 获取所有设置 */
  getAll(): AppSettings {
    return this.store.store
  }

  /** 重置所有设置为默认值 */
  reset(): void {
    this.store.store = DEFAULT_SETTINGS
  }

  /** 重置单个设置为默认值 */
  resetKey<K extends keyof AppSettings>(key: K): void {
    this.store.set(key, DEFAULT_SETTINGS[key])
  }

  /** 监听设置变化 */
  onChange<K extends keyof AppSettings>(
    key: K,
    callback: (newValue: AppSettings[K], oldValue: AppSettings[K]) => void
  ): () => void {
    return this.store.onDidChange(key, callback) ?? (() => {})
  }
}

// 单例导出
export const settingsStore = new SettingsStore()
