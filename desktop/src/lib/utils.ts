import { type ClassValue, clsx } from 'clsx'
import { twMerge } from 'tailwind-merge'
import { useSettingsStore } from '../stores/settingsStore'

const DEFAULT_BACKEND_URL = 'http://127.0.0.1:9876';

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

/**
 * Get the backend URL from settings store, with fallback to default.
 * Can be used outside React components via Zustand's getState().
 */
export function getBackendUrl(): string {
  try {
    return useSettingsStore.getState().backendUrl || DEFAULT_BACKEND_URL;
  } catch {
    return DEFAULT_BACKEND_URL;
  }
}
