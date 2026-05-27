/**
 * Hermes Desktop - Root component
 * Layout: collapsible Sidebar + ChatView, Settings as modal overlay.
 */
import React, { useEffect } from 'react';
import { Sidebar } from './components/sidebar/Sidebar';
import { ChatView } from './components/chat/ChatView';
import { SettingsPanel } from './components/settings/SettingsPanel';
import { useAppStore } from './stores/app-store';
import { useSettingsStore } from './stores/settingsStore';
import { useSystemStore } from './stores/systemStore';

export default function App() {
  const { sidebarCollapsed, settingsOpen } = useSystemStore();

  // Initialize IPC listeners, API client, and health polling on mount
  useEffect(() => {
    // Initialize the API client from persisted settings
    useSettingsStore.getState().initApiClient();

    // Wire up Electron IPC event listeners
    const cleanup = useAppStore.getState().initIpcListeners();

    // Start backend health polling
    useSystemStore.getState().startHealthPolling();

    return () => {
      cleanup?.();
      useSystemStore.getState().stopHealthPolling();
    };
  }, []);

  return (
    <div className="flex h-screen overflow-hidden bg-[var(--bg-primary)] text-[var(--text-primary)]">
      {/* Sidebar - collapsible */}
      <aside
        className={`flex-shrink-0 h-full transition-all duration-300 ease-in-out ${
          sidebarCollapsed ? 'w-0 overflow-hidden' : 'w-64'
        }`}
      >
        <Sidebar />
      </aside>

      {/* Main chat area */}
      <main className="flex-1 flex flex-col min-w-0">
        <ChatView />
      </main>

      {/* Settings modal overlay */}
      {settingsOpen && <SettingsPanel />}
    </div>
  );
}
