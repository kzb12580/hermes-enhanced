import React, { useState, useEffect } from 'react';
import { X, Settings2, Cpu, Key, Info, Thermometer, Hash, Globe, Keyboard, Wifi, Mail } from 'lucide-react';
import { useSystemStore } from '../../stores/systemStore';
import { useSettingsStore } from '../../stores/settingsStore';
import { ModelConfig } from './ModelConfig';
import { VisionModelDownload } from './VisionModelDownload';
import { EmailConfig } from '../email/EmailConfig';

type SettingsTab = 'general' | 'models' | 'network' | 'email' | 'apikeys' | 'about';

const tabs: { id: SettingsTab; label: string; icon: React.ReactNode }[] = [
  { id: 'general', label: '通用', icon: <Settings2 size={16} /> },
  { id: 'models', label: '模型', icon: <Cpu size={16} /> },
  { id: 'network', label: '网络', icon: <Wifi size={16} /> },
  { id: 'email', label: '邮件', icon: <Mail size={16} /> },
  { id: 'apikeys', label: 'API 密钥', icon: <Key size={16} /> },
  { id: 'about', label: '关于', icon: <Info size={16} /> },
];

export function SettingsPanel() {
  const { setSettingsOpen } = useSystemStore();
  const settings = useSettingsStore();
  const [activeTab, setActiveTab] = useState<SettingsTab>('general');

  const handleClose = () => setSettingsOpen(false);

  // Close on backdrop click
  const handleBackdropClick = (e: React.MouseEvent) => {
    if (e.target === e.currentTarget) handleClose();
  };

  // Close on Escape
  React.useEffect(() => {
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') handleClose();
    };
    window.addEventListener('keydown', handleKey);
    return () => window.removeEventListener('keydown', handleKey);
  }, []);

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm fade-in"
      onClick={handleBackdropClick}
    >
      <div className="w-full max-w-2xl max-h-[85vh] bg-[var(--bg-secondary)] rounded-xl shadow-2xl border border-[var(--border)] overflow-hidden flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-[var(--border)]">
          <h2 className="text-lg font-semibold text-[var(--text-primary)]">设置</h2>
          <button
            onClick={handleClose}
            className="p-1.5 rounded-lg text-[var(--text-muted)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-tertiary)] transition-colors"
          >
            <X size={18} />
          </button>
        </div>

        {/* Content */}
        <div className="flex flex-1 min-h-0">
          {/* Tabs sidebar */}
          <nav className="w-40 flex-shrink-0 border-r border-[var(--border)] py-2 px-2 space-y-0.5">
            {tabs.map((tab) => (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={`
                  flex items-center gap-2 w-full px-3 py-2 rounded-lg text-sm transition-colors
                  ${activeTab === tab.id
                    ? 'bg-[var(--bg-tertiary)] text-[var(--text-primary)] font-medium'
                    : 'text-[var(--text-muted)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-tertiary)]/50'
                  }
                `}
              >
                {tab.icon}
                <span>{tab.label}</span>
              </button>
            ))}
          </nav>

          {/* Tab content */}
          <div className="flex-1 overflow-y-auto p-6">
            {activeTab === 'general' && (
              <GeneralSettings />
            )}
            {activeTab === 'models' && (
              <div>
                <h3 className="text-base font-semibold text-[var(--text-primary)] mb-4">模型配置</h3>
                <ModelConfig />
                <div className="mt-6 pt-6 border-t border-[var(--border)]">
                  <VisionModelDownload />
                </div>
              </div>
            )}
            {activeTab === 'network' && (
              <NetworkSettings />
            )}
            {activeTab === 'email' && (
              <div>
                <h3 className="text-base font-semibold text-[var(--text-primary)] mb-4">邮件配置</h3>
                <EmailConfig />
              </div>
            )}
            {activeTab === 'apikeys' && (
              <ApiKeysSettings />
            )}
            {activeTab === 'about' && (
              <AboutSection />
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

function GeneralSettings() {
  const {
    language,
    fontSize,
    sendShortcut,
    showSystemMessages,
    autoScroll,
    temperature,
    maxTokens,
    systemPrompt,
    backendUrl,
    openLinksInExternalBrowser,
    updateSettings,
  } = useSettingsStore();

  return (
    <div className="space-y-6">
      <h3 className="text-base font-semibold text-[var(--text-primary)]">通用设置</h3>

      {/* Backend URL */}
      <div>
        <label className="flex items-center gap-1.5 text-sm font-medium text-[var(--text-secondary)] mb-2">
          <Globe size={14} />
          后端地址
        </label>
        <input
          type="text"
          value={backendUrl}
          onChange={(e) => updateSettings({ backendUrl: e.target.value })}
          className="w-full bg-[var(--bg-primary)] text-[var(--text-primary)] text-sm rounded-lg px-3 py-2 outline-none border border-[var(--border)] focus:border-[var(--accent)] transition-colors font-mono"
        />
      </div>

      {/* Send shortcut */}
      <div>
        <label className="flex items-center gap-1.5 text-sm font-medium text-[var(--text-secondary)] mb-2">
          <Keyboard size={14} />
          发送快捷键
        </label>
        <div className="flex gap-2">
          {(['enter', 'ctrl+enter'] as const).map((option) => (
            <button
              key={option}
              onClick={() => updateSettings({ sendShortcut: option })}
              className={`
                px-4 py-2 rounded-lg text-sm border transition-colors
                ${sendShortcut === option
                  ? 'border-[var(--accent)] bg-[var(--accent)]/10 text-[var(--accent)]'
                  : 'border-[var(--border)] text-[var(--text-muted)] hover:border-[var(--text-muted)]'
                }
              `}
            >
              {option === 'enter' ? 'Enter 发送' : 'Ctrl+Enter 发送'}
            </button>
          ))}
        </div>
      </div>

      {/* Font size */}
      <div>
        <label className="text-sm font-medium text-[var(--text-secondary)] mb-2 block">
          字体大小: {fontSize}px
        </label>
        <input
          type="range"
          min={12}
          max={20}
          value={fontSize}
          onChange={(e) => updateSettings({ fontSize: Number(e.target.value) })}
          className="w-full accent-[var(--accent)]"
        />
      </div>

      {/* Temperature */}
      <div>
        <label className="flex items-center gap-1.5 text-sm font-medium text-[var(--text-secondary)] mb-2">
          <Thermometer size={14} />
          温度: {temperature}
        </label>
        <input
          type="range"
          min={0}
          max={2}
          step={0.1}
          value={temperature}
          onChange={(e) => updateSettings({ temperature: Number(e.target.value) })}
          className="w-full accent-[var(--accent)]"
        />
      </div>

      {/* Max tokens */}
      <div>
        <label className="flex items-center gap-1.5 text-sm font-medium text-[var(--text-secondary)] mb-2">
          <Hash size={14} />
          最大 Token 数
        </label>
        <input
          type="number"
          value={maxTokens}
          onChange={(e) => updateSettings({ maxTokens: Number(e.target.value) })}
          min={256}
          max={128000}
          className="w-full bg-[var(--bg-primary)] text-[var(--text-primary)] text-sm rounded-lg px-3 py-2 outline-none border border-[var(--border)] focus:border-[var(--accent)] transition-colors font-mono"
        />
      </div>

      {/* Open links in external browser */}
      <div>
        <label className="flex items-center gap-3 cursor-pointer">
          <div
            className={`relative w-10 h-5 rounded-full transition-colors ${
              openLinksInExternalBrowser ? 'bg-[var(--accent)]' : 'bg-[var(--bg-tertiary)]'
            }`}
            onClick={() => updateSettings({ openLinksInExternalBrowser: !openLinksInExternalBrowser })}
          >
            <div
              className={`absolute top-0.5 left-0.5 w-4 h-4 rounded-full bg-white transition-transform ${
                openLinksInExternalBrowser ? 'translate-x-5' : ''
              }`}
            />
          </div>
          <div>
            <span className="text-sm font-medium text-[var(--text-primary)]">使用系统默认浏览器</span>
            <p className="text-xs text-[var(--text-muted)]">点击链接时在外部浏览器中打开</p>
          </div>
        </label>
      </div>

      {/* System prompt */}
      <div>
        <label className="text-sm font-medium text-[var(--text-secondary)] mb-2 block">
          系统提示词
        </label>
        <textarea
          value={systemPrompt}
          onChange={(e) => updateSettings({ systemPrompt: e.target.value })}
          placeholder="可选：设置 AI 系统提示词..."
          rows={4}
          className="w-full bg-[var(--bg-primary)] text-[var(--text-primary)] text-sm rounded-lg px-3 py-2 outline-none border border-[var(--border)] focus:border-[var(--accent)] transition-colors resize-none"
        />
      </div>
    </div>
  );
}

function ApiKeysSettings() {
  const { providers, updateProvider } = useSettingsStore();

  return (
    <div className="space-y-6">
      <h3 className="text-base font-semibold text-[var(--text-primary)] mb-2">API 密钥管理</h3>
      <p className="text-sm text-[var(--text-muted)] mb-4">
        配置各模型提供商的 API 密钥。密钥将安全存储在本地。
      </p>

      {providers.map((provider) => (
        <div key={provider.id} className="space-y-2">
          <label className="flex items-center gap-2 text-sm font-medium text-[var(--text-secondary)]">
            <Key size={14} className="text-[var(--accent)]" />
            {provider.name}
          </label>
          <input
            type="password"
            value={provider.apiKey}
            onChange={(e) => updateProvider(provider.id, { apiKey: e.target.value })}
            placeholder={`输入 ${provider.name} API Key...`}
            className="w-full bg-[var(--bg-primary)] text-[var(--text-primary)] text-sm rounded-lg px-3 py-2 outline-none border border-[var(--border)] focus:border-[var(--accent)] transition-colors font-mono"
          />
        </div>
      ))}
    </div>
  );
}

function AboutSection() {
  const [version, setVersion] = useState("v...");
  useEffect(() => {
    // @ts-ignore - window.api injected by preload
    window.api?.app?.getVersion?.()?.then((v: string) => { if (v) setVersion("v" + v) })?.catch(() => {});
  }, []);
  return (
    <div className="space-y-6">
      <h3 className="text-base font-semibold text-[var(--text-primary)]">关于 Hermes Desktop</h3>

      <div className="rounded-lg border border-[var(--border)] p-4 space-y-4">
        <div className="flex items-center gap-3">
          <div className="w-12 h-12 rounded-xl bg-[var(--accent)]/10 flex items-center justify-center">
            <span className="text-2xl">🔮</span>
          </div>
          <div>
            <h4 className="text-base font-semibold text-[var(--text-primary)]">Hermes Desktop</h4>
            <p className="text-sm text-[var(--text-muted)]">{version}</p>
          </div>
        </div>

        <p className="text-sm text-[var(--text-secondary)] leading-relaxed">
          Hermes Desktop 是一个基于 Hermes Agent 的桌面客户端，支持多种 AI 模型提供商，
          提供代码生成、文件操作、网页搜索等智能工具能力。
        </p>

        <div className="grid grid-cols-2 gap-3 text-sm">
          <div>
            <span className="text-[var(--text-muted)]">框架</span>
            <p className="text-[var(--text-primary)]">Electron + React + TypeScript</p>
          </div>
          <div>
            <span className="text-[var(--text-muted)]">后端</span>
            <p className="text-[var(--text-primary)]">Python FastAPI</p>
          </div>
          <div>
            <span className="text-[var(--text-muted)]">状态管理</span>
            <p className="text-[var(--text-primary)]">Zustand</p>
          </div>
          <div>
            <span className="text-[var(--text-muted)]">样式</span>
            <p className="text-[var(--text-primary)]">TailwindCSS</p>
          </div>
        </div>
      </div>

      <div className="text-center text-xs text-[var(--text-muted)]">
        <p>由 <a href="https://nousresearch.com" className="text-[var(--accent)] hover:underline" target="_blank" rel="noopener">Nous Research</a> 出品</p>
        <p className="mt-1">© 2025 Hermes Desktop. All rights reserved.</p>
      </div>
    </div>
  );
}

// ── 网络设置组件 ────────────────────────────────────────────────────────
function NetworkSettings() {
  const [config, setConfig] = useState<any>({});
  const [diagnosis, setDiagnosis] = useState<any>(null);
  const [diagnosing, setDiagnosing] = useState(false);
  const [mirrors, setMirrors] = useState<any>({});
  const [saving, setSaving] = useState(false);

  const BACKEND = 'http://127.0.0.1:9876';

  useEffect(() => {
    fetch(`${BACKEND}/api/setup/network`).then(r => r.json()).then(setConfig).catch(() => {});
    fetch(`${BACKEND}/api/setup/mirrors`).then(r => r.json()).then(setMirrors).catch(() => {});
  }, []);

  const save = async () => {
    setSaving(true);
    try {
      await fetch(`${BACKEND}/api/setup/network`, {
        method: 'PUT', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(config),
      });
    } catch (e) {}
    setSaving(false);
  };

  const diagnose = async () => {
    setDiagnosing(true);
    try {
      const res = await fetch(`${BACKEND}/api/setup/diagnose`);
      setDiagnosis(await res.json());
    } catch (e) { setDiagnosis({ error: '诊断失败' }); }
    setDiagnosing(false);
  };

  const modes = [
    { key: 'auto', label: '🔍 自动检测' },
    { key: 'manual', label: '✏️ 手动设置' },
    { key: 'disabled', label: '🚫 不使用代理' },
  ];

  return (
    <div className="space-y-6">
      <h3 className="text-base font-semibold text-[var(--text-primary)]">网络设置</h3>

      {/* 代理模式 */}
      <div className="rounded-lg border border-[var(--border)] p-4 space-y-3">
        <label className="text-sm font-medium text-[var(--text-secondary)]">代理模式</label>
        <div className="flex gap-2">
          {modes.map(m => (
            <button key={m.key} onClick={() => setConfig((c: any) => ({ ...c, proxy_mode: m.key }))}
              className={`px-3 py-1.5 rounded-full text-sm transition-colors ${
                config.proxy_mode === m.key
                  ? 'bg-[var(--accent)] text-white'
                  : 'bg-[var(--bg-tertiary)] text-[var(--text-muted)] hover:text-[var(--text-primary)]'
              }`}>{m.label}</button>
          ))}
        </div>
        {config.detected_proxy && config.proxy_mode !== 'disabled' && (
          <p className="text-xs text-green-400">检测到代理: {config.detected_proxy}</p>
        )}
      </div>

      {/* 手动代理 */}
      {config.proxy_mode === 'manual' && (
        <div className="rounded-lg border border-[var(--border)] p-4 space-y-3">
          <label className="text-sm font-medium text-[var(--text-secondary)]">代理地址</label>
          <input value={config.proxy || ''} onChange={e => setConfig((c: any) => ({ ...c, proxy: e.target.value }))}
            placeholder="http://127.0.0.1:7890"
            className="w-full px-3 py-2 rounded-lg bg-[var(--bg-tertiary)] text-[var(--text-primary)] border border-[var(--border)] text-sm" />
        </div>
      )}

      {/* HuggingFace 镜像 */}
      <div className="rounded-lg border border-[var(--border)] p-4 space-y-3">
        <label className="text-sm font-medium text-[var(--text-secondary)]">HuggingFace 模型镜像</label>
        <p className="text-xs text-[var(--text-muted)]">中国大陆用户建议选择 hf-mirror</p>
        <div className="flex gap-2 flex-wrap">
          {Object.entries(mirrors.hf || {}).map(([key]: [string, any]) => (
            <button key={key} onClick={() => setConfig((c: any) => ({ ...c, hf_mirror: key }))}
              className={`px-3 py-1.5 rounded-full text-sm transition-colors ${
                config.hf_mirror === key
                  ? 'bg-purple-600 text-white'
                  : 'bg-[var(--bg-tertiary)] text-[var(--text-muted)] hover:text-[var(--text-primary)]'
              }`}>
              {key === 'official' ? '🌐 官方' : key === 'hf-mirror' ? '🇨🇳 hf-mirror' : key}
            </button>
          ))}
        </div>
      </div>

      {/* PyPI 镜像 */}
      <div className="rounded-lg border border-[var(--border)] p-4 space-y-3">
        <label className="text-sm font-medium text-[var(--text-secondary)]">PyPI 下载镜像</label>
        <div className="flex gap-2 flex-wrap">
          {Object.entries(mirrors.pypi || {}).map(([key]: [string, any]) => (
            <button key={key} onClick={() => setConfig((c: any) => ({ ...c, pypi_mirror: key }))}
              className={`px-3 py-1.5 rounded-full text-sm transition-colors ${
                config.pypi_mirror === key
                  ? 'bg-purple-600 text-white'
                  : 'bg-[var(--bg-tertiary)] text-[var(--text-muted)] hover:text-[var(--text-primary)]'
              }`}>
              {key === 'official' ? '🌐 官方' : key === 'tuna' ? '🇨🇳 清华' : key === 'aliyun' ? '🇨🇳 阿里云' : key}
            </button>
          ))}
        </div>
      </div>

      {/* 操作按钮 */}
      <div className="flex gap-3">
        <button onClick={save} disabled={saving}
          className="px-4 py-2 rounded-lg bg-[var(--accent)] text-white text-sm font-medium hover:opacity-90 transition-opacity disabled:opacity-50">
          {saving ? '保存中...' : '💾 保存配置'}
        </button>
        <button onClick={diagnose} disabled={diagnosing}
          className="px-4 py-2 rounded-lg bg-[var(--bg-tertiary)] text-[var(--text-secondary)] text-sm font-medium hover:text-[var(--text-primary)] transition-colors disabled:opacity-50">
          {diagnosing ? '诊断中...' : '🔍 网络诊断'}
        </button>
      </div>

      {/* 诊断结果 */}
      {diagnosis && !diagnosis.error && (
        <div className="rounded-lg border border-[var(--border)] p-4 space-y-2">
          <p className="text-sm font-medium text-[var(--text-secondary)]">诊断结果</p>
          {diagnosis.tests?.map((t: any, i: number) => (
            <div key={i} className="flex items-center gap-2 text-sm">
              <span className={t.ok ? 'text-green-400' : 'text-red-400'}>{t.ok ? '✅' : '❌'}</span>
              <span className="text-[var(--text-primary)]">{t.name}</span>
              <span className="text-[var(--text-muted)] text-xs">
                {t.ok ? `HTTP ${t.status}` : t.error?.substring(0, 60)}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export default SettingsPanel;
