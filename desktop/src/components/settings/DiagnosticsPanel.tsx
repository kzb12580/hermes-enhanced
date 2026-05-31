import React, { useState, useEffect } from 'react';
import { Loader2, CheckCircle, XCircle, AlertCircle, RefreshCw, Wrench, HardDrive, Zap, Cpu, Settings } from 'lucide-react';
import { getBackendUrl } from '../../lib/utils';

interface DiagResult {
  backend?: { uptime_seconds: number; host: string; port: number; python: string };
  tools?: { name: string; timeout: number }[];
  tools_count?: number;
  gpu?: { available: boolean; name?: string; vram_gb?: number; cuda_version?: string; torch_version?: string };
  vision_model?: { found: boolean; path?: string; env_var?: string };
  skills_count?: number;
}

export function DiagnosticsPanel() {
  const [diag, setDiag] = useState<DiagResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [reloading, setReloading] = useState(false);
  const [message, setMessage] = useState('');

  const runDiag = async () => {
    setLoading(true);
    setMessage('');
    try {
      const res = await fetch(`${getBackendUrl()}/api/diagnose`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      setDiag(await res.json());
    } catch (e) {
      setMessage('诊断请求失败: ' + e);
    }
    setLoading(false);
  };

  const reloadTools = async () => {
    setReloading(true);
    setMessage('');
    try {
      const res = await fetch(`${getBackendUrl()}/api/tools/reload`, { method: 'POST' });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      if (data.success) {
        setMessage(`✅ 工具热重载成功: ${data.tools_count} 个工具`);
        await runDiag();
      } else {
        setMessage(`❌ 重载失败: ${data.error}`);
      }
    } catch (e) {
      setMessage('重载请求失败: ' + e);
    }
    setReloading(false);
  };

  useEffect(() => { runDiag(); }, []);

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Settings size={16} className="text-accent" />
          <h3 className="text-sm font-medium text-text-primary">后端诊断</h3>
        </div>
        <div className="flex gap-2">
          <button onClick={runDiag} disabled={loading}
            className="flex items-center gap-1 px-3 py-1.5 rounded-lg text-xs bg-bg-tertiary text-text-primary hover:bg-bg-secondary disabled:opacity-50 transition-colors">
            {loading ? <Loader2 size={12} className="animate-spin" /> : <RefreshCw size={12} />}
            刷新
          </button>
          <button onClick={reloadTools} disabled={reloading}
            className="flex items-center gap-1 px-3 py-1.5 rounded-lg text-xs bg-accent text-white hover:opacity-90 disabled:opacity-50 transition-opacity">
            {reloading ? <Loader2 size={12} className="animate-spin" /> : <Wrench size={12} />}
            热重载工具
          </button>
        </div>
      </div>

      {message && (
        <div className={`p-3 rounded-lg text-xs ${message.startsWith('✅') ? 'bg-success/10 text-success' : 'bg-error/10 text-error'}`}>
          {message}
        </div>
      )}

      {diag && (
        <div className="space-y-3">
          {/* Backend */}
          <div className="p-3 rounded-lg bg-bg-tertiary border border-border">
            <div className="flex items-center gap-2 mb-2">
              <CheckCircle size={14} className="text-success" />
              <span className="text-xs font-medium text-text-primary">后端服务</span>
            </div>
            <div className="grid grid-cols-2 gap-2 text-xs text-text-muted">
              <div>运行时间: {Math.round(diag.backend.uptime_seconds / 60)} 分钟</div>
              <div>端口: {diag.backend.port}</div>
              <div>Python: {diag.backend.python.split(' ')[0]}</div>
              <div>技能: {diag.skills_count} 个</div>
            </div>
          </div>

          {/* GPU */}
          <div className="p-3 rounded-lg bg-bg-tertiary border border-border">
            <div className="flex items-center gap-2 mb-2">
              {diag.gpu.available ? (
                <CheckCircle size={14} className="text-success" />
              ) : (
                <XCircle size={14} className="text-error" />
              )}
              <span className="text-xs font-medium text-text-primary">GPU</span>
            </div>
            {diag.gpu.available ? (
              <div className="grid grid-cols-2 gap-2 text-xs text-text-muted">
                <div>显卡: {diag.gpu.name}</div>
                <div>显存: {diag.gpu.vram_gb} GB</div>
                <div>CUDA: {diag.gpu.cuda_version}</div>
                <div>PyTorch: {diag.gpu.torch_version}</div>
              </div>
            ) : (
              <div className="text-xs text-error">
                {diag.gpu.error || '未检测到 GPU'}
              </div>
            )}
          </div>

          {/* Vision Model */}
          <div className="p-3 rounded-lg bg-bg-tertiary border border-border">
            <div className="flex items-center gap-2 mb-2">
              {diag.vision_model.found ? (
                <CheckCircle size={14} className="text-success" />
              ) : (
                <AlertCircle size={14} className="text-warning" />
              )}
              <span className="text-xs font-medium text-text-primary">视觉模型</span>
            </div>
            {diag.vision_model.found ? (
              <div className="text-xs text-text-muted break-all">
                路径: {diag.vision_model.path}
              </div>
            ) : (
              <div className="text-xs text-warning">
                未找到模型。请在设置页面下载，或设置环境变量 HERMES_VISION_MODEL_PATH
              </div>
            )}
          </div>

          {/* Tools */}
          <div className="p-3 rounded-lg bg-bg-tertiary border border-border">
            <div className="flex items-center gap-2 mb-2">
              <Zap size={14} className="text-accent" />
              <span className="text-xs font-medium text-text-primary">
                工具 ({diag.tools_count} 个)
              </span>
            </div>
            <div className="flex flex-wrap gap-1">
              {diag.tools.map(t => (
                <span key={t.name} className="px-2 py-0.5 text-xs bg-bg-primary text-text-secondary rounded">
                  {t.name}
                </span>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
