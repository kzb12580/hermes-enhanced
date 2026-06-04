import React, { useState } from 'react';
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
  Link,
  RefreshCw,
  Check,
  AlertCircle,
  Loader2,
} from 'lucide-react';

async function fetchModels(
  baseUrl: string,
  apiKey: string
): Promise<{ success: boolean; models: string[]; error?: string }> {
  try {
    const params = new URLSearchParams({ base_url: baseUrl });
    if (apiKey) params.set('api_key', apiKey);

    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 20000);

    const res = await fetch(`${getBackendUrl()}/api/models?${params}`, {
      method: 'GET',
      signal: controller.signal,
    });

    clearTimeout(timeoutId);

    const data = await res.json();
    return {
      success: data.success ?? false,
      models: data.models ?? [],
      error: data.error,
    };
  } catch (err: any) {
    if (err.name === 'AbortError') {
      return { success: false, models: [], error: '请求超时 (20秒)' };
    }
    return {
      success: false,
      models: [],
      error: err.message || '网络请求失败',
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

  const [showAddForm, setShowAddForm] = useState(false);
  const [newProvider, setNewProvider] = useState<Partial<ModelProvider>>({
    name: '',
    type: 'openai',
    baseUrl: '',
    apiKey: '',
    models: [],
    enabled: true,
  });
  const [newModelInputs, setNewModelInputs] = useState<Record<string, string>>({});
  const [fetchingModels, setFetchingModels] = useState<Record<string, boolean>>({});
  const [fetchResults, setFetchResults] = useState<
    Record<string, { success: boolean; message: string }>
  >({});

  const getModelInput = (providerId: string) => newModelInputs[providerId] || '';
  const setModelInput = (providerId: string, value: string) => {
    setNewModelInputs((prev) => ({ ...prev, [providerId]: value }));
  };

  const handleAddModel = (providerId: string, model: string) => {
    const provider = providers.find((p) => p.id === providerId);
    if (!provider || !model.trim()) return;
    if (provider.models.includes(model.trim())) return;
    updateProvider(providerId, { models: [...provider.models, model.trim()] });
    setModelInput(providerId, '');
  };

  const handleRemoveModel = (providerId: string, model: string) => {
    const provider = providers.find((p) => p.id === providerId);
    if (!provider) return;
    updateProvider(providerId, { models: provider.models.filter((m) => m !== model) });
  };

  const handleFetchModels = async (providerId: string) => {
    const provider = providers.find((p) => p.id === providerId);
    if (!provider) return;

    setFetchingModels((prev) => ({ ...prev, [providerId]: true }));
    setFetchResults((prev) => ({ ...prev, [providerId]: { success: false, message: '' } }));

    const result = await fetchModels(provider.baseUrl, provider.apiKey);

    if (result.success && result.models.length > 0) {
      const existingSet = new Set(provider.models);
      const newModels = result.models.filter((m) => !existingSet.has(m));
      const merged = [...provider.models, ...newModels];
      updateProvider(providerId, { models: merged });
      setFetchResults((prev) => ({
        ...prev,
        [providerId]: { success: true, message: `获取成功！新增 ${newModels.length} 个模型，共 ${merged.length} 个` },
      }));
    } else {
      setFetchResults((prev) => ({
        ...prev,
        [providerId]: { success: false, message: result.error || '获取失败' },
      }));
    }

    setFetchingModels((prev) => ({ ...prev, [providerId]: false }));
    setTimeout(() => {
      setFetchResults((prev) => { const next = { ...prev }; delete next[providerId]; return next; });
    }, 5000);
  };

  const handleFetchForNewProvider = async () => {
    if (!newProvider.baseUrl) return;
    setFetchingModels((prev) => ({ ...prev, __new: true }));
    const result = await fetchModels(newProvider.baseUrl, newProvider.apiKey || '');
    if (result.success && result.models.length > 0) {
      setNewProvider((prev) => ({ ...prev, models: result.models }));
      setFetchResults((prev) => ({ ...prev, __new: { success: true, message: `获取到 ${result.models.length} 个模型` } }));
    } else {
      setFetchResults((prev) => ({ ...prev, __new: { success: false, message: result.error || '获取失败' } }));
    }
    setFetchingModels((prev) => ({ ...prev, __new: false }));
    setTimeout(() => {
      setFetchResults((prev) => { const next = { ...prev }; delete next.__new; return next; });
    }, 5000);
  };

  const handleAddProvider = () => {
    if (!newProvider.name?.trim() || !newProvider.baseUrl?.trim()) return;
    const id = newProvider.name.toLowerCase().replace(/\s+/g, '-');
    addProvider({ id, name: newProvider.name, type: newProvider.type as ModelProvider['type'], baseUrl: newProvider.baseUrl, apiKey: newProvider.apiKey || '', models: newProvider.models || [], enabled: true });
    setShowAddForm(false);
    setNewProvider({ name: '', type: 'openai', baseUrl: '', apiKey: '', models: [], enabled: true });
  };

  return (
    <div className="flex flex-col h-full bg-[var(--bg-primary)]">
      {/* Header */}
      <div className="flex items-center justify-between px-6 py-4 border-b border-[var(--hermes-border)]">
        <div className="flex items-center gap-3">
          <Layers size={20} className="text-[var(--hermes-accent)]" />
          <h1 className="text-lg font-semibold text-text-primary">模型管理</h1>
        </div>
        <button
          onClick={() => setShowAddForm(!showAddForm)}
          className="flex items-center gap-1 px-3 py-1.5 text-sm bg-[var(--hermes-accent)] text-white rounded-lg hover:opacity-90 transition-opacity"
        >
          <Plus size={14} /> 添加提供商
        </button>
      </div>

      <div className="flex-1 overflow-y-auto px-6 py-4 space-y-6">
        {/* Current model */}
        <div className="p-4 bg-[var(--bg-secondary)] border border-[var(--hermes-accent)] rounded-lg">
          <h2 className="text-sm font-medium text-text-primary mb-1">当前模型</h2>
          <p className="text-lg text-[var(--hermes-accent)] font-mono">{currentModel}</p>
          <p className="text-xs text-text-muted mt-1">
            提供商: {providers.find((p) => p.id === currentProvider)?.name || currentProvider}
          </p>
        </div>

        {/* Providers with full config */}
        {providers.map((provider) => (
          <div key={provider.id} className="rounded-lg border border-[var(--hermes-border)] overflow-hidden">
            {/* Provider header */}
            <div className="flex items-center justify-between px-4 py-3 bg-[var(--bg-secondary)]">
              <div className="flex items-center gap-3">
                <Server size={16} className="text-[var(--hermes-accent)]" />
                <div>
                  <h4 className="text-sm font-medium text-text-primary">{provider.name}</h4>
                  <p className="text-xs text-text-muted font-mono">{provider.baseUrl}</p>
                </div>
              </div>
              <div className="flex items-center gap-2">
                <button
                  onClick={() => updateProvider(provider.id, { enabled: !provider.enabled })}
                  className={`transition-colors ${provider.enabled ? 'text-[var(--hermes-accent)]' : 'text-text-muted'}`}
                >
                  {provider.enabled ? <ToggleRight size={24} /> : <ToggleLeft size={24} />}
                </button>
                {provider.id !== 'openai' && provider.id !== 'anthropic' && provider.id !== 'ollama' && (
                  <button
                    onClick={() => removeProvider(provider.id)}
                    className="p-1.5 rounded text-text-muted hover:text-red-500 transition-colors"
                  >
                    <Trash2 size={14} />
                  </button>
                )}
              </div>
            </div>

            {/* Provider config */}
            <div className="p-4 space-y-3">
              {/* Base URL */}
              <div>
                <label className="flex items-center gap-1.5 text-xs font-medium text-text-muted mb-1.5">
                  <Link size={12} /> API 地址
                </label>
                <input
                  type="text"
                  value={provider.baseUrl}
                  onChange={(e) => updateProvider(provider.id, { baseUrl: e.target.value })}
                  className="w-full bg-[var(--bg-primary)] text-text-primary text-sm rounded-lg px-3 py-2 outline-none border border-[var(--hermes-border)] focus:border-[var(--hermes-accent)] transition-colors font-mono"
                />
              </div>

              {/* API Key */}
              <div>
                <label className="flex items-center gap-1.5 text-xs font-medium text-text-muted mb-1.5">
                  <Key size={12} /> API Key
                </label>
                <input
                  type="password"
                  value={provider.apiKey}
                  onChange={(e) => updateProvider(provider.id, { apiKey: e.target.value })}
                  placeholder="sk-..."
                  className="w-full bg-[var(--bg-primary)] text-text-primary text-sm rounded-lg px-3 py-2 outline-none border border-[var(--hermes-border)] focus:border-[var(--hermes-accent)] transition-colors font-mono"
                />
              </div>

              {/* Fetch models button */}
              <button
                onClick={() => handleFetchModels(provider.id)}
                disabled={fetchingModels[provider.id] || !provider.baseUrl}
                className="flex items-center gap-2 w-full px-3 py-2 rounded-lg text-sm
                  bg-[var(--hermes-accent)]/10 text-[var(--hermes-accent)] border border-[var(--hermes-accent)]/20
                  hover:bg-[var(--hermes-accent)]/20 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              >
                {fetchingModels[provider.id] ? <Loader2 size={14} className="animate-spin" /> : <RefreshCw size={14} />}
                {fetchingModels[provider.id] ? '获取中...' : '🔍 自动获取模型'}
              </button>

              {/* Fetch result */}
              {fetchResults[provider.id] && (
                <div className={`flex items-center gap-2 px-3 py-2 rounded-lg text-xs ${
                  fetchResults[provider.id].success ? 'bg-green-500/10 text-green-400' : 'bg-red-500/10 text-red-400'
                }`}>
                  {fetchResults[provider.id].success ? <Check size={12} /> : <AlertCircle size={12} />}
                  {fetchResults[provider.id].message}
                </div>
              )}

              {/* Models */}
              <div>
                <label className="text-xs font-medium text-text-muted mb-1.5 block">
                  模型列表 {provider.models.length > 0 && `(${provider.models.length})`}
                </label>
                <div className="flex flex-wrap gap-1.5 mb-2">
                  {provider.models.map((model) => (
                    <span
                      key={model}
                      className={`inline-flex items-center gap-1 px-2 py-1 rounded-md text-xs cursor-pointer transition-colors ${
                        model === currentModel && provider.id === currentProvider
                          ? 'bg-[var(--hermes-accent)] text-white font-medium'
                          : 'bg-[var(--bg-tertiary)] text-text-secondary hover:bg-[var(--bg-surface)]'
                      }`}
                      onClick={() => setCurrentModel(model, provider.id)}
                    >
                      {model}
                      <button
                        onClick={(e) => { e.stopPropagation(); handleRemoveModel(provider.id, model); }}
                        className="ml-0.5 hover:text-red-400"
                      >
                        ×
                      </button>
                    </span>
                  ))}
                  {provider.models.length === 0 && (
                    <span className="text-xs text-text-muted italic">暂无模型，点击上方按钮自动获取</span>
                  )}
                </div>
                <div className="flex gap-2">
                  <input
                    type="text"
                    value={getModelInput(provider.id)}
                    onChange={(e) => setModelInput(provider.id, e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' && getModelInput(provider.id).trim()) {
                        handleAddModel(provider.id, getModelInput(provider.id));
                      }
                    }}
                    placeholder="手动添加模型..."
                    className="flex-1 bg-[var(--bg-primary)] text-text-primary text-xs rounded px-2 py-1.5 outline-none border border-[var(--hermes-border)] focus:border-[var(--hermes-accent)] transition-colors"
                  />
                  <button
                    onClick={() => {
                      const val = getModelInput(provider.id);
                      if (val.trim()) handleAddModel(provider.id, val);
                    }}
                    className="px-2 py-1 rounded text-xs bg-[var(--hermes-accent)] text-white hover:opacity-80 transition-opacity"
                  >
                    <Plus size={14} />
                  </button>
                </div>
              </div>
            </div>
          </div>
        ))}

        {/* Add new provider */}
        {showAddForm ? (
          <div className="rounded-lg border border-[var(--hermes-accent)]/30 p-4 space-y-3">
            <h4 className="text-sm font-medium text-text-primary">添加自定义模型提供商</h4>
            <input
              type="text"
              value={newProvider.name || ''}
              onChange={(e) => setNewProvider({ ...newProvider, name: e.target.value })}
              placeholder="名称（如 DeepSeek、硅基流动）"
              className="w-full bg-[var(--bg-primary)] text-text-primary text-sm rounded-lg px-3 py-2 outline-none border border-[var(--hermes-border)] focus:border-[var(--hermes-accent)]"
            />
            <input
              type="text"
              value={newProvider.baseUrl || ''}
              onChange={(e) => setNewProvider({ ...newProvider, baseUrl: e.target.value })}
              placeholder="API 地址（如 https://api.deepseek.com/v1）"
              className="w-full bg-[var(--bg-primary)] text-text-primary text-sm rounded-lg px-3 py-2 outline-none border border-[var(--hermes-border)] focus:border-[var(--hermes-accent)] font-mono"
            />
            <input
              type="password"
              value={newProvider.apiKey || ''}
              onChange={(e) => setNewProvider({ ...newProvider, apiKey: e.target.value })}
              placeholder="API Key"
              className="w-full bg-[var(--bg-primary)] text-text-primary text-sm rounded-lg px-3 py-2 outline-none border border-[var(--hermes-border)] focus:border-[var(--hermes-accent)] font-mono"
            />
            <button
              onClick={handleFetchForNewProvider}
              disabled={fetchingModels['__new'] || !newProvider.baseUrl}
              className="flex items-center gap-2 w-full px-3 py-2 rounded-lg text-sm
                bg-[var(--hermes-accent)]/10 text-[var(--hermes-accent)] border border-[var(--hermes-accent)]/20
                hover:bg-[var(--hermes-accent)]/20 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              {fetchingModels['__new'] ? <Loader2 size={14} className="animate-spin" /> : <RefreshCw size={14} />}
              {fetchingModels['__new'] ? '获取中...' : '🔍 自动获取模型'}
            </button>
            {fetchResults['__new'] && (
              <div className={`flex items-center gap-2 px-3 py-2 rounded-lg text-xs ${
                fetchResults['__new'].success ? 'bg-green-500/10 text-green-400' : 'bg-red-500/10 text-red-400'
              }`}>
                {fetchResults['__new'].success ? <Check size={12} /> : <AlertCircle size={12} />}
                {fetchResults['__new'].message}
              </div>
            )}
            {newProvider.models && newProvider.models.length > 0 && (
              <div className="flex flex-wrap gap-1">
                {newProvider.models.map((m) => (
                  <span key={m} className="px-2 py-0.5 rounded text-xs bg-[var(--bg-tertiary)] text-text-secondary">{m}</span>
                ))}
              </div>
            )}
            <div className="flex gap-2">
              <button onClick={handleAddProvider} className="px-4 py-2 rounded-lg text-sm bg-[var(--hermes-accent)] text-white hover:opacity-80 transition-opacity">添加</button>
              <button onClick={() => setShowAddForm(false)} className="px-4 py-2 rounded-lg text-sm text-text-muted hover:text-text-primary transition-colors">取消</button>
            </div>
          </div>
        ) : (
          <button
            onClick={() => setShowAddForm(true)}
            className="flex items-center justify-center gap-2 w-full px-4 py-3 rounded-lg border border-dashed border-[var(--hermes-border)] text-text-muted hover:border-[var(--hermes-accent)] hover:text-[var(--hermes-accent)] transition-colors text-sm"
          >
            <Plus size={16} />
            <span>添加自定义提供商</span>
          </button>
        )}
      </div>
    </div>
  );
}

export default ModelsPanel;
