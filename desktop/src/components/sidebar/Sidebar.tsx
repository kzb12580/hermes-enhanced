import React from 'react';
import { SessionList } from './SessionList';
import { useChatStore } from '../../stores/chatStore';
import { useSystemStore } from '../../stores/systemStore';
import {
  Plus,
  Settings,
  MessageSquare,
} from 'lucide-react';

export function Sidebar() {
  const { createSession, sessions } = useChatStore();
  const { toggleSettings, sidebarCollapsed } = useSystemStore();

  return (
    <div className={`flex flex-col h-full bg-bg-secondary border-r border-border ${sidebarCollapsed ? 'w-16' : 'w-full'}`}>
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-border">
        <div className="flex items-center gap-2">
          <MessageSquare size={18} className="text-accent" />
          {!sidebarCollapsed && (
            <>
              <h2 className="text-sm font-semibold text-text-primary">对话</h2>
              {sessions.length > 0 && (
                <span className="text-xs text-text-muted bg-bg-tertiary px-1.5 py-0.5 rounded-full">
                  {sessions.length}
                </span>
              )}
            </>
          )}
        </div>
      </div>

      {!sidebarCollapsed && (
        <>
          {/* New chat button */}
          <div className="px-3 pt-3 pb-1">
            <button
              onClick={createSession}
              className="flex items-center justify-center gap-2 w-full px-3 py-2.5 rounded-lg border border-dashed border-border text-text-secondary hover:border-accent hover:text-accent hover:bg-accent/5 transition-all text-sm"
            >
              <Plus size={16} />
              <span>新建对话</span>
            </button>
          </div>

          {/* Session list */}
          <SessionList />
        </>
      )}

      {/* Footer */}
      <div className="border-t border-border p-3 mt-auto">
        <button
          onClick={toggleSettings}
          className={`flex items-center gap-2 w-full px-3 py-2 rounded-lg text-text-muted hover:text-text-primary hover:bg-bg-tertiary transition-colors text-sm ${sidebarCollapsed ? 'justify-center' : ''}`}
        >
          <Settings size={16} />
          {!sidebarCollapsed && <span>设置</span>}
        </button>
      </div>
    </div>
  );
}

export default Sidebar;
