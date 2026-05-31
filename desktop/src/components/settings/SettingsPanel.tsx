import React, { useState, useEffect, useRef, useCallback } from 'react';
import { X, Settings2, Cpu, Key, Info, Thermometer, Hash, Globe, Keyboard, Wifi, Mail, Zap, Copy, Scissors, ClipboardPaste, TextCursorInput } from 'lucide-react';
import { useSystemStore } from '../../stores/systemStore';
import { useSettingsStore } from '../../stores/settingsStore';
import { ModelConfig } from './ModelConfig';
import { VisionModelDownload } from './VisionModelDownload';
import { SkillsPanel } from './SkillsPanel';
import { DiagnosticsPanel } from './DiagnosticsPanel';
import { EmailConfig } from '../email/EmailConfig';
import { getBackendUrl } from '../../lib/utils';

type SettingsTab = 'general' | 'models' | 'skills' | 'network' | 'email' | 'apikeys' | 'diagnostics' | 'about';

const tabs: { id: SettingsTab; label: string; icon: React.ReactNode }[] = [
  { id: 'general', label: '通用', icon: <Settings2 size={16} /> },
  { id: 'models', label: '模型', icon: <Cpu size={16} /> },
  { id: 'skills', label: '技能', icon: <Zap size={16} /> },
  { id: 'network', label: '网络', icon: <Wifi size={16} /> },
  { id: 'email', label: '邮件', icon: <Mail size={16} /> },
  { id: 'apikeys', label: 'API 密钥', icon: <Key size={16} /> },
  { id: 'diagnostics', label: '诊断', icon: <Wrench size={16} /> },
  { id: 'about', label: '关于', icon: <Info size={16} /> },
];

// ── 右键菜单组件 ──────────────────────────────────────────────────────
interface ContextMenuItem {
  label: string;
  icon?: React.ReactNode;
  action: () => void;
  disabled?: boolean;
}

function ContextMenu({ x, y, items, onClose }: { x: number; y: number; items: ContextMenuItem[]; onClose: () => void }) {
  const menuRef = useRef<HTMLDivElement>(null);
  const [pos, setPos] = useState({ x, y });

  useEffect(() => {
    if (menuRef.current) {
      const rect = menuRef.current.getBoundingClientRect();
      const vw = window.innerWidth;
      const vh = window.innerHeight;
      setPos({
        x: Math.max(0, x + rect.width > vw ? vw - rect.width - 8 : x),
        y: Math.max(0, y + rect.height > vh ? vh - rect.height - 8 : y),
      });
    }
  }, [x, y]);

  useEffect(() => {
    const handleClick = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) onClose();
    };
    const handleEsc = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    document.addEventListener('mousedown', handleClick);
    document.addEventListener('keydown', handleEsc);
    return () => {
      document.removeEventListener('mousedown', handleClick);
      document.removeEventListener('keydown', handleEsc);
    };
  }, [onClose]);

  return (
    <div ref={menuRef} style={{
      position: 'fixed', left: pos.x, top: pos.y, zIndex: 99999,
      background: 'var(--bg-secondary, #1f2937)', border: '1px solid var(--border, #374151)',
      borderRadius: 8, padding: 4, minWidth: 160, boxShadow: '0 4px 12px rgba(0,0,0,0.3)',
    }}>
      {items.map((item, i) => (
        <button key={i} disabled={item.disabled} onClick={() => { item.action(); onClose(); }}
          style={{
            display: 'flex', alignItems: 'center', gap: 8, width: '100%',
            padding: '6px 12px', border: 'none', borderRadius: 6,
            background: 'transparent', cursor: item.disabled ? 'default' : 'pointer',
            color: item.disabled ? 'var(--text-muted, #6b7280)' : 'var(--text-primary, #e5e7eb)',
            fontSize: 13, opacity: item.disabled ? 0.5 : 1,
          }}
          onMouseEnter={e => { if (!item.disabled) (e.target as HTMLElement).style.background = 'var(--bg-tertiary, #374151)'; }}
          onMouseLeave={e => { (e.target as HTMLElement).style.background = 'transparent'; }}
        >
          {item.icon && <span style={{ width: 16, height: 16, display: 'flex', alignItems: 'center' }}>{item.icon}</span>}
          {item.label}
        </button>
      ))}
    </div>
  );
}

