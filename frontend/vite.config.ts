import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'path';

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), 'VITE_');
  // 资源前缀：Portal 部署时可配置为子路径
  const basePath = env.VITE_BASE_PATH || '/';

  return {
    base: basePath,
    plugins: [react()],
    resolve: {
      alias: { '@': path.resolve(__dirname, 'src') },
    },
    server: {
      port: 3000,
      // 开发环境代理后端 API，避免 CORS
      proxy: {
        '/api': {
          target: 'http://localhost:8000',
          changeOrigin: true,
        },
        // Portal 子路径模式联调：/apps/agents/api/* -> /api/*
        '/apps/agents/api': {
          target: 'http://localhost:8000',
          changeOrigin: true,
          rewrite: (path) => path.replace(/^\/apps\/agents/, ''),
        },
      },
    },
    build: {
      // 分包：antd + react 独立 chunk
      rollupOptions: {
        output: {
          manualChunks: {
            'vendor-react': ['react', 'react-dom', 'react-router-dom'],
            'vendor-antd': ['antd', '@ant-design/icons'],
          },
        },
      },
    },
  };
});
