/**
 * Hermes Desktop - Renderer entry point
 */
import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App';
import './styles/globals.css';
import { useSettingsStore } from './stores/settingsStore';

// Initialize the API client from persisted settings before first render
useSettingsStore.getState().initApiClient();

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