// ── Hook: 输入框右键菜单 ──────────────────────────────────────────────
function useInputContextMenu() {
  const [menu, setMenu] = useState<{ x: number; y: number; items: ContextMenuItem[] } | null>(null);

  const handleContextMenu = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    const target = e.target as HTMLInputElement | HTMLTextAreaElement;
    const hasSelection = target.selectionStart !== target.selectionEnd;

    const items: ContextMenuItem[] = [
      {
        label: '撤销',
        icon: <span style={{ fontSize: 12 }}>↩</span>,
        action: () => document.execCommand('undo'),
      },
      {
        label: '剪切',
        icon: <Scissors size={14} />,
        action: () => document.execCommand('cut'),
        disabled: !hasSelection,
      },
      {
        label: '复制',
        icon: <Copy size={14} />,
        action: () => document.execCommand('copy'),
        disabled: !hasSelection,
      },
      {
        label: '粘贴',
        icon: <ClipboardPaste size={14} />,
        action: async () => {
          try {
            const text = await navigator.clipboard.readText();
            document.execCommand('insertText', false, text);
          } catch {
            document.execCommand('paste');
          }
        },
      },
      {
        label: '全选',
        icon: <TextCursorInput size={14} />,
        action: () => { target.focus(); target.select(); },
      },
    ];

    setMenu({ x: e.clientX, y: e.clientY, items });
  }, []);

  const closeMenu = useCallback(() => setMenu(null), []);

  return { menu, handleContextMenu, closeMenu };
}

export function SettingsPanel() {
  const { setSettingsOpen } = useSystemStore();
  const settings = useSettingsStore();
  const [activeTab, setActiveTab] = useState<SettingsTab>('general');
  const ctx = useInputContextMenu();

  const handleClose = () => setSettingsOpen(false);

  const handleBackdropClick = (e: React.MouseEvent) => {
    if (e.target === e.currentTarget) handleClose();
  };

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
      <div className="w-full max-w-2xl max-h-[85vh] bg-bg-secondary rounded-xl shadow-2xl border border-border overflow-hidden flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-border">
          <h2 className="text-lg font-semibold text-text-primary">设置</h2>
          <button
            onClick={handleClose}
            className="p-1.5 rounded-lg text-text-muted hover:text-text-primary hover:bg-bg-tertiary transition-colors"
          >
            <X size={18} />
          </button>
        </div>

        {/* Content */}
        <div className="flex flex-1 min-h-0">
          {/* Tabs sidebar */}
          <nav className="w-40 flex-shrink-0 border-r border-border py-2 px-2 space-y-0.5">
            {tabs.map((tab) => (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={`
                  flex items-center gap-2 w-full px-3 py-2 rounded-lg text-sm transition-colors
                  ${activeTab === tab.id
                    ? 'bg-bg-tertiary text-text-primary font-medium'
                    : 'text-text-muted hover:text-text-primary hover:bg-bg-tertiary/50'
                  }
                `}
              >
                {tab.icon}
                <span>{tab.label}</span>
              </button>
            ))}
          </nav>

          {/* Tab content */}
          <div className="flex-1 overflow-y-auto p-6" onContextMenu={ctx.handleContextMenu}>
            {activeTab === 'general' && (
              <GeneralSettings />
            )}
            {activeTab === 'models' && (
              <div>
                <h3 className="text-base font-semibold text-text-primary mb-4">模型配置</h3>
                <ModelConfig />
                <div className="mt-6 pt-6 border-t border-border">
                  <VisionModelDownload />
                </div>
              </div>
            )}
            {activeTab === 'network' && (
              <NetworkSettings />
            )}
            {activeTab === 'skills' && (
              <div>
                <SkillsPanel />
              </div>
            )}
            {activeTab === 'email' && (
              <div>
                <h3 className="text-base font-semibold text-text-primary mb-4">邮件配置</h3>
                <EmailConfig />
              </div>
            )}
            {activeTab === 'apikeys' && (
              <ApiKeysSettings />
            )}
            {activeTab === 'diagnostics' && (
              <DiagnosticsPanel />
            )}
            {activeTab === 'about' && (
              <AboutSection />
            )}
          </div>
        </div>
      </div>

      {/* Context Menu */}
      {ctx.menu && (
        <ContextMenu x={ctx.menu.x} y={ctx.menu.y} items={ctx.menu.items} onClose={ctx.closeMenu} />
      )}
    </div>
  );
}

