import React, { useState, useEffect } from 'react';
import { X, Settings2, Cpu, Key, Info, Thermometer, Hash, Globe, Keyboard } from 'lucide-react';
import { useSystemStore } from '../../stores/systemStore';
import { useSettingsStore } from '../../stores/settingsStore';
import { ModelConfig } from './ModelConfig';

type SettingsTab = 'general' | 'models' | 'apikeys' | 'about';

const tabs: { id: SettingsTab; label: string; icon: React.ReactNode }[] = [
  { id: 'general', label: '通用', icon: <Settings2 size={16} /> },
  { id: 'models', label: '模型', icon: <Cpu size={16} /> },
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
          step={256}
          className="w-full bg-[var(--bg-primary)] text-[var(--text-primary)] text-sm rounded-lg px-3 py-2 outline-none border border-[var(--border)] focus:border-[var(--accent)] transition-colors"
        />
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

      {/* Toggles */}
      <div className="space-y-3">
        <label className="flex items-center justify-between cursor-pointer">
          <span className="text-sm text-[var(--text-secondary)]">显示系统消息</span>
          <button
            onClick={() => updateSettings({ showSystemMessages: !showSystemMessages })}
            className={`
              w-10 h-6 rounded-full transition-colors relative
              ${showSystemMessages ? 'bg-[var(--accent)]' : 'bg-[var(--bg-surface)]'}
            `}
          >
            <span
              className={`
                absolute top-0.5 w-5 h-5 rounded-full bg-white shadow transition-transform
                ${showSystemMessages ? 'translate-x-[18px]' : 'translate-x-0.5'}
              `}
            />
          </button>
        </label>
        <label className="flex items-center justify-between cursor-pointer">
          <span className="text-sm text-[var(--text-secondary)]">自动滚动到底部</span>
          <button
            onClick={() => updateSettings({ autoScroll: !autoScroll })}
            className={`
              w-10 h-6 rounded-full transition-colors relative
              ${autoScroll ? 'bg-[var(--accent)]' : 'bg-[var(--bg-surface)]'}
            `}
          >
            <span
              className={`
                absolute top-0.5 w-5 h-5 rounded-full bg-white shadow transition-transform
                ${autoScroll ? 'translate-x-[18px]' : 'translate-x-0.5'}
              `}
            />
          </button>
        </label>
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
            <p className="text-sm text-[var(--text-muted)]">v{import("../../../package.json").version}</p>
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

export default SettingsPanel;
