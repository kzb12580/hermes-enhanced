import React, { useState, useEffect, useCallback } from 'react';
import { Clock, RefreshCw, Trash2, MessageSquare } from 'lucide-react';
import { useSettingsStore } from '../../stores/settingsStore';

interface Session {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
  message_count: number;
}

export function SessionsPanel() {
  const { backendUrl, apiKey } = useSettingsStore();
  const [sessions, setSessions] = useState<Session[]>([]);
  const [loading, setLoading] = useState(false);

  const headers = apiKey ? { 'Authorization': `Bearer ${apiKey}` } : {};

  const fetchSessions = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch(`${backendUrl}/api/chat/sessions`, { headers });
      const data = await res.json();
      setSessions(Array.isArray(data) ? data : []);
    } catch (e) {
      console.error('Failed to fetch sessions:', e);
    } finally {
      setLoading(false);
    }
  }, [backendUrl, apiKey]);

  useEffect(() => { fetchSessions(); }, [fetchSessions]);

  const deleteSession = async (id: string) => {
    try {
      await fetch(`${backendUrl}/api/chat/sessions/${id}`, {
        method: 'DELETE',
        headers,
      });
      fetchSessions();
    } catch (e) {
      console.error('Failed to delete session:', e);
    }
  };

  return (
    <div className="flex flex-col h-full bg-[var(--bg-primary)]">
      <div className="flex items-center justify-between px-6 py-4 border-b border-[var(--hermes-border)]">
        <div className="flex items-center gap-3">
          <Clock size={20} className="text-[var(--hermes-accent)]" />
          <h1 className="text-lg font-semibold text-text-primary">历史会话</h1>
          <span className="text-xs text-text-muted bg-[var(--bg-surface)] px-2 py-0.5 rounded-full">{sessions.length} 个</span>
        </div>
        <button onClick={fetchSessions} className="flex items-center gap-1 px-3 py-1.5 text-sm text-text-secondary hover:text-text-primary hover:bg-[var(--bg-surface)] rounded-lg transition-colors">
          <RefreshCw size={14} className={loading ? 'animate-spin' : ''} /> 刷新
        </button>
      </div>

      <div className="flex-1 overflow-y-auto px-6 py-4">
        {sessions.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full text-text-muted">
            <Clock size={48} className="mb-4 opacity-50" />
            <p className="text-sm">暂无历史会话</p>
          </div>
        ) : (
          <div className="space-y-3">
            {sessions.map(session => (
              <div key={session.id} className="p-4 bg-[var(--bg-secondary)] border border-[var(--hermes-border)] rounded-lg hover:border-[var(--hermes-accent)] transition-colors">
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center gap-2">
                    <MessageSquare size={14} className="text-[var(--hermes-accent)]" />
                    <h3 className="text-sm font-medium text-text-primary">{session.title || session.id}</h3>
                  </div>
                  <button onClick={() => deleteSession(session.id)} className="p-1.5 text-text-muted hover:text-red-500 hover:bg-red-50 rounded-lg">
                    <Trash2 size={14} />
                  </button>
                </div>
                <p className="text-xs text-text-muted">{new Date(session.updated_at).toLocaleString('zh-CN')}</p>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

export default SessionsPanel;
