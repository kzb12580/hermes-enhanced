import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import apiClient from '../lib/api';

export interface ModelProvider {
  id: string;
  name: string;
  type: 'openai' | 'anthropic' | 'ollama' | 'custom';
  baseUrl: string;
  apiKey: string;
  models: string[];
  enabled: boolean;
}

export interface AppSettings {
  /** Current selected model ID */
  currentModel: string;
  /** Current provider ID */
  currentProvider: string;
  /** UI language */
  language: 'zh' | 'en';
  /** Font size */
  fontSize: number;
  /** Send shortcut: 'enter' | 'ctrl+enter' */
  sendShortcut: 'enter' | 'ctrl+enter';
  /** Show system messages */
  showSystemMessages: boolean;
  /** Auto-scroll to bottom */
  autoScroll: boolean;
  /** Thinking/reasoning mode: 'off' | 'auto' | 'on' */
  thinkingMode: 'off' | 'auto' | 'on';
  /** Thinking budget tokens (for models that support it) */
  thinkingBudget: number;
  /** Model providers */
  providers: ModelProvider[];
  /** System prompt */
  systemPrompt: string;
  /** Temperature */
  temperature: number;
  /** Max tokens */
  maxTokens: number | null;
  /** Backend URL */
  backendUrl: string;
  /** API key for backend auth */
  apiKey: string;
  /** Open links in external browser */
  openLinksInExternalBrowser: boolean;
}

interface SettingsState extends AppSettings {
  updateSettings: (settings: Partial<AppSettings>) => void;
  addProvider: (provider: ModelProvider) => void;
  updateProvider: (id: string, updates: Partial<ModelProvider>) => void;
  removeProvider: (id: string) => void;
  setCurrentModel: (model: string, provider: string) => void;
  resetSettings: () => void;
  /** Call once at app start to sync persisted backendUrl → apiClient */
  initApiClient: () => void;
}

const defaultProviders: ModelProvider[] = [
  {
    id: 'openai',
    name: 'OpenAI',
    type: 'openai',
    baseUrl: 'https://api.openai.com/v1',
    apiKey: '',
    models: ['gpt-4o', 'gpt-4o-mini', 'gpt-4-turbo', 'gpt-3.5-turbo'],
    enabled: true,
  },
  {
    id: 'anthropic',
    name: 'Anthropic',
    type: 'anthropic',
    baseUrl: 'https://api.anthropic.com',
    apiKey: '',
    models: ['claude-sonnet-4-20250514', 'claude-3-5-sonnet-20241022', 'claude-3-haiku-20240307'],
    enabled: true,
  },
  {
    id: 'ollama',
    name: 'Ollama (本地)',
    type: 'ollama',
    baseUrl: 'http://127.0.0.1:11434',
    apiKey: '',
    models: [],
    enabled: false,
  },
];

const defaultSettings: AppSettings = {
  currentModel: 'gpt-4o',
  currentProvider: 'openai',
  language: 'zh',
  fontSize: 14,
  sendShortcut: 'enter',
  showSystemMessages: false, // 锁死：永久不显示
  autoScroll: true, // 锁死：永远滚动到底部
  thinkingMode: 'off',
  thinkingBudget: 8192,
  providers: defaultProviders,
  systemPrompt: 'You are Hermes, an AI assistant. Be helpful, concise, and respond in the user\'s language. You can help with coding, research, writing, and general questions.',
  temperature: 0.7,
  maxTokens: null,  // null = 后端按模型自适应
  backendUrl: 'http://127.0.0.1:9876',
  apiKey: '',
  openLinksInExternalBrowser: true,
};

export const useSettingsStore = create<SettingsState>()(
  persist(
    (set, get) => ({
      ...defaultSettings,

      updateSettings: (settings) => {
        set(settings);
        if (settings.backendUrl || settings.apiKey !== undefined) {
          const s = get();
          apiClient.updateConfig({
            baseUrl: s.backendUrl,
            apiKey: s.apiKey,
          });
        }
      },

      addProvider: (provider) =>
        set((s) => ({ providers: [...s.providers, provider] })),

      updateProvider: (id, updates) =>
        set((s) => ({
          providers: s.providers.map((p) =>
            p.id === id ? { ...p, ...updates } : p
          ),
        })),

      removeProvider: (id) =>
        set((s) => ({
          providers: s.providers.filter((p) => p.id !== id),
        })),

      setCurrentModel: (model, provider) =>
        set({ currentModel: model, currentProvider: provider }),

      resetSettings: () => {
        set(defaultSettings);
        apiClient.updateConfig({
          baseUrl: defaultSettings.backendUrl,
          apiKey: defaultSettings.apiKey,
        });
      },

      initApiClient: () => {
        const s = get();
        apiClient.updateConfig({
          baseUrl: s.backendUrl,
          apiKey: s.apiKey,
        });
      },
    }),
    {
      name: 'hermes-settings',
      onRehydrateStorage: () => (_state, error) => {
        if (error) {
          console.error('[settingsStore] persist rehydrate failed, clearing storage:', error);
          try { localStorage.removeItem('hermes-settings'); } catch {}
        }
      },
      partialize: (state) => ({
        currentModel: state.currentModel,
        currentProvider: state.currentProvider,
        language: state.language,
        fontSize: state.fontSize,
        sendShortcut: state.sendShortcut,
        showSystemMessages: state.showSystemMessages,
        autoScroll: state.autoScroll,
        thinkingMode: state.thinkingMode,
        thinkingBudget: state.thinkingBudget,
        // 排除 apiKey — 不持久化到 localStorage（安全考虑）
        providers: state.providers.map(p => ({ ...p, apiKey: '' })),
        systemPrompt: state.systemPrompt,
        temperature: state.temperature,
        maxTokens: state.maxTokens,
        backendUrl: state.backendUrl,
        // apiKey: '' — 不持久化
        openLinksInExternalBrowser: state.openLinksInExternalBrowser,
      }),
    }
  )
);

export default useSettingsStore;
