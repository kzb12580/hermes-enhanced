import React, { useState, useEffect, useCallback } from 'react';
import { Brain, Search, Trash2, Plus, RefreshCw } from 'lucide-react';
import { useSettingsStore } from '../../stores/settingsStore';

interface Memory {
  id: string;
  content: string;
  tags: string[];
  created_at: string;
}

export function MemoryPanel() {
  const { backendUrl, apiKey } = useSettingsStore();
  const [memories, setMemories] = useState<Memory[]>([]);
  const [loading, setLoading] = useState(false);
  const [searchKeyword, setSearchKeyword] = useState('');
  const [newMemory, setNewMemory] = useState('');
  const [newTags, setNewTags] = useState('');

  const headers = apiKey ? { 'Authorization': `Bearer ${apiKey}` } : {};

  const fetchMemories = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch(`${backendUrl}/api/memories`, { headers });
      const data = await res.json();
      setMemories(Array.isArray(data) ? data : []);
    } catch (e) {
      console.error('Failed to fetch memories:', e);
    } finally {
      setLoading(false);
    }
  }, [backendUrl, apiKey]);

  useEffect(() => { fetchMemories(); }, [fetchMemories]);

  const handleSearch = () => {
    if (!searchKeyword.trim()) {
      fetchMemories();
      return;
    }
    const keyword = searchKeyword.toLowerCase();
    setMemories(prev => prev.filter(m => 
      m.content.toLowerCase().includes(keyword) || 
      m.tags.some(t => t.toLowerCase().includes(keyword))
    ));
  };

  const handleSave = async () => {
    if (!newMemory.trim()) return;
    try {
      const tags = newTags.split(',').map(t => t.trim()).filter(Boolean);
      await fetch(`${backendUrl}/api/memories`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...headers },
        body: JSON.stringify({ content: newMemory, tags, source: 'user' }),
      });
      setNewMemory('');
      setNewTags('');
      fetchMemories();
    } catch (e) {
      console.error('Failed to save memory:', e);
    }
  };

  const handleDelete = async (id: string) => {
    try {
      await fetch(`${backendUrl}/api/memories/${id}`, {
        method: 'DELETE',
        headers,
      });
      fetchMemories();
    } catch (e) {
      console.error('Failed to delete memory:', e);
    }
  };

  return (
    <div className="flex flex-col h-full bg-[var(--bg-primary)]">
      <div className="flex items-center justify-between px-6 py-4 border-b border-[var(--hermes-border)]">
        <div className="flex items-center gap-3">
          <Brain size={20} className="text-[var(--hermes-accent)]" />
          <h1 className="text-lg font-semibold text-text-primary">记忆管理</h1>
          <span className="text-xs text-text-muted bg-[var(--bg-surface)] px-2 py-0.5 rounded-full">{memories.length} 条</span>
        </div>
        <button onClick={fetchMemories} className="flex items-center gap-1 px-3 py-1.5 text-sm text-text-secondary hover:text-text-primary hover:bg-[var(--bg-surface)] rounded-lg transition-colors">
          <RefreshCw size={14} className={loading ? 'animate-spin' : ''} /> 刷新
        </button>
      </div>

      <div className="px-6 py-4 border-b border-[var(--hermes-border)] space-y-3">
        <div className="flex gap-2">
          <input type="text" placeholder="搜索记忆..." value={searchKeyword} onChange={e => setSearchKeyword(e.target.value)} onKeyDown={e => e.key === 'Enter' && handleSearch()}
            className="flex-1 px-3 py-2 text-sm bg-[var(--bg-secondary)] border border-[var(--hermes-border)] rounded-lg focus:outline-none focus:border-[var(--hermes-accent)] text-text-primary" />
          <button onClick={handleSearch} className="px-3 py-2 text-sm bg-[var(--hermes-accent)] text-white rounded-lg hover:opacity-90"><Search size={16} /></button>
        </div>
        <div className="flex gap-2">
          <input type="text" placeholder="添加新记忆..." value={newMemory} onChange={e => setNewMemory(e.target.value)}
            className="flex-1 px-3 py-2 text-sm bg-[var(--bg-secondary)] border border-[var(--hermes-border)] rounded-lg focus:outline-none focus:border-[var(--hermes-accent)] text-text-primary" />
          <input type="text" placeholder="标签(逗号分隔)" value={newTags} onChange={e => setNewTags(e.target.value)}
            className="w-40 px-3 py-2 text-sm bg-[var(--bg-secondary)] border border-[var(--hermes-border)] rounded-lg focus:outline-none focus:border-[var(--hermes-accent)] text-text-primary" />
          <button onClick={handleSave} className="px-3 py-2 text-sm bg-[var(--hermes-accent)] text-white rounded-lg hover:opacity-90"><Plus size={16} /></button>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto px-6 py-4">
        {loading && memories.length === 0 ? (
          <div className="flex items-center justify-center h-full text-text-muted">加载中...</div>
        ) : memories.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full text-text-muted">
            <Brain size={48} className="mb-4 opacity-50" />
            <p className="text-sm">暂无记忆</p>
          </div>
        ) : (
          <div className="space-y-3">
            {memories.map(memory => (
              <div key={memory.id} className="p-4 bg-[var(--bg-secondary)] border border-[var(--hermes-border)] rounded-lg hover:border-[var(--hermes-accent)] transition-colors">
                <div className="flex items-start justify-between gap-3">
                  <div className="flex-1 min-w-0">
                    <p className="text-sm text-text-primary whitespace-pre-wrap break-words">{memory.content}</p>
                    <div className="flex items-center gap-2 mt-2">
                      {memory.tags.map((tag, i) => (
                        <span key={i} className="text-xs px-2 py-0.5 rounded-full bg-[var(--hermes-accent-subtle)] text-[var(--hermes-accent)]">{tag}</span>
                      ))}
                      <span className="text-xs text-text-muted">{new Date(memory.created_at).toLocaleString('zh-CN')}</span>
                    </div>
                  </div>
                  <button onClick={() => handleDelete(memory.id)} className="p-1.5 text-text-muted hover:text-red-500 hover:bg-red-50 rounded-lg" title="删除">
                    <Trash2 size={14} />
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

export default MemoryPanel;
