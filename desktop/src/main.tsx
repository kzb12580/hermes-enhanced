/**
 * Hermes Desktop - Renderer entry point
 */
import React from 'react';
import ReactDOM from 'react-dom/client';
import './styles/globals.css';
import { ErrorBoundary } from './components/ErrorBoundary';

/**
 * 全局错误兜底：显示可见的错误信息，避免纯黑屏
 */
function showFatalError(title: string, detail: string) {
  const root = document.getElementById('root');
  if (root) {
    root.innerHTML = `
      <div style="min-height:100vh;background:#1a1a2e;color:#e0e0e0;display:flex;align-items:center;justify-content:center;font-family:system-ui,sans-serif;padding:32px">
        <div style="max-width:700px;text-align:center">
          <div style="font-size:48px;margin-bottom:16px">⚠️</div>
          <h1 style="font-size:22px;font-weight:700;color:#ff6b6b;margin-bottom:12px">${title}</h1>
          <pre style="background:#16213e;padding:16px;border-radius:8px;font-size:12px;color:#e2e8f0;text-align:left;overflow:auto;max-height:400px;white-space:pre-wrap;word-break:break-all;border:1px solid #334155">${detail}</pre>
          <button onclick="location.reload()" style="margin-top:20px;padding:10px 24px;border-radius:8px;border:none;background:#3b82f6;color:#fff;font-size:14px;cursor:pointer">重新加载</button>
          <button onclick="localStorage.clear();location.reload()" style="margin-top:20px;margin-left:8px;padding:10px 24px;border-radius:8px;border:none;background:#374151;color:#d1d5db;font-size:14px;cursor:pointer">清除数据并重置</button>
        </div>
      </div>`;
  }
}

/**
 * 延迟导入 App — 捕获模块初始化阶段的错误
 */
async function bootstrap() {
  try {
    // 延迟导入，让 globals.css 先加载
    const { default: App } = await import('./App');

    // Initialize the API client from persisted settings
    try {
      const { useSettingsStore } = await import('./stores/settingsStore');
      useSettingsStore.getState().initApiClient();
    } catch (e) {
      console.error('[main] initApiClient failed:', e);
    }

    const root = document.getElementById('root');
    if (!root) {
      showFatalError('找不到根节点', 'HTML 中缺少 #root 元素');
      return;
    }

    ReactDOM.createRoot(root).render(
      <React.StrictMode>
        <ErrorBoundary>
          <App />
        </ErrorBoundary>
      </React.StrictMode>,
    );
  } catch (err: any) {
    console.error('[main] Bootstrap failed:', err);
    showFatalError(
      '应用启动失败',
      `${err?.message || err}\n\n${err?.stack || ''}`
    );
  }
}

// 捕获未处理的 Promise 错误
window.addEventListener('unhandledrejection', (event) => {
  console.error('[main] Unhandled rejection:', event.reason);
});

// 捕获全局 JS 错误
window.addEventListener('error', (event) => {
  console.error('[main] Global error:', event.error || event.message);
});

bootstrap();
