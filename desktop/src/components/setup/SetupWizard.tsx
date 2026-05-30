import React, { useState, useEffect } from 'react';
import {
  Download, CheckCircle, ArrowRight, Loader2, RefreshCw
} from 'lucide-react';

const BACKEND = 'http://127.0.0.1:9876';

// ── Main Component ──────────────────────────────────────────────────────
export function SetupWizard({ onComplete }: { onComplete: () => void }) {
  const [step, setStep] = useState(0);
  const [modelMirror, setModelMirror] = useState('hf-mirror');
  const [modelDownloading, setModelDownloading] = useState(false);
  const [modelProgress, setModelProgress] = useState(0);
  const [modelStatus, setModelStatus] = useState('');
  const [modelDone, setModelDone] = useState(false);
  const [modelError, setModelError] = useState('');

  // Backend status
  const [backendReady, setBackendReady] = useState(false);
  const [backendChecking, setBackendChecking] = useState(true);
  const [backendError, setBackendError] = useState('');

  // Check backend status on mount
  useEffect(() => {
    checkBackend();
    const interval = setInterval(checkBackend, 3000);
    return () => clearInterval(interval);
  }, []);

  const checkBackend = async () => {
    try {
      const res = await fetch(`${BACKEND}/api/health`, { signal: AbortSignal.timeout(2000) });
      if (res.ok) {
        setBackendReady(true);
        setBackendChecking(false);
        setBackendError('');
      }
    } catch {
      setBackendReady(false);
      setBackendChecking(true);
    }
  };

  const handleComplete = () => {
    localStorage.setItem('hermes_setup_done', 'true');
    localStorage.setItem('hermes_wizard_completed', 'true');
    onComplete();
  };

  const startDownload = async () => {
    if (!backendReady) {
      setModelError('后端未就绪，请稍候...');
      return;
    }

    setModelDownloading(true);
    setModelProgress(0);
    setModelStatus('正在准备下载...');
    setModelError('');

    try {
      const res = await fetch(`${BACKEND}/api/setup/download-model`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ mirror: modelMirror }),
      });
      const data = await res.json();

      if (data.success) {
        // SSE listen for progress
        const es = new EventSource(`${BACKEND}/api/setup/status/stream`);
        es.onmessage = (ev) => {
          try {
            const d = JSON.parse(ev.data);
            if (d.progress) setModelProgress(d.progress);
            if (d.message) setModelStatus(d.message);
            if (d.phase === 'done') {
              setModelDone(true);
              setModelDownloading(false);
              es.close();
            }
            if (d.phase === 'error') {
              setModelDownloading(false);
              setModelError(d.error || d.message || '下载失败');
              es.close();
            }
          } catch {}
        };
        es.onerror = () => {
          es.close();
          setModelDownloading(false);
          setModelError('连接中断');
        };
      } else {
        setModelDownloading(false);
        setModelError(data.error || data.detail || '启动下载失败');
      }
    } catch (e) {
      setModelDownloading(false);
      setModelError('请求失败');
    }
  };

  const steps = ['模型下载', '完成'];

  return (
    <div style={{
      maxWidth: 680, margin: '0 auto', padding: 32,
      fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", "Microsoft YaHei", sans-serif',
    }}>
      <div style={{ textAlign: 'center', marginBottom: 32 }}>
        <h1 style={{ fontSize: 24, fontWeight: 700, color: '#e5e7eb', marginBottom: 8 }}>
          Hermes 桌面版设置
        </h1>
        <p style={{ fontSize: 14, color: '#9ca3af' }}>
          可选：下载 6GB 视觉模型，用于屏幕元素识别和 GUI 自动化
        </p>
      </div>

      {/* Step indicator */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 24 }}>
        {steps.map((s, i) => (
          <React.Fragment key={i}>
            <div style={{
              width: 32, height: 32, borderRadius: '50%',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              fontSize: 14, fontWeight: 600,
              background: i < step ? '#22c55e' : i === step ? '#3b82f6' : '#374151',
              color: '#fff',
            }}>
              {i < step ? '✓' : i + 1}
            </div>
            <span style={{
              fontSize: 13, color: i === step ? '#e5e7eb' : '#6b7280',
              fontWeight: i === step ? 600 : 400,
            }}>{s}</span>
            {i < steps.length - 1 && (
              <div style={{ flex: 1, height: 1, background: i < step ? '#22c55e' : '#374151' }} />
            )}
          </React.Fragment>
        ))}
      </div>

      {/* Step 0: Model Download */}
      {step === 0 && (
        <div>
          <h2 style={{ fontSize: 18, color: '#e5e7eb', marginBottom: 16 }}>
            <Download size={20} style={{ verticalAlign: 'middle', marginRight: 8 }} />
            视觉模型下载（可选）
          </h2>

          <p style={{ fontSize: 14, color: '#9ca3af', marginBottom: 16 }}>
            LocateAnything-3B (~6GB) 用于屏幕元素识别和 GUI 自动化。<br />
            如果只需要聊天、文件和办公功能，可以跳过。
          </p>

          {/* Backend status */}
          {backendChecking && !backendReady && (
            <div style={{
              padding: 16, borderRadius: 8, marginBottom: 20,
              background: 'rgba(59,130,246,0.1)',
              display: 'flex', alignItems: 'center', gap: 12,
            }}>
              <Loader2 size={20} className="spin" style={{ color: '#60a5fa' }} />
              <div>
                <div style={{ fontSize: 14, color: '#93c5fd', fontWeight: 500 }}>
                  正在启动后端服务...
                </div>
                <div style={{ fontSize: 12, color: '#6b7280', marginTop: 4 }}>
                  首次启动可能需要 1-2 分钟，请耐心等待
                </div>
              </div>
            </div>
          )}

          {backendError && (
            <div style={{
              padding: 16, borderRadius: 8, marginBottom: 20,
              background: 'rgba(239,68,68,0.1)',
              display: 'flex', alignItems: 'center', gap: 12,
            }}>
              <span style={{ color: '#fca5a5', fontSize: 14 }}>{backendError}</span>
              <button onClick={checkBackend} style={{
                ...btnStyle, padding: '6px 12px', fontSize: 12,
              }}>
                <RefreshCw size={14} /> 重试
              </button>
            </div>
          )}

          {/* Mirror selection */}
          <div style={{ marginBottom: 20 }}>
            <label style={{
              display: 'block', fontSize: 14, fontWeight: 500,
              color: '#d1d5db', marginBottom: 6,
            }}>下载源</label>
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
              {[
                { key: 'hf-mirror', label: 'hf-mirror（国内推荐）', note: '' },
                { key: 'modelscope', label: 'ModelScope（阿里）', note: '' },
                { key: 'official', label: 'HuggingFace 官方', note: '需 TUN' },
              ].map(m => (
                <button
                  key={m.key}
                  onClick={() => setModelMirror(m.key)}
                  disabled={modelDownloading || !backendReady}
                  style={{
                    display: 'inline-flex', alignItems: 'center', gap: 4,
                    padding: '8px 14px', borderRadius: 20, border: 'none',
                    fontSize: 13, cursor: 'pointer',
                    background: modelMirror === m.key ? '#8b5cf6' : '#1f2937',
                    color: modelMirror === m.key ? '#fff' : '#9ca3af',
                    opacity: (modelDownloading || !backendReady) ? 0.5 : 1,
                  }}
                >
                  {m.label} {m.note && <span style={{ fontSize: 11, color: '#f59e0b' }}>({m.note})</span>}
                </button>
              ))}
            </div>
          </div>

          {/* Progress */}
          {(modelDownloading || modelDone) && (
            <div style={{ marginBottom: 20 }}>
              <div style={{ height: 8, borderRadius: 4, background: '#1f2937', overflow: 'hidden' }}>
                <div style={{
                  height: '100%', borderRadius: 4,
                  width: `${modelProgress}%`,
                  background: modelDone ? '#22c55e' : 'linear-gradient(90deg, #3b82f6, #8b5cf6)',
                  transition: 'width 0.3s ease',
                }} />
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 8, fontSize: 13, color: '#9ca3af' }}>
                <span>{modelStatus || '准备中...'}</span>
                <span>{modelProgress}%</span>
              </div>
            </div>
          )}

          {/* Error */}
          {modelError && (
            <div style={{
              padding: 12, borderRadius: 8, marginBottom: 20,
              background: 'rgba(239,68,68,0.1)',
              display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8,
            }}>
              <span style={{ color: '#fca5a5', fontSize: 14 }}>{modelError}</span>
              <button onClick={startDownload} style={{
                ...btnStyle, padding: '6px 12px', fontSize: 12,
                background: '#ef4444',
              }}>
                <RefreshCw size={14} /> 重试
              </button>
            </div>
          )}

          {/* Buttons */}
          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8, marginTop: 24 }}>
            {!modelDownloading && !modelDone && (
              <button
                onClick={startDownload}
                disabled={!backendReady}
                style={{
                  ...btnStyle,
                  opacity: backendReady ? 1 : 0.5,
                  cursor: backendReady ? 'pointer' : 'not-allowed',
                }}
              >
                <Download size={16} /> {backendReady ? '开始下载' : '等待后端...'}
              </button>
            )}
            {modelDownloading && (
              <button disabled style={{ ...btnStyle, opacity: 0.5 }}>
                <Loader2 size={16} className="spin" /> 下载中...
              </button>
            )}
            <button onClick={handleComplete} style={modelDone ? btnStyle : btnSecondaryStyle}>
              {modelDone ? '完成' : '跳过'} <ArrowRight size={16} />
            </button>
          </div>
        </div>
      )}

      {/* Step 1: Complete */}
      {step === 1 && (
        <div style={{ textAlign: 'center', padding: 32 }}>
          <CheckCircle size={64} color="#22c55e" />
          <h2 style={{ fontSize: 22, color: '#e5e7eb', marginTop: 16, marginBottom: 8 }}>
            设置完成！
          </h2>
          <p style={{ fontSize: 14, color: '#9ca3af', marginBottom: 24 }}>
            Hermes 桌面版已准备就绪
          </p>
          <button onClick={handleComplete} style={{ ...btnStyle, fontSize: 16, padding: '12px 32px' }}>
            开始使用 <ArrowRight size={18} />
          </button>
        </div>
      )}
    </div>
  );
}

// ── Styles ──────────────────────────────────────────────────────────────
const btnStyle: React.CSSProperties = {
  display: 'inline-flex', alignItems: 'center', gap: 6,
  padding: '10px 20px', borderRadius: 8, border: 'none',
  background: '#3b82f6', color: '#fff', fontSize: 14, fontWeight: 500,
  cursor: 'pointer', transition: 'background 0.2s',
};

const btnSecondaryStyle: React.CSSProperties = {
  ...btnStyle, background: '#374151', color: '#d1d5db',
};
