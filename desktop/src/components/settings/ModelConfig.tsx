import React, { useState } from 'react';
import { useSettingsStore, ModelProvider } from '../../stores/settingsStore';
import {
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

// 从 API 获取可用模型列表
async function fetchModels(
  baseUrl: string,
  apiKey: string
): Promise<{ success: boolean; models: string[]; error?: string }> {
  try {
    // 标准化 base URL — 移除尾部斜杠和 /v1 后缀
    let url = baseUrl.replace(/\/+$/, '');
    if (url.endsWith('/v1')) {
      url = url.slice(0, -3);
    }
    // 确保有 /v1 前缀路径
    const modelsUrl = `${url}/v1/models`;

    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
    };
    if (apiKey) {
      headers['Authorization'] = `Bearer ${apiKey}`;
    }

    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 15000);

    const res = await fetch(modelsUrl, {
      method: 'GET',
      headers,
      signal: controller.signal,
    });

    clearTimeout(timeoutId);

    if (!res.ok) {
      const errorText = await res.text().catch(() => '');
      return {
        success: false,
        models: [],
        error: `HTTP ${res.status}: ${errorText || res.statusText}`,
      };
    }

    const data = await res.json();

    // OpenAI 格式: { data: [{ id: "model-name", ... }] }
    if (data.data && Array.isArray(data.data)) {
      const models = data.data
        .map((m: any) => m.id || m.name)
        .filter((m: any) => typeof m === 'string' && m.length > 0)
        .sort();
      return { success: true, models };
    }

    // 某些 API 返回数组格式: [{ id: "model-name" }]
    if (Array.isArray(data)) {
      const models = data
        .map((m: any) => (typeof m === 'string' ? m : m.id || m.name))
        .filter((m: any) => typeof m === 'string' && m.length > 0)
        .sort();
      return { success: true, models };
    }

    return { success: false, models: [], error: '无法解析模型列表格式' };
  } catch (err: any) {
    if (err.name === 'AbortError') {
      return { success: false, models: [], error: '请求超时 (15秒)' };
    }
    return {
      success: false,
      models: [],
      error: err.message || '网络请求失败',
    };
  }
}

