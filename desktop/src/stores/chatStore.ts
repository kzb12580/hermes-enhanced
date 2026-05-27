import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import apiClient, { type ChatCompletionRequest } from '../lib/api';
import { useSettingsStore } from './settingsStore';

export interface ParsedToolCall {
  id: string;
  name: string;
  arguments: string;
  result?: string;
  status: 'pending' | 'running' | 'completed' | 'error';
}

export interface DisplayMessage {
  id: string;
  role: 'user' | 'assistant' | 'system' | 'tool';
  content: string;
  timestamp: number;
  toolCalls?: ParsedToolCall[];
  isStreaming?: boolean;
  error?: string;
}

export interface Session {
  id: string;
  title: string;
  messages: DisplayMessage[];
  createdAt: number;
  updatedAt: number;
}

interface ChatState {
  sessions: Session[];
  currentSessionId: string | null;
  isGenerating: boolean;
  isSending: boolean;
  error: string | null;

  // Derived
  currentSession: () => Session | undefined;
  currentMessages: () => DisplayMessage[];

  // Actions
  createSession: () => string;
  switchSession: (sessionId: string) => void;
  deleteSession: (sessionId: string) => void;
  renameSession: (sessionId: string, title: string) => void;
  addMessage: (message: Omit<DisplayMessage, 'id' | 'timestamp'>) => string;
  updateMessage: (messageId: string, updates: Partial<DisplayMessage>) => void;
  appendToMessage: (messageId: string, content: string) => void;
  setToolCallResult: (messageId: string, toolCallId: string, result: string) => void;
  sendMessage: (content: string) => Promise<void>;
  stopGeneration: () => void;
  clearError: () => void;
}

// Module-level abort controller (not persisted in Zustand state)
let activeAbortController: AbortController | null = null;
let idleStreamTimer: ReturnType<typeof setTimeout> | null = null;

// FIX #1: Generation counter to prevent isSending race conditions.
// Each sendMessage() call increments this; only the matching call clears isSending.
let sendGeneration = 0;

const IDLE_STREAM_TIMEOUT_MS = 60_000;

