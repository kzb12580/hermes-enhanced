import React, { useState, useEffect } from 'react';
import {
  Mail, Send, Inbox, Settings, CheckCircle, AlertCircle,
  Loader2, Plus, Trash2, RefreshCw
} from 'lucide-react';

const BACKEND = 'http://127.0.0.1:9876';

interface EmailConfig {
  email: string;
  password: string;
  imap_server: string;
  imap_port: number;
  smtp_server: string;
  smtp_port: number;
  smtp_ssl: boolean;
}

interface Email {
  id: string;
  from: string;
  subject: string;
  date: string;
  body_preview: string;
  has_attachments: boolean;
}

// ── 邮箱预设 ──────────────────────────────────────────────────────────────
const PRESETS: Record<string, Partial<EmailConfig>> = {
  'qq.com': { imap_server: 'imap.qq.com', imap_port: 993, smtp_server: 'smtp.qq.com', smtp_port: 465, smtp_ssl: true },
  '163.com': { imap_server: 'imap.163.com', imap_port: 993, smtp_server: 'smtp.163.com', smtp_port: 465, smtp_ssl: true },
  'outlook.com': { imap_server: 'outlook.office365.com', imap_port: 993, smtp_server: 'smtp.office365.com', smtp_port: 587, smtp_ssl: false },
  'gmail.com': { imap_server: 'imap.gmail.com', imap_port: 993, smtp_server: 'smtp.gmail.com', smtp_port: 587, smtp_ssl: false },
};