export function ModelConfig() {
  const {
    providers,
    updateProvider,
    removeProvider,
    addProvider,
    currentModel,
    currentProvider,
    setCurrentModel,
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
  // 获取模型状态
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
    updateProvider(providerId, {
      models: [...provider.models, model.trim()],
    });
  };

  const handleRemoveModel = (providerId: string, model: string) => {
    const provider = providers.find((p) => p.id === providerId);
    if (!provider) return;
    updateProvider(providerId, {
      models: provider.models.filter((m) => m !== model),
    });
  };

  // 获取模型列表
  const handleFetchModels = async (providerId: string) => {
    const provider = providers.find((p) => p.id === providerId);
    if (!provider) return;

    setFetchingModels((prev) => ({ ...prev, [providerId]: true }));
    setFetchResults((prev) => ({
      ...prev,
      [providerId]: { success: false, message: '' },
    }));

    const result = await fetchModels(provider.baseUrl, provider.apiKey);

    if (result.success && result.models.length > 0) {
      // 合并新模型（去重）
      const existingSet = new Set(provider.models);
      const newModels = result.models.filter((m) => !existingSet.has(m));
      const merged = [...provider.models, ...newModels];

      updateProvider(providerId, { models: merged });
      setFetchResults((prev) => ({
        ...prev,
        [providerId]: {
          success: true,
          message: `获取成功！新增 ${newModels.length} 个模型，共 ${merged.length} 个`,
        },
      }));
    } else {
      setFetchResults((prev) => ({
        ...prev,
        [providerId]: {
          success: false,
          message: result.error || `获取失败，返回 ${result.models.length} 个模型`,
        },
      }));
    }

    setFetchingModels((prev) => ({ ...prev, [providerId]: false }));
    // 3秒后清除提示
    setTimeout(() => {
      setFetchResults((prev) => {
        const next = { ...prev };
        delete next[providerId];
        return next;
      });
    }, 5000);
  };

  // 新增提供商时也能获取模型
  const handleFetchForNewProvider = async () => {
    if (!newProvider.baseUrl) return;

    setFetchingModels((prev) => ({ ...prev, __new: true }));
    const result = await fetchModels(newProvider.baseUrl, newProvider.apiKey || '');

    if (result.success && result.models.length > 0) {
      setNewProvider((prev) => ({ ...prev, models: result.models }));
      setFetchResults((prev) => ({
        ...prev,
        __new: {
          success: true,
          message: `获取到 ${result.models.length} 个模型`,
        },
      }));
    } else {
      setFetchResults((prev) => ({
        ...prev,
        __new: { success: false, message: result.error || '获取失败' },
      }));
    }

    setFetchingModels((prev) => ({ ...prev, __new: false }));
    setTimeout(() => {
      setFetchResults((prev) => {
        const next = { ...prev };
        delete next.__new;
        return next;
      });
    }, 5000);
  };

  const handleAddProvider = () => {
    if (!newProvider.name?.trim() || !newProvider.baseUrl?.trim()) return;
    const id = newProvider.name.toLowerCase().replace(/\s+/g, '-');
    addProvider({
      id,
      name: newProvider.name,
      type: newProvider.type as ModelProvider['type'],
      baseUrl: newProvider.baseUrl,
      apiKey: newProvider.apiKey || '',
      models: newProvider.models || [],
      enabled: true,
    });
    setShowAddForm(false);
    setNewProvider({
      name: '',
      type: 'openai',
      baseUrl: '',
      apiKey: '',
      models: [],
      enabled: true,
    });
  };

  return (
    <div className="space-y-6">
      {/* Provider list */}
      {providers.map((provider) => (
        <div
          key={provider.id}
          className="rounded-lg border border-[var(--border)] overflow-hidden"
        >
          {/* Provider header */}
          <div className="flex items-center justify-between px-4 py-3 bg-[var(--bg-tertiary)]">
            <div className="flex items-center gap-3">
              <Server size={16} className="text-[var(--accent)]" />
              <div>
                <h4 className="text-sm font-medium text-[var(--text-primary)]">
                  {provider.name}
                </h4>
                <p className="text-xs text-[var(--text-muted)] font-mono">
                  {provider.baseUrl}
                </p>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <button
                onClick={() =>
                  updateProvider(provider.id, { enabled: !provider.enabled })
                }
                className={`transition-colors ${
                  provider.enabled
                    ? 'text-[var(--success)]'
                    : 'text-[var(--text-muted)]'
                }`}
              >
                {provider.enabled ? (
                  <ToggleRight size={24} />
                ) : (
                  <ToggleLeft size={24} />
                )}
              </button>
              {provider.id !== 'openai' &&
                provider.id !== 'anthropic' &&
                provider.id !== 'ollama' && (
                  <button
                    onClick={() => removeProvider(provider.id)}
                    className="p-1.5 rounded text-[var(--text-muted)] hover:text-[var(--error)] transition-colors"
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
              <label className="flex items-center gap-1.5 text-xs font-medium text-[var(--text-muted)] mb-1.5">
                <Link size={12} />
                API 地址
              </label>
              <input
                type="text"
                value={provider.baseUrl}
                onChange={(e) =>
                  updateProvider(provider.id, { baseUrl: e.target.value })
                }
                className="w-full bg-[var(--bg-primary)] text-[var(--text-primary)] text-sm rounded-lg px-3 py-2 outline-none border border-[var(--border)] focus:border-[var(--accent)] transition-colors font-mono"
              />
            </div>

            {/* API Key */}
            <div>
              <label className="flex items-center gap-1.5 text-xs font-medium text-[var(--text-muted)] mb-1.5">
                <Key size={12} />
                API Key
              </label>
              <input
                type="password"
                value={provider.apiKey}
                onChange={(e) =>
                  updateProvider(provider.id, { apiKey: e.target.value })
                }
                placeholder="sk-..."
                className="w-full bg-[var(--bg-primary)] text-[var(--text-primary)] text-sm rounded-lg px-3 py-2 outline-none border border-[var(--border)] focus:border-[var(--accent)] transition-colors font-mono"
              />
            </div>

            {/* 获取模型按钮 */}
            <button
              onClick={() => handleFetchModels(provider.id)}
              disabled={fetchingModels[provider.id] || !provider.baseUrl}
              className="flex items-center gap-2 w-full px-3 py-2 rounded-lg text-sm
                bg-[var(--accent)]/10 text-[var(--accent)] border border-[var(--accent)]/20
                hover:bg-[var(--accent)]/20 disabled:opacity-50 disabled:cursor-not-allowed
                transition-colors"
            >
              {fetchingModels[provider.id] ? (
                <Loader2 size={14} className="animate-spin" />
              ) : (
                <RefreshCw size={14} />
              )}
              {fetchingModels[provider.id] ? '获取中...' : '🔍 自动获取模型'}
            </button>

            {/* 获取结果提示 */}
            {fetchResults[provider.id] && (
              <div
                className={`flex items-center gap-2 px-3 py-2 rounded-lg text-xs ${
                  fetchResults[provider.id].success
                    ? 'bg-[var(--success)]/10 text-[var(--success)]'
                    : 'bg-[var(--error)]/10 text-[var(--error)]'
                }`}
              >
                {fetchResults[provider.id].success ? (
                  <Check size={12} />
                ) : (
                  <AlertCircle size={12} />
                )}
                {fetchResults[provider.id].message}
              </div>
            )}

            {/* Models */}
            <div>
              <label className="text-xs font-medium text-[var(--text-muted)] mb-1.5 block">
                模型列表 {provider.models.length > 0 && `(${provider.models.length})`}
              </label>
              <div className="flex flex-wrap gap-1.5 mb-2">
                {provider.models.map((model) => (
                  <span
                    key={model}
                    className={`
                      inline-flex items-center gap-1 px-2 py-1 rounded-md text-xs cursor-pointer transition-colors
                      ${
                        model === currentModel && provider.id === currentProvider
                          ? 'bg-[var(--accent)] text-[var(--bg-primary)] font-medium'
                          : 'bg-[var(--bg-tertiary)] text-[var(--text-secondary)] hover:bg-[var(--bg-surface)]'
                      }
                    `}
                    onClick={() => setCurrentModel(model, provider.id)}
                  >
                    {model}
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        handleRemoveModel(provider.id, model);
                      }}
                      className="ml-0.5 hover:text-[var(--error)]"
                    >
                      ×
                    </button>
                  </span>
                ))}
                {provider.models.length === 0 && (
                  <span className="text-xs text-[var(--text-muted)] italic">
                    暂无模型，点击上方按钮自动获取
                  </span>
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
                      setModelInput(provider.id, '');
                    }
                  }}
                  placeholder="手动添加模型..."
                  className="flex-1 bg-[var(--bg-primary)] text-[var(--text-primary)] text-xs rounded px-2 py-1.5 outline-none border border-[var(--border)] focus:border-[var(--accent)] transition-colors"
                />
                <button
                  onClick={() => {
                    const val = getModelInput(provider.id);
                    if (val.trim()) {
                      handleAddModel(provider.id, val);
                      setModelInput(provider.id, '');
                    }
                  }}
                  className="px-2 py-1 rounded text-xs bg-[var(--accent)] text-[var(--bg-primary)] hover:opacity-80 transition-opacity"
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
        <div className="rounded-lg border border-[var(--accent)]/30 p-4 space-y-3 fade-in">
          <h4 className="text-sm font-medium text-[var(--text-primary)]">
            添加自定义模型提供商
          </h4>
          <input
            type="text"
            value={newProvider.name || ''}
            onChange={(e) =>
              setNewProvider({ ...newProvider, name: e.target.value })
            }
            placeholder="名称（如 DeepSeek、硅基流动）"
            className="w-full bg-[var(--bg-primary)] text-[var(--text-primary)] text-sm rounded-lg px-3 py-2 outline-none border border-[var(--border)] focus:border-[var(--accent)]"
          />
          <input
            type="text"
            value={newProvider.baseUrl || ''}
            onChange={(e) =>
              setNewProvider({ ...newProvider, baseUrl: e.target.value })
            }
            placeholder="API 地址（如 https://api.deepseek.com）"
            className="w-full bg-[var(--bg-primary)] text-[var(--text-primary)] text-sm rounded-lg px-3 py-2 outline-none border border-[var(--border)] focus:border-[var(--accent)] font-mono"
          />
          <input
            type="password"
            value={newProvider.apiKey || ''}
            onChange={(e) =>
              setNewProvider({ ...newProvider, apiKey: e.target.value })
            }
            placeholder="API Key"
            className="w-full bg-[var(--bg-primary)] text-[var(--text-primary)] text-sm rounded-lg px-3 py-2 outline-none border border-[var(--border)] focus:border-[var(--accent)] font-mono"
          />

          {/* 获取模型按钮（新增时） */}
          <button
            onClick={handleFetchForNewProvider}
            disabled={fetchingModels['__new'] || !newProvider.baseUrl}
            className="flex items-center gap-2 w-full px-3 py-2 rounded-lg text-sm
              bg-[var(--accent)]/10 text-[var(--accent)] border border-[var(--accent)]/20
              hover:bg-[var(--accent)]/20 disabled:opacity-50 disabled:cursor-not-allowed
              transition-colors"
          >
            {fetchingModels['__new'] ? (
              <Loader2 size={14} className="animate-spin" />
            ) : (
              <RefreshCw size={14} />
            )}
            {fetchingModels['__new'] ? '获取中...' : '🔍 自动获取模型'}
          </button>

          {/* 新增时获取结果 */}
          {fetchResults['__new'] && (
            <div
              className={`flex items-center gap-2 px-3 py-2 rounded-lg text-xs ${
                fetchResults['__new'].success
                  ? 'bg-[var(--success)]/10 text-[var(--success)]'
                  : 'bg-[var(--error)]/10 text-[var(--error)]'
              }`}
            >
              {fetchResults['__new'].success ? (
                <Check size={12} />
              ) : (
                <AlertCircle size={12} />
              )}
              {fetchResults['__new'].message}
            </div>
          )}

          {/* 显示已获取的模型 */}
          {newProvider.models && newProvider.models.length > 0 && (
            <div className="flex flex-wrap gap-1">
              {newProvider.models.map((m) => (
                <span
                  key={m}
                  className="px-2 py-0.5 rounded text-xs bg-[var(--bg-tertiary)] text-[var(--text-secondary)]"
                >
                  {m}
                </span>
              ))}
            </div>
          )}

          <div className="flex gap-2">
            <button
              onClick={handleAddProvider}
              className="px-4 py-2 rounded-lg text-sm bg-[var(--accent)] text-[var(--bg-primary)] hover:opacity-80 transition-opacity"
            >
              添加
            </button>
            <button
              onClick={() => setShowAddForm(false)}
              className="px-4 py-2 rounded-lg text-sm text-[var(--text-muted)] hover:text-[var(--text-primary)] transition-colors"
            >
              取消
            </button>
          </div>
        </div>
      ) : (
        <button
          onClick={() => setShowAddForm(true)}
          className="flex items-center gap-2 w-full px-4 py-3 rounded-lg border border-dashed border-[var(--border)] text-[var(--text-muted)] hover:border-[var(--accent)] hover:text-[var(--accent)] transition-colors text-sm"
        >
          <Plus size={16} />
          <span>添加自定义提供商</span>
        </button>
      )}
    </div>
  );
}

export default ModelConfig;
