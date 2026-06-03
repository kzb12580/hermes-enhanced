import React, { useState } from 'react';
import { Layers, Plus, Trash2, Check } from 'lucide-react';
import { useSettingsStore, type ModelProvider } from '../../stores/settingsStore';

export function ModelsPanel() {
  const { providers, currentModel, currentProvider, setCurrentModel, addProvider, removeProvider } = useSettingsStore();
  const [showAdd, setShowAdd] = useState(false);
  const [newProvider, setNewProvider] = useState<Partial<ModelProvider>>({
    type: 'openai',
    baseUrl: '',
    apiKey: '',
    models: [],
  });

  const allModels = providers.flatMap(p => 
    p.models.map(m => ({ model: m, provider: p.id, providerName: p.name }))
  );

  return (
    <div className="flex flex-col h-full bg-[var(--bg-primary)]">
      <div className="flex items-center justify-between px-6 py-4 border-b border-[var(--hermes-border)]">
        <div className="flex items-center gap-3">
          <Layers size={20} className="text-[var(--hermes-accent)]" />
          <h1 className="text-lg font-semibold text-text-primary">模型管理</h1>
        </div>
        <button onClick={() => setShowAdd(!showAdd)} className="flex items-center gap-1 px-3 py-1.5 text-sm bg-[var(--hermes-accent)] text-white rounded-lg hover:opacity-90">
          <Plus size={14} /> 添加提供商
        </button>
      </div>

      <div className="flex-1 overflow-y-auto px-6 py-4 space-y-6">
        {/* Current model */}
        <div className="p-4 bg-[var(--bg-secondary)] border border-[var(--hermes-accent)] rounded-lg">
          <h2 className="text-sm font-medium text-text-primary mb-2">当前模型</h2>
          <p className="text-lg text-[var(--hermes-accent)]">{currentModel}</p>
          <p className="text-xs text-text-muted mt-1">提供商: {providers.find(p => p.id === currentProvider)?.name || currentProvider}</p>
        </div>

        {/* Model list */}
        <div>
          <h2 className="text-sm font-medium text-text-primary mb-3">可用模型</h2>
          <div className="space-y-2">
            {allModels.map(({ model, provider, providerName }) => (
              <button
                key={`${provider}-${model}`}
                onClick={() => setCurrentModel(model, provider)}
                className={`flex items-center justify-between w-full p-3 rounded-lg border transition-colors ${
                  currentModel === model && currentProvider === provider
                    ? 'border-[var(--hermes-accent)] bg-[var(--hermes-accent-subtle)]'
                    : 'border-[var(--hermes-border)] hover:border-[var(--hermes-accent)]'
                }`}
              >
                <div>
                  <p className="text-sm text-text-primary">{model}</p>
                  <p className="text-xs text-text-muted">{providerName}</p>
                </div>
                {currentModel === model && currentProvider === provider && (
                  <Check size={16} className="text-[var(--hermes-accent)]" />
                )}
              </button>
            ))}
          </div>
        </div>

        {/* Providers */}
        <div>
          <h2 className="text-sm font-medium text-text-primary mb-3">提供商配置</h2>
          <div className="space-y-3">
            {providers.map((p) => (
              <div key={p.id} className="p-4 bg-[var(--bg-secondary)] border border-[var(--hermes-border)] rounded-lg">
                <div className="flex items-center justify-between mb-2">
                  <h3 className="text-sm font-medium text-text-primary">{p.name}</h3>
                  <button onClick={() => removeProvider(p.id)} className="p-1 text-text-muted hover:text-red-500">
                    <Trash2 size={14} />
                  </button>
                </div>
                <p className="text-xs text-text-muted">类型: {p.type} | 模型数: {p.models.length}</p>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

export default ModelsPanel;
