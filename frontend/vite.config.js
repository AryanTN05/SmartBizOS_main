import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

// Vite config for SmartBiz OS frontend.
// - React fast-refresh plugin
// - Dev server on :5173
// - /api proxied to FastAPI backend at :8000 so cookies stay same-origin in dev.
// - `@/*` alias → `src/*`
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, 'src'),
    },
  },
  server: {
    port: 5173,
    strictPort: false,
    // Bind to 0.0.0.0 so external tunnels (ngrok, Cloudflare) can reach us.
    host: true,
    // Vite blocks unknown Host headers by default. Allow ngrok's tunnel
    // domains so external visitors can reach us during a demo share.
    allowedHosts: ['.ngrok.io', '.ngrok-free.app', '.ngrok-free.dev', '.ngrok.app', '.ngrok.dev', '.trycloudflare.com'],
    proxy: (() => {
      // Default backend port matches the Makefile / Dockerfile / Render config
      // (uvicorn's default 8000). Override locally with BACKEND_PORT=8001
      // (e.g. when 8000 is held by another OS user). No code change needed.
      const backendPort = process.env.BACKEND_PORT || '8000';
      const target = `http://localhost:${backendPort}`;
      return {
        '/api': { target, changeOrigin: false },
        // Backend Lara endpoints live under /lara-smartbiz/* so they don't
        // collide with the SPA's /lara route. ws: true is needed for the
        // /lara-smartbiz/voice WebSocket.
        '/lara-smartbiz': { target, changeOrigin: false, ws: true },
      };
    })(),
  },
  build: {
    sourcemap: true,
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test/setup.js'],
  },
});
