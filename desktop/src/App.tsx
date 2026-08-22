/**
 * Hermes Desktop - Root component
 * Layout: collapsible Sidebar with navigation + content area
 */
import React, { useEffect, useState } from 'react';
import { Sidebar, type View } from './components/sidebar/Sidebar';
import { ChatView } from './components/chat/ChatView';
import { SettingsPanel } from './components/settings/SettingsPanel';
import { MemoryPanel } from './components/memory/MemoryPanel';
import { ModelsPanel } from './components/models/ModelsPanel';
import { ToolsPanel } from './components/tools/ToolsPanel';
import { SessionsPanel } from './components/sessions/SessionsPanel';
import { EmailPanel } from './components/email/EmailPanel';
import { SkillsPanel } from './components/skills/SkillsPanel';
import { useAppStore } from './stores/app-store';
import { useSettingsStore } from './stores/settingsStore';
import { useSystemStore } from './stores/systemStore';
import { useChatStore } from './stores/chatStore';

export default function App() {
  const { sidebarCollapsed } = useSystemStore();
  const [currentView, setCurrentView] = useState<View>('chat');
  const { activeSkills, toggleActiveSkill } = useChatStore();

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
      case 'models':
        return <ModelsPanel />;
      case 'memory':
        return <MemoryPanel />;
      case 'tools':
        return <ToolsPanel />;
      case 'email':
        return <EmailPanel />;
      case 'skills':
        return <SkillsPanel open={true} onClose={() => {}} activeSkills={activeSkills} onToggleActive={toggleActiveSkill} />;
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
