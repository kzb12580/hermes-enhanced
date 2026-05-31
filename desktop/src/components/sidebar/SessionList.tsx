import React, { useState, useRef, useEffect } from 'react';
import { useChatStore } from '../../stores/chatStore';
import {
  MessageSquare,
  Pencil,
  Trash2,
  Check,
  X,
} from 'lucide-react';

export function SessionList() {
  const { sessions, currentSessionId, switchSession, deleteSession, renameSession } = useChatStore();
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editTitle, setEditTitle] = useState('');
  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null);
  const deleteTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Cleanup delete confirmation timer on unmount
  useEffect(() => {
    return () => {
      if (deleteTimerRef.current) {
        clearTimeout(deleteTimerRef.current);
      }
    };
  }, []);

  const handleStartRename = (sessionId: string, currentTitle: string) => {
    setEditingId(sessionId);
    setEditTitle(currentTitle);
    setConfirmDeleteId(null);
  };

  const handleConfirmRename = () => {
    if (editingId && editTitle.trim()) {
      renameSession(editingId, editTitle.trim());
    }
    setEditingId(null);
    setEditTitle('');
  };

  const handleCancelRename = () => {
    setEditingId(null);
    setEditTitle('');
  };

  const handleDelete = (sessionId: string) => {
    if (confirmDeleteId === sessionId) {
      deleteSession(sessionId);
      setConfirmDeleteId(null);
      if (deleteTimerRef.current) {
        clearTimeout(deleteTimerRef.current);
        deleteTimerRef.current = null;
      }
    } else {
      // Cancel any previous timer
      if (deleteTimerRef.current) {
        clearTimeout(deleteTimerRef.current);
      }
      setConfirmDeleteId(sessionId);
      // Auto-cancel after 3 seconds with cleanup
      deleteTimerRef.current = setTimeout(() => {
        setConfirmDeleteId((prev) => (prev === sessionId ? null : prev));
        deleteTimerRef.current = null;
      }, 3000);
    }
  };

  const formatTime = (timestamp: number) => {
    const date = new Date(timestamp);
    const now = new Date();
    const diff = now.getTime() - date.getTime();

    if (diff < 60000) return '刚刚';
    if (diff < 3600000) return `${Math.floor(diff / 60000)} 分钟前`;
    if (diff < 86400000) return `${Math.floor(diff / 3600000)} 小时前`;
    if (diff < 604800000) return `${Math.floor(diff / 86400000)} 天前`;

    return date.toLocaleDateString('zh-CN', {
      month: 'short',
      day: 'numeric',
    });
  };

  if (sessions.length === 0) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center px-4 py-8 text-center">
        <MessageSquare size={28} className="text-text-muted mb-2" />
        <p className="text-sm text-text-muted">暂无对话</p>
        <p className="text-xs text-text-muted mt-1">点击上方按钮开始新对话</p>
      </div>
    );
  }

  return (
    <div className="flex-1 overflow-y-auto px-2 py-1 space-y-0.5">
      {sessions.map((session) => {
        const isActive = session.id === currentSessionId;
        const isEditing = editingId === session.id;
        const isConfirmingDelete = confirmDeleteId === session.id;

        return (
          <div
            key={session.id}
            className={`
              group relative rounded-lg px-3 py-2.5 cursor-pointer transition-colors
              ${isActive
                ? 'bg-bg-tertiary text-text-primary'
                : 'text-text-secondary hover:bg-bg-tertiary/50'
              }
            `}
            onClick={() => !isEditing && switchSession(session.id)}
          >
            {isEditing ? (
              /* Edit mode */
              <div className="flex items-center gap-1" onClick={(e) => e.stopPropagation()}>
                <input
                  type="text"
                  value={editTitle}
                  onChange={(e) => setEditTitle(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') handleConfirmRename();
                    if (e.key === 'Escape') handleCancelRename();
                  }}
                  className="flex-1 bg-bg-primary text-text-primary text-sm rounded px-2 py-1 outline-none border border-accent min-w-0"
                  autoFocus
                />
                <button
                  onClick={handleConfirmRename}
                  className="p-1 rounded hover:bg-success/20 text-success"
                >
                  <Check size={14} />
                </button>
                <button
                  onClick={handleCancelRename}
                  className="p-1 rounded hover:bg-error/20 text-error"
                >
                  <X size={14} />
                </button>
              </div>
            ) : (
              /* Display mode */
              <>
                <div className="text-sm font-medium truncate pr-14">
                  {session.title}
                </div>
                <div className="text-xs text-text-muted mt-0.5">
                  {formatTime(session.updatedAt)}
                  {session.messages.length > 0 && (
                    <span className="ml-2">· {session.messages.length} 条消息</span>
                  )}
                </div>

                {/* Actions (show on hover) */}
                <div className="absolute right-2 top-1/2 -translate-y-1/2 flex items-center gap-0.5 opacity-0 group-hover:opacity-100 transition-opacity">
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      handleStartRename(session.id, session.title);
                    }}
                    className="p-1 rounded hover:bg-bg-surface text-text-muted hover:text-text-primary"
                    title="重命名"
                  >
                    <Pencil size={13} />
                  </button>
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      handleDelete(session.id);
                    }}
                    className={`p-1 rounded transition-colors ${
                      isConfirmingDelete
                        ? 'bg-error/20 text-error'
                        : 'hover:bg-bg-surface text-text-muted hover:text-error'
                    }`}
                    title={isConfirmingDelete ? '再次点击确认删除' : '删除'}
                  >
                    <Trash2 size={13} />
                  </button>
                </div>
              </>
            )}
          </div>
        );
      })}
    </div>
  );
}

export default SessionList;
