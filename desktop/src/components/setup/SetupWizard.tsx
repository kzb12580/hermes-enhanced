import React, { useState, useEffect, useCallback, useRef } from 'react';
import {
  Settings, Wifi, Download, CheckCircle, AlertCircle,
  Loader2, Monitor, Cpu, HardDrive, Globe, ArrowRight,
  ArrowLeft, RefreshCw, Zap, Shield
} from 'lucide-react';

const BACKEND = 'http://127.0.0.1:9876';

interface DepStatus {
  ok: boolean;
  version?: string;
  cuda?: boolean;
  gpu?: string;
  cuda_version?: string;
}

interface SetupStatus {
  running: boolean;
  phase: string;
  progress: number;
  message: string;
  error: string | null;
  deps: Record<string, DepStatus>;
  log?: string[];
}

interface NetworkConfig {
  proxy?: string;
  proxy_mode?: string;
  hf_mirror?: string;
  pypi_mirror?: string;
  detected_proxy?: string;
}

// ── 步骤指示器 ──────────────────────────────────────────────────────────
function StepIndicator({ current, steps }: { current: number; steps: string[] }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 24 }}>
      {steps.map((s, i) => (
        <React.Fragment key={i}>
          <div style={{
            width: 32, height: 32, borderRadius: '50%',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            fontSize: 14, fontWeight: 600,
            background: i < current ? '#22c55e' : i === current ? '#3b82f6' : '#374151',
            color: '#fff',
          }}>
            {i < current ? '✓' : i + 1}
          </div>
          <span style={{
            fontSize: 13, color: i === current ? '#e5e7eb' : '#6b7280',
            fontWeight: i === current ? 600 : 400,
          }}>{s}</span>
          {i < steps.length - 1 && (
            <div style={{ flex: 1, height: 1, background: i < current ? '#22c55e' : '#374151' }} />
          )}
        </React.Fragment>
      ))}
    </div>
  );
}

