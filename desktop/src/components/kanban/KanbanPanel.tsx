import React from 'react';
import { Kanban } from 'lucide-react';

export function KanbanPanel() {
  return (
    <div className="flex flex-col h-full bg-[var(--bg-primary)]">
      <div className="flex items-center gap-3 px-6 py-4 border-b border-[var(--hermes-border)]">
        <Kanban size={20} className="text-[var(--hermes-accent)]" />
        <h1 className="text-lg font-semibold text-text-primary">看板管理</h1>
      </div>
      <div className="flex-1 flex items-center justify-center">
        <div className="text-center text-text-muted">
          <Kanban size={48} className="mx-auto mb-4 opacity-50" />
          <p className="text-sm">看板功能开发中...</p>
          <p className="text-xs mt-2">支持任务管理、看板视图、任务分配</p>
        </div>
      </div>
    </div>
  );
}

export default KanbanPanel;
