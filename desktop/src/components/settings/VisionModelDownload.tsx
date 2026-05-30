import React, { useState, useEffect } from 'react';
import { Download, Loader2, CheckCircle, AlertCircle, RefreshCw, Trash2, HardDrive } from 'lucide-react';

const BACKEND = 'http://127.0.0.1:9876';

const MIRRORS = [
  { key: 'hf-mirror', label: 'hf-mirror（国内推荐）', note: '' },
  { key: 'modelscope', label: 'ModelScope（阿里）', note: '' },
  { key: 'official', label: 'HuggingFace 官方', note: '需 TUN' },
];

export function VisionModelDownload() {
  const [mirror, setMirror] = useState('hf-mirror');
  const [downloading, setDownloading] = useState(false);
  const [progress, setProgress] = useState(0);
  const [status, setStatus] = useState('');
  const [done, setDone] = useState(false);
  const [error, setError] = useState('');
  const [modelExists, setModelExists] = useState<boolean | null>(null);
  const [checking, setChecking] = useState(true);

  // Check if model exists on mount
  useEffect(() => {
    checkModel();
  }, []);

  const checkModel = async () => {
    setChecking(true);
    try {
      const res = await fetch(`${BACKEND}/api/setup/model-status`);
      const data = await res.json();
      setModelExists(data.exists);
      if (data.exists) setDone(true);
    } catch {
      setModelExists(false);
    }
    setChecking(false);
  };

  const startDownload = async () => {
    setDownloading(true);
    setProgress(0);
    setStatus('正在准备下载...');
    setError('');

    try {
      const res = await fetch(`${BACKEND}/api/setup/download-model`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ mirror }),
      });
      const data = await res.json();

      if (data.success) {
        const es = new EventSource(`${BACKEND}/api/setup/status/stream`);
        es.onmessage = (ev) => {
          try {
            const d = JSON.parse(ev.data);
            if (d.progress) setProgress(d.progress);
            if (d.message) setStatus(d.message);
            if (d.phase === 'done') {
              setDone(true);
              setDownloading(false);
              setModelExists(true);
              es.close();
            }
            if (d.phase === 'error') {
              setDownloading(false);
              setError(d.error || d.message || '下载失败');
              es.close();
            }
          } catch {}
        };
        es.onerror = () => {
          es.close();
          setDownloading(false);
          setError('连接中断');
        };
      } else {
        setDownloading(false);
        setError(data.error || data.detail || '启动下载失败');
      }
    } catch {
      setDownloading(false);
      setError('请求失败');
    }
  };

  const deleteModel = async () => {
    if (!confirm('确定删除视觉模型？(~6GB)')) return;
    try {
      await fetch(`${BACKEND}/api/setup/delete-model`, { method: 'DELETE' });
      setModelExists(false);
      setDone(false);
      setProgress(0);
      setStatus('');
    } catch {
      setError('删除失败');
    }
  };

  if (checking) {
    return (
      <div className="flex items-center gap-2 text-[var(--text-muted)] text-sm py-4">
        <Loader2 size={14} className="animate-spin" />
        检查模型状态...
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2 mb-2">
        <HardDrive size={16} className="text-[var(--accent)]" />
        <h3 className="text-sm font-medium text-[var(--text-primary)]">视觉模型（可选）</h3>
      </div>

      <p className="text-xs text-[var(--text-muted)]">
        LocateAnything-3B (~6GB) 用于屏幕元素识别和 GUI 自动化。
        如果只需要聊天和办公功能，可以不下载。
      </p>

      {/* Model status */}
      {modelExists ? (
        <div className="flex items-center justify-between p-3 rounded-lg bg-[var(--success)]/10 border border-[var(--success)]/20">
          <div className="flex items-center gap-2">
            <CheckCircle size={16} className="text-[var(--success)]" />
            <span className="text-sm text-[var(--success)]">模型已安装</span>
          </div>
          <button
            onClick={deleteModel}
            className="flex items-center gap-1 px-2 py-1 rounded text-xs text-[var(--error)] hover:bg-[var(--error)]/10 transition-colors"
          >
            <Trash2 size={12} /> 删除
          </button>
        </div>
      ) : (
        <>
          {/* Mirror selection */}
          <div>
            <label className="text-xs font-medium text-[var(--text-muted)] mb-1.5 block">下载源</label>
            <div className="flex gap-2 flex-wrap">
              {MIRRORS.map(m => (
                <button
                  key={m.key}
                  onClick={() => setMirror(m.key)}
                  disabled={downloading}
                  className={`px-3 py-1.5 rounded-full text-xs transition-colors ${
                    mirror === m.key
                      ? 'bg-[var(--accent)] text-white'
                      : 'bg-[var(--bg-tertiary)] text-[var(--text-muted)] hover:text-[var(--text-primary)]'
                  } ${downloading ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer'}`}
                >
                  {m.label} {m.note && <span className="text-[var(--warning)]">({m.note})</span>}
                </button>
              ))}
            </div>
          </div>

          {/* Progress */}
          {downloading && (
            <div>
              <div className="h-2 rounded-full bg-[var(--bg-tertiary)] overflow-hidden">
                <div
                  className="h-full rounded-full bg-gradient-to-r from-[var(--accent)] to-purple-500 transition-all duration-300"
                  style={{ width: `${progress}%` }}
                />
              </div>
              <div className="flex justify-between mt-1">
                <span className="text-xs text-[var(--text-muted)]">{status || '准备中...'}</span>
                <span className="text-xs text-[var(--text-muted)]">{progress}%</span>
              </div>
            </div>
          )}

          {/* Error */}
          {error && (
            <div className="flex items-center gap-2 p-3 rounded-lg bg-[var(--error)]/10 text-[var(--error)] text-xs">
              <AlertCircle size={14} />
              {error}
            </div>
          )}

          {/* Buttons */}
          <div className="flex gap-2">
            <button
              onClick={startDownload}
              disabled={downloading}
              className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm bg-[var(--accent)] text-white hover:opacity-90 disabled:opacity-50 disabled:cursor-not-allowed transition-opacity"
            >
              {downloading ? (
                <><Loader2 size={14} className="animate-spin" /> 下载中...</>
              ) : error ? (
                <><RefreshCw size={14} /> 重试下载</>
              ) : (
                <><Download size={14} /> 开始下载</>
              )}
            </button>
          </div>
        </>
      )}
    </div>
  );
}
