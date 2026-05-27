import React, { useEffect, useRef } from 'react';
import { MessageBubble } from './MessageBubble';
import { InputBar } from './InputBar';
import { useChatStore } from '../../stores/chatStore';
import { useSystemStore } from '../../stores/systemStore';
import { Bot, PanelLeftClose, PanelLeft, AlertCircle, Settings } from 'lucide-react';

export function ChatView() {
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const scrollContainerRef = useRef<HTMLDivElement>(null);
  const { currentMessages, currentSession, isGenerating, error } = useChatStore();
  const { sidebarCollapsed, toggleSidebar, toggleSettings, isBackendOnline } = useSystemStore();

  const messages = currentMessages();
  const session = currentSession();

  // Auto-scroll to bottom on new messages (use messages.length to avoid
  // unnecessary re-renders from reference changes — fixes #21)
  const messageCount = messages.length;
  useEffect(() => {
    const container = scrollContainerRef.current;
    if (!container) return;

    // Check if user is near bottom (within 100px)
    const isNearBottom =
      container.scrollHeight - container.scrollTop - container.clientHeight < 100;

    if (isNearBottom) {
      messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    }
  }, [messageCount]);

  // Also scroll when streaming content changes (last message is streaming)
  const lastMessage = messages[messages.length - 1];
  const isStreaming = lastMessage?.isStreaming ?? false;
  const lastContent = lastMessage?.content;
  useEffect(() => {
    if (isStreaming) {
      const container = scrollContainerRef.current;
      if (!container) return;
      const isNearBottom =
        container.scrollHeight - container.scrollTop - container.clientHeight < 100;
      if (isNearBottom) {
        const rafId = requestAnimationFrame(() => {
          messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
        });
        return () => cancelAnimationFrame(rafId);
      }
    }
  }, [isStreaming, lastContent]);

  // Scroll to bottom when switching sessions
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'instant' });
  }, [session?.id]);

  return (
    <div className="flex flex-col h-full">
      {/* Top bar */}
      <header className="flex items-center justify-between px-4 py-2.5 border-b border-[var(--border)] bg-[var(--bg-secondary)] flex-shrink-0">
        <div className="flex items-center gap-2">
          {/* Toggle sidebar */}
          <button
            onClick={toggleSidebar}
            className="p-1.5 rounded-lg text-[var(--text-muted)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-tertiary)] transition-colors"
            title={sidebarCollapsed ? '展开侧边栏' : '收起侧边栏'}
          >
            {sidebarCollapsed ? <PanelLeft size={18} /> : <PanelLeftClose size={18} />}
          </button>

          <h1 className="text-sm font-medium text-[var(--text-primary)] truncate max-w-[300px]">
            {session?.title || 'Hermes Desktop'}
          </h1>
        </div>

        <div className="flex items-center gap-2">
          {/* Backend status indicator */}
          <div className="flex items-center gap-1.5 text-xs">
            <div
              className={`w-2 h-2 rounded-full ${
                isBackendOnline ? 'bg-[var(--success)]' : 'bg-[var(--error)]'
              }`}
            />
            <span className="text-[var(--text-muted)]">
              {isBackendOnline ? '已连接' : '未连接'}
            </span>
          </div>

          {/* Settings */}
          <button
            onClick={toggleSettings}
            className="p-1.5 rounded-lg text-[var(--text-muted)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-tertiary)] transition-colors"
            title="设置"
          >
            <Settings size={18} />
          </button>
        </div>
      </header>

      {/* Messages area */}
      <div
        ref={scrollContainerRef}
        className="flex-1 overflow-y-auto"
      >
        {messages.length === 0 ? (
          /* Empty state */
          <div className="flex flex-col items-center justify-center h-full text-center px-4">
            <div className="w-16 h-16 rounded-2xl bg-[var(--bg-tertiary)] flex items-center justify-center mb-4">
              <Bot size={32} className="text-[var(--accent)]" />
            </div>
            <h2 className="text-xl font-semibold text-[var(--text-primary)] mb-2">
              Hermes Desktop
            </h2>
            <p className="text-sm text-[var(--text-muted)] max-w-md">
              智能 AI 助手，支持代码生成、文件操作、网页搜索等多种工具。
              输入消息开始对话。
            </p>

            {/* Quick actions */}
            <div className="grid grid-cols-2 gap-3 mt-8 max-w-lg w-full">
              {[
                { icon: '💻', text: '帮我写一个 Python 脚本' },
                { icon: '🔍', text: '搜索最新技术资讯' },
                { icon: '📁', text: '整理项目文件结构' },
                { icon: '🐛', text: '分析并修复代码问题' },
              ].map((item, i) => (
                <button
                  key={i}
                  onClick={() => {
                    const store = useChatStore.getState();
                    if (!store.currentSessionId) store.createSession();
                    store.sendMessage(item.text);
                  }}
                  className="flex items-center gap-3 p-3 rounded-xl border border-[var(--border)] bg-[var(--bg-secondary)] hover:bg-[var(--bg-tertiary)] transition-colors text-left"
                >
                  <span className="text-lg">{item.icon}</span>
                  <span className="text-sm text-[var(--text-secondary)]">{item.text}</span>
                </button>
              ))}
            </div>
          </div>
        ) : (
          /* Message list */
          <div className="max-w-3xl mx-auto py-4">
            {messages.map((message) => (
              <MessageBubble key={message.id} message={message} />
            ))}

            {/* Generation indicator: show only when generating and no streaming assistant message yet */}
            {isGenerating && (!lastMessage || lastMessage.role !== 'assistant' || !lastMessage.isStreaming) && (
              <div className="flex gap-3 px-4 py-3 fade-in">
                <div className="w-8 h-8 rounded-full bg-[var(--bg-tertiary)] flex items-center justify-center">
                  <Bot size={16} className="text-[var(--text-secondary)]" />
                </div>
                <div className="flex items-center gap-1.5 px-4 py-3">
                  <div className="w-2 h-2 rounded-full bg-[var(--accent)] pulse-dot" />
                  <div className="w-2 h-2 rounded-full bg-[var(--accent)] pulse-dot" />
                  <div className="w-2 h-2 rounded-full bg-[var(--accent)] pulse-dot" />
                </div>
              </div>
            )}

            <div ref={messagesEndRef} />
          </div>
        )}
      </div>

      {/* Error banner */}
      {error && (
        <div className="flex items-center gap-2 px-4 py-2 bg-[var(--error)]/10 border-t border-[var(--error)]/30 text-sm text-[var(--error)]">
          <AlertCircle size={14} />
          <span className="flex-1">{error}</span>
          <button
            onClick={() => useChatStore.getState().clearError()}
            className="text-xs hover:underline"
          >
            关闭
          </button>
        </div>
      )}

      {/* Input */}
      <InputBar />
    </div>
  );
}

export default ChatView;
