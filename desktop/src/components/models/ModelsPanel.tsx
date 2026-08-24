import React, { useState, useMemo } from 'react';
import { useSettingsStore, type ModelProvider } from '../../stores/settingsStore';
import { getBackendUrl } from '../../lib/utils';
import {
  Layers,
  Plus,
  Trash2,
  ToggleLeft,
  ToggleRight,
  Server,
  Key,
  Link as LinkIcon,
  RefreshCw,
  Check,
  AlertCircle,
  Loader2,
  Eye,
  EyeOff,
  Copy,
  Sparkles,
  Search,
  X,
  Activity,
  Cpu,
  Zap,
  CheckCircle2,
  XCircle,
  Edit3,
} from 'lucide-react';

interface PresetProvider {
  name: string;
  type: ModelProvider['type'];
  baseUrl: string;
  models: string[];
  docUrl?: string;
}

const PRESET_PROVIDERS: PresetProvider[] = [
  {
    name: 'DeepSeek',
    type: 'openai',
    baseUrl: 'https://api.deepseek.com/v1',
    models: ['deepseek-chat', 'deepseek-reasoner'],
    docUrl: 'https://platform.deepseek.com',
  },
  {
    name: 'OpenAI',
    type: 'openai',
    baseUrl: 'https://api.openai.com/v1',
    models: ['gpt-4o', 'gpt-4o-mini', 'o1', 'o3-mini'],
    docUrl: 'https://platform.openai.com',
  },
  {
    name: 'Anthropic',
    type: 'anthropic',
    baseUrl: 'https://api.anthropic.com',
    models: ['claude-3-7-sonnet-20250219', 'claude-3-5-sonnet-20241022', 'claude-3-5-haiku-20241022'],
    docUrl: 'https://console.anthropic.com',
  },
  {
    name: 'SiliconFlow (硅基流动)',
    type: 'openai',
    baseUrl: 'https://api.siliconflow.cn/v1',
    models: ['deepseek-ai/DeepSeek-V3', 'deepseek-ai/DeepSeek-R1', 'Qwen/Qwen2.5-72B-Instruct'],
    docUrl: 'https://cloud.siliconflow.cn',
  },
  {
    name: 'OpenRouter',
    type: 'openai',
    baseUrl: 'https://openrouter.ai/api/v1',
    models: ['anthropic/claude-3.7-sonnet', 'deepseek/deepseek-r1', 'openai/gpt-4o'],
    docUrl: 'https://openrouter.ai',
  },
  {
    name: 'Ollama (本地)',
    type: 'ollama',
    baseUrl: 'http://127.0.0.1:11434',
    models: ['llama3.3', 'qwen2.5', 'deepseek-r1:8b'],
    docUrl: 'https://ollama.com',
  },
  {
    name: 'CLIProxyAPI (代理网关)',
    type: 'openai',
    baseUrl: 'http://127.0.0.1:8317/v1',
    models: ['gemini-3.7-flash-high', 'claude-3-7-sonnet', 'deepseek-r1'],
  },
  {
    name: 'Google Gemini (OpenAI兼容)',
    type: 'openai',
    baseUrl: 'https://generativelanguage.googleapis.com/v1beta/openai',
    models: ['gemini-2.0-flash', 'gemini-2.0-pro-exp'],
    docUrl: 'https://aistudio.google.com',
  },
];

async function fetchModelsApi(
  baseUrl: string,
  apiKey: string
): Promise<{ success: boolean; models: string[]; error?: string; latencyMs?: number }> {
  try {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 20000);

    const res = await fetch(`${getBackendUrl()}/api/models`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ base_url: baseUrl, api_key: apiKey }),
      signal: controller.signal,
    });

    clearTimeout(timeoutId);

    const data = await res.json();
    return {
      success: data.success ?? false,
      models: data.models ?? [],
      error: data.error,
      latencyMs: data.latency_ms,
    };
  } catch (err: any) {
    if (err.name === 'AbortError') {
      return { success: false, models: [], error: '请求超时 (20秒)' };
    }
    return {
      success: false,
      models: [],
      error: err.message || '网络请求失败，请检查后端状态',
    };
  }
}

