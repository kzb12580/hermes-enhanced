import React, { useState, useRef, useCallback, useEffect } from 'react';
import {
  SendHorizonal,
  Square,
  Paperclip,
  ChevronDown,
  Brain,
  BrainCircuit,
  Zap,
  Sparkles,
  X,
} from 'lucide-react';
import { useChatStore } from '../../stores/chatStore';
import type { AttachmentInfo } from '../../stores/chatStore';
import { useSettingsStore } from '../../stores/settingsStore';
import apiClient from '../../lib/api';
import { SkillsPanel } from '../skills/SkillsPanel';
import { ContextMenu, createEditMenuItems, useContextMenu } from '../ui/ContextMenu';

// 思考模式配置
const THINKING_MODES = [
  { value: 'off' as const, label: '关闭', icon: Zap, desc: '标准模式，快速响应' },
  { value: 'auto' as const, label: '自动', icon: Brain, desc: '复杂问题自动深度思考' },
  { value: 'on' as const, label: '深度', icon: BrainCircuit, desc: '强制深度思考，更准确但更慢' },
];

export function InputBar() {
  const [input, setInput] = useState('');
  const [showModelPicker, setShowModelPicker] = useState(false);
  const [showThinkingPicker, setShowThinkingPicker] = useState(false);
  const [showSkillsPanel, setShowSkillsPanel] = useState(false);
  const [pendingAttachments, setPendingAttachments] = useState<AttachmentInfo[]>([]);
  const [isUploading, setIsUploading] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const modelPickerRef = useRef<HTMLDivElement>(null);
  const thinkingPickerRef = useRef<HTMLDivElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // 右键菜单
  const { isOpen, position, menuItems, openMenu, closeMenu } = useContextMenu();

  const { sendMessage, isGenerating, stopGeneration, activeSkills, toggleActiveSkill } = useChatStore();
  const {
    sendShortcut,
    providers,
    currentModel,
    currentProvider,
    setCurrentModel,
    thinkingMode,
    thinkingBudget,
    updateSettings,
  } = useSettingsStore();

  // 点击外部关闭下拉菜单
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (
        modelPickerRef.current &&
        !modelPickerRef.current.contains(e.target as Node)
      ) {
        setShowModelPicker(false);
      }
      if (
        thinkingPickerRef.current &&
        !thinkingPickerRef.current.contains(e.target as Node)
      ) {
        setShowThinkingPicker(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  // Auto-resize textarea
  const adjustHeight = useCallback(() => {
    const textarea = textareaRef.current;
    if (!textarea) return;
    textarea.style.height = 'auto';
    const maxHeight = 200;
    textarea.style.height = `${Math.min(textarea.scrollHeight, maxHeight)}px`;
  }, []);

  useEffect(() => {
    adjustHeight();
  }, [input, adjustHeight]);

  const handleSend = useCallback(() => {
    const trimmed = input.trim();
    if ((!trimmed && pendingAttachments.length === 0) || isGenerating) return;
    sendMessage(trimmed || '(请分析附件)', pendingAttachments.length > 0 ? pendingAttachments : undefined);
    setInput('');
    setPendingAttachments([]);
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
    }
  }, [input, isGenerating, sendMessage, pendingAttachments]);

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (sendShortcut === 'enter') {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        handleSend();
      }
    } else {
      if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
        e.preventDefault();
        handleSend();
      }
    }
  };

  // 右键菜单处理
  const handleContextMenu = useCallback((e: React.MouseEvent<HTMLTextAreaElement>) => {
    const textarea = textareaRef.current;
    if (!textarea) return;

    const hasSelection = textarea.selectionStart !== textarea.selectionEnd;
    const clipboardText = input;

    const items = createEditMenuItems({
      onCut: hasSelection
        ? () => {
            const selected = input.substring(textarea.selectionStart, textarea.selectionEnd);
            navigator.clipboard.writeText(selected);
            setInput(input.substring(0, textarea.selectionStart) + input.substring(textarea.selectionEnd));
          }
        : undefined,
      onCopy: hasSelection
        ? () => {
            const selected = input.substring(textarea.selectionStart, textarea.selectionEnd);
            navigator.clipboard.writeText(selected);
          }
        : undefined,
      onPaste: async () => {
        try {
          const text = await navigator.clipboard.readText();
          const start = textarea.selectionStart;
          const end = textarea.selectionEnd;
          setInput(input.substring(0, start) + text + input.substring(end));
        } catch {
          // Clipboard API 可能被拒绝
        }
      },
      onSelectAll: () => {
        textarea.select();
      },
      hasSelection,
    });

    openMenu(e, items);
  }, [input, openMenu]);

  const handleStop = useCallback(() => {
    stopGeneration();
  }, [stopGeneration]);

  // 文件选择处理 — 实际上传文件到后端
  const handleFileSelect = useCallback(async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (!files || files.length === 0) return;

    setIsUploading(true);
    try {
      const uploadPromises = Array.from(files).map(file => apiClient.uploadFile(file));
      const results = await Promise.all(uploadPromises);
      setPendingAttachments(prev => [...prev, ...results]);
    } catch (err: any) {
      console.error('[InputBar] File upload failed:', err);
      alert(`文件上传失败: ${err.message}`);
    } finally {
      setIsUploading(false);
      if (fileInputRef.current) {
        fileInputRef.current.value = '';
      }
    }
  }, []);

  // 获取当前供应商名称和模型简称
  const currentProviderObj = providers.find((p) => p.id === currentProvider);
  const currentProviderName = currentProviderObj?.name || currentProvider;
  const modelShort = currentModel.length > 20
    ? currentModel.slice(0, 18) + '...'
    : currentModel;

  // 获取当前思考模式信息
  const currentThinking = THINKING_MODES.find((m) => m.value === thinkingMode) || THINKING_MODES[0];
  const ThinkingIcon = currentThinking.icon;

  // 判断是否支持思考模式（DeepSeek、Claude等）
  const supportsThinking =
    currentModel.includes('deepseek') ||
    currentModel.includes('claude') ||
    currentModel.includes('o1') ||
    currentModel.includes('o3') ||
    currentModel.includes('reasoner') ||
    currentModel.includes('thinking');

  const canSend = (input.trim().length > 0 || pendingAttachments.length > 0) && !isGenerating && !isUploading;

  return (
    <div className="border-t border-border bg-bg-secondary p-4">
      <div className="max-w-3xl mx-auto relative">
        {/* 模型切换栏 */}
        <div className="flex items-center gap-2 mb-2">
          {/* 供应商/模型选择器 */}
          <div className="relative" ref={modelPickerRef}>
            <button
              onClick={() => setShowModelPicker(!showModelPicker)}
              className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs
                bg-bg-tertiary text-text-secondary
                hover:bg-bg-surface transition-colors border border-border"
            >
              <span className="text-accent font-medium">
                {currentProviderName}
              </span>
              <span className="text-text-muted">/</span>
              <span>{modelShort}</span>
              <ChevronDown size={12} className={`transition-transform ${showModelPicker ? 'rotate-180' : ''}`} />
            </button>

            {/* 模型下拉菜单 */}
            {showModelPicker && (
              <div className="absolute bottom-full left-0 mb-1 w-72 max-h-80 overflow-y-auto
                bg-bg-primary border border-border rounded-lg shadow-xl z-50">
                {providers
                  .filter((p) => p.enabled && p.models.length > 0)
                  .map((provider) => (
                    <div key={provider.id}>
                      <div className="px-3 py-1.5 text-xs font-medium text-text-muted bg-bg-tertiary sticky top-0">
                        {provider.name}
                      </div>
                      {provider.models.map((model) => (
                        <button
                          key={`${provider.id}-${model}`}
                          onClick={() => {
                            setCurrentModel(model, provider.id);
                            setShowModelPicker(false);
                          }}
                          className={`w-full text-left px-3 py-1.5 text-xs transition-colors
                            ${model === currentModel && provider.id === currentProvider
                              ? 'bg-accent/15 text-accent'
                              : 'text-text-secondary hover:bg-bg-tertiary'
                            }`}
                        >
                          {model}
                        </button>
                      ))}
                    </div>
                  ))}
                {providers.filter((p) => p.enabled && p.models.length > 0).length === 0 && (
                  <div className="px-3 py-4 text-xs text-text-muted text-center">
                    暂无可用模型，请在设置中添加
                  </div>
                )}
              </div>
            )}
          </div>

          {/* 思考模式选择器 */}
          {supportsThinking && (
            <div className="relative" ref={thinkingPickerRef}>
              <button
                onClick={() => setShowThinkingPicker(!showThinkingPicker)}
                className={`flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs
                  border transition-colors
                  ${thinkingMode === 'on'
                    ? 'bg-accent/10 text-accent border-accent/30'
                    : thinkingMode === 'auto'
                      ? 'bg-success/10 text-success border-success/30'
                      : 'bg-bg-tertiary text-text-muted border-border'
                  }`}
              >
                <ThinkingIcon size={12} />
                <span>{currentThinking.label}</span>
                <ChevronDown size={10} className={`transition-transform ${showThinkingPicker ? 'rotate-180' : ''}`} />
              </button>

              {/* 思考模式下拉 */}
              {showThinkingPicker && (
                <div className="absolute bottom-full left-0 mb-1 w-56
                  bg-bg-primary border border-border rounded-lg shadow-xl z-50">
                  <div className="px-3 py-1.5 text-xs font-medium text-text-muted bg-bg-tertiary">
                    思考模式
                  </div>
                  {THINKING_MODES.map((mode) => {
                    const Icon = mode.icon;
                    return (
                      <button
                        key={mode.value}
                        onClick={() => {
                          updateSettings({ thinkingMode: mode.value });
                          setShowThinkingPicker(false);
                        }}
                        className={`w-full text-left px-3 py-2 text-xs transition-colors flex items-start gap-2
                          ${mode.value === thinkingMode
                            ? 'bg-accent/15 text-accent'
                            : 'text-text-secondary hover:bg-bg-tertiary'
                          }`}
                      >
                        <Icon size={14} className="mt-0.5 flex-shrink-0" />
                        <div>
                          <div className="font-medium">{mode.label}</div>
                          <div className="text-text-muted text-[10px] mt-0.5">
                            {mode.desc}
                          </div>
                        </div>
                      </button>
                    );
                  })}

                  {/* 思考预算 */}
                  {thinkingMode !== 'off' && (
                    <div className="px-3 py-2 border-t border-border">
                      <label className="text-[10px] text-text-muted block mb-1">
                        思考预算: {thinkingBudget} tokens
                      </label>
                      <input
                        type="range"
                        min={1024}
                        max={32768}
                        step={1024}
                        value={thinkingBudget}
                        onChange={(e) =>
                          updateSettings({ thinkingBudget: parseInt(e.target.value) })
                        }
                        className="w-full h-1 accent-accent"
                      />
                      <div className="flex justify-between text-[10px] text-text-muted">
                        <span>1K</span>
                        <span>32K</span>
                      </div>
                    </div>
                  )}
                </div>
              )}
            </div>
          )}
        </div>

        {/* Active skills bar */}
        {activeSkills.length > 0 && (
          <div className="flex items-center gap-1.5 mb-2 flex-wrap">
            <Sparkles size={12} className="text-accent flex-shrink-0" />
            {activeSkills.map((skillId) => (
              <span
                key={skillId}
                className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-xs
                  bg-accent/15 text-accent border border-accent/20"
              >
                {skillId}
                <button
                  onClick={() => toggleActiveSkill(skillId)}
                  className="hover:text-error transition-colors"
                >
                  <X size={10} />
                </button>
              </span>
            ))}
          </div>
        )}

        {/* Pending attachments bar */}
        {pendingAttachments.length > 0 && (
          <div className="flex items-center gap-1.5 mb-2 flex-wrap">
            {pendingAttachments.map((att, idx) => (
              <span
                key={idx}
                className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-xs
                  bg-bg-tertiary text-text-secondary border border-border"
              >
                📎 {att.filename}
                <button
                  onClick={() => setPendingAttachments(prev => prev.filter((_, i) => i !== idx))}
                  className="hover:text-error transition-colors"
                >
                  <X size={10} />
                </button>
              </span>
            ))}
            {isUploading && <span className="text-xs text-text-muted">上传中...</span>}
          </div>
        )}

        {/* 输入框 */}
        <div className="flex items-end gap-2 bg-bg-primary rounded-xl border border-border focus-within:border-accent transition-colors">
          <input
            type="file"
            ref={fileInputRef}
            onChange={handleFileSelect}
            className="hidden"
            multiple
          />
          <button
            onClick={() => fileInputRef.current?.click()}
            className="flex-shrink-0 p-3 text-text-muted hover:text-text-primary transition-colors"
            title="添加附件"
          >
            <Paperclip size={18} />
          </button>

          <button
            onClick={() => setShowSkillsPanel(true)}
            className={`flex-shrink-0 p-3 transition-colors ${
              activeSkills.length > 0
                ? 'text-accent hover:text-accent-hover'
                : 'text-text-muted hover:text-text-primary'
            }`}
            title="技能管理"
          >
            <Sparkles size={18} />
          </button>

          <textarea
            ref={textareaRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            onContextMenu={handleContextMenu}
            placeholder="输入消息... (Shift+Enter 换行)"
            rows={1}
            className="flex-1 bg-transparent resize-none py-3 text-sm text-text-primary placeholder-text-muted outline-none max-h-[200px]"
            style={{ minHeight: '24px' }}
            disabled={isGenerating}
          />

          <div className="flex-shrink-0 p-2">
            {isGenerating ? (
              <button
                onClick={handleStop}
                className="p-2 rounded-lg bg-error text-white hover:opacity-80 transition-opacity"
                title="停止生成"
              >
                <Square size={16} />
              </button>
            ) : (
              <button
                onClick={handleSend}
                disabled={!canSend}
                className={`
                  p-2 rounded-lg transition-all
                  ${canSend
                    ? 'bg-accent text-bg-primary hover:bg-accent-hover'
                    : 'bg-bg-tertiary text-text-muted cursor-not-allowed'
                  }
                `}
                title="发送消息"
              >
                <SendHorizonal size={16} />
              </button>
            )}
          </div>
        </div>

        {/* Hint text */}
        <p className="text-center text-xs text-text-muted mt-2">
          {sendShortcut === 'enter'
            ? 'Enter 发送 · Shift+Enter 换行'
            : 'Ctrl+Enter 发送 · Enter 换行'}
        </p>
      </div>

      {/* Skills Panel Modal */}
      <SkillsPanel
        open={showSkillsPanel}
        onClose={() => setShowSkillsPanel(false)}
        activeSkills={activeSkills}
        onToggleActive={toggleActiveSkill}
      />

      {/* Context Menu */}
      {isOpen && (
        <ContextMenu
          x={position.x}
          y={position.y}
          items={menuItems}
          onClose={closeMenu}
        />
      )}
    </div>
  );
}

export default InputBar;
