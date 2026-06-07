import React, { useState, useEffect } from 'react';
import { Settings2, Cpu, Key, Info, Thermometer, Hash, Globe, Keyboard, Folder } from 'lucide-react';
import { useSettingsStore } from '../../stores/settingsStore';

export function SettingsPanel() {
  return (
    <div className="flex flex-col h-full bg-[var(--bg-primary)]">
      {/* Header */}
      <div className="flex items-center gap-2 px-6 py-4 border-b border-[var(--hermes-border)]">
        <Settings2 size={18} className="text-[var(--hermes-accent)]" />
        <h2 className="text-lg font-semibold text-text-primary">设置</h2>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto p-6 space-y-8">
        <GeneralSettings />
        <div className="border-t border-[var(--hermes-border)] pt-8">
          <AboutSection />
        </div>
      </div>
    </div>
  );
}

function GeneralSettings() {
  const {
    language, fontSize, sendShortcut,
    temperature, maxTokens, systemPrompt, backendUrl,
    openLinksInExternalBrowser, thinkingMode, thinkingBudget, updateSettings,
  } = useSettingsStore();

  // Workspace path — stored in Electron store, not Zustand
  const [workspacePath, setWorkspacePath] = useState('');
  useEffect(() => {
    const api = window.api;
    if (api?.settings?.get) {
      api.settings.get('workspacePath').then((v: string) => setWorkspacePath(v || ''));
    }
  }, []);

  const handleWorkspaceChange = (value: string) => {
    setWorkspacePath(value);
    const api = window.api;
    if (api?.settings?.set) {
      api.settings.set('workspacePath', value);
    }
  };

  const handleBrowseFolder = async () => {
    const api = window.api;
    if (api?.dialog?.selectFolder) {
      const result = await api.dialog.selectFolder();
      if (result) handleWorkspaceChange(result);
    }
  };

  return (
    <div className="space-y-6">
      <h3 className="text-base font-semibold text-text-primary flex items-center gap-2">
        <Settings2 size={16} className="text-[var(--hermes-accent)]" />
        通用设置
      </h3>

      {/* Backend URL */}
      <div>
        <label className="flex items-center gap-1.5 text-sm font-medium text-text-secondary mb-2">
          <Globe size={14} />
          后端地址
        </label>
        <input
          type="text"
          value={backendUrl}
          onChange={(e) => updateSettings({ backendUrl: e.target.value })}
          className="w-full bg-[var(--bg-secondary)] text-text-primary text-sm rounded-lg px-3 py-2 outline-none border border-[var(--hermes-border)] focus:border-[var(--hermes-accent)] transition-colors font-mono"
        />
      </div>

      {/* Workspace Path */}
      <div>
        <label className="flex items-center gap-1.5 text-sm font-medium text-text-secondary mb-2">
          <Folder size={14} />
          工作区目录
        </label>
        <div className="flex gap-2">
          <input
            type="text"
            value={workspacePath}
            onChange={(e) => handleWorkspaceChange(e.target.value)}
            placeholder="留空则默认使用桌面"
            className="flex-1 bg-[var(--bg-secondary)] text-text-primary text-sm rounded-lg px-3 py-2 outline-none border border-[var(--hermes-border)] focus:border-[var(--hermes-accent)] transition-colors font-mono"
          />
          <button
            onClick={handleBrowseFolder}
            className="px-3 py-2 rounded-lg text-sm border border-[var(--hermes-border)] text-text-secondary hover:border-[var(--hermes-accent)] transition-colors"
          >
            浏览
          </button>
        </div>
        <p className="text-xs text-text-muted mt-1">AI 的文件操作默认在此目录下进行。重启后端后生效。</p>
      </div>

      {/* Send shortcut */}
      <div>
        <label className="flex items-center gap-1.5 text-sm font-medium text-text-secondary mb-2">
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
                  ? 'border-[var(--hermes-accent)] bg-[var(--hermes-accent)]/10 text-[var(--hermes-accent)]'
                  : 'border-[var(--hermes-border)] text-text-muted hover:border-text-muted'
                }
              `}
            >
              {option === 'enter' ? 'Enter 发送' : 'Ctrl+Enter 发送'}
            </button>
          ))}
        </div>
      </div>

      {/* Language */}
      <div>
        <label className="text-sm font-medium text-text-secondary mb-2 block">
          语言 / Language
        </label>
        <div className="flex gap-2">
          {(['zh', 'en'] as const).map((lang) => (
            <button
              key={lang}
              onClick={() => {
                updateSettings({ language: lang });
                import('../../lib/i18n').then(({ setLang }) => setLang(lang));
              }}
              className={`
                px-4 py-2 rounded-lg text-sm border transition-colors
                ${language === lang
                  ? 'border-[var(--hermes-accent)] bg-[var(--hermes-accent)]/10 text-[var(--hermes-accent)]'
                  : 'border-[var(--hermes-border)] text-text-muted hover:border-text-muted'
                }
              `}
            >
              {lang === 'zh' ? '中文' : 'English'}
            </button>
          ))}
        </div>
      </div>

      {/* Font size */}
      <div>
        <label className="text-sm font-medium text-text-secondary mb-2 block">
          字体大小: {fontSize}px
        </label>
        <input
          type="range"
          min={12}
          max={20}
          value={fontSize}
          onChange={(e) => updateSettings({ fontSize: Number(e.target.value) })}
          className="w-full accent-[var(--hermes-accent)]"
        />
      </div>

      {/* Temperature */}
      <div>
        <label className="flex items-center gap-1.5 text-sm font-medium text-text-secondary mb-2">
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
          className="w-full accent-[var(--hermes-accent)]"
        />
      </div>

      {/* Max tokens */}
      <div>
        <label className="flex items-center gap-1.5 text-sm font-medium text-text-secondary mb-2">
          <Hash size={14} />
          最大 Token 数
        </label>
        <input
          type="number"
          value={maxTokens ?? ''}
          placeholder="自动"
          onChange={(e) => updateSettings({ maxTokens: e.target.value ? Number(e.target.value) : null })}
          min={256}
          max={128000}
          className="w-full bg-[var(--bg-secondary)] text-text-primary text-sm rounded-lg px-3 py-2 outline-none border border-[var(--hermes-border)] focus:border-[var(--hermes-accent)] transition-colors font-mono"
        />
      </div>

      {/* Thinking mode */}
      <div>
        <label className="flex items-center gap-1.5 text-sm font-medium text-text-secondary mb-2">
          <Cpu size={14} />
          思考模式
        </label>
        <div className="flex gap-2">
          {(['off', 'auto', 'on'] as const).map((mode) => (
            <button
              key={mode}
              onClick={() => updateSettings({ thinkingMode: mode })}
              className={`
                px-4 py-2 rounded-lg text-sm border transition-colors
                ${thinkingMode === mode
                  ? 'border-[var(--hermes-accent)] bg-[var(--hermes-accent)]/10 text-[var(--hermes-accent)]'
                  : 'border-[var(--hermes-border)] text-text-muted hover:border-text-muted'
                }
              `}
            >
              {mode === 'off' ? '关闭' : mode === 'auto' ? '自动' : '开启'}
            </button>
          ))}
        </div>
        {thinkingMode !== 'off' && (
          <div className="mt-3">
            <label className="text-xs text-text-muted mb-1 block">
              思考预算 Token: {thinkingBudget.toLocaleString()}
            </label>
            <input
              type="range"
              min={1024}
              max={65536}
              step={1024}
              value={thinkingBudget}
              onChange={(e) => updateSettings({ thinkingBudget: Number(e.target.value) })}
              className="w-full accent-[var(--hermes-accent)]"
            />
          </div>
        )}
      </div>

      {/* Open links in external browser */}
      <div>
        <label className="flex items-center gap-3 cursor-pointer">
          <div
            className={`relative w-10 h-5 rounded-full transition-colors ${
              openLinksInExternalBrowser ? 'bg-[var(--hermes-accent)]' : 'bg-[var(--bg-tertiary)]'
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
            <span className="text-sm font-medium text-text-primary">使用系统默认浏览器</span>
            <p className="text-xs text-text-muted">点击链接时在外部浏览器中打开</p>
          </div>
        </label>
      </div>

      {/* System prompt */}
      <div>
        <label className="text-sm font-medium text-text-secondary mb-2 block">
          系统提示词
        </label>
        <textarea
          value={systemPrompt}
          onChange={(e) => updateSettings({ systemPrompt: e.target.value })}
          placeholder="可选：设置 AI 系统提示词..."
          rows={4}
          className="w-full bg-[var(--bg-secondary)] text-text-primary text-sm rounded-lg px-3 py-2 outline-none border border-[var(--hermes-border)] focus:border-[var(--hermes-accent)] transition-colors resize-none"
        />
      </div>
    </div>
  );
}

function AboutSection() {
  const [version, setVersion] = useState('v...');
  useEffect(() => {
    window.api?.app?.getVersion?.()?.then((v: string) => { if (v) setVersion('v' + v); })?.catch(() => {});
  }, []);

  return (
    <div className="space-y-4">
      <h3 className="text-base font-semibold text-text-primary flex items-center gap-2">
        <Info size={16} className="text-[var(--hermes-accent)]" />
        关于
      </h3>

      <div className="rounded-lg border border-[var(--hermes-border)] bg-[var(--bg-secondary)] p-4 space-y-3">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-[var(--hermes-accent)]/10 flex items-center justify-center">
            <span className="text-xl">🔮</span>
          </div>
          <div>
            <h4 className="text-sm font-semibold text-text-primary">Hermes Desktop</h4>
            <p className="text-xs text-text-muted">{version}</p>
          </div>
        </div>
        <p className="text-xs text-text-muted">
          基于 Hermes Agent 的桌面 AI 助手。支持多模型对话、工具调用、定时任务、看板管理等功能。
        </p>
      </div>
    </div>
  );
}
