/**
 * Hermes Desktop - Root component
 * Layout: collapsible Sidebar with navigation + content area
 */
import React, { useEffect, useState } from 'react';
import { Sidebar } from './components/sidebar/Sidebar';
import { ChatView } from './components/chat/ChatView';
import { SettingsPanel } from './components/settings/SettingsPanel';
import { MemoryPanel } from './components/memory/MemoryPanel';
import { ToolsPanel } from './components/tools/ToolsPanel';
import { ModelsPanel } from './components/models/ModelsPanel';
import { ProvidersPanel } from './components/providers/ProvidersPanel';
import { SchedulesPanel } from './components/schedules/SchedulesPanel';
import { GatewayPanel } from './components/gateway/GatewayPanel';
import { KanbanPanel } from './components/kanban/KanbanPanel';
import { DiscoverPanel } from './components/discover/DiscoverPanel';
import { OfficePanel } from './components/office/OfficePanel';
import { SessionsPanel } from './components/sessions/SessionsPanel';
import { EmailPanel } from './components/email/EmailPanel';
import { SkillsPanel } from './components/skills/SkillsPanel';
import { useAppStore } from './stores/app-store';
import { useSettingsStore } from './stores/settingsStore';
import { useSystemStore } from './stores/systemStore';

type View = 'chat' | 'sessions' | 'discover' | 'office' | 'kanban' | 'models' | 'providers' | 'memory' | 'tools' | 'schedules' | 'gateway' | 'email' | 'skills' | 'settings';

export default function App() {
  const { sidebarCollapsed } = useSystemStore();
  const [currentView, setCurrentView] = useState<View>('chat');

  // Initialize IPC listeners, API client, and health polling on mount
  useEffect(() => {
    try {
      useSettingsStore.getState().initApiClient();
    } catch (e) {
      console.error('[App] initApiClient failed:', e);
    }

    const cleanup = useAppStore.getState().initIpcListeners();
    useSystemStore.getState().startHealthPolling();

    return () => {
      cleanup?.();
      useSystemStore.getState().stopHealthPolling();
    };
  }, []);

  const renderContent = () => {
    switch (currentView) {
      case 'chat':
        return <ChatView />;
      case 'sessions':
        return <SessionsPanel />;
      case 'discover':
        return <DiscoverPanel />;
      case 'office':
        return <OfficePanel />;
      case 'kanban':
        return <KanbanPanel />;
      case 'models':
        return <ModelsPanel />;
      case 'providers':
        return <ProvidersPanel />;
      case 'memory':
        return <MemoryPanel />;
      case 'tools':
        return <ToolsPanel />;
      case 'schedules':
        return <SchedulesPanel />;
      case 'gateway':
        return <GatewayPanel />;
      case 'email':
        return <EmailPanel />;
      case 'skills':
        return <SkillsPanel />;
      case 'settings':
        return <SettingsPanel />;
      default:
        return <ChatView />;
    }
  };

  return (
    <div className="flex h-screen overflow-hidden text-text-primary" style={{ background: 'var(--bg-primary)' }}>
      {/* Sidebar - collapsible with navigation */}
      <aside
        className={`flex-shrink-0 h-full transition-all duration-300 ease-in-out ${
          sidebarCollapsed ? 'w-16' : 'w-64'
        }`}
      >
        <Sidebar currentView={currentView} onViewChange={setCurrentView} />
      </aside>

      {/* Main content area */}
      <main className="flex-1 flex flex-col min-w-0">
        {renderContent()}
      </main>
    </div>
  );
}
