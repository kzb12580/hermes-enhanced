import React, { useState, useRef, useCallback, useEffect } from 'react';
import { SendHorizonal, Square, Paperclip } from 'lucide-react';
import { useChatStore } from '../../stores/chatStore';
import { useSettingsStore } from '../../stores/settingsStore';

export function InputBar() {
  const [input, setInput] = useState('');
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const { sendMessage, isGenerating, stopGeneration } = useChatStore();
  const { sendShortcut } = useSettingsStore();

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
    if (!trimmed || isGenerating) return;
    sendMessage(trimmed);
    setInput('');
    // Reset height
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
    }
  }, [input, isGenerating, sendMessage]);

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (sendShortcut === 'enter') {
      // Enter to send, Shift+Enter for newline
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        handleSend();
      }
    } else {
      // Ctrl+Enter to send, Enter for newline
      if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
        e.preventDefault();
        handleSend();
      }
    }
  };

  const handleStop = useCallback(() => {
    stopGeneration();
  }, [stopGeneration]);

  const canSend = input.trim().length > 0 && !isGenerating;

  return (
    <div className="border-t border-[var(--border)] bg-[var(--bg-secondary)] p-4">
      <div className="max-w-3xl mx-auto relative">
        <div className="flex items-end gap-2 bg-[var(--bg-primary)] rounded-xl border border-[var(--border)] focus-within:border-[var(--accent)] transition-colors">
          {/* Attach button */}
          <button
            className="flex-shrink-0 p-3 text-[var(--text-muted)] hover:text-[var(--text-primary)] transition-colors"
            title="添加附件"
            disabled
          >
            <Paperclip size={18} />
          </button>

          {/* Textarea */}
          <textarea
            ref={textareaRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="输入消息... (Shift+Enter 换行)"
            rows={1}
            className="flex-1 bg-transparent resize-none py-3 text-sm text-[var(--text-primary)] placeholder-[var(--text-muted)] outline-none max-h-[200px]"
            style={{ minHeight: '24px' }}
            disabled={isGenerating}
          />

          {/* Send / Stop button */}
          <div className="flex-shrink-0 p-2">
            {isGenerating ? (
              <button
                onClick={handleStop}
                className="p-2 rounded-lg bg-[var(--error)] text-white hover:opacity-80 transition-opacity"
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
                    ? 'bg-[var(--accent)] text-[var(--bg-primary)] hover:bg-[var(--accent-hover)]'
                    : 'bg-[var(--bg-tertiary)] text-[var(--text-muted)] cursor-not-allowed'
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
        <p className="text-center text-xs text-[var(--text-muted)] mt-2">
          {sendShortcut === 'enter'
            ? 'Enter 发送 · Shift+Enter 换行'
            : 'Ctrl+Enter 发送 · Enter 换行'}
        </p>
      </div>
    </div>
  );
}

export default InputBar;
