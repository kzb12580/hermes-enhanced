/**
 * Hermes Desktop - Root component
 * Layout: collapsible Sidebar + ChatView, Settings as modal overlay.
 * 首次启动自动显示设置向导
 */
import React, { useEffect, useState } from 'react';
import { Sidebar } from './components/sidebar/Sidebar';
import { ChatView } from './components/chat/ChatView';
import { SettingsPanel } from './components/settings/SettingsPanel';
import { SetupWizard } from './components/setup/SetupWizard';
import { useAppStore } from './stores/app-store';
import { useSettingsStore } from './stores/settingsStore';
import { useSystemStore } from './stores/systemStore';

function App() {
  const { sidebarCollapsed, settingsOpen } = useSystemStore();
  const [setupDone, setSetupDone] = useState<boolean | null>(null); // null = loading

  // Initialize IPC listeners, API client, and health polling on mount
  useEffect(() => {
    // Initialize the API client from persisted settings
    useSettingsStore.getState().initApiClient();

    // Wire up Electron IPC event listeners
    const cleanup = useAppStore.getState().initIpcListeners();

    // Start backend health polling
    useSystemStore.getState().startHealthPolling();

    // 检查是否已完成初始设置
    checkSetupStatus();

    return () => {
      cleanup?.();
      useSystemStore.getState().stopHealthPolling();
    };
  }, []);

  const checkSetupStatus = async () => {
    try {
      // Only skip if user has explicitly completed wizard
      const wizardCompleted = localStorage.getItem('hermes_wizard_completed');
      if (wizardCompleted === 'true') {
        setSetupDone(true);
        return;
      }
      // First time -> show wizard (model download)
      setSetupDone(false);
    } catch (e) {
      setSetupDone(false);
    }
  };

  const handleSetupComplete = () => {
    localStorage.setItem('hermes_setup_done', 'true');
    localStorage.setItem('hermes_wizard_completed', 'true');
    setSetupDone(true);
  };

  // 加载中
  if (setupDone === null) {
    return (
      <div style={{
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        height: '100vh', background: '#0f172a', color: '#9ca3af',
      }}>
        <div style={{ textAlign: 'center' }}>
          <div style={{
            width: 32, height: 32, border: '3px solid #374151',
            borderTopColor: '#3b82f6', borderRadius: '50%',
            animation: 'spin 1s linear infinite', margin: '0 auto 16px',
          }} />
          <p>正在初始化...</p>
        </div>
      </div>
    );
  }

  // 首次启动 → 设置向导
  if (!setupDone) {
    return (
      <div style={{ minHeight: '100vh', background: '#0f172a', color: '#e5e7eb' }}>
        <SetupWizard onComplete={handleSetupComplete} />
      </div>
    );
  }

  // 正常主界面
  return (
    <div className="flex h-screen overflow-hidden text-[var(--text-primary)]" style={{ background: 'linear-gradient(135deg, #e8e8e8 0%, #d0d0d0 50%, #b8b8b8 100%)' }}>
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
