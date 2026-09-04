/// <reference types="vitest/config" />
import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';

// The dashboard consumes the shared FastAPI backend. In development we proxy
// `/v1` REST calls and the `/v1/stream` WebSocket to the API so the frontend
// can use same-origin relative URLs (configurable via VITE_API_TARGET).
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '');
  const API_TARGET = env.VITE_API_TARGET || 'http://localhost:8000';

  return {
    plugins: [react()],
    build: {
      rollupOptions: {
        output: {
          manualChunks: {
            react: ['react', 'react-dom', 'react-router-dom'],
            leaflet: ['leaflet', 'react-leaflet'],
            charts: ['recharts'],
          },
        },
      },
    },
    server: {
      port: 5173,
      proxy: {
        '/v1': {
          target: API_TARGET,
          changeOrigin: true,
          ws: true,
        },
      },
    },
    test: {
      globals: true,
      environment: 'jsdom',
      setupFiles: ['./vitest.setup.ts'],
      css: false,
      include: ['src/**/*.{test,spec}.{ts,tsx}'],
    },
  };
});
