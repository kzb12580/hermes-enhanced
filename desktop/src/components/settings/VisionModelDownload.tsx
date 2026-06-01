import React, { useState, useEffect } from 'react';
import { Download, Loader2, CheckCircle, AlertCircle, RefreshCw, Trash2, HardDrive, Wrench, CheckCheck, XCircle } from 'lucide-react';
import { getBackendUrl } from '../../lib/utils';

const MIRRORS = [
  { key: 'hf-mirror', label: 'hf-mirror（国内推荐）', note: '' },
  { key: 'modelscope', label: 'ModelScope（阿里）', note: '' },
  { key: 'official', label: 'HuggingFace 官方', note: '需 TUN' },
];

interface RepairResult {
  name: string;
  status: string;
  detail: string;
  fixable?: boolean;
}

export function VisionModelDownload() {
  const [mirror, setMirror] = useState('hf-mirror');
  const [downloading, setDownloading] = useState(false);
  const [progress, setProgress] = useState(0);
  const [status, setStatus] = useState('');
  const [done, setDone] = useState(false);
  const [error, setError] = useState('');
  const [modelExists, setModelExists] = useState<boolean | null>(null);
  const [checking, setChecking] = useState(true);
  const [gpuAvailable, setGpuAvailable] = useState<boolean | null>(null);
  const [gpuInfo, setGpuInfo] = useState<any>(null);

  // 检测修复状态
  const [repairing, setRepairing] = useState(false);
  const [repairResults, setRepairResults] = useState<RepairResult[]>([]);
  const [repairSummary, setRepairSummary] = useState('');
  const [repairDone, setRepairDone] = useState(false);

  useEffect(() => {
    checkGpuAndModel();
  }, []);

  const checkGpuAndModel = async () => {
    setChecking(true);
    try {
      // 先检测 GPU
      const gpuRes = await fetch(`${getBackendUrl()}/api/setup/gpu-status`);
      if (gpuRes.ok) {
        const gpuData = await gpuRes.json();
        setGpuAvailable(gpuData.show_vision_model);
        setGpuInfo(gpuData);
        
        // 如果有 GPU，再检查模型
        if (gpuData.show_vision_model) {
          await checkModel();
        }
      } else {
        setGpuAvailable(false);
      }
    } catch {
      setGpuAvailable(false);
    }
    setChecking(false);
  };

  const checkModel = async () => {
    try {
      const res = await fetch(`${getBackendUrl()}/api/setup/model-status`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      setModelExists(data.exists);
      if (data.exists) setDone(true);
    } catch {
      setModelExists(false);
    }
  };

  const startDownload = async () => {
    setDownloading(true);
    setProgress(0);
    setStatus('正在准备下载...');
    setError('');

    try {
      const res = await fetch(`${getBackendUrl()}/api/setup/download-model`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ mirror }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      if (data.success) {
        const es = new EventSource(`${getBackendUrl()}/api/setup/status/stream`);
        es.onmessage = (ev) => {
          try {
            const d = JSON.parse(ev.data);
            if (d.progress) setProgress(d.progress);
            if (d.message) setStatus(d.message);
            if (d.phase === 'done') {
              setDone(true);
              setDownloading(false);
              setModelExists(true);
              es.close();
            }
            if (d.phase === 'error') {
              setDownloading(false);
              setError(d.error || d.message || '下载失败');
              es.close();
            }
          } catch {}
        };
        es.onerror = () => {
          es.close();
          setDownloading(false);
          setError('连接中断');
        };
      } else {
        setDownloading(false);
        setError(data.error || data.detail || '启动下载失败');
      }
    } catch {
      setDownloading(false);
      setError('请求失败');
    }
  };

  const deleteModel = async () => {
    if (!confirm('确定删除视觉模型？(~6GB)')) return;
    try {
      const res = await fetch(`${getBackendUrl()}/api/setup/delete-model`, { method: 'DELETE' });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      setModelExists(false);
      setDone(false);
      setProgress(0);
      setStatus('');
      setRepairDone(false);
      setRepairResults([]);
    } catch {
      setError('删除失败');
    }
  };

  const startRepair = async () => {
    setRepairing(true);
    setRepairResults([]);
    setRepairSummary('');
    setRepairDone(false);

    try {
      const res = await fetch(`${getBackendUrl()}/api/setup/repair`, { method: 'POST' });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      setRepairResults(data.results || []);
      setRepairSummary(data.summary || '');
      setRepairDone(true);

      // 如果自动修复了某些依赖，重新检查模型
      if (data.auto_fixed && data.auto_fixed.length > 0) {
        await checkModel();
      }
    } catch {
      setRepairSummary('检测请求失败');
    }
    setRepairing(false);
  };

  if (checking) {
    return (
      <div className="flex items-center gap-2 text-text-muted text-sm py-4">
        <Loader2 size={14} className="animate-spin" />
        检测 GPU 和模型状态...
      </div>
    );
  }

  // 没有 NVIDIA GPU 或 CUDA，不显示视觉模型功能
  if (gpuAvailable === false) {
    return (
      <div className="space-y-4">
        <div className="flex items-center gap-2 mb-2">
          <HardDrive size={16} className="text-[var(--hermes-accent)]" />
          <h3 className="text-sm font-medium text-text-primary">视觉模型（可选）</h3>
        </div>
        <div className="p-3 rounded-lg bg-[var(--bg-tertiary)] border border-[var(--hermes-border)]">
          <p className="text-xs text-text-muted">
            视觉模型需要 NVIDIA GPU（≥6GB 显存）和 CUDA 支持。
          </p>
          {gpuInfo && (
            <div className="mt-2 text-xs text-text-muted">
              <p>GPU: {gpuInfo.has_nvidia_gpu ? gpuInfo.gpu_name : '未检测到'}</p>
              <p>CUDA: {gpuInfo.has_cuda ? gpuInfo.cuda_version : '未安装'}</p>
              <p>显存: {gpuInfo.vram_gb > 0 ? `${gpuInfo.vram_gb}GB` : 'N/A'}</p>
            </div>
          )}
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2 mb-2">
        <HardDrive size={16} className="text-[var(--hermes-accent)]" />
        <h3 className="text-sm font-medium text-text-primary">视觉模型（可选）</h3>
      </div>

      <p className="text-xs text-text-muted">
        LocateAnything-3B (~6GB) 用于屏幕元素识别和 GUI 自动化。
        如果只需要聊天和办公功能，可以不下载。
      </p>
      {gpuInfo && (
        <div className="text-xs text-success">
          ✓ {gpuInfo.gpu_name} ({gpuInfo.vram_gb}GB) | CUDA {gpuInfo.cuda_version}
        </div>
      )}

      {/* Model status */}
      {modelExists ? (
        <div className="flex items-center justify-between p-3 rounded-lg bg-success/10 border border-success/20">
          <div className="flex items-center gap-2">
            <CheckCircle size={16} className="text-success" />
            <span className="text-sm text-success">模型已安装</span>
          </div>
          <div className="flex gap-2">
            <button
              onClick={startRepair}
              disabled={repairing}
              className="flex items-center gap-1 px-2 py-1 rounded text-xs text-[var(--hermes-accent)] hover:bg-[var(--hermes-accent)]/10 transition-colors disabled:opacity-50"
            >
              {repairing ? <Loader2 size={12} className="animate-spin" /> : <Wrench size={12} />}
              检测修复
            </button>
            <button
              onClick={deleteModel}
              className="flex items-center gap-1 px-2 py-1 rounded text-xs text-error hover:bg-error/10 transition-colors"
            >
              <Trash2 size={12} /> 删除
            </button>
          </div>
        </div>
      ) : (
        <>
          {/* Mirror selection */}
          <div>
            <label className="text-xs font-medium text-text-muted mb-1.5 block">下载源</label>
            <div className="flex gap-2 flex-wrap">
              {MIRRORS.map(m => (
                <button
                  key={m.key}
                  onClick={() => setMirror(m.key)}
                  disabled={downloading}
                  className={`px-3 py-1.5 rounded-full text-xs transition-colors ${
                    mirror === m.key
                      ? 'bg-[var(--hermes-accent)] text-white'
                      : 'bg-[var(--bg-tertiary)] text-text-muted hover:text-text-primary'
                  } ${downloading ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer'}`}
                >
                  {m.label} {m.note && <span className="text-warning">({m.note})</span>}
                </button>
              ))}
            </div>
          </div>

          {/* Progress */}
          {downloading && (
            <div>
              <div className="h-2 rounded-full bg-[var(--bg-tertiary)] overflow-hidden">
                <div
                  className="h-full rounded-full bg-gradient-to-r from-accent to-purple-500 transition-all duration-300"
                  style={{ width: `${progress}%` }}
                />
              </div>
              <div className="flex justify-between mt-1">
                <span className="text-xs text-text-muted">{status || '准备中...'}</span>
                <span className="text-xs text-text-muted">{progress}%</span>
              </div>
            </div>
          )}

          {/* Error */}
          {error && (
            <div className="flex items-center gap-2 p-3 rounded-lg bg-error/10 text-error text-xs">
              <AlertCircle size={14} />
              {error}
            </div>
          )}

          {/* Buttons */}
          <div className="flex gap-2">
            <button
              onClick={startDownload}
              disabled={downloading}
              className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm bg-[var(--hermes-accent)] text-white hover:opacity-90 disabled:opacity-50 disabled:cursor-not-allowed transition-opacity"
            >
              {downloading ? (
                <><Loader2 size={14} className="animate-spin" /> 下载中...</>
              ) : error ? (
                <><RefreshCw size={14} /> 重试下载</>
              ) : (
                <><Download size={14} /> 开始下载</>
              )}
            </button>
            <button
              onClick={startRepair}
              disabled={repairing}
              className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm bg-[var(--bg-tertiary)] text-text-primary hover:bg-[var(--bg-secondary)] disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              {repairing ? (
                <><Loader2 size={14} className="animate-spin" /> 检测中...</>
              ) : (
                <><Wrench size={14} /> 检测修复</>
              )}
            </button>
          </div>
        </>
      )}

      {/* Repair Results */}
      {repairDone && (
        <div className="space-y-2 p-3 rounded-lg bg-[var(--bg-tertiary)] border border-[var(--hermes-border)]">
          <div className="flex items-center gap-2 mb-2">
            <CheckCheck size={14} className="text-[var(--hermes-accent)]" />
            <span className="text-xs font-medium text-text-primary">检测结果</span>
          </div>
          {repairResults.map((r, i) => (
            <div key={i} className="flex items-center gap-2 text-xs">
              {r.status === 'ok' ? (
                <CheckCircle size={12} className="text-success flex-shrink-0" />
              ) : r.status === 'fixed' ? (
                <RefreshCw size={12} className="text-warning flex-shrink-0" />
              ) : (
                <XCircle size={12} className="text-error flex-shrink-0" />
              )}
              <span className="font-medium text-text-primary min-w-[100px]">{r.name}</span>
              <span className={`${
                r.status === 'ok' ? 'text-success' :
                r.status === 'fixed' ? 'text-warning' :
                'text-error'
              }`}>
                {r.detail}
              </span>
            </div>
          ))}
          {repairSummary && (
            <div className="text-xs text-text-muted mt-2 pt-2 border-t border-[var(--hermes-border)]">
              {repairSummary}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