const generateId = () =>
  typeof crypto !== 'undefined' && crypto.randomUUID
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.random().toString(36).slice(2, 9)}`;

/**
 * Streaming throttle: batches token appends so React re-renders at most ~30fps.
 * Uses a simple timer-based approach for maximum compatibility.
 */
const STREAM_THROTTLE_MS = 33; // ~30fps
let pendingTokenBuffer = '';
let pendingMessageId: string | null = null;
let flushTimer: ReturnType<typeof setTimeout> | null = null;
let flushStoreRef: { appendToMessage: (id: string, content: string) => void } | null = null;

function flushPendingTokens() {
  if (pendingTokenBuffer && pendingMessageId && flushStoreRef) {
    flushStoreRef.appendToMessage(pendingMessageId, pendingTokenBuffer);
    pendingTokenBuffer = '';
  }
  flushTimer = null;
}

function scheduleTokenFlush(messageId: string, token: string, store: { appendToMessage: (id: string, content: string) => void }) {
  pendingTokenBuffer += token;
  pendingMessageId = messageId;
  flushStoreRef = store;
  if (!flushTimer) {
    flushTimer = setTimeout(flushPendingTokens, STREAM_THROTTLE_MS);
  }
}

function resetFlushState() {
  if (flushTimer) {
    clearTimeout(flushTimer);
    flushTimer = null;
  }
  pendingTokenBuffer = '';
  pendingMessageId = null;
  flushStoreRef = null;
}

export const useChatStore = create<ChatState>()(
  persist(
    (set, get) => ({
      sessions: [],
      currentSessionId: null,
      isGenerating: false,
      isSending: false,
      error: null,

      currentSession: () => {
        const { sessions, currentSessionId } = get();
        return sessions.find((s) => s.id === currentSessionId);
      },

      currentMessages: () => {
        return get().currentSession()?.messages || [];
      },

      createSession: () => {
        const id = generateId();
        const session: Session = {
          id,
          title: '新对话',
          messages: [],
          createdAt: Date.now(),
          updatedAt: Date.now(),
        };
        set((s) => ({
          sessions: [session, ...s.sessions],
          currentSessionId: id,
        }));
        return id;
      },

      switchSession: (sessionId) => {
        // FIX #2: Validate that the session exists before switching
        const session = get().sessions.find((s) => s.id === sessionId);
        if (!session) {
          console.warn(`[chatStore] switchSession: session "${sessionId}" not found`);
          return;
        }
        // Don't reset isGenerating — generation may still be running for the old session
        set({ currentSessionId: sessionId, error: null });
      },

      deleteSession: (sessionId) => {
        // Stop generation if deleting the active session
        const state = get();
        if (state.isGenerating && state.currentSessionId === sessionId) {
          state.stopGeneration();
        }
        set((s) => {
          const sessions = s.sessions.filter((ses) => ses.id !== sessionId);
          const currentSessionId =
            s.currentSessionId === sessionId
              ? sessions[0]?.id || null
              : s.currentSessionId;
          return { sessions, currentSessionId };
        });
      },

      renameSession: (sessionId, title) => {
        set((s) => ({
          sessions: s.sessions.map((ses) =>
            ses.id === sessionId ? { ...ses, title, updatedAt: Date.now() } : ses
          ),
        }));
      },

      addMessage: (message) => {
        const id = generateId();
        const fullMessage: DisplayMessage = {
          ...message,
          id,
          timestamp: Date.now(),
        };
        set((s) => ({
          sessions: s.sessions.map((ses) =>
            ses.id === s.currentSessionId
              ? {
                  ...ses,
                  messages: [...ses.messages, fullMessage],
                  updatedAt: Date.now(),
                }
              : ses
          ),
        }));
        return id;
      },

      updateMessage: (messageId, updates) => {
        set((s) => ({
          sessions: s.sessions.map((ses) =>
            ses.id === s.currentSessionId
              ? {
                  ...ses,
                  messages: ses.messages.map((msg) =>
                    msg.id === messageId ? { ...msg, ...updates } : msg
                  ),
                }
              : ses
          ),
        }));
      },

      appendToMessage: (messageId, content) => {
        set((s) => ({
          sessions: s.sessions.map((ses) =>
            ses.id === s.currentSessionId
              ? {
                  ...ses,
                  messages: ses.messages.map((msg) =>
                    msg.id === messageId
                      ? { ...msg, content: msg.content + content }
                      : msg
                  ),
                }
              : ses
          ),
        }));
      },

      setToolCallResult: (messageId, toolCallId, result) => {
        set((s) => ({
          sessions: s.sessions.map((ses) =>
            ses.id === s.currentSessionId
              ? {
                  ...ses,
                  messages: ses.messages.map((msg) =>
                    msg.id === messageId
                      ? {
                          ...msg,
                          toolCalls: msg.toolCalls?.map((tc) =>
                            tc.id === toolCallId
                              ? { ...tc, result, status: 'completed' as const }
                              : tc
                          ),
                        }
                      : msg
                  ),
                }
              : ses
          ),
        }));
      },

      sendMessage: async (content) => {
        const state = get();

        // Guard against concurrent sends
        if (state.isSending) {
          return;
        }

        let sessionId = state.currentSessionId;

        // Auto-create session if none
        if (!sessionId) {
          sessionId = get().createSession();
        }

        // Abort any previous in-flight request
        if (activeAbortController) {
          activeAbortController.abort();
        }
        resetFlushState();

        // FIX #1: Increment generation counter and capture it
        const myGeneration = ++sendGeneration;

        set({ isSending: true });

        // Add user message
        get().addMessage({ role: 'user', content });

        const settings = useSettingsStore.getState();

        // Add placeholder assistant message
        const assistantMsgId = generateId();
        const assistantMsg: DisplayMessage = {
          id: assistantMsgId,
          role: 'assistant',
          content: '',
          timestamp: Date.now(),
          isStreaming: true,
        };

        set((s) => ({
          isGenerating: true,
          error: null,
          sessions: s.sessions.map((ses) =>
            ses.id === sessionId
              ? { ...ses, messages: [...ses.messages, assistantMsg], updatedAt: Date.now() }
              : ses
          ),
        }));

        const controller = new AbortController();
        activeAbortController = controller;

        // Idle-stream timeout: abort if no token received for 60s
        const resetIdleTimer = () => {
          if (idleStreamTimer) clearTimeout(idleStreamTimer);
          idleStreamTimer = setTimeout(() => {
            console.warn('[chatStore] Idle stream timeout (60s), aborting');
            controller.abort();
          }, IDLE_STREAM_TIMEOUT_MS);
        };
        resetIdleTimer();

        try {
          // Find current provider to get base_url and api_key
        const currentProvider = settings.providers.find(
          (p) => p.id === settings.currentProvider
        );

        const stream = apiClient.chatCompletionStream(
            {
              content,
              model: settings.currentModel,
              session_id: sessionId ?? undefined,
              base_url: currentProvider?.baseUrl,
              api_key: currentProvider?.apiKey,
              system_prompt: settings.systemPrompt || undefined,
              thinking_mode: settings.thinkingMode,
              thinking_budget: settings.thinkingMode !== 'off' ? settings.thinkingBudget : undefined,
            },
            controller.signal
          );

          for await (const token of stream) {
            resetIdleTimer();
            // Handle tool call/result events
            if (token.startsWith('[TOOL_CALL]')) {
              try {
                const tc = JSON.parse(token.slice(12));
                const toolLabel = `\n\n🔧 **Calling tool: ${tc.name}**\n\`\`\`json\n${JSON.stringify(tc.args, null, 2)}\n\`\`\`\n`;
                scheduleTokenFlush(assistantMsgId, toolLabel, get());
              } catch { /* ignore parse errors */ }
              continue;
            }
            if (token.startsWith('[TOOL_RESULT]')) {
              try {
                const tr = JSON.parse(token.slice(13));
                const resultText = tr.result || '';
                const truncated = resultText.length > 500 ? resultText.slice(0, 500) + '...' : resultText;
                const resultLabel = `\n📋 **Result from ${tr.name}:**\n\`\`\`\n${truncated}\n\`\`\`\n`;
                scheduleTokenFlush(assistantMsgId, resultLabel, get());
              } catch { /* ignore parse errors */ }
              continue;
            }
            if (token.startsWith('[THINKING]')) {
              // Skip thinking tokens for now (could add UI later)
              continue;
            }
            // Regular token
            scheduleTokenFlush(assistantMsgId, token, get());
          }
          // Flush any remaining tokens
          flushPendingTokens();
        } catch (err: any) {
          // FIX #3: Don't double-flush here — the finally block handles it
          if (err.name === 'AbortError') {
            get().updateMessage(assistantMsgId, {
              isStreaming: false,
              error: '已停止生成',
            });
          } else {
            set({ error: err.message || '发送消息失败' });
            get().updateMessage(assistantMsgId, {
              isStreaming: false,
              error: err.message || '发送失败',
            });
          }
        } finally {
          // Clear idle timer
          if (idleStreamTimer) {
            clearTimeout(idleStreamTimer);
            idleStreamTimer = null;
          }
          // FIX #3: Single flush in finally (removed redundant flush in catch)
          flushPendingTokens();
          resetFlushState();

          get().updateMessage(assistantMsgId, { isStreaming: false });

          // FIX #1: Only clear isSending if we're still the current generation
          if (myGeneration === sendGeneration) {
            activeAbortController = null;
            set({ isGenerating: false, isSending: false });
          }

          // Auto-rename session based on first message
          const s = get();
          const ses = s.sessions.find((sess) => sess.id === sessionId);
          if (ses && ses.messages.length <= 3 && ses.title === '新对话') {
            const firstUserMsg = ses.messages.find((m) => m.role === 'user');
            if (firstUserMsg) {
              const title = firstUserMsg.content.slice(0, 30) + (firstUserMsg.content.length > 30 ? '...' : '');
              get().renameSession(sessionId!, title);
            }
          }
        }
      },

      stopGeneration: () => {
        if (activeAbortController) {
          activeAbortController.abort();
          activeAbortController = null;
        }
      },

      clearError: () => set({ error: null }),
    }),
    {
      name: 'hermes-chat',
      version: 1,
      migrate: (persistedState: unknown, version: number) => {
        if (version === 0) {
          // v0 -> v1: no schema change, just stamp the version
          return persistedState;
        }
        return persistedState;
      },
      partialize: (state) => ({
        sessions: state.sessions.map((session) => ({
          ...session,
          messages: session.messages.map((msg) => {
            // Strip transient streaming/error fields from persisted messages
            const { isStreaming, error, ...rest } = msg;
            return rest;
          }),
        })),
        currentSessionId: state.currentSessionId,
      }),
    }
  )
);

export default useChatStore;
