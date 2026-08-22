import React, { useEffect, useRef } from 'react';
import { useChatStore } from '../../stores/chatStore';
import { Plus, X, MessageSquare } from 'lucide-react';

export function SessionTabBar() {
  const { sessions, currentSessionId, switchSession, createSession, deleteSession } = useChatStore();
  const tabsContainerRef = useRef<HTMLDivElement>(null);

  // 快捷键支持: Ctrl+T 新建标签, Ctrl+W 关闭当前标签
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      // Ctrl+T or Cmd+T: 新建会话
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 't') {
        e.preventDefault();
        createSession();
      }
      // Ctrl+W or Cmd+W (仅在有会话且焦点非输入框时): 关闭当前会话
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'w' && sessions.length > 1 && currentSessionId) {
        // 如果当前聚焦在 input/textarea 则不劫持，避免影响输入
        const target = e.target as HTMLElement;
        if (target && (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA')) return;
        e.preventDefault();
        deleteSession(currentSessionId);
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [createSession, deleteSession, sessions.length, currentSessionId]);

  return (
    <div className="flex items-center h-8 bg-[var(--bg-primary)] border-b border-[var(--hermes-border)] px-1.5 gap-1 overflow-x-auto select-none no-scrollbar app-no-drag">
      <div ref={tabsContainerRef} className="flex items-center gap-1 flex-1 overflow-x-auto no-scrollbar">
        {sessions.slice(0, 12).map((s) => {
          const isActive = s.id === currentSessionId;
          return (
            <div
              key={s.id}
              onClick={() => switchSession(s.id)}
              className={`group relative flex items-center gap-1.5 px-3 py-1 text-xs rounded-md cursor-pointer max-w-[160px] min-w-[100px] transition-all ${
                isActive
                  ? 'bg-[var(--bg-secondary)] text-text-primary border border-[var(--hermes-border)] shadow-xs font-medium'
                  : 'text-text-muted hover:bg-[var(--bg-secondary)]/60 hover:text-text-secondary border border-transparent'
              }`}
            >
              <MessageSquare size={12} className={isActive ? 'text-[var(--hermes-accent)]' : 'opacity-60'} />
              <span className="truncate flex-1 text-[11px]">{s.title || '新会话'}</span>

              {/* Close Tab button (仅在有多于1个会话时显示) */}
              {sessions.length > 1 && (
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    deleteSession(s.id);
                  }}
                  className="opacity-0 group-hover:opacity-100 p-0.5 rounded hover:bg-[var(--bg-tertiary)] hover:text-rose-500 transition-opacity"
                  title="关闭会话 (Ctrl+W)"
                >
                  <X size={11} />
                </button>
              )}
            </div>
          );
        })}
      </div>

      {/* New Tab Button */}
      <button
        onClick={() => createSession()}
        className="p-1 text-text-muted hover:text-text-primary hover:bg-[var(--bg-secondary)] rounded-md transition-colors flex-shrink-0"
        title="新建会话标签 (Ctrl+T)"
      >
        <Plus size={14} />
      </button>
    </div>
  );
}

export default SessionTabBar;
