import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { initConfig } from './config/app-config.ts';
import ThemeProvider from './theme/ThemeProvider.tsx';
import ErrorBoundary from './components/ErrorBoundary.tsx';
import App from './App.tsx';

// 在 React 渲染之前初始化全局配置
initConfig();

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ErrorBoundary>
      <ThemeProvider>
        <App />
      </ThemeProvider>
    </ErrorBoundary>
  </StrictMode>,
);
