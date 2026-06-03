import React from 'react';
import { Compass } from 'lucide-react';

export function DiscoverPanel() {
  return (
    <div className="flex flex-col h-full bg-[var(--bg-primary)]">
      <div className="flex items-center gap-3 px-6 py-4 border-b border-[var(--hermes-border)]">
        <Compass size={20} className="text-[var(--hermes-accent)]" />
        <h1 className="text-lg font-semibold text-text-primary">发现</h1>
      </div>
      <div className="flex-1 flex items-center justify-center">
        <div className="text-center text-text-muted">
          <Compass size={48} className="mx-auto mb-4 opacity-50" />
          <p className="text-sm">发现功能开发中...</p>
          <p className="text-xs mt-2">技能市场、社区分享、模板库</p>
        </div>
      </div>
    </div>
  );
}

export default DiscoverPanel;
