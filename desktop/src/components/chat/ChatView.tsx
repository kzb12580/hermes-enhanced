import React, { useEffect, useRef, useCallback } from 'react';
import { MessageBubble } from './MessageBubble';
import { InputBar } from './InputBar';
import { useChatStore } from '../../stores/chatStore';
import { useSystemStore } from '../../stores/systemStore';
import { useSettingsStore } from '../../stores/settingsStore';
import { useWindowControls } from '../../hooks/useIpc';
import { Bot, PanelLeftClose, PanelLeft, AlertCircle, Settings, Minus, Square, X } from 'lucide-react';

export function ChatView() {
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const scrollContainerRef = useRef<HTMLDivElement>(null);
  const userScrolledUpRef = useRef(false);
  const lastScrollTimeRef = useRef(0);
  const { currentMessages, currentSession, isGenerating, error } = useChatStore();
  const { sidebarCollapsed, toggleSidebar, toggleSettings, isBackendOnline, setSettingsOpen } = useSystemStore();
  const { autoScroll } = useSettingsStore();
  const { minimize, maximize, close, isElectron } = useWindowControls();

  const messages = currentMessages();
  const session = currentSession();

  // Helper: scroll to bottom
  const scrollToBottom = useCallback((behavior: ScrollBehavior = 'smooth') => {
    if (behavior === 'instant') {
      // For instant scroll, use scrollTop directly (more reliable)
      const container = scrollContainerRef.current;
      if (container) {
        container.scrollTop = container.scrollHeight;
      }
    }
    messagesEndRef.current?.scrollIntoView({ behavior });
  }, []);

  // Track whether user has manually scrolled away from bottom
  useEffect(() => {
    const container = scrollContainerRef.current;
    if (!container) return;

    const handleScroll = () => {
      const isNearBottom =
        container.scrollHeight - container.scrollTop - container.clientHeight < 150;
      userScrolledUpRef.current = !isNearBottom;
    };

    container.addEventListener('scroll', handleScroll, { passive: true });
    return () => container.removeEventListener('scroll', handleScroll);
  }, []);

  // Auto-scroll to bottom on new messages (use messages.length to avoid
  // unnecessary re-renders from reference changes — fixes #21)
  const messageCount = messages.length;
  useEffect(() => {
    if (!autoScroll) return;
    if (userScrolledUpRef.current) return;

    // Use requestAnimationFrame to ensure DOM has updated
    const rafId = requestAnimationFrame(() => {
      scrollToBottom('smooth');
    });
    return () => cancelAnimationFrame(rafId);
  }, [messageCount, autoScroll, scrollToBottom]);

  // Also scroll when streaming content changes (last message is streaming)
  // Throttled to once per 100ms to avoid excessive DOM reflows
  const lastMessage = messages[messages.length - 1];
  const isStreaming = lastMessage?.isStreaming ?? false;
  const lastContent = lastMessage?.content;
  useEffect(() => {
    if (!autoScroll) return;
    if (isStreaming && !userScrolledUpRef.current) {
      const now = Date.now();
      if (now - lastScrollTimeRef.current >= 100) {
        lastScrollTimeRef.current = now;
        scrollToBottom('smooth');
      } else {
        // Schedule a trailing scroll at the throttle boundary
        const delay = 100 - (now - lastScrollTimeRef.current);
        const timer = setTimeout(() => {
          lastScrollTimeRef.current = Date.now();
          scrollToBottom('smooth');
        }, delay);
        return () => clearTimeout(timer);
      }
    }
  }, [isStreaming, lastContent, autoScroll, scrollToBottom]);

  // Scroll to bottom when switching sessions
  useEffect(() => {
    userScrolledUpRef.current = false;
    scrollToBottom('instant');
  }, [session?.id, scrollToBottom]);

  // Listen for show-about event from tray menu
  useEffect(() => {
    const api = (window as any).api;
    if (!api?.app?.onShowAbout) return;
    const cleanup = api.app.onShowAbout(() => {
      setSettingsOpen(true);
    });
    return cleanup;
  }, [setSettingsOpen]);

  return (
    <div className="flex flex-col h-full">
      {/* Top bar */}
      <header className="flex items-center justify-between px-4 py-2.5 border-b border-border bg-bg-secondary flex-shrink-0 app-drag">
        <div className="flex items-center gap-2">
          {/* Toggle sidebar */}
          <button
            onClick={toggleSidebar}
            className="p-1.5 rounded-lg text-text-muted hover:text-text-primary hover:bg-bg-tertiary transition-colors app-no-drag"
            title={sidebarCollapsed ? '展开侧边栏' : '收起侧边栏'}
          >
            {sidebarCollapsed ? <PanelLeft size={18} /> : <PanelLeftClose size={18} />}
          </button>

          <h1 className="text-sm font-medium text-text-primary truncate max-w-[300px]">
            {session?.title || 'Hermes Desktop'}
          </h1>
        </div>

        <div className="flex items-center gap-2">
          {/* Backend status indicator */}
          <div className="flex items-center gap-1.5 text-xs">
            <div
              className={`w-2 h-2 rounded-full ${
                isBackendOnline ? 'bg-success' : 'bg-error'
              }`}
            />
            <span className="text-text-muted">
              {isBackendOnline ? '已连接' : '未连接'}
            </span>
          </div>

          {/* Window control buttons (Electron only) */}
          {isElectron && (
            <div className="flex items-center gap-0.5 ml-2 app-no-drag">
              <button
                onClick={minimize}
                className="w-7 h-7 flex items-center justify-center rounded hover:bg-bg-tertiary text-text-muted hover:text-text-primary transition-colors"
                title="最小化"
              >
                <Minus size={14} />
              </button>
              <button
                onClick={maximize}
                className="w-7 h-7 flex items-center justify-center rounded hover:bg-bg-tertiary text-text-muted hover:text-text-primary transition-colors"
                title="最大化"
              >
                <Square size={12} />
              </button>
              <button
                onClick={close}
                className="w-7 h-7 flex items-center justify-center rounded hover:bg-error/80 hover:text-white text-text-muted transition-colors"
                title="关闭"
              >
                <X size={14} />
              </button>
            </div>
          )}
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
            <div className="w-16 h-16 rounded-2xl bg-bg-tertiary flex items-center justify-center mb-4">
              <Bot size={32} className="text-accent" />
            </div>
            <h2 className="text-xl font-semibold text-text-primary mb-2">
              Hermes Desktop
            </h2>
            <p className="text-sm text-text-muted max-w-md">
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
                  className="flex items-center gap-3 p-3 rounded-xl border border-border bg-bg-secondary hover:bg-bg-tertiary transition-colors text-left"
                >
                  <span className="text-lg">{item.icon}</span>
                  <span className="text-sm text-text-secondary">{item.text}</span>
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
                <div className="w-8 h-8 rounded-full bg-bg-tertiary flex items-center justify-center">
                  <Bot size={16} className="text-text-secondary" />
                </div>
                <div className="flex items-center gap-1.5 px-4 py-3">
                  <div className="w-2 h-2 rounded-full bg-accent pulse-dot" />
                  <div className="w-2 h-2 rounded-full bg-accent pulse-dot" />
                  <div className="w-2 h-2 rounded-full bg-accent pulse-dot" />
                </div>
              </div>
            )}

            <div ref={messagesEndRef} />
          </div>
        )}
      </div>

      {/* Error banner */}
      {error && (
        <div className="flex items-center gap-2 px-4 py-2 bg-error/10 border-t border-error/30 text-sm text-error">
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
