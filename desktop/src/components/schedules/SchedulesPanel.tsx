import React from 'react';
import { Timer } from 'lucide-react';

export function SchedulesPanel() {
  return (
    <div className="flex flex-col h-full bg-[var(--bg-primary)]">
      <div className="flex items-center gap-3 px-6 py-4 border-b border-[var(--hermes-border)]">
        <Timer size={20} className="text-[var(--hermes-accent)]" />
        <h1 className="text-lg font-semibold text-text-primary">定时任务</h1>
      </div>
      <div className="flex-1 flex items-center justify-center">
        <div className="text-center text-text-muted">
          <Timer size={48} className="mx-auto mb-4 opacity-50" />
          <p className="text-sm">定时任务功能开发中...</p>
          <p className="text-xs mt-2">后端暂未实现 cron API</p>
        </div>
      </div>
    </div>
  );
}

export default SchedulesPanel;
