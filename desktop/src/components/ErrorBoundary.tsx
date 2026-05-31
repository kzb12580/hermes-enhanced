import React from 'react';

interface State {
  hasError: boolean;
  error: Error | null;
  errorInfo: React.ErrorInfo | null;
}

export class ErrorBoundary extends React.Component<{children: React.ReactNode}, State> {
  constructor(props: {children: React.ReactNode}) {
    super(props);
    this.state = { hasError: false, error: null, errorInfo: null };
  }

  static getDerivedStateFromError(error: Error) {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: React.ErrorInfo) {
    console.error('[ErrorBoundary] 渲染错误:', error, errorInfo);
    this.setState({ errorInfo });
  }

  render() {
    if (this.state.hasError) {
      return (
        <div style={{
          minHeight: '100vh', background: '#0f172a', color: '#e5e7eb',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", "Microsoft YaHei", sans-serif',
        }}>
          <div style={{ maxWidth: 600, padding: 32, textAlign: 'center' }}>
            <div style={{ fontSize: 48, marginBottom: 16 }}>⚠️</div>
            <h1 style={{ fontSize: 22, fontWeight: 700, marginBottom: 12, color: '#f87171' }}>
              渲染错误
            </h1>
            <p style={{ fontSize: 14, color: '#9ca3af', marginBottom: 16 }}>
              应用加载时遇到错误，请尝试重新加载或重启应用。
            </p>
            <pre style={{
              background: '#1e293b', padding: 16, borderRadius: 8, fontSize: 12,
              color: '#fca5a5', textAlign: 'left', overflow: 'auto', maxHeight: 300,
              border: '1px solid #334155', whiteSpace: 'pre-wrap', wordBreak: 'break-all',
            }}>
              {this.state.error?.toString()}
              {'\n\n'}
              {this.state.errorInfo?.componentStack}
            </pre>
            <div style={{ marginTop: 20, display: 'flex', gap: 8, justifyContent: 'center' }}>
              <button
                onClick={() => window.location.reload()}
                style={{
                  padding: '10px 20px', borderRadius: 8, border: 'none',
                  background: '#3b82f6', color: '#fff', fontSize: 14,
                  cursor: 'pointer', fontWeight: 500,
                }}
              >
                重新加载
              </button>
              <button
                onClick={() => {
                  localStorage.clear();
                  window.location.reload();
                }}
                style={{
                  padding: '10px 20px', borderRadius: 8, border: 'none',
                  background: '#374151', color: '#d1d5db', fontSize: 14,
                  cursor: 'pointer', fontWeight: 500,
                }}
              >
                清除数据并重置
              </button>
            </div>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}
