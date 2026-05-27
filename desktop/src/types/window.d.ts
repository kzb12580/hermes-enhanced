/**
 * Hermes Desktop - 窗口 API 类型声明
 */
import type { API } from '../../electron/preload/index'

declare global {
  interface Window {
    api: API
  }
}
