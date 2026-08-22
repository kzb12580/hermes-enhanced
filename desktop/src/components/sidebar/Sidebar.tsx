import React, { useState } from 'react';
import { SessionList } from './SessionList';
import { useChatStore } from '../../stores/chatStore';
import { useSystemStore } from '../../stores/systemStore';
import {
  Plus,
  Settings,
  MessageSquare,
  Clock,
  Compass,
  Building,
  Layers,
  KeyRound,
  Brain,
  Wrench,
  Timer,
  Kanban,
  Signal,
  Mail,
  Zap,
  ChevronDown,
  ChevronRight,
} from 'lucide-react';

type View = 'chat' | 'sessions' | 'email' | 'skills' | 'models' | 'memory' | 'tools' | 'settings';

interface NavItem {
  view: View;
  icon: React.ElementType;
  label: string;
  group: 'main' | 'data' | 'system';
}

const NAV_ITEMS: NavItem[] = [
  // 主要功能
  { view: 'chat', icon: MessageSquare, label: '对话', group: 'main' },
  { view: 'sessions', icon: Clock, label: '历史会话', group: 'main' },
  { view: 'email', icon: Mail, label: '邮件', group: 'main' },
  { view: 'skills', icon: Zap, label: '技能', group: 'main' },
  // 数据管理
  { view: 'models', icon: Layers, label: '模型', group: 'data' },
  { view: 'memory', icon: Brain, label: '记忆', group: 'data' },
  { view: 'tools', icon: Wrench, label: '工具', group: 'data' },
  // 系统功能
  { view: 'settings', icon: Settings, label: '设置', group: 'system' },
];

interface SidebarProps {
  currentView: View;
  onViewChange: (view: View) => void;
}

export function Sidebar({ currentView, onViewChange }: SidebarProps) {
  const { createSession, sessions } = useChatStore();
  const { sidebarCollapsed } = useSystemStore();
  const [expandedGroups, setExpandedGroups] = useState<Record<string, boolean>>({
    main: true,
    data: true,
    system: true,
  });

  const toggleGroup = (group: string) => {
    setExpandedGroups(prev => ({ ...prev, [group]: !prev[group] }));
  };

  const groupedItems = NAV_ITEMS.reduce((acc, item) => {
    if (!acc[item.group]) acc[item.group] = [];
    acc[item.group].push(item);
    return acc;
  }, {} as Record<string, NavItem[]>);

  const groupLabels: Record<string, string> = {
    main: '主要功能',
    data: '数据管理',
    system: '系统功能',
  };

  return (
    <div className={`flex flex-col h-full bg-[var(--bg-secondary)] border-r border-[var(--hermes-border)] ${sidebarCollapsed ? 'w-16' : 'w-full'}`}>
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-[var(--hermes-border)]">
        <div className="flex items-center gap-2">
          <MessageSquare size={18} className="text-[var(--hermes-accent)]" />
          {!sidebarCollapsed && (
            <h2 className="text-sm font-semibold text-text-primary">Hermes Desktop</h2>
          )}
        </div>
      </div>

      {!sidebarCollapsed && (
        <>
          {/* New chat button */}
          <div className="px-3 pt-3 pb-1">
            <button
              onClick={createSession}
              className="flex items-center justify-center gap-2 w-full px-3 py-2.5 rounded-lg border border-dashed border-[var(--hermes-border)] text-text-secondary hover:border-[var(--hermes-accent)] hover:text-[var(--hermes-accent)] hover:bg-[var(--hermes-accent-subtle)] transition-all text-sm"
            >
              <Plus size={16} />
              <span>新建对话</span>
            </button>
          </div>

          {/* Navigation groups */}
          <div className="flex-1 overflow-y-auto px-2 py-2">
            {Object.entries(groupedItems).map(([group, items]) => (
              <div key={group} className="mb-2">
                <button
                  onClick={() => toggleGroup(group)}
                  className="flex items-center gap-1 w-full px-2 py-1 text-xs font-medium text-text-muted hover:text-text-secondary transition-colors"
                >
                  {expandedGroups[group] ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
                  {groupLabels[group]}
                </button>
                {expandedGroups[group] && (
                  <div className="ml-1 space-y-0.5">
                    {items.map(({ view, icon: Icon, label }) => (
                      <button
                        key={view}
                        onClick={() => onViewChange(view)}
                        className={`flex items-center gap-2 w-full px-3 py-2 rounded-lg text-sm transition-all ${
                          currentView === view
                            ? 'bg-[var(--hermes-accent)] text-white shadow-sm'
                            : 'text-text-secondary hover:bg-[var(--bg-surface)] hover:text-text-primary'
                        }`}
                      >
                        <Icon size={16} />
                        <span>{label}</span>
                      </button>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </div>

          {/* Session list (only show when on chat view) */}
          {currentView === 'chat' && <SessionList />}
        </>
      )}

      {/* Collapsed mode - icon only */}
      {sidebarCollapsed && (
        <div className="flex-1 overflow-y-auto py-2">
          {NAV_ITEMS.map(({ view, icon: Icon, label }) => (
            <button
              key={view}
              onClick={() => onViewChange(view)}
              className={`flex items-center justify-center w-full py-3 transition-colors ${
                currentView === view
                  ? 'text-[var(--hermes-accent)] bg-[var(--hermes-accent-subtle)]'
                  : 'text-text-muted hover:text-text-primary'
              }`}
              title={label}
            >
              <Icon size={18} />
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

export default Sidebar;