// ── 依赖项行 ────────────────────────────────────────────────────────────
function DepRow({ name, status }: { name: string; status: DepStatus }) {
  const icon = status.ok
    ? <CheckCircle size={16} color="#22c55e" />
    : <AlertCircle size={16} color="#ef4444" />;

  let detail = status.ok ? '已安装' : '未安装';
  if (status.version) detail = `v${status.version}`;
  if (status.gpu) detail = `${status.gpu} (${status.cuda_version || 'CUDA'})`;
  if (status.cuda === false && status.ok) detail += ' (CPU模式)';

  return (
    <div style={{
      display: 'flex', alignItems: 'center', justifyContent: 'space-between',
      padding: '8px 12px', borderRadius: 6,
      background: status.ok ? 'rgba(34,197,94,0.08)' : 'rgba(239,68,68,0.08)',
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        {icon}
        <span style={{ fontSize: 14 }}>{name}</span>
      </div>
      <span style={{ fontSize: 13, color: '#9ca3af' }}>{detail}</span>
    </div>
  );
}

// ── 主组件 ──────────────────────────────────────────────────────────────
export function SetupWizard({ onComplete }: { onComplete: () => void }) {
  const [step, setStep] = useState(0);
  const [setupStatus, setSetupStatus] = useState<SetupStatus | null>(null);
  const [networkConfig, setNetworkConfig] = useState<NetworkConfig>({});
  const [diagnosis, setDiagnosis] = useState<any>(null);
  const [diagnosing, setDiagnosing] = useState(false);
  const [installing, setInstalling] = useState(false);
  const [mirrors, setMirrors] = useState<{ hf: Record<string, string>; pypi: Record<string, string> }>({ hf: {}, pypi: {} });
  const eventSourceRef = useRef<EventSource | null>(null);

  // 加载初始状态
  useEffect(() => {
    fetchSetupStatus();
    fetchNetworkConfig();
    fetchMirrors();
  }, []);

  const fetchSetupStatus = async () => {
    try {
      const res = await fetch(`${BACKEND}/api/setup/status`);
      const data = await res.json();
      setSetupStatus(data);
    } catch (e) {
      console.error('获取状态失败:', e);
    }
  };

  const fetchNetworkConfig = async () => {
    try {
      const res = await fetch(`${BACKEND}/api/setup/network`);
      const data = await res.json();
      setNetworkConfig(data);
    } catch (e) { /* ignore */ }
  };

  const fetchMirrors = async () => {
    try {
      const res = await fetch(`${BACKEND}/api/setup/mirrors`);
      const data = await res.json();
      setMirrors(data);
    } catch (e) { /* ignore */ }
  };

  const runDiagnosis = async () => {
    setDiagnosing(true);
    try {
      const res = await fetch(`${BACKEND}/api/setup/diagnose`);
      const data = await res.json();
      setDiagnosis(data);
    } catch (e) {
      setDiagnosis({ error: '诊断请求失败' });
    }
    setDiagnosing(false);
  };

  const saveNetwork = async () => {
    try {
      await fetch(`${BACKEND}/api/setup/network`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(networkConfig),
      });
    } catch (e) { /* ignore */ }
  };

  const startInstall = async () => {
    setInstalling(true);
    try {
      await fetch(`${BACKEND}/api/setup/install`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ skip_model: true, skip_tesseract: false, force_model: false }),
      });

      // SSE 监听进度
      const es = new EventSource(`${BACKEND}/api/setup/status/stream`);
      eventSourceRef.current = es;
      es.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          setSetupStatus(prev => prev ? { ...prev, ...data } : null);
          if (data.phase === 'done' || data.phase === 'error') {
            es.close();
            setInstalling(false);
            fetchSetupStatus();
          }
        } catch (e) { /* ignore */ }
      };
      es.onerror = () => {
        es.close();
        setInstalling(false);
        fetchSetupStatus();
      };
    } catch (e) {
      setInstalling(false);
    }
  };

  // 清理
  useEffect(() => {
    return () => {
      eventSourceRef.current?.close();
    };
  }, []);

  // Only check critical deps - tesseract and model are optional
  const criticalDepNames = ['python', 'pytorch', 'transformers', 'pillow', 'pyautogui'];
  const allDepsOk = setupStatus?.deps
    ? criticalDepNames.every(d => !setupStatus.deps[d] || setupStatus.deps[d].ok)
    : false;

  const steps = ['环境检测', '网络配置', '依赖安装', '完成'];

  return (
    <div style={{
      maxWidth: 680, margin: '0 auto', padding: 32,
      fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif',
    }}>
      <div style={{ textAlign: 'center', marginBottom: 32 }}>
        <h1 style={{ fontSize: 24, fontWeight: 700, color: '#e5e7eb', marginBottom: 8 }}>
          🚀 Hermes Desktop 初始设置
        </h1>
        <p style={{ fontSize: 14, color: '#9ca3af' }}>
          让 AI 像人一样操作你的电脑
        </p>
      </div>

      <StepIndicator current={step} steps={steps} />

      {/* ── Step 0: 环境检测 ── */}
      {step === 0 && (
        <div>
          <h2 style={{ fontSize: 18, color: '#e5e7eb', marginBottom: 16 }}>
            <Monitor size={20} style={{ verticalAlign: 'middle', marginRight: 8 }} />
            环境检测
          </h2>

          {setupStatus?.deps ? (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              {Object.entries(setupStatus.deps).map(([name, status]) => (
                <DepRow key={name} name={name} status={status} />
              ))}
            </div>
          ) : (
            <div style={{ textAlign: 'center', padding: 32 }}>
              <Loader2 size={32} className="spin" />
              <p style={{ color: '#9ca3af', marginTop: 8 }}>正在检测...</p>
            </div>
          )}

          <div style={{
            marginTop: 16, padding: 12, borderRadius: 8,
            background: allDepsOk ? 'rgba(34,197,94,0.1)' : 'rgba(239,68,68,0.1)',
            display: 'flex', alignItems: 'center', gap: 8,
          }}>
            {allDepsOk
              ? <><CheckCircle size={16} color="#22c55e" /><span style={{ color: '#22c55e' }}>所有依赖已就绪！</span></>
              : <><AlertCircle size={16} color="#ef4444" /><span style={{ color: '#ef4444' }}>部分依赖缺失，需要安装</span></>
            }
          </div>

          <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: 24 }}>
            <button
              onClick={() => {
                if (allDepsOk) {
                  localStorage.setItem('hermes_setup_done', 'true');
                  onComplete();
                } else {
                  setStep(1);
                }
              }}
              style={btnStyle}
            >
              {allDepsOk ? '完成，开始使用' : '下一步'} <ArrowRight size={16} />
            </button>
          </div>
        </div>
      )}

      {/* ── Step 1: 网络配置 ── */}
      {step === 1 && (
        <div>
          <h2 style={{ fontSize: 18, color: '#e5e7eb', marginBottom: 16 }}>
            <Globe size={20} style={{ verticalAlign: 'middle', marginRight: 8 }} />
            网络配置
          </h2>

          {/* 代理设置 */}
          <div style={{ marginBottom: 20 }}>
            <label style={labelStyle}>代理模式</label>
            <div style={{ display: 'flex', gap: 8 }}>
              {['auto', 'manual', 'disabled'].map(mode => (
                <button
                  key={mode}
                  onClick={() => setNetworkConfig(prev => ({ ...prev, proxy_mode: mode }))}
                  style={{
                    ...chipStyle,
                    background: networkConfig.proxy_mode === mode ? '#3b82f6' : '#1f2937',
                    color: networkConfig.proxy_mode === mode ? '#fff' : '#9ca3af',
                  }}
                >
                  {mode === 'auto' ? '🔍 自动检测' : mode === 'manual' ? '✏️ 手动设置' : '🚫 不使用'}
                </button>
              ))}
            </div>
            {networkConfig.detected_proxy && networkConfig.proxy_mode !== 'disabled' && (
              <p style={{ fontSize: 13, color: '#22c55e', marginTop: 8 }}>
                检测到代理: {networkConfig.detected_proxy}
              </p>
            )}
          </div>

          {networkConfig.proxy_mode === 'manual' && (
            <div style={{ marginBottom: 20 }}>
              <label style={labelStyle}>代理地址</label>
              <input
                value={networkConfig.proxy || ''}
                onChange={e => setNetworkConfig(prev => ({ ...prev, proxy: e.target.value }))}
                placeholder="http://127.0.0.1:7890"
                style={inputStyle}
              />
            </div>
          )}

          {/* 镜像源 */}
          <div style={{ marginBottom: 20 }}>
            <label style={labelStyle}>HuggingFace 模型镜像</label>
            <p style={{ fontSize: 12, color: '#6b7280', marginBottom: 8 }}>
              中国大陆用户建议选择 hf-mirror
            </p>
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
              {Object.entries(mirrors.hf || {}).map(([key, url]) => (
                <button
                  key={key}
                  onClick={() => setNetworkConfig(prev => ({ ...prev, hf_mirror: key }))}
                  style={{
                    ...chipStyle,
                    background: networkConfig.hf_mirror === key ? '#8b5cf6' : '#1f2937',
                    color: networkConfig.hf_mirror === key ? '#fff' : '#9ca3af',
                  }}
                >
                  {key === 'official' ? '🌐 官方' : key === 'hf-mirror' ? '🇨🇳 hf-mirror' : key}
                </button>
              ))}
            </div>
          </div>

          <div style={{ marginBottom: 20 }}>
            <label style={labelStyle}>PyPI 下载镜像</label>
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
              {Object.entries(mirrors.pypi || {}).map(([key, url]) => (
                <button
                  key={key}
                  onClick={() => setNetworkConfig(prev => ({ ...prev, pypi_mirror: key }))}
                  style={{
                    ...chipStyle,
                    background: networkConfig.pypi_mirror === key ? '#8b5cf6' : '#1f2937',
                    color: networkConfig.pypi_mirror === key ? '#fff' : '#9ca3af',
                  }}
                >
                  {key === 'official' ? '🌐 官方' : key === 'tuna' ? '🇨🇳 清华' : key === 'aliyun' ? '🇨🇳 阿里云' : key}
                </button>
              ))}
            </div>
          </div>

          {/* 网络诊断 */}
          <div style={{ marginBottom: 20 }}>
            <button
              onClick={runDiagnosis}
              disabled={diagnosing}
              style={{ ...chipStyle, background: '#1f2937' }}
            >
              {diagnosing ? <Loader2 size={14} className="spin" /> : <Wifi size={14} />}
              网络诊断
            </button>
            {diagnosis && !diagnosis.error && (
              <div style={{ marginTop: 8, fontSize: 13 }}>
                {diagnosis.tests?.map((t: any, i: number) => (
                  <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 4 }}>
                    {t.ok
                      ? <CheckCircle size={14} color="#22c55e" />
                      : <AlertCircle size={14} color="#ef4444" />}
                    <span style={{ color: t.ok ? '#d1d5db' : '#fca5a5' }}>
                      {t.name}: {t.ok ? `OK (${t.status})` : t.error}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </div>

          <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 24 }}>
            <button onClick={() => setStep(0)} style={btnSecondaryStyle}>
              <ArrowLeft size={16} /> 上一步
            </button>
            <button onClick={() => { saveNetwork(); setStep(2); }} style={btnStyle}>
              下一步 <ArrowRight size={16} />
            </button>
          </div>
        </div>
      )}

      {/* ── Step 2: 依赖安装 ── */}
      {step === 2 && (
        <div>
          <h2 style={{ fontSize: 18, color: '#e5e7eb', marginBottom: 16 }}>
            <Download size={20} style={{ verticalAlign: 'middle', marginRight: 8 }} />
            依赖安装
          </h2>

          {!installing && setupStatus?.phase !== 'done' && (
            <div style={{ marginBottom: 20 }}>
              <p style={{ fontSize: 14, color: '#d1d5db', marginBottom: 12 }}>
                将自动安装以下组件：
              </p>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                {[
                  { icon: <Cpu size={16} />, name: 'PyTorch', desc: '深度学习框架 (自动匹配CUDA)' },
                  { icon: <Zap size={16} />, name: 'LocateAnything-3B', desc: 'NVIDIA 视觉定位模型 (~6GB)' },
                  { icon: <Monitor size={16} />, name: 'GUI 工具', desc: 'pyautogui, Pillow, OpenCV' },
                  { icon: <HardDrive size={16} />, name: 'Office 工具', desc: 'python-docx, pptx, openpyxl' },
                  { icon: <Shield size={16} />, name: 'Tesseract OCR', desc: '屏幕文字识别 + 中文语言包' },
                ].map((item, i) => (
                  <div key={i} style={{
                    display: 'flex', alignItems: 'center', gap: 12,
                    padding: '10px 14px', borderRadius: 8, background: '#1f2937',
                  }}>
                    <span style={{ color: '#3b82f6' }}>{item.icon}</span>
                    <div>
                      <div style={{ fontSize: 14, color: '#e5e7eb' }}>{item.name}</div>
                      <div style={{ fontSize: 12, color: '#6b7280' }}>{item.desc}</div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* 进度条 */}
          {(installing || setupStatus?.phase === 'done') && (
            <div style={{ marginBottom: 20 }}>
              <div style={{
                height: 8, borderRadius: 4, background: '#1f2937', overflow: 'hidden',
              }}>
                <div style={{
                  height: '100%', borderRadius: 4,
                  width: `${setupStatus?.progress || 0}%`,
                  background: setupStatus?.phase === 'error'
                    ? '#ef4444'
                    : setupStatus?.phase === 'done'
                      ? '#22c55e'
                      : 'linear-gradient(90deg, #3b82f6, #8b5cf6)',
                  transition: 'width 0.3s ease',
                }} />
              </div>
              <div style={{
                display: 'flex', justifyContent: 'space-between', marginTop: 8,
                fontSize: 13, color: '#9ca3af',
              }}>
                <span>{setupStatus?.message || '准备中...'}</span>
                <span>{setupStatus?.progress || 0}%</span>
              </div>
            </div>
          )}

          {/* 安装日志 */}
          {setupStatus?.log && setupStatus.log.length > 0 && (
            <div style={{
              maxHeight: 200, overflow: 'auto', padding: 12,
              background: '#0f172a', borderRadius: 8, fontSize: 12,
              fontFamily: 'monospace', color: '#94a3b8',
              marginBottom: 20,
            }}>
              {setupStatus.log.slice(-20).map((line, i) => (
                <div key={i}>{line}</div>
              ))}
            </div>
          )}

          {/* 错误提示 */}
          {setupStatus?.phase === 'error' && (
            <div style={{
              padding: 12, borderRadius: 8, marginBottom: 20,
              background: 'rgba(239,68,68,0.1)',
              display: 'flex', alignItems: 'center', gap: 8,
            }}>
              <AlertCircle size={16} color="#ef4444" />
              <span style={{ color: '#fca5a5', fontSize: 14 }}>
                {setupStatus.error || '安装失败，请检查网络连接'}
              </span>
            </div>
          )}

          <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 24 }}>
            <button onClick={() => setStep(1)} style={btnSecondaryStyle} disabled={installing}>
              <ArrowLeft size={16} /> 上一步
            </button>
            <div style={{ display: 'flex', gap: 8 }}>
              {setupStatus?.phase === 'error' && (
                <button onClick={startInstall} style={btnStyle}>
                  <RefreshCw size={16} /> 重试
                </button>
              )}
              {!installing && setupStatus?.phase !== 'done' && (
                <>
                  <button onClick={startInstall} style={btnStyle}>
                    <Download size={16} /> 开始安装
                  </button>
                  <button onClick={() => { localStorage.setItem('hermes_setup_done', 'true'); onComplete(); }} style={btnSecondaryStyle}>
                    跳过
                  </button>
                </>
              )}
              {setupStatus?.phase === 'done' && (
                <button onClick={() => setStep(3)} style={btnStyle}>
                  下一步 <ArrowRight size={16} />
                </button>
              )}
            </div>
          </div>
        </div>
      )}

      {/* ── Step 3: 完成 ── */}
      {step === 3 && (
        <div style={{ textAlign: 'center', padding: 32 }}>
          <CheckCircle size={64} color="#22c55e" />
          <h2 style={{ fontSize: 22, color: '#e5e7eb', marginTop: 16, marginBottom: 8 }}>
            🎉 设置完成！
          </h2>
          <p style={{ fontSize: 14, color: '#9ca3af', marginBottom: 24 }}>
            Hermes Desktop 已准备就绪，可以开始使用了
          </p>
          <button onClick={onComplete} style={{ ...btnStyle, fontSize: 16, padding: '12px 32px' }}>
            开始使用 <ArrowRight size={18} />
          </button>
        </div>
      )}
    </div>
  );
}

// ── 样式常量 ──────────────────────────────────────────────────────────────
const btnStyle: React.CSSProperties = {
  display: 'inline-flex', alignItems: 'center', gap: 6,
  padding: '10px 20px', borderRadius: 8, border: 'none',
  background: '#3b82f6', color: '#fff', fontSize: 14, fontWeight: 500,
  cursor: 'pointer', transition: 'background 0.2s',
};

const btnSecondaryStyle: React.CSSProperties = {
  ...btnStyle, background: '#374151', color: '#d1d5db',
};

const labelStyle: React.CSSProperties = {
  display: 'block', fontSize: 14, fontWeight: 500, color: '#d1d5db', marginBottom: 6,
};

const inputStyle: React.CSSProperties = {
  width: '100%', padding: '10px 14px', borderRadius: 8,
  border: '1px solid #374151', background: '#1f2937', color: '#e5e7eb',
  fontSize: 14, outline: 'none',
};

const chipStyle: React.CSSProperties = {
  display: 'inline-flex', alignItems: 'center', gap: 4,
  padding: '8px 14px', borderRadius: 20, border: 'none',
  fontSize: 13, cursor: 'pointer', transition: 'all 0.2s',
};
