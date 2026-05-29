import React, { useState } from 'react';
import {
  Download, CheckCircle, ArrowRight, ArrowLeft, Loader2
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

  const handleComplete = () => {
    localStorage.setItem('hermes_setup_done', 'true');
    localStorage.setItem('hermes_wizard_completed', 'true');
    onComplete();
  };

  const startDownload = async () => {
    setModelDownloading(true);
    setModelProgress(0);
    setModelStatus('Starting download...');
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
              setModelError(d.error || d.message || 'Download failed');
              es.close();
            }
          } catch {}
        };
        es.onerror = () => {
          es.close();
          setModelDownloading(false);
          setModelError('Connection lost');
        };
      } else {
        setModelDownloading(false);
        setModelError(data.error || data.detail || 'Failed to start download');
      }
    } catch (e) {
      setModelDownloading(false);
      setModelError('Request failed');
    }
  };

  const steps = ['Model Download', 'Done'];

  return (
    <div style={{
      maxWidth: 680, margin: '0 auto', padding: 32,
      fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif',
    }}>
      <div style={{ textAlign: 'center', marginBottom: 32 }}>
        <h1 style={{ fontSize: 24, fontWeight: 700, color: '#e5e7eb', marginBottom: 8 }}>
          Hermes Desktop Setup
        </h1>
        <p style={{ fontSize: 14, color: '#9ca3af' }}>
          Optional: download the 6GB vision model for screen automation
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
            Vision Model Download (Optional)
          </h2>

          <p style={{ fontSize: 14, color: '#9ca3af', marginBottom: 16 }}>
            LocateAnything-3B (~6GB) for screen element detection and GUI automation.
            Skip if you only need chat, file, and office features.
          </p>

          {/* Mirror selection */}
          <div style={{ marginBottom: 20 }}>
            <label style={{
              display: 'block', fontSize: 14, fontWeight: 500,
              color: '#d1d5db', marginBottom: 6,
            }}>Download Source</label>
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
              {[
                { key: 'hf-mirror', label: 'hf-mirror (China)', note: '' },
                { key: 'modelscope', label: 'ModelScope (Ali)', note: '' },
                { key: 'official', label: 'HuggingFace', note: 'Needs TUN' },
              ].map(m => (
                <button
                  key={m.key}
                  onClick={() => setModelMirror(m.key)}
                  disabled={modelDownloading}
                  style={{
                    display: 'inline-flex', alignItems: 'center', gap: 4,
                    padding: '8px 14px', borderRadius: 20, border: 'none',
                    fontSize: 13, cursor: 'pointer',
                    background: modelMirror === m.key ? '#8b5cf6' : '#1f2937',
                    color: modelMirror === m.key ? '#fff' : '#9ca3af',
                    opacity: modelDownloading ? 0.5 : 1,
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
                <span>{modelStatus || 'Preparing...'}</span>
                <span>{modelProgress}%</span>
              </div>
            </div>
          )}

          {/* Error */}
          {modelError && (
            <div style={{
              padding: 12, borderRadius: 8, marginBottom: 20,
              background: 'rgba(239,68,68,0.1)',
              display: 'flex', alignItems: 'center', gap: 8,
            }}>
              <span style={{ color: '#fca5a5', fontSize: 14 }}>{modelError}</span>
            </div>
          )}

          {/* Buttons */}
          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8, marginTop: 24 }}>
            {!modelDownloading && !modelDone && (
              <button onClick={startDownload} style={btnStyle}>
                <Download size={16} /> Start Download
              </button>
            )}
            {modelDownloading && (
              <button disabled style={{ ...btnStyle, opacity: 0.5 }}>
                <Loader2 size={16} className="spin" /> Downloading...
              </button>
            )}
            <button onClick={handleComplete} style={modelDone ? btnStyle : btnSecondaryStyle}>
              {modelDone ? 'Done' : 'Skip'} <ArrowRight size={16} />
            </button>
          </div>
        </div>
      )}

      {/* Step 1: Complete */}
      {step === 1 && (
        <div style={{ textAlign: 'center', padding: 32 }}>
          <CheckCircle size={64} color="#22c55e" />
          <h2 style={{ fontSize: 22, color: '#e5e7eb', marginTop: 16, marginBottom: 8 }}>
            Setup Complete!
          </h2>
          <p style={{ fontSize: 14, color: '#9ca3af', marginBottom: 24 }}>
            Hermes Desktop is ready to use
          </p>
          <button onClick={handleComplete} style={{ ...btnStyle, fontSize: 16, padding: '12px 32px' }}>
            Start Using <ArrowRight size={18} />
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
