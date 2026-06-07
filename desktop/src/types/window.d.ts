/**
 * Hermes Desktop - 窗口 API 类型声明
 */
import type { ElectronAPI } from './electron-api'

declare global {
  interface Window {
    api?: ElectronAPI
  }
}
