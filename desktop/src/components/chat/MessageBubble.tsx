import React from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import rehypeSanitize from 'rehype-sanitize';
import { CodeBlock } from './CodeBlock';
import { ToolCallCard } from './ToolCallCard';
import { DisplayMessage } from '../../stores/chatStore';
import { User, Bot, AlertCircle } from 'lucide-react';

interface MessageBubbleProps {
  message: DisplayMessage;
}

export function MessageBubble({ message }: MessageBubbleProps) {
  const isUser = message.role === 'user';
  const isSystem = message.role === 'system';
  const isTool = message.role === 'tool';

  if (isSystem) {
    return (
      <div className="flex justify-center my-2 fade-in">
        <div className="px-3 py-1.5 rounded-full bg-[var(--bg-tertiary)] text-[var(--text-muted)] text-xs">
          {message.content}
        </div>
      </div>
    );
  }

  if (isTool) {
    return (
      <div className="flex gap-3 px-4 py-2 my-1 fade-in">
        <div className="flex-shrink-0 w-7 h-7 rounded-full bg-[var(--bg-tertiary)] flex items-center justify-center mt-0.5">
          <span className="text-xs font-mono text-[var(--text-muted)]">T</span>
        </div>
        <div className="min-w-0 flex-1">
          <div className="text-xs text-[var(--text-muted)] mb-1">工具结果</div>
          <pre className="text-xs font-mono bg-[var(--bg-secondary)] rounded p-2 overflow-x-auto text-[var(--text-secondary)]">
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
          ${isUser ? 'bg-[var(--accent)] text-[var(--bg-primary)]' : 'bg-[var(--bg-tertiary)] text-[var(--text-secondary)]'}
        `}
      >
        {isUser ? <User size={16} /> : <Bot size={16} />}
      </div>

      {/* Content */}
      <div className={`min-w-0 flex-1 max-w-[80%] ${isUser ? 'flex flex-col items-end' : ''}`}>
        {/* Tool calls */}
        {message.toolCalls?.map((tc) => (
          <ToolCallCard key={tc.id} toolCall={tc} />
        ))}

        {/* Message bubble */}
        {message.content && (
          <div
            className={`
              rounded-2xl px-4 py-3 text-sm leading-relaxed
              ${isUser
                ? 'bg-[var(--user-bubble)] text-[var(--text-primary)] rounded-tr-md'
                : 'text-[var(--text-primary)] rounded-tl-md'
              }
              ${message.error ? 'border border-[var(--error)]/30' : ''}
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
              <span className="inline-block w-2 h-4 bg-[var(--accent)] ml-0.5 animate-pulse" />
            )}
          </div>
        )}

        {/* Error */}
        {message.error && (
          <div className="flex items-center gap-1.5 mt-1 text-xs text-[var(--error)]">
            <AlertCircle size={12} />
            <span>{message.error}</span>
          </div>
        )}

        {/* Timestamp */}
        <div className={`text-xs text-[var(--text-muted)] mt-1 ${isUser ? 'text-right' : ''}`}>
          {new Date(message.timestamp).toLocaleTimeString('zh-CN', {
            hour: '2-digit',
            minute: '2-digit',
          })}
        </div>
      </div>
    </div>
  );
}

export default MessageBubble;
