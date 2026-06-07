import React, { useState, useEffect, useCallback } from 'react';
import { Wrench, RefreshCw, Check, X } from 'lucide-react';
import { useSettingsStore } from '../../stores/settingsStore';

interface Tool {
  name: string;
  description: string;
  enabled: boolean;
}

export function ToolsPanel() {
  const { backendUrl, apiKey } = useSettingsStore();
  const [tools, setTools] = useState<Tool[]>([]);
  const [loading, setLoading] = useState(false);

  const headers: Record<string, string> = apiKey ? { Authorization: `Bearer ${apiKey}` } : {};

  const fetchTools = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch(`${backendUrl}/api/chat/tools`, { headers });
      const data = await res.json();
      setTools(Array.isArray(data) ? data : data.tools || []);
    } catch (e) {
      console.error('Failed to fetch tools:', e);
    } finally {
      setLoading(false);
    }
  }, [backendUrl, apiKey]);

  useEffect(() => { fetchTools(); }, [fetchTools]);

  return (
    <div className="flex flex-col h-full bg-[var(--bg-primary)]">
      <div className="flex items-center justify-between px-6 py-4 border-b border-[var(--hermes-border)]">
        <div className="flex items-center gap-3">
          <Wrench size={20} className="text-[var(--hermes-accent)]" />
          <h1 className="text-lg font-semibold text-text-primary">工具管理</h1>
          <span className="text-xs text-text-muted bg-[var(--bg-surface)] px-2 py-0.5 rounded-full">{tools.length} 个</span>
        </div>
        <button onClick={fetchTools} className="flex items-center gap-1 px-3 py-1.5 text-sm text-text-secondary hover:text-text-primary hover:bg-[var(--bg-surface)] rounded-lg transition-colors">
          <RefreshCw size={14} className={loading ? 'animate-spin' : ''} /> 刷新
        </button>
      </div>

      <div className="flex-1 overflow-y-auto px-6 py-4">
        {loading && tools.length === 0 ? (
          <div className="flex items-center justify-center h-full text-text-muted">加载中...</div>
        ) : tools.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full text-text-muted">
            <Wrench size={48} className="mb-4 opacity-50" />
            <p className="text-sm">暂无工具</p>
          </div>
        ) : (
          <div className="space-y-3">
            {tools.map(tool => (
              <div key={tool.name} className="p-4 bg-[var(--bg-secondary)] border border-[var(--hermes-border)] rounded-lg">
                <div className="flex items-center gap-2 mb-1">
                  <h3 className="text-sm font-medium text-text-primary">{tool.name}</h3>
                  {tool.enabled !== false && <span className="text-xs px-1.5 py-0.5 rounded-full bg-green-100 text-green-700">启用</span>}
                </div>
                <p className="text-xs text-text-muted">{tool.description}</p>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

export default ToolsPanel;
