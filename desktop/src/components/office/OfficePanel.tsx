import React from 'react';
import { Building } from 'lucide-react';

export function OfficePanel() {
  return (
    <div className="flex flex-col h-full bg-[var(--bg-primary)]">
      <div className="flex items-center gap-3 px-6 py-4 border-b border-[var(--hermes-border)]">
        <Building size={20} className="text-[var(--hermes-accent)]" />
        <h1 className="text-lg font-semibold text-text-primary">办公</h1>
      </div>
      <div className="flex-1 flex items-center justify-center">
        <div className="text-center text-text-muted">
          <Building size={48} className="mx-auto mb-4 opacity-50" />
          <p className="text-sm">办公功能开发中...</p>
          <p className="text-xs mt-2">文档处理、表格、演示文稿</p>
        </div>
      </div>
    </div>
  );
}

export default OfficePanel;
