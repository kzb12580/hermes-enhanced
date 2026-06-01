import React, { useCallback, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import rehypeSanitize from 'rehype-sanitize';
import { CodeBlock } from './CodeBlock';
import { ToolCallCard } from './ToolCallCard';
import { DisplayMessage } from '../../stores/chatStore';
import { User, Bot, AlertCircle, Loader2, ChevronDown, ChevronRight, Brain } from 'lucide-react';
import { ContextMenu, useContextMenu } from '../ui/ContextMenu';
import { Copy } from 'lucide-react';

interface MessageBubbleProps {
  message: DisplayMessage;
}

export const MessageBubble = React.memo(function MessageBubble({ message }: MessageBubbleProps) {
  const isUser = message.role === 'user';
  const isSystem = message.role === 'system';
  const isTool = message.role === 'tool';

  // Thinking section expand/collapse state
  const [thinkingExpanded, setThinkingExpanded] = useState(false);

  // 右键菜单
  const { isOpen, position, menuItems, openMenu, closeMenu } = useContextMenu();

  const handleContextMenu = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    const items = [
      {
        label: '复制',
        icon: <Copy size={14} />,
        shortcut: 'Ctrl+C',
        action: () => navigator.clipboard.writeText(message.content),
      },
    ];
    openMenu(e, items);
  }, [message.content, openMenu]);

  if (isSystem) {
    return (
      <div className="flex justify-center my-2 fade-in">
        <div className="px-3 py-1.5 rounded-full bg-[var(--bg-tertiary)] text-text-muted text-xs">
          {message.content}
        </div>
      </div>
    );
  }

  if (isTool) {
    return (
      <div className="flex gap-3 px-4 py-2 my-1 fade-in">
        <div className="flex-shrink-0 w-7 h-7 rounded-full bg-[var(--bg-tertiary)] flex items-center justify-center mt-0.5">
          <span className="text-xs font-mono text-text-muted">T</span>
        </div>
        <div className="min-w-0 flex-1">
          <div className="text-xs text-text-muted mb-1">工具结果</div>
          <pre className="text-xs font-mono bg-[var(--bg-secondary)] rounded p-2 overflow-x-auto text-text-secondary">
            {message.content}
          </pre>
        </div>
      </div>
    );
  }

  return (
    <div className={`flex gap-3 px-4 py-3 my-1 fade-in ${isUser ? 'flex-row-reverse' : ''}`}>
      {/* Avatar */}
      <div
        className={`
          flex-shrink-0 w-8 h-8 rounded-full flex items-center justify-center
          ${isUser ? 'bg-[var(--hermes-accent)] text-bg-primary' : 'bg-[var(--bg-tertiary)] text-text-secondary'}
        `}
      >
        {isUser ? <User size={16} /> : <Bot size={16} />}
      </div>

      {/* Content */}
      <div
        className={`min-w-0 flex-1 max-w-[80%] ${isUser ? 'flex flex-col items-end' : ''}`}
        onContextMenu={handleContextMenu}
      >
        {/* Tool calls */}
        {message.toolCalls?.map((tc) => (
          <ToolCallCard key={tc.id} toolCall={tc} />
        ))}

        {/* Thinking content - collapsible */}
        {message.thinkingContent && (
          <div className="mb-2">
            <button
              onClick={() => setThinkingExpanded(!thinkingExpanded)}
              className="flex items-center gap-1.5 text-xs text-text-muted hover:text-text-secondary transition-colors px-2 py-1 rounded-md hover:bg-[var(--bg-secondary)]"
            >
              <Brain size={12} />
              <span>思考过程</span>
              {thinkingExpanded ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
            </button>
            {thinkingExpanded && (
              <div className="mt-1 ml-2 pl-3 border-l-2 border-[var(--hermes-accent)]/20 text-xs text-text-muted leading-relaxed max-h-64 overflow-y-auto">
                <pre className="whitespace-pre-wrap font-sans">{message.thinkingContent}</pre>
              </div>
            )}
          </div>
        )}

        {/* Message bubble */}
        {message.content && (
          <div
            className={`
              rounded-2xl px-4 py-3 text-sm leading-relaxed
              ${isUser
                ? 'bg-user-bubble text-text-primary rounded-tr-md'
                : 'text-text-primary rounded-tl-md'
              }
              ${message.error ? 'border border-error/30' : ''}
            `}
          >
            <div className="markdown-body">
              <ReactMarkdown
                remarkPlugins={[remarkGfm]}
                rehypePlugins={[rehypeSanitize]}
                components={{
                  code({ node, className, children, ...props }) {
                    const match = /language-(\w+)/.exec(className || '');
                    const codeString = String(children).replace(/\n$/, '');

                    // Block code (multi-line or has language)
                    if (match || codeString.includes('\n')) {
                      return (
                        <CodeBlock
                          code={codeString}
                          language={match?.[1]}
                        />
                      );
                    }

                    // Inline code
                    return (
                      <code className={className} {...props}>
                        {children}
                      </code>
                    );
                  },
                }}
              >
                {message.content}
              </ReactMarkdown>
            </div>

            {/* Streaming indicator */}
            {message.isStreaming && (
              <span className="inline-block w-2 h-4 bg-[var(--hermes-accent)] ml-0.5 animate-pulse" />
            )}
          </div>
        )}

        {/* Thinking indicator — show when streaming but no content yet */}
        {message.isStreaming && !message.content && !message.thinkingContent && (!message.toolCalls || message.toolCalls.length === 0) && (
          <div className="flex items-center gap-2 px-4 py-2 text-xs text-text-muted">
            <Loader2 size={12} className="animate-spin" />
            <span>AI 正在思考...</span>
          </div>
        )}

        {/* Streaming thinking indicator */}
        {message.isStreaming && message.thinkingContent && !message.content && (
          <div className="flex items-center gap-2 px-2 py-1 text-xs text-[var(--hermes-accent)]">
            <Brain size={12} className="animate-pulse" />
            <span>正在思考...</span>
          </div>
        )}

        {/* Error */}
        {message.error && (
          <div className="flex items-center gap-1.5 mt-1 text-xs text-error">
            <AlertCircle size={12} />
            <span>{message.error}</span>
          </div>
        )}

        {/* Timestamp */}
        <div className={`text-xs text-text-muted mt-1 ${isUser ? 'text-right' : ''}`}>
          {new Date(message.timestamp).toLocaleTimeString('zh-CN', {
            hour: '2-digit',
            minute: '2-digit',
          })}
        </div>
      </div>

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
});

export default MessageBubble;
