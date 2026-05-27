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
} from 'lucide-react';

export function ModelConfig() {
  const { providers, updateProvider, removeProvider, addProvider, currentModel, currentProvider, setCurrentModel } =
    useSettingsStore();

  const [showAddForm, setShowAddForm] = useState(false);
  const [newProvider, setNewProvider] = useState<Partial<ModelProvider>>({
    name: '',
    type: 'openai',
    baseUrl: '',
    apiKey: '',
    models: [],
    enabled: true,
  });
  // Per-provider model input state (fixes shared state across providers)
  const [newModelInputs, setNewModelInputs] = useState<Record<string, string>>({});

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
    setNewProvider({ name: '', type: 'openai', baseUrl: '', apiKey: '', models: [], enabled: true });
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
                <p className="text-xs text-[var(--text-muted)]">{provider.baseUrl}</p>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <button
                onClick={() => updateProvider(provider.id, { enabled: !provider.enabled })}
                className={`transition-colors ${
                  provider.enabled ? 'text-[var(--success)]' : 'text-[var(--text-muted)]'
                }`}
              >
                {provider.enabled ? <ToggleRight size={24} /> : <ToggleLeft size={24} />}
              </button>
              {provider.id !== 'openai' && provider.id !== 'anthropic' && provider.id !== 'ollama' && (
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
                onChange={(e) => updateProvider(provider.id, { baseUrl: e.target.value })}
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
                onChange={(e) => updateProvider(provider.id, { apiKey: e.target.value })}
                placeholder="sk-..."
                className="w-full bg-[var(--bg-primary)] text-[var(--text-primary)] text-sm rounded-lg px-3 py-2 outline-none border border-[var(--border)] focus:border-[var(--accent)] transition-colors font-mono"
              />
            </div>

            {/* Models */}
            <div>
              <label className="text-xs font-medium text-[var(--text-muted)] mb-1.5 block">
                模型列表
              </label>
              <div className="flex flex-wrap gap-1.5 mb-2">
                {provider.models.map((model) => (
                  <span
                    key={model}
                    className={`
                      inline-flex items-center gap-1 px-2 py-1 rounded-md text-xs cursor-pointer transition-colors
                      ${model === currentModel && provider.id === currentProvider
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
                  placeholder="添加新模型..."
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
          <h4 className="text-sm font-medium text-[var(--text-primary)]">添加自定义模型提供商</h4>
          <input
            type="text"
            value={newProvider.name || ''}
            onChange={(e) => setNewProvider({ ...newProvider, name: e.target.value })}
            placeholder="名称（如 OpenAI Compatible）"
            className="w-full bg-[var(--bg-primary)] text-[var(--text-primary)] text-sm rounded-lg px-3 py-2 outline-none border border-[var(--border)] focus:border-[var(--accent)]"
          />
          <input
            type="text"
            value={newProvider.baseUrl || ''}
            onChange={(e) => setNewProvider({ ...newProvider, baseUrl: e.target.value })}
            placeholder="API 地址"
            className="w-full bg-[var(--bg-primary)] text-[var(--text-primary)] text-sm rounded-lg px-3 py-2 outline-none border border-[var(--border)] focus:border-[var(--accent)] font-mono"
          />
          <input
            type="password"
            value={newProvider.apiKey || ''}
            onChange={(e) => setNewProvider({ ...newProvider, apiKey: e.target.value })}
            placeholder="API Key（可选）"
            className="w-full bg-[var(--bg-primary)] text-[var(--text-primary)] text-sm rounded-lg px-3 py-2 outline-none border border-[var(--border)] focus:border-[var(--accent)] font-mono"
          />
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
