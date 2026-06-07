/**
 * Custom hook for IPC communication with the Electron main process.
 * Falls back to HTTP API when not running in Electron.
 *
 * Uses window.api (exposed by preload via contextBridge).
 */

import { useEffect, useCallback, useRef } from 'react';
import type { ElectronAPI, MainProcessSettings } from '../types/electron-api';

type ApiType = ElectronAPI;

const isElectron = (): boolean => {
  return typeof window !== 'undefined' && Boolean(window.api);
};

function getApi(): ApiType | null {
  if (!isElectron()) return null;
  return window.api ?? null;
}

/**
 * Hook for invoking IPC methods (request-response pattern).
 * Maps to window.api.* methods exposed by the preload script.
 */
export function useIpcInvoke() {
  const invoke = useCallback(async <T = unknown>(
    channel: string,
    ...args: unknown[]
  ): Promise<T | null> => {
    const api = getApi();
    if (!api) {
      console.debug('[IPC] invoke (no-op in browser):', channel, args);
      return null;
    }

    // Route to the correct window.api method based on channel
    switch (channel) {
      // Window control
      case 'window:minimize':
        return api.window.minimize() as Promise<T>;
      case 'window:maximize':
        return api.window.maximize() as Promise<T>;
      case 'window:close':
        return api.window.close() as Promise<T>;
      case 'window:restore':
        return api.window.restore() as Promise<T>;
      case 'window:is-maximized':
        return api.window.isMaximized() as Promise<T>;

      // Python backend
      case 'python:start':
        return api.python.start() as Promise<T>;
      case 'python:stop':
        return api.python.stop() as Promise<T>;
      case 'python:restart':
        return api.python.restart() as Promise<T>;
      case 'python:status':
        return api.python.getStatus() as Promise<T>;
      case 'python:health':
        return api.python.checkHealth() as Promise<T>;
      case 'python:logs':
        return api.python.getLogs() as Promise<T>;

      // App info
      case 'app:version':
        return api.app.getVersion() as Promise<T>;
      case 'app:quit':
        return api.app.quit() as Promise<T>;
      case 'app:restart':
        return api.app.restart() as Promise<T>;

      // Updater
      case 'update:check':
        return api.updater.checkForUpdates() as Promise<T>;
      case 'update:download':
        return api.updater.downloadUpdate() as Promise<T>;
      case 'update:install':
        return api.updater.installUpdate() as Promise<T>;

      // Settings
      case 'settings:get':
        return api.settings.get(args[0] as keyof MainProcessSettings) as Promise<T>;
      case 'settings:set':
        return api.settings.set(
          args[0] as keyof MainProcessSettings,
          args[1] as never
        ) as Promise<T>;
      case 'settings:get-all':
        return api.settings.getAll() as Promise<T>;

      default:
        console.warn('[IPC] Unknown channel:', channel);
        return null;
    }
  }, []);

  return invoke;
}

/**
 * Hook for listening to events from the main process.
 * Uses the on* listener methods on window.api.
 */
export function useIpcReceive(channel: string, handler: (data: unknown) => void) {
  const handlerRef = useRef(handler);
  handlerRef.current = handler;

  useEffect(() => {
    const api = getApi();
    if (!api) return;

    let cleanup: (() => void) | undefined;

    switch (channel) {
      case 'python:status-change':
        cleanup = api.python.onStatusChange((state) => handlerRef.current(state));
        break;
      case 'python:log-stream':
        cleanup = api.python.onLogStream((log) => handlerRef.current(log));
        break;
      case 'window:maximized':
        cleanup = api.window.onMaximizedChange((isMaximized) =>
          handlerRef.current({ isMaximized })
        );
        break;
      case 'update:available':
        cleanup = api.updater.onUpdateAvailable((info) => handlerRef.current(info));
        break;
      case 'update:progress':
        cleanup = api.updater.onDownloadProgress((progress) =>
          handlerRef.current(progress)
        );
        break;
      case 'update:downloaded':
        cleanup = api.updater.onUpdateDownloaded((info) => handlerRef.current(info));
        break;
      case 'update:status':
        cleanup = api.updater.onStatusChange((status) => handlerRef.current(status));
        break;
      default:
        console.warn('[IPC] Unknown listener channel:', channel);
    }

    return () => {
      if (typeof cleanup === 'function') {
        cleanup();
      }
    };
  }, [channel]);
}

/**
 * Hook for listening to backend health status via IPC.
 */
export function useBackendStatus(callback: (status: { online: boolean; version?: string }) => void) {
  const callbackRef = useRef(callback);
  callbackRef.current = callback;

  useIpcReceive('python:status-change', (data) => {
    const state = data as { status?: string };
    callbackRef.current({
      online: state.status === 'running',
      version: undefined,
    });
  });
}

/**
 * Hook for window control actions (minimize, maximize, close).
 */
export function useWindowControls() {
  const invoke = useIpcInvoke();

  const minimize = useCallback(() => invoke('window:minimize'), [invoke]);
  const maximize = useCallback(() => invoke('window:maximize'), [invoke]);
  const close = useCallback(() => invoke('window:close'), [invoke]);

  return { minimize, maximize, close, isElectron: isElectron() };
}

export default useIpcInvoke;
