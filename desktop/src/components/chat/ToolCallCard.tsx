import React, { useState } from 'react';
import { ChevronDown, ChevronRight, Wrench, CheckCircle, XCircle, Loader2 } from 'lucide-react';
import { ParsedToolCall } from '../../stores/chatStore';

interface ToolCallCardProps {
  toolCall: ParsedToolCall;
}

export function ToolCallCard({ toolCall }: ToolCallCardProps) {
  const [expanded, setExpanded] = useState(false);

  const statusIcon = {
    pending: <Loader2 size={14} className="animate-spin text-[var(--text-muted)]" />,
    running: <Loader2 size={14} className="animate-spin text-[var(--accent)]" />,
    completed: <CheckCircle size={14} className="text-[var(--success)]" />,
    error: <XCircle size={14} className="text-[var(--error)]" />,
  };

  const statusText = {
    pending: '等待中',
    running: '执行中',
    completed: '已完成',
    error: '出错',
  };

  let parsedArgs: string;
  try {
    parsedArgs = JSON.stringify(JSON.parse(toolCall.arguments), null, 2);
  } catch {
    parsedArgs = toolCall.arguments || '{}';
  }

  let parsedResult: string = '';
  try {
    if (toolCall.result) {
      parsedResult = JSON.stringify(JSON.parse(toolCall.result), null, 2);
    }
  } catch {
    parsedResult = toolCall.result || '';
  }

  return (
    <div className="my-2 rounded-lg border border-[var(--border)] bg-[var(--bg-secondary)] overflow-hidden fade-in">
      {/* Header */}
      <button
        onClick={() => setExpanded(!expanded)}
        className="flex items-center gap-2 w-full px-3 py-2 text-left hover:bg-[var(--bg-tertiary)] transition-colors"
      >
        {expanded ? (
          <ChevronDown size={14} className="text-[var(--text-muted)] flex-shrink-0" />
        ) : (
          <ChevronRight size={14} className="text-[var(--text-muted)] flex-shrink-0" />
        )}
        <Wrench size={14} className="text-[var(--accent)] flex-shrink-0" />
        <span className="text-sm font-medium text-[var(--text-primary)] truncate">
          {toolCall.name}
        </span>
        <span className="ml-auto flex items-center gap-1.5 text-xs text-[var(--text-muted)]">
          {statusIcon[toolCall.status]}
          <span>{statusText[toolCall.status]}</span>
        </span>
      </button>

      {/* Expanded content */}
      {expanded && (
        <div className="border-t border-[var(--border)] p-3 space-y-3">
          {/* Arguments */}
          <div>
            <h4 className="text-xs font-semibold text-[var(--text-muted)] uppercase tracking-wider mb-1">
              参数
            </h4>
            <pre className="text-xs font-mono bg-[var(--bg-primary)] rounded p-2 overflow-x-auto text-[var(--text-secondary)] max-h-48 overflow-y-auto">
              {parsedArgs}
            </pre>
          </div>

          {/* Result */}
          {toolCall.result && (
            <div>
              <h4 className="text-xs font-semibold text-[var(--text-muted)] uppercase tracking-wider mb-1">
                结果
              </h4>
              <pre className="text-xs font-mono bg-[var(--bg-primary)] rounded p-2 overflow-x-auto text-[var(--text-secondary)] max-h-64 overflow-y-auto">
                {parsedResult}
              </pre>
            </div>
          )}

          {toolCall.status === 'running' && !toolCall.result && (
            <div className="flex items-center gap-2 text-xs text-[var(--text-muted)]">
              <Loader2 size={12} className="animate-spin" />
              <span>正在执行工具...</span>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default ToolCallCard;
