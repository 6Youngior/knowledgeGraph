import { Component, StrictMode, type ErrorInfo, type ReactNode } from 'react';
import ReactDOM from 'react-dom/client';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { App } from './App';
import { ToastProvider } from './components/Toast';
import './styles.css';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 15000,
      retry: 1,
      refetchOnWindowFocus: false,
    },
  },
});

class ErrorBoundary extends Component<
  { children: ReactNode },
  { error: Error | null }
> {
  state = { error: null as Error | null };

  static getDerivedStateFromError(error: Error) {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('FinGraph render error', error, info);
  }

  render() {
    if (this.state.error) {
      return (
        <div
          style={{
            minHeight: '100vh',
            display: 'grid',
            placeItems: 'center',
            background: '#060a12',
            color: '#dbe7f6',
            fontFamily:
              '-apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif',
            padding: 32,
          }}
        >
          <div style={{ maxWidth: 520 }}>
            <div
              style={{
                color: '#5eead4',
                fontSize: 11,
                letterSpacing: '.16em',
                marginBottom: 10,
              }}
            >
              FINGRAPH · RENDER ERROR
            </div>
            <h1 style={{ fontSize: 22, margin: '0 0 10px' }}>界面渲染遇到问题</h1>
            <p style={{ color: '#94a3b8', lineHeight: 1.7, fontSize: 13 }}>
              请刷新页面重试。如果问题持续，检查后端 API 是否已启动，并查看浏览器控制台。
            </p>
            <button
              type="button"
              onClick={() => window.location.reload()}
              style={{
                marginTop: 12,
                padding: '9px 16px',
                borderRadius: 9,
                border: '1px solid rgba(94,234,212,.4)',
                background: 'rgba(94,234,212,.12)',
                color: '#5eead4',
                cursor: 'pointer',
              }}
            >
              刷新页面
            </button>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}

ReactDOM.createRoot(document.getElementById('root') as HTMLElement).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <ErrorBoundary>
        <ToastProvider>
          <App />
        </ToastProvider>
      </ErrorBoundary>
    </QueryClientProvider>
  </StrictMode>,
);
