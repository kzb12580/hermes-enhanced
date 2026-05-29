// Hermes Desktop — 视觉模型设置组件
// 文件: src/components/Settings/DesktopToolsSettings.tsx

import React, { useState, useEffect } from 'react';

interface DesktopToolsConfig {
  enabled: boolean;
  vision: {
    model: string;
    device: 'cuda' | 'cpu';
    mode: 'fast' | 'slow' | 'hybrid';
    preload: boolean;
    auto_unload: boolean;
  };
  gui: {
    failsafe: boolean;
    pause: number;
    coordinate_verify: boolean;
  };
  office: {
    max_content_mb: number;
    max_rows: number;
  };
}

const DEFAULT_CONFIG: DesktopToolsConfig = {
  enabled: false,
  vision: {
    model: 'nvidia/LocateAnything-3B',
    device: 'cuda',
    mode: 'hybrid',
    preload: false,
    auto_unload: true,
  },
  gui: {
    failsafe: true,
    pause: 0.05,
    coordinate_verify: true,
  },
  office: {
    max_content_mb: 10,
    max_rows: 100000,
  },
};

export function DesktopToolsSettings() {
  const [config, setConfig] = useState<DesktopToolsConfig>(DEFAULT_CONFIG);
  const [status, setStatus] = useState<'idle' | 'testing' | 'ok' | 'error'>('idle');
  const [gpuInfo, setGpuInfo] = useState<string>('');

  // 加载配置
  useEffect(() => {
    window.electron.invoke('config:get', 'desktop_tools').then((c: any) => {
      if (c) setConfig({ ...DEFAULT_CONFIG, ...c });
    });
    // 检测 GPU
    window.electron.invoke('desktop-tools:check-gpu').then((info: string) => {
      setGpuInfo(info);
    });
  }, []);

  const save = async () => {
    await window.electron.invoke('config:set', 'desktop_tools', config);
  };

  const testVision = async () => {
    setStatus('testing');
    try {
      const result = await window.electron.invoke('desktop-tools:test-vision');
      setStatus(result.success ? 'ok' : 'error');
    } catch {
      setStatus('error');
    }
  };

  const testDeps = async () => {
    const result = await window.electron.invoke('desktop-tools:check-deps');
    console.log('Dependencies:', result);
  };

  return (
    <div className="settings-section">
      <h2>🖥️ PC 自动化</h2>
      <p className="settings-desc">
        让 Hermes 像人一样操作你的电脑：截图、点击、输入、创建文档。
      </p>

      {/* 总开关 */}
      <div className="setting-row">
        <label>
          <input
            type="checkbox"
            checked={config.enabled}
            onChange={(e) => setConfig({ ...config, enabled: e.target.checked })}
          />
          <span>启用 PC 自动化工具</span>
        </label>
        <span className="setting-hint">包含 15 个工具：GUI操作 + Office文档 + OCR</span>
      </div>

      {config.enabled && (
        <>
          {/* 视觉模型 */}
          <h3>👁️ 视觉定位模型</h3>
          <div className="setting-row">
            <label>模型</label>
            <input
              type="text"
              value={config.vision.model}
              onChange={(e) => setConfig({
                ...config,
                vision: { ...config.vision, model: e.target.value }
              })}
              placeholder="nvidia/LocateAnything-3B"
            />
          </div>

          <div className="setting-row">
            <label>设备</label>
            <select
              value={config.vision.device}
              onChange={(e) => setConfig({
                ...config,
                vision: { ...config.vision, device: e.target.value as 'cuda' | 'cpu' }
              })}
            >
              <option value="cuda">CUDA (GPU) — 推荐 {gpuInfo && `(${gpuInfo})`}</option>
              <option value="cpu">CPU — 慢但无需GPU</option>
            </select>
          </div>

          <div className="setting-row">
            <label>推理模式</label>
            <select
              value={config.vision.mode}
              onChange={(e) => setConfig({
                ...config,
                vision: { ...config.vision, mode: e.target.value as any }
              })}
            >
              <option value="hybrid">混合模式 (推荐) — 平衡速度和准确</option>
              <option value="fast">快速模式 — 最高速度</option>
              <option value="slow">稳定模式 — 最高准确</option>
            </select>
          </div>

          <div className="setting-row">
            <label>
              <input
                type="checkbox"
                checked={config.vision.preload}
                onChange={(e) => setConfig({
                  ...config,
                  vision: { ...config.vision, preload: e.target.checked }
                })}
              />
              <span>启动时预加载模型</span>
            </label>
            <span className="setting-hint">占用约 6GB 显存，但首次使用无需等待</span>
          </div>

          <div className="setting-row">
            <label>
              <input
                type="checkbox"
                checked={config.vision.auto_unload}
                onChange={(e) => setConfig({
                  ...config,
                  vision: { ...config.vision, auto_unload: e.target.checked }
                })}
              />
              <span>空闲时自动释放显存</span>
            </label>
            <span className="setting-hint">30分钟无操作后自动卸载模型</span>
          </div>

          <div className="setting-actions">
            <button onClick={testVision} disabled={status === 'testing'}>
              {status === 'testing' ? '测试中...' : '🧪 测试视觉模型'}
            </button>
            <button onClick={testDeps}>📦 检查依赖</button>
            {status === 'ok' && <span className="status-ok">✅ 模型加载成功</span>}
            {status === 'error' && <span className="status-error">❌ 模型加载失败</span>}
          </div>

          {/* GUI 设置 */}
          <h3>🖱️ GUI 操作</h3>
          <div className="setting-row">
            <label>
              <input
                type="checkbox"
                checked={config.gui.failsafe}
                onChange={(e) => setConfig({
                  ...config,
                  gui: { ...config.gui, failsafe: e.target.checked }
                })}
              />
              <span>FAILSAFE 紧急停止</span>
            </label>
            <span className="setting-hint">鼠标移到左上角立即停止所有操作</span>
          </div>

          <div className="setting-row">
            <label>
              <input
                type="checkbox"
                checked={config.gui.coordinate_verify}
                onChange={(e) => setConfig({
                  ...config,
                  gui: { ...config.gui, coordinate_verify: e.target.checked }
                })}
              />
              <span>点击前验证坐标</span>
            </label>
            <span className="setting-hint">防止点击屏幕外区域</span>
          </div>
        </>
      )}

      <div className="setting-row setting-footer">
        <button className="btn-primary" onClick={save}>保存设置</button>
      </div>
    </div>
  );
}