function GeneralSettings() {
  const {
    language, fontSize, sendShortcut, showSystemMessages, autoScroll,
    temperature, maxTokens, systemPrompt, backendUrl,
    openLinksInExternalBrowser, updateSettings,
  } = useSettingsStore();

  return (
    <div className="space-y-6">
      <h3 className="text-base font-semibold text-text-primary">通用设置</h3>

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
          className="w-full bg-bg-primary text-text-primary text-sm rounded-lg px-3 py-2 outline-none border border-border focus:border-accent transition-colors font-mono"
        />
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
                  ? 'border-accent bg-accent/10 text-accent'
                  : 'border-border text-text-muted hover:border-text-muted'
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
                  ? 'border-accent bg-accent/10 text-accent'
                  : 'border-border text-text-muted hover:border-text-muted'
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
          className="w-full accent-accent"
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
          className="w-full accent-accent"
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
          value={maxTokens}
          onChange={(e) => updateSettings({ maxTokens: Number(e.target.value) })}
          min={256}
          max={128000}
          className="w-full bg-bg-primary text-text-primary text-sm rounded-lg px-3 py-2 outline-none border border-border focus:border-accent transition-colors font-mono"
        />
      </div>

      {/* Open links in external browser */}
      <div>
        <label className="flex items-center gap-3 cursor-pointer">
          <div
            className={`relative w-10 h-5 rounded-full transition-colors ${
              openLinksInExternalBrowser ? 'bg-accent' : 'bg-bg-tertiary'
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
          className="w-full bg-bg-primary text-text-primary text-sm rounded-lg px-3 py-2 outline-none border border-border focus:border-accent transition-colors resize-none"
        />
      </div>
    </div>
  );
}

function ApiKeysSettings() {
  const { providers, updateProvider } = useSettingsStore();

  return (
    <div className="space-y-6">
      <h3 className="text-base font-semibold text-text-primary mb-2">API 密钥管理</h3>
      <p className="text-sm text-text-muted mb-4">
        配置各模型提供商的 API 密钥。密钥将安全存储在本地。
      </p>

      {providers.map((provider) => (
        <div key={provider.id} className="space-y-2">
          <label className="flex items-center gap-2 text-sm font-medium text-text-secondary">
            <Key size={14} className="text-accent" />
            {provider.name}
          </label>
          <input
            type="password"
            value={provider.apiKey}
            onChange={(e) => updateProvider(provider.id, { apiKey: e.target.value })}
            placeholder={`输入 ${provider.name} API Key...`}
            className="w-full bg-bg-primary text-text-primary text-sm rounded-lg px-3 py-2 outline-none border border-border focus:border-accent transition-colors font-mono"
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
      <h3 className="text-base font-semibold text-text-primary">关于 Hermes Desktop</h3>

      <div className="rounded-lg border border-border p-4 space-y-4">
        <div className="flex items-center gap-3">
          <div className="w-12 h-12 rounded-xl bg-accent/10 flex items-center justify-center">
            <span className="text-2xl">🔮</span>
          </div>
          <div>
            <h4 className="text-base font-semibold text-text-primary">Hermes Desktop</h4>
            <p className="text-sm text-text-muted">{version}</p>
          </div>
        </div>

        <p className="text-sm text-text-secondary leading-relaxed">
          Hermes Desktop 是一个基于 Hermes Agent 的桌面客户端，支持多种 AI 模型提供商，
          提供代码生成、文件操作、网页搜索等智能工具能力。
        </p>

        <div className="grid grid-cols-2 gap-3 text-sm">
          <div>
            <span className="text-text-muted">框架</span>
            <p className="text-text-primary">Electron + React + TypeScript</p>
          </div>
          <div>
            <span className="text-text-muted">后端</span>
            <p className="text-text-primary">Python FastAPI</p>
          </div>
          <div>
            <span className="text-text-muted">状态管理</span>
            <p className="text-text-primary">Zustand</p>
          </div>
          <div>
            <span className="text-text-muted">样式</span>
            <p className="text-text-primary">TailwindCSS</p>
          </div>
        </div>
      </div>

      <div className="text-center text-xs text-text-muted">
        <p>由 <a href="https://nousresearch.com" className="text-accent hover:underline" target="_blank" rel="noopener">Nous Research</a> 出品</p>
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

  useEffect(() => {
    fetch(`${getBackendUrl()}/api/setup/network`).then(r => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json(); }).then(setConfig).catch(() => {});
    fetch(`${getBackendUrl()}/api/setup/mirrors`).then(r => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json(); }).then(setMirrors).catch(() => {});
  }, []);

  const save = async () => {
    setSaving(true);
    try {
      const res = await fetch(`${getBackendUrl()}/api/setup/network`, {
        method: 'PUT', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(config),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
    } catch (e) {}
    setSaving(false);
  };

  const diagnose = async () => {
    setDiagnosing(true);
    try {
      const res = await fetch(`${getBackendUrl()}/api/setup/diagnose`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
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
      <h3 className="text-base font-semibold text-text-primary">网络设置</h3>

      {/* 代理模式 */}
      <div className="rounded-lg border border-border p-4 space-y-3">
        <label className="text-sm font-medium text-text-secondary">代理模式</label>
        <div className="flex gap-2">
          {modes.map(m => (
            <button key={m.key} onClick={() => setConfig((c: any) => ({ ...c, proxy_mode: m.key }))}
              className={`px-3 py-1.5 rounded-full text-sm transition-colors ${
                config.proxy_mode === m.key
                  ? 'bg-accent text-white'
                  : 'bg-bg-tertiary text-text-muted hover:text-text-primary'
              }`}>{m.label}</button>
          ))}
        </div>
        {config.detected_proxy && config.proxy_mode !== 'disabled' && (
          <p className="text-xs text-green-400">检测到代理: {config.detected_proxy}</p>
        )}
      </div>

      {/* 手动代理 */}
      {config.proxy_mode === 'manual' && (
        <div className="rounded-lg border border-border p-4 space-y-3">
          <label className="text-sm font-medium text-text-secondary">代理地址</label>
          <input value={config.proxy || ''} onChange={e => setConfig((c: any) => ({ ...c, proxy: e.target.value }))}
            placeholder="http://127.0.0.1:7890"
            className="w-full px-3 py-2 rounded-lg bg-bg-tertiary text-text-primary border border-border text-sm" />
        </div>
      )}

      {/* HuggingFace 镜像 */}
      <div className="rounded-lg border border-border p-4 space-y-3">
        <label className="text-sm font-medium text-text-secondary">HuggingFace 模型镜像</label>
        <p className="text-xs text-text-muted">中国大陆用户建议选择 hf-mirror</p>
        <div className="flex gap-2 flex-wrap">
          {Object.entries(mirrors.hf || {}).map(([key]: [string, any]) => (
            <button key={key} onClick={() => setConfig((c: any) => ({ ...c, hf_mirror: key }))}
              className={`px-3 py-1.5 rounded-full text-sm transition-colors ${
                config.hf_mirror === key
                  ? 'bg-purple-600 text-white'
                  : 'bg-bg-tertiary text-text-muted hover:text-text-primary'
              }`}>
              {key === 'official' ? '🌐 官方' : key === 'hf-mirror' ? '🇨🇳 hf-mirror' : key}
            </button>
          ))}
        </div>
      </div>

      {/* PyPI 镜像 */}
      <div className="rounded-lg border border-border p-4 space-y-3">
        <label className="text-sm font-medium text-text-secondary">PyPI 下载镜像</label>
        <div className="flex gap-2 flex-wrap">
          {Object.entries(mirrors.pypi || {}).map(([key]: [string, any]) => (
            <button key={key} onClick={() => setConfig((c: any) => ({ ...c, pypi_mirror: key }))}
              className={`px-3 py-1.5 rounded-full text-sm transition-colors ${
                config.pypi_mirror === key
                  ? 'bg-purple-600 text-white'
                  : 'bg-bg-tertiary text-text-muted hover:text-text-primary'
              }`}>
              {key === 'official' ? '🌐 官方' : key === 'tuna' ? '🇨🇳 清华' : key === 'aliyun' ? '🇨🇳 阿里云' : key}
            </button>
          ))}
        </div>
      </div>

      {/* 操作按钮 */}
      <div className="flex gap-3">
        <button onClick={save} disabled={saving}
          className="px-4 py-2 rounded-lg bg-accent text-white text-sm font-medium hover:opacity-90 transition-opacity disabled:opacity-50">
          {saving ? '保存中...' : '💾 保存配置'}
        </button>
        <button onClick={diagnose} disabled={diagnosing}
          className="px-4 py-2 rounded-lg bg-bg-tertiary text-text-secondary text-sm font-medium hover:text-text-primary transition-colors disabled:opacity-50">
          {diagnosing ? '诊断中...' : '🔍 网络诊断'}
        </button>
      </div>

      {/* 诊断结果 */}
      {diagnosis && !diagnosis.error && (
        <div className="rounded-lg border border-border p-4 space-y-2 text-sm">
          <pre className="text-text-secondary whitespace-pre-wrap">{JSON.stringify(diagnosis, null, 2)}</pre>
        </div>
      )}
      {diagnosis?.error && (
        <div className="rounded-lg border border-red-500/30 p-4 text-sm text-red-400">
          {diagnosis.error}
        </div>
      )}
    </div>
  );
}
