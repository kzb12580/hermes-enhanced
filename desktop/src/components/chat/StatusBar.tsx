import React, { useState, useEffect, useRef } from 'react';
import { useSystemStore } from '../../stores/systemStore';
import { useSettingsStore } from '../../stores/settingsStore';
import { useChatStore } from '../../stores/chatStore';
import { Cpu, Database, Zap, Terminal, X, Trash2, Copy, Check } from 'lucide-react';

export function StatusBar() {
  const { isBackendOnline } = useSystemStore();
  const { connectionMode, currentModel } = useSettingsStore();
  const { currentMessages, isGenerating } = useChatStore();

  const [showLogModal, setShowLogModal] = useState(false);
  const [logs, setLogs] = useState<string[]>([]);
  const [copied, setCopied] = useState(false);
  const logEndRef = useRef<HTMLDivElement>(null);

  const messages = currentMessages();
  const totalChars = messages.reduce((acc, m) => acc + (m.content?.length || 0), 0);
  const estimatedTokens = Math.round(totalChars / 3.5);
  const maxContext = 128000;
  const contextPercentage = Math.min(100, Math.max(0, Math.round((estimatedTokens / maxContext) * 100)));

  // 获取实时日志
  useEffect(() => {
    const fetchLogs = async () => {
      const api = window.api;
      if (api?.python?.getLogs) {
        try {
          const res = await api.python.getLogs();
          if (res?.data) {
            setLogs(res.data);
          }
        } catch { /* ignore */ }
      }
    };

    if (showLogModal) {
      fetchLogs();
      const timer = setInterval(fetchLogs, 1500);
      return () => clearInterval(timer);
    }
  }, [showLogModal]);

  // 监听 IPC 实时日志流
  useEffect(() => {
    const api = window.api;
    if (api?.python?.onLogStream) {
      const cleanup = api.python.onLogStream((data: any) => {
        const line = typeof data === 'string' ? data : (data?.data || JSON.stringify(data));
        setLogs((prev) => [...prev.slice(-499), line]);
      });
      return cleanup;
    }
  }, []);

  // 自动滚动到最新日志
  useEffect(() => {
    if (showLogModal) {
      logEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    }
  }, [logs, showLogModal]);

  const handleCopyLogs = () => {
    navigator.clipboard.writeText(logs.join('\n'));
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <>
      <div className="h-6 px-3 bg-[var(--bg-secondary)] border-t border-[var(--hermes-border)] flex items-center justify-between text-[11px] text-text-muted select-none">
        {/* Left: Backend & Connection Status */}
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-1.5" title={isBackendOnline ? '服务在线' : '服务连接异常'}>
            {isBackendOnline ? (
              <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
            ) : (
              <span className="w-2 h-2 rounded-full bg-rose-500" />
            )}
            <span className="font-medium text-text-secondary">
              {connectionMode === 'remote' ? '🌐 远程 Gateway' : '🖥️ 本地后端'}
            </span>
            <span className="text-[10px] text-text-muted/80">
              {isBackendOnline ? '已连接' : '离线'}
            </span>
          </div>

          <div className="w-[1px] h-3 bg-[var(--hermes-border)]" />

          {/* Model info */}
          <div className="flex items-center gap-1">
            <Cpu size={12} className="text-text-muted" />
            <span className="font-mono text-text-secondary">{currentModel}</span>
          </div>

          <div className="w-[1px] h-3 bg-[var(--hermes-border)]" />

          {/* Real-time Logs trigger button */}
          <button
            onClick={() => setShowLogModal(true)}
            className="flex items-center gap-1 hover:text-text-primary px-1 py-0.5 rounded hover:bg-[var(--bg-tertiary)] transition-colors cursor-pointer"
            title="查看实时运行日志 (排查错误)"
          >
            <Terminal size={11} className="text-[var(--hermes-accent)]" />
            <span>运行日志</span>
          </button>
        </div>

        {/* Right: Context & Activity info */}
        <div className="flex items-center gap-3">
          {isGenerating && (
            <div className="flex items-center gap-1 text-[var(--hermes-accent)] animate-pulse">
              <Zap size={11} />
              <span>执行中...</span>
            </div>
          )}

          {/* Context usage meter */}
          <div
            className="flex items-center gap-1.5 cursor-pointer hover:text-text-primary transition-colors"
            title={`当前会话估算消耗: ~${estimatedTokens.toLocaleString()} tokens (${contextPercentage}%)`}
          >
            <Database size={11} />
            <span>上下文:</span>
            <div className="w-16 h-1.5 bg-[var(--bg-tertiary)] rounded-full overflow-hidden flex">
              <div
                className={`h-full transition-all duration-300 ${
                  contextPercentage > 80
                    ? 'bg-rose-500'
                    : contextPercentage > 50
                    ? 'bg-amber-500'
                    : 'bg-[var(--hermes-accent)]'
                }`}
                style={{ width: `${Math.max(4, contextPercentage)}%` }}
              />
            </div>
            <span className="font-mono text-[10px]">{contextPercentage}%</span>
          </div>
        </div>
      </div>

      {/* Log Modal */}
      {showLogModal && (
        <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-xs flex items-center justify-center p-4">
          <div className="bg-[var(--bg-primary)] border border-[var(--hermes-border)] rounded-xl w-full max-w-3xl h-[80vh] flex flex-col shadow-2xl overflow-hidden">
            {/* Modal Header */}
            <div className="flex items-center justify-between px-4 py-3 border-b border-[var(--hermes-border)] bg-[var(--bg-secondary)]">
              <div className="flex items-center gap-2">
                <Terminal size={16} className="text-[var(--hermes-accent)]" />
                <h3 className="text-sm font-semibold text-text-primary">实时运行与错误日志</h3>
                <span className="text-xs text-text-muted">({logs.length} 行)</span>
              </div>
              <div className="flex items-center gap-2">
                <button
                  onClick={handleCopyLogs}
                  className="flex items-center gap-1 px-2.5 py-1 text-xs rounded border border-[var(--hermes-border)] text-text-secondary hover:text-text-primary hover:bg-[var(--bg-tertiary)] transition-colors"
                  title="复制全部日志"
                >
                  {copied ? <Check size={12} className="text-emerald-500" /> : <Copy size={12} />}
                  <span>{copied ? '已复制' : '复制'}</span>
                </button>
                <button
                  onClick={() => setLogs([])}
                  className="flex items-center gap-1 px-2.5 py-1 text-xs rounded border border-[var(--hermes-border)] text-text-secondary hover:text-rose-500 hover:bg-[var(--bg-tertiary)] transition-colors"
                  title="清空当前日志显示"
                >
                  <Trash2 size={12} />
                  <span>清空</span>
                </button>
                <button
                  onClick={() => setShowLogModal(false)}
                  className="p-1 rounded text-text-muted hover:text-text-primary hover:bg-[var(--bg-tertiary)] transition-colors"
                  title="关闭"
                >
                  <X size={16} />
                </button>
              </div>
            </div>

            {/* Modal Log Content */}
            <div className="flex-1 p-4 overflow-y-auto font-mono text-xs bg-black/40 text-text-secondary space-y-1 select-text">
              {logs.length === 0 ? (
                <div className="flex items-center justify-center h-full text-text-muted">
                  暂无运行日志输出
                </div>
              ) : (
                logs.map((log, idx) => {
                  const isError = log.includes('❌') || log.includes('ERROR') || log.includes('error') || log.includes('Traceback');
                  const isSuccess = log.includes('✅') || log.includes('SUCCESS');
                  return (
                    <div
                      key={idx}
                      className={`leading-relaxed whitespace-pre-wrap break-all ${
                        isError
                          ? 'text-rose-400 bg-rose-500/10 px-1.5 py-0.5 rounded'
                          : isSuccess
                          ? 'text-emerald-400'
                          : 'text-text-secondary'
                      }`}
                    >
                      {log}
                    </div>
                  );
                })
              )}
              <div ref={logEndRef} />
            </div>

            {/* Modal Footer */}
            <div className="px-4 py-2 border-t border-[var(--hermes-border)] bg-[var(--bg-secondary)] flex items-center justify-between text-xs text-text-muted">
              <span>日志文件持久化保存在: <code>~/.hermes/desktop/logs/python-backend.log</code></span>
              <button
                onClick={() => setShowLogModal(false)}
                className="px-3 py-1 rounded bg-[var(--hermes-accent)] text-white text-xs font-medium hover:opacity-90 transition-opacity"
              >
                完成
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}

export default StatusBar;
