import React, { useState } from 'react';
import { KeyRound, Plus, Save, Trash2 } from 'lucide-react';
import { useSettingsStore, type ModelProvider } from '../../stores/settingsStore';

export function ProvidersPanel() {
  const { providers, addProvider, updateProvider, removeProvider } = useSettingsStore();
  const [editing, setEditing] = useState<string | null>(null);
  const [form, setForm] = useState({ name: '', type: 'openai' as ModelProvider['type'], baseUrl: '', apiKey: '', models: '' });

  const handleSave = () => {
    const models = form.models.split(',').map(m => m.trim()).filter(Boolean);
    if (editing) {
      updateProvider(editing, { ...form, models });
    } else {
      addProvider({ id: Date.now().toString(), ...form, models, enabled: true });
    }
    setEditing(null);
    setForm({ name: '', type: 'openai', baseUrl: '', apiKey: '', models: '' });
  };

  return (
    <div className="flex flex-col h-full bg-[var(--bg-primary)]">
      <div className="flex items-center justify-between px-6 py-4 border-b border-[var(--hermes-border)]">
        <div className="flex items-center gap-3">
          <KeyRound size={20} className="text-[var(--hermes-accent)]" />
          <h1 className="text-lg font-semibold text-text-primary">提供商管理</h1>
        </div>
        <button onClick={() => setEditing('new')} className="flex items-center gap-1 px-3 py-1.5 text-sm bg-[var(--hermes-accent)] text-white rounded-lg hover:opacity-90">
          <Plus size={14} /> 添加
        </button>
      </div>

      <div className="flex-1 overflow-y-auto px-6 py-4 space-y-4">
        {providers.map((p) => (
          <div key={p.id} className="p-4 bg-[var(--bg-secondary)] border border-[var(--hermes-border)] rounded-lg">
            <div className="flex items-center justify-between mb-2">
              <h3 className="text-sm font-medium text-text-primary">{p.name}</h3>
              <div className="flex gap-2">
                <button onClick={() => { setEditing(p.id); setForm({ name: p.name, type: p.type, baseUrl: p.baseUrl, apiKey: p.apiKey, models: p.models.join(',') }); }} className="text-xs text-[var(--hermes-accent)] hover:underline">编辑</button>
                <button onClick={() => removeProvider(p.id)} className="text-xs text-red-500 hover:underline">删除</button>
              </div>
            </div>
            <p className="text-xs text-text-muted">{p.baseUrl}</p>
            <p className="text-xs text-text-muted mt-1">模型: {p.models.join(', ')}</p>
          </div>
        ))}

        {editing && (
          <div className="p-4 bg-[var(--bg-secondary)] border border-[var(--hermes-accent)] rounded-lg space-y-3">
            <input type="text" placeholder="名称" value={form.name} onChange={e => setForm({ ...form, name: e.target.value })} className="w-full px-3 py-2 text-sm bg-[var(--bg-primary)] border border-[var(--hermes-border)] rounded-lg" />
            <select value={form.type} onChange={e => setForm({ ...form, type: e.target.value as ModelProvider['type'] })} className="w-full px-3 py-2 text-sm bg-[var(--bg-primary)] border border-[var(--hermes-border)] rounded-lg">
              <option value="openai">OpenAI</option>
              <option value="anthropic">Anthropic</option>
              <option value="ollama">Ollama</option>
              <option value="custom">自定义</option>
            </select>
            <input type="text" placeholder="Base URL" value={form.baseUrl} onChange={e => setForm({ ...form, baseUrl: e.target.value })} className="w-full px-3 py-2 text-sm bg-[var(--bg-primary)] border border-[var(--hermes-border)] rounded-lg" />
            <input type="password" placeholder="API Key" value={form.apiKey} onChange={e => setForm({ ...form, apiKey: e.target.value })} className="w-full px-3 py-2 text-sm bg-[var(--bg-primary)] border border-[var(--hermes-border)] rounded-lg" />
            <input type="text" placeholder="模型(逗号分隔)" value={form.models} onChange={e => setForm({ ...form, models: e.target.value })} className="w-full px-3 py-2 text-sm bg-[var(--bg-primary)] border border-[var(--hermes-border)] rounded-lg" />
            <div className="flex gap-2">
              <button onClick={handleSave} className="flex items-center gap-1 px-3 py-2 text-sm bg-[var(--hermes-accent)] text-white rounded-lg"><Save size={14} /> 保存</button>
              <button onClick={() => setEditing(null)} className="px-3 py-2 text-sm text-text-muted hover:text-text-primary">取消</button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

export default ProvidersPanel;
