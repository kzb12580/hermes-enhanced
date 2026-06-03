import React, { useState, useEffect, useCallback } from 'react';
import { Mail, RefreshCw, Send, Settings, Inbox, Check } from 'lucide-react';
import { useSettingsStore } from '../../stores/settingsStore';

interface EmailConfig {
  smtp_host: string;
  smtp_port: number;
  imap_host: string;
  imap_port: number;
  username: string;
  password: string;
  from_name: string;
}

interface EmailMessage {
  uid: number;
  subject: string;
  from: string;
  date: string;
  seen: boolean;
}

export function EmailPanel() {
  const { backendUrl, apiKey } = useSettingsStore();
  const [tab, setTab] = useState<'inbox' | 'config'>('inbox');
  const [emails, setEmails] = useState<EmailMessage[]>([]);
  const [config, setConfig] = useState<Partial<EmailConfig>>({});
  const [loading, setLoading] = useState(false);
  const [testResult, setTestResult] = useState<string | null>(null);
  const [sendTo, setSendTo] = useState('');
  const [sendSubject, setSendSubject] = useState('');
  const [sendBody, setSendBody] = useState('');

  const headers = { 'Content-Type': 'application/json', ...(apiKey ? { 'Authorization': `Bearer ${apiKey}` } : {}) };

  const fetchConfig = useCallback(async () => {
    try {
      const res = await fetch(`${backendUrl}/api/email/config`, { headers });
      const data = await res.json();
      setConfig(data);
    } catch (e) {
      console.error('Failed to fetch email config:', e);
    }
  }, [backendUrl, apiKey]);

  const fetchInbox = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch(`${backendUrl}/api/email/inbox`, { headers });
      const data = await res.json();
      setEmails(Array.isArray(data) ? data : data.emails || []);
    } catch (e) {
      console.error('Failed to fetch inbox:', e);
    } finally {
      setLoading(false);
    }
  }, [backendUrl, apiKey]);

  useEffect(() => { fetchConfig(); fetchInbox(); }, [fetchConfig, fetchInbox]);

  const saveConfig = async () => {
    try {
      await fetch(`${backendUrl}/api/email/config`, {
        method: 'PUT',
        headers,
        body: JSON.stringify(config),
      });
      setTestResult(null);
    } catch (e) {
      console.error('Failed to save config:', e);
    }
  };

  const testConnection = async () => {
    try {
      const res = await fetch(`${backendUrl}/api/email/test`, {
        method: 'POST',
        headers,
        body: JSON.stringify(config),
      });
      const data = await res.json();
      setTestResult(data.success ? '连接成功!' : `失败: ${data.error}`);
    } catch (e) {
      setTestResult('连接失败');
    }
  };

  const sendEmail = async () => {
    try {
      await fetch(`${backendUrl}/api/email/send`, {
        method: 'POST',
        headers,
        body: JSON.stringify({ to: sendTo, subject: sendSubject, body: sendBody }),
      });
      setSendTo(''); setSendSubject(''); setSendBody('');
      alert('发送成功');
    } catch (e) {
      alert('发送失败');
    }
  };

  return (
    <div className="flex flex-col h-full bg-[var(--bg-primary)]">
      <div className="flex items-center gap-3 px-6 py-4 border-b border-[var(--hermes-border)]">
        <Mail size={20} className="text-[var(--hermes-accent)]" />
        <h1 className="text-lg font-semibold text-text-primary">邮件</h1>
        <div className="flex gap-1 ml-4">
          <button onClick={() => setTab('inbox')} className={`px-3 py-1 text-sm rounded-lg ${tab === 'inbox' ? 'bg-[var(--hermes-accent)] text-white' : 'text-text-muted hover:bg-[var(--bg-surface)]'}`}>收件箱</button>
          <button onClick={() => setTab('config')} className={`px-3 py-1 text-sm rounded-lg ${tab === 'config' ? 'bg-[var(--hermes-accent)] text-white' : 'text-text-muted hover:bg-[var(--bg-surface)]'}`}>配置</button>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto px-6 py-4">
        {tab === 'inbox' ? (
          <div className="space-y-3">
            {/* 发送邮件 */}
            <div className="p-4 bg-[var(--bg-secondary)] border border-[var(--hermes-border)] rounded-lg space-y-2">
              <input type="text" placeholder="收件人" value={sendTo} onChange={e => setSendTo(e.target.value)} className="w-full px-3 py-2 text-sm bg-[var(--bg-primary)] border border-[var(--hermes-border)] rounded-lg" />
              <input type="text" placeholder="主题" value={sendSubject} onChange={e => setSendSubject(e.target.value)} className="w-full px-3 py-2 text-sm bg-[var(--bg-primary)] border border-[var(--hermes-border)] rounded-lg" />
              <textarea placeholder="内容" value={sendBody} onChange={e => setSendBody(e.target.value)} rows={3} className="w-full px-3 py-2 text-sm bg-[var(--bg-primary)] border border-[var(--hermes-border)] rounded-lg" />
              <button onClick={sendEmail} className="flex items-center gap-1 px-3 py-2 text-sm bg-[var(--hermes-accent)] text-white rounded-lg"><Send size={14} /> 发送</button>
            </div>
            {/* 邮件列表 */}
            {emails.map(email => (
              <div key={email.uid} className={`p-3 bg-[var(--bg-secondary)] border rounded-lg ${email.seen ? 'border-[var(--hermes-border)]' : 'border-[var(--hermes-accent)]'}`}>
                <div className="flex items-center justify-between">
                  <h3 className="text-sm font-medium text-text-primary">{email.subject}</h3>
                  <span className="text-xs text-text-muted">{new Date(email.date).toLocaleString('zh-CN')}</span>
                </div>
                <p className="text-xs text-text-muted mt-1">{email.from}</p>
              </div>
            ))}
          </div>
        ) : (
          <div className="space-y-4">
            <div className="p-4 bg-[var(--bg-secondary)] border border-[var(--hermes-border)] rounded-lg space-y-3">
              <h3 className="text-sm font-medium text-text-primary">SMTP 配置</h3>
              <input type="text" placeholder="SMTP 主机" value={config.smtp_host || ''} onChange={e => setConfig({...config, smtp_host: e.target.value})} className="w-full px-3 py-2 text-sm bg-[var(--bg-primary)] border border-[var(--hermes-border)] rounded-lg" />
              <input type="number" placeholder="SMTP 端口" value={config.smtp_port || 587} onChange={e => setConfig({...config, smtp_port: Number(e.target.value)})} className="w-full px-3 py-2 text-sm bg-[var(--bg-primary)] border border-[var(--hermes-border)] rounded-lg" />
            </div>
            <div className="p-4 bg-[var(--bg-secondary)] border border-[var(--hermes-border)] rounded-lg space-y-3">
              <h3 className="text-sm font-medium text-text-primary">IMAP 配置</h3>
              <input type="text" placeholder="IMAP 主机" value={config.imap_host || ''} onChange={e => setConfig({...config, imap_host: e.target.value})} className="w-full px-3 py-2 text-sm bg-[var(--bg-primary)] border border-[var(--hermes-border)] rounded-lg" />
              <input type="number" placeholder="IMAP 端口" value={config.imap_port || 993} onChange={e => setConfig({...config, imap_port: Number(e.target.value)})} className="w-full px-3 py-2 text-sm bg-[var(--bg-primary)] border border-[var(--hermes-border)] rounded-lg" />
            </div>
            <div className="p-4 bg-[var(--bg-secondary)] border border-[var(--hermes-border)] rounded-lg space-y-3">
              <h3 className="text-sm font-medium text-text-primary">账号</h3>
              <input type="text" placeholder="用户名" value={config.username || ''} onChange={e => setConfig({...config, username: e.target.value})} className="w-full px-3 py-2 text-sm bg-[var(--bg-primary)] border border-[var(--hermes-border)] rounded-lg" />
              <input type="password" placeholder="密码" value={config.password || ''} onChange={e => setConfig({...config, password: e.target.value})} className="w-full px-3 py-2 text-sm bg-[var(--bg-primary)] border border-[var(--hermes-border)] rounded-lg" />
            </div>
            <div className="flex gap-2">
              <button onClick={saveConfig} className="flex items-center gap-1 px-3 py-2 text-sm bg-[var(--hermes-accent)] text-white rounded-lg"><Settings size={14} /> 保存</button>
              <button onClick={testConnection} className="flex items-center gap-1 px-3 py-2 text-sm border border-[var(--hermes-border)] rounded-lg hover:bg-[var(--bg-surface)]"><Check size={14} /> 测试连接</button>
            </div>
            {testResult && <p className="text-sm text-text-primary">{testResult}</p>}
          </div>
        )}
      </div>
    </div>
  );
}

export default EmailPanel;
