import { create } from 'zustand';
import apiClient, { SystemStatus } from '../lib/api';

interface SystemState {
  /** Whether the Python backend is reachable */
  isBackendOnline: boolean;
  /** Backend system status info */
  status: SystemStatus | null;
  /** Last health check timestamp */
  lastChecked: number | null;
  /** Whether a health check is in progress */
  isChecking: boolean;
  /** Error message from last failed check */
  error: string | null;
  /** Sidebar collapsed state */
  sidebarCollapsed: boolean;
  /** Settings panel open state */
  settingsOpen: boolean;

  // Actions
  checkHealth: () => Promise<void>;
  setSidebarCollapsed: (collapsed: boolean) => void;
  toggleSidebar: () => void;
  setSettingsOpen: (open: boolean) => void;
  toggleSettings: () => void;
  startHealthPolling: () => void;
  stopHealthPolling: () => void;
}

let pollingInterval: ReturnType<typeof setInterval> | null = null;

export const useSystemStore = create<SystemState>((set, get) => ({
  isBackendOnline: false,
  status: null,
  lastChecked: null,
  isChecking: false,
  error: null,
  sidebarCollapsed: false,
  settingsOpen: false,

  checkHealth: async () => {
    set({ isChecking: true, error: null });
    try {
      const status = await apiClient.healthCheck();
      set({
        isBackendOnline: true,
        status,
        lastChecked: Date.now(),
        isChecking: false,
      });
    } catch (err: any) {
      set({
        isBackendOnline: false,
        status: null,
        lastChecked: Date.now(),
        isChecking: false,
        error: err.message || '无法连接到后端服务',
      });
    }
  },

  setSidebarCollapsed: (collapsed) => set({ sidebarCollapsed: collapsed }),

  toggleSidebar: () => set((s) => ({ sidebarCollapsed: !s.sidebarCollapsed })),

  setSettingsOpen: (open) => set({ settingsOpen: open }),

  toggleSettings: () => set((s) => ({ settingsOpen: !s.settingsOpen })),

  startHealthPolling: () => {
    // Clear any existing interval first (fixes HMR leak)
    if (pollingInterval) {
      clearInterval(pollingInterval);
      pollingInterval = null;
    }
    get().checkHealth();
    pollingInterval = setInterval(() => {
      get().checkHealth();
    }, 30000); // Check every 30 seconds
  },

  stopHealthPolling: () => {
    if (pollingInterval) {
      clearInterval(pollingInterval);
      pollingInterval = null;
    }
  },
}));

// Clean up polling on HMR dispose
if (import.meta.hot) {
  import.meta.hot.dispose(() => {
    if (pollingInterval) {
      clearInterval(pollingInterval);
      pollingInterval = null;
    }
  });
}

export default useSystemStore;