export function ModelsPanel() {
  const {
    providers,
    currentModel,
    currentProvider,
    setCurrentModel,
    updateProvider,
    removeProvider,
    addProvider,
  } = useSettingsStore();

  // Search & Filter State
  const [searchQuery, setSearchQuery] = useState('');
  const [showAddModal, setShowAddModal] = useState(false);
  const [editingProviderId, setEditingProviderId] = useState<string | null>(null);

  // Visibility state for password fields
  const [visibleKeys, setVisibleKeys] = useState<Record<string, boolean>>({});

  // Loading & Test Status states
  const [fetchingModels, setFetchingModels] = useState<Record<string, boolean>>({});
  const [testingConnection, setTestingConnection] = useState<Record<string, boolean>>({});
  const [operationResults, setOperationResults] = useState<
    Record<string, { success: boolean; message: string; latencyMs?: number }>
  >({});

  // Per-provider inline new model input
  const [newModelInputs, setNewModelInputs] = useState<Record<string, string>>({});
  // Per-provider model search query
  const [modelSearchQueries, setModelSearchQueries] = useState<Record<string, string>>({});

  // Form State for Add / Edit Modal
  const [formState, setFormState] = useState<{
    id?: string;
    name: string;
    type: ModelProvider['type'];
    baseUrl: string;
    apiKey: string;
    models: string[];
    enabled: boolean;
  }>({
    name: '',
    type: 'openai',
    baseUrl: '',
    apiKey: '',
    models: [],
    enabled: true,
  });

  const toggleKeyVisibility = (id: string) => {
    setVisibleKeys((prev) => ({ ...prev, [id]: !prev[id] }));
  };

  const copyToClipboard = (text: string) => {
    navigator.clipboard.writeText(text);
  };

  // Filtered providers based on search query
  const filteredProviders = useMemo(() => {
    if (!searchQuery.trim()) return providers;
    const q = searchQuery.toLowerCase();
    return providers.filter(
      (p) =>
        p.name.toLowerCase().includes(q) ||
        p.baseUrl.toLowerCase().includes(q) ||
        p.models.some((m) => m.toLowerCase().includes(q))
    );
  }, [providers, searchQuery]);

  // Active Provider Object
  const activeProvider = useMemo(() => {
    return providers.find((p) => p.id === currentProvider);
  }, [providers, currentProvider]);

  // Total stats
  const totalModelsCount = useMemo(() => {
    return providers.reduce((acc, p) => acc + p.models.length, 0);
  }, [providers]);

  const enabledProvidersCount = useMemo(() => {
    return providers.filter((p) => p.enabled).length;
  }, [providers]);

  // Handle Model Tags inside a Provider
  const handleAddModel = (providerId: string, model: string) => {
    const trimmed = model.trim();
    if (!trimmed) return;
    const provider = providers.find((p) => p.id === providerId);
    if (!provider) return;
    if (provider.models.includes(trimmed)) return;
    updateProvider(providerId, { models: [...provider.models, trimmed] });
    setNewModelInputs((prev) => ({ ...prev, [providerId]: '' }));
  };

  const handleRemoveModel = (providerId: string, model: string) => {
    const provider = providers.find((p) => p.id === providerId);
    if (!provider) return;
    updateProvider(providerId, { models: provider.models.filter((m) => m !== model) });
    // If the removed model was the active model, fall back to first available or empty
    if (currentProvider === providerId && currentModel === model) {
      const remaining = provider.models.filter((m) => m !== model);
      if (remaining.length > 0) {
        setCurrentModel(remaining[0], providerId);
      }
    }
  };

  // Fetch / Refresh Models for Provider
  const handleFetchModels = async (providerId: string) => {
    const provider = providers.find((p) => p.id === providerId);
    if (!provider) return;

    setFetchingModels((prev) => ({ ...prev, [providerId]: true }));
    setOperationResults((prev) => ({ ...prev, [providerId]: { success: false, message: '' } }));

    const result = await fetchModelsApi(provider.baseUrl, provider.apiKey);

    if (result.success && result.models.length > 0) {
      const existingSet = new Set(provider.models);
      const newModels = result.models.filter((m) => !existingSet.has(m));
      const merged = [...provider.models, ...newModels];
      updateProvider(providerId, { models: merged });
      setOperationResults((prev) => ({
        ...prev,
        [providerId]: {
          success: true,
          message: `获取成功！新增 ${newModels.length} 个，共 ${merged.length} 个模型`,
          latencyMs: result.latencyMs,
        },
      }));
    } else {
      setOperationResults((prev) => ({
        ...prev,
        [providerId]: {
          success: false,
          message: result.error || '获取模型列表失败',
          latencyMs: result.latencyMs,
        },
      }));
    }

    setFetchingModels((prev) => ({ ...prev, [providerId]: false }));
    setTimeout(() => {
      setOperationResults((prev) => {
        const next = { ...prev };
        delete next[providerId];
        return next;
      });
    }, 6000);
  };

  // Test Connection
  const handleTestConnection = async (providerId: string) => {
    const provider = providers.find((p) => p.id === providerId);
    if (!provider) return;

    setTestingConnection((prev) => ({ ...prev, [providerId]: true }));
    setOperationResults((prev) => ({ ...prev, [providerId]: { success: false, message: '' } }));

    const result = await fetchModelsApi(provider.baseUrl, provider.apiKey);

    if (result.success) {
      setOperationResults((prev) => ({
        ...prev,
        [providerId]: {
          success: true,
          message: `连接成功 (发现 ${result.models.length} 个模型)`,
          latencyMs: result.latencyMs,
        },
      }));
    } else {
      setOperationResults((prev) => ({
        ...prev,
        [providerId]: {
          success: false,
          message: result.error || '连接失败',
          latencyMs: result.latencyMs,
        },
      }));
    }

    setTestingConnection((prev) => ({ ...prev, [providerId]: false }));
    setTimeout(() => {
      setOperationResults((prev) => {
        const next = { ...prev };
        delete next[providerId];
        return next;
      });
    }, 6000);
  };

  // Open Add Modal
  const openAddModal = (preset?: PresetProvider) => {
    if (preset) {
      setFormState({
        name: preset.name,
        type: preset.type,
        baseUrl: preset.baseUrl,
        apiKey: '',
        models: [...preset.models],
        enabled: true,
      });
    } else {
      setFormState({
        name: '',
        type: 'openai',
        baseUrl: '',
        apiKey: '',
        models: [],
        enabled: true,
      });
    }
    setEditingProviderId(null);
    setShowAddModal(true);
  };

  // Open Edit Modal
  const openEditModal = (provider: ModelProvider) => {
    setFormState({
      id: provider.id,
      name: provider.name,
      type: provider.type,
      baseUrl: provider.baseUrl,
      apiKey: provider.apiKey,
      models: [...provider.models],
      enabled: provider.enabled,
    });
    setEditingProviderId(provider.id);
    setShowAddModal(true);
  };

  // Save Add/Edit Modal
  const handleSaveModal = () => {
    if (!formState.name.trim() || !formState.baseUrl.trim()) return;

    if (editingProviderId) {
      // Update existing
      updateProvider(editingProviderId, {
        name: formState.name.trim(),
        type: formState.type,
        baseUrl: formState.baseUrl.trim(),
        apiKey: formState.apiKey.trim(),
        models: formState.models,
        enabled: formState.enabled,
      });
    } else {
      // Create new
      const id =
        formState.name.toLowerCase().replace(/[^a-z0-9]/g, '-') + '-' + Date.now().toString().slice(-4);
      addProvider({
        id,
        name: formState.name.trim(),
        type: formState.type,
        baseUrl: formState.baseUrl.trim(),
        apiKey: formState.apiKey.trim(),
        models: formState.models,
        enabled: true,
      });
    }

    setShowAddModal(false);
  };

  // Test & Fetch inside Modal
  const handleModalTestAndFetch = async () => {
    if (!formState.baseUrl.trim()) return;
    setFetchingModels((prev) => ({ ...prev, __modal: true }));
    setOperationResults((prev) => ({ ...prev, __modal: { success: false, message: '' } }));

    const result = await fetchModelsApi(formState.baseUrl, formState.apiKey);

    if (result.success && result.models.length > 0) {
      const existingSet = new Set(formState.models);
      const newModels = result.models.filter((m) => !existingSet.has(m));
      const merged = [...formState.models, ...newModels];
      setFormState((prev) => ({ ...prev, models: merged }));
      setOperationResults((prev) => ({
        ...prev,
        __modal: {
          success: true,
          message: `获取成功！共发现 ${result.models.length} 个模型`,
          latencyMs: result.latencyMs,
        },
      }));
    } else {
      setOperationResults((prev) => ({
        ...prev,
        __modal: {
          success: false,
          message: result.error || '获取失败，请检查 Base URL 与 API Key',
          latencyMs: result.latencyMs,
        },
      }));
    }

    setFetchingModels((prev) => ({ ...prev, __modal: false }));
  };

  return (
    <div className="flex flex-col h-full bg-[var(--bg-primary)] overflow-hidden">
      {/* ─── Header ─── */}
      <div className="flex flex-wrap items-center justify-between gap-4 px-6 py-4 border-b border-[var(--hermes-border)] bg-[var(--bg-primary)] z-10">
        <div className="flex items-center gap-3">
          <div className="p-2 rounded-xl bg-[var(--hermes-accent)]/10 text-[var(--hermes-accent)]">
            <Layers size={22} />
          </div>
          <div>
            <h1 className="text-lg font-semibold text-text-primary flex items-center gap-2">
              模型与提供商设置
              <span className="text-xs px-2 py-0.5 rounded-full bg-[var(--bg-tertiary)] text-text-muted font-normal">
                {enabledProvidersCount}/{providers.length} 启用 · {totalModelsCount} 个模型
              </span>
            </h1>
            <p className="text-xs text-text-muted">
              配置 AI 模型接口与 API 密钥，支持 OpenAI、Claude、DeepSeek、Ollama 及兼容网关
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={() => openAddModal()}
            className="flex items-center gap-1.5 px-3.5 py-2 text-sm font-medium bg-[var(--hermes-accent)] text-white rounded-lg hover:opacity-90 active:scale-95 transition-all shadow-sm"
          >
            <Plus size={15} />
            <span>添加自定义提供商</span>
          </button>
        </div>
      </div>

      {/* ─── Main Content Body ─── */}
      <div className="flex-1 overflow-y-auto px-6 py-5 space-y-6">
        {/* ─── Hero / Current Active Model Banner ─── */}
        <div className="relative overflow-hidden p-5 rounded-2xl bg-gradient-to-r from-[var(--bg-secondary)] via-[var(--bg-secondary)] to-[var(--hermes-accent)]/5 border border-[var(--hermes-accent)]/30 shadow-sm">
          <div className="flex flex-wrap items-center justify-between gap-4">
            <div className="space-y-1.5">
              <div className="flex items-center gap-2">
                <span className="flex h-2 w-2 relative">
                  <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
                  <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500"></span>
                </span>
                <span className="text-xs font-semibold tracking-wider text-[var(--hermes-accent)] uppercase">
                  当前对话默认模型
                </span>
                <span className="text-xs px-2 py-0.5 rounded bg-[var(--bg-tertiary)] text-text-secondary">
                  {activeProvider?.name || currentProvider}
                </span>
              </div>
              <div className="flex items-baseline gap-3">
                <h2 className="text-xl font-bold font-mono text-text-primary tracking-tight">
                  {currentModel || '(未选择模型)'}
                </h2>
              </div>
              <p className="text-xs text-text-muted font-mono flex items-center gap-1.5">
                <Server size={12} className="text-text-muted" />
                {activeProvider?.baseUrl || '未配置 Base URL'}
              </p>
            </div>

            <div className="flex items-center gap-2">
              {activeProvider && (
                <button
                  onClick={() => handleTestConnection(activeProvider.id)}
                  disabled={testingConnection[activeProvider.id]}
                  className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium bg-[var(--bg-primary)] border border-[var(--hermes-border)] hover:border-[var(--hermes-accent)] text-text-secondary hover:text-[var(--hermes-accent)] rounded-lg transition-colors shadow-sm"
                >
                  {testingConnection[activeProvider.id] ? (
                    <Loader2 size={13} className="animate-spin" />
                  ) : (
                    <Activity size={13} />
                  )}
                  <span>测试当前连接</span>
                </button>
              )}
            </div>
          </div>
        </div>

        {/* ─── Quick Presets Row ─── */}
        <div className="space-y-2.5">
          <div className="flex items-center justify-between">
            <label className="text-xs font-semibold text-text-secondary flex items-center gap-1.5">
              <Sparkles size={14} className="text-[var(--hermes-accent)]" />
              快捷添加常用服务商
            </label>
          </div>
          <div className="grid grid-cols-2 sm:grid-cols-4 md:grid-cols-4 lg:grid-cols-8 gap-2">
            {PRESET_PROVIDERS.map((preset) => {
              const isAlreadyAdded = providers.some(
                (p) => p.name.toLowerCase() === preset.name.toLowerCase() || p.baseUrl === preset.baseUrl
              );
              return (
                <button
                  key={preset.name}
                  onClick={() => openAddModal(preset)}
                  className="flex flex-col items-start p-2.5 rounded-xl border border-[var(--hermes-border)] bg-[var(--bg-secondary)] hover:border-[var(--hermes-accent)] hover:bg-[var(--hermes-accent)]/5 text-left transition-all group relative"
                >
                  <span className="text-xs font-medium text-text-primary group-hover:text-[var(--hermes-accent)] line-clamp-1">
                    {preset.name}
                  </span>
                  <span className="text-[10px] text-text-muted mt-0.5 line-clamp-1">
                    {isAlreadyAdded ? '已添加 · 点击再建' : `${preset.models.length} 个推荐模型`}
                  </span>
                </button>
              );
            })}
          </div>
        </div>

        {/* ─── Search & Providers Header ─── */}
        <div className="flex flex-wrap items-center justify-between gap-3 pt-2">
          <h3 className="text-sm font-semibold text-text-primary flex items-center gap-2">
            <Server size={16} className="text-[var(--hermes-accent)]" />
            已配置提供商列表 ({filteredProviders.length})
          </h3>

          <div className="relative w-full sm:w-64">
            <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-text-muted" />
            <input
              type="text"
              placeholder="搜索提供商或模型名称..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full pl-9 pr-3 py-1.5 text-xs bg-[var(--bg-secondary)] border border-[var(--hermes-border)] focus:border-[var(--hermes-accent)] rounded-lg outline-none text-text-primary placeholder:text-text-muted transition-colors font-mono"
            />
            {searchQuery && (
              <button
                onClick={() => setSearchQuery('')}
                className="absolute right-2.5 top-1/2 -translate-y-1/2 text-text-muted hover:text-text-primary"
              >
                <X size={12} />
              </button>
            )}
          </div>
        </div>

        {/* ─── Provider Cards List ─── */}
        <div className="space-y-4">
          {filteredProviders.length === 0 && (
            <div className="flex flex-col items-center justify-center p-12 text-center rounded-2xl border border-dashed border-[var(--hermes-border)] bg-[var(--bg-secondary)]">
              <Layers size={36} className="text-text-muted mb-3 opacity-50" />
              <p className="text-sm font-medium text-text-secondary">没有找到匹配的模型提供商</p>
              <p className="text-xs text-text-muted mt-1">您可以点击上方按钮添加新的提供商或清除搜索词</p>
            </div>
          )}

          {filteredProviders.map((provider) => {
            const isCurrentActive = provider.id === currentProvider;
            const isKeyVisible = visibleKeys[provider.id] || false;
            const isFetching = fetchingModels[provider.id] || false;
            const isTesting = testingConnection[provider.id] || false;
            const opResult = operationResults[provider.id];
            const pModelSearch = (modelSearchQueries[provider.id] || '').toLowerCase();

            // Filter models for this card
            const visibleModels = pModelSearch
              ? provider.models.filter((m) => m.toLowerCase().includes(pModelSearch))
              : provider.models;

            return (
              <div
                key={provider.id}
                className={`rounded-2xl border transition-all ${
                  isCurrentActive
                    ? 'border-[var(--hermes-accent)]/60 bg-[var(--bg-secondary)] shadow-sm'
                    : 'border-[var(--hermes-border)] bg-[var(--bg-secondary)] hover:border-[var(--hermes-border)]/80'
                }`}
              >
                {/* ── Card Header ── */}
                <div className="flex flex-wrap items-center justify-between gap-3 px-5 py-3.5 border-b border-[var(--hermes-border)] bg-[var(--bg-surface)]/50 rounded-t-2xl">
                  <div className="flex items-center gap-3">
                    <div
                      className={`p-2 rounded-xl ${
                        provider.enabled
                          ? 'bg-[var(--hermes-accent)]/10 text-[var(--hermes-accent)]'
                          : 'bg-[var(--bg-tertiary)] text-text-muted'
                      }`}
                    >
                      <Cpu size={18} />
                    </div>
                    <div>
                      <div className="flex items-center gap-2">
                        <h4 className="text-sm font-bold text-text-primary">{provider.name}</h4>
                        <span className="text-[10px] px-1.5 py-0.5 rounded uppercase font-mono bg-[var(--bg-tertiary)] text-text-secondary">
                          {provider.type}
                        </span>
                        {isCurrentActive && (
                          <span className="text-[10px] px-2 py-0.5 rounded-full font-medium bg-[var(--hermes-accent)] text-white flex items-center gap-1">
                            <Check size={10} /> 使用中
                          </span>
                        )}
                        {!provider.enabled && (
                          <span className="text-[10px] px-1.5 py-0.5 rounded font-medium bg-amber-500/10 text-amber-500">
                            已禁用
                          </span>
                        )}
                      </div>
                      <p className="text-xs text-text-muted font-mono mt-0.5 flex items-center gap-1">
                        <span>{provider.baseUrl}</span>
                      </p>
                    </div>
                  </div>

                  {/* Actions Header */}
                  <div className="flex items-center gap-2">
                    {/* Enable Toggle */}
                    <button
                      onClick={() => updateProvider(provider.id, { enabled: !provider.enabled })}
                      className={`p-1 transition-colors ${
                        provider.enabled ? 'text-[var(--hermes-accent)]' : 'text-text-muted'
                      }`}
                      title={provider.enabled ? '点击禁用' : '点击启用'}
                    >
                      {provider.enabled ? <ToggleRight size={26} /> : <ToggleLeft size={26} />}
                    </button>

                    {/* Test Button */}
                    <button
                      onClick={() => handleTestConnection(provider.id)}
                      disabled={isTesting || !provider.baseUrl}
                      className="flex items-center gap-1 px-2.5 py-1.5 text-xs rounded-lg border border-[var(--hermes-border)] bg-[var(--bg-primary)] hover:border-[var(--hermes-accent)] text-text-secondary hover:text-[var(--hermes-accent)] disabled:opacity-50 transition-colors"
                      title="测试连通性与延迟"
                    >
                      {isTesting ? (
                        <Loader2 size={13} className="animate-spin" />
                      ) : (
                        <Activity size={13} />
                      )}
                      <span>测试</span>
                    </button>

                    {/* Auto Fetch Button */}
                    <button
                      onClick={() => handleFetchModels(provider.id)}
                      disabled={isFetching || !provider.baseUrl}
                      className="flex items-center gap-1 px-2.5 py-1.5 text-xs rounded-lg bg-[var(--hermes-accent)]/10 text-[var(--hermes-accent)] border border-[var(--hermes-accent)]/20 hover:bg-[var(--hermes-accent)]/20 disabled:opacity-50 transition-colors font-medium"
                      title="从提供商接口自动获取可用模型列表"
                    >
                      {isFetching ? (
                        <Loader2 size={13} className="animate-spin" />
                      ) : (
                        <RefreshCw size={13} />
                      )}
                      <span>获取模型</span>
                    </button>

                    {/* Edit Provider */}
                    <button
                      onClick={() => openEditModal(provider)}
                      className="p-1.5 rounded-lg text-text-muted hover:text-text-primary hover:bg-[var(--bg-tertiary)] transition-colors"
                      title="编辑提供商详情"
                    >
                      <Edit3 size={14} />
                    </button>

                    {/* Delete Provider */}
                    <button
                      onClick={() => {
                        if (window.confirm(`确定要删除提供商 "${provider.name}" 吗？`)) {
                          removeProvider(provider.id);
                        }
                      }}
                      className="p-1.5 rounded-lg text-text-muted hover:text-red-400 hover:bg-red-500/10 transition-colors"
                      title="删除提供商"
                    >
                      <Trash2 size={14} />
                    </button>
                  </div>
                </div>

                {/* ── Card Body ── */}
                <div className="p-5 space-y-4">
                  {/* Operation Alert Bar */}
                  {opResult && (
                    <div
                      className={`flex items-center justify-between px-3.5 py-2.5 rounded-xl text-xs font-medium transition-all ${
                        opResult.success
                          ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20'
                          : 'bg-red-500/10 text-red-400 border border-red-500/20'
                      }`}
                    >
                      <div className="flex items-center gap-2">
                        {opResult.success ? <CheckCircle2 size={14} /> : <XCircle size={14} />}
                        <span>{opResult.message}</span>
                      </div>
                      {opResult.latencyMs !== undefined && (
                        <span className="text-[11px] font-mono px-2 py-0.5 rounded bg-black/20">
                          ⚡ {opResult.latencyMs}ms
                        </span>
                      )}
                    </div>
                  )}

                  {/* Form Grid: Base URL & API Key */}
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    {/* Base URL */}
                    <div>
                      <label className="flex items-center justify-between text-xs font-medium text-text-muted mb-1.5">
                        <span className="flex items-center gap-1.5">
                          <LinkIcon size={13} /> 接口地址 (Base URL)
                        </span>
                        <button
                          onClick={() => copyToClipboard(provider.baseUrl)}
                          className="hover:text-text-primary text-[11px] flex items-center gap-1"
                        >
                          <Copy size={11} /> 复制
                        </button>
                      </label>
                      <input
                        type="text"
                        value={provider.baseUrl}
                        onChange={(e) => updateProvider(provider.id, { baseUrl: e.target.value })}
                        placeholder="https://api.openai.com/v1"
                        className="w-full bg-[var(--bg-primary)] text-text-primary text-xs rounded-xl px-3 py-2.5 outline-none border border-[var(--hermes-border)] focus:border-[var(--hermes-accent)] transition-colors font-mono"
                      />
                    </div>

                    {/* API Key */}
                    <div>
                      <label className="flex items-center justify-between text-xs font-medium text-text-muted mb-1.5">
                        <span className="flex items-center gap-1.5">
                          <Key size={13} /> API 密钥 (Key)
                        </span>
                        <span
                          className={`text-[10px] px-1.5 py-0.2 rounded font-medium ${
                            provider.apiKey ? 'text-emerald-400' : 'text-amber-400'
                          }`}
                        >
                          {provider.apiKey ? '● 已保存' : '○ 未填写密钥'}
                        </span>
                      </label>
                      <div className="relative">
                        <input
                          type={isKeyVisible ? 'text' : 'password'}
                          value={provider.apiKey}
                          onChange={(e) => updateProvider(provider.id, { apiKey: e.target.value })}
                          placeholder="sk-..."
                          className="w-full bg-[var(--bg-primary)] text-text-primary text-xs rounded-xl pl-3 pr-10 py-2.5 outline-none border border-[var(--hermes-border)] focus:border-[var(--hermes-accent)] transition-colors font-mono"
                        />
                        <button
                          type="button"
                          onClick={() => toggleKeyVisibility(provider.id)}
                          className="absolute right-3 top-1/2 -translate-y-1/2 text-text-muted hover:text-text-primary transition-colors"
                          title={isKeyVisible ? '隐藏密钥' : '显示密钥'}
                        >
                          {isKeyVisible ? <EyeOff size={14} /> : <Eye size={14} />}
                        </button>
                      </div>
                    </div>
                  </div>

                  {/* ── Models Subsection ── */}
                  <div className="pt-2 border-t border-[var(--hermes-border)]/60">
                    <div className="flex flex-wrap items-center justify-between gap-2 mb-2.5">
                      <div className="flex items-center gap-2">
                        <span className="text-xs font-semibold text-text-secondary">
                          可用模型列表 ({provider.models.length})
                        </span>
                        <span className="text-[11px] text-text-muted">点击标签可快速设为当前使用模型</span>
                      </div>

                      {/* Small Search for models if list > 5 */}
                      {provider.models.length > 5 && (
                        <div className="relative">
                          <input
                            type="text"
                            placeholder="筛选模型..."
                            value={modelSearchQueries[provider.id] || ''}
                            onChange={(e) =>
                              setModelSearchQueries((prev) => ({
                                ...prev,
                                [provider.id]: e.target.value,
                              }))
                            }
                            className="bg-[var(--bg-primary)] text-text-primary text-[11px] rounded-lg pl-2 pr-6 py-1 border border-[var(--hermes-border)] focus:border-[var(--hermes-accent)] outline-none font-mono"
                          />
                          {modelSearchQueries[provider.id] && (
                            <button
                              onClick={() =>
                                setModelSearchQueries((prev) => ({ ...prev, [provider.id]: '' }))
                              }
                              className="absolute right-1.5 top-1/2 -translate-y-1/2 text-text-muted hover:text-text-primary"
                            >
                              <X size={10} />
                            </button>
                          )}
                        </div>
                      )}
                    </div>

                    {/* Model Pills */}
                    <div className="flex flex-wrap gap-2 mb-3 max-h-48 overflow-y-auto p-1">
                      {visibleModels.map((model) => {
                        const isSelected = isCurrentActive && model === currentModel;
                        return (
                          <div
                            key={model}
                            onClick={() => setCurrentModel(model, provider.id)}
                            className={`group inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs cursor-pointer transition-all border ${
                              isSelected
                                ? 'bg-[var(--hermes-accent)] text-white border-[var(--hermes-accent)] font-semibold shadow-sm'
                                : 'bg-[var(--bg-primary)] text-text-secondary border-[var(--hermes-border)] hover:border-[var(--hermes-accent)] hover:text-text-primary'
                            }`}
                            title={`点击将 ${model} 设为当前激活模型`}
                          >
                            {isSelected && <Check size={12} className="stroke-[3]" />}
                            <span className="font-mono">{model}</span>
                            <button
                              onClick={(e) => {
                                e.stopPropagation();
                                handleRemoveModel(provider.id, model);
                              }}
                              className={`ml-1 p-0.5 rounded hover:bg-black/20 transition-colors ${
                                isSelected ? 'text-white/80 hover:text-white' : 'text-text-muted hover:text-red-400'
                              }`}
                              title="移除此模型"
                            >
                              <X size={11} />
                            </button>
                          </div>
                        );
                      })}

                      {visibleModels.length === 0 && provider.models.length > 0 && (
                        <span className="text-xs text-text-muted py-1 italic">未找到匹配的模型</span>
                      )}

                      {provider.models.length === 0 && (
                        <div className="w-full py-4 text-center rounded-xl bg-[var(--bg-primary)] border border-dashed border-[var(--hermes-border)]">
                          <p className="text-xs text-text-muted">
                            暂无配置模型，您可以点击右上角「获取模型」或在下方手动添加
                          </p>
                        </div>
                      )}
                    </div>

                    {/* Add Model Input */}
                    <div className="flex items-center gap-2">
                      <div className="relative flex-1">
                        <input
                          type="text"
                          value={newModelInputs[provider.id] || ''}
                          onChange={(e) =>
                            setNewModelInputs((prev) => ({
                              ...prev,
                              [provider.id]: e.target.value,
                            }))
                          }
                          onKeyDown={(e) => {
                            if (e.key === 'Enter') {
                              e.preventDefault();
                              handleAddModel(provider.id, newModelInputs[provider.id] || '');
                            }
                          }}
                          placeholder="输入模型名称 (如 gpt-4o 或 deepseek-chat) 后回车添加..."
                          className="w-full bg-[var(--bg-primary)] text-text-primary text-xs rounded-xl px-3 py-2 outline-none border border-[var(--hermes-border)] focus:border-[var(--hermes-accent)] transition-colors font-mono"
                        />
                      </div>
                      <button
                        onClick={() =>
                          handleAddModel(provider.id, newModelInputs[provider.id] || '')
                        }
                        disabled={!(newModelInputs[provider.id] || '').trim()}
                        className="flex items-center gap-1 px-3.5 py-2 rounded-xl text-xs bg-[var(--bg-tertiary)] hover:bg-[var(--hermes-accent)] text-text-secondary hover:text-white disabled:opacity-40 disabled:cursor-not-allowed transition-all font-medium"
                      >
                        <Plus size={13} />
                        <span>添加模型</span>
                      </button>
                    </div>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* ─── Add / Edit Modal ─── */}
      {showAddModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4 animate-in fade-in duration-150">
          <div className="w-full max-w-xl rounded-2xl bg-[var(--bg-secondary)] border border-[var(--hermes-border)] shadow-2xl overflow-hidden flex flex-col max-h-[90vh]">
            {/* Modal Header */}
            <div className="flex items-center justify-between px-6 py-4 border-b border-[var(--hermes-border)] bg-[var(--bg-surface)]">
              <div className="flex items-center gap-2.5">
                <div className="p-2 rounded-xl bg-[var(--hermes-accent)]/10 text-[var(--hermes-accent)]">
                  {editingProviderId ? <Edit3 size={18} /> : <Plus size={18} />}
                </div>
                <h3 className="text-base font-semibold text-text-primary">
                  {editingProviderId ? '编辑模型提供商' : '添加模型提供商'}
                </h3>
              </div>
              <button
                onClick={() => setShowAddModal(false)}
                className="p-1.5 rounded-lg text-text-muted hover:text-text-primary hover:bg-[var(--bg-tertiary)] transition-colors"
              >
                <X size={16} />
              </button>
            </div>

            {/* Modal Body */}
            <div className="flex-1 overflow-y-auto p-6 space-y-4">
              {/* Presets Bar inside Modal */}
              {!editingProviderId && (
                <div>
                  <label className="text-xs font-medium text-text-muted mb-2 block">
                    选择常用模板快速填充:
                  </label>
                  <div className="flex flex-wrap gap-1.5">
                    {PRESET_PROVIDERS.map((preset) => (
                      <button
                        key={preset.name}
                        type="button"
                        onClick={() => {
                          setFormState((prev) => ({
                            ...prev,
                            name: preset.name,
                            type: preset.type,
                            baseUrl: preset.baseUrl,
                            models: [...preset.models],
                          }));
                        }}
                        className={`px-2.5 py-1 text-xs rounded-lg border transition-colors ${
                          formState.name === preset.name
                            ? 'bg-[var(--hermes-accent)] text-white border-[var(--hermes-accent)]'
                            : 'bg-[var(--bg-primary)] text-text-secondary border-[var(--hermes-border)] hover:border-[var(--hermes-accent)]'
                        }`}
                      >
                        {preset.name}
                      </button>
                    ))}
                  </div>
                </div>
              )}

              {/* Provider Name */}
              <div>
                <label className="text-xs font-semibold text-text-secondary mb-1.5 block">
                  提供商名称 <span className="text-red-400">*</span>
                </label>
                <input
                  type="text"
                  value={formState.name}
                  onChange={(e) => setFormState({ ...formState, name: e.target.value })}
                  placeholder="例如：DeepSeek、硅基流动、Ollama 等"
                  className="w-full bg-[var(--bg-primary)] text-text-primary text-sm rounded-xl px-3.5 py-2.5 outline-none border border-[var(--hermes-border)] focus:border-[var(--hermes-accent)] transition-colors"
                />
              </div>

              {/* Provider Protocol Type */}
              <div>
                <label className="text-xs font-semibold text-text-secondary mb-1.5 block">
                  协议类型
                </label>
                <div className="grid grid-cols-4 gap-2">
                  {(['openai', 'anthropic', 'ollama', 'custom'] as const).map((t) => (
                    <button
                      key={t}
                      type="button"
                      onClick={() => setFormState({ ...formState, type: t })}
                      className={`py-2 text-xs font-medium rounded-xl border uppercase transition-colors ${
                        formState.type === t
                          ? 'border-[var(--hermes-accent)] bg-[var(--hermes-accent)]/10 text-[var(--hermes-accent)]'
                          : 'border-[var(--hermes-border)] text-text-muted hover:text-text-primary'
                      }`}
                    >
                      {t}
                    </button>
                  ))}
                </div>
              </div>

              {/* Base URL */}
              <div>
                <label className="text-xs font-semibold text-text-secondary mb-1.5 block">
                  接口地址 (Base URL) <span className="text-red-400">*</span>
                </label>
                <input
                  type="text"
                  value={formState.baseUrl}
                  onChange={(e) => setFormState({ ...formState, baseUrl: e.target.value })}
                  placeholder="https://api.openai.com/v1 或 http://127.0.0.1:11434"
                  className="w-full bg-[var(--bg-primary)] text-text-primary text-sm rounded-xl px-3.5 py-2.5 outline-none border border-[var(--hermes-border)] focus:border-[var(--hermes-accent)] transition-colors font-mono"
                />
              </div>

              {/* API Key */}
              <div>
                <label className="text-xs font-semibold text-text-secondary mb-1.5 block">
                  API Key 密钥
                </label>
                <input
                  type="password"
                  value={formState.apiKey}
                  onChange={(e) => setFormState({ ...formState, apiKey: e.target.value })}
                  placeholder="sk-... (Ollama 或本地无密码服务可留空)"
                  className="w-full bg-[var(--bg-primary)] text-text-primary text-sm rounded-xl px-3.5 py-2.5 outline-none border border-[var(--hermes-border)] focus:border-[var(--hermes-accent)] transition-colors font-mono"
                />
              </div>

              {/* Test & Fetch Button */}
              <div>
                <button
                  type="button"
                  onClick={handleModalTestAndFetch}
                  disabled={fetchingModels['__modal'] || !formState.baseUrl}
                  className="flex items-center justify-center gap-2 w-full px-4 py-2.5 rounded-xl text-xs font-medium bg-[var(--hermes-accent)]/10 text-[var(--hermes-accent)] border border-[var(--hermes-accent)]/20 hover:bg-[var(--hermes-accent)]/20 disabled:opacity-50 transition-colors"
                >
                  {fetchingModels['__modal'] ? (
                    <Loader2 size={14} className="animate-spin" />
                  ) : (
                    <RefreshCw size={14} />
                  )}
                  <span>{fetchingModels['__modal'] ? '测试并获取中...' : '测试连接并自动获取模型列表'}</span>
                </button>
              </div>

              {/* Result Notice */}
              {operationResults['__modal'] && (
                <div
                  className={`flex items-center gap-2 px-3 py-2 rounded-xl text-xs font-medium ${
                    operationResults['__modal'].success
                      ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20'
                      : 'bg-red-500/10 text-red-400 border border-red-500/20'
                  }`}
                >
                  {operationResults['__modal'].success ? (
                    <CheckCircle2 size={14} />
                  ) : (
                    <AlertCircle size={14} />
                  )}
                  <span>{operationResults['__modal'].message}</span>
                </div>
              )}

              {/* Models Preview & Manual Add */}
              <div>
                <label className="text-xs font-semibold text-text-secondary mb-1.5 block">
                  模型列表 ({formState.models.length})
                </label>
                <div className="flex flex-wrap gap-1.5 p-2 rounded-xl bg-[var(--bg-primary)] border border-[var(--hermes-border)] min-h-[60px] max-h-32 overflow-y-auto">
                  {formState.models.map((m) => (
                    <span
                      key={m}
                      className="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg text-xs bg-[var(--bg-tertiary)] text-text-secondary font-mono"
                    >
                      {m}
                      <button
                        type="button"
                        onClick={() =>
                          setFormState((prev) => ({
                            ...prev,
                            models: prev.models.filter((item) => item !== m),
                          }))
                        }
                        className="hover:text-red-400"
                      >
                        ×
                      </button>
                    </span>
                  ))}
                  {formState.models.length === 0 && (
                    <span className="text-xs text-text-muted italic py-1">暂无模型，可点击上方自动获取</span>
                  )}
                </div>
              </div>
            </div>

            {/* Modal Footer */}
            <div className="flex items-center justify-end gap-3 px-6 py-4 border-t border-[var(--hermes-border)] bg-[var(--bg-surface)]">
              <button
                type="button"
                onClick={() => setShowAddModal(false)}
                className="px-4 py-2 text-xs font-medium text-text-secondary hover:text-text-primary hover:bg-[var(--bg-tertiary)] rounded-xl transition-colors"
              >
                取消
              </button>
              <button
                type="button"
                onClick={handleSaveModal}
                disabled={!formState.name.trim() || !formState.baseUrl.trim()}
                className="px-5 py-2 text-xs font-medium bg-[var(--hermes-accent)] text-white hover:opacity-90 disabled:opacity-50 disabled:cursor-not-allowed rounded-xl transition-all shadow-sm"
              >
                保存提供商
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default ModelsPanel;