export function EmailConfig() {
  const [config, setConfig] = useState<EmailConfig>({
    email: '', password: '', imap_server: '', imap_port: 993,
    smtp_server: '', smtp_port: 465, smtp_ssl: true,
  });
  const [emails, setEmails] = useState<Email[]>([]);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<{ ok: boolean; msg: string } | null>(null);
  const [view, setView] = useState<'config' | 'inbox'>('config');

  useEffect(() => {
    loadConfig();
  }, []);

  const loadConfig = async () => {
    try {
      const res = await fetch(`${BACKEND}/api/email/config`);
      const data = await res.json();
      if (data.email) setConfig(data);
    } catch (e) { /* ignore */ }
  };

  const saveConfig = async () => {
    setSaving(true);
    try {
      await fetch(`${BACKEND}/api/email/config`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(config),
      });
      setTestResult({ ok: true, msg: '配置已保存' });
    } catch (e) {
      setTestResult({ ok: false, msg: '保存失败' });
    }
    setSaving(false);
  };

  const testConnection = async () => {
    setTesting(true);
    setTestResult(null);
    try {
      const res = await fetch(`${BACKEND}/api/email/test`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(config),
      });
      const data = await res.json();
      setTestResult({ ok: data.success, msg: data.success ? '连接成功！' : data.error });
    } catch (e) {
      setTestResult({ ok: false, msg: '测试失败' });
    }
    setTesting(false);
  };

  const loadEmails = async () => {
    setLoading(true);
    try {
      const res = await fetch(`${BACKEND}/api/email/inbox?limit=20`);
      const data = await res.json();
      setEmails(data.emails || []);
    } catch (e) { /* ignore */ }
    setLoading(false);
  };

  const autoDetect = () => {
    const domain = config.email.split('@')[1];
    if (domain && PRESETS[domain]) {
      setConfig(prev => ({ ...prev, ...PRESETS[domain] }));
    }
  };

  return (
    <div style={{ maxWidth: 640 }}>
      <div style={{ display: 'flex', gap: 8, marginBottom: 20 }}>
        <button onClick={() => setView('config')} style={{
          ...chipStyle,
          background: view === 'config' ? '#3b82f6' : '#1f2937',
          color: view === 'config' ? '#fff' : '#9ca3af',
        }}>
          <Settings size={14} /> 邮箱配置
        </button>
        <button onClick={() => { setView('inbox'); loadEmails(); }} style={{
          ...chipStyle,
          background: view === 'inbox' ? '#3b82f6' : '#1f2937',
          color: view === 'inbox' ? '#fff' : '#9ca3af',
        }}>
          <Inbox size={14} /> 收件箱
        </button>
      </div>

      {view === 'config' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          <div>
            <label style={labelStyle}>邮箱地址</label>
            <input value={config.email}
              onChange={e => setConfig(c => ({ ...c, email: e.target.value }))}
              onBlur={autoDetect}
              placeholder="your@email.com" style={inputStyle} />
          </div>
          <div>
            <label style={labelStyle}>密码 / 授权码</label>
            <input value={config.password} type="password"
              onChange={e => setConfig(c => ({ ...c, password: e.target.value }))}
              placeholder="QQ邮箱需要授权码，不是QQ密码" style={inputStyle} />
            <p style={{ fontSize: 12, color: '#6b7280', marginTop: 4 }}>
              💡 QQ邮箱: 设置 → 账户 → POP3/IMAP → 生成授权码
            </p>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
            <div>
              <label style={labelStyle}>IMAP 服务器</label>
              <input value={config.imap_server}
                onChange={e => setConfig(c => ({ ...c, imap_server: e.target.value }))}
                placeholder="自动检测" style={inputStyle} />
            </div>
            <div>
              <label style={labelStyle}>IMAP 端口</label>
              <input value={config.imap_port} type="number"
                onChange={e => setConfig(c => ({ ...c, imap_port: Number(e.target.value) }))}
                style={inputStyle} />
            </div>
            <div>
              <label style={labelStyle}>SMTP 服务器</label>
              <input value={config.smtp_server}
                onChange={e => setConfig(c => ({ ...c, smtp_server: e.target.value }))}
                placeholder="自动检测" style={inputStyle} />
            </div>
            <div>
              <label style={labelStyle}>SMTP 端口</label>
              <input value={config.smtp_port} type="number"
                onChange={e => setConfig(c => ({ ...c, smtp_port: Number(e.target.value) }))}
                style={inputStyle} />
            </div>
          </div>

          <div style={{ display: 'flex', gap: 8, marginTop: 8 }}>
            <button onClick={saveConfig} disabled={saving} style={btnStyle}>
              {saving ? <Loader2 size={14} className="spin" /> : <CheckCircle size={14} />}
              保存配置
            </button>
            <button onClick={testConnection} disabled={testing} style={btnSecondaryStyle}>
              {testing ? <Loader2 size={14} className="spin" /> : <RefreshCw size={14} />}
              测试连接
            </button>
          </div>

          {testResult && (
            <div style={{
              padding: 10, borderRadius: 8, fontSize: 14,
              background: testResult.ok ? 'rgba(34,197,94,0.1)' : 'rgba(239,68,68,0.1)',
              color: testResult.ok ? '#22c55e' : '#ef4444',
              display: 'flex', alignItems: 'center', gap: 6,
            }}>
              {testResult.ok ? <CheckCircle size={14} /> : <AlertCircle size={14} />}
              {testResult.msg}
            </div>
          )}
        </div>
      )}

      {view === 'inbox' && (
        <div>
          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 12 }}>
            <span style={{ color: '#9ca3af', fontSize: 14 }}>
              {emails.length} 封邮件
            </span>
            <button onClick={loadEmails} disabled={loading} style={chipStyle}>
              {loading ? <Loader2 size={14} className="spin" /> : <RefreshCw size={14} />}
              刷新
            </button>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6, maxHeight: 400, overflow: 'auto' }}>
            {emails.map((mail, i) => (
              <div key={i} style={{
                padding: '10px 14px', borderRadius: 8,
                background: '#1f2937', cursor: 'pointer',
              }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
                  <span style={{ fontSize: 14, fontWeight: 500, color: '#e5e7eb' }}>
                    {mail.subject || '(无主题)'}
                  </span>
                  <span style={{ fontSize: 12, color: '#6b7280' }}>
                    {mail.date?.substring(0, 16)}
                  </span>
                </div>
                <div style={{ fontSize: 13, color: '#9ca3af' }}>
                  {mail.from}
                </div>
                <div style={{ fontSize: 12, color: '#6b7280', marginTop: 4, lineHeight: 1.4 }}>
                  {mail.body_preview?.substring(0, 150)}...
                </div>
              </div>
            ))}
            {emails.length === 0 && !loading && (
              <div style={{ textAlign: 'center', padding: 32, color: '#6b7280' }}>
                <Inbox size={32} style={{ marginBottom: 8 }} />
                <p>暂无邮件</p>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

const chipStyle: React.CSSProperties = {
  display: 'inline-flex', alignItems: 'center', gap: 4,
  padding: '8px 14px', borderRadius: 20, border: 'none',
  fontSize: 13, cursor: 'pointer',
};

const btnStyle: React.CSSProperties = {
  display: 'inline-flex', alignItems: 'center', gap: 6,
  padding: '10px 20px', borderRadius: 8, border: 'none',
  background: '#3b82f6', color: '#fff', fontSize: 14, cursor: 'pointer',
};

const btnSecondaryStyle: React.CSSProperties = {
  ...btnStyle, background: '#374151', color: '#d1d5db',
};

const labelStyle: React.CSSProperties = {
  display: 'block', fontSize: 14, fontWeight: 500, color: '#d1d5db', marginBottom: 4,
};

const inputStyle: React.CSSProperties = {
  width: '100%', padding: '10px 14px', borderRadius: 8,
  border: '1px solid #374151', background: '#1f2937', color: '#e5e7eb',
  fontSize: 14, outline: 'none',
};
