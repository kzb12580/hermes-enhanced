/**
 * Hermes Desktop - Renderer entry point
 */
import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App';
import './styles/globals.css';
import { useSettingsStore } from './stores/settingsStore';
import { ErrorBoundary } from './components/ErrorBoundary';

// Initialize the API client from persisted settings before first render
try {
  useSettingsStore.getState().initApiClient();
} catch (e) {
  console.error('[main] initApiClient failed:', e);
}

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <ErrorBoundary>
      <App />
    </ErrorBoundary>
  </React.StrictMode>,
);
